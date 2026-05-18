# CI/CD 拡張プラン — マイルストーン詳細

**親ドキュメント**: [ci-expansion-2026-05.md](./ci-expansion-2026-05.md)
**個別チケット**: [../tickets/README.md](../tickets/README.md) — 各 M.X を実装者が一人で着手できるレベルまで具体化した 10 チケット
**作成日**: 2026-05-18
**対象期間**: Month 1-3 (本ドキュメント) + Stretch (Month 4+)

> このドキュメントは [ci-expansion-2026-05.md](./ci-expansion-2026-05.md) の **Top 10 項目** を実装単位のマイルストーンに分解したもの。 GitHub Milestone / Project board と紐づけできる粒度で、 各 M に **目的 / 成功基準 / タスク / 依存 / リスク / 関連ファイル** を明記する。 各 M.X の詳細実装チケット (エージェントチーム配置 / Unit/E2E テスト / Reinvention / Handoff まで) は [../tickets/](../tickets/README.md) を参照。

---

## 全体マップ

| Milestone | テーマ | 期間 | 含まれる Top 10 項目 | 主要成果物 |
|-----------|--------|------|---------------------|------------|
| **M1: Defensive Foundations** | 既存 gate 構造欠陥修復 + onboarding | Month 1 (4 週) | #10 #3 #5 | cancelled baseline alarm / migration lint / first-PR fast lane |
| **M2: Audio Quality Moat** | user-visible 品質 regression 検出 | Month 2 (4 週) | #1 #2 | MOS proxy gate (informational → blocker) / cross-runtime audio byte parity |
| **M3: ABI & Ecosystem Hardening** | semver 違反 / 法務 / supply chain | Month 3 (4 週) | #4 #7 #8 | Public ABI snapshot / license auto-injection / typosquatting weekly scan |
| **M4: Informational Tier** (任意、 並走可) | flaky 検査の signal noise 隔離 | Month 3 並走 | #6 #9 | forward-compat fuzz / timing monotonicity property test (どちらも non-blocker) |
| **M-Stretch: Strategic Bets** | unlimited CI を本気で活かすなら | Month 4+ | (Top 10 外、 親 doc §3 参照) | OSS-Fuzz / Bencher dashboard / real-device farm |

各 M 末尾に **「追加 workflow と同数の既存 workflow を削除候補としてレビュー」** する maintenance budget rule を運用ルールとして固定化 (親 doc §6 net flat policy)。

---

## M1: Defensive Foundations

**期間**: Month 1 (4 週)
**狙い**: 既存 gate の構造欠陥を修復し、 新規 contributor の onboarding 障壁を下げる。 新規メンテナンス税を最小化するため難易度低のみで構成。

### M1.1 — Cancelled / skipped baseline alarm (Top 10 #10)

**実装チケット**: [M1-1-cancelled-baseline-alarm.md](../tickets/M1-1-cancelled-baseline-alarm.md)

| 項目 | 内容 |
|------|------|
| 目的 | PR #419 再発防止: required check が cancelled で終わった場合に merge を block する |
| 成功基準 | (a) `required_status_check_gate.yml` workflow が存在、 (b) Multi-Runtime RTF / Memory regression / CodeQL の baseline 検証が cancelled なら fail、 (c) dev branch protection に new check を required 化 |
| タスク | (1) cancelled / skipped を success として扱う既存 workflow を棚卸し、 (2) gate workflow 作成 (`gh api` で run conclusion を集計)、 (3) branch protection を `gh api` で更新、 (4) `feedback_ci_cancelled_baseline.md` を memory に記載済みなのを確認 |
| 依存 | なし |
| リスク | concurrency group との競合で本物の supersede cancel まで block する可能性 — `head_sha == latest commit` 条件で再 trigger を待つ仕組みを併設 |
| ROI / 難易度 | 高 / 低 |
| 関連ファイル | `.github/workflows/multi-runtime-rtf.yml`, `memory-regression.yml`, `codeql.yml`、 新規 `required_status_check_gate.yml` |
| 想定工数 | 1-2 PR (~8h) |

### M1.2 — Migration guide lint (Top 10 #3)

**実装チケット**: [M1-2-migration-guide-lint.md](../tickets/M1-2-migration-guide-lint.md)

