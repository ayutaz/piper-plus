# M4-4: Android NDK ビルド

> **Phase:** 4 -- 拡張 (将来)
> **見積り:** 大
> **依存:** Phase 3 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m4-4-android-ndk-ビルド)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

Android NDK ツールチェインで `libpiper_plus.so` (arm64-v8a) をクロスコンパイルし、Flutter/Kotlin/Java アプリから利用可能にする。ONNX Runtime Android 版 (AAR) との統合を含む。

**現状:** CMakeLists.txt は Linux x86_64/aarch64、macOS arm64、Windows x64 をサポートしているが、Android 向けのクロスコンパイルは未対応。ONNX Runtime の取得ロジック (L232-269) も Linux/macOS/Windows の 3 プラットフォームのみを想定。OpenJTalk / HTS Engine / spdlog の ExternalProject も Android ツールチェインへの対応が必要。

**ゴール:** `-DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake -DANDROID_ABI=arm64-v8a` でビルドが成功し、Android アプリから `System.loadLibrary("piper_plus")` で利用可能な共有ライブラリを生成する。

---

## 2. 実装する内容の詳細

### 2.1 CMake Android ツールチェイン対応 (`CMakeLists.txt`)

**ONNX Runtime Android 版の取得:**

```cmake
# ---- ONNX Runtime ---
if(ANDROID)
  # Android: Use ONNX Runtime Mobile (AAR contains JNI libs)
  set(ONNXRUNTIME_VERSION "1.14.1")
  set(ONNXRUNTIME_ANDROID_URL
    "https://repo1.maven.org/maven2/com/microsoft/onnxruntime/onnxruntime-android/${ONNXRUNTIME_VERSION}/onnxruntime-android-${ONNXRUNTIME_VERSION}.aar")
  set(ONNXRUNTIME_DIR "${CMAKE_CURRENT_BINARY_DIR}/ort_android")

  # AAR is a ZIP file; extract jni/<ABI>/libonnxruntime.so + headers
  ExternalProject_Add(
    onnxruntime_external
    PREFIX "${CMAKE_CURRENT_BINARY_DIR}/ort_android_dl"
    URL "${ONNXRUNTIME_ANDROID_URL}"
    CONFIGURE_COMMAND ""
    BUILD_COMMAND ""
    INSTALL_COMMAND ${CMAKE_COMMAND} -E make_directory ${ONNXRUNTIME_DIR}/lib
    COMMAND ${CMAKE_COMMAND} -E make_directory ${ONNXRUNTIME_DIR}/include
    # Extract .so from AAR (ZIP) jni/<ABI>/ directory
    COMMAND ${CMAKE_COMMAND} -E tar xf <DOWNLOADED_FILE>
      --format=zip jni/${ANDROID_ABI}/libonnxruntime.so
    COMMAND ${CMAKE_COMMAND} -E copy
      jni/${ANDROID_ABI}/libonnxruntime.so ${ONNXRUNTIME_DIR}/lib/
    # Headers from separate package or bundled
  )
elseif(WIN32)
  # ... existing Windows logic ...
```

**注意:** ONNX Runtime Android AAR は JNI ライブラリ (`jni/arm64-v8a/libonnxruntime.so`) を含むが、C/C++ ヘッダーは別途取得が必要。GitHub Releases の `onnxruntime-android-*-headers.zip` または ソースからコピーする。

**ExternalProject の Android クロスコンパイル対応:**

```cmake
if(ANDROID)
  # Pass Android toolchain to all ExternalProject dependencies
  set(ANDROID_CMAKE_ARGS
    -DCMAKE_TOOLCHAIN_FILE=${CMAKE_TOOLCHAIN_FILE}
    -DANDROID_ABI=${ANDROID_ABI}
    -DANDROID_PLATFORM=${ANDROID_PLATFORM}
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
  )
endif()

# OpenJTalk
set(OPENJTALK_CMAKE_ARGS
  -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
  -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON
  ${ANDROID_CMAKE_ARGS}  # Android の場合はツールチェインを追加
)

# spdlog
ExternalProject_Add(spdlog_external
  ...
  CMAKE_ARGS
    -DSPDLOG_BUILD_SHARED=OFF
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    ${ANDROID_CMAKE_ARGS}
)
```

**HTS Engine (autotools) の Android 対応:**

HTS Engine は autotools ビルド。Android NDK のツールチェインを使う場合:

```cmake
if(ANDROID)
  # HTS Engine stub: pure C, CMake-based, Android toolchain inherited
  set_target_properties(hts_engine_stub PROPERTIES
    POSITION_INDEPENDENT_CODE ON
  )
  # hts_engine_external (autotools) は Android ではスキップし stub を使用
endif()
```

