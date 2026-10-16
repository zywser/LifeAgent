"""评测组 5：联网开关 + 资料联动强化（模块一 + 二）。

覆盖：
- 联网开关：infer_extra_tools 不补 web_search、execute_tool_calls 过滤 web_search（三层拦截中的两层）；
- executor prompt：资料优先硬约束 + 联网规则随开关动态切换；
- retriever：问句壳词剥离、无结果二次检索、命中标记、带文件名格式化；
- 幻觉防线：资料类问题无召回时 reviewer 代码级"未找到"、chat 出口兜底、有召回不误伤。
"""
from __future__ import annotations

import pytest

from langchain_core.documents import Document

from app.graph.nodes import (
    EXECUTOR_PROMPT, WEB_SEARCH_RULE_ON, WEB_SEARCH_RULE_OFF,
    strip_personal_shell, is_personal_data_query, retriever, reviewer, executor,
)
from app.routes.chat import infer_extra_tools, execute_tool_calls, run_chat_stream
from app.graph.tools import TOOL_MAP

from tests.fake_llm import FakeLLM, text_chunk, aim, FakeGraph, collect


# ===== 壳词剥离（单元） =====

def test_strip_personal_shell_unit():
    """问句里的个人资料壳词被剥掉，留下核心检索词。"""
    assert strip_personal_shell("我上传了一个什么资料") == "一个什么资料"
    assert strip_personal_shell("查看我的资料") == ""
    assert strip_personal_shell("我上传的简历有哪些内容") == "简历有哪些内容"
    assert strip_personal_shell("我之前说的项目") == "项目"
    assert strip_personal_shell("普通问题：今天天气怎么样") == "普通问题：今天天气怎么样"


def test_is_personal_data_query_signals():
    """资料类意图信号词命中；普通/实时问题不误判。"""
    assert is_personal_data_query("我叫什么名字")
    assert is_personal_data_query("我上传了一个什么资料")
    assert is_personal_data_query("查看我的资料")
    assert is_personal_data_query("我做了什么项目")
    assert not is_personal_data_query("今天天气怎么样")
    assert not is_personal_data_query("帮我把这个文件转成PDF")


# ===== retriever 升级：壳词剥离二次检索 + 命中标记 + 文件名 =====

class SelectiveStore:
    """按 query 精确命中的假向量库：未收录的 query 无结果（用于触发二次检索分支）。"""

    def __init__(self, hits: dict[str, list[str]], default=None, metadatas=None):
        self.hits = {
            k: [Document(page_content=d, metadata=(metadatas or {}).get(k, {})) for d in v]
            for k, v in hits.items()
        }
        self.default = [Document(page_content=d) for d in (default or [])]

    def similarity_search(self, query: str, k: int = 6):
        if query in self.hits:
            return self.hits[query][:k]
        return self.default[:k]


def test_retriever_second_pass_after_shell_strip(monkeypatch, base_state):
    """问句带壳词时首次检索无结果，剥壳后二次检索命中，并带来源文件名。"""
    notes = SelectiveStore(
        hits={
            "一个什么资料": ["简历：钟永旺，24岁，丽江文化旅游学院，AI Agent 开发方向"],
            "有哪些内容": ["项目经历：智能OA系统、Life Agent"],
        },
        metadatas={"一个什么资料": {"filename": "钟永旺-简历.pdf"}},
    )
    monkeypatch.setattr("app.graph.nodes.get_notes_store", lambda uid: notes)
    monkeypatch.setattr("app.graph.nodes.get_memory_store", lambda uid: SelectiveStore({}))

    out = retriever(dict(base_state, query="我上传了一个什么资料"))
    assert out["notes_found"] is True
    assert out["next_step"] == "executor"
    # 二次检索结果带文件名前缀
    assert "钟永旺-简历.pdf" in out["knowledge_context"]
    assert "钟永旺" in out["knowledge_context"]


def test_retriever_marks_no_recall_when_empty(monkeypatch, base_state):
    """资料与记忆都无结果时：命中标记为 False，上下文为"暂无"占位（防线依据）。"""
    from tests.conftest import FakeStore
    monkeypatch.setattr("app.graph.nodes.get_notes_store", lambda uid: FakeStore())
    monkeypatch.setattr("app.graph.nodes.get_memory_store", lambda uid: FakeStore())
    out = retriever(dict(base_state, query="我叫什么名字"))
    assert out["notes_found"] is False
    assert out["memory_found"] is False
    assert out["knowledge_context"] == "暂无个人笔记"


