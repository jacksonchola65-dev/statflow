from types import SimpleNamespace

import pytest
from app.main import lifespan


class _Connection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def run_sync(self, callback):
        callback(None)


class _Engine:
    def __init__(self):
        self.disposed = False

    def connect(self):
        return _Connection()

    async def dispose(self):
        self.disposed = True


@pytest.mark.asyncio
async def test_lifespan_disposes_database_engine(monkeypatch):
    engine = _Engine()
    monkeypatch.setattr("app.main.get_engine", lambda: engine)

    async with lifespan(SimpleNamespace()):
        assert engine.disposed is False

    assert engine.disposed is True
