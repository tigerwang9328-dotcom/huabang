from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, MappedColumn
from sqlalchemy import text
from typing import AsyncGenerator
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.APP_DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


_finance_engine: AsyncEngine | None = None
_finance_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_finance_session_factory() -> async_sessionmaker[AsyncSession]:
    """Build the dedicated Finance V2 session lazily and never fall back."""
    global _finance_engine, _finance_session_factory
    if _finance_session_factory is None:
        _finance_engine = create_async_engine(
            settings.FINANCE_DATABASE_URL,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            echo=settings.APP_DEBUG,
        )
        _finance_session_factory = async_sessionmaker(
            _finance_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _finance_session_factory


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_finance_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a Finance V2-only connection; configuration gaps fail closed."""
    session_factory = get_finance_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return False
