# Piper TTS - プロジェクト概要

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

---

## ✅ 現在の状態: バイリンガル (JA+EN) モデル — 200 epoch 学習完了

**ブランチ**: `feat/bilingual-phonemizer`

### バイリンガルモデル学習状況 (2026-02-14 更新)

| 項目 | 値 |
|------|-----|
| エポック | **200 / 200 ✅ 完了** (2026-02-14) |
| データセット | `dataset-bilingual-ja-en` (三重padding修正+空phoneme_ids除外+EOS不一致修正) |
| 発話数 | 73,148 (JA=60,148 + EN=13,000、空phoneme_ids 16件除外済み) |
| 話者数 | 21 (JA 20話者 + EN 1話者 LJSpeech) |
| 言語数 | 2 (ja=0, en=1) |
| シンボル数 | 97 |
| バッチサイズ | 20 (`--no-wavlm` によりメモリ余裕あり) |
| Precision | **32-true** (FP32) — V100でFP16-mixed backward異常のため |
| WavLM | **無効** (`--no-wavlm`) — コスト・速度優先で無効化 |
| 学習速度 | **0.45-0.71 it/s** (4 GPU DDP) |
| 学習期間 | 約2.7日 (02/11 08:12 → 02/14 04:55) |
| GPU | Tesla V100-PCIE-16GB × 4 |
| WandB | `yousan/piper-tts` / `dataset-bilingual-ja-en` / run `0yk7tvhb` |
| 品質 | 日本語: 良好、英語: 発音不明瞭（ENデータ18%のため。データ増強で改善可能） |

**FP32切り替えの経緯 (2026-02-11):** `--precision 16-mixed` 使用時、Generator の backward pass が29-40秒かかり全体速度が 0.03 it/s に低下する問題を発見。プロファイリングにより `self.manual_backward(loss_g)` が原因と特定。V100のFP16 mixed precision backward passに固有の性能問題があり、`--precision 32-true` に切り替えることで backward が 0.7-1.1s に改善、全体速度が **0.45 it/s** (15倍高速化) となった。FP32でもGPU peak 13.7GB/16GB で V100に収まる。

**WavLM無効化の経緯 (2026-02-11):** WavLM有効時の学習速度が極めて遅く、完了まで推定19日かかる見込みだった。WavLM無効にすることで短縮。JA-only完了モデルもWavLMなしで学習されており、同条件で品質比較可能。`--no-wavlm` フラグを新規追加し対応。

**修正内容 (2026-02-08):** データセット再生成。以下の3つの修正を適用:
1. **三重パディング修正**: `_add_inter_phoneme_padding()` が既存のワード境界パディング (ID=0) にも追加パディングを挿入し `[0,0,0]` を生成していた。`pid != pad_id` チェックで回避。88.2% (53,028/60,148) のJA utteranceに影響していた。
2. **EOS不一致修正**: 推論時の `post_process_ids()` が常に `$` (ID=2) を付加していたが、学習データの疑問文は `?` (ID=3) で終わる。`_last_eos` 追跡で修正。約15%の utteranceに影響。
3. **空phoneme_ids除外**: テキスト "…" の16件を `process_ja_dataset()` でスキップ。

### バイリンガルモデル

```
/data/piper/output-bilingual-ja-en/
├── lightning_logs/version_28/checkpoints/
│   ├── epoch=199-step=218400.ckpt  ← 最終チェックポイント
│   └── last.ckpt
└── bilingual-ja-en-200epoch.onnx  ← ONNX推論用モデル (74MB, EMA適用済み)
```

### 学習開始コマンド (0→200 epoch、WavLM無効、FP32、修正済みデータセット)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-bilingual-ja-en \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --default_root_dir /data/piper/output-bilingual-ja-en \
  > /data/piper/training_bilingual_fp32.log 2>&1 &
