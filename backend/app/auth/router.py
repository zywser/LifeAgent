from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..db.models import User, RefreshToken
from .service import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from ..deps import get_current_user
from ..config import settings
from ..mailer import send_email, render_verify_html, render_reset_html
from ..security import encrypt_link_token, decrypt_link_token
import hashlib, random
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
    user = User(email=data.email, password_hash=hash_password(data.password), username=f"L{random.randint(0, 999999):06d}")
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token": create_access_token(user.id), "refresh_token": create_refresh_token(db, user.id), "token_type": "bearer", "username": user.username, "email": user.email}


@router.post("/login")
def login(data: Credentials, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    return {"access_token": create_access_token(user.id), "refresh_token": create_refresh_token(db, user.id), "token_type": "bearer", "username": user.username, "email": user.email}


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
    me = db.query(User).filter(User.id == int(payload["sub"])).first()
    return {"access_token": create_access_token(int(payload["sub"])), "refresh_token": create_refresh_token(db, int(payload["sub"])), "token_type": "bearer", "username": me.username if me else "", "email": me.email if me else ""}


# ================= 更换邮箱（老邮箱验证 → 新邮箱验证） =================

class ChangeEmailOldCode(BaseModel):
    verify_code: str


class ChangeEmailNew(BaseModel):
    new_email: EmailStr
    verify_code: str


class ChangePasswordData(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordData(BaseModel):
    token: str
    new_password: str


def _send_code_inner(key_prefix: str, email: str, subject: str):
    """通用验证码发送：key_prefix 用于区分场景。"""
    cd_key = f"verify:cd:{key_prefix}:{email}"
    if _r.exists(cd_key):
        raise HTTPException(429, f"发送过于频繁，请 {_r.ttl(cd_key)} 秒后重试")
    code = f"{random.randint(0, 999999):06d}"
    _r.setex(f"verify:{key_prefix}:{email}", settings.verify_code_ttl, code)
    _r.setex(cd_key, settings.verify_code_cooldown, "1")
    _send_verify_email(email, code)


@router.post("/change_email/send_old")
def change_email_send_old(user: User = Depends(get_current_user)):
    """向当前账号的老邮箱发送验证码（换邮箱第一步）。"""
    _send_code_inner("old", user.email, f"【Life Agent】更换邮箱验证（{user.email}）")
    return {"sent": True, "ttl": settings.verify_code_ttl}


@router.post("/change_email/verify_old")
def change_email_verify_old(data: ChangeEmailOldCode, user: User = Depends(get_current_user)):
    """校验老邮箱验证码，通过后允许进入更换新邮箱步骤。"""
    saved = _r.get(f"verify:old:{user.email}")
    if not saved or saved != data.verify_code:
        raise HTTPException(400, "验证码错误或已过期，请重新获取")
    _r.delete(f"verify:old:{user.email}")
    _r.setex(f"change:ok:{user.id}", 600, "1")
    return {"approved": True}


@router.post("/change_email/send_new")
def change_email_send_new(data: SendCodeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """向新邮箱发送验证码（需先通过老邮箱验证）。"""
    if not _r.exists(f"change:ok:{user.id}"):
        raise HTTPException(403, "请先完成老邮箱验证")
    if data.email.lower() == user.email.lower():
        raise HTTPException(400, "新邮箱不能与当前邮箱相同")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(409, "该邮箱已被注册")
    _send_code_inner("new", data.email, f"【Life Agent】新邮箱验证码")
    return {"sent": True, "ttl": settings.verify_code_ttl}


@router.post("/change_email")
def change_email(data: ChangeEmailNew, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """老邮箱验证通过 + 新邮箱验证码正确 → 更新邮箱。"""
    if not _r.exists(f"change:ok:{user.id}"):
        raise HTTPException(403, "请先完成老邮箱验证")
    if data.new_email.lower() == user.email.lower():
        raise HTTPException(400, "新邮箱不能与当前邮箱相同")
    if db.query(User).filter(User.email == data.new_email).first():
        raise HTTPException(409, "该邮箱已被注册")
    saved = _r.get(f"verify:new:{data.new_email}")
    if not saved or saved != data.verify_code:
        raise HTTPException(400, "新邮箱验证码错误或已过期，请重新获取")
    _r.delete(f"verify:new:{data.new_email}")
    _r.delete(f"change:ok:{user.id}")
    user.email = data.new_email
    db.commit()
    return {"email": user.email, "username": user.username}


# ================= 修改密码 =================

@router.post("/change_password")
def change_password(data: ChangePasswordData, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "当前密码不正确")
    if len(data.new_password) < 6:
        raise HTTPException(400, "新密码至少 6 位")
    if verify_password(data.new_password, user.password_hash):
        raise HTTPException(400, "新密码不能与当前密码相同")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"changed": True}


# ================= 忘记密码（邮件链接 + AES 令牌） =================

@router.post("/forgot_password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """向注册邮箱发送含 AES 加密链接的重置邮件。邮箱不存在也返回成功，避免枚举。"""
    user = db.query(User).filter(User.email == data.email).first()
    if user:
        token = encrypt_link_token(user.email, ttl_sec=3600)
        link = f"{settings.frontend_base}/life/reset-password?token={token}"
        send_email(user.email, "【Life Agent】重置密码", render_reset_html(link))
    return {"sent": True}


@router.post("/reset_password")
def reset_password(data: ResetPasswordData, db: Session = Depends(get_db)):
    try:
        payload = decrypt_link_token(data.token)
    except ValueError:
        raise HTTPException(400, "链接无效或已过期，请重新发送")
    if len(data.new_password) < 6:
        raise HTTPException(400, "新密码至少 6 位")
    user = db.query(User).filter(User.email == payload["email"]).first()
    if not user:
        raise HTTPException(400, "账号不存在")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"changed": True}