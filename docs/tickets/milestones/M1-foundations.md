# M1: Foundations (Tier 1 即着手)

**Milestone ID**: `M1`
**Tier**: Tier 1
**Status**: 計画中
**期間目安**: PR #511 マージ後 〜 1 週間 (各チケット半日 Claude Code 実装)
**前提**: PR #511 (Defensive Foundations) merged

---

## 1. 目的

PR #511 (Defensive Foundations) で意図的に defer された 8 項目のうち、 **単独 PR で完結 / 影響範囲小 / informational tier** という条件を満たすものを最速で着手し、 残 7 項目の議論に必要な data を取り始める。

具体的には:

- 自前 release artifact の **Sigstore Rekor transparency log** での再検証 (T-001) → 発行 (`cosign-release-artifacts.yml`) と検証の双方向化
- 全 workflow の **Action SHA pin の生存検証** (T-002) → `action-pin-gate.yml` の形式強制を補完
- 6 runtime の **CLI `--help` 出力 canonical 化** (T-003) → docs と impl の wording drift を CI 検出

---

## 2. 配下チケット

| ID | タイトル | 提案項目 | Tier | Status | PR |
|----|--------|---------|------|--------|----|
| [T-001](../tickets/T-001-rekor-verify.md) | Rekor verify workflow | `#3a` | informational | 計画中 | — |
| [T-002](../tickets/T-002-action-sha-drift.md) | Action SHA drift detector | `#3b` | informational | 計画中 | — |
| [T-003](../tickets/T-003-cli-help-extract.md) | 6 runtime CLI help auto-extract | `#4` | PR=blocker / weekly=informational | 計画中 | — |

依存関係: T-001 と T-002 は独立、 T-003 は独立。 3 件並列実装可。

---

## 3. 受け入れ基準 (Milestone レベル)

- [ ] 3 チケット全てが merged / informational tier で 1 週間 silent-zero 0 件
- [ ] 新規 workflow 3 件の wall clock 各 10 分以内 (NFR-1.1)
- [ ] `pre-commit run --all-files` の wall clock は 30 秒以内維持 (NFR-1.2)
- [ ] silent-zero 防御パターン (`Collected <unit> (N): ...` defensive log) が 3 workflow 全てに存在
- [ ] fixture-based silent-zero テストが 3 件中 該当 2 件 (T-002 / T-003) で pass

---

## 4. 一から作り直すとしたら (Phase rethink)

> 「PR #511 の learnings を全て持った状態で、 informational tier gate を白紙から設計する」 という思考実験。 現実装が劣っているという意味ではなく、 v2 設計時に評価したい選択肢を残す。

### 設計思考: informational tier gate を 1 つのフレームワークに集約

現在の構造は **gate ごとに workflow + script + baseline + sticky comment 投稿 logic が個別実装** されており、 silent-zero 落とし穴を「全 gate で個別に踏まないように」 注意する必要がある (NFR-5.2 / NFR-5.3 で全 gate に同じ要件を反復)。

代替案: `scripts/lib/informational_gate.py` (~150 行) を共通ライブラリ化し、 以下を 1 箇所に集約:

- baseline JSON load / silent-zero check / `::warning::` 発火
- sticky comment markdown 生成 (template から)
- Issue auto-create (drift 検出時)
- defensive log の `Collected <unit> (N): ...` 出力

各 gate script は `from informational_gate import run_gate; run_gate(name="action-sha-drift", collect=..., compare=...)` で 30 行程度に圧縮。

#### 長所

