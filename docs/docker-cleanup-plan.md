# Docker環境 整理・最新化計画

> **作成日**: 2026-03-07
> **ブランチ**: `refactor/docker-cleanup`
> **ステータス**: 全Phase完了

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
| `Dockerfile` (ルート) | マルチアーキテクチャC++バイナリビルド | ✅ Phase 1でbookworm化、Phase 2でONNX Runtime動的化 |
| `docker/python-inference/Dockerfile` | Python推論 (ONNX Runtime) | ✅ Phase 1で書き直し、Phase 2でuv化 |
| `docker/python-train/Dockerfile` | Python学習 | ✅ Phase 1で依存修正、Phase 2でuv化 |
| `docker/cpp-inference/Dockerfile` | C++バイナリ推論 (プロダクション) | ✅ Phase 4でCMake ExternalProject方式に全面書き直し |
| `docker/cpp-inference/Dockerfile.simple` | C++推論 簡易版 | 維持 |
| `docker/cpp-dev/Dockerfile` | C++開発環境 | ✅ Phase 2でUSE_CUDA定義追加 (CMakeLists.txt) |
| `docker/webui/Dockerfile` | WebUI推論 | ✅ Phase 1で書き直し、Phase 2でuv化 |
| `src/python/Dockerfile` | **廃止** — Phase 1で削除済み | 🗑️ 削除済み |

※ `build/p/src/piper_phonemize_external/Dockerfile` はビルド成果物（管理対象外）

### Docker関連ファイル

| ファイル | 役割 | 状態 |
|----------|------|------|
| `docker/webui/docker-compose.yml` | WebUIのCompose定義 | ✅ Phase 1でヘルスチェック修正 |
| `docker/python-inference/requirements-inference.txt` | Python推論の依存 | 🗑️ Phase 2で削除 |
| `docker/python-inference/requirements-inference-arm64.txt` | Python推論の依存 (ARM64) | 🗑️ Phase 2で削除 |
| `docker/python-train/requirements-train.txt` | Python学習の依存 | 🗑️ Phase 2で削除 |
| `docker/python-train/requirements-torch.txt` | PyTorch依存 | 🗑️ Phase 2で削除 |
| `requirements.txt` (ルート) | 推論依存 | 🗑️ Phase 2で削除 |
| `requirements-train.txt` (ルート) | 学習依存 | 🗑️ Phase 2で削除 |
| `docker/python-inference/inference.py` | 推論スクリプト | ✅ Phase 1で書き直し |
| `docker/python-inference/test.py` | 推論テスト | 維持 |
| `docker/python-train/entrypoint.sh` | 学習エントリポイント (**Dockerfileから未参照**) | デッドファイル（Phase 1で削除済み） |
| `docker/python-train/test.py` | 学習テスト (**Dockerfileから未参照**) | デッドファイル（Phase 1で削除済み） |
| `docker/cpp-inference/entrypoint.sh` | C++推論エントリポイント | 維持 |
| `docker/cpp-inference/test.sh` | C++推論テスト | 維持 |
| `docker/cpp-dev/build.sh` | C++ビルドスクリプト | 維持 |
| `docker/cpp-dev/test.sh` | C++テスト | 維持 |
| `docker/webui/run.sh` | WebUI起動スクリプト | 維持 |
| `docker/test-docker.sh` | Docker統合テスト | 維持 |
| `docker/test-docker-minimal.sh` | Docker最小テスト | 維持 |
| `docker/integration-test.sh` | 統合テスト | 維持 |
| `docker/test-inference.py` | 推論テスト | 維持 |
| `docker/README.md` | ドキュメント | ✅ Phase 3で全面書き直し |
| `.dockerignore` | ルート用Docker ignore | 維持 |
| `src/python/.dockerignore` | Python用Docker ignore | 🗑️ Phase 1で削除済み |

### CI/CDワークフロー (4ファイル)

| ファイル | 対象 | 状態 |
|----------|------|------|
| `.github/workflows/build-docker-images.yml` | Dockerイメージビルド | 🗑️ Phase 3で削除（docker-build.ymlに統合） |
| `.github/workflows/docker-build-minimal.yml` | 最小Dockerビルド | 🗑️ Phase 3で削除（docker-test.ymlに統合） |
| `.github/workflows/docker-build.yml` | Dockerビルド＆push (5イメージ) | ✅ Phase 3で責務整理・ghcr.io push追加 |
| `.github/workflows/docker-test.yml` | PRスモークテスト (python-inference, webui) | ✅ Phase 3で責務整理・WebUI追加 |
| `.github/workflows/python-tests.yml` | Pythonテスト | ✅ Phase 2でextras_require参照に修正 |
| `.github/workflows/ci.yml` | CI全般 | ✅ Phase 2でextras_require参照に修正 |

