# M2: Spec & Docs Gates (Tier 2)

**Milestone ID**: `M2`
**Tier**: Tier 2
**Status**: 計画中
**期間目安**: M1 merge 後 〜 4 週間 (8 チケット × 半日〜1 日)
**前提**: M1 完了 (T-002 baseline 形式 / sticky template 確立、 silent-zero pattern 学習済み)

---

## 1. 目的

M1 で確立した「informational tier + silent-zero 防御」 パターンを **spec sync gate (`#5`)** と **doc examples gate (`#7`)** に展開する:

- **#5 spec sync gate × 5**: `docs/spec/*.toml` の残カバレッジ穴 5 件 (release-versions / model-sha256-manifest / artifact-retention / swift-g2p / test-flake-retry) を 1 spec / 1 PR で個別 gate 化
- **#7 doc examples × 3 phase**: PR-A (audit) → PR-B (informational) → PR-C (blocker 昇格) の段階的着手

M2 終了時点で `docs/spec/` のカバレッジ穴は **0**、 doc examples は 1 ヶ月の informational 観測後に user 判断で blocker 化候補。

---

## 2. 配下チケット

| ID | タイトル | 提案項目 | Tier | Status | PR |
|----|--------|---------|------|--------|----|
| [T-004](../tickets/T-004-release-versions-spec.md) | `release-versions.toml` gate | `#5-1` | blocker | 計画中 | — |
| [T-005](../tickets/T-005-model-sha256-spec.md) | `model-sha256-manifest.toml` gate | `#5-2` | blocker | 計画中 | — |
| [T-006](../tickets/T-006-artifact-retention-spec.md) | `artifact-retention-contract.toml` gate | `#5-3` | blocker | 計画中 | — |
| [T-007](../tickets/T-007-swift-g2p-spec.md) | `swift-g2p-contract.toml` gate | `#5-4` | blocker | 計画中 | — |
| [T-008](../tickets/T-008-test-flake-retry-spec.md) | `test-flake-retry-contract.toml` gate | `#5-5` | blocker | 計画中 | — |
| [T-009](../tickets/T-009-doc-examples-audit.md) | doc examples audit (PR-A) | `#7-A` | (audit only) | 計画中 | — |
| [T-010](../tickets/T-010-doc-examples-gate.md) | doc examples gate (PR-B) | `#7-B` | informational | 計画中 | — |
| [T-011](../tickets/T-011-doc-examples-blocker.md) | doc examples blocker 昇格 (PR-C) | `#7-C` | blocker (user 判断) | 計画中 | — |

### 依存関係

- T-004〜T-008 互いに独立、 並列可 (推奨実装順は ROI: T-004 → T-005 → T-006 → T-007 → T-008)
- T-009 → T-010 → T-011 は逐次 (T-010 は audit 結果で skip directive 設定が必要、 T-011 は T-010 の 1 ヶ月観測が前提)
- T-009 と T-004〜T-008 は並列可

---

## 3. 受け入れ基準 (Milestone レベル)

- [ ] `docs/spec/` のカバレッジ穴 5 → 0 (T-004〜T-008 全 merged)
- [ ] 各 spec gate が fixture-based intentional violation 検出 → exit 1 / 修正後 exit 0 (AC-5.1)
- [ ] `pre-commit run --all-files` 30 秒以内維持 (NFR-1.2、 5 gate 追加後も超過しない)
- [ ] T-009 audit で全 fenced code block を 3 カテゴリ (実行可能 / placeholder 必要 / skip 妥当) に分類済み Issue 化
- [ ] T-010 informational tier 1 ヶ月運用で false positive 5% 以下 (AC-7.2)
- [ ] T-011 blocker 昇格 / 据え置きが user 判断として明示

---

## 4. 一から作り直すとしたら (Phase rethink)

### 設計思考: spec contract toml の universal validator は本当に作れないのか

