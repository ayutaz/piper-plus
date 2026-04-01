"""Compatibility tests: piper_g2p output vs piper_train output.

These tests verify that piper_g2p produces identical results to
piper_train when the appropriate transformations are applied.

These tests are skipped when piper_train is not installed (e.g. in CI
where only piper_g2p is available).
"""

import pytest

from tests.conftest import requires_en, requires_ja

_has_piper_train = pytest.importorskip is not None  # always True, placeholder

try:
    import piper_train.phonemize  # noqa: F401

    _has_piper_train = True
except ImportError:
    _has_piper_train = False

requires_piper_train = pytest.mark.skipif(
    not _has_piper_train, reason="piper_train not installed"
)


@requires_ja
@requires_piper_train
class TestJACompat:
    def test_ja_tokens_ipa_to_pua(self):
        """piper_g2p tokens + BOS/EOS + PUA == piper_train phonemize_japanese().

        piper_g2p returns raw IPA tokens (no BOS/EOS, no PUA).
        After adding BOS/EOS and applying PUA mapping, the result should
        match piper_train's phonemize_japanese().
        """
        from piper_train.phonemize.japanese import phonemize_japanese

        from piper_g2p.encode.pua import map_token
        from piper_g2p.japanese import JapanesePhonemizer

        text = "こんにちは"
        p = JapanesePhonemizer()
        g2p_tokens = p.phonemize(text)

        # Add BOS/EOS (piper_train always adds "^" at start and "$" at end
        # for declarative sentences)
        full_tokens = ["^"] + g2p_tokens + ["$"]

        # Apply PUA mapping (piper_train uses map_sequence internally)
        pua_tokens = [map_token(t) for t in full_tokens]

        train_tokens = phonemize_japanese(text)
        assert pua_tokens == train_tokens, (
            f"Mismatch:\n  g2p+PUA: {pua_tokens}\n  train:   {train_tokens}"
        )

    def test_pua_mapping_matches(self):
        """piper_g2p FIXED_PUA_MAPPING matches piper_train's FIXED_PUA_MAPPING."""
        from piper_train.phonemize.token_mapper import (
            FIXED_PUA_MAPPING as train_mapping,
        )

        from piper_g2p.encode.pua import FIXED_PUA_MAPPING as g2p_mapping

        assert g2p_mapping == train_mapping

    def test_ja_id_map_matches(self):
        """piper_g2p get_phoneme_id_map('ja') matches
        piper_train get_japanese_id_map()."""
        from piper_train.phonemize.jp_id_map import get_japanese_id_map

        from piper_g2p.encode.id_maps import get_phoneme_id_map

        g2p_map = get_phoneme_id_map("ja")
        train_map = get_japanese_id_map()
        assert g2p_map == train_map


@requires_ja
@requires_en
@requires_piper_train
class TestENCompat:
    def test_en_phonemize_matches(self):
        """piper_g2p EN output matches piper_train EN output for the same text."""
        from piper_train.phonemize.english import phonemize_english

        from piper_g2p.english import EnglishPhonemizer

        text = "Hello, how are you today?"
        p = EnglishPhonemizer()
        g2p_tokens = p.phonemize(text)
        train_tokens = phonemize_english(text)
        assert g2p_tokens == train_tokens, (
            f"Mismatch:\n  g2p:   {g2p_tokens}\n  train: {train_tokens}"
        )
