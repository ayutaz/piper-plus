"""Tests for PiperEncoder strict mode."""

import pytest

from piper_plus_g2p.encode.encoder import PiperEncoder


@pytest.fixture
def minimal_id_map():
    return {"_": [0], "^": [1], "$": [2], "a": [3], "k": [4]}


class TestStrictMode:
    def test_strict_raises_on_unknown_token(self, minimal_id_map):
        encoder = PiperEncoder(minimal_id_map, strict=True)
        with pytest.raises(KeyError, match="Unknown phoneme symbol"):
            encoder.encode(["a", "UNKNOWN", "k"])

    def test_non_strict_skips_unknown_token(self, minimal_id_map):
        encoder = PiperEncoder(minimal_id_map, strict=False)
        ids = encoder.encode(["a", "UNKNOWN", "k"])
        assert 3 in ids
        assert 4 in ids

    def test_default_is_non_strict(self, minimal_id_map):
        """Default mode = non-strict: unknown tokens are skipped, no raise."""
        encoder = PiperEncoder(minimal_id_map)
        # If default were strict, this call would raise KeyError. Pin that
        # default is non-strict and the unknown token is silently skipped.
        ids = encoder.encode(["a", "UNKNOWN", "k"])
        # Known tokens still map through.
        assert 3 in ids  # "a"
        assert 4 in ids  # "k"
        # And the result must equal the explicit non-strict path byte-for-byte
        # so default == strict=False is pinned.
        explicit_non_strict = PiperEncoder(minimal_id_map, strict=False).encode(
            ["a", "UNKNOWN", "k"]
        )
        assert ids == explicit_non_strict

    def test_strict_with_valid_tokens(self, minimal_id_map):
        encoder = PiperEncoder(minimal_id_map, strict=True)
        ids = encoder.encode(["a", "k"])
        assert 3 in ids
        assert 4 in ids
