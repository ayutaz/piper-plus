# LLM エコシステム統合ガイド

piper-plus は OpenAI 互換の TTS API を提供しており、OpenAI TTS をサポートする任意の LLM フレームワークと統合できます。本ガイドでは、主要な LLM ツールとの接続方法を説明します。

---

## 前提条件

### piper-plus API サーバーの起動

ONNX モデルと config.json を `models/` ディレクトリに配置し、以下のいずれかの方法で API サーバーを起動してください。

**Docker (推奨):**

```bash
docker run -d \
  --name piper-api \
  -p 8000:8000 \
  -v $(pwd)/models:/app/models:ro \
  ghcr.io/ayutaz/piper-plus/python-inference:dev \
  python /app/inference.py --server --model /app/models/model.onnx
```

**ローカルビルド:**

```bash
# プロジェクトルートで Docker イメージをビルド
docker build -t piper-inference -f docker/python-inference/Dockerfile .

docker run -d \
  --name piper-api \
  -p 8000:8000 \
  -v $(pwd)/models:/app/models:ro \
  piper-inference \
  python /app/inference.py --server --model /app/models/model.onnx
```

詳細は `docker/python-inference/` を参照してください。

### 起動確認

```bash
curl http://localhost:8000/health
# => {"status":"healthy"}
```

### モデルの入手

HuggingFace から取得可能です:

- `ayousanz/piper-plus-tsukuyomi-chan` (日本語 6 言語対応)
- `ayousanz/piper-plus-base` (ベースモデル)

---

## API エンドポイント

| エンドポイント | メソッド | 説明 |
|-------------|--------|------|
| `/v1/audio/speech` | POST | 音声合成 (OpenAI 互換) |
| `/v1/models` | GET | モデル一覧 |
| `/v1/audio/speech/languages` | GET | 対応言語一覧 |
| `/health` | GET | ヘルスチェック |

---

## OpenAI Python SDK

OpenAI 公式の Python SDK を使って piper-plus に接続できます。Python から統合する場合はこの方法を推奨します。

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI(
    api_key="dummy",
    base_url="http://localhost:8000/v1",
)

response = client.audio.speech.create(
    model="piper-plus",
    voice="default",
    input="こんにちは、今日は良い天気ですね。",
)
response.stream_to_file("hello.wav")
```

piper-plus は API キーを検証しないため、`api_key` には任意の文字列を指定してください。

### 言語を指定する場合

piper-plus の拡張パラメータ (`language`, `speaker_id` 等) を送信するには、`extra_body` を使用します:

```python
response = client.audio.speech.create(
    model="piper-plus",
    voice="default",
    input="Hello, how are you today?",
    extra_body={"language": "en"},
)
response.stream_to_file("hello_en.wav")
```

---

## AnythingLLM との統合

[AnythingLLM](https://anythingllm.com/) は OpenAI 互換の TTS プロバイダーをサポートしています。

### 設定手順

1. AnythingLLM の **Settings** を開く
2. **Text-to-Speech** セクションに移動
3. 以下の値を設定:

| 設定項目 | 値 |
|---------|-----|
| Provider | `OpenAI Compatible` (バージョンにより `OpenAI` の場合あり) |
| API Base URL | `http://localhost:8000/v1` |
| API Key | `dummy` |
| Model | `piper-plus` |
| Voice | `default` |

4. **Save** をクリック

### 注意点

- AnythingLLM が Docker 内で動作している場合、API Base URL は `http://host.docker.internal:8000/v1` (Docker Desktop) またはホストの実 IP に変更してください
- piper-plus と AnythingLLM を同じ Docker ネットワークに配置している場合は `http://piper-api:8000/v1` を使用できます

---

## LangChain との統合

LangChain には TTS の標準的な抽象化がないため、OpenAI Python SDK を LangChain のカスタムツールとしてラップする方法を推奨します。

