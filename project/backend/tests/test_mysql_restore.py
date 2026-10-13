"""Combined recovery safety contracts, offline and without a MySQL dependency."""
import subprocess

import pytest
from sqlalchemy import URL

from app.services import offline_snapshot as files
from scripts import rehearse_mysql_restore as drill


@pytest.fixture
def bundle(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "database.sql").write_bytes(b"synthetic SQL")
    (source / "evidence.md").write_bytes(b"source evidence")
    package = tmp_path / "bundle"
    return package, files.capture(source, package), tmp_path / "restored"


@pytest.mark.parametrize("changed", ["database.sql", "evidence.md", "../manifest.json"])
def test_corruption_prevents_sql_import(bundle, monkeypatch, changed):
    package, pin, target = bundle
    (package / "payload" / changed).write_bytes(b"corrupted")
    monkeypatch.setattr(drill.relational, "require_empty_scratch", lambda engine: None)
    monkeypatch.setattr(drill.relational, "restore", lambda *a: pytest.fail("must not import"))
    with pytest.raises(ValueError):
        drill.restore_pair(package, target, pin, None, [], "secret")
    assert not target.exists()


def test_occupied_database_prevents_file_restore(bundle, monkeypatch):
    package, pin, target = bundle
    def occupied(engine):
        raise ValueError("restore_target_not_empty")
    monkeypatch.setattr(drill.relational, "require_empty_scratch", occupied)
    with pytest.raises(ValueError, match="not_empty"):
        drill.restore_pair(package, target, pin, None, [], "secret")
    assert not target.exists()


def test_import_uses_dump_digest_from_pinned_manifest(bundle, monkeypatch):
    package, pin, target = bundle
    monkeypatch.setattr(drill.relational, "require_empty_scratch", lambda engine: None)
    calls = []
    def restored(engine, command, password, path, expected):
        assert path == target / "database.sql"
        assert files.digest(path) == expected
        assert (target / "evidence.md").read_bytes() == b"source evidence"
        calls.append(path)
    monkeypatch.setattr(drill.relational, "restore", restored)
    drill.restore_pair(package, target, pin, None, [], "secret")
    assert len(calls) == 1


def test_failed_sql_import_retains_files_without_success(bundle, monkeypatch):
    package, pin, target = bundle
    monkeypatch.setattr(drill.relational, "require_empty_scratch", lambda engine: None)
    def fail(*args):
        raise RuntimeError("import_failed")
    monkeypatch.setattr(drill.relational, "restore", fail)
    with pytest.raises(RuntimeError, match="import_failed"):
        drill.restore_pair(package, target, pin, None, [], "secret")
    assert (target / "database.sql").is_file()
    files.verify(package, pin)


def test_child_credentials_not_in_arguments_and_error_is_sanitized(monkeypatch, tmp_path):
    def run(command, **kwargs):
        assert "private-password" not in str(command)
        assert "private-password" in kwargs["env"]["RAG4_DRILL_DATABASE_URL"]
        return subprocess.CompletedProcess(command, 1, stderr=b"private-password")
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match="^worker_failed$"):
        drill.child("seed", tmp_path, URL.create("mysql+pymysql", username="test", password="private-password"))
