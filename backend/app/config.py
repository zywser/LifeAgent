import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# 关键：先把 .env 里所有变量加载到 os.environ，
# 这样 langchain / langsmith 等第三方库才能直接读到它们需要的环境变量。
# pydantic-settings 只读不写，不会把变量注入 os.environ。
load_dotenv()


class Settings(BaseSettings):
    app_name: str = "Life Agent"
    secret_key: str
    access_token_expire_minutes: int = 120
    refresh_token_expire_days: int = 7
    database_url: str
    redis_url: str = "redis://localhost:6379"
    dashscope_api_key: str
    tavily_api_key: str = ""
    langsmith_project: str = "Life-Agent"
    langsmith_tracing: bool = True
    langsmith_api_key: str = ""
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    backend_cors_origins: str = "http://localhost:5173,http://localhost"
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    verify_code_ttl: int = 600
    verify_code_cooldown: int = 60
    frontend_base: str = "http://localhost:5174"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.backend_cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# ===== LangSmith 显式接入 =====
# langsmith / langchain 通过环境变量读取 tracing 配置，且只在首次读取时生效。
# 这里把 Settings 里的值（.env 或默认值）显式写入 os.environ，保证：
#  1) 不需要依赖 .env 恰好被第三方库读到的时机问题；
#  2) 未配置 LANGSMITH_API_KEY 时自动降级为关闭 tracing，不打扰正常运行；
#  3) 评测/单测里可以覆盖这些变量来开关。
def apply_langsmith_env() -> None:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true" if settings.langsmith_tracing else "false")
    os.environ.setdefault("LANGSMITH_TRACING", "true" if settings.langsmith_tracing else "false")
    os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
    else:
        # 没有 API key 时关闭 tracing，避免 SDK 反复报错/重试
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["LANGSMITH_TRACING"] = "false"
    if settings.langsmith_endpoint:
        os.environ.setdefault("LANGSMITH_ENDPOINT", settings.langsmith_endpoint)
        os.environ.setdefault("LANGCHAIN_ENDPOINT", settings.langsmith_endpoint)


apply_langsmith_env()
