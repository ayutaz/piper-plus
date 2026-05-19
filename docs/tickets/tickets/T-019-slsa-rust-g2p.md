# T-019: SLSA L3 for crates.io (Rust G2P)

**チケット ID**: `T-019`
**Milestone**: [M3 Supply Chain](../milestones/M3-supply-chain.md)
**Proposal 項目**: `#2-3` (`SLSA Build L3 / crates.io`)
**Tier**: Tier 3 (release blast radius、 1 registry / 1 PR)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**:

- M3 milestone 5 件 (T-017 〜 T-021) の **first ticket**。 推奨実装順 T-019 → T-020 → T-021 → T-017 → T-018。
- M1 完了 (`cosign verify-blob` 運用定着、 `cosign-release-artifacts.yml`) と M2 完了 (`release-versions.toml` / `model-sha256-manifest.toml` 整備済み) が前提。
- 本 ticket は SLSA L3 化の **knowledge probe** 役割。 T-020 / T-021 / T-017 / T-018 が follow するため、 取得した運用知見 (subject 構成、 hermetic build の git tag 抽出、 既存 `actions/attest-build-provenance` との共存) を §7 で必ず申し送る。

---

## 1. タスク目的とゴール

### 目的

`g2p-rust-publish.yml` (crates.io publish workflow) を SLSA Build L3 に昇格させる。

PR #511 後の現状:

- 既存 `g2p-rust-publish.yml` は `actions/attest-build-provenance@v3.2.0` で provenance attestation を生成済 (`actions/attestations` API 経由)。 これは SLSA Build L2 相当 (builder isolation 弱い、 hermetic build なし)。
- `slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml` を sub-workflow として呼ぶことで **SLSA L3 (non-falsifiable provenance + isolated builder + hermetic build)** に昇格できる。
- 5 release workflow 中 **crates.io が最も制約少 (GPG 共存なし、 binary platform binding なし、 module tag 操作なし)**。 1 件目として最適 (R-2 = release breakage blast radius 緩和)。

### ゴール (Done definition)

- [ ] **AC-2.1**: 以下コマンドが exit 0 を返す:

  ```bash
  slsa-verifier verify-artifact piper-plus-g2p-'<version>'.crate \
    --provenance-path piper-plus-g2p-'<version>'.crate.intoto.jsonl \
    --source-uri github.com/ayutaz/piper-plus \
    --source-tag rust-g2p-v'<version>'
  ```

