from app.core.config import settings
from sqlalchemy import create_engine, text
import sys

print('Using DATABASE_URL:', getattr(settings, 'DATABASE_URL', None))
try:
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        r = conn.execute(text('select 1')).scalar()
    print('DB test query result:', r)
    sys.exit(0)
except Exception as e:
    print('DB connection failed:', type(e).__name__, str(e))
    sys.exit(2)
