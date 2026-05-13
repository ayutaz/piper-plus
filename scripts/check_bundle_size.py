#!/usr/bin/env python3
"""Bundle size regression gate.

Measures the build artifact size of every public distribution unit and
compares against a JSON baseline (``tests/fixtures/bundle-size-baseline.json``).
Fails the run if the observed delta exceeds the per-ecosystem tolerance.

Tolerance policy
----------------

============  ================  ====================
Ecosystem     Tolerance (±)     Rationale
============  ================  ====================
npm           3 %               Browser bundle; users
                                ship over the wire,
                                small drift matters.
NuGet         5 %               Compiled DLL; debug
                                symbols / metadata
                                churn is normal.
crates.io     5 %               Source tarball; cargo
                                package occasionally
                                reshuffles file order.
Maven         5 %               AAR includes Kotlin
                                metadata + resources.
============  ================  ====================

Usage
-----

    # Measure + compare (CI mode)
    uv run python scripts/check_bundle_size.py

    # Re-snapshot the baseline (manual; commit the JSON afterwards)
    uv run python scripts/check_bundle_size.py --update-baseline

    # Use a different baseline path (testing)
    uv run python scripts/check_bundle_size.py --baseline /tmp/foo.json

    # Emit a Markdown report for PR comments
    uv run python scripts/check_bundle_size.py --format markdown

Notes
-----

* When an artifact is missing on disk the gate records ``size_bytes: null``
  and skips comparison for that entry (CI ``packages.bundle-size`` job is
  expected to produce them via ``npm pack`` / ``dotnet pack`` /
  ``cargo package`` / ``./gradlew :piper-plus-g2p:bundleRelease``).  The
  comparison itself is robust to a partial matrix so contributors can run
  the script locally without building every ecosystem.
* The baseline JSON intentionally uses ``size_bytes: null`` for the
  initial commit; the first CI run after merging this script is
  responsible for replacing the placeholders via ``--update-baseline``
  (manually triggered, reviewed in a follow-up PR).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = REPO_ROOT / "tests" / "fixtures" / "bundle-size-baseline.json"


# ---------------------------------------------------------------------------
# Artifact discovery
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Artifact:
    """One distributable unit on a public registry."""

    package: str       # registry-facing name (e.g. ``piper-plus``)
    ecosystem: str     # one of ``npm`` / ``nuget`` / ``cargo`` / ``maven``
    tolerance: float   # fractional, e.g. ``0.03`` for ±3 %
    glob: str          # POSIX glob relative to REPO_ROOT


# Per-ecosystem tolerances (kept here to make the policy obvious in review).
NPM_TOL = 0.03
NUGET_TOL = 0.05
CARGO_TOL = 0.05
MAVEN_TOL = 0.05


ARTIFACTS: tuple[Artifact, ...] = (
    # npm — built by ``npm pack`` in the package directory.
    Artifact(
        package="piper-plus",
        ecosystem="npm",
        tolerance=NPM_TOL,
        glob="src/wasm/openjtalk-web/piper-plus-*.tgz",
    ),
    Artifact(
        package="@piper-plus/g2p",
        ecosystem="npm",
        tolerance=NPM_TOL,
        # npm pack rewrites ``@scope/name`` to ``scope-name``.
        glob="src/wasm/g2p/piper-plus-g2p-*.tgz",
    ),
    # NuGet — produced by ``dotnet pack -c Release``.
    Artifact(
        package="PiperPlus.Core",
        ecosystem="nuget",
        tolerance=NUGET_TOL,
        glob="src/csharp/PiperPlus.Core/bin/Release/PiperPlus.Core.*.nupkg",
    ),
    Artifact(
        package="PiperPlus.Cli",
        ecosystem="nuget",
        tolerance=NUGET_TOL,
        glob="src/csharp/PiperPlus.Cli/bin/Release/PiperPlus.Cli.*.nupkg",
    ),
    # crates.io — produced by ``cargo package`` (``.crate`` tarball).
    Artifact(
        package="piper-plus",
        ecosystem="cargo",
        tolerance=CARGO_TOL,
        glob="src/rust/target/package/piper-plus-*.crate",
    ),
    # Maven Central — Android AAR.
    Artifact(
        package="piper-plus-g2p-android",
        ecosystem="maven",
        tolerance=MAVEN_TOL,
        glob="android/piper-plus-g2p/build/outputs/aar/piper-plus-g2p-release.aar",
    ),
)


def _baseline_key(art: Artifact) -> str:
    """Stable JSON key combining ecosystem + package name."""
    return f"{art.ecosystem}::{art.package}"


def _resolve_size_bytes(art: Artifact) -> Optional[int]:
    """Return the on-disk size of the matching artifact, or None."""
    matches = sorted(glob.glob(str(REPO_ROOT / art.glob)))
    if not matches:
        return None
    # If multiple matches (e.g. several versions in target/package), take
    # the newest by mtime so reruns within one CI job stay deterministic.
    matches.sort(key=lambda p: os.path.getmtime(p))
    return os.path.getsize(matches[-1])


# ---------------------------------------------------------------------------
# Baseline I/O
# ---------------------------------------------------------------------------


def _load_baseline(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "artifacts": {}}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _save_baseline(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _current_snapshot() -> dict:
    """Build a fresh ``artifacts`` mapping from disk."""
    artifacts: dict[str, dict] = {}
    for art in ARTIFACTS:
        size = _resolve_size_bytes(art)
        artifacts[_baseline_key(art)] = {
            "package": art.package,
            "ecosystem": art.ecosystem,
            "tolerance": art.tolerance,
            "size_bytes": size,
        }
    return {"version": 1, "artifacts": artifacts}


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


@dataclass
class Comparison:
    package: str
    ecosystem: str
    tolerance: float
    baseline: Optional[int]
    observed: Optional[int]

    @property
    def delta_bytes(self) -> Optional[int]:
        if self.baseline is None or self.observed is None:
            return None
        return self.observed - self.baseline

    @property
    def delta_pct(self) -> Optional[float]:
        if self.baseline is None or not self.baseline or self.observed is None:
            return None
        return (self.observed - self.baseline) / self.baseline

    @property
    def status(self) -> str:
        # ``skip``  — baseline or observation missing (warn, never fail).
        # ``ok``    — within tolerance.
        # ``fail``  — exceeds tolerance.
        if self.delta_pct is None:
            return "skip"
        return "ok" if abs(self.delta_pct) <= self.tolerance else "fail"


def _compare(baseline: dict, observed: dict) -> list[Comparison]:
    base_map = baseline.get("artifacts", {})
    obs_map = observed.get("artifacts", {})
    results: list[Comparison] = []
    for art in ARTIFACTS:
        key = _baseline_key(art)
        b = base_map.get(key, {})
        o = obs_map.get(key, {})
        results.append(
            Comparison(
                package=art.package,
                ecosystem=art.ecosystem,
                tolerance=art.tolerance,
                baseline=b.get("size_bytes"),
                observed=o.get("size_bytes"),
            )
        )
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _fmt_bytes(n: Optional[int]) -> str:
    if n is None:
        return "n/a"
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n / (1024 * 1024):.2f} MiB"


def _fmt_pct(p: Optional[float]) -> str:
    if p is None:
        return "n/a"
    return f"{p * 100:+.2f}%"


def _emoji(status: str) -> str:
    # Keep ASCII-only so PR comments render cleanly on any client.
    return {"ok": "OK", "fail": "FAIL", "skip": "SKIP"}[status]


def _render_markdown(results: list[Comparison]) -> str:
    lines = [
        "## Bundle size gate",
        "",
        "| Status | Ecosystem | Package | Baseline | Observed | Delta | Tolerance |",
        "|--------|-----------|---------|----------|----------|-------|-----------|",
    ]
    for r in results:
        lines.append(
            "| {status} | {eco} | `{pkg}` | {base} | {obs} | {delta} | ±{tol:.0%} |".format(
                status=_emoji(r.status),
                eco=r.ecosystem,
                pkg=r.package,
                base=_fmt_bytes(r.baseline),
                obs=_fmt_bytes(r.observed),
                delta=_fmt_pct(r.delta_pct),
                tol=r.tolerance,
            )
        )
    skips = sum(1 for r in results if r.status == "skip")
    fails = sum(1 for r in results if r.status == "fail")
    lines.extend(
        [
            "",
            f"Summary: {fails} fail / {skips} skip / {len(results) - fails - skips} ok",
            "",
            "_SKIP means the artifact was not built in this job, or the "
            "baseline is a placeholder. The gate never fails on SKIP._",
        ]
    )
    return "\n".join(lines)


def _render_text(results: list[Comparison]) -> str:
    lines = []
    for r in results:
        lines.append(
            f"[{_emoji(r.status):>4}] {r.ecosystem:<6} {r.package:<28} "
            f"baseline={_fmt_bytes(r.baseline):>10}  "
            f"observed={_fmt_bytes(r.observed):>10}  "
            f"delta={_fmt_pct(r.delta_pct):>9}  "
            f"tol=±{r.tolerance:.0%}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Path to the baseline JSON (default: %(default)s).",
    )
    ap.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite the baseline JSON with the current artifact sizes.",
    )
    ap.add_argument(
        "--format",
        choices=("text", "markdown", "json"),
        default="text",
        help="Output format for the comparison report.",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the report to this file (default: stdout).",
    )
    ap.add_argument(
        "--warn-only",
        action="store_true",
        help="Never exit non-zero on regression (still prints the table).",
    )
    args = ap.parse_args(argv)

    snapshot = _current_snapshot()

    if args.update_baseline:
        _save_baseline(args.baseline, snapshot)
        print(f"Updated baseline: {args.baseline}", file=sys.stderr)
        return 0

    baseline = _load_baseline(args.baseline)
    results = _compare(baseline, snapshot)

    if args.format == "markdown":
        rendered = _render_markdown(results)
    elif args.format == "json":
        rendered = json.dumps(
            {
                "results": [
                    {
                        "package": r.package,
                        "ecosystem": r.ecosystem,
                        "tolerance": r.tolerance,
                        "baseline_bytes": r.baseline,
                        "observed_bytes": r.observed,
                        "delta_bytes": r.delta_bytes,
                        "delta_pct": r.delta_pct,
                        "status": r.status,
                    }
                    for r in results
                ]
            },
            indent=2,
        )
    else:
        rendered = _render_text(results)

    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    fails = [r for r in results if r.status == "fail"]
    if fails and not args.warn_only:
        print(
            f"\nERROR: {len(fails)} artifact(s) exceed the size tolerance.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
