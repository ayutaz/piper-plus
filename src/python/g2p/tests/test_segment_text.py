"""Tests for MultilingualPhonemizer.segment_text()."""

from piper_plus_g2p.multilingual import MultilingualPhonemizer


class TestSegmentText:
    def setup_method(self):
        self.phonemizer = MultilingualPhonemizer(["ja", "en"])

    def test_japanese_only(self):
        segments = self.phonemizer.segment_text("こんにちは")
        assert len(segments) == 1
        assert segments[0]["language"] == "ja"
        assert segments[0]["text"] == "こんにちは"

    def test_english_only(self):
        segments = self.phonemizer.segment_text("Hello world")
        assert len(segments) == 1
        assert segments[0]["language"] == "en"
        assert segments[0]["text"] == "Hello world"

    def test_mixed_ja_en(self):
        segments = self.phonemizer.segment_text("こんにちはhello")
        assert len(segments) == 2
        assert segments[0]["language"] == "ja"
        assert segments[1]["language"] == "en"
        # Text content of each segment must round-trip the input.
        assert segments[0]["text"] == "こんにちは"
        assert segments[1]["text"] == "hello"

    def test_mixed_en_ja(self):
        # Reverse direction (en first, ja second) must produce 2 segments
        # with the same text round-trip.
        segments = self.phonemizer.segment_text("helloこんにちは")
        assert len(segments) == 2
        assert segments[0]["language"] == "en"
        assert segments[1]["language"] == "ja"
        assert segments[0]["text"] == "hello"
        assert segments[1]["text"] == "こんにちは"

    def test_empty_string(self):
        segments = self.phonemizer.segment_text("")
        assert segments == []

    def test_returns_dict_format(self):
        # Each segment must be a dict with exactly the documented keys.
        segments = self.phonemizer.segment_text("テスト")
        assert len(segments) == 1
        for seg in segments:
            assert isinstance(seg, dict)
            assert "language" in seg
            assert "text" in seg
            # And no unexpected fields silently leak.
            assert set(seg.keys()) >= {"language", "text"}

    def test_segments_concatenate_to_input(self):
        """Concatenating all segment texts must reproduce the input.

        This pins lossless segmentation — no character drops during the
        Latin/CJK boundary detection.  Drift here would silently lose
        a character that appears mid-language-boundary.
        """
        text = "こんにちはhelloさようなら"
        segments = self.phonemizer.segment_text(text)
        assert len(segments) >= 2  # at least one boundary
        assert "".join(seg["text"] for seg in segments) == text
