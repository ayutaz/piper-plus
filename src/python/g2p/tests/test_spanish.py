"""Tests for piper_plus_g2p.spanish -- SpanishPhonemizer.

Snapshot tests pinning current rule-based phonemiser behaviour. Expected
values are what the implementation currently emits; they form a regression
gate, not phonological ground truth.
"""

from piper_plus_g2p.spanish import SpanishPhonemizer


class TestBasic:
    def test_basic_phonemize(self):
        p = SpanishPhonemizer()
        tokens = p.phonemize("Hola mundo")
        assert len(tokens) > 0

    def test_word_boundary(self):
        p = SpanishPhonemizer()
        tokens = p.phonemize("Hola mundo")
        assert " " in tokens

    def test_no_pua_characters(self):
        p = SpanishPhonemizer()
        tokens = p.phonemize("Hola, mundo!")
        for token in tokens:
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                    f"PUA character: U+{ord(ch):04X} in {token!r}"
                )

    def test_casa(self):
        p = SpanishPhonemizer()
        assert p.phonemize("casa") == ["k", "ˈ", "a", "s", "a"]

    def test_gato(self):
        p = SpanishPhonemizer()
        assert p.phonemize("gato") == ["ɡ", "ˈ", "a", "t", "o"]

    def test_libro(self):
        """libro -> spirantised β + flap ɾ."""
        p = SpanishPhonemizer()
        assert p.phonemize("libro") == ["l", "ˈ", "i", "β", "ɾ", "o"]

    def test_perro_trill(self):
        """'perro' produces the trill 'rr' token."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("perro")
        assert "rr" in tokens
        assert tokens == ["p", "ˈ", "e", "rr", "o"]

    def test_amor_flap(self):
        """word-internal r remains flap ɾ."""
        p = SpanishPhonemizer()
        assert p.phonemize("amor") == ["a", "m", "ˈ", "o", "ɾ"]

    def test_reino_initial_r_is_trill(self):
        """word-initial r becomes trill rr."""
        p = SpanishPhonemizer()
        assert p.phonemize("reino") == ["rr", "ˈ", "e", "i", "n", "o"]

    def test_jamon_x(self):
        """j -> x (velar fricative)."""
        p = SpanishPhonemizer()
        assert p.phonemize("jamon") == ["x", "ˈ", "a", "m", "o", "n"]

    def test_general_g_before_e_is_x(self):
        """g + e/i -> x (general -> x e n e ɾ ˈ a l)."""
        p = SpanishPhonemizer()
        assert p.phonemize("general") == ["x", "e", "n", "e", "ɾ", "ˈ", "a", "l"]

    def test_cielo_c_before_i_is_s(self):
        """c + e/i -> s (Latin American seseo)."""
        p = SpanishPhonemizer()
        assert p.phonemize("cielo") == ["s", "ˈ", "i", "e", "l", "o"]

    def test_queso_qu_is_k(self):
        p = SpanishPhonemizer()
        assert p.phonemize("queso") == ["k", "ˈ", "e", "s", "o"]

    def test_taxi_x(self):
        """x -> k s in 'taxi'."""
        p = SpanishPhonemizer()
        assert p.phonemize("taxi") == ["t", "ˈ", "a", "k", "s", "i"]

    def test_silent_h(self):
        """h is silent in Spanish (hola starts with vowel)."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("hola")
        assert "h" not in tokens
        assert tokens[:2] == ["ˈ", "o"]


class TestStress:
    """Stress placement (paroxytone default + acute mark + n/s ending)."""

    def test_stress_marker_present(self):
        p = SpanishPhonemizer()
        assert "ˈ" in p.phonemize("Hola")

    def test_paroxytone_default_casa(self):
        """'casa' (vowel-final) stresses penultimate syllable."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("casa")
        idx = tokens.index("ˈ")
        assert tokens[idx + 1] == "a"

    def test_acute_mark_jamon(self):
        """jamon (no acute) stresses penultimate syllable."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("jamón")
        idx = tokens.index("ˈ")
        assert tokens[idx + 1] == "o"

    def test_consonant_final_amor(self):
        """consonant-final word (amor, not n/s) stresses last syllable."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("amor")
        idx = tokens.index("ˈ")
        assert tokens[idx + 1] == "o"

    def test_n_ending_examen(self):
        """examen (n-final) stresses penultimate syllable."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("examen")
        idx = tokens.index("ˈ")
        assert tokens[idx + 1] == "a"


class TestSyllabification:
    def test_diphthong_aire(self):
        """aire keeps a-i as nucleus + diphthong."""
        p = SpanishPhonemizer()
        assert p.phonemize("aire") == ["ˈ", "a", "i", "ɾ", "e"]

    def test_diphthong_hueso(self):
        """hueso retains [u, e] sequence (silent h)."""
        p = SpanishPhonemizer()
        assert p.phonemize("hueso") == ["ˈ", "u", "e", "s", "o"]

    def test_diphthong_ciudad(self):
        """ciudad spans s-i-u + ð."""
        p = SpanishPhonemizer()
        assert p.phonemize("ciudad") == ["s", "i", "u", "ð", "ˈ", "a", "ð"]

    def test_consonant_cluster_libro(self):
        """libro has β-ɾ cluster after stressed i."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("libro")
        assert "β" in tokens and "ɾ" in tokens


class TestSpirantisation:
    def test_b_to_beta(self):
        """intervocalic b -> β (verdad -> b e ɾ ð ˈ a ð)."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("verdad")
        assert "ð" in tokens

    def test_d_to_eth_word_final(self):
        """word-final d -> ð (verdad)."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("verdad")
        assert tokens[-1] == "ð"

    def test_g_to_gamma_intervocalic(self):
        """intervocalic g -> ɣ (agua, amigo)."""
        p = SpanishPhonemizer()
        assert "ɣ" in p.phonemize("agua")
        assert "ɣ" in p.phonemize("amigo")


class TestEdgeCases:
    def test_empty_string(self):
        p = SpanishPhonemizer()
        assert p.phonemize("") == []

    def test_whitespace_only(self):
        p = SpanishPhonemizer()
        assert p.phonemize("   ") == []

    def test_digits_dropped(self):
        p = SpanishPhonemizer()
        assert p.phonemize("123") == []

    def test_punctuation_only(self):
        p = SpanishPhonemizer()
        tokens = p.phonemize("!?")
        assert tokens == ["!", "?"]

    def test_punctuation_in_phrase(self):
        p = SpanishPhonemizer()
        tokens = p.phonemize("hola, mundo!")
        assert "," in tokens
        assert "!" in tokens

    def test_hyphen_treated_as_separator(self):
        p = SpanishPhonemizer()
        tokens = p.phonemize("hola-amigo")
        assert tokens == ["ˈ", "o", "l", "a", " ", "a", "m", "ˈ", "i", "ɣ", "o"]


class TestProsody:
    def test_prosody_length(self):
        p = SpanishPhonemizer()
        tokens, prosody = p.phonemize_with_prosody("Buenos dias")
        assert len(tokens) == len(prosody)

    def test_prosody_stress_value(self):
        from piper_plus_g2p.base import ProsodyInfo

        p = SpanishPhonemizer()
        _, prosody = p.phonemize_with_prosody("Hola")
        has_stress = any(isinstance(pi, ProsodyInfo) and pi.a2 == 2 for pi in prosody)
        assert has_stress
