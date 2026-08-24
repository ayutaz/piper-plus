"""Unit tests for scripts/check_action_pins.py.

Regression focus: ``USES_RE`` used to be ``^\\s*uses:\\s*(...)``, which does
not match the YAML list form ``- uses: foo/bar@v1``. That is how most steps
are written, so the gate silently skipped 418 of 806 uses: lines (52%) in
this repo and reported "OK no new sliding-tag references" while 38
sliding-major refs sat in 17 workflows — exactly the class of reference the
PR #414 incident (cosign-installer@v4 deleted upstream, 7 jobs down) created
this gate to block.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_action_pins.py"

SHA40 = "a" * 40


def _load_module():
    # Ensure platform_utils is importable from scripts/
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("check_action_pins", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pins():
    return _load_module()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Minimal fake repo root with a .github/workflows dir."""
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    return tmp_path


def _workflow(repo: Path, name: str, body: str) -> Path:
    path = repo / ".github" / "workflows" / name
    path.write_text(body, encoding="utf-8")
    return path


def _composite(repo: Path, name: str, body: str) -> Path:
    path = repo / ".github" / "actions" / name / "action.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _run(pins, repo: Path, baseline: Path | None = None) -> int:
    argv = ["--repo-root", str(repo)]
    if baseline is not None:
        argv += ["--baseline", str(baseline)]
    return pins.main(argv)


def _refs(pins, repo: Path) -> list[str]:
    return [ref for _, _, ref in pins.collect_uses(repo)]


# --------------------------------------------------------------------------
# classify()
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        (f"actions/checkout@{SHA40}", "ok-sha"),
        ("actions/checkout@v4.2.2", "ok-semver"),
        ("actions/checkout@4.2.2", "ok-semver"),
        ("foo/bar@v1.0.0-rc.1", "ok-semver"),
        ("./.github/actions/retry-upload", "local"),
        ("./.github/workflows/reusable.yml", "local"),
        ("actions/checkout@v6", "sliding-major"),
        ("Swatinem/rust-cache@v2", "sliding-major"),
        ("dtolnay/rust-toolchain@stable", "other"),
        ("pypa/gh-action-pypi-publish@release/v1", "other"),
        ("foo/bar", "other"),
    ],
)
def test_classify(pins, ref: str, expected: str):
    assert pins.classify(ref) == expected


# --------------------------------------------------------------------------
# Detection: the two YAML spellings
# --------------------------------------------------------------------------


def test_list_form_uses_is_detected(pins, repo: Path):
    """Regression for F3: `- uses:` is how most steps are written."""
    _workflow(
        repo,
        "list-form.yml",
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4.2.2\n"
        "      -   uses: actions/setup-go@v5.6.0\n",
    )
    assert _refs(pins, repo) == [
        "actions/checkout@v4.2.2",
        "actions/setup-go@v5.6.0",
    ]


def test_plain_form_uses_is_detected(pins, repo: Path):
    """The mapping-continuation form the original regex already handled."""
    _workflow(
        repo,
        "plain-form.yml",
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - name: Checkout\n"
        "        uses: actions/checkout@v4.2.2\n",
    )
    assert _refs(pins, repo) == ["actions/checkout@v4.2.2"]


def test_both_forms_counted_in_one_file(pins, repo: Path):
    _workflow(
        repo,
        "mixed.yml",
        "      - uses: actions/checkout@v4.2.2\n"
        "      - name: Setup\n"
        "        uses: actions/setup-python@v6.2.0\n",
    )
    assert len(_refs(pins, repo)) == 2


# --------------------------------------------------------------------------
# False positives the wider regex must NOT introduce
# --------------------------------------------------------------------------


def test_reuses_key_is_not_matched(pins, repo: Path):
    """A key merely ending in `uses:` must not be picked up."""
    _workflow(repo, "reuses.yml", "      - reuses: evil/action@v9\n")
    assert _refs(pins, repo) == []


def test_commented_out_uses_is_not_matched(pins, repo: Path):
    _workflow(
        repo,
        "commented.yml",
        "      # uses: actions/checkout@v6\n      #- uses: actions/checkout@v6\n",
    )
    assert _refs(pins, repo) == []


def test_uses_inside_run_block_scalar_is_not_matched(pins, repo: Path):
    """An example `uses:` inside a shell heredoc is documentation, not a step."""
    _workflow(
        repo,
        "heredoc.yml",
        "      - uses: actions/checkout@v4.2.2\n"
        "      - name: Emit an example workflow\n"
        "        run: |\n"
        "          cat > example.yml <<'EOF'\n"
        "          steps:\n"
        "            - uses: actions/checkout@v6\n"
        "          uses: actions/setup-python@v3\n"
        "          EOF\n"
        "      - uses: actions/setup-go@v5.6.0\n",
    )
    assert _refs(pins, repo) == [
        "actions/checkout@v4.2.2",
        "actions/setup-go@v5.6.0",
    ]


