from datetime import datetime, date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import redis
from sqlalchemy.orm import Session
from .db.session import SessionLocal
from .db.models import User, Expense, Todo, Habit, SavingsGoal, Anniversary, Notification, Diary
from .llm import llm
from .config import settings
from langchain_core.messages import HumanMessage, SystemMessage

scheduler = AsyncIOScheduler()
_r = redis.from_url(settings.redis_url, decode_responses=True)


def _push(db, user_id, title, body):
    db.add(Notification(user_id=user_id, title=title, body=body))
    _r.delete(f"notify:{user_id}")


def _llm(prompt, system="你是贴心的生活管家，回答简洁温暖，不超过100字。"):
    try:
        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=prompt)])
        return resp.content
    except Exception:
        return ""


# 注意：这些 job 都是同步函数。AsyncIOScheduler 会自动把它们丢到线程池里跑，
# 避免同步的 db.query / llm.invoke 阻塞事件循环。
def morning_job():
    db: Session = SessionLocal()
    try:
        for u in db.query(User).all():
            todos = db.query(Todo).filter(Todo.user_id == u.id, Todo.done == 0).all()
            exps = db.query(Expense).filter(Expense.user_id == u.id, Expense.kind != "income").all()
            spent = sum(e.amount for e in exps)
            tips = f"今天有 {len(todos)} 件待办；累计支出 ¥{spent:.2f}"
            body = _llm(f"用户数据：{tips}。写一句温暖的早安提醒，包含今日待办概览和鼓励。")
            _push(db, u.id, "早安提醒", body or f"早安！你有 {len(todos)} 件待办，新的一天加油。")
        db.commit()
    finally:
        db.close()


def noon_job():
    db: Session = SessionLocal()
    try:
        for u in db.query(User).all():
            body = _llm("现在是中午12点，写一句午间问候，提醒用户记得吃午饭、下午注意休息。")
            _push(db, u.id, "午间问候", body or "中午啦，记得吃顿好的，下午继续加油！")
        db.commit()
    finally:
        db.close()


def evening_job():
    db: Session = SessionLocal()
    try:
        for u in db.query(User).all():
            today = date.today()
            spent_today = sum(e.amount for e in db.query(Expense).filter(
                Expense.user_id == u.id, Expense.kind != "income",
                Expense.created_at >= datetime.combine(today, datetime.min.time())).all())
            body = _llm(f"用户今天已花 ¥{spent_today:.2f}。写一句傍晚问候，提醒复盘今日花费和明天计划。")
            _push(db, u.id, "傍晚提醒", body or f"晚上好，今天花了 ¥{spent_today:.2f}，复盘一下吧～")
        db.commit()
    finally:
        db.close()


def sleep_job():
    db: Session = SessionLocal()
    try:
        today = date.today()
        for u in db.query(User).all():
            # 今天的日记
            diaries = db.query(Diary).filter(
                Diary.user_id == u.id,
                Diary.created_at >= datetime.combine(today, datetime.min.time())).all()
            diary_text = diaries[-1].content if diaries else "（今天没写日记）"
            # 今天的支出
            spent = sum(e.amount for e in db.query(Expense).filter(
                Expense.user_id == u.id, Expense.kind != "income",
                Expense.created_at >= datetime.combine(today, datetime.min.time())).all())
            undone = db.query(Todo).filter(Todo.user_id == u.id, Todo.done == 0).count()
            body = _llm(
                f"现在是晚上11点。用户今天日记：{diary_text[:200]}；今天支出 ¥{spent:.2f}；未完成待办 {undone} 条。"
                "写一段晚安小结，回顾今天并提醒早睡，不超过120字。",
                system="你是暖心生活管家。"
            )
            _push(db, u.id, "晚安小结", body or "夜深了，放下手机早点睡吧，晚安～")
        db.commit()
    finally:
        db.close()


def check_due_todos():
    """每5分钟检查：到点的待办提醒"""
    db: Session = SessionLocal()
    try:
        now = datetime.now()
        due = db.query(Todo).filter(
            Todo.done == 0, Todo.reminded == 0,
            Todo.due_at != None, Todo.due_at <= now
        ).all()
        for t in due:
            body = _llm(f"用户有一个待办到点了：{t.text}。写一句简短提醒。",
                         system="你是提醒小助手，回复不超过40字。")
            _push(db, t.user_id, "待办提醒", body or f"到点啦：{t.text}")
            t.reminded = 1
        db.commit()
    finally:
        db.close()


