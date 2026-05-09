"""Unit tests for ``scripts/check_ort_versions.py``.

These tests pin the regex contract — Issue #383 follow-up review on
PR #403 flagged that the archive-filename pattern would silently miss
``-`` containing arch segments such as ``onnxruntime-linux-x64-gpu``,
letting a workflow drift on a GPU/CUDA archive while keeping the
surrounding ``vX.Y.Z`` URL aligned. The tests below exercise both the
shapes used today and the GPU/CUDA suffix shapes that motivated the
fix, so future regex changes cannot silently regress detection.

Issue #372 follow-up: extend the suite to cover the floor-check group
(Python / C# / Go / WASM dependency files). The floor-check enforces
``ecosystem version >= canonical`` so a future careless edit cannot
silently lower the pin below the C++ canonical (``cmake/OnnxRuntime.cmake``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


_SCRIPT_PATH = Path(__file__).parent / "check_ort_versions.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_ort_versions", _SCRIPT_PATH)
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
    assert "1.20.0" not in found, f"unexpected match against unrelated string: {found}"


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
        f"archive-name version drift must remain detectable; got {sorted(found.keys())}"
    )


# ---------------------------------------------------------------------------
# Issue #372: parse_version + floor-check semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.20.0", (1, 20, 0)),
        ("v1.20.0", (1, 20, 0)),  # Go-style leading 'v'
        ("1.20", (1, 20, 0)),  # short form gets padded
        ("1", (1, 0, 0)),  # very short form gets padded
        ("1.24.3", (1, 24, 3)),
        ("2.0.0-rc.12", (2, 0, 0)),  # pre-release stripped
        ("1.20.0+build.5", (1, 20, 0)),  # build metadata stripped
    ],
)
def test_parse_version_normalizes(cov, raw, expected):
    assert cov.parse_version(raw) == expected


def test_parse_version_orders_correctly(cov):
    """SemVer ordering must be tuple-comparison correct so the floor
    check accepts ``1.24.3 >= 1.20.0`` but rejects ``1.11.0 < 1.20.0``."""
    pv = cov.parse_version
    assert pv("1.20.0") == pv("1.20.0")
    assert pv("1.24.3") > pv("1.20.0")
    assert pv("1.11.0") < pv("1.20.0")
    assert pv("1.20.1") > pv("1.20.0")
    assert pv("1.21.0") > pv("1.20.99")  # minor beats patch
    assert pv("2.0.0") > pv("1.99.99")  # major beats minor


# ---------------------------------------------------------------------------
# Floor patterns per ecosystem.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "ecosystem", "expected"),
    [
        # Python: PEP 508 style, both onnxruntime and onnxruntime-gpu
        ("onnxruntime>=1.20.0", "python", [("onnxruntime", "1.20.0")]),
        ("onnxruntime-gpu>=1.20.0,<2", "python", [("onnxruntime-gpu", "1.20.0")]),
        # quoted form (pyproject extras / setup.py extras)
        (
            '    "onnxruntime>=1.20.0",',
            "python",
            [("onnxruntime", "1.20.0")],
        ),
        # short version form
        ("onnxruntime>=1.17", "python", [("onnxruntime", "1.17")]),
        # PR #404 review feedback (Comment 1): also accept ``==`` (exact pin)
        # and ``~=`` (compatible release) operators so a future edit using
        # those PEP 440 specifiers does not silently bypass the gate.
        ("onnxruntime==1.20.0", "python", [("onnxruntime", "1.20.0")]),
        ("onnxruntime~=1.20.0", "python", [("onnxruntime", "1.20.0")]),
        # C# csproj — Include first (canonical order in this repo)
        (
            '<PackageReference Include="Microsoft.ML.OnnxRuntime" Version="1.24.3" />',
            "csharp",
            [("Microsoft.ML.OnnxRuntime", "1.24.3")],
        ),
        (
            '<PackageReference Include="Microsoft.ML.OnnxRuntime.Managed" Version="1.24.3" />',
            "csharp",
            [("Microsoft.ML.OnnxRuntime.Managed", "1.24.3")],
        ),
        # PR #404 review feedback (Comment 3): XML attribute order is not
        # semantically significant. Version-first must extract the same
        # (pkg, ver) pair so a tooling-driven attribute reorder cannot
        # silently disable the floor check.
        (
            '<PackageReference Version="1.24.3" Include="Microsoft.ML.OnnxRuntime" />',
            "csharp",
            [("Microsoft.ML.OnnxRuntime", "1.24.3")],
        ),
        (
            '<PackageReference Version="1.24.3" Include="Microsoft.ML.OnnxRuntime.Managed" />',
            "csharp",
            [("Microsoft.ML.OnnxRuntime.Managed", "1.24.3")],
        ),
        # csproj with an unrelated attribute between Include and Version
        (
            '<PackageReference Include="Microsoft.ML.OnnxRuntime" '
            'PrivateAssets="all" Version="1.24.3" />',
            "csharp",
            [("Microsoft.ML.OnnxRuntime", "1.24.3")],
        ),
        # Go go.mod
        (
            "require github.com/yalue/onnxruntime_go v1.27.0",
            "go",
            [("github.com/yalue/onnxruntime_go", "1.27.0")],
        ),
        # npm package.json peerDep, ``>=`` form
        (
            '"onnxruntime-web": ">=1.21.0"',
            "npm",
            [("onnxruntime-web", "1.21.0")],
        ),
        # PR #404 review feedback (Comment 1): also accept npm caret /
        # tilde / exact pin so a future package.json edit using those
        # standard SemVer range specifiers does not bypass the gate.
        (
            '"onnxruntime-web": "^1.21.0"',
            "npm",
            [("onnxruntime-web", "1.21.0")],
        ),
        (
            '"onnxruntime-web": "~1.21.0"',
            "npm",
            [("onnxruntime-web", "1.21.0")],
        ),
        (
            '"onnxruntime-web": "1.21.0"',
            "npm",
            [("onnxruntime-web", "1.21.0")],
        ),
    ],
)
def test_floor_pattern_extracts_package_and_version(cov, text, ecosystem, expected):
    found = cov.find_floor_versions(text, ecosystem)
    assert found == expected, f"ecosystem={ecosystem} text={text!r}"


# ---------------------------------------------------------------------------
# PR #404 review feedback (Comment 1): operator-level drift detection.
# A pin below the floor must be flagged regardless of which lower-bound
# operator is used (``>=``, ``==``, ``~=`` for Python; bare / ``^`` / ``~``
# for npm).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "ecosystem", "expected_violation"),
    [
        ("onnxruntime==1.19.0", "python", ("onnxruntime", "1.19.0")),
        ("onnxruntime~=1.17.0", "python", ("onnxruntime", "1.17.0")),
        ('"onnxruntime-web": "^1.19.0"', "npm", ("onnxruntime-web", "1.19.0")),
        ('"onnxruntime-web": "~1.18.0"', "npm", ("onnxruntime-web", "1.18.0")),
        ('"onnxruntime-web": "1.10.0"', "npm", ("onnxruntime-web", "1.10.0")),
    ],
)
def test_floor_violation_detected_across_operators(
    cov, text, ecosystem, expected_violation
):
    violations = cov.find_floor_violations(text, ecosystem, floor="1.20.0")
    assert violations == [expected_violation]


def test_floor_violation_detected(cov):
    """A pin below the canonical floor (1.20.0) must be flagged."""
    text = "onnxruntime>=1.11.0"  # below floor
    violations = cov.find_floor_violations(text, "python", floor="1.20.0")
    assert violations == [("onnxruntime", "1.11.0")]


def test_floor_pin_at_canonical_passes(cov):
    """A pin equal to the canonical floor must pass (>=1.20.0 satisfies floor 1.20.0)."""
    text = "onnxruntime>=1.20.0"
    violations = cov.find_floor_violations(text, "python", floor="1.20.0")
    assert violations == []


def test_floor_pin_above_canonical_passes(cov):
    """C# 1.24.3 / Go 1.27.0 must pass under Option C (>= canonical)."""
    csproj = '<PackageReference Include="Microsoft.ML.OnnxRuntime" Version="1.24.3" />'
    assert cov.find_floor_violations(csproj, "csharp", floor="1.20.0") == []

    gomod = "github.com/yalue/onnxruntime_go v1.27.0"
    assert cov.find_floor_violations(gomod, "go", floor="1.20.0") == []


