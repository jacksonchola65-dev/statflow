import logging
import re
from collections.abc import Mapping
from typing import Any, cast

import sentry_sdk
from sentry_sdk.types import Event

logger = logging.getLogger("statflow.error_tracking")

_SENSITIVE_KEY_RE = re.compile(
    r"authorization|cookie|csrf|database_url|jwt|password|secret|token|user|email",
    re.IGNORECASE,
)
_SENSITIVE_TEXT_RE = re.compile(
    r"database_url|jwt_secret_key|admin_password|authorization|set-cookie|csrf|password",
    re.IGNORECASE,
)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _sanitize_value(item)
            for key, item in value.items()
            if not _SENSITIVE_KEY_RE.search(str(key))
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_value(item) for item in value)
    if isinstance(value, str) and _SENSITIVE_TEXT_RE.search(value):
        return "[Filtered]"
    return value


def before_send(event: Event, hint: dict[str, Any]) -> Event | None:
    sanitized = _sanitize_value(event)
    if not isinstance(sanitized, dict):
        return None

    sanitized.pop("request", None)
    sanitized.pop("user", None)
    sanitized.pop("server_name", None)
    sanitized.pop("breadcrumbs", None)
    sanitized.pop("extra", None)
    if isinstance(sanitized.get("exception"), dict):
        for exception_value in sanitized["exception"].get("values", []):
            if isinstance(exception_value, dict) and "value" in exception_value:
                exception_value["value"] = "[Filtered]"
    sanitized.pop("message", None)
    return cast(Event, sanitized)


def initialize_error_tracking(
    dsn: str | None,
    environment: str,
    release: str | None,
) -> bool:
    if not dsn:
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release or None,
            send_default_pii=False,
            traces_sample_rate=0,
            default_integrations=False,
            before_send=before_send,
        )
    except Exception:
        logger.warning("Sentry error tracking initialization failed")
        return False
    return True


def capture_unexpected_exception(exc: Exception, request_id: str) -> None:
    try:
        with sentry_sdk.new_scope() as scope:
            scope.set_context("statflow", {"request_id": request_id})
            sentry_sdk.capture_exception(exc)
    except Exception:  # pragma: no cover
        logger.warning("Sentry error capture failed")
