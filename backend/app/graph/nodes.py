"""LangGraph 节点定义。

五个角色：supervisor → planner → retriever → worker → reviewer。
- supervisor：入口空壳
- planner：把用户需求拆成子任务（LLM，async）
- retriever：从向量库召回笔记和记忆（纯检索，不调 LLM）
- worker：生成回答并识别业务意图（LLM，async + 真流式）
- reviewer：质检回答，决定重试或结束
"""
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


def supervisor(state: AgentState) -> dict:
    return {
        "retry_count": state.get("retry_count", 0),
        "subtask_results": state.get("subtask_results", []),
        "next_step": "planner",
    }


async def planner(state: AgentState) -> dict:
    prompt = (
        f"你是任务规划师。把用户需求拆成可执行子任务，最多3个，只输出 JSON 数组，不要任何解释。\n"
        f"拆解规则：\n"
        f"1. 问候、闲聊、简单提问（如「你是谁」「你好」「在吗」「今天怎么样」「你都会什么」等一句话就能回答的问题），"
        f"只输出一个子任务：[\"直接回答用户\"]，不要拆多步、不要安排查询\n"
        f"2. 只有用户明确要求做多件事、或任务本身是多步骤操作时，才拆成多个子任务，且子任务之间要有真实分工\n"
        f"3. 不要把「打招呼+回答」拆成多个子任务，能一句话答完的问题永远只拆 1 个\n"
        f"需求：{state['query']}"
    )
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
    uid = int(state["uid"])
    notes = get_notes_store(uid).similarity_search(state["query"], k=4)
    memories = get_memory_store(uid).similarity_search(state["query"], k=4)
    note_text = "\n".join(d.page_content for d in notes) or "暂无个人笔记"
    memory_text = "\n".join(d.page_content for d in memories) or "暂无历史经验"
    return {"knowledge_context": note_text, "memory_context": memory_text, "next_step": "executor"}


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

前面已经聊到的内容（供参考，不要重复）：
{prior}

请用自然聊天的口吻完成这一部分，直接输出可以给用户看的内容。
涉及记账、待办、写日记、查实时信息时，直接调用对应工具。
习惯打卡（打卡XX/查看习惯进度）、纪念日（记住XX日子/查倒计时）、喝水（记录喝了几杯）、存钱（查存钱进度/存一笔）、笔记与经验记忆检索（我笔记里/我之前说过）也都可以直接调用对应工具。
重要：用户的习惯、纪念日、喝水、存钱、笔记、记忆都是个人数据，你并不掌握这些内容，凡是用户明确询问这类个人数据，必须先调用对应的查询工具拿到真实结果再回答，绝不能凭猜测编造。
但不要主动查询个人数据：问候、闲聊、自我介绍（如「你是谁」「你好」「你都会什么」）这类不需要个人数据的场景，直接自然回答即可，禁止调用任何工具。
另外：用户问到具体产品、新品的评价/价格/参数/发布情况（如「XX手机怎么样」「XX手机值不值得买」「XX新出了吗」），或任何可能是最新消息的问题时，你的训练知识可能已经过时，必须调用 web_search 联网搜索最新信息后再回答，绝不能凭记忆说「还没发布」「没有这款」。"""


async def executor(state: AgentState) -> dict:
    """循环节点：每次执行 plan 里的一个子任务。"""
    plan = state.get("plan", [])
    idx = state.get("subtask_index", 0)
    # 安全保护：index 超出范围直接结束
    if idx >= len(plan):
        return {"next_step": "synthesizer"}

    current = plan[idx]
    prior_results = state.get("subtask_results", [])
    prior_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(prior_results)) or "（暂无）"

    bound_llm = llm.bind_tools(TOOLS)
    from datetime import datetime
    now = datetime.now(_BJ).strftime("%Y-%m-%d %H:%M %A")
    prompt = EXECUTOR_PROMPT.format(
        query=state["query"],
        subtask=current,
        now=now,
        notes=state.get("knowledge_context", ""),
        memory=state.get("memory_context", ""),
        prior=prior_text,
    )

    final_chunk = None
    async for chunk in bound_llm.astream([
        SystemMessage(content=EXECUTOR_SYSTEM),
        HumanMessage(content=prompt),
    ]):
        # AIMessageChunk 支持 + 合并，自动拼接 tool_call_chunks
        final_chunk = chunk if final_chunk is None else final_chunk + chunk

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


async def reviewer(state: AgentState) -> dict:
    """质检 synthesizer 的汇总：≥7 通过，否则回 planner，最多重试 MAX_RETRIES 次。"""
    answer = state.get("draft_answer", "") or ""
    tool_calls = state.get("tool_calls", []) or []
    retries = state.get("retry_count", 0)

    # 模型调用了工具：正文为空是正常的（意图在 tool_calls 里），直接通过，
    # 工具结果由 chat.py 执行后作为回答。不能把这种情况误判成"没理解需求"。
    if tool_calls:
        names = ", ".join(tc.get("name", "?") for tc in tool_calls)
        return {"final_answer": answer, "review_score": 9,
                "review_reason": f"模型调用了工具：{names}，直接通过",
                "next_step": "finish", "error": ""}

    # 只有正文为空且没有工具调用时，才是真正没理解：不浪费 LLM 调用
    if not answer:
        if retries >= MAX_RETRIES:
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
    except Exception:
        # 打分本身失败：默认放行，避免卡死整个链路
        score, reason = PASS_SCORE, "打分失败，默认放行"

    if score >= PASS_SCORE:
        return {"final_answer": answer, "review_score": score,
                "review_reason": reason, "next_step": "finish", "error": ""}

    if retries >= MAX_RETRIES:
        # 重试次数用完，兜底放行，避免无限循环
        return {"final_answer": answer, "review_score": score,
                "review_reason": f"{reason}（已达重试上限）",
                "next_step": "finish", "error": ""}

    return {"retry_count": retries + 1, "review_score": score,
            "review_reason": reason, "next_step": "planner"}