def test_floor_pin_short_version_at_canonical_passes(cov):
    """``onnxruntime>=1.20`` (short form) must pass against floor 1.20.0
    after padding semantics in ``parse_version``."""
    text = "onnxruntime>=1.20"
    violations = cov.find_floor_violations(text, "python", floor="1.20.0")
    assert violations == []


def test_floor_pin_short_version_below_canonical_fails(cov):
    """``onnxruntime>=1.17`` (short form) must fail against floor 1.20.0."""
    text = "onnxruntime>=1.17"
    violations = cov.find_floor_violations(text, "python", floor="1.20.0")
    assert violations == [("onnxruntime", "1.17")]


def test_floor_dedup_within_file(cov):
    """If a file lists the same (package, version) on multiple lines (e.g.
    pyproject.toml extras), the violation should be reported once."""
    text = """
    train = ["onnxruntime>=1.11.0"]
    inference = ["onnxruntime>=1.11.0"]
    """
    violations = cov.find_floor_violations(text, "python", floor="1.20.0")
    assert violations == [("onnxruntime", "1.11.0")]


# ---------------------------------------------------------------------------
# PR #404 review feedback (Comment 2): missing required files must fail
# the gate. The previous behaviour was warn + skip, which silently
# disabled drift / floor verification for moved or renamed files.
# ---------------------------------------------------------------------------


