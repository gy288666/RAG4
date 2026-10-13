"""Opt-in relational backup/restore drill using NEW synthetic databases only.

Never accepts a target database, drops a database, or changes business settings.
All three databases, dumps and a sanitized report are retained for inspection.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot(engine) -> dict:
    """Content fingerprints for all rows; independent of database/row ordering."""
    from sqlalchemy import MetaData, select
    metadata = MetaData()
    metadata.reflect(bind=engine)
    result = {}
    with engine.connect() as connection:
        for table in metadata.sorted_tables:
            rows = sorted(json.dumps(list(row), ensure_ascii=False, default=str,
                                     separators=(",", ":"))
                          for row in connection.execute(select(table)))
            result[table.name] = {"rows": len(rows), "sha256": hashlib.sha256(
                json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()}
    return result


def require_equal(actual, expected):
    if actual != expected:
        raise RuntimeError("snapshot_mismatch")


def require_empty_scratch(engine):
    from sqlalchemy import inspect
    if not re.fullmatch(r"rag4_restore_[0-9a-f]{12}_(source|before|after)", engine.url.database or ""):
        raise ValueError("not_drill_database")
    inspector = inspect(engine)
    if inspector.get_table_names() or inspector.get_view_names():
        raise ValueError("restore_target_not_empty")


def run_client(command, password, *, stdin=None, stdout=None):
    environment = os.environ.copy()
    environment["MYSQL_PWD"] = password
    result = subprocess.run(command, stdin=stdin, stdout=stdout or subprocess.PIPE,
                            stderr=subprocess.PIPE, env=environment, timeout=120, check=False)
    if result.returncode:
        # Do not expose stderr: client errors can include credentials/SQL rows.
        raise RuntimeError("mysql_client_failed")


def backup(command, password, destination):
    if destination.exists():
        raise FileExistsError("backup_already_exists")
    partial = destination.with_suffix(".partial")
    with partial.open("xb") as stream:
        run_client(command, password, stdout=stream)
    if partial.stat().st_size == 0:
        raise RuntimeError("empty_backup")
    partial.rename(destination)
    return file_digest(destination)


def restore(engine, command, password, path, expected_digest):
    require_empty_scratch(engine)
    if file_digest(path) != expected_digest:
        raise ValueError("backup_digest_mismatch")
    with path.open("rb") as stream:
        run_client(command, password, stdin=stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3307)
    parser.add_argument("--user", default="root")
    args = parser.parse_args()
    password = os.environ.get("RAG4_TEST_MYSQL_PASSWORD")
    dump_client, sql_client = shutil.which("mysqldump"), shutil.which("mysql")
    if password is None or not dump_client or not sql_client:
        print(json.dumps({"status": "failed", "stage": "prerequisites"}))
        return 2
    directory = Path(tempfile.mkdtemp(prefix="rag4_restore_"))
    prefix = "rag4_restore_" + uuid.uuid4().hex[:12]
    names = {key: prefix + "_" + key for key in ("source", "before", "after")}
    report = {"status": "running", "directory": str(directory), "databases": names,
              "scope": "synthetic_relational_only", "stages": [],
              "started_at": datetime.now(timezone.utc).isoformat()}
    started = perf_counter()
    stage = "create_scratch"
    engines = {}
    try:
        from sqlalchemy import create_engine, URL
        server_url = URL.create("mysql+pymysql", username=args.user, password=password,
                                host=args.host, port=args.port, query={"charset": "utf8mb4"})
        server = create_engine(server_url)
        try:
            with server.connect() as connection:
                report["mysql_version"] = connection.exec_driver_sql("SELECT VERSION()").scalar()
                for key, name in names.items():
                    connection.exec_driver_sql(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                    engines[key] = create_engine(server_url.set(database=name))
        finally:
            server.dispose()
        os.environ["ENV_FILE"] = str(directory / "absent.env")
        os.environ["DATABASE_URL"] = server_url.set(database=names["source"]).render_as_string(hide_password=False)
        from app import models
        from app.core.database import Base, engine as app_engine
        from app.services.schema_preflight import MIGRATIONS, inspect_schema
        from app.services import index_job_service as jobs
        from sqlalchemy.orm import Session
        phase_tables = {n for tables in MIGRATIONS.values() for n in tables}
        Base.metadata.create_all(engines["source"], tables=[t for t in Base.metadata.sorted_tables if t.name not in phase_tables])
        source = directory / "synthetic.md"
        source.write_text("# Restore drill\n\nEvidence survives backup and migration. 中文引用。", encoding="utf-8")
        with Session(engines["source"]) as session:
            owner = models.User(email="restore@example.invalid", password_hash="not-a-login-hash")
            session.add(owner)
            session.flush()
            owner_id = owner.id
            session.add(models.Document(id="restore-document", user_id=owner_id, file_name=source.name,
                        file_size=source.stat().st_size, local_path=str(source), status="ready"))
            session.commit()
        options = ["--no-defaults", "--protocol=TCP", f"--host={args.host}", f"--port={args.port}",
                   f"--user={args.user}", "--default-character-set=utf8mb4"]

        def dump(key, filename):
            return backup([dump_client, *options, "--single-transaction", "--skip-lock-tables",
                           "--no-tablespaces", "--set-gtid-purged=OFF", "--skip-add-drop-table", "--hex-blob",
                           names[key]], password, directory / filename)

        migration_dir = Path(__file__).resolve().parents[2] / "docs" / "migrations"
        report["migration_sha256"] = {name: file_digest(migration_dir / name) for name in MIGRATIONS}
        def migrate(key):
            for filename in MIGRATIONS:
                sql = (migration_dir / filename).read_text(encoding="utf-8")
                sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
                with engines[key].begin() as connection:
                    for statement in sql.split(";"):
                        if statement.strip():
                            connection.exec_driver_sql(statement)
            if not inspect_schema(engines[key]).ready:
                raise RuntimeError("schema_gate_failed")

        stage = "backup_before"
        before = snapshot(engines["source"])
        report["before_dump_sha256"] = dump("source", "before.sql")
        report["stages"].append(stage)
        stage = "migrate_source"
        migrate("source")
        require_equal({k: v for k, v in snapshot(engines["source"]).items() if k in before}, before)
        job = jobs.run_job(owner_id, jobs.create_job(owner_id, "restore-document", idempotency_key="restore-drill").id)
        if job.status != "succeeded":
            raise RuntimeError("preparation_failed")
        report["stages"].append(stage)
        stage = "backup_after"
        after = snapshot(engines["source"])
        report["after_dump_sha256"] = dump("source", "after.sql")
        report["stages"].append(stage)
        for key, expected in (("before", before), ("after", after)):
            stage = "restore_" + key
            restore(engines[key], [sql_client, *options, names[key]], password,
                    directory / (key + ".sql"), report[key + "_dump_sha256"])
            require_equal(snapshot(engines[key]), expected)
            report["stages"].append(stage)
        stage = "verify_restored_schema"
        if not inspect_schema(engines["after"]).ready:
            raise RuntimeError("restored_schema_invalid")
        stage = "remigrate_before"
        migrate("before")
        require_equal({k: v for k, v in snapshot(engines["before"]).items() if k in before}, before)
        stage = "replay_after"
        migrate("after")
        require_equal(snapshot(engines["after"]), after)
        report.update(status="passed", before=before, after=after)
        report["stages"].extend(["verify_restored_schema", "remigrate_before", "replay_after"])
        app_engine.dispose()
    except Exception as error:
        report.update(status="failed", error_stage=stage, error_type=type(error).__name__)
    finally:
        for engine in engines.values():
            engine.dispose()
        report["duration_ms"] = round((perf_counter() - started) * 1000)
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
