from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..db.models import User, RefreshToken
from .service import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from ..config import settings
from ..mailer import send_email, render_verify_html
import hashlib, random
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime, timezone
import redis as redis_lib

router = APIRouter(prefix="/auth", tags=["auth"])

_r = redis_lib.from_url(settings.redis_url, decode_responses=True)


class Credentials(BaseModel):
    email: EmailStr
    password: str


class RegisterData(BaseModel):
    email: EmailStr
    password: str
    verify_code: str


class SendCodeRequest(BaseModel):
    email: EmailStr


class RefreshRequest(BaseModel):
    refresh_token: str


def _send_verify_email(to_email: str, code: str):
    if not send_email(to_email, "【Life Agent】邮箱验证码", render_verify_html(code, settings.verify_code_ttl // 60)):
        raise HTTPException(500, "邮件发送失败，请检查邮件服务配置")
    try:
        if settings.smtp_port == 465:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
            server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_from or settings.smtp_user, [to_email], msg.as_string())
        server.quit()
    except Exception as e:
        raise HTTPException(500, f"邮件发送失败：{e}")


@router.post("/send_code")
def send_code(data: SendCodeRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(409, "email already registered")
    cd_key = f"verify:cd:{data.email}"
    if _r.exists(cd_key):
        remain = _r.ttl(cd_key)
        raise HTTPException(429, f"发送过于频繁，请 {remain} 秒后重试")
    code = f"{random.randint(0, 999999):06d}"
    _r.setex(f"verify:email:{data.email}", settings.verify_code_ttl, code)
    _r.setex(cd_key, settings.verify_code_cooldown, "1")
    _send_verify_email(data.email, code)
    return {"sent": True, "ttl": settings.verify_code_ttl}


@router.post("/register")
def register(data: RegisterData, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(409, "email already registered")
    key = f"verify:email:{data.email}"
    saved = _r.get(key)
    if not saved or saved != data.verify_code:
        raise HTTPException(400, "验证码错误或已过期，请重新获取")
    _r.delete(key)
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