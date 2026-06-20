---
name: release-prep
description: 7 ランタイム manifest の version 一覧表示、CHANGELOG `[Unreleased]` → `[X.Y.Z]` 移行支援、公開 registry の最新公開 version 確認を 1 コマンドで実行する read-mostly skill。`docs/spec/release-versions.toml` を canonical source として参照。
argument-hint: "[runtime] [--target-version X.Y.Z]"
disable-model-invocation: true
allowed-tools: Bash(cat *) Bash(grep *) Bash(jq *) Bash(curl -s *) Bash(npm view *) Bash(git diff *) Bash(git log *) Bash(git status *) Bash(rg *) Read Edit Grep
---

# Release Preparation Helper

リリース作業の **forensic check** と **CHANGELOG 移行支援** を 1 つにまとめた skill。手動でやると忘れがちな以下 4 段階を 1 コマンドで通す:

1. 各 manifest の **現在の version** を一覧化 (7 runtime × 9 manifest)
2. `release-versions.toml` の `expected_prefix` との照合
3. CHANGELOG.md `[Unreleased]` の内容と、リリース時に必要な **昇格作業** の提案
4. 公開 registry (PyPI / crates.io / NuGet / npm / Maven Central) の **最新公開 version** 取得

実装は **read-mostly** — 変更提案は markdown diff 形式でユーザに提示し、 適用は明示確認後 (memory `feedback_merge_caution.md` に従う)。

## 引数

- `$ARGUMENTS` 空: 全 runtime を一覧
- `python` / `rust` / `csharp` / `npm` / `swift` / `kotlin`: 特定 runtime のみ
- `--target-version X.Y.Z`: 次回リリース予定 version (CHANGELOG 移行提案に使う)

## 現在の状態

- ブランチ: !`git rev-parse --abbrev-ref HEAD`
- 引数: $ARGUMENTS
- canonical truth: !`grep -A1 "^\\[meta\\]" docs/spec/release-versions.toml | head -5`

## フェーズ 1: Manifest version 一覧

以下の 9 manifest を並列で Read し、現在の version を抽出して表化:

| Runtime | Manifest | 抽出キー |
|---------|----------|---------|
| Python (PyPI) | `VERSION` | ファイル全体 |
| Rust (crates.io) | `src/rust/Cargo.toml` | `[workspace.package].version` |
| C# Core (NuGet) | `src/csharp/PiperPlus.Core/PiperPlus.Core.csproj` | `<Version>` |
| C# Cli (NuGet) | `src/csharp/PiperPlus.Cli/PiperPlus.Cli.csproj` | `<Version>` |
| npm synthesis | `src/wasm/openjtalk-web/package.json` | `.version` |
| npm g2p | `src/wasm/g2p/package.json` | `.version` |
| Swift synthesis | `Package.swift` | `let version =` 行 |
| Swift G2P | `Package.swift` | `let g2pVersion =` 行 |
| Kotlin Android | `android/gradle.properties` | `VERSION_NAME=` |

```bash
# 例: rust workspace version
grep -A1 "^\[workspace.package\]" src/rust/Cargo.toml | grep "^version" | head -1
```

## フェーズ 2: Expected prefix との照合

`docs/spec/release-versions.toml` を tomllib で読み、各 manifest の `expected_prefix` を取得。フェーズ 1 の実 version が prefix で始まるかを照合:

```text
| Runtime | Manifest version | expected_prefix | Status |
|---------|------------------|-----------------|--------|
| Python  | 1.12.0           | 1.12.           | ✓      |
| Rust    | 0.4.0            | 0.4.            | ✓      |
| C# Core | 0.3.0            | 0.3.            | ✓      |
| ...     | ...              | ...             | ...    |
```

`mode = "warn"` でも、`fail` ステータスを report 上で強調表示。

## フェーズ 3: CHANGELOG.md 状況

```bash
# [Unreleased] セクション抽出
awk '/^## \[Unreleased\]/{flag=1; next} /^## /{flag=0} flag' CHANGELOG.md | head -60
```

集計:

- `[Unreleased]` 直下の sub-section 数 (h3 見出しの個数)
- 既存 release tag (`## [X.Y.Z]`) の最新 5 件
- `--target-version` 指定時は、 移行 markdown を提示:

