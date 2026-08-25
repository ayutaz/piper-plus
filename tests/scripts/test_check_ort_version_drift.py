"""Unit tests for scripts/check_ort_version_drift.py.

The regression these cover: the gate never once failed a job. Its ``SPEC``
constant pointed at ``docs/spec/ort-versions.md`` three months after the
file moved to ``docs/reference/``, it returned 0 when the spec was absent,
it ``continue``d past targets whose pattern matched nothing, and the
workflow step carried ``continue-on-error: true`` from its first commit.

Behind that sat a real drift (docs said ``>=1.20.0``, pins said
``>=1.26.0``) and an unsound comparison: ``version not in spec_text``, a
bare substring test over the whole document. The tests below pin the
three ways that let a broken pin pass -- cross-row bleed, prefix match,
and any-row match -- because a fix that only repairs the path leaves all
three alive.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_ort_version_drift.py"

# A miniature stand-in for docs/reference/ort-versions.md. The C++ rows
# repeat 1.20.0 on purpose: that repetition is what made the old
# whole-document substring test accept any runtime downgraded to 1.20.0.
SPEC_MD = """\
# ONNX Runtime Version Matrix

## Policy

Out of scope: the Rust row.

## Current versions

| Runtime  | ORT Version  | Floor | Package / Source |
|----------|-------------|-------|------------------|
| Python (runtime) | `>=1.26.0` | `>=1.20.0` | requirements.txt |
| Rust     | 2.0.0-rc.13 | exempt | ort (crates.io) |
| C#       | 1.24.3      | `>=1.20.0` | NuGet |
| Go       | 1.27.0      | `>=1.20.0` | onnxruntime_go |
| C++ (canonical) | **1.20.0** | — | cmake |
| C++ (Windows pre-built) | 1.20.0 | exact | cmake |

## CI Workflow References

nothing to parse here.
"""


@pytest.fixture(scope="module")
def mod():
    # Ensure sibling scripts/ modules are importable
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("check_ort_version_drift", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake(tmp_path, mod, monkeypatch):
    """Build a throwaway repo and point the module at it.

    Returns a helper that writes the Go pin and (optionally) overrides the
    spec text, then runs ``check()``.
    """
    spec_path = tmp_path / "docs" / "reference" / "ort-versions.md"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(SPEC_MD, encoding="utf-8")

    go_mod = tmp_path / "src" / "go" / "go.mod"
    go_mod.parent.mkdir(parents=True)

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "SPEC", spec_path)
    monkeypatch.setattr(
        mod,
        "ROW_CHECKS",
        [("Go", "src/go/go.mod", r"onnxruntime_go\s+v([0-9][0-9.]*)")],
    )
    monkeypatch.setattr(mod, "EXPECTED_CHECK_COUNT", 1)

    class Helper:
        spec = spec_path
        gomod = go_mod

        @staticmethod
        def set_go(version: str) -> None:
            go_mod.write_text(
                f"module github.com/ayutaz/piper-plus/src/go\n\n"
                f"require github.com/yalue/onnxruntime_go v{version}\n",
                encoding="utf-8",
            )

    Helper.set_go("1.27.0")
    return Helper


# --------------------------------------------------------------------------
# The real repository
# --------------------------------------------------------------------------


def test_spec_path_points_at_a_real_file(mod):
    """Directly catches the constant rotting again after a doc move."""
    assert mod.SPEC.exists(), f"SPEC does not exist: {mod.SPEC}"


def test_real_repository_is_clean(mod):
    assert mod.check() == []


def test_real_repository_cli_exits_zero(mod):
    assert mod.run([]) == 0


def test_expected_check_count_matches_row_checks(mod):
    assert len(mod.ROW_CHECKS) == mod.EXPECTED_CHECK_COUNT


def test_every_declared_row_label_exists_in_the_doc(mod):
    rows = mod.parse_current_versions(mod.SPEC.read_text(encoding="utf-8"))
    for label, _, _ in mod.ROW_CHECKS:
        assert label in rows, f"row {label!r} missing from the doc table"


# --------------------------------------------------------------------------
# Happy path on the fake repo
# --------------------------------------------------------------------------


def test_matching_version_passes(fake, mod):
    assert mod.check() == []


# --------------------------------------------------------------------------
# The three ways the old substring comparison let a bad pin through
# --------------------------------------------------------------------------


def test_cross_row_bleed_is_caught(fake, mod):
    """Go set to the C# row's value.

    ``'1.24.3' in spec_text`` is True, so the old check passed.
    """
    fake.set_go("1.24.3")
    drifts = mod.check()
    assert len(drifts) == 1
    assert "1.24.3" in drifts[0]
    assert "[Go]" in drifts[0]


def test_canonical_value_from_another_row_is_caught(fake, mod):
    """Go dropped to 1.20.0, which six C++ rows carry."""
    fake.set_go("1.20.0")
    drifts = mod.check()
    assert len(drifts) == 1
    assert "1.20.0" in drifts[0]


def test_prefix_match_is_caught(fake, mod):
    """A truncated version. ``'1.2' in spec_text`` is True."""
    fake.set_go("1.2")
    drifts = mod.check()
    assert len(drifts) == 1


def test_rc_prefix_match_is_caught(fake, mod, monkeypatch):
    """rc.13 -> rc.1 downgrade. ``'2.0.0-rc.1' in spec_text`` is True."""
    rust_toml = fake.spec.parent.parent.parent / "src" / "rust" / "piper-core" / "Cargo.toml"
    rust_toml.parent.mkdir(parents=True)
    rust_toml.write_text('ort = { version = "2.0.0-rc.1" }\n', encoding="utf-8")
    monkeypatch.setattr(
        mod,
        "ROW_CHECKS",
        [("Rust", "src/rust/piper-core/Cargo.toml", r'ort = \{ version = "([^"]+)"')],
    )
    drifts = mod.check()
    assert len(drifts) == 1
    assert "2.0.0-rc.1" in drifts[0]


# --------------------------------------------------------------------------
# Broken-setup failures: every one of these used to be a silent skip
# --------------------------------------------------------------------------


def test_missing_spec_is_hard_failure(fake, mod):
    fake.spec.unlink()
    with pytest.raises(mod.DriftError, match="spec missing"):
        mod.check()


def test_pattern_matching_nothing_is_hard_failure(fake, mod):
    """The pin the gate guards disappeared -- the #628/#629 failure mode."""
    fake.gomod.write_text("module example.com/x\n", encoding="utf-8")
    with pytest.raises(mod.DriftError, match="matched nothing"):
        mod.check()


