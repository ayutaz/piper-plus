# T-017: SLSA L3 for shared-lib (iOS xcframework / Android AAR)

**チケット ID**: `T-017`
**Milestone**: [M3 Supply Chain](../milestones/M3-supply-chain.md)
**Proposal 項目**: `#2-1` (`SLSA Build L3 / shared-lib`)
**Tier**: Tier 3 (release blast radius、 1 registry / 1 PR、 multi-platform)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**:

- **T-019 / T-020 / T-021 merged 後に着手**。 hash 計算 / generator 呼び出し / 複数 attestation 共存 pattern が確立済。
- 推奨実装順 T-019 → T-020 → T-021 → **T-017** → T-018。
- 本 ticket は **最も subject 構成が複雑** (iOS device .tar.gz + iOS xcframework.zip + G2P xcframework.zip + Android 3 ABI .tar.gz = **6 種 subject** + Linux/macOS/Windows shared lib `.tar.gz`/`.zip` = 累計 **9+ subject**)。 T-021 までの pattern を応用して複数 subject base64 encoding を構築する。
- 既存 `release-shared-lib.yml` は **既に `actions/attest-build-provenance@v3.2.0` 導入済** (L1144、 `subject-path: artifacts/**/*.tar.gz; artifacts/**/*.zip`)。 SLSA L3 化は **既存 attestation の subject 集合をそのまま slsa-github-generator に渡す** 設計。

---

## 1. タスク目的とゴール

### 目的

`release-shared-lib.yml` (iOS xcframework / Android AAR / Linux/macOS/Windows shared lib) を SLSA Build L3 に昇格させる。

PR #511 後の現状:

- 既存 `release-shared-lib.yml` は **巨大** (1150+ 行、 9 jobs: build-shared / build-ios / assemble-xcframework / build-g2p-apple / assemble-g2p-xcframework / build-android / release / etc.)
- `release` job は既に `actions/attest-build-provenance@v3.2.0` で SLSA L2 相当の attestation 生成済。 subject-path = `artifacts/**/*.tar.gz; artifacts/**/*.zip` で **all release asset を一括 subject 化**
- SLSA L3 化には `slsa-github-generator` 経由で provenance を **再生成** (またはL2 と共存)、 かつ all subject の sha256 を `base64-subjects` に集約する

### ゴール (Done definition)

- [ ] **AC-2.1**: 以下コマンドが全 release asset で exit 0 を返す:

  ```bash
  for asset in libpiper_plus-ios-arm64-v1.13.0.tar.gz \
               libpiper_plus-ios-v1.13.0.xcframework.zip \
               libpiper_plus_g2p-apple-v1.13.0.xcframework.zip \
               libpiper_plus-android-arm64-v8a-v1.13.0.tar.gz \
               libpiper_plus-android-armeabi-v7a-v1.13.0.tar.gz \
               libpiper_plus-android-x86_64-v1.13.0.tar.gz \
               libpiper_plus-linux-x64.tar.gz \
               libpiper_plus-macos.tar.gz \
               libpiper_plus-windows-x64.zip; do
    slsa-verifier verify-artifact "$asset" \
      --provenance-path provenance.intoto.jsonl \
      --source-uri github.com/ayutaz/piper-plus \
      --source-tag v1.13.0
  done
  ```

- [ ] **AC-2.2**: OpenSSF Scorecard score 維持。
- [ ] `v1.13.0-rc.X` RC release で **全 subject** の attestation 生成 + verify exit 0 確認。
- [ ] `docs/reference/slsa-verify.md` に **shared-lib セクション** 追加。 9 種 subject の verify 例を全て記載。
- [ ] hermetic build: 既存 `v*` (release prefix) tag-only trigger 維持、 `workflow_dispatch` は既存 PR build path のみで attestation 対象外 (既存挙動維持)。
- [ ] **既存 attest-build-provenance との共存** (DEP-2.1)。 既存 attestation も release asset に残す。

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `.github/workflows/release-shared-lib.yml` | 変更 | `release` job の最後に **複数 subject** の sha256 を集約 → `outputs.hashes` に export。 新 job `slsa-provenance` を追加 (sub-workflow 呼び出し) |
| `docs/reference/slsa-verify.md` | 変更 | shared-lib セクション追加。 9 種 subject の verify 例を全て記載 |
| `docs/spec/slsa-provenance-contract.toml` | 変更 | shared-lib 行追加 (subject = multi-platform binary、 subject 件数 9+) |
| `scripts/generate_slsa_subjects.sh` | 新規 | `artifacts/**/*.{tar.gz,zip}` を walk して `<sha256>  <basename>` を改行区切りで stdout 出力するヘルパー (release job 内で使用、 base64 encoding は workflow YAML 側で実施) |

