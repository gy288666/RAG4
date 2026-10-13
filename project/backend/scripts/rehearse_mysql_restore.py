"""Combined synthetic MySQL + uploads + Chroma recovery; creates NEW databases only."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import rehearse_index_migration as relational


def child(mode, root, url):
    environment = os.environ.copy()
    environment["RAG4_DRILL_DATABASE_URL"] = url.render_as_string(hide_password=False)
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("rehearse_offline_restore.py")),
                             "--worker", mode, "--root", str(root)], env=environment,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if result.returncode:
        raise RuntimeError("worker_failed")


def restore_pair(bundle, destination, pin, engine, command, password):
    """Reject invalid files/occupied DB before importing any SQL; no live pointer edits."""
    from app.services import offline_snapshot as files
    relational.require_empty_scratch(engine)
    manifest = files.verify(bundle, pin)
    expected = manifest["files"].get("database.sql")
    if not isinstance(expected, dict):
        raise ValueError("missing_database_dump")
    files.restore(bundle, destination, expected_manifest_sha256=pin)
    relational.restore(engine, command, password, destination / "database.sql", expected["sha256"])


def run_drill(host="127.0.0.1", port=3307, user="root"):
    password = os.environ.get("RAG4_TEST_MYSQL_PASSWORD")
    dump_client, sql_client = shutil.which("mysqldump"), shutil.which("mysql")
    if password is None or not dump_client or not sql_client:
        return {"status": "failed", "error_stage": "prerequisites"}
    from sqlalchemy import URL, create_engine
    from app.services import offline_snapshot as files
    from app.services.schema_preflight import inspect_schema, MIGRATIONS
    directory = Path(tempfile.mkdtemp(prefix="rag4_mysql_restore_"))
    source, bundle, restored = (directory / key for key in ("source", "bundle", "restored"))
    source.mkdir()
    prefix = "rag4_restore_" + uuid.uuid4().hex[:12]
    names = {key: prefix + "_" + key for key in ("source", "after")}
    report = {"status": "running", "directory": str(directory), "databases": names,
              "scope": "synthetic_stopped_mysql_uploads_chroma", "stages": [],
              "started_at": datetime.now(timezone.utc).isoformat()}
    started = perf_counter()
    stage = "create_databases"
    engines = {}
    try:
        url = URL.create("mysql+pymysql", username=user, password=password, host=host, port=port,
                         query={"charset": "utf8mb4"})
        server = create_engine(url, connect_args={"connect_timeout": 10})
        try:
            with server.connect() as connection:
                report["mysql_version"] = connection.exec_driver_sql("SELECT VERSION()").scalar()
                for key, name in names.items():
                    connection.exec_driver_sql(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                    engines[key] = create_engine(url.set(database=name))
        finally:
            server.dispose()
        stage = "seed_and_stop_writers"
        child("seed", source, url.set(database=names["source"]))
        report["stages"].append(stage)
        before = relational.snapshot(engines["source"])
        stage = "dump_and_capture"
        options = ["--no-defaults", "--protocol=TCP", f"--host={host}", f"--port={port}",
                   f"--user={user}", "--default-character-set=utf8mb4"]
        report["dump_sha256"] = relational.backup([dump_client, *options, "--single-transaction",
            "--skip-lock-tables", "--no-tablespaces", "--set-gtid-purged=OFF", "--skip-add-drop-table",
            "--hex-blob", names["source"]], password, source / "database.sql")
        pin = files.capture(source, bundle)
        report["manifest_sha256"] = pin
        source_files = files.inventory(source)
        migration_dir = Path(__file__).resolve().parents[2] / "docs" / "migrations"
        report["migration_sha256"] = {name: files.digest(migration_dir / name) for name in MIGRATIONS}
        relational.require_equal(relational.snapshot(engines["source"]), before)
        report["stages"].append(stage)
        stage = "restore_pair"
        restore_pair(bundle, restored, pin, engines["after"], [sql_client, *options, names["after"]], password)
        relational.require_equal(relational.snapshot(engines["after"]), before)
        if not inspect_schema(engines["after"]).ready:
            raise ValueError("restored_schema_invalid")
        report["stages"].append(stage)
        stage = "verify_query_and_baseline"
        child("verify", restored, url.set(database=names["after"]))
        report["stages"].append(stage)
        stage = "verify_source_unchanged"
        relational.require_equal(relational.snapshot(engines["source"]), before)
        relational.require_equal(files.inventory(source), source_files)
        report["stages"].append(stage)
        report.update(status="passed", restored_before_verification=before)
    except Exception as error:
        report.update(status="failed", error_stage=stage, error_type=type(error).__name__)
    finally:
        for engine in engines.values():
            engine.dispose()
        report["duration_ms"] = round((perf_counter() - started) * 1000)
        (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3307)
    parser.add_argument("--user", default="root")
    args = parser.parse_args()
    report = run_drill(args.host, args.port, args.user)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "passed" else 1)
