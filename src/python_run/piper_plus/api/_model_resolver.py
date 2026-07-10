"""Model resolution and download logic."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path


logger = logging.getLogger(__name__)

# Well-known model aliases
MODEL_ALIASES: dict[str, dict[str, str]] = {
    "tsukuyomi": {
        "repo_id": "ayousanz/piper-plus-tsukuyomi-chan",
        "onnx_file": "tsukuyomi-chan-6lang-fp16.onnx",
        "config_file": "config.json",
    },
    "base": {
        "repo_id": "ayousanz/piper-plus-base",
        "onnx_file": "piper-plus-base-6lang-fp16.onnx",
        "config_file": "config.json",
    },
}

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "piper-plus" / "models"


class ModelNotFoundError(Exception):
    """Raised when a model cannot be found or downloaded."""


def resolve_model(
    model: str,
    config: str | None = None,
    download: bool = True,
    cache_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Resolve model name/path to ``(onnx_path, config_path)``.

    Resolution order:

    1. Direct file path (if *model* points to an existing ``.onnx`` file).
    2. Built-in alias (see :data:`MODEL_ALIASES`).
    3. HuggingFace repo ID (any string containing ``/``).
    4. Local cache directory lookup.

    Args:
        model: File path, alias name, or HuggingFace repo ID.
        config: Explicit config path.  Auto-detected if *None*.
        download: Whether to download from HuggingFace if not found locally.
        cache_dir: Cache directory for downloads.

    Returns:
        Tuple of ``(onnx_path, config_path)``.

    Raises:
        ModelNotFoundError: If model cannot be found.
    """
    cache_dir = cache_dir or DEFAULT_CACHE_DIR

    # Case 1: Direct file path
    onnx_path = Path(model)
    if onnx_path.is_file():
        config_path = _find_config(onnx_path, config)
        return onnx_path, config_path

    # Case 2: Alias
    if model in MODEL_ALIASES:
        alias = MODEL_ALIASES[model]
        return _download_from_hf(
            alias["repo_id"],
            alias["onnx_file"],
            alias["config_file"],
            cache_dir,
            download,
        )

    # Case 3: HuggingFace repo ID (contains '/')
    if "/" in model:
        return _download_from_hf(
            model,
            None,  # will auto-detect
            None,
            cache_dir,
            download,
        )

    # Case 4: Check cache
    cached = cache_dir / model
    if cached.is_dir():
        onnx_files = list(cached.glob("*.onnx"))
        if onnx_files:
            onnx_path = onnx_files[0]
            config_path = _find_config(onnx_path, config)
            return onnx_path, config_path

    raise ModelNotFoundError(
        f"Model '{model}' not found. "
        f"Available aliases: {', '.join(MODEL_ALIASES.keys())}. "
        f"Or provide a file path or HuggingFace repo ID (e.g., 'user/repo')."
    )


def _find_config(onnx_path: Path, config: str | None) -> Path:
    """Find config.json for an ONNX model."""
    if config:
        config_path = Path(config)
        if config_path.is_file():
            return config_path
        raise ModelNotFoundError(f"Config file not found: {config}")

    # Try common config file patterns
    for pattern in [
        onnx_path.with_suffix(onnx_path.suffix + ".json"),
        onnx_path.parent / "config.json",
        onnx_path.with_name("config.json"),
    ]:
        if pattern.is_file():
            return pattern

    raise ModelNotFoundError(
        f"Config file not found for {onnx_path}. "
        "Specify config= or place config.json next to the model."
    )


def _download_from_hf(
    repo_id: str,
    onnx_file: str | None,
    config_file: str | None,
    cache_dir: Path,
    download: bool,
) -> tuple[Path, Path]:
    """Download model from HuggingFace Hub."""
    if not download:
        raise ModelNotFoundError(f"Model '{repo_id}' not in cache and download=False")

    try:
        from huggingface_hub import hf_hub_download, list_repo_files  # noqa: PLC0415
    except ImportError:
        raise ImportError(
            "huggingface-hub is required for model download. "
            "Install with: pip install huggingface-hub"
        ) from None

    model_dir = cache_dir / repo_id.replace("/", "--")

    # Auto-detect files if not specified
    if onnx_file is None or config_file is None:
        files = list_repo_files(repo_id)
        if onnx_file is None:
            onnx_files = [f for f in files if f.endswith(".onnx")]
            if not onnx_files:
                raise ModelNotFoundError(f"No ONNX file found in {repo_id}")
            onnx_file = onnx_files[0]
        if config_file is None:
            config_file = "config.json"

    # If model_dir already has the files, return directly
    if model_dir.is_dir():
        existing_onnx = model_dir / onnx_file
        existing_config = model_dir / config_file
        if existing_onnx.is_file() and existing_config.is_file():
            return existing_onnx, existing_config

    # Download to a temporary directory first, then atomically rename
    # to mitigate race conditions when multiple processes download
    # the same model concurrently.
    # Note: hf_hub_download uses requests internally; to set a download
    # timeout, use the HF_HUB_DOWNLOAD_TIMEOUT environment variable
    # (supported by huggingface_hub >= 0.22).
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(dir=cache_dir))
    try:
        logger.info("Downloading %s from %s...", onnx_file, repo_id)
        onnx_path = Path(
            hf_hub_download(
                repo_id,
                onnx_file,
                local_dir=str(tmp_dir),
                force_download=False,
                resume_download=True,
            )
        )

        logger.info("Downloading %s from %s...", config_file, repo_id)
        config_path = Path(
            hf_hub_download(
                repo_id,
                config_file,
                local_dir=str(tmp_dir),
                force_download=False,
                resume_download=True,
            )
        )

        # Atomic move to final location
        try:
            tmp_dir.rename(model_dir)
        except OSError:
            # Another process may have already created the directory
            if model_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            else:
                raise

        # Resolve paths in the final directory
        onnx_path = model_dir / onnx_file
        config_path = model_dir / config_file
        return onnx_path, config_path

    except Exception:
        # Clean up temp dir on any failure
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
