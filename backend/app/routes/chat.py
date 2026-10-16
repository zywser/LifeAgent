import json
import re
import uuid
from urllib.parse import urlparse
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session
from ..deps import get_current_user
from ..db.models import User, MemoryItem, Conversation
from ..db.session import get_db, SessionLocal
from ..graph.build import build_graph
from ..graph.tools import TOOL_MAP
from ..graph.nodes import is_personal_data_query
from ..llm import llm
from ..vector_store.factory import get_memory_store

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    # 联网搜索开关：默认关闭（防幻觉优先，用户可在前端随时打开）
    web_search: bool = False


def sse(event: str, data: dict):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def load_history_text(db: Session, user_id: int, session_id: str | None, current_message: str, limit: int = 10) -> str:
    """读取该会话最近的对话历史（跨轮上下文记忆）。

    session_id 即前端会话的 Conversation.id（追问轮已是真实数字 id；
    新会话首轮是本地占位/空，查不到历史是正常的）。取最近 limit 条
    user/assistant 消息格式化；末尾若正是当前问题则排除（当前问句已在 query 位，
    避免重复且防止把用户原文再当指令位）。内容只作为数据位注入，不改变系统提示。
    """
    if not session_id or not session_id.isdigit():
        return ""
    c = (
        db.query(Conversation)
        .filter(Conversation.id == int(session_id), Conversation.user_id == user_id)
        .first()
    )
    if not c:
        return ""
    try:
        msgs = json.loads(c.messages or "[]")
    except Exception:
        return ""
    lines = []
    for m in msgs[-limit:]:
        role = m.get("role") if isinstance(m, dict) else None
        content = (m.get("content") or "").strip() if isinstance(m, dict) else ""
        if not content:
            continue
        if role == "user":
            if content == current_message:      # 当前问句不喂回
                continue
            lines.append(f"用户：{content}")
        elif role == "assistant":
            lines.append(f"助手：{content}")
    return "\n".join(lines[-limit:])


def infer_extra_tools(message: str, called: list[dict], web_search_enabled: bool = True) -> list[dict]:
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
        # 联网开关关闭时不补 web_search（防止个人资料/普通提问被拿去联网搜出无关内容）；
        # 资料类问题同样不补：联网结果会覆盖用户自己上传的资料回答（防幻觉）
        if web_search_enabled and not is_personal_data_query(m):
            extra.append({"name": "web_search", "args": {"query": m}})

    return extra


SUMMARIZE_SYSTEM = (
    "你是 Life Agent 的回复整理器。下面有一段从联网搜索/工具拿到的原始信息，"
    "请把它整理成直接发给用户的一段简洁回复。硬性要求：\n"
    "1. 全部使用简体中文，原文中的英文（含英文摘要、标题、网页文字）一律翻译成中文，不得出现英文段落\n"
    "2. 像朋友聊天一样口语化、自然，不要出现「根据搜索结果」「以下是」「来源显示」这类话\n"
    "3. 只保留真正有用的重点：关键结论、车次/时间/价格/数字/日期，删掉网页正文、日期列表、"
    "页面标签、版权声明、'Read Blog'、'##'、'Home' 等页面噪声\n"
    "4. 长度控制在 150~250 字左右，三四句话讲清要点；如需附来源链接，必须写成 "
    "「[来源名称](链接)」形式（如 [中国天气网](https://www.weather.com.cn/...)），"
    "禁止直接输出一长串 http(s) 裸链接\n"
    "5. 若原始内容确实没有有用信息，如实说「暂时没查到具体信息」，不要硬凑\n"
    "6. 对「已记录/已记住/已创建/已打卡/未配置」这类简短确认结果，原样保留，不要改写"
)


# 匹配正文里的裸 http(s) 链接（前面不是 "]("，避免误伤 markdown 链接内部）
_BARE_URL_RE = re.compile(r"(?<!\]\()(https?://[^\s，。；、）\)」》]+)")


# 匹配 web_search 返回里的"- 标题：内容（来源：URL）"，同时捕获标题与 URL；
# 总结后以 markdown 链接 [标题](URL) 附在末尾，前端 linkify 已支持 markdown 链接
# 转可点击 <a>，显示的是标题而不是一长串域名（用户实测只有裸 URL 的体验问题）。
_SOURCE_RE = re.compile(r"- ([^\n：]{0,80})[：:][\s\S]*?（来源：(https?://[^\s）]+)）")


