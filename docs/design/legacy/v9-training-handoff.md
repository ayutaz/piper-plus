# Zero-Shot TTS v9 再学習 引き継ぎドキュメント

> ⚠️ **本書は zero-shot 20speakers (v9) 用の旧引き継ぎドキュメント**。リベース前の
> `Generator + Multi-scale FiLM` 構造を前提とした内容。dev リベース後の現状については
> [`../multi-6lang-zero-shot-v7-training-results.md`](../multi-6lang-zero-shot-v7-training-results.md)
> を参照。

**作成日**: 2026-04-03
**ブランチ**: `feat/zero-shot-tts` (commit `6d71312`)
**ベース**: `origin/dev` (`3b6ac2b` - piper-g2p)

---

## 1. 現在の状態

### ブランチ状態

- `feat/zero-shot-tts` を最新の `origin/dev` にリベース済み
- CI: push待ち（リベース後未push → `--force-with-lease`でpush済み）
- バックアップブランチ: 削除済み

### v8学習結果（話者再現に失敗 — 再学習必須）

- **ONNXモデル**: `/data/piper/output-zero-shot-20speakers-v8/zero-shot-20speakers-v8.onnx` (39MB)
- **チェックポイント**: 101個 (各848MB, 合計85GB)
- **問題**: 話者再現精度が極めて低い。未知話者のRMSが既知話者の1/10

### v8失敗の根本原因（2件 — 修正済み）

| # | バグ | 影響 | 修正コミット |
|---|------|------|-------------|
| 1 | `dataset.py` に `speaker_embeddings` フィールドがなかった | SCL/DINO/embedding摂動が200ep間ずっと**無効** | `c1ed66b` |
| 2 | `CamPPSpeakerEncoder` の入力名が `"fbank"` (正: `"input"`) | SCLのembedding抽出がValueError | `c1ed66b` |

**原因**: squash-rebase時に `dataset.py` の変更が消失。復元コミット(`09f64e6`)でも見落とされた。

---

## 2. v9再学習コマンド

```bash
WANDB_MODE=disabled NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-zero-shot-20speakers \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 4 \
  --checkpoint-epochs 2 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 4 --no-pin-memory \
  --no-wavlm \
  --spk-emb-noise-sigma 0.05 \
  --d-update-interval 1 \
  --lr-scheduler cosine --lr-warmup-epochs 5 --lr-min 1e-5 \
  --speaker-encoder-path /data/piper/models/campplus.onnx \
  --default_root_dir /data/piper/output-zero-shot-20speakers-v9
```

### 重要な注意事項

- `--c-dino` はCLI引数として**追加済み**（包括レビュー修正により有効化）。デフォルト0.5
- `--kl-annealing-epochs` はCLI引数として**追加済み**（包括レビュー修正により有効化）。デフォルト10
- `--c-spk` はCLI引数として**存在する**（`add_model_specific_args`経由）。デフォルト1.0のため省略可
- `--spk-emb-dropout` は**非推奨・無効化済み**。指定しても警告のみで無効。学習コマンドに含めないこと
- `--d-update-interval 1` は**必須**（2にするとDiscriminator崩壊）
- `--max_epochs 200` は**必須**（100epでは収束不足）
- v8のチェックポイントは削除推奨（85GB、再利用不可）

### GPU別の推奨設定

| パラメータ | T4 (15GB × 4) | A100 (80GB × 1) | RTX 6000 Ada (48GB × 1) |
|---|---|---|---|
| `--devices` | 4 | 1 | 1 |
| `--precision` | `16-mixed` | `bf16-mixed` | `bf16-mixed` |
| `--batch-size` | 20 | 160 | 120 |
| `--samples-per-speaker` | 4 | 8 | 8 |
| `--num-workers` | 4 | 8 | 8 |
| `--no-pin-memory` | 必須 | 不要 | 不要 |

---

## 3. 修正済み機能一覧（v8からの差分）

### 学習コード修正

| 機能 | ファイル | 状態 |
|------|---------|------|
| speaker_embeddings in Batch | `vits/dataset.py` | **復元済み** — Batchクラスにフィールド追加、DataLoaderで.npy読み込み |
| CamPP入力名 "input" | `vits/lightning.py:90` | **修正済み** — `"fbank"` → `"input"` |
| torchaudio遅延import | `vits/lightning.py:68` | **修正済み** — `__call__`内に移動 |
| KLアニーリング | `vits/lightning.py` | **復元済み** — 10ep、0.1→1.0線形増加 |
| DINO自己蒸留 | `vits/lightning.py` | **復元済み** — spk_proj_teacher EMA、c_dino=0.5 |
| Flow dilation_rate=2 | `vits/models.py:850` | **復元済み** |
| spk_proj EMA | `vits/ema.py` | **復元済み** |
| dataset.py無限ループ | `vits/dataset.py` | **修正済み** — while True除去 |
| prosody形式統一 | `vits/dataset.py` | **修正済み** — list[dict\|None]形式 |

### ネイティブ推論（C++/C#/Rust）

| 言語 | 状態 | 追加ファイル |
|------|------|-------------|
| C++ | 完了 | `main.cpp`, `piper.cpp`, `piper.hpp` |
| C# | 完了 | `PiperSession.cs`, `PiperModel.cs`, `Program.cs` |
| Rust | 完了 | `engine.rs`, `voice.rs`, `input.rs`, `main.rs`, `lib.rs` |

全言語で `--speaker-embedding FILE` (raw binary / .npy) + JSONL `speaker_embedding` 対応済み。

---

## 4. データセット・モデルのパス

