# [M4] Swift Package Manager パッケージ併設 (別 repo 管理)

> **iOS Shared Library Distribution 仕様 ([#377](https://github.com/ayutaz/piper-plus/issues/377)) のマイルストーン M4 実装チケット**
> 関連仕様: [`docs/spec/ios-shared-lib.md §8 M4`](../spec/ios-shared-lib.md#m4-将来-swift-package-manager-パッケージ併設)
> **本チケットは「将来別 repo + 別 issue で実装される予定」の設計記録であり、本ブランチでは実装されない。**

---

## 1. メタ情報

| 項目 | 値 |
|------|-----|
| マイルストーン | **M4** |
| 親 Issue | [#377](https://github.com/ayutaz/piper-plus/issues/377) (M4 自体は別 issue 化予定) |
| 担当ブランチ | **別 repo `ayousanz/piper-plus-swift-package-manager` で管理 (本ブランチ `dev` では実装しない)** |
| 状態 | **pending (別 issue 化予定)** |
| 想定 PR | 別 repo に 1〜3 PR (Package.swift 初版 / リリース連携 workflow / README & デモ target) |
| 想定所要 | 1〜2 日 (別 repo セットアップ + リリース連携 + Swift Package Index 登録) |
| 依存 | **M2 完了** (xcframework.zip の安定リリース) **必須**。M3 完了後を推奨 (利用者ガイド整備済) |
| ターゲット OS | iOS 14.0+ / iOS Simulator (arm64) — visionOS / macCatalyst は M5 以降 |
| ターゲット Swift | Swift 5.9+ (`swift-tools-version:5.9`) |
| 配布物 | `Package.swift` (`binaryTarget(url:, checksum:)`) + module map + デモ target |

> **位置づけ:** 本チケットは設計記録であり、本チケットのマージは実装完了を意味しない。M4 着手時に本ドキュメントを参照しつつ別 issue を切ること。
>
> **本書の主仕様 (§1〜§10) は案 Y (別 repo `piper-plus-swift-package-manager` 新設) を仮採用** して書かれている。**§11 では案 X (本体 repo 直下に `Package.swift` 配置) を強く推奨** する別案を批判的に提示する。実装時は §11.7 の判定基準で iOS 利用者観測を行い、案 Y / 案 X / 永久延期のいずれを採るかを別 issue で最終確定すること。

---

## 2. タスク目的とゴール

### Why (動機)

- **SPM ユーザー体験の整備**: iOS / macOS の Swift エコシステムでは Swift Package Manager (SPM) がデファクト標準。`Package.swift` の `dependencies` に URL を 1 行追加するだけで `import PiperPlus` が成立する形態を公式提供することで、導入摩擦を最小化する。
- **発見性の向上**: Swift Package Index (https://swiftpackageindex.com/) に登録することで、検索流入と CI バッジ (互換性マトリクス) を獲得する。
- **iOS App 開発者への訴求**: M2 で xcframework を Releases にアップロードしただけでは、利用者は手動で zip を DL → Xcode に drag & drop する必要があり敷居が高い。SPM パッケージ化でこのギャップを解消する。

### Definition of Done (案 Y 主仕様)

- [ ] 別 repo `ayousanz/piper-plus-swift-package-manager` が公開状態で存在する
- [ ] `Package.swift` で `binaryTarget(url:, checksum:)` が piper-plus Releases の `libpiper_plus-ios-${VERSION}.xcframework.zip` を指している
- [ ] 任意の SwiftPM プロジェクトで `dependencies: [.package(url: "https://github.com/ayousanz/piper-plus-swift-package-manager", from: "1.13.0")]` を追加すると依存解決が成功する
- [ ] piper-plus に新規 tag (`vX.Y.Z`) が push されると、別 repo の `Package.swift` の url/checksum が自動更新される
- [ ] Swift Package Index への登録が完了し、ビルドステータスが GREEN
- [ ] xcframework 内に **module map** が含まれ、Swift から `import PiperPlus` が成立する (M2 §11.7 の繰り上げで対応されている前提)
- [ ] デモ target (`PiperPlusDemo`) で最低 1 件の合成テスト (text → wav) が PASS

> 案 X 採用時 (§11 推奨) は別 repo を新設せず、本体 repo `ayutaz/piper-plus` 直下に `Package.swift` を配置。リリース連携の DoD は不要 (タグ push と SPM 公開が同期)、それ以外の項目は案 X でも適用される。

---

## 3. 実装する内容の詳細

> **実装場所:** 以下は別 repo `ayousanz/piper-plus-swift-package-manager` (案 Y) で行う。案 X 採用時は本体 repo `ayutaz/piper-plus` の別 PR で実施。**いずれにせよ本ブランチ `fix/ios-shared-lib-build-377` ではドキュメント (本チケット) のみ追加する**。

### 3.1 別 repo 新設 (案 Y)

```bash
gh repo create ayousanz/piper-plus-swift-package-manager \
  --public \
  --description "Swift Package Manager distribution of piper-plus iOS xcframework" \
  --license Apache-2.0
```

初期コミットには以下を含める:

- `Package.swift`
- `README.md` (使い方、ORT の併用方法)
- `.github/workflows/update-on-release.yml` (リリース連携)
- `Sources/PiperPlusDemo/` (デモ target、optional)
- `Tests/PiperPlusTests/` (簡易呼出テスト)

### 3.2 Package.swift の構造

```swift
// swift-tools-version: 5.9
import PackageDescription

let version = "1.13.0"
let checksum = "<sha256-from-release>"

let package = Package(
    name: "PiperPlus",
    platforms: [.iOS(.v14), .macOS(.v12)],
    products: [
        .library(name: "PiperPlus", targets: ["PiperPlus"]),
    ],
    targets: [
        .binaryTarget(
            name: "PiperPlus",
            url: "https://github.com/ayutaz/piper-plus/releases/download/v\(version)/libpiper_plus-ios-\(version).xcframework.zip",
            checksum: checksum
        ),
    ]
)
```

### 3.3 リリース連携 (2 案)

**案 1 (推奨): repository-dispatch で push 型連携**

piper-plus 側 `release-shared-lib.yml` の末尾に追加:

```yaml
- name: Trigger SPM repo update
  uses: peter-evans/repository-dispatch@v3
  with:
    token: ${{ secrets.SPM_REPO_PAT }}
    repository: ayousanz/piper-plus-swift-package-manager
    event-type: piper-plus-release
    client-payload: '{"version": "${{ github.ref_name }}", "checksum": "${{ steps.checksum.outputs.value }}"}'
```

別 repo 側 `update-on-release.yml`:

```yaml
on:
  repository_dispatch:
    types: [piper-plus-release]
jobs:
  update:
    steps:
      - uses: actions/checkout@v4
      - run: |
          sed -i "s/let version = .*/let version = \"${{ github.event.client_payload.version }}\"/" Package.swift
          sed -i "s/let checksum = .*/let checksum = \"${{ github.event.client_payload.checksum }}\"/" Package.swift
      - uses: peter-evans/create-pull-request@v6
        with:
          commit-message: "chore: bump to v${{ github.event.client_payload.version }}"
          title: "Release v${{ github.event.client_payload.version }}"
```

**案 2: 別 repo 側で cron polling**

`schedule: cron: '0 */6 * * *'` で piper-plus の Releases API を叩き、新しい tag があれば PR 作成。タイムラグ最大 6h。

→ **案 1 を採用**。PAT は `SPM_REPO_PAT` (別 repo の `contents: write` + `pull-requests: write` スコープ)。

> **代替案 X (§11.2 で詳述、強く推奨):** 上記の別 repo 構成自体を捨て、**本体 repo (`ayutaz/piper-plus`) 直下に `Package.swift` を置く**。リリース連携が完全に消滅し、tag push と SPM パッケージ更新が同期する。sherpa-onnx / whisper.cpp が採用している方式。

### 3.4 module map の組込み

M2 §11.7 で「M2 スコープへの繰り上げ」が提案されており、**M4 着手前に M2 への遡及修正** を検討する。具体的には `cmake/PiperPlusXCFramework.cmake` または assemble script で `Headers/module.modulemap` を自動生成:

```
framework module PiperPlus {
    umbrella header "piper_plus.h"
    export *
    module * { export * }
}
```

遡及対応が困難な場合、別 repo 側で xcframework を DL → module map を追加 → 再 zip → 別 repo 内に同梱する形になるが、binaryTarget の checksum 一致が崩れるため **非推奨**。**M2 側で対応すべき**。

### 3.5 Swift Package Index 登録

https://swiftpackageindex.com/add-a-package で repo URL を入力。`Package.swift` の `swift-tools-version` と product 定義が正しければ自動でビルド検証され、互換性バッジ (iOS / macOS / Swift version) が生成される。

---

## 4. エージェントチームの役割と人数

| 役割 | 人数 | 主担当 |
|------|------|--------|
| **SPM Engineer** | 1名 | `Package.swift` 設計、binaryTarget の url/checksum、module map 仕様調整 (M2 連携)、デモ target |
| **CI Engineer** | 1名 | piper-plus → 別 repo の repository-dispatch 連携、PAT 管理、checksum 自動計算 (`shasum -a 256`) |
| **Reviewer** | 1名 | SPM 仕様準拠、Swift API 慣習、Swift Package Index 互換 |
| **QA Engineer** | 1名 | SwiftUI App / iOS App から `import PiperPlus` 動作検証、Simulator + 実機ロード |

合計 **4 名**。M2/M3 担当者と一部重複可。

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
| 7 | リリース連携 | piper-plus に仮想 tag (`v0.0.0-test`) を push → 別 repo に PR が自動作成 |
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
| 1 | **module map 未組込み** | High | M4 着手前に M2 へ遡及修正 PR。assemble-xcframework script で自動生成。別 repo での再パッケージは checksum 不一致を招くため非推奨 |
| 2 | **リリース連携の権限管理** | Med | PAT (`SPM_REPO_PAT`) ではなく可能なら GitHub App。PAT の場合は 90 日ローテーション必須 |
| 3 | **checksum 自動計算の信頼性** | Med | piper-plus Release Action 内で `shasum -a 256` を output 登録 → repository-dispatch で渡す |
| 4 | **ORT 併用の案内不足** | Med | README に必須セクション「Required: Add onnxruntime-swift-package-manager dependency」を明記 |
| 5 | **Swift Package Index の審査時間** | Low | 登録から GREEN まで数時間〜1日 |
| 6 | **別 repo メンテナンス負荷** | Med | 自動 PR 生成までは workflow 化、merge は人間判断。`gh pr merge --auto` 推奨 |
| 7 | **xcframework サイズ** | Low | binaryTarget は zip を毎回 DL。SPM のデフォルトキャッシュ (`~/Library/Developer/Xcode/DerivedData/SourcePackages`) で対応 |

---

## 10. レビュー項目

- [ ] `Package.swift` の `swift-tools-version` が 5.9 以上
- [ ] `binaryTarget` の `url` が piper-plus Releases の正規パターン (`libpiper_plus-ios-${VERSION}.xcframework.zip`) と一致
- [ ] `checksum` が piper-plus 側 `shasum -a 256` と byte-for-byte 一致
- [ ] `platforms:` が `.iOS(.v14)` 以上
- [ ] `products: [.library]` の name が `PiperPlus` (PascalCase)
- [ ] xcframework 内 module map が `framework module PiperPlus` を宣言
- [ ] リリース連携 workflow の PAT スコープが最小権限 (`contents: write`, `pull-requests: write`)
- [ ] README に ORT 併用方法 (`microsoft/onnxruntime-swift-package-manager` 追加) を明記
- [ ] Swift Package Index バッジ (iOS / Swift version 互換性) を README 先頭に貼付
- [ ] License (Apache-2.0) が piper-plus 本体と整合

---

## 11. 一から作り直すとしたら

M4 は M1-M3 の積み上げの延長で「別 repo で SPM パッケージを併設」と素朴に置いている。しかしこれは前提自体が雑で、観測手段なき iOS 配布チャネル選択を惰性で決めている可能性が高い。本節は M4 着手前に踏み止まり、**そもそも SPM 公開の価値があるか / どこに置くか / リリース連携をどう信頼するか** を批判的に再評価する。

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
| module map は xcframework 内 `Headers/module.modulemap` | M2 §11.7 で M2 スコープに繰り上げ必要 | M2 で `cmake/PiperPlusXCFramework.cmake` に組込 |
| ORT 依存宣言 | `dependencies: [.package(url: "https://github.com/microsoft/onnxruntime-swift-package-manager")]` で対応可 | バージョンピン必須 (1.16+ で API 安定) |
| bitcode | Xcode 14+ で deprecated、不要 | `ENABLE_BITCODE=NO` |
| Privacy Manifest | iOS 17+ で App Store 提出時必須 (Required Reason API 使用時のみ) | M2 で xcframework に同梱、M4 で再追加不要 |

ORT を `dependencies` で宣言する場合、**ORT 公式 SPM パッケージのバージョンと M2 でリンクした ORT バージョンの一致** が必須。不一致なら symbol 競合が起きる。M2 で ORT 1.17.0 をリンクしたら M4 でも 1.17.0 をピン (`from: "1.17.0"` ではなく `exact: "1.17.0"`)。

### 11.5 競合実装の調査

| 実装 | 構造 | 長所 | 短所 |
|------|------|------|------|
| microsoft/onnxruntime-swift-package-manager | 別 repo、`Package.swift` で `binaryTarget(url:, checksum:)` | 公式維持、安定 | リリース遅延、特定バージョンのみ提供 |
| k2-fsa/sherpa-onnx (Package.swift 直下) | 本体 repo に `Package.swift`、`binaryTarget` で xcframework | repo 単一、タグ同期不要 | repo に Apple 設定混入 |
| ggerganov/whisper.cpp | 本体 repo に `Package.swift`、`Sources/whisper/` 直接 | C++ ソース直配布、xcframework 不要 | コンパイルオプション固定、ORT 連携不可 |

whisper.cpp 方式 (ソース直配布) は **piper-plus には不適**: piper-phonemize / espeak-ng / ORT の依存が複雑すぎてソース直配布は破綻する。**sherpa-onnx 方式 (本体 repo + xcframework binaryTarget) が最も近い参考実装** で、案 X の現実性を裏付ける。

### 11.6 現 M4 とのギャップ

| ギャップ | 現 M4 | 推奨対応 |
|----------|-------|----------|
| module map 不在で `import` 不可 | M4 で別 repo に Modules ディレクトリを後付け案 | M2 §11.7 のとおり M2 で組込む。M4 は xcframework に何も追加しない |
| 別 repo メンテ負荷 | 別 repo 新設前提 | 案 X (本体 repo) で根絶 |
| ORT 依存 | 仕様未定 | `dependencies:` で ORT 公式 SPM パッケージを exact ピン |
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

### M2/M3 への遡及対応 (M4 着手前推奨)

- **module map 組込み**: M2 の `assemble-xcframework` script に module map 自動生成を追加。これが M4 の前提条件のため、**M4 着手前に M2 へのパッチ PR が必要**
- **Privacy Manifest**: iOS 17 以降で要求される `PrivacyInfo.xcprivacy` を M2 で xcframework に同梱 (M3 §11 で言及済)。これも M4 着手時に確認

### 利用者観測

- Swift Package Index の依存数 (Reverse Dependencies 数) を月次で監視 → メンテナンス優先度の判断材料
- GitHub Releases の DL 数 (xcframework.zip) の推移と、別 repo の Star 数を併せて track

### M5 以降への伏線

- §11.7 の「3 ヶ月観測 → 案 X 採用 or 永久延期」判断を M3 完了時点で開始、M5 のスコープ決定に反映
- iOS 利用者観測ダッシュボード (M3 §12.2 の別 issue) と連動
