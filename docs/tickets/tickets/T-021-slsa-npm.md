# T-021: SLSA L3 for npm

**チケット ID**: `T-021`
**Milestone**: [M3 Supply Chain](../milestones/M3-supply-chain.md)
**Proposal 項目**: `#2-5` (`SLSA Build L3 / npm`)
**Tier**: Tier 3 (release blast radius、 1 registry / 1 PR)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**:

- **T-019 (Rust G2P) + T-020 (Go module) merged 後に着手**。 T-019 で hash 計算 / generator 呼び出し pattern、 T-020 で source archive 以外の subject (binary tarball) pattern が確立済。
- 推奨実装順 T-019 → T-020 → **T-021** → T-017 → T-018。
- npm は **既に native `--provenance` (npm 9+)** を導入済 (`npm-publish.yml` L122)。 SLSA L3 化は `slsa-github-generator` 経由を **追加** し、 native provenance と共存させる (npm registry が両方を受容)。

---

## 1. タスク目的とゴール

### 目的

`npm-publish.yml` (npm publish workflow) を SLSA Build L3 に昇格させる。

PR #511 後の現状:

- 既存 `npm-publish.yml` は **2 つの provenance** を既に持つ:
  - `actions/attest-build-provenance@v3.2.0` (GitHub-native artifact attestation)
  - `npm publish *.tgz --provenance` (npm registry native provenance、 sigstore 経由)
- これらは SLSA L2-L3 中間に相当する。 完全 SLSA L3 化には `slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml` の追加が必要。 ただし native `npm --provenance` との関係を整理しないと **trust path が 3 重 (gh attestations / npm registry / slsa-github-generator) で downstream user が混乱** する懸念あり (本 ticket §6 で議論)。

### ゴール (Done definition)

- [ ] **AC-2.1**: 以下コマンドが exit 0 を返す:

  ```bash
  slsa-verifier verify-artifact piper-plus-'<version>'.tgz \
    --provenance-path piper-plus-'<version>'.tgz.intoto.jsonl \
    --source-uri github.com/ayutaz/piper-plus \
    --source-tag npm-v'<version>'
  ```

  subject は `npm pack` で生成された `.tgz` tarball (既存 attestation pattern と同一)。

- [ ] **AC-2.2**: OpenSSF Scorecard score 維持。
- [ ] `v1.13.0-rc.X` RC release で attestation 生成 + verify exit 0 確認。
- [ ] `docs/reference/slsa-verify.md` に **npm セクション** 追加。 **重要**: 3 つの provenance (gh attestations / npm native / slsa-github-generator) の **trust path 関係図** を明示。
- [ ] hermetic build: 既存 `npm-v*` tag-only trigger 維持、 `workflow_dispatch.inputs.version` は元から無いため差分ゼロ。
- [ ] **3 attestation 共存**: `attest-build-provenance` (既存) + `npm publish --provenance` (既存) + `slsa-github-generator` (新規) が **全部** 動作する。

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `.github/workflows/npm-publish.yml` | 変更 | `slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml` を sub-workflow 呼び出し。 既存 `npm pack` の `.tgz` を subject として再利用 |
| `docs/reference/slsa-verify.md` | 変更 | npm セクション追加。 3 attestation の trust path 関係図を含む |
| `docs/spec/slsa-provenance-contract.toml` | 変更 | npm 行追加 (subject = npm tarball、 native provenance との共存明示) |

### 2.2 処理シーケンス

