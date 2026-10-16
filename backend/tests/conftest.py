"""评测公共 fixtures：离线可复现的依赖注入。

原则：
- 不连真实 MySQL / Redis / 外部 API；评测期间不向 LangSmith 上报；
- LLM 用脚本化 FakeLLM；工具写库走 sqlite 内存库；向量库/checkpointer 用假对象。
"""
from __future__ import annotations

import os

# 先正常初始化 Settings 与 LangSmith 配置（保持 config.py 的 apply_langsmith_env 接入逻辑原样执行，
# 使 Settings.langsmith_tracing 仍按 .env 解析），随后强制关闭 SDK 上报变量，保证评测全程离线。
from app import config as _config  # noqa: F401  触发 apply_langsmith_env()

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from langchain_core.documents import Document

from tests.fake_llm import FakeLLM


# ===== 假向量库 / 假记忆库 =====
class FakeStore:
    """替代 RedisVectorStore：可预设召回文档，add_texts 只做记录不联网。"""

    def __init__(self, docs: list[str] | None = None):
        self.docs = [Document(page_content=d) for d in (docs or [])]
        self.added: list[str] = []

    def similarity_search(self, query: str, k: int = 4):
        return self.docs[:k]

    def add_texts(self, texts, metadatas=None, **kwargs):
        self.added.extend(texts)
        return [f"mock-{i}" for i in range(len(texts))]


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def patch_llm(monkeypatch, fake_llm):
    """把图节点与 chat 路由使用的 LLM 单例替换为 FakeLLM。"""
    monkeypatch.setattr("app.graph.nodes.llm", fake_llm)
    monkeypatch.setattr("app.routes.chat.llm", fake_llm)
    return fake_llm


@pytest.fixture
def sqlite_db(monkeypatch):
    """sqlite 内存库替换 tools.SessionLocal：工具写库类用例真实落库、可断言，且不碰 MySQL。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr("app.graph.tools.SessionLocal", TestingSessionLocal)
    # chat.py 沉淀记忆也会写 MemoryItem，一并指向测试库
    monkeypatch.setattr("app.routes.chat.SessionLocal", TestingSessionLocal)
    return TestingSessionLocal


@pytest.fixture
def mock_stores(monkeypatch):
    """向量库（笔记/记忆检索）与记忆写入全部指向 FakeStore，不连 Redis。"""
    notes = FakeStore()
    memory = FakeStore()
    monkeypatch.setattr("app.graph.nodes.get_notes_store", lambda uid: notes)
    monkeypatch.setattr("app.graph.nodes.get_memory_store", lambda uid: memory)
    monkeypatch.setattr("app.routes.chat.get_memory_store", lambda uid: memory)
    return {"notes": notes, "memory": memory}


@pytest.fixture
def mem_checkpointer(monkeypatch):
    """把 build_graph 用的 Redis checkpointer 换成内存版，链路级评测不依赖 Redis。"""
    from langgraph.checkpoint.memory import InMemorySaver
    saver = InMemorySaver()

    async def fake_get_checkpointer():
        return saver

    monkeypatch.setattr("app.graph.build.get_checkpointer", fake_get_checkpointer)
    return saver


@pytest.fixture
def base_state() -> dict:
    """节点级评测常用的最小 state。"""
    return {
        "query": "测试问题",
        "uid": 42,
        "plan": ["测试子任务"],
        "subtask_index": 0,
        "subtask_results": [],
        "knowledge_context": "暂无个人笔记",
        "memory_context": "暂无历史经验",
        "tool_calls": [],
        "draft_answer": "",
        "retry_count": 0,
    }
