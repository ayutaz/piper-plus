# T-018: SLSA L3 for Maven Central (Kotlin G2P)

**チケット ID**: `T-018`
**Milestone**: [M3 Supply Chain](../milestones/M3-supply-chain.md)
**Proposal 項目**: `#2-2` (`SLSA Build L3 / Maven Central`)
**Tier**: Tier 3 (release blast radius、 1 registry / 1 PR、 **GPG 共存最難関**)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**:

- **T-019 / T-020 / T-021 / T-017 merged 後に着手**。 hash 計算 / generator 呼び出し / 複数 attestation 共存 / 複数 subject (T-017 = 9 subject) pattern が全て確立済。
- 推奨実装順 T-019 → T-020 → T-021 → T-017 → **T-018**。
- 本 ticket は **GPG 署名 (Maven Central 必須) と SLSA attestation の共存** が最大の論点 (AC-2.3)。 Sonatype が SLSA L3 attestation を Maven repository 形式 (`*.module`、 `pom.xml`、 GPG `.asc`) と並存させる方式を検証する。

---

## 1. タスク目的とゴール

### 目的

`release-kotlin-g2p.yml` (Maven Central publish workflow) を SLSA Build L3 に昇格させる。

PR #511 後の現状:

- 既存 `release-kotlin-g2p.yml` は **Maven Central 必須 GPG 署名** (`signingInMemoryKey` + `signingInMemoryKeyPassword`) を持つ。 これは Sonatype の publish gate (`SIGNING_IN_MEMORY_KEY` 不在で publish 失敗)。
- 既存 workflow は **既に `actions/attest-build-provenance@v3.2.0` 導入済** (L216-221、 subject = `android/piper-plus-g2p/build/outputs/aar/*.aar`)。 SLSA L2 相当の attestation は AAR に対して動作。
- SLSA L3 化には:
  1. `slsa-github-generator` の generator を AAR + sources JAR + javadoc JAR + POM (Maven artifact 4 種) に適用
  2. GPG 署名 (Sonatype publish 用) と SLSA attestation (GitHub Release asset 用) を **別 channel** で配信、 干渉なし
  3. workflow_dispatch.inputs.version の廃止 (FR-2.4、 hermetic build)

### ゴール (Done definition)

- [ ] **AC-2.1**: 以下コマンドが AAR + JAR で exit 0 を返す:

  ```bash
  slsa-verifier verify-artifact \
    io/github/ayutaz/piper-plus-g2p-android/1.13.0/piper-plus-g2p-android-1.13.0.aar \
    --provenance-path piper-plus-g2p-android-1.13.0.aar.intoto.jsonl \
    --source-uri github.com/ayutaz/piper-plus \
    --source-tag kotlin-g2p-v1.13.0
  ```

- [ ] **AC-2.2**: OpenSSF Scorecard score 維持。
- [ ] **AC-2.3** (本 ticket 固有): Maven Central (AAR + JAR) は **GPG 署名と SLSA attestation が共存**:
  - GPG: Sonatype repository 内で `*.asc` として配信 (`gpg --verify` 経由検証)
  - SLSA: GitHub Release asset で `*.intoto.jsonl` として配信 (`slsa-verifier` 経由検証)
  - 両 verifier が exit 0 を返す
- [ ] `v1.13.0-rc.X` RC release で attestation 生成 + verify exit 0 確認。 ただし **Sonatype は RC version 受容するが staging repository で停止** することで cleanup 可能。
- [ ] `docs/reference/slsa-verify.md` に **Maven Central セクション** 追加。 GPG / SLSA の 2 verifier 関係図 (mermaid) を含む。
- [ ] hermetic build: 既存 `workflow_dispatch.inputs.version` を **廃止** (FR-2.4)。 手動 dispatch unblock 機構として `workflow_dispatch.inputs.dry_run` (default true) を別途追加し、 dry_run=false 時のみ publishToMavenLocal + assembleRelease を実行 (PR base trigger 維持)。
- [ ] **3 attestation 共存**: `attest-build-provenance` (既存) + `slsa-github-generator` (新規) + GPG 署名 (既存、 attestation ではないが配信物の一部)。

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `.github/workflows/release-kotlin-g2p.yml` | 変更 | `slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml` を sub-workflow 呼び出し。 AAR + JAR の hash 集約 step、 `workflow_dispatch.inputs.version` 廃止 → `dry_run` 化 |
| `docs/reference/slsa-verify.md` | 変更 | Maven Central セクション追加。 GPG + SLSA の trust path 関係図 (mermaid) を含む |
| `docs/spec/slsa-provenance-contract.toml` | 変更 | maven 行追加 (subject = AAR + sources JAR + javadoc JAR + POM、 GPG asc は SLSA 対象外明示) |
| `scripts/generate_slsa_subjects_maven.sh` | 新規 | `android/piper-plus-g2p/build/outputs/aar/*.aar` + Gradle `publishToMavenLocal` 出力の `~/.m2/repository/io/github/ayutaz/piper-plus-g2p-android/<ver>/*.{aar,jar,pom}` を walk して subject 集約 |

