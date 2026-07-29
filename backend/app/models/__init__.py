# Import all models here so Alembic's env.py can discover them via Base.metadata.
from app.models.user import User  # noqa: F401
from app.models.province import Province  # noqa: F401
from app.models.district import District  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.indicator import Indicator  # noqa: F401
from app.models.dataset import Dataset  # noqa: F401
from app.models.data_point import DataPoint  # noqa: F401
from app.models.data_source import DataSource, DatasetRegistry  # noqa: F401
from app.models.import_template import ImportTemplate  # noqa: F401
from app.models.ingestion import IngestionJob, DatasetColumn, DatasetRow, IngestionStatus, InferredColumnType  # noqa: F401
from app.models.universal_dataset import UniversalDataset, UniversalDatasetVersion, UniversalDatasetColumn, UniversalDatasetRow  # noqa: F401
from app.models.dashboard import Dashboard  # noqa: F401
from app.models.dashboard_card import DashboardCard, DashboardCardSize, DashboardVisualizationType  # noqa: F401

__all__ = [
    "User", "Province", "District", "Category", "Indicator",
    "Dataset", "DataPoint", "DataSource", "DatasetRegistry",
    "IngestionJob", "DatasetColumn", "DatasetRow", "Dashboard", "DashboardCard",
    "UniversalDataset", "UniversalDatasetVersion", "UniversalDatasetColumn", "UniversalDatasetRow",
    "DashboardCardSize", "DashboardVisualizationType",
    "IngestionStatus", "InferredColumnType",
]