def test_uses_inside_folded_scalar_is_not_matched(pins, repo: Path):
    _workflow(
        repo,
        "folded.yml",
        "      - name: Note\n"
        "        script: >-\n"
        "          uses: actions/checkout@v6\n"
        "      - uses: actions/checkout@v4.2.2\n",
    )
    assert _refs(pins, repo) == ["actions/checkout@v4.2.2"]


def test_trailing_comment_is_stripped_from_ref(pins, repo: Path):
    _workflow(repo, "trailing.yml", "      - uses: actions/checkout@v4.2.2  # pinned\n")
    assert _refs(pins, repo) == ["actions/checkout@v4.2.2"]


# --------------------------------------------------------------------------
# File discovery
# --------------------------------------------------------------------------


def test_yaml_extension_workflow_is_discovered(pins, repo: Path):
    """The glob used to be *.yml only, so a *.yaml workflow was invisible."""
    _workflow(repo, "legacy.yaml", "      - uses: actions/checkout@v6\n")
    assert _refs(pins, repo) == ["actions/checkout@v6"]


def test_composite_action_is_discovered(pins, repo: Path):
    """The pre-commit hook's files: pattern always claimed to cover these."""
    _composite(
        repo, "retry-upload", "runs:\n  steps:\n    - uses: actions/checkout@v6\n"
    )
    assert _refs(pins, repo) == ["actions/checkout@v6"]


def test_composite_action_sliding_tag_fails_gate(pins, repo: Path, capsys):
    _composite(repo, "helper", "runs:\n  steps:\n    - uses: some/action@v3\n")
    assert _run(pins, repo) == 1
    assert "some/action@v3" in capsys.readouterr().err


def test_composite_using_key_is_not_mistaken_for_uses(pins, repo: Path):
    """`using: 'composite'` must not be read as a step reference."""
    _composite(repo, "noop", "runs:\n  using: 'composite'\n  steps: []\n")
    assert _refs(pins, repo) == []


# --------------------------------------------------------------------------
# Gate outcome
# --------------------------------------------------------------------------


def test_semver_and_sha_and_local_pass(pins, repo: Path, capsys):
    _workflow(
        repo,
        "good.yml",
        "      - uses: actions/checkout@v4.2.2\n"
        f"      - uses: mymindstorm/setup-emsdk@{SHA40}\n"
        "      - uses: ./.github/actions/retry-upload\n",
    )
    assert _run(pins, repo) == 0
    out = capsys.readouterr().out
    assert "OK no new sliding-tag references" in out
    assert "3 total uses: 1 SHA, 1 SemVer" in out


def test_sliding_major_fails_gate(pins, repo: Path, capsys):
    _workflow(repo, "bad.yml", "      - uses: sigstore/cosign-installer@v4\n")
    assert _run(pins, repo) == 1
    err = capsys.readouterr().err
    assert "FAIL: 1 new sliding-major-tag reference(s)" in err
    assert "+ sigstore/cosign-installer@v4" in err


def test_baseline_grandfathers_sliding_major(pins, repo: Path, capsys):
    _workflow(
        repo,
        "grandfathered.yml",
        "      - uses: Swatinem/rust-cache@v2\n      - uses: actions/checkout@v6\n",
    )
    baseline = repo / "baseline.txt"
    baseline.write_text(
        "# justification: upstream ships major tags only\nSwatinem/rust-cache@v2\n",
        encoding="utf-8",
    )
    assert _run(pins, repo, baseline) == 1
    err = capsys.readouterr().err
    # Baselined ref is tolerated; the un-baselined one still fails.
    assert "Swatinem/rust-cache@v2" not in err
    assert "+ actions/checkout@v6" in err


def test_fully_baselined_tree_passes(pins, repo: Path, capsys):
    _workflow(repo, "wf.yml", "      - uses: Swatinem/rust-cache@v2\n")
    baseline = repo / "baseline.txt"
    baseline.write_text("Swatinem/rust-cache@v2\n", encoding="utf-8")
    assert _run(pins, repo, baseline) == 0
    assert "1 baselined-sliding" in capsys.readouterr().out


def test_baseline_dedupes_repeated_occurrences(pins, repo: Path, capsys):
    """One baseline line covers every occurrence of the same ref."""
    body = "".join("      - uses: Swatinem/rust-cache@v2\n" for _ in range(23))
    _workflow(repo, "many.yml", body)
    baseline = repo / "baseline.txt"
    baseline.write_text("Swatinem/rust-cache@v2\n", encoding="utf-8")
    assert _run(pins, repo, baseline) == 0
    assert "23 total uses" in capsys.readouterr().out


def test_stale_baseline_entry_is_reported(pins, repo: Path, capsys):
    _workflow(repo, "wf.yml", "      - uses: actions/checkout@v4.2.2\n")
    baseline = repo / "baseline.txt"
    baseline.write_text("gone/action@v2\n", encoding="utf-8")
    assert _run(pins, repo, baseline) == 0
    out = capsys.readouterr().out
    assert "1 baseline entry(ies) no longer in tree" in out
    assert "- gone/action@v2" in out