### 2.2 処理シーケンス

```text
1. tag push (refs/tags/v<version>) で trigger
2. 既存 build jobs (build-shared / build-ios / assemble-xcframework / build-g2p-apple /
   assemble-g2p-xcframework / build-android) は変更なし
3. release job:
   a. 既存 step (artifact download / rename / LICENSE_ATTRIBUTIONS / checksums / checksum 検証) 維持
   b. *新規*: scripts/generate_slsa_subjects.sh で artifacts/**/*.{tar.gz,zip} から sha256 集約
      → /tmp/slsa-subjects.txt (9+ 行)
      → base64 encode → outputs.hashes
   c. *既存維持*: actions/attest-build-provenance@v3.2.0 で attestation 生成
   d. *既存維持*: gh release create + asset upload
4. *新規 job* slsa-provenance:
   needs: [release]
   uses: slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v2.X.X
   with:
     base64-subjects: ${{ needs.release.outputs.hashes }}
     upload-assets: true
     provenance-name: piper-plus-v<version>.intoto.jsonl
   permissions:
     id-token: write
     contents: write
     actions: read
5. defensive log: "Generated SLSA L3 provenance for piper-plus v<version> (subjects: N artifacts, total sha256 hash: <combined>)" を stderr に echo
```

### 2.3 既存資産との接続

- **流用**:
  - T-019 / T-020 / T-021 で確立した hash 計算 / generator 呼び出し pattern
  - `release` job 既存の checksum 計算 step (`find . -type f \( -name "*.tar.gz" -o -name "*.zip" \) -exec sha256sum {} \; > checksums-sha256.txt`) を base64 encoding 用に流用
- **共存**:
  - `actions/attest-build-provenance@v3.2.0` (既存) と `slsa-github-generator` (新規) を両方動作
  - `cosign-release-artifacts.yml` (M1) も release published trigger で動作継続
- **補完関係**: 配信 (GitHub Release) は既存どおり、 検証層 (provenance) を 2 重に強化。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | `release-shared-lib.yml` の release job 改変、 `generate_slsa_subjects.sh` 新規、 slsa-provenance job 追加 | workflow YAML + script |
| **Test author** | 1 | RC release plan、 `slsa-verifier verify-artifact` を 9 種 subject 全て検証する script | RC 検証手順 |
| **Spec / Doc author** | 1 | `docs/reference/slsa-verify.md` の shared-lib セクション (9 種 verify 例)、 `slsa-provenance-contract.toml` shared-lib 行 | docs |
| **Release engineer** | 1 | 既存 9-job graph (build → assemble → release) との依存追加の整合性確認、 wall clock 影響 (slsa-provenance job は ~5 分追加) | 運用手順 |
| **Reviewer** | 1 | maintainer cross-cutting (9 subject 集計 logic + RC tag round 手順) | review |

**並列度**: Implementer + Doc author 並列、 Test author + Release engineer は RC round に逐次。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `release-shared-lib.yml` の `release` job への hash 集約 + `slsa-provenance` job 追加
- 9+ 種 subject (iOS / G2P iOS / Android 3 ABI / Linux / macOS / Windows) の provenance
- `docs/reference/slsa-verify.md` の shared-lib セクション

**Out of scope**:

- `Package.swift` の checksum 機構との連動 (既存、 独立)
- HuggingFace mirroring (release asset の HF 配布は別 workflow、 SLSA 対象外)
- M3.2 LICENSE_ATTRIBUTIONS.md / MODEL_CARD.md (既存、 attestation subject に含めない方針)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `generate_slsa_subjects.sh` | `artifacts/` directory に 9 asset | 9 行の `<sha256>  <basename>` を stdout 出力 |
| UT-2 | hash 集約 base64 encoding | 9 行 stdin | `base64 -w 0` で単一行出力 (改行 escape) |
| UT-3 | slsa generator 呼び出し | 9 subject base64 | `*.intoto.jsonl` (subject array に 9 件) が release asset に upload |
| UT-4 | 既存 attest-build-provenance と subject 一致 | 既存 attestation の subject 数 | 新規 intoto.jsonl の subject 数と一致 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | `v1.13.0-rc.1` tag push → full run (9 build jobs + release + slsa-provenance) | `gh run view` で全 job green |
| E2E-2 | 9 種 release asset 全部で `slsa-verifier verify-artifact` exit 0 | `scripts/test_slsa_verify.sh` を for loop で 9 回実行 |
| E2E-3 | iOS Package.swift checksum 検証が通る (既存 step) | release job log 確認 |
| E2E-4 | RC release で `--draft` で publish、 verify 後に prod upgrade or delete | `gh release edit v1.13.0-rc.1 --draft=false` 後の cleanup |
| E2E-5 | OpenSSF Scorecard re-run | baseline 維持 |

