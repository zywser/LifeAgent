from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .db.session import get_db
from .db.models import User
from .auth.service import decode_token
from .logging_config import get_logger

security = HTTPBearer()
logger = get_logger("deps")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> User:
    try:
        payload = decode_token(credentials.credentials)
        user = db.get(User, int(payload["sub"]))
    except Exception as e:
        logger.warning("令牌解析失败：%s", e)
        user = None
    if not user:
        raise HTTPException(401, "not authenticated")
    return user

