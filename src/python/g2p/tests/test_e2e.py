"""End-to-end tests: text -> phonemize -> encode -> phoneme_ids."""

from tests.conftest import requires_en, requires_ja, requires_ko


@requires_ja
class TestJAEndToEnd:
    def test_ja_text_to_ids(self):
        """JA text -> phonemize -> encode -> phoneme_ids produces valid IDs."""
        from piper_plus_g2p.encode.encoder import PiperEncoder
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("こんにちは")

        id_map = get_phoneme_id_map("ja")
        enc = PiperEncoder(id_map)
        ids = enc.encode(tokens)

        assert isinstance(ids, list)
        assert len(ids) > 0
        assert all(isinstance(i, int) for i in ids)
        # First should be BOS, last should be EOS
        bos_id = id_map["^"][0]
        eos_id = id_map["$"][0]
        assert ids[0] == bos_id
        assert ids[-1] == eos_id

    def test_ja_prosody_pipeline(self):
        """JA full pipeline with prosody:
        text -> phonemize_with_prosody -> encode_with_prosody."""
        from piper_plus_g2p.encode.encoder import PiperEncoder
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
        from piper_plus_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens, prosody = p.phonemize_with_prosody("今日は良い天気ですね。")

        id_map = get_phoneme_id_map("ja")
        enc = PiperEncoder(id_map)
        ids, prosody_out = enc.encode_with_prosody(tokens, prosody)

        assert isinstance(ids, list)
        assert isinstance(prosody_out, list)
        assert len(ids) == len(prosody_out)
        assert len(ids) > 0

        # Verify prosody output contains some real values
        non_none = [p for p in prosody_out if p is not None]
        assert len(non_none) > 0, "Expected some non-None prosody entries"
        # Verify ProsodyInfo structure
        sample = non_none[0]
        assert hasattr(sample, "a1")
        assert hasattr(sample, "a2")
        assert hasattr(sample, "a3")


@requires_en
class TestENEndToEnd:
    def test_en_text_to_ids(self):
        """EN text -> phonemize -> verify structure.

        EN does not have a built-in ID map, so we verify the phonemize
        step produces valid tokens and prosody that could be encoded
        with a config.json-sourced ID map.
        """
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        tokens = p.phonemize("Hello world")
        tokens_with_prosody, prosody = p.phonemize_with_prosody("Hello world")

        # Basic structural checks
        assert isinstance(tokens, list)
        assert len(tokens) > 0
        assert tokens == tokens_with_prosody
        assert len(tokens_with_prosody) == len(prosody)

        # Verify word boundary
        assert " " in tokens, "Expected space as word boundary"

        # Verify prosody values are reasonable
        for pi in prosody:
            if pi is not None:
                assert pi.a1 == 0, "EN a1 should always be 0"
                assert pi.a2 >= 0, f"a2 should be non-negative, got {pi.a2}"
                assert pi.a3 >= 0, f"a3 should be non-negative, got {pi.a3}"


class TestSwedishE2E:
    def test_sv_phonemize_encode_roundtrip(self):
        """SV text -> phonemize -> encode -> phoneme_ids has BOS/EOS/padding."""
        from piper_plus_g2p.encode.encoder import PiperEncoder
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
        from piper_plus_g2p.swedish import SwedishPhonemizer

        p = SwedishPhonemizer()
        tokens = p.phonemize("Hej, hur mår du?")

        id_map = get_phoneme_id_map("multilingual")
        enc = PiperEncoder(id_map)
        ids = enc.encode(tokens)

        assert isinstance(ids, list)
        assert len(ids) > 0
        assert all(isinstance(i, int) for i in ids)
        # First should be BOS, last should be EOS
        bos_id = id_map["^"][0]
        eos_id = id_map["$"][0]
        assert ids[0] == bos_id
        assert ids[-1] == eos_id

    def test_sv_pua_tokens_in_ids(self):
        """SV long vowel PUA tokens get proper IDs in multilingual map."""
        from piper_plus_g2p.encode.encoder import PiperEncoder
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
        from piper_plus_g2p.encode.pua import map_token
        from piper_plus_g2p.swedish import SwedishPhonemizer

        p = SwedishPhonemizer()
        # "God morgon Sverige" produces long vowels (e.g. eː in Sverige)
        tokens = p.phonemize("God morgon Sverige.")

        id_map = get_phoneme_id_map("multilingual")
        enc = PiperEncoder(id_map)
        ids = enc.encode(tokens)

        # Verify that SV long vowel PUA characters are present in the map
        sv_long_vowels = ["iː", "yː", "eː", "ɛː", "øː", "ɑː", "oː", "uː", "ʉː"]
        for token in sv_long_vowels:
            pua_char = map_token(token)
            assert len(pua_char) == 1, (
                f"SV long vowel {token!r} should map to single PUA char"
            )
            assert pua_char in id_map, (
                f"SV PUA char for {token!r} (U+{ord(pua_char):04X}) "
                f"missing from multilingual id_map"
            )

        # Verify the encoded output contains valid IDs (no zeros from
        # unknown tokens, except for padding)
        pad_id = id_map["_"][0]
        non_pad = [i for i in ids if i != pad_id]
        assert len(non_pad) > 0, "Expected non-padding IDs in encoded output"


@requires_ko
class TestKoreanE2E:
    def test_ko_phonemize_encode_roundtrip(self):
        """KO text -> phonemize -> encode -> phoneme_ids has BOS/EOS."""
        from piper_plus_g2p.encode.encoder import PiperEncoder
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
        from piper_plus_g2p.korean import KoreanPhonemizer

        p = KoreanPhonemizer()
        tokens = p.phonemize("안녕하세요")

        id_map = get_phoneme_id_map("multilingual")
        enc = PiperEncoder(id_map)
        ids = enc.encode(tokens)

        assert isinstance(ids, list)
        assert len(ids) > 0
        assert all(isinstance(i, int) for i in ids)
        # First should be BOS, last should be EOS
        bos_id = id_map["^"][0]
        eos_id = id_map["$"][0]
        assert ids[0] == bos_id
        assert ids[-1] == eos_id

    def test_ko_pua_tokens_in_ids(self):
        """KO tense/aspirated PUA tokens get proper IDs in multilingual map."""
        from piper_plus_g2p.encode.encoder import PiperEncoder
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
        from piper_plus_g2p.encode.pua import map_token
        from piper_plus_g2p.korean import KoreanPhonemizer

        p = KoreanPhonemizer()
        # "감사합니다" includes aspirated and tense consonants
        tokens = p.phonemize("감사합니다")

        id_map = get_phoneme_id_map("multilingual")
        enc = PiperEncoder(id_map)
        ids = enc.encode(tokens)

        # Verify that KO-specific PUA characters are present in the map
        ko_pua_tokens = [
            "p͈",
            "t͈",
            "k͈",
            "s͈",  # tense consonants
            "tɕ",
            "tɕʰ",
            "t͈ɕ",  # affricates
            "pʰ",
            "tʰ",
            "kʰ",  # aspirated
            "k̚",
            "t̚",
            "p̚",  # unreleased finals
        ]
        for token in ko_pua_tokens:
            pua_char = map_token(token)
            assert len(pua_char) == 1, (
                f"KO token {token!r} should map to single PUA char"
            )
            assert pua_char in id_map, (
                f"KO PUA char for {token!r} (U+{ord(pua_char):04X}) "
                f"missing from multilingual id_map"
            )

        # Verify the encoded output contains valid IDs
        pad_id = id_map["_"][0]
        non_pad = [i for i in ids if i != pad_id]
        assert len(non_pad) > 0, "Expected non-padding IDs in encoded output"
