# Issue #527 マイルストーン定義書

> Phase 0-4 を**ステークホルダー視点のマイルストーン (M1-M5)** として束ねた進捗管理ドキュメント。 GitHub の milestone 機能には登録せず、 本ドキュメント内でのみ管理する (PR 数を絞るため)。

文書ID: PP-MS-527
版: 1.0
適用: dev branch (Issue #527 完了まで)
最終更新: 2026-05-22

---

## マイルストーンと Phase の対応

```
M1: 基盤整備 + 軽量切替                  Phase 0 + Phase 1
   ▼
M2: 非 GPU Docker 統一                   Phase 2
   ▼
M3: GPU Docker 統一 (CUDA 12.8)          Phase 3
   ▼
M4: 新 GPU 学習最適化                     Phase 4
   ▼
M5: リリース + clean-up                  (Phase 外)
```

各マイルストーンは **1 つ以上の PR** にまとめて merge する。 M3 / M4 は実機検証ゲートを持つ。

---

## マイルストーン一覧 (サマリ)

| ID | タイトル | 含む Phase | 期間目安 | 主要 Deliverable | 状態 |
|---|---|---|---|---|---|
| **M1** | 基盤整備 + 軽量切替 | Phase 0 + 1 | 0.5 日 | distutils 修正 + docs/CI/CPU Docker を 3.13 へ | 未着手 |
| **M2** | 非 GPU Docker 統一 | Phase 2 | 0.5 日 | distroless × 2 を debian13 + python 3.13 へ | 未着手 |
| **M3** | GPU Docker 統一 | Phase 3 | 1 日 + 検証 | python-inference/train を CUDA 12.8 + Ubuntu 24.04 + Python 3.13 へ | 未着手 |
| **M4** | 新 GPU 学習最適化 | Phase 4 | 1-2 日 + 実機検証 | TF32 enable + 新 GPU 動作確認 + docs 更新 | 未着手 |
| **M5** | リリース + clean-up | Phase 外 | 0.5 日 | CHANGELOG + version bump + Docker image tag promote | 未着手 |

---

## M1: 基盤整備 + 軽量切替

### 目的

リポジトリ全体で **低リスクの 3.13 化を完了**し、 後続マイルストーンの足場を整える。 CI matrix で 3.13 ジョブが安定して green になる状態を確立する。

### 含む Phase

- **Phase 0**: `distutils` → `setuptools` 書換 (1 行)
- **Phase 1**: ドキュメント + 軽量 CI workflow + CPU Docker (`Dockerfile.cpu`) を 3.13 へ

### Deliverables

| カテゴリ | 内容 | 件数 |
|---|---|---|
| ソースコード | `monotonic_align/setup.py` 1 行書換 | 1 |
| Docker | `docker/python-inference/Dockerfile.cpu` を `python:3.13-slim-trixie` へ | 1 |
| CI workflow | 軽量 workflow 11 個 (lint / audit / sbom / codeql / pre-commit / 等) を 3.13 へ | 11 |
| ドキュメント | `CONTRIBUTING.md` / `README*.md` / `docs/**` の Python version 表記更新 | ~12 |
| Library floor 統一 | `scipy / pytorch-lightning / transformers / wandb / tensorboard / fastapi / uvicorn / pytest / matplotlib / pypinyin / librosa / numba / torchmetrics / onnxscript / coverage / mypy / onnxruntime` の floor を root と member で統一 (詳細は [specifications.md 10.5.2](specifications.md#1052-a-floor-drift-解消-m1-で同時実施推奨)) | 17 library |
| Python 3.13 動作確認 | `mecab-python3` / `sudachipy` の import smoke 追加 | 2 |

PR 数: 1-3 (Phase 0 + Phase 1 + 任意で library floor 統一を別 PR にする選択肢あり)

### Entry Criteria (開始条件)

- [ ] Issue #527 の方針承認 (要求定義書 [`requirements.md`](requirements.md) の stakeholder approval)
- [ ] 要件定義書 [`specifications.md`](specifications.md) の technical review 完了
- [ ] dev branch が clean

### Exit Criteria (完了条件)

- [ ] `python-tests.yml` matrix の 3.13 ジョブが ubuntu / windows / macos で PASS
- [ ] `pre-commit run --all-files` clean
- [ ] 軽量 CI 11 workflow が 3.13 で green
- [ ] `docker build -f docker/python-inference/Dockerfile.cpu` success on amd64 + arm64
- [ ] `monotonic_align` の Cython build が 3.13 環境で success
- [ ] `grep -rE "python-version.{0,10}3\.11" .github/workflows/*.yml` の結果が 5 件以下 (matrix workflow と Phase 2/3 対象を除く)

### 依存

- なし (最初のマイルストーン)

### リスクゲート

| リスク | 判定基準 | 対応 |
|---|---|---|
| Cython monotonic_align が 3.13 で build 失敗 | `python setup.py build_ext --inplace` がローカルで通る | DF-01 で setuptools 経由動作確認済、 リスク極低 |
| 軽量 workflow の 3.13 環境で flake | 3 回連続 PASS で確定 | flake は PR コメントで quarantine 判断 |

### ステークホルダー

- リポジトリオーナー (PR review)
- CI maintainer (workflow 動作確認)

### 想定所要時間

**0.5 日 (4 時間以内)**。 ほぼ機械的な置換作業。

---

## M2: 非 GPU Docker 統一

### 目的

CPU / WebUI / distroless 系の **全 Docker image を Python 3.13 で統一**し、 PR #523 と同型の glibc ABI 整合を取る。 GPU image (M3) と独立に進められる。

### 含む Phase

- **Phase 2**: distroless × 2 (`Dockerfile.cpu.distroless` + `webui/Dockerfile.distroless`) を debian13 + Python 3.13 へ

### Deliverables

| カテゴリ | 内容 |
|---|---|
| Docker | `docker/python-inference/Dockerfile.cpu.distroless` (builder=3.13-trixie、 final=distroless/python3-debian13、 内部パス 6 箇所書換) |
| Docker | `docker/webui/Dockerfile.distroless` (同パターン) |
| CI | `docker-build.yml` の Trivy scan で diff 確認 |

PR 数: 1 (distroless × 2 を 1 PR にまとめる)

### Entry Criteria

- [ ] M1 が完了 (CI 3.13 ジョブが安定 green)
- [ ] Trivy CVE baseline (12.6 系 + Python 3.11) のスナップショット取得

### Exit Criteria

- [ ] 2 つの distroless image が docker build success
- [ ] distroless final 内で `python3 --version` が `3.13.x`
- [ ] `import onnxruntime / soundfile / pyopenjtalk-plus` smoke success
- [ ] Trivy scan: new HIGH/CRITICAL が **0 件**
- [ ] Wyoming smoke (`wyoming-smoke.yml`) が継続 green
- [ ] `docker-build.yml` の distroless ジョブが green

### 依存

- M1 完了 (CI 環境の足場)

### リスクゲート

| リスク | 判定基準 | 対応 |
|---|---|---|
| distroless final で onnxruntime が import 失敗 | smoke test FAIL | builder と final の Debian release を要確認 (両方 trixie 必須、 PR #523 の事故パターン) |
| Trivy で新 HIGH/CRITICAL 発生 | Trivy diff で件数増加 | apt upgrade 追加で対処、 別 issue 切り出しも検討 |
| Wyoming smoke regression | smoke FAIL | Wyoming Dockerfile は据置のため通常影響ないはず、 build cache invalidation で再試行 |

### ステークホルダー

- リポジトリオーナー
- 推論サービス運用者 (distroless image 利用者)

### 想定所要時間

**0.5 日**。 内部パスの書換 (12 箇所) が機械的、 ただし Trivy 確認に時間を取る。

---

## M3: GPU Docker 統一 (CUDA 12.8 + Ubuntu 24.04 + Python 3.13)

### 目的

学習・推論の **CUDA Docker image を fully-aligned 戦略**で統一。 forward-compat 依存を解消し、 RTX 5090 (Blackwell sm_120) を起動可能にする。 これが本 Issue の **技術的核心**。

### 含む Phase

- **Phase 3**: `python-train/Dockerfile` + `python-inference/Dockerfile` を `nvidia/cuda:12.8.1-cudnn-{devel,runtime}-ubuntu24.04` + deadsnakes python3.13 + torch 2.11.0+cu128 へ

### Deliverables

| カテゴリ | 内容 |
|---|---|
| Docker | `docker/python-inference/Dockerfile` (CUDA inference): base image + Python install + apt 構成 |
| Docker | `docker/python-train/Dockerfile`: 同上 + torch wheel cu121 → cu128 + torchvision 削除 |
| ドキュメント | `docker/README.md` の image base 表記更新 |
| ドキュメント | CHANGELOG に "BREAKING: Docker now uses CUDA 12.8 + Ubuntu 24.04, requires host driver R570+" を記載 |
| 検証 | host driver R570+ を学習・推論サーバー全台で確認 (運用作業) |

PR 数: 1-2 (python-train と python-inference を別 PR にしてもよい、 review 負荷次第)

### Entry Criteria

- [ ] M2 が完了 (非 GPU 系が 3.13 統一済)
- [ ] **host driver R570+ が学習・推論サーバー全台で確認済** (運用前提)
- [ ] **nvidia-container-toolkit 1.14+ が host 側で確認済**
- [ ] Ada 6000 / RTX 5090 / T4 のいずれかに smoke test 用アクセス権

### Exit Criteria

- [ ] `docker build -f docker/python-inference/Dockerfile` success on amd64
- [ ] `docker build -f docker/python-train/Dockerfile` success on amd64
- [ ] 起動して `python --version` が `3.13.x`
- [ ] `python -c "import torch; print(torch.__version__)"` が `2.11.0+cu128`
- [ ] `python -c "import torch; torch.cuda.is_available()"` が **True** (新 GPU ホスト)
- [ ] `onnxruntime-gpu` が `CUDAExecutionProvider` を認識
- [ ] Trivy scan: new HIGH/CRITICAL が **0 件**
- [ ] **Ada 6000 実機**で nvidia-smi + `torch.cuda.get_device_capability() == (8, 9)` PASS
- [ ] **RTX 5090 実機**で nvidia-smi + `torch.cuda.get_device_capability() == (12, 0)` PASS
- [ ] **T4 実機**で 6lang base 推論 smoke (WAV 生成成功)

### 依存

- M2 完了 (distroless 系の知見が CUDA Docker でも活用される)
- 運用前提 (host driver / nvidia-container-toolkit) が満たされていること

### リスクゲート (重要)

| リスク | 判定基準 | 対応 |
|---|---|---|
| Ubuntu 24.04 (glibc 2.39) で wheel ABI 不整合 | docker build 失敗 / import error | manylinux_2_28 wheel 提供確認、 pyopenjtalk-plus は wheel 不在なら source build 経路に fallback |
| nvidia/cuda:12.8.1-ubuntu24.04 image の Trivy で大量 CVE | Trivy diff で HIGH/CRITICAL > 5 件増加 | `apt upgrade` 追加、 12.8.1 patch 内の later tag (12.8.x) を選択、 もしくは 12.8.0 に下げて検証 |
| **RTX 5090 で torch.cuda.is_available() = False** | smoke FAIL | host driver R570+ 再確認、 nvidia-container-toolkit 1.14+ 再確認、 docker `--gpus all` flag 確認 |
| host driver R470 以下の運用サーバーがある | 運用前提 NG | サーバー管理者に driver bump を依頼、 完了するまで M3 merge 待ち |

### ステークホルダー

- リポジトリオーナー (PR review)
- **学習サーバー運用者** (driver bump 必要、 実機 smoke 担当)
- 推論サービス運用者 (推論 image の動作確認)
- 3rd party Docker image 利用者 (release note で migration 案内)

### 想定所要時間

**1 日 (8 時間) + 実機検証 0.5 日**。 base image 切替 + apt 再構成は機械的だが、 新 GPU 実機での起動確認に時間を取る。

---

## M4: 新 GPU 学習最適化

### 目的

新 GPU (Ada 6000 / RTX 5090) で **TF32 / bf16-mixed を解禁**し、 V100 比 3-10x の学習速度向上を実現。 関連ドキュメント (CLAUDE.md / training-guide) を新 GPU 前提に整える。

### 含む Phase

- **Phase 4**: TF32 enable + V100 言及の整理 + bf16-mixed 推奨化

### Deliverables

| カテゴリ | 内容 |
|---|---|
| ソースコード | `src/python/piper_train/__main__.py` に `torch.backends.cuda.matmul.allow_tf32 = True` を追加 (1 行) |
| ドキュメント | `CLAUDE.md` の WavLM / トラブルシューティング / Template A/B 注記 (V100 → 新 GPU) |
| ドキュメント | `docs/guides/training/training-guide.md` の precision / VRAM 例 / WavLM 推奨 |
| ドキュメント | `docs/guides/training/wavlm-guide.md` の V100 注意書き削除 |
| 検証 | Ada 6000 実機で TF32 ON/OFF 比較 + bf16 切替 1 epoch smoke |
| 検証 | RTX 5090 実機で 100 step 学習速度測定 |

PR 数: 1

### Entry Criteria

- [ ] M3 完了 (新 GPU で Docker image が動く)
- [ ] Ada 6000 実機への定常アクセス権 (学習担当)
- [ ] 6lang base ckpt が `/data/piper/output-multilingual-6lang/` で利用可能 (既存環境)

### Exit Criteria

- [ ] `__main__.py` の TF32 enable 行が main() 内、 Trainer 構築前に存在
- [ ] Ada 6000 で `torch.backends.cuda.matmul.allow_tf32 == True` 確認
- [ ] T4 / sm_75 以下で noop 動作 (warning 出ない)
- [ ] **Ada 6000 実機**で Template B 1 epoch FT 完走 (loss / metric range canonical ±10% 以内)
- [ ] **RTX 5090 実機**で同 smoke 完走
- [ ] TF32 ON/OFF deterministic 100 step 比較で validation loss 差分が許容範囲
- [ ] ONNX export 出力が `audio_parity` Tier 4 (SNR ≥ 30dB) PASS
- [ ] `CLAUDE.md` line 125 / 312 の V100 言及が新 GPU 前提に置換済
- [ ] `training-guide.md` で `bf16-mixed` が Ada/Blackwell の新メイン推奨として記載
- [ ] `model-quality-gate.yml` で MOS / RTF が baseline ±2% 以内

### 依存

- M3 完了 (新 GPU Docker image が動く)
- 6lang base ckpt + dataset へのアクセス

### リスクゲート (重要)

| リスク | 判定基準 | 対応 |
|---|---|---|
| TF32 enable で learning instability | loss curve が canonical 範囲外 | TF32 OFF flag を opt-in 化、 一旦 enable 行を削除して PR 再構成 |
| bf16-mixed で loss spike | validation loss が baseline ±10% 超 | precision を 16-mixed 据置で再評価、 別 issue で transformer_engine 検討 |
| Ada 6000 / RTX 5090 で学習速度向上が期待値未満 | V100 比 < 3x | プロファイル (`nsys`) で bottleneck 分析、 cudnn.benchmark / channels_last 等の追加最適化検討 |
| ONNX export の audio_parity Tier 4 FAIL | SNR < 30dB | export パスでの precision 影響を分析、 必要なら `--precision 32-true` を export 時のみ強制 |
| RTX 5090 (sm_120) 固有の不具合 | torch 2.11 で動作未確認の op がある | torch upstream issue 確認、 必要なら個別 op を `torch.compile` 除外 |

### ステークホルダー

- リポジトリオーナー
- **学習担当** (実機 smoke + 速度測定)
- 3rd party 学習ユーザ (training-guide 更新の周知)

### 想定所要時間

**1-2 日**。 コード変更は 1 行だが、 実機 smoke + TF32 deterministic 比較 + bf16 切替の 3 軸検証が必要。

---

## M5: リリース + clean-up

### 目的

M1-M4 の成果を **正式リリース** (PyPI / Docker / GitHub Release) として公開し、 ユーザに移行手順を周知する。

### 含む Phase

- Phase 外 (リリース運用)

### Deliverables

| カテゴリ | 内容 |
|---|---|
| バージョン | `VERSION` ファイル + 関連 pyproject.toml の version bump (例: 1.12.0 → 1.13.0 minor bump) |
| CHANGELOG | "BREAKING: default Docker now CUDA 12.8 + Ubuntu 24.04 + Python 3.13" を [Unreleased] → [1.13.0] へ移動 |
| Migration guide | `docs/migration/v1.12-to-v1.13.md` を新規作成 (要 host driver R570+、 nvidia-container-toolkit 1.14+ 等) |
| Release | `dev-create-release.yml` で v1.13.0 release tag 作成 |
| Docker image tag | `piper-plus-cpu:1.13.0` / `piper-plus-gpu:1.13.0` 等を registry に push |
| GitHub Release | release note に M3 の breaking change 警告を強調 |
| Issue close | Issue #527 をクローズ、 PR 一覧 + マイルストーン達成サマリをコメント |

PR 数: 1 (release prep PR)

### Entry Criteria

- [ ] M1〜M4 すべて完了
- [ ] `python-tests.yml` matrix 全 PASS
- [ ] `model-quality-gate.yml` で MOS / RTF baseline ±2% 以内確認
- [ ] CHANGELOG [Unreleased] に Issue #527 関連エントリが揃っている
- [ ] 実機 smoke の log / 計測値が WandB に保管されている

### Exit Criteria

- [ ] v1.13.0 release tag が GitHub に存在
- [ ] PyPI に `piper-plus==1.13.0` が published
- [ ] Docker Hub / GHCR に `piper-plus-cpu:1.13.0` / `piper-plus-gpu:1.13.0` が push 済
- [ ] `docs/migration/v1.12-to-v1.13.md` が存在し、 breaking change と migration step を明示
- [ ] Issue #527 が closed、 達成サマリコメント済
- [ ] CHANGELOG.md `[1.13.0]` セクションが完成
- [ ] release-verify CI が green

### 依存

- M1-M4 すべて完了
- 既存リリースフロー (`/release-prep` `/prepare-release` skill 経由)

### リスクゲート

| リスク | 判定基準 | 対応 |
|---|---|---|
| PyPI publish 失敗 | `dev-create-release.yml` が FAIL | wheel build ログ確認、 setuptools / wheel version 不整合の場合は修正 PR を別途 |
| Docker registry push 失敗 | `docker-build.yml` の push step FAIL | registry auth 確認、 タグ衝突確認 |
| 3rd party ユーザからの bug 報告 | リリース後 7 日以内に critical bug 1 件以上 | hotfix release (1.13.1) で対応、 重大なら 1.12 LTS 維持を別 issue で検討 |

### ステークホルダー

- リポジトリオーナー (release approval)
- PyPI / npm / NuGet maintainer (publish)
- 全 3rd party 利用者 (周知対象)

### 想定所要時間

**0.5 日**。 既存リリースフローに乗るため作業は機械的。

---

## マイルストーン依存図

```
              ┌─────────────────┐
              │   Issue #527    │  (承認待ち)
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │ M1: 基盤整備     │  Phase 0 + 1
              │ 0.5 day          │  (低リスク、 並列化なし)
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │ M2: 非 GPU Docker│  Phase 2
              │ 0.5 day          │  (CPU/distroless × 2)
              └────────┬────────┘
                       ▼
        ┌─────────────────────────────┐
        │ 運用前提: driver R570+      │  (M3 着手前の確認)
        │           + container 1.14+ │
        └──────────────┬──────────────┘
                       ▼
              ┌─────────────────┐
              │ M3: GPU Docker  │  Phase 3
              │ 1 day + 検証     │  (CUDA 12.8 + Ubuntu 24.04 + py3.13)
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │ M4: 新 GPU 最適化 │  Phase 4
              │ 1-2 day + 実機   │  (TF32 + bf16 + 実機検証)
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │ M5: リリース     │  Phase 外
              │ 0.5 day          │  (v1.13.0)
              └─────────────────┘

合計: 3.5-4.5 日 (人日)
```

---

## 累積進捗トラッキング

実装着手時に下記表で更新する。

| Milestone | 状態 | 着手日 | 完了日 | PR 番号 | 備考 |
|---|---|---|---|---|---|
| **承認待ち** | — | — | — | — | requirements.md + specifications.md の stakeholder 承認待ち |
| M1: 基盤整備 | 未着手 | — | — | — | — |
| M2: 非 GPU Docker | 未着手 | — | — | — | — |
| M3: GPU Docker | 未着手 | — | — | — | — |
| M4: 新 GPU 最適化 | 未着手 | — | — | — | — |
| M5: リリース | 未着手 | — | — | — | v1.13.0 |

---

## 中間チェックポイント

実装中に確認すべき定点観測項目:

### CP-01: M1 完了後

- [ ] `python-tests.yml` 3.13 ジョブが 5 PR 連続で green
- [ ] ローカル開発者から「3.13 環境構築が困難」 等の issue がない

### CP-02: M2 完了後

- [ ] distroless image を pull したユーザから ABI 不整合の issue がない
- [ ] Trivy CVE が baseline と同等以下を維持

### CP-03: M3 完了後 (重要)

- [ ] **Ada 6000 / RTX 5090 / T4 すべてで Docker image が起動**
- [ ] 学習サーバー / 推論サーバー全台で host driver R570+ が確定
- [ ] 旧 v1.12 image を継続利用する 3rd party がいないかコミュニティで確認

### CP-04: M4 完了後

- [ ] Ada 6000 で 5 epoch 程度の学習が安定 (1 epoch smoke だけでなく)
- [ ] WandB に新 GPU での学習 metric が記録されている
- [ ] training-guide / CLAUDE.md の V100 言及が **0 件** (検索で確認)

### CP-05: M5 完了後

- [ ] PyPI に v1.13.0 が visible
- [ ] Docker image tag `1.13.0` が pull 可能
- [ ] Issue #527 が close + 達成サマリ comment
- [ ] CHANGELOG `[1.13.0]` が release date 入り

---

## マイルストーン管理ルール

### M-RULE-01: PR と Milestone の対応

各 PR は明示的に対応 Milestone を記載する:
```
## Milestone
M3: GPU Docker 統一 (CUDA 12.8 + Ubuntu 24.04 + Python 3.13)
詳細: docs/reference/python-313/milestones.md#m3-gpu-docker-統一-cuda-128--ubuntu-2404--python-313
```

### M-RULE-02: Exit Criteria の確認

各 Milestone の Exit Criteria は **PR description で checkbox 化**し、 merge 前に全項目チェックを完了させる。 機械チェックできるもの (CI green 等) は GitHub Actions に任せ、 人手確認 (Ada 6000 smoke 等) は PR 本文で証跡を残す。

### M-RULE-03: リスクゲート発動時の処理

リスクゲートが発動した場合 (例: M3 で RTX 5090 起動失敗):
1. PR を draft に戻す
2. 該当 Milestone セクションの **リスクゲート対応**を実施
3. 解決後、 PR を ready for review に戻す
4. 解決できない場合は本ドキュメントに「除外項目」 として追記し、 別 issue 化

### M-RULE-04: 進捗トラッキング更新

実装着手・完了時に **「累積進捗トラッキング」 表**を本ドキュメントで更新する。 GitHub milestone 機能は使わない (PR 数を絞る方針)。

### M-RULE-05: 並列実行

M1 → M2 → M3 → M4 → M5 の **直列実行**を推奨。 Phase 単位では並列可だが、 Milestone 単位は依存関係 (driver / 検証) があるため逐次実行。

---

## 関連ドキュメント

| 文書 | 関係 |
|---|---|
| [`requirements.md`](requirements.md) | 要求定義 (WHAT/WHY) — Milestone の存在意義 |
| [`specifications.md`](specifications.md) | 要件定義 (HOW MUCH/HOW PRECISELY) — Milestone Exit Criteria の典拠 |
| [`README.md`](README.md) | 実装計画 (HOW STEP-BY-STEP) — Milestone 内の Phase 別 diff/rollback |
| [Issue #527](https://github.com/ayutaz/piper-plus/issues/527) | GitHub Issue (トリガー) |

---

定義日: 2026-05-22
適用範囲: dev branch (Issue #527 完了まで)
版数: 1.0 (初版)
