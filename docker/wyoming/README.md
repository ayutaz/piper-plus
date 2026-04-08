# Wyoming Protocol adapter for piper-plus

Home Assistant Wyoming Protocol TTS adapter.  Exposes piper-plus as a TTS
provider that Home Assistant discovers automatically.

## Quick start

```bash
cd docker/wyoming
docker compose up -d
```

The default model (`tsukuyomi`) is downloaded from HuggingFace on first
startup.  Subsequent starts use the cached model.

## Home Assistant setup

1. Open **Settings > Devices & Services > Add Integration**.
2. Search for **Wyoming Protocol**.
3. Enter the Docker host IP and port `10200`.
4. The TTS provider appears as "piper-plus" with per-language voices.

## Environment variables

Copy `.env.example` to `.env` to customise:

| Variable | Default | Description |
|----------|---------|-------------|
| `PIPER_MODEL` | `tsukuyomi` | Model alias, HuggingFace repo ID, or path |
| `PIPER_LANGUAGE` | `ja` | Default language (`ja`, `en`, `zh`, `es`, `fr`, `pt`) |
| `PIPER_SPEAKER_ID` | `0` | Speaker ID for multi-speaker models |
| `PIPER_PORT` | `10200` | Host port mapping |

## Using a custom / local model

Mount the directory containing your `.onnx` and `config.json` files:

```yaml
services:
  wyoming-piper-plus:
    volumes:
      - ./models:/app/models:ro
    command:
      - --model
      - /app/models/my-model.onnx
      - --uri
      - tcp://0.0.0.0:10200
```

## Build from source

From the project root:

```bash
docker build -t wyoming-piper-plus -f docker/wyoming/Dockerfile .
```

## Supported languages

| Code | Language |
|------|----------|
| `ja` | Japanese |
| `en` | English |
| `zh` | Chinese |
| `es` | Spanish |
| `fr` | French |
| `pt` | Portuguese |

## Troubleshooting

**Container exits immediately** -- Check logs with `docker compose logs`.
The most common cause is a network issue preventing the model download.
Ensure the container can reach `huggingface.co`.

**Home Assistant does not discover the service** -- Verify the port is
reachable: `nc -zv <host> 10200`.  If running on a different machine,
ensure no firewall blocks the port.

**Slow first response** -- The first synthesis after startup includes a
model warmup phase (~1-2 s).  Subsequent requests are faster.