- [ ] **AC-2.2**: OpenSSF Scorecard の `Token-Permissions` / `SAST` 以外の項目で score 低下なし (baseline = PR #511 マージ後の Scorecard 値)。
- [ ] `v1.13.0-rc.X` RC release で attestation 生成 + verify exit 0 確認後に prod release。
- [ ] `docs/reference/slsa-verify.md` (新規) で downstream user 検証手順を提供 (FR-2.5、 本 ticket で **初稿** を作成、 残 4 ticket で増補)。
- [ ] hermetic build 化: `workflow_dispatch.inputs.version` 入力は廃止、 `git tag` (`refs/tags/rust-g2p-v*`) から version を抽出する pattern に統一 (FR-2.4)。 既存 workflow は tag-only trigger のため hermetic build は **既存挙動と整合** (差分ゼロ確認のみ)。
- [ ] **既存 `actions/attest-build-provenance` 呼び出しと slsa-github-generator が共存** (どちらの attestation も release asset に upload される、 DEP-2.1)。

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `.github/workflows/g2p-rust-publish.yml` | 変更 | `slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml` を sub-workflow 呼び出し。 hash 計算 step、 provenance upload step を追加 |
| `docs/reference/slsa-verify.md` | 新規 | downstream user 向け `slsa-verifier verify-artifact` 使用法 (本 ticket で **rust-g2p セクションのみ** 初稿、 残 4 ticket で追加) |
| `docs/spec/slsa-provenance-contract.toml` | 新規 (任意) | 5 registry の provenance subject 構成と verifier 期待値の不変条件 (T-021 までに本ファイルが完成、 T-019 では rust 行のみ) |

### 2.2 処理シーケンス

```text
1. tag push (refs/tags/rust-g2p-v<version>) で trigger
2. test job: 既存どおり cargo test (変更なし)
3. publish job:
   a. checkout
   b. setup rust toolchain
   c. tag <-> Cargo.toml version 整合性確認 (既存)
   d. cargo package -p piper-plus-g2p --allow-dirty で .crate 生成 (既存)
   e. *新規*: .crate の sha256 を計算 → outputs.hashes (base64-encoded `<hash>  <filename>` の改行区切り)
   f. *既存維持*: actions/attest-build-provenance@v3.2.0 でも attestation 生成 (DEP-2.1、 共存)
   g. cargo publish (既存)
4. *新規 job* slsa-provenance:
   needs: [publish]
   uses: slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v2.X.X
   with:
     base64-subjects: ${{ needs.publish.outputs.hashes }}
     upload-assets: true   # GitHub Release asset として upload
     provenance-name: piper-plus-g2p-<version>.crate.intoto.jsonl
   permissions:
     id-token: write
     contents: write
     actions: read
5. defensive log: "Generated SLSA L3 provenance for piper-plus-g2p-<version>.crate (subject hash: <sha256>)" を stderr に echo
6. release attestation 生成完了後、 cosign-release-artifacts.yml が release published を trigger に sign-blob (既存、 干渉なし)
```

### 2.3 既存資産との接続

- **流用**: 既存 `g2p-rust-publish.yml` の tag-trigger / cargo package / cargo publish step は **そのまま維持**。 SLSA generator は publish job の後段に **追加 job として並列に attach** する形 (既存 critical path に介入しない)。
- **共存**:
  - `actions/attest-build-provenance@v3.2.0` (既存) と `slsa-github-generator` (新規) を **両方** 動作させる。 前者は GitHub-native attestation API (SLSA L2)、 後者は SLSA L3 reference implementation。 downstream user は両方を持つことで verifier の選択肢が増える (DEP-2.1)。
  - `cosign-release-artifacts.yml` (M1) は release published を trigger に sign-blob する別 workflow。 SLSA generator の attestation upload も release asset として後から cosign 署名対象に含まれる (二重防御)。
- **補完関係**: 形式 (cargo publish) は既存どおり、 検証層 (provenance) のみ強化。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | `g2p-rust-publish.yml` 改変、 hash 計算 step 追加、 slsa generator sub-workflow 呼び出し | workflow YAML |
| **Test author** | 1 | RC release (`v1.13.0-rc.1`) を実行する dry-run plan、 `slsa-verifier` の CI でのテスト (`scripts/test_slsa_verify.sh`) | RC 検証手順 |
| **Spec / Doc author** | 1 | `docs/reference/slsa-verify.md` 初稿 (rust セクション)、 `docs/spec/slsa-provenance-contract.toml` (任意、 T-021 までに完成) | docs |
| **Release engineer** | 1 | crates.io publish の dry-run + 既存 token 権限の SLSA generator 互換確認 (CARGO_REGISTRY_TOKEN は publish job 内のみ、 SLSA generator job は OIDC token で動作) | 運用手順 |
| **Reviewer** | 1 | maintainer による cross-cutting 確認 | review |

**並列度**: Implementer + Doc author は並列実行可、 Release engineer は RC tag round (`v1.13.0-rc.1` → `verify-artifact` 確認 → tag delete → prod) に逐次必要。

**Agent prompt の与え方**:

1. Explore subagent で `slsa-framework/slsa-github-generator` の v2 系 README + `generator_generic_slsa3.yml` の input spec を dump。
2. general-purpose で Implementer + Doc author を並列実行 (依存なし)。
3. main agent で integrate、 RC tag push + `slsa-verifier verify-artifact` 実行。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `g2p-rust-publish.yml` に SLSA L3 generator sub-workflow 追加
- `.crate` artifact に対する provenance attestation 生成 + upload
- `slsa-verifier verify-artifact` exit 0 を確認する RC release round
- `docs/reference/slsa-verify.md` の **rust セクション初稿** (残 4 ticket で順次追加)
- 既存 `attest-build-provenance` との共存維持

**Out of scope**:

- 他 4 registry (T-020 〜 T-018 で対応)
- PyPI / NuGet 新設 (CON-2.1、 user 判断後 T-024 / T-025 として後続 ticket 化)
- `cosign-release-artifacts.yml` の改変 (M1 で完成、 SLSA generator と直交)
- `slsa-verifier` バイナリの downstream 自動配布 (downstream user が `go install github.com/slsa-framework/slsa-verifier/v2/cli/slsa-verifier@latest` で取得する手順を doc に記載するのみ)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `workflow_dispatch.inputs.version` 廃止確認 | `gh workflow run g2p-rust-publish.yml -f version=1.0.0` | input 未定義のため CLI error (hermetic build 強制) |
| UT-2 | hash 計算 step | `target/package/piper-plus-g2p-0.1.0.crate` | sha256 が `base64-subjects` 形式で outputs.hashes に設定 |
| UT-3 | slsa generator sub-workflow 呼び出し | `needs.publish.outputs.hashes` | `*.intoto.jsonl` が release asset として upload |
| UT-4 | 既存 attest-build-provenance との共存 | tag push | 両 attestation が release に存在 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | `v1.13.0-rc.1` tag を push → `g2p-rust-publish.yml` full run | `gh run view <run-id>` で全 job green |
| E2E-2 | release asset から `slsa-verifier verify-artifact` exit 0 | `scripts/test_slsa_verify.sh` (新規) で実行、 CI で artifact download → verify |
| E2E-3 | RC tag delete (`gh release delete v1.13.0-rc.1 --yes; git push --delete origin rust-g2p-v1.13.0-rc.1`) | crates.io には rc release は publish しない (`if: !contains(github.ref, 'rc')` で publish step を skip)、 attestation のみ動作確認 |
| E2E-4 | OpenSSF Scorecard re-run | `gh workflow run scorecard.yml` で baseline 維持確認 |

### 4.4 リグレッション確認

- [ ] 既存 `g2p-rust-publish.yml` の cargo publish が正常動作 (RC release で `--dry-run` 確認)
- [ ] `cosign-release-artifacts.yml` が release published trigger で動作継続 (干渉なし)
- [ ] `actions/attest-build-provenance@v3.2.0` の attestation が release asset に upload 継続
- [ ] silent-zero 防御: `Generated SLSA L3 provenance for ... (subject hash: <sha256>)` を必ず stderr に出力

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | RC tag round で crates.io に rc version を publish してしまう | `cargo publish` step に `if: !contains(github.ref, 'rc')` 条件追加、 SLSA generator のみ動作 | RC dry-run で確認 |
| C-2 | `actions/attest-build-provenance` と `slsa-github-generator` の OIDC token 干渉 | 既存 publish job (`id-token: write`) と new slsa-provenance job (`id-token: write`) は **別 job** で動作、 token 競合なし | workflow job graph |
| C-3 | crates.io 側が `.intoto.jsonl` を asset として認識しない | crates.io は GitHub Release asset と独立 (`cargo publish` のみが crates.io upload)。 `.intoto.jsonl` は GitHub Release asset として配信 (downstream verifier は GH release から download) | 別経路で配布 |
| C-4 | `slsa-github-generator` sub-workflow の version pin が sliding tag | `@vX.Y.Z` 形式で pin (NFR-2.2 / `action-pin-gate.yml`)、 PR レビューで確認 | action-pin-gate.yml |
| C-5 | next 5 ticket への知見漏れ | §7 で hash 計算 logic / subject 構成 / RC tag round 手順を明示申し送り | review checklist |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern を踏んでいないか (`subject hash:` が空文字で success にならないか)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か (`slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v2.X.X` の semver pin、 sliding `@v2` 禁止)
- [ ] `permissions:` が least privilege か (publish job: `contents: read, id-token: write, attestations: write`、 slsa-provenance job: `id-token: write, contents: write, actions: read`)
- [ ] paths filter / trigger が hermetic (tag push のみ、 `workflow_dispatch.inputs.version` 廃止)
- [ ] sticky comment / release notes が `slsa-verifier verify-artifact` コマンド例を含むか (downstream user 向け)
- [ ] RC release で `slsa-verifier verify-artifact` exit 0 を確認したか (AC-2.1 evidence)
- [ ] OpenSSF Scorecard re-run で baseline 維持 (AC-2.2 evidence)
- [ ] 既存 `attest-build-provenance` が共存動作するか (DEP-2.1 evidence)
- [ ] markdownlint MD032 (list around blank line) を全 doc が満たすか
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠しているか

---

## 6. 一から作り直すとしたら

### 案 A: `slsa-github-generator` を使わず自前で in-toto attestation 生成

- **概要**: `in-toto-attestation create --predicate-type https://slsa.dev/provenance/v1 --subject <.crate> --predicate predicate.json > attestation.intoto.jsonl` を直接呼び、 cosign sign-blob で署名。
- **長所**:
  - workflow の自由度が極大 (subject 構成 / predicate 内容を完全制御)
  - sub-workflow への依存ゼロ (`slsa-github-generator` の breaking change 影響を受けない)
- **短所**:
  - `slsa-verifier verify-artifact` の SLSA L3 expectation を満たさない (`--builder-id` が `https://github.com/slsa-framework/slsa-github-generator/...` でないため verify 失敗)
  - OpenSSF Scorecard で `SLSA` 項目 score down (AC-2.2 違反)
  - downstream user が「これは公式 SLSA L3 ではない」 と認識する必要があり、 マーケティング上の意義が消える
- **採否**: 現時点では採用しない。 ただし T-018 (Maven Central) で AAR/JAR classifier subject 設計が複雑化して挫折した場合の fallback として M3 milestone §4 に記録済み。

### 案 B: `cargo-release` 経由で publish + attestation を一括化

- **概要**: `cargo-release` (`crates.io` 専用 release tool) の hook 機構で publish 直前に `slsa-github-generator` 相当の処理を caller workflow にコールバック。
- **長所**:
  - rust ecosystem 標準ツールに集約、 maintainer の認知 cost が低い
  - tag push と cargo publish の同期が自動化 (現行の手動 tag → workflow trigger fall-through を縮約)
- **短所**:
  - `cargo-release` の hook 機構は workflow 内部の job graph と整合せず、 attestation 生成タイミングが post-publish (cargo publish 後) になり、 publish 前 attestation の SLSA L3 要件を満たさない可能性
  - rust 専用、 残 4 ticket (Go / npm / shared-lib / Maven) で同 pattern が使えず統一性ゼロ
- **採否**: 採用しない。 SLSA L3 は publish 前 attestation が前提のため。

### 結論

現時点での選択は **既存 workflow 構造維持 + slsa-github-generator sub-workflow 追加** (案無 = 現方針)。 案 A は M3 milestone §4 で議論済みの fallback で、 T-018 の Maven Central 挫折時に再評価。 v2 設計時は npm 9+ の native `--provenance` (T-021 §6 参照) に倣って `cargo publish --provenance` (将来) が登場した場合に集約検討の余地あり。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-020 (Go) → T-021 (npm) → T-017 (shared-lib) → T-018 (Maven Central)
- **連携 milestone**: M3 (本 milestone 残 4 件) + M4 (`docs/reference/slsa-verify.md` を mkdocs に統合)
- **依存解消**: 本 ticket 完了で T-020 〜 T-018 の「slsa-github-generator 呼び出し pattern が未確立」 unblock

### 7.2 引き継ぎ事項 (Handoff)

> 本ticketで判明した「次の人が知らないとハマる」 情報。 git history では拾えない context を残す。

- **hash 計算 step の base64 encoding**: `slsa-github-generator` の `base64-subjects` input は `<sha256-hex>  <filename>` を **行ごとに 1 subject** で改行区切り、 全体を base64 encode した文字列。 sha256sum 出力をそのまま base64 する。 単一 artifact でも改行 + base64 必須 (空 base64 だと silent-zero で attestation が生成されない)。
- **`subject` 構成の universal pattern**:
  - T-020 (Go module): tag そのもの (`git archive` 結果) を subject、 commit SHA を併記
  - T-021 (npm): `.tgz` tarball を subject (npm pack 出力)
  - T-017 (shared-lib): `.tar.gz` + `.xcframework.zip` + `.aar` を **複数 subject** (`base64-subjects` に複数行)
  - T-018 (Maven AAR / JAR): classifier 別に subject 構成 (CON-2.2)
- **RC tag round の手順**:
  1. `git tag rust-g2p-v1.13.0-rc.1; git push origin rust-g2p-v1.13.0-rc.1`
  2. workflow run 完了確認 (`gh run watch`)
  3. release asset から `.intoto.jsonl` を download
  4. `slsa-verifier verify-artifact <crate> --provenance-path <intoto.jsonl> --source-uri github.com/ayutaz/piper-plus --source-tag rust-g2p-v1.13.0-rc.1` exit 0
  5. RC tag delete (`gh release delete rust-g2p-v1.13.0-rc.1 --yes; git push --delete origin rust-g2p-v1.13.0-rc.1`)
  6. prod tag push (`rust-g2p-v1.13.0`)
- **`workflow_dispatch.inputs.version` 廃止の影響**: 現行 `g2p-rust-publish.yml` は既に tag-only trigger のため hermetic build 化の差分はゼロ。 T-018 (`release-kotlin-g2p.yml`) は `workflow_dispatch.inputs.version` を持つため、 T-018 で hermetic 化に伴い手動 dispatch unblock 機構を別途設計必要。
- **`slsa-github-generator` の `@v2.X.X` semver pin**: 2026-05 時点の最新は `@v2.0.0`、 `@v2` (sliding) は `action-pin-gate.yml` で禁止。 v3 breaking change 時は別 PR で bump (Dependabot 自動)。

### 7.3 未解決の質問

- [ ] PyPI / NuGet dedicated release workflow を新設するか (CON-2.1)、 user 判断。 新設する場合は T-024 (PyPI) / T-025 (NuGet) として M3 に追加。
- [ ] `docs/spec/slsa-provenance-contract.toml` を T-021 までに完成させるか (任意)、 user 判断。

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.2 (`#2`)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.4 (`#2` overview)
- Milestone: [`docs/tickets/milestones/M3-supply-chain.md`](../milestones/M3-supply-chain.md)
- 既存 workflow: [`.github/workflows/g2p-rust-publish.yml`](../../../.github/workflows/g2p-rust-publish.yml)
- 関連 workflow: [`.github/workflows/cosign-release-artifacts.yml`](../../../.github/workflows/cosign-release-artifacts.yml) (M1、 keyless 署名で共存)
- 外部: SLSA framework <https://slsa.dev/spec/v1.0/>, slsa-github-generator <https://github.com/slsa-framework/slsa-github-generator>, slsa-verifier <https://github.com/slsa-framework/slsa-verifier>, in-toto attestation <https://github.com/in-toto/attestation>

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
