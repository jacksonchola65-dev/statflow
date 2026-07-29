from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.universal_dataset import (
    UniversalDataset,
    UniversalDatasetColumn,
    UniversalDatasetRow,
    UniversalDatasetVersion,
)


class UniversalDatasetPersistenceService:
    """Persist universal dataset content from row data into the database."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_dataset_from_rows(
        self,
        *,
        owner_id: uuid.UUID,
        name: str,
        description: str | None,
        source_filename: str,
        rows: list[dict[str, Any]],
    ) -> UniversalDataset:
        """Create a universal dataset, its first version, columns, and rows atomically."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Dataset name cannot be empty")

        if not rows:
            raise ValueError("Rows list cannot be empty")

        normalized_rows: list[dict[str, Any]] = []
        column_names: list[str] = []
        seen_columns: set[str] = set()

        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Each row must be a mapping")

            for key in row.keys():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError("Column names must be non-empty strings")
                if key not in seen_columns:
                    seen_columns.add(key)
                    column_names.append(key)

        for row in rows:
            normalized_rows.append(
                {column_name: row.get(column_name) for column_name in column_names}
            )

        transaction_context = (
            self._session.begin_nested()
            if self._session.in_transaction()
            else self._session.begin()
        )

        try:
            async with transaction_context:
                dataset = UniversalDataset(
                    owner_id=owner_id,
                    name=name.strip(),
                    description=description,
                    source_filename=source_filename,
                    status="draft",
                )
                self._session.add(dataset)
                await self._session.flush()

                inferred_types = {
                    column_name: self._infer_column_type(
                        [row.get(column_name) for row in normalized_rows]
                    )
                    for column_name in column_names
                }

                version = UniversalDatasetVersion(
                    dataset_id=dataset.id,
                    version_number=1,
                    row_count=len(normalized_rows),
                    column_count=len(column_names),
                    schema_json={
                        "columns": column_names,
                        "inferred_types": inferred_types,
                    },
                    source_type="csv",
                )
                self._session.add(version)
                await self._session.flush()

                for ordinal_position, column_name in enumerate(column_names):
                    values = [row.get(column_name) for row in normalized_rows]
                    column = UniversalDatasetColumn(
                        dataset_version_id=version.id,
                        name=column_name,
                        original_name=column_name,
                        inferred_type=self._infer_column_type(values),
                        semantic_type=None,
                        ordinal_position=ordinal_position,
                        nullable=any(value is None for value in values),
                    )
                    self._session.add(column)

                for row_number, normalized_row in enumerate(normalized_rows, start=1):
                    row_hash = self._build_row_hash(normalized_row)
                    row = UniversalDatasetRow(
                        dataset_version_id=version.id,
                        row_number=row_number,
                        data_json=normalized_row,
                        row_hash=row_hash,
                    )
                    self._session.add(row)

                await self._session.flush()

                dataset.current_version_id = version.id
                dataset.current_version = version
                await self._session.flush()

                return dataset
        except Exception:
            await self._session.rollback()
            raise

    @staticmethod
    def _infer_column_type(values: list[Any]) -> str:
        if not values:
            return "string"

        filtered = [value for value in values if value is not None]
        if not filtered:
            return "string"

        if all(isinstance(value, bool) for value in filtered):
            return "boolean"

        if all(isinstance(value, int) and not isinstance(value, bool) for value in filtered):
            return "integer"

        if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in filtered):
            return "decimal"

        return "string"

    @staticmethod
    def _build_row_hash(data_json: dict[str, Any]) -> str:
        normalized = json.dumps(
            data_json,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
