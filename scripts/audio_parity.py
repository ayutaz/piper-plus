#!/usr/bin/env python3
"""Cross-runtime audio byte parity (M2.2).

同一 model + 同一 phoneme IDs に対する 6 runtime (Python / Rust / C# / Go /
JS-WASM / C++) の WAV 出力が階層化判定で「同じ音」と認められるかを検証する
CLI。 階層化判定の閾値は ``docs/spec/audio-parity-contract.toml`` を canonical
source として、 同 file を一度だけ読み込んで適用する。

判定 (ペアごと):

* frames — sample rate とフレーム数の一致。 必須 (不一致なら即失敗)
* sha256 — ファイルの完全一致。 一致すれば合格
* peak_rms — peak 正規化後の RMS の差が ``peak_rms_max_diff`` 以下
* snr — 最小二乗でゲインを合わせたあとの SNR が ``snr_min_db`` 以上

合格 = frames かつ (sha256 または (peak_rms かつ snr))。 Python は出力を
peak 正規化し、 ほかの runtime はしないので、 音量だけの差は不一致に数えない。
以前は「どれか 1 段でも通れば合格」で、 長さの違う WAV や別の波形でも
RMS が近ければ合格になっていた。

stdlib + tomllib のみで実装する。

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
    samples_f32: list[float] | None = None  # None for non-PCM16 input
    rms: float | None = None
    peak: float | None = None


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
        by_name = {t.name: t.passed for t in self.tiers}
        if not by_name.get("frames", False):
            return False
        if by_name.get("sha256", False):
            return True
        return by_name.get("peak_rms", False) and by_name.get("snr", False)


@dataclass
class SkipEntry:
    runtime: str
    reason: str


@dataclass
class ComparisonReport:
    snapshots: dict[str, WavSnapshot] = field(default_factory=dict)
    pairs: list[PairwiseResult] = field(default_factory=list)
    skipped: list[SkipEntry] = field(default_factory=list)

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
    peak: float | None = None
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
            peak = max(abs(s) for s in samples)

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
        peak=peak,
    )


def snapshot(runtime: str, path: Path) -> WavSnapshot:
    snap = _read_wav_pcm16(path)
    snap.runtime = runtime
    return snap


def tier_frames(a: WavSnapshot, b: WavSnapshot) -> TierResult:
    same = a.sample_rate == b.sample_rate and a.num_frames == b.num_frames
    return TierResult(
        name="frames",
        passed=same,
        detail=(
            f"{a.num_frames} vs {b.num_frames} frames "
            f"@ {a.sample_rate} / {b.sample_rate} Hz"
        ),
    )


def tier1_sha256(a: WavSnapshot, b: WavSnapshot) -> TierResult:
    same = a.sha256 == b.sha256
    return TierResult(
        name="sha256",
        passed=same,
        detail=f"{a.sha256[:12]} vs {b.sha256[:12]}",
    )


def _peak_normalised_rms(snap: WavSnapshot) -> float:
    assert snap.rms is not None and snap.peak is not None
    return snap.rms / snap.peak if snap.peak > 0 else 0.0


def tier2_rms(a: WavSnapshot, b: WavSnapshot, threshold: float) -> TierResult:
    if a.rms is None or b.rms is None:
        return TierResult("peak_rms", False, "rms unavailable (non-PCM16)")
    diff = abs(_peak_normalised_rms(a) - _peak_normalised_rms(b))
    return TierResult(
        name="peak_rms",
        passed=diff <= threshold,
        detail=f"Δrms(peak-normalised)={diff:.5f} (≤ {threshold})",
    )


def tier3_snr(a: WavSnapshot, b: WavSnapshot, thresholds: dict) -> TierResult:
    """SNR of ``a`` against ``b`` after least-squares gain matching.

    The gain ``g = <a, b> / <b, b>`` removes a pure volume difference (Python
    peak-normalises, the other runtimes do not), so only a difference in the
    waveform itself counts as noise.
    """
    if a.samples_f32 is None or b.samples_f32 is None:
        return TierResult("snr", False, "samples unavailable")
    if len(a.samples_f32) != len(b.samples_f32):
        return TierResult(
            "snr",
            False,
            f"frame count differs: {a.num_frames} vs {b.num_frames}",
        )
    signal_energy = sum(x * x for x in a.samples_f32)
    ref_energy = sum(y * y for y in b.samples_f32)
    if signal_energy == 0 and ref_energy == 0:
        return TierResult("snr", True, "both signals are silent")
    if signal_energy == 0 or ref_energy == 0:
        return TierResult("snr", False, "one signal is silent")
    gain = sum(x * y for x, y in zip(a.samples_f32, b.samples_f32, strict=True))
    gain /= ref_energy
    noise_energy = sum(
        (x - gain * y) ** 2 for x, y in zip(a.samples_f32, b.samples_f32, strict=True)
    )
    threshold = thresholds.get("snr_min_db", 60.0)
    if noise_energy == 0:
        return TierResult("snr", True, f"samples identical after gain {gain:.4f}")
    snr_db = 10.0 * math.log10(signal_energy / noise_energy)
    return TierResult(
        name="snr",
        passed=snr_db >= threshold,
        detail=f"SNR={snr_db:.2f} dB after gain {gain:.4f} (≥ {threshold})",
    )


def compare_pair(a: WavSnapshot, b: WavSnapshot, contract: dict) -> PairwiseResult:
    thresholds = contract.get("thresholds", {})
    result = PairwiseResult(a=a.runtime, b=b.runtime)
    result.tiers.append(tier_frames(a, b))
    if not result.tiers[-1].passed:
        return result
    result.tiers.append(tier1_sha256(a, b))
    if result.tiers[-1].passed:
        return result
    result.tiers.append(
        tier2_rms(a, b, threshold=thresholds.get("peak_rms_max_diff", 0.005))
    )
    result.tiers.append(tier3_snr(a, b, thresholds))
    return result


def render_markdown(report: ComparisonReport) -> str:
    lines = [
        "## Runtime Parity Deep — audio",
        "",
        f"Pairs compared: **{len(report.pairs)}**, "
        f"failing: **{len(report.failures)}**, "
        f"runtimes skipped: **{len(report.skipped)}**.",
        "",
    ]
    if report.pairs:
        lines.extend(
            [
                "| A | B | Tier | Result | Detail |",
                "|---|---|------|--------|--------|",
            ]
        )
        for pair in report.pairs:
            for tier in pair.tiers:
                flag = "✅" if tier.passed else "⚠️"
                lines.append(
                    f"| `{pair.a}` | `{pair.b}` | {tier.name} | {flag} | "
                    f"{tier.detail} |"
                )
            verdict = "✅ pass" if pair.passed else "❌ FAIL"
            lines.append(f"| `{pair.a}` | `{pair.b}` | **verdict** | {verdict} | |")
    if report.skipped:
        lines.append("")
        lines.append("### Skipped runtimes")
        lines.append("")
        lines.append("| Runtime | Reason |")
        lines.append("|---------|--------|")
        for entry in report.skipped:
            lines.append(f"| `{entry.runtime}` | {entry.reason} |")
    return "\n".join(lines).rstrip() + "\n"


def gather_pairs(
    snapshots: dict[str, WavSnapshot],
    contract: dict,
    skipped: list[SkipEntry] | None = None,
) -> ComparisonReport:
    report = ComparisonReport(snapshots=snapshots, skipped=skipped or [])
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


def collect_skips(
    inputs: dict[str, Path], contract: dict
) -> tuple[dict[str, Path], list[SkipEntry]]:
    """Filter ``inputs`` against ``contract[runtimes]`` and report skips.

    A runtime is skipped when:

    1. It is declared in ``contract[runtimes]`` with
       ``supports_dump_wav = false`` — typically a runtime that has not yet
       implemented the JSONL phoneme_ids dump path (e.g. C++ / WASM during
       Phase 1).
    2. It is declared in ``contract[runtimes]`` but its path is missing from
       ``inputs`` — typically a build job that failed to upload its
       artifact.

    Inputs whose key is not present in ``contract[runtimes]`` at all are
    kept verbatim (allows ad-hoc experimentation).
    """
    runtimes = contract.get("runtimes", {})
    skipped: list[SkipEntry] = []
    kept: dict[str, Path] = {}
    for name, spec in runtimes.items():
        supports = (
            spec.get("supports_dump_wav", True) if isinstance(spec, dict) else True
        )
        path = inputs.get(name)
        if not supports:
            skipped.append(
                SkipEntry(name, "supports_dump_wav = false (Phase 2 follow-up)")
            )
            continue
        if path is None:
            skipped.append(SkipEntry(name, "no --inputs entry provided"))
            continue
        kept[name] = path
    for name, path in inputs.items():
        if name not in runtimes:
            kept[name] = path
    return kept, skipped


def validate_speaker_embedding(path: Path, contract: dict) -> int:
    """Validate a .npy speaker embedding against zero-shot model contract.

    Returns the embedding dimension. Raises ValueError when:
    * the file does not exist
    * numpy is not available (the script otherwise stays stdlib-only, but
      embedding validation inherently needs numpy to parse .npy)
    * the array is not 1-D float32
    * the dimension does not match `expected_embedding_dim` for any
      `has_speaker_embedding = true` model in the contract
    """
    if not path.exists():
        raise ValueError(f"speaker embedding file not found: {path}")
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ValueError(
            "numpy is required to validate --speaker-embedding .npy files"
        ) from exc
    arr = np.load(path)
    if arr.ndim != 1:
        raise ValueError(f"speaker embedding must be 1-D, got shape {arr.shape}")
    if arr.dtype != np.float32:
        raise ValueError(f"speaker embedding must be float32, got dtype {arr.dtype}")
    models = contract.get("models", {})
    expected_dims: set[int] = set()
    for spec in models.values():
        if not isinstance(spec, dict):
            continue
        if spec.get("has_speaker_embedding") and "expected_embedding_dim" in spec:
            expected_dims.add(int(spec["expected_embedding_dim"]))
    if expected_dims and int(arr.shape[0]) not in expected_dims:
        raise ValueError(
            f"speaker embedding dim {arr.shape[0]} does not match any "
            f"contract `expected_embedding_dim` in {sorted(expected_dims)}"
        )
    return int(arr.shape[0])


def cmd_compare(args: argparse.Namespace) -> int:
    contract = load_contract(args.contract)
    if getattr(args, "speaker_embedding", None) is not None:
        # Fail-fast: a missing or malformed embedding would silently fall
        # back to speaker_id=0 in some runtimes, breaking zero-shot parity
        # without surfacing the cause.
        validate_speaker_embedding(args.speaker_embedding, contract)
    if args.inputs_json:
        raw = json.loads(args.inputs_json.read_text())
        inputs = {k: Path(v) for k, v in raw.items()}
    else:
        inputs = parse_inputs(args.inputs)
    kept, skipped = collect_skips(inputs, contract)
    if not kept and not skipped:
        print(
            "at least one --inputs / --inputs-json entry is required", file=sys.stderr
        )
        return 2
    snapshots = {name: snapshot(name, path) for name, path in kept.items()}
    report = gather_pairs(snapshots, contract, skipped=skipped)
    md = render_markdown(report)
    print(md)
    if args.output:
        args.output.write_text(md, encoding="utf-8")
    if args.require_all_runtimes and skipped:
        names = ", ".join(entry.runtime for entry in skipped)
        print(f"ERROR: runtimes without a WAV: {names}", file=sys.stderr)
        return 1
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
    c.add_argument(
        "--require-all-runtimes",
        action="store_true",
        help=(
            "Exit 1 when any runtime declared in the contract is skipped "
            "(no WAV, or supports_dump_wav = false)."
        ),
    )
    c.add_argument(
        "--speaker-embedding",
        type=Path,
        default=None,
        help=(
            "Optional path to a .npy file containing a 1-D float32 speaker "
            "embedding (expected dim per audio-parity-contract.toml's "
            "[models.<name>] entry, typically 192 for CAM++). When supplied, "
            "downstream runtime drivers should forward this tensor to each "
            "runtime CLI's --speaker-embedding input so zero-shot parity is "
            "verified across runtimes."
        ),
    )
    c.set_defaults(func=cmd_compare)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
