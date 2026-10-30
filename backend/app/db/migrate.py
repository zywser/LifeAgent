"""启动时数据库迁移入口（编程式封装 Alembic）。

三种情形：
- 全新空库：执行 `upgrade head`，由基线迁移建出全部表；
- 旧库（已有业务表但无 alembic_version，即历史上 create_all 建的库）：
  其结构已与基线一致，执行 `stamp head` 打标记，不重复执行 DDL；
- 已纳管库（有 alembic_version）：执行 `upgrade head` 应用增量迁移。
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from ..config import settings


def _backend_dir() -> Path:
    # app/db/migrate.py -> 上两级为 backend/
    return Path(__file__).resolve().parents[2]


def run_migrations() -> None:
    backend = _backend_dir()
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    # URL 不写入 config：密码可能含 '%'（URL 编码），configparser 会插值报错。
    # env.py 直接从 settings.database_url 建引擎。

    engine = create_engine(settings.database_url)
    try:
        tables = inspect(engine).get_table_names()
    finally:
        engine.dispose()

    if "alembic_version" not in tables:
        if "users" in tables:
            command.stamp(cfg, "head")
        else:
            command.upgrade(cfg, "head")
    else:
        command.upgrade(cfg, "head")
