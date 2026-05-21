# Default Python 3.11 → 3.13 移行調査

Issue [#527](https://github.com/ayutaz/piper-plus/issues/527) 対応の影響範囲調査ノート。

## 背景

現状リポジトリ全体で **3.11 がデフォルト**として扱われているが、
今後の運用を見据えて **デフォルトを 3.13** に揃えたい (Issue #527)。

ただし `requires-python = ">=3.11"` 自体は変更しない予定。
「サポート下限を引き上げる」ではなく「日常的に使う interpreter を 3.13 に揃える」 という整理。

## 現状サマリ

| カテゴリ | 3.11 | 3.12 | 3.13 | 備考 |
|---|---|---|---|---|
| **CI workflow** | 25 箇所 | 14 箇所 | 41 箇所 | 既に過半が 3.13 |
| **Dockerfile** | 5 image | - | 2 image (wyoming / webui) | 推論/学習側がまだ 3.11 |
| **pyproject.toml** | 7 file (requires-python / target-version / mypy python_version) | - | - | 全 member 一致 |
| **テストマトリクス** | python-tests / g2p-python-ci で 3.11/3.12/3.13 を網羅 | | | 3.13 単体での退行は CI で見える |

CI gate `workspace-python-parity` (`scripts/check_workspace_python_parity.py`) で
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

### C. Dockerfile

| ファイル | 現状 | 切替難度 |
|---|---|---|
| `docker/wyoming/Dockerfile` | **既に 3.13.13** | 不要 |
| `docker/webui/Dockerfile` | **既に 3.13.13** | 不要 |
| `docker/python-inference/Dockerfile` (CUDA) | `python3.11` apt パッケージ (ubuntu22.04 ベース) | **中** (CUDA base が `nvidia/cuda:12.6.3-ubuntu22.04`、 ubuntu22.04 では python3.13 が apt にない → deadsnakes PPA か Ubuntu 24.04 移行が必要) |
| `docker/python-inference/Dockerfile.cpu` | `python:3.11-slim-bookworm` | **小** (`python:3.13-slim-bookworm` に置換するだけ) |
| `docker/python-inference/Dockerfile.cpu.distroless` | builder `python:3.11-slim-bookworm` / final `gcr.io/distroless/python3-debian12` (= python3.11) | **中** (final image を `distroless/python3-debian13` (= python3.13) に切替 + `/usr/local/lib/python3.11` パスを 3.13 に書換) |
| `docker/webui/Dockerfile.distroless` | builder `python:3.11-slim-trixie` / final `distroless/python3-debian12` | 同上 |
| `docker/cpp-inference/Dockerfile.distroless` | コメント中の参照のみ (Python 実行なし) | コメント更新のみ |
| `docker/python-train/Dockerfile` | builder/runtime とも `python3.11` apt (ubuntu22.04) | **大** (`torch==2.2.1+cu121` が **cp313 wheel を提供しない**。 PyTorch 2.5+ への bump が事実上必須。 連動して `torchaudio` / `torchvision` も) |

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

| 依存 | バージョン | cp313 wheel | リスク |
|---|---|---|---|
| `torch` (root) | `>=2.11.0` (ローカル) / `==2.2.1+cu121` (docker/python-train) | torch 2.5+ で cp313 提供。 **2.2.1 は cp313 wheel 無し** | **高** (training Docker は torch bump とセット) |
| `onnxruntime` | `>=1.20.0` | 1.20+ で cp313 提供 | 低 |
| `pyopenjtalk-plus` | `>=0.4` | 最新版で cp313 wheel あり | 低 |
| `piper-phonemize` | `>=1.1.0; python_version < '3.13'` marker | cp313 未提供 | **対応済** (marker で除外) |
| `numba` | `>=0.59` | 0.60+ で cp313 wheel あり | 低 |
| `pytorch-lightning` | `>=2.0` | 2.4+ で cp313 OK | 低 (torch と連動 bump) |
| `numpy` | `<2.5` | 2.1+ で cp313 wheel あり | 低 |
| `scipy` | `>=1.17.1` | 1.14+ で cp313 wheel あり | 低 |

**最大ブロッカー:** `docker/python-train/Dockerfile` の `torch==2.2.1+cu121` pin。
3.13 化と同時に torch bump (例: 2.5.x → 2.7.x) が必要。 ただし学習済みモデルの推論互換性 (state_dict / serialize 形式) は通常維持される。

## 推奨アプローチ

リスクと工数で **3 段階に分割** することを推奨。

### Phase 1: 低リスク CI / docs (小 PR, 1-2 時間)

対象:
- ドキュメント (`CONTRIBUTING.md` / `README*.md` / `docs/**`)
- 軽量 CI workflow (`codespell.yml` / `sbom.yml` / `python-lint.yml` / `pre-commit.yml` 等の lint/audit 系)
- `docker/python-inference/Dockerfile.cpu` (`python:3.11-slim-bookworm` → `python:3.13-slim-bookworm` 1 行)

リスク: 低 (wheels は全て揃っている)
ロールバック: 容易 (個別 workflow)

### Phase 2: distroless / inference CUDA (中 PR, 半日)

対象:
- `docker/python-inference/Dockerfile.cpu.distroless` (builder + final + 内部パス書換)
- `docker/webui/Dockerfile.distroless` (同上)
- `docker/python-inference/Dockerfile` (CUDA): ubuntu22.04 の python3.13 提供方法決定 (deadsnakes PPA or ubuntu24.04 移行)

リスク: 中 (image レイヤ構造の変更を伴う)
要検証: distroless/python3-debian13 が piper-plus の onnxruntime / soundfile を import できるか smoke test

### Phase 3: 学習 Docker (大 PR, 1-2 日)

対象:
- `docker/python-train/Dockerfile`: python 3.11 → 3.13 + torch 2.2.1+cu121 → 2.5+ (cu124 系) bump
- 関連 README / CHANGELOG / training-guide

リスク: 高 (torch bump は学習 reproducibility に影響)
要検証: 既存 6lang base ckpt + Template B FT 1 epoch smoke で loss / forward が一致レンジか

### Phase 4 (任意): mypy / ruff target-version

`[tool.mypy] python_version` と `[tool.ruff] target-version` を `"3.11"` → `"3.13"` に上げると `match` 文 / `Self` 型 / `PEP 695 generics` が解禁される。 ただし **3.11 サポートを切ることになる**ため、 `requires-python` 据置方針と矛盾するため **見送り推奨**。

## 非対応事項

- `requires-python = ">=3.11"` の下限引き上げ → Issue #527 のスコープ外
- `[tool.ruff] target-version = "py311"` の引き上げ → 同上
- `python-tests.yml` matrix `["3.11", "3.12", "3.13"]` の削減 → memory `feedback_ci_matrix_no_reduction.md` (OSS public は CI minute 無制限、 網羅性優先) に従い据置
- `build-phonemize-wheels.yml` の cp313 build → piper-phonemize 1.1.0 が cp313 source build 未対応の問題が解消するまで保留

## 次アクション提案

1. 本ドキュメントを Issue #527 にコメントとして貼り、 Phase 分割の方針承認を求める
2. 承認後 Phase 1 から個別 PR で対応 (`/create-pr` skill 経由)
3. 各 Phase で `python-tests.yml` matrix の 3.13 ジョブが green であることを必須化

---

調査日: 2026-05-21
調査範囲: dev branch HEAD (4e7a879e)
