import sys
from urllib.parse import urlparse

from app.core.config import settings
from sqlalchemy import create_engine, text

parsed = urlparse(settings.DATABASE_URL)
host = parsed.hostname or "unknown-host"
database_name = parsed.path.lstrip("/") or "unknown-database"
print(f"Testing database connectivity for host={host}, database={database_name}")
try:
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        r = conn.execute(text("select 1")).scalar()
    print(f"Database connectivity OK: host={host}, database={database_name}, result={r}")
    sys.exit(0)
except Exception as e:
    print(
        f"Database connectivity failed: {type(e).__name__} for host={host}, database={database_name}"
    )
    sys.exit(2)
