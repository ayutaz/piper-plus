# piper-plus Docker Environments

piper-plus の Docker 環境一式です。Python 推論・学習、WebUI、Wyoming、C++ 推論・開発、Go の 7 つのイメージを提供します。

Python 推論イメージは **GPL-free** です。espeak-ng / piper-phonemize に依存せず、g2p-en (Apache-2.0) と pyopenjtalk-plus を使用します。

依存管理は全イメージで **uv** に統一されています（requirements.txt は使用しません）。

## 利用可能な環境

| イメージ | Dockerfile | ベースイメージ | 用途 | GPU |
|---------|-----------|---------------|------|-----|
| Python 推論 | `docker/python-inference/Dockerfile` | `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` | ONNX モデルによる CPU/GPU 推論 | GPU 対応（CPU/GPU 両対応） |
| Python 学習 | `docker/python-train/Dockerfile` | `nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04` | モデル学習 (multi-stage) | 必要 |
| WebUI | `docker/webui/Dockerfile` | `python:3.11-slim-trixie` | Gradio ベースの Web インターフェース | 不要 |
| C++ 推論 | `docker/cpp-inference/Dockerfile` | `ubuntu:24.04` (CPU専用, multi-stage) | C++ バイナリによる CPU 推論 | 不要 |
| C++ 開発 | `docker/cpp-dev/Dockerfile` | `ubuntu:24.04` (CPU専用) | C++ ビルド・デバッグ環境 | 不要 |
| Wyoming | `docker/wyoming/Dockerfile` | `python:3.11-slim-trixie` (multi-stage) | Home Assistant Wyoming Protocol TTS | 不要 |
| Go | `src/go/docker/Dockerfile` | `golang:1.26 -> debian:trixie-slim` (multi-stage, multi-arch amd64/arm64) | HTTP API サーバー + CLI (piper-plus-go), `serve` サブコマンド対応 | 不要 |

ルートの `Dockerfile` はマルチアーキテクチャ (amd64/arm64/armv7) 対応の C++ バイナリビルド用です。`debian:trixie` ベースの multi-stage ビルドで、CI/CD パイプラインからリリースアーカイブ (`piper-linux-*.tar.gz`) を生成します。ccache によるビルドキャッシュ、アーキテクチャ別の最適化フラグ、クロスコンパイルツールチェインを内蔵しています。

## クイックスタート

全てのビルドコマンドは **プロジェクトルートディレクトリ** から実行してください。

```bash
# Python 推論 (CPU, GPL-free)
docker build -t piper-inference -f docker/python-inference/Dockerfile .

# Python 学習 (GPU)
docker build -t piper-train -f docker/python-train/Dockerfile .

# WebUI (Gradio)
docker build -t piper-webui -f docker/webui/Dockerfile .

# C++ 推論 (CPU)
docker build -t piper-cpp -f docker/cpp-inference/Dockerfile .

# C++ 開発環境
docker build -t piper-cpp-dev -f docker/cpp-dev/Dockerfile .

# Wyoming Protocol (Home Assistant TTS)
docker build -t wyoming-piper-plus -f docker/wyoming/Dockerfile .

# Go (HTTP API + CLI)
docker build -t piper-plus-go -f src/go/docker/Dockerfile .
```

## Python 推論

CPU/GPU 両対応の推論イメージです。`--device` オプションで実行デバイスを選択できます（`auto`/`cpu`/`gpu`）。`setup.py` の `[inference-gpu]` extras（onnxruntime-gpu 含む）でインストールされます。CPU のみの環境では `[inference]` extras も利用可能です。

### ビルド

```bash
docker build -t piper-inference -f docker/python-inference/Dockerfile .
```

### コマンドライン推論

GPU で推論する場合は `--gpus all` と `--device gpu` を指定します。