---

## 2. 調査で発見した問題一覧

5エージェントによる並列調査の結果、合計25件の問題を発見。

### 致命的 (Critical) — 8件 ✅ 全件Phase 1で修正済み

ビルドまたは実行が完全に不可能な問題。

| # | 対象 | 問題 | 状態 |
|---|------|------|------|
| C-1 | `docker/python-inference/inference.py` | `synthesize()` API呼び出しが不正 | ✅ Phase 1 |
| C-2 | `docker/python-inference/Dockerfile` | 旧パイプライン参照 | ✅ Phase 1 |
| C-3 | `docker/python-inference/requirements-inference.txt` | `pyopenjtalk` 未記載 | ✅ Phase 1 → Phase 2で依存統合 |
| C-4 | `docker/python-train/requirements-train.txt` | `pytorch-lightning` 未記載 | ✅ Phase 1 → Phase 2で依存統合 |
| C-5 | `docker/python-train/requirements-train.txt` | 複数パッケージ不足 | ✅ Phase 1 → Phase 2で依存統合 |
| C-6 | `docker/webui/Dockerfile` | espeak-ng未インストール | ✅ Phase 1 |
| C-7 | `docker/webui/Dockerfile` | PYTHONPATHとモジュールパス不整合 | ✅ Phase 1 |
| C-8 | `Dockerfile` (ルート) | `debian:bullseye` EOL間近 | ✅ Phase 1 (bookworm化) |

### 重大 (Major) — 9件

保守性やアーキテクチャに重大な影響を与える問題。

| # | 対象 | 問題 | 状態 |
|---|------|------|------|
| M-1 | `docker/python-inference/Dockerfile` | ベースイメージが過大 | ✅ Phase 1 (`python:3.11-slim`化) |
| M-2 | `docker/python-inference/Dockerfile` | ARM64版で`piper-phonemize`がPyPI未公開 | ✅ Phase 2 (requirements削除、extras_require化) |
| M-3 | `docker/cpp-inference/Dockerfile` + `Dockerfile` | ビルド方式不統一 | ✅ Phase 3（現状維持、コメントで文書化） |
| M-4 | 全Dockerfiles | ONNX Runtimeバージョン不一致 | ✅ Phase 2 (シンボリックリンク動的化) |
| M-5 | `docker/cpp-inference/Dockerfile` | OpenJTalk共有ライブラリCOPY不整合 | ✅ Phase 4で根本修正（ExternalProject方式に変更） |
| M-6 | `Dockerfile` + `CMakeLists.txt` | ARM64最適化レベル `-O0` | ✅ Phase 2 (`-O2`に修正) |
| M-7 | CI/CDワークフロー全体 | 責務不明確、WebUI未含有 | ✅ Phase 3（責務整理・WebUI追加） |
| M-8 | CI/CDワークフロー全体 | ghcr.io自動push未設定 | ✅ Phase 3（docker-build.ymlにpush設定追加） |
| M-9 | `docker/cpp-dev/Dockerfile` | `USE_CUDA=ON` が未定義 | ✅ Phase 2 (`option(USE_CUDA ...)`追加) |

### 中程度・軽微 (Medium/Minor) — 8件

| # | 対象 | 問題 | 状態 |
|---|------|------|------|
| L-1 | `docker/python-train/requirements-train.txt` | 不要パッケージ多数 | ✅ Phase 2 (requirements削除、extras_require化) |
| L-2 | `docker/python-train/` | デッドファイル | ✅ Phase 1 (削除済み) |
| L-3 | `Dockerfile` (ルート) | `COPY . .` で不要ファイル含有 | ✅ Phase 3（.dockerignore改善） |
| L-4 | `Dockerfile` (ルート) | ccache効果なし | ✅ Phase 3（BuildKitキャッシュマウントTIP追加） |
| L-5 | `Dockerfile` (ルート) | piper-phonemize master HEAD固定 | ✅ Phase 3（NOTEコメント追加） |
| L-6 | `docker/webui/docker-compose.yml` | ヘルスチェックでcurl使用 | ✅ Phase 1 (Python urllib化) |
| L-7 | `src/python/Dockerfile` | 完全に廃止状態 | ✅ Phase 1 (削除済み) |
| L-8 | `docker/README.md` | 現状と乖離 | ✅ Phase 3（全面書き直し） |

---

## 3. 構造上の根本的課題

### 3.1 推論パイプラインの二重化 ✅ 解決済み

piper-plusには**2つの完全に異なる推論パイプライン**が混在していた。

