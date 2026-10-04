# Life Agent

个人生活管家多智能体平台：注册登录后，用自然语言管理生活——记账、待办、习惯打卡、日记、喝水、存钱、纪念日、笔记知识库、实时信息查询，全部通过一个像朋友一样的 AI 助手完成。Supervisor 调度 Planner → Retriever → Executor → Synthesizer → Reviewer 五段链路，把任务拆解、检索、执行、汇总、质检串成一次流畅对话，结果写入个人长期记忆向量库。

## 功能总览

| 模块 | 说明 | 入口 |
|---|---|---|
| 智能对话 | 多智能体链路 + SSE 流式输出 + 节点执行时间线 | `/chat` |
| 生活规划 | 结合个人笔记与历史经验拆解行程/任务，可联网查实时信息 | 对话 |
| 记账 | 支出/收入记录、分类、本周消费统计 | `/accounting` |
| 待办 | 带提醒时间的待办清单，到点自动推送通知 | `/todo` |
| 习惯打卡 | 每日打卡、连续天数、按时提醒 | `/habit` |
| 日记 | 心情记录、AI 情绪小结、一周情绪趋势 | `/diary` |
| 喝水 | 每日杯数记录，近 7 天回顾 | `/water` |
| 存钱 | 目标金额、进度、每日应存测算、周一进度提醒 | `/savings` |
| 纪念日 | 生日/纪念日倒计时，前 3 天起逐日提醒 | `/anniversary` |
| 笔记知识库 | 上传 MD/TXT/PDF/Word，自动切分向量化，语义检索 | `/notes` |
| 经验记忆 | Agent 沉淀的任务经验与日记摘要，可查看/删除 | `/memory` |
| Agent 链路 | 节点拓扑与执行日志可视化 | `/graph` |
| 历史对话 | 云端持久化对话记录 | `/history` |
| 个人中心 | AI 对你的印象、账号信息 | `/profile` |

## 技术架构

```mermaid
flowchart LR
  Web[Vue 3 + Element Plus] -->|/api SSE| API[FastAPI]
  API --> Auth[(MySQL 鉴权)]
  API --> G[LangGraph Supervisor]
  G --> P[Planner] --> R[Retriever]
  R --> N[(Redis Notes 向量)] & M[(Redis Memory 向量)]
  R --> E[Executor 循环<br/>模型决策工具调用]
  E --> S[Synthesizer] --> V[Reviewer 质检]
  V -->|不通过 ≤3 次| P
  V -->|通过| API
  API -->|真正执行工具| T[14 个 Tool]
  T --> DB[(MySQL 业务表)]
  T --> TV[Tavily 联网搜索]
  API -->|写回| M
  G --> CK[Redis Checkpointer]
  Sched[APScheduler 定时任务] --> Noti[通知]
```

**技术栈**：FastAPI + LangGraph + SQLAlchemy + MySQL 8 + Redis Stack（向量库 / checkpointer / 缓存）+ DashScope（OpenAI 兼容模式，qwen-plus + text-embedding-v1）+ Tavily（联网搜索）+ Vue 3 + Element Plus + Docker Compose。

## 目录结构

```
Life Agent/
├── main.py                  # 本地开发入口（自动切到 backend 目录）
├── backend/
│   ├── .env.example         # 配置模板（复制为 .env 填写）
│   ├── requirements.txt
│   ├── sql/init.sql         # 建库脚本（业务表由 ORM 启动时自动创建）
│   ├── Dockerfile
│   └── app/
│       ├── main.py          # FastAPI 入口：lifespan 建表/补列/起调度器
│       ├── config.py        # pydantic-settings（先 load_dotenv 供 LangSmith 读取）
│       ├── llm.py           # ChatOpenAI + OpenAIEmbeddings（DashScope 兼容模式）
│       ├── deps.py          # get_current_user（JWT Bearer）
│       ├── auth/            # 注册/登录/刷新 token（bcrypt + JWT + refresh 轮换）
│       ├── db/              # SQLAlchemy 引擎/会话/14 张表模型
│       ├── graph/           # ⭐ LangGraph 多智能体核心
│       │   ├── state.py     # AgentState（节点间共享）
│       │   ├── build.py     # StateGraph 拓扑与编译
│       │   ├── nodes.py     # 6 个节点实现
│       │   ├── router.py    # 条件边路由
│       │   └── tools.py     # 14 个 Tool Calling 工具
│       ├── routes/          # chat / notes / life / summary / sync /
│       │                     # conversations / memory / impression / notify
│       ├── vector_store/    # Redis 向量库 / checkpointer / 删向量
│       ├── ingest/          # 笔记读取（md/txt/pdf/docx）与切分
│       └── scheduler.py     # APScheduler 8 个定时任务
├── web/                     # Vue 3 前端（16 个页面）
│   ├── src/views/           # 页面组件
│   ├── src/api/             # axios 封装 + token 刷新队列 + SSE 客户端
│   ├── src/stores/          # Pinia（auth / run）
│   ├── Dockerfile / nginx.conf
└── deploy/docker-compose.yml  # mysql + redis + backend + web 编排
```

