#!/usr/bin/env python3
"""GT frame-level F0 / V-UV の抽出とキャッシュ化 (v10b S-2、Phase C 前処理)。

docs/design/zero-shot-v10b-s2-f0-design.md §4.6。``dataset.jsonl`` の各発話に
ついて、キャッシュ済み ``audio_norm_path`` から spectrogram と**同一の frame
格子** (SR 22050 / hop 256) の F0 を推定し、``{output_dir}/{cache_id}.f0.npy``
(fp16, ``[T_frames]``, 無声 = 0.0) として書き出す。

    uv run python -m piper_train.tools.extract_f0 \\
        --dataset "${DATASET_DIR}/dataset.jsonl" \\
        --output-dir "${DATASET_DIR}/f0" \\
        --workers 30 --report "${DATASET_DIR}/f0_report.json"

推定器
------
**pyworld の DIO + StoneMask** を既定にする。Harvest は精度で上回るが
~0.3-0.5x RT で 300k 発話では 33h/32core 級になるのに対し、DIO は 5-20x RT で
1.5-3h/32core 級に収まる (設計 doc §4.6)。``--estimator harvest`` で切替可能。

.. warning::

   **本モジュールは「学習ターゲット生成」であり EVAL-ONLY メトリクスではない。**
   評価側の F0 は ``piper_train.tools.measure_prosody`` が **librosa.pyin** で
   独立に測る。推定器を意図的に分けているのは、学習ターゲットと評価が同一
   推定器だと「その推定器が高分散と読む音」を作る方向の抜け道が (弱いながら)
   開くため — 分離しておけば
   docs/design/zero-shot-v10b-quality-plan.md §4.3 の F0 gate が独立性を保つ
   (設計 doc §4.6 / §5.4、R6)。この分離を崩す変更 (例: ここを pyin に統一する、
   逆に measure_prosody を pyworld にする) は gate の独立性を失わせるので、
   契約 docs/spec/zs-eval-contract.md §2 と合わせてレビューすること。

   なお本ファイルは ``piper_train/tools/`` 配下の**オフライン前処理**であり、
   ``scripts/check_zs_metric_isolation.py`` の scope 外 (契約 §2 の
   「オフライン前処理のデータゲートは流用禁止の対象外」に該当する)。学習側は
   キャッシュ済み ``.npy`` を読むだけで、F0 推定器を import しない。

品質ガード
----------
オクターブエラー (DIO の典型的な失敗) は学習ターゲットを直接汚染するため、
話者ごとの F0 中央値から ±1 オクターブ外れたフレーム率と連続長を集計し、
``--report`` の JSON に出す。有声率 / F0 レンジのヒストグラムも同時に出力する。
これらは**オフライン前処理のデータ品質検査**であり、学習 loss には一切
流れない。

ライセンス
----------
``pyworld`` (JeremyCCHsu/Python-Wrapper-for-World-Vocoder) は MIT、内部の
WORLD vocoder (mmorise/World) は modified BSD (3-clause)。いずれも許諾型で、
v8 以降の「public + 商用利用可の open-model」方針と両立する。前処理専用の
依存であり、配布物 (ONNX / ランタイム) には一切含まれない。
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np


logger = logging.getLogger(__name__)


# ``audio_spec_path`` から canonical cache_id を復元する時に剥がす接尾辞。
# ``tools.precompute_mel._SPEC_SUFFIXES`` / ``PiperDataset._MEL_STRIP_SUFFIXES``
# と同一順序で保つこと (writer 3 箇所 / reader 1 箇所の同期点)。
_SPEC_SUFFIXES = (".spec.pt", ".spec.npy", ".pt", ".npy")

# 話者中央値から何 cent 外れたら「オクターブエラー候補」とみなすか。
# 1 オクターブ = 1200 cent。半オクターブ (600) を閾値にすると通常の抑揚
# (男性話者でも ±400 cent 程度) を拾いすぎるため、900 cent で切る。
_OCTAVE_ERROR_CENTS = 900.0


def cache_id_from_spec_path(audio_spec_path: Path | str) -> str:
    """``{sha256}.spec.pt`` 等から cache_id を復元する。"""
    name = Path(audio_spec_path).name
    for suffix in _SPEC_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(audio_spec_path).stem


def f0_path_for(output_dir: Path | str, audio_spec_path: Path | str) -> Path:
    """``{output_dir}/{cache_id}.f0.npy`` を組み立てる。

    ``PiperDataset._f0_path_for`` (reader 側) と同一規約。片方だけ変えると
    キャッシュが黙って無視され S-2 が無効化されるので、両方同時に直すこと。
    """
    return Path(output_dir) / f"{cache_id_from_spec_path(audio_spec_path)}.f0.npy"


def spec_frames_for(audio_length: int, hop_length: int = 256) -> int:
    """``mel_processing.spectrogram_torch`` が返すフレーム数を計算する。

    同関数は ``center=False`` で、事前に ``(n_fft − hop) / 2`` の reflect pad を
    両側に入れる。結果として frame 数は n_fft に依存せず
    ``(audio_length − hop) // hop + 1`` になる。F0 を spec と同じ格子に揃える
    ための唯一の基準なので、``test_spec_frames_for_matches_spectrogram_torch``
    が実際の STFT 出力と突き合わせて固定している。
    """
    if audio_length < hop_length:
        return 1
    return (audio_length - hop_length) // hop_length + 1


def _align_to_frames(f0: np.ndarray, n_frames: int) -> np.ndarray:
    """推定器のフレーム数を spec 格子に合わせる (末尾を trim / 端値で pad)。"""
    if len(f0) == n_frames:
        return f0
    if len(f0) > n_frames:
        return f0[:n_frames]
    pad = np.full(n_frames - len(f0), f0[-1] if len(f0) else 0.0, dtype=f0.dtype)
    return np.concatenate([f0, pad])


def extract_f0_frames(
    audio: np.ndarray,
    sample_rate: int = 22050,
    hop_length: int = 256,
    f0_floor: float = 65.0,
    f0_ceil: float = 800.0,
    estimator: str = "dio",
) -> np.ndarray:
    """波形 → spec 格子の F0 (Hz, float32, 無声 = 0.0)。

    ``estimator`` は ``"dio"`` (DIO + StoneMask、既定) か ``"harvest"``。
    """
    import pyworld  # noqa: PLC0415 — 前処理専用の重い依存を import 時に引かない

    x = np.ascontiguousarray(audio, dtype=np.float64)
    frame_period = hop_length * 1000.0 / sample_rate
    if estimator == "harvest":
        f0, t = pyworld.harvest(
            x,
            sample_rate,
            f0_floor=f0_floor,
            f0_ceil=f0_ceil,
            frame_period=frame_period,
        )
    elif estimator == "dio":
        f0, t = pyworld.dio(
            x,
            sample_rate,
            f0_floor=f0_floor,
            f0_ceil=f0_ceil,
            frame_period=frame_period,
        )
    else:
        raise ValueError(f"unknown estimator: {estimator!r} (dio | harvest)")
    # StoneMask は DIO / Harvest どちらの粗い推定も精密化する
    f0 = pyworld.stonemask(x, f0, t, sample_rate)
    f0 = np.asarray(f0, dtype=np.float32)
    # 推定器の f0_floor/ceil をまたぐ値は無声扱いに倒す (学習ターゲットの汚染防止)
    f0[(f0 < f0_floor) | (f0 > f0_ceil)] = 0.0
    return _align_to_frames(f0, spec_frames_for(len(x), hop_length))


def load_audio_norm(audio_norm_path: Path | str) -> np.ndarray:
    """``.npy`` / 旧 ``.pt`` の audio_norm キャッシュを 1-D float32 で読む。"""
    p = Path(audio_norm_path)
    if p.suffix == ".npy":
        audio = np.load(str(p))
    else:
        import torch  # noqa: PLC0415 — 旧 .pt キャッシュ用の fallback

        audio = torch.load(str(p), weights_only=True, map_location="cpu").numpy()
    audio = np.asarray(audio, dtype=np.float32).squeeze()
    if audio.ndim != 1:
        raise ValueError(f"unexpected audio shape {audio.shape} in {p}")
    return audio


def f0_quality_stats(f0: np.ndarray, reference_median_hz: float | None = None) -> dict:
    """1 発話の F0 品質統計 (有声率 / レンジ / オクターブエラー候補)。

    ``reference_median_hz`` (話者中央値) を渡すと、そこから ±900 cent 以上
    外れた有声フレームの割合と最長連続長を返す — DIO のオクターブエラーは
    連続区間として出るため、率だけでなく run length も見る。
    """
    voiced = f0 > 0
    n_frames = int(f0.size)
    n_voiced = int(voiced.sum())
    stats: dict = {
        "n_frames": n_frames,
        "n_voiced": n_voiced,
        "voiced_rate": (n_voiced / n_frames) if n_frames else 0.0,
    }
    if n_voiced == 0:
        stats.update(
            f0_median_hz=None,
            f0_p5_hz=None,
            f0_p95_hz=None,
            octave_error_rate=0.0,
            octave_error_max_run=0,
        )
        return stats

    fv = f0[voiced].astype(np.float64)
    stats["f0_median_hz"] = float(np.median(fv))
    stats["f0_p5_hz"] = float(np.percentile(fv, 5))
    stats["f0_p95_hz"] = float(np.percentile(fv, 95))

    if reference_median_hz is None or reference_median_hz <= 0:
        stats["octave_error_rate"] = 0.0
        stats["octave_error_max_run"] = 0
        return stats

    cents = 1200.0 * np.log2(fv / reference_median_hz)
    outlier = np.abs(cents) >= _OCTAVE_ERROR_CENTS
    stats["octave_error_rate"] = float(outlier.mean())
    run = best = 0
    for flag in outlier:
        run = run + 1 if flag else 0
        best = max(best, run)
    stats["octave_error_max_run"] = int(best)
    return stats


def summarize_speakers(per_utt: list[dict]) -> dict:
    """話者ごとの集計 (中央値 F0 / 有声率 / オクターブエラー率) を返す。

    per_utt の各要素は ``{"speaker_id": int|None, **f0_quality_stats(...)}``。
    """
    by_speaker: dict = defaultdict(list)
    for row in per_utt:
        by_speaker[row.get("speaker_id")].append(row)

    out: dict = {}
    for speaker_id, rows in by_speaker.items():
        medians = [r["f0_median_hz"] for r in rows if r.get("f0_median_hz")]
        voiced_rates = [r["voiced_rate"] for r in rows]
        oct_rates = [r.get("octave_error_rate", 0.0) for r in rows]
        out[str(speaker_id)] = {
            "n_utterances": len(rows),
            "f0_median_hz": float(np.median(medians)) if medians else None,
            "voiced_rate_median": float(np.median(voiced_rates)),
            "octave_error_rate_mean": float(np.mean(oct_rates)),
            "n_utts_octave_error_gt_5pct": int(sum(1 for r in oct_rates if r > 0.05)),
        }
    return out


def _atomic_np_save(arr: np.ndarray, path: Path) -> None:
    """temp file + rename で書く (``precompute_mel._atomic_np_save`` と同型)。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.close(tmp_fd)
        with open(tmp_path, "wb") as f:
            np.save(f, arr)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# --- worker 状態 (プロセスごとに _worker_init が 1 回だけ埋める) ---
