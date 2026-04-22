# Phase 5 実装計画: Fine-tune 実験

**実装主体**: Claude Code (AIエージェント)
**Phase 5 Claude Code 工数**: 1〜2 日 (実装・評価) + GPU 2 日 (バックグラウンド学習)
**依存**: Phase 1 完了 (style vector conditioning)、Phase 3 完了 (style bank)、Phase 4 完了 (PE-A loss、Stage 5b のみ必須)
**最終判定**: 本家統合成功/不足の Go/No-go 判断材料を生成

> **参考**: 人間エンジニア想定は 3〜5 日。Claude Code では学習実行・ログ監視・評価自動化で短縮。ただし GPU 学習時間 (2 日) はバックグラウンド処理。

---

## 5.1 感情音声データセット取得・調査

### 5.1.1 CREMA-D 詳細 (第一候補)

| 項目 | 詳細 |
|-----|------|
| 公式 | https://github.com/CheyneyComputerScience/CREMA-D |
| 言語 | 英語のみ |
| 規模 | 7,442 発話 / 91 話者 / 6 感情 |
| 感情 | angry, disgusted, fearful, happy, neutral, sad |
| ライセンス | Open Database License (ODbL) 1.0 |
| 商用可否 | ✅ **可能** |
| 入手 | `git clone https://github.com/CheyneyComputerScience/CREMA-D.git` |
| ストレージ | ~27GB 圧縮 / ~48GB 解凍 |
| DL 時間 | 2〜3 時間 (100Mbps) |
| 前処理 | 48kHz → 16kHz resampling 必要 (PE-A 入力基準) |

**使用シナリオ**: fine-tune 実験のファーストステップ。商用可・話者多・感情バランス良好。

### 5.1.2 ESD (Emotional Speech Dataset)

| 項目 | 詳細 |
|-----|------|
| 公式 | https://hltsingapore.github.io/ESD/ |
| 言語 | 英語 + 中国語 (並行) |
| 規模 | 35,000 発話 / 言語別 10 話者 / 5 感情 |
| 感情 | neutral, happy, sad, angry, surprise |
| ライセンス | **研究目的での配布のみ** |
| 商用可否 | ⚠️ **制限あり** (要原著者許可) |
| 入手 | Web フォーム登録 → メール配布 (1〜2 営業日) |
| 形式 | Mono WAV 16kHz 16bit |
| 前処理 | 不要 (既に 16kHz) |

**使用シナリオ**: 多言語対応時のみ。商用配布前に原著者許可取得が必須。

### 5.1.3 EmoV-DB

| 項目 | 詳細 |
|-----|------|
| 公式 | https://github.com/numediart/EmoV-DB |
| 言語 | 英語のみ |
| 規模 | 7,000 発話 / 4 話者 / 5 感情 |
| 感情 | neutral, amused, angry, sleepy |
| ライセンス | Creative Commons Attribution (CC-BY 4.0) |
| 商用可否 | ✅ **可能** (帰属表示必須) |
| 形式 | WAV 16bit 44.1kHz |
| 前処理 | 44.1kHz → 16kHz resampling 必要 |

**使用シナリオ**: CREMA-D の補助。話者数が少ない (4) ため多話者感情制御には向かない。

### 5.1.4 JTES (日本語感情音声)

| 項目 | 詳細 |
|-----|------|
| 配布 | 大学研究室経由 (学内限定) |
| 言語 | 日本語 |
| 規模 | 推定 20,000 発話 / 100+ 話者 / 4 感情 |
| 感情 | neutral, happy, sad, angry |
| ライセンス | 研究目的のみ |
| 商用可否 | ⚠️ 要確認 |
| 入手 | 学内申請 (1〜2 週間) |

**使用シナリオ**: つくよみちゃん日本語感情拡張時の選択肢。入手難易度が高い。

### 5.1.5 データセット比較表

| 項目 | CREMA-D | ESD | EmoV-DB | JTES |
|-----|---------|-----|---------|------|
| 言語 | EN | EN+ZH | EN | JA |
| 発話数 | 7,442 | 35,000 | 7,000 | ~20,000 |
| 話者数 | 91 | 10 | 4 | 100+ |
| 感情数 | 6 | 5 | 5 | 4 |
| 商用可 | ✅ | ⚠️ | ✅ | ⚠️ |
| 入手難易度 | ⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ |
| 推奨優先度 | 1 | 3 | 2 | 4 |

