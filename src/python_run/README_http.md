# Piper HTTP Server

Install the requirements into your virtual environment:

```sh
uv pip install -r requirements_http.txt
```

Run the web server:

```sh
.venv/bin/python3 -m piper.http_server --model ...
```

See `--help` for more options.

Using a `GET` request:

```sh
curl -G --data-urlencode 'text=This is a test.' -o test.wav 'localhost:5000'
```

Using a `POST` request:

```sh
curl -X POST -H 'Content-Type: text/plain' --data 'This is a test.' -o test.wav 'localhost:5000'
```

### Phoneme Timing Endpoint

**`GET/POST /api/phoneme-timing`** - 音素タイミング情報を返す

Query Parameters:
- `text` (required): 合成するテキスト
- `format`: 出力形式 (`json` または `tsv`、デフォルト: `json`)
- `language`: 言語コード (`ja`, `en`, `zh`, `ko`, `es`, `fr`, `pt`, `sv`)
- `language_id`: 数値の言語 ID (language より優先)

Examples:
```bash
# JSON で取得
curl "http://localhost:5000/api/phoneme-timing?text=Hello&format=json"

# TSV で取得
curl "http://localhost:5000/api/phoneme-timing?text=Hello&format=tsv"

# POST + 日本語
curl -X POST "http://localhost:5000/api/phoneme-timing?language=ja&format=json" \
  -d "こんにちは"
```

レスポンス: 200 OK で JSON または TSV を返す。モデルが durations 出力を持たない場合は 400 を返す。