```bash
docker run --rm --gpus all \
  -v $(pwd)/models:/app/models:ro \
  -v $(pwd)/output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx \
    --config /app/models/config.json \
    --output-dir /app/output \
    --text "こんにちは、今日は良い天気ですね。" \
    --speaker-id 0 \
    --device gpu
```

CPU で推論する場合（デフォルト: `auto`）:

```bash
docker run --rm \
  -v $(pwd)/models:/app/models:ro \
  -v $(pwd)/output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx \
    --config /app/models/config.json \
    --output-dir /app/output \
    --text "こんにちは、今日は良い天気ですね。" \
    --speaker-id 0 \
    --device cpu
```

英語モデルの場合は `--language en` を追加してください。

```bash
docker run --rm \
  -v $(pwd)/models:/app/models:ro \
  -v $(pwd)/output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/en_model.onnx \
    --config /app/models/en_model.onnx.json \
    --output-dir /app/output \
    --text "Hello, how are you today?" \
    --language en
```

### API サーバー起動

```bash
docker run -d \
  --name piper-api \
  -v $(pwd)/models:/app/models:ro \
  -p 8000:8000 \
  piper-inference \
  python /app/inference.py --server --model /app/models/model.onnx
```

ポート 8000 (FastAPI) でリクエストを受け付けます。

#### OpenAI 互換 API

`/v1/audio/speech` エンドポイントで OpenAI 互換の TTS API を提供します。

```bash
# curl での使用例
curl -X POST http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "こんにちは", "language": "ja"}' \
  -o output.wav

# OpenAI Python クライアント
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy")
response = client.audio.speech.create(model="piper-plus", input="こんにちは", voice="default")
response.stream_to_file("output.wav")
```

対応エンドポイント:
- `POST /v1/audio/speech` — 音声合成
- `GET /v1/models` — モデル一覧
- `GET /v1/audio/speech/languages` — 対応言語一覧

> **Note:** `response_format` は `wav` のみ対応。

## Python 学習

NVIDIA GPU を使用してモデルを学習するためのイメージです。`setup.py` の `[train]` extras でインストールされます。Multi-stage ビルドによりランタイムイメージのサイズを削減しています。

### ビルド

```bash
docker build -t piper-train -f docker/python-train/Dockerfile .
```

### GPU 学習

```bash
docker run -it --gpus all \
  -v $(pwd)/datasets:/workspace/datasets \
  -v $(pwd)/checkpoints:/workspace/checkpoints \
  -p 6006:6006 \
  piper-train
```

コンテナ内で学習を開始します。

```bash
python -m piper_train \
  --dataset-dir /workspace/datasets/my_dataset \
  --accelerator gpu --devices 1 --precision 16-mixed \
  --max_epochs 200 --batch-size 16 \
  --quality medium
```

マルチスピーカーモデルの場合は `--samples-per-speaker` を追加してください。

```bash
python -m piper_train \
  --dataset-dir /workspace/datasets/my_dataset \
  --prosody-dim 16 \
  --accelerator gpu --devices 1 --precision 16-mixed \
  --max_epochs 200 --batch-size 16 --samples-per-speaker 4 \
  --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995
```

### TensorBoard

学習中のメトリクスは TensorBoard で確認できます。

```bash
# コンテナ内で TensorBoard を起動
tensorboard --logdir /workspace/checkpoints --host 0.0.0.0 --port 6006
```

ブラウザから `http://localhost:6006` にアクセスしてください。

### ONNX 変換

学習完了後、コンテナ内でチェックポイントを ONNX に変換します。

```bash
CUDA_VISIBLE_DEVICES="" python -m piper_train.export_onnx \
  /workspace/checkpoints/lightning_logs/version_0/checkpoints/last.ckpt \
  /workspace/checkpoints/model.onnx
```

デフォルトのエクスポートでは stochastic モードと EMA が自動的に有効化されるため、通常はオプション指定不要です（上記コマンドを推奨）。deterministic なエクスポートが必要な場合（デバッグ用）は `--no-stochastic` を追加してください。

