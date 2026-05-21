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

### C3. CUDA Docker (Ubuntu 22.04) の python3.13 提供 (中リスク)

- `nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04` の Ubuntu 22.04 (Jammy) は **apt で python3.10/3.11 まで**提供。 python3.13 は無い。
- 選択肢:
  1. **deadsnakes PPA を追加**: `apt-add-repository ppa:deadsnakes/ppa` を Dockerfile に追加 (シンプル、 だが追加 apt source の供給安定性は Canonical 外)。
  2. **Ubuntu 24.04 ベースへ bump**: `nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04` (Noble) → python3.12 が apt 標準、 3.13 は deadsnakes 経由。 Jammy EOL 2027、 Noble EOL 2029 で EOL 観点では Noble 推奨。
  3. **`python:3.13-slim` を multi-stage 流用**: CUDA image に builder の python tree を COPY (Wyoming Dockerfile が採用しているパターン)。
- **推奨:** 2 (Ubuntu 24.04 bump + deadsnakes 3.13)。 base image bump は別ブロッカー (cuDNN, glibc) を生むため、 22.04 維持 + deadsnakes を Phase 3 の最小変更とし、 Noble bump は別 issue で切り出すのが安全。

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

## 推奨アプローチ

リスクと工数で **3 段階に分割** することを推奨。

### Phase 0: distutils → setuptools 書換 (前提)

対象:
- `src/python/piper_train/vits/monotonic_align/setup.py` の `from distutils.core import setup` → `from setuptools import setup` (C1)

リスク: 極低 (setuptools shim 経由で既に動いている挙動を明示化するだけ、 ロールバック容易)
工数: 5 分

### Phase 1: 低リスク CI / docs (小 PR, 1-2 時間)

対象:
- ドキュメント (`CONTRIBUTING.md` / `README*.md` / `docs/**` / `QA-RELEASE-CHECKLIST.md` line 66, 453)
- 軽量 CI workflow (`codespell.yml` / `sbom.yml` / `python-lint.yml` / `pre-commit.yml` 等の lint/audit 系)
- `docker/python-inference/Dockerfile.cpu` (`python:3.11-slim-bookworm` → `python:3.13-slim-bookworm` 1 行)
- `runtime-parity-deep.yml` dump-python + compare の 3.11 → 3.13 (C4)

リスク: 低 (wheels は全て揃っている)
ロールバック: 容易 (個別 workflow)

### Phase 2: distroless / inference CUDA (中 PR, 半日)

対象:
- `docker/python-inference/Dockerfile.cpu.distroless` (builder = `python:3.13-slim-trixie`、 final = `distroless/python3-debian13`、 内部パス 6 箇所書換) — C2
- `docker/webui/Dockerfile.distroless` (同上) — C2
- `docker/python-inference/Dockerfile` (CUDA): deadsnakes PPA を 22.04 に追加して python3.13 入れる (C3 案 1) — base image bump は別 issue
- Trivy CVE scan (C2 で final image を debian12 → debian13 へ切り替えると CVE 構成が変わる) — `.github/workflows/docker-build.yml` の Trivy scan で diff 確認

リスク: 中 (image レイヤ構造 + base OS 切替)
要検証:
- distroless/python3-debian13 が piper-plus の onnxruntime / soundfile を import できるか smoke test (`docker/python-inference/Dockerfile.cpu.distroless` の Trivy gate + Wyoming smoke)
- CUDA inference image で deadsnakes 経由 python3.13 + uv pip install が onnxruntime-gpu wheel を解決できるか

### Phase 3: 学習 Docker (大 PR, 1-2 日)

対象:
- `docker/python-train/Dockerfile`: python 3.11 → 3.13 + torch `==2.2.1+cu121` → `==2.11.0+cu128` (uv.lock の canonical に合わせる、 C2)
- 関連 README / CHANGELOG / training-guide
- ubuntu22.04 + deadsnakes 3.13 で `python3.11-dev` の代替 (`python3.13-dev` も deadsnakes で提供) — `pyopenjtalk-plus` の C 拡張 build 用

リスク: 高 (torch bump は学習 reproducibility に影響、 CUDA wheel runtime も 12.1 → 12.8)
要検証:
- 既存 6lang base ckpt + Template B FT 1 epoch smoke で loss / forward が一致レンジか
- WandB ログの metric が同範囲で生成されるか (kl_loss / mel_loss / duration_loss)
- ONNX export 出力が PR #532 前の base と byte-equal でなくとも、 audio_parity の Tier 4 (SNR ≥ 30dB) を満たすか

### Phase 4 (任意): mypy / ruff target-version

`[tool.mypy] python_version` と `[tool.ruff] target-version` を `"3.11"` → `"3.13"` に上げると `match` 文 / `Self` 型 / `PEP 695 generics` が解禁される。 ただし **3.11 サポートを切ることになる**ため、 `requires-python` 据置方針と矛盾するため **見送り推奨**。

## 非対応事項

- `requires-python = ">=3.11"` の下限引き上げ → Issue #527 のスコープ外
- `[tool.ruff] target-version = "py311"` の引き上げ → 同上
- `python-tests.yml` matrix `["3.11", "3.12", "3.13"]` の削減 → memory `feedback_ci_matrix_no_reduction.md` (OSS public は CI minute 無制限、 網羅性優先) に従い据置
- `build-phonemize-wheels.yml` の cp313 build → piper-phonemize 1.1.0 が cp313 source build 未対応の問題が解消するまで保留

## 検証チェックリスト (各 Phase 共通)

切替後の green 判定基準:

| ゲート | 対象 | 期待 |
|---|---|---|
| `python-tests.yml` matrix 3.13 ジョブ | ubuntu / windows / macos × 3.13 | 全 PASS |
| `pre-commit run --all-files` | ruff / format / 50+ gate | clean |
| `docker-build.yml` Trivy scan | distributable image 群 | new HIGH/CRITICAL なし |
| `runtime-parity-deep.yml` | 6 runtime audio parity | Tier 1-4 PASS |
| `wyoming-smoke.yml` | Home Assistant 連携 | smoke green |
| `model-quality-gate.yml` | MOS / RTF 退行 | baseline ±2% 以内 |

## 次アクション提案

1. 本ドキュメントを Issue #527 にコメントとして貼り、 Phase 分割 (0/1/2/3) の方針承認を求める
2. 承認後 Phase 0 (distutils 書換) → Phase 1 → 2 → 3 の順で個別 PR (`/create-pr` skill 経由)
3. 各 Phase で `python-tests.yml` matrix の 3.13 ジョブが green であることを必須化
4. Phase 3 (学習 Docker) は学習サーバー実機で 1 epoch smoke を回した上で merge

---

調査日: 2026-05-21
調査範囲: dev branch HEAD (4e7a879e、 worktree `docs/issue-527-python-313-migration` b84f3681)
追加調査 (懸念事項 C1-C8): 2026-05-21 同日
