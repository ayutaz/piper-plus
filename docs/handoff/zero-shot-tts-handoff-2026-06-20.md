# Zero-Shot TTS — 環境引き継ぎドキュメント (2026-06-20)

**目的**: 学習環境が切り替わる際、ゼロから本ブランチの zero-shot TTS 学習・FT・評価を再現できるよう、必要なものすべてをまとめた手順書。
**ブランチ**: `feat/zero-shot-tts` (HEAD `cb2a095`、`origin/dev` から 16 コミット先行 + 本ドキュメント追加分)
**前回作業日**: 2026-05-21 (Tsukuyomi zero-shot FT 完走)
**作成日**: 2026-06-20

---

## 0. 全体像 (5 分で読む用)

```text
   ┌──────────────────────────────────────────────────────────────────┐
   │ piper-plus zero-shot TTS のサイクル                              │
   │                                                                  │
   │   ① 環境構築 (Python 3.12 + PyTorch CUDA + uv)                  │
   │      └─ §2                                                       │
   │   ② リポジトリ取得 (feat/zero-shot-tts ブランチ)                │
   │      └─ §3                                                       │
   │   ③ モデル取得 (HF から v7 ckpt + Tsukuyomi FT)                 │
   │      └─ §4                                                       │
   │   ④ データセット復元 (生 wav 再 DL → 前処理 → cache 生成)       │
   │      └─ §5, §6 ← 一番時間がかかる (24h+)                        │
   │   ⑤ 学習再開 / 新規 FT                                          │
   │      └─ §7, §8                                                   │
   │   ⑥ ONNX エクスポート + 評価 (SECS 計算)                        │
   │      └─ §9, §10                                                  │
   └──────────────────────────────────────────────────────────────────┘
```

**最短ルート** (推論だけしたい): §2 + §3 + §4 + §9 で OK。
**続きの学習をしたい**: 全部やる (§5 / §6 のデータ復元が必須)。
**FT だけ新規データでやりたい**: §2-§4 + §5 (新データのみ) + §8 でOK。

---

## 1. 現在の到達点 (前回作業時点でのスナップショット)

### 達成済み

- ✅ **v7 multi-6lang zero-shot スクラッチ学習**: 32 epoch (改善継続中で意図的に一時停止)
  - SECS 既知 0.6619 / 未知 (zero-shot) 0.6879
  - V100×4、32-true、12.5 日
- ✅ **Tsukuyomi zero-shot FT (500 epoch)** 完走
  - SECS 0.7749 (Tsukuyomi 再現性) / 0.5158 (異話者コントロール、低いほど良い)
  - T4×1 で 51 分
- ✅ **学習を成立させた 5 つの修正コミット** (詳細は §11)
- ✅ HF モデル 2 つ公開済み (§4)
- ✅ 引き継ぎドキュメント (本書)

### 未完了 / 次のステップ

- ⏳ **v7 学習を epoch 50〜75 へ続行** (任意、改善継続中だった)
- ⏳ **聴感比較 / MOS**: zero-shot Tsukuyomi FT vs 旧 MB-iSTFT FT
- ⏳ Phase 3 改善 (InfoNCE / R1 / データ拡充、[`zero-shot-quality-improvement-plan.md`](../design/zero-shot-quality-improvement-plan.md))

---

## 2. 環境構築

### 2.1 ハードウェア要件

| 用途 | 推奨 GPU | 最低限 |
|---|---|---|
| **v7 学習再開** (multi-6lang スクラッチ続行) | V100-16GB × 4 / A100-40GB × 1 以上 | A100-40GB × 1 |
| **シングルスピーカー FT** | A100 / RTX 6000 Ada / T4 × 1 (16GB 以上) | T4-16GB × 1 |
| **ONNX 推論のみ** | GPU 不要 (CPU で十分) | — |

ディスク: データセット復元する場合 **~600GB 以上** (生 wav + cache .pt 511GB + ckpt 数 GB)。

### 2.2 ソフトウェア

| ツール | バージョン | 用途 |
|---|---|---|
| Python | 3.12 (現環境: 3.12.7) | 全体 |
| uv | 最新 | パッケージ管理 |
| PyTorch | 2.10.0+cu128 (現環境) | 学習 / 推論 |
| CUDA | 12.x (本リポジトリは 12.8 で動作実績) | GPU 学習 |
| NCCL | torch 同梱版 | DDP マルチ GPU |
| onnxruntime | 1.x (`onnxruntime-gpu` 推奨) | ONNX 推論 + SCL CAM++ |

### 2.3 セットアップ手順

```bash
# 1. Python + uv 環境
curl -LsSf https://astral.sh/uv/install.sh | sh
mkdir -p /data/piper && cd /data/piper
uv venv --python 3.12 .venv
source .venv/bin/activate

# 2. リポジトリ取得 (§3 参照)
cd /data
git clone https://github.com/ayutaz/piper-plus.git piper-plus-zero-shot
cd piper-plus-zero-shot
git checkout feat/zero-shot-tts
git pull origin feat/zero-shot-tts

# 3. piper-train + ランタイム依存をインストール
cd /data/piper
uv pip install -e /data/piper-plus-zero-shot/src/python
uv pip install -e /data/piper-plus-zero-shot/src/python/g2p
uv pip install -e /data/piper-plus-zero-shot/src/python_run

# 4. 追加で必要なもの (zero-shot 学習用)
uv pip install onnxruntime-gpu>=1.20.0 huggingface_hub torchaudio soundfile pypinyin g2p-en

# 動作確認
/data/piper/.venv/bin/python -c "import torch; print('torch:', torch.__version__, 'cuda:', torch.cuda.is_available())"
/data/piper/.venv/bin/python -m piper_train --help | head -5
```

### 2.4 必須環境変数 (.env)

`/data/piper/.env` に下記を設定:

```text
HF_TOKEN=<your_hf_token>
WANDB_API_KEY=<optional>
```