### 5.1.6 推奨選定

**Phase 5a (基本実験)**: **CREMA-D のみ**
- 商用可、話者数が多い、感情バランス良好、入手容易
- 工数: 1 日 (DL + 前処理 + manifest 作成)

**Phase 5b (PE-A loss 追加)**: 同じ CREMA-D 使用 + style bank

**Phase 5c (多言語、オプション)**: CREMA-D + ESD 英語パート

**Phase 5d (日本語拡張、オプション)**: CREMA-D + JTES (JTES 入手可能時)

---

## 5.2 データ前処理ツール設計

### 5.2.1 CREMA-D ダウンロードスクリプト

**配置**: `src/python/piper_train/tools/download_crema_d.sh`

```bash
#!/bin/bash
set -e

DATASET_ROOT="${1:-/data/piper/datasets}"
mkdir -p "$DATASET_ROOT"

echo "=== CREMA-D ダウンロード開始 ==="
cd "$DATASET_ROOT"

if [ ! -d "CREMA-D" ]; then
  git clone --depth=1 https://github.com/CheyneyComputerScience/CREMA-D.git
  echo "CREMA-D 取得完了"
else
  echo "既に存在: $DATASET_ROOT/CREMA-D"
fi

if [ -d "CREMA-D/AudioWAV" ]; then
  echo "AudioWAV フォルダ確認 OK: $(ls CREMA-D/AudioWAV/*.wav | wc -l) files"
else
  echo "WARNING: AudioWAV フォルダが見つからない"
  exit 1
fi
```

### 5.2.2 既存データセット統合ツール

