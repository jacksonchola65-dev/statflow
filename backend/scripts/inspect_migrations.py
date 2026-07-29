import sys
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Ensure project root is on sys.path so `app` package imports work when
# running this script from the scripts/ directory.
proj_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(proj_root))

from app.core.config import settings

async def main():
    engine = create_async_engine(settings.TEST_DATABASE_URL, future=True)
    async with engine.connect() as conn:
        # check tables
        res = await conn.execute(text("SELECT to_regclass('public.dashboards') as dashboards, to_regclass('public.dashboard_cards') as dashboard_cards"))
        row = res.first()
        print('dashboards_table_exists', bool(row.dashboards))
        print('dashboard_cards_table_exists', bool(row.dashboard_cards))

        # check foreign keys linking dashboard_cards.dashboard_id -> dashboards.id
        fk_q = text("SELECT conname, confrelid::regclass::text AS referenced_table, conrelid::regclass::text AS table_name, pg_get_constraintdef(oid) AS def FROM pg_constraint WHERE contype='f' AND conrelid IN (SELECT oid FROM pg_class WHERE relname IN ('dashboard_cards'))")
        fk_res = await conn.execute(fk_q)
        fks = fk_res.fetchall()
        print('fks_count', len(fks))
        for fk in fks:
            # fk tuple: (conname, referenced_table, table_name, def)
            print('fk', fk[0], fk[2], fk[1], fk[3])

        # check cascade on delete in fk defs
        cascade = any('ON DELETE CASCADE' in fk[3].upper() for fk in fks)
        print('cascade_delete_configured', cascade)

        # check indexes
        idx_q = text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename IN ('dashboards','dashboard_cards')")
        idx_res = await conn.execute(idx_q)
        idxs = idx_res.fetchall()
        print('indexes_count', len(idxs))
        for idx in idxs:
            print('index', idx.indexname, idx.indexdef)

    await engine.dispose()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
