"""
Tests for DistrictPopulationIngestionService — Phase 8A.5.1B

Comprehensive test suite for the controlled ingestion of verified
2022 Luapula district population evidence.
"""

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from app.models.category import Category
from app.models.data_point import DataPoint
from app.models.dataset import Dataset
from app.models.district import District
from app.models.indicator import Indicator
from app.models.province import Province
from app.services.district_population_ingestion_service import (
    DistrictPopulationIngestionService,
    IngestionStatus,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def setup_dependencies(db_session: AsyncSession) -> tuple[Province, Indicator]:
    """Set up required provinces, districts, categories, and indicators."""

    # Get existing province (already seeded in conftest)
    province_result = await db_session.execute(select(Province).where(Province.code == "LP"))
    province = province_result.scalar_one_or_none()
    if province is None:
        pytest.fail("LP province not found - check test database setup")

    # Create or get districts
    districts = [
        District(province_id=province.id, code="LP-CHEMBE", name="Chembe"),
        District(province_id=province.id, code="LP-CHIENGE", name="Chienge"),
        District(province_id=province.id, code="LP-CHIFUNABULI", name="Chifunabuli"),
        District(province_id=province.id, code="LP-CHIPILI", name="Chipili"),
        District(province_id=province.id, code="LP-KAWAMBWA", name="Kawambwa"),
        District(province_id=province.id, code="LP-LUNGA", name="Lunga"),
        District(province_id=province.id, code="LP-MANSA", name="Mansa"),
        District(province_id=province.id, code="LP-MILENGE", name="Milenge"),
        District(province_id=province.id, code="LP-MWANSABOMBWE", name="Mwansabombwe"),
        District(province_id=province.id, code="LP-MWENSE", name="Mwense"),
        District(province_id=province.id, code="LP-NCHELENGE", name="Nchelenge"),
        District(province_id=province.id, code="LP-SAMFYA", name="Samfya"),
    ]
    db_session.add_all(districts)
    await db_session.flush()

    # Get existing category (already seeded in conftest)
    category_result = await db_session.execute(
        select(Category).where(Category.code == "DEMOGRAPHICS")
    )
    category = category_result.scalar_one_or_none()
    if category is None:
        pytest.fail("DEMOGRAPHICS category not found - check test database setup")

    # Try to get existing POP_TOTAL indicator
    indicator_result = await db_session.execute(
        select(Indicator).where(Indicator.code == "POP_TOTAL")
    )
    indicator = indicator_result.scalar_one_or_none()

    # If not found, create it
    if indicator is None:
        indicator = Indicator(
            category_id=category.id,
            code="POP_TOTAL",
            name="Total Population",
            description="Total population count",
            unit="People",
        )
        db_session.add(indicator)
        await db_session.flush()
    await db_session.commit()
    return province, indicator


def _create_test_csv(path: Path, rows: list[str]) -> None:
    """Create a test CSV file."""
    header = (
        "province_code,province_name,district_code,district_name,"
        "total_population,male,female,rural_population,urban_population,"
        "source_title,source_url,publication_date,table_title,table_page,"
        "verification_status"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n")
        for row in rows:
            f.write(row + "\n")


def _valid_row(
    district_code: str,
    district_name: str,
    population: int,
    male: int,
    female: int,
    rural: int,
    urban: int,
) -> str:
    """Generate a valid CSV row."""
    return (
        f"LP,Luapula,{district_code},{district_name},"
        f"{population},{male},{female},{rural},{urban},"
        '"2022 Census of Population and Housing Summary Report Part 2",'
        '"https://www.zamstats.gov.zm/2022-census-of-population-and-housing-summary-report-part-2/",'
        '"2024-06",'
        '"Dejure Population by Sex, Rural/Urban, Province, District, Constituency and Ward, Zambia 2022",'
        '45,"VERIFIED"'
    )


class TestDistrictPopulationIngestion:
    """Test district population ingestion."""

    @pytest.mark.asyncio
    async def test_12_row_successful_import(
        self, db_session: AsyncSession, setup_dependencies: tuple[Province, Indicator]
    ) -> None:
        """Test successful import of all 12 districts."""
        province, indicator = setup_dependencies

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "luapula_2022.csv"

            rows = [
                _valid_row("LP-CHEMBE", "Chembe", 51634, 26205, 25429, 51634, 0),
                _valid_row("LP-CHIENGE", "Chienge", 190566, 94023, 96543, 175401, 15165),
                _valid_row("LP-CHIFUNABULI", "Chifunabuli", 116634, 57015, 59619, 81391, 35243),
                _valid_row("LP-CHIPILI", "Chipili", 47473, 23676, 23797, 47473, 0),
                _valid_row("LP-KAWAMBWA", "Kawambwa", 124046, 61491, 62555, 92885, 31161),
                _valid_row("LP-LUNGA", "Lunga", 39462, 19343, 20119, 39462, 0),
                _valid_row("LP-MANSA", "Mansa", 329622, 161891, 167731, 157899, 171723),
                _valid_row("LP-MILENGE", "Milenge", 56638, 27776, 28862, 56638, 0),
                _valid_row(
                    "LP-MWANSABOMBWE",
                    "Mwansabombwe",
                    58992,
                    28602,
                    30390,
                    42915,
                    16077,
                ),
                _valid_row("LP-MWENSE", "Mwense", 122796, 59873, 62923, 115888, 6908),
                _valid_row("LP-NCHELENGE", "Nchelenge", 234259, 116149, 118110, 156513, 77746),
                _valid_row("LP-SAMFYA", "Samfya", 147356, 71354, 76002, 96047, 51309),
            ]
            _create_test_csv(csv_path, rows)

            service = DistrictPopulationIngestionService(db_session)
            result = await service.ingest_csv(csv_path)

            assert result.status == IngestionStatus.SUCCESS
            assert result.rows_expected == 12
            assert result.rows_accepted == 12
            assert result.rows_rejected == 0
            assert result.created_datapoints == 12
            assert result.skipped_duplicate == 0
            assert len(result.conflicts) == 0

            # Verify DataPoints were created
            dp_result = await db_session.execute(select(DataPoint))
            dps = list(dp_result.scalars().all())
            assert len(dps) == 12

            # Verify each district has a DataPoint
            for dp in dps:
                assert dp.district_id is not None
                assert dp.province_id is None  # District-level only

    @pytest.mark.asyncio
    async def test_exact_district_code_mapping(
        self, db_session: AsyncSession, setup_dependencies: tuple[Province, Indicator]
    ) -> None:
        """Test that district codes are mapped exactly."""
        province, indicator = setup_dependencies

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            rows = [
                _valid_row("LP-CHEMBE", "Chembe", 51634, 26205, 25429, 51634, 0),
            ]
            _create_test_csv(csv_path, rows)

            service = DistrictPopulationIngestionService(db_session)
            result = await service.ingest_csv(csv_path)

            # Should fail because only 1 row instead of 12
            assert result.status == IngestionStatus.FAILED
            assert any("Expected 12 rows" in e.error for e in result.validation_errors)

    @pytest.mark.asyncio
    async def test_incorrect_district_rejected(
        self, db_session: AsyncSession, setup_dependencies: tuple[Province, Indicator]
    ) -> None:
        """Test that non-existent districts are rejected."""
        province, indicator = setup_dependencies

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"

            # Create 12 rows with 11 valid and 1 invalid district
            rows = [
                _valid_row("LP-CHEMBE", "Chembe", 51634, 26205, 25429, 51634, 0),
                _valid_row("LP-CHIENGE", "Chienge", 190566, 94023, 96543, 175401, 15165),
                _valid_row("LP-CHIFUNABULI", "Chifunabuli", 116634, 57015, 59619, 81391, 35243),
                _valid_row("LP-CHIPILI", "Chipili", 47473, 23676, 23797, 47473, 0),
                _valid_row("LP-KAWAMBWA", "Kawambwa", 124046, 61491, 62555, 92885, 31161),
                _valid_row("LP-LUNGA", "Lunga", 39462, 19343, 20119, 39462, 0),
                _valid_row("LP-MANSA", "Mansa", 329622, 161891, 167731, 157899, 171723),
                _valid_row("LP-MILENGE", "Milenge", 56638, 27776, 28862, 56638, 0),
                _valid_row(
                    "LP-MWANSABOMBWE",
                    "Mwansabombwe",
                    58992,
                    28602,
                    30390,
                    42915,
                    16077,
                ),
                _valid_row("LP-MWENSE", "Mwense", 122796, 59873, 62923, 115888, 6908),
                _valid_row("LP-NCHELENGE", "Nchelenge", 234259, 116149, 118110, 156513, 77746),
                _valid_row("LP-INVALID", "Invalid", 100000, 50000, 50000, 75000, 25000),  # Invalid
            ]
            _create_test_csv(csv_path, rows)

            service = DistrictPopulationIngestionService(db_session)
            result = await service.ingest_csv(csv_path)

            assert result.status == IngestionStatus.FAILED
            assert len(result.conflicts) > 0

    @pytest.mark.asyncio
    async def test_negative_population_rejected(
        self, db_session: AsyncSession, setup_dependencies: tuple[Province, Indicator]
    ) -> None:
        """Test that negative populations are rejected."""
        province, indicator = setup_dependencies

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            rows = [
                "LP,Luapula,LP-CHEMBE,Chembe,-100,50,-150,75,25,"
                + '"Title","URL","2024-06","Table",45,"VERIFIED"'
            ]
            # Add 11 more valid rows to reach 12
            for i in range(11):
                rows.append(
                    _valid_row(f"LP-TEST{i:02d}", f"Test{i}", 10000, 5000, 5000, 7500, 2500)
                )
            _create_test_csv(csv_path, rows)

            service = DistrictPopulationIngestionService(db_session)
            result = await service.ingest_csv(csv_path)

            # Should fail due to validation error
            assert result.status == IngestionStatus.FAILED

    @pytest.mark.asyncio
    async def test_idempotent_second_import(
        self, db_session: AsyncSession, setup_dependencies: tuple[Province, Indicator]
    ) -> None:
        """Test that idempotent second import works correctly."""
        province, indicator = setup_dependencies

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "luapula_2022.csv"

            rows = [
                _valid_row("LP-CHEMBE", "Chembe", 51634, 26205, 25429, 51634, 0),
                _valid_row("LP-CHIENGE", "Chienge", 190566, 94023, 96543, 175401, 15165),
                _valid_row("LP-CHIFUNABULI", "Chifunabuli", 116634, 57015, 59619, 81391, 35243),
                _valid_row("LP-CHIPILI", "Chipili", 47473, 23676, 23797, 47473, 0),
                _valid_row("LP-KAWAMBWA", "Kawambwa", 124046, 61491, 62555, 92885, 31161),
                _valid_row("LP-LUNGA", "Lunga", 39462, 19343, 20119, 39462, 0),
                _valid_row("LP-MANSA", "Mansa", 329622, 161891, 167731, 157899, 171723),
                _valid_row("LP-MILENGE", "Milenge", 56638, 27776, 28862, 56638, 0),
                _valid_row(
                    "LP-MWANSABOMBWE",
                    "Mwansabombwe",
                    58992,
                    28602,
                    30390,
                    42915,
                    16077,
                ),
                _valid_row("LP-MWENSE", "Mwense", 122796, 59873, 62923, 115888, 6908),
                _valid_row("LP-NCHELENGE", "Nchelenge", 234259, 116149, 118110, 156513, 77746),
                _valid_row("LP-SAMFYA", "Samfya", 147356, 71354, 76002, 96047, 51309),
            ]
            _create_test_csv(csv_path, rows)

            service = DistrictPopulationIngestionService(db_session)

            # First import
            result1 = await service.ingest_csv(csv_path)
            assert result1.status == IngestionStatus.SUCCESS
            assert result1.created_datapoints == 12

            # Second import (idempotent)
            result2 = await service.ingest_csv(csv_path)
            assert result2.status == IngestionStatus.SUCCESS
            assert result2.created_datapoints == 0
            assert result2.skipped_duplicate == 12

            # Verify total DataPoints is still 12
            dp_result = await db_session.execute(select(DataPoint))
            dps = list(dp_result.scalars().all())
            assert len(dps) == 12

    @pytest.mark.asyncio
    async def test_conflicting_existing_value_detected(
        self, db_session: AsyncSession, setup_dependencies: tuple[Province, Indicator]
    ) -> None:
        """Test that conflicting population values are detected."""
        province, indicator = setup_dependencies

        # Get districts
        dist_result = await db_session.execute(select(District))
        districts = {d.code: d for d in dist_result.scalars().all()}

        # Get dataset
        dataset = Dataset(
            name="2022 Census of Population and Housing - Luapula District",
            reference_year=2022,
            source_name="Test",
            is_published=True,
        )
        db_session.add(dataset)
        await db_session.flush()

        # Create existing DataPoint with different value
        existing_dp = DataPoint(
            dataset_id=dataset.id,
            indicator_id=indicator.id,
            district_id=districts["LP-CHEMBE"].id,
            province_id=None,
            reference_year=2022,
            value=Decimal("99999"),  # Conflict value
        )
        db_session.add(existing_dp)
        await db_session.commit()

        # Try to ingest with different value
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"

            rows = [
                _valid_row("LP-CHEMBE", "Chembe", 51634, 26205, 25429, 51634, 0),  # Different
                _valid_row("LP-CHIENGE", "Chienge", 190566, 94023, 96543, 175401, 15165),
                _valid_row("LP-CHIFUNABULI", "Chifunabuli", 116634, 57015, 59619, 81391, 35243),
                _valid_row("LP-CHIPILI", "Chipili", 47473, 23676, 23797, 47473, 0),
                _valid_row("LP-KAWAMBWA", "Kawambwa", 124046, 61491, 62555, 92885, 31161),
                _valid_row("LP-LUNGA", "Lunga", 39462, 19343, 20119, 39462, 0),
                _valid_row("LP-MANSA", "Mansa", 329622, 161891, 167731, 157899, 171723),
                _valid_row("LP-MILENGE", "Milenge", 56638, 27776, 28862, 56638, 0),
                _valid_row(
                    "LP-MWANSABOMBWE",
                    "Mwansabombwe",
                    58992,
                    28602,
                    30390,
                    42915,
                    16077,
                ),
                _valid_row("LP-MWENSE", "Mwense", 122796, 59873, 62923, 115888, 6908),
                _valid_row("LP-NCHELENGE", "Nchelenge", 234259, 116149, 118110, 156513, 77746),
                _valid_row("LP-SAMFYA", "Samfya", 147356, 71354, 76002, 96047, 51309),
            ]
            _create_test_csv(csv_path, rows)

            service = DistrictPopulationIngestionService(db_session)
            result = await service.ingest_csv(csv_path)

            # Should detect conflict
            assert any("conflict" in c.lower() for c in result.conflicts)

    @pytest.mark.asyncio
    async def test_no_duplicate_datapoints(
        self, db_session: AsyncSession, setup_dependencies: tuple[Province, Indicator]
    ) -> None:
        """Test that no duplicate DataPoints are created."""
        province, indicator = setup_dependencies

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "luapula_2022.csv"

            rows = [
                _valid_row("LP-CHEMBE", "Chembe", 51634, 26205, 25429, 51634, 0),
                _valid_row("LP-CHIENGE", "Chienge", 190566, 94023, 96543, 175401, 15165),
                _valid_row("LP-CHIFUNABULI", "Chifunabuli", 116634, 57015, 59619, 81391, 35243),
                _valid_row("LP-CHIPILI", "Chipili", 47473, 23676, 23797, 47473, 0),
                _valid_row("LP-KAWAMBWA", "Kawambwa", 124046, 61491, 62555, 92885, 31161),
                _valid_row("LP-LUNGA", "Lunga", 39462, 19343, 20119, 39462, 0),
                _valid_row("LP-MANSA", "Mansa", 329622, 161891, 167731, 157899, 171723),
                _valid_row("LP-MILENGE", "Milenge", 56638, 27776, 28862, 56638, 0),
                _valid_row(
                    "LP-MWANSABOMBWE",
                    "Mwansabombwe",
                    58992,
                    28602,
                    30390,
                    42915,
                    16077,
                ),
                _valid_row("LP-MWENSE", "Mwense", 122796, 59873, 62923, 115888, 6908),
                _valid_row("LP-NCHELENGE", "Nchelenge", 234259, 116149, 118110, 156513, 77746),
                _valid_row("LP-SAMFYA", "Samfya", 147356, 71354, 76002, 96047, 51309),
            ]
            _create_test_csv(csv_path, rows)

            service = DistrictPopulationIngestionService(db_session)
            result = await service.ingest_csv(csv_path)

            assert result.status == IngestionStatus.SUCCESS

            # Verify exactly 12 DataPoints
            dp_result = await db_session.execute(
                select(DataPoint).where(
                    DataPoint.reference_year == 2022,
                )
            )
            dps = list(dp_result.scalars().all())
            assert len(dps) == 12

            # Verify uniqueness by (district_id, indicator_id, reference_year)
            district_set = {dp.district_id for dp in dps}
            assert len(district_set) == 12