```

**注意:** `--precision 32-true` でFP32学習（V100ではFP16-mixedのbackwardが異常に遅いため必須）。`--no-wavlm` でWavLM Discriminatorを無効化し、batch-size 20で学習。`--max-phoneme-ids 400` で長いシーケンス (109件, 0.15%) を除外しメモリスパイクを防止。

### 推論テスト

**日本語:**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en/bilingual-ja-en-200epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en/config.json \
  --output-dir /home/jovyan \
  --text "こんにちは、今日は良い天気ですね。" \
  --language ja-en --speaker-id 0 --noise-scale 0.5
```

**英語:**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en/bilingual-ja-en-200epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en/config.json \
  --output-dir /home/jovyan \
  --text "Hello, how are you today?" \
  --language ja-en --speaker-id 20 --noise-scale 0.5
```

**混合テキスト (コードスイッチング):**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en/bilingual-ja-en-200epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en/config.json \
  --output-dir /home/jovyan \
  --text "今日はgood morningですね" \
  --language ja-en --speaker-id 0 --noise-scale 0.5
```

### 完了済みモデル (JA-only)

```
/data/piper/output-moe-speech-20speakers-v2/
├── lightning_logs/version_0/checkpoints/
│   ├── epoch=199-step=206000.ckpt
│   └── last.ckpt
└── moe-speech-20speakers-v2.onnx  ← JA-only本番用モデル (74MB)
```

---

## 実装済み機能

### バイリンガル (JA+EN) Phonemizer ✅ NEW (2026-02-02)

文内コードスイッチング対応のバイリンガル音素化。Unicode範囲で言語セグメントを自動検出し、各言語のPhonemizerに委譲。

**機能:**
- 統一phoneme_id_map (JA+EN ~110記号、ID衝突なし)
- Unicode範囲ベースの言語自動検出 (CJK→ja、Latin→en)
- 混合テキスト対応: 「今日はgood morningですね」→ JA+EN音素を正しい順序で出力
- BOS/EOS/パディングの統一処理

**実装ファイル:**
- `src/python/piper_train/phonemize/bilingual_id_map.py` — 統一phoneme_id_map生成
- `src/python/piper_train/phonemize/bilingual.py` — `BilingualPhonemizer` (言語検出+混合phonemize)
- `src/python/piper_train/phonemize/registry.py` — `ja-en` 登録
- `test/test_bilingual_phonemizer.py` — 18テスト

**推論コマンド:**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en/bilingual-ja-en-200epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en/config.json \
  --output-dir /home/jovyan \
  --text "今日はgood morningですね" \
  --language ja-en --speaker-id 0 --noise-scale 0.5
```

### バイリンガル学習パイプライン (Phase B) ✅ NEW (2026-02-02)

日英混合データセットでの学習を可能にする学習パイプライン拡張。

**機能:**
- `language_id` フィールド: Dataset/Batch/preprocessに追加 (0=ja, 1=en)
- 言語embedding: `nn.Embedding(n_languages, gin_channels)` をSynthesizerTrnに追加
- speaker embedding + language embeddingを加算して全サブモジュールに注入
- config.jsonに`num_languages`, `language_id_map`フィールド追加
- ONNX export/推論に`lid`入力対応
- preprocess.pyに`--language ja-en`バイリンガルモード追加

**変更ファイル:**
- `vits/dataset.py` — Utterance, UtteranceTensors, Batchにlanguage_id追加
- `vits/models.py` — SynthesizerTrnにn_languages, emb_lang, _get_global_conditioning追加
- `vits/lightning.py` — VitsModelにnum_languages、training loopでlanguage_ids伝播
- `export_onnx.py` — lid入力のONNXエクスポート対応
- `infer_onnx.py` — lid入力の推論対応
- `__main__.py` — config.jsonからnum_languages読み込み
- `preprocess.py` — PhonemeType.BILINGUAL + phonemize_batch_bilingual追加

**学習コマンド例 (バイリンガル):**
```bash
# 1. 前処理
uv run python -m piper_train.preprocess \
  --input-dir /path/to/bilingual_dataset \
  --output-dir /path/to/output \
  --language ja-en --sample-rate 22050 --dataset-format ljspeech

# 2. 学習
uv run python -m piper_train \
  --dataset-dir /path/to/output \
  --prosody-dim 16 --accelerator gpu --devices 4 \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 2