```text
1. tag push (refs/tags/npm-v<version>) で trigger
2. validate job: 既存どおり npm pack --dry-run / size check (変更なし)
3. wasm-build job: 既存どおり build-wasm-reusable.yml (変更なし)
4. publish job:
   a. checkout (既存)
   b. setup-node (registry-url 設定、 既存)
   c. WASM artifact download (既存)
   d. npm pack で .tgz 生成 (既存、 既存 attest-build-provenance の subject 源)
   e. *新規*: .tgz の sha256 を計算 → outputs.hashes (base64-encoded)
   f. attest-build-provenance@v3.2.0 (既存維持)
   g. npm publish *.tgz --provenance --access public (既存維持)
5. *新規 job* slsa-provenance:
   needs: [publish]
   uses: slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v2.X.X
   with:
     base64-subjects: ${{ needs.publish.outputs.hashes }}
     upload-assets: true   # GitHub Release asset として upload (npm registry 側ではない)
     provenance-name: piper-plus-<version>.tgz.intoto.jsonl
   permissions:
     id-token: write
     contents: write
     actions: read
6. defensive log: "Generated SLSA L3 provenance for piper-plus-<version>.tgz (subject hash: <sha256>, npm registry provenance attached, gh attestations attached)" を stderr に echo
```

### 2.3 既存資産との接続

- **流用**: T-019 / T-020 で確立した hash 計算 / generator 呼び出し pattern を npm tarball に適用。
- **共存** (3 attestation):
  - **GitHub attestations API** (`actions/attest-build-provenance@v3.2.0`): GitHub Release asset として `*.attestation` 配信、 `gh attestation verify` で検証可能
  - **npm registry native provenance** (`npm publish --provenance`): npm registry がメタデータとして保持、 `npm view <pkg>@<ver>` で確認可能、 sigstore 経由
  - **slsa-github-generator** (新規): SLSA L3 reference provenance、 GitHub Release asset として `.intoto.jsonl` 配信、 `slsa-verifier verify-artifact` で検証可能
- **補完関係**: 配信 (npm registry) は既存、 検証層を 3 重に強化。 downstream user は **どれか 1 つを検証すれば downstream supply chain check が成立** (doc で trust path を明示)。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | `npm-publish.yml` 改変、 hash 計算 step、 slsa generator sub-workflow 呼び出し | workflow YAML |
| **Test author** | 1 | RC release plan、 `slsa-verifier verify-artifact` を npm tarball 向けに検証、 既存 `npm view --provenance` 互換性確認 | RC 検証手順 |
| **Spec / Doc author** | 1 | `docs/reference/slsa-verify.md` の npm セクション、 **3 attestation trust path 関係図** (mermaid) | docs |
| **Release engineer** | 1 | npm registry の rate limit (新 attestation 追加で publish 時の API call 増加なし、 GitHub Release asset upload 追加のみ) 確認 | 運用手順 |
| **Reviewer** | 1 | maintainer cross-cutting (trust path 整理が本 ticket の最重要レビュー) | review |

**並列度**: Implementer + Doc author 並列、 Test author + Release engineer は RC round に逐次。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `npm-publish.yml` に SLSA L3 generator sub-workflow 追加
- `npm pack` 出力 `.tgz` を subject とする 3 重 provenance attestation
- `docs/reference/slsa-verify.md` の npm セクション (trust path 関係図含む)

**Out of scope**:

- npm registry 側の provenance UI 改善 (npm 公式の機能、 外部依存)
- `@piper-plus/g2p` (G2P-only npm) の SLSA 化 (本 ticket は `piper-plus` メイン package のみ。 別 ticket T-026 で対応する場合の前例として本 pattern を申し送り)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | hash 計算 step | `piper-plus-0.6.0.tgz` (npm pack 出力) | sha256 が `base64-subjects` 形式 |
| UT-2 | slsa generator 呼び出し | `needs.publish.outputs.hashes` | `*.intoto.jsonl` が release asset に upload |
| UT-3 | 3 attestation 共存 | tag push | gh attestations / npm provenance / slsa intoto.jsonl が全て存在 |
| UT-4 | npm view --provenance 互換 | `npm view piper-plus@<rc-ver> --json` | `provenance` field が存在 (既存挙動維持) |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | `npm-v0.7.0-rc.1` tag push → full run | `gh run view` で全 job green |
| E2E-2 | 3 verifier 全部 exit 0 | `slsa-verifier verify-artifact` + `gh attestation verify` + `npm view --provenance` |
| E2E-3 | RC unpublish (`npm unpublish piper-plus@0.7.0-rc.1 --force`) → prod publish | npm registry 側で rc version が削除されたことを確認 |
| E2E-4 | OpenSSF Scorecard re-run | baseline 維持 |