# ===== 联网开关：infer_extra_tools 兜底拦截 =====

def test_infer_extra_tools_web_search_disabled_by_switch():
    """开关关闭：即使消息带查询意图，也不再补 web_search（防幻觉主源）。"""
    extra = infer_extra_tools("华为最新旗舰手机怎么样", called=[], web_search_enabled=False)
    assert all(t["name"] != "web_search" for t in extra)
    assert extra == []   # 此消息本应触发 web_search 兜底，开关关闭后完全不打


def test_infer_extra_tools_web_search_enabled_flag():
    """开关开启（显式）：原有兜底行为保持。"""
    extra = infer_extra_tools("华为最新旗舰手机怎么样", called=[], web_search_enabled=True)
    assert any(t["name"] == "web_search" for t in extra)


# ===== 联网开关：execute_tool_calls 执行层拦截 =====

class FakeWebSearch:
    def __init__(self):
        self.called = False

    async def ainvoke(self, args):
        self.called = True
        return "mock 联网搜索结果"


async def test_execute_tool_calls_skips_web_search_when_disabled(monkeypatch):
    """开关关闭：模型即使决策了 web_search 也不执行（第二层拦截）。"""
    fake_tool = FakeWebSearch()
    monkeypatch.setattr("app.routes.chat.TOOL_MAP", {**TOOL_MAP, "web_search": fake_tool})
    results = await execute_tool_calls(
        [{"name": "web_search", "args": {"query": "今天天气"}}],
        uid=1, web_search_enabled=False,
    )
    assert results == []
    assert fake_tool.called is False


async def test_execute_tool_calls_runs_web_search_when_enabled(monkeypatch):
    """开关开启：web_search 正常执行。"""
    fake_tool = FakeWebSearch()
    monkeypatch.setattr("app.routes.chat.TOOL_MAP", {**TOOL_MAP, "web_search": fake_tool})
    results = await execute_tool_calls(
        [{"name": "web_search", "args": {"query": "今天天气"}}],
        uid=1, web_search_enabled=True,
    )
    assert fake_tool.called is True
    assert any("mock 联网搜索结果" in r for r in results)


# ===== executor prompt：资料优先 + 联网规则动态 =====

def test_executor_prompt_has_personal_data_rule():
    """EXECUTOR_PROMPT 必须包含资料优先硬约束（无据直说、禁编造、禁搜个人资料）。"""
    assert "回答资料类问题" in EXECUTOR_PROMPT
    assert "只能依据上面的【个人笔记】与【历史经验】回答" in EXECUTOR_PROMPT
    assert "资料里没有的" in EXECUTOR_PROMPT
    assert "个人资料类问题禁止调用 web_search" in EXECUTOR_PROMPT


def test_executor_prompt_notes_scope_and_anniversary_boundary():
    """【防回归】资料范围必须覆盖上传文档（技术方案/规范），且"什么时候"不得被当成查纪念日。"""
    assert "【个人笔记】可能是简历" in EXECUTOR_PROMPT
    assert "技术方案、规范文档" in EXECUTOR_PROMPT
    assert "什么时候/时间/几点" in EXECUTOR_PROMPT
    assert "不要调用 query_anniversary" in EXECUTOR_PROMPT


def test_infer_extra_tools_no_tool_for_notes_timing_question():
    """资料内容问法（"实施时间节点与责任分工在什么时候"）不触发任何工具兜底：
    不是纪念日查询（消息无"纪念日/生日"），开关关闭时也不补联网。"""
    extra = infer_extra_tools("实施时间节点与责任分工在什么时候", called=[], web_search_enabled=False)
    assert extra == []


