# T-020: SLSA L3 for Go module

**チケット ID**: `T-020`
**Milestone**: [M3 Supply Chain](../milestones/M3-supply-chain.md)
**Proposal 項目**: `#2-4` (`SLSA Build L3 / Go module`)
**Tier**: Tier 3 (release blast radius、 1 registry / 1 PR)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**:

- **T-019 (Rust G2P, crates.io) merged 後に着手**。 T-019 で取得した運用知見 (`base64-subjects` の hash encoding、 RC tag round 手順、 既存 `attest-build-provenance` との共存 pattern) を本 ticket で適用。
- 推奨実装順 T-019 → **T-020** → T-021 → T-017 → T-018。
- M1 完了 (`cosign verify-blob` 運用定着) + M2 完了 (`release-versions.toml`) が前提。

---

## 1. タスク目的とゴール

### 目的

`g2p-go-publish.yml` (Go module tag publish workflow) を SLSA Build L3 に昇格させる。

PR #511 後の現状:

- 既存 `g2p-go-publish.yml` は **attestation 未実装** (T-019 と異なり `actions/attest-build-provenance` 呼び出しが無い)。 Go module は git tag が canonical 配信物 (`src/go/phonemize/v<version>`) で、 binary artifact が無いため subject 構成が rust とは別 design 必要。
- `slsa-framework/slsa-github-generator` には Go 専用 `generator_go_slsa3.yml` (binary build + provenance) と generic `generator_generic_slsa3.yml` (source archive subject) の 2 種類がある。 Go module は library のため後者が適合。
- hermetic build 化 (FR-2.4) との親和性が極めて高い: git tag が canonical 入力、 build artifact 不要 (`go install` は consumer 側で実行)。

### ゴール (Done definition)

- [ ] **AC-2.1**: 以下コマンドが exit 0 を返す:

  ```bash
  slsa-verifier verify-artifact source.tar.gz \
    --provenance-path source.tar.gz.intoto.jsonl \
    --source-uri github.com/ayutaz/piper-plus \
    --source-tag go-g2p-v<version>
  ```

  Go module の場合 subject は **`git archive` で生成した source tarball** (`source.tar.gz`) を canonical とする。 binary asset がないため。

- [ ] **AC-2.2**: OpenSSF Scorecard の `Token-Permissions` / `SAST` 以外の項目で score 低下なし。
- [ ] `v1.13.0-rc.X` RC release で attestation 生成 + verify exit 0 確認後に prod release。
- [ ] `docs/reference/slsa-verify.md` に **go セクション** を追加 (T-019 で初稿、 本 ticket で増補)。
- [ ] hermetic build 化: `go-g2p-v*` tag-only trigger は既存どおり (差分ゼロ確認)、 ただし source tarball 生成は `git archive --format=tar.gz --prefix=piper-plus-go-g2p-<version>/ <tag>` で deterministic 化。
- [ ] `git tag` 作成 step (既存 `src/go/phonemize/v<version>` module tag push) は維持、 attestation は **module tag ではなく original tag (`go-g2p-v<version>`)** に紐付け (Go module proxy が `go-g2p-v*` を見ないため UX 影響なし)。

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `.github/workflows/g2p-go-publish.yml` | 変更 | `slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml` を sub-workflow 呼び出し。 source archive 生成 step、 hash 計算 step を追加 |
| `docs/reference/slsa-verify.md` | 変更 | go セクション増補 (rust に倣う pattern、 ただし subject = source tarball を明示) |
| `docs/spec/slsa-provenance-contract.toml` | 変更 (T-019 で新規) | go 行を追加 (subject 種別 = source-archive、 module tag = `src/go/phonemize/v*`) |

### 2.2 処理シーケンス

```text
1. tag push (refs/tags/go-g2p-v<version>) で trigger
2. test job: 既存どおり go test (3 OS matrix、 変更なし)
3. lint job: 既存どおり golangci-lint (変更なし)
4. publish job:
   a. checkout (fetch-depth: 0、 既存)
   b. tag から version 抽出 (既存)
   c. *新規*: source archive 生成
      git archive --format=tar.gz --prefix=piper-plus-go-g2p-${VERSION}/ \
        -o piper-plus-go-g2p-${VERSION}.tar.gz HEAD
   d. *新規*: source archive の sha256 を計算 → outputs.hashes (base64-encoded)
   e. *既存維持 + 新規*: actions/attest-build-provenance@v3.2.0 を追加 (T-019 で導入された pattern、 共存)
   f. Go module tag 作成 + push (既存)
   g. pkg.go.dev indexing 要求 (既存)
   h. *新規*: source archive を GitHub Release asset として upload (gh release upload)
5. *新規 job* slsa-provenance:
   needs: [publish]
   uses: slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v2.X.X
   with:
     base64-subjects: ${{ needs.publish.outputs.hashes }}
     upload-assets: true
     provenance-name: piper-plus-go-g2p-<version>.tar.gz.intoto.jsonl
   permissions:
     id-token: write
     contents: write
     actions: read
6. defensive log: "Generated SLSA L3 provenance for piper-plus-go-g2p-<version>.tar.gz (subject hash: <sha256>)" を stderr に echo
```

