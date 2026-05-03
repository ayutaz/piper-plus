# Piper TTS - プロジェクト概要

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

---

## 🚀 現在の状態: 6言語マルチリンガル対応 (コード: 8言語対応、sv/ko含む)

> **Note:** G2Pコードは8言語 (JA/EN/ZH/KO/ES/FR/PT/SV) に対応済み。学習済みモデルは6言語 (SV/KO未学習)。

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

**ワークフロー:**
1. **学習時**: `--resume-from-multispeaker-checkpoint` で emb_lang[0:5] を元の embedding + emb_g_mean 補正のまま保持。`--freeze-dp` は自動有効化。
2. **ONNXエクスポート時**: `export_onnx` が自動で `emb_lang[0]` → `emb_lang[1:5]` にコピーして声質を統一 (`--unify-emb-lang` がシングルスピーカー多言語モデルで自動有効化)。

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

### 多言語 Phonemizer (8言語)

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
| スウェーデン語 | sv | SwedishPhonemizer | 規則ベース (依存なし) |

> **Note:** スウェーデン語 (sv) と韓国語 (ko) はG2Pコード実装済みだが、学習済みモデルには未含有 (sv=6, ko=7)。

**実装 (piper-plus-g2p):** `src/python/g2p/piper_plus_g2p/multilingual.py`, `src/python/g2p/piper_plus_g2p/{chinese,korean,spanish,portuguese,french,swedish}.py`
**実装 (ランタイム):** `src/python_run/piper/phonemize/multilingual.py`, `src/python_run/piper/phonemize/{japanese,english,chinese,spanish,portuguese,french}.py`
**Phonemizer ABC:** `src/python/g2p/piper_plus_g2p/base.py` (抽象基底), `src/python/g2p/piper_plus_g2p/registry.py` (言語レジストリ)

### 言語グループ均等サンプリング (--language-balanced-sampling)

話者数比が不均衡な場合に言語グループ間のバッチバランスを保護。話者数比 >= 3:1 で**自動有効化** (デフォルト)。`--language-balanced-sampling` で強制有効化も可能。

**CLIオプション:** `--language-balanced-sampling`
**実装:** `vits/dataset.py` (`SpeakerBalancedBatchSampler`), `vits/lightning.py`, `__main__.py`

### FP16 ONNX変換

ONNX エクスポート時にデフォルトで FP16 変換を適用。モデルサイズ ~50% 削減。

**CLIオプション:** `--no-fp16` (FP16変換を無効化)
**実装:** `export_onnx.py`

### emb_lang 自動統一 (--unify-emb-lang)

シングルスピーカー多言語モデルのONNXエクスポート時に、`emb_lang` を自動統一。ソース言語 (デフォルト: lang[0]) の embedding を全言語にコピーして声質を統一する。`num_speakers <= 1 and num_languages > 1` で自動有効化。

**CLIオプション:** `--unify-emb-lang` / `--no-unify-emb-lang` (デフォルト: auto), `--unify-emb-lang-source N` (デフォルト: 0)
**実装:** `export_onnx.py` (`should_unify_emb_lang()`, `unify_emb_lang_weights()`)
**テスト:** `tests/test_export_onnx.py` (`TestUnifyEmbLang`, `TestUnifyEmbLangOnnxExport`)

### WavLM Discriminator (--no-wavlm)

Microsoft WavLMベースの知覚品質判別器。デフォルト有効。学習時のみ使用 (推論グラフには含まれない)。GPUメモリ追加 ~1-2GB/GPU。V100では `--no-wavlm` 推奨 (学習速度優先)。

**CLIオプション:** `--no-wavlm`, `--wavlm-every-n-steps N` (デフォルト: 1), `--c-wavlm` (デフォルト: 0.5)
**実装:** `vits/models.py` (`WavLMDiscriminator`), `vits/lightning.py`, `__main__.py`

### MB-iSTFT-VITS2 Decoder (唯一の Generator)

VITS の Decoder は **MB-iSTFT (Multi-Band inverse STFT) + PQMF**。HiFi-GAN `Generator` は削除済み。`upsample_rates=(4,4)` + iSTFT(4x) + PQMF(4x) = 256x で現行と同じ合計倍率を維持しつつ Decoder 計算量を削減。Sub-band Multi-resolution STFT 損失をフルバンド損失に追加。ONNX 互換 iSTFT は DFT 行列方式 (`OnnxISTFT`) で `F.conv_transpose1d` に展開し opset 15 で動作。出力形状 `[B, 1, T]` 維持のため C#/Rust/Go/WASM/C++ ランタイム 変更不要。`--quality high` も対応 (resblock="1" + 512ch + (4,4) upsample)。Issue #268, PR #320。

