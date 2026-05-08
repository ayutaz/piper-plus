"""Tests for piper_plus_g2p.french -- FrenchPhonemizer.

Snapshots pin the current rule-based output (including liaison + elision
helpers).
"""

from piper_plus_g2p.french import FrenchPhonemizer


class TestBasic:
    def test_basic_phonemize(self):
        p = FrenchPhonemizer()
        tokens = p.phonemize("Bonjour")
        assert len(tokens) > 0

    def test_word_boundary(self):
        p = FrenchPhonemizer()
        assert " " in p.phonemize("Bonjour le monde")

    def test_no_pua(self):
        p = FrenchPhonemizer()
        tokens = p.phonemize("Bonjour, le monde!")
        for tok in tokens:
            for ch in tok:
                assert not (0xE000 <= ord(ch) <= 0xF8FF)

    def test_bonjour(self):
        """Bonjour -> b ɔ̃ ʒ u ʁ (nasal o + uvular r)."""
        p = FrenchPhonemizer()
        assert p.phonemize("Bonjour") == ["b", "ɔ̃", "ʒ", "u", "ʁ"]

    def test_amour(self):
        p = FrenchPhonemizer()
        assert p.phonemize("amour") == ["a", "m", "u", "ʁ"]

    def test_merci(self):
        p = FrenchPhonemizer()
        assert p.phonemize("merci") == ["m", "ɛ", "ʁ", "s", "i"]

    def test_oui(self):
        p = FrenchPhonemizer()
        assert p.phonemize("oui") == ["u", "i"]

    def test_qui(self):
        """qui -> k i (qu -> k)."""
        p = FrenchPhonemizer()
        assert p.phonemize("qui") == ["k", "i"]


class TestNasalVowels:
    """ɔ̃, ɑ̃, ɛ̃."""

    def test_pain_nasal_e(self):
        p = FrenchPhonemizer()
        assert p.phonemize("pain") == ["p", "ɛ̃"]

    def test_bon_nasal_o(self):
        p = FrenchPhonemizer()
        assert p.phonemize("bon") == ["b", "ɔ̃"]

    def test_temps_nasal_a(self):
        p = FrenchPhonemizer()
        assert p.phonemize("temps") == ["t", "ɑ̃"]

    def test_main_nasal_e(self):
        p = FrenchPhonemizer()
        assert p.phonemize("main") == ["m", "ɛ̃"]

    def test_enfant_double_nasal(self):
        p = FrenchPhonemizer()
        assert p.phonemize("enfant") == ["ɑ̃", "f", "ɑ̃"]

    def test_bien_nasal(self):
        p = FrenchPhonemizer()
        assert p.phonemize("bien") == ["b", "j", "ɛ̃"]

    def test_grand(self):
        p = FrenchPhonemizer()
        assert p.phonemize("grand") == ["ɡ", "ʁ", "ɑ̃"]


class TestSilentFinals:
    def test_silent_final_t_in_petit(self):
        """petit -> p ə t i (final t silent)."""
        p = FrenchPhonemizer()
        tokens = p.phonemize("petit")
        assert tokens[-1] != "t"
        assert tokens == ["p", "ə", "t", "i"]

    def test_que_silent_e(self):
        """que -> k (final e silent)."""
        p = FrenchPhonemizer()
        assert p.phonemize("que") == ["k"]


