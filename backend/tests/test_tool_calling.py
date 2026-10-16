"""评测组 1：工具调用。

覆盖：模型工具决策捕获、决策与执行分离（打回不重复写库）、
未知工具安全跳过、工具异常不吞掉、uid 防伪造注入、
模型漏调时的关键词兜底补调、查询/记录防误记、纪念日误调守卫、
工具函数真实写库与聚合查询。
"""
from __future__ import annotations

import pytest

from app.graph.nodes import executor
from app.graph.tools import TOOLS, TOOL_MAP
from app.routes.chat import execute_tool_calls, infer_extra_tools
from app.db.models import Expense

from tests.fake_llm import FakeLLM, tool_call_chunk, text_chunk


# ===== executor 决策捕获 =====

async def test_executor_captures_tool_call_decision(monkeypatch, base_state):
    """executor 识别记账意图 → 决策保存在 tool_calls（不执行写库）。"""
    fake = FakeLLM(stream_scripts=[[tool_call_chunk(
        "record_expense", {"amount": 20.0, "category": "餐饮", "note": "午饭"})]])
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    st = dict(base_state, query="记一笔：中午吃饭花了20")
    out = await executor(st)
    assert out["tool_calls"][0]["name"] == "record_expense"
    assert out["tool_calls"][0]["args"]["amount"] == 20.0
    assert out["tool_calls"][0]["args"]["category"] == "餐饮"
    assert out["subtask_index"] == 1          # 子任务推进
    assert out["next_step"] == "synthesizer"
    assert fake.bind_calls                    # 确实 bind 过工具


async def test_executor_accumulates_tool_calls_across_subtasks(monkeypatch, base_state):
    """多轮 executor 循环时 tool_calls 累积而非覆盖。"""
    fake = FakeLLM(stream_scripts=[
        [tool_call_chunk("record_expense", {"amount": 10.0, "category": "餐饮"}, "c1")],
        [tool_call_chunk("create_todo", {"text": "买牛奶"}, "c2")],
    ])
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    st = dict(base_state, plan=["记账", "建待办"], tool_calls=[])
    out1 = await executor(st)
    out2 = await executor({**st, **out1})
    assert [t["name"] for t in out2["tool_calls"]] == ["record_expense", "create_todo"]
    assert out2["subtask_index"] == 2


# ===== 决策与执行分离 =====

async def test_decision_execution_separation(monkeypatch, sqlite_db, base_state):
    """executor 只决策不写库；执行由 execute_tool_calls 负责（打回重试不会重复落库）。"""
    fake = FakeLLM(stream_scripts=[[tool_call_chunk(
        "record_expense", {"amount": 88.0, "category": "购物"})]])
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    out = await executor(dict(base_state, query="买了88块钱的东西"))
    # 决策之后 DB 里没有任何记录
    db = sqlite_db()
    assert db.query(Expense).count() == 0
    # 执行之后才有
    results = await execute_tool_calls(out["tool_calls"], uid=42)
    assert db.query(Expense).count() == 1
    assert "已记录" in results[0]


# ===== execute_tool_calls 的健壮性 =====

async def test_execute_tool_calls_unknown_tool_skipped():
    """未知工具名安全跳过，不抛异常。"""
    results = await execute_tool_calls([{"name": "no_such_tool", "args": {}}], uid=1)
    assert results == []


async def test_execute_tool_calls_error_surfaced(monkeypatch):
    """工具执行异常不静默吞掉：错误原因进入结果，用户能看到。"""
    class BoomTool:
        async def ainvoke(self, args):
            raise RuntimeError("db down")

    monkeypatch.setattr("app.routes.chat.TOOL_MAP", {"boom_tool": BoomTool()})
    results = await execute_tool_calls([{"name": "boom_tool", "args": {}}], uid=1)
    assert results and "⚠️" in results[0] and "db down" in results[0]