```markdown
## [X.Y.Z] - YYYY-MM-DD

(Unreleased から移動した内容)

## [Unreleased]

(空または next-version の作業中項目)
```

ユーザに「これを CHANGELOG.md に適用していいか」明示確認 (memory `feedback_merge_caution.md` 準拠)。

## フェーズ 4: 公開 registry の最新 version

オプションで以下を取得 (rate limit を考慮し並列実行):

```bash
# PyPI
curl -s https://pypi.org/pypi/piper-plus/json | jq -r '.info.version'

# crates.io
curl -s https://crates.io/api/v1/crates/piper-plus | jq -r '.crate.max_version'
curl -s https://crates.io/api/v1/crates/piper-plus-cli | jq -r '.crate.max_version'

# NuGet
curl -s "https://api.nuget.org/v3-flatcontainer/piperplus.core/index.json" | jq -r '.versions[-1]'
curl -s "https://api.nuget.org/v3-flatcontainer/piperplus.cli/index.json" | jq -r '.versions[-1]'

# npm
npm view piper-plus version
npm view @piper-plus/g2p version

# Maven Central (search.maven.org)
curl -s "https://search.maven.org/solrsearch/select?q=g:io.github.ayutaz+AND+a:piper-plus-g2p-android&rows=1&wt=json" | \
    jq -r '.response.docs[0].latestVersion'
```

各 registry で取得失敗 (404 / timeout) は `<未公開>` として表示し fail にしない。

## フェーズ 5: ローカル vs 公開 vs canonical の 3-way 差分

```text
## Release Status

| Runtime | Local | Published | Canonical (.toml) | Verdict |
|---------|-------|-----------|-------------------|---------|
| Python  | 1.12.1 | 1.12.0   | 1.12.             | Local ahead → publish required |
| Rust    | 0.4.0 | 0.4.0     | 0.4.              | In sync |
| C# Core | 0.3.0 | 0.3.0     | 0.3.              | In sync |
| ...     | ...   | ...       | ...               | ...     |
```

Verdict 例:

- `In sync`: local == published == canonical prefix
- `Local ahead → publish required`: local が published より新しい
- `Canonical drift`: local が canonical prefix に該当せず → release-versions.toml 更新が必要
- `Published ahead → local bump needed`: published が新しい (hot fix されたケース等)
- `<未公開>`: registry に存在しない (initial release 直前)

## フェーズ 6: 推奨アクション

verdict に応じて推奨 next action を表示:

| Verdict | 推奨 |
|---------|------|
| `Local ahead → publish required` | `.github/workflows/release-*.yml` の trigger を確認、 dispatch |
| `Canonical drift` | `docs/spec/release-versions.toml` の expected_prefix を更新、 CI gate flip 可否を判断 |
| `Published ahead → local bump needed` | 当該 manifest の version を bump、CHANGELOG に記録 |

## 注意事項

- **本 skill は変更を勝手に適用しない**: フェーズ 3 の CHANGELOG 移行は markdown 出力のみ。ユーザ承認後に Edit で適用
- **rate limit**: 5 registry × 1 req = ~7 req、 GitHub API は無関係なので 5000/h 制限内
- **オフラインモード**: registry 取得失敗時はフェーズ 4 をスキップして report 生成
- **release-versions.toml は canonical truth**: 実 version との不一致は drift として明示
- **memory `feedback_pr_no_milestones.md` 準拠**: マイルストーン提案を含めない

## 使用例

```text
# 全 runtime の current / published / canonical を一覧
/release-prep

# Python だけに絞って詳細表示
/release-prep python

# 2.0.0 リリース予定での CHANGELOG 移行案を生成
/release-prep --target-version 2.0.0

# Rust だけ + target version
/release-prep rust --target-version 0.5.0
```

## 期待効果

- リリース時の **manifest 一括確認** を 1 コマンドに集約 (現状: 9 manifest を手動 Read)
- 「local では bump 済みだが publish されてない」のような状態を即発見
- CHANGELOG `[Unreleased]` の昇格作業の **規定化** (現状: 手動 markdown 編集)
- `release-versions.toml` `mode = "warn"` → `"fail"` 切替の判断材料を提供

`/sync-docs` Agent 7 (version drift 監査) と相補的: `/sync-docs` は drift 検出、`/release-prep` は drift 解消支援。
