# T-009: doc examples audit (PR-A)

**チケット ID**: `T-009`
**Milestone**: [M2 Spec & Docs Gates](../milestones/M2-spec-and-docs.md)
**Proposal 項目**: `#7-A` (Code example execution test — audit phase)
**Tier**: (audit only、 gate 化は T-010 / T-011)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: なし (M2 内で T-004〜T-008 と並列着手可)

---

## 1. タスク目的とゴール

### 目的

`#7` (Code example execution test) の 3 phase chain の最初の phase。 既存 `docs/` 配下 `~150 .md` の fenced code block を全件抽出し、 「実行可能 / placeholder 必要 / skip 妥当」 の 3 カテゴリに分類する audit を完了する。 audit 結果は後続 T-010 (doctest informational gate) が consume する canonical 入力となり、 audit 結果なしで T-010 の skip directive が設計できないため、 chain の起点として独立 PR で先行実施する。

既存 `scripts/check_readme_code_examples.py` (シンボル grep ベース) は「README 公開 API 名が impl に存在するか」 を保守的に守る別目的で、 **置換しない** (CON-7.1)。 本チケットでは「実行可否」 の audit のみ行う。

### ゴール (Done definition)

- [ ] `scripts/check_doc_examples.py --audit` で `docs/` 配下全 fenced code block を 6 言語 (`bash` / `python` / `rust` / `csharp` / `go` / `wasm`) 別に抽出 (AC-7.1)
- [ ] 全 block を 3 カテゴリ (`executable` / `needs_placeholder` / `skip_warranted`) に分類した JSON output を生成
- [ ] カテゴリ別 (3 カテゴリ) に分割した GitHub Issue を auto-create (件数別、 M2-R4 緩和)
- [ ] audit 結果 JSON を `tests/fixtures/doc_examples_audit/audit.json` に commit (T-010 の skip directive 入力として参照)
- [ ] FR-7.3 placeholder 規約 (推奨案 `<{var}>` 形式) を audit 結果から user 判断材料として ticket に提示
- [ ] 既存 `check_readme_code_examples.py` を **置換せず**、 補完関係を `docs/spec/short-text-contract.toml` と同階層の (新規) `docs/spec/doc-examples-contract.toml` に明記
- [ ] silent-zero 防御: `Collected blocks (N=...): bash=A python=B ...` を必ず stderr に出力 (NFR-5.3、 phase 2 argparse bug の教訓)

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `scripts/check_doc_examples.py` | 新規 | audit subcommand を含む top-level entry (~250 行、 T-010 で execute mode を追加) |
| `scripts/doc_examples/__init__.py` | 新規 | module init |
| `scripts/doc_examples/extractor.py` | 新規 | fenced block 抽出 (markdown-it-py 利用 / GFM 準拠) |
| `scripts/doc_examples/classifier.py` | 新規 | 3 カテゴリ分類 logic (placeholder pattern / skip directive / executable 判定) |
| `tests/scripts/test_check_doc_examples_audit.py` | 新規 | fixture-based unit test (silent-zero 再現を含む) |
| `tests/fixtures/doc_examples_audit/sample_docs/` | 新規 | 3 カテゴリ各 2 件の fixture markdown |
| `tests/fixtures/doc_examples_audit/audit.json` | 新規 | audit 結果 JSON canonical snapshot (本 PR で初回生成、 後続 PR で更新) |
| `docs/spec/doc-examples-contract.toml` | 新規 | placeholder 規約 / skip directive 規約 / category 定義の spec contract |
| `docs/tickets/tickets/T-009-doc-examples-audit.md` | 新規 | 本ファイル |

### 2.2 処理シーケンス

```text
1. docs/**.md を glob (除外: .claude/, node_modules/, build/, target/)
2. markdown-it-py で fenced code block を parse (info string から言語特定)
3. block ごとに classifier.py で 3 カテゴリ判定:
   a. placeholder pattern (`<path>` / `<{var}>` / `YOUR_*`) 含む → needs_placeholder
   b. directive `# doctest:skip` / `# noexec` あり → skip_warranted
   c. 環境依存 (`/data/piper/...` absolute path / GPU 必須 / nvidia-smi / wandb login) → skip_warranted
   d. 上記いずれにも該当しない → executable (T-010 が実 subprocess 実行候補とする)