### 2.2 処理シーケンス

```text
1. tag push (refs/tags/kotlin-g2p-v<version>) で trigger
2. build-native job: 既存どおり 3 ABI (arm64-v8a / armeabi-v7a / x86_64) build (変更なし)
3. publish job:
   a. 既存 step (checkout / JDK / Android SDK + NDK / Gradle setup / native libs stage) 維持
   b. version 決定 (既存: tag → version、 ただし *workflow_dispatch.inputs.version は廃止*)
   c. 既存 step (Verify version / Check publishing secrets / assembleRelease) 維持
   d. *新規*: publishToMavenLocal で AAR + sources JAR + javadoc JAR + POM 4 種を ~/.m2/repository に生成
      ./gradlew :piper-plus-g2p:publishToMavenLocal --no-daemon
   e. *新規*: scripts/generate_slsa_subjects_maven.sh で 4 種 artifact の sha256 集約
      → outputs.hashes (base64-encoded)
   f. *既存維持*: attest-build-provenance@v3.2.0 (AAR のみ subject、 既存挙動維持)
   g. *既存維持*: publishAndReleaseToMavenCentral (GPG 署名と同時に Sonatype upload)
   h. *新規*: GitHub Release asset として 4 種 artifact + SLSA intoto.jsonl を upload
4. *新規 job* slsa-provenance:
   needs: [publish]
   uses: slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v2.X.X
   with:
     base64-subjects: ${{ needs.publish.outputs.hashes }}
     upload-assets: true
     provenance-name: piper-plus-g2p-android-<version>.intoto.jsonl
   permissions:
     id-token: write
     contents: write
     actions: read
5. defensive log: "Generated SLSA L3 provenance for piper-plus-g2p-android v<version> (subjects: 4 maven artifacts, GPG signed for Sonatype, SLSA attestation for GitHub Release)" を stderr に echo
```

### 2.3 既存資産との接続

- **流用**:
  - T-019 / T-020 / T-021 / T-017 で確立した hash 計算 / generator 呼び出し / 複数 subject pattern
  - T-017 の `generate_slsa_subjects.sh` をテンプレートに Maven 版を作成 (`generate_slsa_subjects_maven.sh`)
- **共存**:
  - **GPG 署名**: Sonatype publish gate 用、 `signingInMemoryKey` で AAR + JAR + POM に `.asc` 付与。 Maven Central repository 内に配信
  - **SLSA attestation**: GitHub Release asset として `.intoto.jsonl` 配信
  - **既存 `attest-build-provenance`**: AAR のみ subject の GitHub-native attestation (gh attestations API)
- **補完関係**: Sonatype publish path (GPG) は完全維持、 GitHub Release path (SLSA) を **並行追加** する形。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | `release-kotlin-g2p.yml` 改変、 `generate_slsa_subjects_maven.sh` 新規、 `workflow_dispatch.inputs.version` 廃止 → `dry_run` 化 | workflow YAML + script |
| **Test author** | 1 | RC release plan、 Sonatype staging repository での停止 + cleanup 手順、 `slsa-verifier verify-artifact` + `gpg --verify` の 2 verifier 確認 | RC 検証手順 |
| **Spec / Doc author** | 1 | `docs/reference/slsa-verify.md` の Maven Central セクション (GPG + SLSA trust path 関係図 mermaid 含む)、 `slsa-provenance-contract.toml` maven 行 | docs |
| **Release engineer** | 1 | Sonatype Nexus staging repository 操作 (RC で staging 停止 + cleanup)、 GPG key rotation 影響なし確認 | 運用手順 |
| **Reviewer** | 1 | maintainer cross-cutting (GPG / SLSA 共存が最重要レビュー) | review |

