"""Evaluation-only controls for CPU reference-processing comparisons."""

from pathlib import Path

import numpy as np

from ..embedding_cache import file_sha256


def crop_active_frames(audio, sample_rate, active_frames, *, threshold_db=-40.0):
    """Keep a contiguous crop with exactly N active 20 ms RMS frames.

    Activity is an amplitude proxy, not a phonetic VAD/voicing decision. Internal
    pauses are retained; no gain normalization or concatenation is performed.
    """
    audio = np.asarray(audio, dtype=np.float32)
    width = int(sample_rate * 0.02)
    if (
        audio.ndim != 1
        or not np.isfinite(audio).all()
        or width < 1
        or type(active_frames) is not int
        or active_frames < 1
    ):
        raise ValueError("invalid activity crop input")
    frames = audio[: len(audio) // width * width].reshape(-1, width)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    indices = np.flatnonzero(rms >= 10 ** (threshold_db / 20))
    if len(indices) < active_frames:
        raise ValueError(
            f"insufficient active frames: {len(indices)} < {active_frames}"
        )
    start, end = int(indices[0]), int(indices[active_frames - 1]) + 1
    return audio[start * width : end * width].copy(), {
        "start_frame": start,
        "end_frame": end,
        "frame_seconds": 0.02,
        "threshold_dbfs": threshold_db,
        "active_frames": active_frames,
        "activity_seconds": active_frames * 0.02,
        "duration_seconds": (end - start) * 0.02,
        "method": "contiguous RMS activity proxy; not phonetic VAD",
    }


def independent_reals(candidates, sources):
    """Exclude original utterances as well as crops and byte-identical aliases."""
    if not sources:
        raise ValueError("reference sources must not be empty")
    excluded = {file_sha256(Path(path)) for path in sources}
    seen = set()
    result = []
    for value in candidates:
        path = Path(value)
        digest = file_sha256(path)
        if digest not in excluded and digest not in seen:
            seen.add(digest)
            result.append(path)
    return result


def reference_embedding(session, paths, *, chunk_frames=0):
    """Hold the runtime frontend fixed; vary only pooling (whole vs training chunks)."""
    import torch  # noqa: PLC0415

    from piper_plus.embedding import validate_embedding  # noqa: PLC0415

    from ..extract_speaker_embedding import (  # noqa: PLC0415
        _FbankDataset,
        extract_embedding,
        preprocess_audio,
    )

    vectors = []
    chunk_counts = []
    for path in paths:
        fbank = preprocess_audio(path)
        if chunk_frames:
            dataset = _FbankDataset([], source_sr=16000, fixed_frames=chunk_frames)
            chunks = dataset._to_chunks(torch.from_numpy(fbank)).numpy()
        else:
            chunks = fbank[None, :, :]
        chunks_vectors = [extract_embedding(session, chunk) for chunk in chunks]
        vectors.append(validate_embedding(np.mean(chunks_vectors, axis=0)))
        chunk_counts.append(len(chunks))
    if not vectors:
        raise ValueError("reference list must not be empty")
    return validate_embedding(np.mean(vectors, axis=0)), chunk_counts


def load_native_ecapa(source):
    """Load trusted pinned SpeechBrain config/weights, exclusively for evaluation.

    Native waveform frontend is retained: CAM++ Kaldi features are not equivalent
    to SpeechBrain features. Optional dependencies belong in the metrics overlay.
    """
    import torch  # noqa: PLC0415
    import torchaudio  # noqa: PLC0415

    # SpeechBrain 1.0.3 probes an API removed from recent torchaudio. Actual
    # audio loading below is soundfile. Keep the shim within this eval process.
    if not hasattr(torchaudio, "list_audio_backends"):
        torchaudio.list_audio_backends = lambda: ["soundfile"]
    from hyperpyyaml import load_hyperpyyaml  # noqa: PLC0415
    from speechbrain.inference.speaker import EncoderClassifier  # noqa: PLC0415

    source = Path(source)
    with (source / "hyperparams.yaml").open(encoding="utf-8") as stream:
        parameters = load_hyperpyyaml(stream, {"pretrained_path": str(source)})
    parameters["modules"]["embedding_model"].load_state_dict(
        torch.load(
            source / "embedding_model.ckpt", map_location="cpu", weights_only=True
        ),
        strict=True,
    )
    return EncoderClassifier(
        modules=parameters["modules"], hparams=parameters, run_opts={"device": "cpu"}
    )


def native_ecapa_embedding(classifier, path):
    import soundfile as sf  # noqa: PLC0415
    import soxr  # noqa: PLC0415
    import torch  # noqa: PLC0415

    from piper_plus.embedding import validate_embedding  # noqa: PLC0415

    audio, rate = sf.read(path, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if not len(audio) or not np.isfinite(audio).all():
        raise ValueError(f"invalid ECAPA waveform: {path}")
    if rate != 16000:
        audio = soxr.resample(audio, rate, 16000, quality="HQ")
    with torch.inference_mode():
        vector = classifier.encode_batch(torch.from_numpy(audio).unsqueeze(0))
    return validate_embedding(vector.detach().cpu().numpy().squeeze())
