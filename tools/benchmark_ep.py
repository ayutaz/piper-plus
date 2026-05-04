"""CPU スレッド数別・キャッシュ有無の推論速度ベンチマーク.

CoreML EP はこの VITS モデルの Duration Predictor (NonZero + ゼロ要素動的形状)
で非対応のため CPU EP のみで計測する。
"""
import os
import sys
import time
import statistics
import platform
import numpy as np

MODEL_PATH = "test/models/multilingual-test-medium.onnx"
WARMUP_RUNS = 3
BENCH_RUNS = 20
PHONEME_SIZES = [30, 100, 200]
SCALES = np.array([0.667, 1.0, 0.8], dtype=np.float32)


def make_inputs(n_phonemes: int) -> dict:
    rng = np.random.default_rng(42)
    phoneme_ids = rng.integers(3, 170, size=(1, n_phonemes), dtype=np.int64)
    return {
        "input": phoneme_ids,
        "input_lengths": np.array([n_phonemes], dtype=np.int64),
        "scales": SCALES,
        "lid": np.array([0], dtype=np.int64),
        "prosody_features": np.zeros((1, n_phonemes, 3), dtype=np.int64),
    }


def bench_session(sess, label: str) -> dict[int, dict]:
    results = {}
    for n in PHONEME_SIZES:
        inputs = make_inputs(n)
        for _ in range(WARMUP_RUNS):
            sess.run(None, inputs)
        times_ms = []
        for _ in range(BENCH_RUNS):
            t0 = time.perf_counter()
            out = sess.run(None, inputs)
            t1 = time.perf_counter()
            times_ms.append((t1 - t0) * 1000)
        audio_samples = out[0].shape[-1]
        audio_ms = audio_samples / 22050 * 1000
        rtf = statistics.median(times_ms) / audio_ms
        results[n] = {
            "median_ms": statistics.median(times_ms),
            "p95_ms": sorted(times_ms)[int(BENCH_RUNS * 0.95)],
            "audio_ms": audio_ms,
            "rtf": rtf,
        }
        print(
            f"  {label:12s} | {n:4d} ph | "
            f"median={results[n]['median_ms']:7.1f}ms  "
            f"p95={results[n]['p95_ms']:7.1f}ms  "
            f"audio={audio_ms:6.0f}ms  RTF={rtf:.4f}"
        )
    return results


def make_session(threads: int):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(
        MODEL_PATH,
        sess_options=so,
        providers=["CPUExecutionProvider"],
    )


def main():
    import onnxruntime as ort

    cpu_count = os.cpu_count() or 4
    print("=" * 65)
    print("  piper-plus EP ベンチマーク")
    print("=" * 65)
    print(f"  Machine : {platform.machine()}  {platform.processor()}")
    print(f"  Python  : {sys.version.split()[0]}")
    print(f"  ORT     : {ort.__version__}")
    print(f"  Available providers: {ort.get_available_providers()}")
    print(f"  CPU logical cores  : {cpu_count}")
    print(f"  Warmup={WARMUP_RUNS}  Bench={BENCH_RUNS}")
    print()

    print("[CoreML EP 対応確認]")
    print("  このモデル (VITS) は Duration Predictor の NonZero op +")
    print("  ゼロ要素動的形状が CoreML EP 非対応のため CPU EP で計測します。")
    print()

    configs = [
        ("CPU-1thread",  1),
        ("CPU-2thread",  2),
        ("CPU-4thread",  4),
        ("CPU-8thread",  min(8, cpu_count)),
    ]
    # 重複排除
    seen = set()
    unique_configs = []
    for label, n in configs:
        if n not in seen:
            seen.add(n)
            unique_configs.append((label, n))

    all_results: dict[str, dict] = {}

    print("=== セッション作成時間 ===")
    for label, threads in unique_configs:
        t0 = time.perf_counter()
        make_session(threads)
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"  {label:12s}: {elapsed:.0f}ms")
    print()

    print("=== 推論ベンチマーク ===")
    print(f"  {'設定':12s} | {'ph':>4s} | {'median':>10s}  {'p95':>10s}  {'audio_len':>9s}  {'RTF':>6s}")
    print("  " + "-" * 62)
    for label, threads in unique_configs:
        sess = make_session(threads)
        results = bench_session(sess, label)
        all_results[label] = results
        print()

    # 基準: CPU-1thread
    base_label = unique_configs[0][0]
    base = all_results[base_label]

    print("=== スレッド別 高速化倍率 (基準: CPU-1thread) ===")
    print(f"  {'設定':12s} | ", end="")
    print("  ".join(f"{n:>4d}ph" for n in PHONEME_SIZES))
    print("  " + "-" * 50)
    for label, _ in unique_configs:
        speedups = [
            f"{base[n]['median_ms'] / all_results[label][n]['median_ms']:.2f}x"
            for n in PHONEME_SIZES
        ]
        print(f"  {label:12s} | " + "    ".join(f"{s:>6s}" for s in speedups))


if __name__ == "__main__":
    main()
