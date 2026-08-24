FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app/backend

COPY backend/requirements-prod.txt ./requirements-prod.txt
RUN python -m pip install --no-cache-dir -r requirements-prod.txt

COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations
COPY backend/app ./app

RUN groupadd --system --gid 10001 statflow \
    && useradd --system --uid 10001 --gid statflow \
        --home-dir /nonexistent --shell /usr/sbin/nologin statflow

USER statflow

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD-SHELL python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/api/v1/health', timeout=3)"

# Preview/session state is process-local, so production intentionally runs one worker.
# Increase workers only after that state is shared (PostgreSQL/Redis) or stateless.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
