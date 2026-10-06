"""A release wheel must include the modules and dictionaries its users need."""

import importlib.util
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("verify_python_wheel", ROOT / "scripts/verify_python_wheel.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def wheel(tmp_path, *, version="2.0.0", missing=None, legacy=False):
    target = tmp_path / "package.whl"
    files = {
        "piper_plus/__init__.py": "",
        "piper_plus/voice.py": "",
        "piper_plus/__main__.py": "",
        "piper_plus/phonemize/data/zh_en_loanword.json": "{}",
        "piper_plus/phonemize/data/sv_function_words.json": "{}",
        "piper_plus-2.0.0.dist-info/METADATA": f"Name: piper-plus\nVersion: {version}\n",
        "piper_plus-2.0.0.dist-info/licenses/LICENSE.md": "MIT license fixture",
    }
    if missing: files.pop(missing)
    if legacy: files["piper/__init__.py"] = ""
    with zipfile.ZipFile(target, "w") as archive:
        for name, content in files.items(): archive.writestr(name, content)
    return target


def test_accepts_complete_wheel(tmp_path):
    MODULE.verify_wheel(wheel(tmp_path), "piper-plus", "2.0.0")


def test_wrong_version_fails(tmp_path):
    with pytest.raises(ValueError, match="version"):
        MODULE.verify_wheel(wheel(tmp_path, version="0.0.0"), "piper-plus", "2.0.0")


@pytest.mark.parametrize("missing", [
    "piper_plus/voice.py", "piper_plus/phonemize/data/zh_en_loanword.json",
    "piper_plus/phonemize/data/sv_function_words.json",
    "piper_plus-2.0.0.dist-info/licenses/LICENSE.md",
])
def test_missing_runtime_files_fail(tmp_path, missing):
    with pytest.raises(ValueError, match="missing"):
        MODULE.verify_wheel(wheel(tmp_path, missing=missing), "piper-plus", "2.0.0")


def test_legacy_piper_module_is_not_shipped(tmp_path):
    with pytest.raises(ValueError, match="legacy"):
        MODULE.verify_wheel(wheel(tmp_path, legacy=True), "piper-plus", "2.0.0")