def _source_link(pair: tuple[str, str]) -> str:
    title, url = pair
    # 标题里的 markdown 链接语法字符会破坏 [标题](url) 结构，先清掉
    title = re.sub(r"[\[\]()]", "", title).strip()
    if not title:
        # 无标题结果（Tavily 某些结果标题为空）：显示域名而不是裸 URL
        try:
            title = urlparse(url).netloc or url
        except Exception:
            title = url
    return f"- [{title}]({url})"


def _linkify_bare_urls(text: str, pairs: list[tuple[str, str]]) -> str:
    """把正文里的裸 URL 转成 [名称](链接)（问题 A 兜底）。

    LLM 总结时可能把来源 URL 原样写进正文（不带标题），这里用工具原文提取的
    pairs 做映射：有标题用标题，无标题退化为域名；pairs 里没有的 URL 统一转
    成域名链接。只替换裸 URL（前面不是 "](" 的），已是 markdown 链接的不动。
    """
    if not text:
        return text
    url_title = {}
    for title, url in pairs:
        if url and url not in url_title:
            url_title[url] = title
    return _BARE_URL_RE.sub(
        lambda m: _source_link((url_title.get(m.group(1), ""), m.group(1)))[2:],
        text,
    )


async def summarize_answer(query: str, results: list[str]) -> str:
    """把工具返回的原始内容整理成简洁中文回复；短确认结果原样返回，避免浪费 LLM。"""
    joined = "\n".join(r for r in results if r and r.strip())
    if not joined:
        return ""
    # 全部是简短确认（如记账/打卡结果），无需总结
    if len(joined) <= 120:
        return joined
    # 提取来源（标题+URL，去重保序，最多 5 条），LLM 总结时常会丢掉链接，这里兜底
    pairs = list(dict.fromkeys(_SOURCE_RE.findall(joined)))[:5]
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=SUMMARIZE_SYSTEM),
            HumanMessage(content=f"用户问：{query}\n\n原始信息：\n{joined}\n\n直接输出整理后的回复。"),
        ])
        out = (resp.content or "").strip()
        if not out:
            out = joined
        elif pairs and not any(u in out for _, u in pairs):
            out = out + "\n\n参考来源：\n" + "\n".join(_source_link(p) for p in pairs)
        # 兜底：LLM 可能把来源 URL 原样写进正文（裸链接），统一转成 [名称](链接)
        return _linkify_bare_urls(out, pairs)
    except Exception:
        # 总结失败：退回原始拼接（含来源链接），同样做裸 URL 转链接处理
        return _linkify_bare_urls(joined, pairs)


NOTES_ANSWER_SYSTEM = (
    "你是 Life Agent。用户问的问题可能能在 ta 上传的资料里找到答案。"
    "下面是从用户资料库检索到的相关内容（带来源文件名）。"
    "请判断这些内容与用户问题是否相关："
    "1. 相关：基于检索内容直接回答（可以提到来源文件名），像朋友聊天一样口语化、简洁；"
    "2. 不相关或内容不足：明确说「你的资料里没找到这部分」，不要编造、不要用训练知识补。"
)


async def answer_from_notes(query: str, notes: str, memory: str) -> str:
    """模型误调工具（如把资料问题当纪念日查询）且工具被守卫拦截时，
    基于已检索到的资料内容重新回答，避免把"我帮你查一下"这类过渡承诺直出给用户。
    只在链路确有召回（knowledge_context 非"暂无"）时调用；失败返回空串走原兜底。
    """
    ctx = notes if notes and notes != "暂无个人笔记" else ""
    mem = memory if memory and memory != "暂无历史经验" else ""
    if not ctx and not mem:
        return ""
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=NOTES_ANSWER_SYSTEM),
            HumanMessage(content=f"用户问：{query}\n\n资料检索结果：\n{ctx}\n{mem}\n\n直接输出回答。"),
        ])
        return (resp.content or "").strip()
    except Exception:
        return ""


