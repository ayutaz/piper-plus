# piper → piper_plus モジュール改名 (v2.0 / Issue #590)

**ステータス**: Design (レビュー待ち)
**対象バージョン**: v2.0.0 (未リリース。VERSION=2.0.0、git tag は v1.13.0 が最新)
**関連 Issue**: [#590](https://github.com/ayutaz/piper-plus/issues/590) — Allow to install piper and piper-plus to the same environment
**ブランチ**: `feat/piper-plus-module-rename`
**作成日**: 2026-07-10

---

## 1. 概要

piper-plus は rhasspy/piper の唯一の MIT フォークだが、**Python ランタイムと C++ プリビルドバイナリだけが本家と同じ `piper` という名前**（`import piper` / `piper` コマンド / `./bin/piper`）を維持している。一方、モデルも CLI スイッチも本家と非互換であるため、「名前は同じだが中身は非互換」という状態が Issue #590 の根本原因になっている。

本設計は、v2.0 のメジャー境界で **`piper` → `piper_plus` / `piper-plus` へフル改名し、互換 shim を一切残さない (クリーンブレーク)** ことで、本家 `piper-tts` との pip / CLI 完全共存を成立させる。加えて、周辺の install-layout (共有辞書 dir・キャッシュ dir・環境変数 prefix) も cross-runtime で `piper-plus` に統一し、命名の一貫性を全ランタイムで揃える。

---

## 2. 背景: 現状の命名非対称

| ランタイム | 配布名 | 実体名 (import/コマンド/バイナリ) | 本家 piper と衝突 |
|---|---|---|---|
| **Python (PyPI)** | `piper-plus` | `import piper` + コマンド `piper` | ⚠️ する |
| **C++ プリビルド** | release zip | `./bin/piper` | ⚠️ する |
| Rust | `piper-plus-cli` | `piper-plus-cli` | しない |
| Go | `piper-plus` | `piper-plus` | しない |
| C# | `PiperPlus.Cli` | 別名 | しない |
| npm | `piper-plus` | ライブラリ | しない |

後発ランタイム (Rust/Go/C#/npm) は最初から `piper-plus` 系で命名されている。**フォーク由来のコードをそのまま引き継いだ Python と C++ だけ**が `piper` を維持している。本改名はこの歴史的非対称を解消する。

---

## 3. 確定した設計判断 (brainstorming の結論)

| 決定事項 | 内容 | 根拠 |
|---|---|---|
| **改名の深さ** | フル改名: `import piper`→`import piper_plus` / コマンド `piper`→`piper-plus` / C++ バイナリ `piper`→`piper-plus` | 全ランタイムと一貫。issue #590 を根本解決 |
| **後方互換** | クリーンブレーク: piper-plus 本体は `piper_plus/` のみ配置。`piper/` モジュールも `piper` コマンドも一切残さない (shim なし) | shim を残すと本家との pip 共存が破綻する (自己矛盾) |
| **名前空間衝突 (Phase 0)** | 高レベル API `src/python/piper_plus/` を runtime パッケージの `piper_plus.api` サブモジュールに**物理統合** | 1 パッケージに集約、import が直感的 |
| **改名スコープ** | 周辺 dir / env prefix も含めた**全面統一** (アグレッシブ) | v2 メジャー境界で clean 切替 |
| **タイミング** | 未リリースの v2.0.0 に含める | 追加の破壊的リリースを起こさずに済む |
| **配布名** | PyPI `piper-plus` / crates `piper-plus` 等の**配布名は不変**。変わるのは import 名・コマンド名・バイナリ名・layout のみ | PEP 503 で dash↔underscore、配布名変更は不要 |

---

## 4. 名前空間衝突の詳細 (Phase 0 の核心)

ultracode 調査 (12 エージェント / 152 findings) で判明した最大のブロッカー:

- **`src/python/piper_plus/`** = 高レベル API `PiperPlus` (独自 ONNX 推論エンジン `engine.py`)。**PyPI 非配布** (pyproject なし)。Wyoming Docker が `COPY src/python/piper_plus/ /app/piper_plus/` して `import piper_plus` で使う。consumer は `src/python/piper_wyoming/__main__.py:15` の 1 行 + tests 4 ファイルのみ。
- **改名先 runtime `src/python_run/piper/`→`piper_plus/`** = PyPI `piper-plus` 本体 `PiperVoice`。

両者が top-level `piper_plus` を奪い合う。現状は runtime が `piper` 名なので衝突していないが、改名すると同一環境で衝突する。

**決定 (案 B)**: runtime を canonical `piper_plus` とし、高レベル API を `piper_plus.api` サブモジュールに物理統合する。

```
src/python_run/piper_plus/
  ├─ voice.py, config.py, timing.py, ...   (runtime: PiperVoice)
  ├─ __main__.py                            (コマンド piper-plus)
  └─ api/                                   ← src/python/piper_plus/ を移動
       ├─ __init__.py  (PiperPlus, AudioResult, engine, ...)
       ├─ engine.py, audio.py, _model_resolver.py
       └─ ...
```

**要追加検討 (未決点 OQ-1)**: 高レベル API `api/engine.py` (独自 ONNX 推論) と runtime `voice.py` (`PiperVoice`) は**2 つの独立した ONNX 推論実装**である。統合パッケージ内に二重実装が同居することになる。本改名では「物理的に同居させ import パスを整える」ところまでを scope とし、**推論実装の一本化は別 issue に切り出す** (改名と実装統合を混ぜると巨大化・危険)。

---

## 5. スコープ定義

### 5.1 In scope (本設計で変更する)

| カテゴリ | 変更 |
|---|---|
| Python import 名 | `piper` → `piper_plus` (ディレクトリ物理改名 + 絶対 import 修正) |
| Python コマンド | `piper` → `piper-plus` (entry-point、エイリアス無し) |
| Python module 実行 | `python -m piper[.webui/.http_server]` → `python -m piper_plus[...]` |
| 高レベル API 統合 | `src/python/piper_plus/` → `src/python_run/piper_plus/api/` |
| C++ バイナリ | `./bin/piper` / `piper.exe` → `piper-plus` |
| packaging | pyproject scripts / package-data キー / MANIFEST.in / pytest.ini / mypy files |
| tests | import 文 + 文字列ベース mock (`patch("piper.X")` / sys.modules / caplog logger) |
| CI/CD | 17 workflow の `src/python_run/piper/**` path filter + module 実行 + C++ バイナリ参照 |
| docs/README | `./bin/piper` / `python -m piper` / `import piper` の全参照 (9 言語 README + docs) |
| 共有辞書 dir | `share/piper/` → `share/piper-plus/` (cmake 6 + Rust 4 + Go 2 箇所) |
| キャッシュ/データ dir | `~/.local/share/piper` 等 → `piper-plus` (C#/Rust の bare piper を統一) |
| env var prefix | `PIPER_*` → `PIPER_PLUS_*` + HTTP header `x-piper-warning` (cross-runtime) |
| リリースアセット名 | `piper-*.tar.gz` → `piper-plus-cpp-*` (C#/Rust CLI との接頭辞衝突回避に `-cpp-` 識別子) |

### 5.2 Out of scope (変更しない / 別 issue)

- **配布名** (PyPI `piper-plus` / crates.io / npm / NuGet / Maven) は不変。
- **C++ namespace `piper`** (release-shared-lib.yml:418-422 の symbol grep 対象) は本改名 scope 外 (バイナリ名のみ)。
- **推論実装の一本化** (高レベル API engine ↔ runtime PiperVoice の二重実装統合) は別 issue (OQ-1)。
- **CHANGELOG の歴史的記述** / **rhasspy/piper 帰属** / **`*-piper` downstream 名** / **`dataset:piper` メタ** は据置 (改名対象外、sed 除外リスト必須)。
- **`__init__.py` の `version("piper-plus")`** は配布名参照なので触らない。

---

## 6. 実装フェーズ (単一ブランチ・単一 PR)

**ユーザー方針**: 全対応を本ブランチ `feat/piper-plus-module-rename` の**単一 PR** で実施する。単一 PR のため、path filter の silent stop 問題 (dir 改名と filter 更新の間に CI が空回りする期間) は「全変更が atomic」なので**自然に回避**される。以下は PR 分割ではなく、依存順の**実装フェーズ (コミット単位)** を示す。

| フェーズ | 内容 (ultracode Phase) | 依存 | breaking |
|---|---|---|---|
| **F1 基盤** | dir 改名 `git mv src/python_run/piper → piper_plus` + 高レベル API 統合 (`src/python/piper_plus/`→`piper_plus/api/`) + runtime 内部絶対 import 修正 (Phase 0/1) | なし | ⚠️ import |
| **F2 packaging** | pyproject scripts (`piper-plus=piper_plus.__main__:main`) / package-data キー / MANIFEST.in / pytest.ini / setup.py / script/ (Phase 2) | F1 | ⚠️ コマンド |
| **F3 tests** | import 文 + 文字列ベース mock (`patch("piper.X")` / sys.modules setitem / caplog logger) + subprocess `-m piper` (Phase 3) | F1,F2 | — |
| **F4 CI/CD** | 17 workflow の `src/python_run/piper/**` path filter + `python -m piper` + C++ バイナリ参照 (Phase 5) | F1,F5 | — |
| **F5 C++** | cmake `OUTPUT_NAME "piper-plus"` + docker cpp-inference (entrypoint/Dockerfile/distroless/test.sh) lockstep (Phase 4) | なし | ⚠️ バイナリ |
| **F6 docs** | README 9 言語 + docs/ の `./bin/piper`/`python -m piper`/`import piper` + v2.0 移行ガイド新設 (Phase 6) | F1-F5 | doc |
| **F7 周辺 layout** | 共有辞書 dir / キャッシュ dir / env prefix `PIPER_*→PIPER_PLUS_*` (cross-runtime) + リリースアセット名 (Phase 7 拡張) | F1,F5 | ⚠️ layout/資産 |
| **F8 stub+検証** | stub README 注記 + 本家 `piper-tts` co-install e2e + 全ランタイム parity 回帰 (Phase 7/8) | 全て | stub |

> **atomic 制約**: 単一 PR のため CI は最終状態で一括評価される。ただし**中間コミットで CI を green に保つ必要はない**が、レビュー容易性のためフェーズ順にコミットを分ける (F1 の dir 改名を独立コミット、以降フェーズ単位)。path filter (F4) と dir 改名 (F1) が同一 PR に入るため silent stop は発生しない。

> **F7 (周辺 layout) の扱い**: 共有辞書 dir / キャッシュ dir / env prefix の改名は issue #590 の目的 (共存) とは無関係で、既存ユーザーの DL 済み資産を orphan 化する。ユーザー方針で本 PR に含めるが、**コミットを明確に分離**し、レビュー時に影響を独立に評価できるようにする。docker image tag / container / Unix user `piper` (OQ-5) は upstream 非衝突のため本 PR では**据置** (別途方針決定)。

---

## 7. Breaking Changes

1. **Python import**: `import piper` / `from piper.X import ...` 削除 → `import piper_plus` / `from piper_plus.X import ...`。互換 shim 無し。
2. **Python CLI**: `piper` コマンド削除 → `piper-plus`。`pip install piper-plus` 後に `piper` は存在しない。
3. **Python module 実行**: `python -m piper[.webui/.http_server]` → `python -m piper_plus[...]`。
4. **C++ バイナリ**: `./bin/piper` (`piper.exe`) → `./bin/piper-plus` (`piper-plus.exe`)。
5. **install-layout** (PR-F): 共有辞書 dir / キャッシュ dir が `piper-plus` に移動 → 既存 DL 資産は再取得が必要。
6. **env var**: `PIPER_*` → `PIPER_PLUS_*` (全ランタイム)。
7. **リリースアセット名** (PR-F): `piper-linux-x64.tar.gz` 等 → `piper-plus-cpp-*`。新タグの DL URL が変わる (旧タグ添付は per-tag で不変・安全)。
8. **配布名は不変**: PyPI `piper-plus` はそのまま。変わるのは import 名・コマンド名・バイナリ名・layout。

---

## 8. 移行ガイド項目 (docs/migration/v1.12-to-v2.0.md に追記)

- **新メンタルモデル**: `import piper` = 本家 rhasspy/piper、`import piper_plus` = 当 fork。両者は完全独立で pip 共存可能 (単なる rename ではない)。
- import 文の書き換え: `from piper.voice import PiperVoice` → `from piper_plus.voice import PiperVoice`。安全な自動ブリッジは共存目的のため意図的に提供しない。
- CLI 書き換え: `piper --model ...` → `piper-plus --model ...`。
- C++ バイナリ利用者: `./bin/piper` → `./bin/piper-plus`、PATH / スクリプト参照を更新。
- **piper-tts-plus stub ユーザー**: v2.0 では `piper/` が同梱されないため `import piper` が失敗する。`import piper_plus` に切り替えるか、v1.x 継続なら `piper-plus<2` で pin。
- **Wyoming / Home Assistant ユーザー**: 変更不要 (Wyoming アダプタは既に `piper_plus`/`piper_wyoming` 系で本改名の影響を受けない)。
- 継続学習ユーザー (Issue #527/DR-006): 旧 ckpt resume は v2.0 で非保証。継続が必要なら v1.12 Docker image tag を継続利用。
- v1.11-to-v1.12.md:92-97 の http_server「変更不要」記述が v2.0 で矛盾する点に注記。

---

## 9. リスクと緩和

| リスク | 深刻度 | 緩和策 |
|---|---|---|
| **webui.py:23 の `from piper import` を放置** → 本家 co-install 環境で silently 本家 PiperVoice を import し ImportError も出さず誤動作 (最も静かで危険) | 高 | PR-B 最優先修正。PR-G の co-install 検証で `from piper_plus import` が当 fork を解決することを明示 assert |
| **17 workflow の path filter が dir 改名後に silent trigger 停止** (CI が走らなくなる回帰) | 高 | PR-B で dir 改名と同一 PR で全 filter 更新。ダミー変更で発火確認 |
| **文字列ベース mock** (`patch("piper.X")` 約28箇所 + sys.modules setitem + caplog logger 3箇所) は import sed で捕捉されず、外すとテスト偽陽性/偽陰性化 | 高 | PR-B 手順に専用 grep `["']piper\.` を明示。CI で loud fail を確認 |
| **package-data キー `piper`→`piper_plus` 未更新** → voices.json/loanword/sv_function_words が wheel 非同梱 → build 成功・実行時 FileNotFound | 高 | PR-B で pyproject package-data + MANIFEST.in 両方更新。PR-G wheel smoke で data 同梱を確認 |
| **C++ バイナリ改名と docker cpp-inference の非同期** → build 失敗・HEALTHCHECK 常時 unhealthy・distroless 起動不能 | 高 | PR-C で cmake OUTPUT_NAME と docker (entrypoint/Dockerfile/distroless/test.sh) を単一 PR で lockstep。保守案 (target 名保持 + OUTPUT_NAME) で約40 TARGET piper 参照を無変更 |
| **blind sed `s/piper/piper_plus/`** が version("piper-plus") / rhasspy/piper 帰属 / CHANGELOG / dataset:piper / PIPER_ env を誤爆 | 高 | sed 前に除外パターンを明文合意。file:line 単位レビューで機械置換を検証 |
| **stub unpinned 依存** で `pip install -U piper-tts-plus` が v2.0 を引き `import piper` 失敗、共存環境では本家に silently 解決 | 中 | PR-E で stub README に v2.0 import 変更を明記 + pin 方針を確定 (gpu/http extras も一致) |
| **リリースアセット名改名** で DL URL 変更 → docs/install スクリプト/外部 wiki 不整合 | 中 | PR-F で docs 同時更新 + 移行ガイド周知。移行期間は旧名/新名の二重アップロードを検討 |
| **install-layout 変更** で既存 DL 済みモデル/辞書が orphan 化 (再 DL) | 中 | PR-F を独立させ、資産移行の要否をユーザー判断に委ねる。移行ガイドで明示 |

---

## 10. テスト戦略

- **本家共存検証 (最重要)**: 本家 `piper-tts` と改名済 piper-plus v2.0 wheel を同一 clean venv に co-install し、`import piper` が本家を、`import piper_plus` が当 fork を独立解決すること + site-packages に `piper/` と `piper` コマンドが当 wheel 由来で存在しないことを assert。
- **文字列ベース mock sweep**: 専用 grep `["']piper\.` で列挙し、改名漏れが pytest で AttributeError/ModuleNotFoundError/caplog assert 失敗として顕在化することを inference job (onnxruntime 有り) で確認。
- **wheel smoke**: build した wheel の site-packages に `piper_plus/` が置かれ `from piper_plus.phonemize.multilingual import` が通ること、data 3 ファイルが同梱され FileNotFound しないこと。
- **CI path filter 回帰検知**: `src/python_run/piper_plus/**` filter が正しく発火することをダミー変更でトリガ確認。
- **C++/docker/distroless/Wyoming**: `bin/piper-plus --version`、cpp-inference HEALTHCHECK healthy、distroless 起動、Wyoming `import piper_plus` smoke を e2e。
- **cross-runtime parity gate**: dir 改名時は zh_en_loanword_matrix.json の py_runtime provenance + Swedish LID / phoneme-timing golden fixture を lockstep 更新し json-sync gate が byte-for-byte 緑。
- **editable install 再現**: `uv pip install -e src/python_run` 後に `-m piper_plus` 解決・`--cov=piper_plus` が no-data にならないこと。

---

## 11. エコシステム影響

- **朗報**: README:413 の "People using Piper" (HA / Rhasspy / NVDA / OVOS / LocalAI 等) は全て upstream rhasspy/piper を叩いており、piper-plus は元々モデル非互換のため本改名で直接は壊れない。HA 連携の中核 Wyoming アダプタも既に `piper_plus`/`piper_wyoming` 系で runtime `piper` に非依存 → **影響なし** (周知で不安を解消)。
- **実影響 (2 点)**:
  1. C++ プリビルドバイナリ `./bin/piper` とアセット `piper-linux-x64.tar.gz` を `piper-plus` 化することで、piper-plus 配布物を `piper` として利用/スクリプト化していた downstream (mintPiper/Vim-Piper/JetsonGPT 系や手動 DL) が壊れる → CHANGELOG/リリースノートで明示周知必須。
  2. `pip install piper-plus` 後に `piper` コマンドと `import piper` が消え、本家との共存が可能になる反面、旧ユーザー誘導が必須。
- **アセット命名衝突**: リリースアセット名を `piper-plus-*` にすると C# `piper-plus-cli-*` / Rust と接頭辞衝突 → `piper-plus-cpp-*` 等の識別子で命名規約を再設計。
- **HF Space** (`ayousanz/piper-plus-demo`、リポジトリ外) がサンプルで `import piper` / `piper` コマンドを使う場合は改名リリースと同時更新が必要 (要別途確認)。

---

## 12. 未決点 (Open Questions)

| ID | 内容 | 暫定方針 |
|---|---|---|
| OQ-1 | 高レベル API engine ↔ runtime PiperVoice の**二重 ONNX 推論実装**をどう整理するか | 本改名では物理同居まで。実装一本化は別 issue |
| OQ-2 | リリースアセット命名規約 (`piper-plus-cpp-*` で確定か) | PR-F で決定。C#/Rust との整合を要確認 |
| OQ-3 | `script/piper` dev wrapper のファイル名を `script/piper-plus` に rename するか | PR-B で決定 (混乱回避なら rename 推奨) |
| OQ-4 | stub `piper-tts-plus` の依存 pin: `<2` cap (v1.x 凍結) vs unpinned (文書化した break) | PR-E で決定 |
| OQ-5 | docker image tag / container / volume / Unix user `piper` (~30箇所) を sweep するか | 据置推奨 (upstream 非衝突・共存無関係)。方針は PR-F で明記 |
| OQ-6 | HF Space / モデルカードのサンプルコード改名 (リポジトリ外) | 改名リリースと同時に別途対応 |

---

## 13. 検証の受け入れ条件 (Definition of Done)

- [ ] `pip install piper-tts`(本家) + piper-plus v2.0 wheel を同一 venv に co-install して相互汚染なし。
- [ ] `which piper` が本家 or 無し、`which piper-plus` が当 fork。site-packages に当 wheel 由来の `piper/` が存在しない。
- [ ] 全 Python テストが `-m piper_plus` で緑 (import + 文字列 mock 漏れゼロ)。
- [ ] 17 workflow の path filter が新 dir で発火。
- [ ] `bin/piper-plus --version` + docker cpp-inference HEALTHCHECK healthy + distroless 起動 + Wyoming smoke 緑。
- [ ] cross-runtime parity gate (loanword / Swedish LID / phoneme-timing) 緑。
- [ ] v2.0 移行ガイドに rename 節が追加され doc-examples audit snapshot が drift なし。

---

> 本設計は ultracode マルチエージェント調査 (12 エージェント / 152 findings / 全11領域) の結果を統合したもの。調査の生成果物は run `wf_e92339b8-b60` の journal に保存。
