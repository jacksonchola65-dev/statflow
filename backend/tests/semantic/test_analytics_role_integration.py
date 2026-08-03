import time
from typing import Sequence

from app.semantic.analytics_role_models import Aggregation, AnalyticsRoleProfile, DimensionType
from app.semantic.dimension_detector import DimensionColumnInput, DimensionDetector
from app.semantic.measure_detector import MeasureColumnInput, MeasureDetector
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType


def sc(semantic_type: SemanticType, confidence: float) -> SemanticClassification:
    return SemanticClassification(
        semantic_type=semantic_type,
        confidence=confidence,
        evidence=(SemanticEvidence(source="integration", score=confidence),),
    )


def build_role_profile(
    measure_columns: Sequence[MeasureColumnInput],
    dimension_columns: Sequence[DimensionColumnInput],
) -> AnalyticsRoleProfile:
    return AnalyticsRoleProfile(
        measure_candidates=MeasureDetector.discover(tuple(measure_columns)),
        dimension_candidates=DimensionDetector.discover(tuple(dimension_columns)),
    )


def assert_measure_aggregations(profile: AnalyticsRoleProfile, expected: dict[str, Aggregation]):
    assert {m.name: m.aggregation for m in profile.measure_candidates} == expected


def assert_dimension_types(profile: AnalyticsRoleProfile, expected: dict[str, DimensionType]):
    assert {d.name: d.dimension_type for d in profile.dimension_candidates} == expected


def test_retail_dataset_role_integration():
    profile = build_role_profile(
        measure_columns=(
            MeasureColumnInput(
                column_name="sales", classifications=(sc(SemanticType.CURRENCY, 0.88),)
            ),
            MeasureColumnInput(
                column_name="discount_pct", classifications=(sc(SemanticType.PERCENTAGE, 0.72),)
            ),
            MeasureColumnInput(
                column_name="units_sold", classifications=(sc(SemanticType.QUANTITY, 0.81),)
            ),
        ),
        dimension_columns=(
            DimensionColumnInput(
                column_name="product_category",
                classifications=(sc(SemanticType.CATEGORY, 0.91),),
                cardinality_ratio=0.12,
            ),
            DimensionColumnInput(
                column_name="store_country",
                classifications=(sc(SemanticType.COUNTRY, 0.94),),
                cardinality_ratio=0.08,
            ),
            DimensionColumnInput(
                column_name="sale_date",
                classifications=(sc(SemanticType.DATE, 0.90),),
                cardinality_ratio=0.03,
            ),
            DimensionColumnInput(
                column_name="notes",
                classifications=(sc(SemanticType.TEXT, 0.85),),
                cardinality_ratio=0.20,
            ),
        ),
    )

    assert [m.name for m in profile.measure_candidates] == ["sales", "units_sold", "discount_pct"]
    assert_measure_aggregations(
        profile,
        {
            "sales": Aggregation.SUM,
            "discount_pct": Aggregation.AVG,
            "units_sold": Aggregation.SUM,
        },
    )
    assert_dimension_types(
        profile,
        {
            "product_category": DimensionType.CATEGORICAL,
            "store_country": DimensionType.GEOGRAPHIC,
            "sale_date": DimensionType.TEMPORAL,
            "notes": DimensionType.TEXTUAL,
        },
    )


def test_healthcare_dataset_role_integration():
    profile = build_role_profile(
        measure_columns=(
            MeasureColumnInput(
                column_name="cost", classifications=(sc(SemanticType.CURRENCY, 0.82),)
            ),
            MeasureColumnInput(
                column_name="dosage", classifications=(sc(SemanticType.QUANTITY, 0.78),)
            ),
            MeasureColumnInput(
                column_name="recovery_pct", classifications=(sc(SemanticType.PERCENTAGE, 0.77),)
            ),
        ),
        dimension_columns=(
            DimensionColumnInput(
                column_name="patient_id",
                classifications=(sc(SemanticType.IDENTIFIER, 0.95),),
                cardinality_ratio=0.02,
            ),
            DimensionColumnInput(
                column_name="hospital_city",
                classifications=(sc(SemanticType.CITY, 0.88),),
                cardinality_ratio=0.15,
            ),
            DimensionColumnInput(
                column_name="visit_year",
                classifications=(sc(SemanticType.YEAR, 0.92),),
                cardinality_ratio=0.05,
            ),
            DimensionColumnInput(
                column_name="department",
                classifications=(sc(SemanticType.TEXT, 0.80),),
                cardinality_ratio=0.30,
            ),
        ),
    )

    assert_measure_aggregations(
        profile,
        {
            "cost": Aggregation.SUM,
            "dosage": Aggregation.SUM,
            "recovery_pct": Aggregation.AVG,
        },
    )
    assert_dimension_types(
        profile,
        {
            "patient_id": DimensionType.IDENTIFIER,
            "hospital_city": DimensionType.GEOGRAPHIC,
            "visit_year": DimensionType.TEMPORAL,
            "department": DimensionType.TEXTUAL,
        },
    )


