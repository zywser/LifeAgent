"""对话历史云端持久化 API。

- GET    /conversations        列表（不含 messages 全文，带 message_count）
- POST   /conversations        保存/更新（有 id 且属于当前用户则更新，否则新建）
- GET    /conversations/{cid}  单条（含 messages）
- DELETE /conversations/{cid}  删除
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..deps import get_current_user
from ..db.models import User, Conversation
from ..db.session import get_db

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationIn(BaseModel):
    id: int | None = None
    title: str = "新对话"
    preview: str = ""
    messages: list = []


def _time(c: Conversation) -> str:
    ts = c.updated_at or c.created_at
    return ts.isoformat() if ts else ""


@router.get("")
def list_convs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.id.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": r.id,
            "title": r.title,
            "preview": r.preview,
            "time": _time(r),
            "message_count": len(json.loads(r.messages or "[]")),
        }
        for r in rows
    ]


@router.post("")
def save_conv(body: ConversationIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    raw = json.dumps(body.messages, ensure_ascii=False)
    if body.id is not None:
        c = (
            db.query(Conversation)
            .filter(Conversation.id == body.id, Conversation.user_id == user.id)
            .first()
        )
        if c:
            c.title = body.title
            c.preview = body.preview
            c.messages = raw
            db.commit()
            db.refresh(c)
            return {"id": c.id, "title": c.title, "preview": c.preview, "time": _time(c)}
    c = Conversation(user_id=user.id, title=body.title, preview=body.preview, messages=raw)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "title": c.title, "preview": c.preview, "time": _time(c)}


@router.get("/{cid}")
def get_conv(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = (
        db.query(Conversation)
        .filter(Conversation.id == cid, Conversation.user_id == user.id)
        .first()
    )
    if not c:
        raise HTTPException(404, "对话不存在")
    return {
        "id": c.id,
        "title": c.title,
        "preview": c.preview,
        "time": _time(c),
        "messages": json.loads(c.messages or "[]"),
    }


@router.delete("/{cid}")
def del_conv(cid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = (
        db.query(Conversation)
        .filter(Conversation.id == cid, Conversation.user_id == user.id)
        .first()
    )
    if not c:
        raise HTTPException(404, "对话不存在")
    db.delete(c)
    db.commit()
    return {"ok": True}
