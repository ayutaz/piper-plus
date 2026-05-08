"""Regression tests for French runtime liaison/élision parity.

Pins the byte-for-byte equality of the training-side
(``piper_plus_g2p.french.FrenchPhonemizer``) and runtime-side
(``piper.phonemize.french``) phonemizers on the 8 canonical cases that
exercise the liaison / élision logic ported in commit b5581726.

History
-------
Before b5581726, the runtime side did **not** implement liaison or
élision (training-only).  ``les amis``, ``l'eau``, ``j'aime`` produced
different phoneme sequences in training vs. runtime, which silently broke
inference quality on PyPI ``piper-plus``.  The fix ported both rule sets
to the runtime; this test pins that the two sides remain in lockstep.

Note: the existing ``src/python_run/tests/test_french_phonemization.py``
covers a 50-case parity matrix.  This file adds a *focused* regression
matrix targeting the exact 8 cases called out in the audit, plus the
specific liaison/élision categories they probe (vowel determiners,
liaison muette h, plural adjectives, subject pronouns, verb-vowel,
``ille`` exception list).  The two test files are intentionally
redundant: this file is the regression gate, the other is the broad
coverage matrix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


# Ensure the runtime piper package is importable from the python_run tree.
_RUNTIME_DIR = Path(__file__).resolve().parents[3] / "python_run"
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

from piper.phonemize.french import (  # noqa: E402
    _phonemize_french_raw as runtime_phonemize_french_raw,
)
from piper.phonemize.token_mapper import CHAR2TOKEN  # noqa: E402
from piper_plus_g2p.french import FrenchPhonemizer  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _runtime_ipa_tokens(text: str) -> list[str]:
    """Return the runtime IPA token list with PUA codepoints reversed.

    The runtime side maps multi-codepoint phonemes (e.g. ``ɛ̃``) into PUA
    single-codepoint tokens via :func:`piper.phonemize.token_mapper.map_sequence`.
    To compare byte-for-byte against the training-side bare IPA output we
    reverse the mapping here using ``CHAR2TOKEN``.
    """
    raw = runtime_phonemize_french_raw(text)
    return [CHAR2TOKEN.get(tok, tok) for tok in raw]


# ---------------------------------------------------------------------------
# Regression matrix: 8 canonical cases from the audit (commit b5581726).
#
# Each tuple is (text, category) where category documents which rule the
# case exercises.  The category strings are pinned so any future drift in
# wording can be diff-reviewed.
# ---------------------------------------------------------------------------

LIAISON_ELISION_CASES: list[tuple[str, str]] = [
    ("les amis", "liaison: determiner les + vowel"),
    ("l'eau", "élision: clitic l' before vowel"),
    ("j'aime", "élision: clitic j' before vowel"),
    ("un homme", "liaison: 'un' + silent h (h muet)"),
    ("petits enfants", "liaison: plural adjective petits + vowel"),
    ("vous avez", "liaison: subject pronoun vous + vowel"),
    ("nous écrivons", "liaison: subject pronoun nous + vowel é"),
    ("la ville", "no liaison: 'ille' exception list (ville)"),
]


# ---------------------------------------------------------------------------
# Parity tests: training FrenchPhonemizer.phonemize() must match runtime
# byte-for-byte after PUA reversal.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def training_phonemizer() -> FrenchPhonemizer:
    """Single shared instance of the training-side French phonemizer."""
    return FrenchPhonemizer()


class TestFrenchLiaisonElisionRuntimeParity:
    """Regression: training and runtime must agree on liaison / élision rules.

    These 8 cases are the exact regression matrix called out in the
    audit that found the missing runtime port (commit b5581726).
    """

    @pytest.mark.parametrize(("text", "category"), LIAISON_ELISION_CASES)
    def test_phonemize_byte_for_byte(
        self,
        training_phonemizer: FrenchPhonemizer,
        text: str,
        category: str,
    ) -> None:
        """``training.phonemize(text)`` equals ``runtime.phonemize(text)``.

        Compares the bare IPA output of
        ``FrenchPhonemizer.phonemize`` (training side) against the
        runtime side's raw IPA token list with PUA codepoints reversed.

        The runtime side wraps with ``^``/``$`` and applies PUA mapping;
        we reverse those wrappers in :func:`_runtime_ipa_tokens` so the
        comparison isolates the pure G2P logic, which is what must
        remain in lockstep.
        """
        training_tokens = training_phonemizer.phonemize(text)
        runtime_tokens = _runtime_ipa_tokens(text)
        assert training_tokens == runtime_tokens, (
            f"Drift detected for {text!r} ({category}):\n"
            f"  training: {training_tokens}\n"
            f"  runtime : {runtime_tokens}\n"
            f"If this fails, the runtime-side liaison / élision logic\n"
            f"in src/python_run/piper/phonemize/french.py has drifted\n"
            f"from the training side in src/python/g2p/piper_plus_g2p/french.py"
        )


class TestFrenchLiaisonElisionRuntimeProsodyParity:
    """The training-side ``phonemize_with_prosody`` token list must also match.

    The runtime side does not expose prosody info; we only assert that the
    *phoneme* component of the prosody output equals the runtime output,
    pinning that liaison / élision tokens are emitted in the same order
    regardless of which API the training side calls.
    """

    @pytest.mark.parametrize(("text", "category"), LIAISON_ELISION_CASES)
    def test_prosody_phoneme_list_matches_runtime(
        self,
        training_phonemizer: FrenchPhonemizer,
        text: str,
        category: str,
    ) -> None:
        prosody_tokens, _ = training_phonemizer.phonemize_with_prosody(text)
        runtime_tokens = _runtime_ipa_tokens(text)
        assert prosody_tokens == runtime_tokens, (
            f"phonemize_with_prosody drift for {text!r} ({category}):\n"
            f"  training (prosody path): {prosody_tokens}\n"
            f"  runtime                 : {runtime_tokens}"
        )


class TestFrenchLiaisonElisionExpectedPhonemes:
    """Spot-check that the expected liaison/élision phonemes are produced.

    Independent of parity, these tests pin the *content* of the output so
    that a *correlated* drift on both sides (e.g. someone removing liaison
    from both files) would still be caught.
    """

    def test_les_amis_inserts_z_liaison(
        self, training_phonemizer: FrenchPhonemizer
    ) -> None:
        """``les amis`` triggers /z/ liaison (les ends in silent s)."""
        tokens = training_phonemizer.phonemize("les amis")
        assert "z" in tokens, "expected /z/ liaison phoneme in 'les amis'"

    def test_un_homme_inserts_n_liaison(
        self, training_phonemizer: FrenchPhonemizer
    ) -> None:
        """``un homme`` triggers /n/ liaison through silent (muet) h."""
        tokens = training_phonemizer.phonemize("un homme")
        assert "n" in tokens, "expected /n/ liaison phoneme in 'un homme'"

    def test_leau_merges_clitic(self, training_phonemizer: FrenchPhonemizer) -> None:
        """``l'eau`` merges l' clitic with eau -> /l o/ (no spurious space)."""
        tokens = training_phonemizer.phonemize("l'eau")
        # Must NOT contain a space between l and o (clitic merged).
        assert " " not in tokens, "élision should suppress inter-clitic space"
        assert tokens[0] == "l", "élision clitic l' must produce /l/ first"

    def test_la_ville_uses_il_not_ij(
        self, training_phonemizer: FrenchPhonemizer
    ) -> None:
        """``la ville`` uses the /il/ exception (ville is in _ILLE_AS_IL)."""
        tokens = training_phonemizer.phonemize("la ville")
        # 'ville' must produce /v i l/ NOT /v i j/ (j-glide).
        # Find the 'v' and assert the next phonemes.
        assert "v" in tokens, "expected /v/ from 'ville'"
        v_idx = tokens.index("v")
        # After v: i then l (not j).  The trailing 'e' is silent.
        assert tokens[v_idx : v_idx + 3] == ["v", "i", "l"], (
            f"expected /v i l/ for 'ville' (ille exception), got {tokens[v_idx : v_idx + 3]}"
        )
