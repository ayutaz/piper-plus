#!/usr/bin/env python3
import argparse
import json
import logging
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

from .ort_utils import create_session_with_cache, warmup_onnx_session
from .vits.utils import audio_float_to_int16
from .vits.wavfile import write as write_wav


_LOGGER = logging.getLogger("piper_train.infer_onnx")

# --- Short-text synthesis quality constants ---
# Minimum phoneme_ids length below which padding/scale adjustment is applied
MIN_PHONEME_IDS = 40
# RMS threshold for silence trimming (float audio range)
TRIM_THRESHOLD_RMS = 0.01
# Minimum audio samples to keep after trimming (22050 Hz * 0.1s)
TRIM_MIN_SAMPLES = 2205


def _pad_phoneme_ids(
    phoneme_ids: list[int],
    prosody_features: list[dict | None] | None,
) -> tuple[list[int], list[dict | None] | None, bool]:
    """Strategy A: Pad short phoneme_ids with silence tokens.

    Inserts pause tokens (ID=0, blank/pad) evenly after BOS and before EOS
    until the sequence reaches MIN_PHONEME_IDS length.

    Returns:
        (padded_phoneme_ids, padded_prosody_features, was_padded)
    """
    n = len(phoneme_ids)
    if n >= MIN_PHONEME_IDS:
        return phoneme_ids, prosody_features, False

    pad_total = MIN_PHONEME_IDS - n
    pad_front = pad_total // 2
    pad_back = pad_total - pad_front

    # Insert after BOS (index 1) and before EOS (last element)
    # BOS is typically phoneme_ids[0], EOS is phoneme_ids[-1]
    bos = phoneme_ids[:1]
    eos = phoneme_ids[-1:]
    middle = phoneme_ids[1:-1] if n > 1 else []

    padded = bos + [0] * pad_front + middle + [0] * pad_back + eos

    # Pad prosody_features correspondingly
    padded_prosody: list[dict | None] | None = None
    if prosody_features is not None:
        p_bos = prosody_features[:1]
        p_eos = prosody_features[-1:] if len(prosody_features) > 1 else []
        p_middle = prosody_features[1:-1] if len(prosody_features) > 1 else []
        padded_prosody = (
            p_bos + [None] * pad_front + p_middle + [None] * pad_back + p_eos
        )
    elif prosody_features is None:
        padded_prosody = None

    _LOGGER.debug(
        "Strategy A: padded phoneme_ids from %d to %d tokens (+%d front, +%d back)",
        n,
        len(padded),
        pad_front,
        pad_back,
    )
    return padded, padded_prosody, True


def _trim_silence(
    audio: np.ndarray,
    sample_rate: int = 22050,
) -> np.ndarray:
    """Trim leading and trailing silence from int16 audio.

    Uses a sliding RMS window of 256 samples. Keeps at least
    TRIM_MIN_SAMPLES to avoid producing empty audio.
    """
    window_size = 256
    n = len(audio)

    if n <= window_size:
        return audio

    # Convert to float for RMS calculation
    audio_f = audio.astype(np.float32) / 32768.0

    # Compute RMS for each window position
    # Use a cumulative sum approach for efficiency
    sq = audio_f**2
    cumsum = np.concatenate([[0.0], np.cumsum(sq)])
    num_windows = n - window_size + 1
    if num_windows <= 0:
        return audio

    window_sums = cumsum[window_size:] - cumsum[:num_windows]
    rms_values = np.sqrt(window_sums / window_size)

    # Find first window above threshold (start of non-silence)
    above = np.where(rms_values > TRIM_THRESHOLD_RMS)[0]
    if len(above) == 0:
        # Entire audio is silence -- keep minimum
        return audio[:TRIM_MIN_SAMPLES] if n > TRIM_MIN_SAMPLES else audio

    start = above[0]
    end = above[-1] + window_size  # include the last non-silent window

    # Enforce minimum length
    trimmed_len = end - start
    if trimmed_len < TRIM_MIN_SAMPLES:
        # Centre the minimum window around the detected content
        centre = (start + end) // 2
        half = TRIM_MIN_SAMPLES // 2
        start = max(0, centre - half)
        end = min(n, start + TRIM_MIN_SAMPLES)
        start = max(0, end - TRIM_MIN_SAMPLES)

    trimmed = audio[start:end]
    _LOGGER.debug(
        "Strategy A post-trim: %d -> %d samples (%.3fs -> %.3fs)",
        n,
        len(trimmed),
        n / sample_rate,
        len(trimmed) / sample_rate,
    )
    return trimmed