```python
from langchain_core.tools import tool
from openai import OpenAI

tts_client = OpenAI(
    api_key="dummy",
    base_url="http://localhost:8000/v1",
)


@tool
def text_to_speech(text: str, language: str = "ja") -> str:
    """テキストを音声に変換して WAV ファイルとして保存する。"""
    response = tts_client.audio.speech.create(
        model="piper-plus",
        voice="default",
        input=text,
        extra_body={"language": language},
    )
    output_path = "output.wav"
    response.stream_to_file(output_path)
    return f"音声を {output_path} に保存しました"
```

### LangChain Agent での使用例

```python
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

llm = ChatOpenAI(model="gpt-4o")
agent = create_react_agent(llm, [text_to_speech])

result = agent.invoke(
    {"messages": [{"role": "user", "content": "「明日は晴れるでしょう」を音声にしてください"}]}
)
```

---

## Ollama + piper-plus

Ollama でローカル LLM を実行し、その出力を piper-plus で音声合成するパイプラインを構築できます。

### 基本的な構成

```
ユーザー入力 → Ollama (テキスト生成) → piper-plus (音声合成) → 音声出力
```

### Python での実装例

```python
import httpx
from openai import OpenAI

# Ollama (テキスト生成)
ollama_response = httpx.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "llama3",
        "prompt": "日本の四季について一文で説明してください。",
        "stream": False,
    },
)
generated_text = ollama_response.json()["response"]
print(f"生成テキスト: {generated_text}")

# piper-plus (音声合成)
tts_client = OpenAI(
    api_key="dummy",
    base_url="http://localhost:8000/v1",
)
speech = tts_client.audio.speech.create(
    model="piper-plus",
    voice="default",
    input=generated_text,
)
speech.stream_to_file("response.wav")
print("音声を response.wav に保存しました")
```

### Docker Compose での一括起動

Ollama と piper-plus を Docker Compose で一括管理する構成は [`docker/ollama-stack/`](../../docker/ollama-stack/) を参照してください。`docker-compose.yml` と `example.py` が含まれています。

---

## Open WebUI との統合

Open WebUI は OpenAI 互換の TTS エンジンをネイティブにサポートしており、チャット応答の音声読み上げに piper-plus を利用できます。

詳細な設定手順は [Open WebUI 統合ガイド](open-webui-integration.md) を参照してください。

---

## トラブルシューティング

### Connection refused エラー

- piper-api コンテナが起動しているか確認:
  ```bash
  docker ps | grep piper-api
  ```
- ヘルスチェック:
  ```bash
  curl http://localhost:8000/health
  ```
- Docker 内から接続する場合、`localhost` ではなくコンテナ名 (`piper-api`) または `host.docker.internal` を使用してください

### CORS エラー (ブラウザクライアント)

ブラウザから直接 piper-plus API にアクセスする場合、CORS エラーが発生することがあります。piper-plus の FastAPI サーバーは CORS を許可していますが、問題が発生する場合はリバースプロキシ (nginx 等) を経由するか、同一オリジンからのアクセスに変更してください。

### 音声が生成されない / エラーが返る

- API サーバーのログを確認:
  ```bash
  docker logs piper-api
  ```
- モデルファイルが正しく配置されているか確認:
  ```bash
  docker exec piper-api ls -la /app/models/
  ```
- `model.onnx` と `config.json` (または `model.onnx.json`) の両方が必要です

### OpenAI SDK で extra_body が効かない

`openai` パッケージのバージョンが古い場合、`extra_body` パラメータがサポートされていないことがあります。`pip install --upgrade openai` で最新版に更新してください。

### レスポンス形式の制限

piper-plus は現在 `wav` 形式のみ対応しています。クライアントが `mp3` 等を要求している場合は、リクエストの `response_format` を `wav` に変更するか、後段で ffmpeg 等を使って変換してください。

```bash
# WAV → MP3 変換の例
ffmpeg -i output.wav -codec:a libmp3lame -qscale:a 2 output.mp3
```
