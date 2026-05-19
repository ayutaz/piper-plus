# T-005: `model-sha256-manifest.toml` ↔ HF release / runtime loader 同期 gate

**チケット ID**: `T-005`
**Milestone**: [M2 Spec & Docs Gates](../milestones/M2-spec-and-docs.md)
**Proposal 項目**: `#5-2` (`model-sha256-manifest.toml`)
**Tier**: Tier 2 (blocker、 pre-impl direction)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: T-004 完了 (推奨。 `scripts/_lib/` の共通化を流用するため。 ただし並列着手も可)

---

## 1. タスク目的とゴール

### 目的

`docs/spec/model-sha256-manifest.toml` (既存 snapshot) は HuggingFace Hub の model release SHA256 を canonical source として、 各 runtime の model loader が読み込む manifest との parity を保証することを目的とした spec。 しかし現在は **snapshot 化のみで gate なし**、 runtime 側の loader が古い SHA256 で integrity check を pass し続けるリスクがある (例: HF 側で model が誤った binary に上書きされた場合、 各 runtime は気付けない)。

本 spec の direction は **pre-impl** (spec が canonical、 runtime loader が mirror)。 これは要求定義 §4.1 で「HF release の SHA256 を canonical」 と明記されている通り。 全 8 runtime (Python / Rust / C# / Go / WASM / C++ / Kotlin / Swift G2P) の model loader が `model-sha256-manifest.toml` の SHA256 と byte-for-byte 一致しているかを CI gate / pre-commit hook で強制する。

加えて M3 SLSA L3 (T-017〜T-021) の attestation `subject` 構成に SHA256 が必要 (FR-2.2)、 本 ticket の完了が M3 設計を簡略化する。

### ゴール (Done definition)

- [ ] `scripts/check_model_sha256_manifest.py` (~150 行) を新設、 `model-sha256-manifest.toml` の `[models.<name>].sha256` と各 runtime の model loader 内 hardcoded SHA256 (または HF download integrity 設定) を突合 (FR-5.1, FR-5.2 (a))
- [ ] `.pre-commit-config.yaml` に hook 統合 (`model-sha256-manifest.toml` または対象 runtime loader 変更時のみ走る fast-path) (FR-5.2 (b))
- [ ] `.github/workflows/model-sha256-gate.yml` 新設 または `contract-gates-extended.yml` に job 追加 (FR-5.2 (c))
- [ ] `tests/scripts/test_check_model_sha256_manifest.py` で fixture-based intentional violation を再現 (AC-5.1)
- [ ] `pre-commit run --all-files` の合計 wall clock 30 秒以内維持 (NFR-1.2, AC-5.2)
- [ ] forward-compat: spec の `schema_version: 2` 未来フィールド受理を全 runtime に pin (loanword と同型 pattern)

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `scripts/check_model_sha256_manifest.py` | 新規 | 8 runtime loader と spec toml の SHA256 突合 |
| `tests/scripts/test_check_model_sha256_manifest.py` | 新規 | fixture-based unit test |
| `.github/workflows/model-sha256-gate.yml` | 新規 (または既存 gate に統合) | PR base trigger + weekly schedule |
| `.pre-commit-config.yaml` | 変更 | 新 hook 追加 |
| `docs/spec/model-sha256-manifest.toml` | 変更 (必要時) | `[meta].direction = "pre-impl"` 明文化、 schema_version pin |
| `tests/fixtures/model-sha256/` | 新規 | sample manifest + sample runtime loader stub (drift / aligned) |

### 2.2 処理シーケンス

```text
1. `model-sha256-manifest.toml` を load し `[models.<name>]` table を dict 化 (key=model name, value={sha256, hf_repo, size_bytes, ...})
2. 各 runtime の model loader を AST/regex で scan:
   - Python: `src/python_run/piper/voice.py` 内の hash 定数 or download integrity 引数
   - Rust: `src/rust/piper-core/src/model.rs` 内の `const SHA256_*`
   - C#: `src/csharp/PiperPlus.Core/Models/ModelManifest.cs` 内の dictionary literal
   - Go: `src/go/piperplus/model/manifest.go`
   - WASM: `src/wasm/openjtalk-web/src/model-loader.js`
   - C++: `src/cpp/model_loader.cpp` 内の `kModelSha256`
   - Kotlin: `android/piper-plus-g2p/src/main/kotlin/.../ModelManifest.kt`
   - Swift: `Sources/PiperPlus/ModelManifest.swift`
3. spec ↔ 各 runtime の対応する model entry の SHA256 が一致するか検証
4. 不一致時は exit 1、 一致時は exit 0
5. silent-zero guard: `Collected model entries (runtimes=8, models=N): ...` を必ず stderr に出力 (NFR-3.2)
6. forward-compat: `schema_version > 1` の場合に未知 field を warn せず受理 (loanword mirror 方式)
```

### 2.3 既存資産との接続

- **流用**: `scripts/check_loanword_consistency.py` の forward-compat loader pattern (schema_version 受理 logic) を流用
- **流用**: T-004 で切り出した `scripts/_lib/git_tag.py` は不要だが、 spec [meta] パーサーは `scripts/check_spec_meta.py` の re-export を使う
- **共存**: 既存 model 自動 DL の integrity check (HF download 時の hash 検証) を置換せず、 「spec ↔ loader」 の static drift を別途検出
- **補完関係**: M3 SLSA L3 (T-017 系) で release artifact の attestation `subject` に SHA256 を引用 → 本 spec が SLSA 設計のための pre-requisite

---

## 3. エージェントチームの役割と人数

> spec ↔ 8 runtime loader 突合のため、 runtime 別の loader 探査が並列化しやすい。

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer (core)** | 1 | check script 本体 + spec loader | `scripts/check_model_sha256_manifest.py` |
| **Runtime scanner** | 1 | 8 runtime の loader 抽出 logic (AST/regex pattern dump) | `scripts/_lib/runtime_loader_scan.py` (新規) |
| **Test author** | 1 | fixture + intentional violation 再現 (forward-compat も) | `tests/scripts/test_check_model_sha256_manifest.py`, `tests/fixtures/model-sha256/` |
| **Spec / Doc author** | 1 | [meta] / schema_version pin / workflow YAML | `docs/spec/model-sha256-manifest.toml`, `.github/workflows/model-sha256-gate.yml` |

**並列度**: implementer / runtime scanner / test author / spec author の 4 並列可。 runtime scanner が完了次第 implementer が integrate する逐次依存あり。

**Agent prompt の与え方**: Explore subagent でまず 8 runtime の model loader 抽出 pattern (ファイル path / SHA256 リテラル形式) を dump、 結果を runtime scanner に渡す。 implementer は scanner の出力 API を使う設計に絞り、 8 runtime 個別の rabbit hole に潜らない。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- 8 runtime (Python / Rust / C# / Go / WASM / C++ / Kotlin / Swift G2P) の model loader 内 SHA256 リテラルと spec の突合
- spec の forward-compat schema (loanword 同型 pattern)
- pre-commit hook + workflow gate の 2 系統統合

**Out of scope**:

- HF Hub からの実 download 時の hash 検証 (既存の download path で実施済み、 本 ticket は spec ↔ static loader)
- model 学習・配布 PR (CONTRIBUTING_MODELS.md 範囲)
- T-004 release-versions と coupling する model release tag

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `parse_spec_models` | aligned manifest toml | dict[str, ModelEntry] (N entries) |
| UT-2 | `scan_python_loader` | sample `voice.py` with SHA256 const | dict[model_name, sha256] |
| UT-3 | `scan_rust_loader` | sample `model.rs` with `const SHA256_*` | 同上 |
| UT-4 | `check_alignment` | 8 runtime aligned | exit 0 |
| UT-5 | `check_alignment` | Rust loader のみ SHA256 が旧値 (drift) | exit 1, 差分メッセージに `rust:<model>` を含む |
| UT-6 | `check_alignment` | spec の `[models]` が空 (silent-zero pattern) | `::warning::` 発火 (models=0 ガード) |
| UT-7 | forward-compat | `schema_version: 2` で未知 field 含む spec | exit 0、 未知 field は無視 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full workflow run (PR base trigger) | `workflow_dispatch` で実行 → exit 0 |
| E2E-2 | intentional drift PR (C# loader のみ古い SHA256) | sticky comment が「期待値 `hash-A` vs 実測値 `hash-B`」 を明示 |
| E2E-3 | silent-zero 再現 | fixture で spec の `[models]` を空にして check → `Collected model entries (models=0)` で `::warning::` |
| E2E-4 | new model 追加シナリオ | spec に新 model 追加 + 8 runtime 全てに hash 追加 → gate exit 0 |

### 4.4 リグレッション確認

- [ ] 既存 `pre-commit run --all-files` が 30 秒以内 (NFR-1.2)
- [ ] 既存 `check_loanword_consistency.py` の forward-compat pattern と semantic 一致
- [ ] silent-zero 防御: `Collected model entries (runtimes=N, models=M): ...` が stderr に出力
- [ ] 8 runtime の既存 loader が gate 起動後も全 pass (現状 baseline が aligned)

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | 8 runtime の loader 抽出が AST / regex 混在で fragile (例: C++ の `#define` vs `constexpr`) | runtime scanner の抽出 logic を tests/fixtures で全 runtime 分カバー、 抽出 fail 時は exit 2 (drift とは区別) | UT-2/UT-3 系統で各 runtime 1 件以上 |
| C-2 | spec ↔ HF release の同期は別 path (本 gate ではなく release workflow の責務) | 本 gate は static loader のみ対象と spec [meta] と README で明示 | review |
| C-3 | spec entry 0 件で success の silent-zero | `Collected model entries (models=N): ...` defensive log + UT-6 で再現 | fixture test |
| C-4 | M3 SLSA attestation `subject` 側の SHA256 構成と矛盾するスキーマ変更 | schema_version v1 → v2 への migration policy を spec [meta] に明記、 forward-compat loader で吸収 | UT-7 |
| C-5 | new model 追加 PR の merge 順序 (spec か runtime か先) | spec 先 / runtime 後の cadence を docs/spec/README に明記、 gate は両者 align 後に green | review |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern を踏んでいないか (`models=0` が success にならないか)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か
- [ ] `permissions:` が least privilege か (`contents: read` + `pull-requests: write` のみ)
- [ ] paths filter が **誤検出しない / 取り漏れしない** (8 runtime loader + spec toml を網羅)
- [ ] sticky comment が「期待値 vs 実測値」 (SHA256 prefix 12 char で表示) を明示しているか
- [ ] fixture が intentional violation を再現できるか (UT-5)
- [ ] forward-compat: `schema_version: 2` の未知 field を warn せず受理しているか (UT-7)
- [ ] markdownlint / ruff / codespell 全 pass
- [ ] M3 SLSA L3 設計との整合 (attestation `subject` の SHA256 引用形式を見越したスキーマか)

---

## 6. 一から作り直すとしたら

### 案 A: manifest を Python の data file として配布 (`piper.models.manifest`)

- **概要**: `model-sha256-manifest.toml` を Python の package data として `src/python_run/piper/manifest.toml` に同梱配布。 他 runtime は build 時に Python package から copy (single source of truth)。
- **長所**: physical な single source、 drift が構造的に起き得ない (build pipeline が強制)。 forward-compat 対応も 1 箇所のみ。
- **短所**: Python package を build 依存にする必要があり、 Rust / Go / Swift などの runtime build pipeline に Python 実行を組み込む friction が高い。 OSS contributor が Python なしで runtime を build する選択肢が消える。
- **採否**: 現時点では採用しない (cross-language build pipeline の独立性を維持する方針)。 v2 で「common-assets リポジトリ分離」 等を検討する場合に再評価。

### 案 B: SHA256 ではなく content-addressable hash (例: BLAKE3 や sigstore-style digest) で識別

- **概要**: hashing algorithm を SHA256 から BLAKE3 / `sha2-256` digest URI 形式に置換し、 OCI image manifest や SLSA attestation `subject` と統一 format にする。
- **長所**: M3 SLSA L3 attestation `subject` 構成が容易、 OCI/SLSA エコシステムとの相互運用性向上。 BLAKE3 は性能も SHA256 より高速。
- **短所**: 既存 HF Hub の release が SHA256 ベース、 8 runtime の hash library を BLAKE3 対応に置換する blast radius が大きい。 SHA256 は SLSA L3 でも legitimate な subject digest として通る。
- **採否**: 現時点では採用しない (SHA256 で SLSA L3 が問題なく満たせる)。 M5 以降で content-addressable storage を全 release に導入するなら再評価。

### 結論

現時点での選択は **現方針 (spec が canonical、 8 runtime loader が mirror、 SHA256 hashing)**。 理由: HF Hub と既存 release path の一貫性、 8 runtime 独立 build pipeline の維持、 M3 SLSA L3 に SHA256 で十分。 v2 設計時には案 A (Python package 同梱) を再評価する余地あり。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: M3 SLSA L3 (T-017〜T-021) で attestation `subject` の SHA256 を spec から引用 (本 ticket 完了が pre-requisite)
- **連携 milestone**: M3 (`#2` SLSA L3) FR-2.2 の attestation 生成 logic と coupling
- **依存解消**: 本 ticket 完了で T-017 系 の attestation 設計が単純化 (canonical SHA256 source が確定)

### 7.2 引き継ぎ事項 (Handoff)

> 本 ticket で判明した「次の人が知らないとハマる」 情報。

- **forward-compat loader 必須**: loanword sync gate と同型 pattern (`schema_version: 2` の未知 field を warn せず受理) を全 runtime mirror loader に pin。 これを忘れると将来 schema 変更時に 8 runtime 同時改修が必要になる
- **runtime scanner pattern dump 必須**: 8 runtime の loader 抽出 pattern を `tests/fixtures/model-sha256/loader-samples/` に保管。 新 runtime 追加時はここに sample を追記してから check script を更新
- **new model 追加の cadence**: spec を先に PR → 8 runtime mirror PR (loanword check gate 同様)。 1 PR で全部やると review 負荷が高すぎる
- **SHA256 prefix display**: sticky comment では SHA256 を 12 char prefix で表示 (`a1b2c3d4e5f6`)、 full hash は CI log 内のみ。 PR 本文の可読性確保

### 7.3 未解決の質問

- [ ] new model 追加時の cadence (spec PR 先 vs 8 runtime 同 PR) を README に明記する位置
- [ ] HF Hub 側の hash と spec の同期方法 (手動 / 自動化) は別 ticket か

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.5 (FR-5.1 #5-2, AC-5.1), §4.2 (FR-2.2)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.1 (`model-sha256-manifest.toml`)
- Milestone: [`M2`](../milestones/M2-spec-and-docs.md)
- 関連 spec: `docs/spec/model-sha256-manifest.toml`
- 関連 workflow: `.github/workflows/model-sha256-gate.yml` (新設)
- 関連 ticket: T-004 (`scripts/_lib/` 共有)、 T-017〜T-021 (M3 SLSA L3 attestation `subject` 引用)
- 参考実装: `scripts/check_loanword_consistency.py` (forward-compat loader pattern)

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
