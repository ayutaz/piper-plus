import io
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
from .timing import (
    PhonemeTimingInfo,
    TimingResult,
    build_phoneme_id_reverse_map,
    durations_to_timing,
)
from .util import audio_float_to_int16


_LOGGER = logging.getLogger(__name__)

# Short-text mitigation constants (keep in sync with other runtimes — see
# docs/spec/short-text-contract.toml).
#
# Threshold note (issue #356): docs originally claimed VITS becomes unstable
# below ~40 phoneme IDs. Empirical measurements on the tsukuyomi 6lang
# model show a much lower true threshold — synthesis is stable at 8 IDs and
# weakens only below ~7. Setting MIN_PHONEME_IDS too high triggers Strategy
# A on already-stable inputs (e.g. 「こんにちは。」= 22 IDs), and the pad
# tokens leak as audible artifacts that post-trim cannot fully remove. We
# pick 15 as a conservative middle ground: roughly 2× the measured stable
# minimum, still well below typical short utterances like 「こんにちは。」.
MIN_PHONEME_IDS = 15

# Minimum body length (excluding BOS/EOS) for Strategy A to kick in.
# When the body is shorter than this (e.g. 「あ。」 with body of 2 IDs),
# padding-to-body ratio explodes and the pad tokens dominate over the
# actual content even with durations-based trim — bypassing Strategy A
# entirely produces a more natural single-phoneme utterance than padding
# does. The raw VITS output for tiny inputs is degraded but bounded;
# users invoking such inputs presumably accept that limitation.
MIN_BODY_FOR_STRATEGY_A = 3

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
        if "speaker_embedding" in input_names:
            emb_dim = 256
            for inp in session.get_inputs():
                if inp.name == "speaker_embedding":
                    if len(inp.shape) >= 2 and isinstance(inp.shape[1], int):
                        emb_dim = inp.shape[1]
                    break
            inputs["speaker_embedding"] = np.zeros((1, emb_dim), dtype=np.float32)
            inputs["speaker_embedding_mask"] = np.array([[0]], dtype=np.int64)

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
    min_body: int = MIN_BODY_FOR_STRATEGY_A,
) -> tuple[list[int], bool, int, int]:
    """Pad short phoneme_ids with silence tokens after BOS and before EOS.

    Returns ``(padded_ids, was_padded, front_pad, back_pad)`` where
    ``front_pad`` / ``back_pad`` are the numbers of pad tokens inserted
    after BOS and before EOS respectively (both 0 when no padding occurred).

    Skips padding entirely when the body (i.e. ``phoneme_ids`` excluding
    BOS/EOS) has fewer than ``min_body`` IDs. With such tiny bodies the
    padding-to-body ratio becomes so high that pad-token audio dominates
    the actual content; raw VITS output is preferable in that regime.
    """
    body_len = len(phoneme_ids) - 2  # exclude BOS / EOS
    if body_len < min_body:
        return phoneme_ids, False, 0, 0
    if len(phoneme_ids) >= min_length:
        return phoneme_ids, False, 0, 0

    needed = min_length - len(phoneme_ids)
    front = needed // 2
    back = needed - front

    # phoneme_ids: [BOS, ...phonemes..., EOS]
    bos = phoneme_ids[:1]
    body = phoneme_ids[1:-1]
    eos = phoneme_ids[-1:]

    padded = bos + [pad_id] * front + body + [pad_id] * back + eos
    return padded, True, front, back


# Maximum EOS duration (in frames) preserved during Strategy A trim.
# VITS tends to predict an inflated EOS duration under the padded context
# and emits an audible artifact ("こんにちはだぁ" instead of "こんにちは" —
# kun432 氏 issue #356 試聴フィードバック). Empirically, even modest
# clamping (6 frames) leaves a recognisable tail. Default to 0 so the
# entire EOS region is dropped along with the back padding; the unpadded
# PyPI 1.11.0 path keeps a similar tail but with no audible artifact, so
# losing it here is acceptable.
TRIM_EOS_MAX_FRAMES = 0


