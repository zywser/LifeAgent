"""LangGraph 节点定义。

五个角色：supervisor → planner → retriever → worker → reviewer。
- supervisor：入口空壳
- planner：把用户需求拆成子任务（LLM，async）
- retriever：从向量库召回笔记和记忆（纯检索，不调 LLM）
- worker：生成回答并识别业务意图（LLM，async + 真流式）
- reviewer：质检回答，决定重试或结束
"""
import asyncio
import json
import re

from zoneinfo import ZoneInfo
_BJ = ZoneInfo("Asia/Shanghai")
from langchain_core.messages import HumanMessage, SystemMessage
from .state import AgentState
from .tools import TOOLS
from ..llm import llm
from ..vector_store.factory import get_notes_store, get_memory_store


def _text(response) -> str:
    return response.content if hasattr(response, "content") else str(response)


def _extract_json_list(raw: str) -> list[str]:
    """从 LLM 输出中稳健地提取 JSON 数组。"""
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.S)
    candidate = m.group(1) if m else raw
    start, end = candidate.find("["), candidate.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON array found")
    plan = json.loads(candidate[start:end + 1])
    if not isinstance(plan, list):
        raise ValueError("not a list")
    return [str(x) for x in plan]


def _extract_json_object(raw: str) -> dict:
    """从 LLM 输出中稳健地提取 JSON 对象。"""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    candidate = m.group(1) if m else raw
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found")
    data = json.loads(candidate[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data


# ===== 资料问答相关工具函数 =====

# 问句里的"个人资料壳词"：检索前剥掉，避免"我上传了/查看我的资料"这类壳词稀释向量相似度
_PERSONAL_SHELL_RE = re.compile(
    r"我上传了|我上传的|我上传过|我上传|查看我的资料|看下我的资料|看看我的资料|我的资料里|"
    r"我的资料中|我的资料|我的笔记里|我的笔记|我笔记里|我笔记|我的简历里|我的简历|我简历|"
    r"我之前说的|我之前说过|我之前记过|我之前写过|我之前|我记过的|我记过|我记录过|"
    r"资料页|上传的文件|我上传的文件"
)


def strip_personal_shell(query: str) -> str:
    """剥离问句里的个人资料壳词，返回核心检索词；无壳词时原样返回。"""
    core = _PERSONAL_SHELL_RE.sub("", query).strip(" ，。、？?！!；;：:")
    return core


# 资料类意图信号词：命中即视为"问用户自己的资料/个人信息"，用于无召回防编造防线
PERSONAL_QUERY_HINTS = (
    "我的资料", "我上传", "我的简历", "我简历", "我的笔记", "我笔记",
    "我之前", "我记过", "我叫", "我的名字", "我名字", "查看资料",
    "看下资料", "看看资料", "我的档案", "我做过什么", "我做了什么",
    "我的信息", "我的个人", "我是什么名字", "我姓", "我叫什么",
)


def is_personal_data_query(query: str) -> bool:
    """是否资料类问题（问用户自己的资料/个人信息/上传内容）。"""
    return any(h in query for h in PERSONAL_QUERY_HINTS)


def _format_retrieved(docs, fallback: str) -> str:
    """把检索结果格式化为带来源文件名（若有）的文本。"""
    if not docs:
        return fallback
    lines = []
    for d in docs:
        fname = (d.metadata or {}).get("filename", "")
        prefix = f"【{fname}】" if fname else "【个人笔记】"
        lines.append(f"{prefix}\n{d.page_content}")
    return "\n\n".join(lines)


def supervisor(state: AgentState) -> dict:
    return {
        "retry_count": state.get("retry_count", 0),
        "subtask_results": state.get("subtask_results", []),
        "next_step": "planner",
    }


async def planner(state: AgentState) -> dict:
    history = state.get("history_text", "") or ""
    prompt = (
        f"你是任务规划师。把用户需求拆成可执行子任务，最多3个，只输出 JSON 数组，不要任何解释。\n"
        f"拆解规则：\n"
        f"1. 问候、闲聊、简单提问（如「你是谁」「你好」「在吗」「今天怎么样」「你都会什么」等一句话就能回答的问题），"
        f"只输出一个子任务：[\"直接回答用户\"]，不要拆多步、不要安排查询\n"
        f"2. 只有用户明确要求做多件事、或任务本身是多步骤操作时，才拆成多个子任务，且子任务之间要有真实分工\n"
        f"3. 不要把「打招呼+回答」拆成多个子任务，能一句话答完的问题永远只拆 1 个\n"
        f"4. 用户可能在追问上一轮的话题（如只说「有哪些风险」但上文在讨论某个项目），"
        f"遇到指代不清时结合下面的对话历史判断指什么，能合并成一个子任务就不要拆多\n"
    )
    if history:
        prompt += f"对话历史：\n{history}\n"
    prompt += f"需求：{state['query']}"
    try:
        resp = await llm.ainvoke([
            SystemMessage(content="你负责严谨拆解生活任务，只输出 JSON 数组。"),
            HumanMessage(content=prompt),
        ])
        plan = _extract_json_list(_text(resp))[:3]
        if not plan:
            raise ValueError("empty plan")
    except Exception:
        plan = ["理解需求与约束", "结合个人知识与历史经验制定方案", "校验预算与可执行性"]
    return {
        "plan": plan,
        "current_subtask": str(plan[0]),
        # 重置执行状态：subtask_index 从 0 开始，清空旧结果和工具调用
        "subtask_index": 0,
        "subtask_results": [],
        "tool_calls": [],
        "draft_answer": "",
        "next_step": "retriever",
    }


def retriever(state: AgentState) -> dict:
    """检索个人笔记与历史经验（不调 LLM）。

    升级点（资料联动强化）：
    - k 提到 6，覆盖更多候选片段；
    - 问句"壳词剥离"：首次检索无结果时，剥掉"我上传了/我的资料/我之前"等壳词再检一次；
    - 检索结果带来源文件名（metadata.filename），回答时可说明"来自 XX 资料"；
    - 写入 notes_found / memory_found 命中标记，供"资料类问题无召回不编造"防线使用。
    """
    uid = int(state["uid"])
    query = state["query"]

    notes = get_notes_store(uid).similarity_search(query, k=6)
    core = strip_personal_shell(query)
    if not notes and core and core != query:
        notes = get_notes_store(uid).similarity_search(core, k=6)

    memories = get_memory_store(uid).similarity_search(query, k=6)
    if not memories and core and core != query:
        memories = get_memory_store(uid).similarity_search(core, k=6)

    return {
        "knowledge_context": _format_retrieved(notes, "暂无个人笔记"),
        "memory_context": _format_retrieved(memories, "暂无历史经验"),
        "notes_found": bool(notes),
        "memory_found": bool(memories),
        "next_step": "executor",
    }


EXECUTOR_SYSTEM = """你是 Life Agent，一个像朋友一样陪用户安排生活的助手。
说话要自然、口语化，就像微信里跟朋友聊天：
- 不要用 markdown 加粗、列表、✅/❌ 这类符号
- 不要提"子任务""步骤""工具""第几步""本步""根据要求"这类内部过程
- 不要解释自己在做什么、调了什么，直接给结果
- 像真人一样有温度，可以用语气词，但别油腻、别过度热情"""

EXECUTOR_PROMPT = """用户的原始需求：{query}
当前你要负责的那一部分：{subtask}
当前时间：{now}
个人笔记：{notes}
历史经验：{memory}

本次对话之前聊过的内容（供参考：用户可能在追问上一轮的话题，只做上下文理解用，不要重复输出）：
{history}

前面已经聊到的内容（供参考，不要重复）：
{prior}

请用自然聊天的口吻完成这一部分，直接输出可以给用户看的内容。
涉及记账、待办、写日记、查实时信息时，直接调用对应工具。
记账区分两种：用户问「花了多少/账单/消费记录/用了多少钱」是查询，必须调用 query_expenses 查账；
只有用户明确说「记一笔/记录了XX元/买了XX花了XX元」才是记录，调用 record_expense。绝不能把查询当记录去写库。
习惯打卡（打卡XX/查看习惯进度）、纪念日（记住XX日子/查倒计时）、喝水（记录喝了几杯）、存钱（查存钱进度/存一笔）、笔记与经验记忆检索（我笔记里/我之前说过）也都可以直接调用对应工具。
重要：用户的习惯、纪念日、喝水、存钱、笔记、记忆都是个人数据，你并不掌握这些内容，凡是用户明确询问这类个人数据，必须先调用对应的查询工具拿到真实结果再回答，绝不能凭猜测编造。
但不要主动查询个人数据：问候、闲聊、自我介绍（如「你是谁」「你好」「你都会什么」）这类不需要个人数据的场景，直接自然回答即可，禁止调用任何工具。
【个人笔记】可能是简历、技术方案、规范文档、计划书等任何用户上传的资料，不仅限于生活笔记，回答前先看它。
回答资料类问题（用户问自己上传的资料/文件内容/简历/名字/技术方案/规范文档/项目计划里的内容，如实施时间节点、责任分工、分类逻辑、权限、范围等）：
1. 只能依据上面的【个人笔记】与【历史经验】回答，可以提到来源文件名
2. 资料里没有的，明确说「你的资料里没找到这部分，可以在资料页上传后再问我」，绝不编造、绝不把训练记忆或搜索结果当成用户个人资料
3. 个人资料类问题禁止调用 web_search
4. 问句里有「什么时候/时间/几点」并不等于查纪念日：只有明确提到「纪念日/生日/倒计时/还有几天/XX日子」才算查纪念日；问的是资料内容里的时间安排（如实施时间节点、计划周期）时，直接从【个人笔记】里找答案回答，不要调用 query_anniversary
{web_search_rule}"""

# 联网开关对应的规则文案：开启时保持"必须联网搜最新信息"，关闭时反转成"禁止调用"
WEB_SEARCH_RULE_ON = "另外：用户问到具体产品、新品的评价/价格/参数/发布情况（如「XX手机怎么样」「XX手机值不值得买」「XX新出了吗」），或任何可能是最新消息的问题时，你的训练知识可能已经过时，必须调用 web_search 联网搜索最新信息后再回答，绝不能凭记忆说「还没发布」「没有这款」。"
WEB_SEARCH_RULE_OFF = "本次对话联网搜索已关闭：即使问到产品/新品/实时信息（天气、车票、新闻等），也不要调用 web_search，如实说明暂时无法联网查询，其余照常回答。"

# executor 单次 LLM 流式调用的超时（秒）：DashScope 限流/网络卡顿时流式可能长时间无 token，
# 没有超时会导致节点挂起、SSE 一直"执行中"（实测 Executor 卡到第 9 次）。超时后跳过该子任务继续链路。
EXECUTOR_TIMEOUT = 60


async def executor(state: AgentState) -> dict:
    """循环节点：每次执行 plan 里的一个子任务。"""
    plan = state.get("plan", [])
    idx = state.get("subtask_index", 0)
    # 安全保护：index 超出范围（或异常膨胀）直接结束，杜绝无限循环
    if idx >= len(plan) or idx > 6:
        return {"next_step": "synthesizer"}

    current = plan[idx]
    prior_results = state.get("subtask_results", [])
    prior_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(prior_results)) or "（暂无）"

    bound_llm = llm.bind_tools(TOOLS)
    from datetime import datetime
    now = datetime.now(_BJ).strftime("%Y-%m-%d %H:%M %A")
    web_search_enabled = bool(state.get("web_search_enabled", True))
    prompt = EXECUTOR_PROMPT.format(
        query=state["query"],
        subtask=current,
        now=now,
        notes=state.get("knowledge_context", ""),
        memory=state.get("memory_context", ""),
        history=state.get("history_text", "") or "（暂无）",
        prior=prior_text,
        web_search_rule=WEB_SEARCH_RULE_ON if web_search_enabled else WEB_SEARCH_RULE_OFF,
    )

    final_chunk = None
    try:
        # LLM 超时兜底：流式调用挂起（限流/网络/模型侧长时间无 token）时
        # EXECUTOR_TIMEOUT 秒后跳过该子任务，不让整条链路卡死
        async with asyncio.timeout(EXECUTOR_TIMEOUT):
            async for chunk in bound_llm.astream([
                SystemMessage(content=EXECUTOR_SYSTEM),
                HumanMessage(content=prompt),
            ]):
                # AIMessageChunk 支持 + 合并，自动拼接 tool_call_chunks
                final_chunk = chunk if final_chunk is None else final_chunk + chunk
    except asyncio.TimeoutError:
        result = "（这一部分获取回答超时，先跳过；如果确实需要，可以换个说法再问一次）"
        new_tool_calls = []
        results = list(prior_results)
        results.append(result)
        all_tool_calls = list(state.get("tool_calls", []))
        return {
            "subtask_results": results,
            "current_subtask": current,
            "subtask_index": idx + 1,
            "tool_calls": all_tool_calls,
            "next_step": "synthesizer",
        }

    result = final_chunk.content if final_chunk else ""
    new_tool_calls = list(final_chunk.tool_calls) if final_chunk else []

    results = list(prior_results)
    results.append(result)
    # 累积多轮 executor 的工具调用（不是覆盖）
    all_tool_calls = list(state.get("tool_calls", []))
    all_tool_calls.extend(new_tool_calls)

    return {
        "subtask_results": results,
        "current_subtask": current,
        "subtask_index": idx + 1,
        "tool_calls": all_tool_calls,
        "next_step": "synthesizer",
    }


SYNTH_SYSTEM = """你是一个把零散信息整理成自然回复的助手。
你的工作是把几个片段串成一段像朋友聊天一样的话，直接发给用户。
要求：
- 用日常口语，不要 markdown 加粗、不要列表符号、不要 ✅❌
- 不要出现"子任务""第X步""根据要求""结果如下"这类话
- 信息要自然地融进句子里，像真人在说话
- 如果内容已经足够自然，轻微润色即可，不要过度加工"""

SYNTH_PROMPT = """用户问的是：{query}

下面是几个片段的内容，把它们整理成一段自然、连贯、口语化的回复：
{parts}

直接输出整理后的回复本身，不要任何前缀说明。"""


async def synthesizer(state: AgentState) -> dict:
    """汇总所有子任务结果。"""
    valid = [r for r in state.get("subtask_results", []) if r and r.strip()]

    # 只有 0 或 1 个有效结果时不调 LLM，直接用（节省成本、避免冗余）
    if len(valid) <= 1:
        return {"draft_answer": valid[0] if valid else "", "next_step": "reviewer"}

    parts = "\n".join(f"{i+1}. {r}" for i, r in enumerate(valid))
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=SYNTH_SYSTEM),
            HumanMessage(content=SYNTH_PROMPT.format(query=state["query"], parts=parts)),
        ])
        answer = _text(resp)
    except Exception:
        # 汇总失败：简单拼接兜底
        answer = "\n".join(valid)

    return {"draft_answer": answer, "next_step": "reviewer"}


