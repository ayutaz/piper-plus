"""Tests for phonemizer ABC and language registry."""

import pytest

from piper_plus_g2p import Phonemizer, ProsodyInfo
from piper_plus_g2p.english import EnglishPhonemizer
from piper_plus_g2p.japanese import JapanesePhonemizer
from piper_plus_g2p import (
    available_languages,
    get_phonemizer,
)

# EnglishProsodyInfo was always an alias for ProsodyInfo
EnglishProsodyInfo = ProsodyInfo


class TestProsodyInfoUnification:
    """ProsodyInfo is shared across languages."""

    def test_english_alias(self):
        assert EnglishProsodyInfo is ProsodyInfo

    def test_japanese_reexport(self):
        from piper_plus_g2p import ProsodyInfo as JaProsody

        assert JaProsody is ProsodyInfo


class TestRegistry:
    def test_ja_registered(self):
        assert "ja" in available_languages()

    def test_en_registered(self):
        assert "en" in available_languages()

    def test_get_ja(self):
        p = get_phonemizer("ja")
        assert isinstance(p, JapanesePhonemizer)

    def test_get_en(self):
        p = get_phonemizer("en")
        assert isinstance(p, EnglishPhonemizer)

    def test_unknown_language_raises(self):
        with pytest.raises(ValueError, match="Unsupported language"):
            get_phonemizer("xx")

    def test_available_languages_returns_list(self):
        langs = available_languages()
        assert isinstance(langs, list)
        assert set(langs) >= {"ja", "en"}


class TestABCInterface:
    """Phonemizer ABC contract tests."""

    def test_ja_phonemize(self):
        p = get_phonemizer("ja")
        result = p.phonemize("こんにちは")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_ja_phonemize_with_prosody(self):
        p = get_phonemizer("ja")
        phonemes, prosody = p.phonemize_with_prosody("こんにちは")
        assert len(phonemes) == len(prosody)

    def test_en_phonemize(self):
        p = get_phonemizer("en")
        result = p.phonemize("hello")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_en_phonemize_with_prosody(self):
        p = get_phonemizer("en")
        phonemes, prosody = p.phonemize_with_prosody("hello")
        assert len(phonemes) == len(prosody)

    def test_get_phoneme_id_map_ja(self):
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map

        id_map = get_phoneme_id_map("ja")
        assert isinstance(id_map, dict)
        assert len(id_map) > 0

    def test_get_phoneme_id_map_multilingual(self):
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map

        id_map = get_phoneme_id_map("ja-en")
        assert isinstance(id_map, dict)
        assert len(id_map) > 0
        # Multilingual map should be larger than JA-only
        ja_map = get_phoneme_id_map("ja")
        assert len(id_map) > len(ja_map)


class TestPiperEncoderPostProcess:
    """PiperEncoder _post_process inserts BOS/EOS/padding."""

    def test_identity_without_special_tokens(self):
        from piper_plus_g2p.encode.encoder import PiperEncoder

        # With no BOS/EOS in the map, only padding is inserted
        phoneme_id_map = {"_": [0]}
        encoder = PiperEncoder(phoneme_id_map)
        ids = [1, 2, 3]
        prosody = [None, None, None]
        result_ids, result_prosody = encoder._post_process(ids, prosody, "$")
        # Each id gets a pad after it: 1,0, 2,0, 3,0
        assert result_ids == [1, 0, 2, 0, 3, 0]
        assert len(result_prosody) == len(result_ids)

    def test_bos_eos(self):
        from piper_plus_g2p.encode.encoder import PiperEncoder

        phoneme_id_map = {"_": [0], "^": [1], "$": [2]}
        encoder = PiperEncoder(phoneme_id_map)
        ids, prosody = encoder._post_process([10, 20], [None, None], "$")
        assert ids[0] == 1  # BOS
        assert ids[-1] == 2  # EOS

    def test_padding_inserted(self):
        from piper_plus_g2p.encode.encoder import PiperEncoder

        phoneme_id_map = {"_": [0], "^": [1], "$": [2]}
        encoder = PiperEncoder(phoneme_id_map)
        ids, _ = encoder._post_process([10, 20], [None, None], "$")
        # BOS(1), pad(0), 10, pad(0), 20, pad(0), EOS(2)
        assert ids == [1, 0, 10, 0, 20, 0, 2]
