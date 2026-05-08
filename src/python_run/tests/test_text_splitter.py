"""Tests for sentence-level text splitter.

Mirrors the Rust test suite in
``src/rust/piper-core/src/streaming.rs`` and the C# test suite in
``src/csharp/PiperPlus.Core.Tests/TextSplitterTests.cs`` to guarantee
cross-runtime byte-for-byte compatibility on the same input.
"""

import time

import pytest

from piper.text_splitter import split_sentences


class TestSplitSentencesBasics:
    @pytest.mark.unit
    def test_japanese(self):
        text = "こんにちは。今日は良い天気ですね。明日も晴れるでしょう。"
        result = split_sentences(text)
        assert result == [
            "こんにちは。",
            "今日は良い天気ですね。",
            "明日も晴れるでしょう。",
        ]

    @pytest.mark.unit
    def test_english(self):
        text = "Hello world. How are you? I am fine!"
        result = split_sentences(text)
        assert result == ["Hello world.", "How are you?", "I am fine!"]

    @pytest.mark.unit
    def test_mixed_punctuation(self):
        text = "日本語のテスト。English test! 混合テスト？"
        result = split_sentences(text)
        assert result == ["日本語のテスト。", "English test!", "混合テスト？"]

    @pytest.mark.unit
    def test_fullwidth_punctuation(self):
        text = "すごい！本当ですか？はい。"
        result = split_sentences(text)
        assert result == ["すごい！", "本当ですか？", "はい。"]

    @pytest.mark.unit
    def test_single_sentence(self):
        result = split_sentences("一つだけ。")
        assert result == ["一つだけ。"]


class TestSplitSentencesEdgeCases:
    @pytest.mark.unit
    def test_empty(self):
        assert split_sentences("") == []

    @pytest.mark.unit
    def test_whitespace_only(self):
        assert split_sentences("   ") == []

    @pytest.mark.unit
    def test_no_terminator(self):
        text = "This has no ending punctuation"
        assert split_sentences(text) == ["This has no ending punctuation"]

    @pytest.mark.unit
    def test_consecutive_terminators(self):
        # Mirrors Rust test_split_sentences_consecutive_terminators.
        # '?' triggers the first split -> "Really?"
        # '!' immediately triggers another split -> "!"
        # " Yes." is the third chunk -> "Yes."
        result = split_sentences("Really?! Yes.")
        assert result == ["Really?", "!", "Yes."]

    @pytest.mark.unit
    def test_single_char_sentence(self):
        result = split_sentences("A. B.")
        assert result == ["A.", "B."]

    @pytest.mark.unit
    def test_newline_separator(self):
        result = split_sentences("Hello.\nWorld.")
        assert result == ["Hello.", "World."]


class TestSplitSentencesClosingPunctuation:
    @pytest.mark.unit
    def test_japanese_closing_brackets(self):
        text = "「こんにちは。」次の文。"
        result = split_sentences(text)
        assert result == ["「こんにちは。」", "次の文。"]

    @pytest.mark.unit
    def test_right_double_quote(self):
        # U+201C / U+201D: "Hello." should stay attached to the first chunk.
        text = "She said “Hello.” Then left."
        result = split_sentences(text)
        assert result == ["She said “Hello.”", "Then left."]

    @pytest.mark.unit
    def test_right_single_quote(self):
        # U+2018 / U+2019: 'Hi.' should stay attached to the first chunk.
        text = "She said ‘Hi.’ Then left."
        result = split_sentences(text)
        assert result == ["She said ‘Hi.’", "Then left."]

    @pytest.mark.unit
    def test_guillemet(self):
        # U+00AB / U+00BB: «Bonjour.» should stay attached.
        text = "Il a dit «Bonjour.» Ensuite."
        result = split_sentences(text)
        assert result == ["Il a dit «Bonjour.»", "Ensuite."]

    @pytest.mark.unit
    def test_double_byte_close_paren(self):
        text = "（注意。）次の文。"
        result = split_sentences(text)
        assert result == ["（注意。）", "次の文。"]


class TestSplitSentencesShortText:
    """Short-text inputs that previously broke under Strategy A."""

    @pytest.mark.unit
    def test_konnichiwa(self):
        # Issue #356 reference text — the streaming target.
        result = split_sentences("こんにちは。")
        assert result == ["こんにちは。"]

    @pytest.mark.unit
    def test_two_short_sentences(self):
        result = split_sentences("はい。いいえ。")
        assert result == ["はい。", "いいえ。"]


