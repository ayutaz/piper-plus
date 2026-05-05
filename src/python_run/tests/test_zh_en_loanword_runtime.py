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


def test_phonemize_embedded_english_punctuation_invariant():
    """Trailing punctuation does not change the embedded-english output."""
    _require_pypinyin()
    from piper.phonemize.chinese import _phonemize_embedded_english_raw

    a = _phonemize_embedded_english_raw("GPS")
    b = _phonemize_embedded_english_raw("GPS,")
    c = _phonemize_embedded_english_raw("GPS.")
    assert a == b == c


def test_phonemize_embedded_english_digits_dropped():
    """Digits in letter_fallback path are silently dropped."""
    _require_pypinyin()
    from piper.phonemize.chinese import _phonemize_embedded_english_raw

    a = _phonemize_embedded_english_raw("ZZ")
    b = _phonemize_embedded_english_raw("Z2Z9")
    assert a == b


def test_phonemize_embedded_english_priority_loanword():
    """Loanword (case-sensitive) is preferred over uppercase acronym lookup.

    'Python' (loanword) vs 'PYTHON' (no loanword match, no acronym match
    -> letter_fallback) must produce different sequence lengths.
    """
    _require_pypinyin()
    from piper.phonemize.chinese import _phonemize_embedded_english_raw

    py = _phonemize_embedded_english_raw("Python")
    upper = _phonemize_embedded_english_raw("PYTHON")
    assert py != upper
    assert len(upper) > len(py)


def test_multilingual_punctuation_after_embedded_en():
    """Trailing punctuation in dispatched segment keeps the embedded path."""
    _require_pypinyin()
    from piper.phonemize.multilingual import MultilingualPhonemizer

    p = MultilingualPhonemizer(["zh", "en"], default_latin_language="en")
    a = p.phonemize("请打开 GPS")
    b = p.phonemize("请打开 GPS。")
    # Same non-BOS/EOS content modulo a possible trailing period
    a_inner = [t for t in a if t not in {"^", "$"}]
    b_inner = [t for t in b if t not in {"^", "$"}]
    assert abs(len(a_inner) - len(b_inner)) <= 1


def test_multilingual_two_embedded_en_segments():
    """[zh, en, zh, en, zh] -- both EN segments dispatched to embedded path."""
    _require_pypinyin()
    from piper.phonemize.multilingual import MultilingualPhonemizer

    p = MultilingualPhonemizer(["zh", "en"], default_latin_language="en")
    full = p.phonemize("让我用 ChatGPT 和 Python 写代码")
    assert len(full) > 0


def test_runtime_training_consistency_for_embedded_english():
    """Runtime PUA tokens map back to the same training-side IPA sequence.

    Sanity check: the runtime adds PUA encoding on top of the same IPA
    tokens produced training-side, so decoding the PUA chars back to
    their token names should yield a sequence that contains the same
    tone markers as the training-side path.
    """
    _require_pypinyin()
    pytest.importorskip(
        "piper_plus_g2p", reason="training-side g2p package not installed"
    )
    from piper_plus_g2p.chinese import phonemize_embedded_english as train_fn

    from piper.phonemize.chinese import _phonemize_embedded_english_raw

    train_tokens, _ = train_fn("GPS")
    runtime_tokens = _phonemize_embedded_english_raw("GPS")
    train_tones = sum(1 for t in train_tokens if t.startswith("tone"))
    # Runtime side maps tone tokens to PUA, so count PUA codepoints in the
    # tone range (E046-E04A per pua.json).
    runtime_tones = sum(
        1 for tok in runtime_tokens for ch in tok if 0xE046 <= ord(ch) <= 0xE04A
    )
    assert train_tones == runtime_tones
