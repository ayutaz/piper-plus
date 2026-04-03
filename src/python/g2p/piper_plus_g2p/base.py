"""Abstract base class and common types for language phonemizers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
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
    the responsibility of ``piper_plus_g2p.encode.PiperEncoder``.
    """

    MAX_INPUT_LENGTH: int = 10_000  # character limit

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    def _sanitize_input(self, text: str) -> str:
        """Validate and clean *text* before phonemization.

        * Rejects non-str inputs with :class:`TypeError`.
        * Rejects inputs longer than :attr:`MAX_INPUT_LENGTH` with
          :class:`ValueError`.
        * Strips control characters except ``\\n``, ``\\t`` and ``\\r``.
        """
        if not isinstance(text, str):
            raise TypeError(f"Expected str, got {type(text).__name__}")
        if len(text) > self.MAX_INPUT_LENGTH:
            raise ValueError(f"Input too long: {len(text)} > {self.MAX_INPUT_LENGTH}")
        # Remove control characters, keep newline / tab / carriage-return
        return "".join(ch for ch in text if ch >= " " or ch in "\n\t\r")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def phonemize(self, text: str) -> list[str]:
        """Convert text to a list of IPA phoneme tokens.

        The default implementation sanitizes *text* via
        :meth:`_sanitize_input`, then delegates to
        :meth:`phonemize_with_prosody` and discards prosody info.
        Subclasses may override this for a more efficient path.
        """
        text = self._sanitize_input(text)
        if not text:
            return []
        tokens, _ = self.phonemize_with_prosody(text)
        return tokens

    @abstractmethod
    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        """Convert text to IPA phoneme tokens with prosody information."""
