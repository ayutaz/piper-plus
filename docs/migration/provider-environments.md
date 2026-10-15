# 開発版の Python provider と WebUI 環境

この変更は開発ブランチ用です。公開済み v2.0.1 の依存 metadata を変更するものではありません。

## CPU / GPU の選択

次のソースビルドから `piper-plus` の基底依存は ORT を含みません。CPU/GPU wheel は同じ `onnxruntime` module を提供するため、**どちらか一方**を選びます。既存環境を変更する場合は新しい venv を使用してください。

```bash
# ソースパッケージから CPU 用環境へ
uv pip install "src/python_run[cpu]"
# または別の新しい環境へ GPU 用を導入（CUDA 12 / cuDNN の要件は別途必要）
uv pip install "src/python_run[gpu]"
```

root workspace は `cpu` dependency group を既定で有効にし、従来の CPU / training 開発用構成を維持します。GPU のときは既定 CPU group を除きます。

```bash
uv sync --locked --extra inference
uv sync --locked --no-group cpu --extra inference-gpu
uv run --no-sync python -m piper_plus --help
```

root の `inference` / `train` / `cpu` group と `inference-gpu` は排他です。provider を切り替えた後は、通常の `uv sync` で別構成に戻さず、実行に `uv run --no-sync` を使います。
uv の group 選択は [公式の依存管理ドキュメント](https://docs.astral.sh/uv/concepts/projects/dependencies/#default-groups) に従います。

公開済み v2.0.1 の `piper-plus[gpu]` は CPU ORT も要求します。ここでの GPU 手順は、この修正を含むソースからの導入を対象としています。

## WebUI

Gradio 6.26.0 は HF Hub 1.x を要求し、root の Transformers 4.x 学習環境は HF Hub <1 を要求します。専用 lock を持つ環境を使用します。

```bash
uv sync --project environments/webui --locked
uv run --project environments/webui --no-sync python -m piper_plus.webui
```

root 環境へ `requirements_webui.txt` を直接入れる手順は使用しません。
学習を UI から起動するときは、`PIPER_PLUS_TRAINING_PYTHON` を root の学習環境の Python の絶対パスに設定します。[WebUI ガイド](../features/webui.md#ui-と学習環境の分離)を参照してください。UI は指定された interpreter の依存を確認し、その interpreter で学習 worker を起動します。入力は `piper_train` 用に前処理済みの dataset を用意してください。

## 検査

`consumer-contracts.yml` は CPU/GPU の export 結果、クリーンな GPU package 導入、CPU fallback 推論、WebUI の lock・依存整合・interface 作成を検査します。通常の GitHub-hosted runner で CUDA ハードウェア実行や音声品質を承認するものではありません。
