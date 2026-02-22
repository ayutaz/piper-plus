# Piper TTS - プロジェクト概要

Piper TTSは高品質なニューラルテキスト音声合成システムです。VITSアーキテクチャを採用し、日本語を含む多言語に対応しています。

---

## ✅ 現在の状態: enhanced-fixed データセットで再学習準備中

**ブランチ**: `feat/bilingual-phonemizer`

### 正式データセット: `dataset-bilingual-ja-en-enhanced-fixed`

| 項目 | 値 |
|------|-----|
| データセット | `dataset-bilingual-ja-en-enhanced-fixed` |
| 発話数 | **120,142** (JA=60,148 + EN=59,994) — JA:EN ≒ 1:1 |
| 話者数 | 21 (JA 20話者 + EN 1話者 LJSpeech) |
| 言語数 | 2 (ja=0, en=1) |
| シンボル数 | 97 |
| 状態 | **Pod再起動後に1 epoch検証 → 本学習開始** |

### データセット整理 (2026-02-21)

開発過程で増えた不要データセット・outputを一括削除し、ディスクを整理した。

**実施内容:**
1. **JAキャッシュ統合**: `dataset-bilingual-ja-en-multispeaker/cache/` からJAキャッシュ120,296ファイルを `dataset-bilingual-ja-en-enhanced-fixed/cache/` に移動。`dataset.jsonl` のパスも更新し、enhanced-fixedを完全自己完結に
2. **不要データセット削除** (14件): enhanced, backup, v2, multispeaker, test系, css10, tsukuyomi等
3. **不要output削除** (4件): multispeaker-v2, enhanced-test, enhanced, multispeaker
4. **整合性検証済み**: 120,142エントリ全ての `audio_norm_path` / `audio_spec_path` が存在することを確認

| 項目 | 削除前 | 削除後 |
|------|--------|--------|
| ディスク使用量 | 808G (40%) | **695G (34%)** |
| dataset-* 数 | 15 | **2** |
| output-* 数 | 8 | **4** |

### 次のステップ (TODO)

1. ✅ **Pod再起動**: GPU 復旧済み
2. ✅ **1 epoch検証学習**: 正常完了
3. ✅ **本学習 (200 epoch) 開始**: `--audio-log-epochs 0` で epoch 10 から学習中 (PID: 14574)
4. **⚠️ audio logging 再有効化**: 学習完了後の次回 run で `--audio-log-epochs 5` を追加（barrier fix 済み）
5. **不要チェックポイント削除**: `output-bilingual-ja-en/lightning_logs/version_28/checkpoints/` に全200エポック分 (~176GB) が残存。`epoch=199` と `last.ckpt` 以外は削除してディスク節約可能
6. **HuggingFaceアップロード**: バイリンガルモデル (ONNX + config.json) の公開

### 旧バイリンガルモデル (200 epoch完了、旧データセット)

旧データセット `dataset-bilingual-ja-en` (73,148発話、EN比率18%) で学習したモデル。英語の発音が不明瞭だったため、EN比率50%の `enhanced-fixed` で再学習予定。

```
/data/piper/output-bilingual-ja-en/
├── lightning_logs/version_28/checkpoints/
│   ├── epoch=199-step=218400.ckpt  ← 最終チェックポイント
│   └── last.ckpt
└── bilingual-ja-en-200epoch.onnx  ← ONNX推論用モデル (74MB, EMA適用済み)
```

### 学習開始コマンド (enhanced-fixed、0→200 epoch)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-bilingual-ja-en-enhanced-fixed \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --default_root_dir /data/piper/output-bilingual-ja-en-enhanced-fixed \
  > /data/piper/training_enhanced_fixed.log 2>&1 &
```

**注意:** `--precision 32-true` でFP32学習（V100ではFP16-mixedのbackwardが異常に遅いため必須）。`--no-wavlm` でWavLM Discriminatorを無効化し、batch-size 20で学習。`--max-phoneme-ids 400` で長いシーケンスを除外しメモリスパイクを防止。

### 推論テスト (旧モデル)

**日本語:**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en/bilingual-ja-en-200epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en-enhanced-fixed/config.json \
  --output-dir /home/jovyan \
  --text "こんにちは、今日は良い天気ですね。" \
  --language ja-en --speaker-id 0 --noise-scale 0.5
```

