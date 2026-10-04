from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..db.models import User, RefreshToken
from .service import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
import hashlib
from datetime import datetime, timezone

router = APIRouter(prefix="/auth", tags=["auth"])

class Credentials(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/register")
def register(data: Credentials, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(409, "email already registered")
    user = User(email=data.email, password_hash=hash_password(data.password))
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token": create_access_token(user.id), "refresh_token": create_refresh_token(db, user.id), "token_type": "bearer"}

@router.post("/login")
def login(data: Credentials, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    return {"access_token": create_access_token(user.id), "refresh_token": create_refresh_token(db, user.id), "token_type": "bearer"}

@router.post("/refresh")
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token, "refresh")
    except Exception:
        raise HTTPException(401, "invalid refresh token")
    record = db.query(RefreshToken).filter(RefreshToken.token_hash == hashlib.sha256(data.refresh_token.encode()).hexdigest(), RefreshToken.revoked == 0).first()
    if not record or record.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(401, "refresh token expired")
    record.revoked = 1; db.commit()
    return {"access_token": create_access_token(int(payload["sub"])), "refresh_token": create_refresh_token(db, int(payload["sub"])), "token_type": "bearer"}

