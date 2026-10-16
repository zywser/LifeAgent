# Life Agent 后端结构与重点

> 技术栈：FastAPI + LangGraph + MySQL + Redis(向量库/checkpointer) + DashScope(OpenAI 兼容模式)
> 本文只列后端，前端见 `web/` 目录。

## 目录结构

```
backend/
├── .env / .env.example      配置（密钥、DB、Redis、Tavily、LangSmith）
├── requirements.txt
├── requirements-dev.txt     评测依赖（pytest + pytest-asyncio）
├── pytest.ini               评测配置
├── tests/                   ⭐ 自动化评测（56 条，全部离线可复现）
├── sql/init.sql             建表 SQL
├── Dockerfile
└── app/
    ├── main.py              FastAPI app 入口（lifespan、路由挂载）
    ├── config.py            Settings + LangSmith 显式环境注入
    ├── llm.py               ChatOpenAI + embeddings
    ├── deps.py              依赖注入（get_current_user）
    │
    ├── auth/                登录注册、JWT、refresh
    │   ├── router.py
    │   └── service.py
    │
    ├── db/
    │   ├── base.py          SQLAlchemy 基类
    │   ├── session.py       同步 SessionLocal
    │   └── models.py        9 张业务表
    │
    ├── graph/               ⭐ LangGraph 多智能体核心
    │   ├── state.py         AgentState（节点间共享状态）
    │   ├── build.py         StateGraph 编译（节点+边）
    │   ├── nodes.py         6 个节点实现（reviewer 带一致性钳制）
    │   ├── router.py        条件边
    │   └── tools.py         14 个 Tool Calling 工具
    │
    ├── routes/              业务 API
    │   ├── chat.py          SSE 流式对话（run_chat_stream 可独立评测）
    │   ├── notes.py         笔记上传/删除
    │   ├── life.py          记账/待办/日记/储蓄/纪念日
    │   ├── summary.py       数据汇总
    │   ├── conversations.py 对话历史
    │   ├── memory.py        记忆
    │   ├── impression.py    印象
    │   ├── notify.py        未读通知
    │   └── sync.py          同步
    │
    ├── vector_store/
    │   └── factory.py       向量库、checkpointer、删向量
    │
    ├── ingest/
    │   └── loader.py         文件读取 + 文本切分
    │
    └── scheduler.py         APScheduler 定时任务
```

## 一、必看核心（讲项目时就靠这几个）

### 1. `graph/state.py` —— 节点间共享的数据结构

LangGraph 的所有节点通过一个 TypedDict 通信。核心字段：

```python
class AgentState(TypedDict, total=False):
    query: str                  # 用户原始问题
    plan: list[str]             # planner 拆出的子任务列表
    subtask_index: int          # 当前执行到第几个子任务
    subtask_results: list[str]   # 每个子任务的执行结果
    knowledge_context: str       # 检索到的笔记
    memory_context: str         # 检索到的历史经验
    draft_answer: str           # synthesizer 汇总稿
    final_answer: str           # reviewer 通过后的最终回答
    tool_calls: list[dict]      # 累积的工具调用决策
    retry_count: int            # reviewer 打回次数
    review_score / review_reason: int / str
    uid: int
```

看懂它就看懂了整个多智能体怎么传数据。

### 2. `graph/build.py` —— 图的拓扑

```
START → supervisor → planner → retriever
                                ↓
                    executor ←──┘  循环执行每个子任务
                        ↓ 全部完成
                    synthesizer → reviewer
                                      ↓
                                通过→END / 不通过→planner
```

```python
graph.add_edge("retriever", "executor")
graph.add_conditional_edges("executor", route_after_executor,
    {"executor": "executor", "synthesizer": "synthesizer"})
graph.add_edge("synthesizer", "reviewer")
graph.add_conditional_edges("reviewer", route_after_reviewer,
    {"planner": "planner", END: END})
```

这是整个项目的灵魂。

### 3. `graph/nodes.py` —— 6 个节点

