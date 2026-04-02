"""Compatibility tests: piper_g2p output vs piper_train output.

These tests verify that piper_g2p produces identical results to
piper_train when the appropriate transformations are applied.

These tests are skipped when piper_train is not installed (e.g. in CI
where only piper_g2p is available).
"""

import pytest

from tests.conftest import requires_en, requires_ja, requires_zh

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


@requires_piper_train
class TestMultilingualIDMapCompat:
    @pytest.mark.xfail(
        reason=(
            "piper_g2p uses fixed PUA mapping (pua.json) while piper_train "
            "uses dynamic register() which assigns extra PUA codepoints for "
            "Chinese compound finals (ai, ao, ang, etc.) not in pua.json"
        ),
        strict=True,
    )
    def test_multilingual_8lang_id_map_matches(self):
        """piper_g2p multilingual ID map matches piper_train for 8-language set."""
        from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map

        from piper_g2p.encode.id_maps import get_phoneme_id_map

        g2p_map = get_phoneme_id_map("ja-en-zh-ko-es-fr-pt-sv")
        train_map = get_multilingual_id_map(
            ["ja", "en", "zh", "ko", "es", "fr", "pt", "sv"]
        )
        assert g2p_map == train_map


@requires_zh
@requires_piper_train
class TestZHCompat:
    def test_zh_phonemize_matches(self):
        """piper_g2p ZH output + PUA matches piper_train ZH output."""
        from piper_train.phonemize.chinese import phonemize_chinese

        from piper_g2p.chinese import ChinesePhonemizer
        from piper_g2p.encode.pua import map_token

        text = "你好世界"
        p = ChinesePhonemizer()
        g2p_tokens = p.phonemize(text)
        g2p_mapped = [map_token(t) for t in g2p_tokens]
        train_tokens = phonemize_chinese(text)
        assert g2p_mapped == train_tokens, (
            f"Mismatch:\n  g2p+PUA: {g2p_mapped}\n  train:   {train_tokens}"
        )


@requires_piper_train
class TestESCompat:
    def test_es_phonemize_matches(self):
        """piper_g2p ES output + PUA matches piper_train ES output."""
        from piper_train.phonemize.spanish import phonemize_spanish

        from piper_g2p.encode.pua import map_token
        from piper_g2p.spanish import SpanishPhonemizer

        text = "Hola mundo"
        p = SpanishPhonemizer()
        g2p_tokens = p.phonemize(text)
        g2p_mapped = [map_token(t) for t in g2p_tokens]
        train_tokens = phonemize_spanish(text)
        assert g2p_mapped == train_tokens, (
            f"Mismatch:\n  g2p+PUA: {g2p_mapped}\n  train:   {train_tokens}"
        )


@requires_piper_train
class TestFRCompat:
    def test_fr_phonemize_matches(self):
        """piper_g2p FR output + PUA matches piper_train FR output."""
        from piper_train.phonemize.french import phonemize_french

        from piper_g2p.encode.pua import map_token
        from piper_g2p.french import FrenchPhonemizer

        text = "Bonjour le monde"
        p = FrenchPhonemizer()
        g2p_tokens = p.phonemize(text)
        g2p_mapped = [map_token(t) for t in g2p_tokens]
        train_tokens = phonemize_french(text)
        assert g2p_mapped == train_tokens, (
            f"Mismatch:\n  g2p+PUA: {g2p_mapped}\n  train:   {train_tokens}"
        )


@requires_piper_train
class TestPTCompat:
    def test_pt_phonemize_matches(self):
        """piper_g2p PT output + PUA matches piper_train PT output."""
        from piper_train.phonemize.portuguese import phonemize_portuguese

        from piper_g2p.encode.pua import map_token
        from piper_g2p.portuguese import PortuguesePhonemizer

        text = "Olá mundo"
        p = PortuguesePhonemizer()
        g2p_tokens = p.phonemize(text)
        g2p_mapped = [map_token(t) for t in g2p_tokens]
        train_tokens = phonemize_portuguese(text)
        assert g2p_mapped == train_tokens, (
            f"Mismatch:\n  g2p+PUA: {g2p_mapped}\n  train:   {train_tokens}"
        )


@requires_piper_train
class TestSVCompat:
    def test_sv_phonemize_matches(self):
        """piper_g2p SV output + PUA matches piper_train SV output."""
        from piper_train.phonemize.swedish import phonemize_swedish

        from piper_g2p.encode.pua import map_token
        from piper_g2p.swedish import SwedishPhonemizer

        text = "Hej världen"
        p = SwedishPhonemizer()
        g2p_tokens = p.phonemize(text)
        g2p_mapped = [map_token(t) for t in g2p_tokens]
        train_tokens = phonemize_swedish(text)
        assert g2p_mapped == train_tokens, (
            f"Mismatch:\n  g2p+PUA: {g2p_mapped}\n  train:   {train_tokens}"
        )


@requires_ja
@requires_piper_train
class TestJAProsodyCompat:
    def test_ja_prosody_a1_a2_a3_matches(self):
        """piper_g2p JA prosody (a1/a2/a3) matches piper_train for same input.

        piper_train includes BOS (^) at the start while piper_g2p does not,
        so we strip the leading BOS entry from piper_train before comparing.
        """
        from piper_train.phonemize.japanese import phonemize_japanese_with_prosody

        from piper_g2p.japanese import JapanesePhonemizer

        text = "こんにちは"
        p = JapanesePhonemizer()
        _, g2p_prosody = p.phonemize_with_prosody(text)
        train_tokens, train_prosody = phonemize_japanese_with_prosody(text)

        # Strip the leading BOS (^) entry that piper_train adds
        if train_tokens and train_tokens[0] == "^":
            train_prosody = train_prosody[1:]

        assert len(g2p_prosody) == len(train_prosody), (
            f"Length mismatch: g2p={len(g2p_prosody)}, train={len(train_prosody)}"
        )
        for i, (g, t) in enumerate(zip(g2p_prosody, train_prosody)):
            if g is None and t is None:
                continue
            assert g is not None and t is not None, (
                f"Position {i}: one is None (g2p={g}, train={t})"
            )
            assert (g.a1, g.a2, g.a3) == (t.a1, t.a2, t.a3), (
                f"Position {i}: g2p=({g.a1},{g.a2},{g.a3}) "
                f"!= train=({t.a1},{t.a2},{t.a3})"
            )
