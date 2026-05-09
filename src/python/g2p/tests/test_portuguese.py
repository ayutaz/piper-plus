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


class TestEuropeanPortuguese:
    """Pin the five BR↔EU contrasts captured by `_apply_eu_postprocessing`.

    See ``docs/spec/pt-dialect-contract.toml`` (spec_version 2,
    ``[implementation.differences]``) for the typological references
    (Cruz-Ferreira 1995; Mateus & d'Andrade 2000).
    """

    def test_dialect_enum_default_is_br(self):
        from piper_plus_g2p.portuguese import Dialect, PortuguesePhonemizer

        p = PortuguesePhonemizer()
        assert p.dialect == Dialect.BR
        assert p.language_code == "pt"

    def test_european_phonemizer_language_code(self):
        from piper_plus_g2p.portuguese import (
            Dialect,
            EuropeanPortuguesePhonemizer,
        )

        eu = EuropeanPortuguesePhonemizer()
        assert eu.dialect == Dialect.EU
        assert eu.language_code == "pt-PT"

    def test_parametric_eu_equals_subclass(self):
        from piper_plus_g2p.portuguese import (
            Dialect,
            EuropeanPortuguesePhonemizer,
            PortuguesePhonemizer,
        )

        param = PortuguesePhonemizer(dialect=Dialect.EU)
        sub = EuropeanPortuguesePhonemizer()
        for word in ["noite", "cidade", "mais", "Brasil", "carro", "olá mundo"]:
            assert param.phonemize(word) == sub.phonemize(word), (
                f"divergence on {word!r}: {param.phonemize(word)} "
                f"vs {sub.phonemize(word)}"
            )

    # ---- 5 differences pinned individually ----

    def test_difference1_no_td_palatalisation_before_final_e(self):
        from piper_plus_g2p.portuguese import (
            EuropeanPortuguesePhonemizer,
            PortuguesePhonemizer,
        )

        br = PortuguesePhonemizer().phonemize("noite")
        eu = EuropeanPortuguesePhonemizer().phonemize("noite")
        assert "tʃ" in br and "ɨ" not in br, f"BR baseline drift: {br}"
        assert "t" in eu and "tʃ" not in eu, f"EU palatalisation leaked: {eu}"
        assert "ɨ" in eu, f"EU final-e centralisation missing: {eu}"

    def test_difference2_final_unstressed_e_to_central_vowel(self):
        from piper_plus_g2p.portuguese import (
            EuropeanPortuguesePhonemizer,
            PortuguesePhonemizer,
        )

        br = PortuguesePhonemizer().phonemize("cidade")
        eu = EuropeanPortuguesePhonemizer().phonemize("cidade")
        assert br[-1] == "i", f"BR final-e reduction broke: {br}"
        assert eu[-1] == "ɨ", f"EU final-ɨ centralisation broke: {eu}"

    def test_difference3_coda_s_to_postalveolar(self):
        from piper_plus_g2p.portuguese import (
            EuropeanPortuguesePhonemizer,
            PortuguesePhonemizer,
        )

        br = PortuguesePhonemizer().phonemize("mais")
        eu = EuropeanPortuguesePhonemizer().phonemize("mais")
        assert br[-1] == "s", f"BR coda-s drift: {br}"
        assert eu[-1] == "ʃ", f"EU coda-s → ʃ broke: {eu}"

    def test_difference4_coda_l_velarisation(self):
        from piper_plus_g2p.portuguese import (
            EuropeanPortuguesePhonemizer,
            PortuguesePhonemizer,
        )

        br = PortuguesePhonemizer().phonemize("Brasil")
        eu = EuropeanPortuguesePhonemizer().phonemize("Brasil")
        assert br[-1] == "w", f"BR coda-l vocalisation drift: {br}"
        assert eu[-1] == "ɫ", f"EU coda-l → ɫ broke: {eu}"

    def test_difference5_r_canonicalisation_to_uvular(self):
        from piper_plus_g2p.portuguese import EuropeanPortuguesePhonemizer

        eu = EuropeanPortuguesePhonemizer()
        for word in ["cantar", "carro", "rato"]:
            tokens = eu.phonemize(word)
            assert "h" not in tokens, (
                f"EU left BR's debuccalised /h/ in output for {word!r}: {tokens}"
            )

    # ---- Phoneme-count preservation (prosody alignment) ----

    def test_eu_postprocessing_preserves_phoneme_count(self):
        from piper_plus_g2p.portuguese import (
            EuropeanPortuguesePhonemizer,
            PortuguesePhonemizer,
        )

        for word in [
            "noite",
            "cidade",
            "mais",
            "Brasil",
            "obrigado",
            "olá mundo",
            "telefone",
        ]:
            br = PortuguesePhonemizer().phonemize(word)
            eu = EuropeanPortuguesePhonemizer().phonemize(word)
            assert len(br) == len(eu), (
                f"phoneme-count drift for {word!r}: BR={len(br)} EU={len(eu)} "
                f"(BR={br} EU={eu})"
            )

    def test_eu_prosody_alignment(self):
        from piper_plus_g2p.portuguese import EuropeanPortuguesePhonemizer

        eu = EuropeanPortuguesePhonemizer()
        for sentence in ["noite calma", "Brasil é grande", "cidade fria"]:
            phonemes, prosody = eu.phonemize_with_prosody(sentence)
            assert len(phonemes) == len(prosody)
