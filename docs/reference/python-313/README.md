# Default Python 3.11 → 3.13 移行

Issue [#527](https://github.com/ayutaz/piper-plus/issues/527) — デフォルト Python interpreter を 3.11 から 3.13 に揃えるための調査・計画ドキュメント群。

## このフォルダの構成

| 文書 | 内容 |
|---|---|
| [`README.md`](README.md) | (本ファイル) **実装計画 (HOW)** — Phase 分割、 影響範囲、 diff サンプル、 rollback 手順、 PR テンプレ |
| [`requirements.md`](requirements.md) | **要求定義 (WHAT/WHY)** — 目的、 機能/非機能要求、 スコープ、 成功基準、 制約、 前提、 ステークホルダー、 リスク |

> **追加ドキュメント置き場:** 実装着手時に Phase ごとの個別ノート (例: `phase-3-gpu-validation.md` 等) を追加する場合は本フォルダに置く。 追加した際は本表に追記すること。

## 背景

現状リポジトリ全体で **3.11 がデフォルト**として扱われているが、
今後の運用を見据えて **デフォルトを 3.13** に揃えたい (Issue #527)。

ただし `requires-python = ">=3.11"` 自体は変更しない予定。
「サポート下限を引き上げる」ではなく「日常的に使う interpreter を 3.13 に揃える」 という整理。

**2026-05-21 方針確定:** 学習サーバー GPU が V100 → T4 / Ada 6000 / RTX 5090 (Blackwell) へ移行することに伴い、 **Docker 全 image を「CUDA 12.8 + Python 3.13」 で完全統一**する方針に変更。 従来の「base image は 12.6 据置 + wheel cu128 で forward-compat」 戦略から、 **fully-aligned 戦略**へ転換する。

### Fully-aligned target

| 要素 | 全 Docker image での目標値 |
|---|---|
| Python interpreter | **3.13.x** (全 image で同一 minor) |
| CUDA toolkit (image) | **12.8.x** (GPU image のみ) |
| cuDNN (image) | **9.x** (CUDA 12.8 と整合する版、 GPU image のみ) |
| Ubuntu (CUDA image) | **24.04 (Noble)** (Jammy 22.04 から bump、 EOL 2029) |
| Python base (CPU image) | `python:3.13-slim-trixie` (Debian 13) |
| Distroless final | `gcr.io/distroless/python3-debian13` (= Python 3.13) |
| torch wheel | `2.11.0+cu128` (uv.lock canonical と整合) |

統一化のメリット:
- forward-compat 依存を解消 (wheel 内 CUDA runtime と image の CUDA toolkit が同一 major で揃う)
- Trivy CVE 管理が単一 CUDA version で完結 (現状は wheel 12.1 + image 12.6 の二重管理)
- nsys / nvprof / observability tooling の version mismatch リスク解消
- RTX 5090 (sm_120) 起動時の "wheel-only forward-compat" 不確定性が解消

## 現状サマリ

### Python interpreter

| カテゴリ | 3.11 | 3.12 | 3.13 | 備考 |
|---|---|---|---|---|
| **CI workflow** | 25 箇所 | 14 箇所 | 41 箇所 | 既に過半が 3.13 |
| **Dockerfile** | 5 image | 1 image (cpp-dev、 dev tool 用) | 2 image (wyoming / webui) | 推論/学習側がまだ 3.11 |
| **pyproject.toml** | 7 file (requires-python / target-version / mypy python_version) | - | - | 全 member 一致 |
| **テストマトリクス** | python-tests / g2p-python-ci で 3.11/3.12/3.13 を網羅 | | | 3.13 単体での退行は CI で見える |

### CUDA / Docker base

| Image | base image | CUDA | Python | 目標 (Fully-aligned) |
|---|---|---|---|---|
| `docker/python-train/Dockerfile` | nvidia/cuda:12.6.3-cudnn-{devel,runtime}-ubuntu22.04 | 12.6.3 | 3.11 | **12.8.x + ubuntu24.04 + 3.13** |
| `docker/python-inference/Dockerfile` | nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04 | 12.6.3 | 3.11 | **12.8.x + ubuntu24.04 + 3.13** |
| `docker/python-inference/Dockerfile.cpu` | python:3.11-slim-bookworm | (CPU) | 3.11 | **python:3.13-slim-trixie** |
| `docker/python-inference/Dockerfile.cpu.distroless` | python:3.11-slim-bookworm + distroless/python3-debian12 | (CPU) | 3.11 | **python:3.13-slim-trixie + distroless/python3-debian13** |
| `docker/webui/Dockerfile` | python:3.13.13-slim-trixie | (CPU) | 3.13 | 据置 ✓ |
| `docker/webui/Dockerfile.distroless` | python:3.11-slim-trixie + distroless/python3-debian12 | (CPU) | 3.11 | **python:3.13-slim-trixie + distroless/python3-debian13** |
| `docker/wyoming/Dockerfile` | python:3.13.13-slim-trixie | (CPU) | 3.13 | 据置 ✓ |
| torch wheel (Docker) | cu121 (Dockerfile 直 pin) | 12.1 | — | **cu128 (uv.lock canonical 整合)** |
| torch wheel (uv workspace) | cu128 | 12.8 | — | 据置 ✓ |

### 既存 CI gate

`workspace-python-parity` (`scripts/check_workspace_python_parity.py`) で
全 pyproject の `requires-python` 一致が pin されている。

## 影響範囲の内訳

### A. pyproject.toml (7 file)

| ファイル | 設定 | 値 | 変更可否 |
|---|---|---|---|
| `pyproject.toml` (root) | `requires-python` | `>=3.11` | 据置 (下限引き上げない) |
| 〃 | `[tool.ruff] target-version` | `py311` | 据置 (3.11 まで言語機能サポート) |
| 〃 | `[project.optional-dependencies] preprocess` の marker | `python_version < '3.13'` | piper-phonemize wheel 制約 (3.13 では skip 済み、変更不要) |
| `src/python/pyproject.toml` | `requires-python` / `[tool.mypy] python_version` | `>=3.11` / `"3.11"` | 据置 |
| `src/python/g2p/pyproject.toml` | 同上 + `[tool.ruff] target-version` | `>=3.11` / `"3.11"` / `py311` | 据置 |
| `src/python_run/pyproject.toml` | 同上 (`[tool.mypy] python_version`) | `>=3.11` / `"3.11"` | 据置 |
| `src/python_stub/pyproject.toml` | `requires-python` | `>=3.11` | 据置 |
| `src/piper_phonemize_bundled/pyproject.toml` | `requires-python` | `>=3.11` | 据置 |
| `src/rust/piper-python/pyproject.toml` | `requires-python` | `>=3.11` | 据置 |

**結論:** pyproject.toml 側は **触らない**。 下限は 3.11 維持で問題ない (3.13 がデフォルト interpreter になっても 3.11 利用者を切らない)。

### B. CI workflow (3.11 を使う 25 箇所)

「デフォルト Python」を 3.13 に置換する対象。 内訳:

| Workflow | 行 | 用途 | 切替方針 |
|---|---|---|---|
| `ci.yml` | 239, 304 | uv workspace test (Python matrix) | 3.13 へ (matrix も含めて) |
| `pre-commit.yml` | 81 | pre-commit run --all-files | 3.13 へ |
| `python-lint.yml` | 22 | ruff lint matrix | 3.13 へ |
| `python-doctest.yml` | 55, 59 | doctest | 3.13 へ |
| `python-tests.yml` | 49 | OS × Python matrix (`3.11/3.12/3.13`) | **matrix は維持** (全 3 系列回す方針が memory feedback_ci_matrix_no_reduction に登録済) |
| `g2p-python-ci.yml` | 33, 59, 114 | G2P テスト | matrix 据置、 single 起動を 3.13 へ |
| `build-phonemize-wheels.yml` | 36, 119, 188 | piper-phonemize wheels build | **wheel matrix は 3.11/3.12 のまま** (piper-phonemize 1.1.0 が cp313 wheel 未提供) |
| `webui-test.yml` | 43, 118 | WebUI 単体テスト | 3.13 へ (matrix は 3.12/3.13 程度に絞る案) |
| `codeql.yml` | 168 | SAST | 3.13 へ |
| `release-verify.yml` | 107 | release tag 検証 | 3.13 へ |
| `dev-create-release.yml` | 256, 312 | dev release | 3.13 へ |
| `dev-build-all.yml` | 178, 211 | nightly build | 3.13 へ |
| `deploy-huggingface.yml` | 112 | HF Spaces deploy | 3.13 へ |
| `model-quality-gate.yml` | 44 | モデル品質ゲート | 3.13 へ |
| `generate-combined-report.yml` | 25 | レポート生成 | 3.13 へ |
| `runtime-parity-deep.yml` | 58, 298 | runtime parity (audio_parity.py が **3.11 必須**コメントあり) | **要検証** (line 295 のコメント: "Match dump-python (3.11)") |
| `sbom.yml` | 67 | SBOM 生成 | 3.13 へ |
| `security-audit.yml` | 95 | 依存脆弱性 | 3.13 へ |
| `test-hf-space.yml` | 39 | HF Space E2E | 3.13 へ |
| `test-japanese-tts.yml` | 107, 200 | 日本語 TTS E2E | 3.13 へ |
| `timing-parity.yml` | 58 | timing 同期検証 | 3.13 へ |
| `wyoming-smoke.yml` | 66 | Home Assistant 連携 | 3.13 へ (Dockerfile は既に 3.13) |
| `version-consistency.yml` | 72 | バージョン整合性 | 3.13 へ |

**焦点:** 既に 41 workflow が 3.13 にあるので「混在 → 3.13 統一」 の方向で揃える。
`runtime-parity-deep.yml` の dump-python は **3.11 固定の意図的根拠**を確認する必要あり (作成された ONNX dump との parity ハッシュが Python version に依存していないか)。

### C. Dockerfile (Fully-aligned 統一テーブル)

「CUDA 12.8 + Python 3.13」 統一目標における各 Dockerfile の現状と切替先:

| ファイル | 現状 base | 現状 Python | 統一後の base | 統一後の Python | 切替難度 |
|---|---|---|---|---|---|
| `docker/wyoming/Dockerfile` | `python:3.13.13-slim-trixie` | **3.13.13** | 据置 | 据置 | **不要** |
| `docker/webui/Dockerfile` | `python:3.13.13-slim-trixie` | **3.13.13** | 据置 | 据置 | **不要** |
| `docker/python-inference/Dockerfile.cpu` | `python:3.11-slim-bookworm` | 3.11 | `python:3.13-slim-trixie` | 3.13 | **小** (1 行置換) |
| `docker/python-inference/Dockerfile.cpu.distroless` | builder: `python:3.11-slim-bookworm` / final: `distroless/python3-debian12` | 3.11 | builder: `python:3.13-slim-trixie` / final: `distroless/python3-debian13` | 3.13 | **中** (内部パス `/usr/local/lib/python3.11` → `/usr/local/lib/python3.13` 6 箇所書換) |
| `docker/webui/Dockerfile.distroless` | builder: `python:3.11-slim-trixie` / final: `distroless/python3-debian12` | 3.11 | builder: `python:3.13-slim-trixie` / final: `distroless/python3-debian13` | 3.13 | **中** (同上) |
| `docker/python-inference/Dockerfile` (CUDA) | `nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04` | 3.11 (apt) | `nvidia/cuda:12.8.x-cudnn-runtime-ubuntu24.04` | 3.13 (deadsnakes PPA) | **大** (Ubuntu 22.04 → 24.04 + CUDA 12.6 → 12.8 + deadsnakes 経由 python3.13) |
| `docker/python-train/Dockerfile` | `nvidia/cuda:12.6.3-cudnn-{devel,runtime}-ubuntu22.04` | 3.11 (apt) | `nvidia/cuda:12.8.x-cudnn-{devel,runtime}-ubuntu24.04` | 3.13 (deadsnakes PPA) | **特大** (上記 + torch 2.2.1+cu121 → 2.11.0+cu128 + GPU 最適化設定追加) |
| `docker/cpp-inference/Dockerfile.distroless` | `debian:12-slim` builder / `distroless/cc-debian12` | (なし、 C++ のみ) | 据置 or `debian:13-slim` + `distroless/cc-debian13` | (なし) | **任意** (Python 利用なし、 統一性のためなら bump、 別 issue で評価可) |
| `docker/cpp-inference/Dockerfile` | `ubuntu:24.04` | (なし) | 据置 | (なし) | 不要 |
| `docker/cpp-dev/Dockerfile` | `ubuntu:24.04` + python3.12 | 3.12 (dev tool 用) | 据置 (dev tool のため) or python3.13 へ揃え | 任意 | **小** (dev tool 用、 動けば何でも OK) |
| `docker/cpp-inference/Dockerfile.test` | `ubuntu:24.04` | (なし) | 据置 | (なし) | 不要 |

#### CUDA image の選択肢比較

`docker/python-{inference,train}/Dockerfile` の base image 候補:

| 案 | base image | Python 入手方法 | メリット | デメリット |
|---|---|---|---|---|
| **A. Ubuntu 24.04 + deadsnakes 3.13 (推奨)** | `nvidia/cuda:12.8.x-cudnn-runtime-ubuntu24.04` | `apt install software-properties-common` → `add-apt-repository ppa:deadsnakes/ppa` → `apt install python3.13 python3.13-dev python3.13-venv` | Ubuntu EOL 2029、 deadsnakes は信頼性高 (CPython core dev maintained) | deadsnakes PPA への dependency |
| B. Ubuntu 22.04 + deadsnakes 3.13 | `nvidia/cuda:12.8.x-cudnn-runtime-ubuntu22.04` | 同上 | base image 変更なし (Jammy 据置) | Ubuntu Jammy EOL 2027 で再 bump 必要 |
| C. multi-stage で `python:3.13-slim-trixie` builder + CUDA runtime | builder = `python:3.13-slim-trixie`、 runtime = `nvidia/cuda:12.8.x-base-ubuntu24.04` | builder で venv 作成、 COPY で runtime stage に転送 | apt 不要、 distroless 系と同パターン | Dockerfile 複雑化、 nvidia-cuda の `base` variant に site-packages を後付け |

**推奨: A** (Ubuntu 24.04 + deadsnakes)。 wyoming/webui が既に `python:3.13-slim-trixie` (Debian 13 = trixie) を使用しており、 OS 系統は分散するが、 CUDA 必須の image だけ Ubuntu 24.04 + deadsnakes にしても観察性能に大差なし。 Trivy CVE は image 別に scan する仕様。

### D. ドキュメント

| ファイル | 行 | 内容 |
|---|---|---|
| `CONTRIBUTING.md` | 5 | "Python 3.11, 3.12, or 3.13" — 並び順入替 (3.13 を先頭/推奨に) |
| `README.md` | 274 | "Python 3.11+ が必要" — 据置可、 推奨 3.13 を追記すると親切 |
| `README_EN.md` | 257 | 同上 |
| `README_*.md` (KO/ZH/ES/FR/PT/DE) | — | 同上 |
| `QA-RELEASE-CHECKLIST.md` | 66, 144, 453 | "CI は 3.11/3.13" / "3.11 Go 統合テスト" — 3.13 中心の表記に |
| `docs/features/webui.md` | 11 | "Python 3.11+" — 据置可 |
| `docs/guides/training/training-guide.md` | 31 | "python 3.11" — 3.13 に |
| `docker/README.md` | 14 | "python:3.11-slim-bookworm" — Dockerfile 切替後に追従 |

### E. その他

- `.github/dependabot.yml` line 253-265: Python base image の minor bump (3.13 → 3.14) を ignore する記述あり。 **これは維持** (3.13 → 3.14 の自動 PR 抑止)。

## ライブラリ 3.13 互換性リスク

`uv.lock` から各依存の cp313 wheel 提供状況を直接確認した結果:

| 依存 | lockfile version | cp313 wheel | リスク |
|---|---|---|---|
| `torch` (root) | `2.11.0` (Linux は cu128) | **cp311/312/313/313t/314/314t 全 OS** ✓ | 低 (lockfile レベル) |
| `torch` (`docker/python-train`) | `==2.2.1+cu121` (Dockerfile hard pin) | cp313 wheel **無し** | **高** (Phase 3 で 2.11.0+cu128 へ bump 必須) |
| `onnxruntime` | `>=1.20.0` | 1.20+ で cp313 提供 | 低 |
| `pyopenjtalk-plus` | `>=0.4` | 最新版で cp313 wheel あり | 低 |
| `piper-phonemize` | `1.1.0; python_version < '3.13'` marker | cp313 wheel 未提供 | **対応済** (marker で 3.13 では skip) |
| `numba` | `0.65.1` | cp311/312/313/313t/314/314t 全 wheel あり ✓ | 低 |
| `onnxsim-prebuilt` | `0.4.39.post2` | cp311 + **cp312-abi3** (3.12+ で共用) | 低 |
| `pytorch-lightning` | `2.6.1` | pure-python (3.13 OK) | 低 |
| `tensorboard` | `2.20.0` | pure-python (3.13 OK) | 低 |
| `wandb` | `0.26.1` | cp313 wheel 提供済 | 低 |
| `numpy` | `<2.5` | 2.1+ で cp313 wheel あり | 低 |
| `scipy` | `>=1.17.1` | 1.14+ で cp313 wheel あり | 低 |

**最大ブロッカー:** `docker/python-train/Dockerfile` line 73 の `"torch==2.2.1+cu121"` 直 pip install。
ルートの `pyproject.toml` (`torch>=2.11.0`) や `uv.lock` (`2.11.0+cu128`) と乖離している (PR #532 で base image は CUDA 12.6 に bump 済み、 だが torch wheel が古いまま)。 3.13 化のタイミングで `torch==2.11.0+cu128` 等へ揃えると、 cp313 wheel が利用可能でかつ `pyproject.toml` とも整合する。

## ライブラリ bump を同時にやれるか?

「3.13 化したついでに torch などの古い pin も上げたい」 という観点で精査した結論:

**結論:** **3.13 default 化は library bump を自動解禁しない。** 唯一同時 bump 必須なのは `docker/python-train/Dockerfile` の torch のみ (3.13 cp wheel が存在しないため強制セット)。 それ以外は別 PR で個別評価が推奨。

### 理由

`requires-python = ">=3.11"` の **floor は据置**方針 (Issue #527 のスコープ外)。 floor を 3.11 のままにする限り、 library の floor pin (`>=`) を上げても resolver は当面影響しない。 一方 library 側でも、 現状 piper-plus が依存する main packages は **どれも Python 3.11 をまだサポート**しており、 「3.11 を切らないと使えない library version」 が存在しない。

### uv.lock の現状 vs root `pyproject.toml` floor

| 依存 | floor pin | lockfile actual | upstream 最新 (2026-05) | 同時 bump 妥当性 |
|---|---|---|---|---|
| `torch` (root) | `>=2.11.0` | `2.11.0+cu128` | 2.11.x | **既に最新** — 据置 |
| `torch` (docker/python-train) | `==2.2.1+cu121` | — | 2.11.x | **必須セット** — 3.13 cp wheel 無し |
| `onnxruntime` | `>=1.20.0` (src/python) / `>=1.26.0` (requirements) | `1.26.0` | 1.26.x | 既に最新、 floor を上げるか別 issue |
| `pyopenjtalk-plus` | `>=0.4` | `0.4.1.post8` | 0.4.1.post8 | 既に最新 |
| `pytorch-lightning` | `>=2.0` | `2.6.1` | 2.6.x | floor 据置 (2.x は 2.0 から後方互換) |
| `transformers` | `>=4.30` (root) / `>=4.38` (train) | `4.57.6` | 4.57.x | floor 据置 |
| `numpy` | `<2.5` (上限) | `2.4.4` | 2.4.x | 上限は ABI 警戒 |
| `librosa` | `>=0.10` | `0.11.0` | 0.11.x | floor 据置可 |
| `wandb` | `>=0.26.1` | `0.26.1` | 0.26.x | 既に最新 |
| `numba` | `>=0.59` | `0.65.1` | 0.65.x | floor 上げ余地あり (別 PR) |
| `huggingface-hub` | `>=0.36.2,<1.0` | `0.36.2` | 0.36.x | `<1.0` は HF Hub 1.0 改訂への安全策、 据置 |

### 3.13 化と同時にやるもの (本 Issue スコープ)

| 対象 | 現状 | 切替 | 理由 |
|---|---|---|---|
| `docker/python-train/Dockerfile` の torch | `==2.2.1+cu121` | `==2.11.0+cu128` | torch 2.2.1 が cp313 wheel 未提供のため、 3.13 化と同時にしか上げられない |
| `docker/python-train/Dockerfile` の torchaudio | `==2.2.1+cu121` | `==2.11.0+cu128` | torch とバージョン揃え必須 |
| `docker/python-train/Dockerfile` の torchvision | `==0.17.1+cu121` | torchvision 0.21+ (torch 2.11 対応版) | 同上 (ただし piper-train は torchvision を使っていないため削除も可) |

### 別 PR で評価すべきもの (本 Issue スコープ外)

3.13 化と独立してメリットを持つ floor bump。 一括で混ぜると revert 単位が肥大化するため別出し:

| 対象 | 現状 floor | bump 候補 | 別 PR の動機 |
|---|---|---|---|
| `pyproject.toml` の `pytorch-lightning>=2.0` | 2.0 | `>=2.4` | 2.0/2.1 は configure_model API がなく retro 互換性が薄い (2.4 で `configure_model` が安定) |
| `src/python/pyproject.toml` の `wandb>=0.16` | 0.16 | `>=0.20` | 0.16 は old artifact API、 lock も 0.26 |
| `src/python/pyproject.toml` の `librosa>=0.10` | 0.10 | `>=0.11` | librosa 0.11 で resample が高速化 |
| `numba>=0.59` | 0.59 | `>=0.61` | 0.59-0.60 は numpy 2.x ABI issue で warning |
| `huggingface-hub<1.0` 上限 | `<1.0` | 据置 | HF Hub 1.0 は dataset API 全面改訂、 release 直後に動作確認してから外す |
| `numpy<2.5` 上限 | `<2.5` | 据置 | 2.5 は dtype 仕様変更を予告、 librosa / scipy 対応待ち |

### 結論まとめ

- **3.13 化単体で library bump はほぼ起きない** — floor pin は 3.11 据置のため、 resolver は今と同じ wheel を選ぶ
- **必須同時 bump は docker/python-train の torch のみ** (cp wheel 制約) — Phase 3 でセット
- **floor 引き上げによる "クリーンアップ"** は別 PR `chore(deps): raise floor pins` 系で評価 (上表 5 項目)
- **3.13 を default にする本来の意義は** 「Python 自体のセキュリティ + パフォーマンス (3.13 は PGO/LTO + adaptive interpreter で 5-15% 速)」 と 「downstream エコシステムの追従先を統一」 であり、 library version とは独立

## CUDA バージョン

CUDA は **3 層** (base image / torch wheel / uv index) で個別に pin されており、 現状はそれぞれ別 version を持つ。 3.13 化との直接の依存はないが、 `docker/python-train` で torch を bump するなら CUDA wheel suffix も同時整理が必要。

### 現状

| 層 | 場所 | CUDA version | cuDNN | 備考 |
|---|---|---|---|---|
| **base image** (推論) | `docker/python-inference/Dockerfile` | **12.6.3** | 9 | PR #533 で 12.4.1 → 12.6.3 bump |
| **base image** (学習) | `docker/python-train/Dockerfile` builder + runtime | **12.6.3** | 9 | PR #532 で bump |
| **torch wheel** (uv workspace) | `pyproject.toml` `[tool.uv.sources]` | **cu128** (= CUDA 12.8 対応) | torch 内蔵 | ローカル / CI Linux で resolve |
| **torch wheel** (学習 Docker) | `docker/python-train/Dockerfile` line 73 | **cu121** (= CUDA 12.1 対応) | **cuDNN 8.9** | 古い、 直 pip install で uv.lock を経由しない |
| dependabot ignore | `.github/dependabot.yml:263` | nvidia/cuda minor bump 無視 | — | 手動更新方針 (PR #427 経緯) |

なぜ base = 12.6 + wheel = cu121 / cu128 が動くか:
- **NVIDIA CUDA forward compatibility** により、 12.6 driver は 12.1 や 12.8 wheel に bundle された runtime を dlopen して動かせる。
- torch wheel は `site-packages/nvidia/{cublas,cudnn,...}/lib` に自前の runtime を bundle し、 dynamic loader が `LD_LIBRARY_PATH` より優先するため、 base image の cuDNN 9 ではなく **wheel bundle の cuDNN (8.9 for cu121 / 9.x for cu128)** が使われる。

### Issue #527 (3.13 化) との関係

**Fully-aligned 戦略 (2026-05-21 方針確定):** Docker 全 image を CUDA 12.8 + Python 3.13 で完全統一する。 従来の「base image 12.6 据置 + wheel cu128 で forward-compat」 戦略は廃止。

理由:
- RTX 5090 (Blackwell sm_120) の正式対応は CUDA 12.8+ — Issue #527 のタイミングで揃える
- wheel cu128 と image CUDA 12.8 を同 major 揃えにすると forward-compat 依存を解消
- Ubuntu 22.04 → 24.04 で OS EOL を 2027 → 2029 に延長
- Trivy CVE 管理が単一 CUDA major で完結 (wheel 12.1 + image 12.6 の二重管理を解消)

### 同時 bump 内容 (Phase 3 統一化)

| 項目 | 現状 | 切替先 | 根拠 |
|---|---|---|---|
| torch wheel suffix | `cu121` | `cu128` | uv.lock canonical と整合 (`pyproject.toml` `[[tool.uv.index]]` も既に cu128) |
| torchaudio wheel suffix | `cu121` | `cu128` | torch とセット |
| `--extra-index-url` URL | `download.pytorch.org/whl/cu121` | `download.pytorch.org/whl/cu128` | 同上 |
| base image (`nvidia/cuda:12.6.3-cudnn-...-ubuntu22.04`) | 12.6.3 + ubuntu22.04 | **`12.8.x-cudnn-...-ubuntu24.04`** | fully-aligned 戦略、 OS EOL 延長、 RTX 5090 host driver R570+ と整合 |
| cuDNN (image) | 9 (12.6 系) | **9 (12.8 系)** | wheel cu128 と image の cuDNN を 12.8 系で揃える |
| Ubuntu base | 22.04 (Jammy, EOL 2027) | **24.04 (Noble, EOL 2029)** | EOL 延長、 python3.13 deadsnakes PPA で安定供給 |
| Python | `apt python3.11` | **deadsnakes PPA + `python3.13`** | Ubuntu 24.04 apt 標準は python3.12、 3.13 は deadsnakes 経由 |

### 別 issue で評価可能なもの (本 Issue スコープ外)

- dependabot の `nvidia/cuda` minor bump ignore を解除
  → 自動 PR で 12.8 → 12.9 等が来るが、 cuDNN / driver 互換性ローテーションが伴うため**据置推奨**。 PR #427 (12.4 → 12.9 jump) のような 5 minor 飛びを避けたい運用判断。 12.8 に統一後は次の手動 bump タイミング (例: 13.0 LTS) まで据置。
- ROCm / Apple Silicon MPS バックエンドへの拡張
  → torch には mps backend あり、 cu128 とは独立。 これは別 issue。
- `docker/cpp-inference/Dockerfile.distroless` の debian12 → debian13 化
  → Python 利用なし、 統一性のためなら bump、 別 PR で評価可。
- `docker/cpp-dev/Dockerfile` の python3.12 → 3.13
  → dev tool 用、 動けば何でも OK、 別 commit で個別判断。

## CUDA 12.8 アップグレードの恩恵 (3.13 + torch 2.11 + 新 GPU 環境)

「3.13 化のついでに CUDA 12.8 にする最適化恩恵は?」 への分析。

**学習対象 GPU の前提変更 (2026-05-21):** V100 が使えなくなったため、 今後の学習サーバーは以下 3 種に移行する:
- **T4** (Turing sm_75, 16GB GDDR6) — 主に推論用途
- **RTX 6000 Ada Generation** (Ada Lovelace sm_89, 48GB GDDR6) — メイン学習機
- **RTX 5090** (Blackwell sm_120, 32GB GDDR7) — 次世代学習機

この前提変更により **CUDA 12.8 化の優先度は「恩恵あり」 から「Blackwell サポートのため事実上必須」 に昇格**する。 V100 想定で書いていた既存セクションは全面差し替え。

### 結論 (先出し、 新 GPU 前提)

- **RTX 5090 (Blackwell sm_120) を使う場合、 CUDA 12.8 + cu128 wheel は事実上必須**。 cu121 wheel は sm_120 を含まないため Blackwell では起動不能。
- **Ada 6000 (sm_89) も CUDA 12.8 で FP8 / Flash Attention 3 / BF16 native が解禁** → V100 比で学習速度 **5-10 倍**の可能性 (VITS の Conv/GEMM 構成次第)。
- **T4 (sm_75) は学習には VRAM 16GB が厳しい**。 推論 (`docker/python-inference`) は十分。
- **base image (12.6.3) も bump 検討が現実味を帯びる**: RTX 5090 host の最小 driver 要件 (R570+) と整合させるため。

### 新 GPU 別の機能対応表

| 機能 | V100 (sm_70, 旧) | T4 (sm_75) | Ada 6000 (sm_89) | RTX 5090 (sm_120) | 備考 |
|---|---|---|---|---|---|
| FP32 / FP16-mixed | ✅ | ✅ | ✅ | ✅ | 基本動作 |
| TF32 (Ampere+) | ❌ | ❌ | ✅ | ✅ | matmul 1.5-2x 高速化 |
| BF16 native | ❌ (emul) | ❌ | ✅ | ✅ | FP16 より numerical stable |
| FP8 (E4M3/E5M2) | ❌ | ❌ | ✅ (Gen 4 TC) | ✅ (Gen 5 TC) | matmul 2-4x、 学習で活用可能 |
| Flash Attention 2 | ❌ | 限定 | ✅ | ✅ | self-attention 高速化 |
| Flash Attention 3 | ❌ | ❌ | ✅ | ✅ (Gen 5 で最適化) | FA2 比 1.5-2x |
| cu128 wheel 対応 | ✅ | ✅ | ✅ | **必須** | sm_120 PTX は cu128 のみ |
| 最小 PyTorch | 2.x | 2.x | 2.4+ | **2.7+** (2.11 推奨) | Blackwell 公式対応 |
| 最小 driver | R450+ | R450+ | R525+ | **R570+** | RTX 5090 は新 driver 必須 |
| 推奨用途 | (引退) | 推論専用 | **メイン学習** | **次世代学習** | T4 は VRAM 16GB で 6lang base 学習厳しい |

### 学習速度の期待値 (V100 比、 6lang base 学習想定)

| GPU | 構成 | VRAM | 期待倍率 (vs V100) | 備考 |
|---|---|---|---|---|
| V100 16GB | FP32 (canonical), batch=20 | 16GB | 1.0x (baseline) | 旧環境 |
| T4 16GB | FP16-mixed, batch=8-12 | 16GB | 0.5-0.7x | Tensor Core Gen 2 で AMP は効くが VRAM が boundary、 学習向きではない |
| Ada 6000 48GB | BF16-mixed, batch=32-64, TF32 | **48GB** | **3-5x** | VRAM 余裕で batch 拡大 + BF16 + TF32 + FA2 |
| Ada 6000 48GB | FP8-mixed, batch=64+, FA3 | 48GB | **5-8x** | FP8 + Flash Attention 3 (要 torch 2.7+ + transformer_engine 系) |
| RTX 5090 32GB | BF16-mixed, batch=32-48 | 32GB | **5-7x** | Gen 5 TC + 高 clock + GDDR7 |
| RTX 5090 32GB | FP8-mixed, batch=48-64, FA3 | 32GB | **7-10x** | Blackwell の FP8 + FA3 のフル活用 |

> **注意:** VITS 学習で FP8 / FA3 を実際に効かせるには PyTorch 側の AMP 設定 + nn.Module 側の対応が必要。 piper-train は現状 FP32/FP16-mixed のみ。 FP8 採用は別 issue で評価。

### Ada 6000 / RTX 5090 で **新たに使えるようになる** 12.8 機能

V100 時代に「使わない」 と書いたものが、 新 GPU では実用範囲に入る:

| 機能 | 対応 GPU | piper-train 適用性 | 採用判断 |
|---|---|---|---|
| **TF32** | Ada 6000 / RTX 5090 | ✅ Linear / Conv で透過適用 (`torch.backends.cuda.matmul.allow_tf32 = True`) | **本 Issue で同時設定推奨** (1 行追加で 1.3-1.5x) |
| **BF16-mixed** | Ada 6000 / RTX 5090 | ✅ `--precision bf16-mixed` (Lightning native) | **training-guide で推奨**、 既存 `--precision 16-mixed` の上位互換 |
| **FP8 (E4M3)** | Ada 6000 / RTX 5090 | △ transformer_engine 統合が必要 | **別 issue 評価**、 piper-train の VITS architecture は FP8 適用範囲が限定的 |
| **Flash Attention 2** | Ada 6000 / RTX 5090 | △ PyTorch SDPA 経由で自動利用 (attention layer のみ) | **自動適用**、 明示設定不要 |
| **Flash Attention 3** | Ada 6000 / RTX 5090 | △ PyTorch 2.7+ で SDPA が自動選択 | **自動適用** |
| **CUDA Graphs Enhanced** | Ada 6000 / RTX 5090 | ❌ Lightning の動的ループと非互換 | スコープ外 |

### base image bump (12.6.3 → 12.8.x) の評価 (Fully-aligned 戦略)

「3.13 + 新 GPU + Docker 統一」 の方針確定により、 base image bump は **「別 PR で評価」 から「Phase 3 必須項目」 に格上げ**された:

| 項目 | wheel only (cu128) on 12.6 image | **base 12.8 + wheel cu128 (本方針)** | 違い |
|---|---|---|---|
| RTX 5090 動作 | 12.6 image + cu128 wheel + host driver R570+ で forward-compat 動作 | 同左 + 統一 ABI | wheel が sm_120 PTX 含むので動作は同等、 だが「forward-compat に依存しない integrity」 が得られる |
| Ada 6000 動作 | 動く | 動く | 同左 |
| T4 動作 | 動く | 動く | 同左 |
| host driver 要件 | R570+ | R570+ | image 側は変わらない |
| CUDA runtime ABI | wheel bundle 12.8 が image 12.6 上で混在 | **統一 12.8** | nsys / nvprof / trace tool が version mismatch なく動作 |
| Trivy CVE | 12.6 系 (古い CVE 残留可能性) | 12.8 系 (新 base、 PR 時点で最新の CVE 修正反映) | 中立～僅か改善 |
| Ubuntu EOL | 22.04 (2027) | **24.04 (2029)** | OS 寿命延長 |
| 学習速度 (新 GPU) | wheel bundle cuDNN 9.5 で性能 95%+ 取れる | 同左 + nsys/profiling 精度が同 toolchain で揃う | 実測 0-2% (誤差) |

**結論:** 学習サーバー新 GPU 移行 (T4/Ada 6000/RTX 5090) と Docker 統一を同時に進めるため、 base image bump も **Phase 3 にセットで含める**。 別 PR 分離は管理コストが見合わない (PR 数増 vs revert 単位の合理性のトレードオフで、 統一化の方が今回は優位)。

### 推奨アクション (Fully-aligned 戦略、 最終版)

| 優先度 | アクション | 恩恵 | Issue #527 への組み込み |
|---|---|---|---|
| **必須** | torch wheel cu121 → cu128 | RTX 5090 起動可能、 Ada 6000 で TF32/BF16/FA2 解禁 | **Phase 3 セット** |
| **必須** | torch 2.2.1 → 2.11.0 | Blackwell 公式対応 (sm_120) + Triton 3.x | **Phase 3 セット** |
| **必須** | base image `nvidia/cuda:12.6.3-...-ubuntu22.04` → **`12.8.x-...-ubuntu24.04`** | Fully-aligned、 OS EOL 延長、 trace tool 整合性 | **Phase 3 セット (Fully-aligned 戦略)** |
| **必須** | Python install: apt 3.11 → **deadsnakes PPA 3.13** | Ubuntu 24.04 でも 3.13 を統一供給 | **Phase 3 セット** |
| **必須** | distroless final: `python3-debian12` → **`python3-debian13`** | 全 image で Python 3.13 統一 | **Phase 2 セット** |
| **推奨** | `torch.backends.cuda.matmul.allow_tf32 = True` を default に | Ada/Blackwell で 1.3-1.5x | **Phase 4 で同時設定** (1 行追加、 sm_75/T4 では noop) |
| **推奨** | `--precision bf16-mixed` を training-guide で新メイン候補に | Ada/Blackwell で FP16-mixed より stable + 同等速度 | **Phase 4 で training-guide 更新** |
| **任意** | FP8 / transformer_engine 統合 | Ada/Blackwell で +30-50% | 別 issue 評価 (architecture 適用範囲 + transformer_engine library 検証) |
| **削除** | "V100 では `--precision 16-mixed` 避ける" 注意書き | V100 不使用なので不要 | training-guide / CLAUDE.md から段階削除 (Phase 4) |

### CLAUDE.md / training-guide の更新事項

新 GPU 前提に揃えるドキュメント変更:

| ファイル | 行 | 現状 | 更新 |
|---|---|---|---|
| `CLAUDE.md` | 125 | "V100 では `--no-wavlm` 推奨" | "T4 では `--no-wavlm` 推奨 (VRAM 16GB の制約)、 Ada 6000 / RTX 5090 では WavLM 利用可" |
| `CLAUDE.md` | 312 | "学習速度が遅い (V100) ..." トラブルシューティング | "学習速度が遅い (T4) ..." に置換、 Ada/Blackwell では別の対処 |
| `docs/guides/training/training-guide.md` | 258, 282 | "V100 では `--precision 16-mixed` 避ける" | 削除、 もしくは「過去 V100 環境では...」 注記 |
| `docs/guides/training/training-guide.md` | 264 | "24GB vRAM (RTX 3090/4090)" 例 | "48GB vRAM (Ada 6000) / 32GB (RTX 5090)" を追加 |
| `docs/guides/training/training-guide.md` | 266 | "On V100 16GB, --batch-size 20" | "On Ada 6000 48GB, --batch-size 32-64" 等を追加 |
| `docs/guides/training/wavlm-guide.md` | 57 | "V100 では `--precision 16-mixed` は backward が極端に遅い" | 削除、 Ada/Blackwell では bf16-mixed 推奨に |

### Phase 進化の経緯 (V100 → 新 GPU → Fully-aligned 統一)

Phase 3 / 4 のスコープは新 GPU 移行と Docker 統一方針確定で 3 回進化した:

**第 1 版** (V100 想定、 wheel-only):
- python 3.11 → 3.13
- torch 2.2.1+cu121 → 2.11.0+cu128
- base image は据置 (forward-compat 戦略)
- 性能改善 5-12% 期待

**第 2 版** (新 GPU 前提、 wheel-only):
- python 3.11 → 3.13
- torch 2.2.1+cu121 → 2.11.0+cu128 (**RTX 5090 起動の必須条件**)
- base image は据置
- TF32 enable + bf16-mixed 推奨を追加
- 性能改善 **3-10x 期待** (V100 比、 Ada 6000 / RTX 5090 想定)

**第 3 版 (現在、 Fully-aligned 統一)**:
- python 3.11 → 3.13 + **base image を nvidia/cuda 12.6.3 → 12.8.x へ bump**
- Ubuntu 22.04 → 24.04 (EOL 延長)
- torch 2.2.1+cu121 → 2.11.0+cu128
- distroless final も debian12 → debian13 で Python 3.13 統一
- Phase 3 は「CUDA Docker base 統一」、 Phase 4 は「新 GPU 学習最適化」 に分割
- forward-compat 依存を解消、 trace tool / Trivy / OS 寿命の整合性が揃う

PR title は `feat(docker)` 系 (Phase 3) + `feat(training)` 系 (Phase 4) を分けるか、
統合して 1 PR `feat(infra): unify Docker to CUDA 12.8 + Python 3.13 + new GPU` も可。

## 懸念事項 (掘り下げ調査結果)

Phase 計画前に潰すべき個別ブロッカー。

### C1. monotonic_align/setup.py が `distutils` を import している (中リスク)

```python
# src/python/piper_train/vits/monotonic_align/setup.py:1
from distutils.core import setup
```

- `distutils` は **Python 3.12 で stdlib から削除**された (PEP 632)。
- 3.13 でも当然存在しない。
- ただし `setuptools>=60` がインストールされていると `setuptools._distutils` shim を `sys.modules["distutils"]` に注入するため、 setuptools が先に import されていれば動く。
- CI (`.github/workflows/python-tests.yml:101`) はこの shim 経由で 3.13 でも green になっている (fragile)。
- **対応:** `from setuptools import setup` に書換 (1 行)。 別 PR でも本 Phase でもよい。 ruff `S` 系の追加 ignore 不要。

### C2. distroless final image の Python バージョン (中リスク)

| Image | 現状の Python | 切替先 |
|---|---|---|
| `gcr.io/distroless/python3-debian12` | 3.11 (Debian Bookworm 既定) | `gcr.io/distroless/python3-debian13` (Trixie) で 3.13 |
| `python:3.11-slim-bookworm` builder | 3.11 | `python:3.13-slim-trixie` builder (final と Debian release を揃える) |

- builder と final の Debian release が一致していないと glibc ABI が割れて `onnxruntime_pybind11_state.so` が import に失敗する (PR #523 で確認済の事故パターン、 ドキュメント `CHANGELOG.md` line 36 にも経緯あり)。
- Phase 2 では **builder = `python:3.13-slim-trixie`、 final = `distroless/python3-debian13`** を 1 セットで切替必須。
- 内部パスも `/usr/local/lib/python3.11` → `/usr/local/lib/python3.13` に書換 (6 箇所 / image)。

### C3. CUDA Docker (Ubuntu) の python3.13 提供 (中リスク、 方針確定)

- `nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04` の Ubuntu 22.04 (Jammy) は **apt で python3.10/3.11 まで**提供。 python3.13 は無い。
- Fully-aligned 戦略確定 (2026-05-21) により、 **`nvidia/cuda:12.8.x-cudnn-runtime-ubuntu24.04` + deadsnakes PPA** で python3.13 を入れる方針:

```dockerfile
FROM nvidia/cuda:12.8.x-cudnn-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.13 \
        python3.13-dev \
        python3.13-venv \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.13 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1 \
    && rm -rf /var/lib/apt/lists/*
```

- deadsnakes PPA は CPython core dev maintained で信頼性高、 Ubuntu 公式と同等の品質。
- Ubuntu 24.04 (Noble) は EOL 2029、 OS 寿命延長と CUDA 12.8 + Python 3.13 を同時に揃える。
- glibc 2.35 (Jammy) → 2.39 (Noble) の bump があるため、 wheel ABI 互換性は build 時に確認 (onnxruntime / pyopenjtalk-plus の manylinux_2_28 wheel が動作)。

### C4. `runtime-parity-deep.yml` の dump-python 3.11 pin (低リスク、 検証あり)

- `compare` job のコメント (line 295-298) が「Match dump-python (3.11) so scripts/audio_parity.py imports the same numpy / scipy ABI」 と書いている。
- 実際の `scripts/audio_parity.py` は **stdlib `wave` モジュール**で PCM16 を読み、 numpy/scipy は optional (line 17 の docstring に明記)。
- つまり dump-python と compare の Python version を揃える必要は本質的にはない (両方とも 3.13 でも、 dump-python だけ 3.13 でも問題なし)。
- **対応:** dump-python と compare を **両方 3.13 に揃える** で OK。 line 295-298 のコメントは「Match dump-python (3.13)」 に書き換え。

### C5. piper-phonemize 1.1.0 と Windows wheel build (低リスク、 据置)

- `build-phonemize-wheels.yml` の Python matrix が `["3.11", "3.12"]` のまま (line 36, 119)。 cp313 wheel を作っていないので、 ここは 3.13 にしない。
- root `pyproject.toml` line 51 の marker (`python_version < '3.13'`) で 3.13 環境では preprocess extra が skip されるので整合済み。
- **対応:** 据置。 piper-phonemize 自体を upstream の新版に bump するのは別 issue。

### C6. PyPI distribute 用 `wheel` build の cp313 タグ (低リスク)

- `src/python_run/pyproject.toml` (PyPI `piper-plus`) は **pure-python wheel**。 ABI tag は `py3-none-any` で cp 固定なし。
- classifiers に既に `3.13` を列挙済 (line 45)。 3.13 でも sdist + universal wheel で問題なし。

### C7. tarfile.extractall に filter= 未指定 (低リスク、 既知)

- `src/piper_phonemize_bundled/build_dependencies.py:65` 等で `t.extractall(extract_to)` を `filter=` なしで呼んでいる。
- Python 3.12+ で `DeprecationWarning`、 3.14 で default `filter="data"` 化予定。
- 3.13 でも warning が出るが動く。 Issue #527 のスコープ外として **据置**。

### C8. PyPI metadata の email (Issue #527 とは別件、 参考)

- `src/python_run/pyproject.toml:35` の `authors` email は古い (memory `user_email_correction.md` 参照)。
- Issue #527 と無関係なので本対応に含めない。 別 PR で修正推奨。

## 推奨アプローチ (Fully-aligned 統一版)

リスクと工数で **5 段階に分割** することを推奨 (Phase 0-4)。

### Phase 0: distutils → setuptools 書換 (前提)

対象:
- `src/python/piper_train/vits/monotonic_align/setup.py` の `from distutils.core import setup` → `from setuptools import setup` (C1)

リスク: 極低 (setuptools shim 経由で既に動いている挙動を明示化するだけ、 ロールバック容易)
工数: 5 分

### Phase 1: 低リスク CI / docs / CPU Docker (小 PR, 1-2 時間)

対象:
- ドキュメント (`CONTRIBUTING.md` / `README*.md` / `docs/**` / `QA-RELEASE-CHECKLIST.md` line 66, 453)
- 軽量 CI workflow (`codespell.yml` / `sbom.yml` / `python-lint.yml` / `pre-commit.yml` 等の lint/audit 系)
- `docker/python-inference/Dockerfile.cpu` (`python:3.11-slim-bookworm` → `python:3.13-slim-trixie`)
- `runtime-parity-deep.yml` dump-python + compare の 3.11 → 3.13 (C4)

リスク: 低 (wheels は全て揃っている)
ロールバック: 容易 (個別 workflow)

### Phase 2: distroless Docker 統一 (中 PR, 半日)

対象 (distroless × 2):
- `docker/python-inference/Dockerfile.cpu.distroless`
  - builder: `python:3.11-slim-bookworm` → **`python:3.13-slim-trixie`**
  - final: `gcr.io/distroless/python3-debian12` → **`gcr.io/distroless/python3-debian13`**
  - 内部パス: `/usr/local/lib/python3.11` → `/usr/local/lib/python3.13` (6 箇所書換)
- `docker/webui/Dockerfile.distroless` — 同パターン
- Trivy CVE scan diff 確認 (`.github/workflows/docker-build.yml`)

備考:
- builder と final の Debian release を揃える必要あり (glibc ABI、 PR #523 の事故パターン)
- `python:3.13-slim-trixie` = Debian 13、 `distroless/python3-debian13` = Debian 13 で整合

リスク: 中 (image レイヤ構造 + Debian 12 → 13 切替)
要検証:
- distroless/python3-debian13 が onnxruntime / soundfile を import できるか smoke test
- Wyoming smoke (`.github/workflows/wyoming-smoke.yml`) が green

### Phase 3: CUDA Docker base image 統一 (中-大 PR, 1 日)

> **方針確定 (2026-05-21):** base image を 12.6.3 据置 (forward-compat 戦略) ではなく、 **CUDA 12.8 + Ubuntu 24.04 + deadsnakes Python 3.13 で fully-aligned 戦略** に切替。 wheel cu128 と image CUDA toolkit を同 major 揃えにする。

対象 (推論 image):
- `docker/python-inference/Dockerfile`:
  - base: `nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04` → **`nvidia/cuda:12.8.x-cudnn-runtime-ubuntu24.04`**
  - Python install: `apt install python3.11` → deadsnakes PPA 経由で **`python3.13 python3.13-dev python3.13-venv`**
  - update-alternatives で `/usr/bin/python` → `/usr/bin/python3.13` symlink

対象 (学習 image、 Phase 4 と組み合わせ可):
- `docker/python-train/Dockerfile`:
  - base: `nvidia/cuda:12.6.3-cudnn-{devel,runtime}-ubuntu22.04` → **`nvidia/cuda:12.8.x-cudnn-{devel,runtime}-ubuntu24.04`**
  - Python install: 同上 (deadsnakes 3.13)
  - torch: `==2.2.1+cu121` → **`==2.11.0+cu128`** (uv.lock canonical と整合)
  - `--extra-index-url`: `download.pytorch.org/whl/cu121` → `download.pytorch.org/whl/cu128`

備考:
- Ubuntu 22.04 (Jammy, EOL 2027) → 24.04 (Noble, EOL 2029) で OS 寿命延長
- deadsnakes PPA は CPython core dev maintained で信頼性高
- CUDA 12.8 + cuDNN 9 が wheel cu128 と同 major 揃え、 forward-compat 依存解消

リスク: 中-大
- Ubuntu 22.04 → 24.04 で glibc 2.35 → 2.39、 onnxruntime / pyopenjtalk-plus の wheel ABI 確認必要
- nvidia/cuda 12.8 image の Trivy CVE 状況確認 (新 base で新 CVE 出現可能性)
- host driver R570+ 前提 (新 GPU 環境では問題ないが学習サーバー側で確認)

要検証:
- `docker/python-inference/Dockerfile` で onnxruntime-gpu import + 6lang base 推論 smoke
- Trivy CVE diff (新 base → new HIGH/CRITICAL なし)
- host driver R570+ の確認 (T4/Ada 6000/RTX 5090 ホスト)

### Phase 4: 新 GPU 学習最適化 (大 PR, 1-2 日)

> **Phase 3 と組み合わせ可能** だが、 学習側の reproducibility 検証が重いため別 PR として分離も可。

対象 (Phase 3 が完了している前提):
- `src/python/piper_train/__main__.py`: `torch.backends.cuda.matmul.allow_tf32 = True` を `torch.backends.cudnn.benchmark = True` の隣に追加 (1 行、 sm_80+ で TF32 解禁、 sm_75/T4 では noop)
- `docs/guides/training/training-guide.md`: V100 言及を新 GPU 前提に置換
  - 「V100 では `--precision 16-mixed` 避ける」 → 削除 or 過去注記化
  - VRAM 例に Ada 6000 48GB / RTX 5090 32GB / T4 16GB を追加
  - Ada/Blackwell では `--precision bf16-mixed` を新メイン候補として記載
- `docs/guides/training/wavlm-guide.md` line 57: V100 注意書きを削除
- `CLAUDE.md`:
  - line 125: WavLM の V100 注記を T4 注記に
  - line 312: トラブルシューティング表の V100 行を T4 / Ada / RTX 5090 別に再構成
  - Template A/B の `--precision` default を bf16-mixed 推奨候補に格上げ (32-true は legacy V100 互換用と注記)

リスク: 高
- TF32 enable は数値精度に影響 (matmul で 10-bit mantissa 化)
- bf16-mixed への移行は学習結果に影響 (FP16-mixed と rounding pattern が異なる)
- training-guide / CLAUDE.md の trainer template 変更は学習ジョブの canonical 仕様変更

要検証 (新 GPU 実機):
- **Ada 6000 実機**で Template B FT 1 epoch smoke、 loss / metric range が canonical 範囲
- **RTX 5090 実機**で sm_120 起動確認 + 学習速度測定 (期待 5-10x vs V100)
- **T4 実機**で推論 only smoke
- TF32 ON/OFF で 100 step deterministic 比較、 validation loss が許容範囲
- WandB ログの metric range が同等 (kl_loss / mel_loss / duration_loss)
- ONNX export 出力が audio_parity Tier 4 (SNR ≥ 30dB) を満たす

### Phase 5 (任意): mypy / ruff target-version

`[tool.mypy] python_version` と `[tool.ruff] target-version` を `"3.11"` → `"3.13"` に上げると `match` 文 / `Self` 型 / `PEP 695 generics` が解禁される。 ただし **3.11 サポートを切ることになる**ため、 `requires-python` 据置方針と矛盾するため **見送り推奨**。

## Phase 依存関係

```
Phase 0 (distutils → setuptools)
   │  前提: monotonic_align build を 3.13 で fragile shim から解放
   ▼
Phase 1 (docs + 軽量 CI + CPU Docker)
   │  並列実行可: Phase 2 と独立、 ただし PR review 衝突を避けるため Phase 0 → 1 順
   ▼
Phase 2 (distroless × 2 を debian13 で統一)
   │  並列実行可: Phase 3 と独立 (CPU image のみ touch)
   ▼
Phase 3 (CUDA Docker base 統一: 12.6 → 12.8 + Ubuntu 24.04 + deadsnakes 3.13)
   │  必須前提: host driver R570+ 確認 (新 GPU 環境では問題なし)
   │  並列実行可: Phase 4 と独立 (Docker のみ touch、 piper_train コード変更なし)
   ▼
Phase 4 (新 GPU 学習最適化: TF32 + bf16-mixed + docs 更新)
   │  必須前提: Phase 3 完了 (Phase 3 の Docker image で新 GPU 学習可能)
   │  実機検証: Ada 6000 / RTX 5090 で 1 epoch smoke
   ▼
(任意) Phase 5: mypy/ruff target_version — 見送り推奨
```

Phase 1 / 2 は並列でも可だが、 PR review 衝突を避けるため順次推奨。 Phase 3 と Phase 4 は touch するファイル群が異なる (Docker vs piper_train code) ため並列実行可能。

## Phase 別 diff サンプル

実装時の参考。 各 Phase の代表的な変更を before / after で示す。

### Phase 0 — distutils → setuptools

```diff
--- a/src/python/piper_train/vits/monotonic_align/setup.py
+++ b/src/python/piper_train/vits/monotonic_align/setup.py
@@ -1,4 +1,4 @@
-from distutils.core import setup
+from setuptools import setup
 from pathlib import Path

 import numpy
```

### Phase 1 — CPU Docker (Dockerfile.cpu)

```diff
--- a/docker/python-inference/Dockerfile.cpu
+++ b/docker/python-inference/Dockerfile.cpu
@@ -32,7 +32,7 @@
-# Python 3.11 stays as-is — pyproject.toml allows 3.11+; bumping the
-# interpreter is out of scope for a CVE-cleanup PR.
-FROM python:3.11-slim-bookworm
+# Python 3.13 default — see docs/reference/python-313/README.md
+# (Issue #527 Phase 1).
+FROM python:3.13-slim-trixie
```

### Phase 1 — workflow `python-lint.yml` (代表例)

```diff
--- a/.github/workflows/python-lint.yml
+++ b/.github/workflows/python-lint.yml
@@ -19,7 +19,7 @@ jobs:
     strategy:
       matrix:
-        python-version: ['3.11']
+        python-version: ['3.13']
```

(他 21 個の workflow も同パターン、 一覧は「影響範囲の内訳」 B 節参照)

### Phase 2 — distroless (Dockerfile.cpu.distroless)

```diff
--- a/docker/python-inference/Dockerfile.cpu.distroless
+++ b/docker/python-inference/Dockerfile.cpu.distroless
@@ -47,7 +47,7 @@
-FROM python:3.11-slim-bookworm AS builder
+FROM python:3.13-slim-trixie AS builder
@@ -134,12 +134,12 @@
-FROM gcr.io/distroless/python3-debian12
+FROM gcr.io/distroless/python3-debian13
@@ -160,9 +160,9 @@
-COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
+COPY --from=builder /usr/local/lib/python3.13 /usr/local/lib/python3.13
@@ -166,7 +166,7 @@
-ENV PYTHONPATH=/usr/local/lib/python3.11/site-packages
+ENV PYTHONPATH=/usr/local/lib/python3.13/site-packages
```

### Phase 3 — CUDA inference Docker (Dockerfile)

```diff
--- a/docker/python-inference/Dockerfile
+++ b/docker/python-inference/Dockerfile
@@ -8,9 +8,9 @@
-FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04
+FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

 ENV PYTHONUNBUFFERED=1
 ENV DEBIAN_FRONTEND=noninteractive

-# Install Python 3.11 and system dependencies
+# Install Python 3.13 via deadsnakes PPA (Ubuntu 24.04 apt default is 3.12)
 RUN apt-get update && apt-get install -y --no-install-recommends \
+    software-properties-common \
+    && add-apt-repository -y ppa:deadsnakes/ppa \
+    && apt-get update && apt-get install -y --no-install-recommends \
-    python3.11 \
-    python3.11-venv \
+    python3.13 \
+    python3.13-venv \
+    python3.13-dev \
     python3-pip \
     libsndfile1 \
-    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
-    && ln -sf /usr/bin/python3.11 /usr/bin/python \
+    && update-alternatives --install /usr/bin/python python /usr/bin/python3.13 1 \
+    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1 \
     && rm -rf /var/lib/apt/lists/*
```

### Phase 3 — 学習 Docker (Dockerfile)

```diff
--- a/docker/python-train/Dockerfile
+++ b/docker/python-train/Dockerfile
@@ -19,7 +19,7 @@
-FROM nvidia/cuda:12.6.3-cudnn-devel-ubuntu22.04 AS builder
+FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04 AS builder
@@ -43,11 +43,18 @@
+# Install Python 3.13 via deadsnakes PPA
 RUN apt-get update && apt-get install -y --no-install-recommends \
+    software-properties-common \
+    && add-apt-repository -y ppa:deadsnakes/ppa \
+    && apt-get update && apt-get install -y --no-install-recommends \
     build-essential \
     cmake \
     git \
     wget \
     curl \
-    python3.11 \
-    python3.11-dev \
-    python3.11-venv \
+    python3.13 \
+    python3.13-dev \
+    python3.13-venv \
@@ -71,5 +78,5 @@
-# PyTorch (CUDA 12.1)
+# PyTorch (CUDA 12.8, aligned with base image and uv.lock canonical)
 RUN uv pip install \
-    --extra-index-url https://download.pytorch.org/whl/cu121 \
-    "torch==2.2.1+cu121" "torchaudio==2.2.1+cu121" "torchvision==0.17.1+cu121"
+    --extra-index-url https://download.pytorch.org/whl/cu128 \
+    "torch==2.11.0+cu128" "torchaudio==2.11.0+cu128"
@@ -94,7 +101,7 @@
-FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04
+FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04
```

> **注:** `torchvision==0.17.1+cu121` は piper-train が使っていないので削除可。 削除する場合 commit 内で明示。

### Phase 4 — TF32 enable

```diff
--- a/src/python/piper_train/__main__.py
+++ b/src/python/piper_train/__main__.py
@@ -458,7 +458,11 @@ def main():
     ...
     torch.backends.cudnn.benchmark = True
+    # TF32 enable for Ampere+ (sm_80+: A100/Ada 6000/RTX 5090). On
+    # sm_75 (T4) and older, this setting is a noop. Speeds up matmul by
+    # ~1.3-1.5x with negligible quality impact for TTS workloads.
+    torch.backends.cuda.matmul.allow_tf32 = True
```

### Phase 4 — CLAUDE.md (V100 → 新 GPU)

```diff
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -122,7 +122,7 @@
-- **WavLM Discriminator** ... V100 では `--no-wavlm` 推奨。
+- **WavLM Discriminator** ... T4 (VRAM 16GB) では `--no-wavlm` 推奨。 Ada 6000 / RTX 5090 では WavLM 利用可。
@@ -310,7 +310,7 @@
-| 学習速度が遅い (V100) | `--precision 32-true` (FP16-mixed は backward 29-40s に劣化) / ...
+| 学習速度が遅い (T4) | VRAM 制約 (16GB) を確認、 batch_size を 8-12 に絞る / Ada 6000 / RTX 5090 への移行検討 |
+| 学習速度が遅い (Ada 6000 / RTX 5090) | `--precision bf16-mixed` 推奨 / `--compile` で torch.compile / TF32 enabled 確認 |
```

## ロールバック手順

各 Phase で問題が発覚した場合の戻し方:

| Phase | ロールバック方法 | データロス可能性 |
|---|---|---|
| 0 | `git revert <commit>` のみで完了 (1 commit、 setup.py の 1 行) | なし |
| 1 | `git revert <commit>` で workflow / Dockerfile.cpu / docs を一括戻し | なし |
| 2 | `git revert <commit>` で distroless × 2 を debian12 に戻す。 既に push 済 image がある場合は registry の旧 tag を再 promote | image registry の整合性確認のみ |
| 3 | `git revert <commit>` で CUDA Docker を 12.6 + Python 3.11 に戻す。 学習途中の場合は新 image で生成した ckpt が旧 image で読めるか確認 (基本互換、 ただし PyTorch 2.11 → 2.2 ckpt の forward compat は要検証) | **学習 ckpt の互換性確認必須** |
| 4 | `git revert <commit>` で `__main__.py` の TF32 行を削除、 CLAUDE.md / training-guide の V100 言及を復元。 既存学習ジョブは TF32 ありで生成された state_dict なので、 ロールバック後の TF32 OFF 学習で resume すると loss curve が変わる可能性 | **学習 reproducibility 影響あり** |

Phase 3 / 4 のロールバック時は:
1. 新 image で生成した ckpt を別 backup
2. 旧 image (12.6.3 + Python 3.11) を再 build して resume 確認
3. validation loss が canonical 範囲内なら継続、 外れたら新 image での再学習決定

## PR テンプレート

各 Phase の PR 作成時に使うベース。 詳細は `pull_request_template.md` の section 構造に従う。

### Phase 0 PR

```
Title: chore(build): replace distutils.core with setuptools in monotonic_align

## Summary
- src/python/piper_train/vits/monotonic_align/setup.py の `from distutils.core import setup` を `from setuptools import setup` に書換
- distutils は Python 3.12 で stdlib から削除済 (PEP 632)、 setuptools shim 経由で偶然動いていた状態を明示化
- Issue #527 Phase 0 (Python 3.13 移行の前提整理)

## Type
- [x] chore (build/dep)

## Risk Level
- [x] Low

## Affected Components
- [x] Python (training)

## Test Plan
- [ ] python-tests.yml matrix (3.11/3.12/3.13) で monotonic_align build が green
- [ ] `python setup.py build_ext --inplace` がローカルで動作
```

### Phase 3 PR (例)

```
Title: feat(docker): unify python-train/inference to CUDA 12.8 + Ubuntu 24.04 + Python 3.13

## Summary
- nvidia/cuda 12.6.3-ubuntu22.04 → 12.8.1-ubuntu24.04 (OS EOL 2027→2029、 fully-aligned 戦略)
- Python 3.11 (apt) → 3.13 (deadsnakes PPA)
- torch 2.2.1+cu121 → 2.11.0+cu128 (RTX 5090 sm_120 起動条件)
- Issue #527 Phase 3 (詳細: docs/reference/python-313/README.md)

## Type
- [x] feat (infrastructure)

## Risk Level
- [x] High (CUDA / Ubuntu / Python の triple bump)

## Affected Components
- [x] Docker (training)
- [x] Docker (inference)

## Test Plan
- [ ] docker build (python-train + python-inference) が success
- [ ] Trivy CVE diff: new HIGH/CRITICAL なし
- [ ] Ada 6000 実機で `python -c "import torch; torch.cuda.is_available()"` true
- [ ] RTX 5090 実機で sm_120 起動確認 (`torch.cuda.get_device_capability()` (12, 0))
- [ ] T4 実機で onnxruntime-gpu CPUExecutionProvider + CUDAExecutionProvider 認識
- [ ] host driver R570+ を学習サーバー / 推論サーバー全台で確認
```

## 非対応事項

- `requires-python = ">=3.11"` の下限引き上げ → Issue #527 のスコープ外
- `[tool.ruff] target-version = "py311"` の引き上げ → 同上
- `python-tests.yml` matrix `["3.11", "3.12", "3.13"]` の削減 → memory `feedback_ci_matrix_no_reduction.md` (OSS public は CI minute 無制限、 網羅性優先) に従い据置
- `build-phonemize-wheels.yml` の cp313 build → piper-phonemize 1.1.0 が cp313 source build 未対応の問題が解消するまで保留
- `docker/cpp-dev/Dockerfile` の `python3.12` (dev tool 用、 動けば何でも) → Phase 統一外、 別 commit で個別判断
- `docker/cpp-inference/Dockerfile.distroless` の `debian:12-slim` / `distroless/cc-debian12` → Python 利用なし、 必要なら別 PR で debian13 化

## 検証チェックリスト

### 全 Phase 共通 (CI gate)

| ゲート | 対象 | 期待 |
|---|---|---|
| `python-tests.yml` matrix 3.13 ジョブ | ubuntu / windows / macos × 3.13 | 全 PASS |
| `pre-commit run --all-files` | ruff / format / 50+ gate | clean |
| `docker-build.yml` Trivy scan | distributable image 群 | new HIGH/CRITICAL なし |
| `runtime-parity-deep.yml` | 6 runtime audio parity | Tier 1-4 PASS |
| `wyoming-smoke.yml` | Home Assistant 連携 | smoke green |
| `model-quality-gate.yml` | MOS / RTF 退行 | baseline ±2% 以内 |

### Phase 2 (distroless 統一)

| ゲート | 対象 | 期待 |
|---|---|---|
| distroless/python3-debian13 import smoke | onnxruntime / soundfile / pyopenjtalk-plus が import 可能 | 起動 + import 成功 |
| 内部パス書換 | `/usr/local/lib/python3.13/site-packages` で wheel 配置確認 | dist-info が正しく置かれる |
| Trivy diff | debian12 → debian13 で新 HIGH/CRITICAL なし | green |

### Phase 3 (CUDA Docker base 統一)

| ゲート | 対象 | 期待 |
|---|---|---|
| Ubuntu 24.04 + deadsnakes 3.13 + CUDA 12.8 build | docker build 成功 | exit 0 |
| onnxruntime-gpu import | `python3.13 -c "import onnxruntime as ort; ort.get_available_providers()"` | `['CUDAExecutionProvider', 'CPUExecutionProvider']` |
| Trivy CVE (CUDA image) | nvidia/cuda:12.6.3 → 12.8.x で new HIGH/CRITICAL なし | green |
| host driver R570+ 確認 | 学習サーバー / 推論サーバー全台で nvidia-smi → driver >= 570.x | 全台 OK |

### Phase 4 (新 GPU 学習最適化、 実機検証)

| ゲート | 対象 | 期待 |
|---|---|---|
| Ada 6000 smoke | Template B 1 epoch FT | loss / metric range が canonical 範囲、 ONNX export → audio_parity Tier 4 PASS |
| RTX 5090 smoke | 同上 | sm_120 起動確認 + 学習速度測定 (期待 5-10x vs V100) |
| T4 smoke (推論) | `docker/python-inference/Dockerfile` で 6lang base 推論 | 起動 + RTF 範囲内 |
| TF32 ON/OFF 比較 | Ada 6000 で 100 step | validation loss 差分が許容範囲、 audio 出力が perceptually 同等 |
| bf16-mixed 切替検証 | Ada / RTX 5090 で FP16-mixed → bf16-mixed 100 step | loss curve が canonical 範囲、 audio Tier 4 PASS |

## 次アクション提案

1. 本ドキュメントを Issue #527 にコメントとして貼り、 Phase 分割 (0-4) の方針承認を求める
2. 承認後 Phase 0 (distutils 書換) → 1 → 2 → 3 → 4 の順で個別 PR (`/create-pr` skill 経由)
3. 各 Phase で `python-tests.yml` matrix の 3.13 ジョブが green であることを必須化
4. **Phase 3 (CUDA Docker base 統一)** は host driver R570+ 確認後に merge
5. **Phase 4 (新 GPU 学習最適化)** は以下を merge 前必須化:
   - Ada 6000 実機で Template B 1 epoch smoke
   - RTX 5090 実機で sm_120 起動確認 + 学習速度測定
   - T4 で推論 only smoke (`docker/python-inference`)
   - TF32 enable 前後の validation loss 比較
   - bf16-mixed 切替の loss curve 検証

---

調査日: 2026-05-21
調査範囲: dev branch HEAD (4e7a879e、 worktree `docs/issue-527-python-313-migration` b84f3681)
更新履歴:
- 2026-05-21 初版 (Phase 分割 + wheel-only 戦略 + V100 想定)
- 2026-05-21 懸念事項 C1-C8 追加
- 2026-05-21 library bump 評価追加
- 2026-05-21 CUDA バージョン詳細追加
- 2026-05-21 CUDA 12.8 最適化恩恵分析 (V100 想定)
- 2026-05-21 新 GPU 移行 (T4/Ada 6000/RTX 5090) で評価全面改訂
- 2026-05-21 dedicated folder 化 (`docs/reference/python-313/`)
- 2026-05-21 **Fully-aligned 戦略へ転換** (CUDA 12.8 base image + Ubuntu 24.04 + Python 3.13 統一)