def test_missing_target_file_is_hard_failure(fake, mod):
    fake.gomod.unlink()
    with pytest.raises(mod.DriftError, match="target file missing"):
        mod.check()


def test_unknown_row_label_is_hard_failure(fake, mod, monkeypatch):
    monkeypatch.setattr(
        mod, "ROW_CHECKS", [("Haskell", "src/go/go.mod", r"onnxruntime_go\s+v([0-9][0-9.]*)")]
    )
    with pytest.raises(mod.DriftError, match="no such row"):
        mod.check()


def test_missing_table_heading_is_hard_failure(fake, mod):
    fake.spec.write_text("# Doc with no table\n\ntext only\n", encoding="utf-8")
    with pytest.raises(mod.DriftError, match="heading not found"):
        mod.check()


def test_empty_table_is_hard_failure(fake, mod):
    fake.spec.write_text(
        "## Current versions\n\n| Runtime | ORT Version |\n|---|---|\n\n## Next\n",
        encoding="utf-8",
    )
    with pytest.raises(mod.DriftError, match="no data rows"):
        mod.check()


def test_row_checks_shrinking_is_hard_failure(fake, mod, monkeypatch):
    """A silent shrink would cover less while still reporting success."""
    monkeypatch.setattr(mod, "ROW_CHECKS", [])
    with pytest.raises(mod.DriftError, match="EXPECTED_CHECK_COUNT"):
        mod.check()


# --------------------------------------------------------------------------
# Parsing details
# --------------------------------------------------------------------------


def test_parse_skips_header_and_separator_rows(mod):
    rows = mod.parse_current_versions(SPEC_MD)
    assert "Runtime" not in rows
    assert all(set(k) - set("-: ") for k in rows)
    assert rows["Go"] == "1.27.0"
    assert rows["C++ (canonical)"] == "**1.20.0**"


def test_parse_stops_at_the_next_heading(mod):
    rows = mod.parse_current_versions(SPEC_MD)
    assert "Workflow" not in rows
    assert len(rows) == 6


def test_multiline_pattern_is_applied(mod, tmp_path, monkeypatch):
    """`^onnxruntime` must match line 3, not just the file start.

    ``src/python_run/requirements.txt`` opens with comments; without
    ``re.MULTILINE`` the anchored pattern finds nothing, and since that is
    now a hard failure the gate would be permanently red.
    """
    req = tmp_path / "requirements.txt"
    req.write_text(
        "# Core dependencies\n# more comments\nonnxruntime>=1.26.0\n", encoding="utf-8"
    )
    assert mod.extract_versions(req, r"^onnxruntime>=([0-9][0-9.]*)") == ["1.26.0"]


def test_extract_versions_dedupes_repeated_pins(mod, tmp_path):
    """src/python/pyproject.toml declares onnxruntime>=1.26.0 twice."""
    toml = tmp_path / "pyproject.toml"
    toml.write_text('"onnxruntime>=1.26.0"\nx\n"onnxruntime>=1.26.0"\n', encoding="utf-8")
    assert mod.extract_versions(toml, r'"onnxruntime>=([0-9][0-9.]*)"') == ["1.26.0"]


def test_all_pins_in_a_row_must_be_present(fake, mod, monkeypatch):
    """A row backed by two files fails if either pin is absent from it."""
    extra = fake.gomod.parent / "go_gpu.mod"
    extra.write_text("require github.com/yalue/onnxruntime_go v9.9.9\n", encoding="utf-8")
    monkeypatch.setattr(
        mod,
        "ROW_CHECKS",
        [
            ("Go", "src/go/go.mod", r"onnxruntime_go\s+v([0-9][0-9.]*)"),
            ("Go", "src/go/go_gpu.mod", r"onnxruntime_go\s+v([0-9][0-9.]*)"),
        ],
    )
    monkeypatch.setattr(mod, "EXPECTED_CHECK_COUNT", 2)
    drifts = mod.check()
    assert len(drifts) == 1
    assert "9.9.9" in drifts[0]
