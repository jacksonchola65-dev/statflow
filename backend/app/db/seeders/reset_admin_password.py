"""Explicit operator command for rotating the configured admin password.

Run with:
    python -m app.db.seeders.reset_admin_password

This module is intentionally separate from the general seeders and is never
called during application startup.
"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import normalize_async_database_url, settings
from app.models.user import UserRole
from app.repositories.user_repository import UserRepository
from app.services.auth_service import UserNotFoundError
from app.services.user_service import UserService
from sqlalchemy.ext.asyncio import AsyncSession


class AdminPasswordResetError(Exception):
    """Raised when the configured admin cannot be safely updated."""


async def reset_admin_password(session: AsyncSession) -> None:
    """Set the configured admin's password without changing other user data."""
    repository = UserRepository(session)
    user = await repository.get_by_email(settings.ADMIN_EMAIL)

    if user is None:
        raise AdminPasswordResetError("Configured admin user does not exist.")
    if user.role != UserRole.ADMIN:
        raise AdminPasswordResetError("Configured admin email does not belong to an admin user.")

    try:
        await UserService(session).update_user(user.id, password=settings.ADMIN_PASSWORD)
        await session.commit()
    except UserNotFoundError as exc:
        await session.rollback()
        raise AdminPasswordResetError("Configured admin user does not exist.") from exc
    except Exception:
        await session.rollback()
        raise


def _make_reset_session_factory():
    """Create a quiet async session factory for this explicit operator command."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(
        normalize_async_database_url(settings.DATABASE_URL),
        echo=False,
        future=True,
        pool_pre_ping=True,
    )
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


async def main() -> None:
    """Run the password reset only when this module is explicitly invoked."""
    session_factory = _make_reset_session_factory()

    try:
        async with session_factory() as session:
            await reset_admin_password(session)
    except AdminPasswordResetError as exc:
        print(f"Admin password reset refused: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("Admin password reset failed; no password was changed.", file=sys.stderr)
        sys.exit(1)

    print("Configured admin password reset successfully.")


if __name__ == "__main__":
    asyncio.run(main())
