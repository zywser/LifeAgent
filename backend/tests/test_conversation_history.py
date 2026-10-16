"""评测组 6：跨轮对话历史注入（上下文记忆）。

覆盖：
- load_history_text：按会话读取历史、排除当前问句、非数字/无会话兜底；
- executor / planner 的 prompt 收到历史（数据位注入，不污染系统提示）；
- run_chat_stream 把历史透传给图（captured_inputs 断言）。
"""
from __future__ import annotations

import json
import pytest

from app.routes.chat import load_history_text, run_chat_stream
from app.graph.nodes import EXECUTOR_PROMPT, EXECUTOR_SYSTEM, executor, planner
from app.db.models import Conversation

from tests.fake_llm import FakeLLM, text_chunk, aim, FakeGraph, collect


def _seed_conversation(db, user_id: int, cid: int, messages: list[dict]):
    c = Conversation(user_id=user_id, id=cid, title="测试会话", preview="",
                     messages=json.dumps(messages, ensure_ascii=False))
    db.add(c)
    db.commit()
    return c


def test_load_history_text_basic(sqlite_db):
    """按会话读取最近历史，格式化用户/助手消息，排除当前问句。"""
    db = sqlite_db()
    _seed_conversation(db, user_id=2, cid=7, messages=[
        {"role": "user", "content": "实施时间节点与责任分工在什么时候", "time": "19:38"},
        {"role": "assistant", "content": "你上传的《AI全栈RAG知识库系统开发技术方案.docx》里，第五部分写了实施时间节点…", "time": "19:38"},
        {"role": "user", "content": "有哪些风险？以及有什么应对措施", "time": "19:41"},
    ])
    hist = load_history_text(db, user_id=2, session_id="7", current_message="有哪些风险？以及有什么应对措施")
    assert "用户：实施时间节点与责任分工在什么时候" in hist
    assert "助手：你上传的《AI全栈RAG知识库系统开发技术方案.docx》" in hist
    assert "有哪些风险？以及有什么应对措施" not in hist      # 当前问句不喂回


def test_load_history_text_guards(sqlite_db):
    """非数字 session_id / 会话不存在 / 消息为空 → 空历史（不报错）。"""
    db = sqlite_db()
    assert load_history_text(db, 2, None, "q") == ""
    assert load_history_text(db, 2, "abc占位", "q") == ""
    assert load_history_text(db, 2, "99", "q") == ""          # 无此会话
    _seed_conversation(db, 2, 8, [])
    assert load_history_text(db, 2, "8", "q") == ""


async def test_executor_prompt_contains_history(monkeypatch, base_state):
    """历史作为数据位进入 executor 的 HumanMessage（供追问理解，不改变系统提示）。"""
    fake = FakeLLM(stream_scripts=[[text_chunk("好的。")]])
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    hist = "用户：实施时间节点与责任分工在什么时候\n助手：项目分五个阶段…"
    await executor(dict(base_state, query="有哪些风险", history_text=hist))
    human = fake.human_prompts()[0]
    assert "本次对话之前聊过的内容" in human
    assert hist in human
    assert fake.system_prompts() == [EXECUTOR_SYSTEM]          # 系统提示恒定，历史只在数据位


async def test_planner_prompt_contains_history(monkeypatch, base_state):
    """planner 拆解时看到历史，能按上文理解追问（"有哪些风险"→ 项目风险）。"""
    fake = FakeLLM(script=[aim('["直接回答用户"]')])
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    hist = "用户：实施时间节点与责任分工在什么时候\n助手：项目分五个阶段…"
    await planner(dict(base_state, query="有哪些风险", history_text=hist))
    human = fake.human_prompts()[0]
    assert "对话历史" in human
    assert hist in human


async def test_run_chat_stream_passes_history_to_graph():
    """run_chat_stream 把历史透传给图（captured_inputs 含 history_text）。"""
    graph = FakeGraph(events=[], state_values={"final_answer": "ok", "tool_calls": []})
    await collect(run_chat_stream(graph, "有哪些风险", uid=2, session_id="7",
                                  web_search=False, history_text="用户：实施时间节点…"))
    assert graph.captured_inputs["history_text"] == "用户：实施时间节点…"
    assert graph.captured_inputs["web_search_enabled"] is False
