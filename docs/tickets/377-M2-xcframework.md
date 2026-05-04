# [M2] xcframework 化 (配布形式の実用化)

> **iOS Shared Library Distribution 仕様 ([#377](https://github.com/ayutaz/piper-plus/issues/377)) のマイルストーン M2 実装チケット**
> 関連仕様: [`docs/spec/ios-shared-lib.md §8 M2`](../spec/ios-shared-lib.md#m2-xcframework-化-配布形式の実用化)

---

## 1. メタ情報

| 項目 | 値 |
|------|-----|
| マイルストーン | **M2** ([xcframework 化 / 配布形式の実用化](../spec/ios-shared-lib.md#m2-xcframework-化-配布形式の実用化)) |
| 親 Issue | [#377](https://github.com/ayutaz/piper-plus/issues/377) |
| ブランチ | `fix/ios-shared-lib-build-377` |
| 状態 | [README 表 を SoT として参照](README.md) |
| 想定 PR | 1 PR (中、~180-230 行 diff、modulemap + PrivacyInfo 繰り上げ採用で +30 行) |
| 想定所要 (Claude Code 実行ベース) | 実装 2-4 時間 + `workflow_dispatch` CI ~30 分 (matrix 並列で 1-2 サイクル) + 仮想 tag push 検証 ~30 分 |
| 環境制約 | Apple Silicon Mac は本セッションで使用不可。drag-drop / `xcrun simctl` boot / 実機ロード検証は **CI 内 `xcodebuild -create-xcframework` 成功 + `plutil -p Info.plist` 検証で代替**。手動実機検証は v1.13.0-rc1 リリース後の利用者観測で行う |
| 関連仕様 | [docs/spec/ios-shared-lib.md §2.1 ORT 取得経路](../spec/ios-shared-lib.md#21-ort-取得経路), [§2.2 piper-plus 配布形式](../spec/ios-shared-lib.md#22-piper-plus-配布形式), [§2.3 互換性維持](../spec/ios-shared-lib.md#23-互換性維持), [§8 M2](../spec/ios-shared-lib.md#m2-xcframework-化-配布形式の実用化) |
| 対象ワークフロー | `.github/workflows/release-shared-lib.yml` (`build-ios` 既存ジョブの matrix 化 + `assemble-xcframework` 新規ジョブ追加) |
| 対象 CMake | `cmake/ios.toolchain.cmake` (simulator slice パラメータ化), `cmake/PiperPlusShared.cmake` (両 slice の dylib リンク互換性確認) |

> **依存関係:** **M1 完了が前提**。M1 ([`377-M1-ort-fetch-fix.md`](377-M1-ort-fetch-fix.md)) で確立した CDN URL (`https://download.onnxruntime.ai/pod-archive-onnxruntime-c-${ONNXRUNTIME_VERSION}.zip`)、sha256 値 (`1623e1150507d9e50554e3d3e5cf9abf75e1bfd8324b74a602acfe45343db871`)、`.framework` ベース extraction ロジックをそのまま継承する。

---

## 2. タスク目的とゴール

### 目的 (Why)

M1 完了で release パイプラインの巻き添え停止は解消したが、**根本問題 (`.framework` 単独配布が xcframework のサブセットでしかない)** はそのまま残っている。Dart FFI / Godot / Swift / Flutter の各エコシステムは 2019 年以降 xcframework 前提に収束しており、device-only `.framework` 同梱 tar.gz は次のいずれの利用シナリオも完全には満たさない:

1. **Apple Silicon Mac での iOS シミュレータ実行**: simulator slice (arm64+x86_64 universal) が無いため `xcrun simctl` 経由でロードできない
2. **Xcode への drag-and-drop 統合**: `.xcframework` ディレクトリ単位で `Embed & Sign Frameworks` に登録するのが Apple 標準フロー、`.framework` 単独では実機/シミュレータ切替に手作業が必要
3. **将来の SPM 連携 (M4)**: `Package.swift` の `binaryTarget(url: ..., checksum: ...)` は **xcframework.zip を強く想定**、`.framework` 単体の zip は SPM 文法的にも非対応

M2 は `.framework` 同梱 tar.gz を「device + simulator 両 slice を含む xcframework」に進化させ、Dart FFI/Godot/Swift 全てで実用可能な形態を初めて成立させる。仕様書 §1 が指摘する**根本問題の解決**は M1 ではなく M2 で完了する点を明確化する。

### ゴール (DoD)

- [ ] `release-shared-lib.yml` の `build-ios` ジョブが `matrix.slice` で 2 分割され、device (arm64) と simulator (arm64+x86_64) の各 `libpiper_plus.a` + headers がジョブ artifact として個別に upload される
- [ ] 新規 `assemble-xcframework` ジョブが両 slice artifact を download し、`xcodebuild -create-xcframework` で `piper_plus.xcframework` を生成、`libpiper_plus-ios-${VERSION}.xcframework.zip` として upload される
- [ ] `cmake/ios.toolchain.cmake` が `CMAKE_OSX_SYSROOT` (iphoneos / iphonesimulator) と `CMAKE_OSX_ARCHITECTURES` (arm64 / "arm64;x86_64") の組合せで両 slice を生成可能
- [ ] xcframework に device (`ios-arm64`) と simulator (`ios-arm64_x86_64-simulator`) の 2 slice + `Info.plist` が含まれる (`xcodebuild -checkFirstLaunchStatus` 相当のチェック PASS)
- [ ] `lipo -info` で device slice は `arm64`、simulator slice は `arm64 x86_64` を返す
- [ ] Apple Silicon Mac で `xcrun simctl` 経由で simulator slice の動的ロードが成功
- [ ] tag push (`v[0-9]*`) で `Create Release` ジョブが `libpiper_plus-ios-${VERSION}.xcframework.zip` を Releases にアップロード
- [ ] **既存 `libpiper_plus-ios-arm64-${VERSION}.tar.gz` (M1 形式) も並行配布**継続 (v1.13.0 移行期間、v1.14.0 で廃止予告は M3 で行う)
- [ ] 非 iOS ジョブ (`build-shared` x3 / `build-android`) への影響ゼロ

---

## 3. 実装する内容の詳細

### 3.1 編集ファイル一覧

| ファイル | 編集箇所 | 変更内容 | 行数感 |
|---------|---------|---------|-------|
| `.github/workflows/release-shared-lib.yml` | `build-ios` ジョブ (L123-206) | `strategy.matrix.slice` で 2 分割。各 slice で sysroot/archs/SDK 切替、tar.gz 生成は既存形式 (M1 互換) を device slice のみで継続、両 slice の `.a`+headers を slice 別 artifact として upload | +60〜80 |
| `.github/workflows/release-shared-lib.yml` | (新規) `assemble-xcframework` ジョブ | 両 slice artifact を `actions/download-artifact@v8` で取得、`xcodebuild -create-xcframework` で統合、`zip -ry` で zip 化 | +50〜70 |
| `.github/workflows/release-shared-lib.yml` | `release.needs:` (L293) | `[build-shared, build-ios, build-android]` に `assemble-xcframework` を追加 | +1 |
| `.github/workflows/release-shared-lib.yml` | `release` ジョブの `Rename mobile artifacts with version` (L302-315) | xcframework.zip 命名のリネーム処理を追加 | +5〜10 |
| `cmake/ios.toolchain.cmake` | 全体 (現状 26 行) | `CMAKE_OSX_SYSROOT` を CLI 引数で受け取れるようにし、ハードコードを除去。`CMAKE_OSX_ARCHITECTURES` のキャッシュ初期値も "arm64" 固定から CLI 上書き可能形に修正。`IOS TRUE` のセットは維持 | +10 / -3 |
| `cmake/PiperPlusShared.cmake` | iOS 分岐 (L72-80) | simulator slice (universal binary) でも `${ONNXRUNTIME_LIB}` (dylib path) リンクが通ることを確認。原則として大きな変更なし、必要なら `target_link_libraries` の framework 探索パス追加 | 0〜+5 |

### 3.2 ORT framework を piper-plus xcframework に**含めるかどうか**の決定

xcframework の構造上、ORT framework を含めるかは設計選択である。以下 3 案を比較し、**案 A (含めない、利用者が ORT も別途取得)** を採用する。

| 案 | 概要 | xcframework 内容 | 利用者の作業 | サイズ | 採否 |
|----|------|---------------|------------|-------|-----|
| **A. 含めない** (sherpa-onnx 方式) | piper-plus xcframework は piper-plus 単体、ORT は別途取得 | `piper_plus.xcframework/<slice>/libpiper_plus.a` + `<slice>/Headers/piper_plus.h` + ルート `Info.plist` のみ (`.framework` バンドルは生成しない、`-library` 引数で static archive を直接統合) | piper-plus xcframework + ORT xcframework を **両方** Embed | ~6MB (libpiper_plus.a x2 slice) | **✓ 採用** |
| B. 含める (同梱) | xcframework 内に ORT framework も同梱 | `piper_plus.xcframework/<slice>/piper_plus.framework` + `<slice>/onnxruntime.framework` | piper-plus xcframework 1 つだけ Embed で完結 | ~140MB (両 slice の libpiper_plus + ORT 重複) | × 不採用 |
| C. ORT を統合再リンク | ORT を `libpiper_plus.a` に static link して 1 framework 化 | `piper_plus.framework` 内に ORT シンボル吸収 | piper-plus xcframework 1 つだけ Embed | ~70MB (slice あたり ORT 30MB + α) | × 不採用 |

**案 A 採用の根拠:**

1. **xcframework 仕様の素直さ**: `xcodebuild -create-xcframework` の `-library` / `-framework` 引数は単一バイナリを slice ごとに統合する設計。ORT framework を内包するには Apple 非公式の二重ネスト構造を作る必要があり、Xcode の Embed & Sign が機能しない可能性が高い (sherpa-onnx も明示的に避けている)
2. **配布サイズ**: 案 B はビルドジョブ artifact の二重コピー (M1 の tar.gz ですでに ORT を同梱しているため計三重) で zip 命名が膨らむ。GitHub Releases の 2GB/file 制限内に収まるとは言え、利用者の DL 帯域を恒常的に浪費
3. **ORT バージョン整合性**: 案 B は piper-plus 側で ORT バージョンを暗黙ロックする形になり、利用者が別バージョンの ORT を選びたいケース (例: CoreML EP 込みの custom build) で衝突する
4. **業界事例**: sherpa-onnx (k2-fsa)、whisper.cpp (ggml-org) 共に「自モジュールの xcframework は単体配布、依存フレームワークは利用者責任」が基本姿勢
5. **案 C の不採用理由**: ORT を ar archive 化して `libpiper_plus.a` と再リンクするには ORT を最初から static build しておく必要があり、現行 CDN zip では実現不可 (M1 §11.4 の通り Microsoft は dylib のみ提供)

**M3 への影響:** 案 A 採用により、利用者は **piper-plus xcframework** + **onnxruntime xcframework** の **2 つを Embed & Sign に追加する**必要がある。M3 利用者ガイドにはこの点を明記する責務がある。

### 3.3 YAML 差分の概念図

**Before (M1 完了状態、`build-ios` は単一 device slice ジョブ):**

```yaml
build-ios:
  name: Build iOS arm64
  runs-on: macos-14
  steps:
    - uses: actions/checkout@v6
    - name: Download ONNX Runtime iOS (Microsoft CDN)   # M1 で確立
    - name: Configure CMake (iOS)                         # device only
    - name: Build (iOS)
    - name: Package (tar.gz)
    - name: Upload artifact (libpiper_plus-ios-arm64)
```

**After (M2、matrix 化 + assemble-xcframework 追加):**

```yaml
build-ios:
  name: Build iOS ${{ matrix.slice }}
  runs-on: macos-14
  timeout-minutes: 30
  strategy:
    fail-fast: false
    matrix:
      include:
        - slice: ios-arm64
          osx_archs: "arm64"
          sdk: iphoneos
        - slice: ios-arm64_x86_64-simulator
          osx_archs: "arm64;x86_64"
          sdk: iphonesimulator
  steps:
    - uses: actions/checkout@v6
    - name: Validate version tag
    - name: Download ONNX Runtime iOS (Microsoft CDN)
      # M1 で確立した curl + sha256 検証ロジック流用
      # extraction の slice path を ${{ matrix.slice }} に切替
      run: |
        # ... (M1 の curl + sha256 検証はそのまま) ...
        IOS_SLICE="${ORT_FW_ROOT}/${{ matrix.slice }}"
        ORT_FW_DIR="${IOS_SLICE}/onnxruntime.framework"
        # ...
    - name: Configure CMake (iOS slice)
      run: |
        cmake -B build-ios \
          -DCMAKE_TOOLCHAIN_FILE=cmake/ios.toolchain.cmake \
          -DCMAKE_OSX_SYSROOT=${{ matrix.sdk }} \
          -DCMAKE_OSX_ARCHITECTURES="${{ matrix.osx_archs }}" \
          -DCMAKE_OSX_DEPLOYMENT_TARGET=15.0 \
          -DPIPER_PLUS_BUILD_SHARED=ON \
          -DBUILD_SHARED_LIBS=OFF \
          -DONNXRUNTIME_DIR="${ORT_IOS_DIR}" \
          -DONNXRUNTIME_LIB="${ORT_IOS_LIB}" \
          -DONNXRUNTIME_INCLUDE_DIR="${ORT_IOS_DIR}/include"
    - name: Build (iOS slice)
      run: cmake --build build-ios --config Release -j$(sysctl -n hw.ncpu)
    - name: Verify slice arch
      run: |
        lipo -info build-ios/libpiper_plus.a
        # device: arm64 / simulator: arm64 x86_64
    - name: Package slice (raw .a + headers for xcframework assembly)
      run: |
        mkdir -p slice-out/lib slice-out/include
        cp build-ios/libpiper_plus.a slice-out/lib/
        cp src/cpp/piper_plus.h slice-out/include/
        # 旧 tar.gz は device slice のみ生成 (M1 互換)
        if [ "${{ matrix.slice }}" = "ios-arm64" ]; then
          mkdir -p artifacts/lib artifacts/include
          cp build-ios/libpiper_plus.a artifacts/lib/
          cp src/cpp/piper_plus.h artifacts/include/
          cp -R "${ORT_IOS_FRAMEWORK}" artifacts/lib/
          cd artifacts && tar -czf "${{ github.workspace }}/libpiper_plus-ios-arm64.tar.gz" .
        fi
    - name: Upload slice artifact (for xcframework)
      uses: actions/upload-artifact@v7
      with:
        name: piper-plus-slice-${{ matrix.slice }}
        path: slice-out
    - name: Upload tar.gz (M1-compat, device slice only)
      if: matrix.slice == 'ios-arm64'
      uses: actions/upload-artifact@v7
      with:
        name: libpiper_plus-ios-arm64
        path: libpiper_plus-ios-arm64.tar.gz

assemble-xcframework:
  name: Assemble piper_plus.xcframework
  needs: build-ios
  runs-on: macos-14
  timeout-minutes: 15
  steps:
    - uses: actions/checkout@v6
    - name: Download device slice
      uses: actions/download-artifact@v8
      with:
        name: piper-plus-slice-ios-arm64
        path: slices/ios-arm64
    - name: Download simulator slice
      uses: actions/download-artifact@v8
      with:
        name: piper-plus-slice-ios-arm64_x86_64-simulator
        path: slices/ios-arm64_x86_64-simulator
    - name: Create xcframework
      run: |
        set -euo pipefail
        xcodebuild -create-xcframework \
          -library slices/ios-arm64/lib/libpiper_plus.a \
          -headers slices/ios-arm64/include \
          -library slices/ios-arm64_x86_64-simulator/lib/libpiper_plus.a \
          -headers slices/ios-arm64_x86_64-simulator/include \
          -output piper_plus.xcframework

        if [ ! -f piper_plus.xcframework/Info.plist ]; then
          echo "::error::xcframework Info.plist not found"
          exit 1
        fi
        ls -la piper_plus.xcframework/
        find piper_plus.xcframework -name "libpiper_plus.a" -exec lipo -info {} \;
    - name: Zip xcframework
      run: |
        zip -ry libpiper_plus-ios.xcframework.zip piper_plus.xcframework
        shasum -a 256 libpiper_plus-ios.xcframework.zip
    - name: Upload xcframework artifact
      uses: actions/upload-artifact@v7
      with:
        name: libpiper_plus-ios-xcframework
        path: libpiper_plus-ios.xcframework.zip

release:
  name: Create Release
  needs: [build-shared, build-ios, build-android, assemble-xcframework]   # ← 追加
  if: startsWith(github.ref, 'refs/tags/')
  # ... (既存ロジック + xcframework.zip のリネーム追加)
```

### 3.4 `cmake/ios.toolchain.cmake` の simulator slice 対応

現状 (26 行) は `set(CMAKE_OSX_ARCHITECTURES arm64 CACHE STRING "iOS architecture")` で書かれており、**`FORCE` 修飾子はないため CLI 上書きは原理的に可能**。simulator slice では `iphonesimulator` SDK + universal arch (`arm64;x86_64`) が必要だが、toolchain 側の変更は最小限で済む。

**変更方針 (実質ゼロ行変更も視野):**

```cmake
# 現状 (cmake/ios.toolchain.cmake:11)
set(CMAKE_OSX_ARCHITECTURES arm64 CACHE STRING "iOS architecture")
# ↑ FORCE なしのため -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64" 明示渡しで上書き可能

# 推奨 (オプショナル、可読性向上のためのコメント追加のみ)
set(CMAKE_OSX_ARCHITECTURES arm64 CACHE STRING
  "iOS architecture (override via -DCMAKE_OSX_ARCHITECTURES, e.g. \"arm64;x86_64\" for simulator)")

# CMAKE_OSX_SYSROOT は CMake が CMAKE_SYSTEM_NAME=iOS から自動推定するが、
# simulator 利用時は明示指定が必要。CLI から -DCMAKE_OSX_SYSROOT=iphonesimulator を渡す規約。
```

**規約:** CI ジョブの `Configure CMake (iOS slice)` ステップで **`-DCMAKE_OSX_ARCHITECTURES` と `-DCMAKE_OSX_SYSROOT` を必ず明示渡し**する (matrix の `osx_archs` / `sdk` 値より供給)。toolchain 側はハードコード回避と既存のキャッシュ宣言で十分動く。

**追加: bitcode 抑制の維持** — Xcode 14+ で deprecated, Xcode 15 で完全削除。`-fembed-bitcode=off` フラグはそのまま維持。

### 3.5 `cmake/PiperPlusShared.cmake` の確認ポイント

iOS 分岐 (L72-80) は既に `${ONNXRUNTIME_LIB}` パス指定での explicit link になっており、device/simulator 両 slice で同一ロジックが通る想定。simulator slice の universal binary でも `target_link_libraries(piper_plus PRIVATE ${ONNXRUNTIME_LIB})` のみで `lipo` 統合済 dylib path を直接参照できる。**事前にローカル検証で確認**するが、原則として大きな変更は不要。

ただし `piper_plus` 自体は iOS では **STATIC archive としてビルド** される (`cmake/PiperPlusShared.cmake:9-13`)。そのため ORT への参照は `libpiper_plus.a` 内に **未解決外部シンボルとして残り、最終リンクは xcframework 消費側 (利用者アプリ) が行う構造**である。`target_link_libraries(... ${ONNXRUNTIME_LIB})` で CMake が拡張子から dylib と推論しビルドコマンドラインに乗せるが、static archive 生成自体は実シンボル解決を要求しない。M3 で利用者ガイドに ORT xcframework を別途取得・Embed する旨を記載する点と整合する。

### 3.6 触らないファイル (M2 スコープ外)

- `examples/dart/README.md`, `examples/godot/README.md`, `examples/swift/README.md` (M3 で利用者ガイドとして一括更新、`Embed & Sign Frameworks` 手順含む)
- `docs/spec/ort-versions.md` (M3 で更新)
- `CHANGELOG.md` (M3 で v1.13.0 エントリ追加、tar.gz 廃止予告含む)
- `docs/spec/ios-shared-lib.md` 冒頭 Status (M3 で更新)
- module map (`module.modulemap`) — Swift `import` 用、M4 (SPM) で対応
- Privacy Manifest (`PrivacyInfo.xcprivacy`) — 利用者側で追加責務、M3 で言及

---

## 4. 担当者と Agent 並列レビュー観点

> **実行体制:** 本タスクは Claude Code が単独で実装・検証・コミットを行う。レビューは Agent ツール (subagent) で複数観点を並列起動して補強する。「人数」表記は廃止。

| 観点 (subagent role) | 数 | 主担当 | 責務 |
|---------------------|----|------|------|
| **実装** | - | Claude Code (主) | matrix 化、`assemble-xcframework` 新規ジョブ、modulemap/PrivacyInfo 生成ロジック、`xcodebuild -create-xcframework`、`workflow_dispatch` 起動、PR 起票、commit |
| **CMake / iOS 技術レビュー** | 1 観点 | Agent (general-purpose) | toolchain の sysroot/archs パラメータ化、PiperPlusShared.cmake の simulator slice 対応、Info.plist 妥当性、xcodebuild の `-library` 引数妥当性 |
| **整合性レビュー** | 1 観点 | Agent (general-purpose) | 仕様書 §8 M2 ↔ 本チケット ↔ workflow YAML の整合 (slice 命名 / artifact 命名 / sha256 / Embed & Sign 表記) |
| **構造 / DoD レビュー** | 1 観点 | Agent (general-purpose) | M1 tar.gz との並行配布の利用者影響、modulemap/PrivacyInfo 繰り上げ判断の反映、rollback 手順 |

実装後 `Agent` ツールで 2-3 観点を並列起動。matrix 化と xcframework は iOS 固有知識領域のため CMake / iOS 技術レビューは必須観点。重大指摘なしで `gh pr merge --auto`。

---

## 5. 提供範囲

### Included (M2 で扱う)

- `.github/workflows/release-shared-lib.yml` の `build-ios` ジョブを `matrix.slice` で 2 分割 (device / simulator)
- 新規 `assemble-xcframework` ジョブ追加 (`needs: build-ios`)
  - 両 slice artifact ダウンロード
  - `xcodebuild -create-xcframework` で統合
  - `libpiper_plus-ios-${VERSION}.xcframework.zip` 生成・upload
- `release.needs:` への `assemble-xcframework` 追加と新 artifact のリネーム/Releases 添付
- `cmake/ios.toolchain.cmake` の sysroot/archs パラメータ化 (最小変更)
- `cmake/PiperPlusShared.cmake` の両 slice 動作確認 (必要に応じた最小修正)
- M1 形式 `libpiper_plus-ios-arm64-${VERSION}.tar.gz` の **継続配布** (v1.13.0 移行期間)
- ORT framework を xcframework に含めない方針 (案 A) の確定

### Excluded (本 M2 では扱わない)

| 範囲 | 担当マイルストーン |
|------|------------------|
| `examples/dart/README.md` 等の利用者ガイド (`Embed & Sign Frameworks` 手順、ORT xcframework との二重 Embed 案内) | **M3** |
| `docs/spec/ort-versions.md` の iOS 行更新 | **M3** |
| `CHANGELOG.md` v1.13.0 エントリ追加 + tar.gz v1.14.0 廃止予告 | **M3** |
| 本書 `docs/spec/ios-shared-lib.md` 冒頭 Status の更新 | **M3** |
| module map (`module.modulemap`) 自動生成 | **M4** |
| Privacy Manifest (`PrivacyInfo.xcprivacy`) 同梱 | **M3 で言及、実装は将来別 issue** |
| `.dSYM` の同梱 | **M3 で要否判断** |
| Swift Package Manager 連動 repo | **M4** (別 issue) |
| csukuangfj/onnxruntime-libs ミラーへのフォールバック | **将来 (M2 後の運用課題)** |
| visionOS / Mac Catalyst slice 追加 | **将来 M5 候補 (§11.7 検討)** |

---

## 6. テスト項目

| # | 観点 | 期待結果 |
|---|------|---------|
| T1 | `workflow_dispatch` で `build-ios (slice: ios-arm64)` 単独実行 | PASS。`build-ios/libpiper_plus.a` が生成、`lipo -info` で `arm64` |
| T2 | `workflow_dispatch` で `build-ios (slice: ios-arm64_x86_64-simulator)` 単独実行 | PASS。`build-ios/libpiper_plus.a` が universal、`lipo -info` で `arm64 x86_64` |
| T3 | `assemble-xcframework` ジョブが両 slice 統合で PASS | `piper_plus.xcframework/` が生成、`Info.plist` に `AvailableLibraries` 2 entry を含む |
| T4 | xcframework 内の slice 命名 | `ios-arm64/` と `ios-arm64_x86_64-simulator/` の 2 ディレクトリ存在 (Apple 標準命名) |
| T5 | `lipo -info` arch 一致 | device slice = `arm64`、simulator slice = `arm64 x86_64` |
| T6 | Apple Silicon Mac での simulator 実機ロード | `xcrun simctl spawn booted` で simulator slice の `libpiper_plus.a` を組み込んだ test バイナリが起動成功 (手動 E2E) |
| T7 | tag push (`v1.13.0-rc1`) で xcframework.zip が Releases にアップロード | `libpiper_plus-ios-v1.13.0-rc1.xcframework.zip` が GitHub Releases ページに表示 |
| T8 | M1 互換 tar.gz の継続配布 | `libpiper_plus-ios-arm64-v1.13.0-rc1.tar.gz` が **同時に** Releases に存在 (破壊なし) |
| T9 | `checksums-sha256.txt` への記載 | xcframework.zip と tar.gz **両方の sha256** が含まれる |
| T10 | 非 iOS ジョブ非破壊 | `build-shared` (Linux/macOS/Windows)、`build-android` のステップ数・実行時間が現行 ±5% 以内 |
| T11 | matrix の `fail-fast: false` 動作 | device 単独で fail しても simulator は最後まで走る (デバッグ容易性) |
| T12 | xcframework.zip サイズ | ~6〜10MB (ORT framework 非同梱、案 A 採用のため軽量) |

---

## 7. Unit テストの内容

YAML / CMake / bash パッチに対する従来型 unit テストは限定的だが、以下のローカル静的検査を CI Engineer / CMake Engineer がローカル実行する:

| ツール | 対象 | コマンド例 | 期待結果 |
|-------|------|----------|---------|
| `yamllint` | `.github/workflows/release-shared-lib.yml` | `yamllint .github/workflows/release-shared-lib.yml` | PASS (構文エラーなし) |
| `actionlint` | matrix.include の構文、`needs:` の妥当性、新規ジョブ ID 重複なし | `actionlint .github/workflows/release-shared-lib.yml` | PASS |
| `shellcheck` | run ブロック内 bash (xcodebuild コマンド含む) | `shellcheck -s bash <抽出 run>` | quote 漏れ・unbound variable なし |
| `cmake --trace-expand` | `cmake/ios.toolchain.cmake` のキャッシュ展開 | `cmake -B trace-build -DCMAKE_TOOLCHAIN_FILE=cmake/ios.toolchain.cmake -DCMAKE_OSX_SYSROOT=iphonesimulator -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64" --trace-expand 2>&1 \| grep -E '(SYSROOT\|ARCHITECTURES)'` | sysroot=iphonesimulator、archs="arm64;x86_64" が正しく展開 |
| `xcodebuild -version` | runner 環境の Xcode バージョン記録 | `xcodebuild -version` | Xcode 15.x または 16.x、ログに記録 |
| `xcodebuild -create-xcframework -help` | xcodebuild の `-library`/`-headers` 引数仕様確認 | `xcodebuild -create-xcframework -help` | `-library`/`-headers` 受理、`-framework` 不要であることを確認 |

> **注:** `act` (nektos/act) は macos runner を完全エミュレートできない。`act --list -W .github/workflows/release-shared-lib.yml` で構文確認のみ。実機検証は `workflow_dispatch` (E2E §8) で行う。

---

## 8. E2E テストの内容

### 8.1 ローカル CMake 連携検証 (PR 起票前、必須)

macOS で両 slice をローカルビルドし、`xcodebuild -create-xcframework` まで通すことを確認:

```bash
# device slice
cmake -B build-ios-device \
  -DCMAKE_TOOLCHAIN_FILE=cmake/ios.toolchain.cmake \
  -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=15.0 \
  -DPIPER_PLUS_BUILD_SHARED=ON \
  -DBUILD_SHARED_LIBS=OFF \
  -DONNXRUNTIME_DIR="$(pwd)/ort-ios" \
  -DONNXRUNTIME_LIB="$(pwd)/ort-ios/lib/libonnxruntime.dylib" \
  -DONNXRUNTIME_INCLUDE_DIR="$(pwd)/ort-ios/include"
cmake --build build-ios-device --config Release
lipo -info build-ios-device/libpiper_plus.a   # 期待: arm64

# simulator slice
cmake -B build-ios-sim \
  -DCMAKE_TOOLCHAIN_FILE=cmake/ios.toolchain.cmake \
  -DCMAKE_OSX_SYSROOT=iphonesimulator \
  -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64" \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=15.0 \
  -DPIPER_PLUS_BUILD_SHARED=ON \
  -DBUILD_SHARED_LIBS=OFF \
  -DONNXRUNTIME_DIR="$(pwd)/ort-ios-sim" \
  -DONNXRUNTIME_LIB="$(pwd)/ort-ios-sim/lib/libonnxruntime.dylib" \
  -DONNXRUNTIME_INCLUDE_DIR="$(pwd)/ort-ios-sim/include"
cmake --build build-ios-sim --config Release
lipo -info build-ios-sim/libpiper_plus.a       # 期待: arm64 x86_64

# xcframework 統合
xcodebuild -create-xcframework \
  -library build-ios-device/libpiper_plus.a -headers src/cpp \
  -library build-ios-sim/libpiper_plus.a -headers src/cpp \
  -output piper_plus.xcframework
ls piper_plus.xcframework/
```

失敗時は M2 PR を取下げ、CMake 修正範囲を再評価。

### 8.2 `workflow_dispatch` での matrix 単独実行

```bash
gh workflow run release-shared-lib.yml --ref fix/ios-shared-lib-build-377
gh run watch
```

確認:
- `build-ios (slice: ios-arm64)` PASS
- `build-ios (slice: ios-arm64_x86_64-simulator)` PASS
- `assemble-xcframework` PASS
- `build-shared` x3 / `build-android` PASS
- Actions Artifacts に `piper-plus-slice-ios-arm64`, `piper-plus-slice-ios-arm64_x86_64-simulator`, `libpiper_plus-ios-xcframework`, `libpiper_plus-ios-arm64` の **4 つ**が表示

### 8.3 仮想 tag push による release ジョブ完走 (drypath)

```bash
git tag v1.13.0-rc1
git push origin v1.13.0-rc1
gh run watch
```

確認:
- 全ジョブ (5 + assemble-xcframework = 6 ジョブ) PASS
- `release` ジョブが起動し PASS
- GitHub Releases ページに以下が並ぶ:
  - `piper-plus-shared-{linux-x64,macos-arm64,windows-x64}.{tar.gz,zip}`
  - `libpiper_plus-ios-arm64-v1.13.0-rc1.tar.gz` (M1 互換)
  - **`libpiper_plus-ios-v1.13.0-rc1.xcframework.zip` (M2 新規)**
  - `libpiper_plus-android-arm64-v8a-v1.13.0-rc1.tar.gz`
  - `checksums-sha256.txt` (両 iOS artifact の sha256 含む)

### 8.4 xcframework のローカル展開と Xcode への drag-drop 動作確認 (手動 E2E)

iOS Build Engineer または QA Engineer が手動で:

```bash
gh release download v1.13.0-rc1 -p '*.xcframework.zip'
unzip libpiper_plus-ios-v1.13.0-rc1.xcframework.zip
ls piper_plus.xcframework/
# 期待: Info.plist, ios-arm64/, ios-arm64_x86_64-simulator/

# Info.plist 確認
plutil -p piper_plus.xcframework/Info.plist
# 期待: AvailableLibraries に 2 entry (LibraryIdentifier: ios-arm64, ios-arm64_x86_64-simulator)

# 各 slice arch
find piper_plus.xcframework -name "libpiper_plus.a" -exec lipo -info {} \;
# 期待:
#   ios-arm64/libpiper_plus.a: arm64
#   ios-arm64_x86_64-simulator/libpiper_plus.a: arm64 x86_64
```

Xcode 操作 (手動、サンプルプロジェクトに drag-drop):
1. 空の iOS App プロジェクトを作成
2. Project Navigator に `piper_plus.xcframework` をドラッグ
3. "Embed & Sign" を選択
4. Build Settings で device target を arm64、simulator target を arm64 (Apple Silicon) または x86_64 (Intel) に設定
5. Build PASS
6. iPhone simulator で起動成功

### 8.5 シミュレータでの実機ロード (`xcrun simctl`)

```bash
# Apple Silicon Mac で
xcrun simctl boot "iPhone 15"
xcrun simctl spawn booted /path/to/test-binary    # libpiper_plus を組込んだ test バイナリ
# 期待: dyld error なし、piper_plus_create() などの C API 呼出が成功
```

### 8.6 失敗時の roll back 手順

- 仮想 tag を削除: `gh release delete v1.13.0-rc1 --yes && git push --delete origin v1.13.0-rc1`
- ブランチを `dev` HEAD または M1 完了 commit に戻す: `git reset --hard <commit>` (ローカルのみ)

---

## 9. 懸念事項

| # | 懸念 | 確度 | 対応方針 |
|---|------|------|---------|
| C1 | simulator slice ビルド時間が device slice より長い (universal binary、x86_64 込み) | 中 | 観測ベース。`timeout-minutes: 30` は十分マージン。matrix 並列実行で walltime は最遅 slice 律速だが、絶対時間は両方とも ~10〜15 分想定 |
| C2 | `xcodebuild -create-xcframework` の Xcode バージョン互換性 (15.x / 16.x で仕様差) | 中 | `macos-14` runner の Xcode を `xcodebuild -version` でログ記録、major 変更時に M2 フォローアップを別 issue。`-headers` ディレクトリ指定の挙動が Xcode 16 で微変更されている事例あり |
| C3 | module map (`module.modulemap`) を M2 で含めるか M4 で対応か | 低 | **M4 で対応**と確定。M2 では Swift `import` 不要、Dart FFI / Godot は C ヘッダ直参照のみで十分。M3 利用者ガイドにも `module map なし` を明記 |
| C4 | Privacy Manifest (`PrivacyInfo.xcprivacy`) の同梱要否 | 中 | iOS 17+ で必須だが、ORT/piper-plus は **API 直接呼出に該当する Required Reasons API がない** 想定。M3 で要否を確定し、必要なら別 issue で同梱 |
| C5 | `.dSYM` の生成・同梱 | 低 | static archive (`.a`) では `.dSYM` は通常生成されないが、Apple は xcframework に `dSYMs/` 同梱を推奨。M3 で要否判断、現時点では同梱しない方針 |
| C6 | ORT framework を piper-plus xcframework に同梱しない (案 A) ことで利用者が「2 つ Embed しないと動かない」混乱を起こす可能性 | 高 | **M3 利用者ガイドで明確化** が必須。tar.gz は ORT 同梱、xcframework.zip は ORT 別 = **配布物ごとに作法が違う**点が分かりにくい。M3 で配布物比較表を提供 |
| C7 | 既存 `cmake/PiperPlusShared.cmake` で simulator slice 対応漏れの可能性 | 中 | §8.1 ローカル検証で確定。`target_link_libraries` の dylib 直リンクが simulator universal で通らない場合、framework 探索パス追加 (`-F` フラグ) が必要 |
| C8 | matrix 並列で同一 ORT zip を 2 回 DL する非効率 | 低 | 1 回 ~40MB × 2 = 80MB の通信、ジョブごと数秒の追加時間。matrix の利点 (失敗 slice 単独再実行) と引換えで許容。`actions/cache@v4` での共有は M2 では実装せず、必要なら将来別 issue |

---

## 10. レビュー項目

レビュアー (Workflow Reviewer + iOS Distribution Reviewer + CMake Engineer) は以下のチェックリストを順に確認する。

### 10.1 matrix 設計の網羅性

- [ ] `matrix.include` に `slice`, `osx_archs`, `sdk` の 3 キーが含まれる
- [ ] `slice` 名が Apple xcframework 標準命名 (`ios-arm64`, `ios-arm64_x86_64-simulator`) と一致
- [ ] `fail-fast: false` で片方失敗時にもう一方が走る (デバッグ容易性)
- [ ] device-only `tar.gz` 生成は `matrix.slice == 'ios-arm64'` 条件で限定 (重複回避)

### 10.2 `assemble-xcframework` ジョブの artifact ダウンロード・統合ロジック

- [ ] `needs: build-ios` で matrix 全 slice 完了を待つ
- [ ] `actions/download-artifact@v8` で両 slice を別ディレクトリに展開
- [ ] `xcodebuild -create-xcframework` の `-library` / `-headers` ペアが正しく対になっている
- [ ] xcframework Info.plist が生成された後の存在確認 (fail-stop) がある
- [ ] `lipo -info` で両 slice の arch が表示される (CI ログ可観測性)
- [ ] zip は `zip -ry` で symlink 保持 (Apple framework は symlink を含むためただの `zip` ではダメ)

### 10.3 `cmake/ios.toolchain.cmake` の最小変更原則

- [ ] `CMAKE_OSX_ARCHITECTURES` の現状 `CACHE STRING` 宣言 (FORCE なし) を維持し、CI ジョブから `-DCMAKE_OSX_ARCHITECTURES=...` を明示渡しする規約が `Configure CMake (iOS slice)` ステップで実装されている
- [ ] `CMAKE_OSX_SYSROOT` をハードコードしていない (CLI から `-DCMAKE_OSX_SYSROOT=iphonesimulator` を渡す)
- [ ] bitcode 抑制 (`-fembed-bitcode=off`) は維持
- [ ] `IOS TRUE` キャッシュ変数は維持 (consumer 側で利用されている可能性)
- [ ] 変更行数が 5 行以内 (実質ゼロ〜コメント追加のみ)

### 10.4 既存 tar.gz artifact 破壊回避

- [ ] `libpiper_plus-ios-arm64.tar.gz` 生成ステップが device slice (`matrix.slice == 'ios-arm64'`) のみで動く
- [ ] tar.gz の中身が M1 と一致 (`lib/libpiper_plus.a`, `lib/onnxruntime.framework/`, `include/piper_plus.h`)
- [ ] `release` ジョブの `Rename mobile artifacts with version` が tar.gz と xcframework.zip の **両方**をリネーム
- [ ] `softprops/action-gh-release` の `files:` パターンに xcframework.zip が含まれる

### 10.5 xcframework Info.plist の妥当性

- [ ] `plutil -p piper_plus.xcframework/Info.plist` の出力で `AvailableLibraries` が 2 entry
- [ ] 各 entry の `LibraryIdentifier` が slice ディレクトリ名と一致 (`ios-arm64`, `ios-arm64_x86_64-simulator`)
- [ ] `SupportedArchitectures` が device は `[arm64]`、simulator は `[arm64, x86_64]`
- [ ] `SupportedPlatform` が `ios`、simulator slice の `SupportedPlatformVariant` が `simulator`

### 10.6 ORT 同梱方針 (案 A) の妥当性

- [ ] xcframework.zip の中身に ORT framework が **含まれていない**
- [ ] M3 利用者ガイドへの引き継ぎ事項 (§12.2) に「利用者は ORT xcframework も別途 Embed」が明記されている
- [ ] tar.gz と xcframework.zip で ORT 同梱方針が異なる旨が PR 本文で明示

### 10.7 非 iOS ジョブ非破壊

- [ ] `build-shared` (linux-x64/macos-arm64/windows-x64) に diff なし
- [ ] `build-android` に diff なし
- [ ] `release` ジョブの `needs:` 配列以外に変更なし、`if: startsWith(github.ref, 'refs/tags/')` 維持
- [ ] `permissions: contents: write` が維持されている

### 10.8 観測性

- [ ] `xcodebuild -version` がログに出力される (Xcode バージョン追跡)
- [ ] `lipo -info` 出力が両 slice ともログに残る
- [ ] xcframework Info.plist の不在時に `::error::` で fail-stop
- [ ] zip 化後の sha256 がログ出力される

### 10.9 PR サイズの最小性

- [ ] diff が ~150〜200 行以内に収まる
- [ ] 触らないファイル (M2 スコープ外、§3.6) に diff がない
- [ ] `examples/`, `docs/` (M3 担当) に diff がない

### 10.10 artifact actions バージョン整合性

- [ ] `actions/upload-artifact@v7` で生成した slice artifact が `actions/download-artifact@v8` で取得できることを `workflow_dispatch` の dry-run で実際に確認
- [ ] バージョン非対称 (v7 upload / v8 download) で artifact 形式互換が崩れていないか PR テストログで明示
- [ ] 既存ジョブ (build-shared / build-android) も同一バージョンペアを使うため、M2 で破壊した場合 release ジョブが連鎖死する点を意識

### 10.11 マージ条件

- [ ] M1 PR がマージ済み (依存関係) であることを確認
- [ ] `workflow_dispatch` での全 matrix PASS スクリーンショットが PR 本文に記載
- [ ] 仮想 tag (`v1.13.0-rc1`) の dry-run ログ URL が PR 本文に記載

---

## 11. 一から作り直すとしたら

> 本セクションは「実装する PR スコープ」ではなく、**シニアアーキテクト視点での反省的検討**である。M2 (matrix slice + `xcodebuild -create-xcframework` で device + simulator slice 統合) は M1 で確立した CDN 取得経路を流用しつつ「最小侵襲で実用形態に到達する」現実解だが、**その選択を批判的に評価し、白紙からなら何を選ぶか** を記録する。M1 §11 と同様、**観測手段がないため iOS 利用者数は実数不明** という認識を引き継ぐ。

---

### 11.1 そもそも何を作るべきか

M2 が前提とする「device + simulator の 2 slice xcframework」は、**xcframework が解決できる問題空間のごく一部しか使っていない**。xcframework は本来、Apple の 6 プラットフォーム (iOS / macOS / Mac Catalyst / visionOS / tvOS / watchOS) と device/simulator のすべての組み合わせを **単一 zip で配布する** ためのコンテナである。M2 の 2 slice 構成は、その表現力のうち約 17% (2/12 想定 slice) しか利用しない。

白紙設計の問いは「**iOS 利用者は何を欲しいのか**」ではなく「**Apple ecosystem 利用者は何を欲しいのか**」に書き換わる:

| 利用者層 | 欲しい slice 構成 | 観測根拠 |
|---------|----------------|---------|
| Flutter/Dart FFI | iOS device + iOS simulator (Apple Silicon Mac で開発) | `flutter_onnxruntime` が同構成 |
| SwiftUI ネイティブアプリ | iOS device + iOS simulator + macOS arm64 (Mac App 共有コード) | sherpa-onnx の swift サンプルが同構成 |
| visionOS | xrOS-arm64 + xrOS-arm64-simulator | ORT 公式未対応のため **2026-05 時点で実装不可** |
| Mac Catalyst | maccatalyst-arm64_x86_64 | ORT サポートに穴あり (xnnpack 一部不可) |

つまり「2 slice」は **Flutter 用途ピンポイント最適化** であり、SwiftUI 派生需要を取りこぼす。**白紙なら最低 3 slice (iOS device / iOS simulator / macOS universal)** が起点になる。

さらに重要な根本判断:

| 論点 | M2 の暗黙前提 | 白紙設計の問い直し |
|------|-------------|----------------|
| ORT を **piper-plus.xcframework に同梱** するか **別配布** するか | M2 は §3.2 で案 A (含めない) を採用 | 同左 (sherpa-onnx 業界事例と整合)、ただし利用者ガイドで配布物比較を必須に |
| **module map** を xcframework に組み込むか | 組み込まない (Swift 利用者が import 不可) | M4 で必要なら最初から入れるべき |
| **Privacy Manifest** (`PrivacyInfo.xcprivacy`) を埋め込むか | 触れない | **iOS 17+ App Store 必須**。後付けは breaking change |
| **.dSYM** を別 artifact で出すか | 触れない | クラッシュ symbolication に必要、後付けは過去のリリース不可 |

M2 は「2 slice xcframework に到達した時点で実用形態」と暗黙に置いているが、**module map / Privacy Manifest / .dSYM の 3 つはどれか欠けると iOS 17+ 実機リリース時に追加対応が発生する**。最初からこの 3 つを内包する設計が白紙の正解。

### 11.2 代替アーキテクチャ案 (3 案)

#### 案 X: piper-plus.xcframework に ORT framework も同梱 (sherpa-onnx 部分採用)

`xcodebuild -create-xcframework` で piper-plus の static lib + ORT の Mach-O dylib を **1 つの xcframework に再パッケージ** する。利用者は `piper_plus.xcframework` 1 つを drag-and-drop すれば完結。

実装上のキモ: ORT の `onnxruntime.framework` (slice ごと) を piper-plus.xcframework の各 slice に **embed**。Mach-O `LC_RPATH` を `@executable_path/Frameworks` に設定し、利用者側の Embed & Sign で `Frameworks/onnxruntime.framework/onnxruntime` が解決されるよう調整する。

| 観点 | 評価 |
|------|------|
| **メリット** | (a) 利用者は xcframework 1 つで完結、混乱なし、(b) sherpa-onnx と同等 UX、(c) ORT バージョン整合性が xcframework 単位で保証される |
| **デメリット** | (a) ORT を piper-plus 以外でも使う利用者は **二重コピー** 発生 (アプリバイナリ +30〜70MB)、(b) NOTICE / LICENSE 同梱の責務、(c) ORT バージョン更新時に piper-plus も再リリース必要 (バージョン結合) |
| **採用条件 (定量)** | (1) 利用者の 80% 以上が ORT を **他用途で使わない単独利用**、(2) アプリ最終サイズの +30〜70MB が許容される (App Extension 不可になる、§11.5 参照) |

参考実装 (伝聞ベース、要再検証): sherpa-onnx は xcframework に ORT を内包しない別配布方式を採用しているとされる。SPM 統合時に複数 xcframework が必要な場合は `Package.swift` の `targets:` 配列に複数の `binaryTarget(name:url:checksum:)` 宣言を並べるのが Apple SPM 標準パターン。本判断材料は実プロジェクトのコードを直接参照せず推論で記述しているため、案 X 採用検討時は別途実装を確認すること。

#### 案 Y: piper-plus.xcframework は piper-plus のみ、ORT は利用者が別途取得 (sherpa-onnx 主流方式) — **M2 採用案**

piper-plus.xcframework には piper-plus の static lib + headers のみ。ORT は利用者が以下のいずれかで自前取得:

1. CocoaPods (`pod 'onnxruntime-c'`)
2. SPM (`https://github.com/microsoft/onnxruntime-swift-package-manager`)
3. CDN zip 直接展開 (M1 と同じ経路)

| 観点 | 評価 |
|------|------|
| **メリット** | (a) Microsoft 公式 SPM/CocoaPods と完全互換、(b) ORT バージョン更新が piper-plus 再リリース不要 (利用者側で独立更新)、(c) アプリで ORT を他用途共有時に二重コピーなし、(d) piper-plus 単体サイズが ~3MB に収まる |
| **デメリット** | (a) 利用者の組込み手順が 2 段階 (piper-plus + ORT 個別取得)、(b) ORT バージョン不整合リスクを利用者に転嫁、(c) サンプルコード/ドキュメントが複雑化 |
| **採用条件 (定量)** | (1) 利用者の 50% 以上が SwiftPM 慣れ、(2) ORT バージョン整合性チェックを CMake/ビルド時にエラー化できる仕組み (例: `onnxruntime_c_api.h` の `ORT_API_VERSION` マクロを piper-plus 側で要求バージョン以上 assert) |

参考実装: Microsoft 公式 `onnxruntime-swift-package-manager/Package.swift` は単一 `binaryTarget` 構造で、利用プロジェクトはこれを `dependencies` に追加するだけ。sherpa-onnx-spm も同パターンで ORT を `dependencies` 経由で取得し、自前 xcframework は ORT を含まない。

#### 案 Z: xcframework を SwiftPM Package.swift binaryTarget として最初から SPM 公開 (M2+M4 統合)

別 repo `ayousanz/piper-plus-swift-package-manager` を新設し、`Package.swift` の `binaryTarget(url:, checksum:)` で piper-plus Releases の xcframework.zip を参照。M2 で xcframework 化する **と同時に** SPM 公開する。

| 観点 | 評価 |
|------|------|
| **メリット** | (a) Apple ecosystem ネイティブの配布形式、(b) `import PiperPlus` が即座に動く、(c) Swift Package Index 経由で発見性が高い、(d) M4 を別工程化する必要がない |
| **デメリット** | (a) 別 repo メンテ (タグ同期、Package.swift 更新)、(b) 非 Swift 利用者 (Dart/Godot) にはオーバーヘッド、(c) SPM `binaryTarget` の checksum を毎リリース計算する自動化が必要 |
| **採用条件 (定量)** | (1) iOS 利用者の 60% 以上が Swift ネイティブ、(2) tag push 時に SPM repo へ自動 commit するワークフロー (~50 行 YAML) を許容、(3) 別 repo を 5 年単位で維持する意思 |

参考実装: whisper.cpp の `build-xcframework.sh` は xcframework 生成後に `swift package compute-checksum` を呼んで `Package.swift` を自動更新する。これと同等の仕組みを piper-plus に組込めば手動更新ゼロで運用可能。

### 11.3 配布形態の根本選択

| フォーマット | 提供物 | 利用者の組込み手順 | 評価 |
|------------|------|----------------|------|
| `.xcframework` (drag-and-drop) | xcframework.zip 単独 | Xcode に drag、Embed & Sign | M2 採用、最小実装 |
| **SwiftPM `binaryTarget`** | xcframework.zip + 別 repo の Package.swift | `dependencies` に URL 追加 | **Swift native 利用者の標準** |
| `.podspec` (CocoaPods) | xcframework.zip + Podfile.lock 互換の podspec | `pod install` | レガシープロジェクト互換 |
| 三つすべて (sherpa-onnx 方式) | xcframework + SPM repo + podspec | 利用者が選択 | メンテ負荷 3 倍、利用者裾野最大 |

**白紙設計なら xcframework + SwiftPM の 2 形態同時提供** が現実解。CocoaPods は 2024 年以降 Swift コミュニティで shrinking trend (Apple 公式は SPM 推進)、新規プロジェクトでの採用率は 30% 以下と推定される。

#### Module map の取り扱い

xcframework 内の `<slice>/Headers/module.modulemap` を **CMake で自動生成** すべき。M2 spec はこの点に触れていないが、欠けると Swift から `import PiperPlus` が動かない (C ヘッダ直 include で workaround は可能だが unidiomatic)。

```cmake
# cmake/PiperPlusShared.cmake に追加すべき
file(WRITE "${CMAKE_BINARY_DIR}/module.modulemap"
"framework module PiperPlus {
    umbrella header \"piper_plus.h\"
    export *
    module * { export * }
}")
```

#### Privacy Manifest

iOS 17+ で App Store Connect が `PrivacyInfo.xcprivacy` の埋込を **自動検証**。piper-plus は file system access (モデルファイル読込) と推論用メモリ確保のみで、現状は **Required Reason API は使わない見込み**。空の Privacy Manifest を最小実装として埋め込むべき:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>NSPrivacyTracking</key><false/>
    <key>NSPrivacyCollectedDataTypes</key><array/>
    <key>NSPrivacyAccessedAPITypes</key><array/>
</dict>
</plist>
```

**ただし ORT 側に Privacy Manifest が無い** (2026-05 時点) ため、利用者が両方追加する責務を負う。これは Microsoft 上流の問題で piper-plus 単独で解決不能。

#### .dSYM 同梱

クラッシュレポート symbolication には .dSYM が必須。**xcframework 内に同梱は不可** (Apple 仕様、xcframework は実行可能バイナリのみ)、別 artifact `libpiper_plus-ios-${VERSION}.xcframework.dSYM.zip` として配布が標準。

whisper.cpp は `build-xcframework.sh` で `dsymutil` を slice ごとに呼んで `.dSYM` を生成し、別 artifact として Releases にアップロードしている。M2 はこの工程を含んでいない。

### 11.4 CI 戦略 (ビルド時間 / マトリクス)

| 観点 | M2 の選択 | 白紙設計の選択 |
|------|----------|------------|
| **runner** | macos-14 単一 | macos-14 で開始、Xcode 16 安定後に macos-15 移行 |
| **matrix 並列度** | 2 slice (device + simulator) | 4 slice (iOS device / iOS sim / macOS / Mac Catalyst) |
| **assemble job** | 単一 `assemble-xcframework` | 同左 (slice 集約は単一 runner で十分) |
| **キャッシュ** | なし (ORT は毎回 CDN 取得) | `actions/cache@v4` で ORT zip を sha256 キーでキャッシュ |

#### macOS minutes コスト試算 (private repo 想定)

GitHub Actions macOS runner は public repo では無料、private repo では **$0.08/min × 10x multiplier = $0.80/min**:

| シナリオ | 時間 | コスト |
|---------|------|------|
| 現 M2 (2 slice 並列、各 ~10 分) | 2 × 10 min × $0.80 = $16 | PR ごと |
| 案 X (4 slice 並列、各 ~10 分 + assemble 5 分) | 4 × 10 + 5 = 45 min × $0.80 = **$36** | PR ごと |
| ORT ソースビルド統合 (案 X + キャッシュなし) | 4 × 35 + 5 = 145 min × $0.80 = **$116** | 初回 PR、キャッシュ後は $36 |

piper-plus が public repo であるため上記は将来 fork 用の参考値だが、**月 10 PR と仮定すると現 M2 で $160/月、4 slice 拡張で $360/月**。public repo の限り無料だが、組織 fork で private 運用される将来シナリオでは予算インパクトあり。

#### Xcode マイナーバージョン互換性

`xcodebuild -create-xcframework` は Xcode 11 (2019) 以降安定だが、**生成される xcframework の Info.plist 形式が Xcode マイナー更新で稀に変わる** (例: Xcode 15.0 → 15.3 で `LibraryIdentifier` の表記が変化)。

**白紙設計の選択:** runner image を `macos-14` (Xcode 15.x 系) でピン留め、`xcodebuild -version` を CI ログに出力、xcframework Info.plist を artifact に含めて diff チェック可能にする。

#### universal binary の lipo オーバーヘッド

simulator slice は arm64 + x86_64 universal で、`lipo -create` のオーバーヘッドは ~1 秒/MB。ORT の simulator slice は ~67MB なので **lipo に ~1 分かかる**。これは M2 では透過的だが、ビルド時間予算に計上すべき。

### 11.5 セキュリティ・利用者体験

| 観点 | M2 の選択 | 白紙設計の選択 |
|------|----------|------------|
| **xcframework codesign** | 不要 (利用者側で再署名) | 同左 (Apple 仕様、変えられない) |
| **Privacy Manifest** | 触れない | **必ず埋め込む** (空でも) |
| **.dSYM** | 触れない | 別 artifact として配布 |
| **ORT --minimal_build** | M5 まで先送り | 案 X 採用時のみ意味、現 M2 では不可 (公式バイナリ使用) |

#### Embed & Sign の利用者体験

Mach-O dylib (ORT framework) を含む xcframework は **必ず Embed & Sign Frameworks に追加** が必要。Xcode の "General" タブで操作するが、Flutter/Godot 利用者にはこの UI 慣れがなく **失敗率が高い** (sherpa-onnx の Issues で月 1〜2 件発生)。

**白紙設計の解:** `examples/dart/README.md` / `examples/godot/README.md` に **スクリーンショット付き手順** を必ず置く。M2 は M3 で扱う想定だが、xcframework 化と同時に提供しないと **利用者の最初の体験が壊れる**。

#### App Store / App Extension のサイズ制約

| 配布先 | サイズ上限 (uncompressed slice) | piper-plus + ORT 統合可否 |
|-------|------------------------------|----------------------|
| 通常 iOS アプリ | 4 GB | 可 (~35MB) |
| **App Extension** | **32 MB** | **不可** (ORT 単独で超過) |
| App Clip | 10 MB | **不可** |

App Extension で使うには ORT `--minimal_build` + piper-plus サブセット化が必要だが、M2 では対応外。これは **CONTRIBUTING に明記すべき制約**。

### 11.6 現 M2 (xcframework + ORT 同梱検討) とのギャップ

| 観点 | 白紙最適解 | 現 M2 | ギャップ評価 |
|------|----------|-------|------------|
| **slice 数** | 3〜4 (iOS device/sim/macOS/Catalyst) | 2 (iOS device/sim) | 中: M2+ で macOS slice 追加検討 |
| **ORT 同梱判断** | 案 Y (別配布) を明示採用 | §3.2 で案 A 採用済 (案 Y 相当) | 小: 整合 (ただし利用者ガイドが M3 任せの先送り) |
| **module map** | 自動生成 + SPM ready | なし | 大: M4 で必須、現時点で未着手 |
| **Privacy Manifest** | 空でも埋込 | 触れない | 中: iOS 17+ アプリ拒否リスク |
| **.dSYM** | 別 artifact 配布 | 触れない | 中: クラッシュ debug 時に過去版未対応 |
| **SPM 公開** | M2 と同時 | M4 で別工程 | 中: タグ同期に運用リスク |
| **CocoaPods** | 提供しない (SPM 集約) | 触れない | 小: 妥当 |

**現 M2 を選んだ正当化 (限定的):**

1. **M1 の取得経路が確立済み**: 同じ CDN zip を流用、再発明不要
2. **PR スコープを中規模 (~150 行) に保つ**: M4 統合すると 300 行超、レビュー困難
3. **観測上の利用者ゼロ**: Privacy Manifest 不在で拒否される実例が観測されない (まだ誰も使えていない)

**永遠に埋まらない技術的負債:**

- **ORT の Privacy Manifest 不在**: Microsoft 上流問題、piper-plus 単独で解決不能
- **xcframework の binary diff 不可**: 各リリースで full re-download、利用者の CI/CD でキャッシュ困難
- **iOS 利用者の実数不明**: M1 §11 から継承、配布形態最適化判断を実績ベースで下せない
- **Mac Catalyst / visionOS 拡張の決断先送り**: ORT 公式サポート次第、外部依存

### 11.7 もし今から始めるなら (推奨)

**著者個人の推奨: 案 Y + 案 Z 統合 (ORT 別配布の xcframework + 同時 SPM 公開)**

| 推奨度 | ★★★★☆ (4/5) |
|--------|-------------|

**5 段階の実装ステップ:**

1. **xcframework に ORT を同梱せず、piper-plus のみ** (~3MB、案 Y) ← M2 で既に採用
2. **module map / Privacy Manifest を最初から埋込** (.modulemap + .xcprivacy)
3. **`.dSYM` を別 artifact `libpiper_plus-ios-${VERSION}.dSYM.zip` で配布** (whisper.cpp 方式)
4. **同時に SPM repo `ayousanz/piper-plus-swift-package-manager` 公開** (M4 統合、案 Z)
5. **ORT は利用者に Microsoft 公式 SPM で取得を案内** (`onnxruntime-swift-package-manager` 依存)

**この推奨を採用しない合理的理由:**

1. **メンテ可処分時間が不足** (定量: 別 repo 同期に四半期 4 時間以上を割けない): SPM repo の自動化が崩壊し、案 X の単一 xcframework に retreat が誠実
2. **iOS 利用者の 80% 以上が Flutter** (定量: Dart FFI Issue 数 / Swift Issue 数 ≥ 4): SPM 公開の便益が薄い、案 X の Embed & Sign 案内特化が効率的
3. **CI macOS minutes が予算超過** (定量: $300/月超): 4 slice 拡張せず 2 slice 維持、案 Z 同時公開を後ろ倒し

**最終所感:**

現 M2 は **「M1 の継承 + xcodebuild の機械的適用」** で技術的に最短だが、**配布物の意味論的設計 (ORT 同梱判断は §3.2 で確定済、ただし module map、Privacy Manifest、.dSYM は全部先送り)** という負債を抱えたまま完了する。M2 を完了した瞬間、これらの設計負債は「動いている xcframework を壊さないように後付けする」コストに変わる。後付けは常に最初から組込むより 2〜3 倍高い。

具体的な行動推奨:

- **module map / Privacy Manifest を M2 スコープに繰り上げる** (~30 行 CMake 追加で済む、後付けより圧倒的に安い)
- **.dSYM 別 artifact 配布を M2 で開始する** (whisper.cpp の `dsymutil` パターン流用、~10 行追加)
- **M3 完了時点で iOS 利用者の実数把握 (download metrics、Issue 受信頻度) を行い、6 ヶ月以内に SPM 公開 (案 Z) の採用判断を下す**

M2 が「**xcframework に到達した**」で満足すると、利用者から見た piper-plus iOS は **「とりあえず動くが Apple ecosystem 流儀に外れた配布物」** で固定化される。M1 §11 の最終所感を引き継ぎ、**負債は時間で利息が増える**。M2 の 2 slice xcframework が「最低限のチェックボックス埋め」で 1 年放置されることが、最も避けたいシナリオである。

---

## 12. 後続タスクへの連絡事項

### 12.1 M3 (docs / 移行ガイド) への引き継ぎ

> 担当チケット: [`docs/tickets/377-M3-docs-migration.md`](377-M3-docs-migration.md)

M2 完了時点で確定する以下の事実を M3 のドキュメント反映に渡す:

- [ ] **`Embed & Sign Frameworks` 手順を利用者ガイドに記載必須**: piper-plus xcframework + ONNX Runtime xcframework の **2 つを Embed する**作業手順を `examples/dart/README.md` / `examples/godot/README.md` / (新規) `examples/swift/README.md` に追記
- [ ] **配布物の使い分けマトリクス**: 利用者向けに「tar.gz (M1 互換、ORT 同梱、device-only) vs xcframework.zip (M2 新規、ORT 別、device + simulator)」の選択ガイドを M3 で提供
- [ ] **CHANGELOG v1.13.0 エントリ**: 「iOS shared-lib を xcframework として配布開始 (Issue #377)」「`libpiper_plus-ios-arm64-${VERSION}.tar.gz` は v1.13.0 では継続配布、v1.14.0 で廃止予定」を明記
- [ ] **`docs/spec/ort-versions.md` の iOS 行更新**: `xcframework (Microsoft CDN: download.onnxruntime.ai)` 表記
- [ ] **本書 (`docs/spec/ios-shared-lib.md`) 冒頭 Status の更新**: `Proposed` → `M1+M2 完了 / M3 進行中`、最終的に `Implemented (v1.13.0)` へ
- [ ] **module map / Privacy Manifest / dSYM の取り扱い**:
  - module map: M4 (SPM) で必須、M2/M3 では未着手の旨を明記 (§11.7 の繰り上げ提案あり、PR レビューで再判断)
  - Privacy Manifest: ORT が公式提供しない場合、利用者側追加責務として M3 で言及
  - dSYM: M2 では同梱しない、シンボリケーション要望は別 issue として受付 (§11.7 の繰り上げ提案あり)
- [ ] **告知メッセージのドラフト**: Issue #377 への完了コメント、リリースノート文面、(任意) 関連プロジェクト (Flutter community, Godot Asset Library) への告知

### 12.2 M4 (SPM パッケージ併設) への引き継ぎ

> 担当チケット: [`docs/tickets/377-M4-spm-package.md`](377-M4-spm-package.md) (別 issue で管理予定)

M2 で xcframework.zip 配布が確立した前提で、M4 では:

- [ ] `xcframework.zip` を SPM `binaryTarget(url: ..., checksum: ...)` で参照可能にする
  - URL: `https://github.com/ayutaz/piper-plus/releases/download/${VERSION}/libpiper_plus-ios-${VERSION}.xcframework.zip`
  - checksum: M2 で `release` ジョブが生成する `checksums-sha256.txt` から取得
- [ ] **リリースごとに checksum を SPM repo の Package.swift に伝搬する仕組み**:
  - 案 1: piper-plus tag push を契機に `peter-evans/repository-dispatch` で別 repo (`ayousanz/piper-plus-swift-package-manager`) にトリガを送る
  - 案 2: 別 repo 側で `schedule:` cron で定期的に最新 release を polling
  - M4 で実装方式を確定
- [ ] **module map の自動生成**: SPM の `binaryTarget` は xcframework 内部の構造を尊重するため、M4 で xcframework 生成時に `module.modulemap` を `Headers/` 配下に追加する必要あり
  - M2 の `assemble-xcframework` ジョブに module map 生成ステップを後付けで追加する形になる可能性
- [ ] **Swift Package Index 登録**: SPM repo 公開後に [Swift Package Index](https://swiftpackageindex.com/) に登録、検索可能化

### 12.3 横断的な観測点

- **CI 実行時間**: M2 の `build-ios` matrix 化で walltime は最遅 slice 律速、絶対時間は両方 ~10〜15 分想定。`assemble-xcframework` は ~3〜5 分。M2 全体で iOS 関連 ~20 分 (M1 の単独 ~12 分から増加)
- **artifact 数の増加**: M1 で 5 個 → M2 で 7 個 (slice artifact x2、xcframework.zip x1 追加)。Actions Artifacts の保持期間 90 日には影響なし
- **GitHub Releases サイズ**: M2 後の v1.13.0 リリースで iOS 関連は tar.gz (~35MB) + xcframework.zip (~6〜10MB) = ~45MB。リリースあたり許容範囲内
- **csukuangfj/onnxruntime-libs ミラー**: M1 §9 C1 で温存した CDN 失効時のフォールバックは M2 でも実装せず。M2 完了後の運用課題として、CDN HEAD 200 監視を週次 cron で導入するかを別 issue で検討
- **iOS 利用者観測 (M1 §11.5 永遠負債の継承)**: M2 完了後、`download metrics` 取得・Issue 受信頻度・Discord 言及の集計を M3 以降で開始。6 ヶ月以内に M1 §11.9 で示された案 X (ORT ソースビルド) / 案 Z (iOS 廃止) の判断を下す

### 12.4 マージ後アクション

- [ ] `docs/tickets/README.md` 表の M2 行を `pending` → `done (PR #XXX, YYYY-MM-DD)` に更新
- [ ] `docs/spec/ios-shared-lib.md §8 M2` のチェックボックスを `[x] 完了` に更新
- [ ] M3 着手前に最低 1 回 `workflow_dispatch` で全 matrix + `assemble-xcframework` PASS を確認
- [ ] xcframework.zip を Apple Silicon Mac で実機検証 (drag-drop + simulator boot) し、結果を別途 Issue コメントに記録
- [ ] (任意) v1.12.x の hotfix リリースとして cherry-pick するかを別途判断 (現状 v1.13.0 投入予定)
- [ ] M1 §11.9 の「6 ヶ月以内に案 X か案 Z かを判断」リマインダーが M2 完了時点でも有効であることを再確認
- [ ] (M2 §11.7 の §11.7 提案) module map / Privacy Manifest / .dSYM の M2 繰り上げ案を採用する場合は別 PR で追加対応
