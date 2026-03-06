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
        # Expected: ʒ ẽ tʃ i  (tʃ is a single affricate token)
        joined = " ".join(phonemes)
        assert "tʃ i" in joined, f"Expected 'tʃ i' in gente, got: {joined}"

    def test_palatalization_d_cidade(self):
        """'cidade' should have d -> dʒ before unstressed final -e -> i."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("cidade")
        # Expected: s i d a dʒ i  (dʒ is a single affricate token)
        joined = " ".join(phonemes)
        assert "dʒ i" in joined, f"Expected 'dʒ i' in cidade, got: {joined}"

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

    # --- Coda-r → ʁ (uvular fricative) ---

    def test_coda_r_uvular_word_final(self):
        """Word-final r (coda) should be ʁ (uvular fricative)."""
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("mar")
        assert "ʁ" in phonemes, f"Expected ʁ in 'mar', got: {phonemes}"

    def test_coda_r_uvular_before_consonant(self):
        """Coda r before consonant should be ʁ."""
        from piper_train.phonemize.portuguese import phonemize_portuguese

        # 'carta': c-a-r-t-a — r before consonant t
        phonemes = phonemize_portuguese("carta")
        assert "ʁ" in phonemes, f"Expected ʁ in 'carta', got: {phonemes}"

    def test_intervocalic_r_tap(self):
        """Intervocalic single r should be ɾ (tap)."""
        from piper_train.phonemize.portuguese import phonemize_portuguese

        # 'para': p-a-r-a — r between two vowels
        phonemes = phonemize_portuguese("para")
        assert "ɾ" in phonemes, f"Expected ɾ in 'para', got: {phonemes}"
        assert "ʁ" not in phonemes, (
            f"Should not have ʁ in 'para' (intervocalic r), got: {phonemes}"
        )

    def test_intervocalic_r_caro(self):
        """'caro' should have ɾ (tap) for the intervocalic r."""
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("caro")
        assert "ɾ" in phonemes, f"Expected ɾ in 'caro', got: {phonemes}"

    # --- ʎ and ɲ digraphs ---

    def test_lh_produces_palatal_lateral(self):
        """lh digraph should produce ʎ (palatal lateral approximant)."""
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("trabalho")
        assert "ʎ" in phonemes, f"Expected ʎ in 'trabalho', got: {phonemes}"

    def test_nh_produces_palatal_nasal(self):
        """nh digraph should produce ɲ (palatal nasal)."""
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("banho")
        assert "ɲ" in phonemes, f"Expected ɲ in 'banho', got: {phonemes}"

    # --- ʃ and ʒ ---

    def test_ch_produces_postalveolar(self):
        """ch digraph should produce ʃ (voiceless postalveolar fricative)."""
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("chave")
        assert "ʃ" in phonemes, f"Expected ʃ in 'chave', got: {phonemes}"

    def test_j_produces_voiced_postalveolar(self):
        """j should produce ʒ (voiced postalveolar fricative)."""
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("jogo")
        assert "ʒ" in phonemes, f"Expected ʒ in 'jogo', got: {phonemes}"

    def test_g_before_e_produces_voiced_postalveolar(self):
        """g before e/i should produce ʒ."""
        from piper_train.phonemize.portuguese import phonemize_portuguese

        phonemes = phonemize_portuguese("gente")
        assert "ʒ" in phonemes, f"Expected ʒ in 'gente', got: {phonemes}"

    # --- tʃ / dʒ single-token palatalization ---

    def test_ti_palatalization_single_token(self):
        """Palatalized ti should use single tʃ token (not t + ʃ separately)."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("tipo")
        assert "tʃ" in phonemes, f"Expected 'tʃ' token in 'tipo', got: {phonemes}"
        # The separate t and ʃ should NOT appear as consecutive tokens
        for idx in range(len(phonemes) - 1):
            assert not (phonemes[idx] == "t" and phonemes[idx + 1] == "ʃ"), (
                f"Should not have separate t + ʃ tokens in 'tipo', got: {phonemes}"
            )

    def test_di_palatalization_single_token(self):
        """Palatalized di should use single dʒ token (not d + ʒ separately)."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("dia")
        assert "dʒ" in phonemes, f"Expected 'dʒ' token in 'dia', got: {phonemes}"
        for idx in range(len(phonemes) - 1):
            assert not (phonemes[idx] == "d" and phonemes[idx + 1] == "ʒ"), (
                f"Should not have separate d + ʒ tokens in 'dia', got: {phonemes}"
            )

    # --- Nasal coda suppression in word-medial position ---

    def test_nasal_coda_suppressed_banco(self):
        """'banco' nasal coda n should be suppressed (absorbed into nasal vowel)."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("banco")
        joined = " ".join(phonemes)
        # Should produce ã (nasal a) but NOT a following n
        assert "ã" in phonemes, f"Expected nasal ã in 'banco', got: {phonemes}"
        # ã should not be followed by n in the phoneme sequence
        for idx in range(len(phonemes) - 1):
            assert not (phonemes[idx] == "ã" and phonemes[idx + 1] == "n"), (
                f"Nasal coda n should be suppressed in 'banco', got: {joined}"
            )

    def test_nasal_coda_suppressed_campo(self):
        """'campo' nasal coda m should be suppressed (absorbed into nasal vowel)."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("campo")
        joined = " ".join(phonemes)
        # ã should not be followed by m
        for idx in range(len(phonemes) - 1):
            assert not (phonemes[idx] == "ã" and phonemes[idx + 1] == "m"), (
                f"Nasal coda m should be suppressed in 'campo', got: {joined}"
            )

    # --- sc digraph before e/i ---

    def test_sc_digraph_piscina(self):
        """sc before i: 'piscina' should produce single /s/, not /ss/."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("piscina")
        # Count 's' phonemes; should have exactly 1 for the 'sc' digraph
        s_count = phonemes.count("s")
        assert s_count == 1, (
            f"Expected exactly 1 /s/ for 'sc' in 'piscina', got {s_count}: {phonemes}"
        )

    def test_sc_digraph_crescer(self):
        """sc before e: 'crescer' should produce single /s/, not /ss/."""
        from piper_train.phonemize.portuguese import _convert_word

        phonemes, _ = _convert_word("crescer")
        # The 'sc' before 'e' should produce one /s/
        # (There's also an initial 's' from 'cre' → k,ɾ,ɛ then 'sc' → s)
        # Actually 'crescer': c=k, r=ɾ, e, sc=s, e, r=ʁ
        assert "s" in phonemes, f"Expected /s/ in 'crescer', got: {phonemes}"

    # --- Coda-l vocalization before affricates ---

    def test_coda_l_before_affricate(self):
        """l before tʃ affricate should vocalize to [w]."""
        from piper_train.phonemize.portuguese import _convert_word, _apply_coda_l_vocalization

        # Simulate: ['w', 'tʃ', 'i'] — l before tʃ should become w
        result = _apply_coda_l_vocalization(["a", "l", "tʃ", "i"])
        assert result[1] == "w", (
            f"Expected l → w before affricate tʃ, got: {result}"
        )