```

**Phase C 状況:** 200 epoch学習完了 (2026-02-14)。WavLM無効、FP32、batch-size 20。日本語品質良好、英語は発音不明瞭（ENデータ18%のため）

### Phonemizer ABC + 言語レジストリ ✅ NEW (2026-02-01)

`Phonemizer` 抽象基底クラスと言語レジストリにより、if/elif分岐を解消。新言語追加が容易に。

**新言語追加手順:**
1. `Phonemizer` を継承したクラスを作成 (`phonemize`, `phonemize_with_prosody`, `get_phoneme_id_map` を実装)
2. 必要に応じて `post_process_ids` をオーバーライド (BOS/EOS等)
3. `registry.py` の `_auto_register()` に登録

**実装ファイル:**
- `src/python/piper_train/phonemize/base.py` — `Phonemizer` ABC, 共通 `ProsodyInfo`
- `src/python/piper_train/phonemize/registry.py` — 言語レジストリ
- `src/python/piper_train/phonemize/japanese.py` — `JapanesePhonemizer`
- `src/python/piper_train/phonemize/english.py` — `EnglishPhonemizer`
- `test/test_phonemizer_registry.py` — レジストリ・ABCテスト

**変更点:**
- `ProsodyInfo` を `base.py` に統一 (日本語/英語共通)
- `EnglishProsodyInfo` は `ProsodyInfo` のエイリアス (後方互換)
- `infer_onnx.py` の言語分岐をレジストリ経由に変更
- BOS/EOS/パディング処理を `EnglishPhonemizer.post_process_ids()` に移動

### GPL-free 英語G2P (g2p-en) ✅ NEW (2026-01-31)

g2p-en (Apache-2.0) を使用したespeak-ng互換の英語音素化。espeak-ng/piper-phonemize (GPL) なしで英語推論が可能。

**espeak-ng互換の処理:**
- ストレスマーカー (`ˈ`/`ˌ`) を母音の前に挿入
- 単語間スペース挿入、句読点は前の単語に付着
- 機能語 (are, you, the等) のストレス除去
- AA+R → ɑːɹ、ER0 → ɚ、ER1 → ɜː の文脈依存変換
- BOS (`^`) / EOS (`$`) + phoneme間パディング (`_`=ID 0)

**実装ファイル:**
- `src/python/piper_train/phonemize/english.py` — G2P変換
- `src/python/piper_train/infer_onnx.py` — BOS/EOS・パディング挿入
- `test/test_english_phonemizer.py` — 42テスト

**推論コマンド:**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/en_model.onnx \
  --config /path/to/en_model.onnx.json \
  --output-dir /path/to/output \
  --text "Hello, how are you today?" \
  --language en
```

**espeak-ngとの完全一致:**
hello, the cat, car, information, bird（検証済み）

**既知の差異（G2Pエンジン由来）:**
- 疑問詞 (how) のストレス種類: g2p-en=ˈ vs espeak-ng=ˌ
- フラッピング: g2p-en=t vs espeak-ng=ɾ (letter等)
- 縮約形: g2p-en=分離 vs espeak-ng=結合 (I am等)

### WavLM Discriminator ✅ NEW (2026-01-08)

Microsoft WavLMベースの知覚品質判別器。デフォルトで有効だが、`--no-wavlm` で無効化可能。

**期待効果:**
- MOS向上: +0.15-0.25
- 推論速度への影響: なし（学習時のみ使用）

**CLIオプション:**
- `--no-wavlm` — WavLM Discriminatorを無効化（学習速度向上、バッチサイズ増加可能）
- `--wavlm-every-n-steps N` — WavLM lossをNステップごとに計算（デフォルト: 1）
- `--c-wavlm` — WavLM loss重み（デフォルト: 0.5）

**実装ファイル:**
- `src/python/piper_train/vits/models.py` - `WavLMDiscriminator`クラス
- `src/python/piper_train/vits/lightning.py` - 学習ループ統合
- `src/python/piper_train/__main__.py` - `--no-wavlm` フラグ

