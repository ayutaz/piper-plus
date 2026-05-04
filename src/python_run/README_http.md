# Piper HTTP Server

FastAPI ベースの HTTP サーバー。`/synthesize` の代わりにルート (`/`) で WAV を返し、
`?streaming=true` で **チャンク転送 (chunked transfer) ストリーミング** にも対応します。

## インストール

`[http]` extras で `fastapi` + `uvicorn[standard]` を入れます。

```sh
uv pip install "piper-plus[http]"
```

`uv add` を使う場合:

```sh
uv add "piper-plus[http]"
```

## 起動

```sh
.venv/bin/python3 -m piper.http_server --model ...
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

#### クエリパラメータ (両エンドポイント共通)

| パラメータ | 型 | 説明 |
|-----------|----|------|
| `text` | string | 合成対象テキスト (`POST` 時はリクエストボディでも可) |
| `language` | string | 言語コード (`ja`, `en`, `zh`, `ko`, `es`, `fr`, `pt`, `sv`) |
| `language_id` | int | 数値の言語 ID (`language` より優先) |
| `streaming` | bool | `/` のみ。`true` でチャンク転送 (デフォルト: `false`) |
| `format` | string | `/api/phoneme-timing` のみ。`json` (デフォルト) または `tsv` |

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
