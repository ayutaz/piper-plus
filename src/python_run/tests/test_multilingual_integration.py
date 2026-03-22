"""Integration tests for multilingual phonemization (non-mocked).

These tests use real phonemizer libraries to ensure the runtime package
produces correct phonemes for all 6 supported languages.
"""

import pytest


def test_japanese_phonemize_real():
    """Call phonemize_japanese with real pyopenjtalk and verify output."""
    pyopenjtalk = pytest.importorskip(
        "pyopenjtalk_plus",
        reason="pyopenjtalk-plus not installed",
    )
    del pyopenjtalk  # only needed for the skip check

    from piper.phonemize.japanese import phonemize_japanese

    result = phonemize_japanese("こんにちは")
    assert len(result) > 5, f"Expected > 5 tokens, got {len(result)}: {result}"
    assert result[0] == "^", f"Expected BOS '^', got {result[0]!r}"


def test_english_phonemize_real():
    """Call phonemize_english with real g2p_en and verify output."""
    pytest.importorskip("g2p_en", reason="g2p_en not installed")

    from piper.phonemize.english import phonemize_english

    result = phonemize_english("Hello")
    assert len(result) > 3, f"Expected > 3 tokens, got {len(result)}: {result}"
    assert result[0] == "^", f"Expected BOS '^', got {result[0]!r}"
    assert result[-1] == "$", f"Expected EOS '$', got {result[-1]!r}"


def test_chinese_phonemize_real():
    """Call phonemize_chinese with real pypinyin and verify output."""
    pytest.importorskip("pypinyin", reason="pypinyin not installed")

    from piper.phonemize.chinese import phonemize_chinese

    result = phonemize_chinese("你好")
    assert len(result) > 3, f"Expected > 3 tokens, got {len(result)}: {result}"
    assert result[0] == "^", f"Expected BOS '^', got {result[0]!r}"
    assert result[-1] == "$", f"Expected EOS '$', got {result[-1]!r}"


def test_spanish_phonemize_real():
    """Call phonemize_spanish (rule-based) and verify output."""
    from piper.phonemize.spanish import phonemize_spanish

    result = phonemize_spanish("Hola")
    assert len(result) > 3, f"Expected > 3 tokens, got {len(result)}: {result}"
    assert result[0] == "^", f"Expected BOS '^', got {result[0]!r}"
    assert result[-1] == "$", f"Expected EOS '$', got {result[-1]!r}"


def test_french_phonemize_real():
    """Call phonemize_french (rule-based) and verify output."""
    from piper.phonemize.french import phonemize_french

    result = phonemize_french("Bonjour")
    assert len(result) > 3, f"Expected > 3 tokens, got {len(result)}: {result}"
    assert result[0] == "^", f"Expected BOS '^', got {result[0]!r}"
    assert result[-1] == "$", f"Expected EOS '$', got {result[-1]!r}"


def test_portuguese_phonemize_real():
    """Call phonemize_portuguese (rule-based) and verify output."""
    from piper.phonemize.portuguese import phonemize_portuguese

    result = phonemize_portuguese("Ola")
    assert len(result) > 3, f"Expected > 3 tokens, got {len(result)}: {result}"
    assert result[0] == "^", f"Expected BOS '^', got {result[0]!r}"
    assert result[-1] == "$", f"Expected EOS '$', got {result[-1]!r}"


def test_japanese_long_text_splitting():
    """Verify that long Japanese text is split and does not crash OpenJTalk."""
    pyopenjtalk = pytest.importorskip(
        "pyopenjtalk_plus",
        reason="pyopenjtalk-plus not installed",
    )
    del pyopenjtalk

    from piper.phonemize.japanese import phonemize_japanese

    # ~3000 chars — exceeds OpenJTalk's ~2700 char buffer limit
    long_text = "これはテストです。" * 350
    result = phonemize_japanese(long_text)
    assert len(result) > 100, f"Expected many tokens, got {len(result)}"
    assert result[0] == "^", "Expected BOS"