| 項目 | 内容 |
|------|------|
| 目的 | `CHANGELOG.md` の `[Unreleased] > Breaking` 節と `docs/migration/v*.md` の cross-ref を強制 |
| 成功基準 | (a) `migration-guide-lint.yml` workflow が PR で breaking entry を検出した場合、 対応する migration doc の存在 + anchor link を assert、 (b) `migration-changelog-parity.yml` の延長として動作 |
| タスク | (1) keep-a-changelog parser script (`scripts/check_migration_xref.py`)、 (2) breaking entry に migration anchor link を強制する正規表現、 (3) `migration-changelog-parity.yml` を拡張 or 新規 workflow |
| 依存 | なし (既存の `migration-changelog-parity.yml` を継承) |
| リスク | breaking change の粒度が一律ではなく、 docs を必須化すると過剰 friction の懸念 — 「breaking」label 付き PR のみ enforce する設計 |
| ROI / 難易度 | 高 / 低 |
| 関連ファイル | `.github/workflows/migration-changelog-parity.yml`、 `CHANGELOG.md`、 `docs/migration/` |
| 想定工数 | 1 PR (~6h) |

### M1.3 — First-PR fast lane (Top 10 #5)

**実装チケット**: [M1-3-first-pr-fast-lane.md](../tickets/M1-3-first-pr-fast-lane.md)

| 項目 | 内容 |
|------|------|
| 目的 | 新規 contributor の PR は contract gate を warning に降格、 コア lint のみ blocker。 merge 前に maintainer が手動で full gate trigger |
| 成功基準 | (a) `first-pr-fast-lane.yml` で `github.event.pull_request.author_association in ['FIRST_TIME_CONTRIBUTOR', 'NONE', 'FIRST_TIMER']` なら contract gate を `continue-on-error: true` 化、 (b) maintainer が `/run-full-gate` label を付与すると blocker 化 |
| タスク | (1) author_association 判定 logic、 (2) contract gate 18 本に conditional 化、 (3) `CONTRIBUTING.md` に fast lane 説明追加、 (4) maintainer-only label workflow |
| 依存 | M1.1 (gate concept) |
| リスク | full gate を maintainer が忘れて merge する事故 — `merge` API で `required_status_check_gate.yml` を一律 require にして maintainer も bypass 不可にする |
| ROI / 難易度 | 高 / 低 |
| 関連ファイル | `.github/workflows/parity-hub.yml`, `pua-consistency.yml`, `zh-en-loanword-sync.yml`、 新規 `first-pr-fast-lane.yml`、 `CONTRIBUTING.md` |
| 想定工数 | 2 PR (~12h) |

**M1 完了基準**: 3 PR が merge され、 `required_status_check_gate.yml` が dev branch protection に組み込まれていること。

---

## M2: Audio Quality Moat

**期間**: Month 2 (4 週)
**狙い**: piper-plus 最大の盲点である「合成音声 user-visible regression」を 2 軸で塞ぐ。
**設計方針**: 最初の 4 週間は **informational tier** (non-blocking) で false positive 率を観測し、 安定後に blocker 化する。 一気に gate 化しない。

### M2.1 — Audio MOS proxy gate (Top 10 #1)

**実装チケット**: [M2-1-audio-mos-proxy.md](../tickets/M2-1-audio-mos-proxy.md)

| 項目 | 内容 |
|------|------|
| 目的 | PESQ / STOI / ViSQOL で golden sample 10 個に対し PR ごとに走らせ、 閾値割れで fail |
| 成功基準 | (a) `audio-mos-proxy.yml` workflow が tsukuyomi 50 文 × 6 言語の MOS proxy を計算、 (b) baseline JSON (`tests/fixtures/audio-mos-baseline.json`) と比較し threshold 内、 (c) 4 週間 informational 後に blocker 昇格 |
| タスク | (1) golden sample 選定 (短文 / 長文 / SSML / ZH-EN 混在 / PUA 含む)、 (2) PESQ-WB / STOI / UTMOS22 score 計算 script (`scripts/audio_quality_metrics.py`)、 (3) baseline 生成 + commit、 (4) workflow 構築、 (5) PR comment 自動投稿 (sticky comment、 `feedback_pr_body_over_comments` 準拠) |
| 依存 | M1.1 (cancelled silent skip 防止が前提) |
| リスク | UTMOS は PyTorch dependency が重い (~3GB) — Whisper / wav2vec2 representation 抽出に絞り、 軽量化を優先。 GPU は使わず CPU で完結 (~10 min / run、 unlimited CI 前提なので可) |
| ROI / 難易度 | 高 / 中 |
| 関連ファイル | `tools/benchmark/` (既存 MOS script の CI 化)、 `tests/fixtures/audio-mos-baseline.json` 新規、 `.github/workflows/audio-mos-proxy.yml` 新規 |
| 想定工数 | 3-4 PR (~30h) |

