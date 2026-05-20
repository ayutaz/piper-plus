"""Distroless entrypoint for the WebUI image.

The canonical Bash `docker/webui/entrypoint.sh`:
  1. Resolves $PIPER_MODEL_DIR (default `/models`).
  2. If $PIPER_MODEL is set, looks the model up under $PIPER_MODEL_DIR;
     downloads it via `piper_train.model_manager.download_model` if it
     isn't already there.
  3. Exec's `python /app/app.py --model-dir <dir> --output-dir <out>`
     with any extra args passed through.

gcr.io/distroless/python3-debian12 ships no shell, so the Bash wrapper
cannot run. This module ports the three steps above to pure Python and
is invoked from the Dockerfile via
    ENTRYPOINT ["/usr/bin/python3", "/app/entrypoint_distroless.py"]
so `docker run` extra args reach app.py untouched (just like the Bash
version's `"$@"`).

Behavioural parity:
  * Same env-var contract: $PIPER_MODEL / $PIPER_MODEL_DIR /
    $PIPER_OUTPUT_DIR.
  * Same exit codes on download failure (non-zero with a stderr line).
  * Same `exec`-style hand-off: this wrapper uses os.execvp so the
    Python interpreter for app.py replaces this process and signals
    (SIGTERM from `docker stop`) reach app.py directly.

Why pure Python rather than copying entrypoint.sh into the image:
  Distroless intentionally omits Bash. Adding a shell back would
  defeat the supply-chain win. The wrapper is small enough to live in
  the repo alongside app.py.
"""

from __future__ import annotations

import os
import sys


def _maybe_download_model() -> int:
    """Mirror entrypoint.sh's PIPER_MODEL download block.

    Returns the exit code we should propagate (0 on success or when no
    model name was provided; non-zero from the canonical script otherwise).
    """
    model_name = os.environ.get("PIPER_MODEL", "").strip()
    if not model_name:
        return 0

    model_dir = os.environ.get("PIPER_MODEL_DIR", "/models")
    print(f"Checking model: {model_name}", file=sys.stderr)

    # Lazy import inside the function: keeps the no-model path
    # (most common when developers `docker run` for ad-hoc smoke
    # tests) free of the piper_train + ONNX Runtime import cost.
    from piper_train.model_manager import (  # noqa: PLC0415
        download_model,
        resolve_model_path,
    )

    existing = resolve_model_path(model_name, model_dir)
    if existing:
        print(f"Model ready: {existing}", file=sys.stderr)
        return 0

    if not download_model(model_name, model_dir):
        print(f"Failed to download model: {model_name}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    rc = _maybe_download_model()
    if rc != 0:
        return rc

    model_dir = os.environ.get("PIPER_MODEL_DIR", "/models")
    output_dir = os.environ.get("PIPER_OUTPUT_DIR", "/output")

    # Hand off to app.py with the same flag layout the canonical
    # entrypoint.sh used. argv[1:] are the trailing args passed via
    # `docker run <image> -- ...`.
    cmd = [
        sys.executable,
        "/app/app.py",
        "--model-dir",
        model_dir,
        "--output-dir",
        output_dir,
        *argv[1:],
    ]
    # execvp is the intended PID-1 hand-off (replaces this process so
    # signals from `docker stop` reach app.py directly). S606 flags
    # any "process without shell" — that's the whole point here.
    os.execvp(cmd[0], cmd)  # noqa: S606
    # Unreachable: execvp replaces the process. Defensive return.
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