**並列度**: Implementer + Doc author 並列、 Test author + Release engineer は RC round に逐次 (Sonatype staging cleanup が手動操作含むため特に逐次必須)。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `release-kotlin-g2p.yml` への SLSA L3 generator sub-workflow 追加
- 4 種 Maven artifact (AAR / sources JAR / javadoc JAR / POM) の subject 集約
- GPG 署名と SLSA attestation の **共存** (両 verifier exit 0)
- `workflow_dispatch.inputs.version` 廃止 → `dry_run` 入力に置換 (hermetic build 維持 + dry-run UX 維持)
- `docs/reference/slsa-verify.md` の Maven Central セクション (GPG + SLSA 関係図)

**Out of scope**:

- GPG key rotation 自動化 (既存 `SIGNING_IN_MEMORY_KEY` の secret 管理は本 ticket 対象外)
- Sonatype Nexus repository 自動 cleanup (RC version の手動 staging drop が運用手順)
- Android G2P 以外の Android module の Maven 配信 (現状 `piper-plus-g2p-android` のみ)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `generate_slsa_subjects_maven.sh` | `~/.m2/repository/io/github/ayutaz/piper-plus-g2p-android/1.13.0/` に 4 artifact | 4 行 `<sha256>  <basename>` を stdout |
| UT-2 | hash 集約 + base64 | 4 subject | 単一行 base64 出力 |
| UT-3 | slsa generator 呼び出し | 4 subject base64 | `*.intoto.jsonl` (subject array 4 件) が release asset |
| UT-4 | `workflow_dispatch.inputs.dry_run` | `dry_run=true` で manual trigger | publishToMavenLocal のみ実行、 Sonatype publish skip |
| UT-5 | GPG + SLSA 共存 | `gpg --verify *.aar.asc *.aar` + `slsa-verifier verify-artifact *.aar` | 両者 exit 0 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | `kotlin-g2p-v1.13.0-rc.1` tag push → full run | `gh run view` で全 job green |
| E2E-2 | Sonatype staging repository で RC が visible | `https://oss.sonatype.org/#stagingRepositories` で確認 |
| E2E-3 | `gpg --verify <aar>.asc <aar>` exit 0 | Sonatype download 後 verify |
| E2E-4 | `slsa-verifier verify-artifact` exit 0 (AAR) | GitHub Release asset download 後 verify |
| E2E-5 | RC cleanup: Sonatype staging drop (手動 web UI 操作)、 GitHub Release delete | 運用手順実行 |
| E2E-6 | OpenSSF Scorecard re-run | baseline 維持 |

### 4.4 リグレッション確認

- [ ] 既存 build-native job (3 ABI) が動作継続
- [ ] 既存 GPG 署名 (Sonatype publish gate) が動作継続
- [ ] 既存 `attest-build-provenance` の AAR attestation が release asset に存在
- [ ] PR dry-run (`publishToMavenLocal --no-daemon`) が動作継続
- [ ] silent-zero 防御: `subjects: 4 maven artifacts, ...` の 4 が満たないなら `::warning::`
- [ ] wall clock 増加 (slsa-provenance job ~5 分追加) が許容範囲

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | GPG 署名 step (Gradle Maven Publish plugin) と SLSA attestation の step 順序競合 | GPG 署名は `publishAndReleaseToMavenCentral` 内で自動実行 (gradle task)、 SLSA attestation は **別 job (slsa-provenance)** で動作。 job graph で時系列分離 | UT-5 + E2E-3/E2E-4 |
| C-2 | RC release が Sonatype に **promote されてしまう** (cleanup 不可) | `publishAndReleaseToMavenCentral` ではなく `publishToMavenCentral` (release は手動 promote) を RC 時のみ使用、 staging repository で停止 | E2E-2 確認 + maintainer 手動操作 |
| C-3 | `workflow_dispatch.inputs.version` 廃止で運用 unblock 機構喪失 | `dry_run` 入力を追加 (PR base trigger 等価)、 hot-fix release は新 tag push (`kotlin-g2p-v1.13.0-hotfix.1`) で対応 | UT-4 |
| C-4 | 4 種 Maven artifact の subject 集合変動 (sources JAR / javadoc JAR が Gradle 設定変更で消える) | `generate_slsa_subjects_maven.sh` が expected_count=4 を必須化、 不足時 exit 1 | UT-1 |
| C-5 | Sonatype の `gpg --verify` と GitHub Release の `slsa-verifier` で **異なる AAR binary** が配信される懸念 (片方 corrupt) | publishToMavenLocal の AAR と Sonatype publish の AAR が **同一 file** (Gradle が cache from `build/outputs/aar/`)、 sha256 一致確認を E2E-4 で実施 | E2E-4 |
| C-6 | `signingInMemoryKey` の OIDC token と SLSA `id-token: write` の干渉 | 既存 publish job (`id-token: write` 既設) と新 slsa-provenance job (`id-token: write`) は別 job、 GPG key (SIGNING_IN_MEMORY_KEY) は ENV var で publish job 内のみ参照 | workflow job graph |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern (subject 0 件 / 4 未満で success) を fixture test
- [ ] action SHA pin `@v<X.Y.Z>` 形式
- [ ] `permissions:` least privilege (publish: `contents: read, id-token: write, attestations: write` 既存維持、 slsa-provenance: `id-token: write, contents: write, actions: read`)
- [ ] hermetic build (`workflow_dispatch.inputs.version` 廃止確認、 `dry_run` 入力のみ残)
- [ ] AC-2.3 (GPG + SLSA 共存) を RC release で実証
- [ ] OpenSSF Scorecard baseline 維持
- [ ] `docs/reference/slsa-verify.md` の Maven Central セクションが GPG / SLSA 2 verifier 関係図を含む
- [ ] RC cleanup 手順 (Sonatype staging drop) が `docs/reference/slsa-verify.md` または運用 doc に明示
- [ ] markdownlint MD032 全 doc pass
- [ ] PR 本文が `pull_request_template.md` 準拠