### M2.2 — Cross-runtime audio byte parity (Top 10 #2)

**実装チケット**: [M2-2-cross-runtime-audio-parity.md](../tickets/M2-2-cross-runtime-audio-parity.md)

| 項目 | 内容 |
|------|------|
| 目的 | 7 runtime × 3 model で同一入力 → 合成音声 WAV の SHA256 / RMSE / chromaprint fingerprint 比較 |
| 成功基準 | (a) `runtime-parity-deep.yml` の subset として `parity-audio` job が動作、 (b) SNR ≥ 60 dB / mel-spec MSE ≤ 1e-3 を満たす、 (c) 失敗時に diff spectrogram PNG を artifact upload |
| タスク | (1) 各 runtime に `--dump-wav` 経路を実装 or 既存 CLI 活用、 (2) fixture text 選定 (M2.1 と共有可)、 (3) chromaprint / mel-spec MSE 計算 script、 (4) workflow 構築、 (5) 浮動小数 / ORT provider 差を許容する閾値設計 |
| 依存 | M1.1 / M2.1 (fixture 共有) |
| リスク | ORT provider × OS で浮動小数差が大きく、 閾値設定の試行錯誤が必要 — 最初 1 model に絞り、 安定後 3 model に拡大 |
| ROI / 難易度 | 高 / 中 |
| 関連ファイル | `tests/parity/fixtures/golden_audio_corpus.txt` 新規、 `scripts/audio_parity.py` 新規、 `.github/workflows/runtime-parity-deep.yml` 新規 |
| 想定工数 | 4-5 PR (~40h) |

**M2 完了基準**: 2 workflow が dev で稼働、 4 週間 informational で false positive 率 < 5% を観測。 安定後 blocker 化の判断は M3 開始時に再評価。

---

## M3: ABI & Ecosystem Hardening

**期間**: Month 3 (4 週)
**狙い**: semver 違反 / 法務リスク / supply chain 攻撃の 3 軸を塞ぐ。 メンテナンス税は低いが OSS としての信頼性に直結。

### M3.1 — Public ABI snapshot (Top 10 #4)

**実装チケット**: [M3-1-public-abi-snapshot.md](../tickets/M3-1-public-abi-snapshot.md)

| 項目 | 内容 |
|------|------|
| 目的 | C API / Swift / Kotlin の public signature を JSON snapshot 化、 非互換変更で fail |
| 成功基準 | (a) `public-abi-snapshot.yml` が 3 ターゲット (C / Swift / Kotlin) で signature を抽出、 (b) `tests/fixtures/public-abi/{c,swift,kotlin}.json` と diff、 (c) breaking 削除 / 型変更で fail、 追加のみは pass |
| タスク | (1) C: `nm -D libpiper_plus.so \| grep ' T '` + `abi-dumper` で struct layout、 (2) Swift: `swift package describe --type json` + symbol graph、 (3) Kotlin: `binary-compatibility-validator` plugin、 (4) baseline JSON commit、 (5) workflow 構築 |
| 依存 | なし (既存 `cpp-abi-check.yml` `public-api-diff.yml` を継承拡張) |
| リスク | xcframework / AAR の release artifact が PR ごとに生成されないと diff 不可能 — 軽量 build-only path を追加 |
| ROI / 難易度 | 高 / 中 |
| 関連ファイル | `.github/workflows/cpp-abi-check.yml`, `public-api-diff.yml`、 新規 `.github/workflows/public-abi-snapshot.yml`、 `tests/fixtures/public-abi/` |
| 想定工数 | 3 PR (~25h) |

### M3.2 — Model card / license auto-injection (Top 10 #7)

**実装チケット**: [M3-2-license-auto-injection.md](../tickets/M3-2-license-auto-injection.md)

