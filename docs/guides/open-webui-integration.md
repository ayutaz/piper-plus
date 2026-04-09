# Open WebUI との統合ガイド

piper-plus の OpenAI 互換 TTS API を Open WebUI に接続し、チャットの音声読み上げに利用する手順を説明します。

---

## 前提条件

- Docker および Docker Compose がインストール済み
- [Open WebUI](https://github.com/open-webui/open-webui) が稼働中
- piper-plus 用の ONNX モデルと config.json を準備済み
  - HuggingFace から取得可能: `ayousanz/piper-plus-tsukuyomi-chan` (日本語 6 言語対応) または `ayousanz/piper-plus-base` (ベースモデル)

---

## Step 1: piper-plus API サーバーの起動

### 方法 A: docker run で起動

```bash
# プロジェクトルートで Docker イメージをビルド
docker build -t piper-inference -f docker/python-inference/Dockerfile .

# API サーバーを起動
docker run -d \
  --name piper-api \
  -v $(pwd)/models:/app/models:ro \
  -p 8000:8000 \
  piper-inference \
  python /app/inference.py --server --model /app/models/model.onnx
```

`models/` ディレクトリに `model.onnx` と `config.json` (または `model.onnx.json`) を配置してください。

### 方法 B: docker compose で起動

`docker/python-inference/docker-compose.yml` を利用する場合は、モデルファイルの配置と command の調整が必要です。

```bash
cd docker/python-inference
mkdir -p models
# models/ に model.onnx と config.json を配置
```

以下の `docker-compose.yml` で API サーバーとして起動します。

```yaml
services:
  piper-api:
    build:
      context: ../..
      dockerfile: docker/python-inference/Dockerfile
    container_name: piper-api
    ports:
      - "8000:8000"
    volumes:
      - ./models:/app/models:ro
    environment:
      - PYTHONUNBUFFERED=1
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    command:
      - python
      - /app/inference.py
      - --server
      - --model
      - /app/models/model.onnx
```

```bash
docker compose up -d
```

### 方法 C: Open WebUI と同じ docker-compose で起動

Open WebUI を Docker Compose で管理している場合は、同じネットワークに piper-api サービスを追加できます。

```yaml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    ports:
      - "3000:8080"
    volumes:
      - open-webui:/app/backend/data
    # ... 既存の設定 ...

  piper-api:
    image: ghcr.io/ayutaz/piper-plus/python-inference:dev
    container_name: piper-api
    ports:
      - "8000:8000"
    volumes:
      - ./models:/app/models:ro
    environment:
      - PYTHONUNBUFFERED=1
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    command:
      - python
      - /app/inference.py
      - --server
      - --model
      - /app/models/model.onnx

volumes:
  open-webui:
```

この構成では、Open WebUI から piper-api にサービス名 `piper-api` で直接アクセスできます (Docker 内部 DNS)。

### 起動確認

```bash
# ヘルスチェック
curl http://localhost:8000/health
# => {"status":"healthy"}

# 対応言語一覧 (モデルの config.json の language_id_map に定義された言語が返ります)
curl http://localhost:8000/v1/audio/speech/languages
# => {"languages":["en","es","fr","ja","pt","zh"]}  # 6lang モデルの例

# 音声合成テスト
curl -X POST http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "こんにちは", "language": "ja"}' \
  -o test.wav
```

---

## Step 2: Open WebUI の TTS 設定

Open WebUI の管理画面から以下の設定を行います。

1. **Settings** (管理者設定) を開く
2. **Audio** セクションに移動
3. 以下の値を設定:

| 設定項目 | 値 |
|---------|-----|
| TTS Engine | `OpenAI` |
| TTS Base URL | `http://piper-api:8000/v1` |
| TTS API Key | `dummy` (任意の文字列。piper-plus は API キーを検証しません) |
| TTS Model | `piper-plus` |
| TTS Voice | `default` |

**TTS Base URL の注意点:**

- Open WebUI と piper-api が同じ Docker Compose ネットワーク内にある場合: `http://piper-api:8000/v1`
- Open WebUI がホストマシンから piper-api にアクセスする場合: `http://localhost:8000/v1`
- Open WebUI が別の Docker ネットワークにある場合: `http://host.docker.internal:8000/v1` (Docker Desktop) または ホストの実 IP を指定

4. **Save** をクリック

---

## Step 3: 動作確認

1. Open WebUI でチャットを開く
2. LLM にメッセージを送信し、応答を受け取る
3. 応答メッセージの音声再生ボタン (スピーカーアイコン) をクリック
4. piper-plus による音声が再生されることを確認

### 言語の自動検出について

piper-plus の API はリクエストごとに `language` パラメータを受け取ります。Open WebUI の標準 TTS 統合ではこのパラメータを送信しないため、デフォルトの言語 (日本語: `ja`) で合成されます。

英語など他言語での合成が必要な場合は、Open WebUI 側で TTS リクエストをカスタマイズするか、piper-plus API の前段に言語自動検出プロキシを配置する方法があります。

---

## API 仕様

piper-plus が提供する OpenAI 互換エンドポイントの一覧です。

### POST /v1/audio/speech

音声合成リクエスト。

**リクエストボディ (JSON):**

| フィールド | 型 | デフォルト | 説明 |
|-----------|------|----------|------|
| `input` | string | (必須) | 合成するテキスト |
| `model` | string | `"piper-plus"` | モデル名 (任意の値を受け付けます) |
| `voice` | string | `"default"` | 音声名 (任意の値を受け付けます) |
| `response_format` | string | `"wav"` | 出力形式 (`wav` のみ対応) |
| `speed` | float | `1.0` | 話速 (0.0 < speed <= 4.0) |
| `language` | string | `"ja"` | 言語コード (piper-plus 拡張) |
| `speaker_id` | int | `0` | 話者 ID (piper-plus 拡張) |
| `noise_scale` | float | `0.667` | ノイズスケール (piper-plus 拡張) |
| `noise_w` | float | `0.8` | ノイズ W (piper-plus 拡張) |

**レスポンス:** `audio/wav` (バイナリ)

### GET /v1/models

モデル一覧を返します。

```json
{
  "object": "list",
  "data": [
    {
      "id": "piper-plus",
      "object": "model",
      "created": 1712345678,
      "owned_by": "piper-plus"
    }
  ]
}
```

### GET /v1/audio/speech/languages

対応言語一覧を返します。返される言語はロードしたモデルの `config.json` 内の `language_id_map` に定義された言語に依存します。

```json
{
  "languages": ["en", "es", "fr", "ja", "pt", "zh"]
}
```

> **Note:** 上記は 6lang モデル (`ayousanz/piper-plus-tsukuyomi-chan` 等) の例です。異なるモデルを使用した場合、対応言語は変わります。

### GET /health

ヘルスチェック。

```json
{"status": "healthy"}
```

---

## トラブルシューティング

### 「Connection refused」エラー

- piper-api コンテナが起動しているか確認:
  ```bash
  docker ps | grep piper-api
  ```
- ヘルスチェックの状態を確認:
  ```bash
  docker inspect --format='{{json .State.Health}}' piper-api
  ```
- TTS Base URL が正しいか確認。同一 Docker ネットワーク内なら `http://piper-api:8000/v1`、外部からなら `http://localhost:8000/v1`

### 音声が再生されない

- ブラウザの開発者ツール (Network タブ) で `/v1/audio/speech` リクエストのステータスコードを確認
- piper-api のログを確認:
  ```bash
  docker logs piper-api
  ```
- `response_format` の問題: piper-plus は `wav` のみ対応。Open WebUI が他の形式を要求している場合は 400 エラーが返ります

### モデルが見つからない

- コンテナ内のモデルパスを確認:
  ```bash
  docker exec piper-api ls -la /app/models/
  ```
- `model.onnx` と `config.json` (または `model.onnx.json`) の両方が必要

### GPU を使用したい場合

Docker 起動時に GPU パススルーを有効化:
```bash
docker run -d --gpus all \
  --name piper-api \
  -v $(pwd)/models:/app/models:ro \
  -p 8000:8000 \
  piper-inference \
  python /app/inference.py --server --model /app/models/model.onnx --device gpu
```

前提条件: ホストに NVIDIA Driver (>= 525.60.13) と [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) がインストール済みであること。

---

## openedai-speech からの移行

[openedai-speech](https://github.com/matatonic/openedai-speech) からの移行に関するノートです。

### 共通点

- 両方とも OpenAI 互換の `POST /v1/audio/speech` エンドポイントを提供
- `model`, `input`, `voice`, `speed` フィールドを受け付ける
- Open WebUI の TTS Engine 設定で `OpenAI` を選択して接続

### 主な違い

| 項目 | openedai-speech | piper-plus |
|------|----------------|------------|
| 対応形式 | wav, mp3, opus, aac, flac, pcm | wav のみ |
| 対応言語 | モデル依存 | 6 言語 (ja, en, zh, es, fr, pt) |
| 言語指定 | テキストから自動検出 (モデル依存) | `language` パラメータで明示指定 |
| voice マッピング | 設定ファイルで voice 名 -> モデルをマッピング | `voice` フィールドは無視 (`speaker_id` で話者を指定) |
| バックエンド | piper (espeak-ng依存), Coqui TTS 等 | piper-plus (espeak-ng 不使用、GPL-free) |
| ライセンス | AGPL-3.0 | MIT |
| 状態 | アーカイブ済み | 活発に開発中 |

### 移行手順

1. openedai-speech のコンテナを停止
2. piper-plus API サーバーを起動 (Step 1 参照)
3. Open WebUI の TTS 設定で Base URL を piper-plus に変更 (Step 2 参照)
4. `voice` 設定は `default` に変更 (piper-plus は voice 名を使用しません)

### 注意事項

- openedai-speech で `mp3` 等の形式を指定していた場合、piper-plus は `wav` のみ対応のため、Open WebUI 側の設定で `response_format` が `wav` になっていることを確認してください
- openedai-speech の voice 名 (`alloy`, `nova` 等) は piper-plus では無視されます。話者を切り替えるには `speaker_id` パラメータを使用してください

---

## 関連ガイド

- [LLM エコシステム統合ガイド](llm-ecosystem.md) — AnythingLLM, LangChain, Ollama との統合
- [Ollama + piper-plus Stack](../../docker/ollama-stack/) — Docker Compose で一括起動
