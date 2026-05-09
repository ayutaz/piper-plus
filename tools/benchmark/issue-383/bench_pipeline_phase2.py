"""Issue #383 Phase 2 ベンチ - synthesize_stream_raw の TTFB と total を計測。

Phase 2 (G2P-ORT パイプライン) は ``synthesize_stream_raw`` の最初の chunk
が yield されるまでの時間 (TTFB) を短縮することを狙う。Phase 1 では全文の
G2P を待ってから ORT に入るため TTFB = G2P_total + ORT_first だが、
Phase 2 では TTFB = G2P_first + ORT_first に下がる。

本スクリプトは serial / phase1 / phase2 の 3 構成で TTFB と total を比較する:

* serial:  ``PIPER_G2P_PARALLELISM=1`` (旧挙動 / 完全直列)
* phase1+2: 並列度 auto (``synthesize_stream_raw`` が両方を内包)

Phase 1 と Phase 2 を分離するには内部 API を使う必要がある。``phonemize()``
を先に呼ぶと Phase 1 の挙動を測定できるので、それを serial の補完情報として
記録する。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src" / "python_run"))
sys.path.insert(0, str(REPO_ROOT / "src" / "python"))

from piper.phonemize.japanese import clear_phonemize_cache  # noqa: E402
from piper.voice import PiperVoice  # noqa: E402


@dataclass
class StreamRun:
    n_sentences: int
    repeat_idx: int
    ttfb_ms: float  # time to first chunk
    total_ms: float  # full stream completed
    chunks: int
    audio_samples: int


@dataclass
class StreamAggregate:
    label: str
    n_sentences: int
    repeats: int
    ttfb_median: float
    ttfb_mean: float
    total_median: float
    total_mean: float
    audio_seconds_median: float


def load_sentences(text_path: Path) -> list[str]:
    return [
        line.strip()
        for line in text_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_text(base_sentences: list[str], n: int) -> str:
    if n <= len(base_sentences):
        return "".join(base_sentences[:n])
    return "".join(base_sentences[i % len(base_sentences)] for i in range(n))


def measure_stream(
    voice: PiperVoice,
    text: str,
    *,
    speaker_id: int | None = 0,
    language_id: int | None = 0,
) -> StreamRun:
    """Measure synthesize_stream_raw TTFB and total time."""
    t0 = time.perf_counter()
    first_t = None
    audio_samples = 0
    chunks = 0
    for chunk in voice.synthesize_stream_raw(
        text, speaker_id=speaker_id, language_id=language_id
    ):
        if first_t is None:
            first_t = time.perf_counter()
        audio_samples += len(chunk) // 2
        chunks += 1
    t_end = time.perf_counter()

    return StreamRun(
        n_sentences=-1,
        repeat_idx=-1,
        ttfb_ms=(first_t - t0) * 1000.0 if first_t else 0.0,
        total_ms=(t_end - t0) * 1000.0,
        chunks=chunks,
        audio_samples=audio_samples,
    )


def aggregate(label: str, runs: list[StreamRun], sample_rate: int = 22050) -> StreamAggregate:
    ttfbs = sorted(r.ttfb_ms for r in runs)
    totals = sorted(r.total_ms for r in runs)
    audio_samples_median = statistics.median(r.audio_samples for r in runs)
    audio_seconds_median = audio_samples_median / sample_rate
    return StreamAggregate(
        label=label,
        n_sentences=runs[0].n_sentences,
        repeats=len(runs),
        ttfb_median=statistics.median(ttfbs),
        ttfb_mean=statistics.mean(ttfbs),
        total_median=statistics.median(totals),
        total_mean=statistics.mean(totals),
        audio_seconds_median=audio_seconds_median,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue #383 Phase 2 benchmark")
    parser.add_argument(
        "--model",
        default=str(REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx"),
    )
    parser.add_argument("--config", default=None)
    parser.add_argument(
        "--text",
        default=str(REPO_ROOT / "tools" / "benchmark" / "texts" / "ja.txt"),
    )
    parser.add_argument("--ns", nargs="+", type=int, default=[1, 2, 5, 10, 20, 50])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument(
        "--cache-mode",
        choices=["cold", "warm"],
        default="cold",
        help="cold = clear LRU before each repeat; warm = keep cache",
    )
    parser.add_argument(
        "--out",
        default=str(
            REPO_ROOT / "tools" / "benchmark" / "issue-383" / "phase2_results.json"
        ),
    )
    parser.add_argument("--speaker-id", type=int, default=0)
    parser.add_argument("--language-id", type=int, default=0)
    args = parser.parse_args()

    print(f"[bench] loading voice: {args.model}")
    t0 = time.perf_counter()
    voice = PiperVoice.load(args.model, args.config)
    print(f"[bench] voice loaded in {(time.perf_counter()-t0)*1000:.1f} ms")

    base_sentences = load_sentences(Path(args.text))
    print(f"[bench] {len(base_sentences)} seed sentences")

    print("[bench] global warmup (3 short runs)...")
    for _ in range(3):
        measure_stream(voice, build_text(base_sentences, 2))

    # Two configurations:
    #   - "serial" : PIPER_G2P_PARALLELISM=1  (old behavior)
    #   - "phase2" : auto (G2P-ORT pipeline kicks in for 2+ sentences)
    configs = [
        ("serial", "1"),
        ("phase2", None),  # unset -> auto
    ]

    runs_per_config: dict[str, dict[int, list[StreamRun]]] = {}

    for config_name, env_value in configs:
        print(f"\n[bench] === config: {config_name} ===")
        if env_value is None:
            os.environ.pop("PIPER_G2P_PARALLELISM", None)
        else:
            os.environ["PIPER_G2P_PARALLELISM"] = env_value

        runs_per_n: dict[int, list[StreamRun]] = {}
        for n in args.ns:
            text = build_text(base_sentences, n)
            print(
                f"[bench] N={n} chars={sum(1 for c in text if not c.isspace())} "
                f"- {args.warmups} warmup + {args.repeats} repeats"
            )
            for _ in range(args.warmups):
                if args.cache_mode == "cold":
                    clear_phonemize_cache()
                measure_stream(voice, text)

            results: list[StreamRun] = []
            for r in range(args.repeats):
                if args.cache_mode == "cold":
                    clear_phonemize_cache()
                run = measure_stream(voice, text)
                run.n_sentences = n
                run.repeat_idx = r
                results.append(run)
                print(
                    f"  rep {r}: ttfb={run.ttfb_ms:7.1f}ms  "
                    f"total={run.total_ms:8.1f}ms  chunks={run.chunks}"
                )
            runs_per_n[n] = results
        runs_per_config[config_name] = runs_per_n

    payload = {
        "model": str(args.model),
        "config": args.config,
        "text_source": str(args.text),
        "ns": args.ns,
        "repeats": args.repeats,
        "warmups": args.warmups,
        "cache_mode": args.cache_mode,
        "platform": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
        },
        "configs": {
            cfg: {
                "runs": {str(n): [asdict(r) for r in runs] for n, runs in per_n.items()},
                "aggregates": [
                    asdict(aggregate(cfg, runs)) for runs in per_n.values()
                ],
            }
            for cfg, per_n in runs_per_config.items()
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"[bench] wrote {out_path}")

    # Summary
    print(f"\n=== SUMMARY [{args.cache_mode} cache] (median over repeats) ===")
    print(
        f"{'cfg':<8} {'N':>4} {'ttfb_ms':>10} {'total_ms':>10} {'audio_s':>8}"
    )
    for cfg, per_n in runs_per_config.items():
        for n, runs in per_n.items():
            agg = aggregate(cfg, runs)
            print(
                f"{cfg:<8} {n:>4} {agg.ttfb_median:>10.1f} "
                f"{agg.total_median:>10.1f} {agg.audio_seconds_median:>8.2f}"
            )

    # Δ per N
    print("\n=== DELTA serial -> phase2 ===")
    print(f"{'N':>4} {'ttfb_serial':>12} {'ttfb_phase2':>12} {'TTFB Δ':>8} "
          f"{'total_Δ':>8}")
    for n in args.ns:
        ser = aggregate("serial", runs_per_config["serial"][n])
        ph2 = aggregate("phase2", runs_per_config["phase2"][n])
        ttfb_delta = (ph2.ttfb_median - ser.ttfb_median) / ser.ttfb_median * 100
        total_delta = (ph2.total_median - ser.total_median) / ser.total_median * 100
        print(
            f"{n:>4} {ser.ttfb_median:>12.1f} {ph2.ttfb_median:>12.1f} "
            f"{ttfb_delta:>+7.1f}% {total_delta:>+7.1f}%"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