---

## 6. 一から作り直すとしたら

### 案 A: Maven Central GPG を SLSA で代替 (GPG 廃止)

- **概要**: Sonatype の GPG 必須要件が SLSA L3 attestation で代替可能になれば、 GPG 署名を完全廃止。 `signingInMemoryKey` secret 管理が消える。
- **長所**:
  - secret 管理 cost 削減 (GPG key rotation 不要)
  - trust path 単一化 (SLSA L3 verifier のみ)
  - 5 ticket で `cosign verify-blob` / SLSA L3 / GPG 3 種が並存しないシンプル化
- **短所**:
  - **2026-05 時点で Sonatype は GPG 必須**。 SLSA L3 代替は受容されていない (Sonatype publish API gate)。
  - GPG 廃止は ecosystem-wide な後方互換性破壊 (Maven 4.x まで GPG 要件は残る見込み)
  - Java/Kotlin ecosystem の慣習と乖離 (Spring / Apache 等は全 GPG 必須)
- **採否**: v1 では採用不可 (Sonatype 制約)。 ただし Sonatype の SLSA 公式対応が来た場合は M3 retrospective で再評価。 **本案を採用しない理由は AC-2.3 (GPG/SLSA 共存) の存在意義**。

### 案 B: 共存維持 (本 ticket の現実装)

- **概要**: GPG (Sonatype 配信) + SLSA L3 (GitHub Release 配信) + `attest-build-provenance` (GitHub attestations) の 3 trust path 並存。
- **長所**:
  - downstream user の verifier 選択肢が豊富 (Java ecosystem の GPG ユーザ + supply chain 重視の SLSA ユーザ両対応)
  - Sonatype 制約と整合、 publish 失敗リスクなし
  - 5 ticket 統一性維持
- **短所**:
  - 3 trust path の維持 cost (doc / 運用 / secret 管理)
  - downstream user が「どの verifier を使うべきか」 を判断する負担
- **採否**: v1 で採用。

### 案 C: `slsa-github-generator` を使わず自前 in-toto + Maven dependency attestation

- **概要**: T-019 §6 案 A を Maven 向けに拡張。 `in-toto-attestation` で predicate に dependency tree (Gradle dependencyInsight 出力) を埋め込み、 supply chain 深度を増す。
- **長所**: predicate に Gradle dependency graph を含めることで「どの ORT version で build されたか」 等を attestation に固定可能。
- **短所**: SLSA L3 verify 失敗、 Scorecard score down。
- **採否**: 採用しない (T-019 §6 案 A と同理由)。

### 結論

現時点での選択は **案 B (共存維持)**。 案 A は Sonatype 制約により不可。 v2 (M3 retrospective + 数年後) で Sonatype の SLSA 公式対応進展次第で案 A 再評価。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: M3 完了。 後続は M4 (mkdocs 統合) で `docs/reference/slsa-verify.md` を mkdocs nav に統合。
- **連携 milestone**: M3 完了で `cosign + SLSA L3` dual-protection が全 5 registry で揃う。
- **依存解消**: 本 ticket 完了で M3 milestone close、 `docs/proposals/ci-expansion-deferred-items.md` の `#2` 全項目完了。

### 7.2 引き継ぎ事項 (Handoff)

