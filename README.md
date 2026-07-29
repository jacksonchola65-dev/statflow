# StatFlow

> Data for Better Decisions

StatFlow helps governments, NGOs and researchers explore development indicators — turning raw statistics into clear, actionable insights across regions and time.

---

## Technology stack

| Layer       | Technology                                      |
|-------------|-------------------------------------------------|
| Frontend    | React 19, Vite 8, Tailwind CSS v4, React Router v7, Recharts, Leaflet, Axios |
| Backend     | Python 3.12, FastAPI, Uvicorn                   |
| ORM         | SQLAlchemy 2.0 (async) + asyncpg                |
| Validation  | Pydantic v2, pydantic-settings                  |
| Migrations  | Alembic (pending initialisation)                |
| Database    | PostgreSQL                                      |
| Linting     | oxlint (frontend)                               |

---

## Directory structure

```
statflow/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app factory + lifespan
│   │   ├── api/v1/          # Versioned API routers
│   │   │   └── endpoints/   # Route handlers
│   │   ├── core/config.py   # Settings (reads from .env)
│   │   ├── db/              # SQLAlchemy engine, session, base
│   │   ├── models/          # ORM models (to be added)
│   │   └── schemas/         # Pydantic schemas (to be added)
│   ├── venv/                # Python virtual environment
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── frontend/
│   ├── src/
│   │   ├── app/router.jsx   # React Router route definitions
│   │   ├── components/      # Shared UI components
│   │   ├── pages/           # Page-level components
│   │   ├── services/api.js  # Axios client + API calls
│   │   ├── App.jsx          # Root component (BrowserRouter)
│   │   ├── index.css        # Tailwind CSS v4 entry
│   │   └── main.jsx         # React DOM entry point
│   ├── public/
│   ├── package.json
│   └── vite.config.js       # Vite config + /api dev proxy
├── docs/
├── .gitignore
└── README.md
```

---

## Local setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL running locally

### Backend

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
# Edit .env — set DATABASE_URL to your local Postgres instance
```

### Seed the database

After running Alembic migrations, seed reference data and the initial admin user:

```bash
cd backend
venv\Scripts\activate

# Seed reference data (provinces, districts, categories, indicators, datasets)
python -m app.db.seeders.seed

# Seed the initial admin user (reads ADMIN_EMAIL / ADMIN_PASSWORD from .env)
python -m app.db.seeders.users
```

Both seed commands are idempotent — safe to run multiple times.


### Frontend

```bash
cd frontend
npm install
```

---

## Running the applications

### Backend (terminal 1)

```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Endpoints:
- `GET  http://localhost:8000/api/v1/health`
- `GET  http://localhost:8000/api/v1/docs`   (Swagger UI)
- `GET  http://localhost:8000/api/v1/redoc`

### Frontend (terminal 2)

```bash
cd frontend
npm run dev
```

App: `http://localhost:5173`

The Vite dev server proxies all `/api/*` requests to `http://localhost:8000`, so no CORS issues during development.

---

## Notes

- The backend will log a warning on startup if the database is not reachable, but it will not crash — the health endpoint will still respond.
- Alembic migrations have not been initialised yet. No database tables exist.
- Docker support is planned but not yet added.
