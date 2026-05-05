"""Standalone correctness tests for piper_plus_g2p output.

These tests were originally comparing piper_plus_g2p output vs piper_train.phonemize
output. Since piper_train.phonemize has been removed (code moved to piper_plus_g2p),
these are now standalone correctness tests verifying piper_plus_g2p behavior.
"""

from tests.conftest import requires_en, requires_ja, requires_zh


@requires_ja
class TestJACorrectness:
    def test_ja_tokens_ipa_to_pua(self):
        """Tokens + BOS/EOS + PUA should produce valid phoneme sequence."""
        from piper_plus_g2p.encode.pua import map_token
        from piper_plus_g2p.japanese import JapanesePhonemizer

        text = "こんにちは"
        p = JapanesePhonemizer()
        g2p_tokens = p.phonemize(text)

        # Add BOS/EOS
        full_tokens = ["^"] + g2p_tokens + ["$"]

        # Apply PUA mapping
        pua_tokens = [map_token(t) for t in full_tokens]

        # Verify structure: starts with BOS, ends with EOS
        assert pua_tokens[0] == "^"
        assert pua_tokens[-1] == "$"
        assert len(pua_tokens) > 2  # more than just BOS+EOS

    def test_pua_mapping_count(self):
        """FIXED_PUA_MAPPING should have the expected number of entries."""
        from piper_plus_g2p.encode.pua import FIXED_PUA_MAPPING

        assert len(FIXED_PUA_MAPPING) == 99

    def test_ja_id_map_format(self):
        """get_phoneme_id_map('ja') should return a valid id map."""
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map

        g2p_map = get_phoneme_id_map("ja")
        assert isinstance(g2p_map, dict)
        assert len(g2p_map) == 65  # 10 special + 55 phonemes
        assert "^" in g2p_map
        assert "$" in g2p_map
        assert "_" in g2p_map


@requires_ja
@requires_en
class TestENCorrectness:
    def test_en_phonemize_produces_output(self):
        """piper_plus_g2p EN should produce valid phoneme output."""
        from piper_plus_g2p.english import EnglishPhonemizer

        text = "Hello, how are you today?"
        p = EnglishPhonemizer()
        g2p_tokens = p.phonemize(text)
        assert len(g2p_tokens) > 0
        assert all(isinstance(t, str) for t in g2p_tokens)


class TestMultilingualIDMap:
    def test_multilingual_8lang_id_map_size(self):
        """piper_plus_g2p multilingual ID map should have expected size."""
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map

        g2p_map = get_phoneme_id_map("ja-en-zh-ko-es-fr-pt-sv")
        assert len(g2p_map) > 170  # should have many symbols
        assert "^" in g2p_map
        assert "$" in g2p_map


@requires_zh
class TestZHCorrectness:
    def test_zh_phonemize_produces_output(self):
        """piper_plus_g2p ZH should produce valid phoneme output."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        text = "你好世界"
        p = ChinesePhonemizer()
        g2p_tokens = p.phonemize(text)
        assert len(g2p_tokens) > 0


class TestESCorrectness:
    def test_es_phonemize_produces_output(self):
        """piper_plus_g2p ES should produce valid phoneme output."""
        from piper_plus_g2p.spanish import SpanishPhonemizer

        text = "Hola mundo"
        p = SpanishPhonemizer()
        g2p_tokens = p.phonemize(text)
        assert len(g2p_tokens) > 0


class TestFRCorrectness:
    def test_fr_phonemize_produces_output(self):
        """piper_plus_g2p FR should produce valid phoneme output."""
        from piper_plus_g2p.french import FrenchPhonemizer

        text = "Bonjour le monde"
        p = FrenchPhonemizer()
        g2p_tokens = p.phonemize(text)
        assert len(g2p_tokens) > 0


class TestPTCorrectness:
    def test_pt_phonemize_produces_output(self):
        """piper_plus_g2p PT should produce valid phoneme output."""
        from piper_plus_g2p.portuguese import PortuguesePhonemizer

        text = "Olá mundo"
        p = PortuguesePhonemizer()
        g2p_tokens = p.phonemize(text)
        assert len(g2p_tokens) > 0


class TestSVCorrectness:
    def test_sv_phonemize_produces_output(self):
        """piper_plus_g2p SV should produce valid phoneme output."""
        from piper_plus_g2p.swedish import SwedishPhonemizer

        text = "Hej världen"
        p = SwedishPhonemizer()
        g2p_tokens = p.phonemize(text)
        assert len(g2p_tokens) > 0


@requires_ja
class TestJAProsodyCorrectness:
    def test_ja_prosody_a1_a2_a3(self):
        """piper_plus_g2p JA prosody should produce valid a1/a2/a3 values."""
        from piper_plus_g2p.japanese import JapanesePhonemizer

        text = "こんにちは"
        p = JapanesePhonemizer()
        _, g2p_prosody = p.phonemize_with_prosody(text)

        assert len(g2p_prosody) > 0
        # At least some entries should have prosody info
        infos = [pr for pr in g2p_prosody if pr is not None]
        assert len(infos) > 0
        for info in infos:
            assert hasattr(info, "a1")
            assert hasattr(info, "a2")
            assert hasattr(info, "a3")