async def execute_tool_calls(tool_calls: list[dict], uid: int, message: str = "", web_search_enabled: bool = True) -> list[str]:
    """执行模型在 worker 里决定的工具调用（reviewer 已通过）。

    uid 在这里注入（模型不填 uid）；工具是同步函数，ainvoke 会自动走线程池。
    message 用于误调守卫：模型偶发把不相关工具（如查火车票却调 query_anniversary）
    当作个人数据查询，这里按用户消息是否提及对应领域做拦截。
    web_search_enabled=False 时过滤掉 web_search（开关关闭的第二层拦截，防止模型自行决策）。
    """
    results = []
    for tc in tool_calls:
        name = tc.get("name")
        tool = TOOL_MAP.get(name)
        if tool is None:
            continue
        # 联网开关关闭：即使模型决策了 web_search 也不执行；
        # 资料类问题：无论开关状态，一律不执行 web_search（防止联网内容覆盖用户上传的资料回答）
        if name == "web_search" and (not web_search_enabled or is_personal_data_query(message)):
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


def node_detail(name: str, output) -> dict:
    """从节点返回值里提取可展示的详情（LangGraph v2 事件 data.output 是节点返回的 dict）。"""
    if not isinstance(output, dict):
        return {"node": name}
    detail = {"node": name}
    if name == "planner" and output.get("plan"):
        detail["plan"] = output["plan"]
    elif name == "executor":
        if output.get("current_subtask"):
            detail["current_subtask"] = output["current_subtask"]
        detail["subtask_index"] = output.get("subtask_index")
    elif name == "reviewer":
        detail["review_score"] = output.get("review_score")
        detail["review_reason"] = output.get("review_reason")
        # next_step == "planner" 表示质检未通过、即将重试
        detail["retry"] = output.get("next_step") == "planner"
    return detail


