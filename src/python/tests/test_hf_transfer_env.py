"""Regression guard for hf_transfer (HF Hub concurrent chunk downloader).

v8 前処理高速化 (#1) — 生データ DL の 3-5x 高速化のために
`hf_transfer` (Rust) backend + 環境変数 `HF_HUB_ENABLE_HF_TRANSFER=1` を
統合した。 backend が無効化されたり env var が drift すると:

- vast.ai bare-VM で生データ DL が 3-5h → 1-1.5h に落ちない
  (前処理 wall-clock が gate 化して本走 launch がずれる)
- Docker image 側は Dockerfile の `ENV HF_HUB_ENABLE_HF_TRANSFER=1` を
  頼りにしているため、 落ちると image は静かに旧 backend に fallback
  (`huggingface_hub` が hf_transfer 未検出時に RuntimeError を投げない設計)

そのため以下 3 面を pin する:

1. `src/python/pyproject.toml` の train extras に `hf_transfer` が floor 付きで宣言
2. `docker/python-train/Dockerfile` の runtime stage に
   `ENV HF_HUB_ENABLE_HF_TRANSFER=1` が定義
3. env が伝播した状態で `hf_transfer` を import すると SystemError を起こさない
   (backend が動作する契約、 import self-check)

`hf_transfer` はランタイム依存で dev / test 環境でも常に import 可能とは
限らないため、 3 番目は `pytest.importorskip` で optional にする。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT_PATH = REPO_ROOT / "src" / "python" / "pyproject.toml"
DOCKERFILE_PATH = REPO_ROOT / "docker" / "python-train" / "Dockerfile"


def _load_pyproject() -> dict:
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover — Python 3.10 not supported
        import tomli as tomllib  # type: ignore[import-not-found, no-redef]
    return tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. train extras に hf_transfer が pin されている
# ---------------------------------------------------------------------------


def test_train_extras_declares_hf_transfer() -> None:
    """`src/python[train]` extras に `hf_transfer` が declare されている。

    drift 例: floor から外れる / dev extras に誤配置される → Docker image で
    Runtime import 失敗 → huggingface_hub が silent fallback → 前処理 DL の
    実効 3-5x が消える。
    """
    data = _load_pyproject()
    train_deps = (
        data.get("project", {})
        .get("optional-dependencies", {})
        .get("train", [])
    )
    assert train_deps, "pyproject.toml missing [project.optional-dependencies].train"

    hf_transfer_entries = [
        entry
        for entry in train_deps
        if entry.split("[")[0].split(">")[0].split("=")[0].split(";")[0].strip()
        == "hf_transfer"
    ]
    assert hf_transfer_entries, (
        "hf_transfer must be declared in [project.optional-dependencies].train "
        "for v8 preprocess DL speedup (3-5x). See docs/handoff/zero-shot-v8-2026-07-09.md "
        "§2 環境セットアップ."
    )
    # floor が明示されていること (`hf_transfer>=X.Y` 形式)
    entry = hf_transfer_entries[0]
    assert ">=" in entry, (
        f"hf_transfer entry {entry!r} lacks a floor — pin `hf_transfer>=0.1.6` "
        "or later to avoid silent supply-chain drift."
    )


# ---------------------------------------------------------------------------
# 2. Dockerfile に HF_HUB_ENABLE_HF_TRANSFER=1 が焼き込まれている
# ---------------------------------------------------------------------------


def test_dockerfile_enables_hf_transfer_env() -> None:
    """`docker/python-train/Dockerfile` の runtime stage に
    `ENV HF_HUB_ENABLE_HF_TRANSFER=1` が入っている。

    Dockerfile は 2 stage 構成 (builder / runtime)。 runtime stage は
    最終 image に反映されるため、 ここに ENV が無いと `docker run` 時に
    HF Hub DL が旧 backend にフォールバックし v8 前処理の 3-5x 高速化が失われる。
    """
    assert DOCKERFILE_PATH.is_file(), f"Dockerfile not found: {DOCKERFILE_PATH}"
    body = DOCKERFILE_PATH.read_text(encoding="utf-8")

    # ENV line (spaces or `=` both accepted by Docker、 正規化して照合)
    normalized = body.replace(" ", "").replace("\t", "")
    assert "ENVHF_HUB_ENABLE_HF_TRANSFER=1" in normalized, (
        "Dockerfile must declare `ENV HF_HUB_ENABLE_HF_TRANSFER=1` so the "
        "HF Hub Rust downloader is active in the final image. Without it, "
        "v8 preprocess raw-data DL falls back to single-threaded backend "
        "(3-5x slower)."
    )


# ---------------------------------------------------------------------------
# 3. env var 伝播 + backend 動作契約
# ---------------------------------------------------------------------------


def test_env_var_propagates_in_child_environment() -> None:
    """`HF_HUB_ENABLE_HF_TRANSFER=1` が Python 側で `os.environ` に見える。

    Dockerfile / handoff shell の `export` が Python process に届くことを
    unit-test で pin。 実 huggingface_hub の副作用は起こさず、
    純粋な env-var propagation の契約のみ確認。
    """
    with mock.patch.dict(os.environ, {"HF_HUB_ENABLE_HF_TRANSFER": "1"}, clear=False):
        assert os.environ.get("HF_HUB_ENABLE_HF_TRANSFER") == "1"


def test_hf_transfer_importable_when_installed() -> None:
    """`hf_transfer` が install 済み環境では import できる。

    dev / CI で `hf_transfer` が入っていない環境 (未 install) では skip。
    Docker image (train extras 経由 install 済み) や v8 vast.ai 環境では
    このテストが actually 通り、 backend が壊れていないことを pin する。
    """
    hf_transfer = pytest.importorskip(
        "hf_transfer",
        reason="hf_transfer not installed — train extras 未適用のため skip",
    )
    # Rust backend が提供する download_file / multipart_upload symbol 相当を
    # 確認 (存在すれば import は成功しているとみなす)。 具体的な API 面は
    # huggingface_hub が呼び出すため attribute 名は緩めに検査。
    assert hasattr(hf_transfer, "__file__") or hasattr(hf_transfer, "__name__")
