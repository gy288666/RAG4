from pathlib import Path
import shutil

import pytest

from app.services import offline_snapshot as snapshots


@pytest.fixture
def captured(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "uploads").mkdir()
    (source / "uploads" / "中文.md").write_text("中文证据", encoding="utf-8")
    (source / "empty").mkdir()
    bundle = tmp_path / "bundle"
    pin = snapshots.capture(source, bundle)
    return source, bundle, pin


def test_round_trip_preserves_bytes_and_empty_directories(captured, tmp_path):
    source, bundle, pin = captured
    target = tmp_path / "restored"
    snapshots.restore(bundle, target, expected_manifest_sha256=pin)
    assert snapshots.inventory(source) == snapshots.inventory(target)
    assert (target / "empty").is_dir()


@pytest.mark.parametrize("change", ["alter", "missing", "extra", "manifest"])
def test_corrupt_bundle_rejected_before_destination_creation(captured, tmp_path, change):
    _, bundle, pin = captured
    payload = bundle / "payload" / "uploads" / "中文.md"
    if change == "alter":
        payload.write_bytes(b"wrong")
    elif change == "missing":
        payload.unlink()
    elif change == "extra":
        (bundle / "payload" / "unexpected").write_bytes(b"extra")
    else:
        (bundle / "manifest.json").write_text('{}', encoding="utf-8")
    target = tmp_path / "restored"
    with pytest.raises(ValueError, match="integrity|digest"):
        snapshots.restore(bundle, target, expected_manifest_sha256=pin)
    assert not target.exists()


def test_existing_destination_untouched(captured, tmp_path):
    _, bundle, pin = captured
    target = tmp_path / "existing"
    target.mkdir()
    (target / "keep").write_bytes(b"old data")
    with pytest.raises(FileExistsError):
        snapshots.restore(bundle, target, expected_manifest_sha256=pin)
    assert (target / "keep").read_bytes() == b"old data"


def test_nested_destination_rejected(captured):
    source, _, _ = captured
    with pytest.raises(ValueError, match="overlapping"):
        snapshots.capture(source, source / "nested")


def test_mutating_source_does_not_publish_manifest(captured, tmp_path, monkeypatch):
    source, _, _ = captured
    original = shutil.copytree
    def copy(*args, **kwargs):
        result = original(*args, **kwargs)
        (source / "late").write_bytes(b"late write")
        return result
    monkeypatch.setattr(shutil, "copytree", copy)
    target = tmp_path / "interrupted"
    with pytest.raises(ValueError, match="source_changed"):
        snapshots.capture(source, target)
    assert not (target / "manifest.json").exists()


def test_link_entry_is_rejected_without_following(captured, monkeypatch):
    source, _, _ = captured
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p.name == "中文.md" or original(p))
    with pytest.raises(ValueError, match="linked_entry"):
        snapshots.inventory(source)


def test_real_chroma_process_exit_restore_query_and_baseline():
    from scripts.rehearse_offline_restore import run_drill
    report = run_drill()
    assert report["status"] == "passed", report
    assert report["manifest_sha256"]
