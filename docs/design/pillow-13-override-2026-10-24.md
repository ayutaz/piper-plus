# gradio を入れる環境で Pillow を 13.0.0 に上げる (2026-10-24)

## 何が起きたか

PR #853 の Trivy Container Scan で、CUDA 版 python-inference image が CRITICAL 5 件で失敗した。5 件とも Pillow 12.3.0 の advisory である。

- CVE-2026-112393: libtiff で圧縮 TIFF を書くときの heap buffer overflow
- CVE-2026-112398: FlashPix の JPEG タイル復号でのバッファ外書き込み
- CVE-2026-112403: JPEG の draft scale 指定時のバッファ外書き込み
- CVE-2026-112900: EPS 入力で Ghostscript に渡す引数の注入
- CVE-2026-96639: 複数フレームの読み込みでの確保サイズの取り違え

ほかに HIGH と MEDIUM が 35 件以上ある。すべて Pillow 13.0.0 で修正された。PR の変更とは関係がなく、dev の image も次に scan すれば同じ理由で失敗する。

## なぜ普通に上げられないか

gradio は 6.26.0 (このリポジトリの pin) も 6.30.0 (最新) も `pillow<13.0,>=8.0` を宣言している。そのため、`requirements_webui.txt` を普通に入れると 12.3.0 に解決される。gradio を上げるだけでは解決しない。

root の `uv.lock` には gradio が含まれない。Pillow は matplotlib などから入るだけなので、`uv lock --upgrade-package pillow` だけで 13.0.0 に上がる。

## 対応

gradio を入れるすべての場所で、Pillow の上限を上書きする。

| 場所 | 方法 |
|------|------|
| `docker/python-inference/Dockerfile`、`Dockerfile.cpu`、`Dockerfile.cpu.distroless`、`docker/webui/Dockerfile`、`Dockerfile.distroless` | `uv pip install -r requirements_webui.txt --override overrides_webui.txt` |
| `environments/webui` (文書が案内する WebUI の導入先) | `[tool.uv] override-dependencies = ["pillow>=13.0.0"]` と lock の更新 |
| root `uv.lock` | `uv lock --upgrade-package pillow` |

上書きの中身は `src/python_run/overrides_webui.txt` の 1 行 (`pillow>=13.0.0`) で、`environments/webui/pyproject.toml` にも同じ値を書く。

## 上書きしても動くか

WebUI が gradio で扱うのはテキストと音声だけで、画像の入力は受け付けない。gradio 6.26.0 と Pillow 13.0.0 を入れた環境で、次を確かめた。

- `import gradio` と `Blocks` の構築
- `launch()` した app に `gradio_client` から文字列を送り、`gr.Audio` の出力 (WAV) を受け取れる
- 同じ画面に `gr.Image(type="pil")` を置いても構築できる。PIL での PNG 保存もできる

Docker image のビルドと各 image 内の `import gradio` は、CI の Docker build と Trivy Container Scan で確かめる。

## 対象外

Hugging Face Space (`huggingface-space/requirements.txt`) は、Space SDK が gradio を入れる。pip の 1 回の install に注入されるので上書きの手段がなく、今回は対象外とする。

## 再発防止

`tests/scripts/test_webui_pillow_override.py` (pre-commit `webui-pillow-override`) は次を検査する。

1. `overrides_webui.txt` が Pillow を 13.0.0 以上に上書きしていること
2. `environments/webui/pyproject.toml` の `override-dependencies` が同じ内容であること
3. `requirements_webui.txt` を入れる Dockerfile がすべて `--override` を付け、上書きファイルを COPY していること。対象の Dockerfile が 5 本以上見つかること
4. root と `environments/webui` の lock が Pillow 13.0.0 以上に解決していること

gradio が Pillow 13 を許すようになったら、上書きファイル、Dockerfile の `--override`、pyproject の項目、このテストを削除する。
