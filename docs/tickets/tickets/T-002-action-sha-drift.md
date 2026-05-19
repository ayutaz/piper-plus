# T-002: Action SHA drift detector

**チケット ID**: `T-002`
**Milestone**: [M1 Foundations](../milestones/M1-foundations.md)
**Proposal 項目**: `#3b` (Action SHA pin の生存検証)
**Tier**: Tier 1 (informational tier)
**Status**: レビュー待ち
**PR**: (branch ready: `feat/t-002-action-sha-drift`, commit `1004f4f3` — `/create-pr` skill で起票予定)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: なし (T-001 とは独立、 並列実装可能)

---

## 1. タスク目的とゴール

### 目的

PR #511 で `action-pin-gate.yml` (action の SHA pin **形式** 強制 + sliding tag 禁止) が merged された。 しかし「pin された SHA が現在も GitHub 上で生存しているか」 (= dangling / force-pushed / org or repo 削除) は **未検証** で、 supply chain 改竄の検出穴が残っている。 本チケットで GitHub API による生存検証を weekly cadence で実施し、 `action-pin-gate.yml` の形式強制を生存検証で補完する。

informational tier で 4 週間運用後、 false positive が baseline で吸収可能なら blocker 昇格を user に提示する (CON-3.1)。

### ゴール (Done definition)

- [ ] `scripts/check_action_sha_drift.py` を新設し、 全 `.github/workflows/*.yml` から `uses: <action>@<sha>` を抽出し GitHub API で resolve、 dangling / force-pushed を検出 (**FR-3.2**)
- [ ] baseline JSON `scripts/action_sha_baseline.json` を初回 scan で生成、 commit (**FR-3.3**)
- [ ] `.github/workflows/action-sha-drift.yml` を新設 (informational tier、 weekly `0 4 * * 1` + PR base + `workflow_dispatch`) (**FR-3.4**)
- [ ] silent-zero 防止: `total < baseline.expected_total * 0.5` で `::warning::` 発火、 `Collected pins (N actions): ...` を stderr に必須 echo (**FR-3.5** / **AC-3.3**)
- [ ] drift 検出時 Issue auto-create (`label: action-sha-drift`) (**FR-3.6**)
- [ ] GitHub API rate limit 30%+ 余裕 (270 pin × 1 req / 5000 req/h 上限) (**AC-3.2**)
- [ ] workflow wall clock 5 分以内 (**NFR-1.5**)
- [ ] `tests/scripts/test_check_action_sha_drift.py` で silent-zero / dangling / force-pushed の 3 分類 fixture test (**NFR-3.2**)

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `scripts/check_action_sha_drift.py` | 新規 (~100 行) | workflow glob → uses regex 抽出 → GitHub API resolve → markdown report |
| `scripts/action_sha_baseline.json` | 新規 | 初回 scan で生成、 schema_version=1 / expected_total_pins / allowlist / ignore_actions |
| `.github/workflows/action-sha-drift.yml` | 新規 | weekly schedule + PR base + workflow_dispatch、 sticky comment + Issue auto-create |
| `tests/scripts/test_check_action_sha_drift.py` | 新規 | 3 分類 (OK / dangling / force-pushed) + silent-zero fixture test |
| `tests/fixtures/action-sha-drift/baseline_ok.json` | 新規 | 全 pin 生存 fixture |
| `tests/fixtures/action-sha-drift/baseline_half_missing.json` | 新規 | silent-zero pattern fixture (total < expected_total * 0.5) |

### 2.2 入力仕様 (要件定義書 §3.1.3)

| 入力 | 型 | source |
|------|----|----|
| workflow YAML | `string[]` | `.github/workflows/*.yml` (glob) |
| `uses:` ref | `string` (例: `actions/checkout@abc123...`) | regex `uses: ([^\s#]+)@([0-9a-f]{40})` で抽出 |
| baseline JSON | `dict` | `scripts/action_sha_baseline.json` |
| GitHub API response | `dict` | `GET /repos/{owner}/{repo}/commits/{sha}` |

