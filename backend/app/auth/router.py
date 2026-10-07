from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..db.models import User, RefreshToken
from .service import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from ..config import settings
import hashlib, random, smtplib
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
    if not settings.smtp_user or not settings.smtp_password:
        raise HTTPException(500, "邮件服务未配置，请联系管理员")
    subject = "【Life Agent】邮箱验证码"
    ttl_min = settings.verify_code_ttl // 60
    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f0f4f8;">
  <div style="max-width:520px;margin:24px auto;background:#ffffff;border-radius:12px;overflow:hidden;font-family:'Helvetica Neue',Arial,'PingFang SC','Microsoft YaHei',sans-serif;box-shadow:0 4px 20px rgba(0,0,0,.06);">
    <div style="background:#2563eb;padding:22px 32px;">
      <div style="color:#ffffff;font-size:18px;font-weight:700;line-height:1.4;">
        <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#ffffff;vertical-align:middle;margin-right:8px;"></span>
        Life Agent
      </div>
    </div>
    <div style="padding:32px;">
      <p style="margin:0 0 6px;font-size:17px;color:#111827;font-weight:700;">邮箱验证</p>
      <p style="margin:0 0 24px;font-size:14px;color:#6b7280;line-height:1.6;">您正在注册 Life Agent 账号，请输入以下验证码完成激活：</p>
      <div style="background:#eff6ff;border:1px dashed #93c5fd;border-radius:10px;padding:22px 16px;text-align:center;margin-bottom:24px;">
        <span style="font-size:38px;font-weight:800;color:#2563eb;letter-spacing:8px;line-height:1.2;">{code}</span>
      </div>
      <p style="margin:0 0 8px;font-size:13px;color:#9ca3af;line-height:1.6;">验证码 {ttl_min} 分钟内有效，请尽快完成验证。</p>
      <p style="margin:0;font-size:13px;color:#9ca3af;line-height:1.6;">如果不是您本人操作，请忽略本邮件。</p>
    </div>
    <div style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">Life Agent · 个人生活管家多智能体平台</p>
    </div>
  </div>
</body>
</html>"""
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email
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