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
        assert "ã" in phonemes or any(
            p in phonemes for p in ["ã", "ẽ", "ĩ", "õ", "ũ"]
        )

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
        from piper_train.phonemize.portuguese import (
            phonemize_portuguese_with_prosody,
        )

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

    # --- t/d palatalization before unstressed final -e ---

    def test_palatalization_t_gente(self):
        """'gente' should have t -> tʃ before unstressed final -e -> i."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("gente")
        # Expected: ʒ ẽ n t ʃ i
        joined = " ".join(phonemes)
        assert "t ʃ i" in joined, f"Expected 'tʃi' in gente, got: {joined}"

    def test_palatalization_d_cidade(self):
        """'cidade' should have d -> dʒ before unstressed final -e -> i."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("cidade")
        # Expected: s i d a d ʒ i
        joined = " ".join(phonemes)
        assert "d ʒ i" in joined, f"Expected 'dʒi' in cidade, got: {joined}"

    def test_palatalization_preserves_stress(self):
        """Palatalization should not affect the stressed vowel."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, stress_idx = _convert_word("gente")
        # Stress should be on ẽ (the first vowel), not on the final i
        assert phonemes[stress_idx] == "ẽ", (
            f"Stress should be on ẽ, got {phonemes[stress_idx]}"
        )

    # --- Unstressed vowel reduction ---

    def test_unstressed_final_e_reduces_to_i(self):
        """Unstressed final -e should reduce to [i]."""
        from piper_train.phonemize.portuguese import _convert_word

        # "quase" -> k w a z i (final e -> i)
        phonemes, _ = _convert_word("quase")
        assert phonemes[-1] == "i", (
            f"Expected final 'i' in quase, got: {phonemes}"
        )

    def test_unstressed_final_o_reduces_to_u(self):
        """Unstressed final -o should reduce to [u]."""
        from piper_train.phonemize.portuguese import _convert_word

        # "gato" -> ɡ a t u (final o -> u)
        phonemes, _ = _convert_word("gato")
        assert phonemes[-1] == "u", (
            f"Expected final 'u' in gato, got: {phonemes}"
        )

    # --- Coda-l vocalization ---

    def test_coda_l_brasil(self):
        """'Brasil' should vocalize final l to [w]."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("brasil")
        # Expected: b ɾ a z i w
        assert phonemes[-1] == "w", (
            f"Expected final 'w' in brasil, got: {phonemes}"
        )
        assert "l" not in phonemes, (
            f"Should not have 'l' in brasil, got: {phonemes}"
        )

    def test_coda_l_alto(self):
        """'alto' should vocalize coda l to [w]."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("alto")
        # Expected: a w t u
        assert "w" in phonemes, (
            f"Expected 'w' in alto (coda-l), got: {phonemes}"
        )
        assert "l" not in phonemes, (
            f"Should not have 'l' in alto, got: {phonemes}"
        )

    def test_onset_l_preserved(self):
        """Onset l (before vowel) should remain as [l]."""
        from piper_train.phonemize.portuguese import _convert_word

        # "lua" -> l u a (onset l stays)
        phonemes, _ = _convert_word("lua")
        assert "l" in phonemes, (
            f"Expected onset 'l' in lua, got: {phonemes}"
        )

    # --- qu words ---

    def test_qu_before_a_produces_kw(self):
        """'quase' should have /kw/ (qu before a)."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("quase")
        # Expected: k w a z i
        joined = " ".join(phonemes)
        assert "k w" in joined, (
            f"Expected 'kw' in quase, got: {joined}"
        )

    def test_qu_before_a_quatro(self):
        """'quatro' should have /kw/ (qu before a)."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("quatro")
        # Expected: k w a t ɾ u
        joined = " ".join(phonemes)
        assert "k w" in joined, (
            f"Expected 'kw' in quatro, got: {joined}"
        )

    def test_qu_before_e_silent_u(self):
        """'que' should have /k/ without w (qu before e, u is silent)."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("que")
        # Expected: k i (or k e reduced to i)
        assert "w" not in phonemes, (
            f"Should not have 'w' in que (silent u), got: {phonemes}"
        )
        assert phonemes[0] == "k", (
            f"Expected 'k' at start of que, got: {phonemes}"
        )

    # --- Nasal before nh should NOT nasalize ---

    def test_no_nasalization_before_nh(self):
        """Vowel before 'nh' digraph should NOT be nasalized."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("banho")
        # Expected: b a ɲ u (not b ã ɲ u)
        assert "ã" not in phonemes, (
            f"Should not have nasal 'ã' before nh in banho, got: {phonemes}"
        )
        assert "a" in phonemes, (
            f"Expected oral 'a' in banho, got: {phonemes}"
        )

    def test_no_nasalization_before_nh_vinho(self):
        """'vinho' should not nasalize i before nh."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("vinho")
        assert "ĩ" not in phonemes, (
            f"Should not have nasal 'ĩ' before nh in vinho, got: {phonemes}"
        )

    # --- ens ending paroxytone ---

    def test_ens_ending_paroxytone_homens(self):
        """'homens' should be paroxytone (stress on penultimate)."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, stress_idx = _convert_word("homens")
        # Stress should be on 'o' (first vowel), not on 'e'
        assert phonemes[stress_idx] == "o", (
            f"Expected stress on 'o' in homens, got stress on "
            f"'{phonemes[stress_idx]}' at idx {stress_idx}"
        )

    def test_ens_ending_paroxytone_nuvens(self):
        """'nuvens' should be paroxytone (stress on penultimate)."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, stress_idx = _convert_word("nuvens")
        # Stress should be on 'u' (first vowel), not on 'e'
        assert phonemes[stress_idx] == "u", (
            f"Expected stress on 'u' in nuvens, got stress on "
            f"'{phonemes[stress_idx]}' at idx {stress_idx}"
        )

    # --- Nasal consonant duplication ---

    def test_no_duplicate_nasal_bom(self):
        """'bom' should not duplicate the nasal: b õ, not b õ m."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("bom")
        assert phonemes == ["b", "õ"], (
            f"Expected ['b', 'õ'] for bom, got: {phonemes}"
        )

    def test_no_duplicate_nasal_jardim(self):
        """'jardim' should not have trailing m after nasal vowel."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("jardim")
        # Should end with ĩ, not ĩ m
        assert phonemes[-1] != "m", (
            f"Should not end with 'm' after nasal vowel in jardim, "
            f"got: {phonemes}"
        )

    # --- Stress tracking with digraphs ---

    def test_stress_tracking_qu_word(self):
        """Stress should be correctly placed in 'quase' despite qu digraph."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, stress_idx = _convert_word("quase")
        # quase is paroxytone, stress on 'a'
        assert phonemes[stress_idx] == "a", (
            f"Expected stress on 'a' in quase, got stress on "
            f"'{phonemes[stress_idx]}' at idx {stress_idx}, "
            f"phonemes={phonemes}"
        )

    def test_stress_tracking_ou_word(self):
        """Stress tracking should work with 'ou' diphthong."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, stress_idx = _convert_word("ouvir")
        # ouvir ends in consonant -> oxytone, stress on last vowel (i)
        assert phonemes[stress_idx] == "i" or phonemes[stress_idx] == "ĩ", (
            f"Expected stress on 'i' in ouvir, got stress on "
            f"'{phonemes[stress_idx]}' at idx {stress_idx}"
        )
