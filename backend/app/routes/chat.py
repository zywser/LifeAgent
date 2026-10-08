import json
import re
import uuid
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage
from ..deps import get_current_user
from ..db.models import User, MemoryItem
from ..db.session import SessionLocal
from ..graph.build import build_graph
from ..graph.tools import TOOL_MAP
from ..llm import llm
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

    # —— 账单查询（查）——
    # 防模型把"花了多少钱/账单"误调 record_expense 记一笔（曾实测误记 ¥0.0 进账单）
    expense_query_words = ("花了多少", "账单", "支出情况", "消费", "用了多少", "花费", "花了什么",
                           "这个月花", "上个月花", "今天花", "查账", "流水", "花销", "开销",
                           "花了多少钱", "记账情况")
    expense_write_words = ("记一笔", "记一下", "记录", "报销", "记账", "付了", "买了", "存一笔")
    if any(k in m for k in expense_query_words) and not any(k in m for k in expense_write_words) \
            and "query_expenses" not in names and "record_expense" not in names:
        if "这个月" in m or "本月" in m:
            _days = 30
        elif "上个月" in m:
            _days = 30
        elif "今天" in m or "昨天" in m:
            _days = 1
        elif "最近" in m or "这周" in m or "本周" in m:
            _days = 7
        else:
            _days = 7
        extra.append({"name": "query_expenses", "args": {"days": _days}})

    # —— 日常生活联网搜索兜底（宽触发）——
    # 模型训练知识有滞后，凡带查询意图、非问候闲聊、非个人数据操作的问题，
    # 模型漏调 web_search 时一律补调，宁可多搜一次，也不用过时知识硬答。
    # 覆盖面：车票/机票/酒店/天气/新闻/汇率等实时信息，产品/新品咨询，
    # 以及吃喝玩乐、菜谱、政策、法规、健康、数码、时事、景点、赛事等方方面面。
    query_intent = ("查", "查询", "查查", "看看", "搜", "搜一下", "怎么样", "好不好", "值不值得",
                    "多少钱", "几点", "什么时候", "有没有", "有吗", "怎么", "哪里", "哪家", "哪个",
                    "什么", "推荐", "了解", "介绍", "区别", "对比", "价格", "值得", "最新", "有哪些",
                    "是啥", "去哪儿", "啥时候", "多少", "能买到", "去不去", "好用吗", "哪款")
    chitchat = ("你是谁", "你会什么", "你能做什么", "你都会什么", "介绍一下你", "你的功能",
                "你能干嘛", "你会干嘛", "你是谁呀", "你是什么", "能帮我什么")
    personal = ("笔记", "记忆", "经验", "习惯", "纪念日", "存钱", "喝水", "待办", "账单", "流水",
                "日记", "周报", "打卡", "记住", "记一下", "记录", "写日记", "喝了", "花了", "创建",
                "添加", "删除", "修改", "提醒我", "设个", "记账", "收入", "支出", "我的")
    if any(k in m for k in query_intent) and not any(k in m for k in chitchat) \
            and not any(k in m for k in personal) and "web_search" not in names:
        extra.append({"name": "web_search", "args": {"query": m}})

    return extra


SUMMARIZE_SYSTEM = (
    "你是 Life Agent 的回复整理器。下面有一段从联网搜索/工具拿到的原始信息，"
    "请把它整理成直接发给用户的一段简洁回复。硬性要求：\n"
    "1. 全部使用简体中文，原文中的英文（含英文摘要、标题、网页文字）一律翻译成中文，不得出现英文段落\n"
    "2. 像朋友聊天一样口语化、自然，不要出现「根据搜索结果」「以下是」「来源显示」这类话\n"
    "3. 只保留真正有用的重点：关键结论、车次/时间/价格/数字/日期，删掉网页正文、日期列表、"
    "页面标签、版权声明、'Read Blog'、'##'、'Home' 等页面噪声\n"
    "4. 长度控制在 150~250 字左右，三四句话讲清要点，末尾可附 1~2 个主要来源链接\n"
    "5. 若原始内容确实没有有用信息，如实说「暂时没查到具体信息」，不要硬凑\n"
    "6. 对「已记录/已记住/已创建/已打卡/未配置」这类简短确认结果，原样保留，不要改写"
)


