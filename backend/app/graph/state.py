from typing import TypedDict, Any

class AgentState(TypedDict, total=False):
    query: str
    plan: list[str]
    subtask_index: int
    current_subtask: str
    subtask_results: list[str]
    knowledge_context: str
    memory_context: str
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

