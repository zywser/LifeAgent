from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..deps import get_current_user
from ..db.models import User
from ..llm import llm
from langchain_core.messages import HumanMessage, SystemMessage

router = APIRouter(prefix="/summary", tags=["summary"])

class Snapshot(BaseModel):
    todos: list = []
    expenses: list = []
    anniversaries: list = []
    habits: dict = {}
    water: int = 0
    savings: dict = {}

@router.post("/today")
async def today_summary(snap: Snapshot, user: User = Depends(get_current_user)):
    lines = [f"用户：{user.email}", f"待办未完成：{len([t for t in snap.todos if not t.get('done')])} 条"]
    if snap.todos:
        for t in snap.todos[:5]:
            lines.append(f"  - [{'x' if t.get('done') else ' '}] {t.get('text','')}")
    spent = sum(float(e.get('amount',0)) for e in snap.expenses)
    lines.append(f"累计记账：{len(snap.expenses)} 笔，共 ¥{spent:.2f}")
    if snap.anniversaries:
        lines.append(f"纪念日：{len(snap.anniversaries)} 个即将到来")
        for a in snap.anniversaries[:3]:
            lines.append(f"  - {a.get('name','')}：{a.get('date','')}")
    lines.append(f"今日喝水：{snap.water} 杯")
    if snap.savings:
        lines.append(f"存钱目标：{snap.savings.get('name','')} ¥{snap.savings.get('saved',0)}/¥{snap.savings.get('target',0)}")

    data = "\n".join(lines)
    prompt = f"""你是用户的私人生活管家。根据以下用户今日生活数据，用亲切、简洁的语气生成一段不超过150字的"今日晨间摘要"，像朋友发消息一样：
- 先说早安
- 点出今天最重要的事（待办/纪念日）
- 给出一条贴心建议
- 不要列点，自然一段话

数据：
{data}"""
    resp = llm.invoke([
        SystemMessage(content="你是贴心的生活管家，说话温暖、不啰嗦。"),
        HumanMessage(content=prompt)
    ])
    return {"summary": resp.content}
