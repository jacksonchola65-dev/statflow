import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def main():
    url = settings.DATABASE_URL
    print('DATABASE_URL=', url)
    engine = create_async_engine(url, future=True, pool_pre_ping=True)
    async with engine.connect() as conn:
        tables = await conn.execute(text("select table_name from information_schema.tables where table_schema='public' order by table_name"))
        tables = [row[0] for row in tables.fetchall()]
        print('Tables:', ', '.join(tables))
        print('=== table row counts ===')
        for name in tables:
            try:
                cnt = await conn.execute(text(f'select count(*) from {name}'))
                print(f'{name}:', cnt.scalar())
            except Exception as e:
                print(f'{name}: count failed:', type(e).__name__, e)
        print('=== alembic_version ===')
        try:
            version = await conn.execute(text('select version_num from alembic_version'))
            print([row[0] for row in version.fetchall()])
        except Exception as e:
            print('alembic_version error:', type(e).__name__, e)
        for query, label in [
            ('select id, status, created_at, completed_at from ingestion_jobs order by created_at desc limit 5', 'ingestion_jobs sample'),
            ('select id, ingestion_job_id, dataset_name, status, created_at from datasets order by created_at desc limit 10', 'datasets sample'),
            ('select id, ingestion_job_id, values from dataset_rows order by id desc limit 5', 'dataset_rows sample'),
        ]:
            print('===', label, '===')
            try:
                result = await conn.execute(text(query))
                for row in result.fetchall():
                    print(row)
            except Exception as e:
                print(label, 'failed:', type(e).__name__, e)
    await engine.dispose()

asyncio.run(main())