**ARM64 NEON 最適化の有効化:**

```cmake
if(ANDROID AND ANDROID_ABI STREQUAL "arm64-v8a")
  target_compile_definitions(piper_plus PRIVATE USE_ARM64_NEON)
  target_sources(piper_plus PRIVATE src/cpp/audio_neon.cpp)
endif()
```

### 2.2 Android 固有の辞書パス解決

`openjtalk_dictionary_manager.c` の `get_exe_relative_dict_path()` は `/proc/self/exe` を使うが、Android では非標準的な結果を返す。Android 向けの辞書パス解決:

```c
#ifdef __ANDROID__
// Android: /proc/self/exe は dalvikvm や app_process を返す。
// 辞書は APK assets またはアプリの files ディレクトリに配置する想定。
// OPENJTALK_DICTIONARY_PATH 環境変数または PiperPlusConfig.dict_dir で明示指定が必須。
static const char* get_exe_relative_dict_path() {
    return NULL;  // Android では exe-relative は使わない
}
#endif
```

### 2.3 CI ワークフロー (``.github/workflows/android-build.yml` 新規)

```yaml
name: Android Build
on:
  push:
    branches: [dev, feature/c-api-*]
    paths:
      - 'src/cpp/**'
      - 'CMakeLists.txt'
      - '.github/workflows/android-build.yml'
  pull_request:
    paths:
      - 'src/cpp/**'
      - 'CMakeLists.txt'

jobs:
  build-android:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        abi: [arm64-v8a]
        # armeabi-v7a は将来追加検討
    steps:
      - uses: actions/checkout@v4

      - name: Setup Android NDK
        uses: android-actions/setup-android@v3
        with:
          ndk-version: '26.1.10909125'

      - name: Configure CMake
        run: |
          cmake -B build-android \
            -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake \
            -DANDROID_ABI=${{ matrix.abi }} \
            -DANDROID_PLATFORM=android-24 \
            -DPIPER_PLUS_BUILD_SHARED=ON \
            -DCMAKE_BUILD_TYPE=Release

      - name: Build
        run: cmake --build build-android --config Release -j$(nproc)

      - name: Verify outputs
        run: |
          file build-android/libpiper_plus.so
          # ELF 64-bit LSB shared object, ARM aarch64 を確認
          readelf -d build-android/libpiper_plus.so | grep NEEDED
          readelf --dyn-syms build-android/libpiper_plus.so | grep piper_plus_
```

### 2.4 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `CMakeLists.txt` | Android ABI 判定、ONNX Runtime Android 版取得、ExternalProject へのツールチェイン引き渡し、ARM64 NEON 条件分岐 |
| `src/cpp/openjtalk_dictionary_manager.c` | `__ANDROID__` 分岐で `get_exe_relative_dict_path()` を無効化 |
| `src/cpp/custom_dictionary.cpp` | `getDictExeDir()` の Android 対応 (`__ANDROID__` で `current_path()` フォールバック) |
| `.github/workflows/android-build.yml` | 新規 CI ワークフロー |
| `cmake/android-toolchain.cmake` | (オプション) プリセット設定ファイル |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| ビルドエージェント | 1 | CMake Android ツールチェイン対応 + ExternalProject 修正 |
| テストエージェント | 1 | CI ワークフロー作成 + Android エミュレータでのスモークテスト |
| レビューエージェント | 1 | クロスコンパイル設定の検証 + ABI 互換性確認 |

合計 3 名。Android クロスコンパイルは ExternalProject (OpenJTalk, spdlog, HTS Engine) の各依存ライブラリへのツールチェイン引き渡しが複雑で、トラブルシューティングに時間を要する可能性が高い。

---

## 4. 提供範囲とテスト項目

### スコープ

- `arm64-v8a` 向けの `libpiper_plus.so` ビルド
- ONNX Runtime Android 版 (AAR) との統合
- 全 ExternalProject の Android クロスコンパイル対応
- CI でのビルド検証 (実機テストは含まない)
- ARM64 NEON 最適化の有効化

### スコープ外

- `armeabi-v7a` (32-bit ARM) 対応 -- 将来追加
- `x86_64` (エミュレータ用) 対応 -- 将来追加
- Android アプリのサンプルコード (Flutter/Kotlin)
- JNI バインディング (Flutter の `dart:ffi` は直接 C API を呼ぶため不要)

### ビルドテスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestBuildARM64` | `arm64-v8a` でビルド成功 | `libpiper_plus.so` が ELF aarch64 バイナリ |
| `TestSymbolVisibility` | `readelf --dyn-syms` で公開シンボル確認 | `piper_plus_` プレフィックスのみ |
| `TestDependencies` | `readelf -d` で依存ライブラリ確認 | `libonnxruntime.so`, `libc.so`, `libm.so`, `libdl.so` のみ |
| `TestNEONEnabled` | `nm` で `findMaxAudioValueNEON` シンボル | ARM64 ビルドで存在 |
| `TestNoDesktopRegression` | 既存 3 プラットフォームビルド | 回帰なし |

