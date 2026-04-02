"""Tests for piper_plus_g2p.encode — PUA mapping, ID maps, and PiperEncoder."""

import pytest

from piper_plus_g2p.encode.encoder import PiperEncoder
from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
from piper_plus_g2p.encode.pua import FIXED_PUA_MAPPING, map_token
from tests.conftest import requires_ja


class TestPUAMapping:
    def test_pua_mapping_count(self):
        """FIXED_PUA_MAPPING has exactly 96 entries."""
        assert len(FIXED_PUA_MAPPING) == 96

    def test_pua_single_char_passthrough(self):
        """Single-character tokens pass through map_token unchanged."""
        assert map_token("a") == "a"
        assert map_token("k") == "k"
        assert map_token("#") == "#"

    def test_pua_multi_char_mapping(self):
        """Multi-character token 'ch' maps to U+E00E."""
        result = map_token("ch")
        assert result == chr(0xE00E)


class TestJAIDMap:
    def test_ja_id_map_format(self):
        """JA id map is a dict with '_', '^', '$' keys present."""
        id_map = get_phoneme_id_map("ja")
        assert isinstance(id_map, dict)
        # These are PUA-mapped single chars, so look up the mapped keys
        # '_' is 1 char -> passthrough
        assert "_" in id_map, "'_' (pause/pad) must be in id map"
        assert "^" in id_map, "'^' (BOS) must be in id map"
        assert "$" in id_map, "'$' (EOS) must be in id map"

    @requires_ja
    def test_ja_id_map_has_correct_size(self):
        """JA id map should have 65 symbols (10 special + 55 phonemes)."""
        g2p_map = get_phoneme_id_map("ja")
        assert len(g2p_map) == 65

    def test_en_id_map_raises(self):
        """get_phoneme_id_map('en') raises ValueError (not built-in)."""
        with pytest.raises(ValueError, match="No built-in"):
            get_phoneme_id_map("en")


class TestPiperEncoder:
    def test_bos_eos_insertion(self):
        """Encoded result starts with BOS id and ends with EOS id."""
        id_map = get_phoneme_id_map("ja")
        enc = PiperEncoder(id_map)

        bos_id = id_map["^"][0]
        eos_id = id_map["$"][0]

        # Minimal token list: just a single vowel
        ids = enc.encode(["a"])
        assert ids[0] == bos_id, f"First id should be BOS ({bos_id}), got {ids[0]}"
        assert ids[-1] == eos_id, f"Last id should be EOS ({eos_id}), got {ids[-1]}"

    def test_inter_phoneme_padding(self):
        """Pad (ID=0) is inserted between phoneme IDs."""
        id_map = get_phoneme_id_map("ja")
        enc = PiperEncoder(id_map)
        pad_id = id_map["_"][0]  # should be 0

        ids = enc.encode(["a", "i"])
        # After BOS+pad, we expect: a, pad, i, pad, EOS
        # Check that pad_id appears in the middle
        assert pad_id in ids[2:-1], "Pad ID should appear between phonemes"

    def test_custom_eos_token(self):
        """eos_token parameter changes which EOS symbol is used."""
        id_map = get_phoneme_id_map("ja")
        enc = PiperEncoder(id_map)

        q_id = id_map["?"][0]
        ids = enc.encode(["a"], eos_token="?")
        assert ids[-1] == q_id, f"Last id should be '?' ({q_id}), got {ids[-1]}"

    def test_encode_with_prosody(self):
        """encode_with_prosody returns (phoneme_ids, prosody_features) tuple."""
        from piper_plus_g2p.base import ProsodyInfo

        id_map = get_phoneme_id_map("ja")
        enc = PiperEncoder(id_map)

        tokens = ["a", "i"]
        prosody = [ProsodyInfo(a1=-2, a2=1, a3=3), ProsodyInfo(a1=0, a2=2, a3=3)]
        ids, prosody_out = enc.encode_with_prosody(tokens, prosody)

        assert isinstance(ids, list)
        assert isinstance(prosody_out, list)
        assert len(ids) == len(prosody_out)
        # At least some entries should be ProsodyInfo with a1/a2/a3
        infos = [p for p in prosody_out if p is not None]
        assert len(infos) > 0
        assert isinstance(infos[0], ProsodyInfo)
        assert hasattr(infos[0], "a1")
        assert hasattr(infos[0], "a2")
        assert hasattr(infos[0], "a3")