def _setup_main_with_canonical(monkeypatch, tmp_path, cov, canonical: str = "1.20.0"):
    """Point ``cov.CMAKE_FILE`` at a fake canonical and stub argv so
    ``cov.main()`` can be invoked from a unit test."""
    fake_cmake = tmp_path / "OnnxRuntime.cmake"
    fake_cmake.write_text(f'set(ONNXRUNTIME_VERSION "{canonical}")\n')
    monkeypatch.setattr(cov, "CMAKE_FILE", fake_cmake)
    monkeypatch.setattr(sys, "argv", ["check_ort_versions.py"])


def test_missing_exact_match_target_fails(cov, monkeypatch, tmp_path, capsys):
    """If a TARGETS path no longer exists (file moved/renamed), the
    gate must FAIL, not silently warn."""
    _setup_main_with_canonical(monkeypatch, tmp_path, cov)
    monkeypatch.setattr(cov, "TARGETS", [tmp_path / "absent.cmake"])
    monkeypatch.setattr(cov, "FLOOR_TARGETS", [])

    rc = cov.main()
    captured = capsys.readouterr()
    assert rc == 1, f"expected fail, stdout was: {captured.out}"
    assert "required file missing" in captured.out
    assert "absent.cmake" in captured.out


def test_missing_floor_target_fails(cov, monkeypatch, tmp_path, capsys):
    """Same as above for FLOOR_TARGETS — a missing floor file must FAIL
    so the gate cannot silently exempt a runtime."""
    _setup_main_with_canonical(monkeypatch, tmp_path, cov)
    monkeypatch.setattr(cov, "TARGETS", [])
    monkeypatch.setattr(
        cov, "FLOOR_TARGETS", [(tmp_path / "absent_pyproject.toml", "python")]
    )

    rc = cov.main()
    captured = capsys.readouterr()
    assert rc == 1, f"expected fail, stdout was: {captured.out}"
    assert "required file missing" in captured.out
    assert "absent_pyproject.toml" in captured.out


def test_all_targets_present_passes(cov, monkeypatch, tmp_path, capsys):
    """Sanity check the missing-file logic is not over-eager: a real
    file with canonical content must still pass when it's the only
    target (regression guard for the warn → fail flip)."""
    _setup_main_with_canonical(monkeypatch, tmp_path, cov)
    fake_target = tmp_path / "fake_workflow.yml"
    fake_target.write_text('  ONNXRUNTIME_VERSION: "1.20.0"\n')
    monkeypatch.setattr(cov, "TARGETS", [fake_target])

    fake_floor = tmp_path / "fake_pyproject.toml"
    fake_floor.write_text('"onnxruntime>=1.20.0",\n')
    monkeypatch.setattr(cov, "FLOOR_TARGETS", [(fake_floor, "python")])

    rc = cov.main()
    captured = capsys.readouterr()
    assert rc == 0, f"expected pass, stdout was: {captured.out}"
    assert "all ORT version references match" in captured.out
