"""真实 LLM 端到端回归（默认跳过，控制调用成本）。

设计上不依赖 MySQL / Redis：checkpointer 用内存版、向量库用空 FakeStore，
并选用不会触发工具的通用问题，因此只验证真实 LLM + 真实图编排本身。

启用方式（需可访问 DashScope）：
    RUN_REAL_LLM_E2E=1 python -m pytest tests/test_e2e_real_llm.py -q
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_REAL_LLM_E2E") or not os.environ.get("DASHSCOPE_API_KEY"),
    reason="set RUN_REAL_LLM_E2E=1 and DASHSCOPE_API_KEY to run real-LLM e2e",
)


async def _run_graph(question: str) -> dict:
    from app.graph.build import build_graph

    graph = await build_graph(999, "e2e")
    return await graph.ainvoke(
        {
            "query": question,
            "uid": 999,
            "retry_count": 0,
            "web_search_enabled": False,
            "history_text": "",
        },
        config={"configurable": {"thread_id": "e2e-thread"}, "recursion_limit": 60},
    )


async def test_general_question_returns_answer(mock_stores, mem_checkpointer):
    result = await _run_graph("用一句话鼓励一下正在准备面试的我。")
    answer = (result.get("final_answer") or "").strip()
    assert answer, "真实链路应返回非空最终答案"
    assert not result.get("error"), "链路不应带错误状态"


async def test_greeting_completes_graph(mock_stores, mem_checkpointer):
    result = await _run_graph("你好，简单介绍一下你能做什么。")
    assert (result.get("final_answer") or "").strip(), "问候类问题应正常结束并作答"
