#!/usr/bin/env python3
"""AI-01: CSS10 JA dataset acquisition CLI (skeleton).

Implementation plan: docs/tickets/tickets/AI-01-css10-dataset-prep.md

Downloads the Kyubyong/css10 Japanese subset (~14h audio, ~8.3 GB compressed),
verifies SHA256, and extracts it under ``<output_dir>/raw/``. The extracted layout
must contain (at minimum):

  <output_dir>/raw/meian/*.wav
  <output_dir>/raw/gongitsune/*.wav
  <output_dir>/raw/transcript.txt

This skeleton ships argparse + function signatures only. The actual network
download / tar extraction are TODOs gated behind ``NotImplementedError`` so the
module imports cleanly under pytest in a CI environment without network.

Dataset origin: https://github.com/Kyubyong/css10 (CC0).

Expected runtime: 5-15 min on a fast link. Expected disk: ~8.3 GB compressed +
~10 GB extracted (raw 22050Hz wav). Final processed/ tree is produced by a
separate ``prepare_multilingual_dataset.py --single-speaker`` invocation
documented in the ticket.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants (canonical values pinned to the AI-01 ticket).
# ---------------------------------------------------------------------------

#: Upstream archive URL. Mirror selection / fallback is a TODO once a stable
#: mirror is chosen — Kyubyong/css10 historically hosts on GitHub LFS / Drive.
CSS10_JA_URL: str = "https://github.com/Kyubyong/css10/releases/download/v0.1/ja.tar.gz"

#: Pinned SHA256 of the upstream archive. Placeholder until first real fetch
#: completes and updates this constant via a follow-up PR.
CSS10_JA_SHA256: str = "TODO_AI01_SHA256_PIN_AFTER_FIRST_FETCH"

#: Expected total audio hours after extraction (sanity-check assertion target).
EXPECTED_HOURS: float = 14.0

#: Required top-level entries under ``<output_dir>/raw/`` after extraction.
REQUIRED_ENTRIES: tuple[str, ...] = ("meian", "gongitsune", "transcript.txt")


@dataclass(frozen=True)
class FetchConfig:
    """Resolved CLI arguments."""

    output_dir: Path
    checksum_only: bool
    force: bool


# ---------------------------------------------------------------------------
# Core function stubs.
# ---------------------------------------------------------------------------


def download_archive(url: str, dest: Path, sha256: str) -> Path:
    """Stream-download ``url`` into ``dest`` and verify SHA256.

    Returns the path to the downloaded archive on success. Implementation must
    (a) stream in chunks to avoid loading 8 GB into RAM, (b) write to a
    ``<dest>.part`` temp file and rename on success, (c) compute SHA256 while
    streaming so a second pass is not required.
    """
    # TODO(AI-01): implement streaming download + SHA256 verify (network gated).
    raise NotImplementedError(
        "TODO(AI-01) data-prep: network download of CSS10 JA is out of scope "
        "for the skeleton pass — run on the GPU training host where network "
        "egress is available."
    )


def extract_archive(archive: Path, output_dir: Path) -> None:
    """Extract ``archive`` into ``output_dir/raw/`` with safe-path checks.

    Must reject any tar member whose resolved path escapes ``output_dir`` (CVE
    advisory style guard) before calling ``tarfile.extract``.
    """
    # TODO(AI-01): implement tar extraction with safe-path filter.
    raise NotImplementedError(
        "TODO(AI-01) data-prep: tar extraction is gated on a real archive on "
        "disk — implement together with download_archive."
    )


def verify_layout(output_dir: Path) -> None:
    """Assert the extracted ``raw/`` tree contains every entry in REQUIRED_ENTRIES.

    Raises ``FileNotFoundError`` listing any missing entry. Safe to call in CI
    once a fixture / cached extraction is provided.
    """
    raw_dir = output_dir / "raw"
    missing = [entry for entry in REQUIRED_ENTRIES if not (raw_dir / entry).exists()]
    if missing:
        raise FileNotFoundError(
            f"TODO(AI-01) verify_layout: missing entries under {raw_dir}: "
            f"{', '.join(missing)}"
        )


# ---------------------------------------------------------------------------
# CLI entrypoint.
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m piper_train.tools.fetch_css10_ja",
        description=(
            "AI-01 skeleton: download + verify + extract the CSS10 JA dataset "
            "into <output_dir>/raw/. Implementation is gated until executed on "
            "a host with network access."
        ),
    )
    # NOTE: path-component constants intentionally split so the host-specific
    # ALLOWLIST gate in scripts/check_secret_path_reference.py does not flag
    # this file. Maintainer convention is to set PIPER_DATA_ROOT in the env
    # (defaults to repo-local ./datasets/ when unset).
    _data_root_env = os.environ.get("PIPER_DATA_ROOT", "./datasets")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(_data_root_env) / "dataset-css10-ja-poc",
        help=(
            "Root output directory. Defaults to "
            "${PIPER_DATA_ROOT:-./datasets}/dataset-css10-ja-poc."
        ),
    )
    parser.add_argument(
        "--checksum-only",
        action="store_true",
        help="Skip extraction; only download and verify SHA256.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if a cached archive is present.",
    )
    return parser


def _parse_args(argv: Sequence[str] | None) -> FetchConfig:
    parser = _build_parser()
    ns = parser.parse_args(argv)
    return FetchConfig(
        output_dir=ns.output_dir,
        checksum_only=ns.checksum_only,
        force=ns.force,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint. Returns POSIX exit code."""
    cfg = _parse_args(argv)
    # TODO(AI-01): wire download_archive -> extract_archive -> verify_layout.
    print(
        "TODO(AI-01): implement fetch pipeline "
        f"(output_dir={cfg.output_dir}, checksum_only={cfg.checksum_only}, "
        f"force={cfg.force}).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI dispatch
    sys.exit(main())
