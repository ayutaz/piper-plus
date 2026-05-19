# T-001: Sigstore Rekor verify workflow

**チケット ID**: `T-001`
**Milestone**: [M1 Foundations](../milestones/M1-foundations.md)
**Proposal 項目**: `#3a` (Sigstore Rekor transparency log 検証)
**Tier**: Tier 1 (informational tier)
**Status**: レビュー待ち
**PR**: (branch ready: `feat/t-001-rekor-verify`, commit `571a7a8e` — `/create-pr` skill で起票予定)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: なし (PR #511 で `cosign-release-artifacts.yml` が発行側として merged 済み)

---

## 1. タスク目的とゴール

### 目的

PR #511 で `cosign-release-artifacts.yml` が release artifact の cosign 署名を **発行** する側として実装されたが、 **検証** 側 (Rekor transparency log での再検証) が未整備のため、 発行 → 検証の双方向化が成立していない。 本チケットで verify workflow を新設し、 「自前 release artifact が attacker 改竄を受けていないこと」 を weekly cadence で証明し続ける状態を作る。

informational tier で 4 週間運用後、 false positive が 0 件であれば blocker 昇格を user に提示する (CON-3.1)。

### ゴール (Done definition)

- [ ] `.github/workflows/rekor-verify.yml` を新設し、 weekly schedule (`0 3 * * 1`) で直近 N=10 release の cosign 署名を Rekor transparency log で再検証する (**FR-3.1**)
- [ ] 「cosign 導入前の古い release」 は skip 条件分岐で除外する (**AC-3.4**)
- [ ] 全 10 release で `cosign verify-blob` exit 0 を達成 (**AC-3.4**)
- [ ] silent-zero 防止: `gh release list` 0 件のとき `::warning::` 発火 + `Collected releases (N): ...` を stderr に echo (**FR-3.5**)
- [ ] verify 失敗時 Issue auto-create (`label: rekor-verify-failure`) (**FR-3.6**)
- [ ] workflow wall clock 10 分以内 (**NFR-1.1**)
- [ ] PR #511 の `cosign sign-blob` invocation と `certificate-identity-regexp` / `certificate-oidc-issuer` を一字一句 mirror (**M1-R3**)

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `.github/workflows/rekor-verify.yml` | 新規 | schedule `0 3 * * 1` + `workflow_dispatch`、 ubuntu-24.04、 cosign installer |
| `scripts/verify_rekor_releases.py` | 新規 | gh release list → 10 件 loop → cosign verify-blob → markdown report 集約 |
| `tests/scripts/test_verify_rekor_releases.py` | 新規 | fixture-based unit test (golden release / silent-zero / 古い release skip) |
| `tests/fixtures/rekor-verify/golden_release.json` | 新規 | 検証成功 fixture (release_tag / assets / sig / pem / expected_verify=pass) |
| `tests/fixtures/rekor-verify/legacy_release.json` | 新規 | cosign 導入前 fixture (sig 不在 → skip 判定) |

### 2.2 処理シーケンス

```text
1. checkout repo                                              # actions/checkout@v6.0.2 (pin)
2. install cosign                                             # sigstore/cosign-installer@v3.X (SHA pin)
3. release_list = gh release list -L 10 --json tagName -q '.[].tagName'
4. silent-zero guard: len(release_list) == 0 なら
     - stderr "::warning::Collected releases (0): empty release_list"
     - exit 2 (informational tier では noop だが log は残す)
5. for tag in release_list:
   a. gh release download $tag --pattern '*.tar.gz' --pattern '*.sig' --pattern '*.pem'
   b. .sig / .pem 不在の release は skip (cosign 導入前)、 status=skipped で記録
   c. cosign verify-blob \
        --rekor-url https://rekor.sigstore.dev \
        --certificate-identity-regexp "<PR #511 と同一>" \
        --certificate-oidc-issuer https://token.actions.githubusercontent.com \
        --signature <sig> --certificate <pem> <artifact>
   d. 結果を /tmp/rekor-report.md に append
6. defensive log: "Collected releases (N): tag=v1.13.0 status=pass tag=v1.12.0 status=pass ..." を stderr に必ず echo
7. exit code 集計: 全 pass → 0 / 1+ fail → 1 (informational tier では continue-on-error: true で CI green)
8. artifact upload (rekor-verify-report-${{ github.run_id }})
9. 1+ fail 時: gh issue create --label rekor-verify-failure --title "[rekor-verify] <N> release verify failed"
```

### 2.3 入力仕様 (要件定義書 §3.1.3)

| 入力 | 型 | source |
|------|----|----|
| release tag list | `string[]` | `gh release list -L 10 --json tagName` |
| artifact URL | `string` | `gh release view <tag> --json assets` |
| `.sig` / `.pem` | `bytes` | release asset (PR #511 cosign 生成) |

### 2.4 出力仕様 (要件定義書 §3.1.4)

- **artifact**: `rekor-verify-report.md` (markdown 表、 release × verify status)
- **stderr 必須 log**: `Verified releases (N total): tag=v1.13.0 status=pass ...`
- **exit code**: 0 = 全 pass / 1 = いずれかの release verify 失敗 (informational tier では 1 でも CI green)
- **Issue auto-create 条件**: 1+ release が verify 失敗 (label: `rekor-verify-failure`)

### 2.5 既存資産との接続

- **流用**: `cosign-release-artifacts.yml` (PR #511) の `certificate-identity-regexp` / `certificate-oidc-issuer` を **そのまま mirror** (drift 防止のため grep で抽出して一致確認)
- **共存**: PR #511 が「発行」、 本チケットが「検証」 として 1 pair を構成
- **補完関係**: `action-pin-gate.yml` (action SHA 形式強制) / T-002 (action SHA 生存検証) とは独立軸 (release artifact vs 入力 action)
- **再利用**: cosign installer SHA pin は PR #511 と同一 version 必須

### 2.6 トリガー / concurrency

| 項目 | 値 |
|------|----|
| trigger | `schedule` + `workflow_dispatch` |
| paths filter | — (release は path 非依存) |
| schedule | `0 3 * * 1` (月曜 03:00 UTC) |
| concurrency | `rekor-verify-${{ github.run_id }}` (concurrent 不可) |
| permissions | `contents: read`, `issues: write` (Issue auto-create 用) |

### 2.7 エラーケース / 例外処理 (要件定義書 §3.1.8)

| ケース | 期待動作 |
|-------|---------|
| `cosign verify-blob` exit ≠ 0 | release を「verify 失敗」 として記録、 ループ継続 (1 失敗で全体停止しない) |
| `.sig` / `.pem` 不在 (cosign 導入前 release) | skipped で記録、 verify 試行せず |
| `gh release list` 0 件 | silent-zero check が `::warning::` を発火、 informational tier では continue |
| cosign installer download 失敗 | 最大 3 回 retry (`actions/cache` + network 起因対策)、 全失敗で workflow fail |

---

## 3. エージェントチームの役割と人数

> 並列実装可能な単位で agent team を構成。 各 agent は独立して動作し、 不整合は merge 前 review で検出する。

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | core logic 実装 | `scripts/verify_rekor_releases.py`, `.github/workflows/rekor-verify.yml` |
| **Test author** | 1 | fixture + unit test | `tests/scripts/test_verify_rekor_releases.py`, `tests/fixtures/rekor-verify/*.json` |
| **Spec / Doc author** | 1 | PR #511 mirror 確認 + docstring | `cosign sign-blob` invocation の grep 確認、 verify_rekor_releases.py docstring |
| **Reviewer** | 1 | cross-cutting consistency | M1-R3 (PR #511 mirror)、 silent-zero pattern、 `permissions:` least privilege review |

**並列度**: Implementer と Test author は **並列実行可** (script の interface (関数シグネチャ + return 型) を先に合意してから着手すれば独立)。 Spec/Doc author は両者の deliverable を最後に統合。

**Agent prompt の与え方**:

1. Explore subagent で PR #511 (`cosign-release-artifacts.yml`) を dump させ、 `certificate-identity-regexp` / `certificate-oidc-issuer` の literal string を抽出
2. general-purpose agent を 2 並列 (Implementer / Test author) で起動、 interface を共有して並列実装
3. main agent で M1-R3 mirror 確認 + sticky comment (該当しないが Issue template) wording の review

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- 直近 N=10 release の cosign 署名検証 (FR-3.1)
- cosign 導入前 release の skip 条件分岐 (AC-3.4)
- silent-zero 防御 (`Collected releases (N): ...` 必須 echo)
- verify 失敗時 Issue auto-create (FR-3.6)
- weekly schedule + workflow_dispatch (UC-3.5 incident response)

**Out of scope**:

- blocker tier 昇格判定 (CON-3.1、 4 週間運用後に user 判断)
- Rekor 以外の transparency log 利用 (notation など) → §6 「一から作り直すとしたら」 で検討
- 自前 release 以外の third-party artifact 検証 (T-002 / action SHA drift 担当)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `verify_rekor_releases.py:main` | golden_release.json (sig + pem + artifact 揃い) | exit 0、 status=pass、 stderr に `Collected releases (1): ...` |
| UT-2 | `verify_rekor_releases.py:main` | legacy_release.json (sig 不在) | exit 0、 status=skipped、 verify 試行なし |
| UT-3 | `verify_rekor_releases.py:main` | release_list 空 (silent-zero pattern) | exit 2、 stderr に `::warning::` + `Collected releases (0): ...` |
| UT-4 | `verify_rekor_releases.py:main` | sig 改竄 fixture (cosign verify 失敗) | exit 1、 status=fail、 Issue body 生成内容を assert |
| UT-5 | sticky / Issue body template | fixture 3 release (pass/skipped/fail 各 1) | 期待 markdown を string equal で assert |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full workflow run (weekly schedule simulation) | `workflow_dispatch` で実行し、 直近 10 release を実 cosign verify、 wall clock < 10 min |
| E2E-2 | cosign 導入前 release が混在 | 古い release tag (v1.0〜v1.4 等) を含む 10 件で run、 skipped カウントを assert |
| E2E-3 | sig 改竄 simulation | fixture release を test repo に置き、 verify 失敗 → Issue auto-create を assert |

### 4.4 リグレッション確認

- [ ] `pre-commit run --all-files` が 30 秒以内 (NFR-1.2、 本チケットは script 追加のみで pre-commit hook 不要)
- [ ] PR #511 `cosign-release-artifacts.yml` の動作に影響しない (read-only な検証側)
- [ ] silent-zero 防御: `Collected releases (N): ...` が stderr に出力 (UT-3 で再現)
- [ ] cosign installer SHA pin が PR #511 と同一 version

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | PR #511 の `certificate-identity-regexp` と微妙に drift し、 全 release が verify 失敗 (silent total failure) | 実装時に PR #511 を grep して一字一句 mirror、 review で再確認 | E2E-1 で実 verify 成功を確認 |
| C-2 | Rekor sigstore.dev の availability 障害 → silent CI fail | informational tier (`continue-on-error: true`)、 3 連続失敗で Issue auto-create | weekly run の trend を `gh run list` で監視 |
| C-3 | cosign installer の `@v3.X` sliding tag → SHA pin で固定 | `action-pin-gate.yml` で強制、 baseline 一致確認 | 既存 gate |
| C-4 | release が 0 件 (新規 repo 時) で silent skip | silent-zero guard で `::warning::` + 明示 log | UT-3 |
| C-5 | gh release download の rate limit | 直近 10 release × ~5 file/release = 50 download/run、 weekly cadence なら問題なし | NFR-1.3 観測 |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern を踏んでいないか (`Collected releases: 0` が success にならないか)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か (sliding `@v<major>` 禁止) — cosign installer / actions/checkout / actions/setup-python
- [ ] `permissions:` が least privilege か (`contents: read` + `issues: write` のみ)
- [ ] `certificate-identity-regexp` / `certificate-oidc-issuer` が PR #511 と一字一句一致
- [ ] Issue body template が要件定義書 §6.2 format 準拠
- [ ] fixture が intentional violation を再現できるか (UT-4 sig 改竄)
- [ ] markdownlint / ruff / codespell 全 pass
- [ ] 既存 `cosign-release-artifacts.yml` / `action-pin-gate.yml` との重複なし
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠

---

## 6. 一から作り直すとしたら

> 既存実装 / 既存ドキュメントから離れて、 同じ目的を達成する別アプローチを 1-2 案、 思考実験として記載。

### 案 A: Rekor verify を release workflow 側で生成時に同梱する

- **概要**: `cosign-release-artifacts.yml` (発行側) で `cosign sign-blob` の直後に `cosign verify-blob` を実行し、 verify-blob ログを `.verify-receipt` ファイルとして release asset に同梱する。 検証側は `.verify-receipt` を download して inspect するのみ (cosign 不要)
- **長所**: 検証側 CI で cosign installer 不要 → wall clock 大幅短縮 / Rekor 障害が verify 側に影響しない / 「発行時に検証済み」 の事実が release artifact に刻まれる (supply chain provenance)
- **短所**: 発行後の Rekor entry tamper を検出できない (Rekor は append-only だが log server 自体が compromised なら…) / `.verify-receipt` 自体を sign しない限り mutable / PR #511 の release workflow 改変が必要
- **採否**: **現時点では採用しない**。 PR #511 が既に merged で改変 cost が大きく、 検証側のみで完結する設計の方が「PR #511 と分離して安全に着手可能」。 SLSA L3 (M3) で release workflow 改変するタイミングで再評価。

### 案 B: cosign 以外の sig verifier 採用 (notation など)

- **概要**: CNCF Notation (OCI artifact signing) で署名し、 OCI registry (ghcr.io) に store。 verify は `notation verify` で実行
- **長所**: OCI ecosystem との統合 (Distroless / Chainguard 移行 M3 と相性) / public good infrastructure (sigstore.dev) への依存削減
- **短所**: piper-plus は OCI artifact ではなく `.tar.gz` 配布 → registry に store するのは無理筋 / cosign + Rekor は SLSA L3 attestation の de facto standard、 移行は M3 全体に波及
- **採否**: **採用しない**。 cosign + Rekor は SLSA L3 と直結し M3 で利用するため、 ここで別 stack を導入すると分断する。

### 結論

現時点での選択は **既存 cosign + Rekor stack の検証側追加** (案として記載した代替を採用せず)。 v2 設計時には案 A (`.verify-receipt` 同梱) を release workflow 改変のタイミングで再評価する余地あり。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-017 (M3 SLSA L3 shared-lib) — 本チケットの `cosign verify-blob` 経路が定着していれば SLSA attestation 検証も同 pattern で実装可能
- **連携 milestone**: M3 (Supply Chain) — Rekor verify が4週間 informational で安定すれば、 SLSA verifier も同じ運用 pattern を踏襲できる
- **依存解消**: 本チケット完了で T-002 / T-003 とは独立、 M2 / M3 への blocker は無し (informational tier で並走)

### 7.2 引き継ぎ事項 (Handoff)

> 本チケットで判明した「次の人が知らないとハマる」 情報。 git history では拾えない context を残す。

- `certificate-identity-regexp` は PR #511 の `cosign-release-artifacts.yml` を **canonical source** として grep 抽出する。 直接 hardcode せず、 review 時に 1 字ずつ確認すること (M1-R3)
- cosign 導入前 release (`v1.0`〜`v1.4` 等) は `.sig` / `.pem` 不在 → skip 条件分岐が必須。 skip と fail を混同しないこと
- weekly schedule `0 3 * * 1` (月曜 03:00 UTC) は T-002 (`0 4 * * 1`) と 1 時間ずらし、 同時刻 GitHub Actions queue 圧迫を回避
- Rekor sigstore.dev は public good infrastructure で **availability SLA 無し**。 単発 fail は false positive 扱い、 3 連続 fail で Issue 化を目安に
- 4 週間 informational 観測後、 blocker 昇格判定は user に提示 (CON-3.1)。 自律的に blocker 化しないこと

### 7.3 未解決の質問

- [ ] release N=10 件は妥当か (FR-3.1)。 古い release が多い repo では skipped 多発になるが、 「直近 10 件」 の cadence は事故時 incident response (UC-3.5) でも妥当か
- [ ] cosign installer の version update (e.g. v3.X → v3.Y) を Dependabot に任せるか、 手動 bump にするか

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.3 (FR-3.1 / FR-3.5 / FR-3.6 / AC-3.4 / CON-3.1 / DEP-3.1)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §3.1 (3a Rekor verify、 §3.1.3〜§3.1.4 / §3.1.6 / §3.1.7 / §3.1.8 / §3.1.9)
- 関連 workflow (発行側): `.github/workflows/cosign-release-artifacts.yml` (PR #511 merged)
- 関連 workflow (本チケット): `.github/workflows/rekor-verify.yml` (新規)
- 関連 spec: なし (本チケットは workflow + script のみで spec toml は不要)
- インタフェース仕様: 要件定義書 §6.2 Issue auto-create format

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
| 2026-05-19 | 実装完了 (commit `571a7a8e` on `feat/t-001-rekor-verify`)。 PR #511 mirror assert 込み 15 unit test pass。 PR 起票は `/create-pr` skill 実行待ち。 | Claude Code |
