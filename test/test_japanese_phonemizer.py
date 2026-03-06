"""Tests for Japanese phonemizer."""

import pytest


def test_basic_phonemize():
    """Test basic Japanese phonemization produces non-empty output."""
    from piper_train.phonemize.japanese import phonemize_japanese

    phonemes = phonemize_japanese("こんにちは")
    assert len(phonemes) > 0, "Should produce non-empty phoneme list"


def test_bos_eos_markers():
    """Test BOS/EOS markers are present."""
    from piper_train.phonemize.japanese import phonemize_japanese
    from piper_train.phonemize.token_mapper import CHAR2TOKEN

    def decode(phonemes):
        return [CHAR2TOKEN.get(p, p) for p in phonemes]

    text = "窓を開ける。"
    phonemes = phonemize_japanese(text)
    decoded = decode(phonemes)
    assert "^" in decoded, "Should have BOS marker"
    assert "$" in decoded, "Should have EOS marker"
    assert "]" in decoded, f"Expected accent nucleus ']' in output: {decoded}"
    assert "[" in decoded, f"Expected rising pitch '[' in output: {decoded}"


def test_n_phoneme_variants():
    """Test context-dependent N phoneme rules produce correct variants."""
    from piper_train.phonemize.japanese import phonemize_japanese
    from piper_train.phonemize.token_mapper import CHAR2TOKEN

    def decode(phonemes):
        return [CHAR2TOKEN.get(p, p) for p in phonemes]

    # N before p -> N_m (bilabial)
    decoded = decode(phonemize_japanese("さんぽ"))
    assert "N_m" in decoded, f"Expected N_m before 'p': {decoded}"

    # N before n -> N_n (alveolar)
    decoded = decode(phonemize_japanese("あんない"))
    assert "N_n" in decoded, f"Expected N_n before 'n': {decoded}"

    # N before k -> N_ng (velar)
    decoded = decode(phonemize_japanese("ぎんこう"))
    assert "N_ng" in decoded, f"Expected N_ng before 'k': {decoded}"

    # N at end -> N_uvular
    decoded = decode(phonemize_japanese("ほん"))
    assert "N_uvular" in decoded, f"Expected N_uvular at end: {decoded}"


def test_phonemize_with_prosody_alignment():
    """Test that phonemize_japanese_with_prosody returns aligned tokens and prosody."""
    from piper_train.phonemize.japanese import phonemize_japanese_with_prosody

    tokens, prosody = phonemize_japanese_with_prosody("今日は天気が良い。")
    assert len(tokens) == len(prosody), (
        f"Token count ({len(tokens)}) != prosody count ({len(prosody)})"
    )
    # BOS/EOS/markers should have None prosody
    from piper_train.phonemize.token_mapper import CHAR2TOKEN
    for tok, pro in zip(tokens, prosody):
        decoded = CHAR2TOKEN.get(tok, tok)
        if decoded in ("^", "$", "_", "#", "[", "]"):
            assert pro is None, f"Special token '{decoded}' should have None prosody"


def test_question_type_markers():
    """Test question type markers from _get_question_type."""
    from piper_train.phonemize.japanese import _get_question_type

    assert _get_question_type("何ですか？") == "?"
    assert _get_question_type("本当?!") == "?!"
    assert _get_question_type("本当！？") == "?!"
    assert _get_question_type("そうなの?.") == "?."
    assert _get_question_type("行くよね?~") == "?~"
    assert _get_question_type("今日は良い天気。") == "$"


def test_id_map_sizes():
    """Test ID map contains expected number of symbols."""
    from piper_train.phonemize.jp_id_map import get_japanese_id_map
    from piper_train.phonemize.bilingual_id_map import get_bilingual_id_map

    ja_map = get_japanese_id_map()
    assert len(ja_map) == 65, f"Expected 65 symbols for JA, got {len(ja_map)}"

    bilingual_map = get_bilingual_id_map()
    assert len(bilingual_map) == 97, f"Expected 97 symbols for JA+EN, got {len(bilingual_map)}"
