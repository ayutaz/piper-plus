"""Tests for piper_plus_g2p.encode — PUA mapping, ID maps, and PiperEncoder."""

import json
import warnings
from pathlib import Path

import pytest

from piper_plus_g2p.encode.encoder import PiperEncoder
from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
from piper_plus_g2p.encode.pua import (
    CHAR2TOKEN,
    FIXED_PUA_MAPPING,
    TOKEN2CHAR,
    map_token,
)
from tests.conftest import requires_ja

# Path to the cross-platform fixture
_FIXTURE_PATH = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "g2p"
    / "phoneme_test_cases.json"
)


def _load_pua_spot_checks() -> list[dict]:
    """Load pua_spot_checks from the cross-platform fixture."""
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["pua_spot_checks"]


class TestPUAMapping:
    def test_pua_mapping_count(self):
        """FIXED_PUA_MAPPING has exactly 99 entries."""
        assert len(FIXED_PUA_MAPPING) == 99

    def test_pua_single_char_passthrough(self):
        """Single-character tokens pass through map_token unchanged."""
        assert map_token("a") == "a"
        assert map_token("k") == "k"
        assert map_token("#") == "#"

    def test_pua_multi_char_mapping(self):
        """Multi-character token 'ch' maps to U+E00E."""
        result = map_token("ch")
        assert result == chr(0xE00E)


class TestPUAAllEntries:
    """Verify every entry in FIXED_PUA_MAPPING via map_token round-trip."""

    @pytest.mark.parametrize(
        "token,codepoint",
        list(FIXED_PUA_MAPPING.items()),
        ids=[t for t in FIXED_PUA_MAPPING],
    )
    def test_map_token_matches_fixed_mapping(self, token: str, codepoint: int):
        """map_token(token) returns the PUA char for every registered entry."""
        expected_char = chr(codepoint)
        assert map_token(token) == expected_char

    @pytest.mark.parametrize(
        "token,codepoint",
        list(FIXED_PUA_MAPPING.items()),
        ids=[t for t in FIXED_PUA_MAPPING],
    )
    def test_token2char_matches(self, token: str, codepoint: int):
        """TOKEN2CHAR[token] equals chr(codepoint) for every entry."""
        assert TOKEN2CHAR[token] == chr(codepoint)

    @pytest.mark.parametrize(
        "token,codepoint",
        list(FIXED_PUA_MAPPING.items()),
        ids=[t for t in FIXED_PUA_MAPPING],
    )
    def test_char2token_reverse(self, token: str, codepoint: int):
        """CHAR2TOKEN[chr(codepoint)] maps back to the original token."""
        assert CHAR2TOKEN[chr(codepoint)] == token


class TestPUASpotChecks:
    """Verify spot-check entries from the cross-platform fixture file."""

    @pytest.mark.parametrize(
        "entry",
        _load_pua_spot_checks(),
        ids=[e["token"] for e in _load_pua_spot_checks()],
    )
    def test_fixture_spot_check(self, entry: dict):
        """Each pua_spot_checks entry matches FIXED_PUA_MAPPING."""
        token = entry["token"]
        expected_codepoint = int(entry["codepoint"], 16)
        assert token in FIXED_PUA_MAPPING, f"Token {token!r} not in FIXED_PUA_MAPPING"
        assert FIXED_PUA_MAPPING[token] == expected_codepoint
        assert map_token(token) == chr(expected_codepoint)


class TestPUAUnmappedTokens:
    """Test map_token behaviour for tokens NOT in the fixed mapping.

    Note: as of PUA v2 (docs/spec/pua-contract.toml), the default behaviour
    is strict=True which raises UnmappedMultiCodepointTokenError. The legacy
    warning-only behaviour is still available via strict=False for one-off
    decoding utilities. See test_pua_invariants.py::TestMapTokenFailFast for
    strict-mode tests.
    """

    def test_unknown_multi_char_returns_unchanged_with_warning(self):
        """Legacy strict=False: unknown multi-char returns unchanged with warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = map_token("xyz_unknown", strict=False)
            assert result == "xyz_unknown"
            assert len(w) == 1
            assert "no pua mapping" in str(w[0].message).lower()

    def test_unknown_two_char_returns_unchanged(self):
        """Legacy strict=False: two-character token not in mapping returns unchanged."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = map_token("zq", strict=False)
            assert result == "zq"
            assert len(w) == 1

    def test_single_char_not_in_mapping_passes_through(self):
        """Single char not in FIXED_PUA_MAPPING passes through without warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = map_token("Z")
            assert result == "Z"
            assert len(w) == 0, "Single-char passthrough should not emit a warning"


class TestPUABoundaryValues:
    """Boundary-value tests for the PUA codepoint range."""

    def test_first_pua_mapping(self):
        """First PUA mapping starts at U+E000 (token 'a:')."""
        assert FIXED_PUA_MAPPING["a:"] == 0xE000
        assert map_token("a:") == chr(0xE000)

    def test_last_pua_mapping(self):
        """Last PUA mapping is the highest codepoint in the table."""
        max_codepoint = max(FIXED_PUA_MAPPING.values())
        max_token = [t for t, cp in FIXED_PUA_MAPPING.items() if cp == max_codepoint][0]
        assert map_token(max_token) == chr(max_codepoint)
        # Verify it's still in the BMP PUA range (U+E000-U+F8FF)
        assert 0xE000 <= max_codepoint <= 0xF8FF

    def test_all_codepoints_in_pua_range(self):
        """Every codepoint in the mapping is within U+E000-U+F8FF (BMP PUA)."""
        for token, codepoint in FIXED_PUA_MAPPING.items():
            assert 0xE000 <= codepoint <= 0xF8FF, (
                f"Token {token!r} has codepoint U+{codepoint:04X} outside PUA range"
            )

    def test_no_duplicate_codepoints(self):
        """Every codepoint in the mapping is unique (no two tokens share one)."""
        codepoints = list(FIXED_PUA_MAPPING.values())
        assert len(codepoints) == len(set(codepoints)), "Duplicate codepoints found"

    def test_no_duplicate_tokens(self):
        """Every token string in the mapping is unique."""
        tokens = list(FIXED_PUA_MAPPING.keys())
        assert len(tokens) == len(set(tokens)), "Duplicate tokens found"

    def test_bidirectional_map_sizes_match(self):
        """TOKEN2CHAR and CHAR2TOKEN have the same size as FIXED_PUA_MAPPING."""
        assert len(TOKEN2CHAR) == len(FIXED_PUA_MAPPING)
        assert len(CHAR2TOKEN) == len(FIXED_PUA_MAPPING)

    def test_fixture_pua_map_count_matches(self):
        """The fixture's pua_map_count matches the actual mapping size."""
        with open(_FIXTURE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        assert data["pua_map_count"] == len(FIXED_PUA_MAPPING)


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
