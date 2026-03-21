# Piper TTS - プロジェクト概要

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

---

## 🚀 現在の状態: 6言語マルチリンガル対応

**ブランチ**: `dev`

### 最新データセット: `dataset-multilingual-6lang-filtered` (6言語マルチリンガル)

| 項目 | 値 |
|------|-----|
| データセット | `dataset-multilingual-6lang-filtered` |
| 発話数 | **508,187** |
| 話者数 | 571 |
| シンボル数 | 173 |
| 言語数 | 6 (ja=0, en=1, zh=2, es=3, fr=4, pt=5) |
| 最小発話数/話者 | 31 (>=30 でフィルタ済み) |
| 状態 | **学習完了 (2026-03-16)** -- 75 epoch、epoch=74-step=504712.ckpt |

**言語別内訳:**

| 言語 | 話者数 | 発話数 | ソース |
|------|--------|--------|--------|
| ja | 20 | 60,148 | MOE-Speech (v4再利用) |
| en | 310 | 74,912 | LibriTTS-R (v4再利用) |
| zh | 142 | 63,223 | AISHELL-3 (Apache-2.0) |
| es | 63 | 168,374 | CML-TTS Spanish (CC-BY-4.0) |
| fr | 28 | 107,464 | CML-TTS French (CC-BY-4.0) |
| pt | 8 | 34,066 | CML-TTS Portuguese (CC-BY-4.0) |

**前処理ツール:** `src/python/piper_train/tools/prepare_multilingual_dataset.py`

### 6言語事前学習コマンド (学習完了)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-multilingual-6lang-filtered \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 75 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 5 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --audio-log-epochs 5 \
  --default_root_dir /data/piper/output-multilingual-6lang \
  > /data/piper/training_multilingual_6lang.log 2>&1 &
```

**設計根拠:**

| パラメータ | 値 | 根拠 |
|-----------|-----|------|
| `--max_epochs 75` | 75ep x 3,758 batches/gpu = ~282K gradient steps (v4の~270Kと同等) |
| `--batch-size 20` | v4と同一。173 symbols でも V100 16GB に収まる |
| `--samples-per-speaker 2` | 6言語 x スロット配分: ja=2, en=2, zh=2, es=2, fr=1, pt=1 |
| `--checkpoint-epochs 5` | 75ep / 5 = 15 チェックポイント |
| 実際の学習時間 | ~92時間 (~3.8日) -- 7回リスタート含む |
| language-balanced-sampling | 自動有効化 (話者比 >= 3:1) |

---

## つくよみちゃん 6langベースファインチューニング (2026-03-16 完了)

6言語マルチリンガルモデル (571話者, 75 epoch) をベースとして、つくよみちゃんデータ (100発話, ~11分) を転移学習。500 epoch完了。v1はfreeze_dpタイミングバグで失敗、v2で修正済み。

**2段階方式:**
1. **学習時**: `--resume-from-multispeaker-checkpoint` で emb_lang[0:5] を元の embedding + emb_g_mean 補正のまま保持。`--freeze-dp` は自動有効化。
2. **後処理 (ONNX エクスポート前)**: `emb_lang[0]` (JA=つくよみちゃん) -> `emb_lang[1:5]` (EN/ZH/ES/FR/PT) にコピーして声質を統一。

**データセット:** `/data/piper/dataset-tsukuyomi-finetune-6lang/` (100発話, 1話者, 173シンボル, 6言語)

**学習コマンド:**
```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-tsukuyomi-finetune-6lang \
  --prosody-dim 16 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 500 --batch-size 4 --samples-per-speaker 4 \
  --checkpoint-epochs 50 --quality medium \
  --base_lr 2e-5 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --val-every-n-epochs 50 \
  --audio-log-epochs 50 \
  --resume-from-multispeaker-checkpoint \
    /data/piper/output-multilingual-6lang/lightning_logs/version_0/checkpoints/epoch=74-step=504712.ckpt \
  --default_root_dir /data/piper/output-tsukuyomi-finetune-6lang-v2 \
  > /data/piper/training_tsukuyomi_6lang_v2.log 2>&1 &
