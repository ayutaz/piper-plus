#!/usr/bin/env python3
"""Verify cosign signatures on recent GitHub releases via Rekor (T-001).

PR #511 introduced ``cosign-release-artifacts.yml`` as the **signing**
side of release artifact provenance. This script is the **verifying**
side: it walks the N most recent releases, finds each artifact +
``.sig`` + ``.pem``, and invokes ``cosign verify-blob`` against the
Rekor transparency log to confirm the signature is still valid. The
``certificate-identity-regexp`` and ``certificate-oidc-issuer`` are
mirrored byte-for-byte from PR #511 (M1-R3); drift is caught at PR
review and by ``scripts/check_release_workflow_mirror`` (future T).

Silent-zero defence (NFR-5.3): the defensive log
``Collected releases (N): ...`` is always echoed to stderr, and a
``::warning::`` is emitted when ``gh release list`` returns 0 entries.

Skip-vs-fail: a release missing the ``.sig`` / ``.pem`` pair (cosign was
not yet wired up at that point in history) is classified ``skipped``,
not ``fail``. ``fail`` is reserved for cosign verify-blob exit != 0.

Usage:
    python scripts/verify_rekor_releases.py --limit 10 --workdir /tmp/rekor
    python scripts/verify_rekor_releases.py --fixture path/to/fixture.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent

CERTIFICATE_IDENTITY_REGEXP = "https://github.com/ayutaz/piper-plus"
CERTIFICATE_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
REKOR_URL = "https://rekor.sigstore.dev"

ARTIFACT_PATTERNS = ("*.tar.gz", "*.tgz", "*.zip", "*.whl", "*.nupkg", "*.aar")
SIG_SUFFIXES = (".sig",)
CERT_SUFFIXES = (".pem",)


def list_recent_releases(
    limit: int,
    gh_runner: Callable[[list[str]], str] | None = None,
) -> list[str]:
    """Return the tagName of the N most recent releases via gh CLI."""
    runner = gh_runner or _default_gh_runner
    raw = runner(
        [
            "gh",
            "release",
            "list",
            "--limit",
            str(limit),
            "--json",
            "tagName",
            "--jq",
            ".[].tagName",
        ]
    )
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _default_gh_runner(argv: list[str]) -> str:
    return subprocess.run(
        argv,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def find_assets_for_release(
    release: dict[str, Any],
) -> list[dict[str, Any]]:
    """Pair every artifact with its ``.cosign.bundle`` sibling.

    PR #511's ``cosign-release-artifacts.yml`` produces a single
    ``<asset>.cosign.bundle`` per artifact (cosign ``--bundle`` flag),
    not the legacy ``.sig`` / ``.pem`` two-file form. Releases predating
    PR #511 do not have a bundle — those artifacts return
    ``status='skipped'`` from :func:`classify_asset`. Per-asset metadata
    (``expected_verify`` etc.) is preserved so fixture mode can drive
    deterministic test outcomes.
    """
    raw_assets = release.get("assets", []) or []
    names = [a["name"] for a in raw_assets]
    by_name = {a["name"]: a for a in raw_assets}
    bundles = {
        n.removesuffix(".cosign.bundle"): n
        for n in names
        if n.endswith(".cosign.bundle")
    }
    artifacts: list[dict[str, Any]] = []
    for n in names:
        if n.endswith((".sig", ".pem", ".cosign.bundle")):
            continue
        artifact_meta = by_name.get(n, {})
        artifacts.append(
            {
                "name": n,
                "bundle": bundles.get(n, ""),
                "expected_verify": artifact_meta.get("expected_verify", "pass"),
            }
        )
    return artifacts


def classify_asset(asset: dict[str, Any]) -> str:
    """Return one of: ``ready``, ``skipped``."""
    if asset.get("bundle"):
        return "ready"
    return "skipped"


def verify_blob(
    artifact_path: Path,
    bundle_path: Path,
    cosign_cmd: str = "cosign",
    runner: Callable[[list[str]], int] | None = None,
) -> dict[str, Any]:
    """Run ``cosign verify-blob`` against a ``--bundle`` and return a result.

    PR #511 signs blobs with ``cosign sign-blob --bundle <name>.cosign.bundle``,
    embedding both the signature and the Fulcio-issued certificate in a
    single file. The verify side must use ``--bundle`` (not the legacy
    ``--signature`` + ``--certificate`` pair) or every verify call fails
    with "could not verify" even though the upstream signature is valid.
    """
    argv = [
        cosign_cmd,
        "verify-blob",
        "--rekor-url",
        REKOR_URL,
        "--certificate-identity-regexp",
        CERTIFICATE_IDENTITY_REGEXP,
        "--certificate-oidc-issuer",
        CERTIFICATE_OIDC_ISSUER,
        "--bundle",
        str(bundle_path),
        str(artifact_path),
    ]
    invoke = runner or _default_subprocess_runner
    try:
        rc = invoke(argv)
        if rc == 0:
            return {"status": "pass", "cosign_argv": argv}
        return {
            "status": "fail",
            "cosign_argv": argv,
            "error": f"cosign verify-blob exit {rc}",
        }
    except FileNotFoundError as e:
        return {
            "status": "error",
            "cosign_argv": argv,
            "error": f"cosign binary not found: {e}",
        }


def _default_subprocess_runner(argv: list[str]) -> int:
    result = subprocess.run(argv, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
    return result.returncode


def emit_collected_log(tags: list[str]) -> None:
    """Always-echoed defensive log to defend against silent-zero."""
    summary = " ".join(tags[:5]) if tags else "(none)"
    suffix = " ..." if len(tags) > 5 else ""
    print(
        f"Collected releases ({len(tags)}): {summary}{suffix}",
        file=sys.stderr,
    )


def render_report(
    tags: list[str],
    results: list[dict[str, Any]],
) -> str:
    """Render the per-release verify report as markdown."""
    lines = ["## Rekor verify report", ""]
    summary: dict[str, int] = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    lines.append(
        f"**Collected releases ({len(tags)}):** "
        + (", ".join(f"`{t}`" for t in tags) if tags else "(none)")
    )
    lines.append("")
    lines.append("| Release | Artifact | Status | Note |")
    lines.append("|---------|----------|--------|------|")
    for r in results:
        status = r["status"].upper()
        note = r.get("error", "") or r.get("note", "")
        lines.append(f"| `{r['tag']}` | `{r['artifact']}` | **{status}** | {note} |")
    lines.append("")
    parts = [f"total={len(results)}"]
    for k in ("pass", "skipped", "fail", "error"):
        if summary.get(k, 0) > 0:
            parts.append(f"{k}={summary[k]}")
    lines.append("Summary: " + ", ".join(parts))
    return "\n".join(lines) + "\n"


def run_verify(
    releases: list[dict[str, Any]],
    download_dir: Path,
    *,
    cosign_cmd: str = "cosign",
    cosign_runner: Callable[[list[str]], int] | None = None,
    download_fn: Callable[[str, str, Path], Path] | None = None,
) -> list[dict[str, Any]]:
    """Iterate releases × assets, dispatch verify_blob, collect results."""
    results: list[dict[str, Any]] = []
    for release in releases:
        tag = release.get("tag") or release.get("tagName")
        if not tag:
            continue
        for asset in find_assets_for_release(release):
            kind = classify_asset(asset)
            if kind == "skipped":
                results.append(
                    {
                        "tag": tag,
                        "artifact": asset["name"],
                        "status": "skipped",
                        "note": "no .cosign.bundle (pre-cosign release)",
                    }
                )
                continue
            if download_fn is None:
                # In offline mode we accept a pre-computed verify outcome
                # from the fixture (asset['expected_verify']).
                expected = asset.get("expected_verify", "pass")
                results.append(
                    {
                        "tag": tag,
                        "artifact": asset["name"],
                        "status": expected,
                        "note": "(offline / fixture mode)",
                    }
                )
                continue
            artifact_path = download_fn(tag, asset["name"], download_dir)
            bundle_path = download_fn(tag, asset["bundle"], download_dir)
            verify_result = verify_blob(
                artifact_path,
                bundle_path,
                cosign_cmd=cosign_cmd,
                runner=cosign_runner,
            )
            results.append(
                {
                    "tag": tag,
                    "artifact": asset["name"],
                    **verify_result,
                }
            )
    return results


def load_fixture(path: Path) -> list[dict[str, Any]]:
    """Load a fixture JSON containing a list of release descriptions."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "releases" not in data:
        raise ValueError(
            f"Fixture {path} must be {{'releases': [...]}} shape.",
        )
    return data["releases"]


