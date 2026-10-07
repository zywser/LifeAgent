from datetime import datetime, date

from zoneinfo import ZoneInfo
_BJ = ZoneInfo("Asia/Shanghai")
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..deps import get_current_user
from ..db.models import User, Expense, Todo, Habit, HabitLog, SavingsGoal, Anniversary, Diary, MemoryItem, WaterLog
from ..llm import llm
from ..vector_store.factory import get_memory_store
from langchain_core.messages import HumanMessage, SystemMessage
from ..db.session import get_db, SessionLocal

router = APIRouter(prefix="/life", tags=["life"])


# ===== Expense =====
class ExpenseIn(BaseModel):
    amount: float
    kind: str = "expense"
    category: str = "其他"
    note: str = ""

@router.post("/expenses")
def add_expense(body: ExpenseIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = Expense(user_id=user.id, amount=body.amount, kind=body.kind, category=body.category, note=body.note)
    db.add(e); db.commit(); db.refresh(e)
    return {"id": e.id, "amount": e.amount, "kind": e.kind, "category": e.category, "note": e.note}

@router.get("/expenses")
def list_expenses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Expense).filter(Expense.user_id == user.id).order_by(Expense.id.desc()).all()
    return [{"id": r.id, "amount": r.amount, "kind": r.kind, "category": r.category, "note": r.note,
             "time": r.created_at.isoformat() if r.created_at else ""} for r in rows]

