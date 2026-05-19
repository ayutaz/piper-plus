"""Unit tests for scripts/check_doc_examples.py audit subcommand (T-009)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_doc_examples.py"
CONTRACT = REPO_ROOT / "docs" / "spec" / "doc-examples-contract.toml"
SAMPLE_DOCS = REPO_ROOT / "tests" / "fixtures" / "doc_examples_audit" / "sample_docs"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "check_doc_examples",
        SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


@pytest.fixture(scope="module")
def classifier_mod():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from doc_examples import classifier

    return classifier


@pytest.fixture(scope="module")
def extractor_mod():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from doc_examples import extractor

    return extractor


@pytest.fixture(scope="module")
def config(classifier_mod):
    return classifier_mod.load_config(CONTRACT)


# ----- extractor (UT-1) -----


def test_extractor_returns_blocks_with_metadata(extractor_mod):
    text = (
        "intro\n\n"
        "```bash\n"
        "echo hi\n"
        "```\n\n"
        "between\n\n"
        "```python\n"
        "print(1)\n"
        "print(2)\n"
        "```\n"
    )
    blocks = extractor_mod.extract_from_text(text, file="x.md")
    assert len(blocks) == 2
    assert blocks[0].language == "bash"
    assert blocks[0].body.strip() == "echo hi"
    assert blocks[1].language == "python"
    assert blocks[1].body.count("print") == 2
    # Hash determinism: same body → same hash.
    assert (
        blocks[0].hash_sha1
        == extractor_mod.extract_from_text(text, file="other.md")[0].hash_sha1
    )


# ----- classifier (UT-2 〜 UT-5) -----


def test_classifier_flags_placeholder(classifier_mod, config):
    res = classifier_mod.classify(
        language="bash",
        body="curl http://<HA_TOKEN>:8123/api/",
        config=config,
    )
    assert res.category == classifier_mod.CATEGORY_NEEDS_PLACEHOLDER
    assert "<HA_TOKEN>" in res.placeholders_detected


def test_classifier_respects_doctest_skip(classifier_mod, config):
    res = classifier_mod.classify(
        language="python",
        body="# doctest:skip\nimport torch\n",
        config=config,
    )
    assert res.category == classifier_mod.CATEGORY_SKIP_WARRANTED
    assert any("doctest:skip" in d for d in res.directives_detected)


def test_classifier_detects_env_dependency(classifier_mod, config):
    res = classifier_mod.classify(
        language="bash",
        body="ls /data/piper/output-multilingual/",
        config=config,
    )
    assert res.category == classifier_mod.CATEGORY_SKIP_WARRANTED
    assert "/data/piper/" in res.env_dependencies


def test_classifier_passes_clean_block(classifier_mod, config):
    res = classifier_mod.classify(
        language="python",
        body="from pathlib import Path\nprint(Path('.').resolve())\n",
        config=config,
    )
    assert res.category == classifier_mod.CATEGORY_EXECUTABLE


def test_classifier_routes_unknown_language_to_skip(
    classifier_mod,
    config,
):
    res = classifier_mod.classify(
        language="erlang",
        body="-module(hello).\n",
        config=config,
    )
    assert res.category == classifier_mod.CATEGORY_SKIP_WARRANTED
    assert "unknown_language" in res.directives_detected


def test_classifier_normalises_aliases(classifier_mod, config):
    assert classifier_mod.normalize_language("sh", config) == "bash"
    assert classifier_mod.normalize_language("py3", config) == "python"
    assert classifier_mod.normalize_language("javascript", config) == "wasm"
    assert classifier_mod.normalize_language("erlang", config) == ""


# ----- silent-zero (UT-6) -----


def test_main_silent_zero_when_no_docs(
    mod,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    empty = tmp_path / "docs"
    empty.mkdir()
    rc = mod.main(
        [
            "audit",
            "--config",
            str(CONTRACT),
            "--docs-root",
            str(empty),
            "--repo-root",
            str(tmp_path),
            "--generated-at",
            "2026-05-19T00:00:00Z",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert "Collected blocks (total=0)" in captured.err
    assert "::warning::" in captured.err


# ----- audit JSON shape (UT-8) -----


def test_audit_fixture_run_produces_expected_categories(
    mod,
    tmp_path: Path,
):
    """Run the audit over the three category fixtures and verify counts."""
    out = tmp_path / "audit.json"
    # Stage the sample-docs under a tmp repo so the contract's
    # exclude_dirs (docs/proposals etc.) don't apply.
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    for name in ("executable.md", "placeholder.md", "skip.md"):
        (docs_root / name).write_text((SAMPLE_DOCS / name).read_text(encoding="utf-8"))
    rc = mod.main(
        [
            "audit",
            "--config",
            str(CONTRACT),
            "--docs-root",
            str(docs_root),
            "--repo-root",
            str(tmp_path),
            "--output",
            str(out),
            "--generated-at",
            "2026-05-19T00:00:00Z",
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    totals = payload["totals"]
    # executable.md: 1 bash + 1 python (both clean) → 2 executable
    # placeholder.md: 1 bash (<HA_TOKEN>) + 1 python (YOUR_API_KEY) → 2 placeholder
    # skip.md: 1 bash (doctest:skip) + 1 python (noexec) + 1 text (unknown lang) → 3 skip
    assert totals["executable"] == 2
    assert totals["needs_placeholder"] == 2
    assert totals["skip_warranted"] == 3
    assert totals["total"] == 7


def test_check_snapshot_drift_returns_one(
    mod,
    tmp_path: Path,
):
    """Modifying the corpus and comparing to a snapshot must exit 1."""
    out = tmp_path / "snapshot.json"
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "executable.md").write_text(
        (SAMPLE_DOCS / "executable.md").read_text(encoding="utf-8")
    )
    mod.main(
        [
            "audit",
            "--config",
            str(CONTRACT),
            "--docs-root",
            str(docs_root),
            "--repo-root",
            str(tmp_path),
            "--output",
            str(out),
            "--generated-at",
            "2026-05-19T00:00:00Z",
        ]
    )
    # Mutate the docs and re-run with --check-snapshot.
    (docs_root / "extra.md").write_text("```bash\necho new\n```\n")
    rc = mod.main(
        [
            "audit",
            "--config",
            str(CONTRACT),
            "--docs-root",
            str(docs_root),
            "--repo-root",
            str(tmp_path),
            "--check-snapshot",
            str(out),
            "--generated-at",
            "2026-05-19T00:00:00Z",
        ]
    )
    assert rc == 1


def test_committed_snapshot_matches_repo_docs(mod):
    """Running the audit against the repo's docs must match the snapshot.

    This is the public guarantee: anyone running the same script + spec
    against the same docs/ tree gets the same audit JSON.
    """
    snapshot = REPO_ROOT / "tests" / "fixtures" / "doc_examples_audit" / "audit.json"
    if not snapshot.exists():
        pytest.skip("audit.json snapshot not committed yet")
    rc = mod.main(
        [
            "audit",
            "--config",
            str(CONTRACT),
            "--docs-root",
            str(REPO_ROOT / "docs"),
            "--repo-root",
            str(REPO_ROOT),
            "--check-snapshot",
            str(snapshot),
            "--generated-at",
            "2026-05-19T00:00:00Z",
        ]
    )
    assert rc == 0, (
        "audit drifted from the committed snapshot — regenerate via "
        "`scripts/check_doc_examples.py audit --output "
        "tests/fixtures/doc_examples_audit/audit.json` and commit."
    )
