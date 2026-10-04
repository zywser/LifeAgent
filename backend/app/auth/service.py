from datetime import datetime, timedelta, timezone
import hashlib
import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from ..config import settings
from ..db.models import User, RefreshToken

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": str(user_id), "type": "access", "exp": exp}, settings.secret_key, algorithm="HS256")


def create_refresh_token(db: Session, user_id: int) -> str:
    raw = jwt.encode({"sub": str(user_id), "type": "refresh", "jti": hashlib.sha256(f"{user_id}:{datetime.now().timestamp()}".encode()).hexdigest(), "exp": datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)}, settings.secret_key, algorithm="HS256")
    db.add(RefreshToken(user_id=user_id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)))
    db.commit()
    return raw


def decode_token(token: str, expected_type: str = "access") -> dict:
    payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("invalid token type")
    return payload

