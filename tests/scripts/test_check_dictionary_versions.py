"""Unit tests for scripts/check_dictionary_versions.py.

The regression these cover: the gate checked nothing at all. All four of its
targets matched nothing -- three because ``src/python_run/setup.py`` stopped
declaring dependencies in Issue #418, and the fourth because its pattern
(``jpreprocess\\s*=\\s*"..."``) never matched the real
``jpreprocess = { version = "0.9", optional = true }`` form.

Since the drift loop iterated over the *found* versions, an empty ``found``
meant the loop body never ran and the gate printed
``[OK] All discoverable dictionary versions are referenced in spec``. It went
green precisely because it had lost every target -- the same class as
#628 / #629 / #632.

Behind that sat a real drift: the spec declared ``pyopenjtalk-plus
0.4.1.post7`` while ``requirements.txt`` and ``cmake/ExternalDeps.cmake`` had
both moved to ``post8`` (PR #410).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_dictionary_versions.py"

SPEC_TOML = """\
[meta]
spec_version = "1.0"

[japanese.pyopenjtalk_plus]
package = "pyopenjtalk-plus"
version = "0.4.1.post8"

[japanese.jpreprocess]
package = "jpreprocess"
crates_io_version = "0.9.1"

[english.g2p_en]
package = "g2p-en"
version = "2.1.0"
"""

REQUIREMENTS = """\
# Core dependencies
onnxruntime>=1.26.0

