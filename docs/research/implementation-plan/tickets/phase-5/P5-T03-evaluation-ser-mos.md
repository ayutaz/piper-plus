# P5-T03: 評価 (SER 精度、自然性 MOS、ベース比較)

| 項目 | 値 |
|------|-----|
| Phase | 5 |
| マイルストーン | [#15](https://github.com/ayutaz/piper-plus/milestone/15) |
| ステータス | 未着手 |
| 優先度 | 高 |
| Claude Code 工数 | 4〜6h (学習完了後) |
| 依存チケット | P5-T02 (Stage 5a 学習完了) |
| 後続チケット | P5-T04 (ONNX), P5-T05 (最終レポート) |
| 関連 PR | PR-G |
| 期日 | 2026-05-08 |

## 1. タスク目的とゴール

### 1.1 目的

Stage 5a 学習で得られた best ckpt (もしくは最終 epoch ckpt) を用い、phase-5.md §5.7 の成功基準を満たすかを定量評価する。評価指標は以下 3 軸:

1. **英語感情認識精度 (SER)**: Hugging Face の `superb/hubert-large-superb-er` (または `emotion2vec` / `wav2vec2-emotion`) で自動分類、CREMA-D validation split 30 発話 × 6 感情で正解率計測
2. **自然性 MOS**: PESQ / STOI / 自動 MOS (`compute_metrics.py`) でベース 6lang モデルとの比較
3. **多言語レグレッションチェック**: 6lang 他言語 (JA/ZH/ES/FR/PT) で短文合成し、ベースモデルと定性比較

成功基準 (phase-5.md §5.7.1): 英語 SER >= 65%, MOS >= 3.8 (ベース比 -0.2 以下), style_vector_dim=0 でのレグレッションなし。

失敗時のネクストアクション (phase-5.md §5.10 判定フロー) を評価レポートに明記:
- データ不足 → シナリオ B (つくよみちゃん emotion="neutral" 追加) or C (ESD 追加)
- catastrophic forgetting → LR/freeze 調整
- 根本問題 → ベース再学習 (別 Phase に格上げ)

### 1.2 ゴール (Definition of Done)

- [ ] `tools/evaluate_pea_emotion.py` (新規) が実装され、以下の 4 モードをサポート
    - [ ] `--mode ser`: 感情認識精度を自動計測
    - [ ] `--mode mos`: PESQ / STOI / 自動 MOS を計算
    - [ ] `--mode regression`: 6lang 他言語で spot check
    - [ ] `--mode all`: 上記全てを実行しレポート生成
- [ ] `docs/research/reports/phase-5-evaluation.md` (新規) に以下が記録されている
    - [ ] Stage 5a の学習サマリ (epoch 数、val_loss、学習時間)
    - [ ] SER 結果: confusion matrix 付き、6 感情別精度、総合精度
    - [ ] MOS 結果: ベースモデル vs Stage 5a モデルの対比表 (PESQ/STOI/MOS 数値)
    - [ ] 多言語 regression 結果: 6 言語 × 2 サンプル = 12 サンプルの生成成功/失敗
    - [ ] 成功基準への到達状況: ○/×/△ (全 3 基準)
    - [ ] 失敗時のネクストアクション (もし該当すれば)
- [ ] CREMA-D validation split (18 話者 × 6 感情 × 数発話 = 200 サンプル目安) で SER を計測
- [ ] 計測コマンドが `README` もしくはスクリプト内 docstring で再現可能な形で記述されている
- [ ] WandB run にも評価結果 (SER / MOS) が summary メトリクスとして書き込まれている (optional)
- [ ] 評価対象モデル: Stage 5a best ckpt (Stage 5b が走った場合は併せて比較)

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `tools/evaluate_pea_emotion.py` (新規、+300 行程度)
- `docs/research/reports/phase-5-evaluation.md` (新規)
- `tools/benchmark/models.yaml` (既存、Stage 5a モデル追加)
- `tools/benchmark/generate_samples.py` (既存、`--style-vector` 引数追加 or 呼び出しラッパー)
- `tools/benchmark/compute_metrics.py` (既存、そのまま利用)

### 2.2 実装手順

1. **CREMA-D validation split の定義**:
    - P5-T01 の dataset.jsonl から speaker ベースで 80:20 split を再現 (seed 固定)
    - validation 18 話者 (91 × 0.2) × 6 感情 × 平均 2 文 = 216 発話目安
    - `data/piper/dataset-crema-d-emotion/val_speakers.json` に話者 ID リストを保存
2. **SER 評価器準備**:
    - Hugging Face `superb/hubert-large-superb-er` を `transformers.pipeline("audio-classification", ...)` でロード
    - 事前に CREMA-D 生音声で精度ベンチマーク (目標 90%+、モデル自体の精度)
3. **合成サンプル生成**:
    - Stage 5a ckpt を ONNX 化する前に PyTorch 推論で 216 発話分を合成 (各発話の emotion に対応する `style_vector_path` の `.npy` を読み込んで注入)
    - テキストは CREMA-D 12 固定文のいずれか (話者・感情ごとに 1 文)
    - 出力 WAV を `/tmp/stage_5a_samples/<speaker>_<sentence>_<emotion>.wav` に保存
4. **SER 計測**:
    - 合成 WAV を SER classifier に投入、予測 emotion と期待 emotion の一致率計算
    - confusion matrix を pandas DataFrame で生成
    - per-emotion accuracy, overall accuracy を計算
5. **MOS 計測**:
    - 同じ 216 発話の `ground-truth WAV` (CREMA-D 原音) をペア参照として PESQ / STOI 計算
    - `tools/benchmark/compute_metrics.py` を流用
    - 自動 MOS (例: `NISQA` モデル) を optional で追加
6. **多言語 regression**:
    - 6 言語 × 2 sample (短文) = 12 サンプルを Stage 5a ckpt で合成
    - ベース 6lang 75epoch モデルでも同じテキストを合成
    - 音声長・明瞭度 (MEL spectrogram 可視化) を比較
    - 定性評価は `docs/research/reports/phase-5-evaluation.md` に記述
7. **レポート生成**:
    - Markdown テンプレートに数値を差し込み、`docs/research/reports/phase-5-evaluation.md` を生成
    - confusion matrix を画像 (`matplotlib`) で保存、レポートに埋め込み
8. **成功/失敗判定**:
    - phase-5.md §5.7.1 の 4 基準をチェックリスト形式で評価
    - 失敗時は §5.10 の判定フローに従いネクストアクションを明記

### 2.3 コード例 (抜粋)

```python
# tools/evaluate_pea_emotion.py

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import pipeline

_LOGGER = logging.getLogger("evaluate_pea_emotion")

EMOTION_LABELS = ["angry", "disgusted", "fearful", "happy", "neutral", "sad"]


def evaluate_ser(
    samples_dir: Path,
    val_manifest: Path,
    classifier_name: str = "superb/hubert-large-superb-er",
    device: int = 0,
) -> dict:
    """合成 WAV に対して SER を計測."""
    classifier = pipeline(
        "audio-classification",
        model=classifier_name,
        device=device,
    )

    with open(val_manifest) as f:
        val_records = [json.loads(line) for line in f]

    y_true, y_pred = [], []
    for rec in val_records:
        wav_path = samples_dir / f"{rec['speaker']}_{rec['sentence']}_{rec['emotion']}.wav"
        if not wav_path.exists():
            _LOGGER.warning("Missing sample: %s", wav_path)
            continue
        pred = classifier(str(wav_path), top_k=1)[0]
        y_true.append(rec["emotion"])
        y_pred.append(pred["label"].lower())

    # 正解率 + confusion matrix
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    accuracy = correct / len(y_true) if y_true else 0.0

    confusion = pd.crosstab(
        pd.Series(y_true, name="true"),
        pd.Series(y_pred, name="pred"),
        normalize="index",
    )
    per_emotion_acc = {
        emo: confusion.loc[emo, emo] if emo in confusion.index and emo in confusion.columns else 0.0
        for emo in EMOTION_LABELS
    }

    return {
        "total": len(y_true),
        "correct": correct,
        "accuracy": accuracy,
        "per_emotion_accuracy": per_emotion_acc,
        "confusion_matrix": confusion.to_dict(),
    }


def evaluate_mos(
    baseline_samples: Path,
    stage_5a_samples: Path,
    reference_samples: Path,
) -> dict:
    """PESQ / STOI / 自動 MOS 比較."""
    from tools.benchmark.compute_metrics import compute_pesq, compute_stoi

    baseline_mos = []
    stage_5a_mos = []

    for ref_wav in reference_samples.glob("*.wav"):
        base_wav = baseline_samples / ref_wav.name
        s5a_wav = stage_5a_samples / ref_wav.name
        if not base_wav.exists() or not s5a_wav.exists():
            continue
        baseline_mos.append({
            "file": ref_wav.name,
            "pesq": compute_pesq(str(ref_wav), str(base_wav)),
            "stoi": compute_stoi(str(ref_wav), str(base_wav)),
        })
        stage_5a_mos.append({
            "file": ref_wav.name,
            "pesq": compute_pesq(str(ref_wav), str(s5a_wav)),
            "stoi": compute_stoi(str(ref_wav), str(s5a_wav)),
        })

    return {
        "baseline_pesq_mean": np.mean([r["pesq"] for r in baseline_mos]),
        "baseline_stoi_mean": np.mean([r["stoi"] for r in baseline_mos]),
        "stage_5a_pesq_mean": np.mean([r["pesq"] for r in stage_5a_mos]),
        "stage_5a_stoi_mean": np.mean([r["stoi"] for r in stage_5a_mos]),
    }


def generate_report(ser_result: dict, mos_result: dict, output_path: Path) -> None:
    """評価結果を Markdown レポートに書き出し."""
    ser_ok = ser_result["accuracy"] >= 0.65
    mos_ok = mos_result["stage_5a_pesq_mean"] >= 3.8 and \
             (mos_result["stage_5a_pesq_mean"] - mos_result["baseline_pesq_mean"]) >= -0.2

    with open(output_path, "w") as f:
        f.write("# Phase 5 Stage 5a 評価レポート\n\n")
        f.write(f"## SER 結果\n\n")
        f.write(f"- 総合精度: {ser_result['accuracy']*100:.2f}%\n")
        f.write(f"- 合否: {'○' if ser_ok else '×'} (基準 >= 65%)\n\n")
        f.write(f"### 感情別精度\n\n")
        for emo, acc in ser_result["per_emotion_accuracy"].items():
            f.write(f"- {emo}: {acc*100:.2f}%\n")
        f.write(f"\n## MOS 結果\n\n")
        f.write(f"- Stage 5a PESQ: {mos_result['stage_5a_pesq_mean']:.2f}\n")
        f.write(f"- Baseline PESQ: {mos_result['baseline_pesq_mean']:.2f}\n")
        f.write(f"- 合否: {'○' if mos_ok else '×'} (基準 >= 3.8, ベース比 -0.2 以下)\n\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["ser", "mos", "regression", "all"], default="all")
    parser.add_argument("--stage-5a-ckpt", type=Path, required=True)
    parser.add_argument("--baseline-ckpt", type=Path, required=True)
    parser.add_argument("--val-manifest", type=Path, required=True)
    parser.add_argument("--output-report", type=Path, required=True)
    parser.add_argument("--samples-dir", type=Path, default=Path("/tmp/stage_5a_samples"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    # ... (実装本体)
```

### 2.4 実行コマンド例

```bash
# 1. 合成サンプル生成 (Stage 5a + Baseline)
uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-emotion-fine-tune-v1/stage_5a.onnx \
  --config /data/piper/dataset-crema-d-emotion/config.json \
  --text "Don't forget a jacket." \
  --language ja-en-zh-es-fr-pt \
  --speaker-id 0 \
  --style-vector /data/piper/style_bank_crema_d/happy_centroid.npy \
  --output-dir /tmp/stage_5a_samples

# 2. 評価実行
uv run python tools/evaluate_pea_emotion.py \
  --mode all \
  --stage-5a-ckpt /data/piper/output-emotion-fine-tune-v1/lightning_logs/version_0/checkpoints/best.ckpt \
  --baseline-ckpt /data/piper/output-multilingual-6lang/lightning_logs/version_0/checkpoints/epoch=74-step=504712.ckpt \
  --val-manifest /data/piper/dataset-crema-d-emotion/val_manifest.jsonl \
  --output-report docs/research/reports/phase-5-evaluation.md
```

## 3. エージェントチーム構成

| 役割 | 人数 | 主な責務 |
|------|------|---------|
| Evaluator | 1 | `evaluate_pea_emotion.py` の実装、SER / MOS 計測ロジック |
| Sample Generator | 1 | Stage 5a + Baseline の 216 発話合成、`/tmp/stage_5a_samples/` 整理 |
| Reporter | 1 | `phase-5-evaluation.md` の Markdown 整形、confusion matrix 画像生成、判定フロー記述 |

## 4. 提供範囲 (Deliverables)

- [ ] `tools/evaluate_pea_emotion.py` (新規、CLI 実装)
- [ ] `docs/research/reports/phase-5-evaluation.md` (新規、評価レポート)
- [ ] `docs/research/reports/phase-5-confusion-matrix.png` (optional、画像)
- [ ] `/tmp/stage_5a_samples/` もしくは `/data/piper/evaluation/stage_5a/` (合成サンプル、レポート生成後は削除可)
- [ ] SER 総合精度 (数値)
- [ ] MOS 対比表 (Markdown 表)
- [ ] 成功/失敗判定 + ネクストアクション

**提供範囲外**:
- 人間評価 MOS (ユーザー判断、optional)
- Stage 5b 学習 (本評価結果で Go/No-go 判断後、P5-T02 §2.4 コマンドで起動)

## 5. テスト項目

### 5.1 Unit テスト

- 該当なし (Phase 1〜4 で既にカバー、評価ツールは調査スクリプト扱い)
- ただし `evaluate_pea_emotion.py` が以下の smoke test を通ること:
    - `--mode ser --val-manifest <dummy 5 records>` で例外なく走る
    - `--mode mos` で `compute_pesq` / `compute_stoi` が正常呼び出し

### 5.2 E2E テスト

- ONNX → 6 ランタイム → wav 出力までの通しの動作確認 (これは P5-T04 の範囲だが、評価の前提として 1 サンプル確認)
- 216 発話の合成が完了 (`/tmp/stage_5a_samples/*.wav` に 216 ファイル)
- SER 計測の出力 JSON に `accuracy`, `per_emotion_accuracy`, `confusion_matrix` が含まれる
- MOS 計測の出力 JSON に `baseline_pesq_mean`, `stage_5a_pesq_mean` が含まれる

### 5.3 人間評価 (optional、ユーザー判断)

- MOS リスナーテスト: 評価者 10〜20 名 × 30 発話 × 5 点尺度 (phase-5.md §5.5.3)
- A/B blind test: ベース 6lang vs Stage 5a で好みを比較
- Google Forms で配布、集計結果を `phase-5-evaluation.md` に追記

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **SER classifier 自体の精度**: `superb/hubert-large-superb-er` の CREMA-D 上での精度が 90% 未満だと、Stage 5a の SER が見かけ低く出る。事前に CREMA-D 生音声での精度を計測しベースラインを確立
- **Catastrophic forgetting (6lang 言語品質低下)**: 多言語 regression で 6 言語中どれかが明らかに劣化した場合、`--base_lr` 引き下げや `--freeze-dp` 強化を P5-T02 でやり直すか検討
- **CREMA-D 英語のみ → 多言語感情表現力不足**: 日本語で `style_vector=angry` を与えても感情が伝わらない可能性。定性的に 1 サンプル確認し、不足が明確ならシナリオ B を P5-T05 の提言に追記
- **GPU 2 日の学習でインフラ問題 (OOM, 電源断)**: P5-T02 で学習が途中中断している場合、本 T03 着手前に再開する必要あり
- **SER 精度が期待値 (65%+) に届かない場合のネクストアクション**: phase-5.md §5.10 判定フローに従い以下を検討
    - データ不足 → シナリオ B/C
    - catastrophic forgetting → LR/freeze 調整
    - 根本問題 → ベース再学習に格上げ
- **自動 MOS 評価の限界**: PESQ/STOI は参照音声が必要、自動 MOS (NISQA 等) は学習分布外で過小評価されがち。人間評価 (optional) を推奨
- **validation split の再現性**: seed 固定して dataset.jsonl を split、Phase 5 全体で同じ split を使うこと

### 6.2 レビュー項目

- [ ] SER classifier のロードが成功し、CREMA-D 原音で >= 85% の基準精度が出ている
- [ ] validation split が speaker ベース (train と val で話者重複なし)
- [ ] 216 発話すべてで合成成功 (欠落数 < 5%)
- [ ] confusion matrix が対角優位 (対角成分が非対角成分の 2 倍以上)
- [ ] MOS PESQ が 1.0 〜 4.5 の範囲内 (計算ミス防止)
- [ ] `phase-5-evaluation.md` に成功基準への到達 (○/×) が明示されている
- [ ] 失敗時のネクストアクションが具体的に記述されている (シナリオ B/C or ベース再学習)
- [ ] 多言語 regression の 12 サンプルすべてで生成成功 (0 秒出力や NaN なし)

## 7. 一から作り直すとしたら

### 7.1 代替案の検討

- **代替案 A: 自動 SER のみで判定 (MOS は optional)**
    - 利点: 評価工数が 1/2 に削減、自動化可能
    - 欠点: 音質劣化を見逃す、catastrophic forgetting の検知漏れ
- **代替案 B: emotion2vec ベースの SER に切り替え**
    - 利点: より最新・高精度 (CREMA-D 相当で 95%+)
    - 欠点: モデルが大きい、依存追加
- **代替案 C: A/B test (ベース vs 新) を自動化**
    - 利点: 主観評価を人間評価者なしで得られる (LLM-as-judge + 音声埋め込み類似度)
    - 欠点: LLM による音声評価は発展途上、信頼性要検証
- **代替案 D: 評価指標を 6 軸に拡張 (自然性 / 感情明瞭度 / 話者類似度 / 発話リズム / 音素明瞭度 / 多言語品質)**
    - 利点: 多面的な評価、失敗原因の切り分けが容易
    - 欠点: 工数 3 倍、期日内に実施困難

### 7.2 現在の実装を選んだ理由

- phase-5.md §5.5 の評価プロトコルに準拠、既存の `compute_metrics.py` を流用することで工数最小化
- CREMA-D 英語特化評価で Stage 5a の基本能力を検証、多言語評価は regression check として軽量に実施
- 人間評価 (MOS) は optional とし、自動評価で Go/No-go 判定を下す

### 7.3 リファクタ機会 (将来)

- `evaluate_pea_emotion.py` を `tools/benchmark/` に統合し、`compute_metrics.py` と同じ I/F で呼び出し可能にする
- confusion matrix 生成を seaborn ベースに変更、レポート埋め込み画像を自動生成
- 評価プロトコルを CI に組み込み、Stage 5a ckpt が更新されるたびに自動実行 (WandB sweep 連携)
- A/B test を GitHub Pages + audio player で公開、コミュニティからの評価を集める

## 8. 後続タスクへの連絡事項

- **P5-T04 へ**: Stage 5a best ckpt の ONNX エクスポート可否判定 (SER >= 65% なら進行、未満なら判断保留)
- **P5-T05 へ**: `phase-5-evaluation.md` の結果を最終レポート (`pea-style-conditioning-report.md`) に統合
- **Stage 5b 判断**: 本評価で Stage 5a の SER が基準クリアなら Stage 5b を P5-T02 §2.4 のコマンドで起動 (Phase 4 完了済み前提)
- **人間評価 (optional)**: MOS リスナーテスト実施時は `docs/research/reports/phase-5-mos-survey.md` に集計結果を追記する想定

## 9. 参考リンク

- `phase-5.md §5.5` 評価プロトコル
- `phase-5.md §5.7` 成功基準
- `phase-5.md §5.10` 完了後の判定フロー
- Hugging Face `superb/hubert-large-superb-er`: https://huggingface.co/superb/hubert-large-superb-er
- `emotion2vec`: https://github.com/ddlBoJack/emotion2vec
- `NISQA` (自動 MOS): https://github.com/gabrielmittag/NISQA
- 既存評価ツール: `tools/benchmark/compute_metrics.py`, `tools/benchmark/generate_samples.py`, `tools/benchmark/models.yaml`
- CLAUDE.md 「MOS ベンチマークツール」