# 匹配 web_search 返回里的（来源：URL），总结后强制附在末尾，保证前端能转成可点击链接
_SOURCE_RE = re.compile(r"（来源：(https?://[^\s）]+)）")


async def summarize_answer(query: str, results: list[str]) -> str:
    """把工具返回的原始内容整理成简洁中文回复；短确认结果原样返回，避免浪费 LLM。"""
    joined = "\n".join(r for r in results if r and r.strip())
    if not joined:
        return ""
    # 全部是简短确认（如记账/打卡结果），无需总结
    if len(joined) <= 120:
        return joined
    # 提取来源链接（去重保序，最多 5 条），LLM 总结时常会丢掉链接，这里兜底
    urls = list(dict.fromkeys(_SOURCE_RE.findall(joined)))[:5]
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=SUMMARIZE_SYSTEM),
            HumanMessage(content=f"用户问：{query}\n\n原始信息：\n{joined}\n\n直接输出整理后的回复。"),
        ])
        out = (resp.content or "").strip()
        if not out:
            out = joined
        elif urls and not any(u in out for u in urls):
            out = out + "\n\n参考来源：\n" + "\n".join(f"- {u}" for u in urls)
        return out
    except Exception:
        # 总结失败：退回原始拼接（含来源链接），保证有回复
        return joined


async def execute_tool_calls(tool_calls: list[dict], uid: int, message: str = "") -> list[str]:
    """执行模型在 worker 里决定的工具调用（reviewer 已通过）。

    uid 在这里注入（模型不填 uid）；工具是同步函数，ainvoke 会自动走线程池。
    message 用于误调守卫：模型偶发把不相关工具（如查火车票却调 query_anniversary）
    当作个人数据查询，这里按用户消息是否提及对应领域做拦截。
    """
    results = []
    for tc in tool_calls:
        name = tc.get("name")
        tool = TOOL_MAP.get(name)
        if tool is None:
            continue
        # 误调守卫：纪念日查询只在用户明确提到纪念日/生日/倒计时时执行，
        # 防止模型把"查火车票/机票"等误判成查个人纪念日
        if name == "query_anniversary" and not any(
            k in message for k in ("纪念日", "生日", "倒计时", "还有几天", "重要日子", "快到")
        ):
            continue
        args = dict(tc.get("args", {}))
        args["uid"] = uid
        try:
            results.append(await tool.ainvoke(args))
        except Exception as exc:
            # 不静默吞异常：失败原因直接进结果，用户能看到"搜索失败"而不是无回复
            results.append(f"⚠️ 工具「{name}」执行失败：{exc}")
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

            # 模型漏调用时按消息意图补调（兜底，保证动作真实落库/查询有据可答）
            all_tool_calls = list(tool_calls) + infer_extra_tools(req.message, tool_calls)
            tool_results = await execute_tool_calls(all_tool_calls, user.id, req.message)
            # plan 的多个子任务可能对同一问题重复调用工具，结果去重
            seen = set()
            tool_results = [r for r in tool_results if not (r in seen or seen.add(r))]

            # 工具结果优先：模型说话+调工具时，正文常是"稍等/我帮你查一下"这类
            # 过渡语，真正的内容在工具结果里，作为回答主体；
            # 长文本工具结果（如联网搜索）先交给 LLM 总结成简洁中文，
            # 避免把网页原文/英文摘要直接甩给用户
            if tool_results:
                answer = await summarize_answer(req.message, tool_results)
            elif not answer:
                answer = "（完成）"

            # 仅"工具调用驱动的回答"沉淀为长期记忆：模型未调工具、凭猜测输出的
            # 内容不写记忆，避免把编造的"已完成/已记录"当经验沉淀（闲聊历史由
            # 对话列表保存，不占用经验记忆）
            if tool_results and answer:
                mem_content = f"用户问题：{req.message}\n任务摘要：{answer}"
                try:
                    get_memory_store(user.id).add_texts(
                        [mem_content],
                        metadatas=[{"user_id": user.id, "type": "memory"}],
                    )
                except Exception:
                    # 记忆沉淀失败（embedding 限流 / Redis 抖动）不影响本次回答
                    pass
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
