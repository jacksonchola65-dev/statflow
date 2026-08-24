from types import SimpleNamespace

import pytest
from app.db.seeders import users as admin_seeder
from app.models.user import UserRole


@pytest.mark.asyncio
async def test_existing_admin_password_is_not_reset(monkeypatch):
    original_hash = "stored-password-hash"
    existing = SimpleNamespace(
        is_active=True,
        role=UserRole.ADMIN,
        hashed_password=original_hash,
    )

    class _Repository:
        def __init__(self, _session):
            pass

        async def get_by_email(self, _email):
            return existing

    monkeypatch.setattr(admin_seeder, "UserRepository", _Repository)
    monkeypatch.setattr(admin_seeder.settings, "ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(admin_seeder.settings, "ADMIN_PASSWORD", "new-bootstrap-password")

    result = await admin_seeder.seed_admin_user(SimpleNamespace())

    assert result == {"created": 0, "skipped": True}
    assert existing.hashed_password == original_hash