4. JSON output 生成 (schema は §2.3)
5. silent-zero 防御: `Collected blocks (N): bash=A python=B rust=C csharp=D go=E wasm=F` を stderr に echo
   集計 0 件 (markdown extraction 失敗) は ::warning:: を立てる
6. --create-issue 指定時に gh CLI で 3 カテゴリ × Issue label で auto-create
   (`audit:executable` / `audit:placeholder` / `audit:skip`)
```

### 2.3 output JSON schema

`tests/fixtures/doc_examples_audit/audit.json` の構造:

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-19T10:00:00Z",
  "totals": {
    "executable": 42,
    "needs_placeholder": 73,
    "skip_warranted": 35,
    "total": 150
  },
  "by_language": {
    "bash": {"executable": 12, "needs_placeholder": 30, "skip_warranted": 10},
    "python": {"executable": 18, "needs_placeholder": 15, "skip_warranted": 8}
  },
  "blocks": [
    {
      "file": "docs/guides/home-assistant.md",
      "line_start": 42,
      "line_end": 58,
      "language": "bash",
      "category": "needs_placeholder",
      "suggested_action": "wrap_with_doctest_skip_until_t011",
      "placeholders_detected": ["<HA_TOKEN>", "<your-pi-ip>"],
      "directives_detected": [],
      "env_dependencies": [],
      "hash_sha1": "abc123..."
    }
  ]
}
```

**T-010 が consume する path**: `tests/fixtures/doc_examples_audit/audit.json` (固定)。 T-010 は `blocks[].category == "executable"` のみ実行候補に取り、 `needs_placeholder` / `skip_warranted` は skip。 file + line_start + hash_sha1 の triple で「audit 後に block が変更された」 を検出可 (T-010 で stale audit 警告)。

### 2.4 Issue auto-create logic

3 カテゴリ × 言語 6 種で最大 18 Issue を作成すると review fatigue (M2-R4) になるため、 以下の strategy:

- **executable** カテゴリ: 1 Issue にまとめる (label `audit:executable`、 件数を本文に table 化)
- **needs_placeholder** カテゴリ: 言語別 6 Issue (label `audit:placeholder lang:<lang>`、 各 ~10-15 件の bullet list)
- **skip_warranted** カテゴリ: 1 Issue にまとめる (label `audit:skip`、 skip 理由別 sub-bullet)

合計 8 Issue (1 + 6 + 1)。 user は category 単位で承認 / 修正指示。

### 2.5 既存資産との接続

- **流用**: `markdown-it-py` (link-check.yml で既使用), `platform_utils.force_utf8_output` (scripts/ 共通)
- **共存**: `scripts/check_readme_code_examples.py` (シンボル grep、 公開 API 名 drift 検出) は別目的 / 別 entrypoint で維持
- **補完関係**: `docs/spec/doc-examples-contract.toml` で「symbol grep gate (既存) vs execution audit gate (本 PR)」 の役割分担を spec 化

---

## 3. エージェントチームの役割と人数

> audit 対象が `~150 .md / ~500+ fenced block` と大きく、 並列化メリットが高い。 runtime 別 audit を 4-5 worker に分散。

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer (extractor)** | 1 | markdown parsing / glob / `extractor.py` | `scripts/doc_examples/extractor.py` |
| **Implementer (classifier)** | 1 | 3 カテゴリ分類 logic / placeholder pattern / directive parser | `scripts/doc_examples/classifier.py` |
| **Auditor (bash / python)** | 1 | bash + python block の手動レビュー (suggested_action 検証) | audit JSON 内の bash + python entry |
| **Auditor (rust / csharp / go / wasm)** | 1 | 残 4 言語の手動レビュー | audit JSON 内の rust + csharp + go + wasm entry |
| **Test author** | 1 | fixture markdown + unit test + silent-zero 再現 | `tests/scripts/test_check_doc_examples_audit.py` |
| **Spec / Doc author** | 1 | `doc-examples-contract.toml` + ticket header の placeholder 規約推奨 | `docs/spec/doc-examples-contract.toml` |
| **Reviewer** | 1 | cross-cutting (audit JSON schema が T-010 の入力に matching するか) | review |

