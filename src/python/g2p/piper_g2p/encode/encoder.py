"""PiperEncoder -- IPA token lists to Piper phoneme_ids.

Converts the output of a ``Phonemizer`` (a list of IPA token strings)
into the integer ``phoneme_ids`` array expected by the Piper ONNX model,
inserting BOS/EOS markers and inter-phoneme padding.

The padding scheme is identical to ``piper_train.phonemize.base.Phonemizer.post_process_ids()``.
"""

from __future__ import annotations

from ..base import ProsodyInfo
from .pua import map_token

__all__ = ["PiperEncoder"]


class PiperEncoder:
    """Encode IPA token sequences into Piper ``phoneme_ids``.

    Parameters
    ----------
    phoneme_id_map : dict[str, list[int]]
        Mapping from (PUA-encoded) symbol to its integer ID(s).
        Obtain via ``get_phoneme_id_map("ja")`` or from the model's
        ``config.json``.
    """

    def __init__(self, phoneme_id_map: dict[str, list[int]]) -> None:
        self._id_map = phoneme_id_map

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def encode(
        self,
        tokens: list[str],
        eos_token: str = "$",
    ) -> list[int]:
        """Convert IPA tokens to ``phoneme_ids``.

        Steps:
        1. Multi-character tokens -> PUA single characters via ``map_token``.
        2. Each character is looked up in ``phoneme_id_map``.
        3. BOS (``^``), EOS, and inter-phoneme padding are inserted.

        Parameters
        ----------
        tokens : list[str]
            IPA token list produced by a ``Phonemizer``.
        eos_token : str
            EOS symbol (default ``"$"``).

        Returns
        -------
        list[int]
            Integer phoneme IDs ready for ONNX inference.
        """
        raw_ids = self._tokens_to_raw_ids(tokens)
        dummy_prosody: list[dict | None] = [None] * len(raw_ids)
        result_ids, _ = self._post_process(raw_ids, dummy_prosody, eos_token)
        return result_ids

    def encode_with_prosody(
        self,
        tokens: list[str],
        prosody_list: list[ProsodyInfo | None],
        eos_token: str = "$",
    ) -> tuple[list[int], list[dict | None]]:
        """Convert IPA tokens + prosody to ``(phoneme_ids, prosody_features)``.

        Parameters
        ----------
        tokens : list[str]
            IPA token list.
        prosody_list : list[ProsodyInfo | None]
            Per-token prosody (same length as *tokens*).
        eos_token : str
            EOS symbol (default ``"$"``).

        Returns
        -------
        tuple[list[int], list[dict | None]]
            ``(phoneme_ids, prosody_features)`` where prosody dicts
            have keys ``{"a1", "a2", "a3"}`` and padding positions are
            ``None``.
        """
        raw_ids = self._tokens_to_raw_ids(tokens)
        raw_prosody = self._convert_prosody(prosody_list, len(raw_ids))
        return self._post_process(raw_ids, raw_prosody, eos_token)

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _tokens_to_raw_ids(self, tokens: list[str]) -> list[int]:
        """Map token strings -> flat list of phoneme IDs (no padding)."""
        ids: list[int] = []
        for token in tokens:
            mapped = map_token(token)
            for ch in mapped:
                if ch in self._id_map:
                    ids.extend(self._id_map[ch])
        return ids

    @staticmethod
    def _convert_prosody(
        prosody_list: list[ProsodyInfo | None],
        expected_len: int,
    ) -> list[dict | None]:
        """Convert ProsodyInfo objects to dicts, padding if needed."""
        result: list[dict | None] = []
        for p in prosody_list:
            if p is not None:
                result.append({"a1": p.a1, "a2": p.a2, "a3": p.a3})
            else:
                result.append(None)

        # If token->id expansion produced more IDs than prosody entries,
        # pad with None (shouldn't happen with well-formed input, but
        # be defensive).
        while len(result) < expected_len:
            result.append(None)

        return result[:expected_len]

    def _post_process(
        self,
        phoneme_ids: list[int],
        prosody_features: list[dict | None],
        eos_token: str,
    ) -> tuple[list[int], list[dict | None]]:
        """Insert BOS/EOS and inter-phoneme padding.

        Mirrors ``piper_train.phonemize.base.Phonemizer.post_process_ids()``.
        """
        id_map = self._id_map
        pad_ids = id_map.get("_", [0])
        bos_ids = id_map.get("^")
        eos_ids = id_map.get(eos_token, id_map.get("$"))

        # Insert pad between every phoneme ID, but skip after existing
        # pad/pause tokens (whose ID is in pad_ids).
        padded_ids: list[int] = []
        padded_prosody: list[dict | None] = []
        for phoneme_id, prosody_feature in zip(
            phoneme_ids, prosody_features, strict=True
        ):
            padded_ids.append(phoneme_id)
            padded_prosody.append(prosody_feature)
            if phoneme_id not in pad_ids:
                padded_ids.extend(pad_ids)
                padded_prosody.extend([None] * len(pad_ids))

        phoneme_ids = padded_ids
        prosody_features = padded_prosody

        # Wrap with BOS / EOS
        if bos_ids:
            phoneme_ids = bos_ids + [pad_ids[0]] + phoneme_ids
            prosody_features = [None] * (len(bos_ids) + 1) + prosody_features
        if eos_ids:
            phoneme_ids = phoneme_ids + eos_ids
            prosody_features = prosody_features + [None] * len(eos_ids)

        return phoneme_ids, prosody_features