```bash
CUDA_VISIBLE_DEVICES="" python -m piper_train.export_onnx \
  --no-stochastic \
  /workspace/checkpoints/lightning_logs/version_0/checkpoints/last.ckpt \
  /workspace/checkpoints/model.onnx
```

## WebUI

Gradio ベースの Web インターフェースです。ブラウザから音声合成を試すことができます。

### docker-compose で起動 (推奨)

```bash
# モデルディレクトリを指定して起動
MODELS_DIR=/path/to/models OUTPUT_DIR=/path/to/output \
  docker compose -f docker/webui/docker-compose.yml up
```

環境変数を省略した場合、`./models` と `./output` がデフォルトで使用されます。

### 手動起動

```bash
# ビルド
docker build -t piper-webui -f docker/webui/Dockerfile .

# 起動
docker run -p 7860:7860 \
  -v $(pwd)/models:/models:ro \
  -v $(pwd)/output:/output \
  piper-webui
```

ブラウザから `http://localhost:7860` にアクセスしてください。

## C++ 推論

C++ バイナリ (`piper`) による CPU 推論環境です。CMake ExternalProject で必要な依存関係（ONNX Runtime と OpenJTalk のみ、espeak-ng 不使用）を自動ビルドし、ランタイムステージにコピーする multi-stage ビルドです。GPU は不要で、CPU のみで高速に推論を実行できます。

### ビルド

```bash
docker build -t piper-cpp -f docker/cpp-inference/Dockerfile .
```

### 推論

```bash
docker run --rm \
  -v $(pwd)/models:/app/models:ro \
  -v $(pwd)/output:/app/output \
  piper-cpp \
  bash -c 'echo "Hello world" | piper --model /app/models/model.onnx --output_file /app/output/output.wav'
```

日本語モデルの場合:

```bash
docker run --rm \
  -v $(pwd)/models:/app/models:ro \
  -v $(pwd)/output:/app/output \
  piper-cpp \
  bash -c 'echo "こんにちは" | piper --model /app/models/model.onnx --output_file /app/output/output.wav'
```

### MODEL_PATH 環境変数

`MODEL_PATH` 環境変数を指定すると、entrypoint スクリプトが自動的に `PIPER_MODEL_PATH` を設定します。

```bash
docker run --rm \
  -v $(pwd)/models:/app/models:ro \
  -v $(pwd)/output:/app/output \
  -e MODEL_PATH=/app/models/model.onnx \
  piper-cpp \
  bash -c 'echo "こんにちは" | piper --output_file /app/output/output.wav'
```

## C++ 開発環境

CMake、Ninja、clang、gdb、valgrind 等の開発ツールを含むフル装備の CPU 開発環境です。ccache によるビルドキャッシュをサポートします。

### ビルド

```bash
docker build -t piper-cpp-dev -f docker/cpp-dev/Dockerfile .
```

### インタラクティブ開発

```bash
# ccache ボリュームの作成 (初回のみ)
docker volume create piper-ccache

# コンテナ起動
docker run -it \
  -v $(pwd):/workspace \
  -v piper-ccache:/workspace/.ccache \
  piper-cpp-dev
```

### build.sh によるビルド

コンテナ内にはビルドスクリプト `/workspace/build.sh` が用意されています。

```bash
# Release ビルド (デフォルト)
./build.sh

# Debug ビルド
BUILD_TYPE=Debug ./build.sh

# ビルド + テスト実行
RUN_TESTS=1 ./build.sh

# カバレッジレポート生成
COVERAGE=1 ./build.sh
```

| 環境変数 | デフォルト | 説明 |
|----------|----------|------|
| `BUILD_TYPE` | `Release` | CMake ビルドタイプ (`Release` / `Debug`) |
| `RUN_TESTS` | 未設定 | `1` に設定するとビルド後に `ctest` を実行 |
| `COVERAGE` | 未設定 | `1` に設定すると `gcovr` でカバレッジレポートを生成 |

