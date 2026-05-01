"""Wyoming Protocol TTS handler for piper-plus.

Uses PiperPlus high-level API instead of reimplementing inference logic.
"""

from __future__ import annotations

import logging

from wyoming.info import Attribution, Info, TtsProgram, TtsVoice

from piper_wyoming import __version__


logger = logging.getLogger(__name__)

# Trained languages only (not SV/KO which are G2P-only)
SUPPORTED_LANGUAGES = ("ja", "en", "zh", "es", "fr", "pt")


def build_info(languages: list[str] | None = None) -> Info:
    """Build Wyoming service info for discovery."""
    langs = languages or list(SUPPORTED_LANGUAGES)
    attribution = Attribution(
        name="piper-plus",
        url="https://github.com/ayutaz/piper-plus",
    )
    voices = [
        TtsVoice(
            name=f"piper-plus-{lang}",
            description=f"piper-plus ({lang})",
            attribution=attribution,
            installed=True,
            languages=[lang],
            # Voice モデル自身のバージョンが無いため None (rhasspy/wyoming-piper 準拠)
            version=None,
        )
        for lang in langs
    ]
    return Info(
        tts=[
            TtsProgram(
                name="piper-plus",
                description="piper-plus: Multilingual Neural TTS (MIT, no espeak-ng)",
                attribution=attribution,
                installed=True,
                voices=voices,
                # サービスソフトウェアのバージョン
                version=__version__,
            )
        ]
    )


def resolve_language(synthesize_event, default: str = "ja") -> str:
    """Extract language from a Wyoming Synthesize event.

    Wyoming maps ``{"language": "en"}`` to ``SynthesizeVoice(name="en")``,
    and ``{"name": "piper-plus-en"}`` keeps ``name="piper-plus-en"``.
    We check for both patterns.
    """
    voice = synthesize_event.voice
    if voice is None:
        return default

    # Check voice.language first (set by some HA versions)
    if voice.language and voice.language in SUPPORTED_LANGUAGES:
        return voice.language

    # Check voice.name -- could be a bare language code or "piper-plus-XX"
    if voice.name:
        name = voice.name
        if name in SUPPORTED_LANGUAGES:
            return name
        for lang in SUPPORTED_LANGUAGES:
            if name.endswith(f"-{lang}"):
                return lang

    return default