[phase-3-4.md §3.3](phase-3-4.md#33-inject_style_labelspy-既存データセット拡張) の `inject_style_labels.py` を利用。

### 5.2.3 Manifest 生成スクリプト

**配置**: `src/python/piper_train/tools/prepare_emotion_finetune_dataset.py`

```python
"""
CREMA-D + 既存 6lang or つくよみちゃん を統合して fine-tune 用データセットを作成。

入力:
  --crema-d-dir: CREMA-D/AudioWAV パス
  --base-dataset-dir: 既存データセット (6lang or つくよみちゃん)
  --style-bank: build_pea_style_bank.py で生成した .npz
  --style-vectors-dir: build_pea_style_bank.py が生成した per-utterance .npy
  --output-dir: 統合データセット出力先

処理:
  1. CREMA-D WAV を prepare_multilingual_dataset.py 相当で前処理
     (audio_norm, mel spectrogram 生成)
  2. 既存データセットの manifest を統合 (speaker_id, language_id を再採番)
  3. inject_style_labels.py を呼んで style_vector_path / emotion を注入
  4. 統合 manifest.jsonl を出力
"""
```

---

## 5.3 Fine-tune シナリオ

### 5.3.1 シナリオA: CREMA-D のみ (推奨ファースト)

| 項目 | 値 |
|-----|-----|
| データ | CREMA-D 7,442 発話 (train 80% + val 20%) |
| ベース | 6lang `epoch=74-step=504712.ckpt` |
| style_vector_dim | 256 (Phase 0 で確定) |
| style_condition_mode | global |
| style_condition_dropout | 0.1 |
| 工数 | 1 日 (DL 完了後) + 24h 学習 |
| 期待 | 英語で 6 感情制御、MOS 感情表現 3.3〜3.7、感情認識精度 70〜80% |

### 5.3.2 シナリオB: CREMA-D + つくよみちゃん

| 項目 | 値 |
|-----|-----|
| データ | CREMA-D 7,442 + つくよみちゃん 100 (emotion="neutral") |
| 工数 | 1.5 日 |
| 期待 | 英語感情制御 + 日本語 neutral 品質維持 |

**事前準備**: つくよみちゃん 100 発話に `emotion="neutral"` を注入 (`inject_style_labels.py`)

### 5.3.3 シナリオC: 多言語 (オプション)

| 項目 | 値 |
|-----|-----|
| データ | CREMA-D + ESD 英語 + JTES (入手可能時) |
| 規模 | ~22,000 発話 |
| 工数 | 2〜3 日 (ESD 取得含む) |
| 期待 | 多言語で感情制御 (ただし fine-tune の限界あり、ベース再学習推奨) |

### 5.3.4 推奨: 段階的 A → B → C

1. **Day 1-2**: シナリオA (24h GPU 学習 + 評価)
2. **Day 3-4**: 結果が有望ならシナリオB
3. **Day 5 以降**: 多言語対応必要ならシナリオC

---

## 5.4 Fine-tune コマンド詳細

### 5.4.1 Stage 5a: Style vector conditioning のみ (PE-A loss なし)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
export WANDB_PROJECT="piper-plus-emotion-finetune" && \
export WANDB_NOTES="Phase 5a: Style conditioning only, CREMA-D, 200 epochs" && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-emotion-finetune \
  --prosody-dim 16 \
  --style-vector-dim 256 \
  --style-condition-mode global \
  --style-condition-dropout 0.1 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 200 --batch-size 4 --samples-per-speaker 2 \
  --checkpoint-epochs 20 --quality medium \
  --base_lr 2e-5 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm --freeze-dp \
  --val-every-n-epochs 20 \
  --audio-log-epochs 20 \
  --load_weights_from_checkpoint \
    /data/piper/output-multilingual-6lang/lightning_logs/version_0/checkpoints/epoch=74-step=504712.ckpt \
  --default_root_dir /data/piper/output-emotion-fine-tune-v1 \
  > /data/piper/training_emotion_v1.log 2>&1 &
```

**パラメータ根拠**:
- `--style-vector-dim 256`: PE-A embedding 次元と整合
- `--style-condition-mode global`: text mode より安定
- `--style-condition-dropout 0.1`: regularization、style なし生成も学習
- `--base_lr 2e-5`: ベース学習の 1/10 (catastrophic forgetting 防止)
- `--freeze-dp`: duration predictor 凍結 (既存話長保持)
- `--ema-decay 0.9995`: 既存との整合
- `--no-wavlm`: 計算簡略化

**想定学習時間**: V100 1GPU で 20〜24h (200 epoch)

**早期停止**: validation loss が 50 epoch 連続で改善しないか、良好なチェックポイントが 3 つ以上溜まった時点で手動停止。

### 5.4.2 Stage 5b: PE-A loss 追加

**前提**: Phase 4 完了、`style_bank_crema_d.npz` 生成済み。

```bash
export WANDB_NOTES="Phase 5b: Style + PE-A loss, warmup 2k steps" && \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-emotion-finetune \
  --prosody-dim 16 \
  --style-vector-dim 256 \
  --style-condition-mode global \
  --style-condition-dropout 0.1 \
  --pea-emotion-style-bank /data/piper/style_bank_crema_d.npz \
  --pea-emotion-loss-weight 0.1 \
  --pea-emotion-centroid-weight 0.1 \
  --pea-emotion-margin-weight 0.05 \
  --pea-emotion-loss-every-n-steps 4 \
  --pea-emotion-warmup-steps 2000 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 200 --batch-size 4 --samples-per-speaker 2 \
  --checkpoint-epochs 20 --quality medium \
  --base_lr 2e-5 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --no-wavlm --freeze-dp \
  --val-every-n-epochs 20 \
  --audio-log-epochs 20 \
  --load_weights_from_checkpoint \
    /data/piper/output-emotion-fine-tune-v1/lightning_logs/version_X/checkpoints/best.ckpt \
  --default_root_dir /data/piper/output-emotion-fine-tune-v2 \
  > /data/piper/training_emotion_v2.log 2>&1 &
```

**PE-A パラメータ根拠**:
- `--pea-emotion-loss-weight 0.1`: 全 loss に対する PE-A 寄与を 10% に制御
- `--pea-emotion-centroid-weight 0.1`: セントロイド引き寄せ 10%
- `--pea-emotion-margin-weight 0.05`: マージン loss 5% (弱め)
- `--pea-emotion-loss-every-n-steps 4`: 4 step ごと計算 (計算コスト削減)
- `--pea-emotion-warmup-steps 2000`: 最初 2000 step は PE-A loss 無視 (early instability 防止)

**想定学習時間**: 20〜24h (PE-A overhead ~10%)

### 5.4.3 Stage 5c: 多言語拡張 (オプション)

Stage 5b のコマンド + データ追加:

```bash
--dataset-dir /data/piper/dataset-emotion-finetune-multilingual \
--pea-emotion-style-bank /data/piper/style_bank_crema_d_esd.npz
```

---

## 5.5 評価プロトコル

### 5.5.1 定量評価

#### (1) 感情認識精度 (自動評価)

```python
from transformers import pipeline
emotion_classifier = pipeline(
    "audio-classification",
    model="superb/hubert-large-superb-er",  # or speech-emotion-recognition-english
    device=0
)

# 評価セット: CREMA-D validation split 30 発話 × 6 感情
# 各発話を fine-tune モデルで合成
# emotion_classifier で分類 → 正解率計算
```

**目標値**: 70% 以上

#### (2) MOS 自然性

- 評価者: 10〜20 名 (英語ネイティブ推奨)
- サンプル: 30 発話 (感情 × 話者バランス)
- 評価基準: 5 点尺度 (1=不自然, 5=非常に自然)
- 対比: ベース 6lang モデル同テキスト

**目標値**: 3.8 以上 (ベース比 -0.2 以下)

#### (3) MOS 感情表現

- 同じ評価者 × 30 発話 × 「意図した感情がどの程度伝わるか」

**目標値**: 3.5 以上

#### (4) 言語別評価

- 英語: CREMA-D validation 15 発話
- 日本語 (シナリオB 時): つくよみちゃん 10 発話
- 中/仏/西/葡: ベース 6lang サンプル 5 発話ずつ (品質維持確認)

### 5.5.2 定性評価

#### (1) Style vector 補間

```python
# 2 感情セントロイド間を線形補間
emotion_happy_vec = np.load("style_vectors/happy_centroid.npy")
emotion_sad_vec = np.load("style_vectors/sad_centroid.npy")

for alpha in np.linspace(0.0, 1.0, 5):
    blended_vec = alpha * emotion_happy_vec + (1 - alpha) * emotion_sad_vec
    # 合成して listening test
```

#### (2) Style dropout 効果

```python
# 同じテキストで style on/off 比較
model.inference(text, style_vector=happy_vector)   # with style
model.inference(text, style_vector=None)           # without style
```

#### (3) ベースモデル比較

同テキストを 3 モデルで合成:
- ベース 6lang (style 前)
- fine-tune v1 (style only)
- fine-tune v2 (style + PE-A loss)

Blind test で評価者が由来推定不可能状態で比較。

### 5.5.3 リスナーテスト設計

**配布方法**: Google Forms (無料)、またはクラウドサービス (CrowdWorks 等)

**質問例**:

```
質問1: この音声はどの程度自然に聞こえますか? (1=不自然, 5=非常に自然)
  音声: [URL]

質問2: この音声の感情 (happy/sad/angry/...) はどの程度伝わりますか? (1=全く, 5=非常に)
  ラベル: [intended emotion]
  音声: [URL]

質問3: どちらの音声の方が自然に感じますか? (A/B 比較、blind)
  A: [モデル1]
  B: [モデル2]
```

**サンプル数**: 30 テキスト × 6 感情 = 180 サンプル、評価者 10 名なら 1 人 18 サンプル

### 5.5.4 評価ツール

`src/python/piper_train/tools/evaluate_emotion_model.py` を新規作成:

```
機能:
  1. 感情認識精度の自動評価 (hubert-er 等)
  2. CSV レポート生成 (感情 × 言語 × モデルで)
  3. Google Forms 生成用 CSV エクスポート
```

---

## 5.6 つくよみちゃん感情拡張シナリオ

### 5.6.1 方法別比較

現状: つくよみちゃん 100 発話 (neutral のみ、1 話者)。

| 方法 | コスト | メリット | デメリット | 実現性 |
|------|--------|---------|----------|--------|
| **方法1**: fine-tune 継承 | 0 (既存のみ) | 追加データ不要。声質一貫 | 日本語感情データなし、汎化依存 | ★★★ |
| **方法2**: 感情音声収録 | 高 (3〜5 日 + 声優) | 自然度最高 | 新規 250〜500 発話必要 | ★★ |
| **方法3**: 合成データ | 中 (1 日) | 追加収録不要 | 音質低、過学習リスク | ★ |

### 5.6.2 推奨プラン

**Stage 1**: 方法1 で fine-tune (シナリオB と同一)
- つくよみちゃんを emotion="neutral" として manifest 追加
- CREMA-D 学習した style_proj を継承
- 推論時に happy/sad/angry を style_vector で指定

**評価**:
- 「happy つくよみちゃん」「sad つくよみちゃん」等を試合成
- MOS 評価で自然性・感情表現を測定

**Stage 2** (Stage 1 結果不足時):
- 方法2 検討 (声優再録依頼、50〜100 発話 × 5 感情)
- 費用・スケジュール次第

---

## 5.7 成功基準

### 5.7.1 最低基準 (Go/No-go)

以下をすべて満たせば **本家統合成功**:

- 英語感情認識精度: **65% 以上**
- MOS 自然性: **3.8 以上** (ベース比 -0.2 以下)
- 学習収束、validation loss 安定
- style_vector_dim=0 でのレグレッションなし

### 5.7.2 目標

実用的品質:

- 英語感情認識精度: **75% 以上**
- MOS 自然性: **4.0 以上** (ベース同等)
- MOS 感情表現: **3.5 以上**
- 日本語 (シナリオB 時) の声質維持

### 5.7.3 ストレッチ

理想:

- 多言語感情認識精度: 60% 以上 (英語以外)
- MOS 感情表現: 4.0 以上
- Style vector 補間で中間感情が自然に出る
- 他話者 (つくよみちゃん等) でも感情制御動作

---

## 5.8 工数内訳

| タスク | Claude Code 実装 | GPU/外部 | 人間エンジニア (参考) |
|-------|---------------|---------|-----------------|
| CREMA-D DL + 前処理 + manifest | 1〜2h | DL 待機 2〜3h | 1 日 |
| Stage 5a 学習 (200ep) | 1h (起動・監視) | GPU 20〜24h | 2 日 |
| Stage 5a 評価 | 2〜4h | - | 2 日 |
| Stage 5b 学習 (Phase 4 完了後) | 1h (起動・監視) | GPU 20〜24h | 1 日 |
| Stage 5b 評価 | 2〜4h | - | 0.5 日 |
| 評価ツール (MOS スクリプト、自動評価) | 2〜4h | - | 2 日 |
| リスナーテスト配布・集計 (ユーザー作業) | - | 1〜2 週間 (評価者確保) | - |
| ドキュメント (実験報告、fine-tune ガイド) | 1〜2h | - | 1 日 |
| **Claude Code 合計** | **約 1〜2 日 (8〜16h)** | GPU 40〜48h (2日) | 5〜7 日 |

**並列**: GPU 学習中 (~24h) に Claude Code は評価ツール準備、Phase 別ドキュメント更新等を並行。
**ユーザー作業**: リスナーテスト (MOS 評価) は評価者への依頼・集計が必要なため別途 1〜2 週間。

---

## 5.9 リスクと対策

| リスク | 対策 |
|-------|------|
| CREMA-D DL 長時間 (27GB) | 事前 DL、他作業と並行 |
| fine-tune catastrophic forgetting | `--base_lr 2e-5` + `--freeze-dp` + EMA |
| validation loss 振動 | batch-size 削減 or LR schedule 調整 |
| PE-A loss 不安定 | warmup 延長、weight 調整 |
| MOS 評価者確保困難 | 内部評価者 + クラウドサービス併用 |
| 日本語感情表現の弱さ | JTES 追加 or 方法2 (新規収録) 検討 |
| つくよみちゃん品質劣化 | `--freeze-dp` + 低 LR + ベース比較テスト必須 |

---

## 5.10 Phase 5 完了後の判定フロー

```
Stage 5a 完了
     ↓
評価 (感情認識精度 + MOS 自然性)
     ↓
  合格 (最低基準クリア)?
    ├── Yes ──→ Stage 5b (PE-A loss 追加)
    │               ↓
    │            評価
    │               ↓
    │         目標値クリア?
    │            ├── Yes ──→ 本家統合完了、モデル配布
    │            └── No  ──→ データ補強 (Stage 5c) or 調整実験
    │
    └── No ──→ 原因分析
                   ├── データ不足 → シナリオB/C 検討
                   ├── catastrophic forgetting → LR/freeze 調整
                   └── 根本問題 → ベース再学習に格上げ
```

---

## 参考

- Phase 0-1 計画: [phase-0-1.md](phase-0-1.md)
- Phase 2 計画: [phase-2.md](phase-2.md)
- Phase 3-4 計画: [phase-3-4.md](phase-3-4.md)
- 全体調査: `../peav-style-conditioning.md` (特に §15, §16)
- CREMA-D: https://github.com/CheyneyComputerScience/CREMA-D
- ESD: https://hltsingapore.github.io/ESD/
- 感情認識モデル例: https://huggingface.co/superb/hubert-large-superb-er