### 4.4 リグレッション確認

- [ ] 既存 `npm publish --provenance` が動作継続 (npm registry に provenance metadata が保持される)
- [ ] 既存 `attest-build-provenance` が動作継続
- [ ] silent-zero 防御: `Generated SLSA L3 provenance for piper-plus-<version>.tgz (subject hash: <sha256>, ...)` を必ず stderr に出力
- [ ] npm registry の publish API rate limit 余裕あり (新規 API call 増なし)

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | 3 attestation の trust path が downstream user に伝わらない | `docs/reference/slsa-verify.md` に mermaid 関係図 + どの verifier をいつ使うかの recommendation | doc review |
| C-2 | npm registry 側の native provenance と slsa-github-generator provenance の内容差異 | 両者は同一 `.tgz` (sha256 一致) を subject とするため、 verify は両方 pass する。 差は **配信経路 (npm registry vs GitHub Release)** と **transparency log の参照先** | RC release で実検証 |
| C-3 | RC 版 (`0.7.0-rc.1`) が npm registry に publish されると downstream に誤取得される | `npm publish --tag rc` で latest tag 汚染を防ぐ、 または rc では `npm publish --dry-run` で attestation のみ生成 (RC 用 conditional 追加) | publish step の conditional review |
| C-4 | npm 9+ の native `--provenance` が将来 SLSA L3 を name space で内包した場合、 slsa-github-generator が redundant 化 | M3 retrospective で再評価 (案 A 参照) | future-proof note |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern (subject hash 空文字検出) を fixture test
- [ ] action SHA pin `@v<X.Y.Z>` 形式
- [ ] `permissions:` least privilege (publish: `contents: read, id-token: write, attestations: write` 既存維持、 slsa-provenance: `id-token: write, contents: write, actions: read`)
- [ ] hermetic build (tag-only trigger 維持)
- [ ] RC release で 3 verifier 全部 exit 0 (AC-2.1 + 既存挙動)
- [ ] OpenSSF Scorecard baseline 維持
- [ ] `docs/reference/slsa-verify.md` の trust path 関係図が明確
- [ ] RC tag の `--tag rc` 運用が `latest` を汚染しないか
- [ ] markdownlint MD032 全 doc pass
- [ ] PR 本文が `pull_request_template.md` 準拠

---

## 6. 一から作り直すとしたら

### 案 A: `slsa-github-generator` を使わず npm 9+ native `--provenance` のみに集約

- **概要**: npm registry の native provenance は SLSA Build L3 expectations を逐次満たしてきており、 将来的に **slsa-github-generator が不要** になる可能性が高い。 `npm publish --provenance` のみで SLSA L3 verify 可能になれば、 GitHub Release asset 経由の attestation は redundant。
- **長所**:
  - workflow 簡略化 (sub-workflow 追加なし、 既存 `npm publish --provenance` 1 行で完結)
  - downstream user は `npm view <pkg> --provenance` 単一 path で trust 検証
  - npm ecosystem の future direction (npm v10+) と整合
- **短所**:
  - 2026-05 時点で `slsa-verifier verify-artifact` が npm native provenance を verify できるかは要検証 (npm registry の provenance format = sigstore bundle、 slsa-verifier は `*.intoto.jsonl` 期待)
  - SLSA L3 公式 reference が `slsa-github-generator` 経由のため、 native のみだと「SLSA L3 公式準拠」 マーケティングが弱い
  - 5 ticket の統一性 (T-019 / T-020 / T-017 / T-018 は全部 generator 経由) が崩れる
