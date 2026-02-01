"""Abstract base class and common types for language phonemizers."""

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
    ) -> tuple[list[int], list[dict | None]]:
        """Post-process phoneme IDs (e.g. BOS/EOS/padding). Default is no-op."""
        return phoneme_ids, prosody_features
