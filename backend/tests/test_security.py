"""
Tests for app.core.security — password hashing and JWT utilities.

All functions under test are synchronous; no pytest-asyncio needed.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    AccessTokenPayload,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.user import UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_UUID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
_ROLE = UserRole.ADMIN


def _build_raw_token(payload: dict) -> str:
    """Encode a raw JWT without going through create_access_token."""
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _valid_payload(**overrides) -> dict:
    """Return a minimal valid raw payload, with optional field overrides."""
    now = datetime.now(timezone.utc)
    base = {
        "sub": str(_SAMPLE_UUID),
        "exp": now + timedelta(minutes=60),
        "iat": now,
        "jti": str(uuid.uuid4()),
        "role": UserRole.ADMIN.value,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Password hashing tests
# ---------------------------------------------------------------------------


def test_hash_differs_from_plaintext():
    """The stored hash must never equal the plaintext password."""
    assert hash_password("secret") != "secret"


def test_correct_password_verifies():
    """verify_password returns True when the password matches the stored hash."""
    hashed = hash_password("secret")
    assert verify_password("secret", hashed) is True


def test_wrong_password_fails():
    """verify_password returns False when the password does not match."""
    hashed = hash_password("secret")
    assert verify_password("wrong", hashed) is False


def test_malformed_hash_returns_false():
    """A malformed stored hash must return False, never raise."""
    result = verify_password("secret", "not-a-valid-hash")
    assert result is False


def test_empty_password_raises():
    """hash_password must raise ValueError for an empty string."""
    with pytest.raises(ValueError, match="Password must not be empty"):
        hash_password("")


# ---------------------------------------------------------------------------
# JWT creation tests
# ---------------------------------------------------------------------------


def test_token_contains_all_required_claims():
    """The raw token payload must include sub, email, role, exp, iat, and jti (REQ-4.3)."""
    token = create_access_token(_SAMPLE_UUID, _ROLE, email="admin@statflow.zm")
    # Decode without verification to inspect raw claims
    raw = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    for claim in ("sub", "email", "role", "exp", "iat", "jti"):
        assert claim in raw, f"Expected claim '{claim}' missing from token payload"
    assert raw["email"] == "admin@statflow.zm"


def test_token_round_trip():
    """decode_access_token on a freshly created token returns a matching AccessTokenPayload."""
    token = create_access_token(_SAMPLE_UUID, _ROLE)
    payload = decode_access_token(token)

    assert isinstance(payload, AccessTokenPayload)
    assert payload.sub == _SAMPLE_UUID
    assert payload.role == _ROLE


# ---------------------------------------------------------------------------
# JWT validation tests — all use raw jwt.encode to construct edge-case tokens
# ---------------------------------------------------------------------------


def test_expired_token_raises():
    """A token with exp in the past must raise InvalidTokenError."""
    now = datetime.now(timezone.utc)
    expired_payload = _valid_payload(
        exp=now - timedelta(seconds=1),
        iat=now - timedelta(hours=1),
    )
    token = _build_raw_token(expired_payload)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_tampered_signature_raises():
    """Flipping a character in the signature segment must raise InvalidTokenError."""
    token = create_access_token(_SAMPLE_UUID, _ROLE)
    parts = token.split(".")
    # Mutate the signature (last segment)
    sig = parts[2]
    # Flip the first character: 'A'→'B', anything else → 'A'
    tampered_sig = ("B" if sig[0] == "A" else "A") + sig[1:]
    tampered_token = ".".join([parts[0], parts[1], tampered_sig])

    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered_token)


def test_missing_required_claim_raises():
    """A JWT built without jti must raise InvalidTokenError."""
    payload = _valid_payload()
    del payload["jti"]
    token = _build_raw_token(payload)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_invalid_sub_uuid_raises():
    """A JWT with sub='not-a-uuid' must raise InvalidTokenError."""
    token = _build_raw_token(_valid_payload(sub="not-a-uuid"))

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_invalid_jti_uuid_raises():
    """A JWT with jti='not-a-uuid' must raise InvalidTokenError."""
    token = _build_raw_token(_valid_payload(jti="not-a-uuid"))

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_invalid_role_raises():
    """A JWT with an unrecognised role value must raise InvalidTokenError."""
    token = _build_raw_token(_valid_payload(role="SUPERUSER"))

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)