- **採否**: v1 では採用しない (5 ticket 統一性優先)。 v2 (M3 retrospective) で `slsa-verifier` の npm native 対応進展次第で再評価。 本案は **future-proof note** として §7 に申し送り。

### 案 B: npm registry を canonical 配信、 GitHub Release asset を ZERO にする

- **概要**: npm tarball は npm registry が唯一の配信元、 GitHub Release には何も upload しない (attestation 含む)。 trust 検証は `npm view --provenance` のみ。
- **長所**:
  - 配信経路の単一化、 mirroring 不要
  - npm-only consumer の運用 simplification
- **短所**:
  - SLSA L3 verify が npm native のみに依存、 案 A の短所を全て継承
  - GitHub Release を見る consumer (例: vendor 直 download) が attestation を取れない
- **採否**: 採用しない。

### 結論

現時点での選択は **3 attestation 共存** (Implementer 案)。 5 ticket 統一性 + trust path 冗長性 (一部経路が壊れても他で検証可能) の 2 軸で正当化。 v2 では案 A を再評価。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-017 (shared-lib、 multi-platform binary) → T-018 (Maven Central、 GPG 共存最難関)
- **連携 milestone**: M3 残 2 件、 M4 (`@piper-plus/g2p` の SLSA 化を考えるか user 判断)
- **依存解消**: T-017 で「複数 subject (`.tar.gz` + `.xcframework.zip` + `.aar`)」 pattern が必要、 本 ticket で 3 attestation 共存 pattern が確立されたことで T-017 の trust path 整理が容易化

### 7.2 引き継ぎ事項 (Handoff)

- **3 attestation の trust path 関係**: downstream user 視点で「どれを使うか」 の recommendation を `docs/reference/slsa-verify.md` に明示。 推奨:
  1. **npm consumer (一般)**: `npm view <pkg> --provenance` (built-in、 設定不要)
  2. **CI integrator (高信頼性必要)**: `slsa-verifier verify-artifact` + GitHub Release asset (公式 reference)
  3. **GitHub-native (gh CLI 利用者)**: `gh attestation verify` (gh CLI に統合)
- **future-proof note (案 A)**: npm 10+ で native provenance が SLSA L3 verifier 公式対応した場合、 `slsa-github-generator` 経由は redundant 化する可能性。 M3 retrospective で `slsa-verifier --provenance-type npm-attestation` (仮称) の登場有無を再評価。
- **RC release の `--tag rc` 運用**: `npm publish --tag rc` で `latest` tag 汚染を防ぐ。 prod release では `npm publish --tag latest` (default)。 RC 後の cleanup は `npm dist-tag rm piper-plus rc` で実施。
- **`@piper-plus/g2p` (G2P-only npm) の SLSA 化**: 本 ticket scope 外。 必要に応じて T-026 として後続 ticket 化、 本 ticket の 3 attestation pattern をそのまま流用可。

### 7.3 未解決の質問

- [ ] RC release を npm registry に publish するか、 GitHub Release asset のみで停止するか。 現案は `--tag rc` で publish (downstream の early access を許容)。
- [ ] `@piper-plus/g2p` の SLSA 化 (T-026 新設) を user が判断。

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.2 (`#2`)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.4 (`#2` overview)
- Milestone: [`docs/tickets/milestones/M3-supply-chain.md`](../milestones/M3-supply-chain.md)
- 既存 workflow: [`.github/workflows/npm-publish.yml`](../../../.github/workflows/npm-publish.yml)
- 関連 ticket: [`T-019-slsa-rust-g2p.md`](T-019-slsa-rust-g2p.md), [`T-020-slsa-go-g2p.md`](T-020-slsa-go-g2p.md)
- 外部: SLSA framework <https://slsa.dev/spec/v1.0/>, slsa-github-generator <https://github.com/slsa-framework/slsa-github-generator>, npm provenance <https://docs.npmjs.com/generating-provenance-statements>

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