async def run_chat_stream(graph, message: str, uid: int, session_id: str = "default",
                          web_search: bool = False, history_text: str = ""):
    """SSE 事件流生成器（节点状态 / token / 工具调用 / 质检 / 最终结果 / 异常）。

    抽成独立函数便于评测直接注入 fake graph 验证事件序列；
    HTTP 路由只是把它包进 StreamingResponse 的薄包装。
    history_text 为跨轮对话历史（由路由从 conversations 表加载），注入链路供
    planner/executor 理解追问上下文（如"有哪些风险"承接上一轮的"实施时间节点"）。
    """
    # 每轮请求用唯一 thread_id：避免 checkpointer 把上一轮的中间状态
    # （旧 plan / subtask_results / tool_calls）带进新问题，造成串话和工具误判
    thread_id = f"u{uid}_{session_id}_{uuid.uuid4().hex}"
    # metadata 会随 run 一起写入 LangSmith，可在 UI 上按用户/会话检索调用链路
    config = {
        "configurable": {"thread_id": thread_id},
        # 重试安全垫：默认 limit=25 会在"连续低分打回 4 轮"（最坏 1+4×7=29 超步）
        # 恰好触顶报错 Recursion limit reached；提到 60 保证 reviewer 的
        # MAX_RETRIES 兜底能正常走完，而不是把循环报错甩给用户
        "recursion_limit": 60,
        "metadata": {"uid": uid, "session_id": session_id, "thread_id": thread_id, "web_search": web_search},
    }

    try:
        async for event in graph.astream_events(
            {"query": message, "uid": uid, "retry_count": 0, "web_search_enabled": web_search,
             "history_text": history_text},
            config=config,
            version="v2",
        ):
            kind, name = event.get("event", ""), event.get("name", "")
            if kind == "on_chain_start" and name in {"supervisor", "planner", "retriever", "executor", "synthesizer", "reviewer"}:
                yield sse("node_start", {"node": name})
            elif kind == "on_chain_end" and name in {"supervisor", "planner", "retriever", "executor", "synthesizer", "reviewer"}:
                yield sse("node_end", node_detail(name, event.get("data", {}).get("output")))
            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                text = getattr(chunk, "content", "") if chunk else ""
                if text:
                    yield sse("token", {"text": text})
            elif kind == "on_chat_model_end":
                # 模型决策的工具调用（executor 里 bind_tools 产生）：前端可显示"正在调用 XX 工具"
                message_out = event.get("data", {}).get("output")
                calls = getattr(message_out, "tool_calls", None) or []
                for tc in calls:
                    yield sse("tool_call", {
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {}),
                    })

        # 链路结束后拿最终 state
        state = await graph.aget_state(config)
        values = state.values or {}
        answer = values.get("final_answer", "") or ""
        tool_calls = values.get("tool_calls", []) or []

        # 模型漏调用时按消息意图补调（兜底，保证动作真实落库/查询有据可答；
        # 联网开关关闭时不补 web_search）
        all_tool_calls = list(tool_calls) + infer_extra_tools(message, tool_calls, web_search_enabled=web_search)
        tool_results = await execute_tool_calls(all_tool_calls, uid, message, web_search_enabled=web_search)
        # plan 的多个子任务可能对同一问题重复调用工具，结果去重
        seen = set()
        tool_results = [r for r in tool_results if not (r in seen or seen.add(r))]

        # 资料类问题优先基于资料回答：即便 executor 违规决策了 web_search 等工具
        # （执行层已对资料问题硬过滤 web_search，但其他工具结果仍可能出现），
        # 正文主体也不能被联网/工具内容覆盖用户自己上传的资料（防幻觉）。
        ctx = values.get("knowledge_context", "") or ""
        memctx = values.get("memory_context", "") or ""
        notes_answer = ""
        if is_personal_data_query(message) \
                and ((ctx and ctx != "暂无个人笔记") or (memctx and memctx != "暂无历史经验")):
            notes_answer = await answer_from_notes(message, ctx, memctx)

        if tool_results and not notes_answer:
            # 工具结果优先：模型说话+调工具时，正文常是"稍等/我帮你查一下"这类
            # 过渡语，真正的内容在工具结果里，作为回答主体；
            # 长文本工具结果（如联网搜索）先交给 LLM 总结成简洁中文，
            # 避免把网页原文/英文摘要直接甩给用户
            answer = await summarize_answer(message, tool_results)
        else:
            if notes_answer:
                # 资料类问题 + 链路有召回：基于资料直接回答
                answer = notes_answer
            elif tool_calls and (ctx or memctx):
                # 模型决策了工具但执行层全部拦截/失败（典型：把资料问题误当纪念日，
                # query_anniversary 被误调守卫拦下，结果为空）：
                # 若链路有检索召回，基于资料重新回答，不再把"帮你查一下"式过渡语直出。
                notes_answer = await answer_from_notes(message, ctx, memctx)
                if notes_answer:
                    answer = notes_answer
            if not answer:
                answer = "（完成）"

        # 幻觉防线出口兜底（与 reviewer 防线双保险）：
        # 资料类问题 + 链路检索无召回 + 无工具调用时，即便模型输出了编造内容，
        # 最终回答也强制替换为"未找到"，不把幻觉放给用户。
        if not tool_results and is_personal_data_query(message) \
                and not values.get("notes_found") and not values.get("memory_found"):
            answer = "我在你的资料里没找到这部分内容。可以到「我的资料」页上传相关文件后再问我，或者换个说法再试试～"

        # 仅"工具调用驱动的回答"沉淀为长期记忆：模型未调工具、凭猜测输出的
        # 内容不写记忆，避免把编造的"已完成/已记录"当经验沉淀（闲聊历史由
        # 对话列表保存，不占用经验记忆）
        if tool_results and answer:
            mem_content = f"用户问题：{message}\n任务摘要：{answer}"
            try:
                get_memory_store(uid).add_texts(
                    [mem_content],
                    metadatas=[{"user_id": uid, "type": "memory"}],
                )
            except Exception:
                # 记忆沉淀失败（embedding 限流 / Redis 抖动）不影响本次回答
                pass
            # 同步落库，供"经验记忆"页面展示
            try:
                mdb = SessionLocal()
                try:
                    mdb.add(MemoryItem(user_id=uid, content=mem_content, kind="memory"))
                    mdb.commit()
                finally:
                    mdb.close()
            except Exception:
                pass
        yield sse("final", {"answer": answer})
    except Exception as exc:
        # 异常事件带类型，前端可以区分"LLM 超时/向量库不可用/其他"分别提示
        yield sse("error", {"message": str(exc), "error_type": type(exc).__name__})


@router.post("/chat")
async def chat(req: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    graph = await build_graph(user.id, req.session_id or "default")
    history = load_history_text(db, user.id, req.session_id, req.message)
    return StreamingResponse(
        run_chat_stream(graph, req.message, user.id, req.session_id or "default",
                        web_search=req.web_search, history_text=history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
