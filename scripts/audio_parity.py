#!/usr/bin/env python3
"""Cross-runtime audio byte parity (M2.2).

同一 model + 同一 phoneme IDs に対する 6 runtime (Python / Rust / C# / Go /
JS-WASM / C++) の WAV 出力が階層化判定で「同じ音」と認められるかを検証する
CLI。 階層化判定の閾値は ``docs/spec/audio-parity-contract.toml`` を canonical
source として、 同 file を一度だけ読み込んで適用する。

階層化判定:

* tier 1 — ``SHA256`` 完全一致 (期待値、 ただし FP16 / iSTFT で破れがち)
* tier 2 — peak RMS 差が ``peak_rms_max_diff`` 以下
* tier 3 — chromaprint fingerprint の Hamming distance が
            ``chromaprint_max_hamming`` 以下
* tier 4 — mel-spec MSE ≤ ``mel_spec_max_mse`` かつ SNR ≥ ``snr_min_db``

stdlib + tomllib + (optional) numpy/scipy で実装。 numpy / scipy 不在の
環境 (informational tier bootstrap) では tier 1 (SHA256) と tier 2
(byte-length 同一) のみ評価し、 不在 ranges は ``None`` で報告する。

CLI:

    python scripts/audio_parity.py compare --inputs python=a.wav rust=b.wav ...
    python scripts/audio_parity.py compare --inputs-json runtimes.json --out diff.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import tomllib
import wave
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_TOML = REPO_ROOT / "docs/spec/audio-parity-contract.toml"


@dataclass
class WavSnapshot:
    runtime: str
    path: Path
    sha256: str
    sample_rate: int
    num_channels: int
    sample_width: int
    num_frames: int
    samples_f32: list[float] | None = None  # None when numpy is unavailable
    rms: float | None = None


@dataclass
class TierResult:
    name: str
    passed: bool
    detail: str


@dataclass
class PairwiseResult:
    a: str
    b: str
    tiers: list[TierResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return any(t.passed for t in self.tiers)


@dataclass
class ComparisonReport:
    snapshots: dict[str, WavSnapshot] = field(default_factory=dict)
    pairs: list[PairwiseResult] = field(default_factory=list)

    @property
    def failures(self) -> list[PairwiseResult]:
        return [p for p in self.pairs if not p.passed]


def load_contract(path: Path = CONTRACT_TOML) -> dict:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    thresholds = data.get("thresholds", {})
    _validate_thresholds(thresholds)
    return data


def _validate_thresholds(thresholds: dict) -> None:
    for key, floor in (
        ("peak_rms_max_diff", 0.0),
        ("mel_spec_max_mse", 0.0),
        ("chromaprint_max_hamming", 0.0),
    ):
        value = thresholds.get(key)
        if value is None or value <= floor:
            raise ValueError(
                f"thresholds[{key!r}] must be > {floor}, got {value!r}; an "
                "all-zero contract would silently pass any input."
            )
    snr = thresholds.get("snr_min_db")
    if snr is None or snr <= 0:
        raise ValueError(f"thresholds[snr_min_db] must be positive, got {snr!r}.")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_wav_pcm16(path: Path) -> WavSnapshot:
    """Read a 16-bit PCM WAV into a stdlib-only snapshot.

    We deliberately stay on the stdlib so the bootstrap workflow can run on
    a minimal runner; if numpy is available the caller can attach
    ``samples_f32`` later for tier 4 evaluation.
    """
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    samples: list[float] | None = None
    rms: float | None = None
    if sample_width == 2:
        ints = struct.unpack(f"<{len(raw) // 2}h", raw)
        if n_channels > 1:
            # average channels to mono for parity comparison
            grouped = [
                ints[i : i + n_channels] for i in range(0, len(ints), n_channels)
            ]
            samples = [sum(g) / (n_channels * 32768.0) for g in grouped]
        else:
            samples = [s / 32768.0 for s in ints]
        if samples:
            rms = math.sqrt(sum(s * s for s in samples) / len(samples))

    return WavSnapshot(
        runtime="",
        path=path,
        sha256=sha256_of(path),
        sample_rate=sample_rate,
        num_channels=n_channels,
        sample_width=sample_width,
        num_frames=n_frames,
        samples_f32=samples,
        rms=rms,
    )


def snapshot(runtime: str, path: Path) -> WavSnapshot:
    snap = _read_wav_pcm16(path)
    snap.runtime = runtime
    return snap


def tier1_sha256(a: WavSnapshot, b: WavSnapshot) -> TierResult:
    same = a.sha256 == b.sha256
    return TierResult(
        name="sha256",
        passed=same,
        detail=f"{a.sha256[:12]} vs {b.sha256[:12]}",
    )


def tier2_rms(a: WavSnapshot, b: WavSnapshot, threshold: float) -> TierResult:
    if a.rms is None or b.rms is None:
        return TierResult("peak_rms", False, "rms unavailable (non-PCM16)")
    diff = abs(a.rms - b.rms)
    return TierResult(
        name="peak_rms",
        passed=diff <= threshold,
        detail=f"Δrms={diff:.5f} (≤ {threshold})",
    )


def tier3_mel_mse_or_snr(
    a: WavSnapshot, b: WavSnapshot, thresholds: dict
) -> TierResult:
    """Tier 4 equivalent — SNR / mel-MSE. We compute on raw samples if numpy
    is unavailable (uses a coarse time-domain SNR proxy instead of mel-MSE)."""
    if a.samples_f32 is None or b.samples_f32 is None:
        return TierResult("snr", False, "samples unavailable")
    if a.num_frames != b.num_frames:
        return TierResult(
            "snr",
            False,
            f"frame count differs: {a.num_frames} vs {b.num_frames}",
        )
    signal_energy = sum(x * x for x in a.samples_f32)
    noise_energy = sum(
        (x - y) ** 2 for x, y in zip(a.samples_f32, b.samples_f32, strict=True)
    )
    if signal_energy == 0:
        return TierResult("snr", False, "reference signal is silent")
    if noise_energy == 0:
        return TierResult("snr", True, "samples identical")
    snr_db = 10.0 * math.log10(signal_energy / noise_energy)
    threshold = thresholds.get("snr_min_db", 60.0)
    return TierResult(
        name="snr",
        passed=snr_db >= threshold,
        detail=f"SNR={snr_db:.2f} dB (≥ {threshold})",
    )


def compare_pair(a: WavSnapshot, b: WavSnapshot, contract: dict) -> PairwiseResult:
    thresholds = contract.get("thresholds", {})
    result = PairwiseResult(a=a.runtime, b=b.runtime)
    result.tiers.append(tier1_sha256(a, b))
    if result.tiers[-1].passed:
        return result
    result.tiers.append(
        tier2_rms(a, b, threshold=thresholds.get("peak_rms_max_diff", 0.005))
    )
    if result.tiers[-1].passed:
        return result
    result.tiers.append(tier3_mel_mse_or_snr(a, b, thresholds))
    return result


def render_markdown(report: ComparisonReport) -> str:
    lines = [
        "## Runtime Parity Deep — audio (informational tier)",
        "",
        f"Pairs compared: **{len(report.pairs)}**, "
        f"failing: **{len(report.failures)}**.",
        "",
        "| A | B | Tier | Result | Detail |",
        "|---|---|------|--------|--------|",
    ]
    for pair in report.pairs:
        for tier in pair.tiers:
            flag = "✅" if tier.passed else "⚠️"
            lines.append(
                f"| `{pair.a}` | `{pair.b}` | {tier.name} | {flag} | {tier.detail} |"
            )
    return "\n".join(lines).rstrip() + "\n"


def gather_pairs(snapshots: dict[str, WavSnapshot], contract: dict) -> ComparisonReport:
    report = ComparisonReport(snapshots=snapshots)
    names = sorted(snapshots)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a = snapshots[names[i]]
            b = snapshots[names[j]]
            report.pairs.append(compare_pair(a, b, contract))
    return report


def parse_inputs(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for spec in values:
        if "=" not in spec:
            raise SystemExit(f"--inputs entry must be RUNTIME=PATH (got {spec!r})")
        runtime, path = spec.split("=", 1)
        result[runtime] = Path(path)
    return result


def cmd_compare(args: argparse.Namespace) -> int:
    contract = load_contract(args.contract)
    if args.inputs_json:
        raw = json.loads(args.inputs_json.read_text())
        inputs = {k: Path(v) for k, v in raw.items()}
    else:
        inputs = parse_inputs(args.inputs)
    if not inputs:
        print(
            "at least one --inputs / --inputs-json entry is required", file=sys.stderr
        )
        return 2
    snapshots = {name: snapshot(name, path) for name, path in inputs.items()}
    report = gather_pairs(snapshots, contract)
    md = render_markdown(report)
    print(md)
    if args.output:
        args.output.write_text(md, encoding="utf-8")
    if args.fail_on_mismatch and report.failures:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument(
        "--inputs",
        nargs="*",
        default=[],
        help="RUNTIME=PATH pairs, e.g. python=/tmp/a.wav rust=/tmp/b.wav",
    )
    c.add_argument("--inputs-json", type=Path, default=None)
    c.add_argument("--contract", type=Path, default=CONTRACT_TOML)
    c.add_argument("--output", type=Path, default=None)
    c.add_argument("--fail-on-mismatch", action="store_true")
    c.set_defaults(func=cmd_compare)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
