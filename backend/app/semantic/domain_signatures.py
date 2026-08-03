from app.semantic.domain_models import DomainEvidence
from app.semantic.semantic_types import DatasetDomain, SemanticType

# Immutable domain signature registry: tuple of DomainEvidence entries.
# Conservative signatures per domain; weights in (0.25, 1.0], common types (DATE, IDENTIFIER) use lower weights.
DOMAIN_SIGNATURES = (
    # HEALTHCARE
    DomainEvidence(
        domain=DatasetDomain.HEALTHCARE,
        semantic_type=SemanticType.PERSON,
        weight=0.9,
        description="patient/person identifier",
    ),
    DomainEvidence(
        domain=DatasetDomain.HEALTHCARE,
        semantic_type=SemanticType.AGE,
        weight=0.85,
        description="age is healthcare-relevant",
    ),
    DomainEvidence(
        domain=DatasetDomain.HEALTHCARE,
        semantic_type=SemanticType.CATEGORY,
        weight=0.7,
        description="gender/category classifications common",
    ),
    DomainEvidence(
        domain=DatasetDomain.HEALTHCARE,
        semantic_type=SemanticType.DATE,
        weight=0.3,
        description="dates are common but generic",
    ),
    DomainEvidence(
        domain=DatasetDomain.HEALTHCARE,
        semantic_type=SemanticType.IDENTIFIER,
        weight=0.35,
        description="identifiers present but generic",
    ),
    # FINANCE
    DomainEvidence(
        domain=DatasetDomain.FINANCE,
        semantic_type=SemanticType.CURRENCY,
        weight=0.95,
        description="monetary values indicate finance",
    ),
    DomainEvidence(
        domain=DatasetDomain.FINANCE,
        semantic_type=SemanticType.PERCENTAGE,
        weight=0.8,
        description="rates and percentages common",
    ),
    DomainEvidence(
        domain=DatasetDomain.FINANCE,
        semantic_type=SemanticType.DATE,
        weight=0.3,
        description="transaction dates common but generic",
    ),
    DomainEvidence(
        domain=DatasetDomain.FINANCE,
        semantic_type=SemanticType.IDENTIFIER,
        weight=0.35,
        description="account identifiers",
    ),
    DomainEvidence(
        domain=DatasetDomain.FINANCE,
        semantic_type=SemanticType.ORGANIZATION,
        weight=0.7,
        description="organisation/company present",
    ),
    # EDUCATION
    DomainEvidence(
        domain=DatasetDomain.EDUCATION,
        semantic_type=SemanticType.PERSON,
        weight=0.95,
        description="student/person fields",
    ),
    DomainEvidence(
        domain=DatasetDomain.EDUCATION,
        semantic_type=SemanticType.AGE,
        weight=0.9,
        description="age useful in education contexts",
    ),
    DomainEvidence(
        domain=DatasetDomain.EDUCATION,
        semantic_type=SemanticType.CATEGORY,
        weight=0.8,
        description="demographic or program categories",
    ),
    DomainEvidence(
        domain=DatasetDomain.EDUCATION,
        semantic_type=SemanticType.DATE,
        weight=0.35,
        description="dates (enrolment/graduation)",
    ),
    DomainEvidence(
        domain=DatasetDomain.EDUCATION,
        semantic_type=SemanticType.IDENTIFIER,
        weight=0.4,
        description="student id",
    ),
    # AGRICULTURE
    DomainEvidence(
        domain=DatasetDomain.AGRICULTURE,
        semantic_type=SemanticType.QUANTITY,
        weight=0.9,
        description="yields and quantities",
    ),
    DomainEvidence(
        domain=DatasetDomain.AGRICULTURE,
        semantic_type=SemanticType.DATE,
        weight=0.35,
        description="planting/harvest dates",
    ),
    DomainEvidence(
        domain=DatasetDomain.AGRICULTURE,
        semantic_type=SemanticType.PROVINCE,
        weight=0.6,
        description="regional fields",
    ),
    DomainEvidence(
        domain=DatasetDomain.AGRICULTURE,
        semantic_type=SemanticType.DISTRICT,
        weight=0.6,
        description="local area",
    ),
    DomainEvidence(
        domain=DatasetDomain.AGRICULTURE,
        semantic_type=SemanticType.CATEGORY,
        weight=0.5,
        description="crop/category",
    ),
    # GOVERNMENT
    DomainEvidence(
        domain=DatasetDomain.GOVERNMENT,
        semantic_type=SemanticType.PERSON,
        weight=0.7,
        description="person references in government datasets",
    ),
    DomainEvidence(
        domain=DatasetDomain.GOVERNMENT,
        semantic_type=SemanticType.ORGANIZATION,
        weight=0.7,
        description="organisations/agencies",
    ),
    DomainEvidence(
        domain=DatasetDomain.GOVERNMENT,
        semantic_type=SemanticType.PROVINCE,
        weight=0.6,
        description="regional identifiers",
    ),
    DomainEvidence(
        domain=DatasetDomain.GOVERNMENT,
        semantic_type=SemanticType.DISTRICT,
        weight=0.6,
        description="local districts",
    ),
    DomainEvidence(
        domain=DatasetDomain.GOVERNMENT,
        semantic_type=SemanticType.IDENTIFIER,
        weight=0.35,
        description="gov identifiers",
    ),
    DomainEvidence(
        domain=DatasetDomain.GOVERNMENT,
        semantic_type=SemanticType.DATE,
        weight=0.3,
        description="dates (policy, records)",
    ),
    # RETAIL
    DomainEvidence(
        domain=DatasetDomain.RETAIL,
        semantic_type=SemanticType.CURRENCY,
        weight=0.95,
        description="prices and monetary fields",
    ),
    DomainEvidence(
        domain=DatasetDomain.RETAIL,
        semantic_type=SemanticType.QUANTITY,
        weight=0.85,
        description="stock quantities",
    ),
    DomainEvidence(
        domain=DatasetDomain.RETAIL,
        semantic_type=SemanticType.CATEGORY,
        weight=0.7,
        description="product categories",
    ),
    DomainEvidence(
        domain=DatasetDomain.RETAIL,
        semantic_type=SemanticType.DATE,
        weight=0.35,
        description="sale dates",
    ),
    DomainEvidence(
        domain=DatasetDomain.RETAIL,
        semantic_type=SemanticType.IDENTIFIER,
        weight=0.35,
        description="product identifiers",
    ),
    # MANUFACTURING
    DomainEvidence(
        domain=DatasetDomain.MANUFACTURING,
        semantic_type=SemanticType.QUANTITY,
        weight=0.9,
        description="parts and quantities",
    ),
    DomainEvidence(
        domain=DatasetDomain.MANUFACTURING,
        semantic_type=SemanticType.CATEGORY,
        weight=0.7,
        description="product category",
    ),
    DomainEvidence(
        domain=DatasetDomain.MANUFACTURING,
        semantic_type=SemanticType.DATE,
        weight=0.35,
        description="production dates",
    ),
    DomainEvidence(
        domain=DatasetDomain.MANUFACTURING,
        semantic_type=SemanticType.IDENTIFIER,
        weight=0.35,
        description="serial/part id",
    ),
    DomainEvidence(
        domain=DatasetDomain.MANUFACTURING,
        semantic_type=SemanticType.ORGANIZATION,
        weight=0.6,
        description="manufacturer",
    ),
    # INSURANCE
    DomainEvidence(
        domain=DatasetDomain.INSURANCE,
        semantic_type=SemanticType.PERSON,
        weight=0.9,
        description="insured person",
    ),
    DomainEvidence(
        domain=DatasetDomain.INSURANCE,
        semantic_type=SemanticType.CURRENCY,
        weight=0.9,
        description="claim amounts",
    ),
    DomainEvidence(
        domain=DatasetDomain.INSURANCE,
        semantic_type=SemanticType.PERCENTAGE,
        weight=0.7,
        description="rates and percentages",
    ),
    DomainEvidence(
        domain=DatasetDomain.INSURANCE,
        semantic_type=SemanticType.DATE,
        weight=0.35,
        description="policy/claim dates",
    ),
    DomainEvidence(
        domain=DatasetDomain.INSURANCE,
        semantic_type=SemanticType.IDENTIFIER,
        weight=0.35,
        description="policy id",
    ),
    DomainEvidence(
        domain=DatasetDomain.INSURANCE,
        semantic_type=SemanticType.CATEGORY,
        weight=0.5,
        description="claim category",
    ),
    # TELECOM
    DomainEvidence(
        domain=DatasetDomain.TELECOM,
        semantic_type=SemanticType.PHONE,
        weight=0.95,
        description="subscriber phone numbers",
    ),
    DomainEvidence(
        domain=DatasetDomain.TELECOM,
        semantic_type=SemanticType.PERSON,
        weight=0.7,
        description="customer person",
    ),
    DomainEvidence(
        domain=DatasetDomain.TELECOM,
        semantic_type=SemanticType.ORGANIZATION,
        weight=0.6,
        description="provider organisation",
    ),
    DomainEvidence(
        domain=DatasetDomain.TELECOM,
        semantic_type=SemanticType.DATE,
        weight=0.35,
        description="call/usage dates",
    ),
    DomainEvidence(
        domain=DatasetDomain.TELECOM,
        semantic_type=SemanticType.IDENTIFIER,
        weight=0.35,
        description="subscriber id",
    ),
    DomainEvidence(
        domain=DatasetDomain.TELECOM,
        semantic_type=SemanticType.QUANTITY,
        weight=0.6,
        description="usage quantity",
    ),
    # ENERGY
    DomainEvidence(
        domain=DatasetDomain.ENERGY,
        semantic_type=SemanticType.QUANTITY,
        weight=0.9,
        description="consumption quantities",
    ),
    DomainEvidence(
        domain=DatasetDomain.ENERGY,
        semantic_type=SemanticType.DATE,
        weight=0.35,
        description="metering dates",
    ),
    DomainEvidence(
        domain=DatasetDomain.ENERGY,
        semantic_type=SemanticType.ORGANIZATION,
        weight=0.6,
        description="utility organisation",
    ),
    DomainEvidence(
        domain=DatasetDomain.ENERGY,
        semantic_type=SemanticType.CATEGORY,
        weight=0.5,
        description="energy type/category",
    ),
    DomainEvidence(
        domain=DatasetDomain.ENERGY,
        semantic_type=SemanticType.IDENTIFIER,
        weight=0.35,
        description="meter id",
    ),
    # HR
    DomainEvidence(
        domain=DatasetDomain.HR,
        semantic_type=SemanticType.PERSON,
        weight=0.95,
        description="employee/person fields",
    ),
    DomainEvidence(
        domain=DatasetDomain.HR,
        semantic_type=SemanticType.AGE,
        weight=0.7,
        description="age in HR contexts",
    ),
    DomainEvidence(
        domain=DatasetDomain.HR,
        semantic_type=SemanticType.IDENTIFIER,
        weight=0.35,
        description="employee identifier (staff id)",
    ),
    DomainEvidence(
        domain=DatasetDomain.HR,
        semantic_type=SemanticType.ORGANIZATION,
        weight=0.6,
        description="employer org",
    ),
    DomainEvidence(
        domain=DatasetDomain.HR,
        semantic_type=SemanticType.DATE,
        weight=0.35,
        description="hire dates",
    ),
    DomainEvidence(
        domain=DatasetDomain.HR,
        semantic_type=SemanticType.CURRENCY,
        weight=0.8,
        description="salary fields",
    ),
    # RESEARCH
    DomainEvidence(
        domain=DatasetDomain.RESEARCH,
        semantic_type=SemanticType.DECIMAL,
        weight=0.8,
        description="measurement decimals",
    ),
    DomainEvidence(
        domain=DatasetDomain.RESEARCH,
        semantic_type=SemanticType.INTEGER,
        weight=0.7,
        description="count integers",
    ),
    DomainEvidence(
        domain=DatasetDomain.RESEARCH,
        semantic_type=SemanticType.PERCENTAGE,
        weight=0.6,
        description="statistical percentages",
    ),
    DomainEvidence(
        domain=DatasetDomain.RESEARCH,
        semantic_type=SemanticType.CATEGORY,
        weight=0.5,
        description="experimental category",
    ),
    DomainEvidence(
        domain=DatasetDomain.RESEARCH,
        semantic_type=SemanticType.DATE,
        weight=0.35,
        description="experiment date",
    ),
    DomainEvidence(
        domain=DatasetDomain.RESEARCH,
        semantic_type=SemanticType.TEXT,
        weight=0.4,
        description="notes/text fields",
    ),
)