class TestLiaison:
    """Obligatoire liaison: les amis, vous avez, etc."""

    def test_liaison_les_amis_inserts_z(self):
        """les amis -> l ə z [space] a m i."""
        p = FrenchPhonemizer()
        assert p.phonemize("les amis") == ["l", "ə", "z", " ", "a", "m", "i"]

    def test_liaison_vous_avez_inserts_z(self):
        p = FrenchPhonemizer()
        assert p.phonemize("vous avez") == ["v", "u", "z", " ", "a", "v", "ə"]

    def test_liaison_nous_allons(self):
        p = FrenchPhonemizer()
        assert p.phonemize("nous allons") == ["n", "u", "z", " ", "a", "l", "ɔ̃"]

    def test_liaison_mes_enfants(self):
        p = FrenchPhonemizer()
        assert p.phonemize("mes enfants") == [
            "m",
            "ə",
            "z",
            " ",
            "ɑ̃",
            "f",
            "ɑ̃",
        ]

    def test_liaison_des_hommes(self):
        p = FrenchPhonemizer()
        assert p.phonemize("des hommes") == [
            "d",
            "ə",
            "z",
            " ",
            "o",
            "m",
            "ə",
        ]

    def test_liaison_un_ami_inserts_n(self):
        """un ami -> ɛ̃ n [space] a m i (n liaison)."""
        p = FrenchPhonemizer()
        assert p.phonemize("un ami") == ["ɛ̃", "n", " ", "a", "m", "i"]

    def test_no_liaison_two_consonants(self):
        """sous + bon: no liaison required (no consonant inserted)."""
        p = FrenchPhonemizer()
        tokens = p.phonemize("sous bon")
        # consonant→consonant transition keeps separator without liaison link
        assert " " in tokens


class TestElision:
    """l', d', j', c' attach to following word."""

    def test_lartbre(self):
        """l'arbre -> l a ʁ b ʁ."""
        p = FrenchPhonemizer()
        assert p.phonemize("l'arbre") == ["l", "a", "ʁ", "b", "ʁ"]

    def test_jaime(self):
        """j'aime -> ʒ ɛ m."""
        p = FrenchPhonemizer()
        assert p.phonemize("j'aime") == ["ʒ", "ɛ", "m"]

    def test_cest(self):
        """c'est -> s ɛ s (snapshot of current behaviour)."""
        p = FrenchPhonemizer()
        assert p.phonemize("c'est") == ["s", "ɛ", "s"]


class TestSpecialDigraphs:
    def test_eau_to_o(self):
        """eau -> o."""
        p = FrenchPhonemizer()
        assert p.phonemize("eau") == ["o"]

    def test_au_to_o_in_haut(self):
        """haut -> o (silent h + au -> o)."""
        p = FrenchPhonemizer()
        assert p.phonemize("haut") == ["o"]

    def test_oi_to_wa(self):
        """roi -> ʁ w a."""
        p = FrenchPhonemizer()
        assert p.phonemize("roi") == ["ʁ", "w", "a"]

    def test_ille_palatal(self):
        """fille -> f i j (ill -> j)."""
        p = FrenchPhonemizer()
        assert p.phonemize("fille") == ["f", "i", "j"]

    def test_gn_palatal(self):
        """champagne ends with ɲ."""
        p = FrenchPhonemizer()
        tokens = p.phonemize("champagne")
        assert "ɲ" in tokens

    def test_eu_to_oe(self):
        """feu -> f ø."""
        p = FrenchPhonemizer()
        assert p.phonemize("feu") == ["f", "ø"]


class TestEdgeCases:
    def test_empty_string(self):
        p = FrenchPhonemizer()
        assert p.phonemize("") == []

    def test_whitespace_only(self):
        p = FrenchPhonemizer()
        assert p.phonemize("   ") == []

    def test_digits_dropped(self):
        p = FrenchPhonemizer()
        assert p.phonemize("123") == []

    def test_punctuation_in_phrase(self):
        p = FrenchPhonemizer()
        tokens = p.phonemize("Bonjour, le monde!")
        assert "," in tokens
        assert "!" in tokens


class TestProsody:
    def test_prosody_length(self):
        p = FrenchPhonemizer()
        tokens, prosody = p.phonemize_with_prosody("Bonjour le monde")
        assert len(tokens) == len(prosody)

    def test_prosody_has_stress(self):
        from piper_plus_g2p.base import ProsodyInfo

        p = FrenchPhonemizer()
        _, prosody = p.phonemize_with_prosody("Bonjour")
        assert any(isinstance(pi, ProsodyInfo) and pi.a2 == 2 for pi in prosody)