| 項目 | 旧パイプライン | 新パイプライン |
|------|---------------|---------------|
| モジュール | `src/python_run/piper` | `piper_train.infer_onnx` |
| 実装 | C++バインディングベース | Pure Python |
| prosody対応 | なし | あり (A1/A2/A3) |
| テキスト直接入力 | なし | `--text` オプション |
| Docker環境 | ~~こちらを参照~~ | ✅ **Phase 1で統一** |
| ローカル開発 | 使用していない | **現在使用中** |

**Phase 1で解決**: Docker環境を新パイプライン (`piper_train.infer_onnx`) に統一。

### 3.2 依存管理の断片化 ✅ 解決済み

**Phase 2で解決**: `setup.py` の `extras_require` に `inference`/`train` グループを追加し、Single Source of Truth化。

| 方式 | 用途 | 状態 |
|------|------|------|
| `setup.py` extras_require | 依存の正式定義 | ✅ Single Source of Truth |
| `pyproject.toml` optional-dependencies | uv でのローカル開発 | ✅ ミラー |
| Docker内 `uv pip install --system ".[inference]"` | Docker環境 | ✅ extras_require経由 |
| `requirements-*.txt` 6ファイル | 旧方式 | 🗑️ 全削除 |

### 3.3 CI/CDの不整合 ✅ Phase 3で解決済み

4つのDocker関連ワークフローを2つに統合し、責務を明確化。

| ワークフロー | ファイル | 状態 |
|-------------|---------|------|
| build-docker-images | `.github/workflows/build-docker-images.yml` | 🗑️ 削除（docker-build.ymlに統合） |
| docker-build-minimal | `.github/workflows/docker-build-minimal.yml` | 🗑️ 削除（docker-test.ymlに統合） |
| docker-build | `.github/workflows/docker-build.yml` | ✅ 5イメージのビルド＆push |
| docker-test | `.github/workflows/docker-test.yml` | ✅ PRスモークテスト |

**解決内容**:
- `docker-build.yml`: 5イメージ(python-inference, python-train, webui, cpp-dev, cpp-inference)のビルド＆ghcr.io push
- `docker-test.yml`: PR時のスモークテスト(python-inference, webui)
- `ci.yml`からdocker-testジョブを削除（docker-test.ymlに移行）
- GHAキャッシュ有効化

---

## 4. 整理方針

### Phase 1-2で完了した対応

| カテゴリ | 対応内容 |
|----------|---------|
| Python推論 | `piper_train.infer_onnx` ベースで書き直し → uv化 |
| Python学習 | 依存修正 → uv化 |
| WebUI | espeak-ng不要構成で書き直し → uv化 |
| 依存管理 | `extras_require` (`inference`/`train`) に統合、requirements.txt 6ファイル削除 |
| C++ Docker | ARM64最適化修正、USE_CUDA定義、OpenJTalk --enable-shared、ONNX Runtime動的化 |
| 廃止ファイル | `src/python/Dockerfile`, デッドファイル削除 |
| ベースイメージ | Debian bookworm化 |

### Phase 3で完了した対応

| カテゴリ | 対応内容 |
|----------|---------|
| CI/CD | ワークフロー2つに統合、ghcr.io自動push、WebUI追加 |
| ビルド最適化 | `.dockerignore` 改善、BuildKitキャッシュマウントTIP、piper-phonemize NOTEコメント |
| ドキュメント | `docker/README.md` 全面書き直し |
| C++ビルド方式 | 調査の結果、用途が異なるため現状維持（コメントで文書化） |

---

## 5. 実装ロードマップ

### Phase 1: 致命的問題の修正 ✅ 完了

**コミット**: `5531ef0` — `refactor: Docker環境Phase1 - 致命的問題8件の修正 + 整理計画ドキュメント`

| # | タスク | 状態 |
|---|--------|------|
| 1-1 | Python推論Dockerfileを `piper_train.infer_onnx` ベースで書き直し | ✅ |
| 1-2 | 推論スクリプトを新パイプラインで書き直し | ✅ |
| 1-3 | Python学習Dockerfileの依存を修正 | ✅ |
| 1-4 | WebUI Dockerfileをespeak-ng不要な構成で書き直し | ✅ |
| 1-5 | ルートDockerfileのベースイメージをbookwormに更新 | ✅ |
| 1-6 | 廃止ファイルの削除 | ✅ |
| 1-7 | 各Dockerイメージのビルド・動作確認 | ✅ |

### Phase 2: 依存管理の統合 + 構造改善 ✅ 完了

**コミット**: `f4cf529` — `refactor: Docker環境Phase2 - 依存管理統合(uv化) + C++修正`

#### グループA: Python依存管理の統合

