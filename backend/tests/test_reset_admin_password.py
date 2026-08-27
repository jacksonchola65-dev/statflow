from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.db.seeders import reset_admin_password as reset_command
from app.models.user import UserRole


class _FakeSession:
    def __init__(self):
        self.commit = AsyncMock()
        self.rollback = AsyncMock()


class _FakeRepository:
    user = None

    def __init__(self, _session):
        pass

    async def get_by_email(self, _email):
        return self.user


class _FakeUserService:
    update_user = AsyncMock()

    def __init__(self, _session):
        pass


def _admin():
    return SimpleNamespace(
        id="admin-id",
        role=UserRole.ADMIN,
        email="admin@example.com",
        full_name="Original Name",
        is_active=True,
        hashed_password="old-hash",
    )


@pytest.fixture
def reset_dependencies(monkeypatch):
    user = _admin()
    _FakeRepository.user = user
    _FakeUserService.update_user.reset_mock()
    monkeypatch.setattr(reset_command, "UserRepository", _FakeRepository)
    monkeypatch.setattr(reset_command, "UserService", _FakeUserService)
    monkeypatch.setattr(reset_command.settings, "ADMIN_EMAIL", user.email)
    monkeypatch.setattr(reset_command.settings, "ADMIN_PASSWORD", "new-password-secure")
    return user


@pytest.mark.asyncio
async def test_existing_admin_password_is_reset_without_other_user_changes(reset_dependencies):
    session = _FakeSession()

    await reset_command.reset_admin_password(session)

    _FakeUserService.update_user.assert_awaited_once_with(
        "admin-id", password="new-password-secure"
    )
    session.commit.assert_awaited_once_with()
    assert reset_dependencies.role == UserRole.ADMIN
    assert reset_dependencies.email == "admin@example.com"
    assert reset_dependencies.full_name == "Original Name"
    assert reset_dependencies.is_active is True
    assert reset_dependencies.hashed_password == "old-hash"


@pytest.mark.asyncio
async def test_reset_can_be_run_again_with_the_same_password(reset_dependencies):
    session = _FakeSession()

    await reset_command.reset_admin_password(session)
    await reset_command.reset_admin_password(session)

    assert _FakeUserService.update_user.await_count == 2
    assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_nonexistent_admin_is_rejected_without_creation(monkeypatch):
    _FakeRepository.user = None
    session = _FakeSession()
    monkeypatch.setattr(reset_command, "UserRepository", _FakeRepository)
    monkeypatch.setattr(reset_command.settings, "ADMIN_EMAIL", "missing@example.com")

    with pytest.raises(reset_command.AdminPasswordResetError, match="does not exist"):
        await reset_command.reset_admin_password(session)

    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_admin_target_is_rejected_without_mutation(monkeypatch):
    target = _admin()
    target.role = UserRole.VIEWER
    _FakeRepository.user = target
    session = _FakeSession()
    monkeypatch.setattr(reset_command, "UserRepository", _FakeRepository)

    with pytest.raises(reset_command.AdminPasswordResetError, match="does not belong"):
        await reset_command.reset_admin_password(session)

    session.commit.assert_not_awaited()


def test_reset_session_factory_normalizes_render_style_url(monkeypatch):
    captured = {}

    def fake_engine(url, **kwargs):
        captured["url"] = url
        return object()

    monkeypatch.setattr(reset_command.settings, "DATABASE_URL", "postgresql://db.example/statflow")
    monkeypatch.setattr(
        "sqlalchemy.ext.asyncio.create_async_engine",
        fake_engine,
    )

    reset_command._make_reset_session_factory()

    assert captured["url"] == "postgresql+asyncpg://db.example/statflow"


@pytest.mark.asyncio
async def test_cli_output_does_not_include_password_or_hash(monkeypatch, capsys):
    secret = "new-password-secure"
    password_hash = "$argon2id$v=19$m=65536$hidden"

    class _SessionContext:
        async def __aenter__(self):
            return _FakeSession()

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        reset_command,
        "_make_reset_session_factory",
        lambda: lambda: _SessionContext(),
    )
    monkeypatch.setattr(reset_command, "reset_admin_password", AsyncMock())
    monkeypatch.setattr(reset_command.settings, "ADMIN_PASSWORD", secret)

    await reset_command.main()

    output = capsys.readouterr()
    assert secret not in output.out + output.err
    assert password_hash not in output.out + output.err
