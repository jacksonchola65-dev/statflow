"""
District Population Ingestion Service — Phase 8A.5.1B

Controlled ingestion of verified 2022 Luapula district population evidence
from the ZamStats 2022 Census of Population and Housing.

Features:
- CSV staging artifact validation
- Official dataset creation/reuse
- District mapping and conflict detection
- Idempotent DataPoint persistence
- Comprehensive error reporting
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional

from app.models.data_point import DataPoint
from app.models.dataset import Dataset
from app.models.district import District
from app.models.indicator import Indicator
from app.models.province import Province
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class IngestionStatus(str, Enum):
    """Status of ingestion operation."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ConflictType(str, Enum):
    """Type of conflict detected during ingestion."""

    NONE = "NONE"
    EXISTING_VALUE_DIFFERS = "EXISTING_VALUE_DIFFERS"
    MISSING_DISTRICT = "MISSING_DISTRICT"
    INVALID_POPULATION = "INVALID_POPULATION"


@dataclass
class StagingRow:
    """Parsed row from the staging artifact."""

    province_code: str
    province_name: str
    district_code: str
    district_name: str
    total_population: int
    male: int
    female: int
    rural_population: int
    urban_population: int
    source_title: str
    source_url: str
    publication_date: str
    table_title: str
    table_page: int
    verification_status: str


@dataclass
class ValidationError:
    """Validation error for a staging row."""

    row_num: int
    district_code: str
    error: str


@dataclass
class IngestionResult:
    """Result of a district population ingestion operation."""

    status: IngestionStatus
    rows_expected: int
    rows_accepted: int
    rows_rejected: int
    validation_errors: list[ValidationError]
    dataset_id: Optional[str]
    dataset_name: str
    created_datapoints: int
    updated_datapoints: int
    skipped_duplicate: int
    conflicts: list[str]