def test_executor_prompt_web_search_rule_dynamic():
    """联网规则文案随开关切换：关闭时不出现"必须调用 web_search"指令。"""
    base = dict(query="q", subtask="s", now="now", notes="n", memory="m", prior="p", history="h")
    off_prompt = EXECUTOR_PROMPT.format(**base, web_search_rule=WEB_SEARCH_RULE_OFF)
    on_prompt = EXECUTOR_PROMPT.format(**base, web_search_rule=WEB_SEARCH_RULE_ON)
    assert "本次对话联网搜索已关闭" in off_prompt
    assert "不要调用 web_search" in off_prompt
    assert "必须调用 web_search 联网搜索最新信息后再回答" not in off_prompt
    assert "必须调用 web_search 联网搜索最新信息后再回答" in on_prompt


async def test_executor_personal_question_prompt_sees_switch(monkeypatch, base_state):
    """资料类问题 + 开关关闭 + 无召回：executor 的 HumanMessage 同时带资料空位与关闭规则。"""
    fake = FakeLLM(stream_scripts=[[text_chunk("（模型不应编造，这里只验证 prompt）")]])
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    st = dict(
        base_state,
        query="我叫什么名字",
        knowledge_context="暂无个人笔记",
        memory_context="暂无历史经验",
        notes_found=False, memory_found=False,
        web_search_enabled=False,
    )
    await executor(st)
    human = fake.human_prompts()[0]
    assert "个人笔记：暂无个人笔记" in human
    assert "本次对话联网搜索已关闭" in human
    assert "必须调用 web_search 联网搜索最新信息后再回答" not in human


# ===== 幻觉防线：资料类问题无召回 =====

async def test_reviewer_anti_hallucination_no_recall(monkeypatch, base_state):
    """资料类问题 + 检索无召回：模型即便编造了具体答案，reviewer 也直接以"未找到"结束，不调 LLM。"""
    fake = FakeLLM(script=[aim('{"score": 8, "reason": "看起来回答了"}')])
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    out = await reviewer(dict(
        base_state,
        query="我叫什么名字",
        draft_answer="你叫小寳，是个可爱的AI宠物",   # 模型编造的内容
        tool_calls=[],
        notes_found=False, memory_found=False,
    ))
    assert out["next_step"] == "finish"
    assert "没找到" in out["final_answer"]
    assert "你的资料" in out["final_answer"]
    assert out["review_score"] == 0
    assert "禁止编造" in out["review_reason"]
    assert fake.script == [aim('{"score": 8, "reason": "看起来回答了"}')]   # LLM 未被调用
    assert fake.script  # script 原样保留 = 防线代码级生效


async def test_reviewer_anti_hallucination_allows_when_recalled(monkeypatch, base_state):
    """同一资料类问题但检索有召回：防线不误伤，正常走 LLM 质检。"""
    fake = FakeLLM(script=[aim('{"score": 9, "reason": "依据资料回答了姓名"}')])
    monkeypatch.setattr("app.graph.nodes.llm", fake)
    out = await reviewer(dict(
        base_state,
        query="我叫什么名字",
        draft_answer="你叫钟永旺，来自丽江文化旅游学院。",
        tool_calls=[],
        notes_found=True, memory_found=False,
    ))
    assert out["next_step"] == "finish"
    assert out["review_score"] == 9
    assert out["final_answer"] == "你叫钟永旺，来自丽江文化旅游学院。"


async def test_export_anti_hallucination_override():
    """chat 出口兜底：资料类问题 + 无召回 + 无工具时，即便链路输出了编造内容，final 事件也强制替换为"未找到"。"""
    graph = FakeGraph(
        events=[],
        state_values={
            "final_answer": "你叫小寳，还做过微针和热玛吉。",   # 幻觉内容
            "tool_calls": [],
            "notes_found": False,
            "memory_found": False,
        },
    )
    events = await collect(run_chat_stream(graph, "我叫什么名字", uid=42, session_id="s1", web_search=False))
    finals = [e for e in events if e.startswith("event: final")]
    assert finals, "必须有 final 事件"
    assert "没找到" in finals[0]
    assert "小寳" not in finals[0]
    assert "热玛吉" not in finals[0]


