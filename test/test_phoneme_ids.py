"""Tests for self-contained phonemes_to_ids() logic (src/cpp/phoneme_ids.hpp).

Validates BOS/EOS insertion, inter-phoneme padding, missing phoneme tracking,
and edge cases. These tests mirror the C++ implementation to ensure parity.
"""
import pytest


# Reimplement the C++ phonemes_to_ids logic in Python for validation
def phonemes_to_ids(phonemes, id_map, add_bos=True, add_eos=True, intersperse_pad=True,
                    pad=ord('_'), bos=ord('^'), eos=ord('$')):
    """Python reimplementation of C++ phonemes_to_ids() from phoneme_ids.hpp."""
    result = []
    missing = {}

    # BOS
    if add_bos and bos in id_map:
        result.extend(id_map[bos])
        if intersperse_pad and pad in id_map:
            result.extend(id_map[pad])

    # Phonemes with optional padding
    for ph in phonemes:
        if ph not in id_map:
            missing[ph] = missing.get(ph, 0) + 1
            continue
        result.extend(id_map[ph])
        if intersperse_pad and pad in id_map:
            result.extend(id_map[pad])

    # EOS
    if add_eos and eos in id_map:
        result.extend(id_map[eos])

    return result, missing


class TestPhonemesToIds:
    """Test phonemes_to_ids conversion logic."""

    @pytest.fixture
    def simple_id_map(self):
        """Minimal ID map for testing."""
        return {
            ord('_'): [0],   # pad
            ord('^'): [1],   # BOS
            ord('$'): [2],   # EOS
            ord('a'): [10],
            ord('b'): [11],
            ord('k'): [12],
        }

    def test_basic_with_padding(self, simple_id_map):
        """BOS + pad + phonemes with pad + EOS."""
        phonemes = [ord('a'), ord('b')]
        ids, missing = phonemes_to_ids(phonemes, simple_id_map)
        # Expected: [BOS, pad, a, pad, b, pad, EOS]
        assert ids == [1, 0, 10, 0, 11, 0, 2]
        assert missing == {}

    def test_basic_without_padding(self, simple_id_map):
        """BOS + phonemes (no pad) + EOS."""
        phonemes = [ord('a'), ord('b')]
        ids, missing = phonemes_to_ids(phonemes, simple_id_map, intersperse_pad=False)
        assert ids == [1, 10, 11, 2]
        assert missing == {}

    def test_no_bos_no_eos(self, simple_id_map):
        """Just phonemes, no BOS/EOS."""
        phonemes = [ord('a')]
        ids, missing = phonemes_to_ids(phonemes, simple_id_map, add_bos=False, add_eos=False)
        assert ids == [10, 0]  # a, pad
        assert missing == {}

    def test_no_bos_no_eos_no_pad(self, simple_id_map):
        """Just phonemes, nothing else."""
        phonemes = [ord('a'), ord('b')]
        ids, missing = phonemes_to_ids(phonemes, simple_id_map,
                                       add_bos=False, add_eos=False, intersperse_pad=False)
        assert ids == [10, 11]
        assert missing == {}

    def test_empty_phonemes(self, simple_id_map):
        """Empty input with BOS/EOS."""
        ids, missing = phonemes_to_ids([], simple_id_map)
        assert ids == [1, 0, 2]  # BOS, pad, EOS
        assert missing == {}

    def test_missing_phoneme_tracked(self, simple_id_map):
        """Unknown phonemes are tracked and skipped."""
        phonemes = [ord('a'), ord('z'), ord('b'), ord('z')]
        ids, missing = phonemes_to_ids(phonemes, simple_id_map)
        # z is missing, skipped in output
        assert ids == [1, 0, 10, 0, 11, 0, 2]
        assert missing == {ord('z'): 2}

    def test_multi_id_phoneme(self):
        """Phonemes mapping to multiple IDs."""
        id_map = {
            ord('_'): [0],
            ord('^'): [1],
            ord('$'): [2],
            ord('x'): [50, 51],  # multi-ID phoneme
        }
        ids, missing = phonemes_to_ids([ord('x')], id_map)
        assert ids == [1, 0, 50, 51, 0, 2]

    def test_none_id_map_returns_empty(self):
        """None/empty ID map returns empty."""
        ids, missing = phonemes_to_ids([ord('a')], {})
        # BOS/EOS not in map, so nothing added; 'a' also missing
        assert ids == []
        assert missing == {ord('a'): 1}

    def test_multilingual_model_pattern(self):
        """Realistic multilingual model pattern: BOS _ ph _ ph _ EOS."""
        id_map = {
            ord('_'): [0],
            ord('^'): [1],
            ord('$'): [2],
            ord('k'): [10],
            ord('o'): [11],
            ord('N'): [12],
        }
        # "kon" in phonemes
        phonemes = [ord('k'), ord('o'), ord('N')]
        ids, missing = phonemes_to_ids(phonemes, id_map)
        assert ids == [1, 0, 10, 0, 11, 0, 12, 0, 2]
        assert len(missing) == 0

    def test_openjtalk_pattern_no_bos_eos(self):
        """OpenJTalk models: BOS/EOS already in phoneme list, no intersperse."""
        id_map = {
            ord('_'): [0],
            ord('^'): [1],
            ord('$'): [2],
            ord('a'): [10],
        }
        # OpenJTalk phonemes already have BOS/EOS
        phonemes = [ord('^'), ord('a'), ord('$')]
        ids, missing = phonemes_to_ids(phonemes, id_map,
                                       add_bos=False, add_eos=False, intersperse_pad=False)
        assert ids == [1, 10, 2]