| 节点 | 作用 |
|---|---|
| `supervisor` | 入口空壳，做状态初始化 |
| `planner` | LLM 把用户需求拆成 ≤3 个子任务，重置执行状态 |
| `retriever` | 从 Redis 向量库召回笔记和记忆（不调 LLM） |
| `executor` | **循环节点**，每次执行一个子任务，`llm.bind_tools(TOOLS)` 流式输出 |
| `synthesizer` | 把多个子任务结果串成一段自然的回答 |
| `reviewer` | LLM 打分（≥7 通过），不通过打回 planner，最多 3 次 |

### 4. `graph/tools.py` —— 4 个工具

| 工具 | 作用 |
|---|---|
| `record_expense` | 记账（amount/category/kind/note） |
| `create_todo` | 建待办（带 `due_at`，支持相对时间） |
| `write_diary` | 写日记 |
| `web_search` | Tavily 联网搜索 |

**关键设计：决策与执行分离**
- executor 里模型只决定"调什么工具、参数是什么"，存进 state，**不真正写库**
- reviewer 质检通过后，由 `chat.py` 才真正执行工具
- 这样 reviewer 打回重试时，不会重复写库

`uid` 用 `InjectedToolArg` 注入，对模型隐藏。

### 5. `routes/chat.py` —— SSE 流式 + 工具执行

- `graph.astream_events(version="v2")` 把 token 实时推给前端
- 事件序列：`node_start` / `node_end`（带节点详情）/ `token` / `tool_call` / `final` / `error`（带 error_type）
- `node_end` 详情：planner 带 plan、executor 带 current_subtask/subtask_index、reviewer 带 review_score/review_reason/retry
- 链路结束后从 `graph.aget_state(config)` 拿最终 state
- 再根据 `tool_calls` 真正执行工具（`TOOL_MAP[name].ainvoke(args)`）
- 最后把最终回答写回向量记忆库
- 流式逻辑抽成顶层 `run_chat_stream(graph, message, uid, session_id, web_search=False)`，评测可直接注入 fake graph 验证事件序列；`web_search` 透传进初始 state 与工具兜底/执行层

### 6. `llm.py` —— LLM 客户端

```python
llm = ChatOpenAI(
    model="qwen-plus",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature=0.7,
    streaming=True,
)
embeddings = OpenAIEmbeddings(
    model="text-embedding-v1",
    check_embedding_ctx_length=False,   # DashScope 兼容模式只接受原始字符串
)
```

走 DashScope 的 OpenAI 兼容模式，不用 `langchain_community` 里已废弃的 `ChatTongyi`。

## 二、次重点（出问题会去翻）

### `vector_store/factory.py`

- `get_notes_store(uid)` / `get_memory_store(uid)`：两个 RedisVectorStore
- `get_checkpointer()`：LangGraph 的 Redis checkpointer，支持多轮对话记忆
- `delete_note_vectors(uid, doc_id)`：笔记删除时按 `{key_prefix}:{doc_id}_c*` scan 清向量

### `db/models.py`

9 张表：User、RefreshToken、Note、Expense、Todo、Habit、SavingsGoal、Diary、Anniversary、Notification。

### `scheduler.py`

APScheduler 跑 8 个定时任务（提醒、日报等）。注意：**job 必须是同步函数**，AsyncIOScheduler 会自动丢线程池；之前踩过 async 包同步调用阻塞事件循环的坑。

## 三、踩过的坑（讲项目时的亮点）

| 坑 | 解决 |
|---|---|
| DashScope 兼容模式 embedding 报 400 | `OpenAIEmbeddings(check_embedding_ctx_length=False)` |
| reviewer 把"工具调用导致正文空"误判为"没理解需求" | 空回答前先检查 `tool_calls`，有工具调用直接通过 |
| LangSmith 读不到 `.env` 变量 | `config.py` 在 Settings 加载前先 `load_dotenv()` 注入 os.environ |
| 笔记删除后向量残留 | 上传时用可预测 key `{doc_id}_c{i}`，删除时 scan 清 |
| async 路由里跑同步 DB 阻塞事件循环 | scheduler 的 job 改成同步函数 |