要求定義 CON-5.1 は 「universal な validator は構造的に作れない、 個別実装が現実解」 と結論付けている。 これは 31 spec の経験則として正しいが、 **「spec 側を universal にできない」 と 「validator 側を universal にできない」 は別問題** という整理が抜けている。

代替案 A: **spec 自体に validator pluggable 化**

```toml
# docs/spec/release-versions.toml
[meta]
schema_version = 1
canonical = "git-tag"
validator = "scripts/validators/git_tag_snapshot.py"
validator_args = { tag_pattern = "^v\\d+\\.\\d+\\.\\d+$" }

[snapshot]
v1.12.0 = { pypi = "1.12.0", nuget = "0.3.0", crates = "0.4.0" }
```

`scripts/check_spec_contract.py` は spec を load し、 `[meta].validator` を dynamic import して `validate(spec_data, args)` を呼ぶだけ。

#### 長所

- 全 spec gate が 1 entrypoint (`check_spec_contract.py`) を経由 → silent-zero pattern を 1 箇所で防御
- 新 spec 追加 cost は「validator script を 1 つ書く」 のみ
- spec ↔ validator の対応関係が spec 自体に書かれ、 docs と impl が物理的に近接

#### 短所

- spec が「**docs**」 から「**動作可能なデータ + コード参照**」 に意味的に変質 → 「spec = 不変条件の宣言」 という単純さが失われる
- validator script の path がリポジトリ移動・rename 時に spec 側の breakage を招く
- 既存 26 spec の retrofitting コストが高い (M2 で 5 spec を新規追加するタイミングでないと採用機会がない)

#### 結論

**v1 では現方針 (1 spec / 1 check script の個別実装) を維持**。 M2 で 5 件追加した後、 「実装後に validator pluggable 化のメリットが見えたら、 別 milestone (M5 Spec Framework) として retrofitting PR」 という余地を残す。

### 設計思考: doc examples を runtime CI に統合する vs 専用 workflow

T-010 は `scripts/check_doc_examples.py` を新規 workflow で回す設計。 各 runtime の test と doc examples 実行を「同一 CI job 内」 で実行する代替案がある。

代替案: **runtime ごとの test workflow に doc examples step を組み込む**

```yaml
# python-tests.yml 末尾
- name: Run doc examples (python blocks)
  run: |
    python scripts/check_doc_examples.py --language python --execute
```

#### 長所

- toolchain setup を共有 (Python venv / Rust target / etc. を再利用、 wall clock 削減)
- 「runtime CI が green = runtime + その docs が両方 green」 という 1 signal で release readiness 判定が容易
- T-008 (`test-flake-retry-contract.toml`) で定義する retry policy が doc examples にも自動適用

#### 短所

- 既存 8 runtime CI workflow 全てに改変が必要 (blast radius が大)
- doc examples の failure が runtime test の failure と区別困難 → CI summary の可読性が下がる
- audit (PR-A) phase で「ある block は実行可能 / ある block は placeholder」 という per-block 制御を runtime CI で実装するのは構造的に難しい

#### 結論

**v1 では専用 workflow (`#7` proposal 通り) で開始**。 T-011 で blocker 昇格判定する際、 「実行 latency が 30 分超過していないか」 を測定した上で、 超過していれば runtime CI 統合への移行を別 milestone で検討。

### 設計思考: spec gate の 「post-hoc snapshot」 vs 「pre-impl spec」

要求定義 FR-5.3 で「実装側 canonical const が存在せず、 toml は post-hoc snapshot 用途」 と判明した場合は spec rewrite するとあるが、 そもそも **どの spec が pre-impl で、 どの spec が post-hoc か** を最初から型分類する設計が代替案。

代替案: spec toml の `[meta].direction` field

```toml
[meta]
schema_version = 1
direction = "pre-impl"   # spec が canonical、 impl が mirror
# direction = "post-hoc"  # impl (例: git tag) が canonical、 toml が snapshot
```