REVIEWER_SYSTEM = "你是严格的质量审核员。先判断回答是否真正解决了用户的核心问题，再打分。只输出 JSON，不要任何解释。"

REVIEWER_PROMPT = """评估回答是否解决了用户的核心问题。分数必须与理由严格一致。

用户问题：{query}
待评估回答：
{answer}

评分标准：
- 9-10：直接、准确、像真人聊天一样自然地回答了用户
- 7-8：解决了主要问题，仅有小瑕疵
- 5-6：触及了问题但没解决核心诉求，或答非所问、遗漏关键点
- 0-4：空洞、拒绝回答、完全不相关

硬性约束（必须遵守）：
- 如果理由里指出了"没解决核心问题/答非所问/信息缺失"这类严重问题，score 最高只能给 6，绝不允许给 7 以上
- 回答简短但直接、自然、完整地解决了用户问题（包括问候、闲聊的得体应答），给 8 分以上，不得因"太简单""没展开""没提到用户个人数据"而打回重试
- 打回重试只针对真正的缺陷：答非所问、遗漏用户明确要的内容、机器话术、空洞无物
- 如果回答里满是"子任务/步骤/根据要求/结果如下"这类机器话术，或大段 markdown 加粗和列表，扣 1-2 分
- 打分前先自问：用户看完这段话，感觉像朋友在说话吗？他的问题被解决了吗？

只输出 JSON：
{{"score": 7, "reason": "一句话说明扣分点或通过理由"}}"""