def check_habits():
    """每小时检查习惯打卡提醒"""
    db: Session = SessionLocal()
    try:
        now = datetime.now()
        hhmm = now.strftime("%H:%M")
        today = now.date()
        habits = db.query(Habit).filter(Habit.remind_time == hhmm).all()
        for h in habits:
            if h.last_check == today:
                continue
            body = _llm(f"该打卡习惯「{h.name}」了。写一句简短提醒。",
                         system="你是打卡提醒小助手，回复不超过30字。")
            _push(db, h.user_id, "习惯打卡", body or f"该做「{h.name}」啦，完成了吗？")
        db.commit()
    finally:
        db.close()


def check_anniversaries():
    """每天早上检查纪念日倒计时"""
    db: Session = SessionLocal()
    try:
        today = date.today()
        for a in db.query(Anniversary).all():
            yr = today.year
            this_year = date(yr, a.event_date.month, a.event_date.day)
            target = date(yr + 1, a.event_date.month, a.event_date.day) if this_year < today else this_year
            # 一次性纪念日
            if a.year and a.year != yr:
                continue
            days = (target - today).days
            if days == 3 and not a.reminded_3:
                _push(db, a.user_id, "纪念日提醒", f"还有 3 天就是 {a.name}，提前准备一下吧～")
                a.reminded_3 = 1
            elif days == 2 and not a.reminded_2:
                _push(db, a.user_id, "纪念日提醒", f"还有 2 天 {a.name}，别忘了安排！")
                a.reminded_2 = 1
            elif days == 1 and not a.reminded_1:
                _push(db, a.user_id, "纪念日提醒", f"明天就是 {a.name}，准备好了吗？")
                a.reminded_1 = 1
            elif days == 0 and not a.reminded_day:
                body = _llm(f"今天是 {a.name}，写一句温暖的祝福。",
                             system="你是祝福小助手，不超过50字。")
                _push(db, a.user_id, "纪念日", body or f"今天是 {a.name}，祝你开心！")
                a.reminded_day = 1
        db.commit()
    finally:
        db.close()


def check_savings():
    """每天早上检查存钱进度"""
    db: Session = SessionLocal()
    try:
        today = date.today()
        for g in db.query(SavingsGoal).all():
            days_left = (g.deadline - today).days
            if days_left <= 0:
                continue
            pct = g.saved_amount / g.target_amount * 100 if g.target_amount else 0
            # 每周一提醒一次进度
            if today.weekday() == 0 and pct < 100:
                need = max(0, g.target_amount - g.saved_amount)
                daily = need / days_left if days_left > 0 else 0
                body = _llm(f"存钱目标「{g.purpose}」：已存 ¥{g.saved_amount:.0f}/¥{g.target_amount:.0f}（{pct:.0f}%），剩 {days_left} 天，每天需存 ¥{daily:.0f}。写一句鼓励。")
                _push(db, g.user_id, "存钱进度", body or f"「{g.purpose}」进度 {pct:.0f}%，继续加油！")
        db.commit()
    finally:
        db.close()


def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(morning_job, CronTrigger(hour=8, minute=0), id="morning", replace_existing=True)
        scheduler.add_job(noon_job, CronTrigger(hour=12, minute=0), id="noon", replace_existing=True)
        scheduler.add_job(evening_job, CronTrigger(hour=18, minute=0), id="evening", replace_existing=True)
        scheduler.add_job(sleep_job, CronTrigger(hour=23, minute=0), id="sleep", replace_existing=True)
        scheduler.add_job(check_due_todos, "interval", minutes=5, id="due_todos", replace_existing=True)
        scheduler.add_job(check_habits, "interval", minutes=60, id="habits", replace_existing=True)
        scheduler.add_job(check_anniversaries, CronTrigger(hour=9, minute=0), id="anniv", replace_existing=True)
        scheduler.add_job(check_savings, CronTrigger(hour=9, minute=5), id="savings", replace_existing=True)
        scheduler.start()


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