@router.delete("/expenses/{eid}")
def del_expense(eid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.query(Expense).filter(Expense.id == eid, Expense.user_id == user.id).first()
    if not r: raise HTTPException(404)
    db.delete(r); db.commit(); return {"ok": True}


# ===== Todo =====
class TodoIn(BaseModel):
    text: str
    due_at: str | None = None  # ISO "2026-09-30T14:00"

@router.post("/todos")
def add_todo(body: TodoIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    due = None
    if body.due_at:
        try:
            due = datetime.fromisoformat(body.due_at)
        except Exception:
            due = None
    t = Todo(user_id=user.id, text=body.text, due_at=due)
    db.add(t); db.commit(); db.refresh(t)
    return {"id": t.id, "text": t.text, "done": 0, "due_at": body.due_at}

@router.get("/todos")
def list_todos(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Todo).filter(Todo.user_id == user.id).order_by(Todo.id.desc()).all()
    return [{"id": r.id, "text": r.text, "done": r.done,
             "due_at": r.due_at.isoformat() if r.due_at else None,
             "time": r.created_at.isoformat() if r.created_at else ""} for r in rows]

@router.put("/todos/{tid}")
def toggle_todo(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(Todo).filter(Todo.id == tid, Todo.user_id == user.id).first()
    if not t: raise HTTPException(404)
    t.done = 1 if t.done == 0 else 0
    db.commit(); return {"ok": True, "done": t.done}

@router.delete("/todos/{tid}")
def del_todo(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(Todo).filter(Todo.id == tid, Todo.user_id == user.id).first()
    if not t: raise HTTPException(404)
    db.delete(t); db.commit(); return {"ok": True}


# ===== Habit =====
class HabitIn(BaseModel):
    name: str
    icon: str = "✨"
    remind_time: str = "09:00"

@router.post("/habits")
def add_habit(body: HabitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    h = Habit(user_id=user.id, name=body.name, icon=body.icon, remind_time=body.remind_time)
    db.add(h); db.commit(); db.refresh(h)
    return {"id": h.id, "name": h.name, "icon": h.icon, "remind_time": h.remind_time, "checked_count": 0}

@router.get("/habits")
def list_habits(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Habit).filter(Habit.user_id == user.id).all()
    today = datetime.now(_BJ).date()
    return [{"id": r.id, "name": r.name, "icon": r.icon or "✨", "remind_time": r.remind_time,
             "checked_count": r.checked_count,
             "checked_today": r.last_check == today,
             "streak": _habit_streak(db, r.id, user.id)} for r in rows]

def _habit_streak(db: Session, habit_id: int, uid: int) -> int:
    """连续打卡天数：今天已打卡则从今天往回数，今天未打卡则从昨天往回数。"""
    from datetime import timedelta
    logs = (
        db.query(HabitLog.check_date)
        .filter(HabitLog.habit_id == habit_id, HabitLog.user_id == uid)
        .all()
    )
    dates = {d[0] for d in logs}
    streak = 0
    d = datetime.now(_BJ).date()
    if d not in dates:
        d = d - timedelta(days=1)
    while d in dates:
        streak += 1
        d = d - timedelta(days=1)
    return streak

@router.post("/habits/{hid}/check")
def check_habit(hid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    h = db.query(Habit).filter(Habit.id == hid, Habit.user_id == user.id).first()
    if not h: raise HTTPException(404)
    today = datetime.now(_BJ).date()
    if h.last_check != today:
        h.last_check = today
        h.checked_count += 1
        # 写打卡流水（同一天已存在则跳过，保证 unique 约束）
        exists = db.query(HabitLog).filter(HabitLog.habit_id == hid, HabitLog.check_date == today).first()
        if not exists:
            db.add(HabitLog(habit_id=hid, user_id=user.id, check_date=today))
        db.commit()
    return {"ok": True, "checked_count": h.checked_count, "checked_today": True}

@router.delete("/habits/{hid}")
def del_habit(hid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    h = db.query(Habit).filter(Habit.id == hid, Habit.user_id == user.id).first()
    if not h: raise HTTPException(404)
    db.delete(h); db.commit(); return {"ok": True}


# ===== Savings =====
class SavingsIn(BaseModel):
    purpose: str
    target_amount: float
    saved_amount: float = 0
    deadline: str  # YYYY-MM-DD

@router.post("/savings")
def add_savings(body: SavingsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        dl = date.fromisoformat(body.deadline)
    except Exception:
        raise HTTPException(400, "deadline 格式应为 YYYY-MM-DD")
    g = SavingsGoal(user_id=user.id, purpose=body.purpose, target_amount=body.target_amount,
                    saved_amount=body.saved_amount, deadline=dl)
    db.add(g); db.commit(); db.refresh(g)
    return {"id": g.id, "purpose": g.purpose, "target_amount": g.target_amount,
            "saved_amount": g.saved_amount, "deadline": body.deadline}

@router.get("/savings")
def list_savings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(SavingsGoal).filter(SavingsGoal.user_id == user.id).order_by(SavingsGoal.id.desc()).all()
    return [{"id": r.id, "purpose": r.purpose, "target_amount": r.target_amount,
             "saved_amount": r.saved_amount,
             "deadline": r.deadline.isoformat() if r.deadline else ""} for r in rows]

@router.put("/savings/{gid}")
def update_savings(gid: int, body: SavingsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = db.query(SavingsGoal).filter(SavingsGoal.id == gid, SavingsGoal.user_id == user.id).first()
    if not g: raise HTTPException(404)
    try:
        dl = date.fromisoformat(body.deadline)
    except Exception:
        raise HTTPException(400, "deadline 格式应为 YYYY-MM-DD")
    g.purpose = body.purpose
    g.target_amount = body.target_amount
    g.saved_amount = body.saved_amount
    g.deadline = dl
    db.commit(); return {"ok": True}

@router.delete("/savings/{gid}")
def del_savings(gid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    g = db.query(SavingsGoal).filter(SavingsGoal.id == gid, SavingsGoal.user_id == user.id).first()
    if not g: raise HTTPException(404)
    db.delete(g); db.commit(); return {"ok": True}


# ===== Anniversary =====
class AnnivIn(BaseModel):
    name: str
    event_date: str  # MM-DD
    year: int = 0  # 0=每年

@router.post("/anniversaries")
def add_anniv(body: AnnivIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        month, day = body.event_date.split("-")
        yr = body.year if body.year else datetime.now(_BJ).date().year
        ev = date(yr, int(month), int(day))
    except Exception:
        raise HTTPException(400, "event_date 格式应为 MM-DD，如 06-01")
    a = Anniversary(user_id=user.id, name=body.name, event_date=ev, year=body.year)
    db.add(a); db.commit(); db.refresh(a)
    return {"id": a.id, "name": a.name, "event_date": body.event_date, "year": body.year}

@router.get("/anniversaries")
def list_anniv(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Anniversary).filter(Anniversary.user_id == user.id).all()
    return [{"id": r.id, "name": r.name,
             "event_date": r.event_date.strftime("%m-%d") if r.event_date else "",
             "year": r.year} for r in rows]

@router.delete("/anniversaries/{aid}")
def del_anniv(aid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.query(Anniversary).filter(Anniversary.id == aid, Anniversary.user_id == user.id).first()
    if not a: raise HTTPException(404)
    db.delete(a); db.commit(); return {"ok": True}


# ===== Diary =====
class DiaryIn(BaseModel):
    mood: str = "🙂"
    content: str

@router.post("/diary")
def add_diary(body: DiaryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = Diary(user_id=user.id, mood=body.mood, content=body.content)
    today = datetime.now(_BJ).date()
    exps = db.query(Expense).filter(
        Expense.user_id == user.id, Expense.kind != "income",
        Expense.created_at >= datetime.combine(today, datetime.min.time())).all()
    todos = db.query(Todo).filter(Todo.user_id == user.id, Todo.done == 0).all()
    spent = sum(e.amount for e in exps)
    try:
        resp = llm.invoke([
            SystemMessage(content="你是生活小助手，根据用户日记+今日数据写一段不超过100字的温柔小结。"),
            HumanMessage(content=f"用户心情：{body.mood}\n日记：{body.content}\n今日支出：¥{spent:.2f}\n未完成待办：{len(todos)}条")
        ])
        d.summary = resp.content
    except Exception:
        d.summary = ""
    db.add(d); db.commit(); db.refresh(d)
    try:
        mem_content = f"日期：{today.isoformat()} 心情：{body.mood}\n{body.content}"
        get_memory_store(user.id).add_texts(
            [mem_content],
            metadatas=[{"user_id": user.id, "type": "diary"}]
        )
        # 同步落库，供"经验记忆"页面展示
        mdb = SessionLocal()
        try:
            mdb.add(MemoryItem(user_id=user.id, content=mem_content, kind="diary"))
            mdb.commit()
        finally:
            mdb.close()
    except Exception:
        pass
    return {"id": d.id, "mood": d.mood, "content": d.content, "summary": d.summary,
            "date": d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else ""}

@router.get("/diary")
def list_diary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Diary).filter(Diary.user_id == user.id).order_by(Diary.id.desc()).all()
    return [{"id": r.id, "mood": r.mood, "content": r.content, "summary": r.summary,
             "date": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else ""} for r in rows]

@router.get("/diary/mood-trend")
def mood_trend(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Diary).filter(Diary.user_id == user.id).order_by(Diary.created_at.desc()).limit(7).all()
    if len(rows) < 3:
        return {"analysis": "日记太少，写几天再来看趋势～", "count": len(rows)}
    data = "\n".join(f"{r.created_at.strftime('%m-%d') if r.created_at else ''} {r.mood} {r.content[:50]}" for r in reversed(rows))
    try:
        resp = llm.invoke([
            SystemMessage(content="你是情绪分析小助手，根据用户最近一周日记，分析情绪趋势，指出低谷并给一句建议，不超过150字。"),
            HumanMessage(content=data)
        ])
        return {"analysis": resp.content, "count": len(rows)}
    except Exception:
        return {"analysis": "", "count": len(rows)}


@router.put("/diary/{did}")
def update_diary(did: int, body: DiaryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = db.query(Diary).filter(Diary.id == did, Diary.user_id == user.id).first()
    if not d:
        raise HTTPException(404, "日记不存在")
    d.mood = body.mood
    d.content = body.content
    d.summary = ""  # 编辑后旧 AI 小结作废
    db.commit()
    return {"id": d.id, "mood": d.mood, "content": d.content, "summary": d.summary,
            "date": d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else ""}


@router.delete("/diary/{did}")
def del_diary(did: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = db.query(Diary).filter(Diary.id == did, Diary.user_id == user.id).first()
    if not d:
        raise HTTPException(404, "日记不存在")
    db.delete(d)
    db.commit()
    return {"ok": True}


# ===== Water（Agent 工具与页面共用） =====
class WaterIn(BaseModel):
    date: str = ""  # YYYY-MM-DD，留空表示今天
    cups: int

@router.get("/water")
def list_water(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(WaterLog).filter(WaterLog.user_id == user.id).all()
    return [{"date": r.log_date.isoformat(), "cups": r.cups} for r in rows]

@router.post("/water")
def set_water(body: WaterIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        d = date.fromisoformat(body.date) if body.date else datetime.now(_BJ).date()
    except Exception:
        raise HTTPException(400, "date 格式应为 YYYY-MM-DD")
    cups = max(0, int(body.cups))
    row = db.query(WaterLog).filter(WaterLog.user_id == user.id, WaterLog.log_date == d).first()
    if row:
        row.cups = cups
    else:
        db.add(WaterLog(user_id=user.id, log_date=d, cups=cups))
    db.commit()
    return {"date": d.isoformat(), "cups": cups}