```

**推論結果:**

| テキスト | 言語 | 音声長 |
|---------|------|--------|
| 「こんにちは、つくよみちゃんです。」 | JA | 3.05s |
| "Hello, how are you today?" | EN | 2.54s |
| "你好，今天天气很好。" | ZH | 1.21s |
| "¿Hola, cómo estás hoy?" | ES | 2.86s |
| "Bonjour, comment allez-vous?" | FR | 2.11s |
| "Olá, como você está hoje?" | PT | 2.24s |

**注意:** ZH の duration (1.21s) が他言語 (2-3s) と比べて短い。凍結された DP の ZH パラメータ特性による。

**生成モデル:** `/data/piper/output-tsukuyomi-finetune-6lang-v2/tsukuyomi-6lang-v2-fixed.onnx` (emb_lang後処理済み)
**チェックポイント:** `output-tsukuyomi-finetune-6lang-v2/lightning_logs/version_0/checkpoints/epoch=499-step=22000.ckpt`

---

## ファインチューニング テンプレート

### Template A: 事前学習 (Multi-speaker pretraining)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir <DATASET_DIR> \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs <EPOCHS> --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 5 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --audio-log-epochs 5 \
  --default_root_dir <OUTPUT_DIR> \
  > training.log 2>&1 &
```

### Template B: シングルスピーカー ファインチューニング

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir <FINETUNE_DATASET> \
  --prosody-dim 16 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 500 --batch-size 4 --samples-per-speaker 4 \
  --checkpoint-epochs 50 --quality medium \
  --base_lr 2e-5 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --val-every-n-epochs 50 \
  --audio-log-epochs 50 \
  --resume-from-multispeaker-checkpoint <BASE_CHECKPOINT> \
  --default_root_dir <OUTPUT_DIR> \
  > training.log 2>&1 &
