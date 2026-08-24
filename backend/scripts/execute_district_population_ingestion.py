"""
Execute Phase 8A.5.1B Step 7: Run the ingestion on the verified staging artifact.

This script ingests the verified 2022 Luapula district population evidence
into the StatFlow data model.
"""

import asyncio
import os
import sys
from datetime import date
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import normalize_async_database_url, settings
from app.models.data_source import (
    DatasetRegistry,
    DataSource,
    FileFormat,
    ImportMethod,
    SourceType,
    VerificationStatus,
)
from app.services.district_population_ingestion_service import (
    DistrictPopulationIngestionService,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def create_script_engine():
    return create_async_engine(
        normalize_async_database_url(settings.DATABASE_URL),
        echo=False,
        future=True,
    )


async def main():
    """Execute the ingestion."""
    # Create async engine and session factory
    engine = create_script_engine()

    async_session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_factory() as session:
        service = DistrictPopulationIngestionService(session)

        # Path to the staging artifact (in root docs/evidence directory)
        repository_root = Path(__file__).resolve().parents[2]
        configured_path = os.getenv("LUAPULA_EVIDENCE_PATH")
        csv_path = (
            Path(configured_path).expanduser().resolve()
            if configured_path
            else (
                repository_root
                / "docs"
                / "evidence"
                / "luapula_district_population_2022_verified.csv"
            )
        )
        print(f"\n{'=' * 80}")
        print("PHASE 8A.5.1B STEP 7: Execute Controlled Ingestion")
        print(f"{'=' * 80}\n")
        print(f"CSV Path: {csv_path}")
        print(f"CSV Exists: {csv_path.exists()}\n")

        if not csv_path.exists():
            print(f"ERROR: Staging artifact not found at {csv_path}")
            raise FileNotFoundError(csv_path)

        # Execute ingestion
        print("Starting ingestion...")
        result = await service.ingest_csv(csv_path)

        # Report results
        print(f"\n{'=' * 80}")
        print("INGESTION RESULT")
        print(f"{'=' * 80}")
        print(f"Status: {result.status.value}")
        print(f"Rows Expected: {result.rows_expected}")
        print(f"Rows Accepted: {result.rows_accepted}")
        print(f"Rows Rejected: {result.rows_rejected}")
        print(f"Created DataPoints: {result.created_datapoints}")
        print(f"Updated DataPoints: {result.updated_datapoints}")
        print(f"Skipped Duplicates: {result.skipped_duplicate}")
        print(f"Dataset ID: {result.dataset_id}")
        print(f"Dataset Name: {result.dataset_name}")

        if result.validation_errors:
            print(f"\nValidation Errors ({len(result.validation_errors)}):")
            for error in result.validation_errors:
                print(f"  Row {error.row_num} ({error.district_code}): {error.error}")

        if result.conflicts:
            print(f"\nConflicts ({len(result.conflicts)}):")
            for conflict in result.conflicts:
                print(f"  - {conflict}")

        if result.status.value == "SUCCESS":
            source_result = await session.execute(
                select(DataSource).where(DataSource.name == "Zambia Statistics Agency (ZamStats)")
            )
            source = source_result.scalar_one_or_none()
            if source is None:
                source = DataSource(
                    name="Zambia Statistics Agency (ZamStats)",
                    description="Official national statistical agency of Zambia",
                    organization_type="OFFICIAL_STATISTICAL_AGENCY",
                    base_url="https://www.zamstats.gov.zm/",
                    country="Zambia",
                )
                session.add(source)
                await session.flush()

            registry_result = await session.execute(
                select(DatasetRegistry).where(DatasetRegistry.dataset_name == result.dataset_name)
            )
            registry = registry_result.scalar_one_or_none()
            if registry is None:
                registry = DatasetRegistry(
                    data_source_id=source.id,
                    dataset_name=result.dataset_name,
                    description="Verified 2022 de jure population by Luapula district",
                    source_type=SourceType.OFFICIAL,
                    category="DEMOGRAPHICS",
                    file_format=FileFormat.CSV,
                    source_url="https://www.zamstats.gov.zm/2022-census-of-population-and-housing-summary-report-part-2/",
                    publication_date=date(2024, 6, 1),
                    import_method=ImportMethod.MANUAL,
                    verification_status=VerificationStatus.VERIFIED,
                )
                session.add(registry)
            await session.commit()
            print(f"\n{'=' * 80}")
            print("✓ Ingestion committed to database")
            print(f"{'=' * 80}\n")
        else:
            await session.rollback()
            print(f"\n{'=' * 80}")
            print("✗ Ingestion rolled back")
            print(f"{'=' * 80}\n")


if __name__ == "__main__":
    asyncio.run(main())
