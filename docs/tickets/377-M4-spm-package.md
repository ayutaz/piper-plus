# [M4] Swift Package Manager パッケージ併設 (本体 repo 直下、案 X 採用)

> **iOS Shared Library Distribution 仕様 ([#377](https://github.com/ayutaz/piper-plus/issues/377)) のマイルストーン M4 実装チケット**
> 関連仕様: [`docs/spec/ios-shared-lib.md §8 M4`](../spec/ios-shared-lib.md#m4-将来-swift-package-manager-パッケージ併設)
> **道 A 確定により本ブランチで着手する。§11.7 推奨どおり案 X (本体 repo `ayutaz/piper-plus` 直下に `Package.swift`) を主仕様とする。M2 で module map を組込済みのため後付け再 zip 不要。**

---

## 1. メタ情報

| 項目 | 値 |
|------|-----|
| マイルストーン | **M4** |
| 親 Issue | [#377](https://github.com/ayutaz/piper-plus/issues/377) |
| 担当ブランチ | `fix/ios-shared-lib-build-377` (本体 repo 内、道 A 確定) |
| 状態 | [README 表 を SoT として参照](README.md) |
| 想定 PR | 1 PR (小、~50-80 行: `Package.swift` + 最小 README、checksum はメンテナがリリース時に手動更新) |
| 想定所要 (Claude Code 実行ベース) | 実装 1-2 時間 + `swift package resolve` 検証 (CI 内で完結) ~15 分 |
| 環境制約 | Apple Silicon Mac は本セッションで使用不可。`xcodebuild -resolvePackageDependencies` / 実機 `import` テストは **Swift Package Index の自動互換性チェック + GitHub Actions macos-15 runner 上の `swift build` で代替** |
| 依存 | **M2 完了必須** (xcframework + module map が成立)、M3 推奨 (利用者ガイド整備済) |
| ターゲット OS | iOS 15.0+ / iOS Simulator (arm64+x86_64) — M2 と一致。visionOS / macCatalyst は M5 以降 |
| ターゲット Swift | Swift 5.9+ (`swift-tools-version: 5.9`) |
| 配布物 | 本体 repo 直下の `Package.swift` (`binaryTarget(url:, checksum:)`) + M2 同梱 module map + (オプション) `Sources/PiperPlusDemo/` |

> **位置づけ:** 本チケットは道 A 確定により本ブランチで実装される。
>
> **採用案:** §11.7 推奨どおり **案 X (本体 repo 直下に `Package.swift`)** を主仕様。sherpa-onnx / whisper.cpp と同方式。別 repo (案 Y) はリリース連携 PAT 管理コストが大きく、本体 repo 単一管理が経済合理。§3 以降は案 X ベースで全面再構成済み。

---

## 2. タスク目的とゴール

### Why (動機)

- **SPM ユーザー体験の整備**: iOS / macOS の Swift エコシステムでは Swift Package Manager (SPM) がデファクト標準。`Package.swift` の `dependencies` に URL を 1 行追加するだけで `import PiperPlus` が成立する形態を公式提供することで、導入摩擦を最小化する。
- **発見性の向上**: Swift Package Index (https://swiftpackageindex.com/) に登録することで、検索流入と CI バッジ (互換性マトリクス) を獲得する。
- **iOS App 開発者への訴求**: M2 で xcframework を Releases にアップロードしただけでは、利用者は手動で zip を DL → Xcode に drag & drop する必要があり敷居が高い。SPM パッケージ化でこのギャップを解消する。

### Definition of Done (案 Y 主仕様)

- [ ] 本体 repo (`ayutaz/piper-plus`) 直下に `Package.swift` が配置されている
- [ ] `Package.swift` で `binaryTarget(url:, checksum:)` が piper-plus Releases の `libpiper_plus-ios-v${VERSION}.xcframework.zip` を指している (URL の `v` 接頭辞が workflow Rename ステップと一致)
- [ ] `platforms: [.iOS(.v15)]` のみ宣言、macOS / visionOS 等は xcframework に slice が無い限り宣言しない
- [ ] consumer 側 `Package.swift` テンプレートが `examples/swift/README.md` に存在 (piper-plus 一行のみ — wrapper target が ORT を transitive 解決する旨明記)
- [ ] **メンテナ手動更新フロー** (sherpa-onnx 方式) が `Package.swift` 冒頭コメントと `examples/swift/README.md` に記載されている:
  - tag push 前に `dev` で `swift package compute-checksum` 結果を反映 → commit → tag → push
  - 旧設計 (release ジョブ内 auto-PR) は不採用 (tag commit に古い manifest が残ると SPM resolve が失敗するため)
- [ ] 任意の SwiftPM プロジェクトで `dependencies: [.package(url: "https://github.com/ayutaz/piper-plus", from: "1.13.0")]` + ORT 公式 SPM パッケージを追加で `import PiperPlus` が成立 (初回 v1.13.0 リリース後、メンテナが手動更新済み tag commit を切った時点で有効)
- [ ] xcframework 内に **module map** が含まれ、Swift から `import PiperPlus` が成立する (M2 §3.1 modulemap 自動生成で対応済)
- [ ] (将来) Swift Package Index への登録、ビルドステータスが GREEN (利用者観測 ≥ 5 件確認後の運用判断)

---

## 3. 実装する内容の詳細

> **実装場所:** 案 X 採用済 — 本体 repo `ayutaz/piper-plus` 直下に `Package.swift` を配置する。本ブランチ `fix/ios-shared-lib-build-377` で実施。

### 3.1 Package.swift の構造 (本体 repo 直下、案 X)

wrapper Swift target で `binaryTarget` を包むことで、`onnxruntime` を `dependencies:` に置き、consumer に transitive 解決させる:

```swift
// swift-tools-version: 5.9
import PackageDescription

let version = "1.13.0"
let checksum = "<sha256-from-release>"

let package = Package(
    name: "PiperPlus",
    // iOS-only — macOS / visionOS / Mac Catalyst slices は M5 候補
    platforms: [.iOS(.v15)],
    products: [
        .library(name: "PiperPlus", targets: ["PiperPlus"]),
    ],
    dependencies: [
        // ORT 公式 SPM パッケージを semver range で宣言 (1.17 系の patch update を許容)
        .package(
            url: "https://github.com/microsoft/onnxruntime-swift-package-manager",
            from: "1.17.0"
        ),
    ],
    targets: [
        // Wrapper target — `binaryTarget` は `dependencies:` を持てないため、
        // ここで onnxruntime を transitive に引き、consumer の `Package.swift` を簡略化する
        .target(
            name: "PiperPlus",
            dependencies: [
                .target(name: "PiperPlusBinary"),
                .product(
                    name: "onnxruntime",
                    package: "onnxruntime-swift-package-manager"
                ),
            ],
            path: "Sources/PiperPlus"
        ),
        .binaryTarget(
            name: "PiperPlusBinary",
            // URL の `v` 接頭辞は `release-shared-lib.yml` の Rename ステップ
            // (`mv ... libpiper_plus-ios-${TAG}.xcframework.zip` で `${TAG}` =
            // `v1.13.0`) と整合する
            url: "https://github.com/ayutaz/piper-plus/releases/download/v\(version)/libpiper_plus-ios-v\(version).xcframework.zip",
            checksum: checksum
        ),
    ]
)
```

`Sources/PiperPlus/PiperPlus.swift` は `@_exported import PiperPlusBinary` 1 行のみ — wrapper target を空にしないためのプレースホルダかつ C API surface 再エクスポートを兼ねる。

### 3.2 リリース連携 (sherpa-onnx 方式: メンテナ手動更新)

**根本制約:** SwiftPM の `binaryTarget(url:, checksum:)` は **resolved 時点での tag commit 内の `Package.swift` の値**で URL/checksum を解決する。tag push **後** に `Package.swift` を更新しても (旧設計案: release ジョブ内 auto-PR を `dev` に投げる)、その tag に対する `swift package resolve` は古い checksum を見るため失敗する。`Package.swift` の正しい値は **tag commit そのものに含まれていなければならない**。

**採用フロー:** メンテナが tag push の **前** に `Package.swift` を手動更新する。sherpa-onnx と同じ運用:

```bash
# 1. xcframework.zip を生成 (tag を切らずに workflow_dispatch で起動)
gh workflow run release-shared-lib.yml --ref dev

# 2. CI 完了を待ち、Actions Artifacts から libpiper_plus-ios-xcframework を DL
gh run download <run-id> -n libpiper_plus-ios-xcframework

# 3. checksum 計算
swift package compute-checksum libpiper_plus-ios.xcframework.zip
# → 出力された 64 桁の hex を控える

# 4. Package.swift を編集
#    let version = "1.13.0"
#    let checksum = "<上で計算した値>"
sed -i.bak \
  -e 's/^let version = .*/let version = "1.13.0"/' \
  -e 's/^let checksum = .*/let checksum = "<COMPUTED>"/' \
  Package.swift

# 5. dev に commit + tag push
git add Package.swift
git commit -m "chore(spm): bump Package.swift to v1.13.0"
git push origin dev
git tag v1.13.0
git push origin v1.13.0

# 6. tag push が release ジョブを起動、xcframework.zip が GitHub Release にアップロード
#    (xcframework のビルドは決定論的で、step 1 で計算した checksum と一致する)
```

**不採用 (旧設計): release ジョブ内 auto-PR**

旧設計では `release` ジョブの末尾で `Package.swift` を `sed` 更新 → `peter-evans/create-pull-request` で `dev` に PR 作成、という自動化を組んでいたが、**tag commit には古い `Package.swift` が残るため SPM resolve 失敗** という致命的欠陥があった (Copilot レビュー #381 で指摘)。release ジョブからは Package.swift 関連ステップを撤去済。

**不採用 (案 Y): 別 repo + repository-dispatch** — 別 repo メンテ負荷、PAT 管理、dispatch 失敗 fallback の運用コスト過大。本体 repo 単一管理で解消。

**不採用 (案 Z): cron polling** — タイムラグ最大 6h、観測欠如、運用上 brittle。

### 3.3 module map の組込み (M2 で対応済)

道 A 確定により M2 §3.1 で **`cmake/PiperPlusShared.cmake` の iOS 分岐に module map 自動生成ステップが追加済**。M4 ではこれを利用するだけで `import PiperPlus` が成立するため、追加実装不要。

参考 (M2 で生成される modulemap 内容、非 framework 形式 — static archive xcframework のため):
```
module PiperPlus {
    umbrella header "piper_plus.h"
    export *
    module * { export * }
}
```

> SPM `binaryTarget` は static archive xcframework に対し非 framework 形式の module map を期待する (`framework module` 構文は `.framework` bundle 内でのみ有効)。

M4 の `Package.swift` の `binaryTarget(url:, checksum:)` は xcframework 内 `Headers/module.modulemap` を自動的に解決するため、追加 modulemap 設定は不要。

### 3.4 Swift Package Index 登録

https://swiftpackageindex.com/add-a-package で repo URL を入力。`Package.swift` の `swift-tools-version` と product 定義が正しければ自動でビルド検証され、互換性バッジ (iOS / macOS / Swift version) が生成される。

---

## 4. 担当者と Agent 並列レビュー観点

> **実行体制:** 本タスクは Claude Code が単独で実装・検証・コミットを行う。レビューは Agent ツール (subagent) で複数観点を並列起動して補強する。「人数」表記は廃止。

| 観点 (subagent role) | 数 | 主担当 | 責務 |
|---------------------|----|------|------|
| **実装** | - | Claude Code (主) | `Package.swift` 配置 (案 X)、binaryTarget url/checksum 連携、`release-shared-lib.yml` 内での checksum 自動更新ステップ追加、最小 README、PR 起票、commit |
| **SPM 仕様レビュー** | 1 観点 | Agent (general-purpose) | `swift-tools-version` / `binaryTarget` / `dependencies` ピン方法 / `platforms:` 値が SPM 仕様準拠か |
| **整合性レビュー** | 1 観点 | Agent (general-purpose) | M2 で生成する xcframework.zip の URL / checksum 連動、ORT バージョン pin が M2 と一致 |

実装後 `Agent` ツールで 1-2 観点を並列起動。`xcodebuild -resolvePackageDependencies` の実機検証は環境制約上不可、Swift Package Index の自動互換性チェック (登録後) で代替。重大な指摘がなければ `gh pr merge --auto` で CI 完了マージ。

---

## 5. 提供範囲

### Included (M4 スコープ内)

- 別 repo `ayousanz/piper-plus-swift-package-manager` の新設と公開 (案 X 採用時は本体 repo 直下に `Package.swift` を置く)
- `Package.swift` の binaryTarget 定義
- piper-plus tag push → 別 repo `Package.swift` 自動更新の workflow (案 X 採用時は不要)
- Swift Package Index 登録
- 簡易デモ target (`PiperPlusDemo`)
- README (ORT 併用方法、minimum example)

### Excluded (M4 スコープ外)

- **piper-plus 本体への変更 (案 Y 採用時)**: M2 完了時点で xcframework 配布は確定済み、案 Y では本体 repo に `Package.swift` を置かない。ただし module map 組込みの遡及対応は別途 M2 修正 PR として扱う
- **CocoaPods 配布**: SPM のみに集中。CocoaPods は別 issue
- **visionOS / Mac Catalyst slice**: M5 以降
- **ORT の同梱**: ORT は別 SPM 経由 (`microsoft/onnxruntime-swift-package-manager`)
- **Swift API ラッパー**: 当面 C ヘッダ直叩き (`piper_plus.h`)。Swift-idiomatic ラッパーは将来検討

> 案 X 採用時は「piper-plus 本体への変更」が **必須** (本体 repo 直下に `Package.swift` 追加) となるため、上記 Excluded から除外する。

---

## 6. テスト項目

| # | 観点 | 内容 |
|---|------|------|
| 1 | 依存解決 | 新規 SwiftPM プロジェクトの `dependencies` に URL 追加 → `swift package resolve` 成功 |
| 2 | Xcode 連携 | `xcodebuild -resolvePackageDependencies` 成功、`Package.resolved` 生成 |
| 3 | import 成立 | Swift コードで `import PiperPlus` がコンパイルエラーなく通る (module map が機能) |
| 4 | 合成動作 | デモ target で text-to-speech 合成 → 16-bit PCM wav 生成 |
| 5 | Simulator 互換 | Apple Silicon Mac の iOS Simulator (arm64) でロード成功 |
| 6 | 実機互換 | iOS 実機 (arm64) でロード成功 (要 codesign 確認) |
| 7 | リリース時 checksum guard | tag commit の `Package.swift` の checksum が all-zero placeholder のまま push → release ジョブが fail (案 X のため別 repo PR は無し) |
| 8 | checksum 検証 | sha256 が不一致な状態で resolve → SPM がエラーを返す (改ざん検知) |

---

## 7. Unit テストの内容

- **checksum 計算**: `swift package compute-checksum libpiper_plus-ios-${VERSION}.xcframework.zip` の出力が piper-plus Release Action 側の `shasum -a 256` と一致することを CI で assert
- **Package.swift 構文検証**: 別 repo の CI で `swift build --target PiperPlus` を実行 (binaryTarget は実体 zip があれば成功)
- **デモ target テスト**:
  ```swift
  func testCanLoadLibrary() {
      XCTAssertNotNil(piper_plus_create_synthesizer)
  }
  ```

---

## 8. E2E テストの内容

1. **新規 SwiftUI App での導入**: Xcode で新規 iOS App プロジェクトを作成 → File → Add Package Dependencies → repo URL → `from: "1.13.0"` 指定でビルド成功 → `import PiperPlus` 通過
2. **Simulator 動作**: Apple Silicon Mac の iOS Simulator (iPhone 15, iOS 17) で起動 → サンプル text を合成 → AVAudioPlayer で再生成功
3. **実機ロード**: iOS 実機 (arm64) で codesign 通過 → アプリ起動 → wav 生成
4. **リリース連携 dry-run**: piper-plus に `v0.0.0-rc1` push → 別 repo に PR が 5 分以内に自動作成 → diff で url/checksum のみ変更を確認
5. **ORT 併用**: 利用者プロジェクトに `microsoft/onnxruntime-swift-package-manager` 追加 → 同時に依存解決成功 → 推論実行成功

---

## 9. 懸念事項

| # | 懸念 | 影響度 | 対応案 |
|---|------|--------|--------|
| 1 | ~~**module map 未組込み**~~ → **解消 (M2 で対応済、道 A 確定)** | 解消 | M2 §3.1 で `cmake/PiperPlusShared.cmake` に modulemap 自動生成済、M4 で追加対応不要 |
| 2 | **リリース連携の権限管理** | Med | PAT (`SPM_REPO_PAT`) ではなく可能なら GitHub App。PAT の場合は 90 日ローテーション必須 |
| 3 | **checksum 自動計算の信頼性** | Med | piper-plus Release Action 内で `shasum -a 256` を output 登録 → repository-dispatch で渡す |
| 4 | **ORT 併用の案内不足** | Med | README に必須セクション「Required: Add onnxruntime-swift-package-manager dependency」を明記 |
| 5 | **Swift Package Index の審査時間** | Low | 登録から GREEN まで数時間〜1日 |
| 6 | **別 repo メンテナンス負荷** | Med | 自動 PR 生成までは workflow 化、merge は人間判断。`gh pr merge --auto` 推奨 |
| 7 | **xcframework サイズ** | Low | binaryTarget は zip を毎回 DL。SPM のデフォルトキャッシュ (`~/Library/Developer/Xcode/DerivedData/SourcePackages`) で対応 |

---

## 10. レビュー項目

- [ ] `Package.swift` の `swift-tools-version` が 5.9 以上
- [ ] `binaryTarget` の `url` が piper-plus Releases の正規パターン (`libpiper_plus-ios-v${VERSION}.xcframework.zip`、v 接頭辞有り) と一致
- [ ] `checksum` が piper-plus 側 `shasum -a 256` と byte-for-byte 一致 (release ジョブの `Verify Package.swift checksum matches xcframework asset` が CI ガード)
- [ ] `platforms:` が `.iOS(.v15)` 以上 (v15 が最低互換)
- [ ] `products: [.library]` の name が `PiperPlus` (PascalCase)
- [ ] xcframework 内 module map が `module PiperPlus` (非 framework 形式) を宣言 — static archive のため
- [ ] リリース連携 workflow の PAT スコープが最小権限 (`contents: write`, `pull-requests: write`)
- [ ] README に ORT 併用方法 (`microsoft/onnxruntime-swift-package-manager` 追加) を明記
- [ ] Swift Package Index バッジ (iOS / Swift version 互換性) を README 先頭に貼付
- [ ] License (Apache-2.0) が piper-plus 本体と整合

---

## 11. 一から作り直すとしたら

M4 は M1-M3 の積み上げの延長で「別 repo で SPM パッケージを併設」と素朴に置いていた。しかしこれは前提自体が雑で、観測手段なき iOS 配布チャネル選択を惰性で決めている可能性が高い。本節は M4 着手前に踏み止まり、**そもそも SPM 公開の価値があるか / どこに置くか / リリース連携をどう信頼するか** を批判的に再評価する。

> **⚠️ 指示子スコープ注記:** 本節の「案 X / 案 Y / 案 Z」は **M4 文脈に閉じた指示子** で、他チケットとは指す内容が異なる。M4 §11.2 では: 案 X = 本体 repo に `Package.swift` 配置 (現在の主仕様)、案 Y = SPM 別 repo + 自動連携、案 Z = SPM 公開せず CocoaPods のみ を指す。
>
> **🔔 採用案決定:** 道 A 確定により本節 §11.7 推奨どおり **案 X (本体 repo `Package.swift`) を主仕様として採用済み**。§1〜§10 は案 X ベースで再構成済。本節は判断記録として残す。

### 11.1 そもそも何を作るべきか

M4 仕様が暗黙に前提としているのは「iOS 利用者は SwiftPM 経由で `import PiperPlus` したい」だが、この前提を裏付ける観測データは存在しない。M3 で xcframework.zip が GitHub Releases に上がっても、ダウンロード数・GitHub Stars 経由参照・Issue 起票数のいずれも iOS 利用実態を示さない (Releases ダウンロード数は CI/bot 込みのノイズ)。**SPM 公開する前に、xcframework を手動 drag-and-drop で使う利用者の声を Issue で集めるべき** であり、声がゼロなら M4 は永久延期が合理である。

別 repo で併設する方式は GitHub Actions 二重メンテナンス、タグ同期コスト、Package Index 登録 (Swift Package Index は repo 単位で 1 件) などの永続コストを生む。一方、本体 repo に `Package.swift` を置く方式 (sherpa-onnx / whisper.cpp 方式) は **repo 単一・タグ単一・CI 単一** で済み、別 repo 化の理由は「Package.swift が piper-plus repo を肥大化させる」程度しかない。実際、`Package.swift` は 1 ファイル数十行で肥大化するほどでもない。

module map / Privacy Manifest を M2 (xcframework 生成段階) で組み込むか、M4 (パッケージ化段階) で追加するかは、**「xcframework 単体で `import` 可能であるべきか」** の哲学的判断に帰結する。M2 で組込んでおけば xcframework を手動配置するユーザーも `import PiperPlus` できる。M4 まで遅らせると xcframework 単体配布は壊れたまま (header 直接 include しか手段がない)。これは M2 §11.7 の指摘どおり、**M2 で組込む一択** であり、M4 まで先送りする合理がない。

### 11.2 代替アーキテクチャ案 (3 案)

| 案 | 構成 | メリット | デメリット | 採用条件 |
|----|------|----------|------------|----------|
| **案 X: 本体 repo に `Package.swift`** | piper-plus repo 直下に `Package.swift`、tag → SwiftPM 自動公開 | repo 単一、CI 単一、タグ同期不要、whisper.cpp と同方式 | piper-plus repo に Apple ecosystem 設定が混入、`Sources/PiperPlus/` ディレクトリ慣習を守るか議論 | iOS 利用者 ≥ 5 件確認後、永続運用コスト最小化を優先する場合 |
| **案 Y: SPM 別 repo・自動連携** (現 M4 仕様) | `piper-plus-swift-package-manager` 新設、tag push → repository-dispatch で自動更新 | 本体 repo 軽量、Swift エコシステム慣習に沿う | 認証 PAT 管理、自動連携の故障検知が困難、別 repo の Issue が分散 | 自動連携故障時の手動回復手順が確立し、PAT ローテーション運用がある場合 |
| **案 Z: SPM 公開せず CocoaPods のみ** | Podspec 公開のみ、SPM は手動 drag-and-drop 案内 | 配布チャネル単純、メンテ最小 | 2026 年現在 SwiftPM が主流、CocoaPods は deprecation 議論 | iOS 利用者の 90% が CocoaPods を使うことが観測できた場合 (現実的にあり得ない) |

定量条件: 案 X は iOS Issue ≥ 5 件 / 月、案 Y は PAT 管理に専任 ≥ 0.1 人月、案 Z は CocoaPods 利用者比率 ≥ 80% を満たす場合のみ採用。**現状はいずれも閾値未達** であり、「M4 を着手しない」が最も合理的な可能性がある。

### 11.3 リリース連携の根本選択

| 連携方式 | 即時性 | 認証 | 故障検知 | 推奨度 |
|----------|--------|------|----------|--------|
| `peter-evans/repository-dispatch` | 即時 (秒) | PAT (repo: write) 必要 | dispatch 失敗が piper-plus CI に出る | 中 (PAT 管理コスト) |
| `schedule:` cron (毎日) | 最大 24h 遅延 | 不要 | cron job 失敗が見えにくい | 低 (遅延 + 観測欠如) |
| 手動更新 (リリース都度) | リリース担当依存 | 不要 | 忘却が最大リスク | 高 (シンプル) |
| 案 X (本体 repo) | 即時 (タグ push と同時) | 不要 | piper-plus CI で完結 | 最高 |

案 X を採用すれば連携問題そのものが消滅する。案 Y を採るなら **手動更新が現実解** で、自動連携は PAT ローテーション・dispatch 失敗時の手動 fallback 手順を整備できる体制がない限り採用すべきでない。

module map 不在のままリリースされた場合の検知は、**`Package.swift` 内の test target で `import PiperPlus` が成功するかを CI で実行** するのが唯一の信頼できる手段。tag push 時に `swift build --package-path .` を Release CI に組み込み、module map なしで失敗するなら release を中断する。

### 11.4 SPM 仕様の制約

| 制約 | 影響 | 回避策 |
|------|------|--------|
| `binaryTarget` は xcframework のみ | 静的 `.a` 直配布不可 | M2 で xcframework 化済みなので問題なし |
| slice 構成 (iOS device/sim, macOS, Catalyst, visionOS, tvOS) | M2 で iOS device/sim のみなら macOS 利用者は別途 | 当面 iOS のみで開始、要望次第で追加 |
| module map は xcframework 内 `Headers/module.modulemap` | **M2 で同梱済 (道 A 確定)** | `cmake/PiperPlusShared.cmake` で自動生成、M4 で追加対応不要 |
| ORT 依存宣言 | `dependencies: [.package(url: "https://github.com/microsoft/onnxruntime-swift-package-manager")]` で対応可 | バージョンピン必須 (1.16+ で API 安定) |
| bitcode | Xcode 14+ で deprecated、不要 | `ENABLE_BITCODE=NO` |
| Privacy Manifest | iOS 17+ で App Store 提出時必須 (Required Reason API 使用時のみ) | **M2 で空 Manifest 同梱済 (道 A 確定)**、M4 で再追加不要 |

ORT を `dependencies` で宣言する場合、**ORT 公式 SPM パッケージのバージョンと M2 でリンクした ORT バージョンの一致** が必須。不一致なら symbol 競合が起きる。M2 で ORT 1.17.0 をリンクしたら M4 でも 1.17.0 をピン (`from: "1.17.0"` ではなく `exact: "1.17.0"`)。

### 11.5 競合実装の調査

| 実装 | 構造 | 長所 | 短所 |
|------|------|------|------|
| microsoft/onnxruntime-swift-package-manager | 別 repo、`Package.swift` で `binaryTarget(url:, checksum:)` | 公式維持、安定 | リリース遅延、特定バージョンのみ提供 |
| k2-fsa/sherpa-onnx (Package.swift 直下) | 本体 repo に `Package.swift`、`binaryTarget` で xcframework | repo 単一、タグ同期不要 | repo に Apple 設定混入 |
| ggerganov/whisper.cpp | 本体 repo に `Package.swift`、`Sources/whisper/` 直接 | C++ ソース直配布、xcframework 不要 | コンパイルオプション固定、ORT 連携不可 |

whisper.cpp 方式 (ソース直配布) は **piper-plus には不適**: piper-phonemize / espeak-ng / ORT の依存が複雑すぎてソース直配布は破綻する。**sherpa-onnx 方式 (本体 repo + xcframework binaryTarget) が最も近い参考実装** で、案 X の現実性を裏付ける。

### 11.6 現 M4 とのギャップ (道 A 確定後の更新)

| ギャップ | 旧 M4 仕様 | 道 A 確定後の対応 |
|----------|-------|----------|
| ~~module map 不在で `import` 不可~~ | M4 で別 repo に Modules ディレクトリを後付け案 | **解消**: M2 §3.1 で `cmake/PiperPlusShared.cmake` に modulemap 自動生成、M4 で追加対応不要 |
| ~~別 repo メンテ負荷~~ | 別 repo 新設前提 (案 Y) | **解消**: 案 X 採用により本体 repo 直下 `Package.swift` で完結、別 repo / PAT 不要 |
| ORT 依存 | 仕様未定 | M4 §3.4 で `dependencies:` に ORT 公式 SPM パッケージを `exact:` ピン (M2 でリンクした 1.17.0 と一致) |
| Package Index 登録タイミング | M4 完了後 | iOS 利用者 ≥ 5 件確認後、それまで未登録 (drag-and-drop 案内) |

### 11.7 もし今から始めるなら (推奨)

**段階的推奨 (5 段階):**

1. **M4 着手前に iOS 利用者を観測**: GitHub Issue / Discussion で「iOS で xcframework を使った人」を募集、3 ヶ月で ≥ 5 件集まらなければ M4 永久延期
2. **M2 §11.7 の繰り上げを実施**: module map / Privacy Manifest を M2 スコープに繰り上げ、xcframework 単体で `import PiperPlus` 可能にする。これだけで利用者の 80% は満足する可能性
3. **M4 着手時は案 X (本体 repo) を採用**: `piper-plus/Package.swift` を直下に置き、`binaryTarget(url:, checksum:)` で同 repo Releases の xcframework.zip を参照。タグ同期問題が消滅
4. **ORT 依存を `exact:` でピン**: M2 と一致するバージョンを `Package.swift` で固定。CI で `swift build` を tag push 時に実行し、module map / 依存解決失敗を検知
5. **Swift Package Index 登録は最後**: 利用者 ≥ 10 件 / 月 を確認してから登録、それまでは README に手動追加手順のみ記載

**この推奨を採用しない合理的理由 (定量):**

- iOS 利用者が観測されない (≤ 1 件 / 3 ヶ月) → M4 永久延期が合理
- piper-plus repo に Apple ecosystem 設定混入を避けたい組織方針 → 案 Y (別 repo 手動更新) に移行
- ORT バージョン一致が CI で保証できない (テスト環境なし) → SPM 公開を諦めて xcframework 手動案内のみ

**永遠負債リスト (M4 完了後も残る課題):**

| 負債 | 重大度 | 観測手段 |
|------|--------|----------|
| iOS 利用者数不明問題 | 高 | Issue / Discussion 経由 (推測のみ) |
| ORT SPM バージョン追従 | 中 | ORT release watch、半年に 1 回手動更新 |
| visionOS / tvOS slice 追加要望 | 低 | Issue 起票次第 |
| App Store 審査での Privacy Manifest 不備 | 中 | 利用者からの審査落ち報告のみ (能動検知不可) |
| Swift Package Index 検索順位 | 低 | 利用者の発見性、観測不能 |

**結論:** 現 M4 仕様 (別 repo 自動連携) は **観測なき需要への過剰投資** で、案 X (本体 repo `Package.swift`) + M2 §11.7 繰り上げが最小コスト最大効果。M4 着手前に iOS 利用者観測を 3 ヶ月行い、需要が確認できなければ永久延期する判断を持つべきである。SPM 公開は「あれば嬉しい」レベルの機能であり、**M1-M3 の本体機能 (xcframework 生成・配布) が優先** である事実を見失ってはならない。

---

## 12. 後続タスクへの連絡事項

### 別 issue 候補

- **CocoaPods 配布**: `PiperPlus.podspec` を別 repo に追加する派生 issue。SPM が主流のため優先度は低いが、レガシー Xcode プロジェクト向け需要あり
- **visionOS slice 追加**: M5 で `cmake/ios.toolchain.cmake` を visionOS 対応に拡張 → xcframework に xros / xrsimulator slice を追加 → 別 repo の `Package.swift` の `platforms:` に `.visionOS(.v1)` 追加
- **Mac Catalyst slice**: 同様に macabi slice を追加し、iPad app on Mac で動作検証
- **Swift API ラッパーパッケージ (`PiperPlusKit`) の検討**: 現状は C ヘッダ直叩きだが、`final class Synthesizer` などの Swift-idiomatic API を上に被せる第二パッケージを別 issue で提案可能

### M2/M3 への遡及対応 (道 A 確定により対応済)

- ~~**module map 組込み**~~: **M2 §3.1 で対応済** (道 A 確定、`cmake/PiperPlusShared.cmake` の iOS 分岐末尾に modulemap 自動生成ロジック追加)
- ~~**Privacy Manifest**~~: **M2 §3.1 で対応済** (道 A 確定、`cmake/PrivacyInfo.xcprivacy` 新規追加 + xcframework ルートに配置)

### 利用者観測

- Swift Package Index の依存数 (Reverse Dependencies 数) を月次で監視 → メンテナンス優先度の判断材料
- GitHub Releases の DL 数 (xcframework.zip) の推移と、別 repo の Star 数を併せて track

### M5 以降への伏線

- §11.7 の「3 ヶ月観測 → 案 X 採用 or 永久延期」判断を M3 完了時点で開始、M5 のスコープ決定に反映
- iOS 利用者観測ダッシュボード (M3 §12.2 の別 issue) と連動
