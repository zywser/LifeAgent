"""长期记忆查询 API（页面展示用，记忆写入与向量库同步）。

- GET    /memory/list     记忆条目列表（倒序，limit 100）
- DELETE /memory/{mid}    删除一条记忆
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..deps import get_current_user
from ..db.models import User, MemoryItem
from ..db.session import get_db
from ..vector_store.factory import delete_memory_vectors

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/list")
def list_memory(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user.id)
        .order_by(MemoryItem.id.desc())
        .limit(100)
        .all()
    )
    return {
        "count": db.query(MemoryItem).filter(MemoryItem.user_id == user.id).count(),
        "items": [
            {
                "id": r.id,
                "content": r.content,
                "kind": r.kind,
                "time": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
    }


@router.delete("/{mid}")
def del_memory(mid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = (
        db.query(MemoryItem)
        .filter(MemoryItem.id == mid, MemoryItem.user_id == user.id)
        .first()
    )
    if not m:
        raise HTTPException(404, "记忆不存在")
    # 先清理向量库再删 DB 记录；DB 记录保留便于清理失败时重试
    vectors_deleted = delete_memory_vectors(user.id, m.content)
    db.delete(m)
    db.commit()
    return {"ok": True, "vectors_deleted": vectors_deleted}
