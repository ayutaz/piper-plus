import json
import logging
import os
import wave
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime

from .config import PhonemeType, PiperConfig
from .const import BOS, EOS, PAD
from .phonemize.token_mapper import FIXED_PUA_MAPPING
from .util import audio_float_to_int16


_LOGGER = logging.getLogger(__name__)

# Short-text mitigation constants (keep in sync with other runtimes)
MIN_PHONEME_IDS = 40
SHORT_TEXT_CHARS = 10
SILENCE_PAD_MS = 300
TRIM_THRESHOLD_RMS = 0.01
TRIM_MIN_SAMPLES = 2205  # 22050 Hz * 0.1 s

# Optional: use shared ORT utilities when piper_train is available
try:
    from piper_train.ort_utils import (
        create_session_with_cache as _shared_create_session_with_cache,
        warmup_onnx_session as _shared_warmup,
    )

    _HAS_SHARED_ORT_UTILS = True
except ImportError:
    _HAS_SHARED_ORT_UTILS = False

# Multi-character phoneme to PUA character mapping — derived from token_mapper
# to guarantee consistency across the codebase.
MULTI_CHAR_TO_PUA = {k: chr(v) for k, v in FIXED_PUA_MAPPING.items()}


def _warmup_session(
    session: onnxruntime.InferenceSession,
    runs: int = 2,
    phoneme_length: int = 100,
) -> None:
    """Inline warmup for python_run (cannot import piper_train.ort_utils).

    Keep in sync with piper_train.ort_utils.warmup_onnx_session().
    """
    if os.environ.get("PIPER_DISABLE_WARMUP", "").lower() in ("1", "true", "yes"):
        return
    if runs <= 0:
        return
    try:
        phoneme_ids = np.full((1, phoneme_length), 8, dtype=np.int64)
        phoneme_ids[0, 0] = 1  # BOS
        phoneme_ids[0, -1] = 2  # EOS
        input_lengths = np.array([phoneme_length], dtype=np.int64)
        scales = np.array([0.667, 1.0, 0.8], dtype=np.float32)

        input_names = {inp.name for inp in session.get_inputs()}
        inputs = {
            "input": phoneme_ids,
            "input_lengths": input_lengths,
            "scales": scales,
        }
        if "sid" in input_names:
            inputs["sid"] = np.array([0], dtype=np.int64)
        if "lid" in input_names:
            inputs["lid"] = np.array([0], dtype=np.int64)
        if "prosody_features" in input_names:
            inputs["prosody_features"] = np.zeros(
                (1, phoneme_length, 3), dtype=np.int64
            )

        output_names = [o.name for o in session.get_outputs()]
        for _ in range(runs):
            session.run(output_names, inputs)

        _LOGGER.info("Warmup completed (%d runs)", runs)
    except Exception as e:
        _LOGGER.warning("Warmup failed (non-fatal): %s", e)


