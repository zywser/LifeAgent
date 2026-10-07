# Life Agent · 私人生活智能管家

一个用自然语言管理个人生活的 AI 管家：记账、待办、习惯打卡、日记、喝水、存钱、纪念日、笔记知识库、实时信息查询，全部通过与 AI 助手的对话完成。基于 FastAPI + LangGraph + Vue 3，本地开发与 Docker 部署均可。

## 功能总览

| 模块 | 说明 | 前端入口 |
|---|---|---|
| 智能对话 | 多智能体链路 + SSE 流式输出 + 节点执行时间线，可联网查询实时信息 | 对话 |
| 今日摘要 | 按北京时间动态生成问候（早安/中午好/下午好/晚上好/夜深了）+ 今日要点 | Home |
| 记账 | 支出/收入记录、分类、累计统计（可对话记账） | `/accounting` |
| 待办 | 带提醒时间的待办清单，到点自动推送通知 + 邮件 | `/todo` |
| 习惯打卡 | 每日打卡、连续天数、按时提醒 | `/habit` |
| 日记 | 心情记录、AI 情绪小结、一周情绪趋势 | `/diary` |
| 喝水 | 每日杯数记录，近 7 天回顾 | `/water` |
| 存钱 | 目标金额、进度、每日应存测算、周一进度提醒 | `/savings` |
| 纪念日 | 生日/纪念日倒计时，前 3 天起逐日提醒 | `/anniversary` |
| 笔记知识库 | 上传 MD/TXT/PDF/Word，自动切分向量化，语义检索 | `/notes` |
| 经验记忆 | Agent 沉淀的任务经验与日记摘要，可查看/删除 | `/memory` |
| Agent 链路 | 节点拓扑与执行日志可视化 | `/graph` |
| 历史对话 | 云端持久化对话记录 | `/history` |
| 个人中心 | AI 印象、头像上传（裁剪，≤5MB）、昵称持久化、更换邮箱（两步验证码）、修改密码 | `/profile` |
| 全局主题 | 4 套主题换色：白天 / 黑夜 / 活力橙 / 自然绿，输入框/卡片/弹窗全部跟随 | 顶栏圆点 |
| 邮件推送 | 通知开关，开启后站内提醒同步发邮件（验证码/待办/纪念日等） | Home / Profile |

## 技术架构

```mermaid
flowchart LR
  Web[Vue 3 + Element Plus] -->|/api SSE| API[FastAPI]
  API --> Auth[(MySQL 鉴权)]
  API --> G[LangGraph Supervisor]
  G --> P[Planner] --> R[Retriever]
  R --> N[(Redis 向量库)] & M[(Redis 记忆向量)]
  R --> E[Executor 循环<br/>模型决策工具调用]
  E --> S[Synthesizer] --> V[Reviewer 质检]
  V -->|不通过 ≤ 3 次| P
  V -->|通过| API
  API -->|真正执行工具| T[14 个 Tool]
  T --> DB[(MySQL 业务表)]
  T --> TV[Tavily 联网搜索]
  API -->|写回| M
  G --> CK[Redis Checkpointer]
  Sched[APScheduler 定时任务<br/>北京时间] --> Noti[通知 + 邮件]
```

**技术栈**：FastAPI + LangGraph + SQLAlchemy + MySQL 8 + Redis Stack（向量库/checkpointer/缓存）+ DashScope（qwen-plus + text-embedding-v1）+ Tavily（联网搜索）+ Vue 3 + Element Plus + Docker Compose。全部定时任务与时间判断统一 `Asia/Shanghai` 时区。

## 目录结构

```
Life Agent/
├── main.py                  # 本地开发入口（自动切到 backend 目录）
├── backend/
│   ├── .env.example         # 配置模板（复制为 .env 填写）
│   ├── requirements.txt
│   ├── Dockerfile           # python:3.13-slim + tzdata（时区数据）
│   └── app/
│       ├── main.py          # FastAPI 入口：lifespan 建表/补列/起调度器
│       ├── config.py        # pydantic-settings（先 load_dotenv 供 LangSmith 读取）
│       ├── llm.py           # ChatOpenAI + OpenAIEmbeddings（DashScope 兼容模式）
│       ├── deps.py          # get_current_user（JWT Bearer）
│       ├── auth/            # 注册（邮箱验证码）/登录/刷新 token（bcrypt + JWT + refresh 轮换）
│       │   ├── router.py    # 登录/注册/刷新/验证码/忘记密码/重置
│       │   └── service.py   # bcrypt 哈希 + JWT 签发/校验
│       ├── security.py      # AES-256-CBC 重置密码链接令牌
│       ├── mailer.py        # 邮件发送 + HTML 模板（验证码/通知/重置链接）
│       ├── db/              # SQLAlchemy 引擎/会话/表模型
│       ├── graph/           # LangGraph 多智能体核心
│       │   ├── state.py     # AgentState（节点间共享）
│       │   ├── build.py     # StateGraph 拓扑与编译
│       │   ├── nodes.py     # 节点实现（当前时间=北京时间）
│       │   ├── router.py    # 条件路由
│       │   └── tools.py     # 14 个 Tool Calling 工具
│       ├── routes/          # chat/notes/life/summary/sync/conversations/memory/impression/notify
│       ├── vector_store/    # Redis 向量库/checkpointer/删向量
│       ├── ingest/          # 笔记读取（md/txt/pdf/docx）与切分
│       └── scheduler.py     # APScheduler 8 个定时任务（北京时间）
├── web/                     # Vue 3 前端（16 个页面）
│   ├── src/views/           # 页面组件
│   ├── src/api/             # axios 封装 + token 刷新队列 + SSE 客户端
│   ├── src/stores/          # Pinia（auth）
│   ├── Dockerfile           # node 构建 + nginx 托管（含 /api 反代）
│   └── nginx.conf           # 静态托管 + /api 代理 + 上传大小限制
└── deploy/docker-compose.yml  # redis + backend + web 编排（接入 oa_oa 网络）
```

