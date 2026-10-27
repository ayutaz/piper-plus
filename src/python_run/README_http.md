# Piper HTTP Server

FastAPI ベースの HTTP サーバー。`/synthesize` の代わりにルート (`/`) で WAV を返し、
`?streaming=true` で **チャンク転送 (chunked transfer) ストリーミング** にも対応します。

## インストール

`[http]` extras は `fastapi` + `uvicorn[standard]` だけを入れます。v2.0.2 は
ONNX Runtime を基底依存に含めないため、CPU なら `[cpu]`、GPU なら `[gpu]` を
一緒に指定します。

```sh
uv pip install "piper-plus[cpu,http]"
```

`uv add` を使う場合:

```sh
uv add "piper-plus[cpu,http]"
```

GPU は `[cpu,http]` の代わりに `[gpu,http]` を使います。

## 起動

```sh
.venv/bin/python3 -m piper_plus.http_server --model ...
```

`--help` で全オプション一覧。デフォルトは `--host 0.0.0.0 --port 5000`。

## エンドポイント

| メソッド | パス | 用途 |
|--------|------|-----|
| GET / POST | `/` | テキストから WAV を合成して返す |
| GET / POST | `/api/phoneme-timing` | 音素タイミング情報を JSON / TSV で返す |
| GET | `/docs` | Swagger UI (FastAPI 自動生成) |
| GET | `/openapi.json` | OpenAPI 仕様 |

### `/` — 音声合成

#### 通常 (一括) リクエスト

`GET`:

```sh
curl -G --data-urlencode 'text=This is a test.' -o test.wav 'localhost:5000'
```

`POST`:

```sh
curl -X POST -H 'Content-Type: text/plain' \
  --data 'This is a test.' -o test.wav 'localhost:5000'
```

#### ストリーミング (`?streaming=true`)

`Transfer-Encoding: chunked` で WAV を逐次配信します。文単位に音声を生成し、
ヘッダーは「サイズ未確定」用のプレースホルダー (`0xFFFFFFFF`) を埋め込むため、
ブラウザ / `ffmpeg` / 多くの音声プレーヤーでそのまま再生できます。

```sh
# ストリーミングで取得し ffplay で逐次再生
curl -N -X POST -H 'Content-Type: text/plain' \
  --data 'これはストリーミング再生のテストです。次の文も続けて流します。' \
  'http://localhost:5000/?streaming=true' | ffplay -nodisp -autoexit -
```

`streaming` の有効値: `true` / `1` / `yes` / `on` (大文字小文字無視)。

#### `/` のクエリパラメータ

| パラメータ | 型 | 説明 |
|-----------|----|------|
| `text` | string | 合成対象テキスト (`POST` 時はリクエストボディでも可) |
| `language` | string | 言語コード (`ja`, `en`, `zh`, `ko`, `es`, `fr`, `pt`, `sv`) |
| `language_id` | int | 数値の言語 ID (`language` より優先) |
| `streaming` | bool | `true` でチャンク転送 (デフォルト: `false`) |

`POST /` は `text/plain` の本文をテキストとして受け取ります。JSON body を
送る場合は、サーバーが受け付ける `text`、`speaker_id`、および
`speaker_embedding`（モデル互換の float32 配列）のフィールドを使用してください。

#### `/api/phoneme-timing` のクエリパラメータ

| パラメータ | 型 | 説明 |
|-----------|----|------|
| `text` | string | 音素化対象テキスト (`POST` 時はリクエストボディでも可) |
| `language` | string | 言語コード (`ja`, `en`, `zh`, `ko`, `es`, `fr`, `pt`, `sv`) |
| `language_id` | int | 数値の言語 ID (`language` より優先) |
| `format` | string | `json` (デフォルト) または `tsv` |

### `/api/phoneme-timing` — 音素タイミング

```sh
# JSON
curl 'http://localhost:5000/api/phoneme-timing?text=Hello&format=json'

# TSV
curl 'http://localhost:5000/api/phoneme-timing?text=Hello&format=tsv'

# POST + 日本語
curl -X POST 'http://localhost:5000/api/phoneme-timing?language=ja&format=json' \
  -d 'こんにちは'
```

`200 OK` で JSON または TSV を返します。モデルが duration 出力を持たない場合は
`400 Bad Request` (`{"error": "Model does not support duration output"}`) を返します。

## v1.11 以前 (Flask) からの互換性

v1.12.0 で HTTP サーバーは Flask から FastAPI に移行しましたが、URL / クエリパラメータは互換です:

- `GET/POST /` で WAV を返す挙動は変更なし
- `/api/phoneme-timing` のレスポンス形状も同一
- 追加: `?streaming=true` クエリ
- 追加: `/docs` (Swagger UI), `/openapi.json`
