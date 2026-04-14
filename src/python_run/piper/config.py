"""Piper configuration"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PhonemeType(str, Enum):
    OPENJTALK = "openjtalk"
    BILINGUAL = "bilingual"
    MULTILINGUAL = "multilingual"


@dataclass
class PiperConfig:
    """Piper configuration"""

    num_symbols: int
    """Number of phonemes"""

    num_speakers: int
    """Number of speakers"""

    sample_rate: int
    """Sample rate of output audio"""

    length_scale: float
    noise_scale: float
    noise_w: float

    phoneme_id_map: Mapping[str, Sequence[int]]
    """Phoneme -> [id,]"""

    phoneme_type: PhonemeType

    hop_size: int = 256
    """STFT hop length in samples (default: 256 for VITS medium quality)"""

    num_languages: int = 1
    """Number of languages"""

    language_id_map: Mapping[str, int] | None = None
    """Language code -> language id (e.g. {"ja": 0, "en": 1})"""

    @staticmethod
    def from_dict(config: dict[str, Any]) -> "PiperConfig":
        inference = config.get("inference", {})

        return PiperConfig(
            num_symbols=config["num_symbols"],
            num_speakers=config["num_speakers"],
            sample_rate=config["audio"]["sample_rate"],
            noise_scale=inference.get("noise_scale", 0.667),
            length_scale=inference.get("length_scale", 1.0),
            noise_w=inference.get("noise_w", 0.8),
            hop_size=config.get("audio", {}).get("hop_size", 256),
            phoneme_id_map=config["phoneme_id_map"],
            phoneme_type=PhonemeType(config.get("phoneme_type", "multilingual")),
            num_languages=config.get("num_languages", 1),
            language_id_map=config.get("language_id_map"),
        )
