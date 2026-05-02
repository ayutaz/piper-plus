"""Tests for sentence-level text splitter.

Mirrors the Rust test suite in
``src/rust/piper-core/src/streaming.rs`` and the C# test suite in
``src/csharp/PiperPlus.Core.Tests/TextSplitterTests.cs`` to guarantee
cross-runtime byte-for-byte compatibility on the same input.
"""

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
