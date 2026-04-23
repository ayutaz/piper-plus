#!/usr/bin/env python3
"""Build a PE-A audio style bank (``.npz``) from an emotion-labelled dataset.

This tool extracts audio embeddings via the Meta "Perception Encoder" family
(``facebook/pe-av-small``) and aggregates them into per-emotion centroids
plus a global centroid. The resulting ``.npz`` file is byte-for-byte
compatible with the fork ``yusuke-ai/piper-plus``'s ``_init_pea_emotion_loss``
buffer loader, so the same artefact can be consumed by Phase 4 without
schema translation.

Schema::

    emotion_names     : object (str)  [N]
    emotion_centroids : float32        [N, D]   (L2-normalised rows)
    global_centroid   : float32        [D]      (raw mean, not re-normalised)

Two model loaders are tried in order (following the Phase 0 P0-T03 outcome):

1. ``transformers.AutoModel.from_pretrained("facebook/pe-av-small", ...)``
   with ``trust_remote_code=True``. Known to fail today because the
   ``model_type=pe_audio_video`` auto-class is not yet upstreamed.
2. ``perception_models`` (Meta's ``facebookresearch/perception_models`` pip
   package). If the package is installed, we import
   ``perception_models.pe_av.PEAudio`` and call its ``get_audio_embeds``.

If BOTH loaders fail, a clear ``ImportError`` with an installation hint is
raised so downstream phases can diagnose quickly.

CLI examples::

    # Generate style bank from a CREMA-D staging directory
    uv run python -m piper_train.tools.build_pea_style_bank \\
        --input-dataset /data/piper/datasets/CREMA-D \\
        --output-bank   /data/piper/style_bank_crema_d.npz \\
        --per-utterance-dir /data/piper/style_vectors_crema_d

    # Read from a CSV/JSONL manifest instead of CREMA-D folder layout
    uv run python -m piper_train.tools.build_pea_style_bank \\
        --manifest /data/piper/custom_emotion.csv \\
        --output-bank /data/piper/style_bank_custom.npz
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - fallback when tqdm missing
    def tqdm(iterable, **_kwargs):  # type: ignore[misc]
        return iterable

_LOGGER = logging.getLogger("build_pea_style_bank")

PE_A_SAMPLE_RATE = 16000
PE_A_DEFAULT_MODEL = "facebook/pe-av-small"

# CREMA-D 4-part filename convention:  <speaker>_<sentence>_<emotion>_<intensity>
EMOTION_CODE_MAP = {
    "ANG": "angry",
    "DIS": "disgusted",
    "FEA": "fearful",
    "HAP": "happy",
    "NEU": "neutral",
    "SAD": "sad",
}


# ---------------------------------------------------------------------------
# Audio dataset
# ---------------------------------------------------------------------------


class EmotionAudioDataset:
    """Iterable over ``(audio_array, emotion, audio_path)`` samples.

    Two ingestion modes are supported:

    * ``_load_from_crema_d``: walks ``<dataset_dir>/AudioWAV/*.wav`` and
      derives the emotion from the filename's third underscore segment.
    * ``_load_from_manifest``: accepts CSV or JSONL with ``audio_path`` +
      ``emotion`` columns (any key-style is fine for JSONL).

    The dataset is *lightweight* by design: audio loading and resampling are
    deferred to ``__getitem__`` so that massive CREMA-D-sized corpora can be
    enumerated without OOM. Each fetched sample is converted to mono, peak
    normalised, and returned as a 1-D float32 numpy array.
    """

    def __init__(
        self,
        dataset_dir: Optional[Path] = None,
        manifest_path: Optional[Path] = None,
        sample_rate: int = PE_A_SAMPLE_RATE,
    ) -> None:
        self.dataset_dir = Path(dataset_dir) if dataset_dir else None
        self.manifest_path = Path(manifest_path) if manifest_path else None
        self.sample_rate = sample_rate
        self.samples: list[dict[str, Any]] = []

        if manifest_path is not None:
            self._load_from_manifest(Path(manifest_path))
        elif dataset_dir is not None:
            self._load_from_crema_d()
        else:
            raise ValueError(
                "EmotionAudioDataset requires either dataset_dir or manifest_path"
            )

    def _load_from_crema_d(self) -> None:
        assert self.dataset_dir is not None
        audio_dir = self.dataset_dir / "AudioWAV"
        if not audio_dir.exists():
            raise FileNotFoundError(f"AudioWAV directory not found: {audio_dir}")
        for wav_file in sorted(audio_dir.glob("*.wav")):
            parts = wav_file.stem.split("_")
            if len(parts) < 4:
                _LOGGER.warning(
                    "Skipping malformed CREMA-D filename: %s", wav_file.name
                )
                continue
            code = parts[2]
            emotion = EMOTION_CODE_MAP.get(code)
            if emotion is None:
                _LOGGER.warning(
                    "Unknown CREMA-D emotion code %r in %s", code, wav_file.name
                )
                continue
            self.samples.append({"audio_path": wav_file, "emotion": emotion})

    def _load_from_manifest(self, manifest_path: Path) -> None:
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")
        suffix = manifest_path.suffix.lower()
        if suffix == ".jsonl":
            self._load_jsonl(manifest_path)
        else:
            self._load_csv(manifest_path)

    def _load_jsonl(self, path: Path) -> None:
        with open(path, "r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:  # pragma: no cover
                    _LOGGER.warning(
                        "Skipping bad JSONL row %d in %s: %s", line_no, path, exc
                    )
                    continue
                audio_path = item.get("audio_path") or item.get("audio_norm_path")
                emotion = item.get("emotion")
                if not audio_path or not emotion:
                    _LOGGER.warning(
                        "Row %d missing audio_path/emotion: %s", line_no, item
                    )
                    continue
                self.samples.append(
                    {"audio_path": Path(audio_path), "emotion": str(emotion).lower()}
                )

    def _load_csv(self, path: Path) -> None:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(
                (ln for ln in fh if ln and not ln.startswith("#"))
            )
            for row_no, row in enumerate(reader, start=1):
                audio_path = row.get("audio_path") or row.get("audio_norm_path")
                emotion = row.get("emotion")
                if not audio_path or not emotion:
                    _LOGGER.warning(
                        "CSV row %d missing audio_path/emotion: %s", row_no, row
                    )
                    continue
                self.samples.append(
                    {"audio_path": Path(audio_path), "emotion": emotion.lower()}
                )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        item = self.samples[idx]
        audio_path: Path = item["audio_path"]
        audio = self._load_audio(audio_path)
        return {
            "audio": audio,
            "emotion": item["emotion"],
            "audio_path": str(audio_path),
        }

    def _load_audio(self, path: Path) -> np.ndarray:
        """Return a mono, peak-normalised float32 waveform at ``self.sample_rate``."""
        import soundfile as sf  # type: ignore[import-not-found]

        waveform, sr = sf.read(str(path), dtype="float32", always_2d=False)
        if waveform.ndim == 2:
            waveform = waveform.mean(axis=1)
        if sr != self.sample_rate:
            # Prefer torchaudio when available (accurate sinc resampler);
            # fall back to numpy linear interpolation for environments that do
            # not ship torchaudio (PE-A build host usually has it).
            waveform = _resample(waveform, sr, self.sample_rate)
        peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
        if peak > 0:
            waveform = waveform / peak
        return waveform.astype(np.float32, copy=False)


def _resample(waveform: np.ndarray, src_sr: int, tgt_sr: int) -> np.ndarray:
    """Resample with torchaudio if available; otherwise linear-interpolation."""
    if src_sr == tgt_sr:
        return waveform
    try:
        import torch
        import torchaudio.functional as taF  # type: ignore[import-not-found]

        t = torch.from_numpy(waveform.astype(np.float32))
        resampled = taF.resample(t, src_sr, tgt_sr)
        return resampled.numpy()
    except ImportError:
        # Minimal linear interpolation fallback.
        ratio = tgt_sr / src_sr
        n_out = int(round(len(waveform) * ratio))
        if n_out <= 1:
            return waveform[:1].astype(np.float32, copy=False)
        idx = np.linspace(0, len(waveform) - 1, n_out)
        left = np.floor(idx).astype(np.int64)
        right = np.clip(left + 1, 0, len(waveform) - 1)
        frac = idx - left
        out = waveform[left] * (1.0 - frac) + waveform[right] * frac
        return out.astype(np.float32, copy=False)


# ---------------------------------------------------------------------------
# PE-A model loading
# ---------------------------------------------------------------------------


class PEAModelError(RuntimeError):
    """Raised when neither PE-A loader path is usable."""


def load_pea_model(
    model_name: str = PE_A_DEFAULT_MODEL,
    device: str = "cpu",
):
    """Load a PE-A audio model via transformers Option A then perception_models.

    Returns an opaque handle whose sole required capability is understood by
    :func:`extract_audio_embedding`. On failure, raises :class:`PEAModelError`
    containing actionable installation hints (logged to stderr as well).
    """
    errors: list[str] = []

    # Option A: transformers AutoModel with trust_remote_code
    try:
        from transformers import AutoModel  # type: ignore[import-not-found]

        _LOGGER.info("Trying transformers.AutoModel.from_pretrained(%r)", model_name)
        model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
        model.eval()
        if hasattr(model, "to"):
            model = model.to(device)
        return {"kind": "transformers", "model": model, "name": model_name}
    except Exception as exc:  # pragma: no cover - depends on env
        msg = f"transformers AutoModel failed: {exc}"
        _LOGGER.info(msg)
        errors.append(msg)

    # Option B: perception_models pip package
    try:
        import importlib

        pm = importlib.import_module("perception_models")
        _LOGGER.info("Loaded perception_models version=%s", getattr(pm, "__version__", "?"))
        # Primary symbol proposed upstream; tolerate minor re-organisations.
        PEAudio = None
        for mod_path in ("perception_models.pe_av", "perception_models.pe_audio"):
            try:
                sub = importlib.import_module(mod_path)
            except ImportError:
                continue
            for attr in ("PEAudio", "PEAModel", "AudioEncoder"):
                if hasattr(sub, attr):
                    PEAudio = getattr(sub, attr)
                    break
            if PEAudio is not None:
                break
        if PEAudio is None:
            raise ImportError(
                "perception_models installed but no PEAudio/PEAModel class found"
            )
        model = PEAudio.from_pretrained(model_name) if hasattr(
            PEAudio, "from_pretrained"
        ) else PEAudio()
        if hasattr(model, "eval"):
            model.eval()
        if hasattr(model, "to"):
            model = model.to(device)
        return {"kind": "perception_models", "model": model, "name": model_name}
    except Exception as exc:
        msg = f"perception_models import failed: {exc}"
        _LOGGER.info(msg)
        errors.append(msg)

    hint = (
        "PE-A model could not be loaded. Tried (A) transformers AutoModel and "
        "(B) perception_models. Install options:\n"
        "  A) pip install transformers>=4.40  (requires upstream model_type=pe_audio_video support)\n"
        "  B) pip install git+https://github.com/facebookresearch/perception_models.git\n"
        "Errors:\n  - " + "\n  - ".join(errors)
    )
    raise PEAModelError(hint)


def extract_audio_embedding(
    model_handle: dict[str, Any],
    audio: np.ndarray,
    device: str = "cpu",
) -> np.ndarray:
    """Extract a single L2-normalised audio embedding as a 1-D numpy array.

    PE-A accepts variable-length waveforms; we therefore run it with
    ``batch_size=1``.
    """
    import torch

    model = model_handle["model"]
    tensor = torch.from_numpy(np.asarray(audio, dtype=np.float32))
    if tensor.ndim == 1:
        tensor = tensor.unsqueeze(0)  # [1, T]
    tensor = tensor.to(device)

    with torch.no_grad():
        embed = None
        # Preferred API surface
        for fn_name in ("get_audio_embeds", "encode_audio", "forward_audio"):
            if hasattr(model, fn_name):
                embed = getattr(model, fn_name)(tensor)
                break
        if embed is None:
            # Fallback: call with keyword or positional
            try:
                embed = model(audio=tensor)
            except TypeError:
                embed = model(tensor)

    if not isinstance(embed, torch.Tensor):
        # Some implementations return dataclass/dict
        if isinstance(embed, dict):
            for key in ("audio_embeds", "embedding", "last_hidden_state", "pooler_output"):
                if key in embed:
                    embed = embed[key]
                    break
        else:
            embed = getattr(embed, "audio_embeds", None) or getattr(embed, "embedding", embed)
        if not isinstance(embed, torch.Tensor):  # pragma: no cover - defensive
            raise TypeError(f"Unexpected PE-A output type: {type(embed)}")

    if embed.ndim == 3:
        # [B, T, D] -> mean-pool over time
        embed = embed.mean(dim=1)
    if embed.ndim == 2:
        embed = embed.squeeze(0)
    if embed.ndim != 1:
        raise ValueError(f"PE-A embedding has unexpected shape: {tuple(embed.shape)}")

    vec = embed.detach().cpu().numpy().astype(np.float32, copy=False)
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return vec


# ---------------------------------------------------------------------------
# Centroid aggregation and I/O
# ---------------------------------------------------------------------------


def compute_centroids(
    all_embeddings: np.ndarray,
    emotion_labels: list[str],
) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Compute per-emotion + global centroids from stacked embeddings.

    * per-emotion centroid: ``L2_normalise(mean(embeddings_for_emotion))``
    * global centroid: raw mean over ALL embeddings (no re-normalisation)
    """
    if all_embeddings.ndim != 2:
        raise ValueError(
            f"all_embeddings must be 2-D [N, D]; got {all_embeddings.shape}"
        )
    if len(emotion_labels) != all_embeddings.shape[0]:
        raise ValueError(
            f"Label length {len(emotion_labels)} != embeddings {all_embeddings.shape[0]}"
        )

    unique_emotions = sorted(set(emotion_labels))
    embedding_dim = all_embeddings.shape[1]
    centroids = np.zeros((len(unique_emotions), embedding_dim), dtype=np.float32)
    labels_arr = np.asarray(emotion_labels)
    for i, emotion in enumerate(unique_emotions):
        mask = labels_arr == emotion
        subset = all_embeddings[mask]
        if len(subset) == 0:  # pragma: no cover - defensive
            continue
        mean_vec = subset.mean(axis=0)
        norm = float(np.linalg.norm(mean_vec))
        if norm > 0:
            mean_vec = mean_vec / norm
        centroids[i] = mean_vec.astype(np.float32, copy=False)

    global_centroid = all_embeddings.mean(axis=0).astype(np.float32, copy=False)
    return unique_emotions, centroids, global_centroid


def save_style_bank(
    output_path: Path,
    emotion_names: list[str],
    emotion_centroids: np.ndarray,
    global_centroid: np.ndarray,
) -> None:
    """Persist the style bank to a ``.npz`` file with the schema documented above."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if emotion_centroids.dtype != np.float32:
        emotion_centroids = emotion_centroids.astype(np.float32)
    if global_centroid.dtype != np.float32:
        global_centroid = global_centroid.astype(np.float32)

    # Sanity: L2 norm of each centroid row must be ~1.0 for PE-A loss.
    row_norms = np.linalg.norm(emotion_centroids, axis=-1)
    bad = np.where(np.abs(row_norms - 1.0) > 1e-3)[0]
    if bad.size > 0:
        raise ValueError(
            f"emotion_centroids rows not L2-normalised; bad indices: {bad.tolist()}"
        )

    np.savez(
        str(output_path),
        emotion_names=np.array(emotion_names, dtype=object),
        emotion_centroids=emotion_centroids,
        global_centroid=global_centroid,
    )
    _LOGGER.info(
        "Saved style bank: %s (N=%d, D=%d)",
        output_path,
        emotion_centroids.shape[0],
        emotion_centroids.shape[1],
    )


def generate_report(
    output_path: Path,
    emotion_names: list[str],
    emotion_centroids: np.ndarray,
    global_centroid: np.ndarray,
    per_emotion_counts: dict[str, int],
) -> None:
    """Write a JSON report with per-emotion counts + cosine similarity matrix."""
    if emotion_centroids.shape[0] == 0:
        cos_matrix: list[list[float]] = []
    else:
        norms = np.linalg.norm(emotion_centroids, axis=-1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        normed = emotion_centroids / norms
        cos_matrix = (normed @ normed.T).astype(float).tolist()

    report = {
        "emotion_names": list(emotion_names),
        "counts": per_emotion_counts,
        "embedding_dim": int(emotion_centroids.shape[1]) if emotion_centroids.size else 0,
        "cosine_similarity_matrix": cos_matrix,
        "global_centroid_norm": float(np.linalg.norm(global_centroid)),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    _LOGGER.info("Wrote report: %s", output_path)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def build_style_bank(
    dataset: EmotionAudioDataset,
    model_handle: dict[str, Any],
    device: str = "cpu",
    per_utterance_dir: Optional[Path] = None,
) -> tuple[list[str], np.ndarray, np.ndarray, dict[str, int]]:
    """Iterate over the dataset, extract embeddings, and aggregate centroids."""
    if per_utterance_dir is not None:
        per_utterance_dir = Path(per_utterance_dir)
        per_utterance_dir.mkdir(parents=True, exist_ok=True)

    emotion_labels: list[str] = []
    embeddings: list[np.ndarray] = []
    counts: dict[str, int] = {}

    for idx in tqdm(range(len(dataset)), desc="Extracting PE-A embeddings"):
        sample = dataset[idx]
        emb = extract_audio_embedding(model_handle, sample["audio"], device=device)
        embeddings.append(emb)
        emotion_labels.append(sample["emotion"])
        counts[sample["emotion"]] = counts.get(sample["emotion"], 0) + 1

        if per_utterance_dir is not None:
            utt_id = Path(sample["audio_path"]).stem
            np.save(str(per_utterance_dir / f"{utt_id}.npy"), emb)

    if not embeddings:
        raise RuntimeError("No audio samples were processed; check dataset inputs")

    stacked = np.stack(embeddings, axis=0)
    emotion_names, centroids, global_centroid = compute_centroids(
        stacked, emotion_labels
    )
    return emotion_names, centroids, global_centroid, counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_argv(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build PE-A emotion style bank (.npz) from labelled audio"
    )
    ingest = parser.add_mutually_exclusive_group(required=True)
    ingest.add_argument(
        "--input-dataset",
        type=Path,
        default=None,
        help="Path to a CREMA-D-style dataset (contains AudioWAV/)",
    )
    ingest.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="CSV or JSONL manifest with audio_path + emotion columns",
    )

    parser.add_argument(
        "--output-bank",
        type=Path,
        required=True,
        help="Destination .npz file",
    )
    parser.add_argument(
        "--per-utterance-dir",
        type=Path,
        default=None,
        help="Optional directory for per-utterance <utt_id>.npy embeddings",
    )
    parser.add_argument(
        "--pe-model-name",
        default=PE_A_DEFAULT_MODEL,
        help="HuggingFace or perception_models model identifier",
    )
    parser.add_argument(
        "--emotion-column",
        default="emotion",
        help=(
            "Manifest column that carries the emotion label (CSV/JSONL). "
            "The CREMA-D loader ignores this option and uses filename parsing."
        ),
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="PyTorch device string (cpu / cuda / cuda:0 / mps)",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=PE_A_SAMPLE_RATE,
        help="Target sample rate for resampling (PE-A expects 16000)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional JSON report path (default: <output-bank>.report.json)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_argv(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    dataset = EmotionAudioDataset(
        dataset_dir=args.input_dataset,
        manifest_path=args.manifest,
        sample_rate=args.sample_rate,
    )
    _LOGGER.info("Loaded dataset: %d samples", len(dataset))
    if len(dataset) == 0:
        _LOGGER.error("Dataset is empty; nothing to do")
        return 1

    try:
        model_handle = load_pea_model(args.pe_model_name, device=args.device)
    except PEAModelError as exc:
        _LOGGER.error("%s", exc)
        return 2

    emotion_names, centroids, global_centroid, counts = build_style_bank(
        dataset=dataset,
        model_handle=model_handle,
        device=args.device,
        per_utterance_dir=args.per_utterance_dir,
    )

    save_style_bank(args.output_bank, emotion_names, centroids, global_centroid)

    report_path = args.report or Path(str(args.output_bank) + ".report.json")
    generate_report(
        report_path,
        emotion_names=emotion_names,
        emotion_centroids=centroids,
        global_centroid=global_centroid,
        per_emotion_counts=counts,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - thin entry point
    sys.exit(main())
