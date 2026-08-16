#!/usr/bin/env python3
"""Cross-utterance SECS 評価ハーネス (dual-encoder + ceiling/floor 正規化転写率)。

EVAL-ONLY: 本モジュールの全指標は評価専用。学習 loss / reward / 動的サンプル選別への
流用を恒久禁止 (docs/spec/zs-eval-contract.md §2 禁止事項 4)。

Why this exists (docs/design/zero-shot-v10-roadmap.md A-1e):
same-utterance SECS は SCL の Goodhart で膨張する (0.775 誤報の既知事故) ため、
zero-shot の話者類似度は **cross-utterance SECS のみ**で判定する。さらに cosine
のスケールは encoder ごとに非互換なので、ceiling (同一話者の実発話同士) と
floor (近い声質の別話者) で正規化した転写率

    normalized_transfer = (cross_utt_secs - floor) / (ceiling - floor)

を主指標とする (報告 headline も raw SECS ではなく normalized_transfer —
契約 §2)。CAM++ 単独での go/no-go を防ぐため、held-out の第 2 encoder
(ECAPA、``export_ecapa_onnx`` で作成) を ``--encoder2`` で並走できる。

定義:
- cross_utt_secs: synth 各ファイルの「speaker-utts (exclude-ref 除外後) との平均
  cosine」を synth 全体で平均
- same_utt_secs: synth 各ファイルと exclude-ref (条件付けに使った発話) の平均
  cosine。**判定使用禁止 (参考値)**
- gap_same_minus_cross: same_utt_secs − cross_utt_secs。SCL Goodhart で膨らむ
  成分の直接観測 (baseline 比 +0.01 以上の拡大は警告)
- ceiling: speaker-utts (exclude-ref 除外後) 同士の全ペア平均 cosine
- floor: speaker-utts (exclude-ref 除外後) と floor-refs の全ペア平均 cosine

JSON schema は "zs-eval-v3" (v1 → v2 → v3 は field 追加のみの後方互換)。
v3 (Phase A、docs/design/zero-shot-v10b-quality-plan.md §2) の追加:

- **manifest** (E-5(i)): synth / speaker-utts / floor / encoder の全ファイルを
  ファイル名 + sha256 で pin (+ ``--meta-json`` の合成条件 verbatim 埋め込み)。
  §4.3 の事前登録判定はこの manifest 値への「固定」として運用する
- **content-hash guard** (E-5(ii)): ``--exclude-ref`` は path 一致に加え sha256
  一致でも cross 集合から除外。synth と実音声 (speaker/floor) の sha256 一致は
  取り違えとして SystemExit (eval 全体が無効になるため警告では足りない)
- **above_ceiling_flag** (E-7(iii)): cross_utt_secs > ceiling は「synth が実発話
  ペアより参照に近い」= 録音特性複製の疑い (YourTTS arXiv:2112.02418)。
  goodhart_flag とは独立の flag family — どちらか true なら改善と報告しない
- **band / comb / prosody ブロック** (E-1〜E-4、default ON): 帯域プロファイル
  (band_profile) + SR/128 格子コム超過 (comb_metrics) + 韻律記述統計
  (prosody_stats) を synth と real anchor (= 除外後 speaker-utts) で測る。
  測定は素の出力 wav に対して行うこと (後処理禁止 — 契約 §2 禁止事項 5)。
  事前登録閾値 (plan §4.3) の pass/fail 判定はツールでは行わない (参考表示のみ
  — 判定は /eval-zs skill と /publish-model の責務)

``--baseline-json`` で過去の eval JSON と比較し、「primary (CAM++) だけ上がり
第 2 encoder が追随しない」パターン (Phase 0 Arm B で実証された Goodhart) を
``goodhart_flag`` として機械判定する。契約: ``docs/spec/zs-eval-contract.md``。

Usage:
    python -m piper_train.tools.eval_zs_secs \\
        --synth-dir synth_wavs/ \\
        --speaker-utts speaker_wavs/ \\
        --exclude-ref speaker_wavs/ref_001.wav \\
        --floor-refs floor_wavs/ \\
        --encoder models/campplus.onnx \\
        --encoder2 models/ecapa.onnx \\
        --require-encoder2 \\
        --meta-json synthesis_conditions.json \\
        --baseline-json prev_report.json \\
        --json-out report.json

備考: 両 encoder とも入力は ``extract_speaker_embedding.preprocess_audio`` の
Kaldi fbank [1, T, 80]。ECAPA 側の前処理差は exporter が graph 内で吸収済み
(export_ecapa_onnx docstring 参照)。推論は再現性優先で CPU 固定。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import onnxruntime

from piper_train.extract_speaker_embedding import extract_embedding, preprocess_audio
from piper_train.tools import (
    measure_band_noise,
    measure_comb_artifacts,
    measure_prosody,
)
from piper_train.tools.acoustic_frames import (
    HOP as _AC_HOP,
    N_FFT as _AC_N_FFT,
    PYIN_FMAX,
    PYIN_FMIN,
    SR_ANALYSIS as _AC_SR,
    analyze_frames,
    load_wav,
)


_LOGGER = logging.getLogger(__name__)

# JSON schema バージョン (v1 → v2 → v3 は field 追加のみの後方互換)
SCHEMA_VERSION = "zs-eval-v3"

# Goodhart 判定閾値。Phase 0/1 の事前登録閾値 (CAM++ +0.02 未満 = 効果なし /
# ECAPA +0.01 未満 = 不同調 → Goodhart 棄却) をそのまま制度化する
# (docs/design/zero-shot-warm-restart-diagnostics-phase0-1.md §2)。
GOODHART_PRIMARY_DELTA = 0.02
GOODHART_ENCODER2_DELTA = 0.01
# same/cross gap (Goodhart 成分) の拡大警告閾値
GAP_WIDENING_DELTA = 0.01

# baseline 比較で情報表示する音響 Δ の (block, group, key) — §4.6。flag 化はしない
_ACOUSTIC_DELTA_KEYS = (
    ("comb", "synth", "comb_excess_db_median"),
    ("comb", "synth", "hf_autocorr_lag128_median"),
    ("comb", "synth", "hf_autocorr_lag256_median"),
    ("band", "synth", "voiced_hi_excess_db_median"),
    ("band", "delta", "shelf_voiced_max_delta_db"),
)


def collect_wavs(directory: str | Path) -> list[Path]:
    """ディレクトリ直下の wav ファイルを収集する (大文字拡張子も、重複除去)。"""
    d = Path(directory)
    if not d.is_dir():
        raise SystemExit(f"not a directory: {d}")
    found = {p.resolve() for p in list(d.glob("*.wav")) + list(d.glob("*.WAV"))}
    return sorted(found)


def _l2_normalize(embs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(embs, axis=-1, keepdims=True)
    return embs / np.where(norms > 1e-8, norms, 1.0)


def compute_secs_report(
    synth_embs: np.ndarray,
    speaker_embs: np.ndarray,
    ref_emb: np.ndarray | None = None,
    floor_embs: np.ndarray | None = None,
) -> dict:
    """埋め込み群から SECS レポート (1 encoder ぶん) を計算する純関数。

    Args:
        synth_embs: [N, D] 合成音声の embedding。
        speaker_embs: [M, D] 同一話者の実発話 embedding (exclude-ref は除外済み)。
        ref_emb: [D] 条件付けに使った発話の embedding (same-utt SECS 用)。
        floor_embs: [K, D] 近い声質の別話者 embedding (floor 用)。

    Returns:
        dict: cross_utt_secs / same_utt_secs / gap_same_minus_cross / ceiling /
        floor / normalized_transfer / cross_exceeds_ceiling / n_synth / n_refs。
        該当データが無い指標は None (キー欠落ではなく null 明示 — zs-eval 契約)。
        ceiling は speaker_embs が 2 発話未満だと計算不能で None になる
        (CLI 側は 2 発話以上を要求する)。

        normalized_transfer は **ceiling > floor のときのみ**定義する (E-5(iii)
        符号ガード): ceiling <= floor は floor 集合が話者に近すぎる兆候で、
        負の分母で符号反転した「正規化」値を出すより null + 警告が安全。
        cross_exceeds_ceiling (E-7(iii)) は cross > ceiling の録音特性複製
        シグナル (ceiling が無ければ null)。
    """
    synth = _l2_normalize(np.asarray(synth_embs, dtype=np.float64))
    refs = _l2_normalize(np.asarray(speaker_embs, dtype=np.float64))
    if synth.ndim != 2 or refs.ndim != 2:
        raise ValueError("synth_embs / speaker_embs must be 2-D [N, D]")

    # cross-utt: synth ごとの refs 平均 cosine → synth 全体で平均 (= 全ペア平均)
    cross = float(np.mean(synth @ refs.T))

    same: float | None = None
    if ref_emb is not None:
        r = _l2_normalize(np.asarray(ref_emb, dtype=np.float64).reshape(1, -1))
        same = float(np.mean(synth @ r.T))

    ceiling: float | None = None
    if refs.shape[0] >= 2:
        sim = refs @ refs.T
        iu = np.triu_indices(refs.shape[0], k=1)
        ceiling = float(sim[iu].mean())

    floor: float | None = None
    if floor_embs is not None and len(floor_embs) > 0:
        fl = _l2_normalize(np.asarray(floor_embs, dtype=np.float64))
        floor = float(np.mean(refs @ fl.T))

    normalized_transfer: float | None = None
    if ceiling is not None and floor is not None:
        denom = ceiling - floor
        if denom <= 0:
            # E-5(iii) 符号ガード: ceiling <= floor では正規化転写率は未定義
            _LOGGER.warning(
                "ceiling (%.4f) <= floor (%.4f): floor 集合が話者に近すぎる — "
                "floor 選定を疑うこと。normalized_transfer は null",
                ceiling,
                floor,
            )
        elif denom <= 1e-6:
            _LOGGER.warning(
                "ceiling (%.4f) and floor (%.4f) nearly equal; "
                "normalized_transfer is undefined",
                ceiling,
                floor,
            )
        else:
            normalized_transfer = float((cross - floor) / denom)

    # SCL Goodhart で膨らむ成分の直接観測 (same-utt 過適合の指標)
    gap: float | None = None
    if same is not None:
        gap = float(same - cross)

    return {
        "cross_utt_secs": cross,
        "same_utt_secs": same,
        "gap_same_minus_cross": gap,
        "ceiling": ceiling,
        "floor": floor,
        "normalized_transfer": normalized_transfer,
        # E-7(iii): synth が実発話ペアより参照に近い = 録音特性複製の疑い
        "cross_exceeds_ceiling": None if ceiling is None else bool(cross > ceiling),
        "n_synth": int(synth.shape[0]),
        "n_refs": int(refs.shape[0]),
    }


def _encoder_gap(block: dict) -> float | None:
    """encoder ブロックから same/cross gap を取り出す。

    zs-eval-v1 の JSON には gap_same_minus_cross field が無いため、
    same_utt_secs / cross_utt_secs から復元する (後方互換)。
    """
    gap = block.get("gap_same_minus_cross")
    if gap is not None:
        return float(gap)
    same = block.get("same_utt_secs")
    cross = block.get("cross_utt_secs")
    if same is not None and cross is not None:
        return float(same) - float(cross)
    return None


def compare_with_baseline(
    report: dict,
    baseline: dict,
    primary: str = "campplus",
    secondary: str = "encoder2",
) -> dict:
    """現レポートを過去の eval JSON と比較し、Δ と Goodhart 判定を返す純関数。

    Goodhart 判定 (docs/spec/zs-eval-contract.md、Phase 0 Arm B の制度化):
    primary の Δcross >= +0.02 かつ secondary の Δcross < +0.01 のとき True。
    SCL と同型の encoder (CAM++) だけが動く = 「参照 embedding への一致」の
    再現であって話者類似の改善ではない、と機械判定する。どちらかの Δ が
    計算不能 (encoder 欠落など) なら None (判定不能)。

    Returns:
        dict: goodhart_flag (bool | None) / gap_widened_encoders
        (gap が +0.01 以上拡大した encoder 名リスト) / deltas
        (encoder ごとの cross_utt_secs / gap_same_minus_cross の Δ)。
    """
    base_encoders = baseline.get("encoders", {})
    deltas: dict = {}
    gap_widened: list[str] = []
    for name, cur in report["encoders"].items():
        base = base_encoders.get(name)
        if base is None:
            continue
        d_cross: float | None = None
        if (
            cur.get("cross_utt_secs") is not None
            and base.get("cross_utt_secs") is not None
        ):
            d_cross = float(cur["cross_utt_secs"]) - float(base["cross_utt_secs"])
        cur_gap = _encoder_gap(cur)
        base_gap = _encoder_gap(base)
        d_gap: float | None = None
        if cur_gap is not None and base_gap is not None:
            d_gap = cur_gap - base_gap
            if d_gap >= GAP_WIDENING_DELTA:
                gap_widened.append(name)
        deltas[name] = {"cross_utt_secs": d_cross, "gap_same_minus_cross": d_gap}

    d_primary = deltas.get(primary, {}).get("cross_utt_secs")
    d_secondary = deltas.get(secondary, {}).get("cross_utt_secs")
    goodhart: bool | None = None
    if d_primary is not None and d_secondary is not None:
        goodhart = bool(
            d_primary >= GOODHART_PRIMARY_DELTA
            and d_secondary < GOODHART_ENCODER2_DELTA
        )
    return {
        "goodhart_flag": goodhart,
        "gap_widened_encoders": gap_widened,
        "deltas": deltas,
    }


def _acoustic_value(report: dict, block: str, group: str, key: str) -> float | None:
    """report[block][group][key] を null-safe に float で取り出す。"""
    blk = report.get(block)
    if not isinstance(blk, dict):
        return None
    grp = blk.get(group)
    if not isinstance(grp, dict):
        return None
    value = grp.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def acoustics_baseline_delta(report: dict, baseline: dict) -> dict | None:
    """baseline 比の音響 Δ (現在 − baseline) を返す純関数 (§4.6、情報表示のみ)。

    baseline が v1/v2 (band/comb ブロックなし) なら None【決定】。flag 化は
    しない — 「4-9kHz ep69 比非悪化」判定 (plan §4.3) の材料を自動供給するのが
    目的で、判定自体は /eval-zs skill の責務。
    """
    if not (baseline.get("band") or baseline.get("comb")):
        return None
    out: dict = {}
    for block, group, key in _ACOUSTIC_DELTA_KEYS:
        cur = _acoustic_value(report, block, group, key)
        base = _acoustic_value(baseline, block, group, key)
        out[key] = None if cur is None or base is None else float(cur - base)
    return out


# ---------------------------------------------------------------------------
# manifest (E-5(i)) + content-hash guard (E-5(ii))
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_entries(paths: list[Path], hashes: dict[Path, str]) -> list[dict]:
    return [{"file": p.name, "sha256": hashes[p]} for p in paths]


def _hash_all(paths: list[Path]) -> dict[Path, str]:
    return {p: _sha256_file(p) for p in paths}


def _encoder_manifest(encoder_path: str | Path) -> dict:
    p = Path(encoder_path)
    return {
        "path": str(encoder_path),
        "sha256": _sha256_file(p) if p.is_file() else None,
    }


# ---------------------------------------------------------------------------
# band / comb / prosody ブロック (E-1〜E-4、default ON)
# ---------------------------------------------------------------------------

_BAND_PARAMS = {
    "sr": _AC_SR,
    "n_fft": _AC_N_FFT,
    "hop": _AC_HOP,
    "profile_ref_band_hz": list(measure_band_noise.PROFILE_REF_BAND_HZ),
    "shelf_ref_band_hz": list(measure_band_noise.SHELF_REF_BAND_HZ),
    "shelf_band_hz": list(measure_band_noise.SHELF_BAND_HZ),
    "hi_band_hz": list(measure_band_noise.DEFAULT_HI_BAND),
}

_COMB_PARAMS = {
    "grid_hz": _AC_SR / 128.0,  # 172.265625 Hz = SR/128
    "band_hz": list(measure_comb_artifacts.COMB_BAND_HZ),
    "highpass_hz": measure_comb_artifacts.HIGHPASS_HZ,
    "n_fft": measure_comb_artifacts.N_FFT,
    "hop": measure_comb_artifacts.HOP,
    "autocorr_lags": list(measure_comb_artifacts.AUTOCORR_LAGS),
}

_PROSODY_PARAMS = {
    "f0_estimator": "librosa.pyin",
    "fmin": PYIN_FMIN,
    "fmax": PYIN_FMAX,
    "frame_length": _AC_N_FFT,
    "hop": _AC_HOP,
}


def _median_or_none(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def _analyze_clip_group(paths: list[Path]) -> dict:
    """wav 群を per-file 解析する (失敗は WARNING + 集計から除外 — §4.7 縮退)。"""
    profiles: list[dict] = []
    combs: list[dict] = []
    prosody: list[dict] = []
    hi_excess: list[float] = []
    for p in paths:
        try:
            wav = load_wav(p)
            comb = measure_comb_artifacts.comb_metrics(wav, _AC_SR)
            fa = analyze_frames(wav, _AC_SR)
            prof = measure_band_noise.band_profile(fa) if fa is not None else None
            stats = measure_prosody.prosody_stats(fa) if fa is not None else None
            hi = measure_band_noise.voiced_high_band_excess(wav, _AC_SR)
        except Exception as exc:  # noqa: BLE001 — per-file 縮退 (§4.7【決定 D14】)
            _LOGGER.warning("acoustics analysis failed for %s: %s", p.name, exc)
            continue
        if comb is not None:
            combs.append({"file": p.name, **comb})
        if prof is not None:
            profiles.append(prof)
        if stats is not None:
            prosody.append(stats)
        if hi is not None:
            hi_excess.append(float(hi))
    return {
        "profiles": profiles,
        "combs": combs,
        "prosody": prosody,
        "hi_excess": hi_excess,
    }


def _comb_group_medians(entries: list[dict]) -> dict:
    """comb per-file 値のグループ median【決定 D12 — 外れ値耐性】。"""
    return {
        "comb_excess_db_median": _median_or_none(
            [e["comb_excess_db"] for e in entries]
        ),
        "hf_autocorr_lag128_median": _median_or_none(
            [e["hf_autocorr_lag128"] for e in entries]
        ),
        "hf_autocorr_lag256_median": _median_or_none(
            [e["hf_autocorr_lag256"] for e in entries]
        ),
    }


def compute_acoustics_blocks(
    synth_files: list[Path], real_files: list[Path]
) -> tuple[dict | None, dict | None, dict | None]:
    """band / comb / prosody ブロック (synth vs real anchor) を計算する。

    real anchor = speaker-utts の cross set (exclude-ref 除外後)【決定 D11】。
    どちらかの群が全滅 (解析不能) したブロックは None (null 明示)。gate 適用は
    synth 側のみ (real は文脈表示【決定 D4】) — 判定は /eval-zs skill の責務。
    """
    synth = _analyze_clip_group(synth_files)
    real = _analyze_clip_group(real_files)

    band: dict | None = None
    synth_band = measure_band_noise.band_group_summary(synth["profiles"])
    real_band = measure_band_noise.band_group_summary(real["profiles"])
    if synth_band is not None and real_band is not None:
        band = {
            "params": dict(_BAND_PARAMS),
            "synth": {
                **synth_band,
                "voiced_hi_excess_db_median": _median_or_none(synth["hi_excess"]),
            },
            "real": {
                **real_band,
                "voiced_hi_excess_db_median": _median_or_none(real["hi_excess"]),
            },
            "delta": measure_band_noise.band_delta_vs_real(synth_band, real_band),
        }

    comb: dict | None = None
    if synth["combs"] and real["combs"]:
        comb = {
            "params": dict(_COMB_PARAMS),
            "per_file": synth["combs"],
            "synth": _comb_group_medians(synth["combs"]),
            "real": _comb_group_medians(real["combs"]),
        }

    prosody: dict | None = None
    synth_pros = measure_prosody.prosody_group_summary(synth["prosody"])
    real_pros = measure_prosody.prosody_group_summary(real["prosody"])
    if synth_pros is not None and real_pros is not None:
        prosody = {
            "params": dict(_PROSODY_PARAMS),
            "synth": synth_pros,
            "real": real_pros,
            "delta": measure_prosody.prosody_delta(synth_pros, real_pros),
        }

    return band, comb, prosody


# ---------------------------------------------------------------------------
# ONNX embedding 抽出
# ---------------------------------------------------------------------------


def _create_session(encoder_path: str | Path) -> onnxruntime.InferenceSession:
    """SECS 評価用 ONNX session。再現性優先で CPU 固定 (GPU 競合も回避)。"""
    return onnxruntime.InferenceSession(
        str(encoder_path), providers=["CPUExecutionProvider"]
    )


def _extract_embs(
    session: onnxruntime.InferenceSession,
    wav_paths: list[Path],
    fbank_cache: dict[Path, np.ndarray],
) -> np.ndarray:
    """wav 群から embedding を抽出する。fbank は encoder 間で共有キャッシュ。"""
    embs = []
    for p in wav_paths:
        if p not in fbank_cache:
            fbank_cache[p] = preprocess_audio(p)
        embs.append(extract_embedding(session, fbank_cache[p]))
    return np.stack(embs, axis=0)


# ---------------------------------------------------------------------------
# レポート表示
# ---------------------------------------------------------------------------


def _fmt(value: float | None, width: int = 9) -> str:
    return f"{value:{width}.4f}" if value is not None else f"{'n/a':>{width}}"


def _fmt_plain(value: float | None, fmt: str = "{:.3f}") -> str:
    return fmt.format(value) if value is not None else "n/a"


def _print_report(report: dict, synth_dir: str, speaker_dir: str) -> None:
    print(f"=== zero-shot cross-utterance SECS report ({report['schema']}) ===")
    # E-7(i): 報告の主役は normalized_transfer (raw SECS の単独 headline 禁止)
    headline = " / ".join(
        f"{name} {_fmt_plain(r['normalized_transfer'], '{:.4f}')}"
        for name, r in report["encoders"].items()
    )
    print(f"HEADLINE normalized_transfer: {headline}")
    print("  (raw SECS を単独 headline にしない — docs/spec/zs-eval-contract.md §2)")
    print(f"synth dir  : {synth_dir}")
    print(f"speaker dir: {speaker_dir}")
    print()
    header = (
        f"{'encoder':<10} {'norm_transfer':>13} {'cross_utt':>9} "
        f"{'ceiling':>9} {'floor':>9} {'same_utt*':>9} {'n_synth':>7} {'n_refs':>6}"
    )
    print(header)
    print("-" * len(header))
    for name, r in report["encoders"].items():
        nt = r["normalized_transfer"]
        nt_str = f">>> {nt:.4f} <<<" if nt is not None else f"{'n/a':>13}"
        print(
            f"{name:<10} {nt_str:>13} {_fmt(r['cross_utt_secs'])} "
            f"{_fmt(r['ceiling'])} {_fmt(r['floor'])} {_fmt(r['same_utt_secs'])} "
            f"{r['n_synth']:>7} {r['n_refs']:>6}"
        )
    print()
    print(
        "判定は normalized_transfer (cross-utt ベース) で行うこと。\n"
        "* same_utt は SCL Goodhart で膨張するため判定使用禁止 (参考値のみ、\n"
        "  docs/design/zero-shot-v10-roadmap.md 運用原則 1)。"
    )
    # E-7(iii): above_ceiling の常時表示
    flags = " / ".join(
        f"{name} "
        + (
            "n/a"
            if r["cross_exceeds_ceiling"] is None
            else ("yes" if r["cross_exceeds_ceiling"] else "no")
        )
        for name, r in report["encoders"].items()
    )
    print(f"above_ceiling: {flags}")
    _print_acoustics(report)


def _print_acoustics(report: dict) -> None:
    """acoustics サマリ (§4.4)。事前登録値は参考表示のみで PASS/FAIL は出さない。"""
    print("--- acoustics (synth vs real anchor = speaker-utts) ---")
    band, comb, prosody = report.get("band"), report.get("comb"), report.get("prosody")
    if band is None and comb is None and prosody is None:
        print("n/a (--skip-acoustics or 解析不能)")
        return
    if comb is not None:
        print(
            "comb_excess_db median: "
            f"synth {_fmt_plain(comb['synth']['comb_excess_db_median'])} / "
            f"real {_fmt_plain(comb['real']['comb_excess_db_median'])}"
            "   [v10b 事前登録: <1.5]"
        )
        print(
            "hf_autocorr @128/@256: synth "
            f"{_fmt_plain(comb['synth']['hf_autocorr_lag128_median'], '{:.4f}')}/"
            f"{_fmt_plain(comb['synth']['hf_autocorr_lag256_median'], '{:.4f}')} / "
            "real "
            f"{_fmt_plain(comb['real']['hf_autocorr_lag128_median'], '{:.4f}')}/"
            f"{_fmt_plain(comb['real']['hf_autocorr_lag256_median'], '{:.4f}')}"
            "   [<0.05]"
        )
    else:
        print("comb_excess_db: n/a")
    if band is not None:
        shelf_v = band["delta"]["shelf_voiced_max_delta_db"]
        shelf_u = band["delta"]["shelf_unvoiced_max_delta_db"]
        print(
            "shelf 5.5-8.5k voiced max Δ: "
            f"{_fmt_plain(shelf_v, '{:+.2f}')} dB "
            f"(unvoiced {_fmt_plain(shelf_u, '{:+.2f}')} dB)   [≤+2.0 / ≤+3.0]"
        )
        print(
            "voiced_hi_excess (4-9k) median: "
            f"synth {_fmt_plain(band['synth']['voiced_hi_excess_db_median'], '{:.1f}')} / "
            f"real {_fmt_plain(band['real']['voiced_hi_excess_db_median'], '{:.1f}')} dB"
        )
    if prosody is not None:
        d = prosody["delta"]
        print(
            "F0 delta (synth−real): "
            f"std {_fmt_plain(d.get('f0_std_hz'), '{:+.1f}')} Hz / "
            f"p5-95 range {_fmt_plain(d.get('f0_range_p5_p95_hz'), '{:+.1f}')} Hz / "
            f"median {_fmt_plain(d.get('f0_median_hz'), '{:+.1f}')} Hz"
            "   [事前登録: std ≥45Hz, range ≥150Hz (synth 絶対値)]"
        )


def _fmt_delta(value: float | None) -> str:
    return f"{value:+.4f}" if value is not None else "n/a"


def _print_baseline_comparison(comparison: dict) -> None:
    print()
    print(f"=== baseline comparison (vs {comparison['baseline_path']}) ===")
    for name, d in comparison["deltas"].items():
        print(
            f"{name:<10} Δcross_utt: {_fmt_delta(d['cross_utt_secs']):>8}  "
            f"Δgap(same-cross): {_fmt_delta(d['gap_same_minus_cross']):>8}"
        )
    flag = comparison["goodhart_flag"]
    if flag is True:
        label = "TRUE — primary だけ上昇 (Goodhart 疑い、改善と判定しないこと)"
    elif flag is False:
        label = "false"
    else:
        label = "n/a (encoder2 の Δ が計算不能 — 判定不能)"
    print(f"goodhart_flag: {label}")
    acoustics = comparison.get("acoustics")
    if acoustics:
        deltas = "  ".join(
            f"Δ{key}: {_fmt_delta(value)}" for key, value in acoustics.items()
        )
        print(f"acoustics Δ (現在 − baseline、情報表示のみ): {deltas}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_meta_json(path_str: str) -> dict:
    path = Path(path_str)
    if not path.is_file():
        raise SystemExit(f"--meta-json not found: {path}")
    meta = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(meta, dict):
        raise SystemExit(
            f"--meta-json must be a JSON object (合成条件 dict): {path} "
            f"(got {type(meta).__name__})"
        )
    return meta


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="piper_train.tools.eval_zs_secs",
        description="Cross-utterance SECS (dual-encoder, ceiling/floor 正規化転写率)",
    )
    parser.add_argument("--synth-dir", required=True, help="合成 wav 群のディレクトリ")
    parser.add_argument(
        "--speaker-utts",
        required=True,
        help="同一話者の実発話ディレクトリ (cross-utt 対象)",
    )
    parser.add_argument(
        "--exclude-ref",
        help=(
            "条件付けに使った発話 wav。path 一致または sha256 (内容) 一致で "
            "cross 集合から除外し、same-utt SECS の参照として使用"
        ),
    )
    parser.add_argument(
        "--floor-refs", help="近い声質の別話者 wav 群のディレクトリ (optional)"
    )
    parser.add_argument(
        "--floor-selection-note",
        help="floor 集合の選定基準の自由記述 (manifest に記録、E-5(i))",
    )
    parser.add_argument("--encoder", required=True, help="CAM++ ONNX モデルパス")
    parser.add_argument(
        "--encoder2", help="第 2 encoder ONNX パス (ECAPA、optional、Goodhart 検知用)"
    )
    parser.add_argument(
        "--require-encoder2",
        action="store_true",
        help="--encoder2 未指定なら exit 2 (publish/CI ゲート用)",
    )
    parser.add_argument(
        "--baseline-json",
        help=(
            "過去の eval JSON (zs-eval-v1/v2/v3)。encoder ごとの Δ を表示し、"
            "Goodhart 判定 (goodhart_flag) を行う。v3 なら音響 Δ も情報表示"
        ),
    )
    parser.add_argument(
        "--meta-json",
        help=(
            "合成条件 JSON (noise_scale / noise_scale_w / seed / texts 等) を "
            "manifest.synthesis に verbatim 埋め込み (E-5(iii)。§4.3 判定は "
            "manifest pin 値で行う)"
        ),
    )
    parser.add_argument(
        "--skip-acoustics",
        action="store_true",
        help="band/comb/prosody ブロックを計算しない (null 出力、SECS のみの高速 run)",
    )
    parser.add_argument("--json-out", help="レポート JSON の出力先パス")
    args = parser.parse_args(argv)

    if args.require_encoder2 and not args.encoder2:
        _LOGGER.error(
            "--require-encoder2: --encoder2 (held-out 第 2 encoder) が未指定。"
            "CAM++ 単独では Goodhart 検知不能のため gate fail (exit 2)。"
            "契約: docs/spec/zs-eval-contract.md"
        )
        return 2
    if not args.encoder2:
        _LOGGER.warning(
            "--encoder2 未指定: 第 2 encoder なしでは Goodhart 検知不能 "
            "(CAM++ 単独での go/no-go 判定は禁止 — docs/spec/zs-eval-contract.md)。"
            "publish/CI ゲートでは --require-encoder2 を付けること"
        )

    baseline: dict | None = None
    baseline_path: Path | None = None
    if args.baseline_json:
        baseline_path = Path(args.baseline_json)
        if not baseline_path.is_file():
            raise SystemExit(f"--baseline-json not found: {baseline_path}")
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    meta: dict | None = _load_meta_json(args.meta_json) if args.meta_json else None

    synth_files = collect_wavs(args.synth_dir)
    if not synth_files:
        raise SystemExit(f"no wav files in --synth-dir: {args.synth_dir}")

    speaker_files = collect_wavs(args.speaker_utts)
    ref_path: Path | None = None
    ref_sha: str | None = None
    if args.exclude_ref:
        ref_path = Path(args.exclude_ref).resolve()
        if not ref_path.is_file():
            raise SystemExit(f"--exclude-ref not found: {ref_path}")
        ref_sha = _sha256_file(ref_path)

    floor_files = collect_wavs(args.floor_refs) if args.floor_refs else []
    if args.floor_refs and not floor_files:
        raise SystemExit(f"no wav files in --floor-refs: {args.floor_refs}")

    # --- content-hash guard (E-5(ii)) ---
    speaker_hashes = _hash_all(speaker_files)
    # exclude-ref: path 一致 or sha256 (内容) 一致で cross 集合から除外
    excluded = [
        p
        for p in speaker_files
        if p == ref_path or (ref_sha is not None and speaker_hashes[p] == ref_sha)
    ]
    cross_files = [p for p in speaker_files if p not in excluded]
    for p in excluded:
        _LOGGER.info("excluded conditioning reference from cross set: %s", p)
    if len(cross_files) < 2:
        raise SystemExit(
            "need >= 2 speaker utterances after --exclude-ref exclusion "
            f"(got {len(cross_files)}); ceiling requires pairwise cosine"
        )

    synth_hashes = _hash_all(synth_files)
    floor_hashes = _hash_all(floor_files)
    real_by_sha: dict[str, Path] = {}
    for p, digest in {**speaker_hashes, **floor_hashes}.items():
        real_by_sha.setdefault(digest, p)
    for p, digest in synth_hashes.items():
        twin = real_by_sha.get(digest)
        if twin is not None:
            # 合成物と実音声の取り違えは ceiling 系すべてを汚染するため
            # 警告では足りない【決定 D15】
            raise SystemExit(
                f"synth file {p} is byte-identical (sha256) to real audio {twin} — "
                "合成物と実音声の取り違えの疑い。eval 全体が無効のため中止 "
                "(docs/spec/zs-eval-contract.md)"
            )
    dup_shas = {
        digest
        for digest in list(speaker_hashes.values())
        if list(speaker_hashes.values()).count(digest) > 1
    }
    if dup_shas:
        dup_names = sorted(
            p.name for p, digest in speaker_hashes.items() if digest in dup_shas
        )
        _LOGGER.warning(
            "speaker-utts に重複 sha256 (duplicate content): %s — "
            "ceiling が膨張する可能性 (自己類似 1.0 のペアが混入)",
            ", ".join(dup_names),
        )

    encoders = [("campplus", args.encoder)]
    if args.encoder2:
        encoders.append(("encoder2", args.encoder2))

    fbank_cache: dict[Path, np.ndarray] = {}
    report: dict = {
        "schema": SCHEMA_VERSION,
        "encoders": {},
        "goodhart_flag": None,
        "above_ceiling_flag": None,
        "band": None,
        "comb": None,
        "prosody": None,
        "manifest": None,
    }
    for name, encoder_path in encoders:
        _LOGGER.info("extracting embeddings with %s (%s)", name, encoder_path)
        session = _create_session(encoder_path)
        synth_embs = _extract_embs(session, synth_files, fbank_cache)
        speaker_embs = _extract_embs(session, cross_files, fbank_cache)
        ref_emb = (
            _extract_embs(session, [ref_path], fbank_cache)[0]
            if ref_path is not None
            else None
        )
        floor_embs = (
            _extract_embs(session, floor_files, fbank_cache) if floor_files else None
        )
        report["encoders"][name] = compute_secs_report(
            synth_embs, speaker_embs, ref_emb=ref_emb, floor_embs=floor_embs
        )

    # E-7(iii): トップレベル flag は primary (campplus) の値
    report["above_ceiling_flag"] = report["encoders"]["campplus"][
        "cross_exceeds_ceiling"
    ]
    if report["above_ceiling_flag"]:
        _LOGGER.warning(
            "above_ceiling: cross_utt_secs > ceiling — synth が実発話ペアより"
            "参照に近い = 録音特性複製の疑い (YourTTS arXiv:2112.02418)。"
            "改善と報告しないこと (docs/spec/zs-eval-contract.md §3)"
        )

    # E-1〜E-4: band / comb / prosody (default ON、real anchor = 除外後 cross set)
    if not args.skip_acoustics:
        band, comb, prosody = compute_acoustics_blocks(synth_files, cross_files)
        report["band"] = band
        report["comb"] = comb
        report["prosody"] = prosody

    # E-5(i): manifest (ファイル名 + sha256 pin)
    report["manifest"] = {
        "synth": {
            "dir": args.synth_dir,
            "files": _file_entries(synth_files, synth_hashes),
        },
        "speaker_utts": {
            "dir": args.speaker_utts,
            "files": _file_entries(cross_files, speaker_hashes),
        },
        "excluded_by_hash": _file_entries(excluded, speaker_hashes),
        "floor_refs": (
            {
                "dir": args.floor_refs,
                "files": _file_entries(floor_files, floor_hashes),
            }
            if args.floor_refs
            else None
        ),
        "floor_selection_note": args.floor_selection_note,
        "exclude_ref": (
            {"file": ref_path.name, "sha256": ref_sha} if ref_path is not None else None
        ),
        "encoders": {
            "campplus": _encoder_manifest(args.encoder),
            "encoder2": _encoder_manifest(args.encoder2) if args.encoder2 else None,
        },
        "synthesis": meta,
    }

    comparison: dict | None = None
    if baseline is not None:
        comparison = compare_with_baseline(report, baseline)
        comparison = {"baseline_path": str(baseline_path), **comparison}
        comparison["acoustics"] = acoustics_baseline_delta(report, baseline)
        report["baseline_comparison"] = comparison
        report["goodhart_flag"] = comparison["goodhart_flag"]
        if comparison["goodhart_flag"]:
            d = comparison["deltas"]
            _LOGGER.warning(
                "Goodhart 疑い: primary (campplus) Δcross %+.4f >= +%.2f に対し "
                "encoder2 Δcross %+.4f < +%.2f — SCL と同型の encoder だけが動いて"
                "おり話者類似の改善とは認めない (SECS 単独判定禁止、"
                "docs/spec/zs-eval-contract.md)",
                d["campplus"]["cross_utt_secs"],
                GOODHART_PRIMARY_DELTA,
                d["encoder2"]["cross_utt_secs"],
                GOODHART_ENCODER2_DELTA,
            )
        if comparison["gap_widened_encoders"]:
            _LOGGER.warning(
                "same/cross gap が baseline 比 +%.2f 以上拡大: %s — same-utt "
                "Goodhart 成分の膨張を示唆 (docs/spec/zs-eval-contract.md)",
                GAP_WIDENING_DELTA,
                ", ".join(comparison["gap_widened_encoders"]),
            )

    _print_report(report, args.synth_dir, args.speaker_utts)
    if comparison is not None:
        _print_baseline_comparison(comparison)

    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        _LOGGER.info("wrote %s", json_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
