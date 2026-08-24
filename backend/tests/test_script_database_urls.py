import importlib

import pytest
from sqlalchemy.ext import asyncio as sqlalchemy_asyncio


@pytest.mark.parametrize(
    "module_name",
    [
        "app.db.seeders.seed",
        "scripts.execute_district_population_ingestion",
        "scripts.validate_evidence_resolver",
        "scripts.verify_luapula_population",
    ],
)
def test_async_scripts_normalize_render_style_database_url(monkeypatch, module_name: str):
    module = importlib.import_module(module_name)
    database_url = "postgresql://user:p%40ss@render-postgres.example/statflow?sslmode=require"
    monkeypatch.setattr(module.settings, "DATABASE_URL", database_url)
    captured = {}

    def fake_create_async_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    if module_name == "app.db.seeders.seed":
        monkeypatch.setattr(sqlalchemy_asyncio, "create_async_engine", fake_create_async_engine)
        module._make_quiet_session_factory()
    else:
        monkeypatch.setattr(module, "create_async_engine", fake_create_async_engine)
        module.create_script_engine()

    assert captured["url"] == (
        "postgresql+asyncpg://user:p%40ss@render-postgres.example/statflow?sslmode=require"
    )