**英語:**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en/bilingual-ja-en-200epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en-enhanced-fixed/config.json \
  --output-dir /home/jovyan \
  --text "Hello, how are you today?" \
  --language ja-en --speaker-id 20 --noise-scale 0.5
```

**混合テキスト (コードスイッチング):**
```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-bilingual-ja-en/bilingual-ja-en-200epoch.onnx \
  --config /data/piper/dataset-bilingual-ja-en-enhanced-fixed/config.json \
  --output-dir /home/jovyan \
  --text "今日はgood morningですね" \
  --language ja-en --speaker-id 0 --noise-scale 0.5
```

### V100 FP32 / WavLM無効の経緯

**FP32切り替え (2026-02-11):** `--precision 16-mixed` 使用時、Generator の backward pass が29-40秒かかり全体速度が 0.03 it/s に低下。`--precision 32-true` で backward が 0.7-1.1s に改善、全体速度 **0.45 it/s** (15倍高速化)。FP32でもGPU peak 13.7GB/16GB で V100に収まる。

**WavLM無効化 (2026-02-11):** WavLM有効時の学習速度が極めて遅く、完了まで推定19日。`--no-wavlm` で短縮。事前学習フェーズでは `--no-wavlm` で十分。

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

### 学習高速化 ✅ NEW (2026-02-19)

Validation頻度削減、DataLoader最適化、LRスケジューラ修正、DDP最適化により学習スループットを向上。

**変更内容:**

| 項目 | 変更前 | 変更後 | 効果 |
|------|--------|--------|------|
| Validation頻度 | 毎エポック | 5エポックごと (`--val-every-n-epochs 5`) | Validation overhead 80%削減 |
| Validation バッチ数 | 全データ | 50バッチ (`--limit-val-batches 50`) | Validation時間短縮 |
| DataLoader num_workers | 0 | 2 | データ読み込み並列化 |
| DataLoader pin_memory | 無効 | 有効（デフォルト） | GPU転送高速化 |
| LRスケジューラ | エポック終了時に未ステップ | `on_train_epoch_end` で手動ステップ | 学習率が正しく減衰 |
| DDP strategy | `static_graph=True`（誤設定） | `find_unused_parameters=True` + `gradient_as_bucket_view=True` | GAN交互学習の未使用パラメータを正しく処理 |
| `__getitem__` スレッドセーフ | `pop(idx)` でリスト変更 | インデックスアクセスのみ | マルチワーカー安全 |

**新規CLIオプション:**
- `--val-every-n-epochs N` — Validation実行頻度（デフォルト: 5）
- `--limit-val-batches N` — Validation時の最大バッチ数（デフォルト: 50）

**デフォルト変更:**
- `--num-workers`: 0 → 2（明示的に `--num-workers 0` で旧動作に戻せる）
- `pin_memory`: 無効 → 有効（`--no-pin-memory` で無効化可能）

**実装ファイル:**
- `src/python/piper_train/__main__.py` — 新CLI引数追加、num_workersデフォルト変更
- `src/python/piper_train/vits/lightning.py` — `on_train_epoch_end()` LRスケジューラ修正、DDP `find_unused_parameters=True`
- `src/python/piper_train/vits/dataset.py` — `__getitem__` スレッドセーフ修正

**テストファイル (19テスト、4ファイル):**
- `src/python/tests/test_model_config.py` — CLI引数デフォルト値テスト
- `src/python/tests/test_dataset_getitem.py` — `__getitem__` スレッドセーフテスト
- `src/python/tests/test_ddp_strategy.py` — DDP strategy設定テスト
- `src/python/tests/test_lr_scheduler.py` — LRスケジューラステップテスト

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
  --config /data/piper/dataset-bilingual-ja-en-enhanced-fixed/config.json \
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

**Phase C 状況:** 旧データセット (73,148発話、EN比率18%) で200 epoch学習完了 (2026-02-14)。enhanced-fixedデータセット (120,142発話、EN比率50%) で再学習予定

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

### WandB Audio Logging ✅ NEW (2026-02-14)

Validation時に生成される音声サンプルをWandBに自動アップロード。

**機能:**
- 毎エポック2サンプルを WandB Table 形式でログ（メモリ最適化版）
- リッチメタデータ: テキスト、話者ID、言語ID、エポック、ステップ、合成パラメータ
- WandBダッシュボードでブラウザ再生可能
- バイリンガル（ja/en）、マルチスピーカー（21話者）対応
- Graceful fallback: WandB未設定時は音声ログスキップ（学習継続）

**使用方法:**
```bash
# WandB APIキー設定（必須）
export WANDB_API_KEY=your_key_here

