#!/usr/bin/env python3
"""
Inference script for multilingual VITS model.
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import torch


# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

from piper_train.phonemize.multilingual_phoneme_map import (
    get_multilingual_phoneme_mapper,
)
from piper_train.vits.models_multilingual import MultilingualSynthesizerTrn


try:
    from piper_train.phonemize.multilingual import phonemize_multilingual
except ImportError:
    from piper_train.phonemize.multilingual_stub import phonemize_multilingual

_LOGGER = logging.getLogger(__name__)


def load_checkpoint(checkpoint_path: Path, device: str = "cpu"):
    """Load model from checkpoint."""
    checkpoint = torch.load(checkpoint_path, map_location=device)

    # Extract hyperparameters
    hparams = checkpoint.get("hyper_parameters", {})

    # Create model
    model = MultilingualSynthesizerTrn(
        n_vocab=hparams.get("num_symbols", 512),
        spec_channels=hparams.get("spec_channels", 513),
        segment_size=hparams.get("segment_size", 8192)
        // hparams.get("hop_length", 256),
        inter_channels=hparams.get("inter_channels", 192),
        hidden_channels=hparams.get("hidden_channels", 192),
        filter_channels=hparams.get("filter_channels", 768),
        n_heads=hparams.get("n_heads", 2),
        n_layers=hparams.get("n_layers", 6),
        kernel_size=hparams.get("kernel_size", 3),
        p_dropout=hparams.get("p_dropout", 0.1),
        resblock=hparams.get("resblock", "2"),
        resblock_kernel_sizes=hparams.get("resblock_kernel_sizes", [3, 5, 7]),
        resblock_dilation_sizes=hparams.get(
            "resblock_dilation_sizes", [[1, 2], [2, 6], [3, 12]]
        ),
        upsample_rates=hparams.get("upsample_rates", [8, 8, 4]),
        upsample_initial_channel=hparams.get("upsample_initial_channel", 256),
        upsample_kernel_sizes=hparams.get("upsample_kernel_sizes", [16, 16, 8]),
        n_speakers=hparams.get("num_speakers", 1),
        gin_channels=hparams.get("gin_channels", 0),
        use_sdp=hparams.get("use_sdp", True),
        n_languages=hparams.get("num_languages", 8),
        lang_embedding_dim=hparams.get("lang_embedding_dim", 64),
    )

    # Load state dict
    state_dict = checkpoint["state_dict"]
    # Remove "model_g." prefix if present
    state_dict = {k.replace("model_g.", ""): v for k, v in state_dict.items()}
    model.load_state_dict(state_dict)

    model.eval()
    model.to(device)

    return model, hparams


def synthesize(
    model,
    text: str,
    language: str,
    speaker_id: int = 0,
    noise_scale: float = 0.667,
    length_scale: float = 1.0,
    noise_scale_w: float = 0.8,
    sample_rate: int = 22050,
):
    """Synthesize speech from text."""
    # Get phoneme mapper
    mapper = get_multilingual_phoneme_mapper()

    # Phonemize text
    phonemes = phonemize_multilingual(text, language)
    _LOGGER.info(f"Phonemes: {phonemes}")

    # Convert to IDs
    phoneme_ids = []
    current_language = None

    language_map = {
        "ja": 0,
        "en": 1,
        "zh": 2,
        "es": 3,
        "fr": 4,
        "de": 5,
        "ko": 6,
        "mixed": 7,
    }

    for phoneme in phonemes:
        if phoneme.startswith("<lang:") and phoneme.endswith(">"):
            lang_code = phoneme[6:-1]
            current_language = lang_code
            phoneme_ids.append(mapper.get_phoneme_id(phoneme, ""))
        elif phoneme.startswith("</lang:") and phoneme.endswith(">"):
            phoneme_ids.append(mapper.get_phoneme_id(phoneme, ""))
            current_language = None
        elif current_language:
            phoneme_ids.append(mapper.get_phoneme_id(phoneme, current_language))
        else:
            phoneme_ids.append(mapper.get_phoneme_id(phoneme, language))

    _LOGGER.info(f"Phoneme IDs: {phoneme_ids}")

    # Convert to tensors
    text_tensor = torch.LongTensor(phoneme_ids).unsqueeze(0)
    text_lengths = torch.LongTensor([len(phoneme_ids)])

    # Language ID
    lang_id = language_map.get(language, 0)
    lang_ids = torch.LongTensor([lang_id])

    # Speaker ID
    sid = torch.LongTensor([speaker_id]) if model.n_speakers > 1 else None

    # Generate audio
    with torch.no_grad():
        audio, *_ = model.infer(
            text_tensor,
            text_lengths,
            sid=sid,
            lang_ids=lang_ids,
            noise_scale=noise_scale,
            length_scale=length_scale,
            noise_scale_w=noise_scale_w,
        )

    audio = audio.squeeze().cpu().numpy()

    return audio, sample_rate


def save_wav(audio: np.ndarray, sample_rate: int, output_path: Path):
    """Save audio to WAV file."""
    import wave

    # Normalize and convert to int16
    audio = np.clip(audio, -1, 1)
    audio = (audio * 32767).astype(np.int16)

    with wave.open(str(output_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.tobytes())


def main():
    parser = argparse.ArgumentParser(description="Multilingual TTS inference")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Path to model checkpoint",
    )
    parser.add_argument(
        "--text",
        type=str,
        required=True,
        help="Text to synthesize",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="ja",
        choices=["ja", "en", "zh", "es", "fr", "de", "ko"],
        help="Language code (default: ja)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output.wav"),
        help="Output WAV file path",
    )
    parser.add_argument(
        "--speaker-id",
        type=int,
        default=0,
        help="Speaker ID for multi-speaker models",
    )
    parser.add_argument(
        "--noise-scale",
        type=float,
        default=0.667,
        help="Noise scale for variability",
    )
    parser.add_argument(
        "--length-scale",
        type=float,
        default=1.0,
        help="Length scale (< 1.0 = faster, > 1.0 = slower)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        choices=["cpu", "cuda"],
        help="Device to use",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Check device
    if args.device == "cuda" and not torch.cuda.is_available():
        _LOGGER.warning("CUDA requested but not available, using CPU")
        args.device = "cpu"

    # Load model
    _LOGGER.info(f"Loading model from {args.checkpoint}")
    model, hparams = load_checkpoint(args.checkpoint, args.device)
    sample_rate = hparams.get("sample_rate", 22050)

    # Synthesize
    _LOGGER.info(f"Synthesizing: {args.text}")
    audio, sr = synthesize(
        model,
        args.text,
        args.language,
        args.speaker_id,
        args.noise_scale,
        args.length_scale,
        sample_rate=sample_rate,
    )

    # Save audio
    save_wav(audio, sr, args.output)
    _LOGGER.info(f"Audio saved to {args.output}")

    # Print duration
    duration = len(audio) / sr
    _LOGGER.info(f"Duration: {duration:.2f} seconds")


if __name__ == "__main__":
    main()