### 4.4 リグレッション確認

- [ ] 既存 9-job pipeline が動作継続 (`build-shared` / `build-ios` / `assemble-xcframework` / `build-g2p-apple` / `assemble-g2p-xcframework` / `build-android` / `release`)
- [ ] 既存 `attest-build-provenance` の attestation が release asset に存在
- [ ] `cosign-release-artifacts.yml` の keyless 署名が release published trigger で動作
- [ ] `Package.swift` の `checksum` / `g2pChecksum` 検証 step が通る
- [ ] silent-zero 防御: `subjects: N artifacts` の N が 9 未満なら `::warning::` (asset 漏れ検出)
- [ ] wall clock 増加 (slsa-provenance job ~5 分追加) が許容範囲

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | 9+ subject の hash 集約で 1 つでも漏れると attestation 不完全 | `generate_slsa_subjects.sh` が expected_count=9 を必須化、 不足時 exit 1 | UT-1 + defensive log |
| C-2 | release job の wall clock が +5 分 (既存 ~30 分 → ~35 分) で release cycle 影響 | slsa-provenance job は release job と並列化 (`needs: [release]` ではなく `needs: [build-shared, build-ios, ...]` で並列開始) | NFR-1.1 確認 |
| C-3 | iOS xcframework / G2P xcframework の checksum と Package.swift の整合性 | 既存 step が SLSA より先に動作、 hash 計算は同一 sha256 ベースで競合なし | review |
| C-4 | Android 3 ABI のうち 1 ABI build 失敗時の subject 集合変動 | `fail-fast: false` で動作継続するが、 release job の `needs:` に全 ABI 必須、 1 ABI 落ちれば release job 自体が fail (既存挙動維持) | workflow graph |
| C-5 | RC release が `--draft` で publish された場合、 `slsa-verifier` の `--source-tag` が見つかるか | `--draft=false` 後に verify、 または draft 状態でも `gh release view --json` で asset URL 取得可能 | E2E-2 で確認 |
| C-6 | 既存 attest-build-provenance の `subject-path: artifacts/**/*.{tar.gz,zip}` と slsa-github-generator の base64-subjects 集合が **乖離** | `generate_slsa_subjects.sh` が同じ glob pattern を使用、 fixture test で一致確認 (UT-4) | UT-4 |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern (subject 0 件で success) を fixture test で再現
- [ ] action SHA pin `@v<X.Y.Z>` 形式
- [ ] `permissions:` least privilege (release: `contents: write, id-token: write, attestations: write` 既存維持、 slsa-provenance: `id-token: write, contents: write, actions: read`)
- [ ] hermetic build (tag-only trigger、 workflow_dispatch は PR-build path のみで attestation 対象外)
- [ ] RC release で 9 種 verify exit 0 (AC-2.1)
- [ ] OpenSSF Scorecard baseline 維持
- [ ] `docs/reference/slsa-verify.md` の shared-lib セクションが 9 種 verify 例を網羅
- [ ] `generate_slsa_subjects.sh` の expected_count=9 が hardcode せず、 glob pattern からの実数を使用 (asset 追加時の自動追従)
- [ ] markdownlint MD032 全 doc pass
- [ ] PR 本文が `pull_request_template.md` 準拠

---

## 6. 一から作り直すとしたら

### 案 A: `slsa-github-generator` を使わず自前で in-toto attestation 生成

- **概要**: T-019 §6 案 A と同じ。 自前 in-toto + cosign sign-blob。
- **長所**: 9+ subject 構成の自由度極大。 例えば `predicate.attestation_type` に builder の matrix config (NDK version / ORT version / etc.) を埋め込み可能。
- **短所**: SLSA L3 verify 失敗、 Scorecard score down。 T-019 〜 T-021 で確立した pattern との不整合。
- **採否**: 採用しない。 T-018 (Maven) の fallback として記録。

### 案 B: subject を **代表 manifest** に集約 (TUF / in-toto-attestation の collection 機能利用)

