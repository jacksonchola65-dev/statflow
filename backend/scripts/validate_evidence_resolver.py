"""
Execute Phase 8A.5.1B Step 8: Validate Evidence Resolver Coverage

Verify that all 12 Luapula districts can be resolved through the
decision evidence system.
"""

import asyncio
import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.models.data_point import DataPoint
from app.models.district import District
from app.models.indicator import Indicator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

REQUIRED_DISTRICTS = [
    "LP-CHEMBE",
    "LP-CHIENGE",
    "LP-CHIFUNABULI",
    "LP-CHIPILI",
    "LP-KAWAMBWA",
    "LP-LUNGA",
    "LP-MANSA",
    "LP-MILENGE",
    "LP-MWANSABOMBWE",
    "LP-MWENSE",
    "LP-NCHELENGE",
    "LP-SAMFYA",
]


async def main():
    """Validate evidence resolver coverage."""
    # Create async engine and session factory
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
    )

    async_session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_factory() as session:
        print(f"\n{'=' * 80}")
        print("PHASE 8A.5.1B STEP 8: Validate Evidence Resolver Coverage")
        print(f"{'=' * 80}\n")

        # Get POP_TOTAL indicator
        indicator_result = await session.execute(
            select(Indicator).where(Indicator.code == "POP_TOTAL")
        )
        indicator = indicator_result.scalar_one_or_none()

        if indicator is None:
            print("ERROR: POP_TOTAL indicator not found")
            return

        # Get all districts
        district_result = await session.execute(
            select(District).where(District.code.in_(REQUIRED_DISTRICTS))
        )
        districts = {d.code: d for d in district_result.scalars().all()}

        # Verify DataPoints were created for all districts

        dp_result = await session.execute(
            select(DataPoint).where(
                DataPoint.indicator_id == indicator.id,
                DataPoint.reference_year == 2022,
            )
        )
        resolved = len(list(dp_result.scalars().all()))
        failed = []

        for code in REQUIRED_DISTRICTS:
            district = districts.get(code)
            if district is None:
                failed.append((code, "District not found"))
                continue

            # Check if DataPoint exists for this district
            dp_result = await session.execute(
                select(DataPoint).where(
                    DataPoint.indicator_id == indicator.id,
                    DataPoint.district_id == district.id,
                    DataPoint.reference_year == 2022,
                )
            )
            dp = dp_result.scalar_one_or_none()

            if dp:
                print(f"✓ {code}: RESOLVED (value={dp.value})")
            else:
                failed.append((code, "No DataPoint found"))
                print(f"✗ {code}: NOT RESOLVED")
        # Report summary
        coverage_pct = (resolved / len(REQUIRED_DISTRICTS)) * 100
        print(f"\n{'=' * 80}")
        print("EVIDENCE RESOLVER SUMMARY")
        print(f"{'=' * 80}")
        print(f"Districts Expected: {len(REQUIRED_DISTRICTS)}")
        print(f"Districts Resolved: {resolved}")
        print(f"Districts Failed: {len(failed)}")
        print(f"Coverage: {coverage_pct:.1f}%")

        if failed:
            print("\nFailed Resolutions:")
            for code, reason in failed:
                print(f"  - {code}: {reason}")

        print(f"{'=' * 80}\n")


if __name__ == "__main__":
    asyncio.run(main())
