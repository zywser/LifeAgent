# Life Agent 后端结构与重点

> 技术栈：FastAPI + LangGraph + MySQL + Redis(向量库/checkpointer) + DashScope(OpenAI 兼容模式)
> 本文只列后端，前端见 `web/` 目录。

## 目录结构

```
backend/
├── .env / .env.example      配置（密钥、DB、Redis、Tavily、LangSmith）
├── requirements.txt
├── sql/init.sql             建表 SQL
├── Dockerfile
└── app/
    ├── main.py              FastAPI app 入口（lifespan、路由挂载）
    ├── config.py            Settings
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
    │   ├── nodes.py         6 个节点实现
    │   ├── router.py        条件边
    │   └── tools.py         4 个 Tool Calling 工具
    │
    ├── routes/              业务 API
    │   ├── chat.py          SSE 流式对话
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
- 节点开始/结束用 SSE 事件 `node_start` / `node_end`，前端右侧链路据此点亮
- 链路结束后从 `graph.aget_state(config)` 拿最终 state
- 再根据 `tool_calls` 真正执行工具（`TOOL_MAP[name].ainvoke(args)`）
- 最后把最终回答写回向量记忆库

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

- LangSmith 全链路 trace（`LANGSMITH_TRACING=true`）
- 项目名 `Life-Agent`
- 在 LangSmith 上能看到每个节点的 LLM 调用、token 用量、工具入参

## 五、生产差距（可以说的改进方向）

- 数据库迁移用 Alembic，现在靠 `sql/init.sql`
- 异常 fallback：LLM 调用失败时的优雅降级
- prompt injection 防护
- 车票/酒店实时数据要接垂直 API（Tavily 只能搜网页摘要）
- 单元测试和集成测试
