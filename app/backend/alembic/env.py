"""Alembic migration configuration"""
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
from sqlmodel import SQLModel

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 允许通过环境变量覆盖数据库 URL（应用启动时 database.py 也会动态设置）
import os
_alembic_db_url = os.environ.get("ALEMBIC_DB_URL")
if _alembic_db_url:
    config.set_main_option("sqlalchemy.url", _alembic_db_url)

# 导入全部 model 模块，确保 target_metadata 覆盖所有表
import iptv_check.infra.database  # noqa: F401
import iptv_check.infra.persistence.event_store  # noqa: F401
import iptv_check.application.services.fetch_service  # noqa: F401

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
