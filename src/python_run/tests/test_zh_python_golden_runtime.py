"""Runtime Chinese G2P vs the training-side golden (issue #790).

``piper_plus.phonemize.chinese`` is a separate implementation from the
training-side ``piper_plus_g2p`` that produced
``tests/fixtures/g2p/phoneme_test_cases_golden.json``. The other runtimes
only checked that Chinese output was non-empty, which let dictionaries that
dropped every tone ship unnoticed; this compares token by token.
"""

import json
import re
from pathlib import Path

import pytest


pytest.importorskip("pypinyin", reason="pypinyin not installed")

from piper_plus.phonemize.chinese import phonemize_chinese  # noqa: E402
from piper_plus.phonemize.token_mapper import map_sequence  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN = REPO_ROOT / "tests" / "fixtures" / "g2p" / "phoneme_test_cases_golden.json"

# Python's MultilingualPhonemizer drops the sentence punctuation that the
# per-language phonemizers keep; compare the spoken tokens only.
SKIPPED = {"^", "$", "_", " ", ".", ",", "!", "?", ";", ":"}


def _zh_cases():
    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))["test_cases"]
    # Latin letters and digits go through the ZH-EN / number handling.
    return [
        c
        for c in cases
        if c["language"] == "zh" and not re.search(r"[A-Za-z0-9]", c["input"])
    ]


def test_golden_has_enough_chinese_cases():
    assert len(_zh_cases()) >= 40


@pytest.mark.parametrize("case", _zh_cases(), ids=lambda c: c["input"])
def test_runtime_chinese_matches_golden(case):
    expected = [
        t for t in map_sequence(case["expected_phonemes"].split()) if t not in SKIPPED
    ]
    actual = [t for t in phonemize_chinese(case["input"]) if t not in SKIPPED]
    assert actual == expected
