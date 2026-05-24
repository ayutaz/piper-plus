# Issue #527 要件定義書

> [要求定義 (`requirements.md`)](requirements.md) で定義された WHAT/WHY を **システム要件 (HOW MUCH / HOW PRECISELY)** に落とした技術仕様書。 実装手順 (HOW STEP-BY-STEP) は [`README.md`](README.md) を参照。

文書ID: PP-IR-527
版: 1.0
適用: dev branch (Issue #527 完了まで)
最終更新: 2026-05-22

---

## 1. システム概要

### 1.1 対象システム

| 領域 | 範囲 |
|---|---|
| ソースコード | `src/python/piper_train/` + `src/python_run/piper/` (Python ランタイム) |
| Docker image | `docker/python-train/` `docker/python-inference/` `docker/webui/` `docker/wyoming/` |
| CI/CD | `.github/workflows/*.yml` (25 workflow が直接対象) |
| ドキュメント | `CLAUDE.md` `README*.md` `CONTRIBUTING.md` `QA-RELEASE-CHECKLIST.md` `docs/**` |
| 設定 | `pyproject.toml` (7 file)、 `.pre-commit-config.yaml`、 `.github/dependabot.yml` |

### 1.2 対象外システム

| 領域 | 理由 |
|---|---|
| `src/{rust,go,csharp,wasm,cpp,kotlin,swift}/` | piper_train のみ touch、 他ランタイムは model file 経由で結合 |
| `src/python/g2p/piper_plus_g2p/` (G2P) | 言語別 phonemizer ロジックは無変更、 Python 3.13 で動作確認のみ |
| 学習済 ONNX モデル (HuggingFace 配布) | byte 互換性維持 |
| `data/` 配下のデータセット | データ前処理は対象外 |

---

## 2. システム構成要件 (System Configuration Requirements)

### SCR-01: Python interpreter

| 設定 | 値 | 確認方法 |
|---|---|---|
| Python interpreter (デフォルト) | **3.13.x** | `docker exec <image> python --version` で `Python 3.13.x` |
| `requires-python` (pyproject.toml × 7) | `>=3.11` (据置) | `scripts/check_workspace_python_parity.py` が PASS |
| Python 3.13 minor 範囲 | `3.13.0` 以上 | runtime での `sys.version_info >= (3, 13)` |
| Python 3.14 への自動 bump | **抑止** | `dependabot.yml` の Python minor bump ignore を維持 |

### SCR-02: CUDA / cuDNN (GPU Docker)

| 設定 | 値 | 確認方法 |
|---|---|---|
| CUDA toolkit (base image) | **12.8.x** | `nvcc --version` で `release 12.8` |
| cuDNN (base image) | **9.x** (12.8 系に同梱) | `dpkg -l \| grep cudnn` |
| nvidia-container-toolkit (host) | `>=1.14.0` | A-05 で確認、 サーバー側準備 |
| host NVIDIA driver | `>=570.0` | `nvidia-smi` で `Driver Version: 570.x` 以上 |

### SCR-03: OS / Linux distribution

| 設定 | 値 | 確認方法 |
|---|---|---|
| Ubuntu (CUDA Docker) | **24.04 (Noble)** | `cat /etc/os-release` で `VERSION_ID="24.04"` |
| glibc (CUDA Docker) | **2.39** (Noble 同梱) | `ldd --version` で `2.39` |
| Debian (CPU Docker base) | **trixie (13)** | `python:3.13-slim-trixie` 利用、 `/etc/debian_version` で `13.x` |
| Debian (distroless final) | **debian13** | `gcr.io/distroless/python3-debian13` 利用 |

### SCR-04: PyTorch / CUDA wheel

| 設定 | 値 | 確認方法 |
|---|---|---|
| torch (Docker) | **2.11.0+cu128** | `python -c "import torch; print(torch.__version__)"` で `2.11.0+cu128` |
| torchaudio (Docker) | **2.11.0+cu128** | 同 |
| torchvision | **削除** (piper-train は未使用) | `pip list \| grep torchvision` が空 |
| PyTorch index URL | `https://download.pytorch.org/whl/cu128` | Dockerfile の `--extra-index-url` が cu128 |
| uv.lock (workspace canonical) | `2.11.0+cu128` (Linux), `2.11.0` (他 OS) | 据置 |

### SCR-05: Python パッケージ管理

| 設定 | 値 |
|---|---|
| パッケージマネージャ | `uv >=0.9,<1` |
| Python install 経路 (Ubuntu 24.04) | **deadsnakes PPA** (`ppa:deadsnakes/ppa`) |
| 必要 apt パッケージ | `python3.13` `python3.13-dev` `python3.13-venv` `python3-pip` |
| symlink 設定 | `/usr/bin/python` → `python3.13`、 `/usr/bin/python3` → `python3.13` (update-alternatives) |

---

## 3. 機能要件詳細 (Functional Requirements — Detailed)

要求定義 FR-01〜FR-10 を実装レベルに落とす。

### FR-01: デフォルト Python 3.13 化 (詳細)

#### FR-01-01: CI workflow の Python version 更新

**対象 workflow** (3.11 → 3.13、 matrix 維持除く):

| Workflow | 現状値 | 更新後 | 種別 |
|---|---|---|---|
| `python-lint.yml` | `['3.11']` matrix | `['3.13']` | single-value matrix |
| `python-doctest.yml` | `"3.11"` × 2 箇所 | `"3.13"` | single |
| `pre-commit.yml` | `'3.11'` | `'3.13'` | single |
| `codeql.yml` | `'3.11'` | `'3.13'` | single |
| `deploy-huggingface.yml` | `'3.11'` | `'3.13'` | single |
| `dev-create-release.yml` | `'3.11'` × 2 箇所 | `'3.13'` | single |
| `dev-build-all.yml` | `'3.11'` × 2 箇所 | `'3.13'` | single |
| `generate-combined-report.yml` | `'3.11'` | `'3.13'` | single |
| `model-quality-gate.yml` | `'3.11'` | `'3.13'` | single |
| `release-verify.yml` | `'3.11'` | `'3.13'` | single |
| `runtime-parity-deep.yml` | `"3.11"` × 2 箇所 (line 58, 298) | `"3.13"` | single (B-C4 関連、 コメント更新も) |
| `sbom.yml` | `'3.11'` | `'3.13'` | single |
| `security-audit.yml` | `"3.11"` | `"3.13"` | single |
| `test-hf-space.yml` | `'3.11'` | `'3.13'` | single |
| `test-japanese-tts.yml` | `'3.11'` × 2 箇所 | `'3.13'` | single |
| `timing-parity.yml` | `'3.11'` | `'3.13'` | single |
| `version-consistency.yml` | `'3.11'` | `'3.13'` | single |
| `wyoming-smoke.yml` | `"3.11"` | `"3.13"` | single |
| `ci.yml` | `['3.11']` matrix + `'3.11'` 比較 (line 304) | `['3.13']` | single-value matrix |
| `webui-test.yml` | `['3.11', '3.12']` matrix + `'3.11'` single | matrix `['3.13']` single | 削減 |

**維持する matrix** (FR-01 では更新しない):
- `python-tests.yml`: `["3.11", "3.12", "3.13"]` 据置 (C-02)
- `g2p-python-ci.yml`: `['3.11', '3.12', '3.13']` 据置 (同上)
- `build-phonemize-wheels.yml`: `["3.11", "3.12"]` 据置 (C-03、 piper-phonemize cp313 未提供)

**受入基準:**
- `grep -rE "python-version.{0,10}3\.11" .github/workflows/*.yml` の結果が **5 件以下** (matrix 内のみ残る)
- 各更新 workflow の next 実行で `Set up Python 3.13` が success

#### FR-01-02: ローカル開発環境

| 設定 | 要件 |
|---|---|
| `pre-commit-config.yaml` | `language_version` を明示指定しない (システム Python を使う) |
| ローカル uv 推奨 Python | 3.13 (ドキュメント記載のみ、 強制しない) |

#### FR-01-03: ドキュメント更新

| ファイル | 行 | 現状 | 更新後 |
|---|---|---|---|
| `CONTRIBUTING.md` | 5 | `Python 3.11, 3.12, or 3.13` | `Python 3.13 (推奨), 3.12, または 3.11` |
| `README.md` | 274 | `Python 3.11+ が必要` | `Python 3.13+ 推奨 (3.11+ サポート)` |
| `README_EN.md` | 257 | `Requires Python 3.11+` | `Requires Python 3.13+ (3.11+ supported)` |
| `README_KO.md` `README_ZH.md` `README_ES.md` `README_FR.md` `README_PT.md` `README_DE.md` | — | 各言語の 3.11+ 表記 | 3.13+ 表記に更新 |
| `QA-RELEASE-CHECKLIST.md` | 66, 453 | `3.11/3.13` | `3.11/3.12/3.13` |
| `docs/features/webui.md` | 11 | `Python 3.11+` | 据置 (下限表記) |
| `docs/guides/training/training-guide.md` | 31 | `python 3.11` | `python 3.13` |
| `docker/README.md` | 14 | `python:3.11-slim-bookworm` | `python:3.13-slim-trixie` |

### FR-02: Docker 全 image Python 3.13 統一 (詳細)

各 Dockerfile の具体的な書換要件:

#### FR-02-01: `docker/python-inference/Dockerfile.cpu` (CPU 推論、 Phase 1)

```yaml
変更:
  base_image:
    before: "python:3.11-slim-bookworm"
    after: "python:3.13-slim-trixie"
  python_paths: 自動 (image 内 default)

受入基準:
  - docker build success
  - 起動して python --version が 3.13.x
  - import onnxruntime success
  - import soundfile success
  - 推論 smoke test (6lang base) で WAV 生成
```

#### FR-02-02: `docker/python-inference/Dockerfile.cpu.distroless` (Phase 2)

```yaml
変更:
  builder_base:
    before: "python:3.11-slim-bookworm"
    after: "python:3.13-slim-trixie"
  final_base:
    before: "gcr.io/distroless/python3-debian12"
    after: "gcr.io/distroless/python3-debian13"
  internal_paths:
    - "COPY --from=builder /usr/local/lib/python3.11 ..." → "/usr/local/lib/python3.13 ..."
    - "PYTHONPATH=/usr/local/lib/python3.11/site-packages" → "/usr/local/lib/python3.13/site-packages"
    (合計 6 箇所、 内部パスのみ)

受入基準:
  - docker build success (multi-stage)
  - distroless final で /usr/bin/python3 が 3.13.x
  - import onnxruntime / soundfile / pyopenjtalk-plus success (G-01, G-02)
  - Trivy scan: new HIGH/CRITICAL なし
  - Wyoming smoke が green を維持
```

#### FR-02-03: `docker/webui/Dockerfile.distroless` (Phase 2)

```yaml
変更:
  builder_base:
    before: "python:3.11-slim-trixie"
    after: "python:3.13-slim-trixie"
  final_base:
    before: "gcr.io/distroless/python3-debian12"
    after: "gcr.io/distroless/python3-debian13"
  internal_paths: 6 箇所 (FR-02-02 と同パターン)

受入基準:
  - docker build success
  - Gradio WebUI 起動 (port 7860)
  - 6lang base での音声合成 demo が動作
```

#### FR-02-04: `docker/python-inference/Dockerfile` (CUDA 推論、 Phase 3)

```yaml
変更:
  base_image:
    before: "nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04"
    after: "nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04"
  python_install:
    method: "deadsnakes PPA"
    add_repos: ["ppa:deadsnakes/ppa"]
    apt_packages:
      - python3.13
      - python3.13-venv
      - python3.13-dev (optional、 native extension build がある場合)
      - python3-pip
    symlinks:
      - "update-alternatives /usr/bin/python → python3.13"
      - "update-alternatives /usr/bin/python3 → python3.13"

受入基準:
  - docker build success on linux/amd64
  - nvidia-smi が動作 (--gpus all で)
  - python -c "import torch; torch.cuda.is_available()" → True (新 GPU 環境)
  - onnxruntime-gpu が CUDAExecutionProvider 認識
  - Trivy scan: new HIGH/CRITICAL なし
```

#### FR-02-05: `docker/python-train/Dockerfile` (Phase 3 + Phase 4)

```yaml
変更:
  base_image (builder):
    before: "nvidia/cuda:12.6.3-cudnn-devel-ubuntu22.04"
    after: "nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04"
  base_image (runtime):
    before: "nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04"
    after: "nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04"
  python_install: deadsnakes PPA + python3.13 (FR-02-04 と同パターン)
  torch_install:
    extra_index_url:
      before: "https://download.pytorch.org/whl/cu121"
      after: "https://download.pytorch.org/whl/cu128"
    packages:
      before: ["torch==2.2.1+cu121", "torchaudio==2.2.1+cu121", "torchvision==0.17.1+cu121"]
      after: ["torch==2.11.0+cu128", "torchaudio==2.11.0+cu128"]
      # torchvision は piper-train が未使用のため削除
  comments_to_update:
    - "CUDA/cuDNN version mismatch" の説明 (line 7-19) を「fully-aligned」 に書換

受入基準:
  - docker build success on linux/amd64
  - python -c "import torch; print(torch.__version__)" → "2.11.0+cu128"
  - python -c "import pytorch_lightning; print(pytorch_lightning.__version__)" → "2.6.x"
  - Ada 6000 実機で Template B 1 epoch FT 完走 (FR-06)
  - RTX 5090 実機で torch.cuda.get_device_capability() → (12, 0) (FR-05)
```

#### FR-02-06: 据置 image (変更なし、 確認のみ)

- `docker/wyoming/Dockerfile`: 既に `python:3.13.13-slim-trixie`、 据置
- `docker/webui/Dockerfile`: 既に `python:3.13.13-slim-trixie`、 据置
- `docker/cpp-inference/*`: Python 利用なし、 据置
- `docker/cpp-dev/Dockerfile`: dev tool 用 python3.12、 据置

### FR-03: GPU Docker CUDA 12.8 統一 (詳細)

SCR-02 と FR-02-04 / FR-02-05 で網羅。 追加で:

| 項目 | 要件 |
|---|---|
| CUDA image tag | `12.8.0` ではなく **`12.8.1`** を選択 (より bugfix が含まれる minor) |
| ABI 揃え | wheel cu128 と image CUDA 12.8 が同 major、 forward-compat 依存解消 |
| cuDNN version | image 同梱 cuDNN 9.x + wheel bundle cuDNN 9.5+ で同 major |

### FR-04: torch wheel cu128 統一 (詳細)

| 項目 | 要件 |
|---|---|
| Dockerfile 内の `torch==` pin | `2.11.0+cu128` (cu121 言及が 0 件) |
| `--extra-index-url` | `https://download.pytorch.org/whl/cu128` (cu121 が 0 件) |
| `pyproject.toml` の `[[tool.uv.index]]` | 据置 (既に cu128) |
| `uv.lock` | 据置 (既に `torch 2.11.0+cu128`) |

### FR-05 〜 FR-07: 新 GPU 動作 (詳細)

| GPU | 検証要件 |
|---|---|
| **RTX 5090** (sm_120) | `python -c "import torch; assert torch.cuda.get_device_capability() == (12, 0)"` PASS。 Template B 1 epoch FT 完走。 学習速度 V100 比 5x 以上。 |
| **Ada 6000** (sm_89) | 同 `(8, 9)` PASS。 Template B 1 epoch FT 完走。 loss curve canonical 範囲。 |
| **T4** (sm_75) | 推論 image 起動。 6lang base モデル推論で WAV 生成。 RTF < 0.5 (16kHz)。 |

### FR-08: TF32 enable (詳細)

#### FR-08-01: コード変更

`src/python/piper_train/__main__.py` line 461 (`torch.backends.cudnn.benchmark = True` の隣) に追加:

```python
torch.backends.cudnn.benchmark = True
# TF32 enable for Ampere+ (sm_80+: A100/Ada 6000/RTX 5090). On
# sm_75 (T4) and older, this setting is a noop. Speeds up matmul by
# ~1.3-1.5x with negligible quality impact for TTS workloads.
torch.backends.cuda.matmul.allow_tf32 = True
```

#### FR-08-02: 受入基準

- 該当行が `__main__.py` の `main()` 関数内、 Trainer 構築前に存在
- Ada 6000 / RTX 5090 で `torch.backends.cuda.matmul.allow_tf32` が `True`
- T4 / sm_75 以下では noop (warning 出ない)
- TF32 enable 状態で Template B 1 epoch smoke 完走

### FR-09: bf16-mixed 推奨 (詳細)

#### FR-09-01: ドキュメント変更

`docs/guides/training/training-guide.md` の `--precision` 表で:

| 値 | 推奨対象 |
|---|---|
| `bf16-mixed` | **Ada 6000 / RTX 5090 (新メイン推奨)** |
| `16-mixed` (FP16) | 互換性維持、 旧 GPU 用 |
| `32-true` | legacy V100 互換、 数値安定性最優先時 |

#### FR-09-02: コード変更

`--precision` の default は **据置** (現状 `16-mixed`)。 ドキュメント側でのみ推奨を変更。 既存 CLAUDE.md Template A/B も `16-mixed` 据置で、 オプションとして `bf16-mixed` を新 GPU 環境で記載。

### FR-10: distroless Python 3.13 統一 (詳細)

FR-02-02 / FR-02-03 で網羅。 追加で:

| 項目 | 要件 |
|---|---|
| distroless final image tag | `gcr.io/distroless/python3-debian13:latest` (`nonroot` variant の場合は `:nonroot` を選択) |
| 内部パス | `/usr/local/lib/python3.13/site-packages` |
| `PYTHONPATH` 環境変数 | 同上 |
| 内部 python3 シンボリックリンク | distroless image の `/usr/bin/python3` = `python3.13` (自動) |

---

## 4. 非機能要件詳細 (Non-Functional Requirements — Detailed)

要求定義 NFR-01〜NFR-09 を測定可能な閾値に落とす。

### NFR-01: 後方互換性 (Python 3.11)

| 指標 | 閾値 | 測定方法 |
|---|---|---|
| `python-tests.yml` matrix Python 3.11 ジョブ | 全 OS で PASS | GitHub Actions PASS 数 |
| `g2p-python-ci.yml` matrix Python 3.11 ジョブ | 全 PASS | 同 |
| `requires-python` 値 (7 file) | 全て `>=3.11` | `check_workspace_python_parity.py` |

### NFR-02: 学習再現性 (DR-006 適用後)

過去 ckpt resume は **非サポート** (DR-006)。 新規学習のみ動作確認:

| 指標 | 閾値 | 測定方法 |
|---|---|---|
| **新規学習 from scratch 1 epoch** | 完走 (loss が発散しない) | Ada 6000 実機、 Template A から短縮した smoke 構成 |
| validation loss (1 epoch 後) | canonical 範囲 (発散・NaN なし) | wandb / tensorboard 確認 |
| ONNX export 出力 | audio_parity Tier 4 PASS (SNR ≥ 30dB) | `runtime-parity-deep.yml` |

**削除した指標** (DR-006 により非サポート):
- ~~6lang base ckpt resume が成功する~~
- ~~validation loss が canonical の ±10% 以内 (resume 後)~~

### NFR-03: セキュリティ (Trivy)

| 指標 | 閾値 |
|---|---|
| HIGH / CRITICAL CVE (新規) | **0 件** (既存より増えない) |
| MEDIUM CVE (新規) | 増減 ±2 件まで許容 (apt upgrade で吸収可能) |
| supply-chain CVE (pip / uv) | 0 件 |

測定: `docker-build.yml` の Trivy scan で diff 確認。

### NFR-04: OS 寿命

| 項目 | 要件 |
|---|---|
| Ubuntu base (CUDA Docker) | **24.04 (Noble) EOL 2029-04** に揃える |
| Debian base (CPU Docker) | **trixie (13) EOL 2028 頃** |
| 計画的次回 bump | CUDA 13.0 LTS リリース後 (推定 2027-2028) |

### NFR-05: 観測性

| 項目 | 要件 |
|---|---|
| `nsys profile` / `nvprof` | image 内 CUDA 12.8 toolkit と wheel 12.8 runtime で version mismatch 警告ゼロ |
| `nvidia-smi` (image 内) | image 同梱版が host driver と communicate 可能 |
| `torch.cuda` API 経由の memory tracking | normal |

### NFR-06: メンテナンス性

| 項目 | 要件 |
|---|---|
| forward-compat 依存箇所 | 0 箇所 (wheel と image の CUDA major 一致) |
| CUDA version pinning 箇所 | 単一 (Dockerfile + `pyproject.toml` の cu128 index) |

### NFR-07: クロスランタイム整合性

| 指標 | 閾値 |
|---|---|
| `runtime-parity-deep.yml` | Tier 1-4 全 PASS |
| `audio-parity-contract.toml` | SNR ≥ 30dB (Tier 4 閾値) |
| `phoneme-timing-formula` | (hop_length / sample_rate) × 1000 が全 6 ランタイムで byte-equal |

### NFR-08: 学習速度

| GPU | V100 比 倍率 (期待) | 測定方法 |
|---|---|---|
| Ada 6000 (BF16+TF32+FA2) | **3-5x** | Template B FT 100 step wall-clock |
| RTX 5090 (BF16+FA3) | **5-7x** | 同 |
| RTX 5090 (FP8+FA3、 別 issue) | 7-10x | 別 issue で測定 |

### NFR-09: MOS / RTF 退行

| 指標 | 閾値 |
|---|---|
| MOS (subjective) | baseline ±0.05 以内 |
| RTF (real-time factor) | baseline ±2% 以内 |

測定: `model-quality-gate.yml`。

---

## 5. データ要件 (Data Requirements)

### DR-01: モデルチェックポイント (DR-006 適用後)

過去 ckpt の resume は **非サポート** (DR-006 で確定)。 v1.13.0 移行時の扱い:

| 項目 | 要件 |
|---|---|
| 既存 6lang base ckpt の resume | **非サポート** — torch 2.11 環境で load 不可でも修正しない |
| 既存学習済 ONNX (`piper-plus-base` 等 HF 配布物) | **据置で推論可能** — ONNX レベルの forward 互換は ONNX Runtime 1.26+ で成立 |
| 新規学習 ckpt | torch 2.11 環境で from scratch、 もしくは torch 2.11 で生成した base からの FT |
| optimizer state_dict | 破棄して再構築 (既存仕様、 影響なし) |
| EMA state | 新規学習で生成、 旧 ckpt から継承しない |
| 旧 ckpt 継続学習が必要なユーザ | **v1.12 Docker image を使用** (旧 image tag は registry に保持、 OQ-14 で確定) |

### DR-02: ONNX エクスポート

| 項目 | 要件 |
|---|---|
| `OPSET_VERSION` (main) | **15** 据置 (`src/python/piper_train/export_onnx.py:31`) |
| `OPSET_VERSION` (speaker_encoder) | **17** 据置 (`src/python/piper_train/speaker_encoder/export_encoder.py:35`) |
| `docs/spec/onnx-export-contract.toml` | 据置 |
| 全 6 ランタイム読込互換 | audio_parity で検証 |

### DR-03: phoneme set

| 項目 | 要件 |
|---|---|
| `num_symbols` | **173** 据置 (strict gate) |
| PUA codepoints | 据置 |
| カスタム辞書フォーマット (JSON v1/v2 + TSV) | 据置 |

### DR-04: WandB ログ

| 項目 | 要件 |
|---|---|
| metric range (kl_loss, mel_loss, duration_loss) | canonical ±10% 以内 |
| audio log | 50 epoch 周期で記録 (既存) |
| `WANDB_API_KEY` env var | 据置 |

---

## 6. 外部インターフェース要件

### EIR-01: PyPI

| パッケージ | 要件 |
|---|---|
| `piper-plus` (src/python_run) | classifiers に 3.13 既掲、 据置 |
| `piper-train` (src/python) | 同上 (publish していないが metadata は揃える) |
| `piper-plus-g2p` (src/python/g2p) | 同上 |

### EIR-02: Docker Hub / GHCR

| image | tag 戦略 |
|---|---|
| `piper-plus-cpu` | next release tag (例 `v1.13.0`) で Python 3.13 base に切替 |
| `piper-plus-gpu` (train + inference) | 同 |
| `piper-plus-distroless` | 同 |
| 旧 v1.12.x tag | **削除しない** (rollback 用に保持) |

### EIR-03: HuggingFace

| 項目 | 要件 |
|---|---|
| Spaces deployment | `deploy-huggingface.yml` で Python 3.13 setup |
| Model repo (ckpt/onnx) | 据置 (PR で変更なし) |

### EIR-04: GitHub Actions / CI

| 設定 | 要件 |
|---|---|
| `actions/setup-python@v6.2.0` | 既存 version 据置、 input `python-version` のみ更新 |
| matrix 構造 | 必要に応じて削減 (`webui-test.yml` の `['3.11', '3.12']` → `['3.13']`) |

---

## 7. テスト要件 (Test Requirements)

### TR-01: 単体テスト (CI)

| テストスイート | 要件 |
|---|---|
| `python-tests.yml` matrix (3.11/3.12/3.13 × 3 OS) | 全 PASS |
| `g2p-python-ci.yml` matrix | 全 PASS |
| Wyoming smoke | green |
| Runtime parity (6 ランタイム) | Tier 1-4 PASS |

### TR-02: ビルドテスト (CI)

| ビルド対象 | 要件 |
|---|---|
| `docker/python-inference/Dockerfile.cpu` | success on amd64 + arm64 |
| `docker/python-inference/Dockerfile.cpu.distroless` | success on amd64 |
| `docker/webui/Dockerfile.distroless` | success on amd64 |
| `docker/python-inference/Dockerfile` (CUDA) | success on amd64 |
| `docker/python-train/Dockerfile` | success on amd64 |
| `docker/wyoming/Dockerfile` | 据置 success |

### TR-03: 実機テスト (CI 外、 手動)

| GPU | テストケース |
|---|---|
| Ada 6000 | Template B 1 epoch FT、 loss curve 確認 |
| Ada 6000 | TF32 ON/OFF deterministic 100 step 比較 |
| RTX 5090 | `(12, 0)` 起動確認、 Template B 1 epoch smoke |
| T4 | 推論 image 起動、 6lang base 推論、 RTF 計測 |

### TR-04: 互換性テスト

| 対象 | 要件 |
|---|---|
| 6lang base ckpt → 新 image FT | resume 成功、 loss canonical |
| 旧 image (v1.12) で生成した ONNX → 新 image 推論 | audio_parity Tier 4 |
| 新 image (PR) で生成した ONNX → 旧 ランタイム | audio_parity Tier 4 (forward 互換) |

### TR-05: パフォーマンス測定

| 指標 | 測定方法 | 閾値 |
|---|---|---|
| Template B FT step time (Ada 6000) | wandb / 内部 timer | V100 比 3x 以上短縮 |
| 推論 RTF (T4、 16kHz、 短文) | `tools/benchmark/` | < 0.5 |
| ONNX export 時間 | 内部 timer | 据置 (劇的劣化なし) |

---

## 8. 移行要件 (Migration Requirements)

### MR-01: コードの段階的 migration

Phase 順序 (要求定義 Phase 0-4 と一致):

1. **Phase 0**: distutils → setuptools (1 commit、 5 分)
2. **Phase 1**: docs + 軽量 CI + CPU Docker (1-2 時間)
3. **Phase 2**: distroless × 2 (半日)
4. **Phase 3**: CUDA Docker base 統一 (1 日)
5. **Phase 4**: 新 GPU 学習最適化 (1-2 日、 実機検証含む)

### MR-02: rollback 計画

各 Phase で `git revert` 可能性を保証:
- Phase 0/1: 完全 revert 可能
- Phase 2: image registry の旧 tag 再 promote 必要
- Phase 3/4: 学習 ckpt の互換性検証必須 (DR-01)

詳細は [README.md ロールバック手順](README.md#ロールバック手順) を参照。

### MR-03: 既存ユーザへの周知

| 対象ユーザ | 周知方法 |
|---|---|
| PyPI `piper-plus` ユーザ | CHANGELOG + README で Python 3.13 推奨を明記 |
| Docker image ユーザ | image tag の release note |
| 学習ユーザ | training-guide / CLAUDE.md 更新 + Issue #527 でアナウンス |
| Home Assistant ユーザ | Wyoming Docker は変更なし、 周知不要 |

---

## 9. 運用要件 (Operational Requirements)

### OR-01: CI/CD

| 項目 | 要件 |
|---|---|
| Pre-commit | local + CI 両方で動作 (3.13 環境) |
| Dependabot | Python minor bump (3.13 → 3.14) は ignore 維持 (`.github/dependabot.yml:257`) |
| Trivy scan | weekly + per-PR の両方で動作 |

### OR-02: 監視

| 監視対象 | 方法 |
|---|---|
| 学習サーバー GPU usage | `nvidia-smi`、 既存運用 |
| 推論サーバー RTF | `model-quality-gate.yml` 経由の benchmark |
| Docker image size | CI で warning (size regression gate) |

### OR-03: トラブル対応

| 問題 | 対応 |
|---|---|
| RTX 5090 で torch.cuda.is_available() が False | host driver R570+ 確認、 nvidia-container-toolkit 1.14+ 確認 |
| Ada 6000 で TF32 が効いていない | `torch.backends.cuda.matmul.allow_tf32 == True` 確認、 sm_80+ 確認 |
| docker build で wheel 解決失敗 | uv version 確認 (>=0.9,<1)、 cu128 index URL 確認 |
| Trivy CVE で blocker 出現 | apt upgrade 追加、 必要なら base image を 12.8.x の later patch に bump |

---

## 10. トレーサビリティマトリクス

要求定義 (requirements.md) の各 FR/NFR と本要件定義 (specifications.md) の対応:

| 要求定義 ID | 要件定義 ID | 実装 Phase |
|---|---|---|
| FR-01 (Python 3.13 default) | FR-01-01〜03 | Phase 1 |
| FR-02 (Docker Python 3.13 統一) | FR-02-01〜06 | Phase 1/2/3 |
| FR-03 (GPU Docker CUDA 12.8) | SCR-02 + FR-03 + FR-02-04/05 | Phase 3 |
| FR-04 (torch wheel cu128) | SCR-04 + FR-04 | Phase 3 |
| FR-05 (RTX 5090 動作) | FR-05〜07 + TR-03 | Phase 3/4 検証 |
| FR-06 (Ada 6000 動作) | 同上 | 同 |
| FR-07 (T4 動作) | 同上 | 同 |
| FR-08 (TF32 enable) | FR-08-01/02 | Phase 4 |
| FR-09 (bf16-mixed 推奨) | FR-09-01/02 | Phase 4 |
| FR-10 (distroless 3.13) | FR-02-02/03 + FR-10 | Phase 2 |
| NFR-01 (3.11 サポート) | NFR-01 | 全 Phase |
| NFR-02 (学習再現性) | NFR-02 + DR-01 | Phase 4 |
| NFR-03 (Trivy) | NFR-03 | Phase 2/3 |
| NFR-04 (OS 寿命) | NFR-04 + SCR-03 | Phase 2/3 |
| NFR-05 (観測性) | NFR-05 | Phase 3 |
| NFR-06 (メンテナンス) | NFR-06 | Phase 3 |
| NFR-07 (クロスランタイム) | NFR-07 + DR-02 | 全 Phase |
| NFR-08 (学習速度) | NFR-08 + TR-05 | Phase 4 |
| NFR-09 (MOS/RTF) | NFR-09 + TR-05 | Phase 4 |
| C-01 (3.11 floor 据置) | NFR-01 で実現 | — |
| C-02 (matrix 維持) | FR-01-01 注記 | Phase 1 |
| C-03 (phonemize cp313 据置) | FR-01-01 注記 | — |
| C-04 (host driver) | A-01 + OR-03 | Phase 3 検証 |
| C-05 (FP8 対象外) | — | 別 issue |
| C-06 (ruff py311 据置) | — | — |

---

## 10.5 ライブラリ bump 候補 (Library Update Survey)

> 「3.13 化のついでに他に更新したいライブラリは?」 への網羅調査結果。 全 dependency の floor pin と uv.lock actual を全件突合。

### 10.5.1 サマリ — 3 カテゴリで整理

| カテゴリ | 件数 | 推奨対応 | Issue #527 への組み込み |
|---|---|---|---|
| **A. Floor drift 解消** (root と member で乖離) | 11 件 | 統一して整合性確保 | **M1 で同時実施** (低コスト、 1 PR で吸収) |
| **B. Major bump で security/性能改善** (別 PR 推奨) | 3 件 | 別 PR で慎重に評価 | 別 issue |
| **C. 据置** (上限制約 / exact pin) | 6 件 | 触らない | — |

### 10.5.2 A. Floor drift 解消 (M1 で同時実施推奨)

**問題:** root `pyproject.toml` と member `src/python/pyproject.toml` / `src/python_run/pyproject.toml` で同 library の floor pin が異なる。 これは silent drift で、 ローカル開発で member だけ install すると古い version が解決される可能性がある。 既存の `workspace-python-parity` gate が `requires-python` のみ pin しているのと同パターンで、 主要 library の floor 統一が望まれる。

| Library | root floor | member floor (src/python) | run floor (python_run/requirements.txt) | uv.lock actual | **推奨統一値** |
|---|---|---|---|---|---|
| `scipy` | (なし) | `>=1.12` | — | `1.17.1` | `>=1.17.1` |
| `pytorch-lightning` | `>=2.0` | `>=2.0` | — | `2.6.1` | `>=2.4.0` (configure_model API 安定化点) |
| `transformers` | `>=4.30` | `>=4.38` | — | `4.57.6` | `>=4.50.0` (3.13 対応版) |
| `wandb` | `>=0.26.1` | `>=0.16` | — | `0.26.1` | `>=0.26.1` (root 値で統一) |
| `tensorboard` | `>=2.20.0` | `>=2.16` | — | `2.20.0` | `>=2.20.0` (root 値で統一) |
| `onnxruntime` | `>=1.17` | `>=1.20.0` | `>=1.26.0` | `1.26.0` | `>=1.26.0` (3 箇所統一、 C++ canonical) |
| `fastapi` | `>=0.136.1` | `>=0.110` | (run pyproject `>=0.110,<1`) | `0.136.1` | `>=0.136.1` (root 値) |
| `uvicorn` | `>=0.27` | `>=0.27` | `>=0.27,<1` | `0.46.0` | `>=0.46.0` |
| `pytest` | `>=9.0.3,<10` | `>=7.4` | `>=7.0` | `9.0.3` | `>=9.0.3,<10` (root 値) |
| `matplotlib` | `>=3.10.9` | `>=3.8` | — | `3.10.9` | `>=3.10.9` (root 値) |
| `pypinyin` | `>=0.50` | — | `>=0.55.0` | `0.55.0` | `>=0.55.0` |
| `librosa` | `>=0.10` | `>=0.10` | — | `0.11.0` | `>=0.11.0` |
| `numba` | `>=0.59` | `>=0.59` | — | `0.65.1` | `>=0.61.0` (numpy 2.x ABI warning 解消) |
| `torchmetrics` | `>=1.9.0` | `>=1.0` | — | `1.9.0` | `>=1.9.0` (root 値) |
| `onnxscript` | `>=0.7.0` | `>=0.6.2` | — | `0.7.0` | `>=0.7.0` (root 値) |
| `coverage` | `>=7.14.0` | `>=7.6` | — | `7.14.0` | `>=7.14.0` (root 値) |
| `mypy` | `>=1.20.2` | `>=1.7` | — | `1.20.2` | `>=1.20.2` (root 値) |

**実装方針:**
- M1 (Phase 1) で `src/python/pyproject.toml` と `src/python_run/pyproject.toml` の floor を root と統一
- `uv.lock` は規定値が変わらない場合は据置 (resolver は今と同じ wheel を選ぶ)
- 新 CI gate (任意): `scripts/check_workspace_library_floor.py` を追加して主要 library の floor 統一を pin (`workspace-python-parity` と同パターン)

**期待 PR:** `chore(deps): unify library floor pins across workspace members`

### 10.5.3 B. Major bump で改善余地あり (別 PR 推奨)

本 Issue (3.13 化) と独立した動機を持つ bump。 Issue #527 と混ぜると revert 単位が肥大化するため別出し。

| Library | 現状 floor | uv.lock | 推奨 bump | 動機 | 別 issue 候補 |
|---|---|---|---|---|---|
| `psutil` | `>=5.9` | `7.2.2` | `>=7.0` | psutil 6.x → 7.x で major bump、 過去 CVE 修正含む。 lockfile は既に 7.x | `chore(deps): bump psutil floor to 7.x` |
| `onnxsim-prebuilt` | (pin なし) | `0.4.39.post2` | `>=0.4.39` | floor 未指定で resolver が古い version を引き上げる可能性、 明示化推奨 | `chore(deps): pin onnxsim-prebuilt floor` |
| `g2p-en` | `>=2.1.0` | `2.1.0` | (現状最新) | upstream で更新あれば追従 | 不要 (現状最新) |

### 10.5.4 C. 据置すべきもの (明示)

| Library | 現状 | 据置理由 |
|---|---|---|
| `huggingface-hub` | `>=0.36.2,<1.0` | HF Hub 1.0 は dataset API 全面改訂、 release 動作確認後に外す |
| `numpy` | `<2.5` | numpy 2.5 で dtype 仕様変更予告、 librosa/scipy upstream 対応待ち |
| `black` | `==26.3.1` | exact pin (formatter は version 一致必須) |
| `ruff` | `==0.15.12` | 6 箇所 sync の canonical version (`ruff-version-sync` gate あり) |
| `piper-phonemize` | `>=1.1.0; python_version < '3.13'` | cp313 wheel 未提供、 marker で制約済 |
| `pyopenjtalk-plus` | `>=0.4` | floor のままで lockfile は `0.4.1.post8`、 floor 上げる積極理由なし |
| `g2pk2` | `>=0.0.3` | upstream 開発停滞、 pin 上げる動機なし |
| `mecab-python3` | `>=1.0` | 安定 library、 lockfile `1.0.12` |
| `unidic-lite` | `>=1.0` | 同上 |

### 10.5.5 Python 3.13 動作確認が必要なもの (G-XX として既掲)

[`requirements.md`](requirements.md#93-グレーゾーン-要検証) の「グレーゾーン (要検証)」 を再掲:

| Library | uv.lock | 3.13 動作確認 Phase |
|---|---|---|
| `onnxsim-prebuilt` | `0.4.39.post2` (cp312-abi3 wheel) | Phase 3 で `python -m onnxsim` smoke (G-01) |
| `pyopenjtalk-plus` | `0.4.1.post8` (Cython extension) | Phase 3 で docker build + 推論 smoke (G-02) |
| `g2pk2` | `0.0.3` (pure Python) | Phase 1 で `import g2pk2` smoke (G-03) |
| `wandb` | `0.26.1` | Phase 4 で WandB ログ確認 (G-04) |
| `pytorch-lightning` | `2.6.1` | Phase 4 で bf16-mixed smoke (G-05) |
| `numba` | `0.65.1` | Phase 4 で norm_audio / VAD 経路 (G-06) |
| `mecab-python3` | `1.0.12` | Phase 1 で `import MeCab` smoke (**新規追加**) |
| `sudachipy` | `0.6.10` | Phase 1 で `import sudachipy` smoke (**新規追加**) |

### 10.5.6 推奨アクション (まとめ)

| 優先度 | アクション | 組み込み |
|---|---|---|
| **必須** (M1) | floor drift 解消 (10.5.2 表の 17 library) | M1 で `chore(deps): unify library floor pins` PR を 1 つ追加 |
| **推奨** (M1) | `mecab-python3` / `sudachipy` の Python 3.13 import smoke を追加 | Phase 1 の CI smoke step に追加 (1 行) |
| **任意** (別 issue) | `psutil` floor `>=5.9` → `>=7.0` | `chore(deps): bump psutil floor to 7.x` |
| **任意** (別 issue) | `onnxsim-prebuilt` floor を `>=0.4.39` で明示 pin | 同上 |
| **任意** (将来) | `huggingface-hub` `<1.0` 上限を release 後に外す | HF Hub 1.0 release 後の別 issue |
| **任意** (将来) | `numpy` `<2.5` 上限を librosa/scipy 対応後に外す | dependency upstream 待ち |

### 10.5.7 floor 統一の実装 diff サンプル

`src/python/pyproject.toml` の `[project.optional-dependencies] train`:

```diff
 train = [
-    "scipy>=1.12",
-    "librosa>=0.10",
+    "scipy>=1.17.1",
+    "librosa>=0.11.0",
     "soundfile>=0.12",
-    "pytorch-lightning>=2.0",
-    "torchmetrics>=1.0",
-    "transformers>=4.38",
+    "pytorch-lightning>=2.4.0",
+    "torchmetrics>=1.9.0",
+    "transformers>=4.50.0",
     "onnx>=1.21.0",
     "onnxruntime>=1.26.0",
     "pyopenjtalk-plus",
     ...
-    "tensorboard>=2.16",
-    "wandb>=0.16",
+    "tensorboard>=2.20.0",
+    "wandb>=0.26.1",
-    "matplotlib>=3.8",
+    "matplotlib>=3.10.9",
-    "numba>=0.59",
+    "numba>=0.61.0",
     ...
 ]
```

`src/python_run/requirements.txt`:

```diff
-onnxruntime>=1.26.0
+onnxruntime>=1.26.0  # 据置 (canonical)
-pypinyin>=0.55.0
+pypinyin>=0.55.0  # 据置 (canonical)
```

(requirements.txt 側は既に最新値、 root pyproject の `>=0.50` を `>=0.55.0` に揃える側で対応)

---

## 10.6 決定事項記録 (Decision Records)

本 Issue で確定した方針判断を ADR (Architecture Decision Record) 形式で記録する。 将来 「なぜそうしたのか」 を参照できるようにする。

### DR-001: Fully-aligned Docker 戦略の採用

- **状態**: Accepted (2026-05-21)
- **コンテキスト**: 当初は「base image は 12.6 据置 + wheel cu128 で forward-compat 動作」 戦略を検討していたが、 学習サーバー GPU が V100 → T4/Ada 6000/RTX 5090 へ移行することが確定 (2026-05-21)。 RTX 5090 (Blackwell sm_120) は CUDA 12.8+ 必須。
- **決定**: Docker 全 image を「CUDA 12.8 + Ubuntu 24.04 + Python 3.13」 で完全統一する fully-aligned 戦略を採用。
- **理由**:
  - RTX 5090 の "wheel-only forward-compat" 不確定性が解消
  - wheel と image の CUDA major が揃うことで forward-compat 依存解消
  - Trivy CVE 管理が単一 CUDA major で完結
  - Ubuntu EOL 2027 → 2029 で OS 寿命延長
- **トレードオフ**:
  - PR スコープ拡大 (Phase 3 が "Docker bump" → "Fully-aligned migration" に)
  - Ubuntu 22.04 → 24.04 で glibc 2.35 → 2.39、 wheel ABI 確認必要
- **代替案**:
  - **A. wheel-only forward-compat 据置 (棄却)**: シンプルだが forward-compat 依存が残り、 RTX 5090 起動の不確定性
  - **B. base image のみ 12.8 bump、 Ubuntu 22.04 維持 (棄却)**: Jammy EOL 2027 が近く、 結局 24.04 bump を後で行う必要
- **影響**: M3 のスコープ + Phase 3 の検証要件 + host driver R570+ 前提

### DR-002: Library Floor Drift Unification を M1 に組み込み

- **状態**: Accepted (2026-05-24)
- **コンテキスト**: 調査の結果、 root `pyproject.toml` と member (`src/python/pyproject.toml` `src/python_run/pyproject.toml`) で 17 library の floor pin が乖離していることが判明。 例: `pytorch-lightning` root `>=2.0` vs member `>=2.0` だが uv.lock は `2.6.1`、 `transformers` root `>=4.30` vs member `>=4.38`、 `onnxruntime` root `>=1.17` vs member `>=1.20.0` vs requirements.txt `>=1.26.0`。
- **決定**: 17 library の floor を **M1 (Phase 1) で同時統一**する (本 Issue #527 のスコープ内とする)。 詳細は §10.5.2 表。
- **理由**:
  - silent drift で member だけ install すると古い version が解決される可能性
  - Issue #527 で既に複数 pyproject.toml を touch するため、 同 PR で吸収できればコスト追加 ほぼゼロ
  - 既存 `workspace-python-parity` gate (`requires-python` 整合) と同パターン、 library 版 gate も任意で追加検討
  - 別 issue 化すると忘れられる / 後追いコスト発生
- **トレードオフ**:
  - M1 PR の review 範囲がやや拡大 (3.11→3.13 と floor 統一の 2 軸変更が 1 PR に混在)
  - 別 commit にすれば revert 可能性は維持される
- **代替案**:
  - **A. 完全に別 issue (棄却)**: メンテナンス頻度低、 忘れられるリスク
  - **B. 別 PR だが M1 の一部 (折衷案)**: M1 内で `chore(deps): unify floor pins` PR を別に切る選択肢あり (実装者判断)
- **影響**: M1 Deliverables に 17 library 統一 + 任意で `scripts/check_workspace_library_floor.py` gate 追加

### DR-003: Major Library Bump は別 Issue に切り出し

- **状態**: Accepted (2026-05-24)
- **コンテキスト**: floor drift 統一の調査中、 単なる整合性確保ではなく **意図的な major bump** が必要なものを発見:
  - `psutil >=5.9` → `>=7.0` (major bump、 security 修正含む)
  - `onnxsim-prebuilt` (pin 不在、 floor 明示必要)
  - `huggingface-hub <1.0` 上限解除 (1.0 release 後)
  - `numpy <2.5` 上限解除 (upstream 対応後)
- **決定**: 上記 4 件は **Issue #527 のスコープから明示的に除外**し、 別 issue として切り出す。
- **理由**:
  - major bump は学習 reproducibility / API 互換性に影響するため独立検証が必要
  - Issue #527 と混ぜると revert 単位が肥大化 (3.13 化を戻すと library bump も戻る)
  - `huggingface-hub 1.0` / `numpy 2.5` は upstream リリースタイミング待ち、 本 Issue の進行を阻害してはいけない
- **トレードオフ**:
  - 別 issue メンテナンスのオーバーヘッド (合計 4 issue)
  - dependabot 自動 PR でも対応可能なものは自動化を期待
- **代替案**:
  - **A. M1 で全部やる (棄却)**: PR 肥大化、 失敗時の影響範囲特定が困難
  - **B. M5 (リリース後) に回す (棄却)**: リリース後のタイミングは bumper 担当が決まりにくい、 上記が独立した PR の方が判断軽い
- **影響**: requirements.md §4.2 (対象外) に 4 件追加、 別 issue 候補として明記

### DR-004: New GPU Optimization は Phase 4 で分離

- **状態**: Accepted (2026-05-21)
- **コンテキスト**: Phase 3 (CUDA Docker base 統一) と Phase 4 (TF32 + bf16 推奨) は当初 1 PR にまとめる案もあった。
- **決定**: Phase 3 (infrastructure) と Phase 4 (training optimization) を分離。
- **理由**:
  - Phase 3 は Docker 設定のみ、 piper-train code 変更なし → CI で十分検証可能
  - Phase 4 は piper-train code (TF32) + docs (V100→新 GPU) → 実機 smoke 必要
  - 分離すると Phase 3 で問題があっても Phase 4 を巻き戻す必要なし
  - 学習担当が実機 smoke を Phase 4 だけ集中対応できる
- **トレードオフ**: PR 数増 (1 → 2)
- **代替案**: 統合 PR (棄却、 review 負荷増 + revert 影響範囲拡大)
- **影響**: マイルストーン M3 / M4 を分離 ([`milestones.md`](milestones.md) 参照)

### DR-005: リリースバージョンは v1.13.0 (minor bump)

- **状態**: Accepted (2026-05-25)
- **コンテキスト**: Issue #527 の変更は Docker base image / Python interpreter / torch / CUDA すべて変更でユーザ環境への影響大。 一方 PyPI `piper-plus` ランタイム API は無変更 (NFR-01 で 3.11 サポート維持)。 SemVer 解釈に裁量の余地あり。
- **決定**: **v1.13.0 (minor bump)** として release する。 patch (v1.12.x) は採用しない。
- **理由**:
  - Docker 利用者にとって breaking 級 (host driver R570+ 要件、 base image 大幅変更)
  - 前回 v1.11 → v1.12 の breaking も同様に minor bump で対応 (`docs/migration/v1.11-to-v1.12.md`)
  - Migration guide を伴う変更は minor 以上の SemVer 慣習に合致
  - PyPI API 互換だけで patch にすると Docker 利用者の breaking が release note に埋もれるリスク
- **トレードオフ**:
  - v1.12.x patch 系列で hotfix が必要になった場合の分岐コスト
  - 学習用 model_manager 等の "v1.13" minor リリース対応工数
- **代替案**:
  - **B. v1.12.1 patch (棄却)**: Docker 利用者の breaking が patch 表記に隠れ、 周知不足のリスク
  - **C. v2.0.0 major (棄却)**: API 互換維持しているのに major bump は過剰、 SemVer 違反気味
- **影響**:
  - `VERSION` ファイルを `1.13.0` に bump (M5 で実施)
  - `docs/migration/v1.12-to-v1.13.md` を新規作成
  - PyPI / Docker Hub / GHCR の tag を `1.13.0` で publish
  - CHANGELOG `[Unreleased]` → `[1.13.0] - YYYY-MM-DD`

### DR-006: 過去 ckpt resume 非対応を許容

- **状態**: Accepted (2026-05-25)
- **コンテキスト**: Issue #527 で torch 2.2.1+cu121 → 2.11.0+cu128 に bump する。 PyTorch upstream の互換ポリシーは「model weights は forward 互換、 optimizer state_dict は保証なし」 で、 piper-train は `--resume-from-multispeaker-checkpoint` で optimizer 破棄して再開する仕組みを持つが、 model state_dict の load 自体が失敗するケース (内部 key 変更、 量子化 op 削除等) もありうる。 当初は「smoke で失敗したら再学習 vs 旧 image 維持」 のフォールバック判断が必要 (OQ-03) としていた。
- **決定**: **過去 ckpt の resume は対応しない (非サポート)。** torch 2.11 環境で旧 ckpt (torch 2.2 系で生成) を load することは保証しない。
- **理由**:
  - 既存 ONNX (生成済) はランタイム側で推論継続可能 (forward 互換は ONNX opset で成立)
  - 新規学習は torch 2.11 環境で from scratch または torch 2.11 で新規生成した base ckpt からの FT のみ対応
  - 「resume 保証」 は実機 smoke + 数値 reproducibility 検証コストが大きい、 切ることで Phase 4 の検証スコープを縮小可能
  - 学習サーバー GPU 移行 (V100 → 新 GPU) のタイミングなので、 どのみち再 base 学習が必要になる流れ
- **トレードオフ**:
  - 既存 6lang base ckpt の継続学習が不可、 base 再生成コスト (75 epoch 規模、 1-2 週間)
  - 利用ユーザ (3rd party) の中で旧 ckpt 継続学習者がいた場合、 v1.12 で運用継続を強制 (旧 Docker image tag は保持される、 DR-007 案で別決定)
- **代替案**:
  - **A. resume 完全保証 (棄却)**: PyTorch upstream が保証しない部分まで本リポジトリで担保する技術コストが高い
  - **B. 失敗時のみ fallback (open-questions.md 旧推奨案、 棄却)**: 結局判断を smoke 時に持ち越すだけ、 先に「非対応」 と決めた方が明確
- **影響**:
  - **NFR-02 (学習再現性) の更新**: 「6lang base ckpt resume」 → 「from scratch 1 epoch 完走」 に変更
  - **DR-01 (モデルチェックポイント) の更新**: 既存 ckpt の lazy load 要件削除
  - **M4 Entry Criteria** から resume smoke 削除、 新規学習 smoke に置換
  - **CHANGELOG breaking note** に「resume 非対応」 を明記
  - **Migration guide** で「v1.12 までで学習した ckpt を v1.13 で resume する場合は v1.12 で継続学習、 v1.13 では新規学習のみ」 を案内
  - 旧 v1.12 Docker image tag を保持 (OQ-14 を「残す」 で確定する根拠が強化)

## 11. 既知の前提・調査結果 (Discovered Facts)

実装前の追加調査で確定した事実:

### DF-01: piper-train code 内の deprecated PyTorch API 利用 (調査済)

| 検査対象 | 結果 |
|---|---|
| `torch.cuda.amp.autocast` 直接利用 | **0 件** (Lightning Trainer 経由のため間接的) |
| `torch.set_default_tensor_type` 利用 | **0 件** |
| `torch.distributed.algorithms.ddp_comm_hooks` | **0 件** |
| `torch.jit.script` | **1 件** (`commons.py:fused_add_tanh_sigmoid_multiply`、 simple 関数で互換) |
| `torch.onnx.export` | **3 callsite** (`export_onnx.py`, `export_onnx_streaming.py`, `speaker_encoder/export_encoder.py`)、 `opset_version` 明示指定で安全 |

**結論:** piper-train code は torch 2.11 API 変更で直接書換 必要箇所が **ない**。 Lightning Trainer が precision を吸収するため amp 経路も unaffected。

### DF-02: 3.11 を使う workflow の正確な内訳 (調査済)

23 workflow が `python-version: '3.11'` 直接指定、 3 workflow が `matrix: ['3.11', ...]` 形式。 合計 26 workflow が touch 対象。 詳細は FR-01-01 表参照。

### DF-03: ONNX OPSET_VERSION の canonical (調査済)

| Path | Opset |
|---|---|
| `src/python/piper_train/export_onnx.py:31` | **15** |
| `src/python/piper_train/speaker_encoder/export_encoder.py:35` | **17** |
| `docs/spec/onnx-export-contract.toml` | main=15、 speaker_encoder=17 (line 122-124) |

差異は意図的 (STFT op が opset 17 で導入されたため speaker_encoder のみ 17)。 Phase 4 で torch 2.11 に bump する際も **据置** (DR-02)。

### DF-04: 外部 image / package の存在確認 (前提化)

- `python:3.13-slim-trixie` (Docker Hub official): 存在確認、 stable
- `gcr.io/distroless/python3-debian13`: 存在確認、 stable (2024 中頃以降)
- `nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04`: 存在確認、 stable
- `nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04`: 同上
- `ppa:deadsnakes/ppa` (Ubuntu 24.04): `python3.13` / `python3.13-dev` / `python3.13-venv` 提供確認、 Felix Krull (CPython core dev) maintained

---

## 12. 関連ドキュメント

| 文書 | 内容 |
|---|---|
| [`requirements.md`](requirements.md) | 要求定義 (WHAT/WHY) |
| [`README.md`](README.md) | 実装計画 (HOW) — Phase 別 diff、 rollback、 PR テンプレ |
| [Issue #527](https://github.com/ayutaz/piper-plus/issues/527) | GitHub Issue (トリガー) |
| [`../../spec/onnx-export-contract.toml`](../../spec/onnx-export-contract.toml) | ONNX opset の canonical 契約 |
| [`../../spec/audio-parity-contract.toml`](../../spec/audio-parity-contract.toml) | audio Tier 1-4 閾値 |

---

定義日: 2026-05-22
適用範囲: dev branch (Issue #527 完了まで)
版数: 1.0 (初版)
