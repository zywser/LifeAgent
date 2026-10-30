"""Alembic 迁移环境。

数据库 URL 与目标元数据均来自应用本身，避免在 alembic.ini 里重复维护：
- url   <- app.config.settings.database_url
- target_metadata <- app.db.base.Base.metadata（导入 models 以注册全部表）
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import settings
from app.db.base import Base
import app.db.models  # noqa: F401  确保 14 张表全部注册到 metadata

# 注意：数据库 URL 直接来自 settings，不写入 alembic config。
# 密码经 URL 编码后可能含 '%'（如 %40），写进 configparser 会触发插值错误。
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
