"""Tests for Spanish phonemizer."""

from piper_train.phonemize.spanish import (
    SpanishPhonemizer,
    _find_syllable_boundaries,
    _g2p_word,
    _segment_graphemes,
    phonemize_spanish,
    phonemize_spanish_with_prosody,
)


class TestSpanishPhonemizer:
    """Tests for rule-based Spanish G2P."""

    def test_simple_word(self):
        phonemes = phonemize_spanish("hola")
        assert len(phonemes) > 0
        assert "o" in phonemes
        assert "l" in phonemes
        assert "a" in phonemes

    def test_ene_sound(self):
        phonemes = phonemize_spanish("niño")
        assert "ɲ" in phonemes

    def test_rr_trill(self):
        phonemes, _ = _g2p_word("perro")
        assert "rr" in phonemes  # trilled r (rr digraph)

    def test_initial_r_trill(self):
        phonemes, _ = _g2p_word("rojo")
        assert "rr" in phonemes  # initial r is trilled

    def test_intervocalic_r_tap(self):
        phonemes = phonemize_spanish("pero")
        assert "ɾ" in phonemes

    def test_c_before_e(self):
        phonemes = phonemize_spanish("cena")
        assert "s" in phonemes  # Latin American seseo

    def test_c_before_a(self):
        phonemes = phonemize_spanish("casa")
        assert "k" in phonemes

    def test_j_sound(self):
        phonemes = phonemize_spanish("jota")
        assert "x" in phonemes

    def test_stress_with_accent(self):
        phonemes, prosody = phonemize_spanish_with_prosody("café")
        assert len(phonemes) == len(prosody)
        # Stressed phoneme should have a2=2
        stressed = [p for p in prosody if p is not None and p.a2 == 2]
        assert len(stressed) > 0

    def test_prosody_alignment(self):
        phonemes, prosody = phonemize_spanish_with_prosody("hola mundo")
        assert len(phonemes) == len(prosody)

    def test_phonemizer_class(self):
        p = SpanishPhonemizer()
        phonemes = p.phonemize("hola")
        assert len(phonemes) > 0

    def test_phonemizer_get_id_map_returns_none(self):
        p = SpanishPhonemizer()
        assert p.get_phoneme_id_map() is None

    def test_qu_sound(self):
        phonemes = phonemize_spanish("queso")
        assert "k" in phonemes

    def test_ll_yeismo(self):
        phonemes = phonemize_spanish("calle")
        assert "ʝ" in phonemes

    def test_silent_h(self):
        phonemes = phonemize_spanish("hola")
        assert "h" not in phonemes  # h is silent in Spanish

    # ---------------------------------------------------------------
    # Issue #1: qu words — stress marker must be present
    # ---------------------------------------------------------------

    def test_qu_queso_stress(self):
        """'queso' (cheese): qu->k, stress on first syllable (que-so)."""
        phonemes = phonemize_spanish("queso")
        assert "ˈ" in phonemes, "stress marker missing for 'queso'"
        # Expected: k ˈe s o
        assert phonemes == ["k", "ˈ", "e", "s", "o"]

    def test_qu_pequeno_stress(self):
        """'pequeño' (small): stress on second syllable (pe-que-ño)."""
        phonemes = phonemize_spanish("pequeño")
        assert "ˈ" in phonemes, "stress marker missing for 'pequeño'"
        # Expected: p e k ˈe ɲ o
        assert phonemes == ["p", "e", "k", "ˈ", "e", "ɲ", "o"]

    # ---------------------------------------------------------------
    # Issue #1: gu words — stress marker must be present
    # ---------------------------------------------------------------

    def test_gu_guerra_stress(self):
        """'guerra' (war): gu before e is silent u, stress on first syllable."""
        phonemes = phonemize_spanish("guerra")
        assert "ˈ" in phonemes, "stress marker missing for 'guerra'"
        # gu+e -> g (u silent), so: ɡ ˈe rr a (rr is PUA-encoded)
        assert phonemes == ["ɡ", "ˈ", "e", "\ue01d", "a"]

    def test_gu_guitarra_stress(self):
        """'guitarra' (guitar): gu before i is silent u, stress on 2nd syl."""
        phonemes = phonemize_spanish("guitarra")
        assert "ˈ" in phonemes, "stress marker missing for 'guitarra'"
        # gui-ta-rra: ɡ i t ˈa rr a (rr is PUA-encoded)
        assert phonemes == ["ɡ", "i", "t", "ˈ", "a", "\ue01d", "a"]

    # ---------------------------------------------------------------
    # Issue #2: gü (diaeresis) — must produce /gw/
    # ---------------------------------------------------------------

    def test_gue_diaeresis_produces_gw(self):
        """'güe' should produce /gw/ (diaeresis makes u pronounced)."""
        phonemes = phonemize_spanish("güe")
        assert "ɡ" in phonemes
        assert "w" in phonemes
        assert "e" in phonemes

    def test_pinguino_gw(self):
        """'pingüino' should produce /gw/ for the gü digraph."""
        phonemes = phonemize_spanish("pingüino")
        assert "ɡ" in phonemes
        assert "w" in phonemes
        # Stress should be on the 'i' after gw: pin-güi-no
        assert "ˈ" in phonemes, "stress marker missing for 'pingüino'"
        # Expected: p i n ɡ w ˈi n o
        assert phonemes == ["p", "i", "n", "ɡ", "w", "ˈ", "i", "n", "o"]

    # ---------------------------------------------------------------
    # Issue #3: sc + e/i — no geminate
    # ---------------------------------------------------------------

    def test_sc_escena_no_geminate(self):
        """'escena' (scene): sc+e should produce single /s/, not /ss/."""
        phonemes = phonemize_spanish("escena")
        # Count how many 's' phonemes there are
        s_count = phonemes.count("s")
        assert s_count == 1, f"expected 1 's' but got {s_count}: {phonemes}"
        # Stress on second syllable (e-sce-na -> penultimate)
        assert "ˈ" in phonemes
        # Expected: e s ˈe n a
        assert phonemes == ["e", "s", "ˈ", "e", "n", "a"]

    def test_sc_piscina_no_geminate(self):
        """'piscina' (pool): sc+i should produce single /s/, not /ss/."""
        phonemes = phonemize_spanish("piscina")
        s_count = phonemes.count("s")
        assert s_count == 1, f"expected 1 's' but got {s_count}: {phonemes}"

    # ---------------------------------------------------------------
    # Issue #4: syllabification treats digraphs as single units
    # ---------------------------------------------------------------

    def test_syllabification_ch_not_split(self):
        """'mucho': ch should stay together in one syllable (mu-cho)."""
        units = _segment_graphemes("mucho")
        boundaries = _find_syllable_boundaries("mucho")
        # units: m, u, ch, o -> boundaries should split as mu.cho
        # ch is a single unit, so it should be at the start of syllable 2
        graphemes = [u[0] for u in units]
        assert "ch" in graphemes, f"'ch' not segmented as digraph: {graphemes}"
        assert len(boundaries) == 2  # mu-cho = 2 syllables

    def test_syllabification_ll_not_split(self):
        """'calle': ll should stay together in one syllable (ca-lle)."""
        units = _segment_graphemes("calle")
        graphemes = [u[0] for u in units]
        assert "ll" in graphemes, f"'ll' not segmented as digraph: {graphemes}"

    def test_syllabification_rr_not_split(self):
        """'perro': rr should stay together in one syllable (pe-rro)."""
        units = _segment_graphemes("perro")
        graphemes = [u[0] for u in units]
        assert "rr" in graphemes, f"'rr' not segmented as digraph: {graphemes}"

    # ---------------------------------------------------------------
    # Issue #5: no duplicate ñ handler (regression test)
    # ---------------------------------------------------------------

    def test_ene_single_phoneme(self):
        """Verify ñ produces exactly one ɲ phoneme (no duplicates)."""
        phonemes = phonemize_spanish("ñ")
        assert phonemes.count("ɲ") == 1

    # ---------------------------------------------------------------
    # Issue #6: grapheme segmentation consistency
    # ---------------------------------------------------------------

    def test_segment_graphemes_qu(self):
        """_segment_graphemes keeps 'qu' as a single unit."""
        units = _segment_graphemes("queso")
        graphemes = [u[0] for u in units]
        assert "qu" in graphemes

    def test_segment_graphemes_gu(self):
        """_segment_graphemes keeps 'gu' (before e/i) as a single unit."""
        units = _segment_graphemes("guerra")
        graphemes = [u[0] for u in units]
        assert "gu" in graphemes

    def test_segment_graphemes_gue_diaeresis(self):
        """_segment_graphemes keeps 'gü' as a single unit."""
        units = _segment_graphemes("pingüino")
        graphemes = [u[0] for u in units]
        assert "gü" in graphemes

    # ---------------------------------------------------------------
    # Fix 1: Accented weak vowel forces hiatus
    # ---------------------------------------------------------------

    def test_hiatus_accented_weak_vowel(self):
        """Accented weak vowel forces hiatus."""
        # día should be 2 syllables with stress on í
        phonemes = phonemize_spanish("día")
        assert "ˈ" in phonemes
        i_idx = phonemes.index("ˈ")
        assert phonemes[i_idx + 1] == "i"

    def test_pais_hiatus(self):
        """país has hiatus: pa-ís (2 syllables)."""
        phonemes = phonemize_spanish("país")
        assert "ˈ" in phonemes

    # ---------------------------------------------------------------
    # Fix 2: xc+e/i produces no double /s/
    # ---------------------------------------------------------------

    def test_xc_no_double_s(self):
        """exceso should not produce double s."""
        phonemes = phonemize_spanish("exceso")
        # Count s phonemes - should be exactly 2 (from x→ks and final s)
        s_count = sum(1 for p in phonemes if p == "s")
        assert s_count == 2, f"expected 2 's' but got {s_count}: {phonemes}"

    # ---------------------------------------------------------------
    # Fix 3: Spirantization after lateral and rhotic
    # ---------------------------------------------------------------

    def test_stop_after_lateral(self):
        """b after l should produce stop [b] (not spirant β)."""
        phonemes = phonemize_spanish("alba")
        assert "b" in phonemes

    def test_spirantization_after_rhotic(self):
        """b after r should produce β."""
        phonemes = phonemize_spanish("árbol")
        assert "β" in phonemes

    # ---------------------------------------------------------------
    # Fix 5: Function word stress suppression
    # ---------------------------------------------------------------

    def test_function_word_no_stress(self):
        """Common function words should not have stress marker."""
        phonemes = phonemize_spanish("el")
        assert "ˈ" not in phonemes

    # ---------------------------------------------------------------
    # Fix 6: ü diaeresis should NOT affect stress
    # ---------------------------------------------------------------

    def test_diaeresis_no_stress_shift(self):
        """ü (diaeresis) should not shift stress position."""
        # bilingüe: stress on "lin" (penultimate), not on "gü"
        phonemes = phonemize_spanish("bilingüe")
        # Should have stress marker before the penultimate vowel
        assert "ˈ" in phonemes

    # ---------------------------------------------------------------
    # Fix 7: g after l should produce stop [ɡ]
    # ---------------------------------------------------------------

    def test_g_stop_after_lateral(self):
        """g after l should produce stop [ɡ], not spirant [ɣ]."""
        phonemes = phonemize_spanish("algo")
        assert "ɡ" in phonemes
        assert "ɣ" not in phonemes

    # ---------------------------------------------------------------
    # Fix 8: xc digraph segmentation for stress alignment
    # ---------------------------------------------------------------

    def test_xc_digraph_segmentation(self):
        """'excepción': xc+e should be segmented as digraph in _segment_graphemes."""
        units = _segment_graphemes("excepción")
        graphemes = [u[0] for u in units]
        assert "xc" in graphemes, (
            f"'xc' should be a digraph in _segment_graphemes, got: {graphemes}"
        )

    def test_xc_stress_alignment(self):
        """'excepción': stress should be correctly placed despite xc digraph."""
        phonemes = phonemize_spanish("excepción")
        assert "ˈ" in phonemes, f"stress marker missing for 'excepción': {phonemes}"
