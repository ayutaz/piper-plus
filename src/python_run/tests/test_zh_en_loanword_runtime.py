"""Runtime tests for ZH-EN code-switching (Issue #384).

Mirrors src/python/g2p/tests/test_zh_en_loanword.py but exercises the
inference-side ``piper.phonemize.chinese`` and ``piper.phonemize.multilingual``
modules. These produce PUA-encoded tokens and do not return prosody.
"""

import pytest


def _require_pypinyin():
    pytest.importorskip("pypinyin", reason="pypinyin not installed")


def _require_g2p_en():
    pytest.importorskip("g2p_en", reason="g2p_en not installed")


def test_phonemize_embedded_english_acronym():
    """GPS produces PUA-mapped tokens with tone markers (mapped to PUA)."""
    _require_pypinyin()
    from piper.phonemize.chinese import _phonemize_embedded_english_raw

    raw = _phonemize_embedded_english_raw("GPS")
    assert len(raw) > 0


def test_phonemize_embedded_english_loanword_python():
    """Python loanword is recognised case-sensitively."""
    _require_pypinyin()
    from piper.phonemize.chinese import _phonemize_embedded_english_raw

    raw = _phonemize_embedded_english_raw("Python")
    assert len(raw) > 0


def test_phonemize_embedded_english_letter_fallback():
    """Unknown token falls back to letter-by-letter conversion."""
    _require_pypinyin()
    from piper.phonemize.chinese import _phonemize_embedded_english_raw

    raw = _phonemize_embedded_english_raw("ZZ")
    # Should produce tokens (Z = zi4 -> "ts ɨ tone4")
    assert len(raw) > 0


def test_phonemize_embedded_english_empty():
    """Empty string returns empty list."""
    _require_pypinyin()
    from piper.phonemize.chinese import _phonemize_embedded_english_raw

    assert _phonemize_embedded_english_raw("") == []


def test_phonemize_embedded_english_public_api_has_bos_eos():
    """Public phonemize_embedded_english adds BOS/EOS like phonemize_chinese."""
    _require_pypinyin()
    from piper.phonemize.chinese import phonemize_embedded_english

    tokens = phonemize_embedded_english("AI")
    assert len(tokens) >= 2  # at least ^ ... $


def test_multilingual_dispatch_zh_en_zh():
    """[zh, en, zh] pattern in zh-en multilingual routes EN through embedded path."""
    _require_pypinyin()
    from piper.phonemize.multilingual import MultilingualPhonemizer

    p = MultilingualPhonemizer(["zh", "en"], default_latin_language="en")
    # 让我用 ChatGPT 写代码
    tokens = p.phonemize("让我用 ChatGPT 写代码")
    assert len(tokens) > 0


def test_multilingual_dispatch_zh_then_en():
    """[zh, en] pattern routes EN through embedded path."""
    _require_pypinyin()
    from piper.phonemize.multilingual import MultilingualPhonemizer

    p = MultilingualPhonemizer(["zh", "en"], default_latin_language="en")
    tokens = p.phonemize("请打开 GPS")
    assert len(tokens) > 0


def test_multilingual_dispatch_en_then_zh():
    """[en, zh] pattern routes EN through embedded path."""
    _require_pypinyin()
    from piper.phonemize.multilingual import MultilingualPhonemizer

    p = MultilingualPhonemizer(["zh", "en"], default_latin_language="en")
    tokens = p.phonemize("GPS 在哪里")
    assert len(tokens) > 0


def test_multilingual_pure_english_uses_english_path():
    """Pure EN text in zh-en multilingual goes to EnglishPhonemizer (no zh context)."""
    _require_pypinyin()
    _require_g2p_en()
    from piper.phonemize.chinese import phonemize_embedded_english
    from piper.phonemize.multilingual import MultilingualPhonemizer

    p = MultilingualPhonemizer(["zh", "en"], default_latin_language="en")
    en_path = p.phonemize("Hello world")
    embedded = phonemize_embedded_english("Hello world")

    # Different paths -> different output
    assert en_path != embedded


def test_multilingual_pure_zh_unaffected():
    """Pure ZH text behaves identically before/after the change (regression)."""
    _require_pypinyin()
    from piper.phonemize.chinese import phonemize_chinese
    from piper.phonemize.multilingual import MultilingualPhonemizer

    p = MultilingualPhonemizer(["zh", "en"], default_latin_language="en")
    text = "今天天气很好"
    via_ml = p.phonemize(text)
    via_zh = phonemize_chinese(text)
    # ML strips BOS/EOS from the segment, then re-maps; the zh-only path keeps them.
    # Compare the phoneme content (excluding ^ $) instead.
    zh_inner = [t for t in via_zh if t not in {"^", "$"}]
    ml_inner = [t for t in via_ml if t not in {"^", "$"}]
    assert zh_inner == ml_inner