class DistrictPopulationIngestionService:
    """Service for ingesting verified district population data."""

    # Constants
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
    EXPECTED_COUNT = len(REQUIRED_DISTRICTS)

    OFFICIAL_DATASET_NAME = "2022 Census of Population and Housing - Luapula District"
    OFFICIAL_DATASET_YEAR = 2022
    INDICATOR_CODE = "POP_TOTAL"
    PROVINCE_CODE = "LP"

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the ingestion service."""
        self._session = session

    async def ingest_csv(self, csv_path: str | Path) -> IngestionResult:
        """
        Ingest district population data from a verified CSV artifact.

        Args:
            csv_path: Path to the staging CSV file

        Returns:
            IngestionResult with detailed success/failure information
        """
        csv_path = Path(csv_path)

        # Step 1: Validate CSV and parse rows
        rows, validation_errors = await self._parse_and_validate_csv(csv_path)
        if validation_errors or len(rows) != self.EXPECTED_COUNT:
            return IngestionResult(
                status=IngestionStatus.FAILED,
                rows_expected=self.EXPECTED_COUNT,
                rows_accepted=0,
                rows_rejected=self.EXPECTED_COUNT,
                validation_errors=validation_errors
                or [ValidationError(0, "ALL", "No valid rows parsed from CSV")],
                dataset_id=None,
                dataset_name=self.OFFICIAL_DATASET_NAME,
                created_datapoints=0,
                updated_datapoints=0,
                skipped_duplicate=0,
                conflicts=[],
            )

        # Step 2: Ensure required dependencies exist
        indicator = await self._get_indicator(self.INDICATOR_CODE)
        if indicator is None:
            return IngestionResult(
                status=IngestionStatus.FAILED,
                rows_expected=self.EXPECTED_COUNT,
                rows_accepted=0,
                rows_rejected=len(rows),
                validation_errors=[
                    ValidationError(0, "ALL", f"Indicator {self.INDICATOR_CODE} not found")
                ],
                dataset_id=None,
                dataset_name=self.OFFICIAL_DATASET_NAME,
                created_datapoints=0,
                updated_datapoints=0,
                skipped_duplicate=0,
                conflicts=[],
            )

        province = await self._get_province(self.PROVINCE_CODE)
        if province is None:
            return IngestionResult(
                status=IngestionStatus.FAILED,
                rows_expected=self.EXPECTED_COUNT,
                rows_accepted=0,
                rows_rejected=len(rows),
                validation_errors=[
                    ValidationError(0, "ALL", f"Province {self.PROVINCE_CODE} not found")
                ],
                dataset_id=None,
                dataset_name=self.OFFICIAL_DATASET_NAME,
                created_datapoints=0,
                updated_datapoints=0,
                skipped_duplicate=0,
                conflicts=[],
            )

        # Step 3: Build district code → District map
        district_map = await self._build_district_map()
        missing_districts = [code for code in self.REQUIRED_DISTRICTS if code not in district_map]
        if missing_districts:
            return IngestionResult(
                status=IngestionStatus.FAILED,
                rows_expected=self.EXPECTED_COUNT,
                rows_accepted=0,
                rows_rejected=len(rows),
                validation_errors=[
                    ValidationError(
                        0,
                        "ALL",
                        f"Missing districts: {', '.join(missing_districts)}",
                    )
                ],
                dataset_id=None,
                dataset_name=self.OFFICIAL_DATASET_NAME,
                created_datapoints=0,
                updated_datapoints=0,
                skipped_duplicate=0,
                conflicts=[],
            )

        mapping_errors = [
            ValidationError(0, row.district_code, "District belongs to another province")
            for row in rows
            if row.district_code in district_map
            and district_map[row.district_code].province_id != province.id
        ]
        mapping_errors.extend(
            ValidationError(0, row.district_code, "District name does not match canonical name")
            for row in rows
            if row.district_code in district_map
            and district_map[row.district_code].name != row.district_name
        )
        if mapping_errors:
            return IngestionResult(
                status=IngestionStatus.FAILED,
                rows_expected=self.EXPECTED_COUNT,
                rows_accepted=0,
                rows_rejected=len(rows),
                validation_errors=mapping_errors,
                dataset_id=None,
                dataset_name=self.OFFICIAL_DATASET_NAME,
                created_datapoints=0,
                updated_datapoints=0,
                skipped_duplicate=0,
                conflicts=[],
            )

        # Step 4: Get or create the official dataset
        dataset = await self._get_or_create_dataset()
        if dataset is None:
            return IngestionResult(
                status=IngestionStatus.FAILED,
                rows_expected=self.EXPECTED_COUNT,
                rows_accepted=0,
                rows_rejected=len(rows),
                validation_errors=[ValidationError(0, "ALL", "Failed to create dataset")],
                dataset_id=None,
                dataset_name=self.OFFICIAL_DATASET_NAME,
                created_datapoints=0,
                updated_datapoints=0,
                skipped_duplicate=0,
                conflicts=[],
            )

        # Step 5: Ingest rows
        result = await self._persist_datapoints(dataset, indicator, province, district_map, rows)
        result.dataset_id = str(dataset.id)
        result.dataset_name = self.OFFICIAL_DATASET_NAME
        return result

    async def _parse_and_validate_csv(
        self, csv_path: Path
    ) -> tuple[list[StagingRow], list[ValidationError]]:
        """Parse and validate the staging CSV."""
        rows: list[StagingRow] = []
        errors: list[ValidationError] = []

        if not csv_path.exists():
            errors.append(ValidationError(0, "ALL", f"File not found: {csv_path}"))
            return [], errors

        try:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    errors.append(ValidationError(0, "ALL", "CSV has no header row"))
                    return [], errors

                for row_num, row in enumerate(reader, start=2):  # Row 2+ (header is 1)
                    try:
                        staging_row = self._parse_row(row)
                        rows.append(staging_row)
                    except ValueError as e:
                        errors.append(
                            ValidationError(
                                row_num,
                                row.get("district_code", "UNKNOWN"),
                                str(e),
                            )
                        )
        except Exception as e:
            errors.append(ValidationError(0, "ALL", f"CSV parsing failed: {str(e)}"))
            return [], errors

        if len(rows) != self.EXPECTED_COUNT:
            errors.append(
                ValidationError(
                    0,
                    "ALL",
                    f"Expected {self.EXPECTED_COUNT} rows, got {len(rows)}",
                )
            )

        district_codes = [row.district_code for row in rows]
        duplicates = {code for code in district_codes if district_codes.count(code) > 1}
        for code in sorted(duplicates):
            errors.append(ValidationError(0, code, "Duplicate district_code in staging artifact"))

        for row_num, staging_row in enumerate(rows, start=2):
            if staging_row.province_code != self.PROVINCE_CODE:
                errors.append(
                    ValidationError(row_num, staging_row.district_code, "Wrong province_code")
                )
            if staging_row.verification_status != "VERIFIED":
                errors.append(
                    ValidationError(
                        row_num,
                        staging_row.district_code,
                        "verification_status must be VERIFIED",
                    )
                )
            if (
                not staging_row.source_title
                or not staging_row.source_url
                or not staging_row.publication_date
            ):
                errors.append(
                    ValidationError(
                        row_num,
                        staging_row.district_code,
                        "Required source metadata is missing",
                    )
                )
            if staging_row.table_page <= 0 or not staging_row.table_title:
                errors.append(
                    ValidationError(
                        row_num,
                        staging_row.district_code,
                        "Required table metadata is missing",
                    )
                )

        return rows, errors

    @staticmethod
    def _parse_row(row: dict) -> StagingRow:
        """Parse a single CSV row."""
        try:
            total_pop = int(row["total_population"])
            if total_pop <= 0:
                raise ValueError("total_population must be > 0")

            male = int(row["male"])
            if male < 0:
                raise ValueError("male must be >= 0")

            female = int(row["female"])
            if female < 0:
                raise ValueError("female must be >= 0")

            rural = int(row["rural_population"])
            if rural < 0:
                raise ValueError("rural_population must be >= 0")

            urban = int(row["urban_population"])
            if urban < 0:
                raise ValueError("urban_population must be >= 0")

            table_page = int(row["table_page"])

            return StagingRow(
                province_code=row["province_code"].strip(),
                province_name=row["province_name"].strip(),
                district_code=row["district_code"].strip(),
                district_name=row["district_name"].strip(),
                total_population=total_pop,
                male=male,
                female=female,
                rural_population=rural,
                urban_population=urban,
                source_title=row["source_title"].strip(),
                source_url=row["source_url"].strip(),
                publication_date=row["publication_date"].strip(),
                table_title=row["table_title"].strip(),
                table_page=table_page,
                verification_status=row["verification_status"].strip(),
            )
        except (KeyError, ValueError) as e:
            raise ValueError(f"Row parsing failed: {str(e)}")

    async def _get_indicator(self, code: str) -> Optional[Indicator]:
        """Retrieve indicator by code."""
        result = await self._session.execute(select(Indicator).where(Indicator.code == code))
        return result.scalar_one_or_none()

    async def _get_province(self, code: str) -> Optional[Province]:
        """Retrieve province by code."""
        result = await self._session.execute(select(Province).where(Province.code == code))
        return result.scalar_one_or_none()

    async def _get_or_create_dataset(self) -> Optional[Dataset]:
        """Get existing dataset or create a new one."""
        # Try to find existing dataset
        result = await self._session.execute(
            select(Dataset).where(
                Dataset.name == self.OFFICIAL_DATASET_NAME,
                Dataset.reference_year == self.OFFICIAL_DATASET_YEAR,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        # Create new dataset
        dataset = Dataset(
            name=self.OFFICIAL_DATASET_NAME,
            description=(
                "2022 Census of Population and Housing - Luapula Province. "
                "Official de jure population counts by district. "
                "Source: Zambia Statistics Agency (ZamStats)"
            ),
            source_name="Zambia Statistics Agency (ZamStats)",
            source_url=(
                "https://www.zamstats.gov.zm/"
                "2022-census-of-population-and-housing-summary-report-part-2/"
            ),
            reference_year=self.OFFICIAL_DATASET_YEAR,
            is_published=True,
        )
        self._session.add(dataset)
        await self._session.flush()
        return dataset

    async def _build_district_map(self) -> dict[str, District]:
        """Build a map of district code → District."""
        result = await self._session.execute(
            select(District).where(District.code.in_(self.REQUIRED_DISTRICTS))
        )
        districts = result.scalars().all()
        return {d.code: d for d in districts}

    async def _persist_datapoints(
        self,
        dataset: Dataset,
        indicator: Indicator,
        province: Province,
        district_map: dict[str, District],
        rows: list[StagingRow],
    ) -> IngestionResult:
        """Persist DataPoints for each district."""
        created = 0
        updated = 0
        skipped = 0
        conflicts: list[str] = []

        existing_points: dict[str, Optional[DataPoint]] = {}
        for row in rows:
            district = district_map.get(row.district_code)
            if district is None:
                conflicts.append(f"District {row.district_code} not found in map")
                continue

            existing_result = await self._session.execute(
                select(DataPoint).where(
                    DataPoint.dataset_id == dataset.id,
                    DataPoint.indicator_id == indicator.id,
                    DataPoint.district_id == district.id,
                    DataPoint.reference_year == self.OFFICIAL_DATASET_YEAR,
                )
            )
            existing = existing_result.scalar_one_or_none()
            existing_points[row.district_code] = existing

            if existing:
                if Decimal(str(existing.value)) != Decimal(str(row.total_population)):
                    conflicts.append(
                        f"{row.district_code}: existing value "
                        f"{existing.value} conflicts with new value "
                        f"{row.total_population}"
                    )
        if conflicts:
            return IngestionResult(
                status=IngestionStatus.FAILED,
                rows_expected=self.EXPECTED_COUNT,
                rows_accepted=0,
                rows_rejected=len(rows),
                validation_errors=[],
                dataset_id=str(dataset.id),
                dataset_name=self.OFFICIAL_DATASET_NAME,
                created_datapoints=0,
                updated_datapoints=0,
                skipped_duplicate=0,
                conflicts=conflicts,
            )

        for row in rows:
            district = district_map[row.district_code]
            existing = existing_points[row.district_code]
            if existing:
                skipped += 1
            else:
                dp = DataPoint(
                    dataset_id=dataset.id,
                    indicator_id=indicator.id,
                    district_id=district.id,
                    province_id=None,  # Explicitly null for district level
                    reference_year=self.OFFICIAL_DATASET_YEAR,
                    value=Decimal(str(row.total_population)),
                )
                self._session.add(dp)
                created += 1

        await self._session.flush()

        return IngestionResult(
            status=IngestionStatus.SUCCESS,
            rows_expected=self.EXPECTED_COUNT,
            rows_accepted=created + updated + skipped,
            rows_rejected=len(rows) - (created + updated + skipped),
            validation_errors=[],
            dataset_id=str(dataset.id),
            dataset_name=self.OFFICIAL_DATASET_NAME,
            created_datapoints=created,
            updated_datapoints=updated,
            skipped_duplicate=skipped,
            conflicts=conflicts,
        )
