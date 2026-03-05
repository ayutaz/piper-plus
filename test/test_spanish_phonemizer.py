"""Tests for Spanish phonemizer."""

import pytest


class TestSpanishPhonemizer:
    """Tests for rule-based Spanish G2P."""

    def test_simple_word(self):
        from piper_train.phonemize.spanish import phonemize_spanish

        phonemes = phonemize_spanish("hola")
        assert len(phonemes) > 0
        assert "o" in phonemes
        assert "l" in phonemes
        assert "a" in phonemes

    def test_ene_sound(self):
        from piper_train.phonemize.spanish import phonemize_spanish

        phonemes = phonemize_spanish("niño")
        assert "ɲ" in phonemes

    def test_rr_trill(self):
        from piper_train.phonemize.spanish import phonemize_spanish

        phonemes = phonemize_spanish("perro")
        assert "rr" in phonemes  # trilled r (rr digraph)

    def test_initial_r_trill(self):
        from piper_train.phonemize.spanish import phonemize_spanish

        phonemes = phonemize_spanish("rojo")
        assert "rr" in phonemes  # initial r is trilled

    def test_intervocalic_r_tap(self):
        from piper_train.phonemize.spanish import phonemize_spanish

        phonemes = phonemize_spanish("pero")
        assert "ɾ" in phonemes

    def test_c_before_e(self):
        from piper_train.phonemize.spanish import phonemize_spanish

        phonemes = phonemize_spanish("cena")
        assert "s" in phonemes  # Latin American seseo

    def test_c_before_a(self):
        from piper_train.phonemize.spanish import phonemize_spanish

        phonemes = phonemize_spanish("casa")
        assert "k" in phonemes

    def test_j_sound(self):
        from piper_train.phonemize.spanish import phonemize_spanish

        phonemes = phonemize_spanish("jota")
        assert "x" in phonemes

    def test_stress_with_accent(self):
        from piper_train.phonemize.spanish import phonemize_spanish_with_prosody

        phonemes, prosody = phonemize_spanish_with_prosody("café")
        assert len(phonemes) == len(prosody)
        # Stressed phoneme should have a2=2
        stressed = [p for p in prosody if p is not None and p.a2 == 2]
        assert len(stressed) > 0

    def test_prosody_alignment(self):
        from piper_train.phonemize.spanish import phonemize_spanish_with_prosody

        phonemes, prosody = phonemize_spanish_with_prosody("hola mundo")
        assert len(phonemes) == len(prosody)

    def test_phonemizer_class(self):
        from piper_train.phonemize.spanish import SpanishPhonemizer

        p = SpanishPhonemizer()
        phonemes = p.phonemize("hola")
        assert len(phonemes) > 0

    def test_phonemizer_get_id_map_returns_none(self):
        from piper_train.phonemize.spanish import SpanishPhonemizer

        p = SpanishPhonemizer()
        assert p.get_phoneme_id_map() is None

    def test_qu_sound(self):
        from piper_train.phonemize.spanish import phonemize_spanish

        phonemes = phonemize_spanish("queso")
        assert "k" in phonemes

    def test_ll_yeismo(self):
        from piper_train.phonemize.spanish import phonemize_spanish

        phonemes = phonemize_spanish("calle")
        assert "ʝ" in phonemes

    def test_silent_h(self):
        from piper_train.phonemize.spanish import phonemize_spanish

        phonemes = phonemize_spanish("hola")
        assert "h" not in phonemes  # h is silent in Spanish