def _trim_padding_by_durations(
    audio: np.ndarray,
    durations: np.ndarray,
    front_pad: int,
    back_pad: int,
    hop_size: int,
    eos_max_frames: int = TRIM_EOS_MAX_FRAMES,
) -> np.ndarray:
    """Trim Strategy A padding using model durations (precise method).

    The padded sequence layout is::

        [BOS, pad×front_pad, ...body..., pad×back_pad, EOS]

    Each ``durations[i]`` is the frame count VITS assigned to phoneme ``i``.
    Multiplying the pad-token frame counts by ``hop_size`` gives the exact
    number of audio samples generated for the padding, which can be sliced
    off without relying on RMS thresholds.

    Trimming policy (issue #356):

    * **BOS + front padding**: stripped completely. VITS produces an
      audible "あ" at the start under the padded context.
    * **Back padding**: stripped completely.
    * **EOS**: keep only the first ``eos_max_frames`` frames (default
      ``TRIM_EOS_MAX_FRAMES`` = 0, i.e. drop the entire EOS region).
      0 was chosen empirically because even modest clamping (6 frames)
      left an audible "だぁ"-like tail under the padded context. Callers
      can pass a larger value to preserve a natural utterance tail.

    Returns ``audio`` unchanged when inputs are inconsistent.
    """
    if front_pad <= 0 and back_pad <= 0:
        return audio
    if durations is None or hop_size <= 0:
        return audio

    durations_1d = np.asarray(durations).reshape(-1)
    expected_len = 1 + front_pad + back_pad + 1  # BOS + pads + EOS
    if durations_1d.size < expected_len:
        return audio

    # BOS + front padding samples (stripped).
    front_samples = (
        int(durations_1d[0 : 1 + front_pad].sum() * hop_size) if front_pad > 0 else 0
    )

    # Back padding samples + EOS excess (over eos_max_frames) samples.
    back_pad_samples = (
        int(durations_1d[-(1 + back_pad) : -1].sum() * hop_size) if back_pad > 0 else 0
    )
    eos_frames = float(durations_1d[-1])
    eos_excess_frames = max(0.0, eos_frames - float(eos_max_frames))
    back_samples = back_pad_samples + int(eos_excess_frames * hop_size)

    start = max(0, front_samples)
    end = max(start, len(audio) - back_samples)
    if start >= len(audio) or end <= 0 or start >= end:
        return audio
    return audio[start:end]


