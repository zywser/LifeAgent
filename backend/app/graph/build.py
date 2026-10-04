from langgraph.graph import StateGraph, START, END
from .state import AgentState
from .nodes import supervisor, planner, retriever, executor, synthesizer, reviewer
from .router import route_after_executor, route_after_reviewer
from ..vector_store.factory import get_checkpointer


async def build_graph(uid: int, session_id: str):
    graph = StateGraph(AgentState)

    # 注册节点
    graph.add_node("supervisor", supervisor)
    graph.add_node("planner", planner)
    graph.add_node("retriever", retriever)
    graph.add_node("executor", executor)
    graph.add_node("synthesizer", synthesizer)
    graph.add_node("reviewer", reviewer)

    # 入口：START → supervisor
    graph.add_edge(START, "supervisor")

    # 规划 → 检索
    graph.add_edge("supervisor", "planner")
    graph.add_edge("planner", "retriever")
    graph.add_edge("retriever", "executor")

    # executor 循环：还有子任务回 executor，否则去 synthesizer
    graph.add_conditional_edges(
        "executor",
        route_after_executor,
        {
            "executor": "executor",
            "synthesizer": "synthesizer",
        },
    )

    # 汇总 → 质检
    graph.add_edge("synthesizer", "reviewer")

    # reviewer 条件分支：重试或结束
    graph.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {
            "planner": "planner",
            END: END,
        },
    )

    return graph.compile(checkpointer=await get_checkpointer())