### 統合テスト (将来)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestAndroidEmulator` | x86_64 エミュレータでライブラリロード | `System.loadLibrary` 成功 |
| `TestFlutterFFI` | Flutter の `dart:ffi` から `piper_plus_create` 呼び出し | NULL でない handle 返却 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| OpenJTalk の Android クロスコンパイル | 高 | OpenJTalk は CMake ベースだが、iconv 依存が Android で問題になる可能性。Android NDK の libiconv は限定的。テストで確認し、必要なら iconv を無効化またはバンドル |
| ONNX Runtime ヘッダーの取得 | 高 | AAR には .so のみでヘッダーが含まれない。GitHub Releases の separate headers package を使うか、onnxruntime ソースツリーから include/ をコピーする仕組みが必要 |
| HTS Engine の autotools ビルド | 中 | autotools の Android クロスコンパイルは `--host=aarch64-linux-android` が必要。M1-1 で `-fPIC` 対応済みの `hts_engine_stub` (CMake ベース) を使えば autotools は不要 |
| ライブラリサイズ | 中 | 全 8 言語 G2P を含むと `libpiper_plus.so` が大きくなる (推定 5-10MB)。Android では `-ffunction-sections -fdata-sections` + `--gc-sections` でサイズ削減。`-Os` 最適化も検討 |
| `/proc/self/exe` が非標準 | 低 | Android では dalvikvm のパスを返す。Phase 1 の `dict_dir` 明示指定で回避済み。M4-6 (dladdr) で改善予定 |
| C++ 標準ライブラリの選択 | 低 | NDK r25+ はデフォルトで `c++_shared` (libc++_shared.so)。アプリ側と一致させる必要。CMake で `ANDROID_STL=c++_shared` を明示 |

### レビュー時の確認項目

1. Android ツールチェインが全 ExternalProject に正しく伝播していること
2. ONNX Runtime Android 版のヘッダーとライブラリが正しくリンクされること
3. `libpiper_plus.so` の NEEDED が最小限であること
4. `STL` の選択が `c++_shared` であること (アプリとの互換)
5. 既存の 3 プラットフォームビルドに回帰がないこと
6. `ANDROID_PLATFORM` が十分に低いこと (android-24 = API 24 = Android 7.0)

---

## 6. 一から作り直すとしたら

**Phase 3 に含めるべきだったか:** Android は最も利用頻度の高いモバイルプラットフォームであり、Flutter/Dart ユースケースの主要ターゲット。Phase 3 (配布) に含めた方が、C API の価値を早期に実証できた。ただし、Phase 3 のスコープが既に大きい (リリースワークフロー + pkg-config + ドキュメント) ため、独立チケットとしたのは妥当。

**Conan / vcpkg 統合:** ExternalProject で全依存をソースからビルドする現在の方式は、Android クロスコンパイルでの設定の複雑さを増大させる。Conan や vcpkg のクロスコンパイルプロファイルを使えば、依存管理が大幅に簡素化される。ただし、既存のビルドシステムとの互換性を維持する必要がある。

**AAR パッケージング:** 最終的に `libpiper_plus.so` を AAR として配布することで、Android 開発者は `implementation 'com.piperplus:piper-plus:x.y.z'` で依存追加できる。ただし、AAR のビルドは Gradle タスクが必要で、CMake の範囲外。将来の配布チケットとして検討。

---

## 7. 後続タスクへの連絡事項

- **M3-5 (リリースワークフロー):** Android ビルドが完了すれば、リリースワークフローに `arm64-v8a` のアーティファクトを追加可能。
- **M4-6 (dladdr 辞書自動検出):** Android では `dladdr()` が利用可能 (`<dlfcn.h>`)。M4-6 の実装は Android でも動作するため、`dict_dir = NULL` 時の自動検出が改善される。
- **Flutter サンプル:** Android ビルドが完了すれば、`examples/flutter/` に Flutter アプリのサンプルを追加可能。ただし、これは Phase 4 の範囲外。
- **辞書の同梱:** Android アプリでは OpenJTalk 辞書を APK の `assets/` に同梱し、初回起動時に `getFilesDir()` にコピーするパターンが一般的。`dict_dir` には解凍後のパスを指定する。
- **armeabi-v7a / x86_64:** 32-bit ARM とエミュレータ用 x86_64 は将来の追加候補。優先度は利用者フィードバックに基づく。
