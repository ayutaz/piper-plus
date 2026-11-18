"""Tests for piper_train.tools.phoneme_aliases (plan §7.5 P0-8, S4 data).

Dropped tokens (space, punctuation, pt ``ã``, es ``ʝ``, fr ``ɥ``) are mapped onto
symbols already in the 185-symbol table, so ``num_symbols`` (and the ONNX size)
does not change.
"""

import copy

import pytest

from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
from piper_plus_g2p.encode.pua import map_token
from piper_train.tools.phoneme_aliases import ALIASES, extend_id_map, remap_row

pytestmark = pytest.mark.unit

ID_MAP = get_phoneme_id_map("ja-en-zh-es-fr-pt")


def _ids(*tokens):
    return [ID_MAP[map_token(t)][0] for t in tokens]


def _row(phonemes, phoneme_ids, prosody, language_id=1):
    return {
        "text": "x",
        "language_id": language_id,
        "phonemes": phonemes,
        "phoneme_ids": phoneme_ids,
        "prosody_features": prosody,
    }


P = {"a1": 0, "a2": 0, "a3": 1}
Q = {"a1": 0, "a2": 2, "a3": 2}


def _old_row():
    # tokens: a ␠ b ,   -> ' ' and ',' dropped by the 185-symbol map
    bos, pad, eos = _ids("^", "_", "$")
    a, b = _ids("ə", "b")
    ids = [bos, pad, a, pad, b, pad, eos]
    pros = [None, None, P, None, Q, None, None]
    return _row(["ə", " ", "b", ","], ids, pros)


def test_extend_id_map_keeps_symbol_count_and_maps_to_existing_ids():
    ext = extend_id_map(ID_MAP)
    assert {v[0] for v in ext.values()} == {v[0] for v in ID_MAP.values()}
    for k, v in ID_MAP.items():
        assert ext[k] == v
    assert ext[" "] == ID_MAP["#"]
    assert ext[","] == ID_MAP["_"]
    assert ext["ã"] == ID_MAP[map_token("ɐ̃")]
    assert all(len(k) == 1 for k in ext)


def test_aliases_only_cover_tokens_missing_from_table():
    for raw in ALIASES:
        assert map_token(raw) not in ID_MAP


def test_remap_with_original_map_is_identity():
    row = _old_row()
    assert remap_row(copy.deepcopy(row), ID_MAP, ID_MAP) == row


def test_remap_inserts_boundary_and_pause_with_null_prosody():
    out = remap_row(_old_row(), ID_MAP, extend_id_map(ID_MAP))
    bos, pad, eos, hsh = _ids("^", "_", "$", "#")
    a, b = _ids("ə", "b")
    assert out["phoneme_ids"] == [bos, pad, a, pad, hsh, pad, b, pad, pad, eos]
    assert out["prosody_features"] == [None, None, P, None, None, None, Q, None, None, None]


def test_remap_keeps_final_question_mark_as_eos():
    # English rows ending in '?' use it as the EOS: no pad after it and no '$'
    bos, pad, q, hsh = _ids("^", "_", "?", "#")
    a, b = _ids("ə", "b")
    row = _row(["ə", " ", "b", "?"], [bos, pad, a, pad, b, pad, q], [None, None, P, None, Q, None, None])
    out = remap_row(row, ID_MAP, extend_id_map(ID_MAP))
    assert out["phoneme_ids"] == [bos, pad, a, pad, hsh, pad, b, pad, q]
    assert out["prosody_features"] == [None, None, P, None, None, None, Q, None, None]


def test_japanese_row_without_phonemes_is_untouched():
    row = _row([], [1, 0, 20, 0, 2], [None, None, P, None, None], language_id=0)
    assert remap_row(copy.deepcopy(row), ID_MAP, extend_id_map(ID_MAP)) == row


def test_remap_rejects_rows_that_do_not_match_the_original_map():
    row = _old_row()
    row["phoneme_ids"] = row["phoneme_ids"][:-2] + row["phoneme_ids"][-1:]
    with pytest.raises(ValueError):
        remap_row(row, ID_MAP, extend_id_map(ID_MAP))