async def test_export_falls_back_to_notes_when_tool_blocked(monkeypatch):
    """【防回归】模型把资料问题误当纪念日查询（query_anniversary 被守卫拦截、工具结果空），
    但链路有召回时：final 基于资料重新回答，不再直出"我帮你查一下"过渡语。"""
    fake = FakeLLM(script=[aim("从你上传的《AI全栈RAG知识库系统开发技术方案.docx》来看，实施分五个阶段：第一阶段第1-2周需求调研，责任人产品+运维开发…")])
    monkeypatch.setattr("app.routes.chat.llm", fake)
    graph = FakeGraph(
        events=[],
        state_values={
            "final_answer": "我帮你查一下有哪些纪念日哈～稍等",   # 模型过渡语（工具被拦截）
            "tool_calls": [{"name": "query_anniversary", "args": {}}],
            "knowledge_context": "【AI全栈RAG知识库系统开发技术方案.docx】\n五、实施时间节点与责任分工\n第一阶段 第1-2周 需求调研与基础环境搭建 责任人：产品+运维开发",
            "memory_context": "暂无历史经验",
            "notes_found": True,
            "memory_found": False,
        },
    )
    events = await collect(run_chat_stream(
        graph, "实施时间节点与责任分工在什么时候", uid=2, session_id="s1", web_search=False,
    ))
    finals = [e for e in events if e.startswith("event: final")]
    assert finals, "必须有 final 事件"
    assert "技术方案" in finals[0]        # 基于资料重新回答
    assert "纪念日" not in finals[0]      # 不再是误判的过渡语
    assert fake.script == []              # answer_from_notes 消费了唯一响应


async def test_summarize_answer_appends_titled_sources(monkeypatch):
    """【防回归】联网搜索来源以 markdown 链接 [标题](URL) 附在末尾，而非裸 URL。
    （用户实测：引用的链接全是字符串域名，没有名称）"""
    from app.routes.chat import summarize_answer

    fake = FakeLLM(script=[aim("云南整体是西北高、东南低的高原省份，地形立体，多高山峡谷与坝子。")])
    monkeypatch.setattr("app.routes.chat.llm", fake)
    tool_out = (
        "云南是高原省份，整体西北高、东南低，地形非常立体，包含高山、峡谷、高原、坝子等多种地貌类型。\n"
        "- 云南省（维基百科）：云南省地处云贵高原，西部为横断山脉高山峡谷区（来源：https://zh.wikipedia.org/wiki/云南）\n"
        "- ：这条只有正文没有标题（来源：https://www.ynxc.gov.cn/html/2024/yns_0418/11831.html）"
    )
    out = await summarize_answer("云南的地貌是什么样的", [tool_out])
    assert "参考来源：" in out
    assert "- [云南省（维基百科）](https://zh.wikipedia.org/wiki/云南)" in out
    assert "- [www.ynxc.gov.cn](https://www.ynxc.gov.cn/html/2024/yns_0418/11831.html)" in out   # 无标题退化为域名链接（用户实测裸 URL 体验差）
    assert "（来源：" not in out
    assert fake.script == []              # 总结消费了唯一响应


async def test_summarize_answer_appends_titled_sources(monkeypatch):
    """【防回归】联网搜索来源以 markdown 链接 [标题](URL) 附在末尾，而非裸 URL。
    （用户实测：引用的链接全是字符串域名，没有名称）"""
    from app.routes.chat import summarize_answer

    fake = FakeLLM(script=[aim("云南整体是西北高、东南低的高原省份，地形立体，多高山峡谷与坝子。")])
    monkeypatch.setattr("app.routes.chat.llm", fake)
    tool_out = (
        "云南是高原省份，整体西北高、东南低，地形非常立体，包含高山、峡谷、高原、坝子等多种地貌类型。\n"
        "- 云南省（维基百科）：云南省地处云贵高原，西部为横断山脉高山峡谷区（来源：https://zh.wikipedia.org/wiki/云南）\n"
        "- ：这条只有正文没有标题（来源：https://www.ynxc.gov.cn/html/2024/yns_0418/11831.html）"
    )
    out = await summarize_answer("云南的地貌是什么样的", [tool_out])
    assert "参考来源：" in out
    assert "- [云南省（维基百科）](https://zh.wikipedia.org/wiki/云南)" in out
    assert "- [www.ynxc.gov.cn](https://www.ynxc.gov.cn/html/2024/yns_0418/11831.html)" in out   # 无标题退化为域名链接（用户实测裸 URL 体验差）
    assert "（来源：" not in out
    assert fake.script == []              # 总结消费了唯一响应
