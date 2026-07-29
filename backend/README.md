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