def _trim_silence(
    audio: np.ndarray,
    threshold_rms: float = TRIM_THRESHOLD_RMS,
    window: int = 256,
    min_samples: int = TRIM_MIN_SAMPLES,
) -> np.ndarray:
    """Trim leading/trailing silence from int16 audio using windowed RMS.

    Fallback used when model durations are unavailable. Note that VITS pad
    tokens often produce voiced-looking audio (RMS > threshold), so this
    method is unreliable for Strategy A trimming; prefer
    :func:`_trim_padding_by_durations` whenever durations are present.
    """
    if len(audio) <= min_samples:
        return audio

    float_audio = audio.astype(np.float32) / 32768.0
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
        """Text to phonemes grouped by sentence.

        Plain text is split at sentence boundaries (`.`, `!`, `?`, `。`,
        `！`, `？`, `．`, including trailing closing punctuation) so callers
        such as :meth:`synthesize_stream_raw` can yield audio incrementally.
        SSML markup (``<speak>...``) is treated as a single unit to preserve
        its structure.

        Empty or whitespace-only input returns ``[]`` (no sentences) so
        callers do not waste cycles synthesizing a BOS/EOS-only chunk.
        """
        from .text_splitter import split_sentences

        stripped = text.lstrip()
        is_ssml = stripped.startswith("<speak") and (
            len(stripped) == len("<speak")
            or stripped[len("<speak")] in (">", " ", "\t", "\n", "\r")
        )
        if is_ssml:
            sentences = [text]
        elif not text.strip():
            sentences = []
        else:
            sentences = split_sentences(text) or [text]

        # NOTE: PhonemeType.BILINGUAL is a legacy compatibility branch for
        # v3/v4 JA+EN datasets that predate the 6-language multilingual model
        # (PR #218, v1.7). Modern models use MULTILINGUAL exclusively.
        # Deprecated: scheduled for removal in a future major release; new
        # models must not set phoneme_type="bilingual".
        if self.config.phoneme_type in (
            PhonemeType.MULTILINGUAL,
            PhonemeType.BILINGUAL,  # Deprecated: legacy v3/v4 bilingual datasets
        ):
            try:
                from .phonemize.multilingual import MultilingualPhonemizer
            except ImportError:
                _LOGGER.warning(
                    "MultilingualPhonemizer unavailable; falling back to JA phonemizer"
                )
            else:
                # Legacy bilingual = JA+EN only; multilingual = 6 trained languages.
                # SV/KO have G2P implementations but are not in any trained model
                # yet (see CLAUDE.md: "学習済みモデルは 6 言語"), so they are not
                # listed here.
                languages = (
                    ["ja", "en"]
                    if self.config.phoneme_type == PhonemeType.BILINGUAL
                    else ["ja", "en", "zh", "es", "fr", "pt"]
                )
                mp = MultilingualPhonemizer(languages=languages)
                results: list[list[str]] = []
                for sentence in sentences:
                    phonemes = mp.phonemize(sentence)
                    _LOGGER.debug(
                        "MultilingualPhonemizer: '%s' -> %s", sentence, phonemes
                    )
                    results.append(phonemes)
                return results

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
            results = []
            for sentence in sentences:
                result = (
                    phonemize_japanese(sentence, custom_dict=custom_dict)
                    if custom_dict
                    else phonemize_japanese(sentence)
                )
                results.append(result)
            return results

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
        """Synthesize WAV audio from text.

        Multi-sentence input is split at sentence boundaries by
        :meth:`phonemize` and rendered chunk-by-chunk via
        :meth:`synthesize_stream_raw`. The chunks are concatenated into a
        single WAV file. SSML markup (``<speak>...``) is treated as a
        single unit.
        """
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
        """Synthesize raw audio per sentence from text.

        Yields one PCM 16-bit mono audio chunk per sentence. Sentence
        boundaries are detected by :func:`piper.text_splitter.split_sentences`
        (mirrors the Rust / C# / Go / C++ implementations) so a single call
        with multi-sentence input produces multiple chunks suitable for
        streaming clients (e.g. HTTP ``?streaming=true``).

        SSML input (``<speak>...``) is yielded as a single chunk to preserve
        the markup structure.

        Each chunk is wrapped with ``sentence_silence`` worth of trailing
        silence; very short plain-text inputs additionally receive
        Strategy C silence padding around every chunk.
        """
        # Strategy C: auto-inject silence padding for very short plain text
        is_short_text = (
            not text.lstrip().startswith(("<speak>", "<speak "))
            and sum(1 for c in text if not c.isspace()) <= SHORT_TEXT_CHARS
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

    def _synthesize_ids_core(
        self,
        phoneme_ids: list[int],
        speaker_id: int | None = None,
        length_scale: float | None = None,
        noise_scale: float | None = None,
        noise_w: float | None = None,
        volume: float = 1.0,
        language_id: int | None = None,
    ) -> tuple[bytes, "np.ndarray | None", list[int]]:
        """Core synthesis returning ``(audio_bytes, durations, original_phoneme_ids)``.

        Internal method that runs the full synthesis pipeline:

        1. Applies short-text mitigation (Strategy A padding + Strategy B
           noise scale adjustment) for inputs shorter than ``MIN_PHONEME_IDS``.
        2. Runs ONNX inference with the configured parameters.
        3. Trims silence introduced by padding (when applicable).

        Parameters
        ----------
        phoneme_ids : list[int]
            Phoneme IDs including BOS (first) and EOS (last) tokens.
            Saved as ``original_phoneme_ids`` before any padding is applied.
        speaker_id, length_scale, noise_scale, noise_w, volume, language_id
            See :meth:`synthesize_with_timing` for parameter descriptions.

        Returns
        -------
        tuple[bytes, np.ndarray | None, list[int]]
            A 3-tuple of:

            - ``audio_bytes`` : PCM 16-bit mono audio (silence trimmed if padded).
            - ``durations`` : 1-D float32 array of frame counts per phoneme,
              or ``None`` if the model has no ``durations`` output.
              Length matches the *padded* phoneme sequence; callers should
              align with ``original_phoneme_ids`` length when computing timing.
            - ``original_phoneme_ids`` : The input ``phoneme_ids`` list,
              preserved before any padding mutation.

        Notes
        -----
        This is a private helper. Public APIs:

        - :meth:`synthesize_ids_to_raw` for raw bytes (backward-compat wrapper).
        - :meth:`synthesize_with_timing` for full text-to-speech with timing.
        """
        original_phoneme_ids = list(phoneme_ids)

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
        phoneme_ids, was_padded, front_pad, back_pad = _pad_phoneme_ids(
            phoneme_ids, pad_id
        )

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

        # speaker_embedding / speaker_embedding_mask are always declared by
        # export_onnx.py as a forward-compat hook, but the bundled checkpoints
        # are not trained for zero-shot speaker transfer (spk_proj is lazy-
        # initialised and never sees gradients). Feed zeros with mask=0 so the
        # torch.where branch in models.py:VitsModel.infer falls back to the
        # trained speaker_id / lid conditioning.
        if "speaker_embedding" in input_names:
            emb_dim = 256
            for inp in self.session.get_inputs():
                if inp.name == "speaker_embedding":
                    if len(inp.shape) >= 2 and isinstance(inp.shape[1], int):
                        emb_dim = inp.shape[1]
                    break
            args["speaker_embedding"] = np.zeros((1, emb_dim), dtype=np.float32)
            args["speaker_embedding_mask"] = np.array([[0]], dtype=np.int64)

        # Synthesize through Onnx
        output_names = [o.name for o in self.session.get_outputs()]
        _outputs = self.session.run(output_names, args)

        # Extract audio by name (not index) for robustness across models
        # that may list outputs in a different order.
        if "output" in output_names:
            audio_idx = output_names.index("output")
        else:
            audio_idx = 0
        audio = _outputs[audio_idx].squeeze(0)

        # Extract durations by name (not index) for robustness
        durations = None
        if "durations" in output_names:
            dur_idx = output_names.index("durations")
            if dur_idx < len(_outputs):
                durations = _outputs[dur_idx].squeeze()
        audio = audio_float_to_int16(audio.squeeze(), volume=volume)

        # Strategy A: trim silence introduced by padding.
        # Prefer durations-based precise trim; fall back to RMS when the model
        # has no durations output (older VITS exports).
        if was_padded:
            if durations is not None:
                audio = _trim_padding_by_durations(
                    audio,
                    durations,
                    front_pad,
                    back_pad,
                    self.config.hop_size,
                )
            else:
                audio = _trim_silence(audio)

        return audio.tobytes(), durations, original_phoneme_ids

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
        audio_bytes, _, _ = self._synthesize_ids_core(
            phoneme_ids,
            speaker_id=speaker_id,
            length_scale=length_scale,
            noise_scale=noise_scale,
            noise_w=noise_w,
            volume=volume,
            language_id=language_id,
        )
        return audio_bytes

    @property
    def has_duration_output(self) -> bool:
        """Whether the ONNX model exposes a ``durations`` output tensor.

        Returns
        -------
        bool
            ``True`` if the loaded ONNX session has an output named
            ``'durations'`` (Duration Predictor output), ``False`` otherwise.

        Notes
        -----
        When ``False``, calling :meth:`synthesize_with_timing` will return
        ``None`` for the timing result. Older VITS models exported without
        ``durations`` are still supported for plain audio synthesis.
        """
        return "durations" in {o.name for o in self.session.get_outputs()}

    def synthesize_with_timing(
        self,
        text: str,
        wav_file: wave.Wave_write | None = None,
        *,
        speaker_id: int | None = None,
        length_scale: float | None = None,
        noise_scale: float | None = None,
        noise_w: float | None = None,
        sentence_silence: float = 0.0,
        volume: float = 1.0,
        language_id: int | None = None,
    ) -> tuple[bytes, TimingResult | None]:
        """Synthesize audio with phoneme timing information.

        Synthesizes ``text`` to speech and returns both the raw WAV bytes
        and per-phoneme timing data (when supported by the model).

        Parameters
        ----------
        text : str
            Input text to synthesize.
        wav_file : wave.Wave_write or None, optional
            If provided, audio frames are also written to this file object
            in addition to being returned in the tuple. The caller must have
            already opened the file in 'wb' mode.
        speaker_id : int or None, optional
            Speaker ID for multi-speaker models. Defaults to None (uses
            speaker 0 if the model is multi-speaker).
        length_scale : float or None, optional
            Speech speed multiplier. None uses the config default.
        noise_scale : float or None, optional
            Speaker variation noise scale. None uses the config default.
        noise_w : float or None, optional
            Phoneme width noise scale. None uses the config default.
        sentence_silence : float, default 0.0
            Seconds of silence to insert between sentences.
        volume : float, default 1.0
            Volume multiplier applied to the output samples.
        language_id : int or None, optional
            Language ID for multilingual models. Required for models that
            expose an ``lid`` input tensor.

        Returns
        -------
        tuple[bytes, TimingResult | None]
            ``(wav_bytes, timing_result)`` where:

            - ``wav_bytes`` : Complete WAV file content (RIFF header + PCM).
            - ``timing_result`` : :class:`piper.timing.TimingResult` with
              per-phoneme entries, or ``None`` if the model does not output
              a ``durations`` tensor (check ``self.has_duration_output``).

        Notes
        -----
        Cross-runtime compatibility: timing values are byte-for-byte identical
        to the Rust, Go, C++, C#, and WASM implementations.

        Multi-sentence input is handled by accumulating cumulative ``start_ms``
        offsets across sentences, including any ``sentence_silence`` gap.

        Examples
        --------
        >>> voice = PiperVoice.load('model.onnx', config_path='config.json')
        >>> wav_bytes, timing = voice.synthesize_with_timing('Hello world')
        >>> if timing is not None:
        ...     for p in timing.phonemes:
        ...         print(f'{p.phoneme}: {p.start_ms:.1f}-{p.end_ms:.1f} ms')
        """
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setframerate(self.config.sample_rate)
            wf.setsampwidth(2)
            wf.setnchannels(1)

            all_timing_entries: list[PhonemeTimingInfo] = []
            cumulative_ms = 0.0

            # Build reverse map for phoneme display names
            pua_reverse = {chr(v): k for k, v in FIXED_PUA_MAPPING.items()}
            reverse_map = build_phoneme_id_reverse_map(
                self.config.phoneme_id_map, pua_reverse
            )

            sentence_phonemes = self.phonemize(text)
            num_silence_samples = int(sentence_silence * self.config.sample_rate)
            all_raw_frames: list[bytes] = []

            for phonemes in sentence_phonemes:
                phoneme_ids = self.phonemes_to_ids(phonemes)
                audio_bytes, durations, original_ids = self._synthesize_ids_core(
                    phoneme_ids,
                    speaker_id=speaker_id,
                    length_scale=length_scale,
                    noise_scale=noise_scale,
                    noise_w=noise_w,
                    volume=volume,
                    language_id=language_id,
                )

                wf.writeframes(audio_bytes)
                all_raw_frames.append(audio_bytes)

                if durations is not None:
                    tokens = [
                        reverse_map.get(pid, f"ph_{i}")
                        for i, pid in enumerate(original_ids)
                    ]
                    dur_list = durations.tolist()

                    # Align lengths (durations may include padding)
                    if len(dur_list) != len(tokens):
                        _LOGGER.debug(
                            "Duration-token length mismatch: durations=%d, tokens=%d; "
                            "truncating to %d",
                            len(dur_list),
                            len(tokens),
                            min(len(dur_list), len(tokens)),
                        )
                    min_len = min(len(dur_list), len(tokens))
                    dur_list = dur_list[:min_len]
                    tokens = tokens[:min_len]

                    timing = durations_to_timing(
                        dur_list,
                        tokens,
                        self.config.sample_rate,
                        hop_length=self.config.hop_size,
                    )

                    for p in timing.phonemes:
                        all_timing_entries.append(
                            PhonemeTimingInfo(
                                phoneme=p.phoneme,
                                start_ms=p.start_ms + cumulative_ms,
                                end_ms=p.end_ms + cumulative_ms,
                                duration_ms=p.duration_ms,
                            )
                        )
                    cumulative_ms += timing.total_duration_ms

                if sentence_silence > 0:
                    silence_ms = sentence_silence * 1000.0
                    cumulative_ms += silence_ms
                    silence_frame = bytes(num_silence_samples * 2)
                    wf.writeframes(silence_frame)
                    all_raw_frames.append(silence_frame)

        # Also write to caller's wav_file if provided
        if wav_file is not None:
            wav_file.setframerate(self.config.sample_rate)
            wav_file.setsampwidth(2)
            wav_file.setnchannels(1)
            for frame_data in all_raw_frames:
                wav_file.writeframes(frame_data)

        timing_result = None
        if all_timing_entries:
            timing_result = TimingResult(
                phonemes=all_timing_entries,
                total_duration_ms=cumulative_ms,
                sample_rate=self.config.sample_rate,
            )

        wav_buf.seek(0)
        return wav_buf.getvalue(), timing_result
