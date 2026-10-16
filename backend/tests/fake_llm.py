"""评测用可编程 FakeLLM 与 FakeGraph。

真实 LLM 调用（DashScope）在评测中不可控、花钱、还可能被限流；
这里用脚本化的假对象把链路跑成确定性的：
- FakeLLM：按调用顺序消费预设响应，支持 ainvoke（planner/synthesizer/reviewer）
  与 astream（executor 真流式 + bind_tools 工具决策），并记录收到的 messages 供断言。
- FakeGraph：模拟 LangGraph 编译图，按预设 v2 事件流喂给 run_chat_stream，
  用于验证 SSE 事件序列与异常路径。
"""
from __future__ import annotations

import types

from langchain_core.messages import AIMessage, AIMessageChunk


class FakeLLM:
    """脚本化假 LLM。

    - script：list[AIMessage]，ainvoke 按序消费（planner / synthesizer / reviewer）。
    - stream_scripts：list[list[AIMessageChunk]]，astream 按序消费（executor 每轮子任务）。
    - 所有收到的 messages 追加进 calls，测试据此断言"用户输入没有进入 SystemMessage"等。
    """

    def __init__(self, script=None, stream_scripts=None):
        self.script = list(script or [])
        self.stream_scripts = list(stream_scripts or [])
        self.calls: list[list] = []          # 每次 ainvoke / astream 收到的完整 messages
        self.bind_calls: list = []           # bind_tools 收到的工具列表

    # ---- 与 langchain ChatModel 对齐的接口 ----
    async def ainvoke(self, messages, **kwargs):
        self.calls.append(messages)
        if self.script:
            return self.script.pop(0)
        return AIMessage(content="（默认 fake 回复）")

    async def astream(self, messages, **kwargs):
        self.calls.append(messages)
        if self.stream_scripts:
            chunks = self.stream_scripts.pop(0)
            for c in chunks:
                yield c
        else:
            yield AIMessageChunk(content="（默认 fake 流式回复）")

    def bind_tools(self, tools, **kwargs):
        self.bind_calls.append(tools)
        return self

    # ---- 断言辅助 ----
    def system_prompts(self) -> list[str]:
        """所有调用里的 SystemMessage 内容（用于验证系统提示未被用户输入污染）。"""
        out = []
        for msgs in self.calls:
            for m in msgs:
                if getattr(m, "type", "") == "system":
                    out.append(m.content)
        return out

    def human_prompts(self) -> list[str]:
        out = []
        for msgs in self.calls:
            for m in msgs:
                if getattr(m, "type", "") == "human":
                    out.append(m.content)
        return out


def text_chunk(text: str) -> AIMessageChunk:
    return AIMessageChunk(content=text)


def tool_call_chunk(name: str, args: dict, call_id: str = "call_1", index: int = 0) -> AIMessageChunk:
    """构造带工具调用决策的流式 chunk（args 需要 JSON 字符串）。"""
    import json
    return AIMessageChunk(
        content="",
        tool_call_chunks=[{
            "name": name,
            "args": json.dumps(args, ensure_ascii=False),
            "id": call_id,
            "index": index,
        }],
    )


def aim(content: str) -> AIMessage:
    return AIMessage(content=content)


def aim_tool_call(name: str, args: dict, call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


# ===== LangGraph v2 事件构造器 =====
def ev_chain_start(name: str, data: dict | None = None) -> dict:
    return {"event": "on_chain_start", "name": name, "data": data or {}}


def ev_chain_end(name: str, output) -> dict:
    return {"event": "on_chain_end", "name": name, "data": {"output": output}}


def ev_model_stream(text: str) -> dict:
    return {"event": "on_chat_model_stream", "name": "ChatOpenAI",
            "data": {"chunk": AIMessageChunk(content=text)}}


def ev_model_end(content: str = "", tool_calls: list[dict] | None = None) -> dict:
    msg = AIMessage(content=content, tool_calls=tool_calls or [])
    return {"event": "on_chat_model_end", "name": "ChatOpenAI", "data": {"output": msg}}


class FakeGraph:
    """模拟 LangGraph 编译图：按预设事件流喂给 run_chat_stream。"""

    def __init__(self, events=None, state_values=None, error: Exception | None = None):
        self.events = list(events or [])
        self.state_values = dict(state_values or {})
        self.error = error
        self.captured_config = None
        self.captured_inputs = None

    async def astream_events(self, inputs, config=None, **kwargs):
        self.captured_inputs = inputs
        self.captured_config = config
        if self.error is not None:
            raise self.error
        for e in self.events:
            yield e

    async def aget_state(self, config):
        return types.SimpleNamespace(values=dict(self.state_values))


async def collect(gen):
    """把 async generator 的所有产出收集成列表（评测统一入口）。"""
    return [item async for item in gen]
