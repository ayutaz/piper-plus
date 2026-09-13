"""Hindi G2P for piper-plus inference.

Canonical implementation lives in ``piper_plus_g2p.hindi``. This module
re-exports it when that package is installed so
``MultilingualPhonemizer`` can dispatch ``hi`` the same way as Spanish.
"""

from __future__ import annotations

from .token_mapper import map_sequence


__all__ = ["phonemize_hindi"]


def phonemize_hindi(text: str) -> list[str]:
    """Phonemize Hindi / Hinglish; tokens are PUA-mapped for the runtime."""
    try:
        from piper_plus_g2p.hindi import phonemize_hindi as _phonemize  # noqa: PLC0415
    except ImportError as exc:
        raise ValueError(
            "Hindi G2P requires the piper-plus-g2p package "
            "(pip install piper-plus-g2p)."
        ) from exc
    return map_sequence(_phonemize(text))