def _load_session_inline(
    model_path: str | Path,
    *,
    use_cuda: bool = False,
) -> onnxruntime.InferenceSession:
    """Create an InferenceSession using inline logic (no piper_train dependency).

    This is the fallback used when piper_train.ort_utils is not available.
    Keep in sync with piper_train.ort_utils.create_session_with_cache().
    """
    providers: list[str | tuple[str, dict[str, Any]]]
    if use_cuda:
        providers = [
            (
                "CUDAExecutionProvider",
                {"cudnn_conv_algo_search": "HEURISTIC"},
            )
        ]
    else:
        providers = ["CPUExecutionProvider"]

    # Keep in sync with piper_train.ort_utils.create_session_options()
    sess_options = onnxruntime.SessionOptions()
    sess_options.graph_optimization_level = (
        onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
    )
    sess_options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL

    # Thread settings: env var > auto-detect (sched_getaffinity > cpu_count)
    env_threads = os.environ.get("PIPER_INTRA_THREADS")
    intra_threads: int | None = None
    if env_threads is not None:
        try:
            intra_threads = max(1, min(int(env_threads), 4))
        except ValueError:
            _LOGGER.warning(
                "Ignoring invalid PIPER_INTRA_THREADS=%r; using auto-detected thread count",
                env_threads,
            )

    if intra_threads is None:
        try:
            logical_cores = len(os.sched_getaffinity(0))
        except (AttributeError, OSError):
            logical_cores = os.cpu_count() or 2
        intra_threads = min(logical_cores // 2 or 1, 4)

    sess_options.intra_op_num_threads = intra_threads
    sess_options.inter_op_num_threads = 1

    sess_options.enable_cpu_mem_arena = True
    sess_options.enable_mem_pattern = True
    sess_options.enable_mem_reuse = True

    # Dynamic block sizing: reduce latency variance (keep in sync with ort_utils)
    sess_options.add_session_config_entry("session.dynamic_block_base", "4")

    # === Model cache logic: Keep in sync with piper_train.ort_utils.create_session_with_cache() ===
    _disable_cache = os.environ.get("PIPER_DISABLE_CACHE", "").lower() in (
        "1",
        "true",
        "yes",
    )

    model_p = Path(model_path)
    device_label = "cuda0" if use_cuda else "cpu"
    cache_path = model_p.with_suffix(f".{device_label}.opt.onnx")
    sentinel_path = Path(str(cache_path) + ".ok")
    use_cached = not _disable_cache and cache_path.exists() and sentinel_path.exists()

    if _disable_cache:
        _LOGGER.info("Model cache disabled via PIPER_DISABLE_CACHE")
        effective_model_path = str(model_path)
    elif use_cached:
        _LOGGER.info("Loading pre-optimized model from %s", cache_path)
        sess_options.graph_optimization_level = (
            onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL
        )
        effective_model_path = str(cache_path)
    else:
        if cache_path.exists() and not sentinel_path.exists():
            _LOGGER.warning(
                "Removing incomplete cache %s (missing sentinel)", cache_path
            )
            try:
                cache_path.unlink()
            except OSError:
                pass
        try:
            sess_options.optimized_model_filepath = str(cache_path)
        except Exception as exc:
            _LOGGER.warning(
                "Could not set optimized model path %s: %s (continuing without cache)",
                cache_path,
                exc,
            )
        effective_model_path = str(model_path)

    session = onnxruntime.InferenceSession(
        effective_model_path,
        sess_options=sess_options,
        providers=providers,
    )

    # Write sentinel if cache was created
    if not _disable_cache and not use_cached and cache_path.exists():
        try:
            sentinel_path.write_text("ok")
            _LOGGER.info("Cache sentinel written: %s", sentinel_path)
        except OSError as exc:
            _LOGGER.warning("Failed to write sentinel %s: %s", sentinel_path, exc)

    return session


def _pad_phoneme_ids(
    phoneme_ids: list[int],
    pad_id: int,
    min_length: int = MIN_PHONEME_IDS,
) -> tuple[list[int], bool]:
    """Pad short phoneme_ids with silence tokens after BOS and before EOS.

    Returns (padded_ids, was_padded).
    """
    if len(phoneme_ids) >= min_length:
        return phoneme_ids, False

    needed = min_length - len(phoneme_ids)
    front = needed // 2
    back = needed - front

    # phoneme_ids: [BOS, ...phonemes..., EOS]
    bos = phoneme_ids[:1]
    body = phoneme_ids[1:-1]
    eos = phoneme_ids[-1:]

    padded = bos + [pad_id] * front + body + [pad_id] * back + eos
    return padded, True


def _trim_silence(
    audio: np.ndarray,
    threshold_rms: float = TRIM_THRESHOLD_RMS,
    window: int = 256,
    min_samples: int = TRIM_MIN_SAMPLES,
) -> np.ndarray:
    """Trim leading/trailing silence from int16 audio using windowed RMS."""
    if len(audio) <= min_samples:
        return audio

    float_audio = audio.astype(np.float32) / 32767.0
    n_windows = len(float_audio) // window

    if n_windows == 0:
        return audio

    # Compute per-window RMS
    truncated = float_audio[: n_windows * window].reshape(n_windows, window)
    rms = np.sqrt(np.mean(truncated**2, axis=1))

    # Find first and last window above threshold
    above = np.where(rms > threshold_rms)[0]
    if len(above) == 0:
        return audio[:min_samples]

    start_sample = above[0] * window
    end_sample = min((above[-1] + 1) * window, len(audio))

    length = end_sample - start_sample
    if length < min_samples:
        center = (start_sample + end_sample) // 2
        start_sample = max(0, center - min_samples // 2)
        end_sample = min(len(audio), start_sample + min_samples)
        start_sample = max(0, end_sample - min_samples)

    return audio[start_sample:end_sample]


@dataclass
class PiperVoice:
    session: onnxruntime.InferenceSession
    config: PiperConfig

    @staticmethod
    def load(
        model_path: str | Path,
        config_path: str | Path | None = None,
        use_cuda: bool = False,
    ) -> "PiperVoice":
        """Load an ONNX model and config."""
        if config_path is None:
            candidate = Path(f"{model_path}.json")
            if candidate.exists():
                config_path = candidate
            else:
                config_path = Path(model_path).parent / "config.json"

        with open(config_path, encoding="utf-8") as config_file:
            config_dict = json.load(config_file)

        if _HAS_SHARED_ORT_UTILS and not use_cuda:
            # CPU: use shared ORT utilities (avoids code duplication)
            session = _shared_create_session_with_cache(model_path, device="cpu")
            _shared_warmup(session)
        else:
            # CUDA or standalone: use inline implementation
            # (preserves cudnn_conv_algo_search=HEURISTIC for CUDA EP)
            # Keep in sync with piper_train.ort_utils
            session = _load_session_inline(model_path, use_cuda=use_cuda)
            _warmup_session(session)

        return PiperVoice(
            config=PiperConfig.from_dict(config_dict),
            session=session,
        )

    def phonemize(self, text: str) -> list[list[str]]:
        """Text to phonemes grouped by sentence."""
        if self.config.phoneme_type in (
            PhonemeType.MULTILINGUAL,
            PhonemeType.BILINGUAL,
        ):
            try:
                from .phonemize.multilingual import MultilingualPhonemizer
            except ImportError:
                _LOGGER.warning(
                    "MultilingualPhonemizer unavailable; falling back to JA phonemizer"
                )
            else:
                languages = (
                    ["ja", "en"]
                    if self.config.phoneme_type == PhonemeType.BILINGUAL
                    else ["ja", "en", "zh", "es", "fr", "pt"]
                )
                mp = MultilingualPhonemizer(languages=languages)
                phonemes = mp.phonemize(text)
                _LOGGER.debug("MultilingualPhonemizer: '%s' -> %s", text, phonemes)
                return [phonemes]

        if self.config.phoneme_type in (
            PhonemeType.OPENJTALK,
            PhonemeType.MULTILINGUAL,
            PhonemeType.BILINGUAL,
        ):
            from .phonemize.japanese import (
                get_default_dictionary,
                phonemize_japanese,
            )

            custom_dict = get_default_dictionary()
            result = (
                phonemize_japanese(text, custom_dict=custom_dict)
                if custom_dict
                else phonemize_japanese(text)
            )
            return [result]

        raise ValueError(f"Unsupported phoneme type: {self.config.phoneme_type}")

    def phonemes_to_ids(self, phonemes: list[str]) -> list[int]:
        """Phonemes to ids."""
        id_map = self.config.phoneme_id_map
        ids: list[int] = list(id_map[BOS])

        for phoneme in phonemes:
            if phoneme not in id_map:
                _LOGGER.warning("Missing phoneme from id map: %s", phoneme)
                continue

            ids.extend(id_map[phoneme])

            # Bilingual and multilingual models use intersperse padding (PAD between phonemes).
            if self.config.phoneme_type in (
                PhonemeType.BILINGUAL,
                PhonemeType.MULTILINGUAL,
            ):
                ids.extend(id_map[PAD])

        ids.extend(id_map[EOS])

        return ids

    def synthesize(
        self,
        text: str,
        wav_file: wave.Wave_write,
        speaker_id: int | None = None,
        length_scale: float | None = None,
        noise_scale: float | None = None,
        noise_w: float | None = None,
        sentence_silence: float = 0.0,
        volume: float = 1.0,
        language_id: int | None = None,
    ):
        """Synthesize WAV audio from text."""
        wav_file.setframerate(self.config.sample_rate)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setnchannels(1)  # mono

        for audio_bytes in self.synthesize_stream_raw(
            text,
            speaker_id=speaker_id,
            length_scale=length_scale,
            noise_scale=noise_scale,
            noise_w=noise_w,
            sentence_silence=sentence_silence,
            volume=volume,
            language_id=language_id,
        ):
            wav_file.writeframes(audio_bytes)

    def synthesize_stream_raw(
        self,
        text: str,
        speaker_id: int | None = None,
        length_scale: float | None = None,
        noise_scale: float | None = None,
        noise_w: float | None = None,
        sentence_silence: float = 0.0,
        volume: float = 1.0,
        language_id: int | None = None,
    ) -> Iterable[bytes]:
        """Synthesize raw audio per sentence from text."""
        # Strategy C: auto-inject silence padding for very short plain text
        is_short_text = (
            not text.lstrip().startswith("<speak>")
            and len(text.replace(" ", "")) <= SHORT_TEXT_CHARS
        )

        sentence_phonemes = self.phonemize(text)

        # 16-bit mono
        num_silence_samples = int(sentence_silence * self.config.sample_rate)
        silence_bytes = bytes(num_silence_samples * 2)

        # Pre-compute break silence for Strategy C
        if is_short_text:
            break_samples = int(self.config.sample_rate * SILENCE_PAD_MS / 1000)
            break_bytes = bytes(break_samples * 2)
        else:
            break_bytes = b""

        for phonemes in sentence_phonemes:
            phoneme_ids = self.phonemes_to_ids(phonemes)
            audio_bytes = self.synthesize_ids_to_raw(
                phoneme_ids,
                speaker_id=speaker_id,
                length_scale=length_scale,
                noise_scale=noise_scale,
                noise_w=noise_w,
                volume=volume,
                language_id=language_id,
            )
            yield break_bytes + audio_bytes + break_bytes + silence_bytes

    def synthesize_ids_to_raw(
        self,
        phoneme_ids: list[int],
        speaker_id: int | None = None,
        length_scale: float | None = None,
        noise_scale: float | None = None,
        noise_w: float | None = None,
        volume: float = 1.0,
        language_id: int | None = None,
    ) -> bytes:
        """Synthesize raw audio from phoneme ids."""
        if length_scale is None:
            length_scale = self.config.length_scale

        if noise_scale is None:
            noise_scale = self.config.noise_scale

        if noise_w is None:
            noise_w = self.config.noise_w

        # Strategy B: reduce noise for short sequences (check before padding)
        original_len = len(phoneme_ids)
        if original_len < MIN_PHONEME_IDS:
            ratio = max(0.0, min(original_len / MIN_PHONEME_IDS, 1.0))
            noise_scale *= max(0.5, ratio)
            noise_w *= max(0.4, ratio)

        # Strategy A: pad short sequences with silence tokens
        pad_id = 0
        phoneme_ids, was_padded = _pad_phoneme_ids(phoneme_ids, pad_id)

        phoneme_ids_array = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
        phoneme_ids_lengths = np.array([phoneme_ids_array.shape[1]], dtype=np.int64)
        scales = np.array(
            [noise_scale, length_scale, noise_w],
            dtype=np.float32,
        )

        args = {
            "input": phoneme_ids_array,
            "input_lengths": phoneme_ids_lengths,
            "scales": scales,
        }

        if self.config.num_speakers <= 1:
            speaker_id = None

        if (self.config.num_speakers > 1) and (speaker_id is None):
            # Default speaker
            speaker_id = 0

        # Include sid only for multi-speaker models
        if self.config.num_speakers > 1:
            if speaker_id is None:
                speaker_id = 0
            sid = np.expand_dims(np.array([speaker_id], dtype=np.int64), 0)
            args["sid"] = sid

        # Include lid for multilingual models
        input_names = {inp.name for inp in self.session.get_inputs()}
        if "lid" in input_names:
            lid_value = language_id if language_id is not None else 0
            lid = np.array([lid_value], dtype=np.int64)
            args["lid"] = lid

        # Include prosody_features if model requires them (zeros as default)
        if "prosody_features" in input_names:
            num_phonemes = phoneme_ids_array.shape[1]
            prosody = np.zeros((1, num_phonemes, 3), dtype=np.int64)
            args["prosody_features"] = prosody

        # Synthesize through Onnx
        audio = self.session.run(
            None,
            args,
        )[0].squeeze(0)
        audio = audio_float_to_int16(audio.squeeze(), volume=volume)

        # Strategy A: trim silence introduced by padding
        if was_padded:
            audio = _trim_silence(audio)

        return audio.tobytes()