**注意:**
- WavLMは学習時のみ使用（推論グラフには含まれない）
- FP16 Mixed Precision対応済み（内部でfloat32変換）
- GPUメモリ追加: 約1-2GB/GPU
- DDP + `find_unused_parameters=True` 環境では `--wavlm-every-n-steps N` (N>1) にすると未使用パラメータ同期のオーバーヘッドで逆に遅くなる（~3x低下確認済み）。マルチGPUでは N=1 を推奨

### テキスト直接入力推論 ✅ NEW (2026-01-08)

`infer_onnx.py`に`--text`オプション追加。JSONLなしで日本語テキストから直接音声生成。

**使用方法:**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/model.onnx \
  --config /path/to/config.json \
  --output-dir /path/to/output \
  --text "こんにちは" \
  --speaker-id 0
```

**追加引数:**
| 引数 | 説明 |
|------|------|
| `--text` | 日本語テキスト入力 |
| `--config` | config.jsonパス（phoneme_id_map必須） |
| `--speaker-id` | 話者ID（デフォルト: 0） |

### Issue #204: 疑問詞マーカーの拡張 ✅

日本語の疑問文の種類を区別するための新しいマーカーを追加。

| マーカー | Unicode | 用途 | 例 |
|----------|---------|------|-----|
| `?!` | 0xE016 | 強調疑問 | 本当?! 本当！？ |
| `?.` | 0xE017 | 平叙疑問 | そうなの?. |
| `?~` | 0xE018 | 確認疑問 | 行くよね?~ |

**実装ファイル:**
- `src/python/piper_train/phonemize/japanese.py` - `_get_question_type()` 関数

### Issue #207: 文脈依存「ん」(N) バリアント ✅ NEW

「ん」の発音が後続音によって変わることを反映。

| バリアント | Unicode | 条件 | 例 |
|-----------|---------|------|-----|
| `N_m` | 0xE019 | m/b/p の前（両唇音同化）| さんぽ |
| `N_n` | 0xE01A | n/t/d/ts/ch の前（歯茎音同化）| あんない |
| `N_ng` | 0xE01B | k/g の前（軟口蓋音同化）| ぎんこう |
| `N_uvular` | 0xE01C | 語末/母音の前（口蓋垂音）| ほん |

**実装ファイル:**
- `src/python/piper_train/phonemize/japanese.py` - `_apply_n_phoneme_rules()` 関数
- `src/python/piper_train/phonemize/jp_id_map.py` - 新トークン定義
- `src/python/piper_train/phonemize/token_mapper.py` - PUAマッピング

**音素変換例:**
```
さんぽ → s a N_m p o     (N → N_m: pの前)
あんない → a N_n n a i   (N → N_n: nの前)
ぎんこう → g i N_ng k o o (N → N_ng: kの前)
ほん → h o N_uvular      (N → N_uvular: 語末)
```

**期待効果:**
- MOS向上: +0.04-0.08
- 推論速度への影響: なし（前処理のみ）

### prosody_features (A1/A2/A3) モデル統合 ✅

OpenJTalkから抽出されるA1/A2/A3値をDuration Predictorの入力として活用。

**A1/A2/A3の意味:**

| フィールド | 意味 | 値の例 |
|-----------|------|--------|
| A1 | アクセント核からの相対位置 | -4, -3, ..., 0, 1, ... |
| A2 | アクセント句内のモーラ位置 | 1, 2, 3, ... |
| A3 | アクセント句内の総モーラ数 | 1-10+ |

**使用方法:**
```bash
# 学習時
uv run python -m piper_train --prosody-dim 16 ...

# 前処理時（prosody_features 付きデータセット作成）
uv run python /data/piper/add_prosody_features.py --input-dataset ... --output-dir ...
```

**デフォルト有効:** prosodyはデフォルトで有効（`--prosody-dim 16`）

### SpeakerBalancedBatchSampler ✅

マルチスピーカーモデルのDuration Predictor崩壊問題を解決するカスタムバッチサンプラー。

```bash
--batch-size 32 --samples-per-speaker 4  # 8話者 × 4サンプル = 32
```

### FP16 Mixed Precision ✅ (⚠️ V100非推奨)

`--precision 16-mixed` で有効化。**ただしV100ではGenerator backward passが29-40秒に低下する致命的な性能問題があるため、V100では `--precision 32-true` を使用すること。** A100/L4等の新しいGPUでは正常に動作する可能性がある。

---

## 学習設定

### 推奨設定 (20話者、L4 GPU 16GB × 4、WavLM無効)

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers-v2 \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --no-wavlm \
  --default_root_dir /data/piper/output-moe-speech-20speakers-v2
```

