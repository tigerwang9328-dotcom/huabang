import os
import sys
import importlib.util
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

_model_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "models", "douyin_color_analytics.py")
_model_spec = importlib.util.spec_from_file_location("douyin_color_analytics_migration_model", _model_path)
if _model_spec is None or _model_spec.loader is None:
    raise RuntimeError("Cannot load Douyin migration metadata")
_model_module = importlib.util.module_from_spec(_model_spec)
_model_spec.loader.exec_module(_model_module)
DouyinColorBase = _model_module.DouyinColorBase


config = context.config
database_url = os.environ.get("DOUYIN_MIGRATOR_DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = DouyinColorBase.metadata


def run_migrations_offline():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema="douyin",
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        connection.execute(text("SET ROLE huabang_douyin_migrator"))
        # SET ROLE starts an implicit transaction in SQLAlchemy 2.x. Commit it
        # before Alembic opens its DDL transaction or the migration is rolled
        # back when the connection closes.
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema="douyin",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
