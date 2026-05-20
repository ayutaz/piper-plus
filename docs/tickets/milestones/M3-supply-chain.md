# M3: Supply Chain (Tier 3、 大規模 / release blast radius)

**Milestone ID**: `M3`
**Tier**: Tier 3
**Status**: 計画中
**期間目安**: M2 merge 後 〜 8 週間 (10 チケット × 1 PR / 1 image or registry)
**前提**: M1 完了 (`cosign verify-blob` 運用定着) + M2 完了 (`model-sha256-manifest.toml` / `release-versions.toml` 整備済み)

---

## 1. 目的

供給網 (supply chain) の防御層を 2 軸で強化する:

- **#1 Distroless 移行**: container image の attack surface を最小化 (image size 50%+ 削減 / CVE 80%+ 削減を目標)
- **#2 SLSA Build L3**: release artifact に in-toto provenance attestation を付与し、 downstream user が `slsa-verifier` で source repo / build environment を検証可能に

両者とも **1 PR で 1 image / 1 registry** の cadence。 一括移行禁止 (R-2 / R-4 緩和)。

> **2026-05-20 scope 変更**: Distroless は **5 image → 4 image** に縮小。 cpp-dev (T-016) は scope-out 確定。 理由は PR #524 で spike 目的 (multi-stage pattern / ABI 整合 / entrypoint 移植) が webui + cpp-inference の trial bundle により達成済、 加えて dev image は distroless 哲学と本質的に不整合 (cmake/gdb 等を final stage に残さざるを得ない) で大目的への寄与が限定的なため。 詳細は PR #526 (scope-out 確定) を参照。 旧 T-016 ticket file は削除済 (git history で参照可能)。

---

## 2. 配下チケット

### Distroless × 4 image (`python-train` は GPU CUDA toolkit 依存で対象外、 `cpp-dev` は 2026-05-20 scope-out)

| ID | タイトル | 提案項目 | 影響範囲 | Status | PR |
|----|--------|---------|--------|--------|----|
| [T-012](../tickets/T-012-distroless-python-inference.md) | `python-inference` distroless 化 | `#1-1` | HF Space deploy | 着手中 (trial merged 2026-05-20、 promotion 観測中) | #523 |
| [T-013](../tickets/T-013-distroless-webui.md) | `webui` distroless 化 | `#1-2` | Gradio demo | 着手中 (trial merged 2026-05-20、 promotion 観測中) | #524 |
| [T-014](../tickets/T-014-distroless-wyoming.md) | `wyoming` distroless 化 | `#1-3` | Home Assistant addon | 計画中 | — |
| [T-015](../tickets/T-015-distroless-cpp-inference.md) | `cpp-inference` distroless 化 | `#1-4` | C++ runtime image | 着手中 (trial merged 2026-05-20、 promotion 観測中) | #524 |