class TestSplitSentencesContractCompliance:
    """Verify alignment with docs/spec/text-splitter-contract.toml."""

    @pytest.mark.unit
    def test_fullwidth_full_stop_terminator(self):
        # U+FF0E (．) is listed in the canonical contract terminators set.
        result = split_sentences("テスト．次の文．")
        assert result == ["テスト．", "次の文．"]

    @pytest.mark.unit
    def test_fullwidth_full_stop_with_closing_bracket(self):
        result = split_sentences("「やった．」次の文．")
        assert result == ["「やった．」", "次の文．"]


class TestSplitSentencesNewlineHandling:
    """Pin behavior for newline / whitespace edge cases.

    The contract (``docs/spec/text-splitter-contract.toml``) does not enumerate
    which whitespace characters act as inter-sentence separators. The Python
    implementation relies on :py:meth:`str.isspace` after a sentence
    terminator, which covers ``\\n``, ``\\r``, ``\\t``, U+2028 (LINE
    SEPARATOR) and U+2029 (PARAGRAPH SEPARATOR). These tests pin that
    behavior so future refactors do not silently regress.

    Crucially, none of these whitespace characters are themselves sentence
    *terminators* — they only separate already-terminated chunks. Whitespace
    appearing inside an un-terminated run remains inline (no split).
    """

    @pytest.mark.unit
    def test_crlf_separator(self):
        # Windows-style line endings: ``\r\n`` between two terminated
        # sentences should produce two clean chunks (no embedded \r or \n).
        result = split_sentences("A.\r\nB.")
        assert result == ["A.", "B."]

    @pytest.mark.unit
    def test_cr_only_separator(self):
        # Classic-Mac-style ``\r`` is whitespace per ``str.isspace`` and is
        # consumed after a terminator, yielding two chunks.
        result = split_sentences("A.\rB.")
        assert result == ["A.", "B."]

    @pytest.mark.unit
    def test_unicode_line_separator_u2028(self):
        # U+2028 LINE SEPARATOR is whitespace per Python — consumed as
        # post-terminator whitespace, yielding two chunks with no inline
        # separator surviving in either chunk.
        result = split_sentences("A. B.")
        assert result == ["A.", "B."]

    @pytest.mark.unit
    def test_unicode_paragraph_separator_u2029(self):
        # U+2029 PARAGRAPH SEPARATOR — same treatment as U+2028.
        result = split_sentences("A. B.")
        assert result == ["A.", "B."]

    @pytest.mark.unit
    def test_mixed_lf_crlf(self):
        # Mixing ``\n`` and ``\r\n`` between terminated sentences must still
        # yield exactly three chunks with no surviving newline characters.
        result = split_sentences("A.\nB.\r\nC.")
        assert result == ["A.", "B.", "C."]

    @pytest.mark.unit
    def test_tab_only_separation(self):
        # Tab is whitespace per ``str.isspace``. After a terminator it is
        # consumed as inter-sentence whitespace, producing two chunks.
        result = split_sentences("A.\tB.")
        assert result == ["A.", "B."]

    @pytest.mark.unit
    def test_inline_newline_without_terminator(self):
        # No terminator means no split, regardless of embedded whitespace.
        # ``\n`` here must remain inline in the single emitted chunk.
        result = split_sentences("A\nB")
        assert result == ["A\nB"]

    @pytest.mark.unit
    def test_inline_u2028_without_terminator(self):
        # U+2028 inside an un-terminated run stays inline (1 chunk).
        result = split_sentences("A B")
        assert result == ["A B"]


class TestSplitSentencesAdditionalEdgeCases:
    """Behavior pinning for runs of consecutive terminators and huge inputs."""

    @pytest.mark.unit
    def test_consecutive_terminators_bang_q_bang(self):
        # "!?!" — each terminator triggers an independent split: 3 chunks.
        result = split_sentences("!?!")
        assert result == ["!", "?", "!"]

    @pytest.mark.unit
    def test_consecutive_terminators_double_q(self):
        # "??" — two terminators, two chunks.
        result = split_sentences("??")
        assert result == ["?", "?"]

    @pytest.mark.unit
    def test_consecutive_terminators_double_period(self):
        # ".." — two terminators, two chunks.
        result = split_sentences("..")
        assert result == [".", "."]

    @pytest.mark.unit
    def test_huge_input_no_crash(self):
        # ~1.3 MB input must complete quickly (no pathological backtracking
        # — the splitter is a single linear pass). 5s is a generous ceiling.
        text = "Hello world. " * 100_000
        start = time.monotonic()
        result = split_sentences(text)
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"split_sentences took {elapsed:.2f}s on 1MB+ input"
        assert len(result) == 100_000
        assert result[0] == "Hello world."
        assert result[-1] == "Hello world."
