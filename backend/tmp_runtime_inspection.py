import asyncio

from sqlalchemy import select, func

from app.db.session import engine
from app.models.user import User
from app.models.dataset import Dataset
from app.models.ingestion import IngestionJob, DatasetRow
from app.models.data_source import DatasetRegistry

async def main() -> None:
    async with engine.connect() as conn:
        users = await conn.execute(select(User.email, User.role, User.is_active).order_by(User.email))
        users = users.all()
        print('USERS_COUNT', len(users))
        for email, role, active in users:
            print('USER', email, role, active)

        datasets = await conn.execute(select(Dataset.id, Dataset.name, Dataset.source_name, Dataset.source_url, Dataset.is_published).order_by(Dataset.name))
        datasets = datasets.all()
        print('DATASET_COUNT', len(datasets))
        for id_, name, source_name, source_url, published in datasets:
            print('DATASET', id_, name, source_name, source_url, published)

        row_count = await conn.execute(select(func.count()).select_from(DatasetRow))
        print('DATASET_ROWS_COUNT', row_count.scalar_one())

        ingestion_counts = await conn.execute(select(IngestionJob.status, func.count()).group_by(IngestionJob.status))
        for status, count in ingestion_counts.all():
            print('INGESTION_STATUS', status, count)

        total_jobs = await conn.execute(select(func.count()).select_from(IngestionJob))
        print('INGESTION_JOBS_COUNT', total_jobs.scalar_one())

        latest_job = await conn.execute(
            select(IngestionJob.id, IngestionJob.status, IngestionJob.original_filename, IngestionJob.file_format, IngestionJob.file_size_bytes, IngestionJob.row_count, IngestionJob.column_count, IngestionJob.created_at, IngestionJob.completed_at, IngestionJob.updated_at, IngestionJob.failed_at, IngestionJob.error_message)
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )
        latest = latest_job.first()
        if latest:
            print('LATEST_INGESTION_JOB', *latest)

        registries = await conn.execute(select(DatasetRegistry.id, DatasetRegistry.dataset_name, DatasetRegistry.source_type, DatasetRegistry.source_url, DatasetRegistry.import_method, DatasetRegistry.refresh_frequency, DatasetRegistry.last_imported_at, DatasetRegistry.verification_status, DatasetRegistry.created_at, DatasetRegistry.updated_at).order_by(DatasetRegistry.created_at.desc()))
        registries = registries.all()
        print('REGISTRY_COUNT', len(registries))
        for row in registries[:5]:
            print('REGISTRY', *row)

if __name__ == '__main__':
    asyncio.run(main())