PASS_SCORE = 7
MAX_RETRIES = 3

# 质检一致性钳制（代码级兜底）：
# LLM 打分偶发出现"理由批评严厉、分数却很高"的不一致（如 reason 说"没解决核心问题"
# 却给 8 分）。这里用信号词规则强制分数与理由一致：理由命中严重缺陷时最高只能给
# PASS_SCORE-1（6 分），与 REVIEWER_PROMPT 里的软约束构成"prompt 约束 + 代码强制"双保险。
SEVERE_DEFECT_KEYWORDS = (
    "未解决", "没解决", "没有解决", "答非所问", "没有回答", "没回答",
    "没理解", "没有理解", "缺失", "遗漏", "编造", "瞎编", "凭空",
    "空洞", "不符", "答错", "拒绝回答", "机器话术", "不相关",
    "完全没有", "基本服务缺失", "关键信息", "未直接回答", "没有满足",
    "错误信息", "没有包含", "答不上", "未涉及", "偏离", "跑题",
)


def clamp_score_for_reason(score: int, reason: str) -> int:
    """分数与理由一致性强制：理由命中严重缺陷信号词时，分数最高不超过 PASS_SCORE-1。"""
    if score > PASS_SCORE - 1 and any(k in reason for k in SEVERE_DEFECT_KEYWORDS):
        return PASS_SCORE - 1
    return score


