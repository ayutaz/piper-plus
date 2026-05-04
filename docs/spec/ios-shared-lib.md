# iOS Shared Library Distribution Specification

> **Version:** 1.0 (Proposed)
> **Status:** Proposed — to be implemented in branch `fix/ios-shared-lib-build-377`
> **対象 Issue:** [#377](https://github.com/ayutaz/piper-plus/issues/377)
> **対象ファイル:** `.github/workflows/release-shared-lib.yml`, `cmake/ios.toolchain.cmake`, `cmake/PiperPlusShared.cmake`

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
- **Zip 構造:**
  ```
  onnxruntime.xcframework/
  ├── Headers/
  │   ├── onnxruntime_c_api.h
  │   ├── onnxruntime_cxx_api.h         ← C++ API 同梱
  │   ├── onnxruntime_cxx_inline.h
  │   └── cpu_provider_factory.h
  ├── Info.plist
  ├── ios-arm64/
  │   └── onnxruntime.a                  ← device static archive
  └── ios-arm64_x86_64-simulator/
      └── onnxruntime.a                  ← simulator static archive (universal)
  ```

### 2.2 piper-plus 配布形式

**xcframework として配布**する。slice 構成:

| Slice | アーキテクチャ | 用途 |
|-------|--------------|------|
| `ios-arm64` | arm64 (device) | 実機 (iPhone/iPad) |
| `ios-arm64_x86_64-simulator` | arm64 + x86_64 (universal) | シミュレータ (Apple Silicon Mac / Intel Mac) |

**最終 artifact:** `libpiper_plus-ios-${VERSION}.xcframework.zip`

### 2.3 互換性維持

既存の `libpiper_plus-ios-arm64-${VERSION}.tar.gz` (device only `.a`) は
v1.13.0 移行期間として継続提供する。v1.14.0 で xcframework のみに集約予定。

---

## 3. 実装スコープ

### 3.1 `.github/workflows/release-shared-lib.yml`

`build-ios` ジョブを以下に再構成:

```yaml
build-ios:
  name: Build iOS xcframework
  runs-on: macos-14
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
  runs-on: macos-14
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
| Xcode メジャーバージョン更新による破壊変更 | 中 | runner image を `macos-14` でピン留め、必要時のみ更新 |
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

## 8. 実装チェックリスト

- [ ] `release-shared-lib.yml` の `build-ios` を 2 slice matrix に分割
- [ ] `assemble-xcframework` ジョブを新規追加
- [ ] CDN URL への切り替え (curl + sha256 検証)
- [ ] `cmake/ios.toolchain.cmake` の simulator slice 対応
- [ ] `examples/dart/README.md` の iOS 手順を xcframework ベースに更新
- [ ] `docs/spec/ort-versions.md` の iOS 行更新
- [ ] CHANGELOG エントリ追加
- [ ] ローカルでの xcframework 動作確認 (macos-14 相当環境)
- [ ] CI ドライラン (`workflow_dispatch` で tag なし実行)
- [ ] tag push でのフルリリース確認 (次回リリース時)

---

## Updating

本仕様変更時:

1. ORT バージョンを上げる場合: `release-shared-lib.yml` の `env.ONNXRUNTIME_VERSION` と本書 §2.1 の検証日を更新。
2. xcframework slice を追加する場合 (例: visionOS): §2.2 のテーブルと `release-shared-lib.yml` の matrix に追加。
3. 取得経路を変更する場合: §2.1 と §5 を更新し、 `docs/spec/ort-versions.md` も同期。