### 2.5 学習用環境変数 (シェル起動時)

```bash
export PYTHONPATH=/data/piper-plus-zero-shot/src/python
export WANDB_MODE=disabled                    # WANDB 不要なら disabled
export NCCL_DEBUG=WARN
export NCCL_P2P_DISABLE=1
export NCCL_IB_DISABLE=1
export PIPER_FORCE_CPU_ORT=1                  # SCL CAM++ を CPU 強制 (GPU 共有競合回避)
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# ORT が PyTorch 同梱 cuDNN を見つけられない問題回避 (任意)
CUDNN=/data/piper/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib
CUBLAS=/data/piper/.venv/lib/python3.12/site-packages/nvidia/cublas/lib
NVRTC=/data/piper/.venv/lib/python3.12/site-packages/nvidia/cuda_nvrtc/lib
CURAND=/data/piper/.venv/lib/python3.12/site-packages/nvidia/curand/lib
CUFFT=/data/piper/.venv/lib/python3.12/site-packages/nvidia/cufft/lib
export LD_LIBRARY_PATH="$CUDNN:$CUBLAS:$NVRTC:$CURAND:$CUFFT:$LD_LIBRARY_PATH"
```

---

## 3. リポジトリ取得

### 3.1 ブランチ状態 (作業の起点)

```text
リモート: https://github.com/ayutaz/piper-plus.git
ブランチ: feat/zero-shot-tts
HEAD:     cb2a095 docs: v7 epoch 32 評価結果と Tsukuyomi zero-shot FT 完走を反映
ベース:   origin/dev (5fceade Release v1.12.0)
```

引き継ぎ時点で `origin/dev` から **17+ コミット先行**。すべて重要なバグ修正と機能追加。

### 3.2 重要修正コミット (学習を成立させた変更)

| commit | 修正 | 解決した問題 |
|---|---|---|
| `5cdfafb` | MBiSTFTGenerator に **Multi-scale FiLM 復活** | dev リベース時に廃止された旧 Generator の FiLM を MB-iSTFT に移植 → zero-shot 学習が初めて成立 |
| `34ad257` | **DDP-synced NaN skip** | rank ごとに skip がバラついて NCCL all_reduce mismatch → 30 分後 timeout (CUDA illegal access 偽装) を防止 |
| `5e700d4` | dino_loss 診断 log | student_emb / teacher_emb / center どれが NaN 化したか追跡可能に |
| `ba71e16` | **speaker_embedding noise 加算後 L2 再正規化** | `norm=1 → sqrt(1+σ²·dim) ≈ 1.22` の magnitude 不一致を解消、`loss_dino` の 0 マスク貼り付き解消 |
| `95e74cb` | **dino_center を teacher_emb NaN 汚染から防御** | spk_proj が稀に NaN を出す瞬間に center が永続汚染されるのを防止 |

これらすべてが `feat/zero-shot-tts` の HEAD に反映済み。ベースの `dev` ブランチに戻すと再現できない。

---

## 4. HF からモデル取得

### 4.1 リポジトリ (すべて private)

> ⚠️ すべて **private repo**。`HF_TOKEN` (write 権限不要、read 権限で OK) を環境変数または `~/.cache/huggingface/token` に設定してアクセス。

