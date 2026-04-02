"""PiperEncoder -- IPA token lists to Piper phoneme_ids.

Converts the output of a ``Phonemizer`` (a list of IPA token strings)
into the integer ``phoneme_ids`` array expected by the Piper ONNX model,
inserting BOS/EOS markers and inter-phoneme padding.

The padding scheme is identical to
``piper_train.phonemize.base.Phonemizer.post_process_ids()``.
"""

from __future__ import annotations

import logging

from ..base import ProsodyInfo
from .pua import map_token

__all__ = ["PiperEncoder"]

_log = logging.getLogger(__name__)


class PiperEncoder:
    """Encode IPA token sequences into Piper ``phoneme_ids``.

    Parameters
    ----------
    phoneme_id_map : dict[str, list[int]]
        Mapping from (PUA-encoded) symbol to its integer ID(s).
        Obtain via ``get_phoneme_id_map("ja")`` or from the model's
        ``config.json``.
    """

    def __init__(
        self,
        phoneme_id_map: dict[str, list[int]],
        *,
        strict: bool = False,
    ) -> None:
        self._id_map = phoneme_id_map
        self._strict = strict

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
        dummy_prosody: list[ProsodyInfo | None] = [None] * len(raw_ids)
        result_ids, _ = self._post_process(raw_ids, dummy_prosody, eos_token)
        return result_ids

    def encode_with_prosody(
        self,
        tokens: list[str],
        prosody_list: list[ProsodyInfo | None],
        eos_token: str = "$",
    ) -> tuple[list[int], list[ProsodyInfo | None]]:
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
        tuple[list[int], list[ProsodyInfo | None]]
            ``(phoneme_ids, prosody_features)`` where each entry is a
            :class:`ProsodyInfo` with attributes ``a1``, ``a2``, ``a3``
            and padding positions are ``None``.
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
                else:
                    if self._strict:
                        raise KeyError(
                            f"Unknown phoneme symbol {ch!r} not in phoneme_id_map"
                        )
                    _log.warning(
                        "Unknown symbol %r dropped (not in phoneme_id_map)",
                        ch,
                    )
        return ids

    @staticmethod
    def _convert_prosody(
        prosody_list: list[ProsodyInfo | None],
        expected_len: int,
    ) -> list[ProsodyInfo | None]:
        """Pass through ProsodyInfo objects, padding with None if needed."""
        result: list[ProsodyInfo | None] = list(prosody_list)

        # If token->id expansion produced more IDs than prosody entries,
        # pad with None (shouldn't happen with well-formed input, but
        # be defensive).
        while len(result) < expected_len:
            result.append(None)

        return result[:expected_len]

    @staticmethod
    def prosody_to_dicts(
        prosody: list[ProsodyInfo | None],
    ) -> list[dict | None]:
        """Convert a prosody list to plain dicts for JSON serialization.

        Use this when you need ``{"a1", "a2", "a3"}`` dicts (e.g. for
        JSONL output) instead of :class:`ProsodyInfo` objects.

        Parameters
        ----------
        prosody : list[ProsodyInfo | None]
            Prosody list as returned by :meth:`encode_with_prosody`.

        Returns
        -------
        list[dict | None]
            Each :class:`ProsodyInfo` is converted to
            ``{"a1": ..., "a2": ..., "a3": ...}``; ``None`` entries
            remain ``None``.
        """
        return [{"a1": p.a1, "a2": p.a2, "a3": p.a3} if p else None for p in prosody]

    def _post_process(
        self,
        phoneme_ids: list[int],
        prosody_features: list[ProsodyInfo | None],
        eos_token: str,
    ) -> tuple[list[int], list[ProsodyInfo | None]]:
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
        padded_prosody: list[ProsodyInfo | None] = []
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
            bos_prosody: list[ProsodyInfo | None] = [None] * (len(bos_ids) + 1)
            prosody_features = bos_prosody + prosody_features
        if eos_ids:
            phoneme_ids = phoneme_ids + eos_ids
            prosody_features = prosody_features + [None] * len(eos_ids)

        return phoneme_ids, prosody_features