### 2.3 既存資産との接続

- **流用**: T-019 で確立した hash 計算 / slsa-generator sub-workflow 呼び出し pattern を Go 向けに適用。
- **共存**:
  - Go module tag push (`src/go/phonemize/v<version>`) は Go ecosystem の canonical 配信物として維持。 SLSA attestation は **original tag (`go-g2p-v<version>`)** の GitHub Release asset として配信。
  - downstream user の `go install` は module tag を見るため SLSA verify は **optional な supply chain check** (`go install` 前に attestation verify する手順を doc 化)。
- **補完関係**: 配信 (module tag) は既存どおり、 検証層 (provenance + source archive) のみ追加。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | `g2p-go-publish.yml` 改変、 source archive 生成 step、 slsa generator sub-workflow 呼び出し | workflow YAML |
| **Test author** | 1 | RC release plan、 `slsa-verifier verify-artifact` を source tarball 向けに検証 | RC 検証手順 |
| **Spec / Doc author** | 1 | `docs/reference/slsa-verify.md` に go セクション増補、 `slsa-provenance-contract.toml` に go 行追加 | docs |
| **Release engineer** | 1 | Go module tag (`src/go/phonemize/v*`) と original tag (`go-g2p-v*`) の 2 重 tag 構造の整合性確認、 pkg.go.dev indexing への影響なし確認 | 運用手順 |
| **Reviewer** | 1 | maintainer cross-cutting | review |

**並列度**: Implementer + Doc author + Test author 並列、 Release engineer は RC round に逐次。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `g2p-go-publish.yml` に SLSA L3 generator sub-workflow + source archive 生成 step 追加
- `git archive` で生成した source tarball を subject とする provenance attestation
- `actions/attest-build-provenance@v3.2.0` の新規導入 (T-019 と共存 pattern)
- `docs/reference/slsa-verify.md` の go セクション増補

**Out of scope**:

- Go module proxy (`proxy.golang.org`) 側への attestation 配信 (proxy は upstream attestation を見ないため、 GitHub Release 経路のみ)
- `gotestsum` 導入 (M4 = `#8` test aggregation の範囲)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | source archive 生成 | `git archive --format=tar.gz --prefix=piper-plus-go-g2p-1.0.0/ -o out.tar.gz HEAD` | deterministic な tarball (`git archive` は timestamp 安定) |
| UT-2 | hash 計算 step | `out.tar.gz` | sha256 が `base64-subjects` 形式で outputs.hashes に設定 |
| UT-3 | slsa generator 呼び出し | `needs.publish.outputs.hashes` | `*.intoto.jsonl` が release asset として upload |
| UT-4 | module tag と original tag の整合 | tag push | 2 tag が指す commit が同一 SHA |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | `go-g2p-v1.13.0-rc.1` tag push → full run | `gh run view` で全 job green |
| E2E-2 | release asset から `slsa-verifier verify-artifact <source.tar.gz>` exit 0 | `scripts/test_slsa_verify.sh` で実行 |
| E2E-3 | RC tag delete → prod tag push、 module tag (`src/go/phonemize/v1.13.0`) が pkg.go.dev で indexing 成功 | `curl proxy.golang.org/.../@v/v1.13.0.info` |
| E2E-4 | OpenSSF Scorecard re-run | baseline 維持 |

### 4.4 リグレッション確認

- [ ] 既存 Go module tag push (`src/go/phonemize/v*`) が動作継続
- [ ] `pkg.go.dev` indexing 要求 (`curl proxy.golang.org/...`) が動作継続
- [ ] silent-zero 防御: `Generated SLSA L3 provenance for piper-plus-go-g2p-<version>.tar.gz (subject hash: <sha256>)` を必ず stderr に出力
- [ ] T-019 で確立した `actions/attest-build-provenance` 共存 pattern が再現可能

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | source tarball の hash が `git archive` 出力 timestamp で揺れる | `git archive` は committer date を deterministic に使用 (git config なし)、 同一 commit から同一 tarball が生成される (fixture test で確認) | UT-1 |
| C-2 | downstream user が `go install` 前に attestation verify する手順を知らない | `docs/reference/slsa-verify.md` の go セクションで **module tag からの逆引き** 手順を明示 (original tag を見つけて release asset を download) | doc review |
| C-3 | 既存 publish job の `contents: write` permission と新 slsa-provenance job の `id-token: write` 干渉 | 別 job で動作、 token scope 別管理 | workflow job graph |
| C-4 | T-019 で確立した pattern との差分 (Go は source archive subject、 Rust は binary subject) | §7 で T-021 / T-017 への申し送りに明記 | review |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern (`subject hash:` 空文字検出) を fixture test で確認
- [ ] action SHA pin が `@v<X.Y.Z>` 形式
- [ ] `permissions:` least privilege (publish: `contents: write` 既存 + `id-token: write` 新規 + `attestations: write` 新規、 slsa-provenance: `id-token: write, contents: write, actions: read`)
- [ ] hermetic build (tag-only trigger 維持、 `workflow_dispatch.inputs` 新規追加なし)
- [ ] RC release で `slsa-verifier verify-artifact` exit 0 確認
- [ ] OpenSSF Scorecard baseline 維持
- [ ] markdownlint MD032 全 doc pass
- [ ] PR 本文が `pull_request_template.md` に準拠

