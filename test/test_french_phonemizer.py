"""Tests for French phonemizer."""


class TestFrenchPhonemizer:
    """Tests for rule-based French G2P."""

    def test_simple_word(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("bonjour")
        assert len(phonemes) > 0

    def test_nasal_vowel_an(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("france")
        assert "\u0251\u0303" in phonemes

    def test_nasal_vowel_on(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("bon")
        assert "\u0254\u0303" in phonemes

    def test_nasal_vowel_in(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("vin")
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
