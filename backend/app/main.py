import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.error_tracking import capture_unexpected_exception, initialize_error_tracking
from app.core.metrics import (
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS,
    route_template,
)
from app.db.session import get_engine
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("statflow.api")


class StructuredLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredLogFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))


configure_logging()
initialize_error_tracking(
    settings.SENTRY_DSN,
    settings.SENTRY_ENVIRONMENT or settings.ENVIRONMENT,
    settings.SENTRY_RELEASE,
)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting %s [%s]", settings.APP_NAME, settings.ENVIRONMENT)
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            await conn.run_sync(lambda _: None)
        logger.info("Database connection verified.")
    except Exception:  # pragma: no cover
        logger.warning("Database connectivity check failed during startup")

    yield

    logger.info("Shutting down %s", settings.APP_NAME)
    await engine.dispose()
    logger.info("Database engine disposed.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        redoc_url=f"{settings.API_V1_PREFIX}/redoc",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get(settings.REQUEST_ID_HEADER, str(uuid.uuid4()))
        request.state.request_id = request_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            excluded_error_paths = {
                "/metrics",
                f"{settings.API_V1_PREFIX}/health",
                f"{settings.API_V1_PREFIX}/ready",
            }
            if request.url.path not in excluded_error_paths:
                capture_unexpected_exception(exc, request_id)
            logger.exception(
                "Unhandled request exception",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id},
                headers={settings.REQUEST_ID_HEADER: request_id},
            )

        response.headers[settings.REQUEST_ID_HEADER] = request_id
        duration_seconds = time.perf_counter() - start
        duration_ms = round(duration_seconds * 1000, 2)
        try:
            route = route_template(request)
            HTTP_REQUESTS.labels(
                method=request.method,
                route=route,
                status_code=str(response.status_code),
            ).inc()
            HTTP_REQUEST_DURATION.labels(
                method=request.method,
                route=route,
            ).observe(duration_seconds)
        except Exception:  # pragma: no cover
            logger.exception("HTTP metrics instrumentation failed")
        logger.info(
            "HTTP request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.exception(
            "Unhandled server error",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
            headers={settings.REQUEST_ID_HEADER: request_id},
        )

    @app.exception_handler(FastAPIHTTPException)
    async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        headers = dict(exc.headers or {})
        headers[settings.REQUEST_ID_HEADER] = request_id
        response = JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=headers,
        )
        return response

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
