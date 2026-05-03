#!/usr/bin/env python3
import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
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


def _style_vector_to_tensor(utt: dict) -> torch.FloatTensor | None:
    """Convert inline or file-backed style vector spec to a (1, D) tensor.

    Recognised shapes in ``utt``:
        * ``"style_vector"``: inline list/ndarray of floats.
        * ``"style_vector_path"``: path to ``.npy`` (numpy) or ``.pt``/``.pth``
          (torch). ``.pt`` may optionally wrap the tensor in
          ``{"style_vector": ...}`` or ``{"embedding": ...}``.

    Returns ``None`` when neither key is present.

    Raises:
        ValueError: torch-serialised dict does not expose a known key.
    """
    style_vector = utt.get("style_vector")
    if style_vector is not None:
        return torch.as_tensor(style_vector, dtype=torch.float32).view(1, -1)

    style_vector_path = utt.get("style_vector_path")
    if style_vector_path is None:
        return None

    path = Path(style_vector_path)
    if path.suffix == ".npy":
        return torch.from_numpy(np.load(path)).float().view(1, -1)

    loaded = torch.load(path, map_location="cpu", weights_only=False)
    if isinstance(loaded, dict):
        loaded = loaded.get("style_vector", loaded.get("embedding"))
    if loaded is None:
        raise ValueError(f"No style vector found in {path}")
    return torch.as_tensor(loaded, dtype=torch.float32).view(1, -1)


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
    parser.add_argument(
        "--device", default="cuda" if torch.cuda.is_available() else "cpu"
    )
    args = parser.parse_args()

    args.output_dir = Path(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device(args.device)
    model = VitsModel.load_from_checkpoint(
        args.checkpoint,
        dataset=None,
        strict=False,
        use_wavlm_discriminator=False,
    ).to(device)

    # Check if model uses prosody features
    has_prosody = getattr(model.model_g, "prosody_dim", 0) > 0
    if has_prosody:
        _LOGGER.info(
            "Model uses prosody features (prosody_dim=%d)", model.model_g.prosody_dim
        )
    has_style = getattr(model.model_g, "style_vector_dim", 0) > 0
    if has_style:
        _LOGGER.info(
            "Model uses style vectors (style_vector_dim=%d)",
            model.model_g.style_vector_dim,
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
        utt_id = str(utt.get("utt_id", i))
        phoneme_ids = utt["phoneme_ids"]
        speaker_id = utt.get("speaker_id")
        language_id = utt.get("language_id", 0)
        prosody_features_data = utt.get("prosody_features")
        style_vector = _style_vector_to_tensor(utt)

        text = torch.LongTensor(phoneme_ids).unsqueeze(0).to(device)
        text_lengths = torch.LongTensor([len(phoneme_ids)]).to(device)
        scales = [args.noise_scale, args.length_scale, args.noise_scale_w]
        sid = (
            torch.LongTensor([speaker_id]).to(device)
            if speaker_id is not None
            else None
        )
        lid = None
        if getattr(model.model_g, "n_languages", 1) > 1:
            lid = torch.LongTensor([language_id]).to(device)
        if style_vector is not None:
            style_vector = style_vector.to(device)

        # Prepare prosody features if model supports them
        prosody_features = None
        if has_prosody and prosody_features_data is not None:
            prosody_features = _prosody_features_to_tensor(prosody_features_data).to(
                device
            )
            _LOGGER.debug("Using prosody features for utterance %d", i)

        start_time = time.perf_counter()
        audio = (
            model(
                text,
                text_lengths,
                scales,
                sid=sid,
                lid=lid,
                prosody_features=prosody_features,
                style_vector=style_vector,
            )
            .detach()
            .cpu()
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
