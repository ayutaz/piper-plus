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
| **NFR-01: 後方互換性** | Python 3.11 サポートを維持 (Python interpreter のみ) | `requires-python = ">=3.11"` 据置、 `python-tests.yml` matrix で 3.11 が PASS。 ハードウェア / driver / 数値再現性などの**その他互換性損失は [9. 互換性影響評価](#9-互換性影響評価-breaking-changes-棚卸し) を参照** |
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

#### 4.1.5 ライブラリ依存 (floor drift お掃除)

DR-002 (決定事項) により、 root pyproject と member pyproject の floor pin drift を M1 で同時統一する。

| 対象 library | 統一値 | 配置 |
|---|---|---|
| `scipy` | `>=1.17.1` | M1 |
| `pytorch-lightning` | `>=2.4.0` | M1 |
| `transformers` | `>=4.50.0` | M1 |
| `wandb` | `>=0.26.1` | M1 |
| `tensorboard` | `>=2.20.0` | M1 |
| `onnxruntime` | `>=1.26.0` | M1 |
| `fastapi` | `>=0.136.1` | M1 |
| `uvicorn` | `>=0.46.0` | M1 |
| `pytest` | `>=9.0.3,<10` | M1 |
| `matplotlib` | `>=3.10.9` | M1 |
| `pypinyin` | `>=0.55.0` | M1 |
| `librosa` | `>=0.11.0` | M1 |
| `numba` | `>=0.61.0` | M1 |
| `torchmetrics` | `>=1.9.0` | M1 |
| `onnxscript` | `>=0.7.0` | M1 |
| `coverage` | `>=7.14.0` | M1 |
| `mypy` | `>=1.20.2` | M1 |

詳細は [`specifications.md §10.5`](specifications.md#105-ライブラリ-bump-候補-library-update-survey) 参照。

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
| `psutil` major bump (`>=5.9` → `>=7.0`) | security/major bump、 別 PR で評価 (DR-01 参照) | "Issue #XXX: chore(deps): bump psutil floor to 7.x" |
| `onnxsim-prebuilt` floor 明示 pin | 明示化のみ、 機能影響なし | "Issue #XXX: chore(deps): pin onnxsim-prebuilt floor" |
| `huggingface-hub <1.0` 上限解除 | HF Hub 1.0 release 動作確認後 | "Issue #XXX: chore(deps): allow huggingface-hub 1.0+" |
| `numpy <2.5` 上限解除 | numpy 2.5 dtype 仕様変更、 librosa/scipy upstream 対応待ち | "Issue #XXX: chore(deps): allow numpy 2.5+" |
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
| **R-01** | torch 2.2 → 2.11 bump で学習結果が変わる | 中 (DR-006 で resume 非サポート確定後に降格) | 中 | Phase 4 で from scratch 1 epoch smoke、 loss 発散がないことを確認。 過去 ckpt resume の検証は非対象 (DR-006) |
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

## 9. 互換性影響評価 (Breaking Changes 棚卸し)

**NFR-01 (3.11 サポート維持) は約束するが、 それ以外で「最適化と引き換えに失われる互換性」 が複数存在**する。 stakeholder 承認時の判断材料として全件列挙する。

### 9.1 失う互換性 (Breaking)

#### A. ハードウェア互換性

| ID | 失うもの | 影響範囲 | 対象 GPU | 緩和策 |
|---|---|---|---|---|
| **B-A1** | **V100 (sm_70) で新機能利用不可** | 学習速度の向上 | V100 | V100 は既に引退方針、 影響なし |
| **B-A2** | **Pascal P100 / P40 (sm_60/61) は wheel cu128 で deprecation 警告** | 学習・推論 | P100/P40 | 該当ハードなし、 影響なし |
| **B-A3** | **Maxwell (sm_50/52/53) は CUDA 12.x で完全非対応** | 学習・推論 | M40 等 | 既に CUDA 11.x 時点で deprecated、 影響なし |
| **B-A4** | **host driver R470 以下は cu128 wheel 起動不可** | 推論サーバー / 学習サーバー | 全 GPU 共通 | A-01 で R570+ を前提化、 サーバー管理者に確認 |
| **B-A5** | **古い nvidia-container-toolkit (1.10 以下) で `--gpus all` が CUDA 12.8 image を扱えない** | docker run 動作 | Docker host | サーバーの nvidia-container-toolkit を 1.14+ に更新 |

#### B. ソフトウェア互換性

| ID | 失うもの | 影響範囲 | 緩和策 |
|---|---|---|---|
| **B-B1** | **Python 3.10 以下は使えない** | 3.10 ユーザ | 既に `>=3.11` で 3.10 は切られている、 追加影響なし |
| **B-B2** | **Ubuntu 22.04 (Jammy) base image の wheel を再利用しない** | Docker build | Ubuntu 24.04 manylinux_2_28 wheel に揃える、 全 wheel 確認済 |
| **B-B3** | **glibc 2.35 (Jammy) でビルドした native extension は 2.39 (Noble) で再 build 推奨** | Cython 等 | piper-plus は wheel 経由なので影響なし、 ローカル開発のみ要 rebuild |
| **B-B4** | **CUDA 11.x driver でホストされた環境では起動不可** | 古い学習サーバー | 該当なし、 新サーバーは driver R570+ |
| **B-B5** | **deadsnakes PPA 経由 python3.13 は Ubuntu 公式サポート対象外** | Docker maintenance | CPython core dev maintained、 ただし Ubuntu 公式 SLA 範囲外 |
| **B-B6** | **distroless debian12 image を継続利用するユーザ (3rd party)** | 推論サービス | Issue #527 PR ノートに migration 指示を明記、 image tag は `v1.x.y-debian12` を残すか別途検討 |

#### C. データ・モデル互換性

| ID | 失うもの | 影響範囲 | 緩和策 |
|---|---|---|---|
| **B-C1** | **PyTorch 2.2 ckpt の resume を非サポート化 (model weights も含む)** | 学習 resume | DR-006 により v2.0 では過去 ckpt の resume 自体を保証しない。 v1.12 image で継続学習が必要なユーザは旧 image tag を使用 |
| **B-C2** | **ONNX export の opset_version default が 17 → 20+ に変わる可能性** | 推論ランタイム互換 | 明示的に `--opset 17` 等を export 時に指定して固定、 audio_parity Tier 4 で検証 |
| **B-C3** | **TF32 enable で生成された state_dict は TF32 OFF 環境で resume 時に loss curve が変わる** | 学習 reproducibility | 既存 ckpt は TF32 ありで再学習推奨、 もしくは TF32 OFF flag を opt-in 化 |
| **B-C4** | **bf16-mixed で学習した ckpt を FP16-mixed で resume すると数値表現の違いで loss spike の可能性** | 学習 reproducibility | precision は学習ジョブ通して固定、 途中変更しない運用 |

#### D. API 互換性 (PyTorch 2.2 → 2.11)

| ID | 失うもの | 影響範囲 | 緩和策 |
|---|---|---|---|
| **B-D1** | **`torch.cuda.amp.autocast` → `torch.amp.autocast('cuda', ...)` への移行** | piper-train code | piper-train は Lightning Trainer の precision 経由なので直接の影響なし |
| **B-D2** | **`torch.distributed.algorithms.ddp_comm_hooks` の一部 hook 削除** | DDP 学習 | piper-train は標準 DDP のため影響なし |
| **B-D3** | **`torch.jit.script` の一部仕様変更** | TorchScript export | piper-plus は ONNX export のみ、 TorchScript 経路は legacy |
| **B-D4** | **`torch.onnx.export` の `dynamic_axes` 等の引数名変更可能性** | ONNX export | `export_onnx.py` の引数を 2.11 docs に揃える、 Phase 4 で要検証 |
| **B-D5** | **`torch.optim.lr_scheduler.LRScheduler` の一部 method signature 変更** | Lightning Trainer | pytorch-lightning 2.6.1 が absorb、 piper-train 側は影響なし |
| **B-D6** | **`torch.set_default_tensor_type` deprecated**、 `torch.set_default_dtype` / `torch.set_default_device` への移行 | piper-train code | piper-train code でgrep 確認 (未使用予想)、 使われていれば置換 |

#### E. 数値再現性

| ID | 失うもの | 影響範囲 | 緩和策 |
|---|---|---|---|
| **B-E1** | **TF32 enable で matmul mantissa が 23-bit → 10-bit に低下** | 数値精度 | TTS workload では perceptual 影響なし、 ただし `torch.use_deterministic_algorithms(True)` と非互換 |
| **B-E2** | **bf16-mixed は FP16-mixed と異なる数値表現** | 学習 loss curve | dynamic range は広いが mantissa が短い、 loss scaling 不要だが分布変わる |
| **B-E3** | **cuDNN 8.9 → 9.5 で convolution algorithm 選択が変わる** | step 単位の数値再現 | cuDNN 内部の autotune 結果が変わる、 wall-clock は速くなるが bit-exact ではない |
| **B-E4** | **`torch.backends.cudnn.deterministic = True` を設定しても完全な determinism は得られない** | reproducible 学習 | Phase 4 で TF32 ON 時の determinism は諦める方針、 必要なら opt-in flag |

#### F. ドキュメント・サポート互換性

| ID | 失うもの | 影響範囲 | 緩和策 |
|---|---|---|---|
| **B-F1** | **V100 想定のトラブルシューティング情報が無効化** | CLAUDE.md / training-guide | Phase 4 で新 GPU 前提に置換 |
| **B-F2** | **`--precision 32-true` 推奨 (V100 用) が legacy 扱いになる** | training-guide | bf16-mixed を新メイン推奨に格上げ、 32-true は legacy compatibility 用と注記 |
| **B-F3** | **`--no-wavlm` 推奨 (V100 用) も VRAM 16GB 制約 (T4) 用に意味が変わる** | docs | T4 (16GB) では `--no-wavlm`、 Ada/Blackwell (32-48GB) では WavLM 利用可、 ニュアンス変更を明記 |

### 9.2 失わない互換性 (Maintained)

確認のため明示:

| ID | 維持されるもの | 確認方法 |
|---|---|---|
| **K-01** | Python 3.11 サポート (NFR-01) | `requires-python = ">=3.11"` 据置、 `python-tests.yml` matrix で 3.11 PASS |
| **K-02** | Python 3.12 サポート | 同 matrix で 3.12 PASS |
| **K-03** | 既存 PyPI `piper-plus` の API 互換 | runtime 関連は変更なし、 推論側のみ |
| **K-04** | 学習済み ONNX モデルの推論互換 | ランタイム側の onnxruntime は既に 1.26.0 で安定、 audio_parity Tier 4 PASS で検証 |
| **K-05** | 6lang base ckpt から FT 可能 | Template B FT smoke で確認 |
| **K-06** | Wyoming Docker (Home Assistant 連携) の動作 | 既に Python 3.13、 Phase 2 で変更なし |
| **K-07** | C# / Rust / Go / WASM / C++ ランタイム | piper_train の変更は piper runtime に波及しない (model file のみ共有) |
| **K-08** | Phoneme set / G2P 仕様 | num_symbols=173 strict gate で pin、 言語別 phonemizer も無変更 |
| **K-09** | OpenAI 互換 TTS API | docker/python-inference の FastAPI 経由、 同じ |
| **K-10** | カスタム辞書 / `[[ phoneme ]]` インライン記法 | 機能変更なし |

### 9.3 グレーゾーン (要検証)

実装中に「動くかもしれないが要確認」 の項目:

| ID | 項目 | 検証方法 | 検証 Phase |
|---|---|---|---|
| **G-01** | onnxsim-prebuilt 0.4.39 (cp312-abi3 wheel) が cp313 で完全動作 | Phase 3 で `python -m onnxsim` smoke test | Phase 3 |
| **G-02** | `pyopenjtalk-plus` の Cython extension が glibc 2.39 (Noble) wheel で問題なし | Phase 3 で docker build 成功 + 推論 smoke | Phase 3 |
| **G-03** | `g2pk2` (Korean phonemizer) が Python 3.13 で動作 | `import g2pk2` smoke | Phase 1 |
| **G-04** | `wandb` 0.26 の web socket / API が cu128 環境で接続 | Phase 4 学習 smoke で WandB ログ確認 | Phase 4 |
| **G-05** | `pytorch-lightning` 2.6.1 の `precision="bf16-mixed"` が Ada/Blackwell で期待通り動作 | Phase 4 で 100 step bf16 smoke | Phase 4 |
| **G-06** | `numba` 0.65.1 の JIT compile が Python 3.13 + Ubuntu 24.04 で正常 | Phase 4 norm_audio / VAD 経路の動作 | Phase 4 |

### 9.4 結論

**「ほぼ全ての互換性は維持できる」 が、 以下の 4 つだけは断念**:

1. **V100 / Pascal / Maxwell GPU を新機能と組み合わせる**未来 (これらは既に引退方針なので影響軽微)
2. **CUDA 11.x driver 環境**でのサポート (推論サービス運用者は driver bump 必要)
3. **TF32 OFF / TF32 ON のステップ単位 bit-exact 再現性** (perceptual 互換は維持)
4. **`torch.use_deterministic_algorithms(True)` モード**と TF32 / cuDNN 9.5 autotune の併用

それ以外の API / データ / ランタイム / phoneme / G2P / モデル互換は全て維持される。

## 10. 用語定義

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

## 11. 関連ドキュメント

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