## 多智能体核心设计

### 执行链路

```
START → supervisor → planner → retriever
                                       ↓
                          executor ←——┘  循环执行每个子任务
                                 ↓ 全部完成
                          synthesizer → reviewer
                                         ↓
                                通过→END / 不通过→planner（≤3 次）
```

| 节点 | 作用 |
|---|---|
| `supervisor` | 入口，初始化状态 |
| `planner` | LLM 把需求拆成 ≤3 个子任务（输出异常时回退固定方案） |
| `retriever` | 从向量库召回个人笔记与历史经验（不调 LLM） |
| `executor` | 循环节点，`llm.bind_tools(TOOLS)` 流式执行每个子任务 |
| `synthesizer` | 汇总子任务结果成一段自然回答（≤2 段时跳过 LLM） |
| `reviewer` | LLM 打分（≥7 通过），不通过打回 planner，最多重试 3 次 |

### 关键设计：决策与执行分离

- executor 里模型只**决定**调用哪些工具、参数是什么，存进 `state.tool_calls`，**不真正写库**；
- reviewer 质检**通过后**，由 `chat.py` 才真正执行工具（`TOOL_MAP[name].ainvoke(args)`）；
- 这样 reviewer 打回重试时不会重复写库；
- 模型漏调用工具时，`chat.py` 按消息里的明确业务意图（打卡/喝水/纪念日/存钱等强信号）做关键词兜底补调，保证动作真实落库、查询有据可答。

### 工具集（14 个）

`record_expense`（记账）、`create_todo`（建待办，支持相对时间换算 ISO）、`write_diary`（写日记）、`web_search`（Tavily 联网搜索：车票/酒店/天气/新闻等实时信息）、`check_habit`/`query_habits`（习惯打卡/查询）、`add_anniversary`/`query_anniversary`（纪念日/倒计时）、`record_water`/`query_water`（喝水/近 7 天）、`query_savings`/`update_savings`（存钱）、`query_notes`/`query_memory`（笔记/记忆检索）。

`uid` 通过 `InjectedToolArg` 注入，对模型隐藏；所有向量索引、checkpoint thread 均带 `user:{uid}` 前缀实现用户隔离。

### 对话流（SSE）

`POST /chat` 返回 `text/event-stream`，事件序列：`node_start` / `node_end`（链路节点点亮）、`token`（流式 token）、`final`（最终回答，工具结果优先）、`error`。每轮请求使用唯一 `thread_id`，避免上一轮的中间状态串入新问题。

## 快速开始

### 方式一：Docker Compose

```bash
# 1. 准备配置
cp backend/.env.example backend/.env
#    编辑 backend/.env，至少填写：
#    SECRET_KEY（随机长字符串）、DATABASE_URL、REDIS_URL、
#    DASHSCOPE_API_KEY（阿里云百炼）、TAVILY_API_KEY（可选，联网搜索）、
#    SMTP_USER/SMTP_PASSWORD（QQ 邮箱授权码，验证码/通知邮件）、FRONTEND_BASE（重置链接域名）

# 2. 启动（redis + backend + web）
docker compose -f deploy/docker-compose.yml up -d --build

# 3. 访问
open http://localhost
```

部署注意：
- 前端路由基路径为 `/life/`（与 OA 系统同域共 Nginx，由 OA 的 nginx 反代 `/life/` 到本服务），独立部署时请把 `web/vite.config.js` 的 `base` 与 OA 侧代理路径保持一致；
- 后端镜像已安装 `tzdata` 并设置 `TZ=Asia/Shanghai`，定时任务与时间判断均为北京时间；
- `.env` 中 `DATABASE_URL` / `REDIS_URL` 使用服务名（`mysql` / `redis`），若复用 OA 的 MySQL/Redis 改为对应网络服务名。

### 方式二：本地开发

