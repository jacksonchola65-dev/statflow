import pytest
from app.core.config import normalize_async_database_url, normalize_sync_database_url


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("postgresql://user:pass@db.example/app", "postgresql+asyncpg://user:pass@db.example/app"),
        (
            "postgres://user:p%40ss@db.example/app?sslmode=require",
            "postgresql+asyncpg://user:p%40ss@db.example/app?sslmode=require",
        ),
        (
            "postgresql+asyncpg://user:p%40ss@db.example/app?sslmode=require",
            "postgresql+asyncpg://user:p%40ss@db.example/app?sslmode=require",
        ),
    ],
)
def test_normalize_async_database_url(value, expected):
    assert normalize_async_database_url(value) == expected


def test_normalize_sync_database_url_preserves_url_components():
    value = "postgres://user:p%40ss@db.example/app?sslmode=require"
    assert normalize_sync_database_url(value) == (
        "postgresql+psycopg2://user:p%40ss@db.example/app?sslmode=require"
    )


def test_normalize_database_url_rejects_non_postgresql():
    with pytest.raises(ValueError, match="PostgreSQL"):
        normalize_async_database_url("sqlite:///statflow.db")