**注意:** WavLMはデフォルトで有効。`--no-wavlm` で無効化するとbatch-size 20が使用可能に。WavLM有効時はL4 16GBでbatch-size 20でOOM発生するため batch-size 12 が必要。

### 話者数別の推奨設定

| 話者数 | batch_size | samples_per_speaker | 実効バッチ | 備考 |
|-------|------------|---------------------|-----------|------|
| 5話者 | 20 | 4 | 20 | ✅ 検証済み (WavLMなし) |
| **20話者** | **20** | **2** | **40** | **✅ WavLM無効時 (`--no-wavlm`)** |
| 20話者 | 12 | 2 | 24 | WavLM有効時 (L4 16GB OOM対策) |

### NCCL環境変数（マルチGPU必須）

```bash
NCCL_DEBUG=WARN
NCCL_P2P_DISABLE=1
NCCL_IB_DISABLE=1
```

---

## 重要なファイルパス

### ソースコード

| 用途 | パス |
|------|------|
| 学習スクリプト | `src/python/piper_train/__main__.py` |
| VITS実装 | `src/python/piper_train/vits/` |
| Phonemizer ABC | `src/python/piper_train/phonemize/base.py` |
| 言語レジストリ | `src/python/piper_train/phonemize/registry.py` |
| 英語音素化 | `src/python/piper_train/phonemize/english.py` |
| 日本語音素化 | `src/python/piper_train/phonemize/japanese.py` |
| IDマップ | `src/python/piper_train/phonemize/jp_id_map.py` |
| トークンマッパー | `src/python/piper_train/phonemize/token_mapper.py` |
| ONNXエクスポート | `src/python/piper_train/export_onnx.py` |
| 推論スクリプト | `src/python/piper_train/infer_onnx.py` |
| バイリンガルPhonemizer | `src/python/piper_train/phonemize/bilingual.py` |
| バイリンガルIDマップ | `src/python/piper_train/phonemize/bilingual_id_map.py` |

### データセット

| 用途 | パス | 発話数 | 特徴 |
|------|------|--------|------|
| **バイリンガル JA+EN** ✅最新 | `/data/piper/dataset-bilingual-ja-en/` | 73,148 | JA 60,148 + EN 13,000、21話者、97シンボル、空phoneme_ids除外+JA padding修正済み |
| 20話者 v2 (JA-only) | `/data/piper/dataset-moe-speech-20speakers-v2/` | 60,164 | Issue #204, #207 対応 |

### 学習済み/学習中モデル

| 用途 | パス | 状態 |
|------|------|------|
| **バイリンガル JA+EN** | `/data/piper/output-bilingual-ja-en/bilingual-ja-en-200epoch.onnx` | ✅ 200 epoch完了 (74MB, EMA適用) — JA良好、EN発音不明瞭 |
| 20話者 v2 JA-only (200epoch) | `/data/piper/output-moe-speech-20speakers-v2/moe-speech-20speakers-v2.onnx` | ✅ 完了 |
| つくよみちゃん | HuggingFace: `ayousanz/piper-plus-tsukuyomi-chan` | ✅ 完了 |

### 便利ツール

| ツール | パス | 用途 |
|--------|------|------|
| `add_prosody_features.py` | `/data/piper/add_prosody_features.py` | 既存データセットにprosody_features追加＋phoneme_ids再生成 |
| `prepare_bilingual_dataset.py` | `/data/piper/prepare_bilingual_dataset.py` | JA+ENバイリンガルデータセット作成（JA padding修正済み） |