```bash
# 后端
cd backend
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd web
npm ci
npm run dev                                       # http://localhost:5173（/api 已代理到 8000）
```

MySQL 与 Redis 需自行启动，并保证 `backend/.env` 中的连接串可达。

## 配置项（backend/.env）

| 变量 | 说明 |
|---|---|
| `SECRET_KEY` | JWT 签名密钥 + AES 令牌派生，**必须替换为随机长串** |
| `DATABASE_URL` | SQLAlchemy 连接串，如 `mysql+pymysql://user:pass@host:3306/lifeagent` |
| `REDIS_URL` | Redis 连接串（向量库/checkpointer/通知缓存） |
| `DASHSCOPE_API_KEY` | 阿里云百炼 Key（LLM + Embedding） |
| `TAVILY_API_KEY` | Tavily Key，留空则联网搜索返回"未配置"提示 |
| `BACKEND_CORS_ORIGINS` | CORS 白名单，逗号分隔 |
| `SMTP_HOST/PORT/USER/PASSWORD/FROM` | QQ 邮箱 SMTP（465 端口 + 授权码），验证码/通知/重置链接邮件 |
| `FRONTEND_BASE` | 邮件中重置密码链接的前端地址，生产必须为公网域名 |
| `VERIFY_CODE_TTL` | 邮箱验证码有效期（秒），默认 600 |
| `VERIFY_CODE_COOLDOWN` | 验证码重发冷却（秒），默认 60 |
| `LANGSMITH_*` | LangSmith 链路追踪（可选） |

## 账号安全

- **注册**：邮箱 + 验证码激活（验证码存 Redis，10 分钟有效、60 秒冷却），默认用户名 `L + 6 位随机数字`；
- **登录**：JWT access（2h）+ refresh（7 天，存库可吊销，轮换）；
- **更换邮箱**：老邮箱验证码 → 新邮箱验证码两步校验；
- **修改密码**：当前密码 + 新密码 + 确认；
- **忘记密码**：邮箱发送含 AES-256-CBC 加密链接（1 小时有效）跳转重置页。

## 定时任务（APScheduler，北京时间）

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

> job 均为同步函数，AsyncIOScheduler 自动丢线程池执行，避免同步 DB 调用阻塞事件循环。时区统一 `Asia/Shanghai`（`AsyncIOScheduler(timezone=TZ)` + `datetime.now(TZ)`），部署到 UTC 容器也不会错点。

## 示例对话

- `帮我规划从曲靖出发的3天自驾，预算700`
- `参考我上次的避坑经验，安排一个周末大理轻旅行，预算1000`
- `打卡跑步` / `我习惯打卡情况怎么样`
- `记住6月5号是妈的生日`
- `喝了3杯水`
- `存钱目标：年底攒2万去日本，已存5000`
- `查一下明天曲靖到大理的火车票`
- `我笔记里关于露营的注意事项`

## API 一览

- `POST /auth/register | /auth/login | /auth/refresh` — 注册（验证码）/登录/刷新 token
- `POST /auth/send_code | /auth/forgot_password | /auth/reset_password` — 验证码/找回/重置
- `GET /profile/me` / `PUT /profile/me` / `POST /profile/avatar` — 资料/昵称持久化/头像上传
- `POST /chat` — SSE 流式对话
- `GET|POST /life/*` — 记账、待办、习惯、存钱、纪念日、日记、喝水
- `GET|POST|DELETE /notes/*` — 笔记上传（≤10MB）、列表、语义搜索、删除
- `POST /summary/today` — 今日动态问候摘要（LLM）
- `POST /sync/life` — 前端生活数据同步到记忆向量库
- `GET|POST|DELETE /conversations` — 对话历史
- `GET|DELETE /memory/*` — 经验记忆
- `POST /profile/impression` — AI 印象
- `GET|POST|DELETE /notify/*` — 通知（含邮件开关）

## 安全与限流

- 密码 bcrypt 哈希；JWT HS256 + 过期时间 + refresh 轮换存库；
- 上传白名单 + 大小限制：头像 ≤5MB（jpg/png/webp/gif），笔记 ≤10MB（md/txt/pdf/docx）；
- Nginx `client_max_body_size 20m`；验证码 60 秒冷却 + 10 分钟有效；
- CORS 白名单来自 `.env`，`SECRET_KEY` 无默认值（缺失直接启动失败）；
- `.env` 已被 `.gitignore` 排除，仓库仅含 `.env.example`。

## 已知限制

- 数据库无 Alembic 迁移，新表靠 `create_all` + 启动时 `ALTER` 补列，生产环境建议引入迁移工具；
- LLM 调用失败时部分接口直接返回空，尚未做优雅降级兜底；
- Tavily 只能搜网页摘要，车票/酒店实时价格需接入垂直 API；
- Redis checkpointer 的旧 thread 无自动清理，长期运行会缓慢增长；
- 无单元测试 / 集成测试。
