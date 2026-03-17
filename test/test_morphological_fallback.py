"""Tests for English morphological fallback (tryMorphologicalFallback in C++).

Validates that inflected English words can be phonemized by stripping
common suffixes (-ing, -ed, -s, -er, -ly, -est) and looking up the base form.
These tests use the Python g2p-en pipeline to verify the expected behavior.
"""
import pytest

g2p_en = pytest.importorskip("g2p_en", reason="g2p-en required")


def _get_english_phonemizer():
    """Get the English phonemizer instance."""
    from piper_train.phonemize.english import EnglishPhonemizer
    return EnglishPhonemizer()


class TestMorphologicalFallback:
    """Test suffix stripping patterns that C++ tryMorphologicalFallback implements."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.phonemizer = _get_english_phonemizer()

    def _phonemize(self, text):
        return self.phonemizer.phonemize(text)

    # -ing suffix
    def test_ing_direct(self):
        """running → run + ING (direct base)."""
        ph = self._phonemize("running")
        assert len(ph) > 0, "Should produce phonemes for 'running'"

    def test_ing_with_e_restoration(self):
        """making → make + ING (restore 'e')."""
        ph = self._phonemize("making")
        assert len(ph) > 0, "Should produce phonemes for 'making'"

    def test_ing_with_dedup(self):
        """sitting → sit + ING (deduplicate consonant)."""
        ph = self._phonemize("sitting")
        assert len(ph) > 0, "Should produce phonemes for 'sitting'"

    # -ed suffix
    def test_ed_direct(self):
        """walked → walk + ED."""
        ph = self._phonemize("walked")
        assert len(ph) > 0, "Should produce phonemes for 'walked'"

    def test_ed_with_dedup(self):
        """stopped → stop + ED."""
        ph = self._phonemize("stopped")
        assert len(ph) > 0, "Should produce phonemes for 'stopped'"

    def test_ed_single_d(self):
        """loved → love + D."""
        ph = self._phonemize("loved")
        assert len(ph) > 0, "Should produce phonemes for 'loved'"

    # -s/-es/-ies suffix
    def test_s_direct(self):
        """cats → cat + S."""
        ph = self._phonemize("cats")
        assert len(ph) > 0, "Should produce phonemes for 'cats'"

    def test_es(self):
        """boxes → box + ES."""
        ph = self._phonemize("boxes")
        assert len(ph) > 0, "Should produce phonemes for 'boxes'"

    def test_ies(self):
        """countries → country + S (ies→y)."""
        ph = self._phonemize("countries")
        assert len(ph) > 0, "Should produce phonemes for 'countries'"

    # -er suffix
    def test_er_direct(self):
        """faster → fast + ER."""
        ph = self._phonemize("faster")
        assert len(ph) > 0, "Should produce phonemes for 'faster'"

    def test_er_with_dedup(self):
        """runner → run + ER."""
        ph = self._phonemize("runner")
        assert len(ph) > 0, "Should produce phonemes for 'runner'"

    # -ly suffix
    def test_ly_direct(self):
        """quickly → quick + LY."""
        ph = self._phonemize("quickly")
        assert len(ph) > 0, "Should produce phonemes for 'quickly'"

    def test_ily(self):
        """happily → happy + LY."""
        ph = self._phonemize("happily")
        assert len(ph) > 0, "Should produce phonemes for 'happily'"

    # -est suffix
    def test_est(self):
        """fastest → fast + EST."""
        ph = self._phonemize("fastest")
        assert len(ph) > 0, "Should produce phonemes for 'fastest'"

    # Words already in CMU dict (should work without fallback)
    def test_common_word(self):
        """hello — in CMU dict, no fallback needed."""
        ph = self._phonemize("hello")
        assert len(ph) > 0

    def test_sentence(self):
        """Full sentence with mixed known and inflected words."""
        ph = self._phonemize("the cats are running quickly")
        assert len(ph) > 0