## 四、可观测性

- LangSmith 全链路 trace（`LANGSMITH_TRACING=true`），项目名 `Life-Agent`
- `config.py` 启动时**显式**把 `LANGCHAIN_TRACING_V2` / `LANGCHAIN_PROJECT` / `LANGSMITH_*` 写入环境变量（不再依赖第三方库读 `.env` 的时机）；未配 `LANGSMITH_API_KEY` 自动关闭 tracing
- 每个 run 带 `metadata: {uid, session_id, thread_id, web_search}`，LangSmith 上可按用户/会话检索调用链路
- 在 LangSmith 上能看到每个节点的 LLM 调用、token 用量、工具入参
- SSE 事件：`node_start` / `node_end`（带详情）/ `token` / `tool_call` / `final` / `error`（带 error_type）

## 四.5、联网搜索开关 + 资料联动（防幻觉）

**背景**：资料页上传 PDF 后对话出现幻觉（"我叫什么名字"答出无关的"小寳/Little Fox 中文歌"、项目答成"微针热玛吉"）——根因是 web_search 宽触发把个人资料问题拿去联网、retriever 问法一变就漏召回、prompt 无资料优先约束。

**实现要点（三层）**：

1. **开关（默认关，`ChatRequest.web_search=False`）**：
   - `infer_extra_tools(message, called, web_search_enabled=True)`：关闭时不补 web_search（幻觉主源断掉）；
   - `execute_tool_calls(..., web_search_enabled=True)`：关闭时过滤模型自行决策的 web_search（`name == "web_search" and not enabled → continue`）；
   - executor prompt 动态规则：`EXECUTOR_PROMPT.format(web_search_rule=WEB_SEARCH_RULE_ON/OFF)`——关闭时提示"不要调用 web_search，实时问题如实说明"。
2. **retriever 升级（`nodes.py`）**：k 4→6；`strip_personal_shell()` 剥离"我上传了/我的资料/我之前"等壳词；首次无结果时用剥壳核心词**二次检索**；结果经 `_format_retrieved()` 带 `【filename】` 前缀；写入 `notes_found`/`memory_found` 命中标记。
3. **幻觉防线（代码级双保险）**：
   - reviewer：`is_personal_data_query(query)` 命中且 `notes_found`/`memory_found` 均 False → 不调 LLM，直接 `final_answer="你的资料里没找到…"`、`review_score=0` 结束；
   - chat 出口兜底：链路结束后同条件强制替换 `answer`（防模型输出绕过）。