- silent-zero pattern が「フレームワーク本体の unit test」 1 箇所で保証 (PR #511 phase 2 bug と同型を全 gate で再発防止)
- sticky comment / Issue template の **wording 一貫性** が自動担保
- 新 gate 追加 cost が大幅減 (新 gate = collect function + compare function 2 つだけ)

#### 短所

- 既存 `check_action_pins.py` 等の **再利用性が逆に下がる** (フレームワーク前提の structure)
- 抽象化の早すぎる導入 → gate 間で要求がズレた時に escape hatch が必要 (例: `#3a` Rekor は API 不要、 `#3b` は GitHub API 必須)
- CLAUDE.md の 「Don't add abstractions beyond what the task requires」 と緊張関係

#### 結論

**v1 では現方針 (gate ごと個別実装) を維持**。 M1 で 3 gate を実装した後、 「実際に同じ pattern を 3 回書いたか」 を retrospective し、 真に重複していれば M3 着手前に共通化 (refactor PR)。 v1 を急ぐ理由: PR #511 の learnings を 1 週間内に M2 議論へ持ち込みたい。

### 設計思考: Rekor verify と SHA drift を 1 workflow に統合する

T-001 (Rekor) と T-002 (SHA drift) は **「供給網改竄検出」 という同一目的** を別観点で監視している (発行物 vs 入力依存)。

代替案: `.github/workflows/supply-chain-monitor.yml` の 1 workflow で 2 job (`rekor-verify`, `action-sha-drift`) を持つ構成。

#### 長所

- workflow 数の節約 (3 → 2 で M1 の new workflow 数を 1 削減)
- 「供給網監視」 の単一エントリーポイント (`gh workflow run supply-chain-monitor.yml`)

#### 短所

- schedule の cron が異なる (`0 3 * * 1` vs `0 4 * * 1`) → 同 workflow 内では 1 schedule のみ
- failure 通知の粒度が下がる (どちらの監視が fail したか sticky / Issue で都度区別が必要)
- T-001 と T-002 で要求される `permissions:` が若干違う (Rekor は OIDC `id-token: write` 不要、 SHA drift は GitHub API token のみで OK だが Rekor は cosign installer 経由で latency 高め)

#### 結論

**v1 では別 workflow 推奨**。 schedule の独立性と failure 粒度が分離 cost より重い。 M3 で SLSA / Distroless の supply-chain 軸が増えた段階で「supply-chain-monitor」 として再統合を検討する余地あり。

### 設計思考: CLI help を runtime build 不要で抽出する

T-003 は 6 runtime build を matrix で並列実行する設計。 build cache 利用で wall clock 10 分以内 (NFR-1.4) を狙うが、 release タイミングで toolchain version が更新されると cache miss で +5-10 min。

代替案: 各 runtime の `--help` 出力を **release artifact に同梱** する (release workflow で `<binary> --help > help.txt` を artifact upload)。 CI 側は artifact を download して diff するのみ。

#### 長所

- CI side で build 不要 (wall clock 10 → 1 分以内)
- release artifact 自体が docs の canonical source (release notes との整合性向上)

#### 短所

- release workflow 改変が必要 (M3 / SLSA L3 と coupling、 release path 全部に影響)
- release 前の dev branch では `help.txt` が **stale** (前 release の出力で diff してしまう)
- artifact retention が切れた古い release で help.txt 取得不能

#### 結論

**v1 では build 方式維持**。 release artifact 同梱は SLSA L3 (M3 T-017〜T-021) で release workflow を改変するタイミングで再評価。 M3 完了後の M2 振り返り PR でこちらに移行する選択肢を残す。

---

## 5. リスクと対策 (Milestone 共通)

| ID | リスク | 対策 |
|----|------|------|
| M1-R1 | 3 並列実装で agent team の wording / sticky template が microscopic に drift | template (`docs/tickets/_template.md`) と要件定義書 §6.1 sticky template を canonical 化、 PR review で commenter が 1 文字ずつ確認 |
| M1-R2 | informational tier 4 週間観測中に false positive 多発 → maintainer fatigue | M1 merged 後 2 週間で retrospective PR、 必要なら baseline を一度 reset |
| M1-R3 | PR #511 の `cosign-release-artifacts.yml` (発行側) と T-001 (検証側) で certificate-identity-regexp の wording 不一致 | T-001 実装時に PR #511 の `cosign sign-blob` invocation を grep して identity を一字一句 mirror |

---

## 6. 後続 Milestone への申し送り

### M2 へ

- T-001 / T-002 で確立した **sticky comment template** と **defensive log pattern** を M2 の 5 spec gate (T-004〜T-008) で再利用 (要件定義書 §6.1 が canonical)
- T-003 の sanitize rule TOML (`scripts/sanitize_cli_help_rules.toml`) は spec contract 化を **しない** (`#5` の対象外、 sanitize は spec rewrite を伴わない pure config)
- T-002 の baseline JSON shape (`schema_version` + `expected_total_<unit>` + `allowlist`) を `#5` の `release-versions.toml` / `model-sha256-manifest.toml` の baseline shape に流用

### M3 へ

- T-001 で `cosign verify-blob` の運用が定着している前提で SLSA L3 (T-017〜) に着手 (T-017 PR で T-001 workflow の `permissions:` を参考)
- T-002 の Action SHA baseline は M3 (Distroless / SLSA) で **新 action 大量追加** が予想されるため、 baseline 更新 cadence を M1 merged 時に確立しておく

### M4 へ

- M1 で 4 週間 informational tier の false positive ベースラインを取り、 M4 の test aggregation (T-023) の sticky comment 設計に反映

---

## 7. 関連ドキュメント

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.3 / §4.4
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §3
- 親 index: [`../README.md`](../README.md)

---

## 8. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