- **概要**: 9 個別 asset を subject にせず、 `checksums-sha256.txt` (既存) を **唯一の subject** にし、 `predicate` に詳細を構造化する。 downstream user は manifest を取得 → 各 asset の checksum を検証 → 個別 asset を separately download。
- **長所**:
  - attestation 1 個で 9 asset を間接 attest、 SLSA generator への base64-subjects 渡しが 1 行で完結
  - manifest pattern は 既存 `model-sha256-manifest.toml` (M2) と整合
- **短所**:
  - `slsa-verifier verify-artifact` は subject 直接検証が期待動作、 manifest 間接検証は **standard SLSA L3 pattern ではない**
  - downstream user に 2 step 検証 (manifest verify + asset hash check) を強要、 UX 悪化
  - downstream tool (`gh attestation verify` 等) が manifest pattern 未対応
- **採否**: 採用しない。 ただし v2 設計時に SLSA spec が `subject collection` を正式 support した場合は再評価。

### 結論

現時点での選択は **9+ subject を直接 base64-subjects に渡す** (Implementer 案)。 案 B は SLSA spec の現状と非整合。 v2 では SLSA spec evolution を見て再評価。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-018 (Maven Central、 GPG 共存最難関)
- **連携 milestone**: M3 残 1 件
- **依存解消**: T-018 で「複数 classifier (AAR / sources JAR / javadoc JAR) を subject にする pattern」 が必要。 本 ticket で 9+ subject 集約 pattern が確立されたため、 T-018 は classifier 別の subject 構成のみが残課題

### 7.2 引き継ぎ事項 (Handoff)

- **`generate_slsa_subjects.sh` の expected_count 検出 logic**: `find artifacts -type f \( -name "*.tar.gz" -o -name "*.zip" \)` で集めた件数を `RELEASE_ASSET_COUNT` として `${GITHUB_OUTPUT}` に export、 release notes auto-update で利用可能。 asset 追加時 (例: ARM64 macOS shared lib 追加) は glob pattern 自動追従、 hardcode 不要。
- **複数 subject の base64 encoding**:

  ```bash
  scripts/generate_slsa_subjects.sh artifacts/ | base64 -w 0
  ```

  単一行に圧縮 (改行を `\n` escape ではなく base64 内に encoding)。 slsa-github-generator は base64 decode 後に行分割して subject array に展開。

- **既存 `attest-build-provenance` との subject 一致確認**: 両 attestation が同一 sha256 を subject とすることを `gh attestation verify` で確認可能。 一致しない場合は `generate_slsa_subjects.sh` の glob pattern を `attest-build-provenance` の `subject-path` に合わせる (`artifacts/**/*.{tar.gz,zip}`)。
- **wall clock 影響**: slsa-provenance job は release job と並列化可能 (`needs: [build-shared, build-ios, assemble-xcframework, build-g2p-apple, assemble-g2p-xcframework, build-android]` で release と同タイミング開始)。 ただし `outputs.hashes` を取るために release job 経由が必要なら逐次化必須。 trade-off を maintainer 判断。
- **T-018 への申し送り**: Maven AAR + sources JAR + javadoc JAR + POM の 4 種 classifier を subject にする必要あり (CON-2.2)。 本 ticket と同じ `generate_slsa_subjects.sh` pattern を Maven 用に複製 (`generate_slsa_subjects_maven.sh`) し、 classifier 別に subject 構成。

### 7.3 未解決の質問

- [ ] M3.2 LICENSE_ATTRIBUTIONS.md / MODEL_CARD.md を subject に含めるか。 現案は **含めない** (binary asset のみ、 doc は git ref で trust)。
- [ ] release-shared-lib.yml の wall clock が許容範囲 (slsa-provenance job ~5 分追加で release cycle に影響なし) かを user 判断。

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.2 (`#2`)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.4 (`#2` overview)
- Milestone: [`docs/tickets/milestones/M3-supply-chain.md`](../milestones/M3-supply-chain.md)
- 既存 workflow: [`.github/workflows/release-shared-lib.yml`](../../../.github/workflows/release-shared-lib.yml)
- 関連 ticket: [`T-019-slsa-rust-g2p.md`](T-019-slsa-rust-g2p.md), [`T-020-slsa-go-g2p.md`](T-020-slsa-go-g2p.md), [`T-021-slsa-npm.md`](T-021-slsa-npm.md)
- 関連 workflow: [`.github/workflows/cosign-release-artifacts.yml`](../../../.github/workflows/cosign-release-artifacts.yml) (M1、 keyless 署名)
- 外部: SLSA framework <https://slsa.dev/spec/v1.0/>, slsa-github-generator <https://github.com/slsa-framework/slsa-github-generator>

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