| # | タスク | 状態 |
|---|--------|------|
| A-1 | `setup.py` に `extras_require` (`inference`/`train`) 追加 | ✅ |
| A-2 | `pyproject.toml` に `inference`/`train` グループ追加 | ✅ |
| A-3 | Python推論 Dockerfile → uv化 | ✅ |
| A-4 | Python学習 Dockerfile → uv化 | ✅ |
| A-5 | WebUI Dockerfile → uv化 | ✅ |
| A-6 | root requirements削除 + CI参照修正 | ✅ |

#### グループB: C++ Docker修正

| # | タスク | 状態 |
|---|--------|------|
| B-1 | ARM64最適化レベル `-O0` → `-O2` | ✅ |
| B-2 | `USE_CUDA` CMakeオプション定義追加 | ✅ |
| B-3 | OpenJTalk/HTS Engine `--enable-shared` 追加 | ✅ |
| B-4 | ONNX Runtime シンボリックリンク動的化 | ✅ |

#### 削除ファイル (6件)

- `requirements.txt` (root)
- `requirements-train.txt` (root)
- `docker/python-inference/requirements-inference.txt`
- `docker/python-inference/requirements-inference-arm64.txt`
- `docker/python-train/requirements-train.txt`
- `docker/python-train/requirements-torch.txt`

### Phase 3: CI/CD整備 + ドキュメント更新 ✅ 完了

**コミット**: `refactor/docker-cleanup` ブランチ

| # | タスク | 対象 | 問題番号 | 状態 |
|---|--------|------|---------|------|
| 3-1 | CI/CDワークフローの責務整理・統合 | `.github/workflows/docker-*.yml` | M-7 | ✅ `build-docker-images.yml`削除、`docker-build-minimal.yml`削除、`ci.yml`からdocker-test削除 |
| 3-2 | ghcr.ioへの自動push設定 | `.github/workflows/docker-build.yml` | M-8 | ✅ pushトリガー・GHAキャッシュ・全イメージghcr.io push |
| 3-3 | WebUIをCI/CDに追加 | `.github/workflows/docker-build.yml`, `docker-test.yml` | M-7 | ✅ build-webuiジョブ・test-webuiジョブ追加 |
| 3-4 | ルートDockerfileのビルド最適化 | `Dockerfile`, `.dockerignore`, `CMakeLists.txt` | L-3, L-4, L-5 | ✅ .dockerignore改善、BuildKitキャッシュマウントTIP、piper-phonemize NOTEコメント |
| 3-5 | C++推論ビルド方式の統一検討 | `docker/cpp-inference/Dockerfile`, `Dockerfile` | M-3 | ✅ 現状維持（用途が異なるため統一不要、コメントで文書化） |
| 3-6 | `docker/README.md` の全面書き直し | `docker/README.md` | L-8 | ✅ 5環境のドキュメントを最新化 |
| 3-7 | 最終統合テスト | 全体 | — | ✅ CI/CD委託（docker-test.ymlでPR時スモークテスト自動実行） |

**成果物**: CI/CDが2ワークフローに整理され、ドキュメントが最新化された状態

#### ワークフロー統合結果

| 統合前 | 統合後 | 役割 |
|--------|--------|------|
| `build-docker-images.yml` | 🗑️ 削除 | docker-build.ymlに統合 |
| `docker-build-minimal.yml` | 🗑️ 削除 | docker-test.ymlに統合 |
| `docker-build.yml` | ✅ 維持・拡充 | 5イメージのビルド＆ghcr.io push |
| `docker-test.yml` | ✅ 維持・拡充 | PR時スモークテスト (python-inference, webui) |

#### 削除ファイル (2件)

- `.github/workflows/build-docker-images.yml`
- `.github/workflows/docker-build-minimal.yml`

### Phase 4: 最終修正 + 品質改善 ✅ 完了

**コミット**: `1cd78a6`, `5eacc88`, `5d2c906`

| # | タスク | 状態 |
|---|--------|------|
| 4-1 | `docker/cpp-train` → `docker/cpp-dev` にリネーム（開発環境の正しい名称に変更） | ✅ |
| 4-2 | 全Dockerファイルの `pip install` → `uv pip install` 移行（13ファイル） | ✅ |
| 4-3 | cpp-inference Dockerfileの全面書き直し（CMake ExternalProject方式、ubuntu:22.04 builder） | ✅ |
| 4-4 | ONNX Runtimeバージョン自動検出によるGPU版インストール | ✅ |
| 4-5 | `.gitattributes` 追加（*.sh text eol=lf）+ 全シェルスクリプトのCRLF→LF変換 | ✅ |
| 4-6 | cpp-inference推論テスト（RTF=0.094, en_US-amy-lowモデル） | ✅ |

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
