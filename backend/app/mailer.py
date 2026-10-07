"""通用邮件发送（SMTP）+ 邮件 HTML 模板。

供验证码邮件、定时任务通知邮件共用。
send_email 不抛异常：SMTP 未配置或发送失败时返回 False，方便定时任务容错。
"""
import html
import smtplib
from email.header import Header
from email.mime.text import MIMEText

from .config import settings


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """发送 HTML 邮件。成功返回 True，SMTP 未配置或发送失败返回 False。"""
    if not settings.smtp_user or not settings.smtp_password:
        return False
    msg = MIMEText(html_body, "html", "utf-8")
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
        return True
    except Exception:
        return False


def render_notify_html(title: str, body: str) -> str:
    """通知邮件 HTML：蓝白卡片，与验证码邮件同一风格。"""
    t = html.escape(title)
    b = html.escape(body)
    return f"""<!DOCTYPE html>
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
      <p style="margin:0 0 10px;font-size:17px;color:#111827;font-weight:700;">{t}</p>
      <p style="margin:0;font-size:15px;color:#374151;line-height:1.8;white-space:pre-wrap;">{b}</p>
    </div>
    <div style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">Life Agent · 个人生活管家多智能体平台</p>
    </div>
  </div>
</body>
</html>"""


def render_verify_html(code: str, ttl_min: int) -> str:
    """验证码邮件 HTML：验证码单独一行、加大加粗。"""
    return f"""<!DOCTYPE html>
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