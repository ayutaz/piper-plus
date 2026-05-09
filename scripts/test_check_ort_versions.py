"""Unit tests for ``scripts/check_ort_versions.py``.

These tests pin the regex contract — Issue #383 follow-up review on
PR #403 flagged that the archive-filename pattern would silently miss
``-`` containing arch segments such as ``onnxruntime-linux-x64-gpu``,
letting a workflow drift on a GPU/CUDA archive while keeping the
surrounding ``vX.Y.Z`` URL aligned. The tests below exercise both the
shapes used today and the GPU/CUDA suffix shapes that motivated the
fix, so future regex changes cannot silently regress detection.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).parent / "check_ort_versions.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_ort_versions", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_ort_versions", mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def cov():
    return _load_module()


# ---------------------------------------------------------------------------
# Archive filename pattern (the one PR #403 review fixed).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename",
    [
        # Currently-used archives (cmake / workflows)
        "onnxruntime-linux-x64-1.20.0.tgz",
        "onnxruntime-linux-aarch64-1.20.0.tgz",
        "onnxruntime-osx-arm64-1.20.0.tgz",
        "onnxruntime-osx-x86_64-1.20.0.tgz",
        "onnxruntime-osx-universal2-1.20.0.tgz",
        "onnxruntime-win-x64-1.20.0.zip",
        "onnxruntime-win-arm64-1.20.0.zip",
        # GPU / CUDA suffix shapes that the original ``[a-z0-9_]+`` pattern
        # silently dropped — the fix must keep these visible so a workflow
        # cannot drift on the archive name alone.
        "onnxruntime-linux-x64-gpu-1.20.0.tgz",
        "onnxruntime-win-x64-gpu-1.20.0.zip",
        "onnxruntime-linux-x64-cuda-1.20.0.tgz",
    ],
)
def test_archive_pattern_extracts_version(cov, filename):
    found = cov.find_versions(filename)
    assert "1.20.0" in found, (
        f"archive pattern failed to detect 1.20.0 in {filename!r}; "
        f"matches were {sorted(found.keys())}"
    )


def test_archive_pattern_does_not_match_unrelated_strings(cov):
    """Pattern must remain anchored to ``onnxruntime-{platform}-`` so an
    unrelated tool name like ``llama-runtime-linux-x64-1.20.0`` does not
    trigger a false-positive."""
    text = "llama-runtime-linux-x64-1.20.0.tgz"
    found = cov.find_versions(text)
    # No archive-shaped version should be picked up. The cache-key fallback
    # pattern (``onnxruntime[-_]<ver>``) also does not apply here because
    # the prefix is wrong.
    assert "1.20.0" not in found, (
        f"unexpected match against unrelated string: {found}"
    )


# ---------------------------------------------------------------------------
# Other patterns — keep them pinned so the fix above does not accidentally
# weaken them.
# ---------------------------------------------------------------------------

def test_cmake_set_pattern(cov):
    found = cov.find_versions('set(ONNXRUNTIME_VERSION "1.20.0")')
    assert "1.20.0" in found


def test_actions_env_pattern(cov):
    found = cov.find_versions('  ONNXRUNTIME_VERSION: "1.20.0"')
    assert "1.20.0" in found


def test_release_url_pattern(cov):
    found = cov.find_versions(
        "https://github.com/microsoft/onnxruntime/releases/download/v1.20.0/"
        "onnxruntime-linux-x64-1.20.0.tgz"
    )
    assert "1.20.0" in found


def test_maven_android_pattern(cov):
    found = cov.find_versions(
        "https://repo1.maven.org/maven2/com/microsoft/onnxruntime/"
        "onnxruntime-android/1.20.0/onnxruntime-android-1.20.0.aar"
    )
    assert "1.20.0" in found


def test_pod_archive_pattern(cov):
    found = cov.find_versions(
        "https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.20.0.zip"
    )
    assert "1.20.0" in found


# ---------------------------------------------------------------------------
# Drift detection: a mismatched version inside an archive name must surface.
# ---------------------------------------------------------------------------

def test_drift_in_archive_name_is_visible(cov):
    """If a workflow keeps ``v1.20.0`` in the URL but the archive name
    drifts to ``...x64-gpu-1.19.0.tgz``, both versions should now be
    reported so the gate can fail. The pre-fix pattern would have hidden
    the archive-name drift entirely."""
    mixed = (
        "https://github.com/microsoft/onnxruntime/releases/download/v1.20.0/"
        "onnxruntime-linux-x64-gpu-1.19.0.tgz"
    )
    found = cov.find_versions(mixed)
    assert "1.20.0" in found
    assert "1.19.0" in found, (
        "archive-name version drift must remain detectable; "
        f"got {sorted(found.keys())}"
    )
