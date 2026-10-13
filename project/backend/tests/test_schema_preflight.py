"""Schema gate tests use separate disposable databases, never application data."""
import pytest
from sqlalchemy import MetaData, UniqueConstraint, create_engine, event

from app.core.database import Base
from app.services.schema_preflight import MIGRATIONS, inspect_schema


@pytest.fixture
def schema_engine():
    engine = create_engine("sqlite://")
    yield engine
    engine.dispose()


def test_complete_schema_is_read_only(schema_engine):
    Base.metadata.create_all(schema_engine)
    statements = []
    event.listen(schema_engine, "before_cursor_execute",
                 lambda conn, cursor, statement, params, context, many: statements.append(statement))
    result = inspect_schema(schema_engine)
    assert result.ready and not result.issues and not result.migration_files
    assert result.duration_ms >= 0
    assert all(s.lstrip().upper().startswith(("SELECT", "PRAGMA")) for s in statements)


def test_empty_database_lists_ordered_migrations(schema_engine):
    result = inspect_schema(schema_engine)
    assert not result.ready
    assert result.migration_files == tuple(MIGRATIONS)
    assert {i.table for i in result.issues} >= {"users", "documents", "index_rebuild_recoveries"}


def test_partially_applied_migration(schema_engine):
    Base.metadata.create_all(schema_engine, tables=[Base.metadata.tables[n] for n in
                              ("users", "documents", "document_chunk_sets")])
    result = inspect_schema(schema_engine)
    assert result.migration_files[0] == "002_chunk_preparation.sql"
    assert not any(i.table == "document_chunk_sets" for i in result.issues)


@pytest.mark.parametrize("definition,code,subject", [
    ("user_id INTEGER NOT NULL PRIMARY KEY, version_id VARCHAR(64)", "missing_column", "revision"),
    ("user_id INTEGER NOT NULL PRIMARY KEY, version_id VARCHAR(8), revision INTEGER NOT NULL", "column_type", "version_id"),
    ("user_id INTEGER NOT NULL PRIMARY KEY, version_id VARCHAR(64), revision INTEGER", "column_nullable", "revision"),
    ("user_id INTEGER NOT NULL, version_id VARCHAR(64), revision INTEGER NOT NULL", "primary_key", ""),
    ("user_id INTEGER NOT NULL PRIMARY KEY, version_id VARCHAR(64), revision INTEGER NOT NULL", "foreign_key", "user_id"),
])
def test_existing_drift_is_not_claimed_repairable(schema_engine, definition, code, subject):
    with schema_engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE TABLE user_active_indexes ({definition})")
    Base.metadata.create_all(schema_engine)
    result = inspect_schema(schema_engine)
    assert not result.ready and not result.migration_files
    assert any(i.table == "user_active_indexes" and i.code == code and i.subject == subject for i in result.issues)


def test_missing_unique_and_index(schema_engine):
    # Clone only columns/PK/FKs, deliberately omit the ORM unique key and index.
    from sqlalchemy.schema import CreateTable
    table = Base.metadata.tables["document_index_jobs"].to_metadata(MetaData())
    for constraint in list(table.constraints):
        if isinstance(constraint, UniqueConstraint):
            table.constraints.remove(constraint)
    for name in ("users", "documents"):
        Base.metadata.tables[name].to_metadata(table.metadata)
    with schema_engine.begin() as connection:
        connection.execute(CreateTable(table))
    Base.metadata.create_all(schema_engine)
    codes = {i.code for i in inspect_schema(schema_engine).issues if i.table == table.name}
    assert codes == {"unique_constraint", "index"}


def test_mysql_reflection_charset_and_integer_display_width():
    from sqlalchemy import String
    from sqlalchemy.dialects import mysql
    from app.services.schema_preflight import _type_name
    dialect = mysql.dialect()
    assert _type_name(String(64, collation="utf8mb4_bin"), dialect) == _type_name(
        mysql.VARCHAR(64, charset="utf8mb4", collation="utf8mb4_bin"), dialect)
    assert _type_name(mysql.INTEGER(display_width=11), dialect) == "INTEGER"
    assert _type_name(mysql.INTEGER(unsigned=True), dialect) != "INTEGER"
