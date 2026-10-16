# Python 2.0.2 の provider と WebUI 環境

v2.0.2 から CPU/GPU の provider を明示的に選択します。旧 v2.0.1 の依存 metadata は変更されません。

## CPU / GPU の選択

v2.0.2 から `piper-plus` の基底依存は ORT を含みません。CPU/GPU wheel は同じ `onnxruntime` module を提供するため、**どちらか一方**を選びます。既存環境を変更する場合は新しい venv を使用してください。

```bash
# CPU 用の新しい環境へ
uv pip install "piper-plus[cpu]==2.0.2"
# または別の新しい環境へ GPU 用を導入（CUDA 12 / cuDNN の要件は別途必要）
uv pip install "piper-plus[gpu]==2.0.2"
```

root workspace は `cpu` dependency group を既定で有効にし、従来の CPU / training 開発用構成を維持します。GPU のときは既定 CPU group を除きます。

```bash
uv sync --locked --extra inference
uv sync --locked --no-group cpu --extra inference-gpu
uv run --no-sync python -m piper_plus --help
```

root の `inference` / `train` / `cpu` group と `inference-gpu` は排他です。provider を切り替えた後は、通常の `uv sync` で別構成に戻さず、実行に `uv run --no-sync` を使います。
uv の group 選択は [公式の依存管理ドキュメント](https://docs.astral.sh/uv/concepts/projects/dependencies/#default-groups) に従います。

公開済み v2.0.1 の `piper-plus[gpu]` は CPU ORT も要求します。GPU を使う場合は v2.0.2 の `[gpu]` を新規環境へ導入してください。

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
