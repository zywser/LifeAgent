"""评测组 3：回答质量（reviewer 质检与整链路）。

覆盖：质检通过/重试/重试上限兜底、工具驱动回答不误判、打分失败默认放行、
简短但完整回答不被打回、分数与理由一致性钳制（历史痛点）、
整图端到端的正常与重试路径。
"""
from __future__ import annotations

import pytest

from app.graph.nodes import (
    PASS_SCORE, clamp_score_for_reason, reviewer,
)
from app.routes.chat import run_chat_stream

from tests.fake_llm import FakeLLM, aim, text_chunk, aim_tool_call
from tests.conftest import FakeStore


# ===== reviewer 节点级 =====

async def test_reviewer_passes_good_answer(monkeypatch, base_state):
    fake = FakeLLM(script=[aim('{"score": 8, "reason": "直接、准确、自然地回答了用户"}')])
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    out = await reviewer(dict(base_state, draft_answer="今天花了20块，主要是午饭。", tool_calls=[]))
    assert out["next_step"] == "finish"
    assert out["final_answer"] == "今天花了20块，主要是午饭。"
    assert out["review_score"] == 8


async def test_reviewer_short_but_complete_passes(monkeypatch, base_state):
    """简短但完整的回答（如问候）必须通过，不得因'太简单'打回。"""
    fake = FakeLLM(script=[aim('{"score": 9, "reason": "得体地回应了问候"}')])
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    out = await reviewer(dict(base_state, query="你好", draft_answer="你好呀，今天过得怎么样？", tool_calls=[]))
    assert out["next_step"] == "finish"
    assert out["review_score"] >= PASS_SCORE


async def test_reviewer_clamp_score_reason_mismatch(monkeypatch, base_state):
    """【历史痛点】理由批评严厉但分数给高分 → 代码级钳制降分并打回重试。"""
    fake = FakeLLM(script=[aim('{"score": 8, "reason": "回答没有解决核心问题，答非所问，信息缺失"}')])
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    out = await reviewer(dict(base_state, draft_answer="这个嘛，我也不太清楚。", tool_calls=[]))
    assert out["review_score"] == PASS_SCORE - 1          # 8 → 6
    assert out["next_step"] == "planner"                  # 触发重试
    assert out["retry_count"] == 1


def test_clamp_score_for_reason_unit():
    """一致性钳制纯函数：命中严重缺陷词即封顶 PASS_SCORE-1。"""
    assert clamp_score_for_reason(8, "没解决核心问题") == PASS_SCORE - 1
    assert clamp_score_for_reason(9, "基本服务缺失") == PASS_SCORE - 1
    assert clamp_score_for_reason(10, "答非所问，未直接回答") == PASS_SCORE - 1
    assert clamp_score_for_reason(8, "直接准确自然") == 8        # 正面理由不误伤
    assert clamp_score_for_reason(6, "答非所问") == 6            # 已在 6 以下不再动


async def test_reviewer_tool_call_driven_passes(monkeypatch, base_state):
    """正文空但有工具调用 → 直接通过（不能误判成'没理解需求'）。"""
    out = await reviewer(dict(
        base_state,
        draft_answer="",
        tool_calls=[{"name": "record_expense", "args": {"amount": 20.0, "category": "餐饮"}}],
    ))
    assert out["next_step"] == "finish"
    assert out["review_score"] == 9
    assert "直接通过" in out["review_reason"]


async def test_reviewer_empty_answer_retries(monkeypatch, base_state):
    fake = FakeLLM()
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    out = await reviewer(dict(base_state, draft_answer="", tool_calls=[]))
    assert out["next_step"] == "planner"
    assert out["retry_count"] == 1
    assert fake.script == [] and fake.stream_scripts == []    # 空回答不浪费 LLM 调用


async def test_reviewer_empty_answer_max_retries_fallback(monkeypatch, base_state):
    """空回答重试到上限 → 兜底话术结束，不无限循环。"""
    fake = FakeLLM()
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    out = await reviewer(dict(base_state, draft_answer="", tool_calls=[], retry_count=3))
    assert out["next_step"] == "finish"
    assert "抱歉" in out["final_answer"]


