"""AES 加密工具：用于生成/解析邮件链接中的重置令牌。

方案：AES-256-CBC + PKCS7 填充，载荷为 JSON {email, exp}，整体 base64url 编码。
密钥从 settings.secret_key 派生（SHA-256），不新增配置项。
"""
import base64
import hashlib
import json
import os
import time

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .config import settings


def _key() -> bytes:
    return hashlib.sha256(settings.secret_key.encode()).digest()


def encrypt_link_token(email: str, ttl_sec: int = 3600) -> str:
    """生成 AES 加密令牌，内含邮箱与过期时间戳。"""
    payload = json.dumps({"email": email, "exp": int(time.time()) + ttl_sec}).encode()
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    data = padder.update(payload) + padder.finalize()
    enc = Cipher(algorithms.AES(_key()), modes.CBC(iv)).encryptor()
    ct = enc.update(data) + enc.finalize()
    return base64.urlsafe_b64encode(iv + ct).decode()


def decrypt_link_token(token: str) -> dict:
    """解密并校验令牌，返回 {email, exp}；无效或过期抛 ValueError。"""
    try:
        raw = base64.urlsafe_b64decode(token.encode())
        if len(raw) < 32:
            raise ValueError("token too short")
        iv, ct = raw[:16], raw[16:]
        dec = Cipher(algorithms.AES(_key()), modes.CBC(iv)).decryptor()
        data = dec.update(ct) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        payload = unpadder.update(data) + unpadder.finalize()
        obj = json.loads(payload)
    except Exception as e:
        raise ValueError(f"invalid token: {e}") from e
    if int(obj.get("exp", 0)) < int(time.time()):
        raise ValueError("token expired")
    return obj
