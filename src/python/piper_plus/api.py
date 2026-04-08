"""PiperPlus -- high-level Python API for multilingual neural TTS."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Iterator

import numpy as np

from piper_plus._model_resolver import (
    MODEL_ALIASES,
    ModelNotFoundError,
    resolve_model,
)
from piper_plus.audio import AudioResult


logger = logging.getLogger(__name__)

# Sentence boundary pattern for streaming split.
# Matches period, exclamation, question mark (including CJK variants)
# followed by optional closing quotes/brackets and whitespace or end-of-string.
_SENTENCE_BOUNDARY = re.compile(
    r"(?<=[.!?\u3002\uff01\uff1f])[\"'\u300d\uff09\u3011\u3015)]*"
    r"(?:\s+|$)"
)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences at common sentence boundaries.

    Returns a list of non-empty sentence strings.
    """
    parts = _SENTENCE_BOUNDARY.split(text)
    return [s.strip() for s in parts if s.strip()]


class PiperPlus:
    """High-level text-to-speech engine.

    Wraps the low-level ONNX inference pipeline from ``piper_train``
    into a simple, user-friendly interface.

    Example::

        tts = PiperPlus("tsukuyomi")
        result = tts.synthesize("Hello, world!")
        result.save("hello.wav")
        print(f"Duration: {result.duration:.2f}s")

    Args:
        model: Model file path, alias (``"tsukuyomi"``, ``"base"``),
            or HuggingFace repo ID (``"ayousanz/piper-plus-tsukuyomi-chan"``).
        config: Explicit config.json path.  Auto-detected when *None*.
        device: Inference device: ``"cpu"``, ``"gpu"``, or ``"auto"``.
        download: Whether to download the model if not found locally.
        cache_dir: Override the default model cache directory.
        noise_scale: Controls phoneme-level variability (default 0.667).
        length_scale: Controls speaking speed (default 1.0).
        noise_scale_w: Controls stochastic duration variability (default 0.8).
    """

    def __init__(
        self,
        model: str,
        *,
        config: str | None = None,
        device: str = "auto",
        download: bool = True,
        cache_dir: Path | None = None,
        noise_scale: float = 0.667,
        length_scale: float = 1.0,
        noise_scale_w: float = 0.8,
    ) -> None:
        # Import piper_train components (may not be installed)
        try:
            from piper_train.ort_utils import (  # noqa: PLC0415
                create_session_with_cache,
                warmup_onnx_session,
            )
            from piper_train.vits.utils import audio_float_to_int16  # noqa: PLC0415
        except ImportError:
            raise ImportError(
                "piper_train is required for the PiperPlus API. "
                "Install the piper-plus package with: "
                "pip install piper-plus  OR  uv pip install -e src/python"
            ) from None

        self._audio_float_to_int16 = audio_float_to_int16

        # Resolve model path
        onnx_path, config_path = resolve_model(
            model, config=config, download=download, cache_dir=cache_dir
        )
        self._onnx_path = onnx_path
        self._config_path = config_path

        # Load config
        with open(config_path, encoding="utf-8") as f:
            self._config: dict = json.load(f)

        self._phoneme_id_map: dict[str, list[int]] = self._config["phoneme_id_map"]
        self._language_id_map: dict[str, int] = self._config.get("language_id_map", {})
        self._speaker_id_map: dict[str, int] = self._config.get("speaker_id_map", {})
        self._sample_rate: int = self._config.get(
            "audio", {}
        ).get("sample_rate", 22050)

        # Inference scales
        self.noise_scale = noise_scale
        self.length_scale = length_scale
        self.noise_scale_w = noise_scale_w

        # Determine language string for phonemizer
        if self._language_id_map:
            self._language = "-".join(sorted(self._language_id_map.keys()))
        else:
            self._language = "ja"

        # Create ORT session
        logger.info("Loading model from %s", onnx_path)
        self._session = create_session_with_cache(str(onnx_path), device=device)
        logger.info(
            "Loaded model (providers: %s)", self._session.get_providers()
        )

        # Detect model capabilities from input names
        input_names = {inp.name for inp in self._session.get_inputs()}
        self._has_prosody = "prosody_features" in input_names
        self._has_sid = "sid" in input_names
        self._has_lid = "lid" in input_names

        # Warmup
        warmup_onnx_session(self._session)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def sample_rate(self) -> int:
        """Audio sample rate of the loaded model (Hz)."""
        return self._sample_rate

    @property
    def languages(self) -> list[str]:
        """List of supported language codes."""
        if self._language_id_map:
            return sorted(self._language_id_map.keys())
        return [self._language]

    @property
    def speakers(self) -> dict[str, int]:
        """Speaker name to ID mapping (empty for single-speaker models)."""
        return dict(self._speaker_id_map)

    @property
    def config(self) -> dict:
        """Raw model config dictionary."""
        return dict(self._config)

    # ------------------------------------------------------------------
    # Core synthesis
    # ------------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        *,
        speaker_id: int = 0,
        language: str | None = None,
    ) -> AudioResult:
        """Synthesize speech from text.

        Args:
            text: Input text to synthesize.
            speaker_id: Speaker ID for multi-speaker models (default 0).
            language: Override language code.  When *None*, the language
                is auto-detected from the text for multilingual models.

        Returns:
            :class:`AudioResult` containing the generated audio.
        """
        audio_int16 = self._synthesize_raw(text, speaker_id=speaker_id, language=language)
        return AudioResult(audio=audio_int16, sample_rate=self._sample_rate)

    def synthesize_stream(
        self,
        text: str,
        *,
        speaker_id: int = 0,
        language: str | None = None,
    ) -> Iterator[AudioResult]:
        """Synthesize speech sentence-by-sentence, yielding chunks.

        Splits *text* at sentence boundaries and yields one
        :class:`AudioResult` per sentence.  Useful for streaming
        playback or real-time applications.

        Args:
            text: Input text to synthesize.
            speaker_id: Speaker ID for multi-speaker models.
            language: Override language code.

        Yields:
            :class:`AudioResult` for each sentence.
        """
        sentences = _split_sentences(text)
        if not sentences:
            return

        for sentence in sentences:
            audio_int16 = self._synthesize_raw(
                sentence, speaker_id=speaker_id, language=language
            )
            yield AudioResult(audio=audio_int16, sample_rate=self._sample_rate)

    def tts_to_file(
        self,
        text: str,
        path: str | Path,
        *,
        speaker_id: int = 0,
        language: str | None = None,
    ) -> AudioResult:
        """Synthesize text and save directly to a WAV file.

        Args:
            text: Input text to synthesize.
            path: Output WAV file path.
            speaker_id: Speaker ID for multi-speaker models.
            language: Override language code.

        Returns:
            :class:`AudioResult` for the generated audio.
        """
        result = self.synthesize(text, speaker_id=speaker_id, language=language)
        result.save(path)
        return result

    # ------------------------------------------------------------------
    # Class methods
    # ------------------------------------------------------------------

    @staticmethod
    def list_models() -> dict[str, dict[str, str]]:
        """Return dictionary of built-in model aliases.

        Returns:
            Mapping from alias name to model metadata (repo_id, files).
        """
        return dict(MODEL_ALIASES)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _synthesize_raw(
        self,
        text: str,
        *,
        speaker_id: int = 0,
        language: str | None = None,
    ) -> np.ndarray:
        """Run the full phonemize -> inference pipeline.

        Returns int16 PCM audio as a 1-D numpy array.
        """
        from piper_train.infer_onnx import (  # noqa: PLC0415
            _detect_dominant_language,
            text_to_phoneme_ids_and_prosody,
        )

        # Determine effective language for phonemizer
        effective_language = language if language else self._language

        # Convert text to phoneme IDs + prosody
        phoneme_ids, prosody_features_data = text_to_phoneme_ids_and_prosody(
            text,
            self._phoneme_id_map,
            language=effective_language,
            language_id_map=self._language_id_map if self._has_lid else None,
        )

        if not phoneme_ids:
            return np.array([], dtype=np.int16)

        # Build ONNX inputs
        text_array = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
        text_lengths = np.array([text_array.shape[1]], dtype=np.int64)
        scales = np.array(
            [self.noise_scale, self.length_scale, self.noise_scale_w],
            dtype=np.float32,
        )

        inputs: dict[str, np.ndarray] = {
            "input": text_array,
            "input_lengths": text_lengths,
            "scales": scales,
        }

        # Speaker ID
        if self._has_sid:
            inputs["sid"] = np.array([speaker_id], dtype=np.int64)

        # Language ID (auto-detect from text for multilingual models)
        if self._has_lid:
            if language and language in self._language_id_map:
                lid = self._language_id_map[language]
            elif self._language_id_map:
                lid = _detect_dominant_language(text, self._language_id_map)
            else:
                lid = 0
            inputs["lid"] = np.array([lid], dtype=np.int64)

        # Prosody features
        if self._has_prosody:
            if prosody_features_data:
                prosody_array = []
                for pf in prosody_features_data:
                    if pf is None:
                        prosody_array.append([0, 0, 0])
                    else:
                        prosody_array.append([pf["a1"], pf["a2"], pf["a3"]])
                inputs["prosody_features"] = np.expand_dims(
                    np.array(prosody_array, dtype=np.int64), 0
                )
            else:
                inputs["prosody_features"] = np.zeros(
                    (1, text_array.shape[1], 3), dtype=np.int64
                )

        # Run inference
        t0 = time.perf_counter()
        outputs = self._session.run(None, inputs)
        audio_float = outputs[0].squeeze((0, 1))
        elapsed = time.perf_counter() - t0

        audio_int16 = self._audio_float_to_int16(audio_float)

        audio_duration = len(audio_int16) / self._sample_rate
        rtf = elapsed / audio_duration if audio_duration > 0 else 0.0
        logger.debug(
            "Synthesized %.2fs audio in %.3fs (RTF=%.2f)",
            audio_duration,
            elapsed,
            rtf,
        )

        return audio_int16