async def test_execute_tool_calls_uid_forced_injection(sqlite_db):
    """模型 args 里伪造的 uid 必须被真实 uid 覆盖（防越权写他人数据）。"""
    await execute_tool_calls(
        [{"name": "record_expense", "args": {"amount": 5.0, "category": "餐饮", "uid": 999}}],
        uid=42,
    )
    db = sqlite_db()
    row = db.query(Expense).first()
    assert row is not None and row.user_id == 42


# ===== 漏调兜底（infer_extra_tools）=====

def test_infer_extra_tools_checkin_fallback():
    """模型漏调时按强信号补调习惯打卡。"""
    extra = infer_extra_tools("打卡跑步", called=[])
    assert any(t["name"] == "check_habit" and t["args"]["habit_name"] == "跑步" for t in extra)


def test_infer_extra_tools_water_fallback():
    """漏调时补调喝水记录。"""
    extra = infer_extra_tools("喝了3杯水", called=[])
    assert any(t["name"] == "record_water" and t["args"]["cups"] == 3 for t in extra)


def test_infer_extra_tools_query_expenses_never_record():
    """查询账单意图绝不能被兜底成记一笔（曾实测误记 ¥0.0 进账单）。"""
    extra = infer_extra_tools("这个月花了多少钱", called=[])
    names = {t["name"] for t in extra}
    assert "query_expenses" in names
    assert "record_expense" not in names
    # 已调用过 query_expenses 时不再重复补
    assert infer_extra_tools("这个月花了多少钱", called=[{"name": "query_expenses"}]) == []


def test_infer_extra_tools_web_search_fallback():
    """带查询意图、非闲聊、非个人数据的消息，漏调时补 web_search。"""
    extra = infer_extra_tools("华为最新旗舰手机怎么样", called=[])
    assert any(t["name"] == "web_search" for t in extra)


def test_infer_extra_tools_no_trigger_for_chitchat():
    """问候闲聊不触发任何工具兜底。"""
    assert infer_extra_tools("你是谁", called=[]) == []


# ===== 误调守卫 =====

async def test_execute_tool_calls_query_anniversary_guard():
    """消息没提纪念日/生日时，模型误调的 query_anniversary 不执行。"""
    results = await execute_tool_calls(
        [{"name": "query_anniversary", "args": {}}],
        uid=42,
        message="明天曲靖到大理的火车票",
    )
    assert results == []


async def test_execute_tool_calls_query_anniversary_allowed():
    """用户明确问纪念日时正常执行。"""
    results = await execute_tool_calls(
        [{"name": "query_anniversary", "args": {}}],
        uid=42,
        message="有哪些纪念日快到了",
    )
    assert results and "纪念日" in results[0]


# ===== 工具函数真实写库 =====

def test_record_expense_writes_db(sqlite_db):
    TOOL_MAP["record_expense"].invoke({"amount": 12.5, "category": "交通", "note": "打车", "uid": 7})
    db = sqlite_db()
    row = db.query(Expense).filter(Expense.user_id == 7).first()
    assert row.amount == 12.5 and row.category == "交通" and row.kind == "expense"


def test_query_expenses_aggregates(sqlite_db):
    TOOL_MAP["record_expense"].invoke({"amount": 20, "category": "餐饮", "uid": 7})
    TOOL_MAP["record_expense"].invoke({"amount": 30, "category": "交通", "uid": 7})
    TOOL_MAP["record_expense"].invoke({"amount": 100, "category": "工资", "kind": "income", "uid": 7})
    out = TOOL_MAP["query_expenses"].invoke({"days": 7, "uid": 7})
    assert "支出合计 ¥50.0" in out and "收入 ¥100.0" in out


# ===== 工具集静态安全 =====

def test_toolset_no_dangerous_operations():
    """工具集里不存在删除/转账/提现等危险操作工具（注入攻击无处落脚）。"""
    names = {t.name for t in TOOLS}
    for danger in ("delete", "transfer", "withdraw", "drop", "update_password", "send_money"):
        assert danger not in names, f"工具集中出现危险工具：{danger}"
