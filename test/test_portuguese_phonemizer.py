"""Tests for Brazilian Portuguese phonemizer."""

import pytest


class TestPortuguesePhonemizer:
    """Tests for rule-based Brazilian Portuguese G2P."""

    def test_simple_word(self):
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("casa")
        assert len(phonemes) > 0
        assert "k" in phonemes
        assert "a" in phonemes

    def test_nasal_vowel_tilde(self):
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("mão")
        assert "ã" in phonemes

    def test_nasal_vowel_before_n(self):
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("banco")
        assert "ã" in phonemes or any(p in phonemes for p in ["ã", "ẽ", "ĩ", "õ", "ũ"])

    def test_nh_digraph(self):
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("banho")
        assert "ɲ" in phonemes

    def test_lh_digraph(self):
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("filho")
        assert "ʎ" in phonemes

    def test_rr_uvular(self):
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("carro")
        assert "ʁ" in phonemes

    def test_initial_r_uvular(self):
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("rio")
        assert "ʁ" in phonemes

    def test_intervocalic_r_tap(self):
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("caro")
        assert "ɾ" in phonemes

    def test_prosody_alignment(self):
        from piper_train.phonemize.portuguese import phonemize_portuguese_with_prosody

        phonemes, prosody = phonemize_portuguese_with_prosody("olá mundo")
        assert len(phonemes) == len(prosody)

    def test_phonemizer_class(self):
        from piper_train.phonemize.portuguese import PortuguesePhonemizer

        p = PortuguesePhonemizer()
        phonemes = p.phonemize("olá")
        assert len(phonemes) > 0

    def test_phonemizer_get_id_map_returns_none(self):
        from piper_train.phonemize.portuguese import PortuguesePhonemizer

        p = PortuguesePhonemizer()
        assert p.get_phoneme_id_map() is None

    def test_cedilla(self):
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("caça")
        assert "s" in phonemes
