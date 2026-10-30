"""统一日志配置。

- 输出到标准输出（Docker 环境下可直接被 `docker logs` 收集）
- 级别由环境变量 LOG_LEVEL 控制，默认 INFO
- 第三方库（apscheduler/httpx/httpcore 等）默认提升到 WARNING，避免刷屏
- setup_logging() 幂等，重复调用不会重复添加 handler
"""
import logging
import os
from logging.config import dictConfig

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_CONFIGURED = False


def setup_logging() -> None:
    global _CONFIGURED
    level = (os.environ.get("LOG_LEVEL") or "INFO").upper()
    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": _DEFAULT_FORMAT,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
            },
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
        "loggers": {
            # 应用内 logger 统一前缀
            "lifeagent": {"level": level, "handlers": ["console"], "propagate": False},
            # 压低第三方库的冗余日志
            "apscheduler": {"level": "WARNING"},
            "httpx": {"level": "WARNING"},
            "httpcore": {"level": "WARNING"},
            "urllib3": {"level": "WARNING"},
            "openai": {"level": "WARNING"},
            "langsmith": {"level": "WARNING"},
        },
    })
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """获取应用 logger（统一 lifeagent 前缀，保证级别受 LOG_LEVEL 管理）。"""
    if not _CONFIGURED:
        setup_logging()
    if not name.startswith("lifeagent"):
        name = f"lifeagent.{name}"
    return logging.getLogger(name)
