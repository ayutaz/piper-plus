"""Verify byte-stable Apple archives across packaging runs."""

import hashlib
import importlib.util
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def archiver():
    spec = importlib.util.spec_from_file_location("xcframework_archive", ROOT / "scripts/zip_xcframework.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_archive


def fixture(parent, reversed_order=False):
    source = parent / "example.xcframework"
    entries = [("Info.plist", b"plist"), ("slice/Headers/a.h", b"header"), ("slice/lib.a", b"library" * 1000)]
    if reversed_order:
        entries.reverse()
    for name, value in entries:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        os.utime(path, (1700000000 if reversed_order else 1600000000,) * 2)
    return source


def test_archive_bytes_ignore_mtime_and_creation_order(tmp_path):
    one = tmp_path / "one.zip"
    two = tmp_path / "two.zip"
    archiver()(fixture(tmp_path / "one"), one)
    archiver()(fixture(tmp_path / "two", True), two)
    assert one.read_bytes() == two.read_bytes()
    with zipfile.ZipFile(one) as archive:
        assert archive.read("example.xcframework/slice/lib.a") == b"library" * 1000
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())
        assert all(not item.extra for item in archive.infolist())


def test_archive_checksum_changes_with_library_content(tmp_path):
    source = fixture(tmp_path / "source")
    one, two = tmp_path / "one.zip", tmp_path / "two.zip"
    archiver()(source, one)
    (source / "slice/lib.a").write_bytes(b"new library")
    archiver()(source, two)
    assert hashlib.sha256(one.read_bytes()).digest() != hashlib.sha256(two.read_bytes()).digest()


def test_release_uses_deterministic_g2p_archive():
    import yaml
    workflow = yaml.safe_load((ROOT / ".github/workflows/release-shared-lib.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["assemble-g2p-xcframework"]["steps"]
    command = next(step["run"] for step in steps if step.get("name") == "Zip xcframework")
    assert "python3 scripts/zip_xcframework.py" in command
    assert "zip -ry" not in command