> 本 ticket は M3 milestone の **最後のチケット**。 5 ticket 全体で取得した運用知見をまとめて申し送る。

- **5 ticket 統合知見 (T-019 → T-020 → T-021 → T-017 → T-018)**:

  1. **hash 計算 step**: `sha256sum` 出力を `base64 -w 0` で encode、 改行は base64 内部に保持。 単一 subject でも base64 encoding 必須 (空 base64 で silent-zero)。
  2. **subject 構成 pattern**:
     - T-019 (Rust): `.crate` 1 subject
     - T-020 (Go): source archive `.tar.gz` 1 subject
     - T-021 (npm): `.tgz` 1 subject (3 attestation 共存)
     - T-017 (shared-lib): 9+ multi-platform binary subject
     - T-018 (Maven): 4 種 classifier subject (AAR / sources JAR / javadoc JAR / POM)
  3. **既存 `attest-build-provenance` 共存**: 全 5 ticket で維持。 GitHub-native attestation (gh attestations API) と SLSA L3 (slsa-github-generator) の dual-attestation。
  4. **hermetic build (FR-2.4) の運用影響**:
     - T-019 / T-020 / T-021: 元から tag-only trigger、 差分ゼロ
     - T-017: 元から tag-only trigger、 差分ゼロ
     - T-018 (本 ticket): `workflow_dispatch.inputs.version` 廃止 → `dry_run` 入力に置換 (手動 hot-fix は新 tag push で対応)
  5. **RC tag round の手順**:
     - tag push → workflow run → release asset 確認 → `slsa-verifier verify-artifact` exit 0 → RC tag delete + GitHub Release delete (Sonatype 経由の T-018 のみ staging drop も実施)
- **`docs/reference/slsa-verify.md` の最終構造**: 5 ticket の verify 例を runtime 別に並べた reference doc。 trust path 関係図 (T-021 で 3 attestation、 T-018 で GPG + SLSA + gh attestations の 4 trust path) は mermaid で集約。
- **Sonatype staging cleanup の操作詳細**:
  1. `https://oss.sonatype.org/#stagingRepositories` にログイン
  2. RC version の staging repository (例: `iogithubayutaz-XXXX`) を選択
  3. "Drop" ボタンで cleanup
  4. confirm dialog で "Confirm"
  5. staging repository が空になることを確認
- **GPG key 管理**: `SIGNING_IN_MEMORY_KEY` は GitHub Actions secret として管理。 key rotation 時は GitHub secret 更新 + `data-sources.yml` の GPG key fingerprint 更新を別 PR で実施。 SLSA L3 化は本 ticket では GPG rotation スコープ外。
- **M4 への申し送り**: `docs/reference/slsa-verify.md` を mkdocs nav `Reference > Supply Chain > SLSA Verification` 配下に統合。 inbound link (`https://github.com/ayutaz/piper-plus/blob/dev/docs/reference/slsa-verify.md`) は維持。

### 7.3 未解決の質問

- [ ] PyPI / NuGet dedicated release workflow の新設 (CON-2.1) を user 判断。 必要なら T-024 (PyPI) / T-025 (NuGet) として後続 ticket 化。
- [ ] M3 retrospective で reusable supply chain workflow (`.github/workflows/_supply-chain-release.yml`) への refactor 採否を user 判断 (M3 milestone §4 参照)。

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.2 (`#2`)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.4 (`#2` overview)
- Milestone: [`docs/tickets/milestones/M3-supply-chain.md`](../milestones/M3-supply-chain.md)
- 既存 workflow: [`.github/workflows/release-kotlin-g2p.yml`](../../../.github/workflows/release-kotlin-g2p.yml)
- 関連 ticket: [`T-019-slsa-rust-g2p.md`](T-019-slsa-rust-g2p.md), [`T-020-slsa-go-g2p.md`](T-020-slsa-go-g2p.md), [`T-021-slsa-npm.md`](T-021-slsa-npm.md), [`T-017-slsa-shared-lib.md`](T-017-slsa-shared-lib.md)
- 関連 workflow: [`.github/workflows/cosign-release-artifacts.yml`](../../../.github/workflows/cosign-release-artifacts.yml) (M1、 keyless 署名)
- 外部: SLSA framework <https://slsa.dev/spec/v1.0/>, slsa-github-generator <https://github.com/slsa-framework/slsa-github-generator>, Sonatype OSSRH <https://central.sonatype.org/publish/publish-guide/>, Maven Central requirements <https://central.sonatype.org/publish/requirements/>

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