| 項目 | 内容 |
|------|------|
| 目的 | HF release で生成される ONNX 同梱物に LibriTTS-R / AISHELL-3 / CML-TTS / MOE-Speech の attribution を build 時 injection |
| 成功基準 | (a) `release-shared-lib.yml` / `deploy-huggingface.yml` の publish 直前で `MODEL_CARD.md` + `LICENSE_ATTRIBUTIONS.md` を auto-generate、 (b) 6 言語のデータセット出典・ライセンス・話者数を表組み、 (c) HF Hub 上の readme.md template に注入 |
| タスク | (1) `scripts/generate_model_card.py` (CLAUDE.md のデータセット表から抽出)、 (2) `LICENSE_ATTRIBUTIONS.md` template (各 dataset の license + URL + commit hash)、 (3) `release-shared-lib.yml` 末尾に hook、 (4) HF Hub upload 時に metadata 注入 |
| 依存 | なし |
| リスク | データセットの license は時間経過で変わる可能性 — `data-sources.yml` を canonical source として upstream 変更を quarterly review |
| ROI / 難易度 | 中 / 低 |
| 関連ファイル | `CLAUDE.md` (データセット表)、 `release-shared-lib.yml`, `deploy-huggingface.yml`、 新規 `scripts/generate_model_card.py`、 `data-sources.yml` 新規 |
| 想定工数 | 2 PR (~15h) |

### M3.3 — Typosquatting weekly scan (Top 10 #8)

**実装チケット**: [M3-3-typosquatting-watch.md](../tickets/M3-3-typosquatting-watch.md)

| 項目 | 内容 |
|------|------|
| 目的 | PyPI / npm / crates / NuGet / Maven の "piper-pIus" / "piper_plus_g2p" / "piperplus" 類似名を週次 scan、 issue 起票 |
| 成功基準 | (a) `typosquatting-watch.yml` が schedule で 5 registry を polling、 (b) Levenshtein distance ≤ 2 の package を検出、 (c) 新規検出で Issue auto-create (label `security:typosquatting`) |
| タスク | (1) `scripts/check_typosquatting.py` (registry API 経由)、 (2) 既知 false positive 除外リスト (`tests/fixtures/typosquatting-allowlist.json`)、 (3) workflow 構築、 (4) namespace 予約: PyPI `piper_plus` / `piperplus` を placeholder publish (README に「本物はこちら」)、 npm `@piper-plus/*` scope を保護 |
| 依存 | なし |
| リスク | registry API rate limit — 週次 schedule で抑制、 backoff retry を実装。 placeholder publish は OSS audience に誤解を与えないよう README を明確に |
| ROI / 難易度 | 中 / 低 |
| 関連ファイル | 新規 `.github/workflows/typosquatting-watch.yml`、 `scripts/check_typosquatting.py`、 `tests/fixtures/typosquatting-allowlist.json` |
| 想定工数 | 2 PR (~12h) |

**M3 完了基準**: 3 workflow が稼働、 ABI snapshot baseline が commit 済、 model card auto-injection が次回 HF release で動作確認できること。

---

## M4: Informational Tier (任意、 M3 と並走可)

**狙い**: 確率的 / flaky な検査を **PR ブロックせず informational tier** に隔離。 signal noise 蓄積を回避しつつ trend 監視を可能に。

### M4.1 — Loanword / PUA forward-compat fuzz (Top 10 #6)

**実装チケット**: [M4-1-loanword-pua-forward-compat.md](../tickets/M4-1-loanword-pua-forward-compat.md)

`schema_version: 99` のランダム未来フィールドを 7 ランタイムに食わせ、 panic / exception しないことを保証。 `feedback_data_asset_distribution.md` の延長で `forward-compat` を CI 化。

- 成功基準: 既存 loanword / PUA workflow に `--fuzz-future-schema` job 追加、 `continue-on-error: true`
- 工数: 1-2 PR (~10h)
- 関連: `zh-en-loanword-sync.yml`, `pua-consistency.yml`

### M4.2 — Phoneme timing monotonicity property test (Top 10 #9)

**実装チケット**: [M4-2-timing-monotonicity-property.md](../tickets/M4-2-timing-monotonicity-property.md)

任意入力で `start ≤ end` かつ累積単調なことを Hypothesis で 1000 ケース。 **PR ブロックせず informational** に留める。

- 成功基準: `timing-parity.yml` に property test job 追加、 `continue-on-error: true`、 失敗履歴を gh-pages にダッシュボード化
- 工数: 1 PR (~8h)
- 関連: `timing-parity.yml`, `src/python_run/piper/timing.py`