**使用例**:
```bash
# prosody_features追加
uv run python /data/piper/add_prosody_features.py \
  --input-dataset /data/piper/dataset-moe-speech-20speakers/dataset.jsonl \
  --output-dir /data/piper/dataset-moe-speech-20speakers-v2 \
  --workers 8

# バイリンガルデータセット作成
uv run python /data/piper/prepare_bilingual_dataset.py \
  --ja-dataset /data/piper/dataset-moe-speech-20speakers-v2/dataset.jsonl \
  --en-input-dir /data/piper/ljspeech/LJSpeech-1.1 \
  --output-dir /data/piper/dataset-bilingual-ja-en \
  --sample-rate 22050 --max-en-utterances 13000 --workers 8
```

---

## 基本コマンド

### ONNX変換

```bash
# WavLM無効モデル（deterministic、--no-ema）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-ema \
  /path/to/checkpoint.ckpt \
  /path/to/output.onnx

# WavLM有効モデル（stochastic + EMA重み適用）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic \
  /path/to/checkpoint.ckpt \
  /path/to/output.onnx
```

| オプション | デフォルト | 説明 |
|-----------|----------|------|
| `--stochastic` | off | noise_scaleによるサンプリングを有効化（WavLMモデル推奨） |
| `--use-ema` | on | チェックポイントのEMA重みをデコーダに適用 |
| `--no-ema` | - | EMA重み適用を無効化 |

### 推論テスト

```bash
cat /path/to/test.jsonl | \
  CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
    --model /path/to/model.onnx \
    --output-dir /path/to/output
```

**JSONLフォーマット:**
```json
{"phoneme_ids": [1, 8, 5, 39, ...], "speaker_id": 0, "prosody_features": [{"a1": -2, "a2": 1, "a3": 5}, ...]}
```

---

## トラブルシューティング

### 推論音声が「ピー」音になる

**原因**: Duration Predictorの学習失敗

**対処法**:
1. `--samples-per-speaker` を使用
2. `--disable_auto_lr_scaling` を使用
3. 学習率を下げる（`--base_lr 1e-4`）

### GPUメモリ不足 (OOM)

**対処法**:
1. NCCL環境変数を設定
2. `batch_size` と `samples_per_speaker` を下げる
3. 異なるバッチサイズからのリジュームを避ける

### 学習速度が遅い

**対処法**:
1. ゾンビGPUプロセスを確認: `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` でOSプロセスに対応しないPIDがないか確認。`kill -9` で終了したプロセスがGPUメモリを占有し続けることがある
2. `--max-phoneme-ids 400` で長いシーケンスを除外しメモリスパイクを防止
3. `MEMORY_CLEANUP_FREQUENCY` を調整（`lightning.py`、デフォルト: 500）

**注意**: WavLM有効時の学習速度は ~0.03 it/s と遅い (WavLM無効時の 3-5倍)。速度を優先する場合は `--no-wavlm` で無効化推奨。マルチGPU環境で `--wavlm-every-n-steps N` (N>1) は使用しないこと。`find_unused_parameters=True` との相互作用でWavLMパラメータ（~94M）の未使用同期が発生し、逆に~3x遅くなる

### ONNX変換エラー

- `CUDA_VISIBLE_DEVICES=""`でCPUモードを使用

---

## HuggingFaceリソース

| リソース | URL |
|----------|-----|
| つくよみちゃんモデル | `ayousanz/piper-plus-tsukuyomi-chan` |
| 20話者データセット | `ayousanz/moe-speech-20speakers-ljspeech` |
| ベースモデル | `ayousanz/piper-plus-base` |

---

## 関連PR/Issue

| PR/Issue | 内容 | 状態 |
|----------|------|------|
| PR #212 | WavLM Discriminator追加 | Open |
| PR #210 | Issue #204, #207 実装 | Open |
| Issue #204 | 疑問詞マーカーの拡張 | 実装完了 |
| Issue #207 | 文脈依存N phoneme variants | 実装完了 |
| Issue #198 | WavLM Discriminator | 実装完了 |
| PR #196 | A1/A2/A3 prosody機能 | Merged |
| PR #195 | FP16 Mixed Precision | Merged |
