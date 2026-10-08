"""Agent 可调用的工具集（Tool Calling）。

设计说明：
- 工具函数用 @tool 定义，uid 通过 InjectedToolArg 注入（不暴露给模型，
  模型不需要、也不应该自己填用户 id）。
- 这些工具函数会真正执行写库；但 worker 节点里模型的 tool_calls 只是
  "决策"，存在 state 里，等 reviewer 质检通过后，才由 chat.py 调用
  执行——这样如果 reviewer 打回重试，不会重复写库。
"""
from typing import Annotated
from datetime import datetime, date, timedelta

from zoneinfo import ZoneInfo
_BJ = ZoneInfo("Asia/Shanghai")
from langchain_core.tools import tool, InjectedToolArg
from tavily import TavilyClient

from ..config import settings
from ..db.session import SessionLocal
from ..db.models import Expense, Todo, Diary, Habit, HabitLog, Anniversary, SavingsGoal, WaterLog
from ..vector_store.factory import get_notes_store, get_memory_store


@tool
def record_expense(
    amount: float,
    category: str,
    note: str = "",
    kind: str = "expense",
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """记录一笔支出或收入。当用户提到花了、收到、记一笔、报销、买东西花了多少钱时调用。
    amount 为金额数字；kind 为 expense（支出）或 income（收入）；
    category 为分类（餐饮/交通/购物/住宿/娱乐/工资/兼职/红包/理财/其他）；note 为备注。
    """
    db = SessionLocal()
    try:
        e = Expense(user_id=uid, amount=float(amount), kind=kind,
                    category=category or "其他", note=note or "")
        db.add(e)
        db.commit()
        label = "收入" if kind == "income" else "支出"
        return f"已记录{label}：{category} ¥{amount}（{note or '无备注'}）"
    finally:
        db.close()


@tool
def create_todo(
    text: str,
    due_at: str = "",
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """创建一条待办提醒。当用户说提醒我、记得做、待办、别忘了做某事时调用。
    text 为待办内容；due_at 为提醒时间，必须是 ISO 格式（如 2026-10-02T15:00），
    请结合当前时间把"明天下午3点""周五前"这类相对时间换算成 ISO；用户没提时间就留空。"""
    due_dt = None
    if due_at:
        try:
            due_dt = datetime.fromisoformat(due_at)
        except Exception:
            due_dt = None
    db = SessionLocal()
    try:
        db.add(Todo(user_id=uid, text=text, due_at=due_dt))
        db.commit()
        time_str = f"，时间 {due_dt.strftime('%Y-%m-%d %H:%M')}" if due_dt else ""
        return f"已创建待办：{text}{time_str}"
    finally:
        db.close()


@tool
def write_diary(
    content: str,
    mood: str = "🙂",
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """写一篇日记。当用户说写日记、记日记、今天日记时调用。mood 为心情表情，content 为日记正文。"""
    db = SessionLocal()
    try:
        db.add(Diary(user_id=uid, mood=mood, content=content))
        db.commit()
        return f"已写日记：{mood} {content[:20]}"
    finally:
        db.close()


@tool
def web_search(query: str, uid: Annotated[int, InjectedToolArg] = None) -> str:
    """联网搜索实时信息。当用户问到需要最新、实时信息的内容时调用，比如：
    车票/车次/机票、酒店价格、天气、新闻、景点门票、开放时间、近期活动、
    最新政策或价格等。返回搜索结果摘要和来源链接。
    """
    if not settings.tavily_api_key:
        return "联网搜索未配置（缺少 TAVILY_API_KEY），无法获取实时信息。"
    try:
        client = TavilyClient(api_key=settings.tavily_api_key)
        resp = client.search(
            query=query,
            search_depth="basic",
            max_results=3,
            include_answer=True,
        )
    except Exception as exc:
        # 搜索失败也要把原因返回给用户，而不是让上层静默吞掉
        return f"联网搜索失败：{exc}（请检查 TAVILY_API_KEY 与网络后重试）"
    lines = []
    if resp.get("answer"):
        lines.append(resp["answer"])
    for r in resp.get("results", []):
        content = (r.get("content") or "").strip()
        # 网页摘要常被 Tavily 抓成几百上千字全文，截断到 120 字，避免回答超长
        if len(content) > 120:
            content = content[:120] + "…"
        lines.append(f"- {r.get('title', '')}：{content}（来源：{r.get('url', '')}）")
    return "\n".join(lines) if lines else "未搜索到相关结果。"


# ===== 习惯打卡 =====
def _habit_streak(db, habit_id: int, uid: int) -> int:
    """连续打卡天数：今天已打卡则从今天往回数，今天未打卡则从昨天往回数。"""
    logs = db.query(HabitLog.check_date).filter(
        HabitLog.habit_id == habit_id, HabitLog.user_id == uid).all()
    dates = {d[0] for d in logs}
    streak = 0
    d = datetime.now(_BJ).date()
    if d not in dates:
        d = d - timedelta(days=1)
    while d in dates:
        streak += 1
        d = d - timedelta(days=1)
    return streak


@tool
def check_habit(
    habit_name: str,
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """习惯打卡。当用户说打卡、今天打卡XX、完成XX习惯、打卡XX时调用。
    habit_name 为习惯名称（如"跑步""阅读"）；若该习惯不存在会自动创建并打卡。"""
    db = SessionLocal()
    try:
        h = db.query(Habit).filter(Habit.user_id == uid, Habit.name == habit_name).first()
        created = False
        if not h:
            h = Habit(user_id=uid, name=habit_name, icon="✨", remind_time="09:00")
            db.add(h); db.commit(); db.refresh(h)
            created = True
        today = datetime.now(_BJ).date()
        if h.last_check != today:
            h.last_check = today
            h.checked_count += 1
            exists = db.query(HabitLog).filter(
                HabitLog.habit_id == h.id, HabitLog.check_date == today).first()
            if not exists:
                db.add(HabitLog(habit_id=h.id, user_id=uid, check_date=today))
            db.commit()
        suffix = "（自动创建了该习惯）" if created else ""
        return f"已为「{habit_name}」打卡{suffix}"
    finally:
        db.close()


@tool
def query_habits(
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """查询习惯打卡情况。当用户问习惯进度、打卡情况、连续几天、今天有哪些习惯要打卡时调用。"""
    db = SessionLocal()
    try:
        rows = db.query(Habit).filter(Habit.user_id == uid).all()
        if not rows:
            return "还没有习惯，可以直接说「帮我打卡跑步」来创建并打卡。"
        today = datetime.now(_BJ).date()
        lines = []
        for r in rows:
            streak = _habit_streak(db, r.id, uid)
            status = "今日已打卡" if r.last_check == today else "今日未打卡"
            lines.append(f"{r.icon} {r.name}：{status}，连续{streak}天，累计{r.checked_count}次")
        return "\n".join(lines)
    finally:
        db.close()


# ===== 纪念日 =====
@tool
def add_anniversary(
    name: str,
    event_date: str,
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """新增纪念日。当用户说记住XX日子、XX的生日是X月X日、纪念日时调用。
    event_date 为 MM-DD 格式（如 06-01），默认每年都会过；同名同日已存在时不会重复添加。"""
    db = SessionLocal()
    try:
        month, day = event_date.split("-")
        ev = date(datetime.now(_BJ).date().year, int(month), int(day))
    except Exception:
        return "日期格式不对，请用 MM-DD 格式（如 06-01）再说一次。"
    try:
        exists = db.query(Anniversary).filter(
            Anniversary.user_id == uid,
            Anniversary.name == name,
            Anniversary.event_date == ev,
        ).first()
        if exists:
            return f"「{name}」（每年 {event_date}）之前已经记住了，不用重复添加。"
        db.add(Anniversary(user_id=uid, name=name, event_date=ev, year=0))
        db.commit()
        return f"已记住纪念日：{name}（每年 {event_date}）"
    finally:
        db.close()


@tool
def query_anniversary(
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """查询纪念日与倒计时。仅当用户明确提到"纪念日、生日、还有几天到XX、最近有什么纪念日"
    这类个人纪念日时才调用；查询火车票/车次、机票、酒店、天气、新闻等实时公共信息
    请调用 web_search，绝不要用本工具。"""
    db = SessionLocal()
    try:
        rows = db.query(Anniversary).filter(Anniversary.user_id == uid).all()
        if not rows:
            return "还没有纪念日，可以直接说「记住6月1号是妈的生日」来添加。"
        today = datetime.now(_BJ).date()
        lines = []
        for r in rows:
            target = date(today.year, r.event_date.month, r.event_date.day)
            if target < today:
                target = date(today.year + 1, r.event_date.month, r.event_date.day)
            days = (target - today).days
            tip = "就是今天！" if days == 0 else f"还有{days}天"
            lines.append(f"{r.name}（{r.event_date.strftime('%m-%d')}）：{tip}")
        return "\n".join(lines)
    finally:
        db.close()


# ===== 喝水 =====
@tool
def record_water(
    cups: int,
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """记录今日喝水杯数。当用户说喝水、喝了X杯水、记录喝水、今天喝了几杯时调用。
    cups 为今天已喝的总杯数（覆盖式记录）。"""
    db = SessionLocal()
    try:
        today = datetime.now(_BJ).date()
        row = db.query(WaterLog).filter(
            WaterLog.user_id == uid, WaterLog.log_date == today).first()
        if row:
            row.cups = max(0, int(cups))
        else:
            db.add(WaterLog(user_id=uid, log_date=today, cups=max(0, int(cups))))
        db.commit()
        return f"已记录今日喝水 {cups} 杯"
    finally:
        db.close()


@tool
def query_water(
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """查询喝水记录。当用户问今天喝了几杯水、喝水情况、近几天喝了多少时调用。
    返回今日杯数及近 7 天记录。"""
    db = SessionLocal()
    try:
        rows = db.query(WaterLog).filter(WaterLog.user_id == uid).all()
        if not rows:
            return "还没有喝水记录，喝一杯后可以说「帮我记录喝水」或到喝水页面点一下。"
        today = datetime.now(_BJ).date()
        today_cups = next((r.cups for r in rows if r.log_date == today), 0)
        recent = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            cups = next((r.cups for r in rows if r.log_date == d), 0)
            recent.append(f"{d.month}月{d.day}日 {cups}杯")
        return f"今日喝水 {today_cups} 杯。近 7 天：{'、'.join(recent)}"
    finally:
        db.close()


# ===== 存钱 =====
@tool
def query_savings(
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """查询存钱目标与进度。当用户问存钱进度、还差多少钱、每天要存多少、存钱目标时调用。"""
    db = SessionLocal()
    try:
        rows = db.query(SavingsGoal).filter(SavingsGoal.user_id == uid).all()
        if not rows:
            return "还没有存钱目标，可以在存钱目标页面创建，或告诉我想存什么、存多少、什么时候到期。"
        lines = []
        for r in rows:
            left = max(0, r.target_amount - r.saved_amount)
            days = (r.deadline - datetime.now(_BJ).date()).days
            daily = left / days if days > 0 else left
            lines.append(
                f"「{r.purpose}」已存¥{r.saved_amount:.0f}/¥{r.target_amount:.0f}，"
                f"还差¥{left:.0f}，每天需存约¥{daily:.0f}（还剩{days}天）")
        return "\n".join(lines)
    finally:
        db.close()


@tool
def update_savings(
    purpose: str,
    amount: float,
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """往存钱目标里存入一笔钱。当用户说存了X元、往XX目标存钱时调用。
    purpose 为存钱目标名称，amount 为本次存入金额。"""
    db = SessionLocal()
    try:
        g = db.query(SavingsGoal).filter(
            SavingsGoal.user_id == uid, SavingsGoal.purpose == purpose).first()
        if not g:
            return f"没找到名为「{purpose}」的存钱目标，可先告诉我想存什么、目标金额和到期时间。"
        g.saved_amount += float(amount)
        db.commit()
        return f"已存入¥{amount}，「{purpose}」当前已存¥{g.saved_amount:.0f}/¥{g.target_amount:.0f}"
    finally:
        db.close()


# ===== 笔记 / 记忆检索 =====
@tool
def query_notes(
    query: str,
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """在个人笔记中检索相关内容。当用户问"我笔记里""我之前记过关于XX"时调用，返回匹配片段。"""
    try:
        docs = get_notes_store(uid).similarity_search(query, k=5)
        if not docs:
            return "没在笔记里找到相关内容。"
        return "\n".join(f"- {d.page_content}" for d in docs)
    except Exception:
        return "检索笔记失败，稍后再试。"


@tool
def query_memory(
    query: str,
    uid: Annotated[int, InjectedToolArg] = None,
) -> str:
    """在历史经验记忆中检索。当用户问"我之前说过""我的经验里关于XX"时调用，返回相关记忆片段。"""
    try:
        docs = get_memory_store(uid).similarity_search(query, k=5)
        if not docs:
            return "没在历史记忆中找到相关内容。"
        return "\n".join(f"- {d.page_content}" for d in docs)
    except Exception:
        return "检索记忆失败，稍后再试。"


# 暴露给模型的工具列表（uid 会在 bind_tools 时被自动排除，因为它是 InjectedToolArg）
TOOLS = [record_expense, create_todo, write_diary, web_search,
         check_habit, query_habits, add_anniversary, query_anniversary,
         record_water, query_water, query_savings, update_savings,
         query_notes, query_memory]
TOOL_MAP = {t.name: t for t in TOOLS}
