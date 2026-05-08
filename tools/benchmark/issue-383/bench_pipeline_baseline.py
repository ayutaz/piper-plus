"""Issue #383 ベースライン計測 — G2P / ORT を分離し直列パイプラインの内訳を取る。

現状 (`PiperVoice.synthesize_stream_raw`) は文分割後に sentence ごとに
[G2P → phonemes_to_ids → ORT 推論] を直列実行している。本スクリプトは:

* 文数 N ∈ {1, 2, 5, 10, 20, 50} について N 文の合成を REPEATS 回実行する
* 各 sentence の G2P 時間 / phonemes_to_ids 時間 / ORT 推論時間 を
  ``time.perf_counter`` で計測し、全体に対する G2P 比率を算出する
* 結果を JSON / Markdown で保存する

並列化後は同じ条件で再計測し差分を見る。
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

# Allow running without `pip install -e` for python_run.
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src" / "python_run"))
sys.path.insert(0, str(REPO_ROOT / "src" / "python"))

from piper.voice import PiperVoice  # noqa: E402
from piper.phonemize.japanese import clear_phonemize_cache  # noqa: E402


@dataclass
class SentenceTiming:
    sentence_idx: int
    char_count: int
    phoneme_count: int
    g2p_ms: float
    ids_ms: float
    ort_ms: float
    audio_samples: int


@dataclass
class RunResult:
    n_sentences: int
    repeat_idx: int
    total_ms: float
    g2p_total_ms: float
    ids_total_ms: float
    ort_total_ms: float
    overhead_ms: float  # total - (g2p + ids + ort)
    sentence_timings: list[SentenceTiming] = field(default_factory=list)


@dataclass
class AggregatedResult:
    n_sentences: int
    repeats: int
    total_ms_median: float
    total_ms_mean: float
    total_ms_p95: float
    total_ms_min: float
    total_ms_max: float
    g2p_ms_median: float
    ort_ms_median: float
    ids_ms_median: float
    g2p_ratio_median: float
    audio_seconds_median: float
    rtf_median: float  # real-time factor = total_ms / (audio_seconds * 1000)


def load_sentences(text_path: Path) -> list[str]:
    return [line.strip() for line in text_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_text(base_sentences: list[str], n: int) -> str:
    """文数 n のテキストを構築。base が足りない場合は循環。"""
    if n <= len(base_sentences):
        return "".join(base_sentences[:n])
    return "".join(base_sentences[i % len(base_sentences)] for i in range(n))


def run_once(
    voice: PiperVoice,
    text: str,
    *,
    speaker_id: int | None = 0,
    language_id: int | None = 0,
) -> RunResult:
    """1 回分の計測。voice.synthesize_stream_raw と同じパスを再現。"""
    n_sentences_target = -1  # filled later
    t_total_start = time.perf_counter()

    # Step 1: phonemize() — 全文の G2P (現状はループで sentence ごとに実行)
    t_g2p_start = time.perf_counter()
    sentence_phonemes = voice.phonemize(text)
    t_g2p_end = time.perf_counter()
    g2p_total_ms = (t_g2p_end - t_g2p_start) * 1000.0

    # Step 2/3: 各文ごとに phonemes_to_ids → ORT
    sentence_timings: list[SentenceTiming] = []
    ids_total_ms = 0.0
    ort_total_ms = 0.0
    for idx, phonemes in enumerate(sentence_phonemes):
        # phonemes_to_ids
        t1 = time.perf_counter()
        phoneme_ids = voice.phonemes_to_ids(phonemes)
        t2 = time.perf_counter()

        # ORT (synthesize_ids_to_raw)
        audio_bytes = voice.synthesize_ids_to_raw(
            phoneme_ids,
            speaker_id=speaker_id,
            language_id=language_id,
        )
        t3 = time.perf_counter()

        ids_ms = (t2 - t1) * 1000.0
        ort_ms = (t3 - t2) * 1000.0
        ids_total_ms += ids_ms
        ort_total_ms += ort_ms

        sentence_timings.append(
            SentenceTiming(
                sentence_idx=idx,
                char_count=-1,  # 個別文の charは phonemize の入力分割が見えないので未取得
                phoneme_count=len(phoneme_ids),
                g2p_ms=-1.0,  # phonemize() は一括なので個別 G2P 時間は計測不能
                ids_ms=ids_ms,
                ort_ms=ort_ms,
                audio_samples=len(audio_bytes) // 2,
            )
        )

    t_total_end = time.perf_counter()
    total_ms = (t_total_end - t_total_start) * 1000.0
    overhead_ms = total_ms - (g2p_total_ms + ids_total_ms + ort_total_ms)

    return RunResult(
        n_sentences=len(sentence_phonemes),
        repeat_idx=-1,
        total_ms=total_ms,
        g2p_total_ms=g2p_total_ms,
        ids_total_ms=ids_total_ms,
        ort_total_ms=ort_total_ms,
        overhead_ms=overhead_ms,
        sentence_timings=sentence_timings,
    )


def aggregate(results: list[RunResult]) -> AggregatedResult:
    totals = sorted(r.total_ms for r in results)
    g2ps = sorted(r.g2p_total_ms for r in results)
    orts = sorted(r.ort_total_ms for r in results)
    idses = sorted(r.ids_total_ms for r in results)
    ratios = sorted(r.g2p_total_ms / r.total_ms for r in results)

    audio_samples_median = statistics.median(
        sum(s.audio_samples for s in r.sentence_timings) for r in results
    )

    sample_rate = 22050  # piper-plus のデフォルト
    audio_seconds_median = audio_samples_median / sample_rate
    total_seconds_median = statistics.median(totals) / 1000.0
    rtf = total_seconds_median / audio_seconds_median if audio_seconds_median > 0 else 0.0

    return AggregatedResult(
        n_sentences=results[0].n_sentences,
        repeats=len(results),
        total_ms_median=statistics.median(totals),
        total_ms_mean=statistics.mean(totals),
        total_ms_p95=totals[int(len(totals) * 0.95)] if len(totals) >= 20 else totals[-1],
        total_ms_min=totals[0],
        total_ms_max=totals[-1],
        g2p_ms_median=statistics.median(g2ps),
        ort_ms_median=statistics.median(orts),
        ids_ms_median=statistics.median(idses),
        g2p_ratio_median=statistics.median(ratios),
        audio_seconds_median=audio_seconds_median,
        rtf_median=rtf,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue #383 baseline benchmark")
    parser.add_argument(
        "--model",
        default=str(REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx"),
        help="ONNX model path",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="config.json path (defaults to <model>.json)",
    )
    parser.add_argument(
        "--text",
        default=str(REPO_ROOT / "tools" / "benchmark" / "texts" / "ja.txt"),
        help="seed text file (one sentence per line)",
    )
    parser.add_argument(
        "--ns",
        nargs="+",
        type=int,
        default=[1, 2, 5, 10, 20, 50],
        help="sentence counts to benchmark",
    )
    parser.add_argument("--repeats", type=int, default=5, help="repetitions per N")
    parser.add_argument("--warmups", type=int, default=2, help="warmup runs per N")
    parser.add_argument(
        "--cache-mode",
        choices=["cold", "warm", "both"],
        default="both",
        help="cold: clear G2P LRU before each repeat / warm: keep cache / both: run both",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "tools" / "benchmark" / "issue-383" / "baseline_results.json"),
        help="output JSON path",
    )
    parser.add_argument("--speaker-id", type=int, default=0)
    parser.add_argument("--language-id", type=int, default=0)
    args = parser.parse_args()

    print(f"[bench] loading voice: {args.model}")
    t0 = time.perf_counter()
    voice = PiperVoice.load(args.model, args.config)
    print(f"[bench] voice loaded in {(time.perf_counter()-t0)*1000:.1f} ms")

    base_sentences = load_sentences(Path(args.text))
    print(f"[bench] {len(base_sentences)} seed sentences from {args.text}")

    runs_per_mode: dict[str, dict[int, list[RunResult]]] = {}

    # Voice-level warmup (model first-run is much slower).
    print("[bench] global warmup (3 short runs)...")
    for _ in range(3):
        run_once(voice, build_text(base_sentences, 2), speaker_id=args.speaker_id, language_id=args.language_id)

    modes = ["cold", "warm"] if args.cache_mode == "both" else [args.cache_mode]
    for mode in modes:
        print(f"\n[bench] === cache-mode: {mode} ===")
        runs_per_n: dict[int, list[RunResult]] = {}
        for n in args.ns:
            text = build_text(base_sentences, n)
            char_count = sum(1 for c in text if not c.isspace())
            print(f"[bench] N={n} (chars={char_count}) - {args.warmups} warmup + {args.repeats} repeats")
            # Per-N warmup (always hot for ORT). For cold mode we still want the
            # cache to be cleared right before each measured repeat below.
            for _ in range(args.warmups):
                run_once(voice, text, speaker_id=args.speaker_id, language_id=args.language_id)
            results: list[RunResult] = []
            for r in range(args.repeats):
                if mode == "cold":
                    clear_phonemize_cache()
                res = run_once(voice, text, speaker_id=args.speaker_id, language_id=args.language_id)
                res.repeat_idx = r
                results.append(res)
                print(
                    f"  rep {r}: total={res.total_ms:7.1f}ms  "
                    f"g2p={res.g2p_total_ms:6.1f}ms ({res.g2p_total_ms/res.total_ms*100:5.1f}%)  "
                    f"ort={res.ort_total_ms:7.1f}ms  ids={res.ids_total_ms:5.1f}ms  "
                    f"oh={res.overhead_ms:5.1f}ms"
                )
            runs_per_n[n] = results
        runs_per_mode[mode] = runs_per_n

    payload = {
        "model": str(args.model),
        "config": args.config,
        "text_source": str(args.text),
        "ns": args.ns,
        "repeats": args.repeats,
        "warmups": args.warmups,
        "cache_modes": modes,
        "platform": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
        },
        "modes": {
            mode: {
                "runs": {
                    str(n): [asdict(r) for r in runs]
                    for n, runs in runs_per_n.items()
                },
                "aggregates": [asdict(aggregate(rs)) for rs in runs_per_n.values()],
            }
            for mode, runs_per_n in runs_per_mode.items()
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"[bench] wrote {out_path}")

    for mode, runs_per_n in runs_per_mode.items():
        aggs = [aggregate(rs) for rs in runs_per_n.values()]
        print(f"\n=== SUMMARY [{mode} cache] (median over repeats) ===")
        print(
            f"{'N':>4} {'total_ms':>10} {'g2p_ms':>8} {'ort_ms':>8} {'ids_ms':>7} "
            f"{'g2p%':>6} {'audio_s':>8} {'RTF':>6}"
        )
        for a in aggs:
            print(
                f"{a.n_sentences:>4} "
                f"{a.total_ms_median:>10.1f} "
                f"{a.g2p_ms_median:>8.1f} "
                f"{a.ort_ms_median:>8.1f} "
                f"{a.ids_ms_median:>7.1f} "
                f"{a.g2p_ratio_median*100:>5.1f}% "
                f"{a.audio_seconds_median:>8.2f} "
                f"{a.rtf_median:>6.3f}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
