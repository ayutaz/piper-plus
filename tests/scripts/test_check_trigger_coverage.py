"""Unit tests for scripts/check_trigger_coverage.py.

Regression focus: the gate resolved a GATE SCRIPT'S INPUTS on the pre-commit
side but NOT on the workflow side. It therefore required the script to appear
in a workflow's ``paths:`` while never requiring the files that script reads.
A gate could be given a new file to compare and go un-triggered by changes to
that file -- which is the exact failure the gate exists to prevent.

Measured on dev before the fix, with fully explicit (no-glob) paths lists:

  * ``contract-gates-extended.yml`` invokes ``check_audio_format_contract.py``,
    which names ``src/python_run/piper_plus/voice.py``,
    ``src/go/piperplus/synthesize.go`` and
    ``src/csharp/PiperPlus.Core/Inference/PiperSession.cs`` -- none listed.
  * ``dictionary-consistency.yml`` invokes ``check_dictionary_consistency.py``,
    which reads ``docs/spec/dictionary-mirrors.toml`` -- a mirror declaration,
    which this gate's own rule says may never be exempted.
  * ``test-hf-space.yml`` invokes ``check_hf_space_gradio_sync.py``, whose
    third pin site ``src/python_run/requirements_webui.txt`` was missing. That
    gap was known and recorded in CHANGELOG as "別途必要" precisely because
    nothing caught it automatically.

These tests pin the new behaviour so disabling it fails here rather than
silently reducing the gate to its old, weaker form.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_trigger_coverage.py"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("check_trigger_coverage", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tc():
    return _load_module()


def test_gate_script_inputs_resolves_what_a_real_gate_reads(tc):
    """The inputs of a real in-tree gate, not a synthetic one.

    check_audio_format_contract.py names its runtime sources in a list; those
    are exactly the files a change to which must re-run the gate.
    """
    tracked = tc.tracked_files()
    inputs = tc.gate_script_inputs("scripts/check_audio_format_contract.py", tracked)

    assert "src/python_run/piper_plus/voice.py" in inputs
    assert "src/go/piperplus/synthesize.go" in inputs


def test_gate_script_inputs_skips_self_analysis_scripts(tc):
    """A checker that names paths as DATA must not have them demanded.

    check_trigger_coverage.py audits every workflow and hook, so it names all
    of them; test_sync_gates_meta.py names 7 other gates and their contract
    TOMLs in order to mutate each and assert the gate notices. Resolving those
    as "inputs" produced 41 of 54 findings before they were exempted, all of
    them demands that unrelated workflows trigger on unrelated contracts.
    """
    tracked = tc.tracked_files()

    for script in sorted(tc.SELF_ANALYSIS_EXEMPT_SCRIPTS):
        assert tc.gate_script_inputs(script, tracked) == set(), script

    # Anti-vacuity: the exemption must be narrow. A non-exempt gate still
    # resolves, otherwise the assertion above would pass on a gate that
    # resolves nothing at all.
    assert tc.gate_script_inputs(
        "scripts/check_audio_format_contract.py", tracked
    ), "a non-exempt gate must still resolve its inputs"


def test_gate_script_inputs_is_empty_for_a_missing_script(tc):
    tracked = tc.tracked_files()
    assert tc.gate_script_inputs("scripts/check_does_not_exist.py", tracked) == set()


def test_referenced_paths_includes_an_invoked_gates_inputs(tc):
    """The workflow side must credit the gate's inputs, not just the gate.

    This is the behaviour that was absent. A workflow whose only mention of a
    file is "it runs a gate that reads it" must still be required to trigger
    on that file.
    """
    tracked = tc.tracked_files()
    workflow_text = (
        "on:\n"
        "  pull_request:\n"
        "    paths:\n"
        "      - 'scripts/check_audio_format_contract.py'\n"
        "jobs:\n"
        "  gate:\n"
        "    steps:\n"
        "      - run: |\n"
        "          python scripts/check_audio_format_contract.py --check\n"
    )

    found = tc.referenced_paths(workflow_text, tracked)

    assert "scripts/check_audio_format_contract.py" in found, "the gate itself"
    assert "src/python_run/piper_plus/voice.py" in found, (
        "the gate's INPUT -- absent before this fix, which is how a gate could "
        "be handed a new file to compare and never run on changes to it"
    )


def test_referenced_paths_does_not_invent_paths_without_a_gate(tc):
    """Anti-vacuity: a workflow that invokes no gate gains nothing.

    Without this, a bug that unconditionally unioned some path set would pass
    the assertion above.
    """
    tracked = tc.tracked_files()
    workflow_text = (
        "on:\n"
        "  pull_request:\n"
        "    paths:\n"
        "      - 'README.md'\n"
        "jobs:\n"
        "  noop:\n"
        "    steps:\n"
        "      - run: echo hello\n"
    )

    assert tc.referenced_paths(workflow_text, tracked) == set()


def test_mirror_declarations_are_recognised(tc):
    """A docs/spec/*-mirrors.toml is never exemptible, so it must be matched.

    Two of the findings this fix surfaced were mirror declarations
    (dictionary-consistency.yml, zh-en-loanword-sync.yml). If the pattern
    stopped matching, those would silently become allowlistable.
    """
    assert tc.MIRROR_DECLARATION_RE.match("docs/spec/dictionary-mirrors.toml")
    assert tc.MIRROR_DECLARATION_RE.match("docs/spec/loanword-mirrors.toml")
    assert not tc.MIRROR_DECLARATION_RE.match("docs/spec/pua-contract.toml")