`pre-impl` spec の gate は **impl が spec と一致しているか** を検証 (spec → impl の方向)。 `post-hoc` spec の gate は **toml が impl の現状と一致しているか** を検証 (impl → toml の方向、 toml 更新を要求するタイプ)。

#### 長所

- spec の意味的 ambiguity (canonical どっち) が解消、 検証方向が宣言的
- T-004 (`release-versions.toml` = post-hoc 候補) と T-005 (`model-sha256-manifest.toml` = pre-impl 候補) が同じ entrypoint で扱える
- M3 SLSA L3 で release workflow が増える際、 release 側の正当性検証が `direction = "post-hoc"` の半自動化対象になる

#### 短所

- `direction` field の意味が「post-hoc は spec を gate が自動更新する (auto-commit)」 か「post-hoc は gate が drift を fail にする (developer に手動更新を要求)」 で運用が分岐 → user の運用判断が要る
- 既存 26 spec の direction を全て 1 PR で分類するのは review burden が大きい

#### 結論

**v1 では direction concept を導入するが、 spec toml 側には反映しない** (T-004〜T-008 の各 ticket 内に「direction = post-hoc/pre-impl」 を文書化のみ)。 spec toml 化は M2 完了後の retrospective で再評価。

---

## 5. リスクと対策 (Milestone 共通)

| ID | リスク | 対策 |
|----|------|------|
| M2-R1 | 5 spec gate 追加で `pre-commit run --all-files` が 30 秒超過 | 各 check script を fast-path 実装 (`changed-files` 限定実行 / cache 利用)、 超過時は pre-push tier に移行 (NFR-1.2) |
| M2-R2 | T-009 audit で「修正可能」 と判定したのに T-010 で実行すると CI flake | ONNX model fixture を Actions cache (~250MB) に乗せる (AC-7.3)、 retry policy を T-008 で gate 化 |
| M2-R3 | T-004 `release-versions.toml` が post-hoc snapshot 設計と判明 → FR-5.3 (spec rewrite) 発動 | T-004 着手前に 30 分の探査 spike で direction 判定、 spike 結果を ticket header に記録 |
| M2-R4 | T-009 audit Issue が大量 (~500 block) で review fatigue | category 別 (実行可能 / placeholder / skip) に分割 Issue 化、 user は category 単位で承認 |

---

## 6. 後続 Milestone への申し送り

### M3 へ

- T-004 (`release-versions.toml`) gate は git tag を canonical 入力とする → M3 SLSA L3 (T-017〜) で `git tag` 抽出 logic を共有 (DEP-5.2)
- T-005 (`model-sha256-manifest.toml`) は HF release の SHA256 を canonical 化 → M3 で SLSA attestation の `subject` に SHA256 が必要になるため、 T-005 完了が SLSA 設計を簡略化する
- T-008 (`test-flake-retry-contract.toml`) の retry policy spec は M3 release workflow が flake 時に retry budget を超過しないかの validation 基準になる

### M4 へ

- T-010 / T-011 (doc examples gate) の運用実績は M4 mkdocs (T-022) で「docs site に表示される code example が必ず実行可能」 という保証の前提
- T-006 (`artifact-retention-contract.toml`) は M4 test aggregation (T-023) で aggregated JSON の retention 期間を決める前提

### post-M2 retrospective へ

- 5 spec gate を実装した結果、 「spec contract universal validator」 を作るべきか / 「direction concept」 を導入すべきかを判断 (本ドキュメント §4 設計思考の再評価)

---

## 7. 関連ドキュメント

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.5 / §4.7
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.1 / §4.2
- 既存 spec [meta] schema: [`scripts/check_spec_meta.py`](../../../scripts/check_spec_meta.py)
- 既存 doc gate: [`scripts/check_readme_code_examples.py`](../../../scripts/check_readme_code_examples.py)
- 親 index: [`../README.md`](../README.md)

---

## 8. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