## Go

Go 製の HTTP API サーバーおよび CLI ツールです。Docker イメージ名は `piper-plus-go`、コンテナ内の CLI コマンドは `piper-plus` です。ONNX モデルを使用した音声合成を HTTP API またはコマンドラインから実行できます。Debian ベースのマルチステージビルドで、OpenJTalk (日本語G2P) を静的リンクし、ONNX Runtime v1.24.4 をバンドルしています。

### ビルド

```bash
docker build -t piper-plus-go -f src/go/docker/Dockerfile .
```

### CLI モード

```bash
docker run --rm \
  -v $(pwd)/models:/models:ro \
  -v $(pwd)/output:/output \
  piper-plus-go \
  -m /models/model.onnx -t "こんにちは" -f /output/output.wav
```

### HTTP サーバーモード

```bash
docker run -d \
  --name piper-go-api \
  -v $(pwd)/models:/models:ro \
  -p 8080:8080 \
  piper-plus-go \
  serve -m /models/model.onnx --addr :8080
```

テスト:

```bash
curl "http://localhost:8080/synthesize?text=Hello&lang=en" -o output.wav
curl http://localhost:8080/health
curl http://localhost:8080/info
```

## ボリュームマウント

### Python 推論

| コンテナパス | 用途 | マウントモード |
|-------------|------|--------------|
| `/app/models` | ONNX モデルと config.json | 読み取り専用 (`:ro`) |
| `/app/output` | 生成された音声ファイル | 読み書き |

### Python 学習

| コンテナパス | 用途 | マウントモード |
|-------------|------|--------------|
| `/workspace/datasets` | 学習データセット | 読み取り専用 (`:ro`) 推奨 |
| `/workspace/checkpoints` | チェックポイント・ログ | 読み書き |

### WebUI

| コンテナパス | 用途 | マウントモード |
|-------------|------|--------------|
| `/models` | ONNX モデル | 読み取り専用 (`:ro`) |
| `/output` | 生成された音声ファイル | 読み書き |

### C++ 推論

| コンテナパス | 用途 | マウントモード |
|-------------|------|--------------|
| `/app/models` | モデルファイル | 読み取り専用 (`:ro`) |
| `/app/output` | 出力ファイル | 読み書き |

### C++ 開発

| コンテナパス | 用途 | マウントモード |
|-------------|------|--------------|
| `/workspace` | ソースコード | 読み書き |
| `/workspace/.ccache` | ビルドキャッシュ (named volume 推奨) | 読み書き |

## ポート

| イメージ | ポート | プロトコル |
|---------|-------|----------|
| Python 推論 | 8000 | FastAPI |
| Python 学習 | 6006 | TensorBoard |
| Python 学習 | 8888 | Jupyter |
| WebUI | 7860 | Gradio |

## GPU 対応

Python 学習イメージと Python 推論イメージは NVIDIA GPU を使用できます。Python 推論イメージは GPU なし（CPU のみ）でも動作します。C++ イメージ（推論・開発）は CPU 専用です。

### 前提条件

- NVIDIA Driver >= 525.60.13
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- Docker >= 19.03

### GPU の指定

```bash
# 全 GPU を使用
docker run --gpus all ...

# 特定の GPU を使用
docker run --gpus '"device=0,1"' ...

# 単一 GPU
docker run --gpus '"device=0"' ...
```

### CPU のみで実行

Python 推論イメージと WebUI は GPU なしでも動作します。`--gpus` フラグなしで起動してください。Python 推論イメージでは `--device cpu` を指定するか、デフォルトの `auto` で自動検出されます。

## 環境変数