## 多智能体核心设计

### 执行链路

```
START → supervisor → planner → retriever
                                        ↓
                            executor ←──┘  循环执行每个子任务
                                ↓ 全部完成
                            synthesizer → reviewer
                                          ↓
                                  通过→END / 不通过→planner（≤3 次）
```

| 节点 | 作用 |
|---|---|
| `supervisor` | 入口，初始化状态 |
| `planner` | LLM 把需求拆成 ≤3 个子任务（输出异常时回退固定方案） |
| `retriever` | 从 Redis 向量库召回个人笔记与历史经验（不调 LLM） |
| `executor` | 循环节点，`llm.bind_tools(TOOLS)` 流式执行每个子任务 |
| `synthesizer` | 汇总子任务结果成一段自然回答（≤1 段时跳过 LLM） |
| `reviewer` | LLM 打分（≥7 通过），不通过打回 planner，最多重试 3 次 |

### 关键设计：决策与执行分离

- executor 里模型只**决定**调用哪些工具、参数是什么，存进 `state.tool_calls`，**不真正写库**；
- reviewer 质检**通过后**，由 `chat.py` 才真正执行工具（`TOOL_MAP[name].ainvoke(args)`）；
- 这样 reviewer 打回重试时不会重复写库；
- 模型漏调用工具时，`chat.py` 按消息里的明确业务意图（打卡/喝水/纪念日/存钱等强信号）做关键词兜底补调，保证动作真实落库、查询有据可答。

### 14 个工具

| 工具 | 作用 |
|---|---|
| `record_expense` | 记账（支出/收入） |
| `create_todo` | 建待办（支持相对时间换算 ISO） |
| `write_diary` | 写日记 |
| `web_search` | Tavily 联网搜索（车票/酒店/天气/新闻等实时信息） |
| `check_habit` / `query_habits` | 习惯打卡 / 查询进度与连续天数 |
| `add_anniversary` / `query_anniversary` | 记纪念日 / 查倒计时 |
| `record_water` / `query_water` | 记录喝水 / 查询近 7 天 |
| `query_savings` / `update_savings` | 存钱进度 / 存入一笔 |
| `query_notes` / `query_memory` | 主动检索笔记 / 历史记忆 |

`uid` 通过 `InjectedToolArg` 注入，对模型隐藏；所有向量索引、checkpoint thread 均带 `user:{uid}` 前缀实现用户隔离。

### 对话流（SSE）

`POST /chat` 返回 `text/event-stream`，事件序列：`node_start` / `node_end`（链路节点点亮）、`token`（流式 token）、`final`（最终回答，工具结果优先）、`error`。每轮请求使用唯一 `thread_id`，避免上一轮的中间状态串入新问题。

## 快速开始

### Docker Compose（推荐）

```bash
# 1. 准备配置
cp backend/.env.example backend/.env
#    编辑 backend/.env，至少填写：
#    SECRET_KEY（随机长字符串）、MYSQL_PASSWORD、MYSQL_ROOT_PASSWORD、
#    DASHSCOPE_API_KEY（阿里云百炼）、TAVILY_API_KEY（可选，联网搜索）、
#    LANGSMITH_API_KEY（可选，链路追踪）

# 2. 启动（mysql + redis + backend + web）
docker compose -f deploy/docker-compose.yml up -d --build

# 3. 访问
open http://localhost
```

### 本地开发

