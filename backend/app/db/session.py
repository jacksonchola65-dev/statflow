import asyncio
from typing import AsyncGenerator

from app.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = None
_engine_loop_id: int | None = None


def get_engine():
    """Create a loop-local engine so tests and app instances do not reuse a
    connection pool across different event loops.
    """
    global engine, _engine_loop_id

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if engine is None or (loop is not None and _engine_loop_id != id(loop)):
        if engine is not None:
            engine.sync_engine.dispose()
        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.ENVIRONMENT == "development",
            future=True,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=True,
        )
        _engine_loop_id = id(loop) if loop is not None else None

    return engine


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an async database session and guarantee it is closed afterwards.
    Usage:
        db: AsyncSession = Depends(get_db)
    """
    session_factory = async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
