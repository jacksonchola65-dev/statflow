"""
tests/test_province_name_to_code.py
=====================================
Focused tests for MappingExecutionService._province_name_to_code()
and _apply_transformation_async() with province_name_to_code operation.

Uses the real test database (provinces are seeded by conftest.py).

Province data seeded by setup_test_database (from provinces.py):
  CP  Central
  CB  Copperbelt
  EA  Eastern
  LP  Luapula
  LK  Lusaka
  MU  Muchinga
  NW  North-Western
  NR  Northern
  SO  Southern
  WE  Western
"""

from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

from app.schemas.ingestion_mapping import TransformationOperation
from app.services.mapping_execution_service import (
    MappingExecutionService,
    TransformationExecutionError,
    UnsupportedTransformationError,
)

OP = TransformationOperation.PROVINCE_NAME_TO_CODE


# ---------------------------------------------------------------------------
# province_name_to_code — integration tests (real DB)
# ---------------------------------------------------------------------------


async def test_exact_province_name_returns_code(db_session):
    """Exact match of a seeded province name → returns its code."""
    svc = MappingExecutionService(session=db_session)
    assert await svc._province_name_to_code("Lusaka") == "LK"


async def test_lowercase_province_name_matches(db_session):
    """All-lowercase input matches case-insensitively."""
    svc = MappingExecutionService(session=db_session)
    assert await svc._province_name_to_code("lusaka") == "LK"


async def test_uppercase_province_name_matches(db_session):
    """All-uppercase input matches case-insensitively."""
    svc = MappingExecutionService(session=db_session)
    assert await svc._province_name_to_code("LUSAKA") == "LK"


async def test_mixed_case_province_name_matches(db_session):
    svc = MappingExecutionService(session=db_session)
    assert await svc._province_name_to_code("LuSaKa") == "LK"


async def test_surrounding_whitespace_is_ignored(db_session):
    svc = MappingExecutionService(session=db_session)
    assert await svc._province_name_to_code("  Lusaka  ") == "LK"


async def test_all_ten_provinces_resolve(db_session):
    """Every seeded province name resolves to a code."""
    expected = {
        "Central": "CP",
        "Copperbelt": "CB",
        "Eastern": "EA",
        "Luapula": "LP",
        "Lusaka": "LK",
        "Muchinga": "MU",
        "North-Western": "NW",
        "Northern": "NR",
        "Southern": "SO",
        "Western": "WE",
    }
    svc = MappingExecutionService(session=db_session)
    for name, expected_code in expected.items():
        code = await svc._province_name_to_code(name)
        assert code == expected_code, f"Expected {name!r} → {expected_code!r}, got {code!r}"


async def test_null_returns_none(db_session):
    """None input returns None — no DB call needed."""
    svc = MappingExecutionService(session=db_session)
    result = await svc._province_name_to_code(None)
    assert result is None


async def test_empty_string_raises(db_session):
    svc = MappingExecutionService(session=db_session)
    with pytest.raises(TransformationExecutionError) as exc_info:
        await svc._province_name_to_code("")
    assert exc_info.value.operation == "province_name_to_code"


async def test_whitespace_only_string_raises(db_session):
    svc = MappingExecutionService(session=db_session)
    with pytest.raises(TransformationExecutionError):
        await svc._province_name_to_code("   ")


async def test_unknown_province_raises(db_session):
    svc = MappingExecutionService(session=db_session)
    with pytest.raises(TransformationExecutionError) as exc_info:
        await svc._province_name_to_code("Atlantis")
    assert "Atlantis" in str(exc_info.value)
    assert exc_info.value.operation == "province_name_to_code"


async def test_integer_input_raises(db_session):
    svc = MappingExecutionService(session=db_session)
    with pytest.raises(TransformationExecutionError):
        await svc._province_name_to_code(42)


async def test_boolean_input_raises(db_session):
    svc = MappingExecutionService(session=db_session)
    with pytest.raises(TransformationExecutionError):
        await svc._province_name_to_code(True)


