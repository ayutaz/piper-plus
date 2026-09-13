"""Phase 0: Hindi phoneme inventory is append-only on the multilingual map."""

from __future__ import annotations

import pytest

from piper_plus_g2p.encode.id_maps import (
    _HINDI_PHONEMES,
    get_phoneme_id_map,
)
from piper_plus_g2p.encode.pua import FIXED_PUA_MAPPING, map_token


@pytest.mark.unit
def test_hindi_phonemes_not_empty():
    assert len(_HINDI_PHONEMES) == 17


@pytest.mark.unit
def test_hindi_new_ids_start_at_185():
    id_map = get_phoneme_id_map("hi")
    assert len(id_map) == 202
    mapped_retroflex = map_token("ɽ", strict=True)
    assert id_map[mapped_retroflex] == [185]


@pytest.mark.unit
def test_prefix_185_unchanged_vs_multilingual_without_hi_collision():
    """First 185 ids are the pre-Hindi (8lang) inventory; Hindi only appends."""
    id_map = get_phoneme_id_map("multilingual")
    by_id = {ids[0]: symbol for symbol, ids in id_map.items()}
    assert 184 in by_id
    assert 185 in by_id
    assert by_id[185] == "ɽ"


@pytest.mark.unit
def test_hindi_pua_range():
    expected = {
        "t̪": 0xE065,
        "d̪": 0xE066,
        "t̪ʰ": 0xE067,
        "d̪ʱ": 0xE068,
        "ʈʰ": 0xE069,
        "ɖʱ": 0xE06A,
        "bʱ": 0xE06B,
        "dʱ": 0xE06C,
        "gʱ": 0xE06D,
        "tʃʰ": 0xE06E,
        "dʒʱ": 0xE06F,
        "ɽʱ": 0xE070,
        "ə̃": 0xE071,
        "q_uvular": 0xE072,
    }
    for token, codepoint in expected.items():
        assert FIXED_PUA_MAPPING[token] == codepoint, token


@pytest.mark.unit
def test_q_uvular_not_japanese_geminate():
    id_map = get_phoneme_id_map("multilingual")
    ja_q = map_token("q", strict=True)
    hi_q = map_token("q_uvular", strict=True)
    assert ja_q != hi_q
    assert id_map[ja_q][0] < 185
    assert id_map[hi_q][0] >= 185


@pytest.mark.unit
def test_single_codepoint_hindi_phones_need_no_pua():
    for phone in ("ɽ", "ʋ", "ɦ"):
        assert len(phone) == 1
        assert phone not in FIXED_PUA_MAPPING
        assert map_token(phone, strict=True) == phone
