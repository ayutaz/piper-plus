"""Tests for piper_plus_g2p.portuguese -- PortuguesePhonemizer.

Snapshots pin the current Brazilian-Portuguese-leaning rule output.
"""

from piper_plus_g2p.portuguese import PortuguesePhonemizer


class TestBasic:
    def test_basic_phonemize(self):
        p = PortuguesePhonemizer()
        tokens = p.phonemize("Olá mundo")
        assert len(tokens) > 0

    def test_word_boundary(self):
        p = PortuguesePhonemizer()
        assert " " in p.phonemize("Bom dia")

    def test_no_pua(self):
        p = PortuguesePhonemizer()
        tokens = p.phonemize("Bom dia")
        for token in tokens:
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), token

    def test_casa(self):
        """intervocalic s -> z (BR)."""
        p = PortuguesePhonemizer()
        assert p.phonemize("casa") == ["k", "a", "z", "a"]

    def test_rosa_z(self):
        """rosa: r -> ʁ, intervocalic s -> z."""
        p = PortuguesePhonemizer()
        assert p.phonemize("rosa") == ["ʁ", "o", "z", "a"]

    def test_amor_final_r_uvular(self):
        p = PortuguesePhonemizer()
        assert p.phonemize("amor") == ["a", "m", "o", "ʁ"]

    def test_jogo(self):
        """j -> ʒ, g intervocalic -> ɡ."""
        p = PortuguesePhonemizer()
        assert p.phonemize("jogo") == ["ʒ", "o", "ɡ", "u"]

    def test_carro_intervocalic_rr(self):
        """rr -> uvular ʁ; final unstressed o -> u."""
        p = PortuguesePhonemizer()
        assert p.phonemize("carro") == ["k", "a", "ʁ", "u"]

    def test_kilo(self):
        p = PortuguesePhonemizer()
        assert p.phonemize("kilo") == ["k", "i", "l", "u"]

    def test_gato(self):
        p = PortuguesePhonemizer()
        assert p.phonemize("gato") == ["ɡ", "a", "t", "u"]


class TestNasalVowel:
    """Nasal vowels (ã, ẽ, ĩ, õ, ũ)."""

    def test_mundo_nasal_u(self):
        p = PortuguesePhonemizer()
        tokens = p.phonemize("mundo")
        nasal_vowels = {"ã", "ẽ", "ĩ", "õ", "ũ"}
        assert any(t in nasal_vowels for t in tokens), tokens

    def test_pao_nasal_a(self):
        """pão -> p ã u."""
        p = PortuguesePhonemizer()
        assert p.phonemize("pão") == ["p", "ã", "u"]

    def test_irmao_nasal_a(self):
        """irmão -> i ʁ m ã u."""
        p = PortuguesePhonemizer()
        assert p.phonemize("irmão") == ["i", "ʁ", "m", "ã", "u"]

    def test_sim_nasal_i(self):
        """sim -> s ĩ."""
        p = PortuguesePhonemizer()
        assert p.phonemize("sim") == ["s", "ĩ"]

    def test_um_nasal_u(self):
        """um -> ũ (single-vowel word)."""
        p = PortuguesePhonemizer()
        assert p.phonemize("um") == ["ũ"]

    def test_lindo_nasal_i(self):
        """lindo -> l ĩ d u."""
        p = PortuguesePhonemizer()
        assert p.phonemize("lindo") == ["l", "ĩ", "d", "u"]

    def test_banco_nasal_a(self):
        """banco -> b ã k u (a + nC -> nasal a)."""
        p = PortuguesePhonemizer()
        assert p.phonemize("banco") == ["b", "ã", "k", "u"]

    def test_gente_nasal_e(self):
        """gente -> ʒ ẽ tʃ i."""
        p = PortuguesePhonemizer()
        assert p.phonemize("gente") == ["ʒ", "ẽ", "tʃ", "i"]

    def test_ponte_nasal_o(self):
        """ponte -> p õ tʃ i."""
        p = PortuguesePhonemizer()
        assert p.phonemize("ponte") == ["p", "õ", "tʃ", "i"]


class TestPalatalisation:
    """BR palatalisation: t/d before /i/ -> tʃ/dʒ."""

    def test_forte_t_before_i_palatal(self):
        """forte -> f o ʁ tʃ i (te -> tʃi)."""
        p = PortuguesePhonemizer()
        assert p.phonemize("forte") == ["f", "o", "ʁ", "tʃ", "i"]

    def test_tarde_d_before_i_palatal(self):
        """tarde -> t a ʁ dʒ i (de -> dʒi)."""
        p = PortuguesePhonemizer()
        assert p.phonemize("tarde") == ["t", "a", "ʁ", "dʒ", "i"]

    def test_noite_palatal(self):
        """noite -> n o i tʃ i."""
        p = PortuguesePhonemizer()
        assert p.phonemize("noite") == ["n", "o", "i", "tʃ", "i"]


class TestCodaLVocalisation:
    """coda L -> /w/ (BR)."""

    def test_sol_word_final_l(self):
        """sol -> s o w."""
        p = PortuguesePhonemizer()
        assert p.phonemize("sol") == ["s", "o", "w"]

    def test_mil_word_final_l(self):
        """mil -> m i w."""
        p = PortuguesePhonemizer()
        assert p.phonemize("mil") == ["m", "i", "w"]

    def test_azul_word_final_l(self):
        """azul -> a z u w."""
        p = PortuguesePhonemizer()
        assert p.phonemize("azul") == ["a", "z", "u", "w"]

    def test_papel_word_final_l(self):
        """papel -> p a p e w."""
        p = PortuguesePhonemizer()
        assert p.phonemize("papel") == ["p", "a", "p", "e", "w"]

    def test_brasil(self):
        """brasil -> b ʁ a z i w."""
        p = PortuguesePhonemizer()
        assert p.phonemize("brasil") == ["b", "ʁ", "a", "z", "i", "w"]

    def test_qual(self):
        """qual -> k w a w."""
        p = PortuguesePhonemizer()
        assert p.phonemize("qual") == ["k", "w", "a", "w"]


class TestPalatal:
    def test_manha_palatal_n(self):
        """manhã: nh -> ɲ."""
        p = PortuguesePhonemizer()
        assert p.phonemize("manhã") == ["m", "a", "ɲ", "ã"]


class TestEdgeCases:
    def test_empty_string(self):
        p = PortuguesePhonemizer()
        assert p.phonemize("") == []

    def test_whitespace_only(self):
        p = PortuguesePhonemizer()
        assert p.phonemize("   ") == []

    def test_digits_dropped(self):
        p = PortuguesePhonemizer()
        assert p.phonemize("123") == []

    def test_punctuation_in_phrase(self):
        p = PortuguesePhonemizer()
        tokens = p.phonemize("Bom dia, mundo!")
        assert "," in tokens
        assert "!" in tokens


class TestProsody:
    def test_prosody_length(self):
        p = PortuguesePhonemizer()
        tokens, prosody = p.phonemize_with_prosody("Olá mundo")
        assert len(tokens) == len(prosody)

    def test_prosody_has_stress(self):
        from piper_plus_g2p.base import ProsodyInfo

        p = PortuguesePhonemizer()
        _, prosody = p.phonemize_with_prosody("Olá")
        assert any(isinstance(pi, ProsodyInfo) and pi.a2 == 2 for pi in prosody)
