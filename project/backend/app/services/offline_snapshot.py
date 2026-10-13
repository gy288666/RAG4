"""Integrity-checked directory snapshots for STOPPED, trusted local workloads.

The caller must stop writers before capture and keep the source quiescent.
This module cannot establish cross-database consistency or stop an application.
Failed destinations are retained, never activated or used to overwrite old data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def inventory(root: Path) -> dict:
    """Only regular files/directories; never follow symlinks or Windows junctions."""
    if root.is_symlink() or (hasattr(root, "is_junction") and root.is_junction()):
        raise ValueError("linked_root")
    if not root.is_dir():
        raise ValueError("missing_source")
    result = {}
    def visit(directory):
        for path in sorted(directory.iterdir()):
            # FILE_ATTRIBUTE_REPARSE_POINT covers junctions on Python 3.11.
            if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
                raise ValueError("linked_entry")
            relative = path.relative_to(root).as_posix()
            if path.is_dir():
                result[relative + "/"] = None
                visit(path)
            elif path.is_file():
                result[relative] = {"size": path.stat().st_size, "sha256": digest(path)}
            else:
                raise ValueError("unsupported_entry")
    if getattr(root.lstat(), "st_file_attributes", 0) & 0x400:
        raise ValueError("linked_root")
    visit(root)
    return result


def _separate(source: Path, target: Path):
    a, b = source.resolve(), target.resolve()
    if a == b or a in b.parents or b in a.parents:
        raise ValueError("overlapping_paths")
    if target.exists() or target.is_symlink():
        raise FileExistsError("destination_exists")


def capture(source: Path, destination: Path) -> str:
    """Capture offline tree; return manifest SHA-256 to retain OUTSIDE the bundle."""
    _separate(source, destination)
    before = inventory(source)
    destination.mkdir(parents=False, exist_ok=False)
    shutil.copytree(source, destination / "payload", symlinks=True)
    if inventory(source) != before or inventory(destination / "payload") != before:
        raise ValueError("source_changed_during_capture")
    manifest = destination / "manifest.json"
    manifest.write_text(json.dumps({"schema": "rag4-offline-v1", "files": before},
                                  sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return digest(manifest)


def verify(bundle: Path, expected_manifest_sha256: str) -> dict:
    """Validate externally pinned manifest plus all files, including extra entries."""
    # Validate the whole tree before opening any manifest or payload link.
    inventory(bundle)
    if {p.name for p in bundle.iterdir()} != {"manifest.json", "payload"}:
        raise ValueError("unexpected_bundle_entry")
    manifest = bundle / "manifest.json"
    if digest(manifest) != expected_manifest_sha256:
        raise ValueError("manifest_digest_mismatch")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("schema") != "rag4-offline-v1" or data.get("files") != inventory(bundle / "payload"):
        raise ValueError("payload_integrity_mismatch")
    return data


def restore(bundle: Path, destination: Path, *, expected_manifest_sha256: str) -> None:
    """Restore exclusively to a NEW tree; returns only after full verification.

    A failure during copying can leave an incomplete destination. Caller must not
    use it; retry with another new path. Never edits a live path or active pointer.
    """
    _separate(bundle, destination)
    manifest = verify(bundle, expected_manifest_sha256)
    destination.mkdir(parents=False, exist_ok=False)
    shutil.copytree(bundle / "payload", destination, dirs_exist_ok=True, symlinks=True)
    if inventory(destination) != manifest["files"]:
        raise ValueError("restored_integrity_mismatch")
