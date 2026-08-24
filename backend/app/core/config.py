from typing import Literal
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/statflow"


def normalize_async_database_url(database_url: str) -> str:
    """Return a PostgreSQL URL using SQLAlchemy's asyncpg driver."""
    database_url = database_url.strip()
    if database_url.startswith("postgres://"):
        return "postgresql+asyncpg://" + database_url[len("postgres://") :]
    if database_url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + database_url[len("postgresql://") :]
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    raise ValueError("DATABASE_URL must use a PostgreSQL URL scheme.")


def normalize_sync_database_url(database_url: str) -> str:
    """Return a PostgreSQL URL using SQLAlchemy's synchronous psycopg2 driver."""
    async_url = normalize_async_database_url(database_url)
    return "postgresql+psycopg2://" + async_url[len("postgresql+asyncpg://") :]


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "StatFlow API"
    ENVIRONMENT: Literal["development", "test", "staging", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str | None = None
    SENTRY_ENVIRONMENT: str | None = None
    SENTRY_RELEASE: str | None = None

    # API
    API_V1_PREFIX: str = "/api/v1"
    REQUEST_ID_HEADER: str = "X-Request-ID"

    # Database
    DATABASE_URL: str = _DEFAULT_DATABASE_URL

    # Database pool settings — tuned for bounded production connections.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Test database (used only by pytest — never loaded in production)
    TEST_DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/statflow_test"

    # CORS — comma-separated list of allowed origins
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    TRUSTED_HOSTS: list[str] = ["localhost", "127.0.0.1", "testserver"]

    # ── JWT / Auth ─────────────────────────────────────────────────────────────

    # Secret key used to sign JWT access tokens.
    # Development default is a placeholder — NEVER use this in production.
    # Generate a production value with: openssl rand -hex 32
    JWT_SECRET_KEY: str = "dev-only-secret-change-me-in-production"

    # Algorithm used to sign JWTs. HS256 is the standard symmetric-key choice.
    JWT_ALGORITHM: str = "HS256"

    # Lifetime of an access token in minutes. 60 minutes is a reasonable default
    # for an internal application; reduce for higher-security deployments.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── Cookie / CSRF (prepared for httpOnly-cookie auth if adopted later) ─────

    # Whether to set the Secure flag on auth cookies.
    # Must be True in production (HTTPS only); False is acceptable for local HTTP.
    COOKIE_SECURE: bool = False

    # SameSite policy for auth cookies.
    # "lax" prevents CSRF on top-level navigation while allowing normal use.
    # Set to "strict" for maximum protection, "none" only when cross-site is required.
    COOKIE_SAMESITE: str = "lax"

    # Name of the CSRF cookie sent to the browser.
    CSRF_COOKIE_NAME: str = "statflow_csrf"

    # Name of the request header the client must reflect back to pass CSRF checks.
    CSRF_HEADER_NAME: str = "X-CSRF-Token"

    # Name of the HttpOnly cookie that carries the JWT access token.
    # Must match the cookie name set by the login endpoint.
    AUTH_COOKIE_NAME: str = "statflow_access"

    # ── Admin seed ────────────────────────────────────────────────────────────

    # Email address of the initial admin user created by the seed script.
    # Defaults to a recognisable development-only address that is valid under
    # standard email validation rules.
    ADMIN_EMAIL: str = "admin@statflow.test"

    # Plaintext password for the initial admin user.
    # PRODUCTION: set a strong value in your .env file or secrets manager.
    # The seed script hashes this before storing it — it is never persisted as
    # plaintext.
    ADMIN_PASSWORD: str = "ChangeMe123!"

    # ── Ingestion limits ───────────────────────────────────────────────────────

    # Maximum file size in bytes accepted by the ingestion endpoint.
    # Measured against the raw byte length of the upload before any parsing.
    # Default: 10 MB.
    INGESTION_MAX_FILE_BYTES: int = 10 * 1024 * 1024  # 10 MB

    # Maximum number of data rows (excluding the header row) allowed per file.
    # Checked after the file is parsed and the header is identified.
    INGESTION_MAX_ROWS: int = 100_000

    # Maximum number of columns allowed per file.
    # Checked immediately after the header row is parsed.
    INGESTION_MAX_COLUMNS: int = 500

    # Optional official ZAMSTATS dataset URL used by the source-specific importer.
    # Leave unset unless a machine-readable official download URL has been confirmed.
    ZAMSTATS_DATASET_URL: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        hide_input_in_errors=True,
    )

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if self.ENVIRONMENT in {"staging", "production"}:
            database_url = self.DATABASE_URL.strip()
            database_host = urlsplit(database_url).hostname
            if (
                not database_url
                or database_url == _DEFAULT_DATABASE_URL
                or database_host in {"localhost", "127.0.0.1", "::1"}
            ):
                raise ValueError("DATABASE_URL must be an explicit PostgreSQL async URL.")
            try:
                normalize_async_database_url(database_url)
            except ValueError as exc:
                raise ValueError("DATABASE_URL must be an explicit PostgreSQL async URL.") from exc

            secret = self.JWT_SECRET_KEY.strip().casefold()
            placeholders = {
                "change-me",
                "change_me",
                "secret",
                "your-secret-key",
                "development-secret",
                "example",
                "dev-only-secret-change-me-in-production",
            }
            if (
                not secret
                or secret in placeholders
                or len(self.JWT_SECRET_KEY.encode("utf-8")) < 32
            ):
                raise ValueError("JWT_SECRET_KEY must be a unique secret of at least 32 bytes.")

            admin_pw = self.ADMIN_PASSWORD or ""
            if not admin_pw.strip() or admin_pw.casefold() in {
                "changeme123!",
                "change-me",
                "password",
                "example",
            }:
                raise ValueError("ADMIN_PASSWORD must be a unique bootstrap credential.")

            if not self.COOKIE_SECURE:
                raise ValueError("COOKIE_SECURE must be true in staging and production.")

            for origin in self.CORS_ORIGINS:
                parsed_origin = urlsplit(origin.strip())
                if parsed_origin.hostname in {"localhost", "127.0.0.1"} or origin.strip() == "*":
                    raise ValueError(
                        "CORS_ORIGINS must not include loopback or wildcard origins "
                        "in non-development environments."
                    )

            if (
                not self.TRUSTED_HOSTS
                or "*" in self.TRUSTED_HOSTS
                or any(
                    host.strip().lower() in {"localhost", "127.0.0.1"}
                    for host in self.TRUSTED_HOSTS
                )
            ):
                raise ValueError("TRUSTED_HOSTS must contain explicit non-loopback hosts.")

        if self.COOKIE_SAMESITE not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be one of: lax, strict, none.")
        if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be true when COOKIE_SAMESITE is none.")

        # ── Database pool settings (all environments) ──────────────────────
        if self.DB_POOL_SIZE < 0:
            raise ValueError(
                f"DB_POOL_SIZE must be a non-negative integer; got {self.DB_POOL_SIZE}."
            )
        if self.DB_MAX_OVERFLOW < 0:
            raise ValueError(
                f"DB_MAX_OVERFLOW must be a non-negative integer; got {self.DB_MAX_OVERFLOW}."
            )
        if self.DB_POOL_TIMEOUT <= 0:
            raise ValueError(
                f"DB_POOL_TIMEOUT must be a positive integer; got {self.DB_POOL_TIMEOUT}."
            )
        if self.DB_POOL_RECYCLE <= 0:
            raise ValueError(
                f"DB_POOL_RECYCLE must be a positive integer; got {self.DB_POOL_RECYCLE}."
            )

        # ── Ingestion limits (all environments) ────────────────────────────
        if self.INGESTION_MAX_FILE_BYTES <= 0:
            raise ValueError(
                f"INGESTION_MAX_FILE_BYTES must be a positive integer; "
                f"got {self.INGESTION_MAX_FILE_BYTES}."
            )
        if self.INGESTION_MAX_ROWS <= 0:
            raise ValueError(
                f"INGESTION_MAX_ROWS must be a positive integer; got {self.INGESTION_MAX_ROWS}."
            )
        if self.INGESTION_MAX_COLUMNS <= 0:
            raise ValueError(
                f"INGESTION_MAX_COLUMNS must be a positive integer; "
                f"got {self.INGESTION_MAX_COLUMNS}."
            )

        return self


settings = Settings()