```

### パラメータ差分

| パラメータ | 事前学習 (A) | ファインチューニング (B) | 理由 |
|-----------|-------------|----------------------|------|
| `--devices` | 4 | 1 | 小データでDDPはオーバーヘッド過多 |
| `--base_lr` | 2e-4 | 2e-5 | catastrophic forgetting防止 (1/10) |
| `--batch-size` | 20 | 4 | 100発話 / 4 = 25 batches/epoch |
| `--max_epochs` | データ量に応じて | 500 | 25x500=12,500 gradient steps |
| `--freeze-dp` | なし | 自動有効化 | DP catastrophic forgetting防止 |
| `--audio-log-epochs` | 5 | 50 | Validation頻度に合わせる |

---

## 実装済み機能

### Duration Predictor 凍結 (--freeze-dp)

ファインチューニング時に Duration Predictor (DP) の catastrophic forgetting を防止。`--freeze-dp` で DP パラメータを凍結し optimizer から除外。`--resume-from-multispeaker-checkpoint` 使用時は自動有効化。

**注意:** `args.freeze_dp = True` は必ず `VitsModel()` 作成の**前**に設定すること (`save_hyperparameters()` がスナップショットを取るため)。

**CLIオプション:** `--freeze-dp`
**実装:** `__main__.py`, `vits/lightning.py` (`configure_optimizers()`)
**テスト:** `tests/test_freeze_dp.py`

### 多言語 Phonemizer (6言語)

`MultilingualPhonemizer` は `UnicodeLanguageDetector` で言語を自動検出し、各言語の Phonemizer に委譲。`models.py` の `gin_channels` 条件は `(num_speakers > 1 or num_languages > 1)` で多言語シングルスピーカーにも対応。

| 言語 | コード | Phonemizer | 依存 |
|------|--------|------------|------|
| 日本語 | ja | JapanesePhonemizer | pyopenjtalk |
| 英語 | en | EnglishPhonemizer | g2p-en (Apache-2.0, espeak-ng互換) |
| 中国語 | zh | ChinesePhonemizer | pypinyin (MIT) |
| 韓国語 | ko | KoreanPhonemizer | g2pk2 (Apache-2.0), optional |
| スペイン語 | es | SpanishPhonemizer | 規則ベース (依存なし) |
| ポルトガル語 | pt | PortuguesePhonemizer | 規則ベース (依存なし) |
| フランス語 | fr | FrenchPhonemizer | 規則ベース (依存なし) |

**実装:** `phonemize/multilingual.py`, `phonemize/multilingual_id_map.py`, `phonemize/{chinese,korean,spanish,portuguese,french}.py`, `phonemize/{zh,ko,es,pt,fr}_id_map.py`
**Phonemizer ABC:** `phonemize/base.py` (抽象基底), `phonemize/registry.py` (言語レジストリ)

### 言語グループ均等サンプリング (--language-balanced-sampling)

話者数比が不均衡な場合に言語グループ間のバッチバランスを保護。話者数比 >= 3:1 で**自動有効化** (デフォルト)。`--language-balanced-sampling` で強制有効化も可能。

**CLIオプション:** `--language-balanced-sampling`
**実装:** `vits/dataset.py` (`SpeakerBalancedBatchSampler`), `vits/lightning.py`, `__main__.py`

### FP16 ONNX変換

ONNX エクスポート時にデフォルトで FP16 変換を適用。モデルサイズ ~50% 削減。

**CLIオプション:** `--no-fp16` (FP16変換を無効化)
**実装:** `export_onnx.py`

### WavLM Discriminator (--no-wavlm)

Microsoft WavLMベースの知覚品質判別器。デフォルト有効。学習時のみ使用 (推論グラフには含まれない)。GPUメモリ追加 ~1-2GB/GPU。V100では `--no-wavlm` 推奨 (学習速度優先)。

**CLIオプション:** `--no-wavlm`, `--wavlm-every-n-steps N` (デフォルト: 1), `--c-wavlm` (デフォルト: 0.5)
**実装:** `vits/models.py` (`WavLMDiscriminator`), `vits/lightning.py`, `__main__.py`

### WandB Audio Logging (--audio-log-epochs)

Validation時に音声サンプルをWandBに自動アップロード。DDP環境では `--audio-log-epochs 5` 推奨 (barrier同期済み)。

**CLIオプション:** `--audio-log-epochs N` (デフォルト: 1, 0で無効化), `--num-test-examples N` (デフォルト: 2)
**実装:** `vits/lightning.py` (`on_validation_epoch_end()`), `__main__.py` (WandbLogger設定)

### テキスト直接入力推論 (--text)

`infer_onnx.py` に `--text` オプション追加。JSONLなしでテキストから直接音声生成。

**CLIオプション:** `--text`, `--config`, `--speaker-id`, `--language`
**実装:** `infer_onnx.py`

### prosody_features (A1/A2/A3) (--prosody-dim)

OpenJTalkから抽出されるA1/A2/A3値をDuration Predictorの入力として活用。デフォルト有効 (`--prosody-dim 16`)。

**CLIオプション:** `--prosody-dim N` (デフォルト: 16)
**前処理:** `uv run python /data/piper/add_prosody_features.py --input-dataset ... --output-dir ...`
**実装:** `vits/models.py`, `vits/lightning.py`

### 転移学習 (--resume-from-multispeaker-checkpoint)

マルチスピーカー -> シングルスピーカー転移の専用フラグ。自動で emb_g 除去 + emb_lang 補正 + freeze-dp 有効化を実行。

**推奨ワークフロー (2段階方式):**
1. **学習時**: `--resume-from-multispeaker-checkpoint` で全言語の emb_lang を保持 (凍結 DP が正しい conditioning を受け取る)
2. **後処理**: ONNX エクスポート前に `emb_lang[0]` -> `emb_lang[1:N]` にコピーして声質を統一

**CLIオプション:** `--resume-from-multispeaker-checkpoint <path>`
**実装:** `__main__.py`

### エネルギーVAD高速キャッシュ

LibriTTS-R の音声キャッシュを Silero ONNX VAD から numpy エネルギーVAD に置き換え。25倍高速化 (~390ms/file -> ~8ms/file)。

**実装:** `norm_audio/__init__.py`, `src/python/piper_train/tools/prepare_bilingual_dataset.py`

### 疑問詞マーカー拡張 (Issue #204)

日本語疑問文の種類を区別するマーカー: `?!` (強調疑問), `?.` (平叙疑問), `?~` (確認疑問)。

**実装:** `phonemize/japanese.py` (`_get_question_type()`)

### 文脈依存N phoneme variants (Issue #207)

「ん」の発音を後続音により4バリアントに分類: N_m (両唇音前), N_n (歯茎音前), N_ng (軟口蓋音前), N_uvular (語末/母音前)。

**実装:** `phonemize/japanese.py` (`_apply_n_phoneme_rules()`), `phonemize/jp_id_map.py`, `phonemize/token_mapper.py`

### 学習高速化

Validation頻度削減、DataLoader最適化 (num_workers=2, pin_memory)、LRスケジューラ修正、DDP `find_unused_parameters=True` に修正。

**CLIオプション:** `--val-every-n-epochs N` (デフォルト: 5), `--limit-val-batches N` (デフォルト: 50), `--num-workers N` (デフォルト: 2), `--no-pin-memory`
**実装:** `__main__.py`, `vits/lightning.py`, `vits/dataset.py`

### C# CLI (PiperPlus)

6言語マルチリンガル対応のクロスプラットフォーム .NET CLI。Python実装と同等の音素化パイプラインを C# で再実装。

| 項目 | 詳細 |
|------|------|
| TFM | PiperPlus.Core: net8.0, PiperPlus.Cli: net9.0 |
| 対応言語 | JA, EN, ZH, ES, FR, PT (6言語) |
| G2P依存 | DotNetG2P v1.8.0 (JA), DotNetG2P.MeCab v1.8.0 (JA), DotNetG2P.English v1.8.0 (EN), DotNetG2P.Chinese/Spanish/French/Portuguese v1.7.0 |
| テスト | 749テスト (xUnit v3) |
| CI | 3 OS × 2 .NET バージョン (csharp-ci.yml) |
| ビルド | `dotnet build src/csharp/PiperPlus.sln` |

**実装:** `src/csharp/PiperPlus.Core/`, `src/csharp/PiperPlus.Cli/`

**追加機能:**
- `lid` (言語ID) テンソル対応: マルチリンガルモデルで `language_id_map` から自動解決
- OpenJTalk 辞書自動ダウンロード: C++ `openjtalk_dictionary_manager.c` と同等の辞書検索・自動DL機能

### Rust 推論エンジン (piper-plus)

Rust によるONNX推論エンジン。ストリーミング、CUDA/CoreML/DirectML対応。PyO3 による Python バインディング提供。

| 項目 | 詳細 |
|------|------|
| クレート | piper-plus, piper-plus-cli, piper-plus-python |
| 対応言語 | JA, EN, ZH, KO, ES, FR, PT (7言語) |
| 特徴 | ストリーミング、GPU推論、WASM対応 |
| CI | 3 OS (rust-tests.yml) |
| ビルド | `cargo build --release -p piper-plus-cli` |

**デフォルトfeature:** `naist-jdic` (JA辞書バンドル) + `dict-download` (OpenJTalk辞書自動DL、C#/C++用)。jpreprocess は lindera 形式辞書を使用するため、OpenJTalk MeCab 形式とは非互換。`PIPER_OFFLINE_MODE=1` で自動DL無効化可能。

**実装:** `src/rust/piper-core/`, `src/rust/piper-cli/`, `src/rust/piper-python/`

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
| 中国語音素化 | `src/python/piper_train/phonemize/chinese.py` |
| 韓国語音素化 | `src/python/piper_train/phonemize/korean.py` |
| スペイン語音素化 | `src/python/piper_train/phonemize/spanish.py` |
| ポルトガル語音素化 | `src/python/piper_train/phonemize/portuguese.py` |
| フランス語音素化 | `src/python/piper_train/phonemize/french.py` |
| IDマップ (JA) | `src/python/piper_train/phonemize/jp_id_map.py` |
| IDマップ (ZH/KO/ES/PT/FR) | `src/python/piper_train/phonemize/{zh,ko,es,pt,fr}_id_map.py` |
| トークンマッパー | `src/python/piper_train/phonemize/token_mapper.py` |
| ONNXエクスポート | `src/python/piper_train/export_onnx.py` |
| 推論スクリプト | `src/python/piper_train/infer_onnx.py` |
| マルチリンガルPhonemizer | `src/python/piper_train/phonemize/multilingual.py` |
| マルチリンガルIDマップ | `src/python/piper_train/phonemize/multilingual_id_map.py` |
| バイリンガルPhonemizer | `src/python/piper_train/phonemize/bilingual.py` |
| バイリンガルIDマップ | `src/python/piper_train/phonemize/bilingual_id_map.py` |

### C# ソースコード

| 用途 | パス |
|------|------|
| ソリューション | `src/csharp/PiperPlus.sln` |
| コアライブラリ | `src/csharp/PiperPlus.Core/` |
| CLI アプリケーション | `src/csharp/PiperPlus.Cli/` |
| テスト | `src/csharp/PiperPlus.Core.Tests/` |
| ONNX推論 | `src/csharp/PiperPlus.Core/Inference/` |
| 日本語音素化 | `src/csharp/PiperPlus.Core/Phonemize/JapanesePhonemizer.cs` |
| 英語音素化 | `src/csharp/PiperPlus.Core/Phonemize/EnglishPhonemizer.cs` |
| 中国語音素化 | `src/csharp/PiperPlus.Core/Phonemize/ChinesePhonemizer.cs` |
| スペイン語音素化 | `src/csharp/PiperPlus.Core/Phonemize/SpanishPhonemizer.cs` |
| ポルトガル語音素化 | `src/csharp/PiperPlus.Core/Phonemize/PortuguesePhonemizer.cs` |
| フランス語音素化 | `src/csharp/PiperPlus.Core/Phonemize/FrenchPhonemizer.cs` |
| マルチリンガルPhonemizer | `src/csharp/PiperPlus.Core/Phonemize/MultilingualPhonemizer.cs` |
| PUAマッピング | `src/csharp/PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs` |
| 設定管理 | `src/csharp/PiperPlus.Core/Config/` |
| 辞書マネージャ | `src/csharp/PiperPlus.Core/Config/DictionaryManager.cs` |

### Rust ソースコード

| 用途 | パス |
|------|------|
| ワークスペース | `src/rust/Cargo.toml` |
| コアライブラリ | `src/rust/piper-core/` |
| CLI アプリケーション | `src/rust/piper-cli/` |
| Python バインディング | `src/rust/piper-python/` |
| 音素化 | `src/rust/piper-core/src/phonemize/` |
| 推論エンジン | `src/rust/piper-core/src/engine.rs` |
| 辞書マネージャ | `src/rust/piper-core/src/dictionary_manager.rs` |

### データセット

| 用途 | パス | 発話数 | 特徴 |
|------|------|--------|------|
| **多言語 6lang** | `/data/piper/dataset-multilingual-6lang-filtered/` | 508,187 | JA+EN+ZH+ES+FR+PT、571話者、173シンボル、>=30発話/話者 |
| **つくよみちゃん 6langベース finetune** | `/data/piper/dataset-tsukuyomi-finetune-6lang/` | 100 | 1話者、173シンボル、multilingual(6言語) |
| バイリンガル JA+EN v4 (参照) | `/data/piper/dataset-bilingual-ja-en-v4/` | 135,060 | JA 60,148 (20話者) + EN 74,912 (310話者)、6langの入力データ |

### 学習済みモデル

| 用途 | パス | 状態 |
|------|------|------|
| **つくよみちゃん 6lang-v2** | `/data/piper/output-tsukuyomi-finetune-6lang-v2/tsukuyomi-6lang-v2-fixed.onnx` | 500 epoch完了 (2026-03-16) -- emb_lang後処理済み、全6言語テスト成功 |
| **多言語 6lang ベースモデル** | `/data/piper/output-multilingual-6lang/` | 75 epoch完了 (2026-03-16) -- epoch=74-step=504712.ckpt、571話者 |
| **CSS10 JA 6lang** | `/data/piper/css10-ja-ljspeech/` -> `test/models/multilingual-test-medium.onnx` | 50 epoch完了 (2026-03-16) -- 6langベースから転移、6,841発話 |
| バイリンガル JA+EN v4 (参照) | `/data/piper/output-bilingual-ja-en-v4/bilingual-ja-en-v4-150epoch.onnx` | 150 epoch完了 (75MB, 2026-03-04) -- EMA適用済み |

### 便利ツール

| ツール | パス | 用途 |
|--------|------|------|
| `prepare_multilingual_dataset.py` | `src/python/piper_train/tools/prepare_multilingual_dataset.py` | 6言語マルチリンガルデータセット作成 |
| `add_prosody_features.py` | `src/python/piper_train/tools/add_prosody_features.py` | 既存データセットにprosody_features追加+phoneme_ids再生成 |
| `prepare_bilingual_dataset.py` | `src/python/piper_train/tools/prepare_bilingual_dataset.py` | JA+ENバイリンガルデータセット作成 |
| `prepare_libritts_parallel.py` | `/data/piper/prepare_libritts_parallel.py` | LibriTTS-R -> LJSpeech形式変換（並列処理） |

---

## 基本コマンド

### ONNX変換

```bash
# 通常エクスポート（EMA + stochastic、デフォルト推奨）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt \
  /path/to/output.onnx

