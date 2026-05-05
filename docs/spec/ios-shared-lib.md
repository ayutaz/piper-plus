# iOS Shared Library Distribution Specification

> **Version:** 1.1
> **Status:** Implemented (v1.13.0) — `fix/ios-shared-lib-build-377` で M1→M2→M3 完了、M4 (Package.swift 案 X) 同ブランチに含む
> **対象 Issue:** [#377](https://github.com/ayutaz/piper-plus/issues/377)
> **対象ファイル:** `.github/workflows/release-shared-lib.yml`, `cmake/ios.toolchain.cmake`, `cmake/PiperPlusShared.cmake`, `cmake/PrivacyInfo.xcprivacy`, `Package.swift` (M4)

---

## 概要

本仕様は piper-plus の **iOS 向け shared library 配布** の取得経路と配布形式を定義する。
v1.11.0 〜 v1.12.0 で iOS ビルドが継続失敗していた問題 (Issue #377) の根本対応として、
ハイブリッド方針 (Microsoft 公式 CDN + xcframework 化) を採用する。

---

## 1. 背景: 問題の階層構造

| 層 | 問題 | v1.12.0 時点の現象 |
|----|------|---------------------|
| 表層 | `Build iOS arm64` ジョブが Download ステップで失敗 | `unzip: cannot find zipfile directory` (取得が空ファイル) |
| 中層 | ONNX Runtime の GitHub Releases から iOS xcframework が削除 | Microsoft が CocoaPods/SPM/CDN 配布に一本化 |
| **根本** | **配布物 `.a` (static archive) が iOS 利用シナリオと不整合** | **Dart FFI / Godot / Swift は `.framework` か `.xcframework` を要求 — 実質誰も使えない** |

Issue #377 は表層の問題を指摘しているが、修正しても利用者が使えなければ意味がない。
本仕様は中層と根本の両方を同時に解決する。

### 失敗ジョブの巻き添え影響

`release-shared-lib.yml` の `release` ジョブは
`needs: [build-shared, build-ios, build-android]` で iOS に依存しているため、
**iOS の失敗で Linux/Windows/macOS/Android shared-lib も含む全 OS の成果物が
GitHub Releases に上がっていない**。これが本対応の最大の優先度根拠。

---

## 2. 採用方針: Plan A (CDN + xcframework 化)

### 2.1 ORT 取得経路

Microsoft 公式 CDN から CocoaPods/SPM 共用 zip を取得する:

```
https://download.onnxruntime.ai/pod-archive-onnxruntime-c-${ONNXRUNTIME_VERSION}.zip
```

- **正当性:** `onnxruntime-swift-package-manager` の `Package.swift` が
  `binaryTarget(url:)` でこの URL を指している。Microsoft が壊すと
  CocoaPods/SPM が連動して壊れるため、強い不変条件として機能する。
- **検証 (2026-05-04):** 1.17.0 / 1.20.0 / 1.22.0 とも HTTP 200 OK (40〜49 MB)。
- **sha256 (1.17.0):** `1623e1150507d9e50554e3d3e5cf9abf75e1bfd8324b74a602acfe45343db871` (40,771,813 bytes)
- **Zip 構造:**
  ```
  onnxruntime.xcframework/
  ├── Info.plist
  ├── ios-arm64/
  │   └── onnxruntime.framework/
  │       ├── onnxruntime              ← Mach-O dynamic library (device, 拡張子なし, ~31MB)
  │       ├── Headers/
  │       │   ├── onnxruntime_c_api.h
  │       │   ├── onnxruntime_cxx_api.h     ← C++ API 同梱
  │       │   ├── onnxruntime_cxx_inline.h
  │       │   ├── coreml_provider_factory.h
  │       │   ├── cpu_provider_factory.h
  │       │   ├── onnxruntime_float16.h
  │       │   ├── onnxruntime_run_options_config_keys.h
  │       │   └── onnxruntime_session_options_config_keys.h
  │       └── Info.plist
  ├── ios-arm64_x86_64-simulator/
  │   └── onnxruntime.framework/
  │       ├── onnxruntime              ← Mach-O dynamic library (simulator universal, ~67MB)
  │       ├── Headers/                  ← (同上)
  │       └── Info.plist
  └── macos-arm64_x86_64/
      └── onnxruntime.framework/
          ├── onnxruntime              ← Mach-O dynamic library (macOS universal, ~69MB)
          ├── Headers/                  ← (同上)
          └── Info.plist
  ```

> **⚠️ 重要 (2026-05-04 発覚):** 旧 GitHub Releases zip は `ios-arm64/onnxruntime.a`
> (static archive) を出力していたが、**現行 CDN zip は `.framework` バンドル形式の
> Mach-O dynamic library のみを提供**する。`.a` static archive は同梱されない。
> したがって:
> - 旧来の `.a` を CMake で static link する CI ロジックは流用不可、`.framework`
>   ベースに書き直す必要がある (M1 で対応)
> - iOS では dylib 単体配布は App Store が拒否するため、消費者側で
>   `Embed & Sign Frameworks` への追加が必須 (M3 で利用者ガイドに明記)
> - 純粋 static archive が必要な場合は ORT ソースビルドに切替 (将来 M5 検討)

### 2.2 piper-plus 配布形式

**xcframework として配布**する。slice 構成:

| Slice | アーキテクチャ | 用途 |
|-------|--------------|------|
| `ios-arm64` | arm64 (device) | 実機 (iPhone/iPad) |
| `ios-arm64_x86_64-simulator` | arm64 + x86_64 (universal) | シミュレータ (Apple Silicon Mac / Intel Mac) |

**最終 artifact:** `libpiper_plus-ios-v${VERSION}.xcframework.zip`

### 2.3 互換性維持

v1.11.0 / v1.12.0 で iOS shared-lib artifact は実際には Releases に上がっていなかった
(`build-ios` ジョブの継続失敗により release ジョブが巻き添え停止)。よって厳密な意味の
「旧形式 `.a` の既存利用者」は観測されておらず、後方互換の対象は存在しない。

ただし `libpiper_plus-ios-arm64-${VERSION}.tar.gz` の **命名そのもの** は v1.13.0 で
継続使用する (中身は `.framework` 同梱の tar.gz になる、§2.1 ⚠️ 注記参照)。v1.14.0 で
`xcframework.zip` 命名に集約し、tar.gz 命名は廃止予定。

---

## 3. 実装スコープ

### 3.1 `.github/workflows/release-shared-lib.yml`

`build-ios` ジョブを以下に再構成:

```yaml
build-ios:
  name: Build iOS xcframework
  runs-on: macos-15
  strategy:
    fail-fast: false
    matrix:
      include:
        - slice: ios-arm64
          osx_archs: arm64
          sdk: iphoneos
        - slice: ios-arm64_x86_64-simulator
          osx_archs: "arm64;x86_64"
          sdk: iphonesimulator
  steps:
    - uses: actions/checkout@v6
    - name: Download ONNX Runtime (CDN)
      run: |
        curl -L --fail \
          -o ort.zip \
          "https://download.onnxruntime.ai/pod-archive-onnxruntime-c-${ONNXRUNTIME_VERSION}.zip"
        unzip -q ort.zip -d ort
        # slice に対応する onnxruntime.a + Headers を抽出
    - name: Configure CMake (per slice)
    - name: Build (per slice)
    - name: Upload slice artifact

assemble-xcframework:
  needs: build-ios
  runs-on: macos-15
  steps:
    - name: Download all slice artifacts
    - name: xcodebuild -create-xcframework
      run: |
        xcodebuild -create-xcframework \
          -library ios-arm64/libpiper_plus.a -headers include \
          -library ios-arm64_x86_64-simulator/libpiper_plus.a -headers include \
          -output piper_plus.xcframework
    - name: Package + upload
```

### 3.2 `cmake/ios.toolchain.cmake`

- 既存の device-only 設定をパラメータ化し、`CMAKE_OSX_SYSROOT` (iphoneos / iphonesimulator) と `CMAKE_OSX_ARCHITECTURES` の組合せに対応させる。
- bitcode は無効 (Xcode 14+ で deprecated)。

### 3.3 `cmake/PiperPlusShared.cmake`

iOS 分岐は既に static lib 出力に切り替わっているため大きな変更不要。simulator slice もまったく同じビルドフローで動く想定。

### 3.4 `examples/dart/README.md`

iOS 統合手順を xcframework ベースに更新:

```bash
# Dart FFI / Flutter から使う場合
unzip libpiper_plus-ios-*.xcframework.zip
# ios/Runner.xcodeproj に piper_plus.xcframework を追加
```

### 3.5 `docs/spec/ort-versions.md`

iOS 行を更新:

```markdown
| iOS | 1.17.0 | xcframework (Microsoft CDN: download.onnxruntime.ai) |
```

---

## 4. 採用しなかった案

| 案 | 概要 | 不採用理由 |
|----|------|----------|
| **CocoaPods 経由** (Issue 推奨) | `pod install` で xcframework を抽出 | CDN 直接取得で同じ zip が得られるため Podfile/`pod install` のオーバーヘッドが不要 |
| **SPM 経由** | `xcodebuild -resolvePackageDependencies` | SPM 自体が CDN の同じ zip を `binaryTarget` で取得するだけ。スタブ Package.swift を作る手間が無駄 |
| **ORT ソースビルド** | `build_apple_framework.py` 実行 | 30〜45 分の初回ビルド、Xcode/protobuf/abseil 互換性管理の負荷が過大。将来 Microsoft が CDN を壊した場合の fallback として温存 |
| **コミュニティミラー** (csukuangfj/onnxruntime-libs) | sherpa-onnx 採用例あり | 第三者リポジトリへの依存。CDN 失効時の fallback として温存 |
| **iOS skip** | `build-ios` ジョブを `if: false` | 利用者がいる可能性を考慮し、また xcframework 化で実用形態を整えれば需要は喚起できる |
| **VOICEVOX 方式** (別 repo で ORT 配布) | `ayousanz/onnxruntime-ios-builder` 新設 | プロジェクト規模に対して過剰、運用負荷 2 重 |

---

## 5. リスクと対応

| リスク | 確度 | 対応 |
|--------|------|------|
| Microsoft CDN URL の変更/失効 | 低 (CocoaPods/SPM 共有のため不変条件強) | csukuangfj/onnxruntime-libs ミラーへの fallback を追加 (`||` で連鎖) |
| 特定パッチバージョンが CDN に未公開 (例: 1.20.1) | 中 | メジャー・マイナーで version pin、欠番回避は `ort-versions.md` で管理 |
| xcframework slice path の変更 | 低 | `find -name "onnxruntime.xcframework" -type d` で動的解決 (既存ロジック流用) |
| Xcode メジャーバージョン更新による破壊変更 | 中 | runner image を `macos-15` (Xcode 16.4 デフォルト、Xcode 26 も installed) でピン留め、必要時のみ更新。次の昇格候補は `macos-26` (Xcode 26.x、iOS 26 SDK) |
| ORT 1.17.0 が将来 CDN から外れる | 低〜中 | アーカイブミラー (csukuangfj) または社内 GitHub Release ミラーへ事前バックアップ |

---

## 6. 移行可能性

Plan A の xcframework ビルドロジック (`xcodebuild -create-xcframework`) は ORT 取得経路と独立している。将来の選択肢:

- **取得経路の差し替え**: CDN → コミュニティミラー → ソースビルド (本仕様の `build-ios` の Download ステップだけを変更)
- **配布形態の拡張**: xcframework に加えて Swift Package Manager リポジトリ (`ayousanz/piper-plus-swift-package-manager`) を併設し `binaryTarget(url:)` で xcframework.zip を参照させる (別 issue で管理)

---

## 7. 関連リンク

- Issue #377: https://github.com/ayutaz/piper-plus/issues/377
- Failed v1.12.0 run: https://github.com/ayutaz/piper-plus/actions/runs/25304553360
- ONNX Runtime iOS Build Docs: https://onnxruntime.ai/docs/build/ios.html
- ONNX Runtime SPM Repo: https://github.com/microsoft/onnxruntime-swift-package-manager
- 業界事例 (sherpa-onnx): https://github.com/k2-fsa/sherpa-onnx/blob/master/.github/workflows/build-xcframework.yaml
- 業界事例 (whisper.cpp): https://github.com/ggml-org/whisper.cpp/blob/master/build-xcframework.sh
- 業界事例 (VOICEVOX/onnxruntime-builder): https://github.com/VOICEVOX/onnxruntime-builder/releases
- ORT issue #21181 (CocoaPods archive zip 欠番): https://github.com/microsoft/onnxruntime/issues/21181

---

## 8. マイルストーン

本仕様の実装は 4 フェーズに分割する。M1〜M3 は本ブランチ (`fix/ios-shared-lib-build-377`) で順次実施、M4 は別 issue 管理。

各マイルストーンは独立した PR として提出可能で、M1 完了時点で表層問題 (release ジョブ巻き添え) は解消され、Linux/Windows/macOS/Android shared-lib も Releases に上がるようになる。

### M1. 取得経路の修復 (release ジョブの解凍)

> **目的:** 表層問題を最短で解消し、shared-lib リリースパイプライン全体を復旧する。

- **状態:** done (PR #381, 2026-05-05)
- **スコープ:**
  - [ ] `release-shared-lib.yml:144-176` の `Download ONNX Runtime iOS` run ブロックを書き換え
    - curl URL を `https://download.onnxruntime.ai/pod-archive-onnxruntime-c-${ONNXRUNTIME_VERSION}.zip` に変更
    - sha256 検証ステップ追加 (再現性 + サプライチェーン最低限)
    - 旧 `.a` 抽出ロジックを `.framework` (Mach-O dylib) ベースに書換 (CDN zip に `.a` が同梱されないため、§2.1 ⚠️ 注記参照)
  - [ ] `Package` ステップで `onnxruntime.framework` を tar.gz に同梱 (利用者は Embed & Sign で取込)
  - [ ] CMake 連携検証: `cmake/PiperPlusShared.cmake` の dylib リンク互換性をシンボル解決検証 (`nm -u` / `nm -gU`) で確認
- **完了条件 (DoD):**
  - `workflow_dispatch` 実行で `Build iOS arm64` ジョブが PASS
  - tag push 時に `Create Release` ジョブが起動し、Linux/Windows/macOS/Android/iOS の全 shared-lib artifact が Releases にアップロード
  - `libpiper_plus-ios-arm64-${VERSION}.tar.gz` が生成され、中身は `lib/libpiper_plus.a` + `lib/onnxruntime.framework/` + `include/piper_plus.h`
- **依存:** なし (M0)
- **リスク:**
  - CDN URL 失効 → §5 のリスク対応 (csukuangfj/onnxruntime-libs ミラーへ `||` フォールバック、M2 以降検討)
  - 特定パッチバージョン未公開 → §5 (version pin)
- **PR 単位:** 1 PR (中、~60-80 行 diff)
- **想定所要 (Claude Code 実行ベース):** 実装 1-2 時間 + `workflow_dispatch` CI ~20 分 (1 サイクル) + 仮想 tag push 検証 ~30 分。**ローカル Apple Silicon Mac 検証は環境制約上不可、CI 完結フロー**

### M2. xcframework 化 (配布形式の実用化)

> **目的:** 根本問題 (`.a` 単独配布が Dart FFI / Godot / Swift と不整合) を解消し、iOS 利用シナリオを実用化する。
> **判断 2 採用:** module map / Privacy Manifest を M2 スコープに繰り上げ (旧 M2 §11.7 提案、4 観点レビュー一致推奨、後付け運用負債を回避)。

- **状態:** done (PR #381, 2026-05-05)
- **スコープ:**
  - [ ] `release-shared-lib.yml` の `build-ios` を `matrix.slice` で 2 分割
    - `slice: ios-arm64` (sdk: iphoneos, archs: arm64)
    - `slice: ios-arm64_x86_64-simulator` (sdk: iphonesimulator, archs: "arm64;x86_64")
  - [ ] 新規 `assemble-xcframework` ジョブを追加 (`needs: build-ios`)
    - 各 slice の `libpiper_plus.a` + headers + `module.modulemap` + `PrivacyInfo.xcprivacy` をダウンロード
    - `xcodebuild -create-xcframework` で統合
    - `libpiper_plus-ios-v${VERSION}.xcframework.zip` を生成
  - [ ] `cmake/ios.toolchain.cmake` の simulator slice 対応
    - `CMAKE_OSX_SYSROOT` (iphoneos / iphonesimulator) と `CMAKE_OSX_ARCHITECTURES` のパラメータ化
    - bitcode 無効維持
  - [ ] `cmake/PiperPlusShared.cmake` の iOS 分岐確認 (大きな変更不要見込み)
  - [ ] **module map 自動生成** (`module.modulemap` を CMake で生成、Swift `import PiperPlus` 成立)
  - [ ] **空 Privacy Manifest 同梱** (`PrivacyInfo.xcprivacy`、Required Reason API 不使用宣言)
  - [ ] `release.needs:` に `assemble-xcframework` を追加 (M1 で `build-ios` を残しつつ並走)
- **完了条件 (DoD):**
  - xcframework に device (arm64) + simulator (arm64 + x86_64) の両 slice が含まれる
  - `lipo -info` または `xcodebuild -checkFirstLaunchStatus` で 3 アーキテクチャ確認
  - 各 slice に `Headers/module.modulemap` + `PrivacyInfo.xcprivacy` が含まれる
  - macOS シミュレータ (Apple Silicon) でのロード検証は環境制約上 CI 内で完結 (`xcodebuild -create-xcframework` 成功 + Info.plist 生成検証)
  - tag push で `libpiper_plus-ios-v${VERSION}.xcframework.zip` が Releases にアップロード
- **依存:** M1 完了
- **リスク:**
  - `xcodebuild -create-xcframework` の互換性 (Xcode 15.x 〜 16.x で安定)
  - simulator slice ビルド失敗時のデバッグコスト
  - **追加:** module map / Privacy Manifest を M2 に繰り上げたことで PR 規模が ~30 行増 (~150 → ~180-230 行)
- **PR 単位:** 1 PR (中、~180-230 行 diff、modulemap + PrivacyInfo 追加分込み)
- **想定所要 (Claude Code 実行ベース):** 実装 2-4 時間 + `workflow_dispatch` CI ~30 分 (matrix 並列のため 1-2 サイクル) + 仮想 tag push 検証 ~30 分。**ローカル Apple Silicon Mac 検証 (drag-drop / `xcrun simctl` boot) は環境制約上不可、CI 内 `xcodebuild -create-xcframework` 成功で代替**

### M3. ドキュメント・移行ガイド整備

> **目的:** 利用者が xcframework を組み込めるよう統合手順を整備し、既存 `.a` 配布の段階的廃止を案内する。

- **状態:** done (PR #381, 2026-05-05)
- **スコープ:**
  - [ ] `examples/dart/README.md` の iOS 統合手順を xcframework ベースに刷新
    - 現状の「`.framework` か `.dylib` が必要」記述 (L113) を実装と整合させる
    - Xcode への組込み手順 (drag & drop / Build Phases)
  - [ ] `examples/godot/README.md:199` の Feature Comparison 表 `Platforms` 行更新 + `## Platform Notes` 配下に新規 `### iOS` セクション追加
  - [ ] `docs/spec/ort-versions.md:19` iOS 行を `xcframework (Microsoft CDN: download.onnxruntime.ai)` に更新
  - [ ] `CHANGELOG.md` の v1.13.0 セクションにエントリ追加
    - "iOS shared-lib を xcframework として配布 (Issue #377)"
    - "既存 `libpiper_plus-ios-arm64.tar.gz` は v1.13.0 移行期間として継続、v1.14.0 で廃止予定"
  - [ ] 本書冒頭 Status を `Proposed` → `Implemented (v1.13.0)` に更新
  - [ ] `docs/guides/ios-integration.md` を新規作成し、Dart/Godot/Swift それぞれの統合方法をまとめる
  - [ ] `examples/swift/README.md` を新規作成 (M4 完了前の暫定 drag-and-drop 手順、M4 完了で SPM 経由に書き換え)
- **完了条件 (DoD):**
  - Dart プロジェクトに xcframework を組込む手順が再現可能
  - CHANGELOG に Breaking change 予告 (v1.14.0 で `.a` 廃止) が記載
  - 本書のステータス更新済み
- **依存:** M2 完了
- **リスク:** Xcode 操作のスクリーンショット陳腐化 (将来の Xcode UI 変更時)
- **PR 単位:** 1 PR (中、~440 行 diff、新規 ~330 行 + 編集 ~110 行)
- **想定所要 (Claude Code 実行ベース):** 実装 1-2 時間 (ドキュメント執筆) + ローカル markdownlint / lychee 検証 ~10 分。**Xcode UI スクリーンショットは Apple Silicon Mac 環境必要のため文字列指示主、画像は別 issue で追補**

### M4. Swift Package Manager パッケージ併設

> **目的:** SPM ユーザーへ公式パッケージを提供し、`import PiperPlus` で消費可能にする。
> **採用案:** 道 A 確定により本ブランチでも着手可。チケット §11 推奨どおり **案 X (本体 repo 直下に `Package.swift`)** を主仕様とする (案 Y の別 repo 新設はリリース連携負債が大きいため不採用)。M2 で module map を組込み済みのため後付け再 zip 不要。

- **状態:** done (PR #381, 2026-05-05)
- **スコープ:**
  - [ ] 本体 repo (`ayutaz/piper-plus`) 直下に `Package.swift` を配置 (案 X)
    - `binaryTarget(url:, checksum:)` で piper-plus Releases の `libpiper_plus-ios-v${VERSION}.xcframework.zip` を参照 (URL の `v` 接頭辞は workflow の Rename ステップと整合)
    - `platforms: [.iOS(.v15)]` のみ (macOS slice は v1.13.0 では未提供、M5 候補)
    - `dependencies` 宣言は **しない** (`binaryTarget` が dependencies を transitively 解決できないため。consumer 側で ORT を別途追加する運用に統一、`examples/swift/README.md` で案内)
  - [ ] tag commit に正しい version + checksum を含める運用フロー (sherpa-onnx 方式):
    - メンテナが tag push **前** に `dev` 上で `Package.swift` を手動更新 (workflow_dispatch で xcframework.zip を生成 → `swift package compute-checksum` → 値を反映 → commit → tag push)
    - 旧設計の release ジョブ内自動 PR 作成は **採用せず** (tag commit に古い manifest が残るため `swift package resolve` が失敗するため)
  - [ ] (オプション) `Sources/PiperPlusDemo/` でコンパイル検証用の最小 target 追加
  - [ ] Swift Package Index 登録 (利用者観測 ≥ 5 件確認後)
- **完了条件 (DoD):**
  - `Package.swift` が本体 repo 直下に存在し、`platforms: [.iOS(.v15)]` のみで宣言されている
  - URL が `libpiper_plus-ios-v\(version).xcframework.zip` パターンに一致
  - 初回 `v1.13.0` リリース時にメンテナが手動更新の手順を踏み、tag commit に正しい checksum が含まれていることを確認
  - `examples/swift/README.md` に consumer 側の `Package.swift` テンプレート (piper-plus + ORT 同時宣言) が記載済み
- **依存:** M2 完了 (xcframework + module map が成立)、M3 推奨 (利用者ガイド整備)
- **リスク:**
  - 本体 repo に Apple ecosystem 設定が混入 (案 X のトレードオフ、sherpa-onnx / whisper.cpp は同方式採用)
  - SPM の dependency hell (ORT バージョン不整合)
- **PR 単位:** 1 PR (小、~50-80 行: `Package.swift` + workflow 更新 + 最小 README)
- **想定所要 (Claude Code 実行ベース):** 実装 1-2 時間 + `swift package resolve` 検証 (CI 内で完結) ~15 分。**ローカル `xcodebuild -resolvePackageDependencies` / 実機ロード検証は環境制約上不可、Swift Package Index の自動互換性チェックで代替**

### 全体タイムライン (Claude Code 実行ベース、道 A 採用)

```
本ブランチ (fix/ios-shared-lib-build-377)
  ├─ M1 (curl URL 修正 + sha256 + .framework extraction)
  │    実装 1-2h + CI 1 サイクル ~20m + 仮想 tag 検証 ~30m
  ├─ M2 (xcframework 化 + module map + Privacy Manifest)
  │    実装 2-4h + CI 1-2 サイクル ~30m + 仮想 tag 検証 ~30m
  ├─ M3 (docs / examples / CHANGELOG)
  │    実装 1-2h + ローカル markdown 検証 ~10m
  └─ M4 (Package.swift 案 X)
       実装 1-2h + swift package resolve 検証 ~15m

総実装時間: 5-10 時間 + CI サイクル時間 (Apple Silicon Mac 不要、CI 完結フロー)
```

### 進捗トラッキング

- 各マイルストーンの完了状態は §8 各 M セクション冒頭の `**状態:**` 行に記載
- マイルストーン完了 PR では本書冒頭の `Status:` フィールドと該当 M の `**状態:**` 行を更新
- M1 完了で `Status: Partially Implemented`、M3 完了で `Status: Implemented (v1.13.0)`、M4 完了で `Status: Implemented + SPM (v1.13.0 or v1.14.0)` を目安とする

---

## Updating

本仕様変更時:

1. **ORT バージョンを上げる場合:** `release-shared-lib.yml` の `env.ONNXRUNTIME_VERSION` と本書 §2.1 の検証日を更新。
2. **xcframework slice を追加する場合** (例: visionOS): §2.2 のテーブルと `release-shared-lib.yml` の matrix に追加。
3. **取得経路を変更する場合:** §2.1 と §5 を更新し、 `docs/spec/ort-versions.md` も同期。
4. **マイルストーン進捗の反映:** 各 M の `**状態:**` 行と本書冒頭の `Status:` を更新。新規マイルストーンを追加する場合は §8 末尾に M5 以降として追記。