**CLIオプション:** `--c-sub-stft` (デフォルト: 1.0), `--sub-stft-fft-sizes` (デフォルト: 171,384,683), `--sub-stft-hop-sizes` (デフォルト: 10,30,60), `--sub-stft-win-sizes` (デフォルト: 60,150,300)
**実装:** `vits/mb_istft.py` (`MBiSTFTGenerator`, `PQMF`), `vits/stft_onnx.py` (`OnnxISTFT`), `vits/stft_loss.py` (`MultiResolutionSTFTLoss`), `vits/models.py`, `vits/lightning.py`, `__main__.py`, `export_onnx.py`
**テスト:** `tests/test_pqmf.py`, `tests/test_mb_istft_generator.py`, `tests/test_stft_loss.py`, `tests/test_stft_onnx.py`, `tests/test_export_onnx_mb_istft.py`, `tests/test_main_mb_istft.py`
**性能:** 旧 HiFi-GAN 168.2ms vs MB-iSTFT 76.2ms (CPU 100 phoneme p50, **2.21x 高速化**)、つくよみちゃん FT 61.9ms (RTF 0.046)。Decoder 単体は ~3.6x 高速 (論文値と同等)。
**Breaking change:** `--mb-istft` フラグ廃止 (常に有効)。HiFi-GAN ベースの旧 ckpt からの resume/FT は不可。MB-iSTFT 対応 base/追加モデルを本マージ時に再公開。

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

**推奨ワークフロー:**
1. **学習時**: `--resume-from-multispeaker-checkpoint` で全言語の emb_lang を保持 (凍結 DP が正しい conditioning を受け取る)
2. **ONNXエクスポート時**: `export_onnx` が `--unify-emb-lang` (自動有効化) で `emb_lang[0]` → `emb_lang[1:N]` にコピーして声質を統一

**CLIオプション:** `--resume-from-multispeaker-checkpoint <path>`
**実装:** `__main__.py`

### エネルギーVAD高速キャッシュ

LibriTTS-R の音声キャッシュを Silero ONNX VAD から numpy エネルギーVAD に置き換え。25倍高速化 (~390ms/file -> ~8ms/file)。

**実装:** `norm_audio/__init__.py`, `src/python/piper_train/tools/prepare_bilingual_dataset.py`

### CPU 推論最適化 (Tier 1-2)