# 学習開始（自動で音声ログ有効）
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-bilingual-ja-en-enhanced-fixed \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 200 --batch-size 20 --no-wavlm \
  --audio-log-epochs 1 \
  --default_root_dir /data/piper/output-bilingual-ja-en-enhanced-fixed
```

**WandB UI での確認:**
1. https://wandb.ai/yourusername/piper-tts にアクセス
2. Run を選択
3. "validation_audio_samples" テーブルを開く
4. 音声を再生、メタデータで絞り込み可能

**Table Schema:**
- text: 元テキスト
- speaker: 話者ID（"spk=0" 形式）
- language: 言語コード（"ja" または "en"）
- epoch: エポック番号
- step: グローバルステップ
- audio: 再生可能な音声ウィジェット

**実装ファイル:**
- `src/python/piper_train/vits/lightning.py` - `on_validation_epoch_end()` でWandB Table形式ログ、`_get_wandb_logger()` ヘルパーメソッド
- `src/python/piper_train/__main__.py` - WandbLogger設定（TensorBoardLoggerと併用）

**実装の詳細:**
- PyTorch Lightning 2.x系では、複数ロガーは `trainer.loggers`（複数形）で管理される
- `_get_wandb_logger()` が `trainer.loggers` をチェックしてWandBLoggerを取得
- Validation epoch終了時に2サンプルの音声を生成し、WandB Table形式でログ
- エラーハンドリング: WandB未設定時は音声ログをスキップ（学習は継続）

**メモリ最適化 (2026-02-14更新):**
- **Generator メモリリークバグを修正** (models.py:360) — `torch.zeros(1)` によるCPUスカラー生成を `xs = None` 初期化に変更、In-place演算 (`xs +=`) を非In-place (`xs = xs +`) に変更
- **サンプル数を5→2に削減** (`--num-test-examples 2`) — メモリ使用量60%削減
- **積極的GPUメモリクリーンアップ** — 各サンプル生成後に `torch.cuda.synchronize()` + `empty_cache()`
- **学習ステップ後にインスタンス変数をクリア** — `_y`, `_y_hat` を `None` に設定してメモリ解放
- **定期的メモリクリーンアップに同期追加** — 500イテレーションごとの `empty_cache()` 前に `synchronize()`

**パフォーマンス最適化:**
- 音声ログは `on_validation_epoch_end()` で実行（validation_stepをブロックしない）
- `torch.no_grad()` + 明示的なメモリクリーンアップで効率化
- `--audio-log-epochs N` フラグで頻度制御（デフォルト: 1）
  - 例: `--audio-log-epochs 5` で5エポックごとにログ
  - `--audio-log-epochs 0` で音声ログを完全に無効化
- `--num-test-examples N` でサンプル数を制御（デフォルト: 2）
  - 例: `--num-test-examples 1` で最小メモリ使用

**⚠️ DDP NCCL タイムアウトバグと現状 (2026-02-22)**

マルチGPU DDP 学習中に `on_validation_epoch_end()` の WandB audio logging が NCCL ALLREDUCE タイムアウト（30分）を引き起こすバグが確認された。

**症状:** validation 後の training step で全ランクが NCCL タイムアウトでクラッシュ

**根本原因:** `on_validation_epoch_end()` で rank 0 が WandB アップロード（同期 I/O）を実行している間に Lightning が ranks 1-3 を次の training step へ進め、rank 0 が ALLREDUCE に参加できなくなる

**実施済み修正 (2026-02-22):**
1. `on_validation_epoch_end()` を `is_global_zero` ブロックで囲む（early return を廃止）
2. 関数末尾に `torch.distributed.barrier()` を追加し、全ランクが同期してから次 epoch へ進むように変更

**現在の運用 (enhanced-fixed 200epoch 学習中):**
- `--audio-log-epochs 0` で audio logging を**一時的に無効化**して学習を安定させている
- この学習が完了したら `--audio-log-epochs 5` を付けて次回 run で有効化する

**次回 run での有効化手順:**
```bash
# barrier fix 済みのため audio logging を再有効化可能
--audio-log-epochs 5  # validation 頻度 (val_every_n_epochs=5) に合わせる
```

**トラブルシューティング:**
- CUDAメモリエラーが発生する場合:
  1. `--audio-log-epochs 10` で頻度を下げる
  2. `--num-test-examples 1` でサンプル数をさらに削減
  3. `--audio-log-epochs 0` で完全無効化
- 学習速度を最優先する場合: `--audio-log-epochs 0` で無効化

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

### 推奨設定 (20話者、V100 GPU 16GB × 4、WavLM無効)

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-moe-speech-20speakers-v2 \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --no-wavlm \
  --default_root_dir /data/piper/output-moe-speech-20speakers-v2
```

