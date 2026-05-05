"""Tests for PUA mapping invariants — see docs/spec/pua-contract.toml.

These tests are the unit-test layer of the multi-codepoint regression
prevention system. They run on every PR via .github/workflows/pua-consistency.yml.

Test categories:
  - L1 inventory coverage: every multi-codepoint token in id_maps.py inventories
    must be in pua.json
  - L2 fail-fast: map_token() must raise on unmapped multi-codepoint tokens in
    strict mode
  - L3 generated map invariants: every key returned by get_phoneme_id_map()
    must be a single Unicode codepoint
  - L4 canonical source: pua.json structure must satisfy schema invariants
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from piper_plus_g2p.encode import id_maps
from piper_plus_g2p.encode.id_maps import (
    _CHINESE_PHONEMES,
    _ENGLISH_PHONEMES,
    _FRENCH_PHONEMES,
    _JAPANESE_PHONEMES,
    _KOREAN_PHONEMES,
    _PORTUGUESE_PHONEMES,
    _SPANISH_PHONEMES,
    _SPECIAL_TOKENS,
    _SWEDISH_PHONEMES,
    get_phoneme_id_map,
)
from piper_plus_g2p.encode.pua import (
    FIXED_PUA_MAPPING,
    PUA_COMPAT_VERSION,
    UnmappedMultiCodepointTokenError,
    map_token,
)

CANONICAL_PUA_JSON = (
    Path(__file__).parent.parent / "piper_plus_g2p" / "data" / "pua.json"
)


# ---------------------------------------------------------------------------
# L4: pua.json schema invariants
# ---------------------------------------------------------------------------


class TestPuaJsonSchema:
    """Validate the canonical pua.json file's structure."""

    @pytest.fixture
    def canonical(self) -> dict:
        return json.loads(CANONICAL_PUA_JSON.read_text(encoding="utf-8"))

    def test_has_version_field(self, canonical):
        assert "version" in canonical
        assert isinstance(canonical["version"], int)

    def test_version_matches_pua_compat_version(self, canonical):
        assert canonical["version"] == PUA_COMPAT_VERSION, (
            f"pua.json version ({canonical['version']}) must equal "
            f"PUA_COMPAT_VERSION ({PUA_COMPAT_VERSION})"
        )

    def test_no_duplicate_tokens(self, canonical):
        tokens = [e["token"] for e in canonical["entries"]]
        assert len(tokens) == len(set(tokens)), (
            f"Duplicate tokens in pua.json: "
            f"{[t for t in tokens if tokens.count(t) > 1]}"
        )

    def test_no_duplicate_codepoints(self, canonical):
        codepoints = [e["codepoint"] for e in canonical["entries"]]
        assert len(codepoints) == len(set(codepoints)), (
            f"Duplicate codepoints in pua.json: "
            f"{[c for c in codepoints if codepoints.count(c) > 1]}"
        )

    def test_codepoints_in_pua_range(self, canonical):
        for entry in canonical["entries"]:
            cp = int(entry["codepoint"], 16)
            assert 0xE000 <= cp <= 0xF8FF, (
                f"Token {entry['token']!r} has codepoint U+{cp:04X} "
                f"outside BMP PUA range U+E000..U+F8FF"
            )

    def test_all_tokens_are_multi_codepoint_or_special(self, canonical):
        # Single-codepoint tokens don't need PUA mapping
        for entry in canonical["entries"]:
            tok = entry["token"]
            # Allow Latin1/IPA single-codepoint that are still multi-byte UTF-8
            if len(tok) == 1:
                pytest.fail(
                    f"Token {tok!r} (U+{ord(tok):04X}) is a single codepoint "
                    "and should not be in pua.json (no PUA mapping needed)"
                )


# ---------------------------------------------------------------------------
# L1: inventory coverage — every inventory token must be in pua.json
# ---------------------------------------------------------------------------


