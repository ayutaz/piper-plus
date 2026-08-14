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
    },
    "docs/spec/zs-eval-contract.md": {
        "goodhart_flag": "評価契約に Goodhart 判定の定義があること",
        "same-utt": "same-utt 単独判定の禁止条項",
    },
    ".claude/hooks/guard-bash.sh": {
        "eval_zs_secs": (
            "SECS 評価の --encoder2 なし実行を block する hook guard"
        ),
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
