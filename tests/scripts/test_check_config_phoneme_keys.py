"""Tests for scripts/check_config_phoneme_keys.py and the PUA config jobs.

Two jobs in ``pua-consistency.yml`` were meant to catch configs the C++
reader cannot load, and neither did:

* ``config-key-validator`` looked for files named ``config.json`` under
  ``test/``, ``tests/`` or ``fixtures/``. The repository's configs are
  ``*.onnx.json``, so it validated nothing and printed "No test/fixture
  config.json files to validate." on every run.
* ``distributed-config-validator`` rejected every multi-codepoint key, so it
  failed on the public zs-v1 base (raw ``ɔɪ``/``œ̃``/``ɐ̃``, which the C++
  reader accepts), read ``resolve/main`` instead of the pinned revision, and
  turned a fetch failure into a skipped model.

The script now applies the C++ reader's rule: single codepoints and the
three raw aliases from the PUA contract pass, anything else fails.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import urllib.error
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_config_phoneme_keys.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pua-consistency.yml"
PIPER_CPP = REPO_ROOT / "src" / "cpp" / "piper.cpp"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_config_phoneme_keys", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_config_phoneme_keys"] = module
    spec.loader.exec_module(module)
    return module


ck = _load_module()
ALIASES = ck.load_raw_aliases()
OI, OE, AT = "ɔɪ", "œ̃", "ɐ̃"


def test_single_codepoint_keys_pass():
    assert ck.check_phoneme_id_map({"a": [1], "": [2], "^": [3]}, ALIASES) == []


def test_the_three_raw_aliases_pass():
    assert ck.check_phoneme_id_map({OI: [5], OE: [6], AT: [7], "a": [1]}, ALIASES) == []


@pytest.mark.parametrize("key", ["a:", "N_m", "ab", "ɔ̃"])
def test_an_unknown_multi_codepoint_key_fails(key):
    problems = ck.check_phoneme_id_map({key: [1]}, ALIASES)
    assert len(problems) == 1 and "U+" in problems[0]


def test_a_raw_alias_that_disagrees_with_its_pua_key_fails():
    assert ck.check_phoneme_id_map({OI: [5], "": [9]}, ALIASES)
    assert ck.check_phoneme_id_map({OI: [5], "": [5]}, ALIASES) == []


def test_aliases_are_the_ones_the_cpp_reader_accepts():
    source = PIPER_CPP.read_text(encoding="utf-8")
    block = source[source.index("knownTokens") : source.index("knownTokens.find")]
    cpp = {
        "".join(chr(int(h, 16)) for h in re.findall(r"\\u([0-9A-Fa-f]{4})", token)): int(cp, 16)
        for token, cp in re.findall(r'\{"((?:\\u[0-9A-Fa-f]{4})+)",\s*0x([0-9A-Fa-f]+)\}', block)
    }
    assert cpp == ALIASES


def test_alias_codepoints_come_from_pua_json():
    assert ALIASES == {OI: 0xE062, OE: 0xE063, AT: 0xE064}


def test_repo_mode_validates_the_shipped_configs():
    """The old job matched no file at all; the repo set must be non-empty and
    include the configs that ship next to models."""
    paths = {p.relative_to(REPO_ROOT).as_posix() for p in ck.repo_configs(REPO_ROOT)}
    assert "test/models/multilingual-test-medium.onnx.json" in paths
    assert "huggingface-space/zs-v1/base.onnx.json" in paths
    assert ck.main(["--repo"]) == 0


def test_a_bad_local_config_fails(tmp_path):
    cfg = tmp_path / "m.onnx.json"
    cfg.write_text('{"phoneme_id_map": {"a:": [1]}}', encoding="utf-8")
    assert ck.main([str(cfg)]) == 1


def test_distributed_urls_use_the_pinned_revision():
    urls = ck.distributed_urls()
    base = [u for u in urls if "piper-plus-base" in u]
    assert base == [
        "https://huggingface.co/ayousanz/piper-plus-base/resolve/"
        "3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1/base.onnx.json"
    ]
    assert len(urls) == len(set(urls))


def test_a_fetch_failure_fails_instead_of_skipping(monkeypatch):
    def boom(*_a, **_k):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(ck.urllib.request, "urlopen", boom)
    monkeypatch.setattr(ck.time, "sleep", lambda _s: None)
    assert ck.main(["--distributed"]) == 1


def test_an_empty_distributed_map_fails(monkeypatch):
    monkeypatch.setattr(ck, "_fetch", lambda _url: {"phoneme_id_map": {}})
    assert ck.main(["--distributed"]) == 1


# ---------------------------------------------------------------------------
# Workflow contract
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _runs(job: dict) -> str:
    return "\n".join(s.get("run", "") for s in job["steps"])


def test_in_repo_job_runs_the_script_over_the_repo(jobs):
    assert "scripts/check_config_phoneme_keys.py --repo" in _runs(jobs["config-key-validator"])


def test_distributed_job_runs_the_script_on_every_event(jobs):
    job = jobs["distributed-config-validator"]
    assert "scripts/check_config_phoneme_keys.py --distributed" in _runs(job)
    assert "if" not in job
