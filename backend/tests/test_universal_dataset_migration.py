from sqlalchemy import text


async def test_universal_dataset_tables_exist(db_session) -> None:
    result = await db_session.execute(
        text("SELECT to_regclass('public.universal_dataset_versions')")
    )
    assert result.scalar() is not None

    result = await db_session.execute(
        text("SELECT to_regclass('public.universal_dataset_columns')")
    )
    assert result.scalar() is not None

    result = await db_session.execute(text("SELECT to_regclass('public.universal_datasets')"))
    assert result.scalar() is not None


async def test_universal_dataset_constraints_exist(db_session) -> None:
    constraints = await db_session.execute(
        text(
            """
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = 'public.universal_dataset_versions'::regclass
              AND conname = 'uq_universal_dataset_versions_dataset_version'
            """
        )
    )
    assert any(
        row[0] == "uq_universal_dataset_versions_dataset_version" for row in constraints.fetchall()
    )


async def test_universal_dataset_rows_constraints_and_indexes_exist(db_session) -> None:
    table_exists = await db_session.execute(
        text("SELECT to_regclass('public.universal_dataset_rows')")
    )
    assert table_exists.scalar() is not None

    constraints = await db_session.execute(
        text(
            """
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = 'public.universal_dataset_rows'::regclass
              AND conname = 'uq_universal_dataset_rows_version_row_number'
            """
        )
    )
    assert any(
        row[0] == "uq_universal_dataset_rows_version_row_number" for row in constraints.fetchall()
    )

    indexes = await db_session.execute(
        text(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'universal_dataset_rows'
            """
        )
    )
    index_names = {row[0] for row in indexes.fetchall()}
    assert "ix_universal_dataset_rows_dataset_version_id" in index_names
    assert "ix_universal_dataset_rows_dataset_version_id_row_number" in index_names
