"""Opt-in real MySQL + SiliconFlow + Chroma smoke test with synthetic data.

Run from backend with RAG4_TEST_MYSQL_PASSWORD set and --credentials-file PATH.
Creates and retains a uniquely named scratch database; never migrates an existing
business database and never executes DROP DATABASE. Prints no credentials.
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import pymysql
    from sqlalchemy import URL

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", required=True)
    parser.add_argument("--embedding-model", default="Qwen/Qwen3-Embedding-8B")
    parser.add_argument("--embedding-dimension", type=int, default=4096)
    args = parser.parse_args()
    raw = Path(args.credentials_file).read_text(encoding="utf-8-sig")
    match = re.search(r"sk-[A-Za-z0-9_-]{10,}", raw)
    if not match:
        raise ValueError("Credentials file contains no API key")
    password = os.environ["RAG4_TEST_MYSQL_PASSWORD"]
    host = os.environ.get("RAG4_TEST_MYSQL_HOST", "127.0.0.1")
    port = int(os.environ.get("RAG4_TEST_MYSQL_PORT", "3307"))
    user = os.environ.get("RAG4_TEST_MYSQL_USER", "root")
    database = "rag4_staging_validation_" + uuid.uuid4().hex[:12]
    directory = Path(tempfile.mkdtemp(prefix="rag4_staging_validation_"))
    # Name is generated internally and contains only safe ASCII identifiers.
    connection = pymysql.connect(host=host, port=port, user=user, password=password, connect_timeout=5)
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.execute("SELECT VERSION()")
        server_version = cursor.fetchone()[0]
    connection.close()
    print(json.dumps({"scratch_database": database, "mysql_server": server_version, "mysql_port": port,
                      "scratch_directory": str(directory)}), flush=True)

    os.environ["DATABASE_URL"] = URL.create("mysql+pymysql", username=user, password=password,
        host=host, port=port, database=database, query={"charset": "utf8mb4"}).render_as_string(hide_password=False)
    os.environ["ENV_FILE"] = str(directory / "nonexistent.env")
    os.environ["DEV_MOCK_AI"] = "false"
    from app.core.database import engine, session_scope
    from app.models.user import User
    from app.models.document import Document
    from app.models.usage_log import UsageLog
    from app.services import index_job_service as jobs, index_build_service as builds
    from app.services import index_version_service as versions
    from app.services import index_rebuild_service as rebuilds
    from app.services.vector_store import ChromaVectorStore, VectorRecord

    # Only pre-existing parent tables; the candidate tables come from actual SQL.
    User.__table__.create(engine)
    Document.__table__.create(engine)
    UsageLog.__table__.create(engine)
    migration_dir = Path(__file__).resolve().parents[2] / "docs" / "migrations"
    with engine.begin() as conn:
        for _ in range(2):
            for filename in ("002_chunk_preparation.sql", "003_index_builds.sql", "004_active_indexes.sql", "005_index_rebuilds.sql", "006_rebuild_recovery.sql", "007_rebuild_requests.sql"):
                sql = (migration_dir / filename).read_text(encoding="utf-8")
                sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
                for statement in sql.split(";"):
                    if statement.strip():
                        conn.exec_driver_sql(statement)

    source = directory / "synthetic.md"
    source.write_text("# Synthetic smoke test\n\nRetrieval finds relevant evidence before generation.", encoding="utf-8")
    with session_scope() as db:
        owner = User(email="synthetic@example.invalid", password_hash="not-a-login-hash")
        db.add(owner)
        db.flush()
        user_id = owner.id
        db.add(Document(id="synthetic-document", user_id=user_id, file_name=source.name,
                        file_size=source.stat().st_size, local_path=str(source), status="ready"))
    prepared = jobs.run_job(user_id, jobs.create_job(user_id, "synthetic-document", idempotency_key="prepare").id)
    assert prepared.status == "succeeded", prepared.error_code
    store = ChromaVectorStore(str(directory / "chroma"))
    baseline = VectorRecord(id="baseline", text="Original synthetic evidence", embedding=[1., 0.],
        doc_id="synthetic-document", user_id=user_id, file_name=source.name, chunk_index=0)
    store.add(user_id, [baseline])
    spec = builds.EmbeddingSpec(endpoint="https://api.siliconflow.cn/v1/embeddings",
        model_id=args.embedding_model, version="siliconflow-smoke-v1", dimension=args.embedding_dimension)
    candidate = builds.create_build(user_id, prepared.chunk_set_id, spec, idempotency_key="candidate")
    result = builds.run_build(user_id, candidate.id, api_key=match.group(), store=store)
    print(json.dumps({"stage": "candidate", "status": result.status,
                      "error_stage": result.error_stage, "error_code": result.error_code}), flush=True)
    assert result.status == "validated", (result.error_stage, result.error_code)
    assert store.read_records(user_id, index_version="baseline") == [baseline]
    assert builds.run_build(user_id, candidate.id, api_key="unused", store=store).status == "validated"
    manifest = json.loads(result.manifest_json)
    from types import SimpleNamespace
    config = SimpleNamespace(embedding_base_url="https://api.siliconflow.cn/v1",
                             embedding_api_key=match.group(), retrieval_top_n=5)
    v1 = versions.create_version(user_id, [candidate.id], store=store)
    v2 = versions.create_version(user_id, [candidate.id], store=store)
    versions.switch_version(user_id, v1.id, expected_revision=0, store=store)
    hits = versions.search_active(user_id, "What does retrieval find?", config, store=store)
    assert hits and all(h.doc_id == "synthetic-document" for h in hits)
    versions.switch_version(user_id, v2.id, expected_revision=1, store=store)
    versions.switch_version(user_id, v1.id, expected_revision=2, store=store)
    assert versions.active_state(user_id) == (v1.id, 3)
    versions.switch_version(user_id, None, expected_revision=3, store=store)
    assert versions.search_active(user_id, "evidence", config, store=store) is None
    batch = rebuilds.create_rebuild(user_id, spec)
    batch = rebuilds.run_rebuild(user_id, batch.id, api_key=match.group(), store=store)
    assert batch.status == "ready", batch.error_code
    assert versions.active_state(user_id) == (None, 4)
    versions.switch_version(user_id, batch.version_id, expected_revision=batch.base_revision, store=store)
    versions.switch_version(user_id, None, expected_revision=5, store=store)
    # Simulate a process interruption after committed checkpoints in scratch DB.
    # Recovery must reuse real vectors and require no further model call.
    from app.models.index_rebuild import IndexRebuild
    interrupted = rebuilds.create_rebuild(user_id, spec)
    with session_scope() as db:
        interrupted_row = db.get(IndexRebuild, interrupted.id)
        interrupted_row.status = "running"
        interrupted_row.attempt = 1
        interrupted_row.checkpoints_json = batch.checkpoints_json
    successor = rebuilds.recover_rebuild(user_id, interrupted.id)
    successor = rebuilds.run_rebuild(user_id, successor.id, api_key="", store=store)
    assert successor.status == "ready"
    assert rebuilds.get_rebuild(user_id, interrupted.id).status == "cancelled"
    print(json.dumps({"migration_replay": "passed", "prepare": prepared.status,
        "build": result.status, "dimension": manifest["dimension"], "records": manifest["record_count"],
        "duration_ms": result.duration_ms, "baseline_preserved": True, "database_retained": True,
        "activation_search_rollback": "passed", "batch_rebuild": batch.status,
        "interrupted_recovery": successor.status}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Raw exceptions from clients may contain connection or request details.
        print(json.dumps({"result": "failed", "error_type": type(exc).__name__,
                          "cause_type": type(exc.__cause__).__name__ if exc.__cause__ else None}), flush=True)
        sys.exit(1)
