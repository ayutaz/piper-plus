"""
Tests for PUA token mapping implementation (piper_plus_g2p.encode.pua)
Testing the actual implementation without modifying it
"""

import pytest

from piper_plus_g2p.encode.pua import (
    CHAR2TOKEN,
    FIXED_PUA_MAPPING,
    TOKEN2CHAR,
    map_token,
)


class TestTokenMapperImplementation:
    """Test the existing token mapper implementation"""

    @pytest.mark.unit
    def test_predefined_mappings_exist(self):
        """Test that predefined PUA mappings exist"""
        # These mappings are defined in the actual implementation
        expected_mappings = {
            "a:": "\ue000",
            "i:": "\ue001",
            "u:": "\ue002",
            "e:": "\ue003",
            "o:": "\ue004",
            "cl": "\ue005",
            "ky": "\ue006",
            "kw": "\ue007",
            "gy": "\ue008",
            "gw": "\ue009",
            "ty": "\ue00a",
            "dy": "\ue00b",
            "py": "\ue00c",
            "by": "\ue00d",
            "ch": "\ue00e",
            "ts": "\ue00f",
            "sh": "\ue010",
            "zy": "\ue011",
            "hy": "\ue012",
            "ny": "\ue013",
            "my": "\ue014",
            "ry": "\ue015",
        }

        for token, expected_char in expected_mappings.items():
            assert TOKEN2CHAR[token] == expected_char
            assert CHAR2TOKEN[expected_char] == token

    @pytest.mark.unit
    def test_map_token_known_multi_char(self):
        """Test mapping a known multi-character token returns PUA character"""
        existing_token = "ch"
        expected_char = "\ue00e"

        result = map_token(existing_token)
        assert result == expected_char
        assert TOKEN2CHAR[existing_token] == expected_char
        assert CHAR2TOKEN[expected_char] == existing_token

    @pytest.mark.unit
    def test_map_token_single_char_passthrough(self):
        """Test that single-character tokens pass through unchanged"""
        result = map_token("a")
        assert result == "a"

    @pytest.mark.unit
    def test_fixed_pua_mapping_in_pua_range(self):
        """Test all FIXED_PUA_MAPPING values are in PUA range"""
        for token, codepoint in FIXED_PUA_MAPPING.items():
            assert 0xE000 <= codepoint <= 0xF8FF, (
                f"Token {token!r} codepoint 0x{codepoint:04X} outside PUA range"
            )

    @pytest.mark.unit
    def test_map_token_on_sequence_basic(self):
        """Test mapping a sequence of tokens using map_token"""
        # Test sequence with both mapped and unmapped tokens
        sequence = ["k", "o", "n", "n", "i", "ch", "i", "w", "a"]

        mapped = [map_token(t) for t in sequence]

        # Verify the mapping
        assert mapped[0] == "k"  # unmapped
        assert mapped[1] == "o"  # unmapped
        assert mapped[5] == "\ue00e"  # "ch" -> PUA
        assert mapped[6] == "i"  # unmapped

    @pytest.mark.unit
    def test_map_token_on_sequence_with_multiple_mappings(self):
        """Test map_token on sequence with multiple multi-char phonemes"""
        sequence = ["ch", "i", "ts", "u", "ky", "o"]

        mapped = [map_token(t) for t in sequence]

        assert mapped[0] == "\ue00e"  # ch
        assert mapped[1] == "i"
        assert mapped[2] == "\ue00f"  # ts
        assert mapped[3] == "u"
        assert mapped[4] == "\ue006"  # ky
        assert mapped[5] == "o"

    @pytest.mark.unit
    def test_map_token_on_empty_sequence(self):
        """Test map_token on an empty sequence"""
        assert [map_token(t) for t in []] == []

    @pytest.mark.unit
    def test_map_token_on_sequence_no_mappings(self):
        """Test map_token on sequence with no multi-char phonemes"""
        sequence = ["a", "i", "u", "e", "o"]
        mapped = [map_token(t) for t in sequence]
        assert mapped == sequence  # Should be unchanged

    @pytest.mark.unit
    def test_char_to_token_reverse_mapping(self):
        """Test reverse mapping from PUA char to token"""
        # Test all predefined reverse mappings
        for char, token in CHAR2TOKEN.items():
            assert TOKEN2CHAR[token] == char

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "token,expected_char",
        [
            ("a:", "\ue000"),  # long vowels
            ("i:", "\ue001"),
            ("u:", "\ue002"),
            ("e:", "\ue003"),
            ("o:", "\ue004"),
            ("cl", "\ue005"),  # consonants
            ("ch", "\ue00e"),
            ("ts", "\ue00f"),
            ("sh", "\ue010"),
        ],
    )
    def test_specific_token_mappings(self, token, expected_char):
        """Test specific token to PUA character mappings"""
        assert TOKEN2CHAR[token] == expected_char
        assert CHAR2TOKEN[expected_char] == token
