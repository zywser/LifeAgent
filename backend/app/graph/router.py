from langgraph.graph import END
from .state import AgentState


def route_after_executor(state: AgentState) -> str:
    """executor 之后的路由：还有子任务则继续执行，全部完成则去汇总。"""
    plan = state.get("plan", [])
    idx = state.get("subtask_index", 0)
    if idx < len(plan):
        return "executor"
    return "synthesizer"


def route_after_reviewer(state: AgentState) -> str:
    """reviewer 之后的路由。

    重试次数的判断由 reviewer 节点负责（它在写 next_step 时已经检查过
    retry_count 上限），这里只信任 next_step，不再重复判断。
    """
    if state.get("next_step") == "planner":
        return "planner"
    return END