| 用途 | パス | サイズ |
|------|------|--------|
| データセット | `/data/piper/dataset-zero-shot-20speakers/` | — |
| dataset.jsonl | 同上 `/dataset.jsonl` | 60,217発話 |
| config.json | 同上 `/config.json` | 20話者, sr=22050 |
| キャッシュ(audio+spec) | 同上 `/cache/22050/` | — |
| speaker embeddings | 同上 `/speaker_embeddings/*.npy` | 各192次元 |
| CAM++ ONNX | `/data/piper/models/campplus.onnx` | 27MB |
| v8出力（削除推奨） | `/data/piper/output-zero-shot-20speakers-v8/` | 85GB |

---

## 5. 学習中の確認ポイント

### 起動直後に確認

```text
spk_proj_teacher          │ Sequential    │  362 K │ train  ← DINO teacher存在確認
```

- `gin_channels: 512` が `hparams.yaml` にあること
- `CamPPSpeakerEncoder loaded` のログが出ること

### 学習中のログで確認

- `loss_spk` が出力されること（SCLが動作している証拠）
- `loss_dino` が出力されること（DINOが動作している証拠）
- `kl_weight` が0.1→1.0に増加すること（epoch 0-10）
- `loss_disc` が6.0固定にならないこと（D:G=1:1の効果）

### 学習完了後

```bash
# ONNX変換（zero-shotモード）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --export-mode zero-shot \
  /data/piper/output-zero-shot-20speakers-v9/checkpoints/last.ckpt \
  /data/piper/output-zero-shot-20speakers-v9/zero-shot-20speakers-v9.onnx

# 推論テスト（リファレンス音声からembedding抽出→推論）
# Step 1: embedding抽出
CUDA_VISIBLE_DEVICES="" uv run python -c "
import numpy as np, soundfile as sf, torch, onnxruntime as ort, torchaudio
wav_np, sr = sf.read('/path/to/reference.wav')
wav = torch.FloatTensor(wav_np).unsqueeze(0)
wav16k = torchaudio.functional.resample(wav, sr, 16000)
fbank = torchaudio.compliance.kaldi.fbank(wav16k, num_mel_bins=80, sample_frequency=16000, dither=0.0)
fbank = fbank - fbank.mean(dim=0, keepdim=True)
session = ort.InferenceSession('/data/piper/models/campplus.onnx', providers=['CPUExecutionProvider'])
emb = session.run(None, {'input': fbank.unsqueeze(0).numpy()})[0][0]
emb = emb / np.linalg.norm(emb)
np.save('/tmp/ref_spk.npy', emb.astype(np.float32))
"

# Step 2: 推論
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /data/piper/output-zero-shot-20speakers-v9/zero-shot-20speakers-v9.onnx \
  --config /data/piper/dataset-zero-shot-20speakers/config.json \
  --output-dir /path/to/output \
  --text "こんにちは、今日は良い天気ですね。" \
  --speaker-embedding /tmp/ref_spk.npy
```

---

## 6. 検証済みルール（絶対に守ること）

1. **`--d-update-interval 1`** — 2にするとDiscriminator崩壊（loss_disc=6.0固定→ガビガビ音）
2. **SCL二重適用禁止** — speaker_encoder存在時はCAM++ SCLのみ。mel-domain SCLはフォールバック
3. **`--max_epochs 200`** — 100epでは収束不足
4. **パッケージ追加は `uv add`** — `pip install` は使わない

---

## 7. CI状態

最終確認: commit `5bcb54e` (包括レビュー修正適用済み)

直近のCI修正:

- `d5f0cb8`: Python Linting + Rust CI修正（ruff/rustfmt/synthesize_with_params）
- `bdbdb8c`: 全テストがCIで実行されるようワークフロー修正
- `b425e31`: CamPP FP16対応 + 消失ツール3本復元
- `5bcb54e`: `infer_onnx.py` の `--speaker-embedding` 重複引数除去

包括レビュー修正（2026-04-12）:

- `go-ci` を `ci-required` ゲートに追加
- `test_short_text_mitigation.py` / `.js` をワークフローに追加
- Rust E2E テストから `#[ignore]` を削除（モデルファイルがリポジトリにトラッキング済み）

全言語（Python, C++, C#, Rust, Go, WASM）のzero-shot E2Eテストが追加済みで、CIで実行される。

---

## 8. 既知の課題

| 課題 | 状態 | 備考 |
|------|------|------|
| `extract_speaker_embedding.py` が消失 | ✅ 解決済み | `b425e31`で復元。`--speaker-audio`オプションも動作確認済み |
| `infer_onnx.py` JSONL text入力 | 未対応 | `text`フィールドからの推論未実装（`phoneme_ids`必須） |
| 20話者のみ | 制約 | zero-shot汎化には数百話者が理想 |
| DP cond_scale | 未実装 | 意図的削除（ac8e456）。復元は要設計判断 |
| C#/Rust/Go SpeakerEncoder mel shape | ✅ 解決済み (包括レビュー) | `[1,80,T]`→`[1,T,80]`修正、FFT window 512→400、CMVN追加 |
| EMA CPU/GPU デバイスミスマッチ | ✅ 解決済み (包括レビュー) | チェックポイントリジューム後のデバイス不一致を修正 |
| DINO center dtype ミスマッチ | ✅ 解決済み (包括レビュー) | FP16学習時のdtype不一致を修正 |
| `--c-dino`, `--kl-annealing-epochs` CLI未対応 | ✅ 解決済み (包括レビュー) | CLI引数として有効化済み |
