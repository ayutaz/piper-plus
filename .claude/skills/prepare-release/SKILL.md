---
name: prepare-release
description: 9 パッケージ × 5 レジストリの version bump と関連ファイル更新 (Cargo.lock / package-lock.json / Swift checksum / CHANGELOG 昇格) を 1 コマンドで適用案にする read-mostly skill。`release-prep` (確認用) の続きに呼び、 実 bump 差分の markdown 提案 + 順序付き publish ガイドを生成する。
argument-hint: "<runtime|all> --target-version X.Y.Z [--dry-run]"
disable-model-invocation: true
allowed-tools: Bash(cat *) Bash(grep *) Bash(jq *) Bash(rg *) Bash(awk *) Bash(curl -s *) Bash(npm view *) Bash(git diff *) Bash(git log *) Bash(git status *) Bash(swift package compute-checksum *) Read Edit Grep
---

# Release Preparation Skill (Bump 適用版)

`release-prep` (read-mostly な確認) の続きとして、 **実際の version bump 差分** を全 manifest にわたり生成する skill。

ユーザは memory `feedback_conservative_changes.md` / `feedback_merge_caution.md` に従い、 適用は明示確認を取ってから (デフォルト dry-run、 markdown diff 提示のみ)。

## カバー範囲

| 段階 | 対応 |
|------|------|
| Version 散在検出 | 9 manifest を一括 bump 案として markdown 出力 |
| Lockfile 再生成 | uv.lock / Cargo.lock / package-lock.json の更新コマンド提示 |
| Swift checksum | xcframework artifact 取得後の `swift package compute-checksum` 手順 |
| CHANGELOG 昇格 | `[Unreleased]` → `[X.Y.Z] - YYYY-MM-DD` の markdown diff |
| Tag 順序ガイド | npm tag (g2p 先行) / shared-lib tag / 内部 chain tag の順序 |
| 公開後検証 | 各 registry で publish 完了確認の手順 |

## 引数

- `$ARGUMENTS` 1 つ目: `all` / `python` / `rust` / `csharp` / `npm` / `swift` / `kotlin`
- `--target-version X.Y.Z`: 次回リリース version (必須)
- `--dry-run` (default): markdown 出力のみ、 ファイル変更しない
- `--apply`: dry-run の確認後にユーザが追加で渡す flag。 これがある時のみ Edit を実行

## 現在の状態

- ブランチ: !`git rev-parse --abbrev-ref HEAD`
- 引数: $ARGUMENTS
- 直近 tag: !`git tag --sort=-v:refname | head -3`

## フェーズ 1: 現 manifest version 読み出し (9 ファイル)

並列で Read し、 各 manifest の現 version を抽出:

| Runtime | Manifest | 抽出キー |
|---------|----------|---------|
| Python | `VERSION` | ファイル全体 |
| Python (g2p) | `src/python/g2p/pyproject.toml` | `[project].version` |
| Rust | `src/rust/Cargo.toml` | `[workspace.package].version` |
| C# Core | `src/csharp/PiperPlus.Core/PiperPlus.Core.csproj` | `<Version>` |
| C# Cli | `src/csharp/PiperPlus.Cli/PiperPlus.Cli.csproj` | `<Version>` |
| npm synth | `src/wasm/openjtalk-web/package.json` | `.version` |
| npm g2p | `src/wasm/g2p/package.json` | `.version` |
| Swift | `Package.swift` | `let version =` 行 + `let g2pVersion =` 行 |
| Kotlin | `android/gradle.properties` | `VERSION_NAME=` |

## フェーズ 2: 既存 sync gate との交差確認

```bash
uv run python scripts/check_voice_catalog_parity.py 2>&1 | tail -3
uv run python scripts/check_ort_versions.py 2>&1 | tail -3
uv run python scripts/check_openjtalk_version_sync.py 2>&1 | tail -3
uv run python scripts/check_ruff_version_sync.py 2>&1 | tail -3
uv run python scripts/check_migration_changelog_parity.py 2>&1 | tail -3
```

drift があれば bump 前に修復するよう警告。

## フェーズ 3: Bump diff の markdown 提示

`--target-version` を基準に、 該当 runtime の manifest 全てに対する diff を markdown 出力:

出力例 (markdown):

- Python (`VERSION`): `1.12.0` → `1.13.0`
- Rust (`src/rust/Cargo.toml` `[workspace.package].version`): `0.4.0` → `0.5.0`
- npm synth (`src/wasm/openjtalk-web/package.json`): `0.6.0` → `0.7.0`

`all` の場合は 9 manifest 全てを順次出力する。

## フェーズ 4: Lockfile 再生成手順

```bash
# Python
uv lock --upgrade-package piper-plus
# Rust
(cd src/rust && cargo update -p piper-plus)
# npm synth
(cd src/wasm/openjtalk-web && npm install --package-lock-only)
# npm g2p
(cd src/wasm/g2p && npm install --package-lock-only)
```

`--apply` 時は順次実行、 そうでなければコマンドのみ表示。

## フェーズ 5: Swift checksum 計算ガイド

Package.swift の `checksum` / `g2pChecksum` は **tag commit に存在していなければならない** (SwiftPM は tag の git ref の manifest を解決し、checksum 不一致なら `artifact has changed checksum` で fail。release-shared-lib.yml の release job も tag push 時に placeholder / 不一致を hard-fail させる)。よって **tag push 前** に実施する (`gh release download` は release がまだ無いので使えない):

