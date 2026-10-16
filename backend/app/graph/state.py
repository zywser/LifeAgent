from typing import TypedDict, Any

class AgentState(TypedDict, total=False):
    query: str
    plan: list[str]
    subtask_index: int
    current_subtask: str
    subtask_results: list[str]
    knowledge_context: str
    memory_context: str
    # 检索命中标记：retriever 写入，供"资料类问题无召回不编造"防线使用
    notes_found: bool
    memory_found: bool
    draft_answer: str
    final_answer: str
    retry_count: int
    review_score: int
    review_reason: str
    tool_calls: list[dict]
    tool_results: list[str]
    error: str
    next_step: str
    uid: int
    # 联网搜索开关（每轮请求传入）：关闭时 executor/兜底/工具执行三层禁用 web_search
    web_search_enabled: bool
    # 跨轮对话历史（chat.py 从 conversations 表读取后注入，供 executor/planner 理解追问上下文）
    history_text: str

