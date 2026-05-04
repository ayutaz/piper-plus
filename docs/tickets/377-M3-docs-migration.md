# [M3] ドキュメント・移行ガイド整備

> **iOS Shared Library Distribution 仕様 ([#377](https://github.com/ayutaz/piper-plus/issues/377)) のマイルストーン M3 実装チケット**
> 関連仕様: [`docs/spec/ios-shared-lib.md §8 M3`](../spec/ios-shared-lib.md#m3-ドキュメント移行ガイド整備)

---

## 1. メタ情報

| 項目 | 値 |
|------|-----|
| マイルストーン | **M3** ([ドキュメント・移行ガイド整備](../spec/ios-shared-lib.md#m3-ドキュメント移行ガイド整備)) |
| 親 Issue | [#377](https://github.com/ayutaz/piper-plus/issues/377) |
| ブランチ | `fix/ios-shared-lib-build-377` |
| 状態 | [README 表 を SoT として参照](README.md) |
| 想定 PR | 1 PR (中、~440 行 diff、新規 ~330 行 + 編集 ~110 行、ドキュメント変更主体) |
| 想定所要 (Claude Code 実行ベース) | 実装 1-2 時間 (ドキュメント執筆) + ローカル markdownlint / lychee 検証 ~10 分 |
| 環境制約 | Apple Silicon Mac は本セッションで使用不可。Xcode UI スクリーンショットは文字列指示主とし、画像は **別 issue で利用者から PR 受付** で補追する方針 |
| 関連仕様 | [docs/spec/ios-shared-lib.md §2.1 zip 構造](../spec/ios-shared-lib.md#21-ort-取得経路), [§2.3 互換性維持](../spec/ios-shared-lib.md#23-互換性維持), [§8 M3](../spec/ios-shared-lib.md#m3-ドキュメント移行ガイド整備) |
| 対象ファイル | `examples/dart/README.md`, `examples/godot/README.md`, `docs/spec/ort-versions.md`, `CHANGELOG.md`, `docs/spec/ios-shared-lib.md`, `docs/tickets/README.md`, (新規) `docs/guides/ios-integration.md`, (新規) `examples/swift/README.md` |

> **依存関係:** **M2 完了** が前提。M2 で `libpiper_plus-ios-${VERSION}.xcframework.zip` 配布が GitHub Releases 上に成立して初めて、利用者向けドキュメントが現実の artifact を指し示せる。M2 着手前に M3 を仕上げると、未公開 artifact を前提とした絵に描いた餅になるため厳禁。

---

## 2. タスク目的とゴール

### 目的 (Why)

M2 完了で xcframework artifact がリリースパイプラインから出るようになっても、**利用者がそれを Xcode プロジェクトに組み込む方法を知らなければ実用化されない**。Issue #377 の本質は「iOS で動く配布物を出す」だが、配布物が Apple エコシステムの作法 (Embed & Sign / xcframework / SPM / CocoaPods) に正しく組み込めて初めて `done` と言える。

加えて M1/M2 で配布物が **2 種類** (tar.gz と xcframework.zip) 並列存在する過渡期に突入する。利用者は「どちらをどう使うか」を即座に判断できないと、混乱から GitHub Issue が大量発生する。配布物選択ガイドを早期に提示し、v1.14.0 で tar.gz 廃止予告を打つことで、過渡期を最短化する。

ドキュメント不在は M1 / M2 までの努力を死蔵させる。M3 は「機能リリース」ではなく **「機能をリリースとして成立させる」** 工程である。

### ゴール (DoD)

- [ ] `examples/dart/README.md` の iOS 統合手順が xcframework + ORT xcframework の二重 Embed & Sign 構成で完備されている
- [ ] `examples/godot/README.md` の Platforms 表に iOS 行が追加され、GDExtension 用の組込み手順が記載されている
- [ ] `docs/spec/ort-versions.md` の iOS 行が `xcframework (Microsoft CDN: download.onnxruntime.ai)` に更新されている
- [ ] `CHANGELOG.md` v1.13.0 エントリに以下が記載されている:
  - iOS shared-lib 配布開始 (xcframework.zip)
  - tar.gz 命名は v1.13.0 で継続、v1.14.0 で廃止予定の予告
  - Issue #377 への参照
- [ ] `docs/spec/ios-shared-lib.md` 冒頭 Status が `Implemented (v1.13.0)` に更新されている
- [ ] `docs/tickets/README.md` 表の M1/M2/M3 行が完了状態 (`done (PR #XXX, YYYY-MM-DD)`) に更新されている
- [ ] `docs/guides/ios-integration.md` (新規) が Dart/Godot/Swift 横断で利用可能な統合ガイドとして成立している
- [ ] `examples/swift/README.md` (新規) が SPM 公開前の暫定手順 (xcframework 手動 drag-and-drop) を提供している
- [ ] **module map / Privacy Manifest / .dSYM の取り扱い方針** が明文化されている (M3 では未対応扱い、後続マイルストーン誘導)
- [ ] `markdownlint` / `prettier --check` / `lychee` のローカル PASS が PR 説明で確認できる

---

## 3. 実装する内容の詳細

### 3.1 編集 / 新規作成ファイル一覧

| ファイル | 種別 | 主な変更内容 | 想定行数 |
|---------|------|-------------|--------|
| `examples/dart/README.md` | 編集 | iOS 章を xcframework ベースに刷新、配布物選択ガイド (tar.gz vs xcframework.zip) 追記、Embed & Sign Frameworks 手順、ORT xcframework 取得方法 3 案 (CocoaPods/SPM/CDN) | +60 / -20 |
| `examples/godot/README.md` | 編集 | (a) L199 の Feature Comparison 表 `Platforms` 行のセル文言更新 (`Linux, Windows, macOS, iOS (xcframework)`)、(b) L201 の `## Platform Notes` 配下に新規 `### iOS` セクション (xcframework 配置 + GDExtension `ios.dependencies` 記述例 + Embed & Sign 手順) を追加 | +40 / -2 |
| `docs/spec/ort-versions.md` | 編集 | iOS 行 (L19) を `xcframework (Microsoft CDN: download.onnxruntime.ai)` に更新、ORT バージョン 1.17.0 の検証日と zip 構造を追記 | +5 / -1 |
| `CHANGELOG.md` | 編集 | v1.13.0 セクションに iOS shared-lib 配布開始 + tar.gz 廃止予告エントリ追加、Breaking change セクションは付けない (v1.14.0 で付ける予定) | +15 |
| `docs/spec/ios-shared-lib.md` | 編集 | 冒頭 Status を `Proposed` → `Implemented (v1.13.0)` 、§8 M1/M2/M3 行のチェックボックス完了化、関連 PR 番号追記 | +5 / -3 |
| `docs/tickets/README.md` | 編集 | 表の M1/M2/M3 状態列を `done` に、PR 列に PR 番号を追記 | +3 / -3 |
| `docs/guides/ios-integration.md` | 新規 | Dart/Godot/Swift 横断 iOS 統合ガイド (前提・配布物選択・Embed 手順・ORT 取得 3 案・トラブルシュート) | +250 |
| `examples/swift/README.md` | 新規 | Swift プロジェクト向け、SPM 公開前の暫定手順 (xcframework drag-and-drop)、M4 完了後 SPM 経由に書き換える旨の予告 | +80 |

> 合計 diff 想定: 新規 ~330 行 + 編集 ~110 行 = ~440 行。ドキュメント主体のため複雑度は低い。

### 3.2 配布物選択ガイド (tar.gz vs xcframework.zip)

`examples/dart/README.md` および `docs/guides/ios-integration.md` 冒頭に以下のディシジョンテーブルを掲載する:

| あなたの状況 | 推奨配布物 | 理由 |
|------------|----------|------|
| Flutter / Dart FFI で iOS アプリをビルドしたい | **xcframework.zip** | Xcode が xcframework を一級扱い、device + simulator 両対応 |
| Godot / GDExtension で iOS export したい | **xcframework.zip** | `.gdextension` の `ios.dependencies` が xcframework を期待 |
| Swift プロジェクトで `import` したい (SPM 待ち) | **xcframework.zip** | M4 で SPM 公開予定、それまで手動 drag-and-drop |
| 古い CMake プロジェクトを引き継いでいる (v1.12.0 以前) | tar.gz (v1.13.0 のみ) | v1.14.0 で廃止予定、移行を強く推奨 |
| CI でカスタムビルドフローを構築している | tar.gz | xcframework は CMake 直接消費に向かない、ただし v1.14.0 で要再検討 |
| シミュレータでテストしたい | **xcframework.zip 一択** | tar.gz は device only |

**v1.13.0 過渡期の方針 (CHANGELOG / ガイドに明記):**

- **新規利用者は xcframework.zip を選ぶ**
- **既存利用者 (tar.gz 利用) は v1.13.0 期間内に xcframework.zip へ移行**
- **v1.14.0 で tar.gz 廃止**

### 3.3 `examples/dart/README.md` iOS 章の構成

現状の "iOS は `.framework` か `.dylib` が必要" 風記述を全面刷新し、以下のセクション構造に再構築:

```markdown
## iOS Integration

### Prerequisites
- Xcode 15+ (Xcode 16 推奨)
- iOS Deployment Target 15.0+
- Apple Silicon Mac (Intel Mac は simulator slice の x86_64 で動作)

### 配布物の選択
[3.2 のディシジョンテーブルを引用]

### Step 1: piper-plus xcframework の取得
$ gh release download v1.13.0 -p 'libpiper_plus-ios-*.xcframework.zip'
$ unzip libpiper_plus-ios-*.xcframework.zip
# 展開結果: piper_plus.xcframework/

### Step 2: ONNX Runtime xcframework の取得 (3 案)

#### 案 A: CocoaPods (推奨、既存 Podfile があるプロジェクト向け)
[Podfile への onnxruntime-c 追加例]

#### 案 B: Swift Package Manager (推奨、純 SPM プロジェクト向け)
[Package.swift への microsoft/onnxruntime-swift-package-manager 追加例]

#### 案 C: Microsoft CDN から手動取得
$ curl -LO https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.17.0.zip
$ unzip pod-archive-onnxruntime-c-1.17.0.zip
# 展開結果: onnxruntime.xcframework/

### Step 3: Xcode への組込み (Embed & Sign Frameworks)
[Xcode UI スクリーンショット 3 枚:
 (1) Project navigator → Add Files
 (2) Targets → General → Frameworks, Libraries, and Embedded Content
 (3) "Embed & Sign" 選択]

### Step 4: Dart FFI からの呼び出し
[既存の DynamicLibrary.process() コード例を維持、importLib path のみ調整]

### Troubleshooting
- "Image Not Found" → Embed が "Do Not Embed" になっていないか確認
- Simulator でクラッシュ → simulator slice が含まれた xcframework か確認
- App Store rejection → bitcode は不要、Privacy Manifest は別途必要 (§Note 参照)

### Note: Privacy Manifest (iOS 17+)
piper-plus 0.x 系および ORT は Required Reason API を直接使用しない見込みのため、
Privacy Manifest なしでも App Store 審査を通過し得る。ただし利用者アプリ側
(file system / network 等) で Required Reason API を使う場合は `PrivacyInfo.xcprivacy`
追加が必要。空 Manifest 同梱の自動化は別 issue で追跡。
```

### 3.4 `examples/godot/README.md` Platforms 関連修正 (2 箇所)

実物の examples/godot/README.md は **Platforms 表を持たない**。L199 は godot-piper-plus との **Feature Comparison 表**で、`Platforms` セルに 1 行で OS 名が並ぶだけ。プラットフォーム別の手順は L201 以降の `## Platform Notes` 配下で `### Linux` / `### macOS` / `### Windows` のセクション (テーブルではない) として記述されている。M3 はこれを 2 箇所に分けて編集する:

**(a) L199 Feature Comparison 表の `Platforms` 行のセル更新:**

```markdown
| Platforms | Linux, Windows, macOS | Linux, Windows, macOS, **iOS (xcframework)**, Android |
```

**(b) `## Platform Notes` 配下に新規 `### iOS` セクションを追加:**

```markdown
### iOS

- **Architecture:** arm64 (device) + arm64/x64 (simulator)
- **Status:** Stable (v1.13.0+)
- **Distribution:** `libpiper_plus-ios-${VERSION}.xcframework.zip`

GDExtension 設定例 (`piper_plus.gdextension`):
```ini
[libraries]
ios.debug = "res://addons/piper-plus/ios/piper_plus.xcframework"
ios.release = "res://addons/piper-plus/ios/piper_plus.xcframework"

[dependencies]
ios.debug = {"res://addons/piper-plus/ios/onnxruntime.xcframework" : ""}
ios.release = {"res://addons/piper-plus/ios/onnxruntime.xcframework" : ""}
```

詳細は [`docs/guides/ios-integration.md`](../../docs/guides/ios-integration.md) を参照。
```

加えて、GDExtension の `ios.dependencies` で ORT xcframework を必須化することにより、Godot エディタの iOS export 時に自動 Embed されることを期待する (要実機検証、§8.4 で確認)。

```ini
[libraries]
ios.debug = "res://addons/piper-plus/ios/piper_plus.xcframework"
ios.release = "res://addons/piper-plus/ios/piper_plus.xcframework"

[dependencies]
ios.debug = {"res://addons/piper-plus/ios/onnxruntime.xcframework" : ""}
ios.release = {"res://addons/piper-plus/ios/onnxruntime.xcframework" : ""}
```

### 3.5 `docs/spec/ort-versions.md` 更新

L19 付近の iOS 行を以下に変更:

```markdown
| iOS | 1.17.0 | xcframework (Microsoft CDN: download.onnxruntime.ai) | 検証日 2026-05-04, sha256 `1623e115...db871` |
```

### 3.6 `CHANGELOG.md` v1.13.0 エントリ

```markdown
## [1.13.0] - 2026-XX-XX

### Added
- iOS shared library distribution as xcframework (Issue #377)
  - Distributed as `libpiper_plus-ios-${VERSION}.xcframework.zip` on GitHub Releases
  - Includes both device (arm64) and simulator (arm64 + x86_64) slices
  - ONNX Runtime is distributed separately (CocoaPods / SPM / CDN)
  - See `docs/guides/ios-integration.md` for Xcode integration steps
- New documentation: `docs/guides/ios-integration.md` covering Dart / Godot / Swift integration
- New example: `examples/swift/` (interim manual drag-and-drop, SPM package planned for v1.14.0)

### Deprecated
- `libpiper_plus-ios-arm64-${VERSION}.tar.gz` (device-only, .framework-bundled tar.gz format)
  - Continued in v1.13.0 for migration period
  - **Will be removed in v1.14.0** — please migrate to xcframework.zip distribution

### Fixed
- Restored Linux/Windows/macOS/Android/iOS shared-lib release pipeline (Issue #377)
  that had been blocked since v1.11.0
  - The `release` job's dependency on the failing iOS build had prevented all OS
    artifacts from being uploaded to GitHub Releases
  - Fixed in M1 (取得経路修復) and consolidated into v1.13.0
```

### 3.7 `docs/spec/ios-shared-lib.md` 冒頭更新

```markdown
> **Version:** 1.0
> **Status:** Implemented (v1.13.0)
> **対象 Issue:** [#377](https://github.com/ayutaz/piper-plus/issues/377)
> **実装 PR:** M1: #XXX / M2: #YYY / M3: #ZZZ
```

§8 M1/M2/M3 のチェックボックス `[ ] 未着手` をすべて `[x] 完了 (PR #XXX, YYYY-MM-DD)` に書き換え。

### 3.8 `docs/tickets/README.md` 表更新

L9-11 の 3 行を:

```markdown
| [377-M1-ort-fetch-fix](377-M1-ort-fetch-fix.md) | [M1: 取得経路の修復](../spec/ios-shared-lib.md#m1-取得経路の修復-release-ジョブの解凍) | [#377](https://github.com/ayutaz/piper-plus/issues/377) | done | #XXX |
| [377-M2-xcframework](377-M2-xcframework.md) | [M2: xcframework 化](../spec/ios-shared-lib.md#m2-xcframework-化-配布形式の実用化) | [#377](https://github.com/ayutaz/piper-plus/issues/377) | done | #YYY |
| [377-M3-docs-migration](377-M3-docs-migration.md) | [M3: ドキュメント・移行ガイド整備](../spec/ios-shared-lib.md#m3-ドキュメント移行ガイド整備) | [#377](https://github.com/ayutaz/piper-plus/issues/377) | done | #ZZZ |
```

### 3.9 `docs/guides/ios-integration.md` (新規) 構成

```markdown
# iOS Integration Guide

## Audience
Dart / Flutter / Godot / Swift プロジェクトに piper-plus を組み込みたい開発者向け。

## Prerequisites / 配布物の選択 / Step 1〜4 / Troubleshooting

## Note: 未対応事項 (v1.13.0 時点)
- Module map: 未提供。Swift から `import PiperPlus` するには手動で modulemap を追加するか、M4 (SPM) を待つ
- Privacy Manifest (`PrivacyInfo.xcprivacy`): 未同梱。利用者側で追加必要
- .dSYM: xcframework 内バイナリは stripped、別 artifact 化されていない (別 issue で追跡)

## 後方互換: tar.gz 配布の取り扱い
v1.13.0 期間中は `libpiper_plus-ios-arm64-${VERSION}.tar.gz` を継続配布。v1.14.0 で廃止。
```

### 3.10 `examples/swift/README.md` (新規) 構成

```markdown
# Swift Integration Example

## Status (v1.13.0)
SPM パッケージは未公開 (M4 で予定)。本書は **暫定的な手動 drag-and-drop 手順** を提供する。
M4 完了 (v1.14.0 想定) 後、本書は SPM 経由手順に書き換える。

## 暫定 module map (Swift import 用)
[手動 modulemap 例: framework header の C 関数を Swift から呼ぶ場合]

## SPM 公開後の予定
import PiperPlus
let voice = try PiperVoice.load(modelPath: "...")
```

### 3.11 module map / Privacy Manifest / .dSYM の取扱方針 (明文化)

`docs/guides/ios-integration.md` および `docs/spec/ios-shared-lib.md` の「Note: 対応状況」節で以下を明記する:

- **module map (`module.modulemap`)**: **M2 で同梱済** (道 A 確定により M2 §11.7 の繰り上げ提案を採用)。各 slice の `Headers/module.modulemap` に `framework module PiperPlus` 宣言が含まれ、M4 SPM 経由の `import PiperPlus` が成立する
- **Privacy Manifest (`PrivacyInfo.xcprivacy`)**: **M2 で空 Manifest 同梱済** (道 A 確定)。`NSPrivacyTracking=false` + 配列 3 つが空。Apple の要件は (a) Required Reason API 使用時、または (b) "commonly used SDK list" 該当時に該当ありの宣言が必要だが、piper-plus は該当しない。**ORT 側 Privacy Manifest は Microsoft 公式が未提供のため、利用者アプリ側で別途追加が必要**な点を強調
- **.dSYM (Debug Symbols)**: xcframework 内バイナリは stripped、.dSYM は別 artifact 化されていない。クラッシュレポートの symbolication が必要な利用者は将来別 issue で追跡 (M3 では追加せず)

### 3.12 触らないファイル (M3 スコープ外)

- `.github/workflows/release-shared-lib.yml` (M2 で確定済、M3 で再編集不要)
- `cmake/ios.toolchain.cmake` / `cmake/PiperPlusShared.cmake` (M2 で確定済)
- `examples/swift/Sources/`, `examples/swift/Package.swift` 等の実コード (M4 で SPM 化時に追加)
- 多言語 README (FR/ES/DE/PT/ZH) — M3 では同期しない、別 issue 化 (§9 C4)

---

## 4. 担当者と Agent 並列レビュー観点

> **実行体制:** 本タスクは Claude Code が単独で実装・検証・コミットを行う。レビューは Agent ツール (subagent) で複数観点を並列起動して補強する。「人数」表記は廃止。

| 観点 (subagent role) | 数 | 主担当 | 責務 |
|---------------------|----|------|------|
| **実装** | - | Claude Code (主) | dart/godot README 改訂、`docs/guides/ios-integration.md` / `examples/swift/README.md` 新規、CHANGELOG / spec status 更新、markdownlint/lychee 実行、PR 起票、commit |
| **整合性レビュー** | 1 観点 | Agent (general-purpose) | 配布物選択ガイド / Embed & Sign 表記 / tar.gz 廃止予告 / spec 冒頭 Status / README 表の同期、リンク切れ |
| **UX / 利用者導線レビュー** | 1 観点 | Agent (general-purpose) | TTHW (Time-To-Hello-World) 30 分目標達成可否、配布物選択 (Hick's Law) 混乱回避、つまづきポイント TOP 5 への対処 |

実装後 `Agent` ツールで 1-2 観点を並列起動。Apple Silicon Mac での実機再現検証は環境制約上不可、利用者観測 (M3 §12.2 別 issue) で代替。重大な指摘がなければ `gh pr merge --auto` で CI 完了マージ。

---

## 5. 提供範囲

### Included (M3 で扱う)

- `examples/dart/README.md` の iOS 統合手順刷新 (xcframework + ORT 二重 Embed 構成)
- `examples/godot/README.md` Platforms 表の iOS 行追加と GDExtension 設定例
- `docs/spec/ort-versions.md` iOS 行更新
- `CHANGELOG.md` v1.13.0 エントリ追加 (iOS 配布開始 + tar.gz 廃止予告)
- `docs/spec/ios-shared-lib.md` 冒頭 Status 更新と §8 M1/M2/M3 チェックボックス完了化
- `docs/tickets/README.md` 表の M1/M2/M3 行更新
- `docs/guides/ios-integration.md` 新規作成 (Dart/Godot/Swift 横断統合ガイド)
- `examples/swift/README.md` 新規作成 (SPM 公開前暫定手順)
- module map / Privacy Manifest / .dSYM の **取扱方針 (未対応宣言と将来計画)** の明文化
- markdownlint / prettier / lychee / cspell によるドキュメント構文・リンク・スペル検証

### Excluded (本 M3 では扱わない)

| 範囲 | 担当マイルストーン / 別 issue |
|------|------------------------|
| SPM repo (`ayousanz/piper-plus-swift-package-manager`) の新設・公開 | **M4** |
| `Package.swift` の `binaryTarget(url:, checksum:)` 設定とリリース連携ワークフロー | **M4** |
| `examples/swift/` への SPM 経由インストール手順本格版 (M4 完了後に書き換え) | **M4** |
| Xcode 側で Swift `import PiperPlus` を成立させるための module map 自動生成 | **M4** (xcframework 生成時 = M2 で組み込めるか M4 で再判断) |
| Privacy Manifest (`PrivacyInfo.xcprivacy`) の自動同梱実装 | **別 issue** |
| .dSYM の別 artifact 化 (`libpiper_plus-ios-${VERSION}.dSYM.zip`) | **別 issue** |
| 多言語 README (FR/ES/DE/PT/ZH) の同期 | **別 issue** |
| download metrics / Issue 受信頻度監視ダッシュボード | **別 issue** (M1 §11.5 永遠負債解消の運用課題) |
| visionOS / Mac Catalyst 拡張 | **将来 (M5+)** |

---

## 6. テスト項目

| # | 観点 | 期待結果 |
|---|------|---------|
| T1 | `examples/dart/README.md` の Markdown レンダリング | GitHub.com の preview で見出し階層・コードブロック・テーブル・画像が崩れず表示される |
| T2 | `examples/godot/README.md` Platforms 表の整形 | iOS 行が他 OS 行と同じカラム数・整列で表示される |
| T3 | `docs/guides/ios-integration.md` の章立て | TOC が自動生成可能な階層 (h2/h3) で、`## Step 1` 〜 `## Step 4` が読み手の動線に沿う |
| T4 | 内部リンク切れチェック (`lychee --offline` 相当) | `docs/spec/ios-shared-lib.md` / `docs/spec/ort-versions.md` / `examples/dart/README.md` への相互リンクが全て解決 |
| T5 | 外部リンク切れチェック (`lychee` オンライン) | Microsoft CDN URL / CocoaPods / SPM repo / Apple Privacy Manifest ドキュメント等が HTTP 200 |
| T6 | コードブロックのコピペ実行可能性 | `gh release download` / `unzip` / `curl` コマンドが macOS で素直に動く (シェルクオート、変数展開ミスなし) |
| T7 | Xcode UI スクリーンショット | 3 枚 (Add Files / Frameworks list / Embed & Sign 選択) が PNG で同梱され、`![Alt](path)` で参照、最新 Xcode 16 UI |
| T8 | 配布物選択ガイドの mental walk-through | 「Flutter で iOS アプリ」「Godot 既存 v1.12.0 利用者」「Swift で `import` したい」の 3 ペルソナで読み、迷わず xcframework.zip にたどり着く |
| T9 | Privacy Manifest 言及の正確性 | iOS 17+ で必須である事実、ストア外 (TestFlight 含む) と App Store 提出時の差分を曖昧にしない |
| T10 | tar.gz 廃止予告の文言 | v1.13.0 では維持、v1.14.0 で廃止という時系列が CHANGELOG / ガイド / spec で一貫 |
| T11 | `CHANGELOG.md` のセマンティック整合 | `### Added` / `### Deprecated` / `### Fixed` のフォーマットが既存 v1.12.0 エントリと一致 |
| T12 | module map / Privacy Manifest / .dSYM の未対応宣言 | 「実装していない」と「将来対応予定」が両立し、利用者が「対応してほしい」issue を作成しやすい誘導が含まれる |

---

## 7. Unit テストの内容

ドキュメント変更主体のため従来型 unit test は不要だが、以下の **静的検査ゲート** をローカル + CI で実行する:

| ツール | 対象 | 目的 |
|-------|------|------|
| `markdownlint-cli2` | 全 Markdown ファイル | 見出し階層・空行・行頭スペース等の構文 |
| `prettier --check` | Markdown / YAML | 整形ルール (テーブル・コードフェンス) |
| `lychee` | 全 Markdown 内のリンク | 内部 / 外部リンク切れ検出 |
| `cspell` | 全 Markdown | スペルチェック (英文ドキュメント部分) |

**CI 統合方針:**

- `markdownlint` と `prettier --check` は既存の `docs.yml` ワークフローがあれば追加、無ければ本 PR で `.github/workflows/docs.yml` を新設
- `lychee` は外部 URL 変動でフラッキー化しやすいため、`continue-on-error: true` で警告扱い
- `cspell` は専門用語 (xcframework / dSYM / piper-plus 固有名詞) を `.cspell.json` の `words[]` に追加して誤検知抑制

---

## 8. E2E テストの内容

### 8.1 Markdown レンダリング確認 (PR 起票前、必須)

```bash
gh repo view ayutaz/piper-plus --web  # PR の Files changed タブで preview 確認
# または grip
pip install grip
grip docs/guides/ios-integration.md
grip examples/dart/README.md
grip examples/swift/README.md
```

確認:
- 見出し階層 (h1/h2/h3) が一貫
- コードブロック言語指定 (`bash`, `swift`, `ini`, `markdown`) が syntax highlight される
- テーブル整列崩れなし
- スクリーンショット画像が表示される (`docs/guides/screenshots/ios-xxx.png`)

### 8.2 実機 (Apple Silicon Mac) で README 手順再現 (必須)

```bash
gh release download v1.13.0-rc1 -p 'libpiper_plus-ios-*.xcframework.zip' \
  -p 'libpiper_plus-ios-arm64-*.tar.gz'  # 両方取得して切り替え検証

unzip libpiper_plus-ios-*.xcframework.zip
ls piper_plus.xcframework  # ios-arm64/ ios-arm64_x86_64-simulator/ Info.plist

curl -LO https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.17.0.zip
unzip pod-archive-onnxruntime-c-1.17.0.zip

mkdir test-piper-ios && cd test-piper-ios
# Xcode 16 で新規 iOS App プロジェクト作成
# General → Frameworks に piper_plus.xcframework と onnxruntime.xcframework を Embed & Sign
xcodebuild -project test-piper-ios.xcodeproj -scheme test-piper-ios \
  -destination 'platform=iOS Simulator,name=iPhone 15 Pro' build
```

### 8.3 Dart / Flutter プロジェクトでの組込み確認

```bash
flutter create --platforms=ios test_piper_flutter
cd test_piper_flutter
# ios/ ディレクトリ配下に xcframework を配置
# ios/Podfile に pod 'onnxruntime-c', '1.17.0' を追加
cd ios && pod install && cd ..
flutter build ios --simulator
```

### 8.4 Godot プロジェクトでの組込み確認

```bash
# Godot 4.x プロジェクトに addons/piper-plus/ios/ を作成
# piper_plus.xcframework と onnxruntime.xcframework を配置
# .gdextension に ios.dependencies を記述
godot --headless --export-release "iOS" build/test.ipa
```

### 8.5 配布物切り替え動作確認 (tar.gz と xcframework.zip 両方)

```bash
# tar.gz 系 (v1.13.0 でも継続配布)
gh release download v1.13.0-rc1 -p 'libpiper_plus-ios-arm64-*.tar.gz'
tar -xzf libpiper_plus-ios-arm64-*.tar.gz
# 旧来の CMake プロジェクトに statically link (libpiper_plus.a + onnxruntime.framework)
```

### 8.6 リンク切れ E2E (lychee オンライン)

```bash
lychee --max-concurrency 5 docs/ examples/ \
  --exclude 'github.com/ayutaz/piper-plus/issues/'
```

### 8.7 失敗時の roll back 手順

- Markdown 構文エラー: PR 内で commit revert
- スクリーンショット陳腐化: PR 内で再撮影 commit、または LFS 切替判断
- リンク切れ (外部): URL 修正 commit、Microsoft が URL を変えた場合は M2 chain と相談

---

## 9. 懸念事項

| # | 懸念 | 確度 | 対応方針 |
|---|------|------|---------|
| C1 | Xcode UI スクリーンショットの陳腐化 (Xcode 17 / 18 で UI 変更時) | 高 | 撮影日 (2026-05) と Xcode バージョンを画像 caption に明記。年次レビューで再撮影。可能なら UI 操作の文章記述を主、スクリーンショットは補助に位置づけ |
| C2 | Privacy Manifest 要件が利用者にとって複雑すぎる、誤った情報を与えるリスク | 中 | iOS Integration Specialist が Apple 公式ドキュメントを引用しつつ "piper-plus は同梱していない、利用者責任で追加" のラインを死守。具体的な `xcprivacy` テンプレート記載は避け、別 issue 誘導 |
| C3 | tar.gz 廃止予告 (v1.14.0) のタイミング — 早すぎる/遅すぎるの議論 | 中 | v1.13.0 で 1 リリース分の周知期間を設ける、v1.14.0 (~3〜6 ヶ月後) で除去。これより短いと利用者ピボット不可、長いとパイプライン分岐維持コストが嵩む |
| C4 | 多言語 README (FR/ES/DE/PT/ZH) の同期コスト | 中 | M3 では英語版のみ更新、他言語は別 issue 化。多言語自動翻訳パイプラインは将来検討。古い iOS 記述を持つ多言語版は冒頭に "EN version is canonical" 注記追加で時間稼ぎ |
| C5 | ~~module map 不在で Swift 利用者が `import` で躓く~~ → **M2 で同梱済 (道 A 確定)、解消** | 解消 | M2 §3.1 で modulemap 自動生成を `cmake/PiperPlusShared.cmake` に追加済、M4 SPM 公開時に追加対応不要 |
| C6 | 配布物 2 種類の使い分けが利用者を混乱させる | 中 | ディシジョンテーブル (§3.2) を CHANGELOG / dart README / ios-integration ガイドの 3 箇所に重複掲載。「迷ったら xcframework.zip」を強い推奨として太字化 |
| C7 | 利用者が ORT xcframework を取得し忘れて "library not found" にハマる | 高 | iOS Integration Guide で **piper-plus 単独では動かない、ORT xcframework が別途必要** を Step 1 の冒頭で太字化。Troubleshooting にも同じエラー → ORT 未取得を疑え、を入れる |

---

## 10. レビュー項目

レビュアー (Documentation Lead + iOS Integration Specialist + QA Engineer) は以下のチェックリストを順に確認する。

### 10.1 `examples/dart/README.md` iOS 章

- [ ] iOS 章が Prerequisites / 配布物選択 / Step 1〜4 / Troubleshooting / Note の構成
- [ ] 配布物選択ガイドが明確 (新規利用者は迷わず xcframework.zip を選べる)
- [ ] Embed & Sign Frameworks の手順が具体的 (Xcode UI 操作のスクリーンショット 3 枚以上)
- [ ] ORT 取得方法 3 案 (CocoaPods / SPM / CDN) すべてが網羅され、推奨順位が明記
- [ ] `gh release download` / `unzip` / `curl` コマンドがコピペで動く

### 10.2 `examples/godot/README.md` Platforms 表

- [ ] iOS 行が他 OS 行と整合 (Architecture / Status / Distribution カラム)
- [ ] GDExtension の `ios.dependencies` 記述例が完全 (debug / release 両方、ORT xcframework path)

### 10.3 配布物選択ガイドの明確さ

- [ ] tar.gz / xcframework.zip の使い分けがディシジョンテーブルで一目瞭然
- [ ] v1.13.0 / v1.14.0 のライフサイクル (`xcframework.zip` 推奨、tar.gz 廃止予定) が時系列で記載
- [ ] 「迷ったら xcframework.zip」がデフォルト推奨として太字 / callout 化されている

### 10.4 Embed & Sign Frameworks 手順の正確性

- [ ] Xcode の "Frameworks, Libraries, and Embedded Content" セクションを正しく指している
- [ ] "Embed & Sign" を選ぶこと、"Do Not Embed" / "Embed Without Signing" は誤りである旨が記載
- [ ] iOS Deployment Target (15.0 推奨) が明記
- [ ] bitcode は不要 (Xcode 14+ で deprecated) が明記

### 10.5 ORT 取得方法 3 案の網羅性

- [ ] CocoaPods (案 A): `pod 'onnxruntime-c', '1.17.0'` の Podfile 例が完全
- [ ] SPM (案 B): `microsoft/onnxruntime-swift-package-manager` の URL とバージョン pin 方法が記載
- [ ] CDN (案 C): `download.onnxruntime.ai` URL と sha256 (1.17.0: `1623e115...db871`) が記載

### 10.6 `docs/spec/ort-versions.md` 整合

- [ ] iOS 行が `xcframework (Microsoft CDN: download.onnxruntime.ai)` に更新
- [ ] バージョン (1.17.0) と検証日 (2026-05-04) が他 OS 行と同じ粒度で記載
- [ ] M1 で確定した sha256 が脚注または Notes 列に保持

### 10.7 `CHANGELOG.md` v1.13.0 エントリの形式

- [ ] `### Added` / `### Deprecated` / `### Fixed` のフォーマットが既存 v1.12.0 / v1.11.0 と一致
- [ ] Issue #377 への参照リンクが含まれる
- [ ] Breaking change セクションは v1.13.0 では付けない (v1.14.0 で tar.gz 廃止時に追加)

### 10.8 tar.gz 廃止予告の文言

- [ ] v1.13.0 期間中は継続配布、v1.14.0 で廃止 — の時系列が CHANGELOG / dart README / ios-integration / spec で完全一致
- [ ] 「廃止予告」「removal」「deprecation」の用語が混在せず統一されている

### 10.9 リンク切れなし

- [ ] `lychee --offline` (内部リンク) が PASS
- [ ] `lychee` (外部リンク) が PASS、または許容できる false-positive のみ
- [ ] Anchor リンク (`#m1-取得経路の修復...`) が日本語アンカー仕様に整合

### 10.10 `docs/spec/ios-shared-lib.md` 冒頭 Status / `docs/tickets/README.md` 表 同期

- [ ] 冒頭 Status が `Implemented (v1.13.0)` に更新
- [ ] `**実装 PR:**` 行に M1/M2/M3 の PR 番号が追記
- [ ] §8 M1/M2/M3 のチェックボックスが `[x] 完了 (PR #XXX, YYYY-MM-DD)` 化
- [ ] `docs/tickets/README.md` 表の状態列・PR 列が 3 行分すべて更新

### 10.11 module map / Privacy Manifest / .dSYM 取扱方針

- [ ] 「未対応である」事実が `docs/guides/ios-integration.md` の Note 節で明示
- [ ] それぞれ将来対応の道筋 (M4 / 別 issue) が示されている
- [ ] 利用者が「対応してほしい」issue を作成しやすい誘導が含まれる

### 10.12 PR 説明欄のチェック

- [ ] markdownlint / prettier / lychee / cspell のローカル実行ログが PR 説明に貼られている
- [ ] 実機 (Apple Silicon Mac) での §8.2 再現確認スクリーンショットが添付
- [ ] M1 / M2 PR への back-reference が含まれる
- [ ] 関連 Issue #377 のクロスリンク

---

## 11. 一から作り直すとしたら

このセクションは M1 §11 / M2 §11 の系譜を継ぐ批判的レビューである。M3 (ドキュメント・移行ガイド整備) を実装する前に、そもそもこの設計でよいのかを問い直す。前提として、iOS 利用者数の観測手段は存在せず、PyPI / npm / crates.io の DL 数からも切り分けできない。つまり「誰のためにどれだけ書くか」の意思決定はエビデンスベースではなく投資配分の博打である、という認識から始める。

> **⚠️ 指示子スコープ注記:** 本節の「案 X / 案 Y / 案 Z」は **M3 文脈に閉じた指示子** で、他チケットとは指す内容が異なる。M3 §11.2 では: 案 X = 実装と同 PR でドキュメント化 (M3 廃止)、案 Y = Documentation as Code、案 Z = 動画 + Discussion 中心 を指す。

### 11.1 そもそも何を作るべきか

#### ドキュメントの「目的」再定義

M3 の実態は「README 増補 + 新規ガイド 1 本 + spec/CHANGELOG 同期」だが、これはアウトプット定義であってアウトカム定義ではない。ゴールは **「Flutter / Godot / Swift 開発者が piper-plus の iOS xcframework を 30 分以内に自プロジェクトで動かせる」** であり、これに対する KPI は時間 (TTHW: Time-To-Hello-World) でしか定義できない。文書量・ファイル数・ガイドの本数は擬似指標である。

#### 中心媒体の三択

| 軸 | README 中心 | Doc サイト中心 (Docusaurus 等) | Inline コード例中心 |
|---|---|---|---|
| 初動コスト | 低 (既存の README に追記) | 高 (CI/CD + サイト構築) | 中 (`examples/ios-swift/` 新設) |
| 検索性 | GitHub 検索のみ | Algolia / 全文検索 | grep ベース |
| バージョン分岐 | tag/branch 切替で実質可能 | versioned docs (Docusaurus 標準) | tag のみ |
| 多言語 | 手動 | i18n プラグイン | 不可 |
| 現状フィット | 全ランタイムで採用済 | 既存資産と分離 | 既存 `examples/` と整合 |

現 M3 は README 中心で、`docs/guides/ios-integration.md` を補助に置く折衷案。これは事実上「次に Doc サイト化したい時の踏み石」だが、踏み石としての位置付けが明示されていない。Doc サイトに移行する具体プランがない以上、この補助ガイドは README の劣化コピーになりやすい。

#### M1/M2 の「ドキュメントを M3 で一括処理」設計の是非

M2 で xcframework を生成する PR にドキュメントが含まれない設計は、典型的な **ドキュメント負債のトランチ化** である。Google Documentation Best Practices や Stripe の "Docs as Product" の主張通り、コードとドキュメントは同一 PR で同一レビュアーが見ない限り乖離する。M3 を独立マイルストーン化した時点で、M2 マージから M3 マージまでの期間 (推定 1〜3 週間) は「動くが触れない」状態になる。これは sherpa-onnx が `docs/source/onnx/` 配下に Lang ごとの統合手順をコードと同一 PR で commit しているのと対照的である。

### 11.2 代替アーキテクチャ案

#### 案 X: 実装と同 PR でドキュメント化 (M3 廃止)

M1 PR / M2 PR それぞれに対応 README diff を含め、M3 マイルストーンを解体する案。

| 観点 | 評価 |
|---|---|
| メリット | コード/ドキュメント乖離期間ゼロ。レビュアー 1 人で両方確認可。`v1.13.0-rc1` の「触れる初日」が早い |
| デメリット | M1/M2 PR が肥大化 (M2 に既に xcframework + CI + 検証が乗っており、+ 200 行のドキュメントは過大) |
| 採用条件 | M1/M2 PR を small-PR 戦略 (ドキュメント分離せず、機能で分割) で再構成可能なら成立 |
| 定量基準 | M2 PR の diff 行数が 1000 行未満なら案 X、超えるなら現案 |

#### 案 Y: Documentation as Code (自動生成)

`examples/ios-swift/Podfile`、`examples/dart/pubspec.yaml` など実コードから snippet 抽出し、`docs/guides/ios-integration.md` には参照だけ書く案。

| 観点 | 評価 |
|---|---|
| メリット | コード例の陳腐化が原理的に発生しない。CI で snippet 実行可 (`cargo test --doc` 相当) |
| デメリット | 抽出ツールチェーン構築コスト。README で読みづらい (snippet マーカーが残る) |
| 採用条件 | Doc サイト (Docusaurus 等) を併用する前提なら ROI が立つ。README 中心では過剰 |
| 競合実例 | `https://onnxruntime.ai/docs/` は手動だが、`https://www.tensorflow.org/lite/guide/ios` は CI で snippet 検証 |

#### 案 Z: 動画 + GitHub Discussion 中心

Loom / YouTube で 5 分の Quick Start 動画、Markdown は最小、Q&A は Discussions に集約。

| 観点 | 評価 |
|---|---|
| メリット | Xcode UI 操作の説明が圧倒的に速い (Embed & Sign のスクショ列挙不要) |
| デメリット | 動画は検索不能、字幕なしで非英語話者排除、Xcode 16 → 17 で全撮り直し |
| 採用条件 | 月間 iOS 利用者 > 100 人かつメンテナが動画編集できる場合のみ |
| 現実性 | 利用者数が観測不能な現状では投資正当化不可 |

### 11.3 形式・媒体の根本選択

| 軸 | 選択肢 | 推奨 | 根拠 |
|---|---|---|---|
| ホスト | README / Wiki / 静的サイト | README + `docs/guides/` | Wiki は CI 連携不可、サイトは過剰 |
| 多言語 | EN のみ / EN+JA / 5 言語 | EN + JA (現状維持) | 翻訳 1 PR あたり 30 分 × 言語数のリニアコスト、ROI 不明 |
| 視覚要素 | スクショ / ASCII / テキスト | スクショ最小 + テキスト主 | Xcode UI は 6-12 ヶ月で陳腐化 |
| 動画 | あり / なし | なし | 撮り直しコストが定常的 |
| 検索 | Algolia / GitHub 検索 | GitHub 検索 | サイト未構築の段階で Algolia は過剰 |
| リンク切れ | 手動 / `lychee` CI | `lychee` CI | 既に他 OSS で実績、導入 30 分 |

スクリーンショット陳腐化については、whisper.cpp の README が一切スクショを使わずテキストとコードブロックのみで構成しているのが参考になる。Xcode の "Frameworks, Libraries, and Embedded Content" の Embed 列を文字で書くのは冗長だが、年 2 回の更新コストよりは安い。

### 11.4 利用者ジャーニーの設計

#### TTHW (Time-To-Hello-World) タイムライン目標

| フェーズ | 目標時間 | 利用者の行動 | ドキュメント側の責務 |
|---|---|---|---|
| 0:00-0:05 | 5 分 | リポジトリ到達 → README 読了 → 配布物選択 | 配布物比較表 (xcframework.zip vs tar.gz) を Top に |
| 0:05-0:15 | 10 分 | xcframework DL → Xcode/Flutter プロジェクトへ Drop | プラットフォーム別 Drop 手順 (Dart/Godot/Swift) |
| 0:15-0:25 | 10 分 | Embed & Sign 設定 → ORT も Embed | スクショ 1 枚 + 文字列指示 + よくある失敗 |
| 0:25-0:30 | 5 分 | モデル DL → 合成 → 音声出力 | コピペ可能な Swift / Dart コード |

これは Flutter 公式の "Adding native code to your Flutter app" の構成に近い。彼らは "Step 1: Configure...", "Step 2: Create..." と数値順序を厳守し、スクショは Xcode の特定設定画面のみ (Embed 列など必要最小限)。

#### つまづきポイント TOP 5 と解

| # | つまづき | 頻度予測 | ドキュメント上の解 |
|---|---|---|---|
| 1 | Embed & Sign を "Do Not Embed" のまま実機ビルド → クラッシュ | 高 | 失敗時のクラッシュログ抜粋を併記 |
| 2 | ORT の dylib を Embed し忘れ → dlopen 失敗 | 高 | 「ORT の Embed は piper_plus とは別 row」と明示 |
| 3 | Privacy Manifest 不在で App Store Connect 弾かれ | 中 | 「現状未提供、自前で `PrivacyInfo.xcprivacy` 作成」リンク先を明示 |
| 4 | シミュレータでは動くが実機で動かない (arm64-only) | 中 | xcframework に simulator/device 双方含むことを明示 |
| 5 | LICENSE 表記漏れ (MIT + ORT MIT + pyopenjtalk-plus BSD) | 低だが致命 | 配布アプリへの帰属表記テンプレ提供 |

これら 5 つのうち #1 #2 は M2 §11.7 で言及済の「Embed & Sign の二重設定」問題と直結し、ドキュメントだけでは根治不可能 (module map による自動 Embed が本筋)。M3 で「ドキュメントで誤魔化す」のは技術的負債の固定化である。

### 11.5 ドキュメント保守の経済学

#### 陳腐化スパン

| 要素 | 半減期 | 年間更新負荷 |
|---|---|---|
| Xcode UI スクショ | 6-12 ヶ月 | 高 |
| Flutter/Dart API | 12-18 ヶ月 | 中 |
| ORT バージョン文字列 | 6 ヶ月 (リリースサイクル) | `docs/spec/ort-versions.md` で集約済、低 |
| URL (HF, GitHub release) | 24 ヶ月+ | `lychee` で検出可 |
| サンプルコード | piper-plus メジャー版同期 | 中 (`examples/` の CI 実行で検出) |

#### 多言語同期コスト試算

5 言語 (EN/JA/ZH/ES/FR) × 30 分/PR × 月 4 PR = 月 10 時間。年 120 時間。これは中規模 OSS 1 人月相当で、利用者が観測不能な現状では正当化不能。**JA + EN の 2 言語固定が経済合理。**

ただし機械翻訳 (DeepL API) を CI に組み込み、翻訳失敗時のみ人間レビューする運用は ROI が立つ可能性あり。M3 スコープ外。

### 11.6 現 M3 とのギャップ

#### M3 を独立マイルストーン化した弊害

M2 の xcframework が `v1.13.0-rc1` で配布開始されてから M3 が完了するまでの 1-3 週間、利用者は GitHub Release ページの xcframework.zip を見ても **どう使うかわからない** 状態に置かれる。これは M1 §11 で指摘した「観測できないがゆえに無視されがち」な問題の延長で、initial impression を最も悪化させる時期に放置している。

#### 配布物選択ガイドの混乱リスク

現状、`v1.13.0` で並走する配布物 2 種を README で並列に提示すると **どちらを選べばよいかわからない** という典型的な選択肢過多 (Hick's Law) を招く。Microsoft onnxruntime の docs (`https://onnxruntime.ai/docs/install/`) は OS×Lang×Hardware のマトリクスで一目で導出させる構造で、これに倣うべき。

#### module map / Privacy Manifest 繰り上げ提案 → **採用済 (道 A 確定)**

M2 §11.7 で示した「module map による Embed & Sign 自動化」と「Privacy Manifest 同梱」は、ドキュメントで回避するより実装で解決する方が総コストが低い、という主張をもとに **道 A 確定で M2 §3.1 / §5 Included に繰り上げ採用済**。これにより M3 で「Privacy Manifest はユーザー側で作成」を主張する必要がなくなり、利用者体験・保守性ともに改善された。M3 §3.11 の Note 節は「M2 で同梱済 / ORT 側は別途必要」の二段構成に簡素化。

### 11.7 もし今から始めるなら (推奨)

#### 推奨案 (5 段階)

1. **M3 解体・各 PR に分散**: README 更新は M1/M2 PR 内に取り込む (M3 §11 案 X) → **不採用**: 道 A 確定により M3 を独立 PR として維持
2. **`docs/guides/ios-integration.md` は「最小 Quick Start」のみ**: TTHW 30 分のジャーニーに集中、トラブルシュートは別ファイル `docs/guides/ios-troubleshooting.md` に分離
3. **配布物選択は単一推奨に絞る**: README Top で `xcframework.zip` を第一推奨、`tar.gz` は CMake 利用者のみと明記
4. **`lychee` + `markdownlint` を CI に追加**: ドキュメント陳腐化検出を自動化
5. ~~**module map / Privacy Manifest を M2.5 として実装繰り上げ**~~ → **M2 で繰り上げ採用済 (道 A 確定)**

#### 推奨を採用しない合理的理由

| 推奨 | 不採用条件 |
|---|---|
| #1 PR 統合 | M1/M2 PR が既に 1500+ 行あり diff 過大 (道 A 確定により分割を維持) |
| #2 Quick Start 集中 | 利用者の Xcode 経験差が大きく、最小手順では足りない (要観測データ) |
| #3 単一推奨 | C/C++ 利用者の存在確認が取れた場合 (現状不明) |
| #4 CI 追加 | CI 実行時間が既に 30 分超で追加余地なし |
| #5 ~~M2.5 繰り上げ~~ | **採用済 (道 A 確定)** |

#### 永遠負債リスト (M3 完了後も残る)

| 課題 | 緊急度 | 推定対応マイルストーン |
|---|---|---|
| 多言語ドキュメント (ZH/ES/FR) | 低 | 利用者観測手段確立後 |
| 動画チュートリアル | 低 | 利用者数 100+/月達成後 |
| Doc サイト (Docusaurus) | 中 | docs/guides が 5 本超えた段階 |
| ~~Privacy Manifest 自動同梱~~ | 解消 | **M2 で対応済 (道 A 確定)** |
| Xcode UI スクショ更新運用 | 中 | 半年ごとの定例タスク化 |
| 利用者問い合わせ集約場所 | 高 | GitHub Discussions 開設判断 |
| `.dSYM` 別 artifact 化 | 中 | 別 issue で追跡 |
| ORT 側 Privacy Manifest 不在 | 中 | Microsoft 上流問題、観測のみ |

#### 結語

M3 の現実解 (README 増補 + ガイド 1 本 + spec 同期) は **「マイルストーン名としてのドキュメント」を達成するが、「利用者がドキュメントから価値を得る」までの距離を縮めない**。白紙から設計するなら、ドキュメントを独立マイルストーン化せず、各実装 PR に分散させ、その代わりに module map と Privacy Manifest を実装で解決する。M3 という箱を温存するのは、組織的な進捗可視化のための装飾であり、利用者観点の最適化ではない。利用者数が観測できない現状では「最も陳腐化しにくく、最も誤解を招きにくい最小ドキュメント」を目指すのが経済合理である。

---

## 12. 後続タスクへの連絡事項

### 12.1 M4 (SPM パッケージ併設) への引き継ぎ

> 担当チケット: [`docs/tickets/377-M4-spm-package.md`](377-M4-spm-package.md)

M3 で確立する以下を M4 が継承する:

- **xcframework artifact のリリース URL 形式が確定**: `https://github.com/ayutaz/piper-plus/releases/download/v${VERSION}/libpiper_plus-ios-${VERSION}.xcframework.zip`。M4 の `Package.swift` の `binaryTarget(url:, checksum:)` でこの URL を pin する。
- **module map は M2 で同梱済 (道 A 確定)**: M4 で SPM 化する際、Swift `import PiperPlus` を成立させるには xcframework 内に `module.modulemap` を含める必要があり、これは M2 §3.1 の `cmake/PiperPlusShared.cmake` 修正で対応済。M4 では SPM の `binaryTarget` が xcframework 内 modulemap を自動的に解決するため追加対応不要。
- **`examples/swift/README.md` は SPM 公開後に書き換え**: M3 では「暫定 drag-and-drop」の手順を提供。M4 完了時に SPM 経由の `import PiperPlus` 手順に全面書き換え、暫定手順は別ブランチに退避。
- **配布物選択ガイドの拡張**: M4 完了で「SPM 経由」が 4 つ目の選択肢として加わるため、ディシジョンテーブルに行追加。
- **tar.gz 廃止タイミングと SPM 公開タイミングの調整**: v1.14.0 で tar.gz 廃止と SPM 公開を同時に行うか、別リリースに分割するかは M4 着手時に判断。

### 12.2 別 issue 候補

M3 で「未対応」と明文化した項目は、それぞれ独立 issue として起票する。M3 完了時に PR の最後で順次 issue 化する:

- **Privacy Manifest 自動同梱実装**: piper-plus xcframework に `PrivacyInfo.xcprivacy` を同梱し、利用者の手間を削減。ORT 側の Privacy Manifest 対応 (Microsoft 側) も依存条件として追跡。
- **.dSYM 別 artifact 化**: `libpiper_plus-ios-${VERSION}.dSYM.zip` を release に追加し、クラッシュレポートの symbolication を可能化。M2 ビルドフローで `dwarfdump --uuid` 確認後に `cp -R *.dSYM` するステップ追加。
- **多言語 README 自動同期**: FR/ES/DE/PT/ZH の README を英語版から差分翻訳するパイプライン構築。LLM 翻訳 + 人手レビューのワークフローが現実解。
- **download metrics 監視ダッシュボード**: GitHub Releases API の download_count を定期取得し、iOS artifact の利用実数を観測。M1 §11.5 の「永遠に埋まらない技術的負債」(利用者実数不明) への直接対応。

### 12.3 横断的な観測点

- **過渡期の利用者混乱の早期検知**: v1.13.0 リリース後 2〜4 週間は GitHub Issue / Discussions / Discord で「iOS で動かない」系の報告を注意深く監視。配布物選択の混乱や Embed 漏れが多発する場合、ガイドへの追記または FAQ 化を即座に実施。
- **CHANGELOG の言語整合**: v1.13.0 で初めて iOS 配布が成立するため、リリースノート (GitHub Releases ページ) にも CHANGELOG と同じ文言を貼り、Issue #377 を closing comment で明示的にリンク。
- **検索性**: `iOS` / `xcframework` / `Embed & Sign` / `ORT` などの語彙が複数ドキュメントに散在するため、`docs/guides/ios-integration.md` を **iOS 関連の単一エントリポイント** として位置づけ、他のドキュメントから集中リンクを貼る。

### 12.4 マージ後アクション

- [ ] `docs/tickets/README.md` 表の M3 行を `pending` → `done (PR #XXX, YYYY-MM-DD)` に更新 (本 PR 内で実施だが、PR 番号は merge 直前に書き換え)
- [ ] `docs/spec/ios-shared-lib.md §8 M3` のチェックボックスを `[x] 完了 (PR #XXX, YYYY-MM-DD)` に更新
- [ ] M3 マージ後 1 週間以内に v1.13.0 タグを切る (M1/M2/M3 の効果を初リリースで観測)
- [ ] §12.2 の別 issue (Privacy Manifest / .dSYM / 多言語 / download metrics) を起票
- [ ] M4 の着手判断: v1.13.0 リリース後 1 ヶ月の利用者反応を待ち、SPM 需要 (Issue / Discord 言及) を確認してから M4 を有効化
- [ ] M1 §11.9 で予告した「6 ヶ月以内に案 X か案 Z かを判断」のリマインダーが M3 完了時点でも有効であることを確認
- [x] ~~M3 §11.7 の繰り上げ提案 (module map / Privacy Manifest を M2 スコープ繰り上げ) を採用するかは、M2 完了直後に再評価~~ → **道 A 確定により M2 §3.1 で採用済、再評価不要**