async def test_reviewer_llm_failure_defaults_pass(monkeypatch, base_state):
    """LLM 打分异常 → 默认放行，链路不卡死。"""
    class BoomLLM:
        async def ainvoke(self, messages, **kwargs):
            raise RuntimeError("model timeout")

    monkeypatch.setattr("app.graph.nodes.llm", BoomLLM())
    out = await reviewer(dict(base_state, draft_answer="回答内容本身是好的。", tool_calls=[]))
    assert out["next_step"] == "finish"
    assert out["review_score"] == PASS_SCORE


# ===== 整图端到端 =====

async def test_graph_end_to_end_good_answer(monkeypatch, mem_checkpointer, base_state):
    """完整链路：planner → retriever → executor → synthesizer → reviewer 通过。"""
    from app.graph.build import build_graph
    monkeypatch.setattr("app.graph.nodes.get_notes_store", lambda uid: FakeStore())
    monkeypatch.setattr("app.graph.nodes.get_memory_store", lambda uid: FakeStore())
    fake = FakeLLM(
        script=[aim('["直接回答用户"]'), aim('{"score": 8, "reason": "自然、完整地解决了问题"}')],
        stream_scripts=[[text_chunk("今天一共花了"), text_chunk("50块，主要是吃饭和交通。")]],
    )
    monkeypatch.setattr("app.graph.nodes.llm", fake)

    graph = await build_graph(uid=42, session_id="e2e")
    config = {"configurable": {"thread_id": "e2e-1"}}
    result = await graph.ainvoke({"query": "今天花了多少钱", "uid": 42, "retry_count": 0}, config=config)
    assert "50块" in result.get("final_answer", "")
    assert result.get("review_score", 0) >= PASS_SCORE
    assert result.get("retry_count", 0) == 0


async def test_graph_end_to_end_retry_loop(monkeypatch, mem_checkpointer, base_state):
    """质检低分 → 打回 planner 重做 → 第二次通过，最终答案来自重做版本。"""
    from app.graph.build import build_graph
    monkeypatch.setattr("app.graph.nodes.get_notes_store", lambda uid: FakeStore())
    monkeypatch.setattr("app.graph.nodes.get_memory_store", lambda uid: FakeStore())
    fake = FakeLLM(
        script=[
            aim('["直接回答用户"]'),                                   # planner v1
            aim('{"score": 4, "reason": "答非所问，遗漏关键信息"}'),    # reviewer v1 打回
            aim('["直接回答用户"]'),                                   # planner v2
            aim('{"score": 9, "reason": "这次回答直接且完整"}'),        # reviewer v2 通过
        ],
        stream_scripts=[
            [text_chunk("这个问题我还不太确定，稍等。")],               # executor v1（差）
            [text_chunk("你上周存钱进度：已存1200，还差3800，每天需存约190。")],  # executor v2（好）
        ],
    )
    monkeypatch.setattr("app.graph.nodes.llm", fake)

    graph = await build_graph(uid=42, session_id="e2e-retry")
    config = {"configurable": {"thread_id": "e2e-retry-1"}}
    result = await graph.ainvoke({"query": "存钱进度怎么样", "uid": 42, "retry_count": 0}, config=config)
    assert result.get("retry_count", 0) == 1
    assert "还差3800" in result.get("final_answer", "")       # 来自重做版本
    assert "不太确定" not in result.get("final_answer", "")
    assert result.get("review_score", 0) == 9


# ===== 可观测与回答质量的交汇：final 事件携带真实答案 =====

async def test_final_event_carries_tool_driven_answer(monkeypatch, sqlite_db, mock_stores):
    """run_chat_stream 的 final 事件以工具执行结果（经总结）作为最终回答。"""
    from tests.fake_llm import FakeGraph, ev_chain_start, ev_chain_end, ev_model_end, collect
    monkeypatch.setattr("app.graph.nodes.get_notes_store", lambda uid: FakeStore())
    monkeypatch.setattr("app.graph.nodes.get_memory_store", lambda uid: FakeStore())

    graph = FakeGraph(
        events=[
            ev_chain_start("supervisor"), ev_chain_end("supervisor", {}),
            ev_chain_start("planner"), ev_chain_end("planner", {"plan": ["查账"]}),
            ev_chain_start("executor"),
            ev_model_end(tool_calls=[{"name": "query_expenses", "args": {"days": 7}, "id": "c1", "type": "tool_call"}]),
            ev_chain_end("executor", {"current_subtask": "查账", "subtask_index": 1}),
        ],
        state_values={
            "final_answer": "（过渡语）",
            "tool_calls": [{"name": "query_expenses", "args": {"days": 7}, "id": "c1", "type": "tool_call"}],
        },
    )
    events = await collect(run_chat_stream(graph, "这个月花了多少", uid=42, session_id="s1"))
    finals = [e for e in events if e.startswith("event: final")]
    assert finals, "必须有 final 事件"
    # sqlite 空库下 query_expenses 返回"最近 7 天没有消费记录。"，被原样用作最终回答
    assert "消费记录" in finals[0]


