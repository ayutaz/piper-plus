"""Wyoming Protocol event handler for piper-plus TTS."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Attribution, Describe, Info, TtsProgram, TtsVoice
from wyoming.tts import Synthesize

from piper_plus_g2p.registry import get_phonemizer
from piper_train.ort_utils import create_session_with_cache, warmup_onnx_session

_LOGGER = logging.getLogger(__name__)

# 6 trained languages (SV/KO have G2P but no trained model)
SUPPORTED_LANGUAGES = ("ja", "en", "zh", "es", "fr", "pt")

SAMPLE_RATE = 22050
SAMPLE_WIDTH = 2  # int16
CHANNELS = 1
CHUNK_BYTES = 4096  # PCM bytes per AudioChunk


def audio_float_to_int16(
    audio: np.ndarray, max_wav_value: float = 32767.0
) -> np.ndarray:
    """Normalize audio and convert to int16 range."""
    audio_norm = audio * (max_wav_value / max(0.01, np.max(np.abs(audio))))
    audio_norm = np.clip(audio_norm, -max_wav_value, max_wav_value)
    return audio_norm.astype("int16")


class PiperPlusSynthesizer:
    """ONNX inference wrapper for piper-plus.

    Reuses the inference pipeline from ``inference.py`` (phonemize -> encode
    -> infer -> decode) without importing the FastAPI server code.  Session
    management follows ``ort_utils.py`` patterns.
    """

    def __init__(
        self,
        model_path: str,
        config_path: str | None = None,
        *,
        device: str = "cpu",
    ) -> None:
        # Resolve config path
        if config_path is None:
            candidate = Path(f"{model_path}.json")
            if candidate.exists():
                config_path = str(candidate)
            else:
                config_path = str(Path(model_path).parent / "config.json")

        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        self.phoneme_id_map: dict[str, list[int]] = config["phoneme_id_map"]
        self.language_id_map: dict[str, int] = config.get("language_id_map", {})

        # Load ONNX session with optimized cache + warmup
        self.session = create_session_with_cache(model_path, device=device)
        warmup_onnx_session(self.session)

        input_names = {inp.name for inp in self.session.get_inputs()}
        self.has_prosody = "prosody_features" in input_names
        self.has_sid = "sid" in input_names
        self.has_lid = "lid" in input_names

        _LOGGER.info(
            "Model loaded: %s (prosody=%s, sid=%s, lid=%s)",
            model_path,
            self.has_prosody,
            self.has_sid,
            self.has_lid,
        )

    def synthesize(
        self,
        text: str,
        *,
        language: str = "ja",
        speaker_id: int = 0,
        noise_scale: float = 0.667,
        length_scale: float = 1.0,
        noise_scale_w: float = 0.8,
    ) -> np.ndarray:
        """Synthesize text to int16 PCM audio array."""
        # Phonemize
        phonemizer = get_phonemizer(language)
        phonemes, prosody_info_list = phonemizer.phonemize_with_prosody(text)

        phoneme_ids: list[int] = []
        prosody_features: list[dict | None] = []

        for phoneme, prosody_info in zip(phonemes, prosody_info_list, strict=True):
            if phoneme in self.phoneme_id_map:
                ids = self.phoneme_id_map[phoneme]
                phoneme_ids.extend(ids)
                for _ in ids:
                    if prosody_info is not None:
                        prosody_features.append(
                            {
                                "a1": prosody_info.a1,
                                "a2": prosody_info.a2,
                                "a3": prosody_info.a3,
                            }
                        )
                    else:
                        prosody_features.append(None)
            else:
                _LOGGER.warning("Unknown phoneme: %s", phoneme)

        if not phoneme_ids:
            return np.array([], dtype=np.int16)

        # Build inputs
        text_input = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
        text_lengths = np.array([text_input.shape[1]], dtype=np.int64)
        scales = np.array(
            [noise_scale, length_scale, noise_scale_w], dtype=np.float32
        )

        inputs = {
            "input": text_input,
            "input_lengths": text_lengths,
            "scales": scales,
        }

        if self.has_sid:
            inputs["sid"] = np.array([speaker_id], dtype=np.int64)

        if self.has_prosody:
            if prosody_features:
                prosody_array = []
                for pf in prosody_features:
                    if pf is None:
                        prosody_array.append([0, 0, 0])
                    else:
                        prosody_array.append([pf["a1"], pf["a2"], pf["a3"]])
                prosody_np = np.expand_dims(
                    np.array(prosody_array, dtype=np.int64), 0
                )
            else:
                prosody_np = np.zeros(
                    (1, text_input.shape[1], 3), dtype=np.int64
                )
            inputs["prosody_features"] = prosody_np

        if self.has_lid:
            language_id = self.language_id_map.get(language, 0)
            inputs["lid"] = np.array([language_id], dtype=np.int64)

        # Inference
        start = time.perf_counter()
        outputs = self.session.run(None, inputs)
        audio = outputs[0].squeeze(0)
        audio = audio_float_to_int16(audio.squeeze())
        elapsed = time.perf_counter() - start

        duration_sec = len(audio) / SAMPLE_RATE
        rtf = elapsed / duration_sec if duration_sec > 0 else 0.0
        _LOGGER.info(
            "Synthesized %.2fs audio in %.2fs (RTF=%.2f)",
            duration_sec,
            elapsed,
            rtf,
        )

        return audio


def _resolve_language(synthesize_event: Synthesize, default: str) -> str:
    """Extract language from a Synthesize event.

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
        # "piper-plus-en" -> "en"
        for lang in SUPPORTED_LANGUAGES:
            if name.endswith(f"-{lang}"):
                return lang

    return default


def get_info() -> Info:
    """Return Wyoming Info describing this TTS service."""
    attribution = Attribution(
        name="piper-plus",
        url="https://github.com/ayutaz/piper-plus",
    )

    voices = []
    for lang in SUPPORTED_LANGUAGES:
        voices.append(
            TtsVoice(
                name=f"piper-plus-{lang}",
                attribution=attribution,
                installed=True,
                description=f"piper-plus ({lang})",
                version=None,
                languages=[lang],
            )
        )

    return Info(
        tts=[
            TtsProgram(
                name="piper-plus",
                attribution=attribution,
                installed=True,
                description="piper-plus multilingual TTS (6 languages)",
                version=None,
                voices=voices,
            )
        ]
    )