| HF Repo | 内容 | サイズ |
|---|---|---|
| [`ayousanz/piper-plus-zero-shot-multi-6lang-v7`](https://huggingface.co/ayousanz/piper-plus-zero-shot-multi-6lang-v7) | v7 ep32 ckpt + singlespk ckpt + ONNX + 評価再現セット + tfevents + 過去 epoch ONNX | ~2.0GB |
| [`ayousanz/piper-plus-zero-shot-tsukuyomi`](https://huggingface.co/ayousanz/piper-plus-zero-shot-tsukuyomi) | Tsukuyomi FT ckpt + ONNX + 評価再現セット + sample wav | ~930MB |
| [`ayousanz/campplus-onnx`](https://huggingface.co/ayousanz/campplus-onnx) | CAM++ Speaker Encoder ONNX (Apache-2.0、ModelScope iic ミラー) | ~27MB |

### 4.2 ダウンロードコマンド

```bash
# HF token 設定 (read 権限で十分)
export HF_TOKEN=$(grep HF_TOKEN /data/piper/.env | cut -d= -f2)
hf auth login --token $HF_TOKEN

# 1. v7 zero-shot multi-6lang (ckpt + ONNX + 評価セット + tfevents + 過去 epoch ONNX)
hf download ayousanz/piper-plus-zero-shot-multi-6lang-v7 \
  --local-dir /data/piper/hf/zero-shot-multi-6lang-v7

# 2. Tsukuyomi FT (ckpt + ONNX + 評価セット + sample)
hf download ayousanz/piper-plus-zero-shot-tsukuyomi \
  --local-dir /data/piper/hf/zero-shot-tsukuyomi

# 3. CAM++ Speaker Encoder (zero-shot 推論 / SCL / 評価で必須)
mkdir -p /data/piper/models
hf download ayousanz/campplus-onnx campplus.onnx \
  --local-dir /data/piper/models
# (上記 mirror が利用不可な場合の代替: ModelScope iic/speech_campplus_sv_zh-cn_16k-common)
```

### 4.2.1 Windows ローカル検証時の注意

Windows PC で HF からモデルを取得して `torch.load` で sanity check する際は **2 つの罠** がある (2026-06-20 検証で確認):

1. **`torch 2.11.0+cpu` が install される** — `pyproject.toml` の cu128 index は Linux only marker。 Windows GPU 学習は手動 `uv pip install --index-url https://download.pytorch.org/whl/cu128 torch==2.11.0+cu128` で上書き
2. **`PosixPath` エラーで `torch.load` 失敗** — Linux 製 ckpt を Windows で読む際は load 前にモンキーパッチ必須:

   ```python
   import pathlib
   pathlib.PosixPath = pathlib.WindowsPath  # Linux→Windows pickle 互換
   import torch
   ckpt = torch.load("epoch=32-step=216326.ckpt", map_location="cpu", weights_only=False)
   ```

詳細: [`docs/migration/v1.12-to-v2.0.md` の "Windows local dev" セクション](../migration/v1.12-to-v2.0.md#windows-local-dev-cross-platform-notes)。 学習自体は Linux 環境で実行する前提のため、 上記 patch は Windows ローカル inspect 専用。

### 4.3 各 ckpt / ファイルの役割

| ファイル | 用途 |
|---|---|
| `v7/epoch=32-step=216326.ckpt` | **学習 resume 用**。`--resume_from_checkpoint` に渡す。Optimizer state / EMA / dino_center / spk_proj_teacher すべて保存 |
| `v7/epoch=32-step=216326.singlespk.ckpt` | **シングルスピーカー FT のベース**。emb_g 除去 + freeze_dp 有効化済み。`--resume-from-multispeaker-checkpoint` に渡す (自動変換) |
| `v7/v7-epoch32-zs.onnx` | **zero-shot 推論用**。speaker_embedding 入力対応、CAM++ で抽出した参照話者 emb を渡せばその声で合成 |
| `v7/eval/compute_secs.py` + `eval/spk_*.npy` + `eval/synthesized_*.wav` | **SECS 評価の完全再現セット**。CAM++ さえあれば SECS 0.6619/0.6879 を即時再現可能 |
| `v7/lightning_logs/version_2/events.out.tfevents.*` | **TensorBoard 用学習推移ログ** (loss/audio epoch 0-32)。`tensorboard --logdir lightning_logs` |
| `v7/past_epochs/v7-epoch{10,20}-zs.onnx` | **SECS 推移の聴感確認用** (任意)。ckpt は無いため学習再開には使えない |
| `tsukuyomi/epoch=499-step=22000.ckpt` | **Tsukuyomi FT 続行用** (追加 epoch を狙う場合) |
| `tsukuyomi/tsukuyomi-ft-epoch499-zs.onnx` | **Tsukuyomi 専用推論**。speaker_embedding 入力なし (single-speaker) |
| `tsukuyomi/eval/spk_*.npy` + `compute_secs.py` | Tsukuyomi FT の SECS 0.7749 を即時再現 |
| `campplus/campplus.onnx` | **CAM++ Speaker Encoder ONNX** (192-dim、16kHz 入力)。学習 + 推論 + 評価すべてで必須 |

---

## 5. データセット — 構成と入手方法

### 5.1 v7 学習で使ったデータセット (合計 497,519 発話 / 571 話者 / 6 言語)

| 言語 | LID | 発話 | 話者 | 出典 | ライセンス |
|---|---|---|---|---|---|
| 日本語 | 0 | 59,694 | 20 | MOE-Speech 20speakers (LJSpeech 形式) | ソース個別 ※ |
| 英語 | 1 | 64,698 | 310 | LibriTTS-R | CC BY 4.0 |
| 中国語 | 2 | 63,223 | 142 | AISHELL-3 | Apache 2.0 |
| スペイン語 | 3 | 168,374 | 63 | CML-TTS Spanish v0.1 | CC BY 4.0 |
| フランス語 | 4 | 107,464 | 28 | CML-TTS French v0.1 | CC BY 4.0 |
| ポルトガル語 | 5 | 34,066 | 8 | CML-TTS Portuguese v0.1 | CC BY 4.0 |

※ MOE-Speech 20speakers は HF `ayousanz/moe-speech-20speakers-ljspeech` で配布。元データソースは各キャラクター原作 (ゲーム音声等)、学習研究目的での利用に留めること。

### 5.2 Tsukuyomi FT データセット (100 発話 / 1 話者)

| 項目 | 値 |
|---|---|
| 元データ | つくよみちゃんコーパス VOICEACTRESS100 |
| 話者 | tsukuyomi (single) |
| 発話 | 100 |
| ライセンス | CC BY-ND 4.0 (商用可、改変禁止) |
| 入手 | <https://tyc.rei-yumesaki.net/material/corpus/> |

### 5.3 データセットの場所 (旧環境での参考パス)

| データセット | パス | サイズ |
|---|---|---|
| 学習用 manifest | `/data/piper/dataset-multilingual-6lang-filtered-new/` | 8.8GB (audio cache 込) |
| Tsukuyomi FT | `/data/piper/dataset-tsukuyomi-finetune-6lang/` | 112MB |
| MOE-Speech 20speakers (生 wav) | `/data/moe-speech-20speakers-ljspeech/` | ~? |
| LibriTTS-R (生 wav) | `/data/piper/libritts-r/libritts-ljspeech-v4/` | ~? |
| AISHELL-3 (生 wav) | `/data/piper/downloads/aishell3/` | ~10GB |
| CML-TTS ES (生 wav) | `/data/piper/downloads/cml_tts_dataset_spanish_v0.1/` | ~? |
| CML-TTS FR (生 wav) | `/data/piper/downloads/cml_tts_dataset_french_v0.1/` | ~? |
| CML-TTS PT (生 wav) | `/data/piper/downloads/cml_tts_dataset_portuguese_v0.1/` | ~? |

---

## 6. データセット復元手順 (生 wav 取得 → 前処理 → cache 生成)

### 6.1 [必要時間: 半日〜1 日] 生 wav の再ダウンロード

```bash
mkdir -p /data/piper/downloads /data/piper/libritts-r /data
cd /data/piper/downloads

# 中国語: AISHELL-3
wget -c http://www.openslr.org/resources/93/data_aishell3.tgz
tar xzf data_aishell3.tgz && mv data_aishell3 aishell3

# スペイン語: CML-TTS Spanish
wget -c https://huggingface.co/datasets/ylacombe/cml-tts/resolve/main/cml_tts_dataset_spanish_v0.1.tar.bz
tar xjf cml_tts_dataset_spanish_v0.1.tar.bz

# フランス語: CML-TTS French
wget -c https://huggingface.co/datasets/ylacombe/cml-tts/resolve/main/cml_tts_dataset_french_v0.1.tar.bz
tar xjf cml_tts_dataset_french_v0.1.tar.bz

# ポルトガル語: CML-TTS Portuguese
wget -c https://huggingface.co/datasets/ylacombe/cml-tts/resolve/main/cml_tts_dataset_portuguese_v0.1.tar.bz
tar xjf cml_tts_dataset_portuguese_v0.1.tar.bz

# 英語: LibriTTS-R (LJSpeech 形式に再パッケージ済みのものを使った)
# 元の LibriTTS-R は http://www.openslr.org/141/
# LJSpeech 形式への変換は src/python/piper_train/tools/ の補助スクリプト参照

# 日本語: MOE-Speech 20speakers
hf download ayousanz/moe-speech-20speakers-ljspeech \
  --repo-type dataset --local-dir /data/moe-speech-20speakers-ljspeech
```

### 6.2 [必要時間: 1〜3 日] データセット前処理 + audio cache 生成

> ⚠️ ここが一番時間がかかる。**747,298 個の `.pt`/`.spec.pt` ファイル生成 = 約 511GB のディスク**。
> CPU は多コアあるほど速い。`--workers 30` で V100 環境で 12〜24 時間。

```bash
cd /data/piper-plus-zero-shot

# 6.2.1 まず ja+en 二言語版を生成 (旧スクリプト、JA は MOE-Speech、EN は LibriTTS-R)
# (これは履歴的経緯。直接 6lang を一発で作る場合は §6.2.2 へジャンプ)
.venv/bin/python -m piper_train.tools.prepare_bilingual_dataset \
  --ja-dir /data/moe-speech-20speakers-ljspeech \
  --en-dir /data/piper/libritts-r/libritts-ljspeech-v4 \
  --output-dir /data/piper/dataset-bilingual-ja-en-v4 \
  --sample-rate 22050 \
  --workers 30

# 6.2.2 6lang データセット生成 (本命)
.venv/bin/python -m piper_train.tools.prepare_multilingual_dataset \
  --ja-en-dataset /data/piper/dataset-bilingual-ja-en-v4/dataset.jsonl \
  --zh-aishell3 /data/piper/downloads/aishell3 \
  --es-cml-tts /data/piper/downloads/cml_tts_dataset_spanish_v0.1 \
  --fr-cml-tts /data/piper/downloads/cml_tts_dataset_french_v0.1 \
  --pt-cml-tts /data/piper/downloads/cml_tts_dataset_portuguese_v0.1 \
  --output-dir /data/piper/dataset-multilingual-6lang-filtered-new \
  --sample-rate 22050 \
  --workers 30 \
  --gpu-spec-device cuda:0
```

これで以下が生成される:

```text
/data/piper/dataset-multilingual-6lang-filtered-new/
├── config.json                # 173 シンボル / 6 言語 / 571 話者の id_map
├── dataset.jsonl              # 全 497,519 発話のメタデータ (text/phonemes/audio_path...)
└── cache/22050/               # 各発話の audio_norm.pt + spec.pt (合計 ~511GB)
```

### 6.3 [必要時間: 4〜8 時間] per-utterance Speaker Embedding 抽出

zero-shot 学習には **発話単位の CAM++ embedding** が必要 (話者単位 emb では DINO/SCL が機能しない、旧 v8 失敗の根本原因)。

```bash
.venv/bin/python -m piper_train.extract_speaker_embedding \
  --encoder /data/piper/models/campplus.onnx \
  --dataset-dir /data/piper/dataset-multilingual-6lang-filtered-new \
  --per-utterance \
  --batch-size 64 \
  --workers 4

# 並列 shard で時間短縮できる (commit f9c18f6 で追加)
# 4 shard 並列の例:
for SHARD in 0 1 2 3; do
  CUDA_VISIBLE_DEVICES=$SHARD nohup \
  .venv/bin/python -m piper_train.extract_speaker_embedding \
    --encoder /data/piper/models/campplus.onnx \
    --dataset-dir /data/piper/dataset-multilingual-6lang-filtered-new \
    --per-utterance --batch-size 128 \
    --shard-index $SHARD --shard-count 4 \
    > /data/piper/extract-shard$SHARD.log 2>&1 &
done
wait
# 最後に finalize (jsonl を再書き出し)
.venv/bin/python -m piper_train.extract_speaker_embedding \
  --encoder /data/piper/models/campplus.onnx \
  --dataset-dir /data/piper/dataset-multilingual-6lang-filtered-new \
  --per-utterance --finalize
```

完了すると `speaker_embeddings/<sha256>.npy` (192 次元 L2 正規化、497,519 個、~76MB) と
`dataset.jsonl` の `speaker_embedding_path` フィールドが揃う。

### 6.4 Tsukuyomi FT データセット作成 (1 話者、100 発話)

```bash
mkdir -p /data/tsukuyomi-chan-ljspeech/wavs
# tyc.rei-yumesaki.net からコーパスを取得、wavs/ 配下に VOICEACTRESS100_*.wav を配置
# metadata.csv (LJSpeech 形式) も用意

.venv/bin/python -m piper_train.preprocess \
  --language ja-en-zh-es-fr-pt \
  --dataset-format ljspeech \
  --input-dir /data/tsukuyomi-chan-ljspeech \
  --output-dir /data/piper/dataset-tsukuyomi-finetune-6lang \
  --sample-rate 22050 \
  --max-workers 8

# per-utterance emb 抽出
.venv/bin/python -m piper_train.extract_speaker_embedding \
  --encoder /data/piper/models/campplus.onnx \
  --dataset-dir /data/piper/dataset-tsukuyomi-finetune-6lang \
  --per-utterance --batch-size 32
```

---

## 7. 学習再開 (v7 epoch=32 → さらに進める)

### 7.1 学習再開コマンド (V100×4、HF からダウンロードした ckpt を使用)

```bash
export WANDB_MODE=disabled
export NCCL_DEBUG=WARN
export NCCL_P2P_DISABLE=1
export NCCL_IB_DISABLE=1
export PYTHONPATH=/data/piper-plus-zero-shot/src/python
export PIPER_FORCE_CPU_ORT=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

cd /data/piper-plus-zero-shot
nohup /data/piper/.venv/bin/python -u -m piper_train \
  --dataset-dir /data/piper/dataset-multilingual-6lang-filtered-new \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 4 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 2 --no-pin-memory --no-wavlm \
  --max-phoneme-ids 400 \
  --spk-emb-noise-sigma 0.05 \
  --d-update-interval 1 \
  --lr-scheduler cosine --lr-warmup-epochs 5 --lr-min 1e-5 \
  --kl-annealing-epochs 10 \
  --c-dino 0.5 --c-spk 1.0 \
  --c-sub-stft 1.0 \
  --gradient-clip-val 0 \
  --speaker-encoder-path /data/piper/models/campplus.onnx \
  --val-every-n-epochs 1 --audio-log-epochs 5 \
  --resume_from_checkpoint /data/piper/hf/zero-shot-multi-6lang-v7/epoch=32-step=216326.ckpt \
  --default_root_dir /data/piper/output-zero-shot-multi-6lang-v7 \
  > /data/piper/output-zero-shot-multi-6lang-v7-train.log 2>&1 &
echo "PID: $!"
```

### 7.2 GPU 別チューニング

| GPU | precision | devices | batch_size | num_workers | 1 epoch 時間 (497k 発話) |
|---|---|---|---|---|---|
| **V100-16GB × 4** (実証済) | `32-true` | 4 | 20 | 2 | 8h53m |
| **A100-40GB × 1** | `bf16-mixed` | 1 | 80-120 | 4 | ~2-3h (見込) |
| **A100-80GB × 1** | `bf16-mixed` | 1 | 160 | 8 | ~1.5h (見込) |
| **RTX 6000 Ada-48GB × 1** | `bf16-mixed` | 1 | 100-120 | 4 | ~2-3h (見込) |
| **T4-16GB × 4** | `bf16-mixed` | 4 | 12-16 | 2 | 未測定、要ベンチ |

> ⚠️ **重要**: V100 は **`32-true` が `16-mixed` より 5x 高速** (backward 27sec → 5.3sec)。A100/RTX/T4 は逆に `bf16-mixed` 推奨。
> ⚠️ `--c-sub-stft 1.0` は必須 (MB-iSTFT の判別)。`--no-wavlm` で WavLM 無効化推奨 (V100 では GPU OOM)。

### 7.3 学習中に何を監視するか

- `loss_disc_all` / `loss_mel` / `loss_dino` / `loss_spk` のうち、`loss_dino` が 0 で貼り付いていないか (commit `ba71e16` / `95e74cb` 以降は安定)
- `non-finite skip` 率 — 数%なら正常、20% 超えるとデータ起因の異常
- `dino_center update skipped: teacher_emb mean has non-finite` — 散発的ならOK、連続したら spk_proj 異常
- WandB を使う場合は `WANDB_MODE=online` + `WANDB_API_KEY` 設定

---

## 8. シングルスピーカー Fine-Tuning (Tsukuyomi 例)

### 8.1 Tsukuyomi FT コマンド

```bash
export WANDB_MODE=disabled
export NCCL_DEBUG=WARN
export PYTHONPATH=/data/piper-plus-zero-shot/src/python
export PIPER_FORCE_CPU_ORT=1

cd /data/piper-plus-zero-shot
nohup /data/piper/.venv/bin/python -u -m piper_train \
  --dataset-dir /data/piper/dataset-tsukuyomi-finetune-6lang \
  --prosody-dim 16 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 500 --batch-size 4 --samples-per-speaker 4 \
  --checkpoint-epochs 50 --quality medium \
  --base_lr 2e-5 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 2 --no-pin-memory --no-wavlm \
  --max-phoneme-ids 400 \
  --c-dino 0.0 --c-spk 0.0 \
  --c-sub-stft 1.0 \
  --lr-scheduler cosine --lr-warmup-epochs 5 --lr-min 1e-5 \
  --val-every-n-epochs 50 --audio-log-epochs 50 \
  --resume-from-multispeaker-checkpoint /data/piper/hf/zero-shot-multi-6lang-v7/epoch=32-step=216326.singlespk.ckpt \
  --default_root_dir /data/piper/output-tsukuyomi-zs-finetune \
  > /data/piper/output-tsukuyomi-zs-finetune.log 2>&1 &
echo "PID: $!"
```

### 8.2 重要ポイント

- `--resume-from-multispeaker-checkpoint`: 自動で **emb_g 除去 + emb_lang 補正 + freeze_dp 有効化**。`singlespk.ckpt` を渡しても再変換されない (既に変換済み)
- `--base_lr 2e-5`: 事前学習の `2e-4` から **1/10**。catastrophic forgetting 防止
- `--c-dino 0.0 --c-spk 0.0`: シングルスピーカーで zero-shot 補助損失は不要 (むしろ干渉)
- `--samples-per-speaker 4`: 100 発話 × 4 = 1 epoch 400 sample / batch_size 4 = **22 batches/epoch**、500 epoch = 11,000 steps
- 学習時間: **T4-16GB × 1 で 51 分**

---

## 9. ONNX エクスポート

### 9.1 v7 zero-shot (multi-speaker、speaker_embedding 入力対応)

```bash
CUDA_VISIBLE_DEVICES="" /data/piper/.venv/bin/python -m piper_train.export_onnx \
  /data/piper/hf/zero-shot-multi-6lang-v7/epoch=32-step=216326.ckpt \
  /data/piper/eval-v7-epoch32/v7-epoch32-zs.onnx
# → FP16 38MB、speaker_embedding 入力対応
```

### 9.2 Tsukuyomi FT (single-speaker、speaker_embedding 入力なし)

```bash
CUDA_VISIBLE_DEVICES="" /data/piper/.venv/bin/python -m piper_train.export_onnx \
  /data/piper/hf/zero-shot-tsukuyomi/epoch=499-step=22000.ckpt \
  /data/piper/eval-tsukuyomi-zs-ft/tsukuyomi-ft-epoch499-zs.onnx
# → FP16 38MB、speaker_embedding 入力なし (single-speaker 自動検出)
```

### 9.3 主要オプション

| オプション | 既定 | 説明 |
|---|---|---|
| `--no-stochastic` | — | deterministic (デバッグ用) |
| `--no-fp16` | — | FP16 変換無効化 |
| `--unify-emb-lang` / `--no-unify-emb-lang` | **auto** | 多言語 single-speaker で自動有効、声質統一 |
| `--unify-emb-lang-source N` | 0 | emb_lang 統一ソース言語 index (0=ja) |
| `--simplify` | — | ONNX simplification |

---

## 10. 評価 (SECS 計算)

### 10.1 評価セットアップ

参照話者 embedding を 1 回だけ抽出 (ref-known, ref-tsukuyomi)。

```bash
mkdir -p /data/piper/eval-v7-epoch32
cd /data/piper/eval-v7-epoch32

# 既知話者 ref (学習データに含まれる、例: MOE-Speech 00163dc9)
/data/piper/.venv/bin/python -m piper_train.extract_speaker_embedding \
  --encoder /data/piper/models/campplus.onnx \
  --audio-dir /data/moe-speech-20speakers-ljspeech/wavs \
  --output spk_known_00163dc9.npy
# (--audio-dir で 00163dc9_*.wav だけ含むサブセットを作るか、--audio 単一指定)

# 未知話者 ref (Tsukuyomi、学習データ外)
/data/piper/.venv/bin/python -m piper_train.extract_speaker_embedding \
  --encoder /data/piper/models/campplus.onnx \
  --audio-dir /data/tsukuyomi-chan-ljspeech/wavs \
  --output spk_tsukuyomi.npy
```

> 💡 **即時再現したい場合**: HF v7 / Tsukuyomi repo の `eval/` フォルダに合成済み wav と
> 参照 emb npy が全部入っています。生 wav の準備をスキップして §10.2 末尾の
> `compute_secs.py` 実行だけで SECS の数字を再現できます。

### 10.2 合成 + SECS 計算

```bash
# 既知話者 emb で合成
CUDA_VISIBLE_DEVICES="" /data/piper/.venv/bin/python -m piper_train.infer_onnx \
  --model v7-epoch32-zs.onnx --config config.json \
  --output-dir synthesized_known \
  --text "今日は良い天気ですね。" \
  --speaker-embedding spk_known_00163dc9.npy \
  --language ja-en-zh-es-fr-pt \
  --noise-scale 0.4 --noise-scale-w 0.5

# 未知話者 emb で合成 (zero-shot 評価のメイン)
CUDA_VISIBLE_DEVICES="" /data/piper/.venv/bin/python -m piper_train.infer_onnx \
  --model v7-epoch32-zs.onnx --config config.json \
  --output-dir synthesized_tsukuyomi \
  --text "今日は良い天気ですね。" \
  --speaker-embedding spk_tsukuyomi.npy \
  --language ja-en-zh-es-fr-pt \
  --noise-scale 0.4 --noise-scale-w 0.5

# SECS 4-way 計算
/data/piper/.venv/bin/python /data/piper/eval-v7-epoch32/compute_secs.py \
  --eval-dir /data/piper/eval-v7-epoch32 \
  --encoder /data/piper/models/campplus.onnx \
  --epoch-label 32 \
  --baseline-known 0.5943 --baseline-tsukuyomi 0.6388
```

期待出力 (epoch 32 時点):

```text
=== SECS (epoch 32) ===
既知 ref ↔ 既知 synth      : 0.6619  (epoch20: 0.5943)
未知 ref ↔ 未知 synth (ZS) : 0.6879  (epoch20: 0.6388)
既知 ref ↔ 未知 synth      : 0.6459
未知 ref ↔ 既知 synth      : 0.6654
```

`compute_secs.py` は `/data/piper/eval-v7-epoch32/compute_secs.py` および `/data/piper/eval-tsukuyomi-zs-ft/compute_secs.py` にあり (本リポジトリ外、HF 配布なし)。本ドキュメント末尾 §A1 に全文付録。

### 10.3 Tsukuyomi FT 評価結果 (達成済み)

| 比較 | SECS |
|---|---|
| Tsukuyomi ref ↔ FT synth | **0.7749** (メイン、再現性) |
| 既知話者 ref ↔ FT synth | 0.5158 (コントロール、低いほど良い) |
| v7 ep32 zero-shot (FT 前) | 0.6879 |
| 改善 | **+0.0870** |

---

## 11. アーキテクチャの内部理解 (引き継ぐ前に把握すべき)

### 11.1 dev リベース後の決定的な変更

ブランチ初期 (リベース前) と現在で構造が大きく違う。**旧 doc を読むときは要注意**:

| コンポーネント | リベース前 | 現在 (v7) | 出所 |
|---|---|---|---|
| Decoder | `Generator` + Multi-scale FiLM | `MBiSTFTGenerator` + Multi-scale FiLM (復活) | dev + commit `5cdfafb` |
| Speaker conditioning | `emb_g` (Embedding 層) | `spk_proj` 2-layer MLP (192→512→512) | branch |
| DINO 自己蒸留 | `spk_proj_teacher` (EMA) | + `dino_center` + 汚染防御 | branch + `95e74cb` |
| SCL | CAM++ ONNX | + `mel_speaker_consistency_loss` fallback | branch |
| Forward 引数 | `forward(..., speaker_embeddings=...)` | 同左 (sid は ONNX 互換のため受理のみ) | branch |
| Output | `(wav,)` | `SynthesizerOutput` NamedTuple | dev |
| Multilingual | bilingual 専用 | `emb_lang` で 6 言語 | dev |
| Sub-band STFT loss | なし | `MultiResolutionSTFTLoss` | dev |
| Inference defaults | `noise_scale=0.667 / w=0.8` | `noise_scale=0.4 / noise_scale_w=0.5` | branch+dev |

### 11.2 NaN skip 経路 (commit `34ad257`)

`training_step` で各 rank が `_ddp_synced_is_finite` を呼び、**全 rank で skip を整合**させる:

```text
[各 rank] loss_g 計算 → is_finite check
        → torch.distributed.all_reduce(local_finite, MIN)
        → 1 rank でも non-finite なら 全 rank skip
        → all_reduce mismatch が発生せず NCCL timeout を防ぐ
```

旧 v7 (5月8日まで) はこれがなく、ランダム step で 30 分後 NCCL timeout で死亡していた。

### 11.3 dino_center 汚染防御 (commit `95e74cb`)

```python
# spk_proj_teacher が稀に NaN を出力
teacher_emb = self.spk_proj_teacher(speaker_embeddings)
if not torch.isfinite(teacher_emb.mean()):
    # ← この瞬間に dino_center を更新すると永続汚染、以後の全 loss が NaN
    log.warning("dino_center update skipped: teacher_emb mean has non-finite")
else:
    self.dino_center = momentum * self.dino_center + (1-momentum) * teacher_emb.mean(0)
```

---

## 12. トラブルシューティング

| 症状 | 原因 / 対処 |
|---|---|
| 推論音声が「ピー」音 | DP 学習失敗。`--samples-per-speaker` を 4 以上 / `--disable_auto_lr_scaling` / `--base_lr 1e-4` |
| 「CUDA illegal memory access」 (DDP 学習中) | **NaN skip による NCCL all_reduce mismatch (偽装症状)**。最新の `feat/zero-shot-tts` HEAD で修正済み (commit `34ad257`)。再発時は古いブランチを使っていないか確認 |
| `loss_dino` が 0 に貼り付く | speaker_embedding noise 加算の magnitude 問題。commit `ba71e16` で修正済み |
| 学習中に `dino_center` が永続的に NaN | teacher_emb 汚染。commit `95e74cb` で修正済み |
| GPU OOM (V100×4) | `NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1` / batch_size と samples_per_speaker を下げる / 異なる batch size からの resume を避ける |
| 学習速度が遅い (V100) | `--precision 32-true` 必須 (FP16-mixed は backward 27s に劣化) / `--max-phoneme-ids 400` / `--val-every-n-epochs 10` / `--no-wavlm` |
| 学習速度が遅い (A100/RTX/T4) | 逆に `--precision bf16-mixed` 必須 |
| ONNX 変換エラー | `CUDA_VISIBLE_DEVICES=""` で CPU モード |
| HiFi-GAN ckpt resume 失敗 | v1.12.0 で `Generator` 削除。MB-iSTFT base から再 FT が必要 |
| SCL CAM++ ONNX が GPU で動かない | `PIPER_FORCE_CPU_ORT=1` で CPU 強制。最新ブランチ (commit `a3614cf`) は GPU 化対応 |
| Per-utterance embedding 抽出が遅い | shard 並列 (commit `f9c18f6`) を使う。4 shard × T4 で 4x 高速 |

---

## 13. 既知の限界と次のステップ

### 13.1 v7 ep32 zero-shot の限界

| 指標 | 現状 | 目標 | 差 |
|---|---|---|---|
| zero-shot SECS (未知 ref ↔ 未知 synth) | 0.6879 | 0.80+ | -0.12 |
| 未知/既知比 (zero-shot 力指標) | 1.039 | 1.0± | OK |
| 言語カバー | 6 言語 (ja/en/zh/es/fr/pt) | + ko/sv | コード対応済、学習未 |

### 13.2 提案する次の改善 (Phase 3)

詳細: [`docs/design/zero-shot-quality-improvement-plan.md`](../design/zero-shot-quality-improvement-plan.md)

1. **学習続行 (低コスト)**: epoch 50 / 75 まで進める。epoch 20→32 で +0.0491 だったので、+0.05〜0.10 が見込める
2. **InfoNCE 損失追加 (中コスト)**: spk_proj に対する対照学習で zero-shot 性能向上
3. **R1 (gradient penalty) 追加 (中コスト)**: Discriminator 安定化
4. **データ拡充 (高コスト)**: ja 話者数を増やす (現在 20 話者) → LibriTTS-R 並みの 300+ 話者を目標
5. **WavLM Discriminator (V100 では OOM、A100 で可能)**: 知覚品質向上

### 13.3 評価方法の改善

- **MOS 評価**: `tools/benchmark/` に Google Form 生成スクリプト存在。Tsukuyomi FT vs 旧 MB-iSTFT FT の聴感比較
- **PESQ / STOI**: `tools/benchmark/` で自動計算可能
- **言語別 SECS**: 現在 ja のみ評価。en/zh/es/fr/pt それぞれで zero-shot SECS を測るべき

---

## 14. 主要ファイル索引

### Python (学習側)

| 用途 | パス |
|---|---|
| 学習エントリ | `src/python/piper_train/__main__.py` |
| VITS 本体 | `src/python/piper_train/vits/models.py` |
| Lightning module (training_step、NaN skip) | `src/python/piper_train/vits/lightning.py` |
| MB-iSTFT decoder (Multi-scale FiLM 復活コード) | `src/python/piper_train/vits/mb_istft.py` |
| Losses (DINO, SCL, sub-band STFT) | `src/python/piper_train/vits/losses.py`, `stft_loss.py` |
| ONNX エクスポート | `src/python/piper_train/export_onnx.py` |
| 推論スクリプト | `src/python/piper_train/infer_onnx.py` |
| Speaker Embedding 抽出 | `src/python/piper_train/extract_speaker_embedding.py` |
| データセット作成 (multi-6lang) | `src/python/piper_train/tools/prepare_multilingual_dataset.py` |
| データセット作成 (bilingual) | `src/python/piper_train/tools/prepare_bilingual_dataset.py` |
| Speaker Encoder ライブラリ | `src/python/piper_train/speaker_encoder/` |

### ドキュメント

| 用途 | パス |
|---|---|
| **本書 (引き継ぎ)** | `docs/handoff/zero-shot-tts-handoff-2026-06-20.md` |
| v7 詳細結果 | `docs/design/multi-6lang-zero-shot-v7-training-results.md` |
| 品質改善プラン | `docs/design/zero-shot-quality-improvement-plan.md` |
| プロジェクト全体 | `CLAUDE.md` |

---

## 15. 引き継ぎチェックリスト

新環境のオペレーターが本ブランチを引き継ぐとき、以下を順にチェック:

- [ ] Python 3.12 + uv + PyTorch + CUDA 環境セットアップ完了 (§2)
- [ ] `feat/zero-shot-tts` ブランチを clone、`piper_train` import 成功 (§3)
- [ ] HF token を `/data/piper/.env` に設定済み (§2.4)
- [ ] `ayousanz/piper-plus-zero-shot-multi-6lang-v7` をダウンロード済み (§4)
- [ ] CAM++ ONNX (`campplus.onnx`) を入手 (§4.2)
- [ ] **推論だけなら**: `v7-epoch32-zs.onnx` + 参照音声で zero-shot 推論できる (§9-§10)
- [ ] **続きの学習する場合**: §5-§6 でデータセット復元 (生 wav 〜 cache 〜 emb 抽出) 完了
- [ ] **学習する場合**: §7 のコマンドで起動、`loss_dino` が正常に下がる、`non-finite skip 率 < 5%` を確認
- [ ] **新規 FT する場合**: §6.4 でターゲット話者の dataset 作成、§8 のコマンドで FT 起動

---

## 付録 A1: compute_secs.py 全文

> 注意: 本スクリプトは HF にアップロードされていない (本リポジトリ外)。引き継ぎ用に本書末尾に転載。

```python
"""Compute SECS (Speaker Embedding Cosine Similarity) for v7 evaluation."""
import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
import torchaudio
import soundfile as sf

logging.basicConfig(level=logging.INFO, format="%(message)s")
LOG = logging.getLogger(__name__)


def extract_campp_embedding(wav_path: Path, session: ort.InferenceSession,
                            target_sr: int = 16000) -> np.ndarray:
    wav, sr = sf.read(str(wav_path), dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    tensor = torch.from_numpy(wav).unsqueeze(0)
    if sr != target_sr:
        tensor = torchaudio.functional.resample(tensor, sr, target_sr)
    fbank = torchaudio.compliance.kaldi.fbank(
        tensor, num_mel_bins=80, sample_frequency=target_sr, dither=0.0
    )
    fbank = fbank - fbank.mean(dim=0, keepdim=True)
    fbank_np = fbank.unsqueeze(0).numpy()
    emb = session.run(None, {"input": fbank_np})[0][0]
    emb = emb / np.linalg.norm(emb)
    return emb.astype(np.float32)


def cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-dir", required=True)
    ap.add_argument("--encoder", default="/data/piper/models/campplus.onnx")
    ap.add_argument("--ref-known", default="spk_known_00163dc9.npy")
    ap.add_argument("--ref-tsukuyomi", default="spk_tsukuyomi.npy")
    ap.add_argument("--synth-known", default="synthesized_known/output.wav")
    ap.add_argument("--synth-tsukuyomi", default="synthesized_tsukuyomi/output.wav")
    ap.add_argument("--epoch-label", default="?")
    ap.add_argument("--baseline-known", type=float, default=None)
    ap.add_argument("--baseline-tsukuyomi", type=float, default=None)
    args = ap.parse_args()

    root = Path(args.eval_dir)
    ref_k = np.load(root / args.ref_known)
    ref_t = np.load(root / args.ref_tsukuyomi)

    session = ort.InferenceSession(args.encoder, providers=["CPUExecutionProvider"])
    LOG.info(f"CAM++ encoder loaded: {args.encoder}")

    synth_k_emb = extract_campp_embedding(root / args.synth_known, session)
    synth_t_emb = extract_campp_embedding(root / args.synth_tsukuyomi, session)
    np.save(root / "spk_synth_known.npy", synth_k_emb)
    np.save(root / "spk_synth_tsukuyomi.npy", synth_t_emb)

    s_kk = cos(ref_k, synth_k_emb)
    s_tt = cos(ref_t, synth_t_emb)
    s_kt = cos(ref_k, synth_t_emb)
    s_tk = cos(ref_t, synth_k_emb)

    def fmt_base(v):
        return f"  (baseline: {v:.4f})" if v is not None else ""

    print()
    print(f"=== SECS (epoch {args.epoch_label}) ===")
    print(f"既知 ref ↔ 既知 synth      : {s_kk:.4f}{fmt_base(args.baseline_known)}")
    print(f"未知 ref ↔ 未知 synth (ZS) : {s_tt:.4f}{fmt_base(args.baseline_tsukuyomi)}")
    print(f"既知 ref ↔ 未知 synth      : {s_kt:.4f}")
    print(f"未知 ref ↔ 既知 synth      : {s_tk:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

## 16. 連絡先

- リポジトリ: <https://github.com/ayutaz/piper-plus>
- HF プロフィール: <https://huggingface.co/ayousanz>
- Issue は GitHub に
