# Piper TTS - プロジェクト概要

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

---

## 🟡 現在の状態: バイリンガル (JA+EN) モデル — データセット再生成後、0 epochから再学習

**ブランチ**: `feat/bilingual-phonemizer`

### バイリンガルモデル学習状況 (2026-02-07 更新)

| 項目 | 値 |
|------|-----|
| エポック | **0** / 200 — データセット修正後、再学習開始 |
| データセット | `dataset-bilingual-ja-en` (JA phoneme padding修正済み) |
| 発話数 | 73,148 (JA=60,148 + EN=13,000、空phoneme_ids 16件除外済み) |
| 話者数 | 21 (JA 20話者 + EN 1話者 LJSpeech) |
| 言語数 | 2 (ja=0, en=1) |
| シンボル数 | 97 |
| WavLM | 有効 (c_wavlm=0.5) |
| WandB | `yousan/piper-tts` / `dataset-bilingual-ja-en` |

**修正内容 (2026-02-07):** JA phoneme IDにinter-phoneme padding (ID 0) が欠落していた問題を修正。
学習データとEN/推論時のphoneme IDパターンが不一致だったため、JA発音品質が低下していた。
`prepare_bilingual_dataset.py`の`process_ja_dataset()`に`_add_inter_phoneme_padding()`を追加し、
JA utterancesにもEN同様の`[BOS, pad, phoneme, pad, phoneme, ..., pad, EOS]`パターンを適用。

### バイリンガルモデル

```
/data/piper/output-bilingual-ja-en/
├── lightning_logs/version_3/checkpoints/
│   ├── epoch=149-step=273600.ckpt  ← 旧データセット (padding未修正)
│   └── last.ckpt  ← 旧データセット (padding未修正)
└── bilingual-ja-en-150epoch.onnx  ← 旧データセット (padding未修正)
```

### 学習開始コマンド (0→200 epoch、修正済みデータセット)

```bash
export $(cat /data/piper/.env | xargs) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-bilingual-ja-en \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --default_root_dir /data/piper/output-bilingual-ja-en
```

### 推論テスト

**日本語:**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en/bilingual-ja-en-150epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en/config.json \
  --output-dir /home/jovyan \
  --text "こんにちは、今日は良い天気ですね。" \
  --language ja-en --speaker-id 0 --noise-scale 0.5
```

**英語:**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en/bilingual-ja-en-150epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en/config.json \
  --output-dir /home/jovyan \
  --text "Hello, how are you today?" \
  --language ja-en --speaker-id 20 --noise-scale 0.5
```

**混合テキスト (コードスイッチング):**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en/bilingual-ja-en-150epoch.onnx \
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
  --model /data/piper/output-bilingual-ja-en/bilingual-ja-en-150epoch.onnx \
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

**Phase C 状況:** データセット修正 (JA phoneme padding追加) 完了、0 epochから再学習開始

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

Microsoft WavLMベースの知覚品質判別器。音質向上のためデフォルトで有効。

**期待効果:**
- MOS向上: +0.15-0.25
- 推論速度への影響: なし（学習時のみ使用）

**実装ファイル:**
- `src/python/piper_train/vits/models.py` - `WavLMDiscriminator`クラス
- `src/python/piper_train/vits/lightning.py` - 学習ループ統合

**注意:**
- WavLMは学習時のみ使用（推論グラフには含まれない）
- FP16 Mixed Precision対応済み（内部でfloat32変換）
- GPUメモリ追加: 約1-2GB/GPU

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

### FP16 Mixed Precision ✅

デフォルトで有効（`--precision 16-mixed`）。学習速度2-3倍向上、GPUメモリ約50%削減。

---

## 学習設定

### 推奨設定 (20話者、L4 GPU 16GB × 4、WavLM有効)

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
  --default_root_dir /data/piper/output-moe-speech-20speakers-wavlm
```

**注意:** WavLMはデフォルトで有効。GPUメモリ増加のため`batch-size`を12に削減。

### 話者数別の推奨設定

| 話者数 | batch_size | samples_per_speaker | 実効バッチ | 備考 |
|-------|------------|---------------------|-----------|------|
| 5話者 | 20 | 4 | 20 | ✅ 検証済み |
| **20話者** | **20** | **2** | **40** | **✅ 検証済み** |

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
| **バイリンガル JA+EN** | `/data/piper/output-bilingual-ja-en/` | 🟡 データセット修正済み、0 epochから再学習開始 |
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
# ベースラインモデル（deterministic、従来通り）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-ema \
  /path/to/checkpoint.ckpt \
  /path/to/output.onnx

# WavLMモデル（stochastic + EMA重み適用）
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