def test_other_ref_warns_but_passes(pins, repo: Path, capsys):
    _workflow(
        repo,
        "other.yml",
        "      - uses: dtolnay/rust-toolchain@stable\n"
        "      - uses: pypa/gh-action-pypi-publish@release/v1\n",
    )
    assert _run(pins, repo) == 0
    out = capsys.readouterr().out
    assert "WARN: 2 'other' ref(s)" in out
    assert "dtolnay/rust-toolchain@stable" in out


def test_other_refs_are_grouped_not_one_line_each(pins, repo: Path, capsys):
    """37 identical branch pins must not produce a 37-line WARN wall."""
    body = "".join("      - uses: dtolnay/rust-toolchain@stable\n" for _ in range(37))
    _workflow(repo, "many-other.yml", body)
    assert _run(pins, repo) == 0
    out = capsys.readouterr().out
    assert "on 37 line(s)" in out
    assert "(37x:" in out
    assert "+34 more" in out


def test_missing_github_dir_errors(pins, tmp_path: Path, capsys):
    assert _run(pins, tmp_path) == 1
    assert "not found" in capsys.readouterr().err


def test_renamed_workflow_dir_fails_closed(pins, tmp_path: Path, capsys):
    """`.github` existing is not enough — the workflows dir itself must exist.

    Guarding on `.github` alone made a typo'd / renamed directory print
    "OK ... (0 total uses)" and exit 0: blindness reported as success, which
    is the exact defect this gate exists to catch.
    """
    (tmp_path / ".github" / "wurkflows").mkdir(parents=True)
    assert _run(pins, tmp_path) == 1
    assert "not found" in capsys.readouterr().err


def test_zero_discovered_uses_fails_closed(pins, repo: Path, capsys):
    """An empty (but present) workflows dir means discovery is broken."""
    assert _run(pins, repo) == 1
    assert "discovery found 0 uses:" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Quoted refs: YAML permits quoting the value, and the quotes must not leak
# into the version — `v6'` misses SLIDING_MAJOR_RE and silently downgrades a
# hard FAIL to a WARN, leaving the whole PR #414 class reachable.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "      - uses: 'actions/checkout@v6'\n",
        '      - uses: "actions/checkout@v6"\n',
        "        uses: 'actions/checkout@v6'\n",
        '        uses: "actions/checkout@v6"\n',
    ],
)
def test_quoted_sliding_major_still_fails_gate(pins, repo: Path, line: str, capsys):
    _workflow(repo, "quoted.yml", line)
    assert _refs(pins, repo) == ["actions/checkout@v6"]
    assert _run(pins, repo) == 1
    assert "actions/checkout@v6" in capsys.readouterr().err


@pytest.mark.parametrize(
    "line",
    [
        "      - uses: 'actions/checkout@v6.1.0'\n",
        '      - uses: "actions/checkout@v6.1.0"\n',
    ],
)
def test_quoted_semver_passes(pins, repo: Path, line: str):
    _workflow(repo, "quoted-ok.yml", line)
    assert _refs(pins, repo) == ["actions/checkout@v6.1.0"]
    assert _run(pins, repo) == 0


def test_update_baseline_writes_sliding_refs(pins, repo: Path):
    _workflow(
        repo,
        "wf.yml",
        "      - uses: Swatinem/rust-cache@v2\n"
        "      - uses: actions/checkout@v4.2.2\n"
        "      - uses: docker/setup-qemu-action@v3\n",
    )
    baseline = repo / "baseline.txt"
    argv = ["--repo-root", str(repo), "--baseline", str(baseline), "--update-baseline"]
    assert pins.main(argv) == 0
    assert pins.load_baseline(baseline) == {
        "Swatinem/rust-cache@v2",
        "docker/setup-qemu-action@v3",
    }


# --------------------------------------------------------------------------
# The real tree
# --------------------------------------------------------------------------


def test_real_repo_sees_both_uses_forms(pins):
    """Guard the 52%-blind-spot regression at repo scale.

    If a future edit narrows USES_RE back to the plain form, the count here
    collapses by roughly half and this test fails.
    """
    refs = pins.collect_uses(REPO_ROOT)
    assert len(refs) > 700, f"only {len(refs)} uses: lines found — regex narrowed?"
    list_form = sum(
        1
        for path, lineno, _ in refs
        if path.read_text(encoding="utf-8")
        .splitlines()[lineno - 1]
        .lstrip()
        .startswith("-")
    )
    assert list_form > 400, f"only {list_form} list-form uses: lines — regex narrowed?"


def test_real_repo_gate_passes(pins, capsys):
    """The committed baseline must cover the committed tree."""
    assert pins.main(["--repo-root", str(REPO_ROOT)]) == 0
    assert "OK no new sliding-tag references" in capsys.readouterr().out
