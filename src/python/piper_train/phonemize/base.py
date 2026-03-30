"""Abstract base class and common types for language phonemizers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProsodyInfo:
    """Common prosody information shared across all languages.

    Attributes
    ----------
    a1 : int
        Language-dependent prosody dimension 1.
        Japanese: relative position from accent nucleus.
        English: fixed at 0.
    a2 : int
        Language-dependent prosody dimension 2.
        Japanese: mora position in accent phrase (1-based).
        English: stress level (0=none, 1=secondary, 2=primary).
    a3 : int
        Language-dependent prosody dimension 3.
        Japanese: total morae in accent phrase.
        English: number of phonemes in the word.
    """

    a1: int
    a2: int
    a3: int


class Phonemizer(ABC):
    """Abstract base class for language phonemizers."""

    @abstractmethod
    def phonemize(self, text: str) -> list[str]:
        """Convert text to a list of phoneme tokens."""

    @abstractmethod
    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        """Convert text to phoneme tokens with prosody information."""

    @abstractmethod
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None:
        """Return language-specific phoneme_id_map, or None to use config-provided map."""

    def post_process_ids(
        self,
        phoneme_ids: list[int],
        prosody_features: list[dict | None],
        phoneme_id_map: dict[str, list[int]],
        eos_token: str = "$",
    ) -> tuple[list[int], list[dict | None]]:
        """Add BOS/EOS and inter-phoneme padding (espeak-ng compatible).

        Default implementation shared by English, Chinese, Korean, Spanish,
        Portuguese, and French phonemizers. Inserts pad tokens between every
        phoneme ID and wraps with BOS (^) / EOS ($) markers.

        Subclasses may override for language-specific behavior (e.g.,
        MultilingualPhonemizer uses a dynamic EOS token, JapanesePhonemizer
        delegates post-processing to the caller).

        Parameters
        ----------
        eos_token : str
            The EOS token to look up in ``phoneme_id_map``.  Defaults to
            ``"$"``.  Falls back to ``"$"`` when the requested token is not
            present in the map.
        """
        pad_ids = phoneme_id_map.get("_", [0])
        bos_ids = phoneme_id_map.get("^")
        eos_ids = phoneme_id_map.get(eos_token, phoneme_id_map.get("$"))

        # Insert pad between every phoneme ID, but skip after existing pad/pause
        # tokens (ID 0) to match the training data padding scheme.
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

        # Wrap with BOS/EOS
        if bos_ids:
            phoneme_ids = bos_ids + [pad_ids[0]] + phoneme_ids
            prosody_features = [None] * (len(bos_ids) + 1) + prosody_features
        if eos_ids:
            phoneme_ids = phoneme_ids + eos_ids
            prosody_features = prosody_features + [None] * len(eos_ids)

        return phoneme_ids, prosody_features
