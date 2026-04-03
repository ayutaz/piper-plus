"""Extended tests for PiperEncoder prosody handling."""

import pytest

from piper_plus_g2p.base import ProsodyInfo
from piper_plus_g2p.encode import PiperEncoder
from piper_plus_g2p.encode.id_maps import get_phoneme_id_map


@pytest.fixture()
def id_map():
    return get_phoneme_id_map("ja")


@pytest.fixture()
def encoder(id_map):
    return PiperEncoder(id_map)


class TestProsodyPaddingConsistency:
    """Prosody length must always equal output ID length (BOS/EOS/PAD included)."""

    def test_prosody_padding_consistency(self, encoder):
        """prosody_features length == phoneme_ids length after encoding."""
        tokens = ["a", "i", "u"]
        prosody = [
            ProsodyInfo(a1=-2, a2=1, a3=5),
            ProsodyInfo(a1=-1, a2=2, a3=5),
            ProsodyInfo(a1=0, a2=3, a3=5),
        ]
        ids, prosody_out = encoder.encode_with_prosody(tokens, prosody)

        assert len(ids) == len(prosody_out), (
            f"phoneme_ids length ({len(ids)}) != "
            f"prosody_features length ({len(prosody_out)})"
        )

    def test_prosody_padding_single_token(self, encoder):
        """Even a single token produces matching lengths."""
        tokens = ["k"]
        prosody = [ProsodyInfo(a1=0, a2=1, a3=1)]
        ids, prosody_out = encoder.encode_with_prosody(tokens, prosody)

        assert len(ids) == len(prosody_out)

    def test_prosody_padding_positions_are_none(self, encoder, id_map):
        """BOS, EOS, and inter-phoneme pad positions have None prosody."""
        tokens = ["a", "i"]
        prosody = [
            ProsodyInfo(a1=1, a2=2, a3=3),
            ProsodyInfo(a1=4, a2=5, a3=6),
        ]
        ids, prosody_out = encoder.encode_with_prosody(tokens, prosody)

        bos_id = id_map["^"][0]
        eos_id = id_map["$"][0]
        pad_id = id_map["_"][0]

        # BOS position
        assert ids[0] == bos_id
        assert prosody_out[0] is None

        # EOS position
        assert ids[-1] == eos_id
        assert prosody_out[-1] is None

        # Pad after BOS
        assert ids[1] == pad_id
        assert prosody_out[1] is None


class TestEncodeWithProsodyNoneValues:
    """Prosody lists containing some None entries."""

    def test_encode_with_prosody_none_values(self, encoder):
        """None entries in prosody_list are preserved through encoding."""
        tokens = ["a", "i", "u"]
        prosody = [
            ProsodyInfo(a1=1, a2=2, a3=3),
            None,
            ProsodyInfo(a1=4, a2=5, a3=6),
        ]
        ids, prosody_out = encoder.encode_with_prosody(tokens, prosody)

        assert len(ids) == len(prosody_out)
        # The non-None ProsodyInfo values must appear somewhere in output
        infos = [p for p in prosody_out if p is not None]
        assert len(infos) >= 2

    def test_none_prosody_does_not_corrupt_ids(self, encoder):
        """phoneme_ids are identical whether prosody has None or not."""
        tokens = ["a", "i"]
        prosody_with_none = [None, ProsodyInfo(a1=0, a2=1, a3=2)]
        prosody_all_set = [
            ProsodyInfo(a1=9, a2=9, a3=9),
            ProsodyInfo(a1=0, a2=1, a3=2),
        ]

        ids_a, _ = encoder.encode_with_prosody(tokens, prosody_with_none)
        ids_b, _ = encoder.encode_with_prosody(tokens, prosody_all_set)

        assert ids_a == ids_b


class TestEncodeWithProsodyAllNone:
    """Prosody list where every entry is None."""

    def test_encode_with_prosody_all_none(self, encoder):
        """All-None prosody still produces valid (ids, prosody) pair."""
        tokens = ["a", "i", "u"]
        prosody = [None, None, None]
        ids, prosody_out = encoder.encode_with_prosody(tokens, prosody)

        assert len(ids) == len(prosody_out)
        assert len(ids) > 0
        # Every prosody entry should be None
        assert all(p is None for p in prosody_out)

    def test_all_none_matches_encode_without_prosody(self, encoder):
        """All-None prosody yields same phoneme_ids as encode() (no prosody)."""
        tokens = ["a", "i"]
        ids_plain = encoder.encode(tokens)
        ids_prosody, _ = encoder.encode_with_prosody(tokens, [None, None])

        assert ids_plain == ids_prosody


class TestEncodeEmptyTokensWithProsody:
    """Empty token list combined with prosody."""

    def test_encode_empty_tokens_with_prosody(self, encoder):
        """Empty tokens produce only BOS+EOS (no crash)."""
        ids, prosody_out = encoder.encode_with_prosody([], [])

        assert len(ids) == len(prosody_out)
        # Should contain at least BOS and EOS
        assert len(ids) >= 2
        # All prosody positions should be None for structural tokens
        assert all(p is None for p in prosody_out)

    def test_encode_empty_tokens_without_prosody(self, encoder):
        """Empty tokens via encode() also succeed."""
        ids = encoder.encode([])
        assert len(ids) >= 2  # BOS + EOS at minimum


class TestProsodyToDictsRoundtrip:
    """ProsodyInfo -> dict -> ProsodyInfo roundtrip."""

    def test_prosody_to_dicts_roundtrip(self):
        """Convert ProsodyInfo to dicts and back; values are preserved."""
        original = [
            ProsodyInfo(a1=-2, a2=1, a3=5),
            None,
            ProsodyInfo(a1=0, a2=3, a3=7),
        ]

        dicts = PiperEncoder.prosody_to_dicts(original)

        # Verify dict format
        assert dicts[0] == {"a1": -2, "a2": 1, "a3": 5}
        assert dicts[1] is None
        assert dicts[2] == {"a1": 0, "a2": 3, "a3": 7}

        # Reconstruct ProsodyInfo from dicts
        reconstructed = [ProsodyInfo(**d) if d is not None else None for d in dicts]

        assert reconstructed == list(original)

    def test_prosody_to_dicts_empty(self):
        """Empty prosody list produces empty dict list."""
        assert PiperEncoder.prosody_to_dicts([]) == []

    def test_prosody_to_dicts_all_none(self):
        """All-None prosody list produces all-None dict list."""
        result = PiperEncoder.prosody_to_dicts([None, None])
        assert result == [None, None]

    def test_roundtrip_through_encoder(self, encoder):
        """Full encode -> prosody_to_dicts -> reconstruct roundtrip."""
        tokens = ["a", "i"]
        prosody = [
            ProsodyInfo(a1=1, a2=2, a3=3),
            ProsodyInfo(a1=4, a2=5, a3=6),
        ]

        _, prosody_out = encoder.encode_with_prosody(tokens, prosody)
        dicts = PiperEncoder.prosody_to_dicts(prosody_out)
        reconstructed = [ProsodyInfo(**d) if d is not None else None for d in dicts]

        assert reconstructed == prosody_out
