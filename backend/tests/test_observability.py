"""评测组 4：可观测性（SSE 事件流 + LangSmith）。

覆盖：node_start/node_end 序列完整、token 流式事件、
工具调用事件、质检详情随 node_end 推送、异常事件带类型、
LangSmith 环境配置显式生效、run metadata 注入（供链路检索）。
"""
from __future__ import annotations

import os

import pytest

from app.routes.chat import run_chat_stream
from tests.fake_llm import (
    FakeGraph, ev_chain_start, ev_chain_end, ev_model_stream, ev_model_end, collect,
)


def _parse(event_line: str) -> tuple[str, dict]:
    """把 SSE 文本解析回 (event_name, data)。"""
    import json
    lines = event_line.strip().split("\n")
    name = lines[0].replace("event: ", "")
    data = json.loads(lines[1].replace("data: ", ""))
    return name, data


FULL_EVENTS = [
    ev_chain_start("supervisor"), ev_chain_end("supervisor", {}),
    ev_chain_start("planner"), ev_chain_end("planner", {"plan": ["回答用户"]}),
    ev_chain_start("retriever"), ev_chain_end("retriever", {}),
    ev_chain_start("executor"),
    ev_model_stream("你好"),
    ev_model_stream("呀！"),
    ev_model_end(content="你好呀！"),
    ev_chain_end("executor", {"current_subtask": "回答用户", "subtask_index": 1}),
    ev_chain_start("synthesizer"), ev_chain_end("synthesizer", {"draft_answer": "你好呀！"}),
    ev_chain_start("reviewer"), ev_chain_end("reviewer", {"review_score": 8, "review_reason": "自然得体", "next_step": "finish"}),
]


async def test_sse_event_sequence_complete():
    """节点开始/结束事件齐全，且链路以 final 收尾。"""
    graph = FakeGraph(events=FULL_EVENTS, state_values={"final_answer": "你好呀！"})
    events = await collect(run_chat_stream(graph, "你好", uid=1, session_id="s1"))
    parsed = [_parse(e) for e in events]

    nodes = ["supervisor", "planner", "retriever", "executor", "synthesizer", "reviewer"]
    starts = {n: [i for i, (ev, d) in enumerate(parsed) if ev == "node_start" and d["node"] == n] for n in nodes}
    ends = {n: [i for i, (ev, d) in enumerate(parsed) if ev == "node_end" and d["node"] == n] for n in nodes}
    for n in nodes:
        assert starts[n] and ends[n], f"节点 {n} 缺少 start/end"
        assert starts[n][0] < ends[n][-1], f"节点 {n} 顺序错误"
    assert any(ev == "final" for ev, _ in parsed)
    assert any(ev == "token" for ev, _ in parsed)


async def test_sse_token_events_pushed():
    """on_chat_model_stream 的文本逐段转成 token 事件。"""
    graph = FakeGraph(events=FULL_EVENTS, state_values={"final_answer": "你好呀！"})
    events = await collect(run_chat_stream(graph, "你好", uid=1, session_id="s1"))
    tokens = [d["text"] for ev, d in (_parse(e) for e in events) if ev == "token"]
    assert tokens == ["你好", "呀！"]


async def test_sse_tool_call_event():
    """模型决策工具调用 → 推送 tool_call 事件（名称 + 参数）。"""
    graph = FakeGraph(events=[
        ev_chain_start("executor"),
        ev_model_end(tool_calls=[
            {"name": "record_expense", "args": {"amount": 20.0, "category": "餐饮"}, "id": "c1", "type": "tool_call"}]),
        ev_chain_end("executor", {"current_subtask": "记账", "subtask_index": 1}),
    ], state_values={})
    events = await collect(run_chat_stream(graph, "记一笔20", uid=1, session_id="s1"))
    calls = [(d["name"], d["args"]) for ev, d in (_parse(e) for e in events) if ev == "tool_call"]
    assert calls == [("record_expense", {"amount": 20.0, "category": "餐饮"})]


async def test_node_end_carries_detail():
    """node_end 携带节点详情：planner 的 plan、executor 的子任务进度、reviewer 的质检分。"""
    graph = FakeGraph(events=[
        ev_chain_start("planner"), ev_chain_end("planner", {"plan": ["任务A", "任务B"]}),
        ev_chain_start("executor"), ev_chain_end("executor", {"current_subtask": "任务B", "subtask_index": 2}),
        ev_chain_start("reviewer"),
        ev_chain_end("reviewer", {"review_score": 6, "review_reason": "答非所问", "next_step": "planner"}),
    ], state_values={"final_answer": "x"})
    events = await collect(run_chat_stream(graph, "帮我做两件事", uid=1, session_id="s1"))
    parsed = [_parse(e) for e in events]

    planner_end = next(d for ev, d in parsed if ev == "node_end" and d["node"] == "planner")
    assert planner_end["plan"] == ["任务A", "任务B"]
    executor_end = next(d for ev, d in parsed if ev == "node_end" and d["node"] == "executor")
    assert executor_end["current_subtask"] == "任务B" and executor_end["subtask_index"] == 2
    reviewer_end = next(d for ev, d in parsed if ev == "node_end" and d["node"] == "reviewer")
    assert reviewer_end["review_score"] == 6
    assert reviewer_end["retry"] is True          # next_step=planner → 前端可提示"质检未过，重试中"


async def test_sse_error_event_with_type():
    """链路异常 → error 事件携带错误类型，前端可区分提示。"""
    graph = FakeGraph(error=TimeoutError("upstream timeout"))
    events = await collect(run_chat_stream(graph, "hi", uid=1, session_id="s1"))
    parsed = [_parse(e) for e in events]
    errors = [d for ev, d in parsed if ev == "error"]
    assert errors and errors[0]["error_type"] == "TimeoutError"
    assert "upstream timeout" in errors[0]["message"]


async def test_run_metadata_in_config():
    """每个 run 的 metadata 携带 uid/session_id/thread_id，LangSmith 可按用户检索。"""
    graph = FakeGraph(events=FULL_EVENTS, state_values={"final_answer": "你好呀！"})
    await collect(run_chat_stream(graph, "你好", uid=42, session_id="chat-7"))
    meta = (graph.captured_config or {}).get("metadata", {})
    assert meta.get("uid") == 42
    assert meta.get("session_id") == "chat-7"
    assert meta.get("thread_id", "").startswith("u42_chat-7_")


def test_langsmith_env_configured(monkeypatch):
    """apply_langsmith_env 按 Settings 显式写入 LangSmith 环境变量（接入不靠 .env 碰运气）。"""
    import os
    from app.config import apply_langsmith_env, settings

    # 场景 1：未配置 API key → 自动关闭 tracing，不打扰正常运行
    monkeypatch.setattr(settings, "langsmith_api_key", "")
    for k in ("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING", "LANGCHAIN_API_KEY", "LANGSMITH_API_KEY"):
        os.environ.pop(k, None)
    apply_langsmith_env()
    assert os.environ.get("LANGCHAIN_TRACING_V2") == "false"
    assert os.environ.get("LANGCHAIN_PROJECT") == "Life-Agent"

    # 场景 2：配置了 API key → 开启 tracing 并注入 key（评测 conftest 会在 import 前覆盖为 false 保证离线）
    monkeypatch.setattr(settings, "langsmith_api_key", "test-key")
    os.environ.pop("LANGCHAIN_TRACING_V2", None)
    os.environ.pop("LANGSMITH_TRACING", None)
    apply_langsmith_env()
    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
    assert os.environ.get("LANGCHAIN_API_KEY") == "test-key"
