"""Cross-runtime Swedish per-word LID parity fixture matrix (Issue #539).

Loads the canonical ``tests/fixtures/g2p/swedish_lid_matrix.json`` (the single
shared fixture that EVERY runtime asserts against, mirrored byte-for-byte into
each runtime's test dir by ``scripts/check_swedish_lid_consistency.py``) and
verifies that the Python canonical ``MultilingualPhonemizer.segment_text``
agrees with each case's ``expect_contains_sv`` flag.

Each case builds a detector with ``languages = fixture["languages"]`` and
``default_latin = fixture["default_latin"]``, runs segmentation, and asserts
``("sv" in segment languages) == expect_contains_sv``. The sister tests in
Rust (piper-plus-g2p + piper-core) / Go / C++ / C# / WASM consume the *same*
fixture, so cross-runtime agreement on these cases is the parity proof.

Reference fixture/test: ``tests/fixtures/g2p/zh_en_loanword_matrix.json`` +
``src/python/g2p/tests/test_golden_fixtures.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from piper_plus_g2p.multilingual import MultilingualPhonemizer

# Repo root: tests/test_swedish_lid_matrix.py -> g2p/ -> python/ -> src/ -> repo
_REPO_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "g2p" / "swedish_lid_matrix.json"


def _load_fixture() -> dict:
    if not _FIXTURE.exists():
        pytest.fail(
            f"Swedish LID matrix fixture missing: {_FIXTURE}. "
            "Re-sync via `python scripts/check_swedish_lid_consistency.py --fix`."
        )
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


_FIXTURE_DATA = _load_fixture()


def _segment_languages(text: str) -> list[str]:
    phon = MultilingualPhonemizer(
        _FIXTURE_DATA["languages"],
        default_latin_language=_FIXTURE_DATA["default_latin"],
    )
    return [seg["language"] for seg in phon.segment_text(text)]


def test_fixture_schema() -> None:
    """The fixture must be schema-version 1 with a non-empty ``cases`` list."""
    assert _FIXTURE_DATA["schema_version"] == 1
    assert _FIXTURE_DATA["languages"] == ["en", "sv"]
    assert _FIXTURE_DATA["default_latin"] == "en"
    assert isinstance(_FIXTURE_DATA["cases"], list)
    assert len(_FIXTURE_DATA["cases"]) >= 10


@pytest.mark.parametrize(
    ("text", "expect_contains_sv"),
    [
        pytest.param(case["text"], case["expect_contains_sv"], id=case["text"])
        for case in _FIXTURE_DATA["cases"]
    ],
)
def test_swedish_lid_matrix(text: str, expect_contains_sv: bool) -> None:
    """``"sv" in segment languages`` must equal the fixture's expectation."""
    langs = _segment_languages(text)
    assert ("sv" in langs) == expect_contains_sv, (
        f"[sv-lid] {text!r}: expected ('sv' in langs)={expect_contains_sv}, "
        f"got langs={langs}.\n"
        "If this is intentional, update the matrix in "
        "tests/fixtures/g2p/swedish_lid_matrix.json and re-sync via "
        "`python scripts/check_swedish_lid_consistency.py --fix`."
    )
