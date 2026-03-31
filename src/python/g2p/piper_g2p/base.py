"""Abstract base class and common types for language phonemizers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProsodyInfo:
    """Prosody information shared across all languages.

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
    """G2P abstract base class.

    phonemize() returns IPA token lists.
    BOS/EOS/padding/PUA encoding is NOT included — that is
    the responsibility of ``piper_g2p.encode.PiperEncoder``.
    """

    @abstractmethod
    def phonemize(self, text: str) -> list[str]:
        """Convert text to a list of IPA phoneme tokens."""

    @abstractmethod
    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        """Convert text to IPA phoneme tokens with prosody information."""