**注意:** V100では `--precision 32-true` を使用すること（FP16-mixedはbackward passが極端に遅くなる）。WavLMはデフォルトで有効。`--no-wavlm` で無効化するとbatch-size 20が使用可能に。WavLM有効時は16GBでbatch-size 20でOOM発生するため batch-size 12 が必要。

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
| **バイリンガル JA+EN** ✅正式 | `/data/piper/dataset-bilingual-ja-en-enhanced-fixed/` | 120,142 | JA 60,148 + EN 59,994、21話者、97シンボル、JA:EN≒1:1 |
| 20話者 v2 (JA-only) 参照用 | `/data/piper/dataset-moe-speech-20speakers-v2/` | 60,164 | Issue #204, #207 対応 |

### 学習済み/学習中モデル

| 用途 | パス | 状態 |
|------|------|------|
| バイリンガル JA+EN (旧データセット) | `/data/piper/output-bilingual-ja-en/bilingual-ja-en-200epoch.onnx` | ✅ 200 epoch完了 (74MB) — EN比率18%で英語不明瞭 |
| **バイリンガル JA+EN (enhanced-fixed)** | `/data/piper/output-bilingual-ja-en-enhanced-fixed/` | 未開始 — enhanced-fixedデータセットで再学習予定 |
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
  --output-dir /data/piper/dataset-bilingual-ja-en-enhanced-fixed \
  --sample-rate 22050 --max-en-utterances 60000 --workers 8
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
4. `--val-every-n-epochs 10` でValidation頻度を下げる（デフォルト: 5エポックごと）
5. `--limit-val-batches 20` でValidationバッチ数を削減（デフォルト: 50）

**注意**: WavLM有効時の学習速度は ~0.03 it/s と遅い (WavLM無効時の 3-5倍)。速度を優先する場合は `--no-wavlm` で無効化推奨。マルチGPU環境で `--wavlm-every-n-steps N` (N>1) は使用しないこと。`find_unused_parameters=True` との相互作用でWavLMパラメータ（~94M）の未使用同期が発生し、逆に~3x遅くなる

### GPU が認識されない (CUDA_ERROR_NO_DEVICE)

**症状**: `nvidia-smi` が `Failed to initialize NVML: Unknown Error`、`torch.cuda.is_available()` が `False`、`cuInit()` が 100 (CUDA_ERROR_NO_DEVICE) を返す。`/dev/nvidia*` は存在するが `open()` で `EPERM`。

**原因**: Kubernetes Pod のGPUリソース割り当てが切れている。コンテナの cgroup がGPUデバイスへのアクセスをブロックしている。

**対処法**: **Podを再起動する**。再起動後に以下を確認:
```bash
nvidia-smi
/data/piper/.venv/bin/python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"
```

**経緯 (2026-02-21):** 学習完了 (02/14) 後にPodが再スケジュールされ、GPUリソースなしで起動した模様。`/dev/nvidia*` ファイルはホストノードからマウントされているが、NVIDIA device plugin によるGPU割り当てがないためアクセス拒否。

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
