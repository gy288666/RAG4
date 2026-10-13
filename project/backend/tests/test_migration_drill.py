"""Safety and integrity checks for the opt-in synthetic MySQL restore drill."""
import subprocess
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from scripts import rehearse_index_migration as drill


def test_snapshot_detects_changed_data_and_ignores_row_order():
    engines = [create_engine("sqlite://") for _ in range(2)]
    try:
        for engine, values in zip(engines, ("(1, '中文'), (2, 'second')", "(2, 'second'), (1, '中文')")):
            with engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE evidence (id INTEGER, text TEXT)")
                connection.exec_driver_sql("INSERT INTO evidence VALUES " + values)
        drill.require_equal(drill.snapshot(engines[0]), drill.snapshot(engines[1]))
        with engines[1].begin() as connection:
            connection.exec_driver_sql("UPDATE evidence SET text='changed' WHERE id=1")
        with pytest.raises(RuntimeError, match="snapshot_mismatch"):
            drill.require_equal(drill.snapshot(engines[0]), drill.snapshot(engines[1]))
    finally:
        for engine in engines:
            engine.dispose()


@pytest.mark.parametrize("name", ["rag_high", "rag4_restore_bad_before", "rag4_restore_123456789abc_before;DROP"])
def test_refuses_non_drill_targets(name):
    with pytest.raises(ValueError, match="not_drill_database"):
        drill.require_empty_scratch(SimpleNamespace(url=SimpleNamespace(database=name)))


@pytest.mark.parametrize("tables,views", [(["users"], []), ([], ["existing_view"])])
def test_refuses_nonempty_restore(monkeypatch, tables, views):
    import sqlalchemy
    monkeypatch.setattr(sqlalchemy, "inspect", lambda engine: SimpleNamespace(
        get_table_names=lambda: tables, get_view_names=lambda: views))
    with pytest.raises(ValueError, match="restore_target_not_empty"):
        drill.require_empty_scratch(SimpleNamespace(url=SimpleNamespace(database="rag4_restore_123456789abc_before")))


def test_corrupt_backup_never_invokes_client(tmp_path, monkeypatch):
    path = tmp_path / "backup.sql"
    path.write_bytes(b"altered")
    monkeypatch.setattr(drill, "require_empty_scratch", lambda engine: None)
    monkeypatch.setattr(drill, "run_client", lambda *a, **k: pytest.fail("client must not run"))
    with pytest.raises(ValueError, match="backup_digest_mismatch"):
        drill.restore(None, [], "secret", path, "different-digest")


def test_failed_backup_is_not_published(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        kwargs["stdout"].write(b"partial SQL")
        raise RuntimeError("mysql_client_failed")
    monkeypatch.setattr(drill, "run_client", fail)
    target = tmp_path / "backup.sql"
    with pytest.raises(RuntimeError):
        drill.backup([], "secret", target)
    assert not target.exists()
    assert target.with_suffix(".partial").exists()


def test_client_keeps_password_off_command_and_sanitizes_errors(monkeypatch):
    def run(command, **kwargs):
        assert "secret" not in str(command)
        assert kwargs["env"]["MYSQL_PWD"] == "secret"
        assert kwargs["timeout"] == 120
        assert not kwargs.get("shell")
        return subprocess.CompletedProcess(command, 1, stderr=b"private SQL and secret")
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match="^mysql_client_failed$"):
        drill.run_client(["mysql", "--no-defaults"], "secret")


def test_successful_backup_digest_and_no_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(drill, "run_client", lambda *a, **k: k["stdout"].write(b"synthetic SQL"))
    target = tmp_path / "backup.sql"
    assert drill.backup([], "secret", target) == drill.file_digest(target)
    with pytest.raises(FileExistsError, match="backup_already_exists"):
        drill.backup([], "secret", target)
    assert target.read_bytes() == b"synthetic SQL"
    # Exclusive creation protects any retained partial artifact.
    target = tmp_path / "another.sql"
    target.with_suffix(".partial").write_bytes(b"prior attempt")
    with pytest.raises(FileExistsError):
        drill.backup([], "secret", target)
