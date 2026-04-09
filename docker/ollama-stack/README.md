# Ollama + piper-plus Stack

LLM テキスト生成 (Ollama) + 多言語音声合成 (piper-plus) を Docker Compose で一括起動するスタックです。

## 前提条件

- Docker および Docker Compose
- piper-plus 用の ONNX モデルと config.json
  - [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) からダウンロード可能

## セットアップ

```bash
# 1. モデルを配置
mkdir -p models
curl -L -o models/model.onnx https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx
curl -L -o models/model.onnx.json https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json

# 2. スタックを起動
docker compose up -d

# 3. Ollama にモデルをダウンロード (初回のみ)
docker compose exec ollama ollama pull llama3.2

# 4. 動作確認
curl http://localhost:8000/health
# => {"status":"healthy"}
```

## 使い方

### サンプルスクリプト

```bash
pip install requests
python example.py "日本の首都について教えてください"
python example.py "Tell me about Tokyo" --language en
```

### 直接 API を呼ぶ

```bash
# Ollama でテキスト生成
curl -s http://localhost:11434/api/generate \
  -d '{"model":"llama3.2","prompt":"Hello","stream":false}' | jq .response

# piper-plus で音声合成
curl -X POST http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"こんにちは","language":"ja"}' \
  -o hello.wav
```

## GPU 対応

GPU を利用する場合は、`docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d` で起動してください (GPU オーバーライドファイルは今後追加予定)。

## 停止

```bash
docker compose down
# データも含めて完全に削除する場合
docker compose down -v
```

## 関連

- [LLM エコシステム統合ガイド](../../docs/guides/llm-ecosystem.md)
- [Open WebUI 統合ガイド](../../docs/guides/open-webui-integration.md)
- [piper-plus API 仕様](../../docs/guides/open-webui-integration.md#api-仕様)
