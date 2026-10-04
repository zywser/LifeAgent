from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..deps import get_current_user
from ..db.models import User
from ..vector_store.factory import get_memory_store

router = APIRouter(prefix="/sync", tags=["sync"])

class LifeData(BaseModel):
    todos: list = []
    expenses: list = []
    anniversaries: list = []
    habits: dict = {}
    water: int = 0
    savings: dict = {}
    diary: list = []

@router.post("/life")
async def sync_life(data: LifeData, user: User = Depends(get_current_user)):
    docs = []
    metas = []

    # 待办
    undone = [t for t in data.todos if not t.get('done')]
    if undone:
        docs.append("用户当前未完成待办：\n" + "\n".join(f"- {t.get('text','')}" for t in undone[:10]))
        metas.append({"user_id": user.id, "type": "todo"})

    # 记账
    if data.expenses:
        total = sum(float(e.get('amount',0)) for e in data.expenses)
        recent = data.expenses[-10:]
        lines = "\n".join(f"- {e.get('time','')} {e.get('category','')} ¥{e.get('amount','')} {e.get('note','')}" for e in recent)
        docs.append(f"用户近期记账（共 {len(data.expenses)} 笔，累计 ¥{total:.2f}）：\n{lines}")
        metas.append({"user_id": user.id, "type": "expense"})

    # 纪念日
    if data.anniversaries:
        lines = "\n".join(f"- {a.get('name','')}：{a.get('date','')}" for a in data.anniversaries)
        docs.append(f"用户的纪念日：\n{lines}")
        metas.append({"user_id": user.id, "type": "anniversary"})

    # 习惯
    if data.habits:
        lines = []
        for name, dates in data.habits.items():
            if isinstance(dates, list) and dates:
                lines.append(f"- {name}：连续 {len(set(dates))} 天")
        if lines:
            docs.append("用户坚持的习惯：\n" + "\n".join(lines))
            metas.append({"user_id": user.id, "type": "habit"})

    # 喝水
    if data.water:
        docs.append(f"用户今天已喝 {data.water} 杯水")
        metas.append({"user_id": user.id, "type": "water"})

    # 存钱
    if data.savings:
        docs.append(f"用户存钱目标：{data.savings.get('name','')}，已存 ¥{data.savings.get('saved',0)}，目标 ¥{data.savings.get('target',0)}")
        metas.append({"user_id": user.id, "type": "savings"})

    # 日记
    if data.diary:
        recent = data.diary[-5:]
        lines = "\n".join(f"- {d.get('date','')} {d.get('mood','')} {d.get('text','')}" for d in recent)
        docs.append(f"用户近期日记：\n{lines}")
        metas.append({"user_id": user.id, "type": "diary"})

    if docs:
        get_memory_store(user.id).add_texts(docs, metadatas=metas)

    return {"ok": True, "synced": len(docs)}