**坑**：
- executor prompt 加了 `{web_search_rule}` 占位后，`format()` 必须同步传参，否则 KeyError（已由新评测 `test_executor_prompt_web_search_rule_dynamic` 覆盖）。
- 连续低分打回会把默认 `recursion_limit=25` 耗完：plan 拆 2 个子任务时 4 轮重试恰好 1+4×6=25 超步触顶报 `Recursion limit reached`（复现自用户提问"RAG知识库中项目目标与范围"）。修复：`run_chat_stream` 的 config 加 `"recursion_limit": 60`（最坏正常路径 1+4×7=29 超步，留足安全垫），新增防回归评测 `test_graph_retry_loop_finishes_within_recursion_limit`。
- 资料问法换表述就答错（用户实测"实施时间节点与责任分工在什么时候"答成"帮你查纪念日"）：向量库诊断确认**内容在且能召回**（uid=2 的 docx 12 chunk，"时间节点"问法命中第 0 条即实施表格），问题在模型决策——问句含"什么时候"触发模型联想 query_anniversary，工具被误调守卫拦下后模型过渡语"帮你查一下"直出给用户。修复：① EXECUTOR_PROMPT 明确【个人笔记】包含技术方案/规范文档等所有上传资料，且"什么时候/时间/几点"不等于查纪念日（只有"纪念日/生日/倒计时/还有几天/XX日子"才算）；② chat 出口新增 `answer_from_notes()`：模型决策的工具被守卫拦截（结果空）但链路有召回时，基于资料重新回答，不再直出过渡承诺。
- 追问卡住（用户实测：问完"实施时间节点"后追问"有哪些风险"，Executor 反复执行 7 次仍不出结果）：根因是**链路没有跨轮对话历史**——executor 的 prior 只是本轮子任务结果，追问句没有上文可依，模型答偏 → reviewer 打回 → 重试循环（虽已加 recursion_limit=60 不会报错，但重试多轮感知上像卡死）。修复：① 前端 `streamChat` 把真实会话 id（`run.currentId`）传给后端；② 后端 `load_history_text()` 读 conversations 表最近 10 条消息（排除当前问句）注入 state；③ executor/planner prompt 各加"对话历史"数据位。首轮回答质量提升后重试循环大幅减少。
- Executor 无限执行/一直执行中（用户实测 Executor(9) 且不重新对话停不下来）：根因是**executor 的 LLM 流式调用没有超时**——ChatOpenAI 默认 600s 超时，DashScope 限流/网络卡顿时单次 astream 可挂数分钟，SSE 一直"执行中"。修复：① executor 的 astream 用 `asyncio.timeout(EXECUTOR_TIMEOUT=60)` 包裹，超时返回"（这一部分获取回答超时…）"跳过该子任务继续链路；② `subtask_index > 6` 硬上限杜绝子任务索引异常膨胀导致的无限循环；③ llm.py ChatOpenAI 加 `timeout=60, max_retries=2`。前端另有"停止"按钮兜底：发送后按钮变停止，点击 AbortController 中断 SSE，全部链路停止。

## 五、自动化评测（tests/）

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -v     # 68 条，全部离线可复现，约 5-6 秒
```

| 组 | 条数 | 覆盖 |
|---|---|---|
| 工具调用 | 16 | 决策捕获、决策/执行分离、uid 防伪造注入、漏调兜底、防误记、误调守卫、工具落库 |
| 提示词注入 | 8 | 直接/间接注入隔离、危险动作无工具可调、planner 当数据处理、链路级端到端 |
| 回答质量 | 11 | 质检通过/重试/上限、一致性钳制（评分与理由不符强降分）、工具驱动回答、整图路径 |
| 可观测性 | 7 | SSE 事件序列、token/工具/质检事件、异常类型、LangSmith 环境、run metadata |
| 联网开关与资料联动 | 14 | 壳词剥离、二次检索命中/无召回标记、开关关闭不补不执行 web_search、prompt 资料优先与联网规则动态切换、资料类无召回 reviewer 防编造（不调 LLM）、chat 出口兜底、有召回不误伤 |
| 递归安全 | 1 | 连续低分打回 4 轮正常兜底结束，不触发 Recursion limit |
| 资料问法边界 | 3 | 资料范围覆盖上传文档、"什么时候"不等于查纪念日、工具拦截后基于资料重答 |
| 上下文记忆 | 5 | 会话历史读取（排除当前问句/占位兜底）、executor/planner 历史注入、链路透传 |
| 执行挂起防护 | 2 | executor LLM 超时兜底、subtask_index 硬上限防无限循环 |
| 联网来源标题 | 1 | 参考来源 [标题](URL) 呈现、无标题退化裸链接 |

关键设计：FakeLLM（脚本化响应 + 流式 + tool_calls）、sqlite 内存库替换 SessionLocal、
InMemorySaver 替换 Redis checkpointer、FakeStore/SelectiveStore 替换向量库——不连任何外部服务。

## 六、生产差距（可以说的改进方向）

- 数据库迁移用 Alembic，现在靠 `sql/init.sql`
- 异常 fallback：LLM 调用失败时的优雅降级
- 车票/酒店实时数据要接垂直 API（Tavily 只能搜网页摘要）
- 评测未覆盖前端 E2E 与多用户并发；提示词注入为离线规则级验证，生产建议叠加云端护栏
- "资料问答技能按钮"（显式锁定只答资料模式）按用户决策暂缓，视模块一+二实际效果再定
- Redis checkpointer 旧 thread 无自动清理
