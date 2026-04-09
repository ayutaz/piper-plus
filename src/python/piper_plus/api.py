"""PiperPlus -- high-level Python API for multilingual neural TTS."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from piper_plus._model_resolver import (
    MODEL_ALIASES,
    resolve_model,
)
from piper_plus.audio import AudioResult
from piper_plus.engine import (
    create_ort_session,
    load_config,
    synthesize as engine_synthesize,
    warmup_session,
)


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

    Uses ``piper_plus.engine`` for ONNX inference (no ``piper_train``
    dependency) and ``piper_plus_g2p`` for phonemization.

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
        # Resolve model path
        onnx_path, config_path = resolve_model(
            model, config=config, download=download, cache_dir=cache_dir
        )
        self._onnx_path = onnx_path
        self._config_path = config_path

        # Load config via engine helper (no piper_train dependency)
        self._config: dict = load_config(config_path)

        self._phoneme_id_map: dict[str, list[int]] = self._config["phoneme_id_map"]
        self._language_id_map: dict[str, int] = self._config.get("language_id_map", {})
        self._speaker_id_map: dict[str, int] = self._config.get("speaker_id_map", {})
        self._sample_rate: int = self._config.get("audio", {}).get("sample_rate", 22050)

        # Inference scales
        self.noise_scale = noise_scale
        self.length_scale = length_scale
        self.noise_scale_w = noise_scale_w

        # Determine language string for phonemizer
        if self._language_id_map:
            self._language = "-".join(sorted(self._language_id_map.keys()))
        else:
            self._language = "ja"

        # Create ORT session via engine (no piper_train dependency)
        effective_device = device
        if device == "auto":
            effective_device = "cpu"
            try:
                import onnxruntime as _ort  # noqa: PLC0415

                if "CUDAExecutionProvider" in _ort.get_available_providers():
                    effective_device = "gpu"
            except Exception:
                pass

        logger.info("Loading model from %s", onnx_path)
        self._session = create_ort_session(str(onnx_path), device=effective_device)
        logger.info("Loaded model (providers: %s)", self._session.get_providers())

        # Detect model capabilities from input names
        input_names = {inp.name for inp in self._session.get_inputs()}
        self._has_prosody = "prosody_features" in input_names
        self._has_sid = "sid" in input_names
        self._has_lid = "lid" in input_names

        # Warmup via engine
        warmup_session(self._session, self._config)

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

        Raises:
            ValueError: If scale parameters are out of valid range.
        """
        if not text or not text.strip():
            return AudioResult(
                audio=np.array([], dtype=np.int16), sample_rate=self.sample_rate
            )

        if not (0.0 < self.noise_scale <= 2.0):
            raise ValueError(f"noise_scale must be in (0, 2.0], got {self.noise_scale}")
        if not (0.1 <= self.length_scale <= 5.0):
            raise ValueError(
                f"length_scale must be in [0.1, 5.0], got {self.length_scale}"
            )
        if not (0.0 <= self.noise_scale_w <= 2.0):
            raise ValueError(f"noise_w must be in [0, 2.0], got {self.noise_scale_w}")

        audio_int16 = self._synthesize_raw(
            text, speaker_id=speaker_id, language=language
        )
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

        Phonemization uses ``piper_plus_g2p`` directly (no ``piper_train``
        dependency).  Falls back to ``piper_train.infer_onnx`` only if
        ``piper_plus_g2p`` is not installed.
        """
        phoneme_ids, prosody_features_data, lid = self._phonemize(
            text, language=language
        )

        if not phoneme_ids:
            return np.array([], dtype=np.int16)

        # Resolve language ID
        language_id: int | None = None
        if self._has_lid:
            if language and language in self._language_id_map:
                language_id = self._language_id_map[language]
            elif lid is not None:
                language_id = lid
            else:
                language_id = 0

        # Delegate to engine.synthesize
        t0 = time.perf_counter()
        audio_int16 = engine_synthesize(
            self._session,
            phoneme_ids,
            config=self._config,
            speaker_id=speaker_id,
            language_id=language_id,
            noise_scale=self.noise_scale,
            length_scale=self.length_scale,
            noise_w=self.noise_scale_w,
            prosody_features=prosody_features_data,
        )
        elapsed = time.perf_counter() - t0

        audio_duration = len(audio_int16) / self._sample_rate
        rtf = elapsed / audio_duration if audio_duration > 0 else 0.0
        logger.debug(
            "Synthesized %.2fs audio in %.3fs (RTF=%.2f)",
            audio_duration,
            elapsed,
            rtf,
        )

        return audio_int16

    def _phonemize(
        self,
        text: str,
        *,
        language: str | None = None,
    ) -> tuple[list[int], list[dict | None], int | None]:
        """Convert text to phoneme IDs, prosody data, and detected language ID.

        Tries ``piper_plus_g2p`` first.  Falls back to
        ``piper_train.infer_onnx.text_to_phoneme_ids_and_prosody`` if
        ``piper_plus_g2p`` is not available.

        Returns:
            (phoneme_ids, prosody_features, detected_language_id)
        """
        effective_language = language if language else self._language

        # --- Primary path: piper_plus_g2p (standalone, no piper_train) ---
        try:
            from piper_plus_g2p import (  # noqa: PLC0415
                UnicodeLanguageDetector,
                get_phonemizer,
            )
            from piper_plus_g2p.encode.encoder import PiperEncoder  # noqa: PLC0415
            from piper_plus_g2p.encode.pua import map_token  # noqa: PLC0415
        except ImportError:
            # Fall back to piper_train path
            return self._phonemize_via_piper_train(text, language=language)

        # For multilingual models with JA input, auto-promote to
        # multilingual phonemizer so intersperse padding is correct.
        lang_id_map = self._language_id_map if self._has_lid else None
        if (
            lang_id_map
            and "-" not in effective_language
            and len(lang_id_map) > 1
            and effective_language == "ja"
        ):
            effective_language = "-".join(sorted(lang_id_map.keys()))

        phonemizer = get_phonemizer(effective_language)
        phonemes, prosody_info_list = phonemizer.phonemize_with_prosody(text)

        encoder = PiperEncoder(self._phoneme_id_map)

        # JA-only models: convert tokens directly (no encoder wrapping)
        if (language or self._language) == "ja" and (
            not lang_id_map or len(lang_id_map) <= 1
        ):
            phoneme_ids: list[int] = []
            prosody_features: list[dict | None] = []
            for phoneme, prosody_info in zip(phonemes, prosody_info_list, strict=True):
                mapped = map_token(phoneme)
                for ch in mapped:
                    if ch in self._phoneme_id_map:
                        ids = self._phoneme_id_map[ch]
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
            return phoneme_ids, prosody_features, None

        # All other languages / multilingual: use PiperEncoder
        result_ids, result_prosody = encoder.encode_with_prosody(
            phonemes, prosody_info_list
        )
        prosody_out: list[dict | None] = []
        for p in result_prosody:
            if p is not None:
                prosody_out.append({"a1": p.a1, "a2": p.a2, "a3": p.a3})
            else:
                prosody_out.append(None)

        # Detect dominant language for lid
        detected_lid: int | None = None
        if self._has_lid and self._language_id_map:
            try:
                languages = list(self._language_id_map.keys())
                detector = UnicodeLanguageDetector(
                    languages, default_latin_language="en"
                )
                context_has_kana = detector.has_kana(text)
                counts: dict[str, int] = {}
                for ch in text:
                    lang = detector.detect_char(ch, context_has_kana=context_has_kana)
                    if lang is not None:
                        counts[lang] = counts.get(lang, 0) + 1
                if counts:
                    dominant = max(counts, key=lambda k: counts[k])
                    detected_lid = self._language_id_map.get(dominant, 0)
                else:
                    detected_lid = self._language_id_map.get("en", 0)
            except Exception:
                detected_lid = 0

        return result_ids, prosody_out, detected_lid

    def _phonemize_via_piper_train(
        self,
        text: str,
        *,
        language: str | None = None,
    ) -> tuple[list[int], list[dict | None], int | None]:
        """Fallback phonemization using piper_train (legacy path)."""
        try:
            from piper_train.infer_onnx import (  # noqa: PLC0415
                _detect_dominant_language,
                text_to_phoneme_ids_and_prosody,
            )
        except ImportError:
            raise ImportError(
                "Neither piper_plus_g2p nor piper_train is installed. "
                "Install one of: pip install piper-plus-g2p  OR  "
                "uv pip install -e src/python"
            ) from None

        effective_language = language if language else self._language
        lang_id_map = self._language_id_map if self._has_lid else None

        phoneme_ids, prosody_data = text_to_phoneme_ids_and_prosody(
            text,
            self._phoneme_id_map,
            language=effective_language,
            language_id_map=lang_id_map,
        )

        detected_lid: int | None = None
        if self._has_lid and self._language_id_map:
            if language and language in self._language_id_map:
                detected_lid = self._language_id_map[language]
            else:
                detected_lid = _detect_dominant_language(text, self._language_id_map)

        return phoneme_ids, prosody_data, detected_lid
