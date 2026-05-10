#!/usr/bin/env python3
import argparse
import json
import logging
import sys
import time
from pathlib import Path

import torch

from .vits.lightning import VitsModel
from .vits.utils import audio_float_to_int16
from .vits.wavfile import write as write_wav


_LOGGER = logging.getLogger("piper_train.infer")


def _prosody_features_to_tensor(prosody_features: list) -> torch.LongTensor:
    """Convert prosody features list to tensor.

    Args:
        prosody_features: List of {"a1": int, "a2": int, "a3": int} or None

    Returns:
        Tensor of shape (1, num_phonemes, 3)
    """
    result = []
    for feat in prosody_features:
        if feat is None:
            result.append([0, 0, 0])
        else:
            result.append([feat["a1"], feat["a2"], feat["a3"]])
    return torch.LongTensor(result).unsqueeze(0)


def main():
    """Main entry point"""
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser(prog="piper_train.infer")
    parser.add_argument(
        "--checkpoint", required=True, help="Path to model checkpoint (.ckpt)"
    )
    parser.add_argument("--output-dir", required=True, help="Path to write WAV files")
    parser.add_argument("--sample-rate", type=int, default=22050)
    parser.add_argument("--noise-scale", type=float, default=0.667)
    parser.add_argument("--length-scale", type=float, default=1.0)
    parser.add_argument("--noise-scale-w", type=float, default=0.8)
    args = parser.parse_args()

    args.output_dir = Path(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    model = VitsModel.load_from_checkpoint(args.checkpoint, dataset=None)

    # Check if model uses prosody features
    has_prosody = getattr(model.model_g, "prosody_dim", 0) > 0
    if has_prosody:
        _LOGGER.info(
            "Model uses prosody features (prosody_dim=%d)", model.model_g.prosody_dim
        )

    # Inference only
    model.eval()

    with torch.no_grad():
        model.model_g.dec.remove_weight_norm()

    for i, line in enumerate(sys.stdin):
        line = line.strip()
        if not line:
            continue

        utt = json.loads(line)
        utt_id = str(i)
        phoneme_ids = utt["phoneme_ids"]
        speaker_id = utt.get("speaker_id")
        prosody_features_data = utt.get("prosody_features")

        text = torch.LongTensor(phoneme_ids).unsqueeze(0)
        text_lengths = torch.LongTensor([len(phoneme_ids)])
        scales = [args.noise_scale, args.length_scale, args.noise_scale_w]
        sid = torch.LongTensor([speaker_id]) if speaker_id is not None else None

        # Prepare prosody features if model supports them
        prosody_features = None
        if has_prosody and prosody_features_data is not None:
            prosody_features = _prosody_features_to_tensor(prosody_features_data)
            _LOGGER.debug("Using prosody features for utterance %d", i)

        start_time = time.perf_counter()
        audio = (
            model(
                text, text_lengths, scales, sid=sid, prosody_features=prosody_features
            )
            .detach()
            .numpy()
        )
        audio = audio_float_to_int16(audio)
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

        output_path = args.output_dir / f"{utt_id}.wav"
        write_wav(str(output_path), args.sample_rate, audio)


if __name__ == "__main__":
    main()
