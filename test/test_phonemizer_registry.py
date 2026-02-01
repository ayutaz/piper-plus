"""Tests for phonemizer ABC and language registry."""

import pytest

from piper_train.phonemize.base import Phonemizer, ProsodyInfo
from piper_train.phonemize.english import EnglishPhonemizer, EnglishProsodyInfo
from piper_train.phonemize.japanese import JapanesePhonemizer
from piper_train.phonemize.registry import (
    available_languages,
    get_phonemizer,
)


class TestProsodyInfoUnification:
    """ProsodyInfo is shared across languages."""

    def test_english_alias(self):
        assert EnglishProsodyInfo is ProsodyInfo

    def test_japanese_reexport(self):
        from piper_train.phonemize.japanese import ProsodyInfo as JaProsody

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

    def test_get_phoneme_id_map_returns_none(self):
        for lang in available_languages():
            p = get_phonemizer(lang)
            assert p.get_phoneme_id_map() is None


class TestDefaultPostProcessIds:
    """Base class post_process_ids is a no-op."""

    def test_ja_noop(self):
        p = get_phonemizer("ja")
        ids = [1, 2, 3]
        prosody = [None, None, None]
        result_ids, result_prosody = p.post_process_ids(ids, prosody, {})
        assert result_ids == ids
        assert result_prosody == prosody


class TestEnglishPostProcessIds:
    """English post_process_ids adds BOS/EOS/padding."""

    def test_bos_eos(self):
        p = get_phonemizer("en")
        phoneme_id_map = {"_": [0], "^": [1], "$": [2]}
        ids, prosody = p.post_process_ids([10, 20], [None, None], phoneme_id_map)
        assert ids[0] == 1  # BOS
        assert ids[-1] == 2  # EOS

    def test_padding_inserted(self):
        p = get_phonemizer("en")
        phoneme_id_map = {"_": [0], "^": [1], "$": [2]}
        ids, _ = p.post_process_ids([10, 20], [None, None], phoneme_id_map)
        # BOS(1), pad(0), 10, pad(0), 20, pad(0), EOS(2)
        assert ids == [1, 0, 10, 0, 20, 0, 2]