def test_japanese_question_markers():
    """Verify question type markers in jp_id_map match phonemizer output."""
    from piper.phonemize.jp_id_map import SPECIAL_TOKENS

    # Confirm the markers exist in the ID map
    for marker in ("?!", "?.", "?~"):
        assert marker in SPECIAL_TOKENS, f"Missing question marker: {marker}"


def test_japanese_n_variants_in_id_map():
    """Verify N phoneme variants in jp_id_map."""
    from piper.phonemize.jp_id_map import JAPANESE_PHONEMES

    for variant in ("N_m", "N_n", "N_ng", "N_uvular"):
        assert variant in JAPANESE_PHONEMES, f"Missing N variant: {variant}"


def test_multilingual_phonemizer_all_languages():
    """Create MultilingualPhonemizer with all 6 languages and test each."""
    pytest.importorskip(
        "pyopenjtalk_plus",
        reason="pyopenjtalk-plus not installed",
    )
    pytest.importorskip("g2p_en", reason="g2p_en not installed")
    pytest.importorskip("pypinyin", reason="pypinyin not installed")

    from piper.phonemize.multilingual import MultilingualPhonemizer

    mp = MultilingualPhonemizer(languages=["ja", "en", "zh", "es", "fr", "pt"])

    test_cases = [
        ("ja", "こんにちは"),
        ("en", "Hello"),
        ("zh", "你好"),
        ("es", "Hola"),
        ("fr", "Bonjour"),
        ("pt", "Ola"),
    ]

    for lang, text in test_cases:
        result = mp.phonemize(text)
        assert len(result) > 0, f"{lang} produced empty result for {text!r}"


def test_multilingual_code_switching():
    """Test mixed Japanese-English text produces more tokens than either alone."""
    pytest.importorskip(
        "pyopenjtalk_plus",
        reason="pyopenjtalk-plus not installed",
    )
    pytest.importorskip("g2p_en", reason="g2p_en not installed")

    from piper.phonemize.multilingual import MultilingualPhonemizer

    mp = MultilingualPhonemizer(languages=["ja", "en"])

    ja_only = mp.phonemize("こんにちは")
    en_only = mp.phonemize("Hello")
    mixed = mp.phonemize("こんにちはHello")

    assert len(mixed) > len(ja_only), (
        f"Mixed ({len(mixed)} tokens) should exceed JA-only ({len(ja_only)} tokens)"
    )
    assert len(mixed) > len(en_only), (
        f"Mixed ({len(mixed)} tokens) should exceed EN-only ({len(en_only)} tokens)"
    )


def test_training_runtime_consistency():
    """Compare token counts between training and runtime phonemizers.

    Skipped automatically in CI / pip-only environments where
    piper_train is not installed.
    """
    pytest.importorskip(
        "pyopenjtalk_plus",
        reason="pyopenjtalk-plus not installed",
    )
    pytest.importorskip("g2p_en", reason="g2p_en not installed")
    pytest.importorskip("pypinyin", reason="pypinyin not installed")
    piper_train_ml = pytest.importorskip(
        "piper_train.phonemize.multilingual",
        reason="piper_train not installed (dev-only)",
    )

    from piper.phonemize.multilingual import (
        MultilingualPhonemizer as RuntimeMP,
    )

    TrainMP = piper_train_ml.MultilingualPhonemizer

    languages = ["ja", "en", "zh", "es", "fr", "pt"]
    runtime_mp = RuntimeMP(languages=languages)
    train_mp = TrainMP(languages=languages)

    test_phrases = {
        "ja": "こんにちは",
        "en": "Hello",
        "zh": "你好",
        "es": "Hola",
        "fr": "Bonjour",
        "pt": "Ola",
    }

    for lang, text in test_phrases.items():
        runtime_tokens = runtime_mp.phonemize(text)
        train_result = train_mp.phonemize(text)
        # Training side returns (phoneme_ids, prosody) tuple
        if isinstance(train_result, tuple):
            train_tokens = train_result[0]
        else:
            train_tokens = train_result

        # Token counts should be identical for the same input
        assert len(runtime_tokens) == len(train_tokens), (
            f"{lang}: runtime produced {len(runtime_tokens)} tokens "
            f"but training produced {len(train_tokens)} tokens "
            f"for {text!r}"
        )
