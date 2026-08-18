#!/usr/bin/env python3
"""S-2 の go/no-go: F0 シフト追従テスト (v10b Phase D 検証項目 3)。

docs/design/zero-shot-v10b-s2-f0-design.md §6.4 の検証 3 / §6.5 R1。

**何を測るのか**: 学習済み ckpt に対し、予測 F0 を ±N semitone シフトして
合成し、**出力の実測 F0 がどれだけ追従したか**を semitone 比で出す::

    追従率 = median( 実測 semitone 差 ) / 指令 semitone 差

S-2 の設計上最大のリスクは「decoder が F0 を無視する」ことである (teacher
forcing 下では GT F0 が z と冗長なので、F0 チャネルを使う勾配圧力が構造的に
弱い)。追従率が ~0 ならその失敗機序が発現しており、S-2 は v10c 送り。
**追従率 ≥ 0.8 が事前登録された go 基準** — 学習を長く回さずに判定できる
単変量テストなので、smoke の早い段階で回す。

    uv run python -m piper_train.tools.f0_shift_ablation \\
        --checkpoint "${OUTPUT_DIR}/checkpoints/last.ckpt" \\
        --reference-embedding ref.npy \\
        --texts-jsonl texts.jsonl \\
        --output-dir "${OUTPUT_DIR}/f0-ablation" \\
        --shifts -2 0 2

**測定器の分離について**: 出力 F0 の実測は
``piper_train.tools.measure_prosody`` (librosa.pyin) を **subprocess で**
呼ぶ。同一プロセスで import しても E-8 gate (``scripts/
check_zs_metric_isolation.py``) には触れない (本ファイルは tools/ 配下で
role 対象外) が、評価器を torch を積んだプロセスに引き込まない構造を保つ
ほうが、「評価は微分不能」という契約の意図に沿う。学習ターゲット側の推定器
(pyworld) とも別実装で、この分離自体が設計 doc R6 の要求である。

本ツールは**評価専用**であり、ここで測った量を学習 loss に流してはいけない
(契約 docs/spec/zs-eval-contract.md §2 禁止事項 4)。
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np


_LOGGER = logging.getLogger("f0_shift_ablation")

# 追従率の事前登録 go 基準 (設計 doc §6.4 検証 3)。ここを下げるのは
# 「測ってから基準をいじる」ことなので、緩和は設計 doc の改訂を伴うこと。
GO_THRESHOLD = 0.8


def semitone_to_scale(semitones: float) -> float:
    """semitone → 周波数倍率 (2^(n/12))。"""
    return float(2.0 ** (semitones / 12.0))


def follow_ratio(
    measured_median_hz: dict[float, float], base_semitone: float = 0.0
) -> dict[float, float]:
    """指令 semitone → 実測 semitone の追従率を返す。

    Args:
        measured_median_hz: ``{指令 semitone: 実測 F0 中央値 [Hz]}``
        base_semitone: 基準とする指令値 (通常 0 = 無シフト)

    Returns:
        ``{指令 semitone: 追従率}`` (基準点自身は除く)。基準の実測値が
        欠測 (None / 0) なら空 dict。
    """
    base_hz = measured_median_hz.get(base_semitone)
    if not base_hz or base_hz <= 0:
        return {}
    out: dict[float, float] = {}
    for commanded, measured in measured_median_hz.items():
        if commanded == base_semitone or not measured or measured <= 0:
            continue
        measured_semitone = 12.0 * np.log2(measured / base_hz)
        out[commanded] = float(measured_semitone / commanded)
    return out


def summarize(ratios: dict[float, float]) -> dict:
    """追従率の集計と go/no-go 判定 (判定は表示のみ、副作用なし)。"""
    values = [v for v in ratios.values() if np.isfinite(v)]
    median_ratio = float(np.median(values)) if values else 0.0
    return {
        "per_shift": ratios,
        "median_follow_ratio": median_ratio,
        "go_threshold": GO_THRESHOLD,
        "verdict": "go" if median_ratio >= GO_THRESHOLD else "no-go",
    }


def write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    """float [-1, 1] の 1-D 波形を 16-bit PCM wav で書く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def measure_group_f0_median(clips_dir: Path, json_out: Path) -> float | None:
    """``measure_prosody`` を subprocess で呼び、group median の F0 を返す。"""
    cmd = [
        sys.executable,
        "-m",
        "piper_train.tools.measure_prosody",
        "--clips-dir",
        str(clips_dir),
        "--json-out",
        str(json_out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        _LOGGER.error("measure_prosody failed: %s", result.stderr[-2000:])
        return None
    with open(json_out, encoding="utf-8") as f:
        report = json.load(f)
    group = report.get("group_median") or {}
    return group.get("f0_median_hz")


def synthesize_shifted(
    model,
    phoneme_ids_list: list[list[int]],
    speaker_embedding: np.ndarray,
    out_dir: Path,
    f0_scale: float,
    sample_rate: int,
    language_id: int | None = None,
    noise_scale: float = 0.4,
    noise_scale_w: float = 0.5,
    length_scale: float = 1.0,
) -> None:
    """``f0_scale`` を掛けた予測 F0 で合成し、wav を ``out_dir`` に書く。"""
    import torch  # noqa: PLC0415 — CLI 実行時にだけ引く

    out_dir.mkdir(parents=True, exist_ok=True)
    emb = torch.from_numpy(speaker_embedding.astype(np.float32)).reshape(1, -1)
    lid = None if language_id is None else torch.LongTensor([language_id])

    with torch.no_grad():
        for idx, phoneme_ids in enumerate(phoneme_ids_list):
            text = torch.LongTensor([phoneme_ids])
            lengths = torch.LongTensor([len(phoneme_ids)])
            out = model.infer(
                text,
                lengths,
                lid=lid,
                noise_scale=noise_scale,
                noise_scale_w=noise_scale_w,
                length_scale=length_scale,
                speaker_embeddings=emb,
                f0_scale=f0_scale,
            )
            audio = out.audio.squeeze().cpu().numpy()
            write_wav(out_dir / f"utt{idx:04d}.wav", audio, sample_rate)


def load_model(checkpoint: str):
    """ckpt から generator を eval モードで読み出す。"""
    import torch  # noqa: PLC0415

    from piper_train.vits.lightning import VitsModel  # noqa: PLC0415

    model = VitsModel.load_from_checkpoint(checkpoint, dataset=None, strict=False)
    model_g = model.model_g
    model_g.eval()
    if not getattr(model_g, "use_f0_path", False):
        raise SystemExit(
            "This checkpoint was not trained with --use-f0-path; the F0 shift "
            "ablation is meaningless without the explicit F0 path."
        )
    with torch.no_grad():
        model_g.dec.remove_weight_norm()
    return model, model_g


def load_texts(path: Path) -> list[list[int]]:
    """1 行 1 発話の jsonl から ``phoneme_ids`` を読む。"""
    out: list[list[int]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line)["phoneme_ids"])
    return out


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument(
        "--reference-embedding",
        required=True,
        help="192 次元 CAM++ 参照 embedding (.npy)",
    )
    ap.add_argument(
        "--texts-jsonl",
        required=True,
        help='1 行 1 発話の jsonl ({"phoneme_ids": [...]})',
    )
    ap.add_argument("--output-dir", required=True)
    ap.add_argument(
        "--shifts",
        type=float,
        nargs="+",
        default=[-2.0, 0.0, 2.0],
        # NOTE: ``help=`` は Windows の cp932 コンソールにそのまま書き出される。
        # em dash (U+2014) 等の cp932 非対応文字を入れると ``--help`` が
        # UnicodeEncodeError で落ちるので、記号は ASCII 範囲に留めること。
        help="指令 semitone シフト (0 を必ず含めること: 基準になる)",
    )
    ap.add_argument("--language-id", type=int, default=None)
    ap.add_argument("--noise-scale", type=float, default=0.4)
    ap.add_argument("--noise-scale-w", type=float, default=0.5)
    ap.add_argument("--length-scale", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args(argv)

    import torch  # noqa: PLC0415

    if 0.0 not in args.shifts:
        ap.error("--shifts must include 0 (the unshifted reference point)")

    torch.manual_seed(args.seed)
    model, model_g = load_model(args.checkpoint)
    sample_rate = int(model.hparams.sample_rate)
    phoneme_ids_list = load_texts(Path(args.texts_jsonl))
    emb = np.load(args.reference_embedding).reshape(-1)

    out_root = Path(args.output_dir)
    measured: dict[float, float] = {}
    for shift in args.shifts:
        # 同一 seed から始めて合成条件を揃える (シフト以外を単変量にする)
        torch.manual_seed(args.seed)
        clips_dir = out_root / f"shift_{shift:+.1f}"
        synthesize_shifted(
            model_g,
            phoneme_ids_list,
            emb,
            clips_dir,
            f0_scale=semitone_to_scale(shift),
            sample_rate=sample_rate,
            language_id=args.language_id,
            noise_scale=args.noise_scale,
            noise_scale_w=args.noise_scale_w,
            length_scale=args.length_scale,
        )
        median_hz = measure_group_f0_median(
            clips_dir, out_root / f"prosody_{shift:+.1f}.json"
        )
        _LOGGER.info("shift %+.1f st -> measured F0 median %s Hz", shift, median_hz)
        if median_hz:
            measured[shift] = median_hz

    report = summarize(follow_ratio(measured))
    report["measured_median_hz"] = measured
    report["checkpoint"] = args.checkpoint
    out_path = out_root / "f0_shift_ablation.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    _LOGGER.info(
        "median follow ratio = %.3f (threshold %.2f) -> %s | wrote %s",
        report["median_follow_ratio"],
        GO_THRESHOLD,
        report["verdict"].upper(),
        out_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
