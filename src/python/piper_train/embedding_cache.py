"""Content-addressed, provenance-checked speaker embedding cache."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

import numpy as np

from piper_plus.embedding import validate_embedding


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, write) -> None:
    """Publish a completed file by rename; never expose partially written data."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as target:
            write(target)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def cache_key(metadata: dict) -> str:
    payload = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def read_verified(path: Path, expected: dict) -> np.ndarray | None:
    """Unidentified encoders and legacy/partial/corrupt caches are not reusable."""
    if not expected.get("encoder_sha256"):
        return None
    try:
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            return None
        if any(metadata.get(key) != value for key, value in expected.items()):
            return None
        if metadata.get("embedding_sha256") != file_sha256(path):
            return None
        return validate_embedding(
            np.load(path, allow_pickle=False), expected["dimension"]
        )
    except (OSError, ValueError, TypeError, KeyError, EOFError):
        return None


def save_verified(path: Path, vector, metadata: dict) -> None:
    vector = validate_embedding(vector, metadata["dimension"])
    atomic_write(path, lambda target: np.save(target, vector, allow_pickle=False))
    sidecar = {**metadata, "embedding_sha256": file_sha256(path)}
    atomic_write(
        path.with_suffix(".json"),
        lambda target: target.write(json.dumps(sidecar, sort_keys=True).encode()),
    )
    # Also check writes when encoder identity is unavailable (no future reuse).
    written = np.load(path, allow_pickle=False)
    validate_embedding(written, metadata["dimension"])
    if not np.array_equal(written, vector):
        raise ValueError("speaker_embedding changed during atomic publication")
