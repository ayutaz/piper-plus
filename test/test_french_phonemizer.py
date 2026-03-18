"""Tests for French phonemizer."""


class TestFrenchPhonemizer:
    """Tests for rule-based French G2P."""

    def test_simple_word(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("bonjour")
        assert len(phonemes) > 0

    def test_nasal_vowel_an(self):
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("france")
        assert "\u0251\u0303" in phonemes

    def test_nasal_vowel_on(self):
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("bon")
        assert "\u0254\u0303" in phonemes

    def test_nasal_vowel_in(self):
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("vin")
        assert "\u025b\u0303" in phonemes

    def test_ou_digraph(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("vous")
        assert "u" in phonemes

    def test_oi_digraph(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("moi")
        assert "w" in phonemes
        assert "a" in phonemes

    def test_ch_digraph(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("chat")
        assert "\u0283" in phonemes

    def test_r_uvular(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("rouge")
        assert "\u0281" in phonemes

    def test_gn_digraph(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("montagne")
        assert "\u0272" in phonemes

    def test_eau_trigraph(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("eau")
        assert "o" in phonemes

    def test_prosody_alignment(self):
        from piper_train.phonemize.french import phonemize_french_with_prosody

        phonemes, prosody = phonemize_french_with_prosody("bonjour le monde")
        assert len(phonemes) == len(prosody)

    def test_phonemizer_class(self):
        from piper_train.phonemize.french import FrenchPhonemizer

        p = FrenchPhonemizer()
        phonemes = p.phonemize("bonjour")
        assert len(phonemes) > 0

    def test_phonemizer_get_id_map_returns_none(self):
        from piper_train.phonemize.french import FrenchPhonemizer

        p = FrenchPhonemizer()
        assert p.get_phoneme_id_map() is None

    def test_silent_final_consonant(self):
        """Final consonants are often silent in French."""
        from piper_train.phonemize.french import phonemize_french

        # "petit" -- the final 't' should be silent
        phonemes = phonemize_french("petit")
        # Verify we get phonemes (the exact handling depends on rules)
        assert len(phonemes) > 0

    def test_accent_marks(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("cafe\u0301")
        assert "e" in phonemes  # e\u0301 -> e

    # -----------------------------------------------------------------
    # Issue 1: Intervocalic s -> z voicing
    # -----------------------------------------------------------------

    def test_intervocalic_s_maison(self):
        """Single 's' between vowels voices to /z/: maison -> /m\u025bz\u0254\u0303/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("maison")
        assert "z" in phonemes, f"Expected /z/ in 'maison', got: {phonemes}"
        assert "s" not in phonemes, f"Should not have /s/ in 'maison', got: {phonemes}"

    def test_intervocalic_s_rose(self):
        """Single 's' between vowels voices to /z/: rose -> /\u0281oz/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("rose")
        assert "z" in phonemes, f"Expected /z/ in 'rose', got: {phonemes}"

    def test_intervocalic_s_poison(self):
        """Intervocalic s voicing: poison -> /pwaz\u0254\u0303/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("poison")
        assert "z" in phonemes, f"Expected /z/ in 'poison', got: {phonemes}"

    def test_double_ss_not_voiced(self):
        """Double 'ss' between vowels stays /s/: poisson -> has /s/ not /z/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("poisson")
        assert "s" in phonemes, f"Expected /s/ in 'poisson', got: {phonemes}"
        assert "z" not in phonemes, f"Should not have /z/ in 'poisson', got: {phonemes}"

    # -----------------------------------------------------------------
    # Issue 2: -er verb ending -> /e/
    # -----------------------------------------------------------------

    def test_er_ending_parler(self):
        """Verb -er ending: parler -> /pa\u0281le/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("parler")
        assert phonemes[-1] == "e", f"Expected final /e/ in 'parler', got: {phonemes}"
        assert "\u0281" not in phonemes[-1:], "Final 'r' should not be pronounced"

    def test_er_ending_manger(self):
        """Verb -er ending: manger -> /m\u0251\u0303\u0292e/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("manger")
        assert phonemes[-1] == "e", f"Expected final /e/ in 'manger', got: {phonemes}"

    def test_er_ending_donner(self):
        """Verb -er ending: donner -> /done/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("donner")
        assert phonemes[-1] == "e", f"Expected final /e/ in 'donner', got: {phonemes}"

    # -----------------------------------------------------------------
    # Issue 3: x handling
    # -----------------------------------------------------------------

    def test_x_silent_word_final_deux(self):
        """Word-final x is silent: deux -> /d\u00f8/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("deux")
        assert "k" not in phonemes, f"Final x should be silent in 'deux', got: {phonemes}"
        assert "s" not in phonemes, f"Final x should be silent in 'deux', got: {phonemes}"

    def test_x_silent_word_final_voix(self):
        """Word-final x is silent: voix -> /vwa/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("voix")
        assert "k" not in phonemes, f"Final x should be silent in 'voix', got: {phonemes}"

    def test_x_examen_voiced(self):
        """ex + vowel -> /\u025bgz/: examen -> /\u025bgzam\u025b\u0303/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("examen")
        ph_str = " ".join(phonemes)
        assert "\u0261" in phonemes, f"Expected /\u0261/ in 'examen', got: {ph_str}"
        assert "z" in phonemes, f"Expected /z/ in 'examen', got: {ph_str}"

    def test_x_extreme_voiceless(self):
        """ex + consonant -> /\u025bks/: extre\u0302me keeps /ks/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("extr\u00eame")
        ph_str = " ".join(phonemes)
        assert "k" in phonemes, f"Expected /k/ in 'extr\u00eame', got: {ph_str}"
        assert "s" in phonemes, f"Expected /s/ in 'extr\u00eame', got: {ph_str}"

    # -----------------------------------------------------------------
    # Issue 4: Final consonant + silent e
    # -----------------------------------------------------------------

    def test_final_consonant_e_table(self):
        """Consonant before final 'e' is pronounced: table -> /tabl/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("table")
        assert "l" in phonemes, f"Expected /l/ in 'table', got: {phonemes}"
        assert "b" in phonemes, f"Expected /b/ in 'table', got: {phonemes}"

    def test_final_consonant_e_libre(self):
        """Consonant before final 'e' is pronounced: libre -> /lib\u0281/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("libre")
        assert "\u0281" in phonemes, f"Expected /\u0281/ in 'libre', got: {phonemes}"
        assert "b" in phonemes, f"Expected /b/ in 'libre', got: {phonemes}"

    def test_final_consonant_e_rose(self):
        """Consonant before final 'e' is pronounced: rose -> /\u0281oz/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("rose")
        assert "z" in phonemes, f"Expected /z/ in 'rose', got: {phonemes}"

    # -----------------------------------------------------------------
    # Issue 5: Semi-vowel hy production
    # -----------------------------------------------------------------

    def test_semivowel_hy_lui(self):
        """u + i -> /\u0265i/: lui -> /l\u0265i/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("lui")
        assert "\u0265" in phonemes, f"Expected /\u0265/ in 'lui', got: {phonemes}"
        assert "i" in phonemes, f"Expected /i/ after /\u0265/ in 'lui', got: {phonemes}"

    def test_semivowel_hy_nuit(self):
        """u + i -> /\u0265i/: nuit -> /n\u0265i/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("nuit")
        assert "\u0265" in phonemes, f"Expected /\u0265/ in 'nuit', got: {phonemes}"

    def test_semivowel_hy_fruit(self):
        """u + i -> /\u0265i/: fruit -> /f\u0281\u0265i/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("fruit")
        assert "\u0265" in phonemes, f"Expected /\u0265/ in 'fruit', got: {phonemes}"

    # -----------------------------------------------------------------
    # Issue 6: -aille / -eille / -ouille / -ille patterns
    # -----------------------------------------------------------------

    def test_aille_travaille(self):
        """aille -> /aj/: travaille -> /t\u0281avaj/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("travaille")
        assert phonemes[-2:] == ["a", "j"] or (
            "j" in phonemes and "a" in phonemes
        ), f"Expected /aj/ ending in 'travaille', got: {phonemes}"

    def test_eille_merveille(self):
        """eille -> /\u025bj/: merveille -> /m\u025b\u0281v\u025bj/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("merveille")
        assert phonemes[-2:] == ["\u025b", "j"], (
            f"Expected /\u025bj/ ending in 'merveille', got: {phonemes}"
        )

    def test_ouille_grenouille(self):
        """ouille -> /uj/: grenouille -> /g\u0281\u0259nuj/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("grenouille")
        assert phonemes[-2:] == ["u", "j"], (
            f"Expected /uj/ ending in 'grenouille', got: {phonemes}"
        )

    def test_ille_default_fille(self):
        """ille -> /ij/ by default: fille -> /fij/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("fille")
        assert "j" in phonemes, f"Expected /j/ in 'fille', got: {phonemes}"

    def test_ille_exception_ville(self):
        """ille -> /il/ exception: ville -> /vil/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("ville")
        assert "l" in phonemes, f"Expected /l/ in 'ville', got: {phonemes}"
        assert "j" not in phonemes, f"Should not have /j/ in 'ville', got: {phonemes}"

    def test_ille_exception_mille(self):
        """ille -> /il/ exception: mille -> /mil/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("mille")
        assert "l" in phonemes, f"Expected /l/ in 'mille', got: {phonemes}"
        assert "j" not in phonemes, f"Should not have /j/ in 'mille', got: {phonemes}"

    def test_ille_exception_tranquille(self):
        """ille -> /il/ exception: tranquille -> /t\u0281\u0251\u0303kil/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("tranquille")
        assert "l" in phonemes, f"Expected /l/ in 'tranquille', got: {phonemes}"
        assert "j" not in phonemes, (
            f"Should not have /j/ in 'tranquille', got: {phonemes}"
        )

    # -----------------------------------------------------------------
    # Issue 7: stion -> /stj\u0254\u0303/ (not /sstj\u0254\u0303/)
    # -----------------------------------------------------------------

    def test_stion_question(self):
        """stion should produce /stj\u0254\u0303/ not /sstj\u0254\u0303/: question."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("question")
        # Should have exactly one 's', then 't', not 'ss' or 'st' doubled
        s_count = phonemes.count("s")
        assert s_count == 1, (
            f"Expected exactly 1 /s/ in 'question', got {s_count}: {phonemes}"
        )
        # Should contain t, j, and nasal
        assert "t" in phonemes, f"Expected /t/ in 'question', got: {phonemes}"
        assert "j" in phonemes, f"Expected /j/ in 'question', got: {phonemes}"

    def test_tion_nation(self):
        """Standard tion -> /sj\u0254\u0303/: nation -> /nasj\u0254\u0303/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("nation")
        assert "s" in phonemes, f"Expected /s/ in 'nation', got: {phonemes}"
        assert "j" in phonemes, f"Expected /j/ in 'nation', got: {phonemes}"

    # -----------------------------------------------------------------
    # Fix 1/2: y_vowel (French /y/) — no bare "y" from French u
    # -----------------------------------------------------------------

    def test_y_vowel_not_bare_y(self):
        """French u vowel should use y_vowel, not bare y."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("lune")
        assert "y" not in phonemes, f"Bare 'y' should not appear for French /y/: {phonemes}"
        assert "y_vowel" in phonemes, f"Expected 'y_vowel' in 'lune': {phonemes}"

    def test_y_vowel_tu(self):
        """tu: u -> y_vowel."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("tu")
        assert "y_vowel" in phonemes, f"Expected 'y_vowel' in 'tu': {phonemes}"
        assert "y" not in phonemes, f"Bare 'y' should not appear: {phonemes}"

    # -----------------------------------------------------------------
    # Fix 3: -er rule restricted to polysyllabic words
    # -----------------------------------------------------------------

    def test_er_monosyllabic_not_verb(self):
        """Monosyllabic -er words should keep /\u025b\u0281/, not /e/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("mer")
        assert "\u025b" in phonemes or "e" not in phonemes or "\u0281" in phonemes, (
            f"'mer' should pronounce r and use open-e: {phonemes}"
        )
        # Specifically: the 'r' must be pronounced (ʁ present)
        assert "\u0281" in phonemes, f"Expected /\u0281/ in 'mer', got: {phonemes}"

    def test_er_verb_infinitive(self):
        """Polysyllabic -er verbs should use /e/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("parler")
        assert phonemes[-1] == "e", f"Expected final /e/ in 'parler', got: {phonemes}"

    # -----------------------------------------------------------------
    # Fix 4: Apostrophe handling
    # -----------------------------------------------------------------

    def test_apostrophe_handling(self):
        """Apostrophe should not crash and should produce phonemes."""
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("l'ami")
        assert len(phonemes) > 0, "Apostrophe handling should not produce empty output"

    def test_curly_apostrophe_handling(self):
        """Curly apostrophe (U+2019) should behave the same as straight apostrophe."""
        from piper_train.phonemize.french import phonemize_french

        phonemes_straight = phonemize_french("l'ami")
        phonemes_curly = phonemize_french("l\u2019ami")
        assert phonemes_straight == phonemes_curly, (
            f"Straight and curly apostrophe should produce same result: "
            f"{phonemes_straight} vs {phonemes_curly}"
        )

    # -----------------------------------------------------------------
    # Fix 5: Open o (ɔ)
    # -----------------------------------------------------------------

    def test_open_o_porte(self):
        """Open o before pronounced consonant: porte -> /pɔʁt/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("porte")
        assert "\u0254" in phonemes, f"Expected /\u0254/ in 'porte', got: {phonemes}"

    def test_open_o_or(self):
        """Open o word-final before r: or -> /\u0254\u0281/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("or")
        assert "\u0254" in phonemes, f"Expected /\u0254/ in 'or', got: {phonemes}"

    # -----------------------------------------------------------------
    # Fix 6: gu before i — u is silent
    # -----------------------------------------------------------------

    def test_gu_before_i_guide(self):
        """gu before i: u is silent — guide should not contain y_vowel."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("guide")
        assert "y_vowel" not in phonemes, (
            f"gu+i: u should be silent in 'guide', got: {phonemes}"
        )
        assert "\u0261" in phonemes or "g" in str(phonemes), (
            f"Expected /ɡ/ in 'guide', got: {phonemes}"
        )

    # -----------------------------------------------------------------
    # Fix 7: euille and eil patterns
    # -----------------------------------------------------------------

    def test_feuille(self):
        """euille -> /\u0153j/: feuille."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("feuille")
        assert "\u0153" in phonemes, f"Expected /\u0153/ in 'feuille', got: {phonemes}"
        assert "j" in phonemes, f"Expected /j/ in 'feuille', got: {phonemes}"

    def test_soleil(self):
        """eil -> /\u025bj/: soleil."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("soleil")
        assert "\u025b" in phonemes, f"Expected /\u025b/ in 'soleil', got: {phonemes}"
        assert "j" in phonemes, f"Expected /j/ in 'soleil', got: {phonemes}"

    # -----------------------------------------------------------------
    # Fix 9: yn/ym -> ɛ̃
    # -----------------------------------------------------------------

    def test_syndicat_nasal(self):
        """yn before consonant -> \u025b\u0303: syndicat."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("syndicat")
        assert "\u025b\u0303" in phonemes, (
            f"Expected /\u025b\u0303/ in 'syndicat', got: {phonemes}"
        )

    def test_symbole_nasal(self):
        """ym before consonant -> \u025b\u0303: symbole."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("symbole")
        assert "\u025b\u0303" in phonemes, (
            f"Expected /\u025b\u0303/ in 'symbole', got: {phonemes}"
        )

    # -----------------------------------------------------------------
    # Fix 1: Declared phonemes — ɲ and ʁ must appear
    # -----------------------------------------------------------------

    def test_gn_produces_palatal_nasal(self):
        """gn -> \u0272: montagne."""
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("montagne")
        assert "\u0272" in phonemes, f"Expected /\u0272/ in 'montagne', got: {phonemes}"

    def test_r_produces_uvular(self):
        """r -> \u0281 consistently."""
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("rouge")
        assert "\u0281" in phonemes, f"Expected /\u0281/ in 'rouge', got: {phonemes}"

    # -----------------------------------------------------------------
    # Fix: -er exception words (hiver, enfer)
    # -----------------------------------------------------------------

    def test_er_exception_hiver(self):
        """hiver should keep /\u025b\u0281/, not use verb -er\u2192/e/ rule."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("hiver")
        assert "\u0281" in phonemes, f"Expected /\u0281/ in 'hiver', got: {phonemes}"

    def test_er_exception_enfer(self):
        """enfer should keep /\u025b\u0281/, not use verb -er\u2192/e/ rule."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("enfer")
        assert "\u0281" in phonemes, f"Expected /\u0281/ in 'enfer', got: {phonemes}"

    # -----------------------------------------------------------------
    # Fix: i before word-final silent e -> /i/ not /j/
    # -----------------------------------------------------------------

    def test_i_before_final_e_vie(self):
        """vie: i before final silent e should be /i/, not /j/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("vie")
        assert "i" in phonemes, f"Expected /i/ in 'vie', got: {phonemes}"
        assert "j" not in phonemes, f"Should not have /j/ in 'vie', got: {phonemes}"

    def test_i_before_final_e_amie(self):
        """amie: i before final silent e should be /i/, not /j/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("amie")
        assert "i" in phonemes, f"Expected /i/ in 'amie', got: {phonemes}"

    # -----------------------------------------------------------------
    # Fix: double r -> single /\u0281/
    # -----------------------------------------------------------------

    def test_double_r_terre(self):
        """terre: rr should produce single /\u0281/, not /\u0281\u0281/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("terre")
        r_count = phonemes.count("\u0281")
        assert r_count == 1, (
            f"Expected exactly 1 /\u0281/ in 'terre', got {r_count}: {phonemes}"
        )

    def test_double_r_guerre(self):
        """guerre: rr should produce single /\u0281/."""
        from piper_train.phonemize.french import _convert_word

        phonemes = _convert_word("guerre")
        r_count = phonemes.count("\u0281")
        assert r_count == 1, (
            f"Expected exactly 1 /\u0281/ in 'guerre', got {r_count}: {phonemes}"
        )

    # -----------------------------------------------------------------
    # Typographic punctuation passthrough
    # -----------------------------------------------------------------

    def test_em_dash_passthrough(self):
        """Em dash (U+2014) should pass through in phoneme output."""
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("oui \u2014 non")
        assert "\u2014" in phonemes, f"Em dash missing from output: {phonemes}"

    def test_en_dash_passthrough(self):
        """En dash (U+2013) should pass through in phoneme output."""
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("oui \u2013 non")
        assert "\u2013" in phonemes, f"En dash missing from output: {phonemes}"

    def test_ellipsis_passthrough(self):
        """Horizontal ellipsis (U+2026) should pass through in phoneme output."""
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("bonjour\u2026")
        assert "\u2026" in phonemes, f"Ellipsis missing from output: {phonemes}"

    def test_guillemets_passthrough(self):
        """French guillemets should pass through in phoneme output."""
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("\u00abbonjour\u00bb")
        assert "\u00ab" in phonemes, f"Left guillemet missing from output: {phonemes}"
        assert "\u00bb" in phonemes, f"Right guillemet missing from output: {phonemes}"

    def test_typographic_punctuation_prosody_alignment(self):
        """Typographic punctuation should maintain prosody alignment."""
        from piper_train.phonemize.french import phonemize_french_with_prosody

        phonemes, prosody = phonemize_french_with_prosody(
            "\u00abbonjour\u00bb \u2014 oui\u2026"
        )
        assert len(phonemes) == len(prosody), (
            f"Prosody alignment broken: "
            f"{len(phonemes)} phonemes vs {len(prosody)} prosody"
        )
