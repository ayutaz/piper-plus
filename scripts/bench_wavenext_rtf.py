#!/usr/bin/env python3
"""WaveNeXt vs MB-iSTFT decoder RTF kill-switch benchmark (random weights).

Stage 1 の GPU smoke 学習に投資する前に、decoder 速度だけを canonical 代理
環境 (GitHub Actions ubuntu-24.04、サーバー級 4 vCPU) で白黒付ける。
速度はランダム重みでも判定可能 (グラフ構造のみに依存)。

計測条件は docs/spec/ort-session-contract.toml 準拠:
intra_op=4 / inter_op=1 / SEQUENTIAL / ORT_ENABLE_ALL。

Part A: decoder 単体 ONNX (WaveNeXt opset17 vs MB-iSTFT opset15) を
        T_frames グリッドで A/B (fp32、可能なら fp16 も)。
Part B: 配布済み実モデル (test/models/multilingual-test-medium.onnx) を
        ORT profiling で回し、end-to-end に占める decoder ノードの時間比を
        推定 (best-effort — fusion でノード名が失われた分は coverage で報告)。

背景: docs/design/wavenext-decoder-ablation/04-pre-stage0-verification.md §2
(ローカル Ryzen 5900X では contract 準拠で WaveNeXt が 30-40% 遅い負方向 prior)。
"""

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path


# Windows コンソール (cp932) でも markdown summary を安全に出力する
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src" / "python"))

SAMPLE_RATE = 22050
HOP = 256
SEED = 1234


def cpu_info() -> dict:
    import os

    info = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "logical_cpus": os.cpu_count(),
        "python": platform.python_version(),
    }
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text().splitlines():
            if line.lower().startswith("model name"):
                info["cpu_model"] = line.split(":", 1)[1].strip()
                break
    return info


def build_decoders():
    import torch

    from piper_train.vits.mb_istft import MBiSTFTGenerator
    from piper_train.vits.wavenext import WaveNeXtGenerator

    torch.manual_seed(SEED)
    wavenext = WaveNeXtGenerator(in_channels=192)
    wavenext.onnx_export_mode = True
    wavenext.eval()

    torch.manual_seed(SEED)
    mb = MBiSTFTGenerator(
        initial_channel=192,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
        gin_channels=0,
    )
    mb.remove_weight_norm()
    mb.onnx_export_mode = True
    mb.eval()
    return wavenext, mb


def export_decoder(model, path: Path, opset: int) -> None:
    import torch

    z = torch.randn(1, 192, 50)
    torch.onnx.export(
        model,
        (z,),
        str(path),
        opset_version=opset,
        input_names=["z"],
        output_names=["audio"],
        dynamic_axes={"z": {0: "batch", 2: "time"}, "audio": {0: "batch", 2: "samples"}},
        dynamo=False,
    )


def to_fp16(src: Path, dst: Path) -> bool:
    try:
        import onnx
        from onnxconverter_common import float16

        model = onnx.load(str(src))
        model_fp16 = float16.convert_float_to_float16(
            model, keep_io_types=True, op_block_list=["LayerNormalization"]
        )
        onnx.save(model_fp16, str(dst))
        return True
    except Exception as exc:  # noqa: BLE001 - fp16 is best-effort
        print(f"fp16 conversion skipped for {src.name}: {exc}", file=sys.stderr)
        return False


def contract_session(path: Path):
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.intra_op_num_threads = 4
    so.inter_op_num_threads = 1
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])


def bench_session(sess, t_frames: int, warmup: int, runs: int) -> dict:
    import numpy as np

    rng = np.random.default_rng(SEED)
    z = rng.standard_normal((1, 192, t_frames), dtype=np.float32)
    feed = {"z": z}
    for _ in range(warmup):
        sess.run(None, feed)
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        sess.run(None, feed)
        times.append((time.perf_counter() - t0) * 1000.0)
    times.sort()
    audio_sec = t_frames * HOP / SAMPLE_RATE
    p50 = statistics.median(times)
    return {
        "t_frames": t_frames,
        "audio_sec": round(audio_sec, 3),
        "p50_ms": round(p50, 2),
        "p95_ms": round(times[int(len(times) * 0.95) - 1], 2),
        "rtf_p50": round(p50 / 1000.0 / audio_sec, 4),
    }