```bash
# 1. release-shared-lib.yml を tag 無しで workflow_dispatch 実行し artifact を生成
gh workflow run release-shared-lib.yml --ref dev
# 完了後、run の workflow artifact を取得 (release ではない)
gh run download <run-id> --name libpiper_plus-ios-xcframework
# g2pChecksum は g2pVersion が今回 tag と一致する時のみ取得・更新
gh run download <run-id> --name libpiper_plus_g2p-apple-xcframework

# 2. swift package compute-checksum (workflow artifact のファイル名は version 無し)
swift package compute-checksum libpiper_plus-ios.xcframework.zip
swift package compute-checksum libpiper_plus_g2p-apple.xcframework.zip   # g2pVersion == TARGET のみ

# 3. Package.swift の `let checksum` (synthesis) を更新。
#    `let g2pChecksum` は g2pVersion が今回 tag と一致する時のみ更新
#    (異なる場合 release-shared-lib.yml が g2p checksum 検証を自動 skip する)。

# 4. dev に commit し、その commit に v<TARGET_VERSION> tag を push (フェーズ 7 の順序)
```

workflow_dispatch build と tag build は deterministic なので checksum は一致する。**この手順は tag push の直前** (フェーズ 7)。 dry-run でも手順を出力する。

## フェーズ 6: CHANGELOG 昇格 markdown diff

```bash
awk '/^## \[Unreleased\]/{flag=1; next} /^## /{flag=0} flag' CHANGELOG.md
```

を抽出し、 以下を提案:

```markdown
## [<TARGET_VERSION>] - <YYYY-MM-DD>

(Unreleased から移動した内容)

## [Unreleased]

(空 or next-version 着手項目)
```

`--apply` で直接 Edit、 そうでなければ diff のみ出力。

## フェーズ 7: Publish 順序ガイド

CONTRIBUTING.md の規約に従い、 tag push 順序を明示:

1. **First**: `wasm-g2p-v<X.Y.Z>` (npm `@piper-plus/g2p`) — g2p に変更が無く既公開なら skip
2. **Second**: `npm-v<X.Y.Z>` (npm `piper-plus`、 g2p に依存)
3. **Third**: `dev-create-release.yml` を **workflow_dispatch** (version 入力) で実行
   → PyPI / crates.io / NuGet を sleep 30 入りで連鎖 publish。 **tag 駆動ではない** (Actions UI から手動実行)
4. **Fourth**: `kotlin-g2p-v<X.Y.Z>` (Maven Central、 独立) — 既公開なら skip
5. **Fifth**: **Package.swift の `checksum` を pre-tag 更新** (フェーズ 5 の workflow_dispatch artifact から compute-checksum → dev に commit)
6. **Last**: その checksum commit に `v<X.Y.Z>` tag を push → release-shared-lib.yml (libpiper_plus + iOS/Android xcframework)

> **重要 (フェーズ 5 参照):** Swift checksum 更新は `v<X.Y.Z>` tag の **前** (ステップ 5)。 placeholder のまま tag を push すると release-shared-lib.yml の release job が hard-fail し、 post-tag の後追い PR では SwiftPM 解決を救済できない (tag の git ref が解決対象のため)。
>
> 順序逆転による npm install 失敗 (g2p が無いと `piper-plus` install fail) も防ぐ。 `v<X.Y.Z>` tag は release-shared-lib.yml と **docker-build.yml を同時発火**させ、 Docker image (`<X.Y.Z>` / `latest`) も自動 publish される点に留意。

## フェーズ 8: 公開後検証コマンド

```bash
# 各 registry で publish 完了を確認
curl -s https://pypi.org/pypi/piper-plus/json | jq -r '.info.version'
curl -s https://crates.io/api/v1/crates/piper-plus | jq -r '.crate.max_version'
npm view piper-plus version
npm view @piper-plus/g2p version
curl -s "https://api.nuget.org/v3-flatcontainer/piperplus.core/index.json" | jq -r '.versions[-1]'
curl -s "https://search.maven.org/solrsearch/select?q=g:io.github.ayutaz+AND+a:piper-plus-g2p-android&rows=1&wt=json" | jq -r '.response.docs[0].latestVersion'
```

target version と一致するまで sleep 30 で polling、 30 分以内に揃わなければエラー報告。

## 注意

- **既存 release-prep skill との関係**: `release-prep` は「現状の version 散在確認」、 本 skill は「次回 version へ bump する適用案生成」。 先に `release-prep` で drift を解消してから本 skill を使う流れが推奨。
- **memory feedback_merge_caution.md**: tag push / publish に類する操作は本 skill では実行しない。 手順表示のみ。
- **memory feedback_pr_no_milestones.md**: マイルストーン番号付与しない。
- **memory feedback_data_asset_distribution.md**: data asset 追加時の 7 manifest 同時更新も本 skill では確認のみ。
- **`--dry-run` がデフォルト** で、 `--apply` は明示指定が必要。

## 使用例

```text
# 全 runtime の v1.13.0 リリース bump 案を生成 (dry-run)
/prepare-release all --target-version 1.13.0

# Python だけ確定、 適用
/prepare-release python --target-version 1.13.0 --apply

# Rust 0.5.0 リリース、 lockfile 再生成手順のみ表示
/prepare-release rust --target-version 0.5.0
```

## 期待効果

- リリース時の **9 manifest 同時 bump** を 1 skill に集約 (現状: 手動 Read + Edit + Lock 再生成 + tag 順序記憶)
- **npm tag 順序違反** (g2p 先行必須) を強制チェック
- **Swift checksum 漏れ** の防止 (release-shared-lib.yml で fail する前にガイド)
- **CHANGELOG `[Unreleased]` 昇格** の規定化 (現状: 手動 markdown 編集)
- **publish 後検証** の自動化 (target version が registry に届くまで polling)