_worker_cfg: dict = {}


def _worker_init(cfg: dict) -> None:
    global _worker_cfg  # noqa: PLW0603
    _worker_cfg = cfg


def _process_one(record: dict) -> dict:
    """1 発話ぶんの F0 を計算して書き出し、品質統計を返す。"""
    cfg = _worker_cfg
    out_path = f0_path_for(cfg["output_dir"], record["audio_spec_path"])
    result = {
        "audio_spec_path": record["audio_spec_path"],
        "speaker_id": record.get("speaker_id"),
        "error": None,
    }
    try:
        if not cfg["overwrite"] and out_path.exists():
            f0 = np.load(out_path).astype(np.float32)
        else:
            audio = load_audio_norm(record["audio_norm_path"])
            f0 = extract_f0_frames(
                audio,
                sample_rate=cfg["sample_rate"],
                hop_length=cfg["hop_length"],
                f0_floor=cfg["f0_floor"],
                f0_ceil=cfg["f0_ceil"],
                estimator=cfg["estimator"],
            )
            _atomic_np_save(f0.astype(np.float16), out_path)
        result.update(f0_quality_stats(f0))
    except Exception as exc:  # noqa: BLE001 — 親プロセスに全て集約して報告
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def iter_records(dataset_jsonl: Path):
    """``dataset.jsonl`` の各行から必要フィールドを取り出す (相対パス解決込み)。"""
    dataset_dir = Path(dataset_jsonl).parent
    with open(dataset_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed jsonl line")
                continue
            an, asp = rec.get("audio_norm_path"), rec.get("audio_spec_path")
            if not an or not asp:
                continue

            def _resolve(p: str) -> str:
                path = Path(p)
                return str(path if path.is_absolute() else dataset_dir / path)

            yield {
                "audio_norm_path": _resolve(an),
                "audio_spec_path": _resolve(asp),
                "speaker_id": rec.get("speaker_id"),
            }


def run(
    dataset_jsonl: Path,
    output_dir: Path,
    sample_rate: int = 22050,
    hop_length: int = 256,
    f0_floor: float = 65.0,
    f0_ceil: float = 800.0,
    estimator: str = "dio",
    workers: int | None = None,
    overwrite: bool = False,
    report_path: Path | None = None,
) -> dict:
    """dataset 全体の F0 を抽出し、品質レポート dict を返す。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = list(iter_records(Path(dataset_jsonl)))
    if not records:
        logger.warning("No utterances found in %s", dataset_jsonl)
        return {"n_ok": 0, "n_error": 0, "speakers": {}}

    cfg = {
        "output_dir": str(output_dir),
        "sample_rate": sample_rate,
        "hop_length": hop_length,
        "f0_floor": f0_floor,
        "f0_ceil": f0_ceil,
        "estimator": estimator,
        "overwrite": overwrite,
    }

    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    logger.info(
        "Extracting F0 for %d utterance(s) with %d worker(s) (estimator=%s)",
        len(records),
        workers,
        estimator,
    )

    if workers <= 1:
        _worker_init(cfg)
        results = [_process_one(r) for r in records]
    else:
        with mp.Pool(workers, initializer=_worker_init, initargs=(cfg,)) as pool:
            results = pool.map(_process_one, records, chunksize=32)

    errors = [r for r in results if r["error"]]
    ok = [r for r in results if not r["error"]]
    for r in errors[:20]:
        logger.error("%s: %s", r["audio_spec_path"], r["error"])

    # --- 品質ガード: 話者中央値を確定させてからオクターブエラーを再判定 ---
    speaker_median = {
        spk: summary["f0_median_hz"] for spk, summary in summarize_speakers(ok).items()
    }
    for row in ok:
        ref = speaker_median.get(str(row.get("speaker_id")))
        if ref:
            f0 = np.load(f0_path_for(output_dir, row["audio_spec_path"])).astype(
                np.float32
            )
            row.update(f0_quality_stats(f0, reference_median_hz=ref))
            row["speaker_id"] = row.get("speaker_id")

    report = {
        "n_ok": len(ok),
        "n_error": len(errors),
        "estimator": estimator,
        "hop_length": hop_length,
        "sample_rate": sample_rate,
        "speakers": summarize_speakers(ok),
        "errors": [
            {"audio_spec_path": r["audio_spec_path"], "error": r["error"]}
            for r in errors[:200]
        ],
    }
    logger.info(
        "F0 extraction done: ok=%d error=%d speakers=%d",
        report["n_ok"],
        report["n_error"],
        len(report["speakers"]),
    )
    if report_path is not None:
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("wrote %s", report_path)
    return report


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True, help="dataset.jsonl のパス")
    ap.add_argument(
        "--output-dir",
        help="F0 キャッシュの出力先 (既定: dataset.jsonl と同階層の f0/)",
    )
    ap.add_argument("--sample-rate", type=int, default=22050)
    ap.add_argument("--hop-length", type=int, default=256)
    ap.add_argument("--f0-floor", type=float, default=65.0)
    ap.add_argument("--f0-ceil", type=float, default=800.0)
    ap.add_argument(
        "--estimator",
        default="dio",
        choices=("dio", "harvest"),
        help="dio (既定、5-20x RT) か harvest (高精度、0.3-0.5x RT)",
    )
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--overwrite", action="store_true", default=False)
    ap.add_argument("--report", help="品質レポート JSON の出力先")
    args = ap.parse_args(argv)

    dataset = Path(args.dataset)
    output_dir = Path(args.output_dir) if args.output_dir else dataset.parent / "f0"
    run(
        dataset_jsonl=dataset,
        output_dir=output_dir,
        sample_rate=args.sample_rate,
        hop_length=args.hop_length,
        f0_floor=args.f0_floor,
        f0_ceil=args.f0_ceil,
        estimator=args.estimator,
        workers=args.workers,
        overwrite=args.overwrite,
        report_path=Path(args.report) if args.report else None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