def _adjust_scales_for_short_input(
    phoneme_ids: list[int],
    noise_scale: float,
    noise_scale_w: float,
    length_scale: float,
    *,
    original_len: int | None = None,
) -> tuple[float, float, float]:
    """Strategy B: Reduce noise scales for short inputs.

    For inputs shorter than MIN_PHONEME_IDS, attenuate noise_scale and
    noise_scale_w proportionally while keeping length_scale unchanged.

    Args:
        phoneme_ids: The phoneme ID sequence (used for length if original_len
            is not provided).
        noise_scale: Base noise scale.
        noise_scale_w: Base noise scale w.
        length_scale: Base length scale (returned unchanged).
        original_len: If provided, use this as the sequence length instead of
            ``len(phoneme_ids)``.  This is required when Strategy A (padding)
            has already been applied, so that the ratio is computed from the
            *pre-padding* length rather than the padded length.

    Returns:
        (adjusted_noise_scale, adjusted_length_scale, adjusted_noise_scale_w)
        in the same order as the scales array [noise_scale, length_scale, noise_w].
    """
    n = original_len if original_len is not None else len(phoneme_ids)
    if n >= MIN_PHONEME_IDS:
        return noise_scale, length_scale, noise_scale_w

    ratio = max(0.0, min(n / MIN_PHONEME_IDS, 1.0))
    adj_noise = noise_scale * max(0.5, ratio)
    adj_noise_w = noise_scale_w * max(0.4, ratio)

    _LOGGER.debug(
        "Strategy B: ratio=%.3f  noise_scale %.3f->%.3f  noise_w %.3f->%.3f",
        ratio,
        noise_scale,
        adj_noise,
        noise_scale_w,
        adj_noise_w,
    )
    return adj_noise, length_scale, adj_noise_w


class _DominantLanguageDetector:
    """Cached wrapper around UnicodeLanguageDetector for dominant-language detection.

    The detector is instantiated once per unique set of languages and reused
    across calls to avoid repeated object construction overhead.
    """

    _cache: "dict[tuple[tuple[str, int], ...], _DominantLanguageDetector]" = {}

    def __init__(self, language_id_map: dict[str, int]):
        from piper_plus_g2p import UnicodeLanguageDetector  # noqa: PLC0415

        self._language_id_map = language_id_map
        languages = list(language_id_map.keys())
        self._detector = UnicodeLanguageDetector(languages, default_latin_language="en")

    @classmethod
    def get(cls, language_id_map: dict[str, int]) -> "_DominantLanguageDetector":
        """Return a cached instance for this language_id_map."""
        key = tuple(sorted(language_id_map.items()))
        if key not in cls._cache:
            cls._cache[key] = cls(language_id_map)
        return cls._cache[key]

    def detect(self, text: str) -> int:
        """Return the language_id for the dominant language in text."""
        context_has_kana = self._detector.has_kana(text)
        counts: dict[str, int] = {}
        for ch in text:
            lang = self._detector.detect_char(ch, context_has_kana=context_has_kana)
            if lang is not None:
                counts[lang] = counts.get(lang, 0) + 1
        if not counts:
            return self._language_id_map.get("en", 0)
        dominant = max(counts, key=lambda k: counts[k])

        return self._language_id_map.get(dominant, 0)


def _detect_dominant_language(text: str, language_id_map: dict[str, int]) -> int:
    """Detect the dominant language in text using Unicode ranges.

    Returns the language_id for the most common script in the text.
    Uses a cached UnicodeLanguageDetector instance for efficiency.
    """
    return _DominantLanguageDetector.get(language_id_map).detect(text)


