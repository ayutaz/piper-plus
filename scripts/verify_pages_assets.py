#!/usr/bin/env python3
"""Verify that critical assets on the deployed GitHub Pages site return HTTP 200.

Runs after `actions/deploy-pages` finishes, mirroring the philosophy of the
HF Space post-deploy gate: `deploy-pages` succeeds as soon as GitHub accepts
the artifact upload, but a missing asset (favicon, model config, WASM bundle)
only manifests as a console 404 once a user opens the page.

This script HEAD-probes each required path against the live origin and
fails the workflow if any returns a non-2xx response. That turns "404 sits
unnoticed for weeks" into an immediate red CI on the deploy run.

Exit codes:
  0 — every required asset returned 2xx within the retry budget
  1 — at least one asset is missing or unreachable
  2 — usage / argument error
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from typing import Iterable


# Critical assets on the piper-plus Pages site. Update this list when the
# deploy bundle layout changes — the gate is only as good as this list.
#
# Note on favicon: we ship `assets/favicon.svg` and reference it from
# <link rel="icon"> in every HTML. Modern browsers (Chrome/Firefox/Safari)
# skip the `/favicon.ico` auto-fetch when an explicit <link rel="icon"> is
# present, so we deliberately do NOT require `/favicon.ico` here — that
# would force shipping a binary ICO solely to silence a console message.
DEFAULT_REQUIRED_PATHS: tuple[str, ...] = (
    "",  # site root
    "assets/favicon.svg",  # explicit favicon target referenced from <link rel=icon>
    "src/index.js",
    "src/model-manager.js",
    "src/cache-manager.js",
    "src/phonemizer/rust-wasm-adapter.js",
    "g2p/src/index.js",
    "dist/rust-wasm/piper_plus_wasm.js",
    "dist/rust-wasm/piper_plus_wasm_bg.wasm",
    "assets/pinyin_single.json",
    "assets/pinyin_phrases.json",
    "multilingual-demo/index.html",
    "404.html",
)


def head_status(url: str, timeout: float) -> int:
    """Return the HTTP status code from a HEAD request, or 0 on network error."""
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return 0


def probe_with_retry(
    url: str, *, timeout: float, retries: int, retry_delay: float
) -> int:
    """HEAD `url` up to `retries+1` times; return the last status code."""
    last = 0
    for attempt in range(retries + 1):
        last = head_status(url, timeout)
        if 200 <= last < 400:
            return last
        if attempt < retries:
            time.sleep(retry_delay)
    return last


def verify(
    base_url: str,
    paths: Iterable[str],
    *,
    timeout: float,
    retries: int,
    retry_delay: float,
) -> int:
    """Probe each path; return the number of non-2xx (3xx is also acceptable)."""
    base = base_url.rstrip("/")
    failures: list[tuple[str, int]] = []
    for path in paths:
        url = f"{base}/{path}" if path else f"{base}/"
        status = probe_with_retry(
            url, timeout=timeout, retries=retries, retry_delay=retry_delay
        )
        marker = "OK" if 200 <= status < 400 else "FAIL"
        print(f"  [{marker}] {status} {url}")
        if not (200 <= status < 400):
            failures.append((url, status))

    print()
    if failures:
        print(f"FAIL: {len(failures)} asset(s) returned non-2xx:")
        for url, status in failures:
            print(f"  - {status} {url}")
        return len(failures)
    print(f"OK: all {len(list(paths))} assets returned 2xx/3xx")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify GitHub Pages deploy by HEAD-probing critical assets"
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="Pages origin, e.g. https://ayutaz.github.io/piper-plus",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=None,
        help="Explicit path to check (repeatable). Overrides default list.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--retry-delay-seconds", type=float, default=10.0)

    args = parser.parse_args(argv)

    paths = tuple(args.path) if args.path else DEFAULT_REQUIRED_PATHS
    print(f"Verifying {len(paths)} asset(s) under {args.base_url}")
    print()

    failures = verify(
        args.base_url,
        paths,
        timeout=args.timeout_seconds,
        retries=args.retries,
        retry_delay=args.retry_delay_seconds,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