```bash
# 后端
cd backend
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000         # 或运行根目录 main.py

# 前端
cd web
npm ci
npm run dev                                       # http://localhost:5173（/api 已代理）
```

MySQL 与 Redis 需自行启动，并保证 `backend/.env` 中的连接串可达。

## 配置项（backend/.env）

| 变量 | 说明 |
|---|---|
| `SECRET_KEY` | JWT 签名密钥，**必须替换为随机长串** |
| `DATABASE_URL` | SQLAlchemy 连接串，如 `mysql+pymysql://user:pass@host:3306/lifeagent` |
| `REDIS_URL` | Redis 连接串（向量库 / checkpointer / 通知缓存） |
| `DASHSCOPE_API_KEY` | 阿里云百炼 Key（LLM + Embedding） |
| `TAVILY_API_KEY` | Tavily Key，留空则联网搜索返回"未配置"提示 |
| `LANGSMITH_*` | LangSmith 链路追踪（可选） |
| `BACKEND_CORS_ORIGINS` | CORS 白名单，逗号分隔 |

## 定时任务（APScheduler）

| 任务 | 时间 | 内容 |
|---|---|---|
| `morning_job` | 08:00 | 早安提醒（待办概览 + 累计支出） |
| `noon_job` | 12:00 | 午间问候 |
| `evening_job` | 18:00 | 傍晚复盘（今日花费） |
| `sleep_job` | 23:00 | 晚安小结（日记 + 支出 + 未完成待办） |
| `check_due_todos` | 每 5 分钟 | 到点待办提醒 |
| `check_habits` | 每小时 | 习惯打卡提醒（按 remind_time 匹配） |
| `check_anniversaries` | 09:00 | 纪念日倒计时（3/2/1 天与当天） |
| `check_savings` | 09:05 | 存钱进度周报（每周一） |

> 注意：job 均为同步函数，AsyncIOScheduler 自动丢线程池执行，避免同步 DB 调用阻塞事件循环。

## 演示话术

- `帮我规划从曲靖出发2天1晚自驾，预算700`
- `参考我上次的避坑经验，安排一个周末大理轻旅行，预算1000`
- `打卡跑步` / `我习惯打卡情况怎么样`
- `记住6月1号是妈的生日`
- `喝了3杯水`
- `存钱目标：年底攒2万去日本，已存5000`
- `查一下明天曲靖到大理的火车票`
- `我笔记里关于露营的注意事项`

## API 一览

- `POST /auth/register | /auth/login | /auth/refresh` — 注册 / 登录 / 刷新 token
- `POST /chat` — SSE 流式对话
- `GET|POST /life/*` — 记账、待办、习惯、存钱、纪念日、日记、喝水
- `GET|POST|DELETE /notes/*` — 笔记上传、列表、语义搜索、删除
- `POST /summary/today` — 今日晨间摘要（LLM）
- `POST /sync/life` — 前端生活数据同步到记忆向量库
- `GET|POST|DELETE /conversations` — 对话历史
- `GET|DELETE /memory/*` — 经验记忆
- `POST /profile/impression` — AI 印象
- `GET|POST|DELETE /notify/*` — 通知

## 已知限制

- 数据库无 Alembic 迁移，新表靠 `create_all` + 启动期 ALTER 补列，生产环境建议引入迁移工具
- LLM 调用失败时部分接口直接返回空，尚未做优雅降级兜底
- Tavily 只能搜网页摘要，车票/酒店实时价格需接入垂直 API
- Redis checkpointer 的旧 thread 无自动清理，长期运行会缓慢增长
- 无单元测试 / 集成测试

## 决策记录

- 采用同步 SQLAlchemy + PyMySQL，减少容器运行时复杂度；异步场景（LLM 流式、SSE）用 asyncio
- 使用 Redis Stack + langchain-redis，向量维度固定 1536
- LLM 走 DashScope OpenAI 兼容模式（`langchain-openai`），不用已废弃的 `ChatTongyi`
- reviewer 质检与工具执行分离，杜绝"打回重试导致重复写库"
- 前端 SSE 用 fetch ReadableStream，兼容 POST 请求体
- 记忆沉淀仅限"工具调用驱动"的回答，模型凭空编造的内容不写长期记忆
