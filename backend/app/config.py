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
    backend_cors_origins: str = "http://localhost:5173,http://localhost"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.backend_cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
