"""Read-only Phase 2 schema gate; never applies migrations or repairs drift.

This checks structural compatibility, not data validity, grants, defaults,
backup recovery, or readiness of the rest of the application.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
import re

from sqlalchemy import Boolean, UniqueConstraint, inspect
from sqlalchemy.engine import Engine

from app import models  # noqa: F401
from app.core.database import Base

MIGRATIONS = {
    "002_chunk_preparation.sql": ("document_chunk_sets", "document_index_jobs"),
    "003_index_builds.sql": ("document_index_builds",),
    "004_active_indexes.sql": ("user_index_versions", "user_active_indexes", "user_index_switches"),
    "005_index_rebuilds.sql": ("user_index_rebuilds",),
    "006_rebuild_recovery.sql": ("index_rebuild_recoveries",),
    "007_rebuild_requests.sql": ("index_rebuild_requests",),
}


@dataclass(frozen=True)
class SchemaIssue:
    table: str
    code: str
    subject: str = ""


@dataclass(frozen=True)
class SchemaReport:
    dialect: str
    ready: bool
    migration_files: tuple[str, ...]
    issues: tuple[SchemaIssue, ...]
    duration_ms: int

    def to_dict(self) -> dict:
        return asdict(self)


def _type_name(value, dialect) -> str:
    # MySQL display widths do not change integer storage; unsigned does.
    name = str(value.compile(dialect=dialect)).upper()
    name = re.sub(r"\b(INTEGER|INT)\(\d+\)", "INTEGER", name)
    name = re.sub(r"\bINT\b", "INTEGER", name)
    # Reflection may spell out a charset inherited by the declared column.
    return name.split(" CHARACTER SET ")[0].split(" COLLATE ")[0]


def inspect_schema(engine: Engine) -> SchemaReport:
    """Inspect one explicit engine using metadata reads only.

    Missing Phase 2 tables suggest ordered additive scripts. Other issues
    require review: re-running CREATE IF NOT EXISTS cannot repair them.
    Baseline validation is deliberately limited to FK prerequisite IDs.
    """
    started = perf_counter()
    issues: list[SchemaIssue] = []
    migrations = []
    with engine.connect() as connection:
        inspector = inspect(connection)
        present = set(inspector.get_table_names())
        for migration, names in MIGRATIONS.items():
            if any(name not in present for name in names):
                migrations.append(migration)
        targets = ["users", "documents"] + [n for names in MIGRATIONS.values() for n in names]
        for name in targets:
            if name not in present:
                issues.append(SchemaIssue(name, "missing_table"))
                continue
            table = Base.metadata.tables[name]
            columns = {c["name"]: c for c in inspector.get_columns(name)}
            expected_columns = [table.c.id] if name in ("users", "documents") else table.columns
            for column in expected_columns:
                actual = columns.get(column.name)
                if actual is None:
                    issues.append(SchemaIssue(name, "missing_column", column.name))
                    continue
                expected_type = column.type.dialect_impl(engine.dialect)
                actual_type = actual["type"]
                boolean_alias = (
                    engine.dialect.name == "mysql" and isinstance(column.type, Boolean)
                    and str(actual_type).upper() == "TINYINT" and actual_type.display_width == 1
                    and not actual_type.unsigned
                )
                if not boolean_alias and _type_name(expected_type, engine.dialect) != _type_name(actual_type, engine.dialect):
                    issues.append(SchemaIssue(name, "column_type", column.name))
                if actual["nullable"] != column.nullable:
                    issues.append(SchemaIssue(name, "column_nullable", column.name))
                expected_collation = getattr(expected_type, "collation", None)
                if expected_collation and getattr(actual_type, "collation", None) != expected_collation:
                    issues.append(SchemaIssue(name, "column_collation", column.name))
            if inspector.get_pk_constraint(name)["constrained_columns"] != [c.name for c in table.primary_key.columns]:
                issues.append(SchemaIssue(name, "primary_key"))
            if engine.dialect.name == "mysql":
                options = inspector.get_table_options(name)
                if options.get("mysql_engine", "").lower() != "innodb":
                    issues.append(SchemaIssue(name, "storage_engine"))
                if options.get("mysql_collate") != "utf8mb4_unicode_ci":
                    issues.append(SchemaIssue(name, "table_collation"))
            if name in ("users", "documents"):
                continue
            indexes = inspector.get_indexes(name)
            unique = {tuple(c["column_names"]) for c in inspector.get_unique_constraints(name)}
            unique.update(tuple(i["column_names"]) for i in indexes if i["unique"])
            for constraint in table.constraints:
                if isinstance(constraint, UniqueConstraint):
                    names = tuple(c.name for c in constraint.columns)
                    if names not in unique:
                        issues.append(SchemaIssue(name, "unique_constraint", ",".join(names)))
            for index in table.indexes:
                names = tuple(c.name for c in index.columns)
                if not any(tuple(i["column_names"])[:len(names)] == names for i in indexes):
                    issues.append(SchemaIssue(name, "index", ",".join(names)))
            foreign_keys = inspector.get_foreign_keys(name)
            for fk in table.foreign_key_constraints:
                names = tuple(c.name for c in fk.columns)
                if not any(
                    tuple(f["constrained_columns"]) == names
                    and f["referred_table"] == fk.referred_table.name
                    and tuple(f["referred_columns"]) == tuple(e.column.name for e in fk.elements)
                    and (f.get("options", {}).get("ondelete") or "").upper() == (fk.ondelete or "").upper()
                    and f.get("referred_schema") in (None, inspector.default_schema_name)
                    for f in foreign_keys
                ):
                    issues.append(SchemaIssue(name, "foreign_key", ",".join(names)))
    return SchemaReport(engine.dialect.name, not issues, tuple(migrations), tuple(issues),
                        round((perf_counter() - started) * 1000))