def text_to_phoneme_ids_and_prosody(
    text: str,
    phoneme_id_map: dict[str, list[int]],
    language: str = "ja",
    language_id_map: dict[str, int] | None = None,
) -> tuple[list[int], list[dict | None]]:
    """Convert text to phoneme IDs and prosody features.

    Args:
        text: Input text
        phoneme_id_map: Mapping from phoneme symbols to IDs
        language: "ja" for Japanese (OpenJTalk), "en" for English (g2p-en)
        language_id_map: Language-to-ID mapping from config. When provided
            and the model supports multiple languages, a single language
            code (e.g. "ja") is auto-promoted to a multilingual phonemizer
            so that intersperse padding is applied correctly.

    Returns:
        tuple of (phoneme_ids, prosody_features)
        - phoneme_ids: List of phoneme IDs
        - prosody_features: List of {"a1": int, "a2": int, "a3": int} or None
    """
    from piper_plus_g2p import get_phonemizer  # noqa: PLC0415

    # For multilingual models with JA input, auto-promote to multilingual
    # phonemizer so that intersperse padding is applied correctly.
    # JA is the only language whose post_process_ids() is a no-op (BOS/EOS
    # are added inline during phonemization), so only JA needs promotion.
    # Other languages (EN/ZH/ES/FR/PT) already get correct padding from
    # their base-class post_process_ids().  Promoting them would cause
    # UnicodeLanguageDetector to misroute Latin-script text to English.
    effective_language = language
    if (
        language_id_map
        and "-" not in language
        and len(language_id_map) > 1
        and language == "ja"
    ):
        effective_language = "-".join(sorted(language_id_map.keys()))
        _LOGGER.debug(
            "Auto-promoting language '%s' to multilingual '%s'",
            language,
            effective_language,
        )

    phonemizer = get_phonemizer(effective_language)
    phonemes, prosody_info_list = phonemizer.phonemize_with_prosody(text)

    from piper_plus_g2p.encode.encoder import PiperEncoder  # noqa: PLC0415

    encoder = PiperEncoder(phoneme_id_map)

    # JA-only models (no language_id_map or single language) do NOT get
    # BOS/EOS/padding from PiperEncoder -- the JA phonemizer already
    # includes these inline. Only multilingual / non-JA paths use the encoder.
    if language == "ja" and (not language_id_map or len(language_id_map) <= 1):
        # JA-only: convert tokens to IDs directly (no encoder wrapping)
        phoneme_ids: list[int] = []
        prosody_features: list[dict | None] = []
        from piper_plus_g2p.encode.pua import map_token  # noqa: PLC0415

        for phoneme, prosody_info in zip(phonemes, prosody_info_list, strict=True):
            mapped = map_token(phoneme)
            for ch in mapped:
                if ch in phoneme_id_map:
                    ids = phoneme_id_map[ch]
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
                    _LOGGER.warning("Unknown phoneme: %s", ch)
        return phoneme_ids, prosody_features

    # All other languages / multilingual: use PiperEncoder for BOS/EOS/padding
    result_ids, result_prosody = encoder.encode_with_prosody(
        phonemes, prosody_info_list
    )
    # Convert ProsodyInfo objects to dicts for JSON compatibility
    prosody_features_out: list[dict | None] = []
    for p in result_prosody:
        if p is not None:
            prosody_features_out.append({"a1": p.a1, "a2": p.a2, "a3": p.a3})
        else:
            prosody_features_out.append(None)

    return result_ids, prosody_features_out


