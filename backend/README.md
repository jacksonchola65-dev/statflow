# StatFlow — Backend

FastAPI backend for the StatFlow platform.

## Stack

| Layer        | Library                        |
|--------------|--------------------------------|
| Framework    | FastAPI 0.139                  |
| ASGI server  | Uvicorn                        |
| ORM          | SQLAlchemy 2.0 (async)         |
| Driver       | asyncpg (async), psycopg2 (sync/Alembic) |
| Validation   | Pydantic v2 + pydantic-settings |
| Migrations   | Alembic (not yet initialised)  |
| Database     | PostgreSQL                     |

## Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env with your database credentials
```

## Running the development server

```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:

- Base URL: `http://localhost:8000`
- Health:   `GET  http://localhost:8000/api/v1/health`
- Swagger:  `http://localhost:8000/api/v1/docs`
- ReDoc:    `http://localhost:8000/api/v1/redoc`

## Running the production container

The production image starts Uvicorn with `--workers 1` and accepts the
platform-provided `PORT` (defaulting to `8000`). This is intentional because
ingestion preview/session state is currently process-local. Increase the
worker count only after that state is shared through PostgreSQL/Redis or the
workflow is redesigned to be stateless.

The application container does not run migrations at startup. Run migrations
as a separate release operation with `python -m alembic upgrade head`.

For the temporary Render pilot, [render.yaml](../render.yaml) provides the
portable service declaration. Set the generated Web Service URL in the
frontend `VITE_API_BASE_URL`, then set the exact Static Site origin in backend
`CORS_ORIGINS` and the generated backend hostname in `TRUSTED_HOSTS`.

Pilot release order is: provision PostgreSQL, inject secrets and configuration,
run migrations, run `python -m app.db.seeders.reference`, execute the controlled Luapula import, run the read-only
evidence verifier, start and verify the backend, deploy the frontend, then run
HTTPS authentication, CSRF, health, readiness, and Decision Intelligence
smoke tests. Render's generated frontend and backend hostnames are different,
 so `COOKIE_SAMESITE=lax` with `COOKIE_SECURE=true` remains appropriate. If a future custom-domain layout is
 genuinely cross-site, set `COOKIE_SAMESITE=none` with `COOKIE_SECURE=true`; CSRF validation remains mandatory in either case.

## Configuration and secrets

Settings are injected through environment variables, which keeps the backend
portable across local containers, CI, and hosting providers. Do not put real
database URLs, JWT secrets, admin passwords, Sentry DSNs, or credentials in
the repository. Production and staging require explicit PostgreSQL URLs,
unique JWT/admin secrets, `COOKIE_SECURE=true`, explicit trusted hosts, and
HTTPS CORS origins. The same-origin production target is
`https://app.statflow.example`; staging must use its own origin, database,
JWT secret, admin credentials, and cookie names.

Supported environments are `development`, `test`, `staging`, and `production`.
Staging and production fail during settings initialization when required
security configuration is missing or unsafe. `TRUSTED_HOSTS` is prepared for
the later trusted-host middleware milestone and is not inferred from request
headers.

## Database seeding

### Seed reference data (provinces, districts, categories, indicators, datasets)

```bash
cd backend
venv\Scripts\activate
python -m app.db.seeders.seed
```

### Seed the initial admin user

```bash
cd backend
venv\Scripts\activate
python -m app.db.seeders.users
```

The script reads `ADMIN_EMAIL` and `ADMIN_PASSWORD` from your `.env` file
(defaults: `admin@statflow.test` / `ChangeMe123!`).

The seeder is **idempotent** — running it a second time does nothing if the
admin account already exists.  No duplicate users are ever created.

> **Production note**: set strong values for `ADMIN_EMAIL` and `ADMIN_PASSWORD`
> in your environment or secrets manager before running the seed command in any
> non-development environment.

## Project structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app factory and lifespan handler
│   ├── api/
│   │   └── v1/
│   │       ├── api.py       # Aggregates all v1 routers
│   │       └── endpoints/
│   │           └── health.py
│   ├── core/
│   │   └── config.py        # Pydantic Settings — reads from .env
│   ├── db/
│   │   ├── base.py          # SQLAlchemy DeclarativeBase
│   │   └── session.py       # Async engine, session factory, get_db dependency
│   ├── models/              # SQLAlchemy ORM models (to be added)
│   └── schemas/             # Pydantic request/response schemas (to be added)
├── requirements.txt
├── .env.example
└── README.md
```