4言語実装 (Python/Rust/C#/C++) の ONNX Runtime セッション設定を統一。全実装で同一パラメータを使用。

**パラメータ仕様**: `docs/spec/ort-session-contract.toml`

| 設定 | 値 | 全実装で統一 |
|------|-----|------------|
| graph_optimization_level | ORT_ENABLE_ALL | ✅ |
| execution_mode | SEQUENTIAL | ✅ |
| max_intra_threads | min(cores/2, 4) | ✅ |
| inter_op_threads | 1 | ✅ |
| dynamic_block_base | 4 | ✅ |
| enable_cpu_mem_arena | true | ✅ |
| enable_memory_pattern | true | ✅ |

**Warmup**: 全実装でダミー推論 2 回 (100 phonemes, BOS=1/EOS=2/dummy=8, scales=[0.667, 1.0, 0.8])。初回推論の JIT 遅延 (500-800ms) を解消。

**最適化モデルキャッシュ**: `.opt.onnx` + `.ok` センチネルファイル方式。2回目以降の起動で ORT グラフ最適化をスキップ。Rust/C#/Python で実装済み。

**日本語音素化 LRU キャッシュ**: `@lru_cache(maxsize=2000)` で文単位キャッシュ。キャッシュヒット時 <1ms (vs 50-150ms uncached)。Python のみ。

**CLIオプション**: `--no-warmup` (C++/Rust/C#)
**環境変数**: `PIPER_DISABLE_WARMUP`, `PIPER_DISABLE_CACHE`, `PIPER_INTRA_THREADS` (Python)

**実装**: `src/python/piper_train/ort_utils.py`, `src/cpp/piper.cpp` (`warmupModel()`, `buildInputTensors()`), `src/rust/piper-core/src/engine.rs`, `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs`

### 疑問詞マーカー拡張 (Issue #204)

日本語疑問文の種類を区別するマーカー: `?!` (強調疑問), `?.` (平叙疑問), `?~` (確認疑問)。

**実装:** `src/python/g2p/piper_plus_g2p/japanese.py` (`_get_question_type()`)

### 文脈依存N phoneme variants (Issue #207)

「ん」の発音を後続音により4バリアントに分類: N_m (両唇音前), N_n (歯茎音前), N_ng (軟口蓋音前), N_uvular (語末/母音前)。

**実装:** `src/python/g2p/piper_plus_g2p/japanese.py` (`_apply_n_phoneme_rules()`), `src/python/g2p/piper_plus_g2p/encode/id_maps.py`, `src/python_run/piper/phonemize/token_mapper.py`

### 学習高速化

Validation頻度削減、DataLoader最適化 (num_workers=2, pin_memory)、LRスケジューラ修正、DDP `find_unused_parameters=True` に修正。

**CLIオプション:** `--val-every-n-epochs N` (デフォルト: 5), `--limit-val-batches N` (デフォルト: 50), `--num-workers N` (デフォルト: 2), `--no-pin-memory`
**実装:** `__main__.py`, `vits/lightning.py`, `vits/dataset.py`

### C# CLI (PiperPlus)

8言語マルチリンガル対応のクロスプラットフォーム .NET CLI。Python実装と同等の音素化パイプラインを C# で再実装。

| 項目 | 詳細 |
|------|------|
| TFM | PiperPlus.Core: net8.0, PiperPlus.Cli: net9.0 |
| 対応言語 | JA, EN, ZH, KO, ES, FR, PT, SV (8言語) |
| G2P依存 | DotNetG2P v1.8.0 (JA), DotNetG2P.MeCab v1.8.0 (JA), DotNetG2P.English v1.8.0 (EN), DotNetG2P.Chinese/Spanish/French/Portuguese v1.8.0 |
| テスト | ~1000テスト (xUnit v3) |
| CI | 3 OS (csharp-ci.yml) |
| ビルド | `dotnet build src/csharp/PiperPlus.sln` |

**実装:** `src/csharp/PiperPlus.Core/`, `src/csharp/PiperPlus.Cli/`

**追加機能:**
- `lid` (言語ID) テンソル対応: マルチリンガルモデルで `language_id_map` から自動解決
- OpenJTalk 辞書自動ダウンロード: C++ `openjtalk_dictionary_manager.c` と同等の辞書検索・自動DL機能
- ストリーミング文分割: `TextSplitter.SplitSentences()` で文ごとに逐次合成 (`--streaming`)
- カスタム辞書: JSON v1.0/v2.0 (C++/Rust互換) + TSV 形式対応 (`--custom-dict`)
- `[[ phoneme ]]` インライン音素記法: テキスト中に直接音素を指定可能
- モデル名自動解決: `--model tsukuyomi` でエイリアス検索 + 自動DL

### Rust 推論エンジン (piper-plus)

Rust によるONNX推論エンジン。ストリーミング、CUDA/CoreML/DirectML対応。PyO3 による Python バインディング提供。

| 項目 | 詳細 |
|------|------|
| クレート | piper-plus, piper-plus-cli, piper-plus-python |
| 対応言語 | JA, EN, ZH, KO, ES, FR, PT, SV (8言語) |
| 特徴 | ストリーミング、GPU推論、WASM対応 |
| CI | 3 OS (rust-tests.yml) |
| ビルド | `cargo build --release -p piper-plus-cli` |

**デフォルトfeature:** `naist-jdic` (JA辞書バンドル) + `dict-download` (OpenJTalk辞書自動DL、C#/C++用)。jpreprocess は lindera 形式辞書を使用するため、OpenJTalk MeCab 形式とは非互換。`PIPER_OFFLINE_MODE=1` で自動DL無効化可能。

**追加機能:**
- カスタム辞書: JSON v1.0/v2.0 対応、`--custom-dict` でCLI統合済み
- バイナリビルドCI: PR時3プラットフォーム、リリース時5ターゲット
- モデル名自動解決: `--model tsukuyomi` でエイリアス検索 + 自動DL
- `--download-model` / `--model-dir`: モデルダウンロード管理
- `--quiet` / `--test-mode` / `--output-raw`: デバッグ・CI対応
- `--sentence-silence` / `--phoneme-silence`: 無音制御
- `--list-models` 言語フィルタ: `--list-models ja`
- 環境変数: PIPER_DEFAULT_MODEL, PIPER_DEFAULT_CONFIG, PIPER_MODEL_DIR

**実装:** `src/rust/piper-core/`, `src/rust/piper-cli/`, `src/rust/piper-python/`

### JavaScript/WASM npm パッケージ (piper-plus)

ブラウザ内で完全オフラインの多言語 TTS を `npm install piper-plus` で利用可能にする npm パッケージ。eSpeak-ng 不使用 (GPL リスク回避)。

| 項目 | 詳細 |
|------|------|
| パッケージ名 | piper-plus |
| バージョン | 0.3.1 |
| 対応言語 | JA, EN, ZH, KO, ES, FR, PT, SV (8言語) |
| 音素化 | piper-plus-g2p WASM (8言語、@piper-plus/g2p) |
| 推論 | onnxruntime-web (peerDependency) |
| テスト | ~1200テスト (JS Node.js test runner) + 34テスト (Rust native) + 22テスト (wasm-bindgen-test) |
| CI | ci.yml (PR/push), npm-publish.yml (タグトリガー), wasm-build.yml (WASM ビルド + feature flag 組み合わせ) |
| ビルド | ブラウザ専用 (Node.js 非対応) |

**コアクラス:**
- `PiperPlus` — 高レベル API (initialize → synthesize → AudioResult)
- `ModelManager` — HuggingFace モデル DL + IndexedDB キャッシュ
- `G2P` (@piper-plus/g2p) — Rust WASM 音素化 (8言語対応、`phonemize()`, `encode()`, `dispose()`)
- `AudioResult` — WAV エンコード + 再生 + ダウンロード

**実装:** `src/wasm/openjtalk-web/src/`, `src/rust/piper-wasm/`, `src/wasm/openjtalk-web/types/index.d.ts`
**テスト:** `src/wasm/openjtalk-web/test/js/test-*.js`, `src/wasm/g2p/test/`, `src/rust/piper-wasm/src/lib.rs`
**npm README:** `src/wasm/openjtalk-web/README.npm.md`
**WASM ビルド CI:** `.github/workflows/wasm-build.yml`

### OpenAI 互換 TTS API

FastAPI ベースの OpenAI 互換 TTS エンドポイント。既存の OpenAI クライアントからそのまま利用可能。

| エンドポイント | メソッド | 説明 |
|-------------|--------|------|
| `/v1/audio/speech` | POST | 音声合成 (OpenAI互換) |
| `/v1/models` | GET | モデル一覧 |
| `/v1/audio/speech/languages` | GET | 対応言語一覧 |
| `/health` | GET | ヘルスチェック |
| `/api/phoneme-timing` | POST/GET | Phoneme Timing 出力 (JSON/TSV) |

**実装:** `docker/python-inference/inference.py`
**テスト:** `docker/python-inference/test_openai_api.py`

### C API 共有ライブラリ (libpiper_plus)

C ABI 互換の共有ライブラリ。opaque handle パターン、ストリーミングコールバック、カスタム辞書、音素タイミング対応。Dart FFI / Godot GDExtension サンプル付き。

**ビルド:** `cmake -B build -DPIPER_PLUS_BUILD_SHARED=ON && cmake --build build`
**実装:** `src/cpp/piper_plus.h` (ヘッダー), `src/cpp/piper_plus_c_api.cpp`, `cmake/PiperPlusShared.cmake`
**テスト:** `src/cpp/tests/test_c_api.cpp`, `test_c_api_integration.cpp`, `test_c_api_audio_regression.cpp`
**FFIサンプル:** `examples/c-api/` (C), `examples/dart/` (Dart), `examples/godot/` (Godot)
**リリースCI:** `.github/workflows/release-shared-lib.yml` (Linux/macOS/Windows)

### Go 推論バインディング (piper-plus)

Go による ONNX 推論バインディング。8言語 G2P、HTTP サーバー、ストリーミング対応。

| 項目 | 詳細 |
|------|------|
| モジュール | `github.com/ayutaz/piper-plus/src/go` |
| G2P モジュール | `github.com/ayutaz/piper-plus/src/go/phonemize` (独立) |
| 対応言語 | JA, EN, ZH, KO, ES, FR, PT, SV (8言語) |
| テスト | 793テスト (piperplus + phonemize) |
| CI | 3 OS (go-ci.yml) |
| ビルド | `cd src/go && go build ./cmd/piper-plus` |

**実装:** `src/go/piperplus/`, `src/go/phonemize/`, `src/go/cmd/piper-plus/`
**サンプル:** `src/go/examples/` (basic, batch, pool, server, streaming)

### piper-plus-g2p 独立 G2P パッケージ

4言語実装の独立 G2P パッケージ。TTS エンジンなしで音素化のみ利用可能。

| 言語 | パッケージ | レジストリ |
|------|----------|----------|
| Python | `piper-plus-g2p` | PyPI |
| Rust | `piper-plus-g2p` | crates.io |
| JS/WASM | `@piper-plus/g2p` | npm |
| Go | `github.com/.../src/go/phonemize` | Go module |

**実装:** `src/python/g2p/`, `src/rust/piper-plus-g2p/`, `src/wasm/g2p/`, `src/go/phonemize/`
**CI:** `g2p-python-ci.yml`, `g2p-rust-ci.yml`, `g2p-wasm-ci.yml`, `g2p-cross-platform-ci.yml`

### WebUI (Gradio)

Gradio ベースの Web UI。6言語マルチリンガルモデル対応、Docker で起動。

**実装:** `docker/webui/app.py`
**Docker:** `docker/webui/Dockerfile`, `docker/webui/docker-compose.yml`
**CI:** `.github/workflows/webui-test.yml`
**ドキュメント:** `docs/features/webui.md`

### Speaker Encoder (ECAPA-TDNN)

Voice Cloning 用の話者エンコーダー。ECAPA-TDNN アーキテクチャで 256 次元 L2 正規化 embedding を出力。参照音声から話者特徴を抽出し、未知の話者の声質でTTS合成を可能にする。

**実装:** `src/python/piper_train/speaker_encoder/` (`ecapa_tdnn.py`, `audio_utils.py`, `encoder.py`, `export_encoder.py`, `evaluate.py`)
**テスト:** `test/test_speaker_encoder.py`

### Speaker Embedding 入力パス (--speaker-embedding)

ONNX 推論時に `speaker_embedding` テンソルで声質を指定。mask パターンで Optional 入力を実現し、speaker_id と speaker_embedding を排他的に使用可能。Speaker Encoder で抽出した embedding を直接渡して未知話者の合成ができる。

**CLIオプション:** `--speaker-embedding`, `--reference-audio`, `--speaker-encoder-model`
**実装:** `vits/models.py` (`infer`), `export_onnx.py`, `infer_onnx.py`
**テスト:** `tests/test_speaker_embedding.py`

### 全ランタイム Voice Cloning 統合

5 ランタイム (Rust/C#/Go/WASM/C++) に Speaker Encoder + speaker_embedding 対応を統合。参照音声から話者 embedding を抽出し、任意の声質で合成可能。

**CLI:** 全ランタイムで `--reference-audio`, `--speaker-embedding`, `--speaker-encoder-model`
**実装:** 各ランタイムの `speaker_encoder.{rs,cs,go,js}` + engine 修正

### SSML 基本サポート (4ランタイム)

`<speak>`, `<break>`, `<prosody rate="...">` を Python/Rust/C#/Go の 4 ランタイムで実装。W3C SSML サブセット準拠。

**実装:**
- Python: `src/python/g2p/piper_plus_g2p/ssml.py`
- Rust: `src/rust/piper-core/src/ssml.rs`
- C#: `src/csharp/PiperPlus.Core/Ssml/SsmlParser.cs`
- Go: `src/go/piperplus/ssml/parser.go`
- ランタイム: `src/python_run/piper/phonemize/ssml.py`

**テスト:** Python 62, Rust 39, C# 59, Go 67 テスト

### MOS ベンチマークツール

MOS (Mean Opinion Score) 評価用のサンプル生成、メトリクス計算 (PESQ/STOI 等)、調査フォーム生成ツール。モデル品質の定量的評価を支援。

**実装:** `tools/benchmark/` (`generate_samples.py`, `compute_metrics.py`, `generate_mos_survey.py`, `models.yaml`)
**ドキュメント:** `docs/benchmark-mos.md`

### iOS/Android ビルド CI

libpiper_plus のモバイルクロスコンパイル。iOS (arm64) と Android (arm64-v8a/armeabi-v7a/x86_64) のネイティブ共有ライブラリをCIで自動ビルド。

**実装:** `.github/workflows/release-shared-lib.yml` (`build-ios`, `build-android`), `cmake/ios.toolchain.cmake`

### モデル投稿ガイド

コミュニティモデル投稿のガイドラインと GitHub Issue テンプレート。モデル公開時の品質基準・ライセンス要件を明文化。

**実装:** `CONTRIBUTING_MODELS.md`, `.github/ISSUE_TEMPLATE/model-request.yml`, `.github/ISSUE_TEMPLATE/model-submission.yml`

### Wyoming Docker + HA 統合

Wyoming Protocol TTS の Docker 環境と Home Assistant 統合ガイド。Docker Compose で Wyoming TTS サーバーを起動し、HA から piper-plus を利用可能。

**実装:** `docker/wyoming/` (`Dockerfile`, `docker-compose.yml`, `.env.example`, `README.md`)
**ドキュメント:** `docs/guides/home-assistant.md`

### 短テキスト合成品質改善

短テキスト (1-2文節) 合成時のノイズ・歪み・0秒出力問題に対する緩和策。VITS アーキテクチャの構造的制限に起因する既知の問題 (rhasspy/piper#252) に対し、3つの Strategy を全ランタイムに並列実装。

| Strategy | 手法 | 効果 | 対象ランタイム |
|----------|------|------|-------------|
| A | Silence Padding + Post-trim | 高 | 全7ランタイム |
| B | Dynamic Scales Adjustment | 中 | 全7ランタイム |
| C | SSML `<break>` Auto-injection | 中 | Python/Rust/C#/Go (SSML対応4ランタイム) |

**設定仕様:** `docs/spec/short-text-contract.toml`

### ストリーミング文単位分割

複数文を含むテキストを `.`/`!`/`?`/`。`/`！`/`？` で分割し、文ごとに音素化・推論・チャンク yield することで真のストリーミング配信を実現。終止符直後の閉じ括弧 (`」 』 ） ］ 】 ｣ ” ’ »` 等) は前文に吸収。SSML (`<speak>...`) 入力は単一ユニットとして扱い構造を保持。

**対応ランタイム:** Python (新規追加)、Rust、C++、C#、Go、JS-WASM (Rust 経由)

**設定仕様:** `docs/spec/text-splitter-contract.toml`

**実装:**
- Python: `src/python_run/piper/text_splitter.py` (`split_sentences()`) — Rust 実装をベースに移植
- 旧 `PiperVoice.phonemize()` は単一文しか返さなかったため、HTTP `?streaming=true` も実質1チャンクで送信されていた問題を解消

**テスト:** `tests/test_text_splitter.py` (18件)、`tests/test_voice_streaming.py` (8件)

**関連:** Zenn スクラップ ([kun432 氏](https://zenn.dev/kun432/scraps/cddbfcd75b8b34))、PR #361 (FastAPI 移行) の続編

### Phoneme Timing 出力

VITS Duration Predictor の出力から音素ごとの開始時刻・終了時刻・継続時間を抽出し JSON/TSV/SRT 形式で出力する機能。リップシンク、字幕生成、カラオケアプリケーション向け。Rust/Go/C++/C# の既存実装と byte-for-byte 互換 (`(hop_length / sample_rate) * 1000` 計算式)。

**対応ランタイム:** Python, JavaScript/WASM (新規追加)、Rust, Go, C++, C# (既存)

**対応形式:** JSON (pretty/compact), TSV (header付き), SRT (字幕用)

**Python API:**
- `PiperVoice.synthesize_with_timing(text, ...) -> tuple[bytes, TimingResult | None]`
- `PiperVoice.has_duration_output -> bool` (モデル対応判定)
- `piper.timing.durations_to_timing()`, `timing_to_json/tsv/srt()`, `build_phoneme_id_reverse_map()`
- HTTP エンドポイント: `POST /api/phoneme-timing` (`format=json|tsv` クエリ対応)

**WASM API:**
- `AudioResult.timing -> TimingResult | null` (deep frozen, immutable)
- `AudioResult.hasTimingInfo -> boolean`
- メインエクスポート + `./timing` サブパスで `durationsToTiming`, `timingToJson/Tsv/Srt`, `buildPhonemeIdToTokenMap` 利用可能
- TypeScript 型定義完備 (`PhonemeTimingInfo`, `TimingResult`)

**設計:**
- `PiperConfig.hop_size` (デフォルト 256) を config.json から読込
- 短文 padding 適用時も `originalPhonemeIds` を保持し timing 計算
- 負の duration は警告ログ付きで 0 にクランプ
- NaN/Infinity validation で TypeError、長さ不一致で RangeError

**実装:**
- Python: `src/python_run/piper/timing.py`, `src/python_run/piper/voice.py`, `src/python_run/piper/http_server.py`
- WASM: `src/wasm/openjtalk-web/src/timing.js`, `src/wasm/openjtalk-web/src/audio-result.js`, `src/wasm/openjtalk-web/src/index.js`

**テスト:**
- Python: `test_phoneme_timing.py` (44件), `test_voice_timing.py` (22件), `test_http_timing.py` (14件), `test_config_fallback.py` (hop_size 5件)
- WASM: `test-phoneme-timing.js` (66件), `test-audio-result-timing.js` (18件), `test-piper-plus-timing.js` (22件)
- クロスランタイム互換性: Rust/Go/C++/C# の既存テストと同じ計算結果

**関連 PR/コミット:**
- Python: feat(python) phoneme timing 機能追加
- WASM: feat(wasm) phoneme timing 機能追加 + refactor(wasm) 品質向上

---

## 重要なファイルパス

### ソースコード

| 用途 | パス |
|------|------|
| 学習スクリプト | `src/python/piper_train/__main__.py` |
| VITS実装 | `src/python/piper_train/vits/` |
| G2P パッケージ (Python) | `src/python/g2p/piper_plus_g2p/` |
| Phonemizer ABC | `src/python/g2p/piper_plus_g2p/base.py` |
| 言語レジストリ | `src/python/g2p/piper_plus_g2p/registry.py` |
| 日本語音素化 | `src/python/g2p/piper_plus_g2p/japanese.py` |
| 英語音素化 | `src/python/g2p/piper_plus_g2p/english.py` |
| 中国語音素化 | `src/python/g2p/piper_plus_g2p/chinese.py` |
| 韓国語音素化 | `src/python/g2p/piper_plus_g2p/korean.py` |
| スペイン語音素化 | `src/python/g2p/piper_plus_g2p/spanish.py` |
| ポルトガル語音素化 | `src/python/g2p/piper_plus_g2p/portuguese.py` |
| フランス語音素化 | `src/python/g2p/piper_plus_g2p/french.py` |
| スウェーデン語音素化 | `src/python/g2p/piper_plus_g2p/swedish.py` |
| ランタイム Phonemizer | `src/python_run/piper/phonemize/` |
| トークンマッパー | `src/python_run/piper/phonemize/token_mapper.py` |
| ONNXエクスポート | `src/python/piper_train/export_onnx.py` |
| 推論スクリプト | `src/python/piper_train/infer_onnx.py` |
| ORT セッション管理 | `src/python/piper_train/ort_utils.py` |
| 言語横断パラメータ仕様 | `docs/spec/ort-session-contract.toml` |
| OpenAI TTS API | `docker/python-inference/inference.py` |
| WebUI | `docker/webui/app.py` |
| Speaker Encoder | `src/python/piper_train/speaker_encoder/` |
| SSML (Python) | `src/python/g2p/piper_plus_g2p/ssml.py` |
| SSML (ランタイム) | `src/python_run/piper/phonemize/ssml.py` |
| Phoneme Timing (Python) | `src/python_run/piper/timing.py` |
| テキスト分割 (Python) | `src/python_run/piper/text_splitter.py` |

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
| 韓国語音素化 | `src/csharp/PiperPlus.Core/Phonemize/KoreanPhonemizer.cs` |
| スウェーデン語音素化 | `src/csharp/PiperPlus.Core/Phonemize/SwedishPhonemizer.cs` |
| マルチリンガルPhonemizer | `src/csharp/PiperPlus.Core/Phonemize/MultilingualPhonemizer.cs` |
| PUAマッピング | `src/csharp/PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs` |
| 設定管理 | `src/csharp/PiperPlus.Core/Config/` |
| 辞書マネージャ | `src/csharp/PiperPlus.Core/Config/DictionaryManager.cs` |
| テキスト分割 | `src/csharp/PiperPlus.Core/Phonemize/TextSplitter.cs` |
| インライン音素パーサー | `src/csharp/PiperPlus.Core/Phonemize/InlinePhonemeParser.cs` |
| Raw音素パーサー | `src/csharp/PiperPlus.Core/Phonemize/RawPhonemeParser.cs` |
| モデルマネージャ | `src/csharp/PiperPlus.Core/Config/ModelManager.cs` |
| SSML パーサー | `src/csharp/PiperPlus.Core/Ssml/SsmlParser.cs` |

### Rust ソースコード

| 用途 | パス |
|------|------|
| ワークスペース | `src/rust/Cargo.toml` |
| コアライブラリ | `src/rust/piper-core/` |
| CLI アプリケーション | `src/rust/piper-cli/` |
| Python バインディング | `src/rust/piper-python/` |
| 音素化 | `src/rust/piper-core/src/phonemize/` |
| 音素変換 (SynthesisRequestData) | `src/rust/piper-core/src/phonemize/phoneme_converter.rs` |
| 推論エンジン | `src/rust/piper-core/src/engine.rs` |
| 辞書マネージャ | `src/rust/piper-core/src/dictionary_manager.rs` |
| カスタム辞書テスト | `src/rust/piper-core/tests/test_custom_dict_integration.rs` |
| デフォルト出力テスト | `src/rust/piper-core/tests/test_default_output.rs` |
| SSML | `src/rust/piper-core/src/ssml.rs` |
| WASM 音素化 | `src/rust/piper-wasm/` |
| G2P パッケージ | `src/rust/piper-plus-g2p/` |

### npm パッケージ ソースコード

| 用途 | パス |
|------|------|
| エントリーポイント | `src/wasm/openjtalk-web/src/index.js` |
| モデルマネージャ | `src/wasm/openjtalk-web/src/model-manager.js` |
| 音声結果 | `src/wasm/openjtalk-web/src/audio-result.js` |
| Phoneme Timing (WASM) | `src/wasm/openjtalk-web/src/timing.js` |
| Rust WASM ビルド成果物 | `src/wasm/openjtalk-web/dist/rust-wasm/` |
| TypeScript型定義 | `src/wasm/openjtalk-web/types/index.d.ts` |
| npm パッケージ設定 | `src/wasm/openjtalk-web/package.json` |
| npm publish CI | `.github/workflows/npm-publish.yml` |
| WASM ビルド CI | `.github/workflows/wasm-build.yml` |

### Go ソースコード

| 用途 | パス |
|------|------|
| メインモジュール | `src/go/` |
| コアパッケージ | `src/go/piperplus/` |
| G2P パッケージ | `src/go/phonemize/` |
| CLI | `src/go/cmd/piper-plus/` |
| SSML パーサー | `src/go/piperplus/ssml/parser.go` |
| サンプル | `src/go/examples/` |

### C API ソースコード

| 用途 | パス |
|------|------|
| ヘッダー | `src/cpp/piper_plus.h` |
| 実装 | `src/cpp/piper_plus_c_api.cpp` |
| CMake | `cmake/PiperPlusShared.cmake` |
| テスト | `src/cpp/tests/test_c_api*.cpp` |
| FFI サンプル | `examples/c-api/`, `examples/dart/`, `examples/godot/` |

### ベンチマーク・ツール

| 用途 | パス |
|------|------|
| サンプル生成 | `tools/benchmark/generate_samples.py` |
| メトリクス計算 | `tools/benchmark/compute_metrics.py` |
| MOS 調査フォーム生成 | `tools/benchmark/generate_mos_survey.py` |
| モデル設定 | `tools/benchmark/models.yaml` |

### Wyoming Docker

| 用途 | パス |
|------|------|
| Docker 環境 | `docker/wyoming/` |
| Dockerfile | `docker/wyoming/Dockerfile` |
| Docker Compose | `docker/wyoming/docker-compose.yml` |
| HA 統合ガイド | `docs/guides/home-assistant.md` |

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
| **多言語 6lang MB-iSTFT** (feat/mb-istft-vits2) | `/data/piper/output-multilingual-6lang-mb-istft/multilingual-6lang-mb-istft-scratch-75epoch.onnx` | 75 epoch完了 (2026-04-16) -- スクラッチ学習、epoch=74-step=500034.ckpt、571話者、Issue #268/PR #320 |
| **つくよみちゃん MB-iSTFT** (feat/mb-istft-vits2) | `/data/piper/output-tsukuyomi-mb-istft-finetune/tsukuyomi-mb-istft-500epoch.onnx` | 500 epoch完了 (2026-05-02) -- 6lang MB-iSTFT ベースから FT、1話者、Issue #268/PR #320 |
| **CSS10 JA 6lang** | `/data/piper/css10-ja-ljspeech/` -> `test/models/multilingual-test-medium.onnx` | 50 epoch完了 (2026-03-16) -- 6langベースから転移、6,841発話 |
| バイリンガル JA+EN v4 (参照) | `/data/piper/output-bilingual-ja-en-v4/bilingual-ja-en-v4-150epoch.onnx` | 150 epoch完了 (75MB, 2026-03-04) -- EMA適用済み |

### 便利ツール

| ツール | パス | 用途 |
|--------|------|------|
| `prepare_multilingual_dataset.py` | `src/python/piper_train/tools/prepare_multilingual_dataset.py` | 6言語マルチリンガルデータセット作成 |
| `add_prosody_features.py` | `src/python/piper_train/tools/add_prosody_features.py` | 既存データセットにprosody_features追加+phoneme_ids再生成 |
| `prepare_bilingual_dataset.py` | `src/python/piper_train/tools/prepare_bilingual_dataset.py` | JA+ENバイリンガルデータセット作成 |
| `prepare_libritts_parallel.py` | `/data/piper/prepare_libritts_parallel.py` | LibriTTS-R -> LJSpeech形式変換（並列処理） |
| `generate_samples.py` | `tools/benchmark/generate_samples.py` | MOS評価用サンプル生成 |
| `compute_metrics.py` | `tools/benchmark/compute_metrics.py` | PESQ/STOI等メトリクス計算 |
| `generate_mos_survey.py` | `tools/benchmark/generate_mos_survey.py` | MOS調査フォーム生成 |

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
| `--no-fp16` | - | FP16変換を無効化（デフォルト: FP16有効、モデルサイズ~50%削減） |
| `--unify-emb-lang` / `--no-unify-emb-lang` | auto | emb_lang 自動統一（シングルスピーカー多言語モデルで自動有効化） |
| `--unify-emb-lang-source N` | 0 | emb_lang 統一のソース言語インデックス |
| `--simplify` | - | ONNX モデル simplification を適用 |
| `--debug` | - | デバッグログ出力 |
| EMA | 常時有効 | チェックポイントに EMA state があれば自動適用（CLIオプションではない） |

### Voice Cloning 推論 (speaker_embedding)

```bash
# 参照音声から話者 embedding を抽出して合成
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/model.onnx \
  --config /path/to/config.json \
  --output-dir /path/to/output \
  --text "こんにちは" \
  --reference-audio /path/to/reference.wav \
  --speaker-encoder-model /path/to/speaker_encoder.onnx \
  --language ja-en-zh-es-fr-pt
```

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
