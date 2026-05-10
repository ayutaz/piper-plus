#!/usr/bin/env python3
"""Tests for French runtime phonemizer (``piper.phonemize.french``).

Includes a strict parity matrix that pins the runtime output against the
training-side phonemizer (``piper_plus_g2p.french``).  The two
implementations are required to agree token-for-token on every entry of
the matrix.

The two sides differ in their final wrapping:

* Training side ``phonemize_french`` returns the bare IPA token list
  (no BOS/EOS, no PUA mapping).
* Runtime side ``phonemize_french`` wraps the same tokens with
  ``["^"] + ... + ["$"]`` and runs ``map_sequence`` (PUA assignment) twice.

For parity purposes we compare the *pre-wrap* output of the runtime side
(``_phonemize_french_raw``) with PUA codepoints reverse-mapped via
``CHAR2TOKEN``.  This isolates the pure G2P logic, which is what we want
to keep in lockstep across training and runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the runtime piper package is importable from the python_run tree.
sys.path.insert(0, str(Path(__file__).parent.parent))

from piper.phonemize.french import (  # noqa: E402
    _phonemize_french_raw as runtime_phonemize_french_raw,
)
from piper.phonemize.french import (  # noqa: E402
    phonemize_french as runtime_phonemize_french,
)
from piper.phonemize.token_mapper import CHAR2TOKEN  # noqa: E402
from piper_plus_g2p.french import (  # noqa: E402
    phonemize_french as training_phonemize_french,
)


def _runtime_ipa_tokens(text: str) -> list[str]:
    """Return the runtime IPA token list with PUA codepoints reversed.

    Mirrors what the training side ``phonemize_french`` returns directly.
    """
    raw = runtime_phonemize_french_raw(text)
    return [CHAR2TOKEN.get(tok, tok) for tok in raw]


# ---------------------------------------------------------------------------
# 50-case parity matrix.
#
# Each entry is a French utterance that exercises liaison, élision, or a
# baseline G2P path.  The parity test asserts byte-for-byte equality
# between training and runtime outputs.
# ---------------------------------------------------------------------------

PARITY_CASES: list[str] = [
    # ----- Obligatory liaison: determiner + vowel -----
    "les amis",
    "des amis",
    "ces amis",
    "mes amis",
    "tes amis",
    "ses amis",
    "nos amis",
    "vos amis",
    "des hommes",
    "mes enfants",
    # ----- Obligatory liaison: numerals + vowel -----
    "deux amis",
    "trois amis",
    "six amis",
    "dix amis",
    # ----- Obligatory liaison: pronouns + vowel -----
    "nous allons",
    "vous avez",
    "ils ont",
    "elles ont",
    "on a",
    # ----- Obligatory liaison: prepositions / adverbs -----
    "en été",
    "dans une",
    "sans aide",
    "chez elle",
    "très important",
    "plus important",
    # ----- Obligatory liaison: 'un' / possessives -----
    "un ami",
    "mon ami",
    "ton ami",
    "son ami",
    # ----- Obligatory liaison: short words / 'est' -----
    "tout est",
    "quand il",
    "il est ami",
    "ont eu",
    "sont arrivés",
    "font une",
    "vont arriver",
    # ----- Élision: l' / d' / j' / c' / n' / qu' -----
    "l'eau",
    "l'arbre",
    "j'ai",
    "j'aime",
    "c'est",
    "n'a",
    "d'accord",
    "qu'il",
    "qu'est-ce",
    # ----- Baseline (no liaison or elision) -----
    "bonjour",
    "merci",
    "vous",
    "amour",
    "monde",
    "fille",
]

# The matrix must contain at least 50 cases per task spec.
assert len(PARITY_CASES) >= 50, f"need >= 50 parity cases, got {len(PARITY_CASES)}"


class TestFrenchRuntimeTrainingParity:
    """50-case byte-for-byte parity matrix between training and runtime."""

    @pytest.mark.parametrize("text", PARITY_CASES)
    def test_runtime_matches_training(self, text: str) -> None:
        """``training.phonemize(text) == runtime.phonemize(text)`` token-wise.

        Compares the raw IPA token list (PUA codepoints reversed) of the
        runtime side against the bare training-side output.  Any drift in
        liaison or élision logic causes this to fail.
        """
        training_tokens = training_phonemize_french(text)
        runtime_tokens = _runtime_ipa_tokens(text)
        assert training_tokens == runtime_tokens, (
            f"Drift detected for {text!r}:\n"
            f"  training: {training_tokens}\n"
            f"  runtime : {runtime_tokens}"
        )


class TestRuntimeBosEosWrap:
    """Sanity checks on the runtime BOS/EOS wrapper (independent of parity)."""

    def test_runtime_wraps_with_bos_eos(self) -> None:
        tokens = runtime_phonemize_french("Bonjour")
        assert tokens[0] == "^"
        assert tokens[-1] == "$"

    def test_runtime_inner_tokens_match_training(self) -> None:
        """After stripping ^ and $ and reversing PUA, runtime equals training."""
        text = "les amis"
        runtime_tokens = runtime_phonemize_french(text)
        # Strip BOS / EOS
        assert runtime_tokens[0] == "^"
        assert runtime_tokens[-1] == "$"
        inner = runtime_tokens[1:-1]
        inner_ipa = [CHAR2TOKEN.get(t, t) for t in inner]
        assert inner_ipa == training_phonemize_french(text)


class TestLiaisonRuntime:
    """Spot-checks of liaison output independent of the parity matrix."""

    def test_les_amis_inserts_z(self) -> None:
        """``les amis`` -> /l ə z (space) a m i/."""
        assert _runtime_ipa_tokens("les amis") == [
            "l",
            "ə",
            "z",
            " ",
            "a",
            "m",
            "i",
        ]

    def test_un_ami_inserts_n(self) -> None:
        """``un ami`` -> /ɛ̃ n (space) a m i/."""
        assert _runtime_ipa_tokens("un ami") == [
            "ɛ̃",
            "n",
            " ",
            "a",
            "m",
            "i",
        ]

    def test_no_liaison_when_next_is_consonant(self) -> None:
        """``les bons`` -> no /z/ liaison (next word starts with consonant)."""
        tokens = _runtime_ipa_tokens("les bons")
        assert "z" not in tokens


class TestElisionRuntime:
    """Spot-checks of élision behaviour."""

    def test_leau(self) -> None:
        """``l'eau`` -> /l o/ (clitic merged with host)."""
        assert _runtime_ipa_tokens("l'eau") == ["l", "o"]

    def test_jaime(self) -> None:
        """``j'aime`` -> /ʒ ɛ m/."""
        assert _runtime_ipa_tokens("j'aime") == ["ʒ", "ɛ", "m"]

    def test_cest(self) -> None:
        """``c'est`` -> /s ɛ s/ (snapshot of current behaviour)."""
        assert _runtime_ipa_tokens("c'est") == ["s", "ɛ", "s"]

    def test_larbre(self) -> None:
        """``l'arbre`` -> /l a ʁ b ʁ/."""
        assert _runtime_ipa_tokens("l'arbre") == ["l", "a", "ʁ", "b", "ʁ"]
