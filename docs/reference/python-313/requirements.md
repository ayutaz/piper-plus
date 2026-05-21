# Issue #527 要求定義書

> 「デフォルトの Python ver を 3.13 にする」 (Issue [#527](https://github.com/ayutaz/piper-plus/issues/527)) の **要求仕様 (WHAT / WHY)** を定義する。 実装詳細 (HOW) は [`README.md`](README.md) を参照。

---

## 1. 目的

piper-plus リポジトリで **デフォルト Python interpreter を 3.11 → 3.13 に統一**する。 同時に Docker 全 image を **「CUDA 12.8 + Python 3.13」** で完全統一し、 新 GPU 環境 (T4 / Ada 6000 / RTX 5090) で最適な学習・推論を可能にする。

## 2. 背景

### 2.1 現状の課題

- リポジトリ内で Python 3.11 / 3.12 / 3.13 が **混在** (CI workflow 25 + 14 + 41 箇所、 Dockerfile 5 + 1 + 2 image)
- Docker 学習 image の `torch==2.2.1+cu121` が古く、 **新 GPU (RTX 5090 = Blackwell sm_120) で起動不能**
- base image (CUDA 12.6.3) と wheel (cu121 / cu128) の CUDA major が乖離、 **forward-compat 依存**で運用
- V100 想定のドキュメント (`CLAUDE.md` / `training-guide.md`) が実態と乖離する見込み

### 2.2 環境変化

- **2026-05-21 確定:** 学習サーバー GPU が V100 (sm_70) → **T4 (sm_75) / Ada 6000 (sm_89) / RTX 5090 (sm_120)** へ移行
- RTX 5090 (Blackwell) の正式サポートは **CUDA 12.8+ かつ PyTorch 2.7+** が前提

### 2.3 機会

- Python 3.13 の adaptive interpreter による 5-15% の汎用パフォーマンス向上
- CUDA 12.8 + cuDNN 9.5 / cuBLAS / NCCL 2.23+ の generic 改善
- Ada/Blackwell では TF32 / BF16 native / Flash Attention 2/3 / FP8 が解禁
- 期待値: V100 比で **学習速度 3-10x 向上**

---

## 3. 要求事項

### 3.1 機能要求 (Functional Requirements)

| ID | 要求 | 優先度 | 受入基準 |
|---|---|---|---|
| **FR-01** | デフォルト Python interpreter を 3.13 に揃える | 必須 | CI workflow の 3.11 言及が 0 件 (matrix 内の `["3.11","3.12","3.13"]` を除く) |
| **FR-02** | Docker 全 image を Python 3.13 で統一 | 必須 | 全 Dockerfile の `FROM` 行が Python 3.13 系 (`python:3.13-*` / `python3.13` via deadsnakes) |
| **FR-03** | GPU Docker image を CUDA 12.8 + Ubuntu 24.04 に統一 | 必須 | `python-train` / `python-inference` (CUDA variant) の base image が `nvidia/cuda:12.8.x-cudnn-*-ubuntu24.04` |
| **FR-04** | torch wheel を cu128 に統一 | 必須 | Dockerfile の `torch==*+cu121` 言及が 0 件、 `--extra-index-url` が `whl/cu128` |
| **FR-05** | RTX 5090 (Blackwell sm_120) で学習可能 | 必須 | 実機で `torch.cuda.get_device_capability()` が `(12, 0)`、 1 epoch FT が完走 |
| **FR-06** | Ada 6000 で学習可能 | 必須 | 実機で Template B 1 epoch FT 完走、 loss curve が canonical 範囲 |
| **FR-07** | T4 で推論可能 (学習対象外) | 必須 | 推論 Dockerfile で 6lang base モデル推論が動作、 RTF 計測 |
| **FR-08** | TF32 を新 GPU で有効化 | 推奨 | `torch.backends.cuda.matmul.allow_tf32 = True` が設定済、 sm_75 以下では noop |
| **FR-09** | bf16-mixed を新 GPU の推奨 precision にする | 推奨 | training-guide で bf16-mixed を main 候補として記載 |
| **FR-10** | distroless final image を Python 3.13 で統一 | 必須 | `gcr.io/distroless/python3-debian13` 利用、 内部パス `/usr/local/lib/python3.13` |

### 3.2 非機能要求 (Non-Functional Requirements)

| ID | 要求 | 受入基準 |
|---|---|---|
| **NFR-01: 後方互換性** | Python 3.11 サポートを維持 | `requires-python = ">=3.11"` 据置、 `python-tests.yml` matrix で 3.11 が PASS |
| **NFR-02: 学習再現性** | 既存学習 ckpt が新 Docker image で resume 可能 | `--resume-from-multispeaker-checkpoint` で 6lang base ckpt をロード成功、 loss が canonical 範囲 |
| **NFR-03: セキュリティ** | Trivy CVE クリーン | `docker-build.yml` の Trivy scan で new HIGH/CRITICAL が 0 |
| **NFR-04: OS 寿命** | Ubuntu EOL を 2 年以上延長 | base image を Ubuntu 22.04 (EOL 2027) → 24.04 (EOL 2029) に bump |
| **NFR-05: 観測性** | observability tool (nsys/nvprof) が version mismatch なく動作 | wheel cu128 + image CUDA 12.8 で同 major 揃え |
| **NFR-06: メンテナンス性** | CUDA forward-compat 依存を解消 | wheel と image の CUDA major が一致 |
| **NFR-07: クロスランタイム整合性** | 既存 contract gate を破らない | `runtime-parity-deep.yml` Tier 1-4 PASS、 audio_parity SNR ≥ 30dB |
| **NFR-08: 学習速度** | 新 GPU で V100 比 3-10x の学習速度向上 | Ada 6000 で Template B FT step time が V100 比で 3x 以上短縮 |
| **NFR-09: MOS / RTF 退行なし** | 既存品質基準を満たす | `model-quality-gate.yml` で baseline ±2% 以内 |

### 3.3 制約事項 (Constraints)

| ID | 制約 | 根拠 |
|---|---|---|
| **C-01** | `requires-python = ">=3.11"` 下限は据置 | Issue #527 のスコープ外、 既存 3.11 ユーザを切らない |
| **C-02** | `python-tests.yml` matrix `["3.11","3.12","3.13"]` は維持 | OSS public で CI minute 無制限、 網羅性優先 (memory `feedback_ci_matrix_no_reduction.md`) |
| **C-03** | `build-phonemize-wheels.yml` の cp313 build 追加は対象外 | piper-phonemize 1.1.0 が cp313 source build 未対応 |
| **C-04** | host driver R570+ が前提 | RTX 5090 (Blackwell) のハード要件 |
| **C-05** | FP8 / transformer_engine 統合は対象外 | architecture 適用範囲 + library 検証が必要、 別 issue |
| **C-06** | `[tool.ruff] target-version = "py311"` は据置 | 3.11 サポート維持と矛盾 |

---

## 4. スコープ

### 4.1 対象 (In Scope)

#### 4.1.1 ソースコード

- `src/python/piper_train/vits/monotonic_align/setup.py` (distutils → setuptools)
- `src/python/piper_train/__main__.py` (TF32 enable 1 行追加)

#### 4.1.2 Docker

| 対象 image | 変更内容 |
|---|---|
| `docker/python-inference/Dockerfile.cpu` | python:3.11-slim-bookworm → python:3.13-slim-trixie |
| `docker/python-inference/Dockerfile.cpu.distroless` | python:3.11 + debian12 → python:3.13 + debian13 |
| `docker/webui/Dockerfile.distroless` | 同上 |
| `docker/python-inference/Dockerfile` (CUDA) | CUDA 12.6.3 + Ubuntu 22.04 + python3.11 → CUDA 12.8 + Ubuntu 24.04 + deadsnakes python3.13 |
| `docker/python-train/Dockerfile` | 同上 + torch 2.2.1+cu121 → 2.11.0+cu128 |

#### 4.1.3 CI workflow

- 3.11 を明示指定している 25 workflow を 3.13 に置換 (matrix workflow を除く)
- `runtime-parity-deep.yml` の dump-python 3.11 → 3.13

#### 4.1.4 ドキュメント

- `CLAUDE.md` (V100 言及を新 GPU に置換)
- `CONTRIBUTING.md` (Python 3.11/3.12/3.13 → 3.13 を推奨表記)
- `README.md` / `README_*.md` (Python 3.11+ → 3.13 推奨)
- `QA-RELEASE-CHECKLIST.md` (CI バージョン表記)
- `docs/guides/training/training-guide.md` (V100 → 新 GPU)
- `docs/guides/training/wavlm-guide.md` (同上)
- `docs/features/webui.md` (Python 表記)
- `docker/README.md` (image base 表記)

### 4.2 対象外 (Out of Scope)

| 項目 | 理由 | 別 issue 化候補 |
|---|---|---|
| `requires-python` 下限引き上げ | C-01 | なし (据置方針) |
| `[tool.ruff] target-version` 引き上げ | C-06 | なし |
| `build-phonemize-wheels.yml` の cp313 build | C-03 | piper-phonemize upstream bump 時 |
| FP8 / transformer_engine 統合 | C-05 | "Issue #XXX: FP8 training support for new GPU" |
| ROCm / MPS バックエンド対応 | 別ハードウェア | "Issue #XXX: Multi-backend GPU support" |
| `docker/cpp-inference/Dockerfile.distroless` の debian13 化 | Python 利用なし、 統一性のみ | "Issue #XXX: cpp-inference distroless debian13 bump" |
| `docker/cpp-dev/Dockerfile` の python3.12 → 3.13 | dev tool 用、 動けば何でも | 不要 (個別判断) |
| `pytorch-lightning` / `wandb` / `librosa` / `numba` の floor pin 引き上げ | 3.13 化と独立 | "Issue #XXX: chore(deps): raise floor pins" |
| base image の CUDA 13.x bump | 12.8 統一後の next step | 12.8 安定運用後に再評価 |
| PyPI metadata の email 修正 | Issue #527 と無関係 | 別 chore PR |

---

## 5. 成功基準 (Acceptance Criteria)

### 5.1 必達 (MUST)

- [ ] 全 Phase (0-4) の PR が merge 済
- [ ] `python-tests.yml` matrix (3.11/3.12/3.13 × 3 OS) で全 PASS
- [ ] `docker-build.yml` Trivy scan で new HIGH/CRITICAL が 0
- [ ] `runtime-parity-deep.yml` Tier 1-4 PASS
- [ ] `model-quality-gate.yml` で baseline ±2% 以内
- [ ] **Ada 6000 実機**で Template B 1 epoch FT smoke 完走
- [ ] **RTX 5090 実機**で sm_120 起動確認 (`(12, 0)`)
- [ ] **T4 実機**で 6lang base 推論 smoke 完走
- [ ] host driver R570+ を学習・推論サーバー全台で確認

### 5.2 望ましい (SHOULD)

- [ ] Ada 6000 で V100 比 3x 以上の学習速度向上を実測
- [ ] RTX 5090 で V100 比 5x 以上の学習速度向上を実測
- [ ] TF32 ON/OFF の validation loss diff が許容範囲
- [ ] bf16-mixed への切替で loss curve が canonical 範囲

### 5.3 任意 (MAY)

- [ ] `torch.compile()` warm 後の +5-10% 向上を実測
- [ ] CHANGELOG に Python 3.13 default 化を記載

---

## 6. 前提条件 (Assumptions)

| ID | 前提 | 確認方法 |
|---|---|---|
| **A-01** | 学習サーバーの host driver が R570+ | `nvidia-smi` で確認 |
| **A-02** | 学習サーバーの新 GPU (Ada 6000 / RTX 5090) が物理的に利用可能 | サーバー管理者に確認 |
| **A-03** | T4 ホストが推論サーバーとして利用可能 | 同上 |
| **A-04** | NVIDIA driver / Docker 設定で `--gpus all` が機能 | `docker run --gpus all nvidia/cuda:12.8 nvidia-smi` で確認 |
| **A-05** | deadsnakes PPA が利用可能 (Ubuntu 24.04 + python3.13 提供) | `add-apt-repository ppa:deadsnakes/ppa` 動作確認 |
| **A-06** | piper-plus-g2p / pyopenjtalk-plus 等の依存が manylinux_2_28 wheel を提供 (glibc 2.39) | `pip download` で確認 |

---

## 7. ステークホルダー

| ロール | 関心事項 | 関与する Phase |
|---|---|---|
| **リポジトリオーナー (ayutaz)** | 全体方針承認、 PR review | 全 Phase |
| **学習担当** | 学習速度向上、 reproducibility | Phase 3, 4 |
| **推論サービス運用者** | inference image の安定性、 CVE 状況 | Phase 1, 2, 3 |
| **3rd party 利用者 (PyPI piper-plus)** | API 互換性、 Python 3.11 サポート維持 | 全 Phase (NFR-01) |
| **Home Assistant 統合ユーザー** | wyoming Docker の動作継続 | Phase 2 (regression check) |
| **CI maintainer** | workflow の green 状態 | Phase 1 |

---

## 8. リスク管理

### 8.1 主要リスク

| ID | リスク | 影響度 | 発生確率 | 緩和策 |
|---|---|---|---|---|
| **R-01** | torch 2.2 → 2.11 bump で学習結果が変わる | 高 | 中 | Phase 4 で実機 1 epoch smoke、 loss curve diff 確認 |
| **R-02** | Ubuntu 22.04 → 24.04 で wheel ABI 非互換 (glibc 2.35 → 2.39) | 高 | 低 | Phase 3 で docker build 失敗を早期検出、 manylinux_2_28 wheel 確認 |
| **R-03** | deadsnakes PPA の供給停止 / 信頼性 | 中 | 極低 | CPython core dev maintained で信頼性高、 代替案は multi-stage で `python:3.13-slim` 流用 |
| **R-04** | distroless debian12 → debian13 で onnxruntime ABI 不一致 | 高 | 低 | Phase 2 で builder/final 両方 trixie 揃え (PR #523 と同型対応) |
| **R-05** | RTX 5090 の cu128 wheel + 12.8 image でも起動失敗 | 高 | 低 | 早期に Ada 6000 で smoke (Blackwell 単独問題か区別)、 host driver R570+ 再確認 |
| **R-06** | TF32 enable で学習結果に意図しない drift | 中 | 中 | Phase 4 で TF32 ON/OFF 100 step deterministic 比較、 必要なら opt-in flag 化 |
| **R-07** | Trivy CVE で新規 HIGH/CRITICAL 表面化 | 中 | 中 | Phase 別に Trivy diff を確認、 必要なら apt upgrade で対処 |
| **R-08** | piper-phonemize cp313 未提供で 3.13 環境の preprocess 機能欠落 | 低 | 既知 | C-03、 既存 marker で macOS x86_64 + 3.11/3.12 限定 → 3.13 では skip (機能としては fall-back 動作) |

### 8.2 リスク受容範囲

- **学習 reproducibility:** loss / metric range が canonical の **±5% 以内**を許容
- **推論音質:** audio_parity Tier 4 (SNR ≥ 30dB) を必須
- **CI green:** matrix の green rate **>95%** (flaky 含めず)

---

## 9. 用語定義

| 用語 | 意味 |
|---|---|
| **Fully-aligned 戦略** | Docker base image / wheel / Python の version を同一 major で揃え、 forward-compat 依存を解消する方針 |
| **forward-compat 戦略** | base image (例 CUDA 12.6) より新しい wheel (例 cu128) を NVIDIA CUDA forward compatibility で動作させる従来方針 |
| **deadsnakes PPA** | CPython core developer が maintain する Ubuntu 用 Python パッケージリポジトリ |
| **sm_XX** | NVIDIA GPU compute capability (sm_70 = V100, sm_75 = T4, sm_89 = Ada, sm_120 = Blackwell) |
| **cu121 / cu128** | PyTorch wheel の CUDA toolkit suffix (12.1 / 12.8 対応) |
| **Tier 1-4** | audio_parity の階層判定 (Tier 1 = byte equal, ..., Tier 4 = SNR ≥ 30dB) |
| **canonical** | リポジトリ内で「正」 とする version / 設定 |

---

## 10. 関連ドキュメント

| 文書 | 内容 |
|---|---|
| [`README.md`](README.md) | 実装計画 (Phase 0-4) + 影響範囲 + diff サンプル + rollback 手順 |
| [Issue #527](https://github.com/ayutaz/piper-plus/issues/527) | GitHub Issue (本要求定義のトリガー) |
| [`../../migration/v1.11-to-v1.12.md`](../../migration/v1.11-to-v1.12.md) | 前回の breaking change 移行ガイド (PR template の参考) |
| [`../ort-versions.md`](../ort-versions.md) | ONNX Runtime version pin マトリクス (CUDA との関係) |

---

定義日: 2026-05-22
適用範囲: dev branch (Issue #527 完了まで)
版数: 1.0 (初版)