> `cpp-dev` (旧 T-016) は 2026-05-20 scope-out 確定 (PR #526)。 spike 目的が PR #524 で達成済 + dev image 構造的不整合のため除外。 ticket file は削除済み、 経緯は git history (PR #524 / #526) を参照。

### SLSA L3 × 5 registry (PyPI / NuGet は新設要否を user 判断)

| ID | タイトル | 提案項目 | 対象 workflow | Status | PR |
|----|--------|---------|------------|--------|----|
| [T-017](../tickets/T-017-slsa-shared-lib.md) | SLSA L3 for shared-lib (iOS xcframework / AAR) | `#2-1` | `release-shared-lib.yml` | 計画中 | — |
| [T-018](../tickets/T-018-slsa-kotlin-g2p.md) | SLSA L3 for Maven Central (Kotlin G2P) | `#2-2` | `release-kotlin-g2p.yml` | 計画中 | — |
| [T-019](../tickets/T-019-slsa-rust-g2p.md) | SLSA L3 for crates.io (Rust G2P) | `#2-3` | `g2p-rust-publish.yml` | 計画中 | — |
| [T-020](../tickets/T-020-slsa-go-g2p.md) | SLSA L3 for Go module | `#2-4` | `g2p-go-publish.yml` | 計画中 | — |
| [T-021](../tickets/T-021-slsa-npm.md) | SLSA L3 for npm | `#2-5` | `npm-publish.yml` | 計画中 | — |

### 依存関係

- Distroless 4 件は互いに独立、 並列実装可 (cpp-dev による spike は PR #524 で webui + cpp-inference の trial bundle に置換され達成済、 残 T-012 / T-014 は trial 観測期間後の promotion + canonical 置換が主タスク)
- SLSA L3 5 件も互いに独立だが、 **最初の 1 件 (推奨: T-019 crates.io、 GPG 署名共存制約なし)** を merged して運用知見を取ってから残 4 件に着手 (R-2 緩和)
- Distroless と SLSA L3 は independence (異なる workflow を扱う)

---

## 3. 受け入れ基準 (Milestone レベル)

### Distroless 共通 AC

- [ ] 各 image: `docker compose up <service>` で起動成功 (AC-1.1a)
- [ ] image size 50%+ 削減 (AC-1.1b、 例: 150MB → 75MB 以下)
- [ ] `trivy image --severity HIGH,CRITICAL` で CVE 数 80%+ 削減 (AC-1.1c)
- [ ] HF Space (T-012) / HA addon (T-014) の deploy 後動作確認手順を user 手動 step で Test Plan に記載 (AC-1.2)
- [ ] PR comment に `docker/<image>/distroless-report.md` (size + CVE diff) 自動投稿 (FR-1.4)

### SLSA L3 共通 AC

- [ ] `slsa-verifier verify-artifact <asset> --provenance-path <intoto.jsonl> --source-uri github.com/ayutaz/piper-plus --source-tag <RC tag>` が exit 0 (AC-2.1)
- [ ] OpenSSF Scorecard の `Token-Permissions` / `SAST` 以外の項目で score 低下なし (AC-2.2)
- [ ] Maven Central (T-018) は GPG 署名と attestation が共存 (AC-2.3)
- [ ] `docs/reference/slsa-verify.md` (新規) で downstream user 検証手順を提供 (FR-2.5)

---

## 4. 一から作り直すとしたら (Phase rethink)

### 設計思考: そもそも release pipeline を「supply chain 最優先」 で再設計するなら

現在の release 構造は **historical な経緯** で成立している:

- `cosign-release-artifacts.yml` (keyless 署名、 後付け)
- 各 registry に dedicated workflow (Maven / npm / Go / Rust / shared-lib / etc.)
- PyPI / NuGet は dedicated workflow なし (`dev-create-release.yml` 経由?)
- Distroless は未導入、 Dockerfile は debian-slim ベース

代替案: **release pipeline を白紙再設計**。 「v1.13 から全 release を SLSA L3 + Distroless + Rekor verify trio で出す」 を 1 PR で実現。

#### 長所

- supply chain 防御層が **同時に揃う** → downstream user が release を信用できる時点が明確
- release workflow 数の削減 (共通化された 1 reusable workflow を全 registry から呼ぶ)
- Maven AAR / JAR の attestation subject 設計など、 cross-registry の共通課題を 1 度に解く

#### 短所

- **blast radius が極大** (1 PR で全 registry / 全 image を変更 → 次 release が ship 不能になるリスク = R-2 を最大化)
- review burden が極大 (5 registry × 5 image = 25 軸を 1 PR で評価不可能)
- 既存 ayousanz の release 運用との互換性検証が困難 (RC release を 1 round 回すだけでは網羅できない)

#### 結論

**v1 では現方針 (1 PR / 1 unit) を絶対遵守**。 ただし M3 完了後、 「supply chain 統合 reusable workflow」 (`.github/workflows/_supply-chain-release.yml`) として **後付けで refactor** する余地を残す。 これは M3 retrospective で判定。

### 設計思考: Distroless ではなく "minimal base" 全般を検討

要求定義 FR-1.2 は `cgr.dev/chainguard/<base>` または `gcr.io/distroless/<base>` の二択。 だが「supply chain 防御目的の minimal image」 にはほかにも選択肢がある:

代替案 A: **Wolfi** (`cgr.dev/chainguard/wolfi-base`) — Chainguard が公開する apk-based distro、 distroless より柔軟 (シェル / ca-certificates 同梱)
代替案 B: **Alpine + multi-stage** — node:alpine / python:alpine。 musl libc 互換問題はあるが size は最小
代替案 C: **Bottlerocket** — AWS の host OS、 container 専用、 SELinux integrated

#### 長所 (Wolfi)

- distroless の「shell なし / debug 不能」 問題を回避
- update cadence が distroless より早い (CVE 対応 lag が小)
- Chainguard と同じく cryptographic provenance あり

#### 短所 (Wolfi)

- 採用事例が distroless より少ない (HF Space / HA addon の互換性が未検証)
- apk packaging に詳しい maintainer が必要

#### 結論

**v1 では distroless / Chainguard の二択 (FR-1.2 通り)**。 T-012 (`python-inference`) 着手前に Wolfi base を **1 つだけ spike** し、 size / CVE / 起動成功を測定。 spike 結果を M3 retrospective で総括し、 残 4 image で Wolfi 採用するか判定。

### 設計思考: SLSA L3 ではなく「自前 provenance」 でいいのではないか

SLSA L3 は **builder identity + isolation + non-falsifiable provenance** を要件とする。 slsa-github-generator を呼ぶことで GitHub Actions 環境が builder identity (`https://github.com/slsa-framework/slsa-github-generator/...`) として記録される。

代替案: **自前で in-toto attestation を生成し、 cosign sign で署名するだけ**

```bash
in-toto-attestation create --predicate-type https://slsa.dev/provenance/v1 \
  --subject '<asset>' --predicate '<generated-predicate.json>' > attestation.intoto.jsonl
cosign sign-blob --keyless ... attestation.intoto.jsonl > attestation.sig
```

#### 長所

- SLSA L3 要件 (`slsa-github-generator` 呼び出し) を満たさずとも、 provenance + 署名は持てる
- workflow の hermetic build 化 (FR-2.4) が optional に
- `subject` の構成を自由に設計可能 (Maven AAR / JAR classifier 等のエッジケースに柔軟)

#### 短所

- `slsa-verifier verify-artifact` の **L3 expectation を満たさない** → AC-2.1 が pass しない
- OpenSSF Scorecard で「`SLSA` 項目が score down」 (AC-2.2 違反)
- downstream user が「これは SLSA L3 ではない」 と認識する必要があり、 マーケティング上の意義が消える

#### 結論

**v1 では SLSA L3 (slsa-github-generator 経由) を採用 (FR-2.2 通り)**。 自前 attestation は「L3 が技術的に困難な workflow があった場合の最終手段」 として T-017 / T-018 の Maven Central (AAR/JAR classifier の subject 設計が複雑) の挫折時 fallback として記録。

---

## 5. リスクと対策 (Milestone 共通)

| ID | リスク | 対策 |
|----|------|------|
| M3-R1 | release pipeline 改変で次 release が ship 不能 (R-2 = 要求定義 §7) | RC release 必須 (FR-2.3)、 1 registry / 1 PR、 RC で `slsa-verifier` exit 0 確認後に prod release |
| M3-R2 | Distroless 移行で HF Space / HA addon の cold start 失敗 (R-4) | 1 image / 1 PR、 user 手動 deploy 検証を Test Plan に必須化 (AC-1.2) |
| M3-R3 | `pyopenjtalk` C 拡張の multi-stage build が distroless final stage で動作しない | T-012 / T-013 / T-014 着手前に「builder stage の gcc 出力を final stage で実行」 spike を 1 件実施 |
| M3-R4 | Maven Central GPG 署名と SLSA attestation の干渉 (AC-2.3) | T-018 着手前に既存 `gpg --verify` step を Test Plan で明示確認、 attestation upload step を GPG step と別 job に分離 |
| M3-R5 | OIDC token (`id-token: write`) 過剰付与で security review fail | 各 workflow で SLSA / cosign 用途の job のみ `id-token: write`、 他 job は default `contents: read` 維持 (NFR-2.1) |

---

## 6. 後続 Milestone への申し送り

### M4 へ

- M3 完了後の `cosign-release-artifacts.yml` + SLSA generator の **dual-protection 状態** を mkdocs (T-022) の release guide に反映
- T-023 (test aggregation) は SLSA attestation の `subject` に 7 runtime の test-results.xml hash を含める拡張余地あり (M3 完了後の M4 設計時に判定)

### post-M3 retrospective へ

- 1 reusable workflow への refactoring 採否 (`.github/workflows/_supply-chain-release.yml`)
- Wolfi base 採用の spike 結果
- 自前 attestation fallback の必要性 (Maven Central T-018 結果次第)

### release notes / docs へ

- T-017 〜 T-021 完了で `docs/reference/slsa-verify.md` が完成 (FR-2.5) → 全 release notes に「Verifying artifacts with SLSA」 セクション追加
- T-012〜T-016 完了で各 Dockerfile の base image が変更 → README の Quick Start docker pull コマンド更新

---

## 7. 関連ドキュメント

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.1 / §4.2
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.3 / §4.4
- 既存 release workflow: `.github/workflows/release-*.yml`, `cosign-release-artifacts.yml`
- 親 index: [`../README.md`](../README.md)
- 外部: SLSA framework <https://slsa.dev/spec/v1.0/>, in-toto <https://github.com/in-toto/attestation>

---

## 8. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
| 2026-05-20 | Distroless scope を 5 image → 4 image に縮小 (cpp-dev / T-016 scope-out 確定)。 PR #524 で webui (T-013) + cpp-inference (T-015) の trial bundle merged により spike 目的達成、 cpp-dev は production 経路なし & distroless 不整合で除外。 個別 ticket Status の merged 反映 (T-012 PR #523 / T-013 + T-015 PR #524) は別 PR で扱う。 | Claude Code |
