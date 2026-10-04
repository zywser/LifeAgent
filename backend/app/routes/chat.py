import json
import re
import uuid
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from ..deps import get_current_user
from ..db.models import User, MemoryItem
from ..db.session import SessionLocal
from ..graph.build import build_graph
from ..graph.tools import TOOL_MAP
from ..vector_store.factory import get_memory_store

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


def sse(event: str, data: dict):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def infer_extra_tools(message: str, called: list[dict]) -> list[dict]:
    """模型漏调用工具时的关键词兜底。

    模型在长提示下偶尔会凭记忆编造"已完成/已记录"而不调工具，这里按消息里的
    明确业务意图补调对应工具（写动作保证真实落库、查询保证有据可答）。
    只处理强信号，避免误触发。
    """
    names = {tc.get("name") for tc in called}
    extra = []
    m = message

    # 习惯打卡（写）：打卡X
    if "打卡" in m and "check_habit" not in names and "query_habits" not in names:
        mm = re.search(r"打卡\s*(.{1,10}?)(?:，|,|。|！|？|；|;|$|顺便|然后|和)", m)
        if mm and not any(k in mm.group(1) for k in ("查询", "看看", "多少", "情况")):
            extra.append({"name": "check_habit", "args": {"habit_name": mm.group(1).strip()}})

    # 习惯查询（查）
    if any(k in m for k in ("习惯进度", "打卡情况", "连续几天", "习惯怎么样")) and \
            "query_habits" not in names and "check_habit" not in names:
        extra.append({"name": "query_habits", "args": {}})

    # 喝水（写）：喝(了)N杯
    if ("杯" in m and "水" in m) and "record_water" not in names and "query_water" not in names:
        mm = re.search(r"喝(?:了|过)?\s*(\d{1,2})\s*杯", m)
        if mm:
            extra.append({"name": "record_water", "args": {"cups": int(mm.group(1))}})

    # 喝水（查）：喝了几杯/喝水情况
    if any(k in m for k in ("喝了几杯", "喝水情况", "喝了多少", "今天喝水")) and \
            "query_water" not in names and "record_water" not in names:
        extra.append({"name": "query_water", "args": {}})

    # 纪念日（查）
    if ("纪念日" in m or "生日" in m) and "query_anniversary" not in names and \
            "add_anniversary" not in names:
        if any(k in m for k in ("有哪些", "几个", "什么纪念日", "还有几天", "什么时候", "查一下", "查查", "看看")):
            extra.append({"name": "query_anniversary", "args": {}})

    # 纪念日（写）：记住/记一下/添加 + M月D日
    if any(k in m for k in ("记住", "记一下", "添加", "设个")) and \
            "add_anniversary" not in names and "query_anniversary" not in names:
        dm = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", m)
        if dm:
            nm = re.search(r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]\s*(?:是)?\s*([^，。,。！？、\s]{1,10})", m)
            name = nm.group(1) if nm else "纪念日"
            extra.append({
                "name": "add_anniversary",
                "args": {"name": name, "event_date": f"{int(dm.group(1)):02d}-{int(dm.group(2)):02d}"},
            })

    # 存钱（查）
    if any(k in m for k in ("存钱进度", "存钱目标", "还差多少", "每天要存", "存钱情况")) and \
            "query_savings" not in names and "update_savings" not in names:
        extra.append({"name": "query_savings", "args": {}})

    return extra


async def execute_tool_calls(tool_calls: list[dict], uid: int) -> list[str]:
    """执行模型在 worker 里决定的工具调用（reviewer 已通过）。

    uid 在这里注入（模型不填 uid）；工具是同步函数，ainvoke 会自动走线程池。
    """
    results = []
    for tc in tool_calls:
        tool = TOOL_MAP.get(tc.get("name"))
        if tool is None:
            continue
        args = dict(tc.get("args", {}))
        args["uid"] = uid
        try:
            results.append(await tool.ainvoke(args))
        except Exception:
            continue
    return results


@router.post("/chat")
async def chat(req: ChatRequest, user: User = Depends(get_current_user)):
    session_id = req.session_id or "default"
    graph = await build_graph(user.id, session_id)
    # 每轮请求用唯一 thread_id：避免 checkpointer 把上一轮的中间状态
    # （旧 plan / subtask_results / tool_calls）带进新问题，造成串话和工具误判
    thread_id = f"u{user.id}_{session_id}_{uuid.uuid4().hex}"
    config = {"configurable": {"thread_id": thread_id}}

    async def stream():
        try:
            async for event in graph.astream_events(
                {"query": req.message, "uid": user.id, "retry_count": 0},
                config=config,
                version="v2",
            ):
                kind, name = event.get("event", ""), event.get("name", "")
                if kind == "on_chain_start" and name in {"supervisor", "planner", "retriever", "executor", "synthesizer", "reviewer"}:
                    yield sse("node_start", {"node": name})
                elif kind == "on_chain_end" and name in {"supervisor", "planner", "retriever", "executor", "synthesizer", "reviewer"}:
                    yield sse("node_end", {"node": name})
                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    text = getattr(chunk, "content", "") if chunk else ""
                    if text:
                        yield sse("token", {"text": text})

            # 链路结束后拿最终 state
            state = await graph.aget_state(config)
            values = state.values or {}
            answer = values.get("final_answer", "") or ""
            tool_calls = values.get("tool_calls", []) or []

            # reviewer 通过后才执行工具（拿 uid）；打回重试不会重复写库
            # 模型漏调用时按消息意图补调（兜底，保证动作真实落库/查询有据可答）
            all_tool_calls = list(tool_calls) + infer_extra_tools(req.message, tool_calls)
            tool_results = await execute_tool_calls(all_tool_calls, user.id)
            # plan 的多个子任务可能对同一问题重复调用工具，结果去重
            seen = set()
            tool_results = [r for r in tool_results if not (r in seen or seen.add(r))]

            # 工具结果优先：模型说话+调工具时，正文常是"稍等/我帮你查一下"这类
            # 过渡语，真正的内容在工具结果里，直接以工具结果作为回答主体
            if tool_results:
                answer = "\n".join(tool_results)
            elif not answer:
                answer = "（完成）"

            # 仅"工具调用驱动的回答"沉淀为长期记忆：模型未调工具、凭猜测输出的
            # 内容不写记忆，避免把编造的"已完成/已记录"当经验沉淀（闲聊历史由
            # 对话列表保存，不占用经验记忆）
            if tool_results and answer:
                mem_content = f"用户问题：{req.message}\n任务摘要：{answer}"
                get_memory_store(user.id).add_texts(
                    [mem_content],
                    metadatas=[{"user_id": user.id, "type": "memory"}],
                )
                # 同步落库，供"经验记忆"页面展示
                try:
                    mdb = SessionLocal()
                    try:
                        mdb.add(MemoryItem(user_id=user.id, content=mem_content, kind="memory"))
                        mdb.commit()
                    finally:
                        mdb.close()
                except Exception:
                    pass
            yield sse("final", {"answer": answer})
        except Exception as exc:
            yield sse("error", {"message": str(exc)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