# ===== 防回归：连续低分打回不得触发 Recursion limit =====

async def test_graph_retry_loop_finishes_within_recursion_limit(monkeypatch, mem_checkpointer):
    """【防回归】模型连续 3 次低分被打回时，第 4 轮 reviewer 兜底放行，
    整图在 recursion_limit=60 内正常结束（复现用户报错"RAG知识库中项目目标与范围"
    → Recursion limit of 25 reached 的根因：4 轮重试恰好耗完默认 25 超步）。"""
    from app.graph.build import build_graph

    class LowScoreLLM(FakeLLM):
        """planner 拆 2 个子任务；executor 输出低质内容；reviewer 恒打 4 分。"""

        async def ainvoke(self, messages, **kwargs):
            self.calls.append(messages)
            text = " ".join(getattr(m, "content", "") or "" for m in messages)
            if "拆成可执行子任务" in text:
                return aim('["子任务一", "子任务二"]')
            return aim('{"score": 4, "reason": "答非所问，没有回答问题"}')

        async def astream(self, messages, **kwargs):
            self.calls.append(messages)
            for c in [text_chunk("这个问题比较复杂，让我再想想怎么回答。")]:
                yield c

        def bind_tools(self, tools, **kwargs):
            return self

    fake = LowScoreLLM()
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    monkeypatch.setattr("app.graph.nodes.get_notes_store", lambda uid: FakeStore())
    monkeypatch.setattr("app.graph.nodes.get_memory_store", lambda uid: FakeStore())

    graph = await build_graph(uid=42, session_id="e2e-loop")
    config = {"configurable": {"thread_id": "e2e-loop-1"}, "recursion_limit": 60}
    result = await graph.ainvoke(
        {"query": "RAG知识库中项目目标与范围", "uid": 42, "retry_count": 0},
        config=config,
    )
    # 兜底轮（retry_count=3 ≥ MAX_RETRIES）正常放行，不再打回，不会触顶报错
    assert result.get("retry_count", 0) == 3
    assert result.get("final_answer", "").strip(), "兜底轮必须给出回答，不能空手结束"
    assert result.get("review_score", 0) < 7    # 确认走的确实是兜底放行（低分）路径


# ===== 防回归：executor 挂起超时与子任务硬上限（Executor 无限执行问题） =====

async def test_executor_llm_hang_timeout_skips_subtask(monkeypatch, base_state):
    """【防回归】executor 的 LLM 流式调用挂起（限流/网络卡死）时，
    超时后跳过该子任务继续链路，不让整条链路卡死（复现 Executor 卡到 9 次一直执行）。"""
    import asyncio
    from app.graph.nodes import executor as exec_node

    class HungLLM:
        async def astream(self, messages, **kwargs):
            await asyncio.sleep(3600)   # 永不返回
            if False:
                yield

        def bind_tools(self, tools, **kwargs):
            return self

    monkeypatch.setattr("app.graph.nodes.llm", HungLLM())
    monkeypatch.setattr("app.graph.nodes.EXECUTOR_TIMEOUT", 0.05)
    st = dict(base_state, plan=["子任务一"], subtask_index=0, web_search_enabled=False)
    out = await exec_node(st)
    assert out["next_step"] == "synthesizer"          # 不卡死，继续走汇总
    assert out["subtask_index"] == 1                  # 子任务正常前进
    assert "超时" in out["subtask_results"][0]        # 给用户明确提示，而非静默


async def test_executor_subtask_index_hard_cap(base_state):
    """【防回归】subtask_index 异常膨胀（>6）时直接结束，杜绝 executor 无限循环。"""
    from app.graph.nodes import executor as exec_node
    out = await exec_node(dict(base_state, plan=["a", "b"], subtask_index=7))
    assert out["next_step"] == "synthesizer"
    assert "subtask_index" not in out                 # 不再推进索引
