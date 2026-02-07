#!/usr/bin/env python3
import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime

from .vits.utils import audio_float_to_int16
from .vits.wavfile import write as write_wav


_LOGGER = logging.getLogger("piper_train.infer_onnx")


def text_to_phoneme_ids_and_prosody(
    text: str,
    phoneme_id_map: dict[str, list[int]],
    language: str = "ja",
) -> tuple[list[int], list[dict | None]]:
    """Convert text to phoneme IDs and prosody features.

    Args:
        text: Input text
        phoneme_id_map: Mapping from phoneme symbols to IDs
        language: "ja" for Japanese (OpenJTalk), "en" for English (g2p-en)

    Returns:
        tuple of (phoneme_ids, prosody_features)
        - phoneme_ids: List of phoneme IDs
        - prosody_features: List of {"a1": int, "a2": int, "a3": int} or None
    """
    from .phonemize.registry import get_phonemizer  # noqa: PLC0415

    phonemizer = get_phonemizer(language)
    phonemes, prosody_info_list = phonemizer.phonemize_with_prosody(text)

    # Convert phonemes to IDs
    phoneme_ids: list[int] = []
    prosody_features: list[dict | None] = []

    for phoneme, prosody_info in zip(phonemes, prosody_info_list, strict=True):
        if phoneme in phoneme_id_map:
            ids = phoneme_id_map[phoneme]
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

    # Language-specific post-processing (BOS/EOS/padding)
    phoneme_ids, prosody_features = phonemizer.post_process_ids(
        phoneme_ids, prosody_features, phoneme_id_map
    )

    return phoneme_ids, prosody_features


def main():
    """Main entry point"""
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser(prog="piper_train.infer_onnx")
    parser.add_argument("--model", required=True, help="Path to model (.onnx)")
    parser.add_argument("--output-dir", required=True, help="Path to write WAV files")
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
    from .phonemize.registry import available_languages  # noqa: PLC0415

    parser.add_argument(
        "--language",
        choices=available_languages(),
        default="ja",
        help="Language for --text mode (default: ja)",
    )
    parser.add_argument(
        "--speaker-id",
        type=int,
        default=0,
        help="Speaker ID for multi-speaker models (default: 0)",
    )
    args = parser.parse_args()

    args.output_dir = Path(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    sess_options = onnxruntime.SessionOptions()
    _LOGGER.debug("Loading model from %s", args.model)
    model = onnxruntime.InferenceSession(str(args.model), sess_options=sess_options)
    _LOGGER.info("Loaded model from %s", args.model)

    # Check if model supports prosody features
    input_names = [inp.name for inp in model.get_inputs()]
    has_prosody = "prosody_features" in input_names
    has_sid = "sid" in input_names
    has_lid = "lid" in input_names
    if has_prosody:
        _LOGGER.info("Model supports prosody features (A1/A2/A3)")
    if has_sid:
        _LOGGER.info("Model supports multi-speaker (sid input)")
    if has_lid:
        _LOGGER.info("Model supports multi-language (lid input)")

    # Handle --text mode: convert text to phoneme_ids and prosody_features
    phoneme_id_map = None
    if args.text:
        # Load config.json for phoneme_id_map
        if args.config:
            config_path = Path(args.config)
        else:
            # Look for config.json next to the model
            model_path = Path(args.model)
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

        # Convert text to phoneme_ids and prosody_features
        phoneme_ids, prosody_features_data = text_to_phoneme_ids_and_prosody(
            args.text, phoneme_id_map, language=args.language
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
            elif args.language == "ja-en":
                # Bilingual mode: default to 0 (ja), speaker_id determines voice
                language_id = language_id_map.get("ja", 0)
            _LOGGER.info("Using language_id=%d for language=%s", language_id, args.language)

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

        text = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
        text_lengths = np.array([text.shape[1]], dtype=np.int64)
        scales = np.array(
            [args.noise_scale, args.length_scale, args.noise_scale_w],
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

        start_time = time.perf_counter()
        outputs = model.run(None, inputs)
        audio = outputs[0].squeeze((0, 1))
        # durations output is available for phoneme timing (e.g., lip-sync, karaoke)
        durations = outputs[1] if len(outputs) > 1 else None
        # audio = denoise(audio, bias_spec, 10)
        audio = audio_float_to_int16(audio.squeeze())
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

        output_path = args.output_dir / f"{utt_id}.wav"
        write_wav(str(output_path), args.sample_rate, audio)


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