async def test_float_input_raises(db_session):
    svc = MappingExecutionService(session=db_session)
    with pytest.raises(TransformationExecutionError):
        await svc._province_name_to_code(3.14)


async def test_decimal_input_raises(db_session):
    svc = MappingExecutionService(session=db_session)
    with pytest.raises(TransformationExecutionError):
        await svc._province_name_to_code(Decimal("1.5"))


# ---------------------------------------------------------------------------
# _apply_transformation_async — delegates province_name_to_code to DB method
# ---------------------------------------------------------------------------


async def test_apply_transformation_async_province_name_to_code(db_session):
    """_apply_transformation_async routes province_name_to_code through DB."""
    svc = MappingExecutionService(session=db_session)
    result = await svc._apply_transformation_async(OP, "Lusaka")
    assert result == "LK"


async def test_apply_transformation_async_delegates_pure_ops(db_session):
    """Pure operations are delegated to the synchronous static method."""
    svc = MappingExecutionService(session=db_session)
    result = await svc._apply_transformation_async(TransformationOperation.UPPERCASE, "lusaka")
    assert result == "LUSAKA"


# ---------------------------------------------------------------------------
# DB failure simulation — uses a mock session
# ---------------------------------------------------------------------------


async def test_database_query_failure_raises_cleanly():
    """If the DB raises an exception, it propagates (not silently swallowed)."""
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(side_effect=RuntimeError("DB connection lost"))

    svc = MappingExecutionService(session=mock_session)
    with pytest.raises(RuntimeError, match="DB connection lost"):
        await svc._province_name_to_code("Lusaka")


# ---------------------------------------------------------------------------
# Ambiguous-match guard (mocked — unique constraint prevents real ambiguity)
# ---------------------------------------------------------------------------


async def test_ambiguous_match_raises():
    """Two provinces with the same name (impossible in prod) → clear error."""
    from unittest.mock import AsyncMock, MagicMock

    from app.models.province import Province

    mock_prov_a = MagicMock(spec=Province)
    mock_prov_a.code = "AA"
    mock_prov_b = MagicMock(spec=Province)
    mock_prov_b.code = "BB"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_prov_a, mock_prov_b]

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    svc = MappingExecutionService(session=mock_session)
    with pytest.raises(TransformationExecutionError) as exc_info:
        await svc._province_name_to_code("Duplicate Province")
    assert "Ambiguous" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Regression — static _apply_transformation still raises for province_name_to_code
# ---------------------------------------------------------------------------


def test_static_apply_transformation_raises_for_province_name_to_code():
    """
    The synchronous static method must still raise UnsupportedTransformationError
    for province_name_to_code, directing callers to use _apply_transformation_async.
    """
    with pytest.raises(UnsupportedTransformationError) as exc_info:
        MappingExecutionService._apply_transformation(OP, "Lusaka")
    assert "province_name_to_code" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Regression — all pure transformations still work after async refactor
# ---------------------------------------------------------------------------


def test_trim_regression():
    assert (
        MappingExecutionService._apply_transformation(TransformationOperation.TRIM, "  hi  ")
        == "hi"
    )


def test_uppercase_regression():
    assert (
        MappingExecutionService._apply_transformation(TransformationOperation.UPPERCASE, "lusaka")
        == "LUSAKA"
    )


def test_lowercase_regression():
    assert (
        MappingExecutionService._apply_transformation(TransformationOperation.LOWERCASE, "LUSAKA")
        == "lusaka"
    )


def test_parse_number_regression():
    assert MappingExecutionService._apply_transformation(
        TransformationOperation.PARSE_NUMBER, "42.5"
    ) == Decimal("42.5")


def test_extract_year_regression():
    assert (
        MappingExecutionService._apply_transformation(
            TransformationOperation.EXTRACT_YEAR, "2024-06-15"
        )
        == 2024
    )
