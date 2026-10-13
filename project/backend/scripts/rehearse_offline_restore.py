"""Synthetic SQLite + uploads + real Chroma OFFLINE recovery drill; no remote AI."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def worker(mode, root):
    database_url = os.environ.get("RAG4_DRILL_DATABASE_URL")
    if database_url:
        from sqlalchemy.engine import make_url
        import re
        url = make_url(database_url)
        if url.drivername != "mysql+pymysql" or not re.fullmatch(
                r"rag4_restore_[0-9a-f]{12}_(source|after)", url.database or ""):
            raise ValueError("not_drill_database")
    os.environ.update(ENV_FILE=str(root / "absent.env"), DATABASE_URL=database_url or "sqlite:///" + (root / "app.db").as_posix(),
                      CHROMA_DIR=str(root / "chroma"), UPLOAD_DIR=str(root / "uploads"), DEV_MOCK_AI="true")
    from app.core.database import Base, engine, session_scope
    from app import models
    from app.services import index_job_service as jobs, index_build_service as builds, index_version_service as versions
    from app.services.offline_snapshot import digest
    from app.services.vector_store import ChromaVectorStore, VectorRecord, records_digest
    from types import SimpleNamespace

    class Model:
        def __init__(self, **kwargs):
            pass
        def embed_documents(self, texts):
            return [[1., 2., 3.] for text in texts]
        def embed_query(self, text):
            return [1., 2., 3.]
    builds.RemoteEmbeddingAdapter = Model
    versions.RemoteEmbeddingAdapter = Model
    store = ChromaVectorStore(str(root / "chroma"))
    if mode == "seed":
        if database_url:
            from scripts.rehearse_index_migration import require_empty_scratch
            from app.services.schema_preflight import MIGRATIONS, inspect_schema
            require_empty_scratch(engine)
            phase_tables = {name for names in MIGRATIONS.values() for name in names}
            Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in phase_tables])
            migration_dir = Path(__file__).resolve().parents[2] / "docs" / "migrations"
            for filename in MIGRATIONS:
                sql = (migration_dir / filename).read_text(encoding="utf-8")
                sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
                with engine.begin() as connection:
                    for statement in sql.split(";"):
                        if statement.strip():
                            connection.exec_driver_sql(statement)
            if not inspect_schema(engine).ready:
                raise ValueError("schema_gate_failed")
        else:
            Base.metadata.create_all(engine)
        (root / "uploads").mkdir()
        path = root / "uploads" / "paper.md"
        path.write_text("# Offline evidence\n\n中文引用。 Restore preserves source and index provenance.", encoding="utf-8")
        with session_scope() as db:
            user = models.User(email="offline@example.invalid", password_hash="not-a-login-hash")
            db.add(user)
            db.flush()
            user_id = user.id
            db.add(models.Document(id="offline-document", user_id=user_id, file_name=path.name,
                   file_size=path.stat().st_size, local_path=str(path), status="ready"))
        store.add(user_id, [VectorRecord(id="baseline-evidence", text="baseline evidence", embedding=[1., 0., 0.],
                  doc_id="offline-document", user_id=user_id, file_name=path.name, chunk_index=0)])
        prepared = jobs.run_job(user_id, jobs.create_job(user_id, "offline-document", idempotency_key="offline").id)
        if prepared.status != "succeeded":
            raise RuntimeError("prepare_failed")
        spec = builds.EmbeddingSpec(endpoint="https://offline.invalid/v1/embeddings", model_id="fake", version="offline-v1", dimension=3)
        build = builds.create_build(user_id, prepared.chunk_set_id, spec, idempotency_key="offline")
        if builds.run_build(user_id, build.id, api_key="", store=store).status != "validated":
            raise RuntimeError("build_failed")
        version = versions.create_version(user_id, [build.id], store=store)
        versions.switch_version(user_id, version.id, expected_revision=0, store=store)
        expected = {"user_id": user_id, "version_id": version.id, "source_sha256": digest(path),
                    "baseline_sha256": records_digest(store.read_records(user_id, index_version="baseline"))}
        (root / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
    else:
        expected = json.loads((root / "expected.json").read_text(encoding="utf-8"))
        user_id = expected["user_id"]
        path = root / "uploads" / "paper.md"
        if digest(path) != expected["source_sha256"]:
            raise ValueError("source_digest_mismatch")
        # Only the disposable restored DB is remapped. The captured DB is untouched.
        with session_scope() as db:
            document = db.get(models.Document, "offline-document")
            document.local_path = str(path)
        state = versions.active_state(user_id)
        if state != (expected["version_id"], 1):
            raise ValueError("active_pointer_mismatch")
        config = SimpleNamespace(embedding_base_url="https://offline.invalid/v1", embedding_api_key="", retrieval_top_n=5)
        hits = versions.search_active(user_id, "evidence", config, store=store)
        if not hits or {hit.doc_id for hit in hits} != {"offline-document"}:
            raise ValueError("restored_query_failed")
        if records_digest(store.read_records(user_id, index_version="baseline")) != expected["baseline_sha256"]:
            raise ValueError("baseline_digest_mismatch")
        versions.switch_version(user_id, None, expected_revision=1, store=store)
        if not store.search(user_id, [1., 0., 0.], 1):
            raise ValueError("baseline_query_failed")
    engine.dispose()


def run_drill():
    from app.services.offline_snapshot import capture, restore, digest
    root = Path(tempfile.mkdtemp(prefix="rag4_offline_restore_"))
    source, bundle, restored = (root / name for name in ("source", "bundle", "restored"))
    source.mkdir()
    report = {"directory": str(root), "scope": "synthetic_stopped_sqlite_uploads_chroma", "status": "running",
              "started_at": datetime.now(timezone.utc).isoformat()}
    started = perf_counter()
    stage = "seed"
    def child(mode, path):
        environment = os.environ.copy()
        environment.pop("RAG4_DRILL_DATABASE_URL", None)
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", mode, "--root", str(path)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, env=environment)
        if result.returncode:
            raise RuntimeError("worker_failed")
    try:
        child("seed", source)  # Wait for process exit; all writers/Chroma handles are gone.
        stage = "capture"
        pin = capture(source, bundle)
        report["manifest_sha256"] = pin
        stage = "restore"
        restore(bundle, restored, expected_manifest_sha256=pin)
        source_digest = digest(source / "app.db")
        stage = "verify_query_and_deactivate"
        child("verify", restored)
        if digest(source / "app.db") != source_digest:
            raise ValueError("source_database_changed")
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error_stage=stage, error_type=type(error).__name__)
    report["duration_ms"] = round((perf_counter() - started) * 1000)
    (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("seed", "verify"), help=argparse.SUPPRESS)
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.root)
    else:
        outcome = run_drill()
        print(json.dumps(outcome, indent=2))
        raise SystemExit(0 if outcome["status"] == "passed" else 1)