**並列度**: 4-5 worker 同時実行可。 Implementer (extractor) → Implementer (classifier) は逐次 (classifier が extractor の output を消費)、 Auditor 2 名は extractor + classifier の最小動作品が出てから並列開始。 Test author は fixture を先に用意し、 Implementer の TDD 入力にする。

**Agent prompt の与え方**: Explore subagent で既存 `check_readme_code_examples.py` と `markdown-it-py` 利用箇所を先に dump、 general-purpose で extractor / classifier / auditor を並列、 最後に main agent で audit JSON を generate して Issue 化案を user に提示 (Issue auto-create は user 承認後)。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `scripts/check_doc_examples.py --audit` の audit mode
- 3 カテゴリ分類 logic と JSON output
- fixture-based unit test (silent-zero 含む)
- `docs/spec/doc-examples-contract.toml` で skip directive / placeholder 規約を declarative 化
- audit 結果 JSON の commit と Issue auto-create

**Out of scope**:

- 実 subprocess 実行 (T-010 PR-B)
- blocker 化判定 (T-011 PR-C)
- `check_readme_code_examples.py` の置換 (CON-7.1)
- placeholder 規約の最終決定 (FR-7.3 user 判断、 本 PR は推奨案提示まで)
- ONNX model fixture の Actions cache 化 (T-010 で実装)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `extractor.extract_blocks()` | 1 ファイル内に bash 3 / python 2 / rust 1 fenced block | 6 block の list、 各 line_start / line_end / language が正 |
| UT-2 | `classifier.classify()` | block 本文に `<HA_TOKEN>` 含む | `needs_placeholder`、 placeholders_detected に `<HA_TOKEN>` |
| UT-3 | `classifier.classify()` | block の先頭に `# doctest:skip` | `skip_warranted`、 directives_detected に `doctest:skip` |
| UT-4 | `classifier.classify()` | block 本文に `/data/piper/output-*/` absolute path | `skip_warranted`、 env_dependencies に `/data/piper/` |
| UT-5 | `classifier.classify()` | placeholder / directive / env dep いずれもない普通の python | `executable` |
| UT-6 (silent-zero) | `check_doc_examples.py --audit` | fixture docs に block 0 件 (glob mismatched) | exit 1、 stderr に `::warning::Collected blocks: 0` |
| UT-7 (silent-zero) | `check_doc_examples.py --audit` | fixture docs の bash block 数が「期待値の半分以下」 | `::warning::` 出力 (NFR-5.3) |
| UT-8 | JSON schema | output が `schema_version: 1` 含み、 `tests/fixtures/doc_examples_audit/audit.schema.json` を pass | `jsonschema.validate` exit 0 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full repo audit (`docs/` 全件) | `python scripts/check_doc_examples.py --audit --output /tmp/audit.json` → exit 0 + JSON 生成 |
| E2E-2 | audit 後 `audit.json` を再生成 → diff 0 (idempotent) | `diff tests/fixtures/doc_examples_audit/audit.json /tmp/audit2.json` |
| E2E-3 | Issue auto-create dry-run | `--create-issue --dry-run` で 8 Issue body が console 出力、 実 Issue 作成なし |
| E2E-4 | stale block 検出 | fixture docs の 1 block を編集 → hash_sha1 変化を audit が検出 |

### 4.4 リグレッション確認

