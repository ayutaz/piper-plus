#!/usr/bin/env python3
"""Upload a Piper-Plus model config (and optionally the .onnx) to Hugging Face Hub.

Always runs `update_model_config.py --validate-only` before upload. That
pre-flight check is the gate that would have blocked the v1.12.0
ɔɪ/œ̃/ɐ̃ regression — without it, multi-codepoint phoneme keys can leak
into the distributed config.json and break C++ inference.

Usage
-----
    # Validate + upload a single config
    python scripts/upload_model_to_hf.py \
        --repo ayousanz/piper-plus-tsukuyomi-chan \
        --config tmp/tsukuyomi-chan-6lang-fp16.onnx.json

    # Validate + upload config and onnx together
    python scripts/upload_model_to_hf.py \
        --repo ayousanz/piper-plus-tsukuyomi-chan \
        --config tmp/tsukuyomi-chan-6lang-fp16.onnx.json \
        --onnx   tmp/tsukuyomi-chan-6lang-fp16.onnx

    # Dry-run (validate only, do not call HF API)
    python scripts/upload_model_to_hf.py --repo ... --config ... --dry-run

    # CI usage: skip interactive token prompt (HF_TOKEN env var required)
    HF_TOKEN=hf_xxx python scripts/upload_model_to_hf.py --repo ... --config ...

The HF token is read from `HF_TOKEN` (preferred) or `HUGGING_FACE_HUB_TOKEN`.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


class UploadAbortedError(RuntimeError):
    """Raised when validation fails — upload must not proceed."""


def run_validation(config_path: Path) -> None:
    """Invoke `python -m piper_train.update_model_config --validate-only`.

    Raises UploadAbortedError if the config still contains multi-codepoint
    phoneme_id_map keys (i.e. PUA normalization didn't fully run).
    """
    print(f"==> Pre-flight validation: {config_path}")
    src_python = REPO_ROOT / "src" / "python"
    cmd = [
        sys.executable,
        "-m",
        "piper_train.update_model_config",
        "--validate-only",
        str(config_path),
    ]
    result = subprocess.run(
        cmd,
        cwd=src_python,
        capture_output=True,
        text=True,
        check=False,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise UploadAbortedError(
            f"validate-only check failed (exit {result.returncode}). "
            "Refusing to upload — fix the config first "
            "(see scripts/regenerate_tsukuyomi_config.py)."
        )
    print("==> Validation passed.")


def upload(
    repo: str,
    files: list[tuple[Path, str]],
    *,
    commit_message: str,
    dry_run: bool,
) -> None:
    """Upload `files` (local_path, repo_path) to HF Hub repo `repo`."""
    if dry_run:
        print("==> DRY RUN — would upload to HF Hub:")
        for local, remote in files:
            print(f"      {local} -> hf://{repo}/{remote}")
        return

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        raise UploadAbortedError(
            "HF_TOKEN (or HUGGING_FACE_HUB_TOKEN) env var must be set "
            "for non-interactive uploads."
        )

    try:
        from huggingface_hub import HfApi
    except ImportError as e:
        raise UploadAbortedError(
            "huggingface_hub is not installed. "
            "Install with `uv pip install huggingface_hub` and retry."
        ) from e

    api = HfApi(token=token)
    print(f"==> Uploading {len(files)} file(s) to {repo}")
    for local, remote in files:
        print(f"    {local.name} -> {remote}")
        api.upload_file(
            path_or_fileobj=str(local),
            path_in_repo=remote,
            repo_id=repo,
            commit_message=commit_message,
        )
    print("==> Upload complete.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        required=True,
        help="HuggingFace repo id (e.g. ayousanz/piper-plus-tsukuyomi-chan)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Local path to the model config.json to validate and upload",
    )
    parser.add_argument(
        "--onnx",
        type=Path,
        default=None,
        help="Optional: local path to the .onnx file to upload alongside config",
    )
    parser.add_argument(
        "--config-remote-name",
        default=None,
        help="Repo-side filename for the config (default: same as local)",
    )
    parser.add_argument(
        "--onnx-remote-name",
        default=None,
        help="Repo-side filename for the onnx (default: same as local)",
    )
    parser.add_argument(
        "--commit-message",
        default="Update model config (validated by upload_model_to_hf.py)",
        help="Commit message for the HF upload",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run validation but do not call HF API",
    )
    args = parser.parse_args()

    if not args.config.exists():
        print(f"ERROR: config not found: {args.config}", file=sys.stderr)
        return 2
    if args.onnx and not args.onnx.exists():
        print(f"ERROR: onnx not found: {args.onnx}", file=sys.stderr)
        return 2

    try:
        run_validation(args.config)
    except UploadAbortedError as e:
        print(f"ABORT: {e}", file=sys.stderr)
        return 1

    files: list[tuple[Path, str]] = [
        (args.config, args.config_remote_name or args.config.name),
    ]
    if args.onnx:
        files.append((args.onnx, args.onnx_remote_name or args.onnx.name))

    try:
        upload(
            args.repo,
            files,
            commit_message=args.commit_message,
            dry_run=args.dry_run,
        )
    except UploadAbortedError as e:
        print(f"ABORT: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
