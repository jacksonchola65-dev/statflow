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
from app.services.auth_service import PasswordPolicyError, UserNotFoundError
from app.services.user_service import UserService
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


class AdminPasswordResetError(Exception):
    """Raised when the configured admin cannot be safely updated."""


class AdminPasswordResetConfigurationError(AdminPasswordResetError):
    """Raised when the configured database URL is invalid."""


class AdminPasswordResetDatabaseError(AdminPasswordResetError):
    """Raised when the database cannot complete the operation."""


class AdminPasswordResetPasswordError(AdminPasswordResetError):
    """Raised when the configured password violates application policy."""


class AdminPasswordResetUpdateError(AdminPasswordResetError):
    """Raised when the password update cannot be completed."""


async def reset_admin_password(session: AsyncSession) -> None:
    """Set the configured admin's password without changing other user data."""
    repository = UserRepository(session)
    user = await repository.get_by_email(settings.ADMIN_EMAIL)

    if user is None:
        raise AdminPasswordResetError("Configured admin user does not exist.")
    if user.role != UserRole.ADMIN:
        raise AdminPasswordResetError("Configured admin email does not belong to an admin user.")
    if not user.is_active:
        raise AdminPasswordResetError("Configured admin user is inactive.")

    try:
        await UserService(session).update_user(user.id, password=settings.ADMIN_PASSWORD)
        await session.commit()
    except UserNotFoundError as exc:
        await session.rollback()
        raise AdminPasswordResetError("Configured admin user does not exist.") from exc
    except PasswordPolicyError as exc:
        await session.rollback()
        raise AdminPasswordResetPasswordError(
            "Configured admin password failed validation."
        ) from exc
    except SQLAlchemyError as exc:
        await session.rollback()
        raise AdminPasswordResetDatabaseError("Database operation failed.") from exc
    except Exception:
        await session.rollback()
        raise AdminPasswordResetUpdateError("Password update failed.")


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
    try:
        session_factory = _make_reset_session_factory()
        async with session_factory() as session:
            await reset_admin_password(session)
    except AdminPasswordResetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError:
        print("ERROR: configuration validation failed", file=sys.stderr)
        sys.exit(1)
    except SQLAlchemyError:
        print("ERROR: database connection failed", file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("ERROR: unexpected reset failure", file=sys.stderr)
        sys.exit(1)

    print("Configured admin password reset successfully.")


if __name__ == "__main__":
    asyncio.run(main())
