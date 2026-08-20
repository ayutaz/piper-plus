#!/usr/bin/env python3
"""zero-shot 再発防止テスト / 評価ガードの存在 gate。

2026-08 の zero-shot 話者類似度事故 (same-utt SECS Goodhart 0.775 誤報 +
posterior leak、docs/design/zero-shot-warm-restart-diagnostics-phase0-1.md) の
再発防止は「事故そのものを再現攻撃するテスト」と「評価ツールの Goodhart
検知面」に固定されている。本 gate はそれらが**黙って削除・改名・弱体化**
されるのを commit 時点で検出する (test-threshold-relaxation gate と同思想)。

防止テストを意図的に廃止/改名する場合は、本スクリプトの EXPECTED を
同一 commit で更新し、commit message に根拠を書くこと。
"""

from __future__ import annotations

import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent

# ファイル → 存在必須のシンボル (防止テスト名 / ガード面) と、その防止対象
EXPECTED: dict[str, dict[str, str]] = {
    "src/python/tests/test_scl_differentiable.py": {
        "def test_diagonal_is_neutral_not_negative": (
            "SupCon cross_utt の対角 neutral (same-utt Goodhart の footgun 固定)"
        ),
        "def test_matches_bruteforce_supcon_reference": (
            "SupCon L_out 形式の第一原理一致 (損失再配線の silent 破壊検出)"
        ),
        "def test_gradient_reaches_spk_proj_and_dec_but_not_enc_q": (
            "B-3 z detach の勾配隔離 (posterior leak 再発検出)"
        ),
    },
    "src/python/tests/test_v10_structure.py": {
        "def test_default_dur_loss_isolated_from_speaker_path": (
            "M3 default の DP 勾配遮断 pin (detach 復活の silent 退行検出)"
        ),
        "def test_snac_layer_invertible": "M1 SNAC flow の可逆性",
        "def test_snac_block_logdet_matches_autograd_slogdet": (
            "M1 logdet の第一原理一致 (KL silent 破損の根本検出)"
        ),
        "def test_lightning_wires_flow_logdet_into_kl_loss": (
            "M1 logdet→KL 配線の mutation 検出 (配線を外すと必ず落ちる)"
        ),
    },
    "src/python/tests/test_v10_speaker_signal.py": {
        "def test_gradients_reach_flow_dec_spk_proj_but_not_enc_q": (
            "S1 swap-SCL の勾配経路 (推論経路への話者監督 + enc_q 遮断)"
        ),
        "def test_speaker_ids_exclude_same_speaker_pairs": (
            "swap 相手の同一話者退化防止 (Goodhart 耐性の要)"
        ),
        "def test_interpolation_branch_preserves_unit_norm": (
            "Latent Filling 補間の L2 正規化 (norm 崩れ = DINO NaN 事故と同型)"
        ),
        "def test_no_latch_under_optimizer_step_accounting": (
            "LF × d_update_interval の no-op ラッチ防止"
        ),
    },
    "src/python/piper_train/tools/eval_zs_secs.py": {
        "goodhart_flag": "評価ツールの Goodhart 自動判定 (Arm B 型偽改善の検出)",
        "require-encoder2": "第 2 encoder 必須 gate (CAM++ 単独判定の禁止)",
        "gap_same_minus_cross": "same/cross gap の常時出力 (Goodhart 成分の観測)",
        "cross_utt_secs": "cross-utterance SECS (same-utt 単独判定の禁止)",
        "above_ceiling": "録音特性複製シグナルの独立 flag (E-7(iii))",
        "manifest": "eval 入力の sha256 pin (E-5(i)、事前登録判定の固定)",
        "comb_hnr": "A3 (1-3kHz 調波間ノイズ) 直接測定ブロックの v3 統合",
    },
    "docs/spec/zs-eval-contract.md": {
        "goodhart_flag": "評価契約に Goodhart 判定の定義があること",
        "same-utt": "same-utt 単独判定の禁止条項",
        "恒久禁止": "評価メトリクスの学習流用の恒久禁止 (§2 禁止事項 4)",
        "above_ceiling_flag": "録音特性複製 flag の契約定義 (§3)",
    },
    # --- Phase A (v10b plan §2 E-1〜E-8): 音響メトリクスの三重固定 ---
    "src/python/piper_train/tools/measure_comb_artifacts.py": {
        "def comb_metrics": (
            "SR/128 格子コム超過 + >4kHz autocorr (がびがびコムのゲーム不能量)"
        ),
        "EVAL-ONLY": "評価専用マーカー (学習 loss 流用禁止の 1 層目)",
    },
    "src/python/piper_train/tools/measure_prosody.py": {
        "def prosody_stats": "韻律平板さの数値化 (F0 std/レンジ/話速)",
        "def prosody_delta": "参照 vs 合成の記述統計差 (類似スコア化の禁止と対)",
        "EVAL-ONLY": "評価専用マーカー",
    },
    "src/python/piper_train/tools/measure_band_noise.py": {
        "def voiced_high_band_excess": "v9 がびがび指標の互換維持 (歴史的 TSV との A/B)",
        "def band_profile": "1kHz 帯域ベクトル + 5.5-8.5kHz 照準値 (希釈の防止)",
        "EVAL-ONLY": "評価専用マーカー",
    },
    # --- v11 評価系 (Phase A レーン 2): comb-HNR (A3 直接測定) + seen-ID 診断 ---
    "src/python/piper_train/tools/measure_comb_hnr.py": {
        "def comb_hnr": (
            "comb-HNR@1-3kHz — A3 調波間ノイズの直接測定 "
            "(v10b 残存ノイズ診断 §1/§8 のアンカーと同一数値系)"
        ),
        "出力自身の F0": (
            "測定プロトコル: 出力自身の F0 トラックで測る "
            "(GT/予測格子は ±20cent で崩壊 — v11 head 設計 §5.3 deviation 4)"
        ),
        "def detect_octave_down": (
            "サブハーモニック挿入 (oct↓ エラー) の検出 (f0 比主根拠)"
        ),
        "EVAL-ONLY": "評価専用マーカー (学習 loss 流用禁止の 1 層目)",
    },
    "src/python/piper_train/tools/eval_seen_speaker_id.py": {
        "def identification_report": (
            "raw + centered top-1 の分離 (ドメイン差 vs 話者同一性の切り分け、"
            "v11 conditioning 設計 §6 の oracle プロトコル製品化)"
        ),
        "診断専用": (
            "go/no-go 不使用の明記 — 本指標の gate 化は Goodhart 面 "
            "(学習 loss 流用は frozen encoder gaming 事例 4 件により恒久禁止)"
        ),
        "EVAL-ONLY": "評価専用マーカー",
    },
    "src/python/tests/test_measure_comb_hnr.py": {
        "def test_self_track_invariant_under_f0_cent_error": (
            "±20cent 罠の再発防止 (自 F0 トラック測定プロトコルの機械 pin)"
        ),
        "def test_white_noise_near_zero_db": "ゼロ点校正 (dB スケールの絶対保証)",
        "def test_harmonic_signal_first_principles": (
            "ノイズパワー ×10 → -10dB の第一原理一致"
        ),
    },
    "scripts/check_zs_metric_isolation.py": {
        "piper_train.vits": "学習コードからのメトリクス import 隔離 gate 本体",
    },
    "src/python/tests/test_measure_comb_artifacts.py": {
        "def test_off_grid_tones_do_not_trip": "格子選択性 (F0 倍音での偽陽性防止)",
        "def test_white_noise_excess_near_zero": "ゼロ点校正 (dB スケールの絶対保証)",
        "def test_frame_tiled_noise_high_autocorr": (
            "フレーム格子アーティファクトの検出能力"
        ),
    },
    "src/python/tests/test_measure_prosody.py": {
        "def test_vibrato_f0_std_matches_first_principles": "F0 std の第一原理一致",
        "def test_flat_f0_near_zero_std": "平板韻律の検出 (ゼロ点)",
    },
    # --- Phase B S-1b (v10b plan §2.2 / §3.2): 話者監督の共進化条件 ---
    # 「識別器/分類器が生成分布上でも更新される場合のみ可」は恒久制約であり、
    # 実音声のみで学習する形式 (frozen encoder と同型の gaming 面) への退行を
    # 機械的に block する。v10a §10 の崩壊機構の再発防止面。
    "src/python/piper_train/vits/losses.py": {
        "def adv_speaker_classifier_loss_d": (
            "adversarial speaker classifier の D 側 loss (real + **fake** 両項)"
        ),
        "fake_target": (
            "fake 入力に「生成」クラスを与える敵対項 — これを外すと "
            "real-only 形式 (plan §2.2 の禁止形) に退行する"
        ),
    },
    "src/python/tests/test_adv_spk_classifier.py": {
        "def test_fake_term_produces_nonzero_gradient_on_classifier": (
            "fake 入力に対する C の勾配が非ゼロ (共進化条件の本体)"
        ),
        "def test_loss_d_includes_the_fake_term": (
            "D 側 loss ≠ real のみ CE (real-only 退行の mutation 検出)"
        ),
        "def test_classifier_trains_before_the_generator_term_ramps_in": (
            "C は step 0 から学習 / G 側のみ ramp (未学習 C を騙させない)"
        ),
    },
    # --- v11 柱 2 (A2'): trainable PQMF synthesis の CLI 封印 ---
    # v10b ep79 で GAN が制約なし合成フィルタを canonical から 42% ドリフト
    # させ band3 +6.9dB の高域ノイズ床を作った (gaming 4 例目、残存ノイズ診断
    # doc §3)。PR 正則化の実装まで CLI で封印 — 封印の解除は本 EXPECTED の
    # 更新 + commit message での根拠明記を要する。
    "src/python/piper_train/__main__.py": {
        "_TRAINABLE_PQMF_SEAL_MSG": (
            "--trainable-pqmf-synthesis の封印メッセージ本体 (argparse 段階の "
            "fail-fast。黙った封印解除の検出)"
        ),
    },
    "src/python/tests/test_v10b_decoder_cli.py": {
        "def test_trainable_pqmf_synthesis_cli_is_sealed": (
            "trainable PQMF synthesis の CLI 拒否テスト (gaming 4 例目の再発"
            "防止 — 残存ノイズ診断 doc §3、PR 正則化実装までの封印)"
        ),
    },
    "src/python/tests/test_jcu_mrd.py": {
        "def test_shuffled_condition_raises_conditional_loss_after_training": (
            "JCU 条件分岐が話者ペアの整合性を実際に判別する構造検証"
        ),
        "def test_body_is_shared_not_duplicated": (
            "無条件/条件分岐の body 共有 (GANSpeech 形式) のパラメータ検算"
        ),
    },
    ".claude/hooks/guard-bash.sh": {
        "eval_zs_secs": ("SECS 評価の --encoder2 なし実行を block する hook guard"),
    },
}


def main() -> int:
    errors: list[str] = []
    for rel_path, symbols in EXPECTED.items():
        path = REPO / rel_path
        if not path.exists():
            errors.append(
                f"{rel_path}: ファイルが存在しない — zero-shot 再発防止面が"
                f"丸ごと消えている ({len(symbols)} 個のガードを含む)"
            )
            continue
        text = path.read_text(encoding="utf-8")
        for symbol, purpose in symbols.items():
            if symbol not in text:
                errors.append(f"{rel_path}: '{symbol}' が見つからない — {purpose}")

    if errors:
        print("zs-prevention gate FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            "\n再発防止テスト/ガードの削除・改名を検出しました。意図的な変更で"
            "あれば scripts/check_zs_prevention_tests.py の EXPECTED を同一 "
            "commit で更新し、commit message に根拠を記載してください "
            "(背景: docs/design/zero-shot-warm-restart-diagnostics-phase0-1.md)。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
