# ---------------------------------------------------------------------------
# MUST be the very first executable code — before any asyncio or asyncpg
# imports. Forces SelectorEventLoop on Windows so asyncpg socket teardown
# works correctly.
# ---------------------------------------------------------------------------
import sys

if sys.platform == "win32":
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
# ---------------------------------------------------------------------------

"""
Shared pytest fixtures for the StatFlow backend test suite.

Isolation strategy:
- A separate database (statflow_test) is used.
  The development database (statflow) is NEVER touched.
- asyncio_default_fixture_loop_scope = function (in pytest.ini) means each
  async fixture runs in the same per-test event loop as the test itself.
  This eliminates all "Future attached to a different loop" errors.
- setup_test_database is synchronous (uses asyncio.run()) so it is
  unaffected by the function-scoped loop setting.
- NullPool ensures connections are never pooled across loops.
"""
import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.session import get_db
from app.main import create_app


# ---------------------------------------------------------------------------
# Session-scoped synchronous fixture: runs once, uses its own event loop.
# Drops+creates tables and seeds provinces before any tests run.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Drop/create tables and seed provinces and categories once for the whole session."""
    from app.core.config import settings
    from app.db.base import Base
    from app.db.seeders.provinces import seed_provinces
    from app.db.seeders.categories import seed_categories

    async def _run():
        engine = create_async_engine(
            settings.TEST_DATABASE_URL,
            echo=False,
            future=True,
            poolclass=NullPool,
        )
        async with engine.begin() as conn:
            # Drop everything including enum types with CASCADE to avoid
            # "type in use" errors when old migrations left tables behind.
            # asyncpg requires each DDL statement to be executed separately.
            await conn.execute(sa.text("DROP SCHEMA public CASCADE"))
            await conn.execute(sa.text("CREATE SCHEMA public"))
            await conn.execute(sa.text("GRANT ALL ON SCHEMA public TO public"))
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        async with factory() as session:
            await seed_provinces(session)
            await seed_categories(session)
        await engine.dispose()

    asyncio.run(_run())
    yield


# ---------------------------------------------------------------------------
# Function-scoped async fixtures — each runs in the same per-test event loop.
# NullPool means the connection is discarded (not returned to pool) on close.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session(setup_test_database) -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh database session for each test.

    Each test runs inside a transaction that is rolled back at teardown.
    This prevents committed endpoint requests from leaking state between tests.
    """
    from app.core.config import settings

    engine = create_async_engine(
        settings.TEST_DATABASE_URL,
        echo=False,
        future=True,
        poolclass=NullPool,
    )

    async with engine.connect() as connection:
        transaction = await connection.begin()
        factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        async with factory() as session:
            try:
                yield session
            finally:
                await session.close()
                if transaction.is_active:
                    await transaction.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx AsyncClient wired to the test database.

    No auth or CSRF overrides — this fixture exercises real authentication
    and CSRF behavior. Tests in tests/api/ that predate Task 10 should use
    authed_client instead.
    """
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with db_session.begin_nested():
            yield db_session
            await db_session.flush()

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession):
    """Seed a real ADMIN user in the test database for auth tests.

    Used by test_users.py (REQ-13.5) to exercise role-enforcement logic.
    Each test that uses this fixture gets a fresh user (unique email) so
    there are no cross-test email collisions.
    """
    import uuid as _uuid
    from app.models.user import UserRole
    from app.services.auth_service import AuthService

    svc = AuthService(db_session)
    user = await svc.create_user(
        email=f"admin-seed-{_uuid.uuid4().hex[:8]}@test.example",
        password="admin-seed-password-secure",
        full_name="Seeded Admin User",
        role=UserRole.ADMIN,
        is_active=True,
    )
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def authed_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an AsyncClient with a real ADMIN user and CSRF bypassed.

    Creates a real User record in the test database so the override returns
    a proper ORM model. Use this fixture in tests that focus on endpoint
    business logic rather than authentication/CSRF behavior.
    """
    import uuid as _uuid
    from app.core.config import settings
    from app.core.dependencies import get_current_user, validate_csrf
    from app.models.user import UserRole
    from app.services.auth_service import AuthService

    app = create_app()

    from types import SimpleNamespace

    # Create a real ADMIN user in the test database.
    svc = AuthService(db_session)
    admin_user = await svc.create_user(
        email=f"authed-client-{_uuid.uuid4().hex[:8]}@test.example",
        password="authed-client-test-password",
        full_name="Authed Client Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    await db_session.flush()

    principal = SimpleNamespace(
        id=admin_user.id,
        role=admin_user.role,
        is_active=admin_user.is_active,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with db_session.begin_nested():
            yield db_session
            await db_session.flush()

    async def override_get_current_user():
        return principal

    async def override_validate_csrf():
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[validate_csrf] = override_validate_csrf

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
