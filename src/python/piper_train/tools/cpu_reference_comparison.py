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


def reference_embedding(session, paths, *, chunk_frames=0, trim=False):
    """Hold the runtime frontend fixed; vary only pooling (whole vs training chunks).

    ``trim=True`` applies the training-identical energy VAD
    (``reference_frontend.trim_reference_audio``) before fbank; the default
    keeps the previous frontend output unchanged.
    """
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
        fbank = preprocess_audio(path, trim=trim)
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


def projected_average(model, embeddings):
    """Average multiple references on the g side: mean_i spk_proj(e_i).

    Diagnostic only (Torch). Embedding-side averaging projects
    ``L2(mean_i e_i)`` once; this keeps each reference's projection separate.
    Uses the model's current ``spk_proj`` weights (raw or EMA as loaded).

    Returns:
        ``[1, gin_channels]`` tensor on the ``spk_proj`` device/dtype.
    """
    import torch  # noqa: PLC0415

    values = np.asarray(embeddings, dtype=np.float32)
    if values.ndim != 2 or values.shape[0] < 1 or not np.isfinite(values).all():
        raise ValueError("embeddings must be a finite non-empty [N, D] array")
    parameter = next(model.spk_proj.parameters())
    projected = model.spk_proj(
        torch.from_numpy(values).to(parameter.device, parameter.dtype)
    )
    return projected.mean(dim=0, keepdim=True)


def pairwise_separability(vectors, labels, *, standardize=False):
    """Same- vs other-speaker cosine separation over all utterance pairs.

    AUC is the Mann-Whitney probability that a random same-speaker pair has a
    higher cosine than a random other-speaker pair (ties count 0.5).
    ``standardize=True`` z-scores each dimension on this same pooled set
    (transductive; mean 0 / unit variance) before cosine.
    """
    values = np.asarray(vectors, dtype=np.float64)
    labels = list(labels)
    if values.ndim != 2 or len(labels) != len(values) or not np.isfinite(values).all():
        raise ValueError("vectors must be finite [N, D] with one label per row")
    normalization = "none (raw cosine)"
    if standardize:
        std = values.std(axis=0)
        values = (values - values.mean(axis=0)) / np.where(std > 0, std, 1.0)
        normalization = (
            "per-dimension z-score on the pooled evaluation set, then cosine"
        )
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if (norms == 0).any():
        raise ValueError("zero vector cannot define cosine")
    unit = values / norms
    rows, cols = np.triu_indices(len(values), k=1)
    cosine = np.sum(unit[rows] * unit[cols], axis=1)
    names = np.asarray(labels, dtype=object)
    same_mask = names[rows] == names[cols]
    same, other = cosine[same_mask], cosine[~same_mask]
    if not len(same) or not len(other):
        raise ValueError("need both same-speaker and other-speaker pairs")
    # Mann-Whitney U via average ranks (ties share the mean rank).
    order = np.concatenate([same, other])
    ranks = np.empty(len(order))
    sorter = np.argsort(order, kind="mergesort")
    sorted_values = order[sorter]
    start = 0
    while start < len(sorted_values):
        end = start
        while (
            end + 1 < len(sorted_values)
            and sorted_values[end + 1] == sorted_values[start]
        ):
            end += 1
        ranks[sorter[start : end + 1]] = (start + end) / 2 + 1
        start = end + 1
    rank_sum = ranks[: len(same)].sum()
    auc = (rank_sum - len(same) * (len(same) + 1) / 2) / (len(same) * len(other))
    return {
        "auc": float(auc),
        "same_mean": float(same.mean()),
        "other_mean": float(other.mean()),
        "gap": float(same.mean() - other.mean()),
        "n_speakers": len(set(labels)),
        "n_utterances": len(labels),
        "n_same_pairs": len(same),
        "n_other_pairs": len(other),
        "normalization": normalization,
    }


def lda_speaker_probe(
    features_a,
    features_b,
    labels,
    *,
    seeds=(0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    n_train=12,
    min_mean_diff=0.005,
    min_wins=7,
):
    """Supervised linear probe: does feature set B separate unseen speakers better?

    Per seed, ``default_rng(seed).permutation`` of the sorted speaker IDs gives
    ``n_train`` train speakers and the rest as test speakers. Each feature set
    is standardized with train-utterance mean/std, an LDA (eigen, shrinkage
    auto) is fit on train speakers, and test utterances are scored by cosine
    verification AUC (``pairwise_separability``). Pre-registered verdict: B
    passes iff mean(AUC_B - AUC_A) >= ``min_mean_diff`` and AUC_B > AUC_A in at
    least ``min_wins`` splits. A split whose LDA raises is recorded and counts
    as AUC_B <= AUC_A with diff 0 (never silently skipped).
    """
    from sklearn.discriminant_analysis import (  # noqa: PLC0415
        LinearDiscriminantAnalysis,
    )

    sets = {
        "A": np.asarray(features_a, dtype=np.float64),
        "B": np.asarray(features_b, dtype=np.float64),
    }
    names = np.asarray(list(labels), dtype=object)
    if any(v.ndim != 2 or len(v) != len(names) for v in sets.values()):
        raise ValueError("features must be [N, D] with one label per row")
    speakers = sorted(set(names.tolist()))
    if len(speakers) <= n_train:
        raise ValueError("need more speakers than n_train")
    splits = []
    for seed in seeds:
        order = np.random.default_rng(seed).permutation(speakers).tolist()
        train, test = sorted(order[:n_train]), sorted(order[n_train:])
        train_mask = np.isin(names, train)
        test_mask = np.isin(names, test)
        split = {
            "seed": int(seed),
            "train_speakers": train,
            "test_speakers": test,
            "auc": {},
            "error": None,
        }
        try:
            for key, values in sets.items():
                mean = values[train_mask].mean(axis=0)
                std = values[train_mask].std(axis=0)
                scaled = (values - mean) / np.where(std > 0, std, 1.0)
                lda = LinearDiscriminantAnalysis(solver="eigen", shrinkage="auto")
                lda.fit(scaled[train_mask], names[train_mask].tolist())
                projected = lda.transform(scaled[test_mask])
                split["auc"][key] = pairwise_separability(
                    projected, names[test_mask].tolist()
                )["auc"]
            split["diff"] = split["auc"]["B"] - split["auc"]["A"]
            split["b_wins"] = split["diff"] > 0
        except Exception as exc:  # noqa: BLE001 — recorded, counted against B
            split["error"] = f"{type(exc).__name__}: {exc}"
            split["diff"] = 0.0
            split["b_wins"] = False
        splits.append(split)
    mean_diff = float(np.mean([s["diff"] for s in splits]))
    wins = sum(s["b_wins"] for s in splits)
    return {
        "splits": splits,
        "mean_diff": mean_diff,
        "wins": wins,
        "n_splits": len(splits),
        "passes": bool(mean_diff >= min_mean_diff and wins >= min_wins),
        "rule": f"mean(AUC_B-AUC_A) >= {min_mean_diff} and AUC_B > AUC_A in >= {min_wins} splits",
    }


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