_TAG_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _download_via_gh(tag: str, asset_name: str, dest_dir: Path) -> Path:
    """Real download path used by the CI workflow."""
    if not _TAG_SAFE.sub("", tag) == tag.replace("/", ""):
        raise ValueError(f"Refusing unsafe tag: {tag!r}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "gh",
            "release",
            "download",
            tag,
            "--pattern",
            asset_name,
            "--dir",
            str(dest_dir),
            "--clobber",
        ],
        check=True,
    )
    return dest_dir / asset_name


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Verify cosign signatures on the N most recent releases.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent releases to verify (FR-3.1).",
    )
    p.add_argument(
        "--workdir",
        type=Path,
        default=Path("/tmp/rekor-verify"),
        help="Where to download release assets.",
    )
    p.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Read releases from a JSON fixture (test/offline mode).",
    )
    p.add_argument(
        "--report", type=Path, default=None, help="Write markdown report to this path."
    )
    p.add_argument(
        "--cosign-cmd", default="cosign", help="cosign binary path (for tests)."
    )
    args = p.parse_args(argv)

    if args.fixture is not None:
        releases = load_fixture(args.fixture)
        tags = [r.get("tag") or r.get("tagName", "") for r in releases]
    else:
        tags = list_recent_releases(args.limit)
        releases = [{"tag": t, "assets": []} for t in tags]
        # In live mode, populate assets via gh release view per tag.
        for r in releases:
            try:
                raw = _default_gh_runner(
                    [
                        "gh",
                        "release",
                        "view",
                        r["tag"],
                        "--json",
                        "assets",
                        "--jq",
                        ".assets",
                    ]
                )
                r["assets"] = json.loads(raw or "[]")
            except subprocess.CalledProcessError as e:
                r["assets"] = []
                print(
                    f"::warning::Failed to list assets for {r['tag']}: {e}",
                    file=sys.stderr,
                )

    emit_collected_log(tags)
    if not tags:
        print(
            "::warning::Collected releases (0): gh release list returned "
            "empty — silent-zero guard.",
            file=sys.stderr,
        )
        return 2

    results = run_verify(
        releases,
        args.workdir,
        cosign_cmd=args.cosign_cmd,
        download_fn=_download_via_gh if args.fixture is None else None,
    )

    report = render_report(tags, results)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
    print(report)

    # Treat both ``fail`` (verify-blob exit != 0) and ``error`` (cosign
    # missing / runner exception) as failure — Copilot review on PR #513
    # flagged that an ``error``-only outcome was silently green and could
    # mask a "verify never ran" condition.
    fail_count = sum(1 for r in results if r["status"] in ("fail", "error"))
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