# deterministic（デバッグ用）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-stochastic \
  /path/to/checkpoint.ckpt \
  /path/to/output.onnx
```

| オプション | デフォルト | 説明 |
|-----------|----------|------|
| `--no-stochastic` | - | deterministic エクスポート（デバッグ用） |
| EMA | 常時有効 | チェックポイントに EMA state があれば自動適用 |
| `--no-fp16` | - | FP16変換を無効化（デフォルト: FP16有効、モデルサイズ~50%削減） |

### 推論テスト (6lang マルチリンガルモデル)

**日本語 (speaker_id=0, JA話者):**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-multilingual-6lang/multilingual-6lang-75epoch.onnx \
  --config /data/piper/dataset-multilingual-6lang-filtered/config.json \
  --output-dir /home/jovyan \
  --text "こんにちは、今日は良い天気ですね。" \
  --language ja-en-zh-es-fr-pt --speaker-id 0 --noise-scale 0.667
```

**注意:** `--language` の言語コード順は任意（内部で canonical key に正規化される）。

**英語 (speaker_id=20, EN話者の先頭):**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-multilingual-6lang/multilingual-6lang-75epoch.onnx \
  --config /data/piper/dataset-multilingual-6lang-filtered/config.json \
  --output-dir /home/jovyan \
  --text "Hello, how are you today?" \
  --language ja-en-zh-es-fr-pt --speaker-id 20 --noise-scale 0.667