| 変数名 | 対象イメージ | 説明 |
|--------|------------|------|
| `WANDB_API_KEY` | Python 学習 | Weights & Biases API キー |
| `NVIDIA_VISIBLE_DEVICES` | Python 学習 | GPU デバイス選択 |
| `GRADIO_SERVER_NAME` | WebUI | サーバーバインドアドレス (デフォルト: `0.0.0.0`) |
| `GRADIO_SERVER_PORT` | WebUI | サーバーポート (デフォルト: `7860`) |
| `CUDA_VISIBLE_DEVICES` | Python 学習 | CUDA デバイス選択 (ONNX 変換時は `""` を指定) |
| `MODEL_PATH` | C++ 推論 | モデルファイルパス (entrypoint が `PIPER_MODEL_PATH` に設定) |
| `BUILD_TYPE` | C++ 開発 | CMake ビルドタイプ (デフォルト: `Release`) |
| `RUN_TESTS` | C++ 開発 | `1` でビルド後にテスト実行 |
| `COVERAGE` | C++ 開発 | `1` でカバレッジレポート生成 |
| `PYTHONUNBUFFERED` | 全 Python イメージ | Python 出力バッファリング無効 (デフォルト: `1`) |

## CI/CD (ghcr.io)

GitHub Actions で全イメージが自動ビルドされ、GitHub Container Registry (`ghcr.io`) にプッシュされます。

### イメージの pull

ローカルでビルドせずに、CI でビルド済みのイメージを直接利用できます。

```bash
# Python 推論
docker pull ghcr.io/ayutaz/piper-plus/python-inference:main

# Python 学習
docker pull ghcr.io/ayutaz/piper-plus/python-train:main

# WebUI
docker pull ghcr.io/ayutaz/piper-plus/webui:main

# C++ 推論
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:main

# C++ 開発
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:main
```

タグには `main` (最新の main ブランチ)、セマンティックバージョン (`v1.0.0` 等)、コミット SHA が使用できます。

### ビルドトリガー

以下のパスが変更されると自動ビルドが実行されます。

- `docker/**`
- `Dockerfile`
- `src/python/**`
- `pyproject.toml`
- `CMakeLists.txt`

手動トリガー (`workflow_dispatch`) にも対応しています。

### テスト (`docker-test.yml`)

PR 時に以下の 3 イメージに対してスモークテストが実行されます。

- `test-python-inference` — Python 推論イメージのビルドとインポートテスト
- `test-cpp-inference` — C++ 推論イメージのビルドと `piper --version` テスト
- `test-webui` — WebUI イメージのビルドとインポートテスト

## トラブルシューティング

### CUDA Out of Memory (OOM)

GPU メモリ不足の場合は以下を試してください。

- `--batch-size` を小さくする (例: 16 -> 8)
- `--precision 16-mixed` を指定して FP16 学習を有効化する (デフォルトで有効)
- マルチ GPU の場合は NCCL 環境変数を設定する

```bash
docker run -it --gpus all \
  -e NCCL_DEBUG=WARN \
  -e NCCL_P2P_DISABLE=1 \
  -e NCCL_IB_DISABLE=1 \
  piper-train
```

### マウントボリュームの権限エラー

コンテナ内でファイルの読み書きができない場合は、ホスト側のユーザー ID を指定してください。

```bash
docker run -it --user $(id -u):$(id -g) \
  -v $(pwd)/output:/app/output \
  piper-inference ...
```

### ビルドエラー

- ビルドキャッシュが原因の場合は `--no-cache` を追加してください。

```bash
docker build --no-cache -t piper-inference -f docker/python-inference/Dockerfile .
```

- Python 学習イメージで CUDA バージョンの不一致が疑われる場合は `nvidia-smi` でドライバーバージョンを確認してください。

### コンテナが起動しない

ヘルスチェックの状態を確認してください。

```bash
docker inspect --format='{{json .State.Health}}' <container_id>
```

### Python 推論で「モジュールが見つからない」エラー

Python 推論イメージは `[inference-gpu]` extras のみをインストールしています。学習関連のモジュール (`pytorch_lightning`, `wandb` 等) は含まれません。推論には `piper_train.infer_onnx` を使用してください。