**運用ルール**: informational tier の workflow が **3 ヶ月連続で 1 度も signal を出さなかった場合、 削除候補**。 net flat policy の一環。

---

## M-Stretch: Strategic Bets (Month 4+ 候補)

**Overview チケット**: [M-Stretch-overview.md](../tickets/M-Stretch-overview.md) — S1-S8 候補 (OSS-Fuzz / Bencher / Real-device / SLSA L3 / Distroless / Sanitizer / cross-runtime differential / PR preview) の各々を昇格判定基準とあわせて整理。

Top 10 外の領域で、 unlimited CI を本気で活かすなら検討に値するもの。 親 doc §3 から抜粋。 各々独立した別 milestone として議論可能:

| 候補 | 親 doc §参照 | 期待効果 | 主な障壁 |
|------|-------------|---------|---------|
| OSS-Fuzz 申請 | §3.3 / §3.6 | 24/7 fuzz + 自動 Issue + bug bounty 対象 | 申請 1-2 週間 + harness 整備 |
| Bencher dashboard 導入 | §3.5 | 7 runtime 横断 perf trend / sticky PR comment | 既存 gh-pages baseline からの移行 |
| Real-device farm | §3.4 | iOS / Android / WebKit の発見不能 bug 検出 | サービス契約 (BS / Firebase) の OSS plan 申請 |
| SLSA Build L3 公式 generator 移行 | §3.6 | OpenSSF Scorecard 9.3+ | 5 registry × 2 PR の作業量 |
| Distroless / Chainguard 移行 | §3.6 | container image attack surface 削減 | Dockerfile 7 個の段階的書き換え |
| Sanitizer 拡張 (全 7 runtime) | §3.1 | C++ / Rust UB / leak の網羅 | suppression file の継続メンテ |
| Cross-runtime differential testing 完全版 | §3.2 | 7 項目全部 (golden phoneme / ORT input / SSML AST 等) | 各 runtime に `--dump-*` flag 実装 |
| PR preview + nightly canary | §3.8 | contributor 体験向上 / regression 早期発見 | secret 漏洩リスク設計 |

---

## マイルストーン横断の運用ルール

### 採用判断 checklist (各 M 開始時)

- [ ] 親 doc §4 の批判的観点を再確認 (「追加しない」が default)
- [ ] 含まれる項目が「既存と排他的でない / 既存 gate では構造的に検出不可能 / user-visible damage を防ぐ」の 3 条件のいずれかを満たすか
- [ ] 同月内に削除候補となる既存 workflow があるか (net flat policy)
- [ ] 想定工数が 4 週 / 1 maintainer の容量を超えないか

### 完了判定 checklist (各 M 終了時)

- [ ] 含まれる workflow が dev で 1 週間 green を維持
- [ ] false positive 率 < 5% (informational tier は除く)
- [ ] PR / Issue で contributor から friction 報告がないか
- [ ] 削除候補レビュー実施済み (net flat policy)
- [ ] 親 doc / 関連 spec toml の更新

### 中止判定 (各 M 内で blocker 発生時)

- false positive 率が 20% を超えた場合 → 当該 milestone item を informational tier に降格
- 工数が見積もりの 2 倍を超えた場合 → scope を半減して再見積もり
- contributor friction 報告が 3 件以上出た場合 → 設計再検討

---

## 関連ドキュメント

- [ci-expansion-2026-05.md](./ci-expansion-2026-05.md) — 親調査レポート (30 エージェント統合)
- [`docs/spec/README.md`](../spec/README.md) — 既存 contract spec 一覧
- [`docs/migration/v1.11-to-v1.12.md`](../migration/v1.11-to-v1.12.md) — breaking change 事例
- [`.claude/README.md`](../../.claude/README.md) — 既存 skill / hook / pre-commit gate
- [`CONTRIBUTING.md`](../../CONTRIBUTING.md) — Contribution guidelines (M1.3 で更新予定)

## 変更履歴

| 日付 | 変更 | 関連 PR |
|------|------|---------|
| 2026-05-18 | 初版作成 (30 エージェント調査結果より Top 10 を M1-M3 + M4 + M-Stretch に分解) | — |
| 2026-05-18 | 個別実装チケット 10 本 + 5 overview を [../tickets/](../tickets/README.md) に追加 (4 エージェント並列執筆 / 計 5314 行)、 各 M.X セクションに backlink 追加 | — |