async def reviewer(state: AgentState) -> dict:
    """质检 synthesizer 的汇总：≥7 通过，否则回 planner，最多重试 MAX_RETRIES 次。"""
    answer = state.get("draft_answer", "") or ""
    tool_calls = state.get("tool_calls", []) or []
    retries = state.get("retry_count", 0)
    # 资料类问题重试上限降到 1：答案来源明确（用户自己上传的资料），一次重试足够，
    # 多轮打回只会放大响应时间（实测资料问答曾 Planner×4 / Executor×8）
    max_retries = 1 if is_personal_data_query(state.get("query", "")) else MAX_RETRIES

    # 模型调用了工具：正文为空是正常的（意图在 tool_calls 里），直接通过，
    # 工具结果由 chat.py 执行后作为回答。不能把这种情况误判成"没理解需求"。
    if tool_calls:
        names = ", ".join(tc.get("name", "?") for tc in tool_calls)
        return {"final_answer": answer, "review_score": 9,
                "review_reason": f"模型调用了工具：{names}，直接通过",
                "next_step": "finish", "error": ""}

    # 幻觉防线（代码级）：资料类问题（问自己的资料/上传内容/个人信息）
    # 且链路检索没有任何命中（notes_found/memory_found 均 False）时，
    # 不允许模型拿训练记忆或搜索结果编造用户个人资料——直接以"未找到"结束，
    # 不浪费一次 LLM 打分，也不把编造内容放行。
    if is_personal_data_query(state.get("query", "")) \
            and not state.get("notes_found") and not state.get("memory_found"):
        return {"final_answer": "我在你的资料里没找到这部分内容。可以到「我的资料」页上传相关文件后再问我，或者换个说法再试试～",
                "review_score": 0,
                "review_reason": "资料类问题无召回，禁止编造个人资料",
                "next_step": "finish", "error": ""}

    # 只有正文为空且没有工具调用时，才是真正没理解：不浪费 LLM 调用
    if not answer:
        if retries >= max_retries:
            return {"final_answer": "抱歉，我没理解你的需求，能再描述一下吗？",
                    "review_score": 0, "review_reason": "空回答",
                    "next_step": "finish", "error": ""}
        return {"retry_count": retries + 1, "review_score": 0,
                "review_reason": "空回答", "next_step": "planner"}

    score, reason = 0, ""
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=REVIEWER_SYSTEM),
            HumanMessage(content=REVIEWER_PROMPT.format(query=state["query"], answer=answer)),
        ])
        verdict = _extract_json_object(_text(resp))
        score = int(verdict.get("score", 0))
        reason = str(verdict.get("reason", ""))
        # 代码级一致性钳制：理由批评严厉时不允许高分，与 prompt 约束双保险
        score = clamp_score_for_reason(score, reason)
    except Exception:
        # 打分本身失败：默认放行，避免卡死整个链路
        score, reason = PASS_SCORE, "打分失败，默认放行"

    if score >= PASS_SCORE:
        return {"final_answer": answer, "review_score": score,
                "review_reason": reason, "next_step": "finish", "error": ""}

    if retries >= max_retries:
        # 重试次数用完，兜底放行，避免无限循环
        return {"final_answer": answer, "review_score": score,
                "review_reason": f"{reason}（已达重试上限）",
                "next_step": "finish", "error": ""}

    return {"retry_count": retries + 1, "review_score": score,
            "review_reason": reason, "next_step": "planner"}
