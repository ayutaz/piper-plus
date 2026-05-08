"""Drift gate for prepare_multilingual_dataset.LANGUAGE_ID_MAP / ALL_LANGUAGES.

These constants are load-bearing: they must stay in lock-step with the trained
model's `language_id_map` config. Reordering or renumbering silently breaks
emb_lang lookups in already-trained checkpoints, so any change must be a
deliberate, reviewed code edit — not a refactor side-effect.
"""

import pytest

pytest.importorskip("torch")

from piper_train.tools.prepare_multilingual_dataset import (  # noqa: E402
    ALL_LANGUAGES,
    LANGUAGE_ID_MAP,
)


@pytest.mark.unit
class TestLanguageIdMap:
    def test_language_id_map_has_seven_languages(self):
        assert len(LANGUAGE_ID_MAP) == 7

    def test_language_id_map_ja_is_zero(self):
        assert LANGUAGE_ID_MAP["ja"] == 0

    def test_language_id_map_en_is_one(self):
        assert LANGUAGE_ID_MAP["en"] == 1

    def test_language_id_map_zh_is_two(self):
        assert LANGUAGE_ID_MAP["zh"] == 2

    def test_language_id_map_es_is_three(self):
        assert LANGUAGE_ID_MAP["es"] == 3

    def test_language_id_map_fr_is_four(self):
        assert LANGUAGE_ID_MAP["fr"] == 4

    def test_language_id_map_pt_is_five(self):
        assert LANGUAGE_ID_MAP["pt"] == 5

    def test_language_id_map_sv_is_six(self):
        assert LANGUAGE_ID_MAP["sv"] == 6

    def test_language_id_map_keys_are_lowercase(self):
        for key in LANGUAGE_ID_MAP:
            assert key == key.lower()
            assert isinstance(key, str)

    def test_language_id_map_values_are_consecutive_from_zero(self):
        values = sorted(LANGUAGE_ID_MAP.values())
        assert values == list(range(len(LANGUAGE_ID_MAP)))

    def test_language_id_map_values_are_unique(self):
        values = list(LANGUAGE_ID_MAP.values())
        assert len(values) == len(set(values))

    def test_language_id_map_exact_snapshot(self):
        assert LANGUAGE_ID_MAP == {
            "ja": 0,
            "en": 1,
            "zh": 2,
            "es": 3,
            "fr": 4,
            "pt": 5,
            "sv": 6,
        }


@pytest.mark.unit
class TestAllLanguages:
    def test_all_languages_matches_map_keys(self):
        assert set(ALL_LANGUAGES) == set(LANGUAGE_ID_MAP.keys())

    def test_all_languages_ordered_by_id(self):
        ordered_by_id = sorted(LANGUAGE_ID_MAP.keys(), key=lambda k: LANGUAGE_ID_MAP[k])
        assert ALL_LANGUAGES == ordered_by_id

    def test_all_languages_exact_snapshot(self):
        assert ALL_LANGUAGES == ["ja", "en", "zh", "es", "fr", "pt", "sv"]
