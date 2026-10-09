"""Pinned inputs for audio generation and offline evaluation (no score imports)."""

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from piper_plus.embedding import validate_embedding

from .embedding_cache import atomic_write, file_sha256


NORMALIZATION_VERSION = "nfkc-strip-PZS-v1"
BACKENDS = ("torch-raw", "torch-ema", "onnx")


def _source_files() -> list[Path]:
    root = Path(__file__).resolve().parents[3]
    files = []
    for directory in (
        root / "src/python/piper_train",
        root / "src/python_run/piper_plus",
        root / "src/python/g2p/piper_plus_g2p",
    ):
        files.extend(directory.rglob("*.py"))
    files.extend(root.glob("pyproject.toml"))
    files.extend((root / "src").glob("*/pyproject.toml"))
    return sorted(files)


def inline_embedding_sha256(vector: list) -> str:
    return text_sha256(json.dumps(vector, separators=(",", ":")))


def clip_embedding(clip: dict, dimension: int) -> np.ndarray:
    value = clip.get("speaker_embedding")
    if value is None:
        value = np.load(clip["speaker_embedding_path"], allow_pickle=False)
    return validate_embedding(value, dimension)


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def conditions_sha256(manifest: dict) -> str:
    conditions = {
        key: value
        for key, value in manifest.items()
        if key not in ("models", "conditions_sha256")
    }
    return text_sha256(
        json.dumps(
            conditions, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
    )


def _pin(path: Path) -> dict:
    path = path.resolve()
    try:
        return {"path": str(path), "sha256": file_sha256(path)}
    except OSError as exc:
        raise ValueError(f"Missing evaluation input: {path}") from exc


def _verify_file(item: dict) -> None:
    if _pin(Path(item["path"]))["sha256"] != item["sha256"]:
        raise ValueError(f"evaluation input hash mismatch: {item['path']}")


def validate_manifest(manifest: dict, *, verify_files: bool = True) -> dict:
    """Validate the serialized schema before any model/ASR is constructed."""
    try:
        if manifest["version"] != 1:
            raise ValueError("Unsupported evaluation manifest version")
        clips = manifest["clips"]
        if not isinstance(clips, list) or not clips:
            raise ValueError("Evaluation clips must not be empty")
        ids = set()
        dimension = manifest["embedding_dimension"]
        if type(dimension) is not int or dimension < 1:
            raise ValueError("Invalid embedding dimension")
        for clip in clips:
            tid = clip["id"]
            if (
                not isinstance(tid, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", tid)
                or tid in ids
            ):
                raise ValueError(f"Invalid/duplicate clip ID: {tid}")
            ids.add(tid)
            if not isinstance(clip["text"], str) or not clip["text"].strip():
                raise ValueError(f"Empty text for {tid}")
            if clip["text_sha256"] != text_sha256(clip["text"]):
                raise ValueError(f"Text hash mismatch for {tid}")
            phonemes = clip["phoneme_ids"]
            if (
                not isinstance(phonemes, list)
                or not phonemes
                or any(type(value) is not int or value < 0 for value in phonemes)
            ):
                raise ValueError(f"Invalid phoneme_ids for {tid}")
            for field in ("language_id", "speaker_id"):
                if type(clip[field]) is not int or clip[field] < 0:
                    raise ValueError(f"Invalid {field} for {tid}")
            prosody = clip.get("prosody_features")
            if prosody is not None and (
                not isinstance(prosody, list)
                or len(prosody) != len(phonemes)
                or any(
                    item is not None
                    and (
                        not isinstance(item, dict)
                        or any(
                            type(item.get(key)) is not int for key in ("a1", "a2", "a3")
                        )
                    )
                    for item in prosody
                )
            ):
                raise ValueError(f"Invalid prosody_features for {tid}")
            inline = clip.get("speaker_embedding")
            if inline is not None:
                validate_embedding(inline, dimension)
                if inline_embedding_sha256(inline) != clip["speaker_embedding_sha256"]:
                    raise ValueError(f"Inline embedding hash mismatch for {tid}")
            if verify_files:
                if inline is None:
                    _verify_file(
                        {
                            "path": clip["speaker_embedding_path"],
                            "sha256": clip["speaker_embedding_sha256"],
                        }
                    )
                    clip_embedding(clip, dimension)
                for reference in clip["reference_audio"]:
                    _verify_file(reference)
        scales = manifest["scales"]
        if (
            not isinstance(scales, list)
            or len(scales) != 3
            or not np.isfinite(scales).all()
            or scales[0] < 0
            or scales[1] <= 0
            or scales[2] < 0
        ):
            raise ValueError("Invalid inference scales")
        if type(manifest["seed"]) is not int or not 0 <= manifest[
            "seed"
        ] <= 2**63 - len(clips):
            raise ValueError("Invalid inference seed")
        epoch = manifest.get("training_epoch")
        if epoch is not None and (type(epoch) is not int or epoch < 0):
            raise ValueError("Invalid training_epoch")
        source = manifest["source"]
        if not re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", source["revision"]):
            raise ValueError("Source revision must be pinned")
        if not isinstance(source["files"], list) or not source["files"]:
            raise ValueError("Actual source files must be pinned")
        if type(manifest["sample_rate"]) is not int or manifest["sample_rate"] <= 0:
            raise ValueError("Invalid sample_rate")
        asr = manifest["asr"]
        if asr["normalization"] != NORMALIZATION_VERSION or not re.fullmatch(
            r"[a-fA-F0-9]{40}", asr["revision"]
        ):
            raise ValueError("ASR revision/normalization must be pinned")
        if any(
            not isinstance(asr[key], str) or not asr[key].strip()
            for key in ("model", "language")
        ):
            raise ValueError("Missing ASR model/language")
        if (
            not isinstance(manifest["models"], dict)
            or not manifest["models"]
            or set(manifest["models"]) - set(BACKENDS)
        ):
            raise ValueError("Invalid evaluation backends")
        if manifest["conditions_sha256"] != conditions_sha256(manifest):
            raise ValueError("Evaluation conditions hash mismatch")
        if verify_files:
            for model in manifest["models"].values():
                _verify_file(model)
            source = manifest["source"]
            _verify_file(
                {"path": source["input_path"], "sha256": source["input_sha256"]}
            )
            _verify_file({"path": source["lock_path"], "sha256": source["lock_sha256"]})
            for implementation in source["files"]:
                _verify_file(implementation)
        return manifest
    except (KeyError, TypeError, AttributeError, OSError, OverflowError) as exc:
        raise ValueError(f"Invalid evaluation manifest: {exc}") from exc


def load_manifest(path: Path, *, verify_files: bool = True) -> dict:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Evaluation manifest must be an object")
    return validate_manifest(manifest, verify_files=verify_files)


def create_manifest(
    *,
    source_path: Path,
    output_path: Path,
    models: dict[str, Path],
    sample_rate: int,
    asr_revision: str,
    source_revision: str,
    scales=(0.4, 1.0, 0.5),
    seed=42,
    asr_model="openai/whisper-small",
    language="ja",
    dimension=192,
    lock_path: Path | None = None,
    training_epoch: int | None = None,
) -> dict:
    source_path = Path(source_path).resolve()
    source = _pin(source_path)
    lock = _pin(
        Path(lock_path)
        if lock_path
        else Path(__file__).resolve().parents[3] / "uv.lock"
    )
    clips = []
    try:
        for line in source_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            inline = entry.get("speaker_embedding")
            if inline is not None:
                inline = validate_embedding(inline, dimension).tolist()
                embedding = {"path": None, "sha256": inline_embedding_sha256(inline)}
            else:
                embedding = _pin(source_path.parent / entry["speaker_embedding_path"])
                validate_embedding(
                    np.load(embedding["path"], allow_pickle=False), dimension
                )
            references = [
                _pin(source_path.parent / reference)
                for reference in entry.get("reference_audio_paths", [])
            ]
            clips.append(
                {
                    "id": entry["id"],
                    "text": entry["text"],
                    "text_sha256": text_sha256(entry["text"]),
                    "phoneme_ids": entry["phoneme_ids"],
                    "language_id": entry.get("language_id", 0),
                    "speaker_id": entry.get("speaker_id", 0),
                    "speaker_embedding_path": embedding["path"],
                    "speaker_embedding": inline,
                    "speaker_embedding_sha256": embedding["sha256"],
                    "reference_audio": references,
                    "prosody_features": entry.get("prosody_features"),
                }
            )
    except (KeyError, TypeError, OSError) as exc:
        raise ValueError(f"Invalid evaluation source: {exc}") from exc
    manifest = {
        "version": 1,
        "source": {
            "revision": source_revision,
            "input_path": source["path"],
            "input_sha256": source["sha256"],
            "lock_path": lock["path"],
            "lock_sha256": lock["sha256"],
            "files": [_pin(path) for path in _source_files()],
        },
        "sample_rate": sample_rate,
        "embedding_dimension": dimension,
        "scales": list(scales),
        "seed": seed,
        "training_epoch": training_epoch,
        "asr": {
            "model": asr_model,
            "revision": asr_revision,
            "language": language,
            "normalization": NORMALIZATION_VERSION,
        },
        "clips": clips,
        "models": {backend: _pin(Path(path)) for backend, path in models.items()},
    }
    manifest["conditions_sha256"] = conditions_sha256(manifest)
    validate_manifest(manifest)
    atomic_write(
        Path(output_path),
        lambda target: target.write(
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        ),
    )
    return manifest