def profile_shipped_model(model_path: Path, runs: int) -> dict:
    """配布済み実モデルの decoder ノード時間比を ORT profiling で推定する。"""
    import numpy as np
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.intra_op_num_threads = 4
    so.inter_op_num_threads = 1
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.enable_profiling = True
    sess = ort.InferenceSession(str(model_path), so, providers=["CPUExecutionProvider"])

    rng = np.random.default_rng(SEED)
    feed = {}
    for inp in sess.get_inputs():
        name, shape = inp.name, inp.shape
        if name == "input":
            feed[name] = rng.integers(10, 60, size=(1, 25), dtype=np.int64)
        elif name == "input_lengths":
            feed[name] = np.array([25], dtype=np.int64)
        elif name == "scales":
            feed[name] = np.array([0.667, 1.0, 0.8], dtype=np.float32)
        elif inp.type == "tensor(int64)":
            feed[name] = np.zeros([d if isinstance(d, int) else 1 for d in shape], dtype=np.int64)
        else:
            feed[name] = np.zeros(
                [d if isinstance(d, int) else 1 for d in shape], dtype=np.float32
            )

    for _ in range(3):
        sess.run(None, feed)
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        sess.run(None, feed)
        times.append((time.perf_counter() - t0) * 1000.0)
    prof_path = Path(sess.end_profiling())

    events = json.loads(prof_path.read_text())
    dec_us = 0
    node_us = 0
    for ev in events:
        if ev.get("cat") != "Node" or "dur" not in ev:
            continue
        node_us += ev["dur"]
        if "/dec/" in ev.get("name", "") or ev.get("name", "").startswith("dec."):
            dec_us += ev["dur"]
    prof_path.unlink(missing_ok=True)
    return {
        "model": model_path.name,
        "end_to_end_p50_ms": round(statistics.median(times), 2),
        "decoder_node_time_share": round(dec_us / node_us, 3) if node_us else None,
        "note": "share は profiling ノード名 '/dec/' ベースの近似 (fusion で名前が失われた分は不算入)",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("wavenext_rtf_results.json"))
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--t-frames", type=int, nargs="+", default=[60, 150, 400])
    args = parser.parse_args()

    results = {"cpu": cpu_info(), "contract": "intra=4/inter=1/SEQUENTIAL/ORT_ENABLE_ALL"}
    print(f"CPU: {results['cpu']}", file=sys.stderr)

    wavenext, mb = build_decoders()
    tmp = Path(tempfile.mkdtemp(prefix="wavenext_rtf_"))
    variants = []
    wn_fp32 = tmp / "wavenext_op17_fp32.onnx"
    mb_fp32 = tmp / "mb_istft_op15_fp32.onnx"
    export_decoder(wavenext, wn_fp32, opset=17)
    export_decoder(mb, mb_fp32, opset=15)
    variants += [("wavenext", "fp32", wn_fp32), ("mb_istft", "fp32", mb_fp32)]
    for arch, fp32_path in (("wavenext", wn_fp32), ("mb_istft", mb_fp32)):
        fp16_path = tmp / f"{arch}_fp16.onnx"
        if to_fp16(fp32_path, fp16_path):
            variants.append((arch, "fp16", fp16_path))

    bench = []
    for arch, precision, path in variants:
        sess = contract_session(path)
        for t in args.t_frames:
            row = {"arch": arch, "precision": precision, **bench_session(sess, t, args.warmup, args.runs)}
            bench.append(row)
            print(f"  {arch:9s} {precision} T={t:4d}: p50={row['p50_ms']}ms rtf={row['rtf_p50']}", file=sys.stderr)
        del sess
    results["decoder_bench"] = bench

    shipped = REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx"
    if shipped.exists():
        try:
            results["shipped_model_profile"] = profile_shipped_model(shipped, args.runs)
        except Exception as exc:  # noqa: BLE001 - part B is best-effort
            results["shipped_model_profile"] = {"error": str(exc)}

    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    # Markdown summary (stdout → GITHUB_STEP_SUMMARY)
    print("## WaveNeXt RTF kill-switch (random weights, contract threading)")
    print(f"\nCPU: `{results['cpu'].get('cpu_model', 'unknown')}` "
          f"({results['cpu']['logical_cpus']} vCPU) / {results['contract']}\n")
    print("| arch | precision | T frames | audio s | p50 ms | p95 ms | RTF p50 |")
    print("|------|-----------|----------|---------|--------|--------|---------|")
    for r in bench:
        print(f"| {r['arch']} | {r['precision']} | {r['t_frames']} | {r['audio_sec']} "
              f"| {r['p50_ms']} | {r['p95_ms']} | {r['rtf_p50']} |")
    for t in args.t_frames:
        for precision in ("fp32", "fp16"):
            wn = next((r for r in bench if r["arch"] == "wavenext" and r["t_frames"] == t
                       and r["precision"] == precision), None)
            mbr = next((r for r in bench if r["arch"] == "mb_istft" and r["t_frames"] == t
                        and r["precision"] == precision), None)
            if wn and mbr:
                ratio = wn["p50_ms"] / mbr["p50_ms"]
                print(f"\n- {precision} T={t}: WaveNeXt / MB-iSTFT p50 ratio = **{ratio:.2f}x**")
    prof = results.get("shipped_model_profile")
    if prof and "error" not in prof:
        print(f"\n配布実モデル ({prof['model']}) end-to-end p50 {prof['end_to_end_p50_ms']}ms、"
              f"decoder ノード時間比 ~ **{prof['decoder_node_time_share']}** ({prof['note']})")


if __name__ == "__main__":
    main()
