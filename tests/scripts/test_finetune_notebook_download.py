"""Run the notebook's actual downloader with a local HF transport stub."""

import ast
import hashlib
import json
from pathlib import Path

import pytest


NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks/finetune.ipynb"


def download_cell():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return next(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if "def download_verified(" in "".join(cell["source"])
    )


def test_helper_path_matches_published_bundle():
    source = ast.parse(download_cell())
    filenames = [
        call.args[0].value
        for call in ast.walk(source)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "download_verified"
    ]
    assert filenames == [
        "base.ckpt",
        "config.json",
        "examples/prepare_single_speaker_finetune.py",
    ]


def run_downloader(tmp_path):
    file = tmp_path / "helper.py"
    file.write_bytes(b"public example fixture")
    calls = []

    def transport(**kwargs):
        calls.append(kwargs)
        return str(file)

    namespace = {
        "hashlib": hashlib,
        "Path": Path,
        "hf_hub_download": transport,
        "BASE_MODEL_REPO": "ayousanz/piper-plus-base",
        "BASE_REVISION": "3620ed788667cb76f08bd6cf2db8152c1f4c8bd1",
        "RELEASE": "releases/zs-v1",
        "BASE_DIR": str(tmp_path),
    }
    function = next(
        item
        for item in ast.parse(download_cell()).body
        if isinstance(item, ast.FunctionDef)
    )
    exec(
        compile(
            ast.Module(body=[function], type_ignores=[]),
            "notebook-download-cell",
            "exec",
        ),
        namespace,
    )
    return namespace["download_verified"], file, calls


def test_download_is_pinned_and_explicitly_anonymous(tmp_path):
    download, file, calls = run_downloader(tmp_path)
    result = download(
        "examples/prepare_single_speaker_finetune.py",
        hashlib.sha256(file.read_bytes()).hexdigest(),
    )
    assert result == str(file)
    assert calls == [
        {
            "repo_id": "ayousanz/piper-plus-base",
            "revision": "3620ed788667cb76f08bd6cf2db8152c1f4c8bd1",
            "filename": "releases/zs-v1/examples/prepare_single_speaker_finetune.py",
            "local_dir": str(tmp_path),
            "token": False,
        }
    ]


def test_hash_mismatch_cannot_proceed_to_execution(tmp_path):
    download, _, _ = run_downloader(tmp_path)
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        download("examples/prepare_single_speaker_finetune.py", "wrong-hash")