def main():
    """Main entry point"""
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser(prog="piper_train.infer_onnx")
    parser.add_argument("--model", help="Path to model (.onnx) or model name/alias")
    parser.add_argument("--output-dir", help="Path to write WAV files")
    parser.add_argument(
        "--list-models",
        nargs="?",
        const="",
        default=None,
        metavar="LANG",
        help="List available voice models (optionally filter by language code)",
    )
    parser.add_argument(
        "--download-model",
        default=None,
        metavar="NAME",
        help="Download a model by name or alias",
    )
    parser.add_argument(
        "--model-dir",
        default=None,
        help="Model download/search directory",
    )
    parser.add_argument("--sample-rate", type=int, default=22050)
    parser.add_argument("--noise-scale", type=float, default=0.667)
    parser.add_argument("--noise-scale-w", type=float, default=0.8)
    parser.add_argument("--length-scale", type=float, default=1.0)
    # Text input options
    parser.add_argument(
        "--text",
        help="Text to synthesize (alternative to JSONL stdin input)",
    )
    parser.add_argument(
        "--config",
        help="Path to config.json with phoneme_id_map (required with --text). "
        "If not specified, looks for config.json next to the model.",
    )
    parser.add_argument(
        "--language",
        default="ja",
        help="Language for --text mode. Single (ja, en, zh, ko, es, pt, fr, sv) "
        "or multilingual combo (ja-en, ja-en-zh-ko-sv, etc.) (default: ja)",
    )
    parser.add_argument(
        "--speaker-id",
        type=int,
        default=0,
        help="Speaker ID for multi-speaker models (default: 0)",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "gpu"],
        default="auto",
        help="Device to run inference on (default: auto)",
    )
    parser.add_argument(
        "--speaker-embedding",
        default=None,
        metavar="PATH",
        help="Path to a .npy file containing a speaker embedding vector "
        "(e.g. 256-dim from ECAPA-TDNN). Overrides --speaker-id.",
    )
    parser.add_argument(
        "--reference-audio",
        "--encode-speaker",
        default=None,
        dest="reference_audio",
        metavar="AUDIO_PATH",
        help="Path to a reference audio file. Extracts speaker embedding "
        "on-the-fly using the speaker encoder ONNX model.",
    )
    parser.add_argument(
        "--speaker-encoder-model",
        "--encode-speaker-model",
        default=None,
        dest="speaker_encoder_model",
        metavar="ONNX_PATH",
        help="Path to the speaker encoder ONNX model "
        "(required with --reference-audio).",
    )
    args = parser.parse_args()

    # Emit deprecation warnings for old option names
    _raw_argv = sys.argv[1:]
    if "--encode-speaker" in _raw_argv:
        import warnings  # noqa: PLC0415

        warnings.warn(
            "--encode-speaker is deprecated, use --reference-audio instead.",
            DeprecationWarning,
            stacklevel=1,
        )
    if "--encode-speaker-model" in _raw_argv:
        import warnings  # noqa: PLC0415

        warnings.warn(
            "--encode-speaker-model is deprecated, use --speaker-encoder-model instead.",
            DeprecationWarning,
            stacklevel=1,
        )

    # Lazy import: model_manager is optional (not available in HF Space environment)
    try:
        from .model_manager import (  # noqa: PLC0415
            download_model,
            list_models,
            resolve_model_path,
        )
    except ImportError:
        list_models = None  # type: ignore[assignment]
        download_model = None  # type: ignore[assignment]
        resolve_model_path = None  # type: ignore[assignment]

    # Handle --list-models (early exit)
    if args.list_models is not None:
        if list_models is None:
            print("Error: model_manager is not available.", file=sys.stderr)
            sys.exit(1)
        list_models(args.list_models if args.list_models else None)
        return

    # Handle --download-model (early exit)
    if args.download_model is not None:
        if download_model is None:
            print("Error: model_manager is not available.", file=sys.stderr)
            sys.exit(1)
        success = download_model(args.download_model, args.model_dir)
        sys.exit(0 if success else 1)

    # Validate required args for inference mode
    if args.model is None:
        print(
            "Error: --model is required for inference. "
            "Use --list-models to see available models.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.output_dir is None:
        if args.text:
            # --text mode: default to "output.wav" in current directory
            args.output_dir = "."
        else:
            print("Error: --output-dir is required for inference.", file=sys.stderr)
            sys.exit(1)

    # Resolve model name/alias to file path
    resolved = (
        resolve_model_path(args.model, args.model_dir) if resolve_model_path else None
    )
    if resolved:
        args.model = resolved
    elif not os.path.exists(args.model):
        print(f"Error: Model not found: {args.model}", file=sys.stderr)
        print(
            "Use --list-models to see available models, "
            "or --download-model to download one.",
            file=sys.stderr,
        )
        sys.exit(1)

    args.output_dir = Path(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    _LOGGER.debug("Loading model from %s", args.model)
    model = create_session_with_cache(args.model, device=args.device)
    _LOGGER.info(
        "Loaded model from %s (providers: %s)", args.model, model.get_providers()
    )
    warmup_onnx_session(model)

    # Check if model supports prosody features
    input_names = [inp.name for inp in model.get_inputs()]
    has_prosody = "prosody_features" in input_names
    has_sid = "sid" in input_names
    has_lid = "lid" in input_names
    has_spk_emb = "speaker_embedding" in input_names
    if has_prosody:
        _LOGGER.info("Model supports prosody features (A1/A2/A3)")
    if has_sid:
        _LOGGER.info("Model supports multi-speaker (sid input)")
    if has_lid:
        _LOGGER.info("Model supports multi-language (lid input)")
    if has_spk_emb:
        _LOGGER.info("Model supports speaker_embedding (voice cloning)")

    # Resolve speaker embedding from --speaker-embedding or --reference-audio
    spk_emb_array = None
    if args.speaker_embedding:
        spk_emb_array = np.load(args.speaker_embedding).astype(np.float32)
        if spk_emb_array.ndim == 1:
            spk_emb_array = spk_emb_array.reshape(1, -1)
        _LOGGER.info(
            "Loaded speaker embedding from %s (dim=%d)",
            args.speaker_embedding,
            spk_emb_array.shape[1],
        )
    elif args.reference_audio:
        if not args.speaker_encoder_model:
            print(
                "Error: --speaker-encoder-model is required with --reference-audio.",
                file=sys.stderr,
            )
            sys.exit(1)
        from .speaker_encoder import SpeakerEncoder  # noqa: PLC0415

        se_encoder = SpeakerEncoder.from_onnx(args.speaker_encoder_model)
        spk_emb_vec = se_encoder.encode(args.reference_audio)
        spk_emb_array = spk_emb_vec.reshape(1, -1).astype(np.float32)
        _LOGGER.info(
            "Encoded speaker embedding from %s (dim=%d)",
            args.reference_audio,
            spk_emb_array.shape[1],
        )

    if spk_emb_array is not None and not has_spk_emb:
        _LOGGER.warning(
            "speaker_embedding provided but model does not have "
            "speaker_embedding input; it will be ignored."
        )

    # Handle --text mode: convert text to phoneme_ids and prosody_features
    phoneme_id_map = None
    if args.text:
        # Load config.json for phoneme_id_map
        if args.config:
            config_path = Path(args.config)
        else:
            # Fallback: {model}.json first (C++ CLI convention), then {model_dir}/config.json
            model_path = Path(args.model)
            onnx_json = model_path.with_suffix(model_path.suffix + ".json")
            if onnx_json.exists():
                config_path = onnx_json
            else:
                config_path = model_path.parent / "config.json"

        if not config_path.exists():
            _LOGGER.error(
                "config.json not found at %s. Use --config to specify path.",
                config_path,
            )
            sys.exit(1)

        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        phoneme_id_map = config.get("phoneme_id_map")
        if not phoneme_id_map:
            _LOGGER.error("phoneme_id_map not found in config.json")
            sys.exit(1)

        _LOGGER.info("Loaded phoneme_id_map from %s", config_path)

        # Load language_id_map (needed for multilingual auto-promotion)
        language_id_map = config.get("language_id_map", {}) if has_lid else {}

        # Convert text to phoneme_ids and prosody_features
        phoneme_ids, prosody_features_data = text_to_phoneme_ids_and_prosody(
            args.text,
            phoneme_id_map,
            language=args.language,
            language_id_map=language_id_map,
        )
        _LOGGER.info(
            "Converted text to %d phoneme IDs: %s",
            len(phoneme_ids),
            args.text[:50] + "..." if len(args.text) > 50 else args.text,
        )

        # Determine language_id from config
        language_id = 0  # default
        if has_lid:
            language_id_map = config.get("language_id_map", {})
            if args.language in language_id_map:
                language_id = language_id_map[args.language]
            elif "-" in args.language:
                # Multilingual mode: detect dominant language from text
                language_id = _detect_dominant_language(args.text, language_id_map)
            _LOGGER.info(
                "Using language_id=%d for language=%s", language_id, args.language
            )

        # Create single utterance
        utterances = [
            {
                "phoneme_ids": phoneme_ids,
                "speaker_id": args.speaker_id if has_sid else None,
                "language_id": language_id if has_lid else None,
                "prosody_features": prosody_features_data,
            }
        ]
    else:
        # Read from stdin (JSONL mode)
        utterances = []
        for line in sys.stdin:
            line = line.strip()
            if line:
                utterances.append(json.loads(line))

    for i, utt in enumerate(utterances):
        utt_id = str(i)
        phoneme_ids = utt["phoneme_ids"]
        speaker_id = utt.get("speaker_id")
        prosody_features_data = utt.get("prosody_features")

        # Save original length before padding for Strategy B
        original_len = len(phoneme_ids)

        # --- Strategy A: Silence Padding for short inputs ---
        phoneme_ids, prosody_features_data, was_padded = _pad_phoneme_ids(
            phoneme_ids, prosody_features_data
        )

        # --- Strategy B: Dynamic Scales Adjustment for short inputs ---
        # Use original_len (pre-padding) so the ratio is based on the actual
        # input length, not the padded length (which is always MIN_PHONEME_IDS).
        adj_noise, adj_length, adj_noise_w = _adjust_scales_for_short_input(
            phoneme_ids,
            args.noise_scale,
            args.noise_scale_w,
            args.length_scale,
            original_len=original_len,
        )

        text = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
        text_lengths = np.array([text.shape[1]], dtype=np.int64)
        scales = np.array(
            [adj_noise, adj_length, adj_noise_w],
            dtype=np.float32,
        )
        sid = None

        if speaker_id is not None:
            sid = np.array([speaker_id], dtype=np.int64)

        # Build input dictionary
        inputs = {
            "input": text,
            "input_lengths": text_lengths,
            "scales": scales,
        }

        # Default sid to 0 for models that require it (e.g. single-speaker multilingual)
        if sid is None and has_sid:
            sid = np.array([0], dtype=np.int64)

        if sid is not None:
            inputs["sid"] = sid

        # Handle language ID if model supports it
        if has_lid:
            language_id = utt.get("language_id", 0)
            inputs["lid"] = np.array([language_id], dtype=np.int64)

        # Handle prosody features if model supports them
        if has_prosody:
            if prosody_features_data is not None:
                # Convert prosody_features to numpy array (float32 to match ONNX export)
                # Format: [[a1, a2, a3], [a1, a2, a3], ...]
                # Each element may be None for special tokens
                prosody_array = []
                for pf in prosody_features_data:
                    if pf is None:
                        prosody_array.append([0, 0, 0])
                    else:
                        prosody_array.append([pf["a1"], pf["a2"], pf["a3"]])
                prosody_features = np.expand_dims(
                    np.array(prosody_array, dtype=np.int64), 0
                )
            else:
                # No prosody data provided - use zeros (int64)
                prosody_features = np.zeros((1, text.shape[1], 3), dtype=np.int64)
            inputs["prosody_features"] = prosody_features

        # Handle speaker embedding if model supports it
        if has_spk_emb:
            if spk_emb_array is not None:
                inputs["speaker_embedding"] = spk_emb_array
                inputs["speaker_embedding_mask"] = np.array([[1]], dtype=np.int64)
            else:
                # No speaker embedding: provide zeros with mask=0
                # Infer emb_dim from the ONNX input shape (dynamic, fallback to 256)
                for inp in model.get_inputs():
                    if inp.name == "speaker_embedding":
                        emb_dim = inp.shape[1] if isinstance(inp.shape[1], int) else 256
                        break
                else:
                    emb_dim = 256
                inputs["speaker_embedding"] = np.zeros((1, emb_dim), dtype=np.float32)
                inputs["speaker_embedding_mask"] = np.array([[0]], dtype=np.int64)

        start_time = time.perf_counter()
        outputs = model.run(None, inputs)
        audio = outputs[0].squeeze(0)
        # durations output is available for phoneme timing (e.g., lip-sync, karaoke)
        durations = outputs[1] if len(outputs) > 1 else None
        # audio = denoise(audio, bias_spec, 10)
        audio = audio_float_to_int16(audio.squeeze())

        # --- Strategy A: Post-trim silence introduced by padding ---
        if was_padded:
            audio = _trim_silence(audio, sample_rate=args.sample_rate)

        end_time = time.perf_counter()

        audio_duration_sec = audio.shape[-1] / args.sample_rate
        infer_sec = end_time - start_time
        real_time_factor = (
            infer_sec / audio_duration_sec if audio_duration_sec > 0 else 0.0
        )

        _LOGGER.debug(
            "Real-time factor for %s: %0.2f (infer=%0.2f sec, audio=%0.2f sec)",
            i + 1,
            real_time_factor,
            infer_sec,
            audio_duration_sec,
        )

        # Log phoneme durations if available (useful for debugging/timing)
        if durations is not None:
            _LOGGER.debug("Phoneme durations shape: %s", durations.shape)

        if args.text:
            output_path = args.output_dir / "output.wav"
        else:
            output_path = args.output_dir / f"{utt_id}.wav"
        write_wav(str(output_path), args.sample_rate, audio)
        _LOGGER.info("Wrote: %s", output_path)


def denoise(
    audio: np.ndarray, bias_spec: np.ndarray, denoiser_strength: float
) -> np.ndarray:
    audio_spec, audio_angles = transform(audio)

    a = bias_spec.shape[-1]
    b = audio_spec.shape[-1]
    repeats = max(1, math.ceil(b / a))
    bias_spec_repeat = np.repeat(bias_spec, repeats, axis=-1)[..., :b]

    audio_spec_denoised = audio_spec - (bias_spec_repeat * denoiser_strength)
    audio_spec_denoised = np.clip(audio_spec_denoised, a_min=0.0, a_max=None)
    audio_denoised = inverse(audio_spec_denoised, audio_angles)

    return audio_denoised


def stft(x, fft_size, hopsamp):
    """Compute and return the STFT of the supplied time domain signal x.
    Args:
        x (1-dim Numpy array): A time domain signal.
        fft_size (int): FFT size. Should be a power of 2, otherwise DFT will be used.
        hopsamp (int):
    Returns:
        The STFT. The rows are the time slices and columns are the frequency bins.
    """
    window = np.hanning(fft_size)
    fft_size = int(fft_size)
    hopsamp = int(hopsamp)
    return np.array(
        [
            np.fft.rfft(window * x[i : i + fft_size])
            for i in range(0, len(x) - fft_size, hopsamp)
        ]
    )


def istft(X, fft_size, hopsamp):
    """Invert a STFT into a time domain signal.
    Args:
        X (2-dim Numpy array): Input spectrogram. The rows are the time slices and columns are the frequency bins.  # noqa: E501
        fft_size (int):
        hopsamp (int): The hop size, in samples.
    Returns:
        The inverse STFT.
    """
    fft_size = int(fft_size)
    hopsamp = int(hopsamp)
    window = np.hanning(fft_size)
    time_slices = X.shape[0]
    len_samples = int(time_slices * hopsamp + fft_size)
    x = np.zeros(len_samples)
    for n, i in enumerate(range(0, len(x) - fft_size, hopsamp)):
        x[i : i + fft_size] += window * np.real(np.fft.irfft(X[n]))
    return x


def inverse(magnitude, phase):
    recombine_magnitude_phase = np.concatenate(
        [magnitude * np.cos(phase), magnitude * np.sin(phase)], axis=1
    )

    x_org = recombine_magnitude_phase
    n_b, n_f, n_t = x_org.shape  # pylint: disable=unpacking-non-sequence
    x = np.empty([n_b, n_f // 2, n_t], dtype=np.complex64)
    x.real = x_org[:, : n_f // 2]
    x.imag = x_org[:, n_f // 2 :]
    inverse_transform = []
    for y in x:
        y_ = istft(y.T, fft_size=1024, hopsamp=256)
        inverse_transform.append(y_[None, :])

    inverse_transform = np.concatenate(inverse_transform, 0)

    return inverse_transform


def transform(input_data):
    x = input_data
    real_part = []
    imag_part = []
    for y in x:
        y_ = stft(y, fft_size=1024, hopsamp=256).T
        real_part.append(y_.real[None, :, :])  # pylint: disable=unsubscriptable-object
        imag_part.append(y_.imag[None, :, :])  # pylint: disable=unsubscriptable-object
    real_part = np.concatenate(real_part, 0)
    imag_part = np.concatenate(imag_part, 0)

    magnitude = np.sqrt(real_part**2 + imag_part**2)
    phase = np.arctan2(imag_part.data, real_part.data)

    return magnitude, phase


if __name__ == "__main__":
    main()
