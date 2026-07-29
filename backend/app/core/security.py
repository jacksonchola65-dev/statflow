"""
core/security.py — Password hashing and JWT utilities for StatFlow.

Security constraints enforced here:
- Plaintext passwords are never logged or returned.
- JWT algorithm is always read from settings, never from the token header.
- Token expiry is always verified; it cannot be disabled from call sites.
- No refresh tokens, cookies, CSRF handling, or endpoint logic lives here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings
from app.models.user import UserRole

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

# Build the PasswordHash instance with Argon2id as the only hasher.
# pwdlib uses Argon2id by default via Argon2Hasher, which is the
# memory-hard, side-channel-resistant variant recommended by OWASP.
# The structure is compatible with pwdlib's check_needs_rehash() for
# future parameter upgrades without breaking existing stored hashes.
_password_hash = PasswordHash([Argon2Hasher()])


def hash_password(password: str) -> str:
    """Hash *password* with Argon2id and return the encoded hash string.

    Raises:
        ValueError: If *password* is an empty string.
    """
    if not password:
        raise ValueError("Password must not be empty.")
    # Plaintext is handed directly to pwdlib; it is never stored or logged.
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Return True if *password* matches *hashed_password*, False otherwise.

    A malformed or unrecognised hash format returns False instead of raising,
    so callers never need to catch library-specific exceptions.
    """
    try:
        return _password_hash.verify(password, hashed_password)
    except Exception:  # noqa: BLE001
        # Any verification error (bad format, unsupported algorithm, …)
        # is treated as a non-match. Plaintext is never surfaced.
        return False


# ---------------------------------------------------------------------------
# JWT typed result and exception
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccessTokenPayload:
    """Validated, typed JWT access-token payload returned by decode_access_token."""

    sub: uuid.UUID    # user UUID
    role: UserRole
    exp: datetime
    iat: datetime
    jti: uuid.UUID    # unique token ID — enables future revocation list


class InvalidTokenError(Exception):
    """Raised for any invalid, expired, malformed, or incomplete JWT."""


# ---------------------------------------------------------------------------
# JWT creation and validation
# ---------------------------------------------------------------------------


def create_access_token(
    user_id: uuid.UUID,
    role: UserRole | str,
    email: str = "",
) -> str:
    """Sign and return a JWT access token for *user_id* with the given *role*.

    Claims included:
        sub   — str(user_id)
        email — user's email address (REQ-4.3)
        role  — UserRole value string (informational; authorization uses DB role)
        exp   — UTC expiry (now + ACCESS_TOKEN_EXPIRE_MINUTES)
        iat   — UTC issued-at
        jti   — random UUID (unique token ID)
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    role_value = role.value if isinstance(role, UserRole) else str(role)

    payload: dict = {
        "sub": str(user_id),
        "email": email,
        "role": role_value,
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
    }

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> AccessTokenPayload:
    """Decode and validate *token*; return a typed AccessTokenPayload.

    Validation performed (raises InvalidTokenError on any failure):
        - Signature valid (HMAC with settings.JWT_SECRET_KEY)
        - Token not expired (exp claim checked — cannot be disabled)
        - sub present and parseable as UUID
        - exp present
        - iat present
        - jti present and parseable as UUID
        - role present and a valid UserRole value

    Algorithm is always taken from settings (never from the token header) to
    prevent algorithm-confusion attacks.

    PyJWT exceptions are caught and re-raised as InvalidTokenError so callers
    receive a single, stable exception type without leaking library internals.
    """
    try:
        raw: dict = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],  # never trust token header
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("Token validation failed.") from exc

    # --- sub ---
    raw_sub = raw.get("sub")
    if not raw_sub:
        raise InvalidTokenError("Missing 'sub' claim.")
    try:
        sub_uuid = uuid.UUID(str(raw_sub))
    except (ValueError, AttributeError) as exc:
        raise InvalidTokenError("'sub' is not a valid UUID.") from exc

    # --- exp ---
    if raw.get("exp") is None:
        raise InvalidTokenError("Missing 'exp' claim.")
    # PyJWT already decoded exp to a datetime or int; normalise to aware datetime.
    raw_exp = raw["exp"]
    if isinstance(raw_exp, datetime):
        exp_dt = raw_exp if raw_exp.tzinfo else raw_exp.replace(tzinfo=timezone.utc)
    else:
        exp_dt = datetime.fromtimestamp(int(raw_exp), tz=timezone.utc)

    # --- iat ---
    if raw.get("iat") is None:
        raise InvalidTokenError("Missing 'iat' claim.")
    raw_iat = raw["iat"]
    if isinstance(raw_iat, datetime):
        iat_dt = raw_iat if raw_iat.tzinfo else raw_iat.replace(tzinfo=timezone.utc)
    else:
        iat_dt = datetime.fromtimestamp(int(raw_iat), tz=timezone.utc)

    # --- jti ---
    raw_jti = raw.get("jti")
    if not raw_jti:
        raise InvalidTokenError("Missing 'jti' claim.")
    try:
        jti_uuid = uuid.UUID(str(raw_jti))
    except (ValueError, AttributeError) as exc:
        raise InvalidTokenError("'jti' is not a valid UUID.") from exc

    # --- role ---
    raw_role = raw.get("role")
    if not raw_role:
        raise InvalidTokenError("Missing 'role' claim.")
    try:
        role_enum = UserRole(raw_role)
    except ValueError as exc:
        raise InvalidTokenError(f"'role' value '{raw_role}' is not a valid UserRole.") from exc

    return AccessTokenPayload(
        sub=sub_uuid,
        role=role_enum,
        exp=exp_dt,
        iat=iat_dt,
        jti=jti_uuid,
    )
