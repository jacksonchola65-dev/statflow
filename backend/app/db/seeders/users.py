"""
Admin user seeder — idempotent.

Creates the initial admin user from the ADMIN_EMAIL / ADMIN_PASSWORD
environment variables (or their defaults in core/config.py).

Idempotency guarantee
---------------------
If a user with ADMIN_EMAIL already exists the seeder does nothing and
exits 0.  Running the seeder a second time will never create a duplicate
or overwrite the password of an existing account.

Run with:
    python -m app.db.seeders.users

Environment variables (set in backend/.env or exported in the shell):
    ADMIN_EMAIL     — email for the admin account  (default: admin@statflow.local)
    ADMIN_PASSWORD  — plaintext password to hash   (default: ChangeMe123!)
"""

import asyncio
import logging
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db.seeders.seed import _make_quiet_session_factory
from app.models.user import UserRole
from app.repositories.user_repository import UserRepository

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
)


async def seed_admin_user(session: AsyncSession) -> dict[str, int | bool]:
    """
    Ensure the admin user defined by ADMIN_EMAIL exists.

    Returns a dict with:
        created  — 1 if the user was inserted, 0 otherwise
        skipped  — True if the user already existed
    """
    repo = UserRepository(session)

    existing = await repo.get_by_email(settings.ADMIN_EMAIL)
    if existing is None:
        hashed = hash_password(settings.ADMIN_PASSWORD)
        await repo.create_user(
            email=settings.ADMIN_EMAIL,
            hashed_password=hashed,
            full_name="StatFlow Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        await session.commit()
        return {"created": 1, "skipped": False}

    # Ensure the seeded admin account remains active and correctly configured.
    # If the password has changed in .env, update the hash using the canonical
    # AuthService hashing implementation.
    needs_update = False
    if not existing.is_active:
        existing.is_active = True
        needs_update = True
    if existing.role != UserRole.ADMIN:
        existing.role = UserRole.ADMIN
        needs_update = True
    if not verify_password(settings.ADMIN_PASSWORD, existing.hashed_password):
        existing.hashed_password = hash_password(settings.ADMIN_PASSWORD)
        needs_update = True

    if needs_update:
        await session.commit()
        return {"created": 0, "skipped": False}

    return {"created": 0, "skipped": True}


async def main() -> None:
    print("\n StatFlow — Admin User Seeder")
    print(" ──────────────────────────────")

    _SeedSession = _make_quiet_session_factory()

    try:
        async with _SeedSession() as session:
            result = await seed_admin_user(session)
    except Exception as exc:
        print(f"\n✘ Seeding failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if result["skipped"]:
        print(f"  Admin user '{settings.ADMIN_EMAIL}' already exists — no changes made.")
    else:
        print(f"  Admin user '{settings.ADMIN_EMAIL}' created successfully.")

    print(" ──────────────────────────────")
    print(" Done.\n")


if __name__ == "__main__":
    asyncio.run(main())