```

**JSONL入力 (phoneme_ids直接指定):**
```bash
cat /path/to/test.jsonl | \
  CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
    --model /path/to/model.onnx \
    --output-dir /path/to/output
```

**JSONLフォーマット (1行1発話):**
```json
{"phoneme_ids": [1, 8, 5, 39, ...], "speaker_id": 0, "prosody_features": [{"a1": -2, "a2": 1, "a3": 5}, ...]}
```
`phoneme_ids` は必須。`speaker_id` (デフォルト: 0)、`prosody_features` (省略時はゼロ) は任意。

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
1. NCCL環境変数を設定: `NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1`
2. `batch_size` と `samples_per_speaker` を下げる
3. 異なるバッチサイズからのリジュームを避ける

### 学習速度が遅い

**対処法**:
1. V100では `--precision 32-true` を使用（FP16-mixedはbackward passが29-40秒に低下する致命的問題あり）
2. ゾンビGPUプロセスを確認: `nvidia-smi --query-compute-apps=pid,used_memory --format=csv`
3. `--max-phoneme-ids 400` で長いシーケンスを除外
4. `--val-every-n-epochs 10` でValidation頻度を下げる
5. `--limit-val-batches 20` でValidationバッチ数を削減
6. WavLM有効時は ~0.03 it/s と遅い。速度優先なら `--no-wavlm` 推奨

### ONNX変換エラー

- `CUDA_VISIBLE_DEVICES=""` でCPUモードを使用

---

## HuggingFaceリソース

| リソース | URL |
|----------|-----|
| つくよみちゃん 6langモデル | `ayousanz/piper-plus-tsukuyomi-chan` |
| 6langベースモデル | `ayousanz/piper-plus-base` |
| 20話者データセット | `ayousanz/moe-speech-20speakers-ljspeech` |

---

## 関連PR/Issue

| PR/Issue | 内容 | 状態 |
|----------|------|------|
| PR #239 | FP16変換ツール | Merged |
| PR #218 | 6言語マルチリンガル + C++ G2P | Merged |
| PR #212 | WavLM Discriminator追加 | Open |
| PR #210 | Issue #204, #207 実装 | Open |
| PR #196 | A1/A2/A3 prosody機能 | Merged |
| PR #195 | FP16 Mixed Precision | Merged |

---

## アーカイブ: バイリンガル版の履歴 (v2/v3/v4)

> 以下は6言語版に置き換えられた旧バージョンの参考情報です。

### バージョン比較

| 指標 | v2 | v3 | v4 | **6lang (現在)** |
|------|-----|-----|-----|-----------------|
| 言語数 | 2 | 2 | 2 | **6** |
| 総発話数 | 63,325 | 115,795 | 135,060 | **508,187** |
| 話者数 | 40 | 848 | 330 | **571** |
| シンボル数 | 97 | 97 | 97 | **173** |
| 学習期間 | 4h19分 (200ep) | ~3日 (350ep) | ~46時間 (150ep) | **~92時間 (75ep)** |
| gradient steps | ~110K | ~202K | ~270K | **~282K** |

### v4 バイリンガル (学習完了 2026-03-04)

JA 60,148発話 (20話者) + EN 74,912発話 (LibriTTS-R 310話者) = 135,060発話、330話者。150 epoch / ~46時間。EN per-speaker データ密度 17.8分 (v3比2.8倍)。v4 の JA+EN が 6lang のベースデータとして再利用されている。

**チェックポイント:** `output-bilingual-ja-en-v4/lightning_logs/version_0/checkpoints/epoch=149-step=269700.ckpt`

### v3 バイリンガル (学習完了 2026-02-27)

JA 60,148発話 (20話者) + EN 55,647発話 (LibriTTS-R 828話者) = 115,795発話、848話者、174h。350 epoch / ~3日。`--language-balanced-sampling` で JA:EN = 50:50 を強制。

**チェックポイント:** `output-bilingual-ja-en-v3/lightning_logs/version_0/checkpoints/epoch=349-step=202300.ckpt`

### つくよみちゃん ファインチューニング履歴

v3 -> v4 -> v4-freeze-dp -> v4-emb-lang-fix -> 6lang-v2 と段階的に改善。

1. **v3ベース (2026-02-28)**: 初回転移学習。`--resume_from_checkpoint` で strict=False フォールバック。emb_lang[1] EN 初期化問題を後処理で修正。
2. **v4ベース (2026-03-04)**: チェックポイント事前変換方式 (emb_g除去 + emb_lang補正)。DP catastrophic forgetting が発生 (音声長 1.11s)。
3. **v4 freeze-dp (2026-03-04)**: `--freeze-dp` で DP 凍結。音声長 1.11s -> 1.76s に改善 (59%)。
4. **v4 emb-lang-fix (2026-03-05)**: `--resume-from-multispeaker-checkpoint` + 後処理 emb_lang コピーの2段階方式を確立。
5. **6lang-v2 (2026-03-16)**: 6言語ベースから転移。freeze_dpタイミングバグ修正後に再実行して成功。

**Key learnings:**
- `emb_lang[0]` -> `emb_lang[1:N]` コピーによる声質統一 (ONNX エクスポート前の後処理)
- `--freeze-dp` による DP catastrophic forgetting 防止
- `--resume-from-multispeaker-checkpoint` による自動変換 (emb_g除去 + emb_lang補正 + freeze-dp)

### 旧データセット・モデルパス

| 種類 | パス |
|------|------|
| v4 データセット | `/data/piper/dataset-bilingual-ja-en-v4/` |
| v3 データセット | `/data/piper/dataset-bilingual-ja-en-v3/` |
| v2 データセット | `/data/piper/dataset-bilingual-ja-en-v2/` |
| つくよみちゃん v3 finetune データ | `/data/piper/dataset-tsukuyomi-finetune-v3/` |
| v4 ONNX | `/data/piper/output-bilingual-ja-en-v4/bilingual-ja-en-v4-150epoch.onnx` |
| v3 ONNX | `/data/piper/output-bilingual-ja-en-v3/bilingual-ja-en-v3-350epoch.onnx` |
| v2 ONNX | `/data/piper/output-bilingual-ja-en-v2/bilingual-ja-en-v2-200epoch.onnx` |
| つくよみちゃん v4 emb-lang-fix | `/data/piper/output-tsukuyomi-finetune-v4-emb-lang-fix/tsukuyomi-v4-emb-lang-fix.onnx` |
| つくよみちゃん v4 freeze-dp | `/data/piper/output-tsukuyomi-finetune-v4-freeze-dp/tsukuyomi-v4-freeze-dp.onnx` |
| つくよみちゃん v3 | `/data/piper/output-tsukuyomi-finetune-v3/tsukuyomi-v3-emb_lang_fixed.onnx` |
| 20話者 JA-only | `/data/piper/output-moe-speech-20speakers-v2/moe-speech-20speakers-v2.onnx` |
| LibriTTS-R v4 ソース | `/data/piper/libritts-r/libritts-ljspeech-v4/` |
| LibriTTS-R v3 ソース | `/data/piper/libritts-r/libritts-ljspeech/` |