class TestInventoryCoverage:
    """Every multi-codepoint token in any inventory list must be in pua.json."""

    @pytest.mark.parametrize(
        "inventory_name,inventory",
        [
            ("_SPECIAL_TOKENS", _SPECIAL_TOKENS),
            ("_JAPANESE_PHONEMES", _JAPANESE_PHONEMES),
            ("_ENGLISH_PHONEMES", _ENGLISH_PHONEMES),
            ("_CHINESE_PHONEMES", _CHINESE_PHONEMES),
            ("_SPANISH_PHONEMES", _SPANISH_PHONEMES),
            ("_FRENCH_PHONEMES", _FRENCH_PHONEMES),
            ("_PORTUGUESE_PHONEMES", _PORTUGUESE_PHONEMES),
            ("_KOREAN_PHONEMES", _KOREAN_PHONEMES),
            ("_SWEDISH_PHONEMES", _SWEDISH_PHONEMES),
        ],
    )
    def test_inventory_multi_codepoint_tokens_have_pua_mapping(
        self, inventory_name: str, inventory: list[str]
    ):
        unmapped = [
            tok for tok in inventory if len(tok) > 1 and tok not in FIXED_PUA_MAPPING
        ]
        assert not unmapped, (
            f"Inventory {inventory_name} has {len(unmapped)} multi-codepoint "
            f"tokens with no PUA mapping: {unmapped}. "
            "Add them to src/python/g2p/piper_plus_g2p/data/pua.json."
        )


# ---------------------------------------------------------------------------
# L2: fail-fast — map_token must raise on unmapped multi-codepoint tokens
# ---------------------------------------------------------------------------


class TestMapTokenFailFast:
    """map_token() in strict mode must raise on unmapped multi-codepoint."""

    def test_known_token_returns_pua_char(self):
        result = map_token("ch")  # Japanese 'ch' -> U+E00E
        assert result == ""

    def test_single_codepoint_passes_through(self):
        assert map_token("a") == "a"
        assert map_token("ɔ") == "ɔ"  # U+0254

    def test_unmapped_multi_codepoint_raises_in_strict_mode(self):
        with pytest.raises(UnmappedMultiCodepointTokenError) as ei:
            map_token("xx_unmapped_token_zzz", strict=True)
        assert "no PUA mapping" in str(ei.value)
        assert "pua.json" in str(ei.value)

    def test_unmapped_multi_codepoint_warns_in_non_strict_mode(self):
        with pytest.warns(UserWarning, match="no PUA mapping"):
            result = map_token("xx_unmapped_token_zzz", strict=False)
        assert result == "xx_unmapped_token_zzz"

    def test_default_is_non_strict_for_runtime_back_compat(self):
        """Default strict=False preserves PiperEncoder back-compat behaviour."""
        with pytest.warns(UserWarning):
            result = map_token("xx_unmapped_token_zzz")
        assert result == "xx_unmapped_token_zzz"

    def test_v2_additions_are_mapped(self):
        # The 3 tokens that caused the v1.12.0 regression
        assert map_token("ɔɪ") == ""  # English diphthong
        assert map_token("œ̃") == ""  # French nasal
        assert map_token("ɐ̃") == ""  # Portuguese nasal


# ---------------------------------------------------------------------------
# L3: generated phoneme_id_map keys must be single-codepoint
# ---------------------------------------------------------------------------


class TestGeneratedMapInvariants:
    """get_phoneme_id_map() must always return single-codepoint keys."""

    @pytest.mark.parametrize(
        "language",
        ["ja", "ko", "sv", "multilingual", "ja-en-zh-es-fr-pt"],
    )
    def test_all_keys_are_single_codepoint(self, language: str):
        pid_map = get_phoneme_id_map(language)
        bad = [k for k in pid_map if len(k) != 1]
        assert not bad, (
            f"get_phoneme_id_map({language!r}) returned multi-codepoint key(s): "
            f"{bad}. C++ runtime would reject this config."
        )

    def test_multilingual_contains_pua_v2_additions(self):
        pid_map = get_phoneme_id_map("multilingual")
        # The 3 tokens that caused the regression should now be PUA-encoded
        assert "" in pid_map  # ɔɪ
        assert "" in pid_map  # œ̃
        assert "" in pid_map  # ɐ̃
        # And the original multi-codepoint forms should NOT be keys
        assert "ɔɪ" not in pid_map
        assert "œ̃" not in pid_map
        assert "ɐ̃" not in pid_map

    def test_id_map_assert_helper_rejects_multi_codepoint(self):
        # Direct test of the invariant helper
        bad_map = {"a": [0], "ɔɪ": [1]}  # 2nd key is 2 codepoints
        with pytest.raises(AssertionError, match="multi-codepoint"):
            id_maps._assert_single_codepoint_keys(bad_map, language="test")
