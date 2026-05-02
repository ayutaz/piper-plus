"""Integration tests for PiperVoice streaming synthesis.

Verifies that ``synthesize_stream_raw()`` yields one audio chunk per
sentence after the text-splitter integration. Mocks the ONNX session
and the ``phonemize`` method so the test does not require a real model
or OpenJTalk.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from piper.config import PhonemeType, PiperConfig
from piper.voice import PiperVoice


def _make_mock_voice(*, sample_rate: int = 22050) -> PiperVoice:
    config = PiperConfig(
        num_symbols=100,
        num_speakers=1,
        sample_rate=sample_rate,
        length_scale=1.0,
        noise_scale=0.667,
        noise_w=0.8,
        phoneme_id_map={
            "_": [0],
            "^": [1],
            "$": [2],
            "a": [10],
            "k": [12],
            "o": [15],
        },
        phoneme_type=PhonemeType.MULTILINGUAL,
    )

    session = MagicMock()

    input_mock = MagicMock()
    input_mock.name = "input"
    input_lengths_mock = MagicMock()
    input_lengths_mock.name = "input_lengths"
    scales_mock = MagicMock()
    scales_mock.name = "scales"
    session.get_inputs.return_value = [input_mock, input_lengths_mock, scales_mock]

    output_mock = MagicMock()
    output_mock.name = "output"
    session.get_outputs.return_value = [output_mock]

    audio_samples = np.zeros((1, 1, sample_rate), dtype=np.float32)
    session.run.return_value = [audio_samples]

    return PiperVoice(session=session, config=config)


class TestSynthesizeStreamRawSentenceSplit:
    """Streaming should yield one chunk per sentence."""

    def test_japanese_three_sentences_yields_three_chunks(self):
        voice = _make_mock_voice()
        # phonemize returns one phoneme list per sentence — emulate the new behaviour.
        voice.phonemize = MagicMock(
            return_value=[["a", "k", "o"], ["k", "o", "a"], ["o", "a", "k"]]
        )

        chunks = list(
            voice.synthesize_stream_raw(
                "こんにちは。今日は良い天気ですね。明日も晴れるでしょう。"
            )
        )
        assert len(chunks) == 3
        assert all(len(c) > 0 for c in chunks)

    def test_english_two_sentences_yields_two_chunks(self):
        voice = _make_mock_voice()
        voice.phonemize = MagicMock(return_value=[["a", "k"], ["o", "k"]])

        chunks = list(voice.synthesize_stream_raw("Hello world. How are you?"))
        assert len(chunks) == 2

    def test_single_sentence_yields_single_chunk(self):
        voice = _make_mock_voice()
        voice.phonemize = MagicMock(return_value=[["a", "k", "o"]])

        chunks = list(voice.synthesize_stream_raw("こんにちは。"))
        assert len(chunks) == 1

    def test_text_without_terminator_yields_single_chunk(self):
        voice = _make_mock_voice()
        voice.phonemize = MagicMock(return_value=[["a", "k", "o"]])

        chunks = list(voice.synthesize_stream_raw("no terminator"))
        assert len(chunks) == 1

    def test_whitespace_only_yields_no_chunks(self):
        # When phonemize returns no sentences, the stream should be empty.
        voice = _make_mock_voice()
        voice.phonemize = MagicMock(return_value=[])

        chunks = list(voice.synthesize_stream_raw("   "))
        assert chunks == []


class TestPhonemizeReturnsPerSentence:
    """``phonemize`` is the layer that performs the sentence split."""

    def _patch_multilingual(self, monkeypatch_target):
        """Replace MultilingualPhonemizer with a recording fake."""
        captured: list[str] = []

        class FakeMP:
            def __init__(self, languages):
                self.languages = languages

            def phonemize(self, sentence: str) -> list[str]:
                captured.append(sentence)
                return [f"ph_{sentence}"]

        from piper.phonemize import multilingual as ml

        original = ml.MultilingualPhonemizer
        ml.MultilingualPhonemizer = FakeMP  # type: ignore[assignment]
        return original, captured

    def _restore_multilingual(self, original):
        from piper.phonemize import multilingual as ml

        ml.MultilingualPhonemizer = original  # type: ignore[assignment]

    def test_japanese_multi_sentence(self):
        voice = _make_mock_voice()
        original, captured = self._patch_multilingual(self)
        try:
            sentences = voice.phonemize("こんにちは。今日は晴れ。")
        finally:
            self._restore_multilingual(original)

        assert len(sentences) == 2
        assert captured == ["こんにちは。", "今日は晴れ。"]

    def test_english_multi_sentence(self):
        voice = _make_mock_voice()
        original, captured = self._patch_multilingual(self)
        try:
            sentences = voice.phonemize("Hello world. How are you?")
        finally:
            self._restore_multilingual(original)

        assert len(sentences) == 2
        assert captured == ["Hello world.", "How are you?"]

    def test_ssml_treated_as_single_unit(self):
        voice = _make_mock_voice()
        original, captured = self._patch_multilingual(self)
        try:
            ssml = "<speak>Hello. How are you?</speak>"
            sentences = voice.phonemize(ssml)
        finally:
            self._restore_multilingual(original)

        assert len(sentences) == 1
        assert captured == [ssml]

    def test_text_without_terminator_returns_single(self):
        voice = _make_mock_voice()
        original, captured = self._patch_multilingual(self)
        try:
            sentences = voice.phonemize("no terminator")
        finally:
            self._restore_multilingual(original)

        assert len(sentences) == 1
        assert captured == ["no terminator"]

    def test_ssml_with_newline_after_speak(self):
        # `<speak\n  lang="ja">...` should NOT be split as plain text — the
        # SSML detector must recognize whitespace after `<speak`.
        voice = _make_mock_voice()
        original, captured = self._patch_multilingual(self)
        try:
            ssml = "<speak\n  lang=\"ja\">Hello. World.</speak>"
            sentences = voice.phonemize(ssml)
        finally:
            self._restore_multilingual(original)

        assert len(sentences) == 1
        assert captured == [ssml]

    def test_ssml_with_tab_after_speak(self):
        voice = _make_mock_voice()
        original, captured = self._patch_multilingual(self)
        try:
            ssml = "<speak\tversion=\"1.0\">Hi.</speak>"
            sentences = voice.phonemize(ssml)
        finally:
            self._restore_multilingual(original)

        assert len(sentences) == 1
        assert captured == [ssml]

    def test_whitespace_only_returns_no_sentences(self):
        # Empty / whitespace-only input must not synthesize a BOS/EOS-only
        # chunk. phonemize() should return an empty list.
        voice = _make_mock_voice()
        original, captured = self._patch_multilingual(self)
        try:
            assert voice.phonemize("") == []
            assert voice.phonemize("   ") == []
            assert voice.phonemize("\n\t  \n") == []
        finally:
            self._restore_multilingual(original)

        assert captured == []