---

## 6. 一から作り直すとしたら

### 案 A: `slsa-github-generator` を使わず自前で in-toto attestation 生成

- **概要**: T-019 §6 案 A と同じ。 自前で in-toto attestation 生成 + cosign sign-blob。
- **長所**: subject 構成自由度極大、 source archive 以外 (例: build matrix の `go build` 出力) も subject 化可能。
- **短所**: SLSA L3 verify 失敗、 Scorecard score down。
- **採否**: T-018 (Maven) 挫折時の fallback。

### 案 B: Go 専用 `generator_go_slsa3.yml` を使う

- **概要**: `slsa-framework/slsa-github-generator` には Go 専用 sub-workflow `generator_go_slsa3.yml` がある。 これは `go build` 出力 (binary) を subject とする。
- **長所**: Go ecosystem 標準 pattern、 binary build matrix と attestation を同時生成。
- **短所**:
  - piper-plus G2P は **library 配布** で binary がない (consumer 側で `go install` するため)。 binary subject の意味が薄い。
  - 5 ticket で **異なる sub-workflow** を使うと統一性が崩れる (T-019 / T-020 / T-021 / T-017 / T-018 全部 generic 経由が望ましい)。
- **採否**: 採用しない。 generic 経由で統一する方が運用 cost が低い。

### 結論

現時点での選択は **generic generator + source archive subject**。 案 B は library 配布の Go module には適合しない。 v2 設計時に binary 配布も追加する場合 (例: `piper-plus-g2p-cli` Go binary を release artifact に追加) は `generator_go_slsa3.yml` 併用検討。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-021 (npm) → T-017 (shared-lib) → T-018 (Maven Central)
- **連携 milestone**: M3 残 3 件
- **依存解消**: T-021 で「source archive 以外 (npm tarball) を subject にする pattern」 が必要、 本 ticket で source archive pattern が確立されたことで T-021 設計の選択肢が明確化

### 7.2 引き継ぎ事項 (Handoff)

- **`git archive` の deterministic 化**: `git archive --format=tar.gz --prefix=<name>-<version>/ <tag>` は committer date 安定 (config 不要)。 ただし `git archive.tarTreeOptions=--owner=0 --group=0` 設定が必要な OS 互換ケースがある。 fixture test で同一 commit から 2 回 archive して bytewise 一致を確認。
- **`actions/attest-build-provenance` 共存の追加**: T-019 で確立した attest-build-provenance + slsa-github-generator 2 重 attestation pattern を本 ticket で **初めて Go workflow に導入** する。 publish job の permissions に `id-token: write, attestations: write` を追加 (既存は `contents: write` のみ)。
- **Go module tag と SLSA tag の対応関係**:
  - original tag: `go-g2p-v1.13.0` ← workflow trigger、 attestation の source-tag
  - module tag: `src/go/phonemize/v1.13.0` ← Go module proxy が見る、 attestation 対象外
  - downstream user は `go install github.com/ayutaz/piper-plus/src/go/phonemize@v1.13.0` で取得し、 attestation verify は `go-g2p-v1.13.0` の release asset から download (doc に明記)
- **`gotestsum` 導入は別 ticket**: M4 (`#8` test aggregation) で扱うため、 本 ticket では既存 `go test -race -count=1` 維持。

### 7.3 未解決の質問

- [ ] source archive の `--prefix` を `piper-plus-go-g2p-` にするか `piper-plus-` (rust と統一) にするか。 現案は前者 (Go ecosystem 慣習)。

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.2 (`#2`)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.4 (`#2` overview)
- Milestone: [`docs/tickets/milestones/M3-supply-chain.md`](../milestones/M3-supply-chain.md)
- 既存 workflow: [`.github/workflows/g2p-go-publish.yml`](../../../.github/workflows/g2p-go-publish.yml)
- 関連 ticket: [`T-019-slsa-rust-g2p.md`](T-019-slsa-rust-g2p.md) (本 ticket の prerequisite knowledge probe)
- 外部: SLSA framework <https://slsa.dev/spec/v1.0/>, slsa-github-generator <https://github.com/slsa-framework/slsa-github-generator>, Go modules <https://go.dev/ref/mod>, pkg.go.dev <https://pkg.go.dev/>

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
