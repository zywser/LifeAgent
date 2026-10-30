"""轻量告警：错误事件统一记录 + 可选邮件通道，带节流防风暴。

- 任何告警都先落 logger.error，保证本地日志可查；
- 配置环境变量 ALERT_EMAIL 后，同一事件在 cooldown 秒内只发一封邮件，
  避免同类故障刷屏（未配置则只记日志）；
- 邮件发送失败不影响主流程。
"""
import os
import time

from .logging_config import get_logger
from .mailer import send_email, render_notify_html

logger = get_logger("alerting")
_last_sent: dict[str, float] = {}


def _alert_email() -> str:
    return os.environ.get("ALERT_EMAIL", "").strip()


def alert(event: str, message: str, *, cooldown: int = 300, **detail) -> None:
    now = time.time()
    detail_txt = (" " + " ".join(f"{k}={v}" for k, v in detail.items())) if detail else ""
    logger.error("ALERT [%s] %s%s", event, message, detail_txt)

    recipient = _alert_email()
    if not recipient:
        return
    if now - _last_sent.get(event, 0) < cooldown:
        return
    subject = f"[Life Agent 告警] {event}"
    body = f"事件：{event}\n时间戳：{int(now)}\n\n{message}\n{detail_txt}"
    if send_email(recipient, subject, render_notify_html(subject, body)):
        _last_sent[event] = now