def test_education_dataset_role_integration():
    profile = build_role_profile(
        measure_columns=(
            MeasureColumnInput(
                column_name="test_score", classifications=(sc(SemanticType.INTEGER, 0.88),)
            ),
            MeasureColumnInput(
                column_name="attendance_pct", classifications=(sc(SemanticType.PERCENTAGE, 0.80),)
            ),
        ),
        dimension_columns=(
            DimensionColumnInput(
                column_name="student_id",
                classifications=(sc(SemanticType.IDENTIFIER, 0.95),),
                cardinality_ratio=0.01,
            ),
            DimensionColumnInput(
                column_name="school_province",
                classifications=(sc(SemanticType.PROVINCE, 0.87),),
                cardinality_ratio=0.18,
            ),
            DimensionColumnInput(
                column_name="enrollment_year",
                classifications=(sc(SemanticType.YEAR, 0.90),),
                cardinality_ratio=0.04,
            ),
        ),
    )

    assert_measure_aggregations(
        profile,
        {
            "test_score": Aggregation.SUM,
            "attendance_pct": Aggregation.AVG,
        },
    )
    assert_dimension_types(
        profile,
        {
            "student_id": DimensionType.IDENTIFIER,
            "school_province": DimensionType.GEOGRAPHIC,
            "enrollment_year": DimensionType.TEMPORAL,
        },
    )


def test_hr_dataset_role_integration():
    profile = build_role_profile(
        measure_columns=(
            MeasureColumnInput(
                column_name="salary", classifications=(sc(SemanticType.CURRENCY, 0.90),)
            ),
            MeasureColumnInput(
                column_name="bonus", classifications=(sc(SemanticType.CURRENCY, 0.75),)
            ),
        ),
        dimension_columns=(
            DimensionColumnInput(
                column_name="employee_id",
                classifications=(sc(SemanticType.IDENTIFIER, 0.96),),
                cardinality_ratio=0.02,
            ),
            DimensionColumnInput(
                column_name="department",
                classifications=(sc(SemanticType.CATEGORY, 0.88),),
                cardinality_ratio=0.12,
            ),
            DimensionColumnInput(
                column_name="hire_date",
                classifications=(sc(SemanticType.DATE, 0.91),),
                cardinality_ratio=0.05,
            ),
        ),
    )

    assert_measure_aggregations(
        profile,
        {
            "salary": Aggregation.SUM,
            "bonus": Aggregation.SUM,
        },
    )
    assert_dimension_types(
        profile,
        {
            "employee_id": DimensionType.IDENTIFIER,
            "department": DimensionType.CATEGORICAL,
            "hire_date": DimensionType.TEMPORAL,
        },
    )


def test_government_dataset_role_integration():
    profile = build_role_profile(
        measure_columns=(
            MeasureColumnInput(
                column_name="budget", classifications=(sc(SemanticType.CURRENCY, 0.92),)
            ),
            MeasureColumnInput(
                column_name="usage_pct", classifications=(sc(SemanticType.PERCENTAGE, 0.83),)
            ),
        ),
        dimension_columns=(
            DimensionColumnInput(
                column_name="agency",
                classifications=(sc(SemanticType.ORGANIZATION, 0.85),),
                cardinality_ratio=0.10,
            ),
            DimensionColumnInput(
                column_name="region",
                classifications=(sc(SemanticType.DISTRICT, 0.86),),
                cardinality_ratio=0.14,
            ),
            DimensionColumnInput(
                column_name="fiscal_year",
                classifications=(sc(SemanticType.YEAR, 0.93),),
                cardinality_ratio=0.03,
            ),
        ),
    )

    assert_measure_aggregations(
        profile,
        {
            "budget": Aggregation.SUM,
            "usage_pct": Aggregation.AVG,
        },
    )
    assert_dimension_types(
        profile,
        {
            "agency": DimensionType.ENTITY,
            "region": DimensionType.GEOGRAPHIC,
            "fiscal_year": DimensionType.TEMPORAL,
        },
    )


def test_measure_only_dataset_role_integration():
    profile = build_role_profile(
        measure_columns=(
            MeasureColumnInput(
                column_name="revenue", classifications=(sc(SemanticType.CURRENCY, 0.92),)
            ),
            MeasureColumnInput(
                column_name="margin", classifications=(sc(SemanticType.PERCENTAGE, 0.81),)
            ),
        ),
        dimension_columns=(),
    )

    assert [m.name for m in profile.measure_candidates] == ["revenue", "margin"]
    assert profile.dimension_candidates == ()


