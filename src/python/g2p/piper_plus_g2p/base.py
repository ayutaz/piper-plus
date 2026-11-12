"""Abstract base class and common types for language phonemizers."""

import unicodedata
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


# Control characters (Unicode Cc) that stripping does not remove:
# docs/spec/input-sanitize-contract.toml [rule] keep / to_space.
_CONTROLS_TO_SPACE = "\u000b\u000c\u0085"
_CONTROLS_KEPT_OR_SPACED = "\n\t\r" + _CONTROLS_TO_SPACE


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

    def _strip_control_chars(self, text: str) -> str:
        """Clean *text* by the rule of ``docs/spec/input-sanitize-contract.toml``.

        * Rejects non-str inputs with :class:`TypeError`.
        * Keeps ``\\n``, ``\\t`` and ``\\r``; turns VT, FF and NEL (U+000B,
          U+000C, U+0085), which separate words, into a space; removes every
          other control character (Unicode Cc).

        No length limit: callers pass whole texts.
        """
        if not isinstance(text, str):
            raise TypeError(f"Expected str, got {type(text).__name__}")
        return "".join(
            " " if ch in _CONTROLS_TO_SPACE else ch
            for ch in text
            if unicodedata.category(ch) != "Cc" or ch in _CONTROLS_KEPT_OR_SPACED
        )

    def _sanitize_input(self, text: str) -> str:
        """:meth:`_strip_control_chars`, plus the :attr:`MAX_INPUT_LENGTH` limit.

        Rejects inputs longer than :attr:`MAX_INPUT_LENGTH` with
        :class:`ValueError`. Only the entry points that had the limit before
        stripping reached every language call this (ja, en, sv's
        ``phonemize``); the others call :meth:`_strip_control_chars`.
        """
        if isinstance(text, str) and len(text) > self.MAX_INPUT_LENGTH:
            raise ValueError(f"Input too long: {len(text)} > {self.MAX_INPUT_LENGTH}")
        return self._strip_control_chars(text)

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
