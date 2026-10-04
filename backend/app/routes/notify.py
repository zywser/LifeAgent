import json
import redis
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..deps import get_current_user
from ..db.models import User, Notification
from ..db.session import get_db
from ..config import settings

router = APIRouter(prefix="/notify", tags=["notify"])
r = redis.from_url(settings.redis_url, decode_responses=True)

def _cache_key(uid): return f"notify:{uid}"

def _invalidate(uid):
    r.delete(_cache_key(uid))

def _fetch_and_cache(uid, db):
    rows = db.query(Notification).filter(Notification.user_id == uid).order_by(Notification.id.desc()).limit(20).all()
    data = [{"id": x.id, "title": x.title, "body": x.body, "read": x.read, "time": x.created_at.isoformat() if x.created_at else ""} for x in rows]
    r.setex(_cache_key(uid), 300, json.dumps(data, ensure_ascii=False))
    return data

@router.get("/list")
def list_notify(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cached = r.get(_cache_key(user.id))
    if cached:
        return json.loads(cached)
    return _fetch_and_cache(user.id, db)

@router.get("/unread")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"count": db.query(Notification).filter(Notification.user_id == user.id, Notification.read == 0).count()}

@router.post("/read/{nid}")
def mark_read(nid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == nid, Notification.user_id == user.id).first()
    if n: n.read = 1; db.commit(); _invalidate(user.id)
    return {"ok": True}

@router.post("/read-all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.user_id == user.id, Notification.read == 0).update({"read": 1})
    db.commit(); _invalidate(user.id)
    return {"ok": True}

@router.delete("/{nid}")
def del_notify(nid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == nid, Notification.user_id == user.id).first()
    if n: db.delete(n); db.commit(); _invalidate(user.id)
    return {"ok": True}