def test_dimension_only_dataset_role_integration():
    profile = build_role_profile(
        measure_columns=(),
        dimension_columns=(
            DimensionColumnInput(
                column_name="category",
                classifications=(sc(SemanticType.CATEGORY, 0.90),),
                cardinality_ratio=0.10,
            ),
            DimensionColumnInput(
                column_name="region",
                classifications=(sc(SemanticType.CITY, 0.85),),
                cardinality_ratio=0.08,
            ),
        ),
    )

    assert profile.measure_candidates == ()
    assert [d.name for d in profile.dimension_candidates] == ["category", "region"]


def test_mixed_measures_and_dimensions_role_integration():
    profile = build_role_profile(
        measure_columns=(
            MeasureColumnInput(
                column_name="revenue", classifications=(sc(SemanticType.CURRENCY, 0.88),)
            ),
            MeasureColumnInput(
                column_name="count", classifications=(sc(SemanticType.INTEGER, 0.78),)
            ),
        ),
        dimension_columns=(
            DimensionColumnInput(
                column_name="country",
                classifications=(sc(SemanticType.COUNTRY, 0.93),),
                cardinality_ratio=0.06,
            ),
            DimensionColumnInput(
                column_name="created_at",
                classifications=(sc(SemanticType.DATETIME, 0.89),),
                cardinality_ratio=0.02,
            ),
        ),
    )

    assert [m.name for m in profile.measure_candidates] == ["revenue", "count"]
    assert [d.name for d in profile.dimension_candidates] == ["country", "created_at"]


def test_empty_dataset_role_integration():
    profile = build_role_profile(measure_columns=(), dimension_columns=())
    assert profile.measure_candidates == ()
    assert profile.dimension_candidates == ()


def test_determinism_in_role_pipeline():
    measure_columns = [
        MeasureColumnInput(column_name="sales", classifications=(sc(SemanticType.CURRENCY, 0.80),)),
        MeasureColumnInput(column_name="pct", classifications=(sc(SemanticType.PERCENTAGE, 0.82),)),
    ]
    dimension_columns = [
        DimensionColumnInput(
            column_name="category",
            classifications=(sc(SemanticType.CATEGORY, 0.85),),
            cardinality_ratio=0.12,
        ),
        DimensionColumnInput(
            column_name="country",
            classifications=(sc(SemanticType.COUNTRY, 0.88),),
            cardinality_ratio=0.06,
        ),
    ]

    first = build_role_profile(measure_columns, dimension_columns)
    second = build_role_profile(measure_columns, dimension_columns)
    assert first == second


def test_input_immutability_in_role_pipeline():
    measure_columns = [
        MeasureColumnInput(
            column_name="revenue", classifications=(sc(SemanticType.CURRENCY, 0.90),)
        )
    ]
    dimension_columns = [
        DimensionColumnInput(
            column_name="region",
            classifications=(sc(SemanticType.COUNTRY, 0.88),),
            cardinality_ratio=0.05,
        )
    ]
    original_measure = tuple(measure_columns)
    original_dimension = tuple(dimension_columns)

    profile = build_role_profile(measure_columns, dimension_columns)

    assert tuple(measure_columns) == original_measure
    assert tuple(dimension_columns) == original_dimension
    assert profile.measure_candidates[0].name == "revenue"
    assert profile.dimension_candidates[0].name == "region"


def test_analytics_role_detection_performance():
    measure_columns = [
        MeasureColumnInput(
            column_name=f"m{i}",
            classifications=(
                sc(
                    SemanticType.DECIMAL if i % 2 == 0 else SemanticType.PERCENTAGE,
                    0.80,
                ),
            ),
            cardinality_ratio=0.15,
            null_ratio=0.05,
        )
        for i in range(100)
    ]
    dimension_columns = [
        DimensionColumnInput(
            column_name=f"d{i}",
            classifications=(
                sc(
                    SemanticType.DATE if i % 3 == 0 else SemanticType.CATEGORY,
                    0.82,
                ),
            ),
            cardinality_ratio=0.12,
            null_ratio=0.03,
        )
        for i in range(100)
    ]

    for _ in range(5):
        build_role_profile(measure_columns, dimension_columns)

    runs = 20
    total = 0.0
    for _ in range(runs):
        start = time.perf_counter()
        build_role_profile(measure_columns, dimension_columns)
        total += time.perf_counter() - start

    average = total / runs
    assert average < 0.006
