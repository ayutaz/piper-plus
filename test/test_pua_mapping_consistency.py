"""Tests for PUA (Private Use Area) mapping consistency.

Validates that FIXED_PUA_MAPPING in token_mapper.py contains all required
entries for C++/Python synchronization. The C++ side hardcodes these exact
codepoints, so any mismatch causes phoneme ID errors at inference time.
"""
import pytest

from piper_train.phonemize.token_mapper import FIXED_PUA_MAPPING, register


class TestFixedPuaMappingCompleteness:
    """Verify all 89 expected PUA entries exist."""

    def test_total_entry_count(self):
        """FIXED_PUA_MAPPING should have exactly 87 entries.

        Range U+E000-E058 = 89 slots, minus 2 reserved gaps
        (0xE01F and 0xE053) = 87 actual entries.
        """
        assert len(FIXED_PUA_MAPPING) == 87, \
            f"Expected 87 entries, got {len(FIXED_PUA_MAPPING)}"

    def test_codepoint_range(self):
        """All codepoints should be in PUA range U+E000-U+E058."""
        for token, cp in FIXED_PUA_MAPPING.items():
            assert 0xE000 <= cp <= 0xE058, \
                f"Token '{token}' has codepoint {hex(cp)} outside E000-E058"

    def test_no_duplicate_codepoints(self):
        """Each codepoint should be unique."""
        codepoints = list(FIXED_PUA_MAPPING.values())
        assert len(codepoints) == len(set(codepoints)), \
            "Duplicate codepoints found in FIXED_PUA_MAPPING"

    def test_no_duplicate_tokens(self):
        """Each token string should be unique."""
        tokens = list(FIXED_PUA_MAPPING.keys())
        assert len(tokens) == len(set(tokens)), \
            "Duplicate tokens found in FIXED_PUA_MAPPING"


class TestJapanesePuaMappings:
    """Validate JA-specific PUA entries (U+E000-U+E01C)."""

    @pytest.mark.parametrize("token,expected_cp", [
        ("a:", 0xE000), ("i:", 0xE001), ("u:", 0xE002),
        ("e:", 0xE003), ("o:", 0xE004),
        ("cl", 0xE005),
        ("ky", 0xE006), ("gy", 0xE008),
        ("ty", 0xE00A), ("dy", 0xE00B),
        ("py", 0xE00C), ("by", 0xE00D),
        ("ch", 0xE00E), ("ts", 0xE00F), ("sh", 0xE010),
        ("zy", 0xE011), ("hy", 0xE012),
        ("ny", 0xE013), ("my", 0xE014), ("ry", 0xE015),
    ])
    def test_ja_phoneme(self, token, expected_cp):
        assert FIXED_PUA_MAPPING[token] == expected_cp

    @pytest.mark.parametrize("token,expected_cp", [
        ("?!", 0xE016), ("?.", 0xE017), ("?~", 0xE018),
    ])
    def test_ja_question_markers(self, token, expected_cp):
        assert FIXED_PUA_MAPPING[token] == expected_cp

    @pytest.mark.parametrize("token,expected_cp", [
        ("N_m", 0xE019), ("N_n", 0xE01A),
        ("N_ng", 0xE01B), ("N_uvular", 0xE01C),
    ])
    def test_ja_n_variants(self, token, expected_cp):
        assert FIXED_PUA_MAPPING[token] == expected_cp


class TestSharedPuaMappings:
    """Validate shared multilingual entries."""

    def test_rr(self):
        """Spanish rr (trill) at U+E01D."""
        assert FIXED_PUA_MAPPING["rr"] == 0xE01D

    def test_y_vowel(self):
        """y_vowel (front rounded) at U+E01E."""
        assert FIXED_PUA_MAPPING["y_vowel"] == 0xE01E


class TestChinesePuaMappings:
    """Validate ZH-specific PUA entries (U+E020-U+E04A)."""

    def test_aspirated_consonants(self):
        """Aspirated stops: ph, th, kh."""
        assert FIXED_PUA_MAPPING["p\u02B0"] == 0xE020  # ph
        assert FIXED_PUA_MAPPING["t\u02B0"] == 0xE021  # th
        assert FIXED_PUA_MAPPING["k\u02B0"] == 0xE022  # kh

    def test_tone_markers(self):
        """Tone markers 1-5 at U+E046-U+E04A."""
        assert FIXED_PUA_MAPPING["tone1"] == 0xE046
        assert FIXED_PUA_MAPPING["tone2"] == 0xE047
        assert FIXED_PUA_MAPPING["tone3"] == 0xE048
        assert FIXED_PUA_MAPPING["tone4"] == 0xE049
        assert FIXED_PUA_MAPPING["tone5"] == 0xE04A

    def test_zh_count(self):
        """ZH should have entries in U+E020-E04A range."""
        zh_entries = {k: v for k, v in FIXED_PUA_MAPPING.items()
                      if 0xE020 <= v <= 0xE04A}
        # 43 entries (E020-E04A = 43 slots, E01F reserved)
        assert len(zh_entries) >= 40, f"Expected >=40 ZH entries, got {len(zh_entries)}"


class TestKoreanPuaMappings:
    """Validate KO-specific PUA entries (U+E04B-U+E052)."""

    def test_ko_count(self):
        """KO should have 8 entries."""
        ko_entries = {k: v for k, v in FIXED_PUA_MAPPING.items()
                      if 0xE04B <= v <= 0xE052}
        assert len(ko_entries) == 8, f"Expected 8 KO entries, got {len(ko_entries)}"

    def test_unreleased_finals(self):
        """Unreleased final stops: k̚, t̚, p̚."""
        assert FIXED_PUA_MAPPING["k\u031A"] == 0xE050  # k̚
        assert FIXED_PUA_MAPPING["t\u031A"] == 0xE051  # t̚
        assert FIXED_PUA_MAPPING["p\u031A"] == 0xE052  # p̚


class TestSpanishPortuguesePuaMappings:
    """Validate ES/PT shared PUA entries."""

    def test_affricates(self):
        """tʃ and dʒ at U+E054-E055."""
        assert FIXED_PUA_MAPPING["t\u0283"] == 0xE054  # tʃ
        assert FIXED_PUA_MAPPING["d\u0292"] == 0xE055  # dʒ


class TestFrenchPuaMappings:
    """Validate FR-specific PUA entries (U+E056-U+E058)."""

    def test_nasal_vowels(self):
        """French nasal vowels: ɛ̃, ɑ̃, ɔ̃."""
        assert FIXED_PUA_MAPPING["\u025B\u0303"] == 0xE056  # ɛ̃
        assert FIXED_PUA_MAPPING["\u0251\u0303"] == 0xE057  # ɑ̃
        assert FIXED_PUA_MAPPING["\u0254\u0303"] == 0xE058  # ɔ̃


class TestRegisterFunction:
    """Verify register() returns correct PUA codepoints for fixed mappings."""

    def test_register_returns_pua_for_fixed(self):
        """register() should return PUA char for multi-char tokens."""
        result = register("ch")
        assert result == chr(0xE00E), f"Expected PUA for 'ch', got {repr(result)}"

    def test_register_returns_same_for_single_char(self):
        """register() should return same char for single-char tokens."""
        result = register("a")
        assert result == "a"

    def test_register_idempotent(self):
        """Calling register() twice returns same result."""
        r1 = register("ts")
        r2 = register("ts")
        assert r1 == r2
