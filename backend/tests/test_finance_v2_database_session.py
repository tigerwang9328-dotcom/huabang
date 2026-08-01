import pytest

from app.core import database
from app.core.config import Settings


def _settings(**overrides):
    defaults = {
        "APP_SECRET_KEY": "finance-v2-test-app-secret-key",
        "DB_PASSWORD": "primary-db-password",
        "JWT_SECRET_KEY": "finance-v2-test-jwt-secret-key",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_finance_database_url_requires_a_complete_dedicated_login():
    settings = _settings(FINANCE_DB_USER="fin_app")

    with pytest.raises(ValueError, match="FINANCE_DB_PASSWORD"):
        _ = settings.FINANCE_DATABASE_URL


def test_finance_database_url_uses_only_the_dedicated_finance_login():
    settings = _settings(
        DB_HOST="primary-db",
        DB_PORT=5433,
        DB_NAME="huabang_ai",
        DB_USER="huabang",
        FINANCE_DB_HOST="finance-db",
        FINANCE_DB_PORT=5434,
        FINANCE_DB_NAME="finance_db",
        FINANCE_DB_USER="fin_app",
        FINANCE_DB_PASSWORD="finance-password",
    )

    assert settings.FINANCE_DATABASE_URL == (
        "postgresql+asyncpg://fin_app:finance-password@finance-db:5434/finance_db"
    )


def test_finance_database_url_escapes_reserved_characters_in_the_dedicated_password():
    settings = _settings(
        FINANCE_DB_HOST="finance-db",
        FINANCE_DB_PORT=5432,
        FINANCE_DB_NAME="huabang_ai",
        FINANCE_DB_USER="fin_app",
        FINANCE_DB_PASSWORD="p@ss:word/with?reserved",
    )

    assert settings.FINANCE_DATABASE_URL == (
        "postgresql+asyncpg://fin_app:p%40ss%3Aword%2Fwith%3Freserved@finance-db:5432/huabang_ai"
    )


class _Session:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def close(self):
        self.closes += 1


@pytest.mark.asyncio
async def test_finance_db_dependency_uses_the_dedicated_session_factory(monkeypatch):
    session = _Session()
    factory = lambda: session
    monkeypatch.setattr(database, "get_finance_session_factory", lambda: factory)

    dependency = database.get_finance_db()
    assert await anext(dependency) is session

    with pytest.raises(StopAsyncIteration):
        await anext(dependency)

    assert session.commits == 1
    assert session.rollbacks == 0
    assert session.closes == 1