pyopenjtalk-plus>=0.4.1.post8
g2p-en>=2.1.0
"""

CARGO = 'jpreprocess = { version = "0.9", optional = true }\n'


@pytest.fixture(scope="module")
def mod():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("check_dictionary_versions", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake(tmp_path, mod, monkeypatch):
    """A throwaway repo with one Python target and one Rust target."""
    spec_path = tmp_path / "docs" / "spec" / "dictionary-versions.toml"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(SPEC_TOML, encoding="utf-8")

    req = tmp_path / "src" / "python_run" / "requirements.txt"
    req.parent.mkdir(parents=True)
    req.write_text(REQUIREMENTS, encoding="utf-8")

    cargo = tmp_path / "src" / "rust" / "piper-core" / "Cargo.toml"
    cargo.parent.mkdir(parents=True)
    cargo.write_text(CARGO, encoding="utf-8")

    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "SPEC", spec_path)
    monkeypatch.setattr(
        mod,
        "CHECKS",
        [
            (
                "pyopenjtalk-plus",
                "src/python_run/requirements.txt",
                r"^pyopenjtalk-plus>=([0-9][0-9a-z.]*)",
                ("japanese", "pyopenjtalk_plus"),
                "version",
                "exact",
            ),
            (
                "jpreprocess (Rust)",
                "src/rust/piper-core/Cargo.toml",
                r'jpreprocess\s*=\s*\{[^}]*version\s*=\s*"([^"]+)"',
                ("japanese", "jpreprocess"),
                "crates_io_version",
                "prefix",
            ),
        ],
    )
    monkeypatch.setattr(mod, "EXPECTED_CHECK_COUNT", 2)

    class Helper:
        spec = spec_path
        requirements = req
        cargo_toml = cargo

    return Helper


# --------------------------------------------------------------------------
# The real repository
# --------------------------------------------------------------------------


def test_spec_path_points_at_a_real_file(mod):
    assert mod.SPEC.exists(), f"SPEC does not exist: {mod.SPEC}"


def test_all_declared_targets_exist(mod):
    """Directly catches a target rotting again (the Issue #418 failure)."""
    for label, rel_path, _, _, _, _ in mod.CHECKS:
        assert (mod.REPO_ROOT / rel_path).exists(), f"{label}: {rel_path} missing"


def test_every_pattern_matches_something_in_the_real_repo(mod):
    """The core regression: all four patterns used to match nothing."""
    for label, rel_path, pattern, _, _, _ in mod.CHECKS:
        found = mod.extract_version(mod.REPO_ROOT / rel_path, pattern, label)
        assert found, f"{label}: pattern matched nothing in {rel_path}"


def test_real_repository_is_clean(mod):
    assert mod.check() == []


def test_real_repository_cli_exits_zero(mod):
    assert mod.run([]) == 0


def test_expected_check_count_matches(mod):
    assert len(mod.CHECKS) == mod.EXPECTED_CHECK_COUNT


# --------------------------------------------------------------------------
# Comparison semantics
# --------------------------------------------------------------------------


def test_matching_versions_pass(fake, mod):
    assert mod.check() == []


def test_exact_mode_reports_drift(fake, mod):
    """The real drift: spec said post7 while requirements.txt said post8."""
    fake.spec.write_text(
        SPEC_TOML.replace('version = "0.4.1.post8"', 'version = "0.4.1.post7"'),
        encoding="utf-8",
    )
    drifts = mod.check()
    assert len(drifts) == 1
    assert "0.4.1.post8" in drifts[0] and "0.4.1.post7" in drifts[0]


def test_prefix_mode_accepts_a_caret_range(fake, mod):
    """Cargo `"0.9"` means >=0.9.0,<0.10.0, so spec 0.9.1 satisfies it.

    Comparing those for equality would report drift on a consistent pair.
    """
    assert mod.check() == []


def test_prefix_mode_rejects_a_different_minor(fake, mod):
    fake.cargo_toml.write_text(
        'jpreprocess = { version = "0.8", optional = true }\n', encoding="utf-8"
    )
    drifts = mod.check()
    assert len(drifts) == 1
    assert "caret range" in drifts[0]


def test_prefix_mode_does_not_accept_a_bare_numeric_extension(fake, mod):
    """`0.9` must not be satisfied by `0.91` -- the dot separator matters."""
    fake.spec.write_text(
        SPEC_TOML.replace('crates_io_version = "0.9.1"', 'crates_io_version = "0.91"'),
        encoding="utf-8",
    )
    drifts = mod.check()
    assert len(drifts) == 1


def test_prefix_mode_accepts_exact_equality(fake, mod):
    fake.spec.write_text(
        SPEC_TOML.replace('crates_io_version = "0.9.1"', 'crates_io_version = "0.9"'),
        encoding="utf-8",
    )
    assert mod.check() == []


# --------------------------------------------------------------------------
# Broken-setup failures: every one of these used to be a silent skip
# --------------------------------------------------------------------------


def test_pattern_matching_nothing_is_hard_failure(fake, mod):
    """The pin the gate guards disappeared -- the Issue #418 failure mode."""
    fake.requirements.write_text("# nothing here\n", encoding="utf-8")
    with pytest.raises(mod.DriftError, match="matched nothing"):
        mod.check()


def test_missing_spec_is_hard_failure(fake, mod):
    fake.spec.unlink()
    with pytest.raises(mod.DriftError, match="spec missing"):
        mod.check()


def test_missing_target_file_is_hard_failure(fake, mod):
    fake.cargo_toml.unlink()
    with pytest.raises(mod.DriftError, match="target file missing"):
        mod.check()


def test_unresolvable_spec_key_is_hard_failure(fake, mod, monkeypatch):
    monkeypatch.setattr(
        mod,
        "CHECKS",
        [
            (
                "bogus",
                "src/python_run/requirements.txt",
                r"^pyopenjtalk-plus>=([0-9][0-9a-z.]*)",
                ("nope", "missing"),
                "version",
                "exact",
            )
        ],
    )
    monkeypatch.setattr(mod, "EXPECTED_CHECK_COUNT", 1)
    with pytest.raises(mod.DriftError, match="does not resolve"):
        mod.check()


def test_missing_spec_field_is_hard_failure(fake, mod, monkeypatch):
    monkeypatch.setattr(
        mod,
        "CHECKS",
        [
            (
                "bogus",
                "src/python_run/requirements.txt",
                r"^pyopenjtalk-plus>=([0-9][0-9a-z.]*)",
                ("japanese", "pyopenjtalk_plus"),
                "no_such_field",
                "exact",
            )
        ],
    )
    monkeypatch.setattr(mod, "EXPECTED_CHECK_COUNT", 1)
    with pytest.raises(mod.DriftError, match="no_such_field"):
        mod.check()


def test_checks_shrinking_is_hard_failure(fake, mod, monkeypatch):
    """A silent shrink would cover less while still reporting success."""
    monkeypatch.setattr(mod, "CHECKS", [])
    with pytest.raises(mod.DriftError, match="EXPECTED_CHECK_COUNT"):
        mod.check()


def test_unknown_mode_is_hard_failure(fake, mod, monkeypatch):
    monkeypatch.setattr(
        mod,
        "CHECKS",
        [
            (
                "bogus",
                "src/python_run/requirements.txt",
                r"^pyopenjtalk-plus>=([0-9][0-9a-z.]*)",
                ("japanese", "pyopenjtalk_plus"),
                "version",
                "approximately",
            )
        ],
    )
    monkeypatch.setattr(mod, "EXPECTED_CHECK_COUNT", 1)
    with pytest.raises(mod.DriftError, match="unknown comparison mode"):
        mod.check()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_returns_one_on_drift(fake, mod):
    fake.spec.write_text(
        SPEC_TOML.replace('version = "0.4.1.post8"', 'version = "0.4.1.post7"'),
        encoding="utf-8",
    )
    assert mod.run([]) == 1


def test_cli_returns_one_on_broken_setup(fake, mod):
    fake.spec.unlink()
    assert mod.run([]) == 1
