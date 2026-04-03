"""Tests for MultilingualPhonemizer.segment_text()."""

from piper_plus_g2p.multilingual import MultilingualPhonemizer


class TestSegmentText:
    def setup_method(self):
        self.phonemizer = MultilingualPhonemizer(["ja", "en"])

    def test_japanese_only(self):
        segments = self.phonemizer.segment_text("こんにちは")
        assert len(segments) >= 1
        assert segments[0]["language"] == "ja"

    def test_english_only(self):
        segments = self.phonemizer.segment_text("Hello world")
        assert len(segments) >= 1
        assert segments[0]["language"] == "en"

    def test_mixed_ja_en(self):
        segments = self.phonemizer.segment_text("こんにちはhello")
        assert len(segments) == 2
        assert segments[0]["language"] == "ja"
        assert segments[1]["language"] == "en"

    def test_empty_string(self):
        segments = self.phonemizer.segment_text("")
        assert segments == []

    def test_returns_dict_format(self):
        segments = self.phonemizer.segment_text("テスト")
        for seg in segments:
            assert "language" in seg
            assert "text" in seg