- [ ] 既存 `pre-commit run --all-files` が 30 秒以内 (NFR-1.2)、 audit script は pre-commit には含めない (重いため weekly schedule のみ)
- [ ] 既存 `check_readme_code_examples.py` の動作不変 (`pytest tests/scripts/test_check_readme_code_examples.py` 全 pass)
- [ ] 既存 `link-check.yml` workflow と `concurrency` group 衝突なし
- [ ] silent-zero 防御: `Collected blocks: N` が stderr に出力 (UT-6 / UT-7)

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | audit 結果が「実行可能」 と判定したのに T-010 で実行すると CI flake | env_dependencies 判定を保守的に (ONNX model / GPU / network 必須は全て skip 寄せ)、 ambiguous は `needs_placeholder` に寄せる | T-010 informational tier 1 ヶ月観測で false positive 集計 (AC-7.2) |
| C-2 | fenced block の info string が `bash` / `shell` / `sh` で揺れている | extractor で alias 正規化 (`sh` / `shell` → `bash`、 `js` / `javascript` → `wasm`) | UT で alias テスト |
| C-3 | markdown 内の inline html (`<pre><code>...`) は extractor が拾えない | scope 外と明示、 GFM fenced block (` ``` `) のみ対象 | `docs/spec/doc-examples-contract.toml` に明記 |
| C-4 | audit 後の docs 編集で hash_sha1 が変わると T-010 が stale flag を立てる | T-010 で stale 検出時の挙動 (re-audit 要求) を `doc-examples-contract.toml` に予約 | T-010 連携 |
| C-5 | Issue auto-create が user 承認なしで 8 Issue 作成すると noisy | `--create-issue` flag は user が明示的に指定するときのみ、 default は dry-run | hook で `gh issue create` を guard (既存 `.claude/hooks/guard-bash.sh` 連動) |
| C-6 | classifier の env_dependencies pattern が false negative (例: `~/.cache/huggingface/`) | spec toml に pattern list を declarative 化、 user が追記可能 | spec gate と本 check 自身の self-test |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern を踏んでいないか (`Collected blocks: 0` が success にならないか UT-6)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か (本 PR は workflow 追加なし、 ただし将来 T-010 で必要)
- [ ] `permissions:` が least privilege か (本 PR は workflow 追加なし)
- [ ] `paths:` filter は **本 PR では不要** (workflow 追加なし、 audit は手動 / weekly のみ。 T-010 で `paths: docs/**` を導入)
- [ ] audit JSON の schema が T-010 (`scripts/check_doc_examples.py --execute`) の入力 schema に一致するか
- [ ] fixture が intentional violation (各カテゴリ各 2 件以上) を再現できるか
- [ ] markdownlint / ruff / codespell 全 pass
- [ ] 既存 `check_readme_code_examples.py` との重複検証なし、 `doc-examples-contract.toml` で補完関係を spec 化
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠しているか
- [ ] Issue auto-create は dry-run default、 user 明示承認後のみ実行

---

## 6. 一から作り直すとしたら

### 案 A: audit を 1 PR で一括 vs runtime 別に分割

- **概要**: 本 PR は「audit script + JSON 全件生成」 を 1 PR で完結させているが、 runtime 別に PR を切る案 (bash audit PR / python audit PR / rust audit PR / ...)
- **長所**: 各 PR の review burden が小さい (~10 ファイル変更)、 言語別 reviewer assign が可能
- **短所**: classifier / extractor が共通基盤、 6 PR の interleaved merge で base branch が unstable に、 JSON schema breakage を抑える効果は薄い (本 PR は schema を `schema_version: 1` で pinning しているため再 ship 不要)
- **採否**: 現方針 (1 PR 一括) を維持。 runtime 別の Issue 分割 (Issue 8 件) で review burden は分散できる

### 案 B: 3 カテゴリではなく fine-grained tag system

- **概要**: `executable` / `needs_placeholder` / `skip_warranted` の 3 値 enum ではなく、 tag セット (`[needs_onnx_model, needs_gpu, has_placeholder_path, has_secret_var]` 等) を block ごとに付与する設計
- **長所**: T-010 で「ONNX cache 改善後は実行可能」 「GPU 不要に書き換え可能」 等の二次判定が可能、 audit を再実行せずに promotion logic を変えられる
- **短所**: tag 体系の合意形成が user 判断項目を増やす (FR-7.3 と同等の追加判断)、 T-010 の実装が複雑化
- **採否**: v1 では 3 値 enum を維持、 v2 (`schema_version: 2`) で tag 体系に migration の余地を残す (`tags: []` を schema に予約フィールドとして追加検討)

### 案 C: doctest 規約を `<{var}>` ではなく Jinja2 `{{var}}` で統一

- **概要**: FR-7.3 の placeholder 規約に Jinja2 syntax (`{{var}}`) を採用、 既存 docs の placeholder を mass edit
- **長所**: Jinja2 は Python 標準的、 既存 ansible / mkdocs プロジェクトと親和性、 IDE の syntax highlight 効く
- **短所**: bash / rust / csharp の `{{` `}}` は format-string / template-literal で competing syntax、 既存 `~150 .md` の mass edit が破壊的
- **採否**: v1 では `<{var}>` 形式 (FR-7.3 推奨案) を維持、 ただし audit 結果で「現状の placeholder 形式 distribution」 を計測し user 判断材料とする (本 PR の audit.json で `placeholders_detected` を集計)

### 結論

現時点での選択は **案 A の現方針 (1 PR 一括 audit)** + **案 B の v2 予約** + **案 C は audit データに基づく user 判断**。 audit 結果が出た後の retrospective で v2 設計を再評価。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-010 (doc examples informational gate)、 T-011 (blocker 昇格判定)
- **連携 milestone**: M2 (本チケット含む) → M4 mkdocs (T-022) で「docs site の code example が必ず実行可能」 の前提に使われる
- **依存解消**: 本チケット merge で T-010 の blockedBy が外れる

### 7.2 引き継ぎ事項 (Handoff)

> 本チケットで判明した「次の人が知らないとハマる」 情報。 T-010 が consume する具体的な path / schema を明記する。

- **audit JSON path**: `tests/fixtures/doc_examples_audit/audit.json` (固定)。 T-010 はこの path を `--audit-input` で参照する。 path 変更時は T-010 も同時更新
- **schema_version**: 1。 break する変更は `schema_version: 2` への bump + 旧版 loader 維持 (forward-compat)
- **block 特定の triple**: `(file, line_start, hash_sha1)` で識別。 docs 編集で line 番号は変動するため、 T-010 では hash_sha1 を primary key 扱い
- **executable 判定の保守性**: ambiguous (network / cache / env var) は全て `needs_placeholder` に寄せている。 T-010 で false positive が出たら本 PR の classifier で skip 寄せに調整
- **Issue auto-create の運用**: 本 PR の Issue 8 件 (executable 1 / placeholder 6 / skip 1) を user が category 単位で triage、 close 不要な Issue は label `wontfix` で永続化
- **placeholder 規約 (FR-7.3) の決定 timing**: audit JSON の `placeholders_detected` 統計を見て user が決定。 本 PR では推奨案 (`<{var}>` 形式) のみ提示、 ticket header に「user 判断待ち」 と明記

### 7.3 未解決の質問

- [ ] placeholder 規約の確定 (FR-7.3、 user 判断、 T-010 着手前に決定必須)
- [ ] Issue auto-create を user が実行するか、 audit JSON を見て手動 Issue 化するか (運用判断)
- [ ] `docs/proposals/` 配下の fenced block も audit 対象とするか (proposal は draft 性質で例が変動的、 skip 推奨)
- [ ] `.claude/` 配下の SKILL.md fenced block も対象とするか (skill instruction で実行されない例も多い、 skip 推奨)

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.7 (FR-7.1〜7.6 / AC-7.1〜7.4 / CON-7.1〜7.2 / DEP-7.1〜7.2)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.2 (`#7` overview、 audit phase の着目点)
- 既存資産: [`scripts/check_readme_code_examples.py`](../../../scripts/check_readme_code_examples.py) (シンボル grep gate、 本 PR で置換しない)
- 関連 spec (新規): `docs/spec/doc-examples-contract.toml`
- 親 milestone: [`../milestones/M2-spec-and-docs.md`](../milestones/M2-spec-and-docs.md)
- 後続: [`T-010-doc-examples-gate.md`](T-010-doc-examples-gate.md), [`T-011-doc-examples-blocker.md`](T-011-doc-examples-blocker.md)

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