### 2.3 出力仕様 (要件定義書 §3.1.4)

**stdout sticky markdown (PR run 時)**:

```markdown
## Action SHA drift report

**Collected pins (N actions): <list of `org/repo@sha` summary>**

| Action | Pinned SHA | Resolved | Status |
|--------|------------|----------|--------|
| actions/checkout | abc123... | abc123... → tag `v6.0.2` | OK |
| foo/bar | def456... | (404 not found) | **DANGLING** |

Summary: total=270, ok=268, dangling=1, force-pushed=1
```

- **exit code**: 0 = no drift / 1 = drift 検出 (informational tier では `continue-on-error: true` で CI green)
- **`::warning::` 出力条件**: `total < baseline.expected_total * 0.5` (silent-zero 防止、 NFR-5.3 準拠)
- **defensive log (stderr 必須)**: `Collected pins (N actions): actions/checkout@abc123 actions/setup-python@def456 ...`

### 2.4 データ構造 (要件定義書 §3.1.5 / §7.1)

`scripts/action_sha_baseline.json`:

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-19T03:00:00Z",
  "expected_total_pins": 270,
  "allowlist": [
    {
      "action": "actions/checkout",
      "sha": "abc123def4567890abc123def4567890abc12345",
      "resolved_tag": "v6.0.2",
      "verified_at": "2026-05-19T03:00:00Z",
      "note": "(optional) why allowed"
    }
  ],
  "ignore_actions": [
    "unmaintained/some-action"
  ]
}
```

field 定義 (要件定義書 §7.1):

| field | 型 | required | 説明 |
|-------|----|----|------|
| `schema_version` | integer | yes | 現行 1、 schema 変更時 increment |
| `generated_at` | string (ISO8601 UTC) | yes | baseline 生成時刻 |
| `expected_total_pins` | integer | yes | silent-zero 検出用の baseline 値 |
| `allowlist` | array | yes | OK と判定する pin 列 |
| `allowlist[].action` | string | yes | `org/repo` 形式 |
| `allowlist[].sha` | string (40-hex) | yes | pin SHA |
| `allowlist[].resolved_tag` | string | yes | 検証時の tag / branch / `(commit-only)` |
| `allowlist[].verified_at` | string (ISO8601) | yes | 検証時刻 |
| `allowlist[].note` | string | no | 補足 (force-pushed 紛らわしい case 等) |
| `ignore_actions` | array of string | yes | 監視対象外 (`org/repo` のみ、 SHA 問わず) |

### 2.5 処理シーケンス (要件定義書 §3.1.6)

```text
1. checkout repo                                  # actions/checkout@v6.0.2 (pin)
2. setup-python (3.13)                            # actions/setup-python@v5.6.0
3. pip install requests
4. python scripts/check_action_sha_drift.py
   a. glob .github/workflows/*.yml
   b. regex `uses: ([^\s#]+)@([0-9a-f]{40})` で抽出
   c. baseline JSON load
   d. 各 SHA を GET /repos/{owner}/{repo}/commits/{sha} で resolve
      - 200 OK + tag/branch 紐付け → ok
      - 200 OK だが tag/branch なし → dangling
      - 404 → force-pushed 疑い (要追加調査、 dangling として report)
   e. silent-zero check: total < expected_total * 0.5 なら stderr に ::warning::
   f. defensive log "Collected pins (N actions): ..." を stderr に必ず echo
   g. markdown report 生成
   h. summary を artifact upload
5. PR run: marocchino/sticky-pull-request-comment@v2.9.4 で投稿 (header: action-sha-drift)
6. drift 検出時 + scheduled run: gh issue create --label action-sha-drift
```

### 2.6 既存資産との接続 (要件定義書 §3.1.9)

- **流用**: `scripts/check_action_pins.py` の REPO_ROOT / WORKFLOW_DIR / `USES_RE` / `SHA_RE` 定数と classify 関数の構造をコピー (重複は許容、 既存 script を改変しない)
- **共存**: `action-pin-gate.yml` (形式強制) と `action-sha-drift.yml` (生存検証) は併存、 trigger / paths が異なるため衝突なし
- **再利用**: `marocchino/sticky-pull-request-comment@v2.9.4` (既存 `runtime-parity-deep.yml` と同一 version)、 `header: action-sha-drift` で sticky 区別
- **artifact 命名**: `action-sha-drift-${{ github.run_id }}` (`runtime-parity-deep` pattern 踏襲)
- **baseline 形式**: `scripts/action_pins_baseline.txt` (既存、 plain text) とは別 schema (本チケットは JSON)、 用途が異なるため併存

### 2.7 トリガー / concurrency

| 項目 | 値 |
|------|----|
| trigger | `schedule` + `pull_request` + `workflow_dispatch` |
| paths filter | `.github/workflows/**.yml`, `scripts/check_action_sha_drift.py`, `scripts/action_sha_baseline.json` |
| schedule | `0 4 * * 1` (月曜 04:00 UTC、 T-001 と 1 時間ずらし) |
| concurrency | `action-sha-drift-${{ github.head_ref \|\| github.ref }}` |
| permissions | `contents: read`, `pull-requests: write` (sticky), `issues: write` (auto-create) |

### 2.8 エラーケース / 例外処理 (要件定義書 §3.1.8)

| ケース | 期待動作 |
|-------|---------|
| GitHub API rate limit 到達 | `time.sleep(60)` + 最大 3 回 retry、 全失敗で exit 2 (informational tier では noop) |
| baseline JSON 不在 | 初回 scan で生成、 `--update-baseline` flag 必要時に明示 (UC-3.3) |
| `uses: ./.github/actions/...` (ローカル composite action) | classify=`local`、 検証対象外 |
| `uses: foo/bar@release/v1` (release branch ref) | SHA pin 形式違反、 `action-pin-gate.yml` 側で既に block 済みのため本 script はスキップ |
| pin total が baseline の半分未満 | silent-zero check が `::warning::` 発火、 fixture test で再現 (AC-3.3) |
| `unmaintained/some-action` (組織削除) | baseline `ignore_actions` で許容 (CON-3.2) |

---

## 3. エージェントチームの役割と人数

> 並列実装可能な単位で agent team を構成。 silent-zero pattern と baseline 形式の dual review が必要。

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | core logic 実装 | `scripts/check_action_sha_drift.py`, `.github/workflows/action-sha-drift.yml` |
| **Test author** | 1 | fixture + unit test | `tests/scripts/test_check_action_sha_drift.py`, fixture 2 件 (baseline_ok / baseline_half_missing) |
| **Spec / Doc author** | 1 | baseline JSON 設計 + docstring | `scripts/action_sha_baseline.json` 初回生成、 schema field 定義 docstring |
| **Reviewer** | 1 | cross-cutting consistency | silent-zero pattern review、 sticky template (要件定義書 §6.1) 一致確認、 `permissions:` least privilege |

**並列度**: Implementer と Test author は **interface 合意後に並列** 可。 Spec/Doc author は baseline JSON 設計が先行 → Implementer に渡す。

**Agent prompt の与え方**:

1. Spec/Doc author が baseline JSON schema (要件定義書 §7.1) を canonicalize、 初回 baseline は実 repo を scan して生成 (270 pin 想定)
2. general-purpose agent 2 並列 (Implementer / Test author) — interface は「`check_action_sha_drift(baseline_path, workflows_dir) -> Report`」 で合意
3. main agent (Reviewer) が要件定義書 §6.1 sticky comment template との一致を grep で確認、 silent-zero unit test の assert 内容を review

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- 全 `.github/workflows/*.yml` の `uses: <action>@<sha>` 生存検証 (FR-3.2)
- baseline JSON による既知 OK の吸収 (FR-3.3)
- silent-zero 防御 (`Collected pins (N): ...` 必須 echo、 半分未満で `::warning::`)
- drift 検出時 Issue auto-create (FR-3.6)
- sticky comment 投稿 (PR run 時)
- workflow_dispatch `--update-baseline` flag で baseline 再生成 (UC-3.3)

**Out of scope**:

- `uses: ./.github/actions/...` (ローカル composite) の検証 (検証対象外、 §3.1.8)
- SHA 形式チェック (`action-pin-gate.yml` 既存責務)
- third-party action の license / security audit (別軸)
- blocker tier 昇格 (CON-3.1、 4 週間運用後 user 判断)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `check_action_sha_drift:resolve_sha` | API mock: 200 OK + tag 紐付け | classify=`ok`、 `resolved_tag` 反映 |
| UT-2 | `check_action_sha_drift:resolve_sha` | API mock: 200 OK + tag なし | classify=`dangling` |
| UT-3 | `check_action_sha_drift:resolve_sha` | API mock: 404 not found | classify=`force-pushed` |
| UT-4 | `check_action_sha_drift:main` | fixture `baseline_half_missing.json` (silent-zero pattern: total=100 < expected_total=270 * 0.5) | stderr に `::warning::` + `Collected pins (100)` |
| UT-5 | `check_action_sha_drift:main` | baseline 不在 + `--update-baseline` | baseline JSON 新規生成、 expected_total_pins が現 pin 数と一致 |
| UT-6 | sticky markdown template | 3 pin (ok=1, dangling=1, force-pushed=1) fixture | 要件定義書 §3.1.4 markdown と byte-for-byte 一致 |
| UT-7 | `ignore_actions` 適用 | baseline `ignore_actions: ["unmaintained/some-action"]` + 該当 pin | classify=`ignored`、 summary に含まれず |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full workflow run (実 GitHub API) | `workflow_dispatch` で 270 pin 全部 resolve、 wall clock < 5 min (NFR-1.5)、 rate limit 余裕 30%+ |
| E2E-2 | PR base trigger | 新 action 追加 PR で sticky comment が `header: action-sha-drift` で投稿される |
| E2E-3 | silent-zero 再現 | fixture 経由で baseline の半分未満 → `::warning::` 発火、 CI log に `Collected pins (N): ...` |
| E2E-4 | drift 検出 → Issue auto-create | dangling fixture で run、 Issue body が要件定義書 §6.2 format 準拠 |

### 4.4 リグレッション確認

- [ ] `pre-commit run --all-files` が 30 秒以内 (NFR-1.2、 本チケットは workflow + script + baseline JSON のみで pre-commit hook 不要)
- [ ] 既存 `action-pin-gate.yml` の動作に影響しない (read-only な生存検証で SHA 形式は触らない)
- [ ] silent-zero 防御: `Collected pins (N): ...` が stderr に出力 (UT-4 で再現)
- [ ] GitHub API rate limit 30%+ 余裕 (E2E-1)
- [ ] sticky comment `header: action-sha-drift` が `runtime-parity-deep` 等の他 sticky と衝突しない

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | GitHub API rate limit 5000 req/h 圧迫 | 270 pin × 1 req = 5.4% 使用、 30%+ 余裕は確保 (AC-3.2)。 weekly cadence で月 1080 req / 月 5000 req/h × 24h × 30 = 3.6M の 0.03% | E2E-1 で rate limit response header 監視 |
| C-2 | silent-zero pattern 再発 (`total=0` が success 扱い) | `total < expected_total * 0.5` で `::warning::`、 fixture test で再現 (UT-4) | UT-4 が fail すれば即検出 |
| C-3 | org / repo 削除 (`unmaintained/some-action`) と force-push attack の区別困難 | trend 化 + `ignore_actions` allowlist で運用 (CON-3.2) | weekly run の Issue 集計 |
| C-4 | baseline JSON の手動メンテ漏れ → false positive | `--update-baseline` flag で半自動更新 (UC-3.3)、 PR review で baseline diff 確認 | baseline JSON の git history |
| C-5 | `action-pin-gate.yml` baseline (`scripts/action_pins_baseline.txt`) との混同 | 形式 (plain text vs JSON) が異なるため file 名で区別、 docs/spec に補完関係を明記 | review |
| C-6 | API token (`GITHUB_TOKEN`) の scope 過剰 | `contents: read` + `pull-requests: write` + `issues: write` のみ、 `actions: read` は不要 (workflow ファイル自体の git checkout で十分) | review |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern を踏んでいないか (`Collected pins: 0` が success にならないか)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か (本 workflow 自身も)
- [ ] `permissions:` が least privilege か (`contents: read` + `pull-requests: write` + `issues: write`)
- [ ] paths filter が **誤検出しない / 取り漏れしない** (`.github/workflows/**.yml` で composite action 配下は除外)
- [ ] sticky comment が「期待値 vs 実測値」 を明示しているか (`expected_total_pins` vs `total`)
- [ ] fixture が intentional violation を再現できるか (UT-4 silent-zero)
- [ ] markdownlint / ruff / codespell 全 pass
- [ ] 既存 `action-pin-gate.yml` / `check_action_pins.py` との重複は流用扱いで OK (改変はしない)
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠

---

## 6. 一から作り直すとしたら

### 案 A: GitHub API ではなく `git ls-remote` で resolve する

- **概要**: 各 action repo に対して `git ls-remote https://github.com/<owner>/<repo>.git` で全 ref を取得し、 pin SHA が含まれるかを local check。 GitHub API token / rate limit 不要
- **長所**: rate limit から完全に解放 (270 pin × `git ls-remote` は ~30 秒で完了想定) / GitHub Enterprise migration 等で API 不安定でも動作 / API token scope 検討不要
- **短所**: `git ls-remote` は tag/branch の HEAD しか返さない → reachability check (SHA が commit graph に含まれるか) には `git clone --depth=1` が追加で必要 / shallow clone でも 270 repo × 5MB = 1.35GB の cache が膨らむ / force-pushed 検出は API より粗い (API は commit metadata で判断可能)
- **採否**: **現時点では採用しない**。 API rate limit は 5.4% 使用で余裕大、 API の方が force-pushed 検出が精密。 v2 設計時に rate limit が逼迫 (e.g. monorepo 化で pin 数 1000+) すれば再評価。

### 案 B: 全 SHA を baseline に list する vs `ignore_actions` だけ list する

- **概要**: 現設計は baseline `allowlist` に全 OK pin を列挙する明示的 allowlist。 代替案は逆で、 baseline には `ignore_actions` のみ列挙し、 「未知の action は API resolve、 resolved できれば OK」 という deny-list 方式
- **長所**: baseline メンテ cost が大幅減 (270 → 数件) / 新 action 追加時に baseline 更新 PR 不要 / `--update-baseline` flag 不要
- **短所**: 「過去には OK だったが今 force-pushed」 のケース検出が困難 (allowlist の `verified_at` が消える) / 「baseline 半分未満」 silent-zero 検出の母数 `expected_total_pins` の根拠が弱くなる / informational → blocker 昇格時の証跡が薄い
- **採否**: **現時点では採用しない**。 silent-zero pattern (NFR-5.3) の防御を最優先するため、 `expected_total_pins` が baseline で固定されている方が安全。 v2 では「allowlist 必須項目」 を `verified_at` のみに簡略化する余地あり (resolved_tag は API で都度取得)。

### 結論

現時点での選択は **GitHub API resolve + 明示的 allowlist baseline** (rate limit 余裕 + silent-zero 防御 + force-pushed 精度の 3 軸でバランス)。 v2 設計時には案 A (`git ls-remote`) を rate limit 逼迫時に、 案 B (deny-list) を baseline メンテ cost が問題化した時に再評価。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: M2 の T-004〜T-008 (spec sync gate × 5) — 本チケットの baseline JSON shape (`schema_version` + `expected_total_<unit>` + `allowlist`) を canonical として `release-versions.toml` / `model-sha256-manifest.toml` の baseline shape に流用 (M1 milestone 申し送り §6 M2 へ)
- **連携 milestone**: M3 (Supply Chain) — Distroless / SLSA L3 で新 action 大量追加が予想されるため、 baseline 更新 cadence を M1 merged 時に確立しておくこと (M1 milestone 申し送り §6 M3 へ)
- **依存解消**: 本チケット完了で M2 / M3 の baseline 設計に直接 input

### 7.2 引き継ぎ事項 (Handoff)

> 本チケットで判明した「次の人が知らないとハマる」 情報。

- baseline 生成は `workflow_dispatch` で `--update-baseline` flag を渡す必要がある (UC-3.3)。 自動更新は branch protection で禁止
- `expected_total_pins` は手動更新が必須。 新 action 大量追加時に「半分未満で `::warning::`」 の閾値が機能しなくなるため、 baseline 更新 PR で必ず更新
- `ignore_actions` は `org/repo` 単位 (SHA 問わず)、 force-pushed 疑いの紛らわしい case は `allowlist[].note` に記録
- sticky comment `header: action-sha-drift` は他 sticky (`runtime-parity-deep` 等) と区別必須。 wording は要件定義書 §6.1 を canonical に
- GitHub API token は `GITHUB_TOKEN` で十分 (Personal Access Token / Fine-grained 不要)、 scope は `contents: read` で OK
- weekly schedule `0 4 * * 1` (月曜 04:00 UTC) は T-001 (`0 3 * * 1`) と 1 時間ずらして同時 queue 圧迫を回避

### 7.3 未解決の質問

- [ ] 270 pin の `expected_total_pins` 初期値は実 scan に依存。 M3 で大量追加されると baseline 更新が頻繁になるが、 自動更新 PR の可否は user 判断
- [ ] dangling 検出時の Issue auto-create が weekly 1 回発火するが、 同じ dangling action が継続する場合の重複 Issue 抑制 (label search で skip ?) は v2 検討

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.3 (FR-3.2 / FR-3.3 / FR-3.4 / FR-3.5 / FR-3.6 / AC-3.1〜AC-3.3 / CON-3.1〜CON-3.2 / DEP-3.2)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §3.1 (3b SHA drift、 §3.1.3〜§3.1.4 / §3.1.5 / §3.1.6 / §3.1.7 / §3.1.8 / §3.1.9) / §7.1 (baseline JSON field 定義)
- 関連 workflow (補完): `.github/workflows/action-pin-gate.yml` (PR #511 merged、 形式強制)
- 関連 script (流用元): `scripts/check_action_pins.py` (REPO_ROOT / `USES_RE` / `SHA_RE` / classify 関数)
- 関連 baseline: `scripts/action_pins_baseline.txt` (既存、 plain text、 形式が異なるため併存)
- インタフェース仕様: 要件定義書 §6.1 sticky comment format / §6.2 Issue auto-create format / §6.3 baseline JSON schema 汎用

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
| 2026-05-19 | 実装完了 (commit `1004f4f3` on `feat/t-002-action-sha-drift`)。 14 unit test pass。 実 repo は SHA pin **3 use / 2 種類** (dawidd6 + mymindstorm)、 初期 baseline は gh api で 2 entry を生存確認済み。 expected_total_pins=3 で silent-zero defence 動作確認済み。 | Claude Code |
