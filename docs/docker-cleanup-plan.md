# Docker環境 整理・最新化計画

> **作成日**: 2026-03-07
> **ブランチ**: `refactor/docker-cleanup`
> **ステータス**: 計画策定完了・実装待ち

## 目次

- [1. 現状のDocker環境マップ](#1-現状のdocker環境マップ)
- [2. 調査で発見した問題一覧](#2-調査で発見した問題一覧)
- [3. 構造上の根本的課題](#3-構造上の根本的課題)
- [4. 整理方針](#4-整理方針)
- [5. 実装ロードマップ](#5-実装ロードマップ)

---

## 1. 現状のDocker環境マップ

### Dockerfiles (8ファイル)

| ファイル | 役割 | 状態 |
|----------|------|------|
| `Dockerfile` (ルート) | マルチアーキテクチャC++バイナリビルド | 動作するがDebian bullseye EOL間近 |
| `docker/python-inference/Dockerfile` | Python推論 (ONNX Runtime) | **動作不可** |
| `docker/python-train/Dockerfile` | Python学習 | **動作不可** |
| `docker/cpp-inference/Dockerfile` | C++バイナリ推論 (プロダクション) | 部分的に動作 |
| `docker/cpp-inference/Dockerfile.simple` | C++推論 簡易版 | 部分的に動作 |
| `docker/cpp-train/Dockerfile` | C++開発環境 | 未定義CMakeオプション問題 |
| `docker/webui/Dockerfile` | WebUI推論 | **動作不可** |
| `src/python/Dockerfile` | **廃止状態** (pytorch-lightning 1.7) | 完全に廃止 |

※ `build/p/src/piper_phonemize_external/Dockerfile` はビルド成果物（管理対象外）

### Docker関連ファイル

| ファイル | 役割 |
|----------|------|
| `docker/webui/docker-compose.yml` | WebUIのCompose定義 |
| `docker/python-inference/requirements-inference.txt` | Python推論の依存 |
| `docker/python-inference/requirements-inference-arm64.txt` | Python推論の依存 (ARM64) |
| `docker/python-train/requirements-train.txt` | Python学習の依存 (74行) |
| `docker/python-train/requirements-torch.txt` | PyTorch依存 |
| `docker/python-inference/inference.py` | 推論スクリプト (旧API) |
| `docker/python-inference/test.py` | 推論テスト |
| `docker/python-train/entrypoint.sh` | 学習エントリポイント (**Dockerfileから未参照**) |
| `docker/python-train/test.py` | 学習テスト (**Dockerfileから未参照**) |
| `docker/cpp-inference/entrypoint.sh` | C++推論エントリポイント |
| `docker/cpp-inference/test.sh` | C++推論テスト |
| `docker/cpp-train/build.sh` | C++ビルドスクリプト |
| `docker/cpp-train/test.sh` | C++テスト |
| `docker/webui/run.sh` | WebUI起動スクリプト |
| `docker/test-docker.sh` | Docker統合テスト |
| `docker/test-docker-minimal.sh` | Docker最小テスト |
| `docker/integration-test.sh` | 統合テスト |
| `docker/test-inference.py` | 推論テスト |
| `docker/README.md` | ドキュメント (**現状と乖離**) |
| `.dockerignore` | ルート用Docker ignore |
| `src/python/.dockerignore` | Python用Docker ignore |

### CI/CDワークフロー (4ファイル)

| ファイル | 対象 |
|----------|------|
| `.github/workflows/build-docker-images.yml` | Dockerイメージビルド |
| `.github/workflows/docker-build-minimal.yml` | 最小Dockerビルド |
| `.github/workflows/docker-build.yml` | Dockerビルド |
| `.github/workflows/docker-test.yml` | Dockerテスト |

---

## 2. 調査で発見した問題一覧

5エージェントによる並列調査の結果、合計25件の問題を発見。

### 致命的 (Critical) — 8件

ビルドまたは実行が完全に不可能な問題。

| # | 対象 | 問題 | 影響 |
|---|------|------|------|
| C-1 | `docker/python-inference/inference.py` | `synthesize()` API呼び出しが不正。`wav_file` 引数が不足しTypeError | Python推論Docker完全動作不可 |
| C-2 | `docker/python-inference/Dockerfile` | 旧パイプライン (`src/python_run`) を参照。現在のpiper-plusの推論 (`piper_train.infer_onnx`) と完全不一致。`COPY src/python_run` は存在しないパス | 最新モデル (prosody_features対応) が使用不可 |
| C-3 | `docker/python-inference/requirements-inference.txt` | `pyopenjtalk` が依存に未記載 | 日本語テキストの音素化が不可能、RuntimeError |
| C-4 | `docker/python-train/requirements-train.txt` | `pytorch-lightning` が依存に未記載 | `python -m piper_train` がImportErrorで失敗 |
| C-5 | `docker/python-train/requirements-train.txt` | `g2p-en`, `pyopenjtalk-plus`, `onnxsim-prebuilt`, `torchmetrics` が依存に不足 | 学習環境が完全に不完全 |
| C-6 | `docker/webui/Dockerfile` | `piper-phonemize` (GPL) が必要だがespeak-ngが未インストール。pip installで失敗 | WebUIビルド失敗 |
| C-7 | `docker/webui/Dockerfile` | `PYTHONPATH` とモジュールパスの不整合。`piper` モジュールが見つからない | WebUI実行時にImportError |
| C-8 | `Dockerfile` (ルート) | `debian:bullseye` (Debian 11) は2026年8月にEOL | セキュリティパッチ停止 |

### 重大 (Major) — 9件

保守性やアーキテクチャに重大な影響を与える問題。

| # | 対象 | 問題 | 影響 |
|---|------|------|------|
| M-1 | `docker/python-inference/Dockerfile` | ベースイメージ (nvidia/cuda + PyTorch) が推論には過大。torch 2.5GB + 不要なCUDA依存 | イメージサイズ肥大化 |
| M-2 | `docker/python-inference/Dockerfile` | ARM64版で `piper-phonemize>=1.0.0` が指定されているがPyPI未公開 | ARM64ビルド不可 |
| M-3 | `docker/cpp-inference/Dockerfile` + `Dockerfile` | 依存ビルド方式が完全に異なる (ExternalProject vs 手動autotools)。espeak-ng, piper-phonemize, OpenJTalkが重複 | 保守コスト大 |
| M-4 | 全Dockerfiles | ONNX Runtimeバージョン不一致 (ルート: 1.14.1, docker/cpp-*: 1.17.1) | モデル互換性リスク |
| M-5 | `docker/cpp-inference/Dockerfile` | OpenJTalkの共有ライブラリCOPYパターンが静的ライブラリ (.a) 構成と不整合 | ランタイムエラーの可能性 |
| M-6 | `Dockerfile` + `CMakeLists.txt` | ARM64の最適化レベルが `-O0` にハードコード | ARM64パフォーマンス著しく低下 |
| M-7 | CI/CDワークフロー全体 | 4つのワークフロー間の責務が不明確。WebUIがどのワークフローにも未含有 | WebUIの自動テスト・ビルドなし |
| M-8 | CI/CDワークフロー全体 | ghcr.ioへの定期的な自動pushが未設定 (workflow_dispatch手動のみ) | 継続的デプロイメントなし |
| M-9 | `docker/cpp-train/Dockerfile` | `USE_CUDA=ON` を指定しているがCMakeLists.txtにこのオプション定義なし | オプションが無視される |

### 中程度・軽微 (Medium/Minor) — 8件

改善が推奨される問題。

| # | 対象 | 問題 | 影響 |
|---|------|------|------|
| L-1 | `docker/python-train/requirements-train.txt` | 74行の「キッチンシンク」型。不要パッケージ多数 (spacy, nltk等) | ビルド時間・イメージサイズ増大 |
| L-2 | `docker/python-train/` | `entrypoint.sh`, `test.py` がDockerfileから参照されていない (デッドファイル) | メンテナンスコスト |
| L-3 | `Dockerfile` (ルート) | `COPY . .` で不要なPythonソース等がコンテキストに含まれる | ビルド時間増加、キャッシュ効率低下 |
| L-4 | `Dockerfile` (ルート) | ccacheがBuildKit cache mountなしで効果なし | リビルド時間削減不可 |
| L-5 | `Dockerfile` (ルート) | piper-phonemizeがmaster HEAD固定で再現性なし | ビルドの再現性欠如 |
| L-6 | `docker/webui/docker-compose.yml` | ヘルスチェックでcurlを使用するが未インストール | ヘルスチェック機能しない |
| L-7 | `src/python/Dockerfile` | 完全に廃止状態 (pytorch-lightning 1.7) | 混乱の原因 |
| L-8 | `docker/README.md` | 現状と乖離 (WebUI記載なし、コマンド古い等) | ユーザーの混乱 |

---

## 3. 構造上の根本的課題

### 3.1 推論パイプラインの二重化

piper-plusには**2つの完全に異なる推論パイプライン**が混在している。

| 項目 | 旧パイプライン | 新パイプライン |
|------|---------------|---------------|
| モジュール | `src/python_run/piper` | `piper_train.infer_onnx` |
| 実装 | C++バインディングベース | Pure Python |
| prosody対応 | なし | あり (A1/A2/A3) |
| テキスト直接入力 | なし | `--text` オプション |
| Docker環境 | こちらを参照 | 未対応 |
| ローカル開発 | 使用していない | **現在使用中** |

**根本的な問題**: Docker環境が旧パイプラインを参照しているが、旧パイプラインのパス (`src/python_run`) は既に存在しない。ローカル開発と Docker環境が完全に乖離している。

**影響範囲**:
- `docker/python-inference/Dockerfile` — `COPY src/python_run` (存在しない)
- `docker/python-inference/inference.py` — 旧APIを使用
- `docker/webui/Dockerfile` — `piper` モジュールをインポート (存在しない)

### 3.2 依存管理の断片化

依存管理が**4つの異なるシステム**に分断されている。

| システム | 用途 | ファイル |
|----------|------|---------|
| uv | ローカル開発 (推奨) | `pyproject.toml` |
| pip + requirements.txt | Docker環境 | `docker/*/requirements*.txt` |
| setup.py | レガシーパッケージング | `setup.py` |
| pyproject.toml | uvが使用 | `pyproject.toml` |

**根本的な問題**: ローカル開発 (uv) とDocker環境 (pip) で依存が同期されていない。致命的問題 C-3, C-4, C-5 の直接の原因。

### 3.3 CI/CDの不整合

4つのDocker関連ワークフローが存在するが、責務が不明確で重複している。

| ワークフロー | ファイル |
|-------------|---------|
| build-docker-images | `.github/workflows/build-docker-images.yml` |
| docker-build-minimal | `.github/workflows/docker-build-minimal.yml` |
| docker-build | `.github/workflows/docker-build.yml` |
| docker-test | `.github/workflows/docker-test.yml` |

**根本的な問題**:
- WebUIがどのワークフローにも含まれていない
- ghcr.ioへの自動pushが未設定
- ワークフロー間の責務の重複と曖昧さ

---

## 4. 整理方針

### 残すもの (維持・改修)

| ファイル | 方針 |
|----------|------|
| `Dockerfile` (ルート) | ベースイメージをDebian bookwormに更新、ARM64最適化修正 |
| `docker/cpp-inference/Dockerfile` | ONNX Runtimeバージョン統一、共有ライブラリCOPY修正 |
| `docker/cpp-inference/Dockerfile.simple` | 維持 |
| `docker/cpp-train/Dockerfile` | 未定義CMakeオプション修正 |
| `docker/webui/Dockerfile` | 新推論パイプラインで書き直し |
| `docker/webui/docker-compose.yml` | ヘルスチェック修正 |
| `.dockerignore` | 最適化 |

### 廃止するもの (削除)

| ファイル | 理由 |
|----------|------|
| `src/python/Dockerfile` | 完全に廃止状態 (pytorch-lightning 1.7) |
| `src/python/.dockerignore` | 上記Dockerfileと共に不要 |
| `docker/python-train/entrypoint.sh` | Dockerfileから未参照のデッドファイル |
| `docker/python-train/test.py` | Dockerfileから未参照のデッドファイル |

### 新規作成・書き直すもの

| ファイル | 内容 |
|----------|------|
| `docker/python-inference/Dockerfile` | **書き直し**: `piper_train.infer_onnx` ベース、pyproject.tomlから依存インストール |
| `docker/python-inference/inference.py` | **書き直し**: 新推論パイプライン対応 |
| `docker/python-train/Dockerfile` | **書き直し**: pyproject.tomlから依存インストール |
| `docker/python-inference/requirements-inference.txt` | **廃止候補**: pyproject.tomlの依存グループに統合 |
| `docker/python-inference/requirements-inference-arm64.txt` | **廃止候補**: 同上 |
| `docker/python-train/requirements-train.txt` | **廃止候補**: 同上 |
| `docker/python-train/requirements-torch.txt` | **廃止候補**: 同上 |
| `docker/README.md` | **書き直し**: 現状に合わせた内容に更新 |

### 依存管理の統合方針

requirements.txtの個別管理をやめ、`pyproject.toml` の依存グループ (`optional-dependencies`) に統合する。

```toml
# pyproject.toml (方針イメージ)
[project.optional-dependencies]
inference = ["onnxruntime>=1.17", "pyopenjtalk-plus", "g2p-en"]
train = ["pytorch-lightning>=2.0", "torchmetrics", ...]
```

Docker内では `pip install .[inference]` や `pip install .[train]` で依存をインストールする。

### CI/CDの統合方針

4つのワークフローを整理し、責務を明確化する。

| 新ワークフロー | 責務 |
|---------------|------|
| `docker-build.yml` | 全Dockerイメージのビルド + ghcr.io push |
| `docker-test.yml` | ビルド後の統合テスト |

---

## 5. 実装ロードマップ

### Phase 1: 致命的問題の修正 (動作可能にする)

**目標**: Python推論・学習・WebUIのDockerイメージを動作可能にする

#### タスク一覧

| # | タスク | 対象 | 問題番号 |
|---|--------|------|---------|
| 1-1 | Python推論Dockerfileを `piper_train.infer_onnx` ベースで書き直し | `docker/python-inference/Dockerfile` | C-1, C-2, C-3 |
| 1-2 | 推論スクリプトを新パイプラインで書き直し | `docker/python-inference/inference.py` | C-1, C-2 |
| 1-3 | Python学習Dockerfileの依存を修正 | `docker/python-train/Dockerfile` | C-4, C-5 |
| 1-4 | WebUI Dockerfileをespeak-ng不要な構成で書き直し | `docker/webui/Dockerfile` | C-6, C-7 |
| 1-5 | ルートDockerfileのベースイメージをbookwormに更新 | `Dockerfile` | C-8 |
| 1-6 | 廃止ファイルの削除 | `src/python/Dockerfile`, デッドファイル | L-7, L-2 |
| 1-7 | 各Dockerイメージのビルド・動作確認 | 全体 | — |

**成果物**: 全Dockerイメージがビルド＆基本動作する状態

### Phase 2: 依存管理の統合 + 構造改善

**目標**: 依存管理を一元化し、保守性を改善する

#### タスク一覧

| # | タスク | 対象 | 問題番号 |
|---|--------|------|---------|
| 2-1 | `pyproject.toml` に `inference`/`train` 依存グループを追加 | `pyproject.toml` | — |
| 2-2 | Docker内で `pip install .[inference]` / `.[train]` を使用するよう変更 | `docker/python-*/Dockerfile` | — |
| 2-3 | 不要になったrequirements.txtを削除 | `docker/*/requirements*.txt` | L-1 |
| 2-4 | ONNX Runtimeバージョンの統一 | 全Dockerfiles | M-4 |
| 2-5 | C++推論のビルド方式統一検討 | `docker/cpp-inference/Dockerfile`, `Dockerfile` | M-3 |
| 2-6 | Python推論の軽量イメージ作成 (CPU用) | `docker/python-inference/Dockerfile` | M-1 |
| 2-7 | ARM64ビルドの修正 | `Dockerfile`, `docker/python-inference/Dockerfile` | M-2, M-6 |
| 2-8 | C++開発DockerfileのCMakeオプション修正 | `docker/cpp-train/Dockerfile` | M-9 |
| 2-9 | OpenJTalk共有ライブラリCOPYの修正 | `docker/cpp-inference/Dockerfile` | M-5 |
| 2-10 | WebUI docker-compose.ymlのヘルスチェック修正 | `docker/webui/docker-compose.yml` | L-6 |

**成果物**: 依存管理が `pyproject.toml` に一元化、Docker間の不整合が解消

### Phase 3: CI/CD整備 + ドキュメント更新

**目標**: CI/CDの責務を明確化し、ドキュメントを最新化する

#### タスク一覧

| # | タスク | 対象 | 問題番号 |
|---|--------|------|---------|
| 3-1 | CI/CDワークフローの責務整理・統合 | `.github/workflows/docker-*.yml` | M-7 |
| 3-2 | ghcr.ioへの自動push設定 | `.github/workflows/docker-build.yml` | M-8 |
| 3-3 | WebUIをCI/CDに追加 | `.github/workflows/docker-build.yml` | M-7 |
| 3-4 | ルートDockerfileのビルド最適化 (.dockerignore改善, ccache, piper-phonemizeコミット固定) | `Dockerfile`, `.dockerignore` | L-3, L-4, L-5 |
| 3-5 | `docker/README.md` の全面書き直し | `docker/README.md` | L-8 |
| 3-6 | 全Dockerイメージの最終統合テスト | 全体 | — |

**成果物**: CI/CDが整備され、ドキュメントが最新化された状態

---

## 補足: 調査体制

本調査は以下の5エージェントによる並列調査で実施。

| エージェント | 担当領域 |
|-------------|---------|
| python-inference-investigator | Python推論Docker環境 |
| python-train-investigator | Python学習Docker環境 |
| cpp-docker-investigator | C++推論/開発Docker環境 |
| webui-cicd-investigator | WebUI・CI/CDワークフロー |
| root-dockerfile-investigator | ルートDockerfile |
