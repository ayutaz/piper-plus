# M1-4: CMake `PIPER_PLUS_BUILD_SHARED` + OBJECT ライブラリ

> **Phase:** 1 --- 基本 C API (MVP)
> **見積り:** 大
> **依存:** M1-1 (-fPIC), M1-5 (ヘッダー)
> **ブロック:** M1-6, M1-7, M1-8
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m1-4-cmake-piper_plus_build_shared--object-ライブラリ)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

CMake に `option(PIPER_PLUS_BUILD_SHARED)` を追加し、共有ライブラリ `libpiper_plus.so` / `.dylib` / `.dll` をビルドできるようにする。現在 `piper` (実行ファイル) と `test_piper` でソースファイルが二重列挙されている問題を `piper_common` OBJECT ライブラリで解消し、共有ライブラリを含む 3 重複を防ぐ。

**ゴール:**
1. `-DPIPER_PLUS_BUILD_SHARED=ON` で 3 プラットフォームに対応する共有ライブラリをビルドできる
2. `-DPIPER_PLUS_BUILD_SHARED=OFF` (デフォルト) で従来通り `piper` のみビルド
3. 既存の `piper` / `test_piper` ビルドが回帰しない

---

## 2. 実装する内容の詳細

### 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `CMakeLists.txt` (ルート) | OBJECT ライブラリ定義、SHARED ターゲット定義、install ルール |

### 具体的な変更内容

#### 2.1 OBJECT ライブラリ `piper_common` の定義

現在 `piper` (L86) と `test_piper` (L87) で同一ソースが列挙されている。これを OBJECT ライブラリに統合する。

```cmake
# ---- Core source files (shared between piper CLI, test_piper, and piper_plus) ----
set(PIPER_CORE_SOURCES
    src/cpp/piper.cpp
    src/cpp/phoneme_parser.cpp
    src/cpp/custom_dictionary.cpp
    src/cpp/language_detector.cpp
    src/cpp/english_phonemize.cpp
    src/cpp/chinese_phonemize.cpp
    src/cpp/korean_phonemize.cpp
    src/cpp/spanish_phonemize.cpp
    src/cpp/french_phonemize.cpp
    src/cpp/portuguese_phonemize.cpp
    src/cpp/swedish_phonemize.cpp
    src/cpp/openjtalk_phonemize.cpp
    src/cpp/openjtalk_phonemize_utils.cpp
    src/cpp/openjtalk_wrapper.c
    src/cpp/openjtalk_dictionary_manager.c
    src/cpp/openjtalk_error.c
    src/cpp/openjtalk_security.c
    src/cpp/openjtalk_optimized.c
    src/cpp/openjtalk_api.c
)

# ARM64 NEON optimizations
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
    list(APPEND PIPER_CORE_SOURCES src/cpp/audio_neon.cpp)
endif()

add_library(piper_common OBJECT ${PIPER_CORE_SOURCES})
set_target_properties(piper_common PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_compile_definitions(piper_common PUBLIC
    _PIPER_VERSION=${piper_version}
    SPDLOG_FMT_EXTERNAL=1
    FMT_HEADER_ONLY=1
)
```

**除外ファイル (CLI 専用):**
- `src/cpp/main.cpp` --- CLI エントリポイント
- `src/cpp/model_manager.cpp` --- モデルダウンロード管理 (CLI のみ)

#### 2.2 `piper` / `test_piper` を `piper_common` から構成

```cmake
# piper 実行ファイル
add_executable(piper src/cpp/main.cpp src/cpp/model_manager.cpp)
target_link_libraries(piper PRIVATE piper_common)

# test_piper
add_executable(test_piper src/cpp/test.cpp src/cpp/model_manager.cpp)
target_link_libraries(test_piper PRIVATE piper_common)
```

#### 2.3 `OPENJTALK_DIC_PATH` コンパイル定義の分離

現在 `piper` と `test_piper` で異なる `OPENJTALK_DIC_PATH` が設定されている (L575-588)。OBJECT ライブラリでは単一の定義しか持てないため、消費側ターゲットで個別設定する。

```cmake
# OPENJTALK_DIC_PATH は消費側ターゲットで個別設定
# (piper_common OBJECT ライブラリには設定しない)
if(WIN32)
    target_compile_definitions(piper PRIVATE OPENJTALK_DIC_PATH="..\\\\share\\\\open_jtalk\\\\dic")
    target_compile_definitions(test_piper PRIVATE OPENJTALK_DIC_PATH="${CMAKE_CURRENT_BINARY_DIR}\\\\naist-jdic")
else()
    target_compile_definitions(piper PRIVATE OPENJTALK_DIC_PATH="../share/open_jtalk/dic")
    target_compile_definitions(test_piper PRIVATE OPENJTALK_DIC_PATH="${CMAKE_CURRENT_BINARY_DIR}/naist-jdic")
endif()
```

**注意:** `OPENJTALK_DIC_PATH` は `openjtalk_dictionary_manager.c` 内で `#ifdef OPENJTALK_DIC_PATH` として参照されているか確認が必要。OBJECT ライブラリで未定義の場合、コンパイル警告が出る可能性がある。対策として `piper_common` には空のデフォルト値を設定するか、ランタイム検出にフォールバックさせる。

#### 2.4 `piper_plus` SHARED ライブラリターゲット

```cmake
option(PIPER_PLUS_BUILD_SHARED "Build piper-plus shared library" OFF)

if(PIPER_PLUS_BUILD_SHARED)
    add_library(piper_plus SHARED src/cpp/piper_plus_c_api.cpp)
    target_link_libraries(piper_plus PRIVATE piper_common)

    # Export macro
    target_compile_definitions(piper_plus PRIVATE PIPER_PLUS_BUILDING_DLL)

    # Symbol visibility
    set_target_properties(piper_plus PROPERTIES
        C_VISIBILITY_PRESET hidden
        CXX_VISIBILITY_PRESET hidden
        VISIBILITY_INLINES_HIDDEN ON
        VERSION ${piper_version}
        SOVERSION 1
    )

    # Public header for install
    set_target_properties(piper_plus PROPERTIES
        PUBLIC_HEADER src/cpp/piper_plus.h
    )

    # Platform-specific settings
    if(APPLE)
        set_target_properties(piper_plus PROPERTIES
            MACOSX_RPATH TRUE
            INSTALL_RPATH "@loader_path"
            BUILD_RPATH "${CMAKE_CURRENT_BINARY_DIR}/ort/lib"
        )
    elseif(NOT MSVC)
        # Linux: -static-libstdc++ is NOT applied (see M1-2)
        set_target_properties(piper_plus PROPERTIES
            INSTALL_RPATH "$ORIGIN"
            BUILD_WITH_INSTALL_RPATH TRUE
        )
    endif()

    # Dependencies (same as piper)
    add_dependencies(piper_plus openjtalk_external hts_engine_external fmt_external spdlog_external)

    # Include directories
    target_include_directories(piper_plus PRIVATE
        ${FMT_DIR}/include
        ${SPDLOG_DIR}/include
        ${OPENJTALK_DIR}/include
        ${OPENJTALK_DIR}/include/openjtalk
        ${HTS_ENGINE_DIR}/include
    )
    if(DEFINED ONNXRUNTIME_DIR)
        target_include_directories(piper_plus PRIVATE ${ONNXRUNTIME_DIR}/include)
        target_link_directories(piper_plus PRIVATE ${ONNXRUNTIME_DIR}/lib)
    endif()

    # Link libraries
    target_link_directories(piper_plus PRIVATE ${FMT_DIR}/lib ${SPDLOG_DIR}/lib)
    if(WIN32)
        target_link_libraries(piper_plus PRIVATE
            optimized ${FMT_DIR}/lib/fmt.lib
            debug ${FMT_DIR}/lib/fmtd.lib
            optimized ${SPDLOG_DIR}/lib/spdlog.lib
            debug ${SPDLOG_DIR}/lib/spdlogd.lib
            ${ONNXRUNTIME_LIB}
        )
        target_link_libraries(piper_plus PRIVATE ${OPENJTALK_DIR}/lib/openjtalk.lib)
    else()
        target_link_libraries(piper_plus PRIVATE fmt spdlog onnxruntime)
        target_link_libraries(piper_plus PRIVATE ${OPENJTALK_DIR}/lib/libopenjtalk.a)
    endif()

    if(USE_HTS_ENGINE_STUB)
        target_link_libraries(piper_plus PRIVATE hts_engine_stub)
    else()
        if(WIN32)
            target_link_libraries(piper_plus PRIVATE ${HTS_ENGINE_DIR}/lib/HTSEngine.lib)
        else()
            target_link_libraries(piper_plus PRIVATE ${HTS_ENGINE_DIR}/lib/libHTSEngine.a)
        endif()
    endif()

    if(UNIX AND NOT APPLE)
        find_package(Threads REQUIRED)
        target_link_libraries(piper_plus PRIVATE Threads::Threads)
    elseif(APPLE)
        target_link_libraries(piper_plus PRIVATE pthread)
    endif()

    # OPENJTALK_DIC_PATH for shared library: use empty default
    # (dict_dir is set at runtime via PiperPlusConfig.dict_dir or OPENJTALK_DICTIONARY_PATH env)
    # Do NOT set a compile-time path since the relative path would be wrong.

    # Windows: Copy ORT DLLs alongside the shared library
    if(WIN32)
        copy_dlls_to_target(piper_plus)
    endif()

    # ---- GNUInstallDirs (M3-1 / M3-4 から前倒し統合) ----
    include(GNUInstallDirs)

    # ---- Install targets with EXPORT (M3-1 / M3-3 から前倒し統合) ----
    # EXPORT 句は M3-3 (CMake Config パッケージ) で使用する。
    # 事前に含めておくことで M3-3 での差分を最小化する。
    install(TARGETS piper_plus
        EXPORT PiperPlusTargets
        LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
        RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
        PUBLIC_HEADER DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
    )
endif()
```

#### 2.5 RPATH 設定 (M3-4 から前倒し統合)

共有ライブラリが install 先で依存ライブラリ (特に ONNX Runtime) を正しく見つけられるようにする。実行ファイル (`piper`) と共有ライブラリ (`piper_plus`) では RPATH の基準が異なるため、明確に分離する。

```cmake
if(PIPER_PLUS_BUILD_SHARED)
    if(APPLE)
        set_target_properties(piper_plus PROPERTIES
            MACOSX_RPATH TRUE
            # 共有ライブラリ自身の位置基準で依存ライブラリを検索
            INSTALL_RPATH "@loader_path"
            # ビルドツリーでの ORT 検索パス
            BUILD_RPATH "${CMAKE_CURRENT_BINARY_DIR}/ort/lib"
            BUILD_WITH_INSTALL_RPATH FALSE
            # install_name を @rpath ベースに設定
            INSTALL_NAME_DIR ""
        )
    elseif(UNIX)
        set_target_properties(piper_plus PROPERTIES
            # Linux: ライブラリ自身の位置基準
            INSTALL_RPATH "$ORIGIN"
            BUILD_WITH_INSTALL_RPATH FALSE
        )
    endif()
    # Windows は RPATH 不要 (DLL 検索パスで解決)
endif()
```

**`@loader_path` vs `@executable_path` の違い:**

| マクロ | 展開先 | 適用対象 |
|--------|--------|---------|
| `@executable_path` | 実行ファイル (`piper`) のディレクトリ | 実行ファイルの依存ライブラリ検索 |
| `@loader_path` | ロード元 (`libpiper_plus.dylib`) のディレクトリ | 共有ライブラリの依存ライブラリ検索 |

共有ライブラリが Flutter/Godot/Python から dlopen される場合、`@executable_path` はホストアプリのパスに展開されるため、同梱の ORT が見つからない。`@loader_path` なら `libpiper_plus.dylib` 自身と同じディレクトリの ORT を確実に見つけられる。

#### 2.6 GNUInstallDirs 導入

ハードコードされた `bin`, `lib`, `include` パスを CMake 標準モジュールで置き換える。これにより `lib64` (Fedora/RHEL) や `lib/x86_64-linux-gnu` (Debian multiarch) に自動対応する。

```cmake
include(GNUInstallDirs)
```

M3-1 で本来行う予定だった GNUInstallDirs 導入を Phase 1 に前倒し。install ターゲットの `DESTINATION` に `${CMAKE_INSTALL_LIBDIR}` / `${CMAKE_INSTALL_BINDIR}` / `${CMAKE_INSTALL_INCLUDEDIR}` を使用する (2.4 節の install ターゲット参照)。

#### 2.7 EXPORT PiperPlusTargets

`install(TARGETS ... EXPORT PiperPlusTargets)` を M1-4 の時点で含めておくことで、M3-3 (CMake Config パッケージ) では `install(EXPORT PiperPlusTargets ...)` と Config テンプレートを追加するだけで済む。

```cmake
install(TARGETS piper_plus
    EXPORT PiperPlusTargets
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
    PUBLIC_HEADER DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| CMake エージェント | 1 | OBJECT ライブラリ定義、SHARED ターゲット、install ルール |
| テストエージェント | 1 | 既存ビルドの回帰テスト、3 プラットフォーム確認 |

合計: 2 名。CMake の変更量が大きく、プラットフォーム固有の問題が起きやすいため、テスト担当を分離する。

---

## 4. 提供範囲とテスト項目

### スコープ

- `piper_common` OBJECT ライブラリ定義
- `piper` / `test_piper` の `piper_common` からの再構成
- `PIPER_PLUS_BUILD_SHARED` オプションと `piper_plus` SHARED ターゲット
- プラットフォーム別の RPATH / SOVERSION / visibility 設定
- RPATH 設定: Linux `$ORIGIN`, macOS `@loader_path` (M3-4 から前倒し統合)
- GNUInstallDirs 導入 (M3-1 から前倒し統合)
- EXPORT PiperPlusTargets (M3-1 / M3-3 から前倒し統合)
- install ターゲット (`${CMAKE_INSTALL_LIBDIR}` + `${CMAKE_INSTALL_INCLUDEDIR}`)

### スコープ外

- `piper_plus_c_api.cpp` の実装 (M1-6)
- `piper_plus.h` ヘッダーの内容 (M1-5)
- テストの追加 (M1-7)
- ONNX Runtime 同梱 install ルール (M3-1 に残置)
- ONNX Runtime の install_name 修正 (M3-4 に残置)
- pkg-config / CMake Config ファイル生成 (M3-2, M3-3)

### テスト項目

| テスト | 方法 | 期待結果 |
|--------|------|----------|
| デフォルトビルド (SHARED=OFF) | `cmake -B build && cmake --build build` | `piper` / `test_piper` がビルド成功、共有ライブラリは生成されない |
| SHARED=ON ビルド (Linux) | `cmake -B build -DPIPER_PLUS_BUILD_SHARED=ON && cmake --build build` | `libpiper_plus.so` / `libpiper_plus.so.1` が生成される |
| SHARED=ON ビルド (macOS) | 同上 | `libpiper_plus.dylib` / `libpiper_plus.1.dylib` が生成される |
| SHARED=ON ビルド (Windows) | 同上 | `piper_plus.dll` + `piper_plus.lib` が生成される |
| シンボル可視性 (Linux) | `nm -D libpiper_plus.so \| grep ' T '` | `piper_plus_` プレフィックスのシンボルのみ |
| シンボル可視性 (macOS) | `nm -gU libpiper_plus.dylib` | `_piper_plus_` プレフィックスのシンボルのみ |
| 既存テスト回帰 | `ctest` で既存テスト実行 | 全テスト PASS |
| install (Linux) | `cmake --install build --prefix /tmp/install` | `lib/libpiper_plus.so*` + `include/piper_plus.h` |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | 影響度 | 対策 |
|------|--------|------|
| `OPENJTALK_DIC_PATH` が OBJECT ライブラリと非互換 | 中 | `piper_common` には設定しない。消費側ターゲット (`piper`, `test_piper`) で個別設定。`piper_plus` は実行時検出に依存 (M1-3 の `dict_dir` / `OPENJTALK_DICTIONARY_PATH` 環境変数) |
| OBJECT ライブラリの compile_definitions が消費側に伝播 | 低 | `target_compile_definitions(piper_common PUBLIC ...)` で `_PIPER_VERSION` 等を伝播。`OPENJTALK_DIC_PATH` は `PRIVATE` で消費側に設定 |
| `piper_common` の依存解決順序 | 中 | `add_dependencies(piper_common openjtalk_external ...)` で ExternalProject の完了を待つ |
| Windows の DLL エクスポート | 中 | `PIPER_PLUS_BUILDING_DLL` define で `__declspec(dllexport)` を有効化。消費側は未定義で `__declspec(dllimport)` になる |

### レビュー項目

- [ ] `piper_common` に `POSITION_INDEPENDENT_CODE ON` が設定されているか
- [ ] `piper` / `test_piper` のビルドが回帰していないか
- [ ] `OPENJTALK_DIC_PATH` が `piper_common` に設定されて**いない**か
- [ ] `piper_plus` に `-static-libstdc++` が適用されて**いない**か (M1-2)
- [ ] SOVERSION が 1 に設定されているか
- [ ] macOS の RPATH が `@loader_path` であるか (`@executable_path` ではない)
- [ ] Linux の RPATH が `$ORIGIN` であるか
- [ ] Windows で `copy_dlls_to_target(piper_plus)` が呼ばれているか
- [ ] `PIPER_PLUS_BUILD_SHARED=OFF` (デフォルト) で `piper_plus` ターゲットが定義されないか
- [ ] `include(GNUInstallDirs)` が追加されているか
- [ ] install の `DESTINATION` に `${CMAKE_INSTALL_LIBDIR}` 等の GNUInstallDirs 変数が使われているか
- [ ] `EXPORT PiperPlusTargets` が install ルールに含まれているか
- [ ] macOS の RPATH に `BUILD_WITH_INSTALL_RPATH FALSE` と `BUILD_RPATH` が設定されているか
- [ ] Linux の RPATH に `BUILD_WITH_INSTALL_RPATH FALSE` が設定されているか

---

## 6. 一から作り直すとしたら

最初から OBJECT ライブラリを前提として CMake を設計する。ソースファイルの列挙は 1 箇所 (`set(PIPER_CORE_SOURCES ...)`) のみとし、`add_executable` / `add_library` はエントリポイントのみを追加する。

また、ExternalProject の依存管理を `FetchContent` に統一する。`FetchContent_MakeAvailable` は CMake configure フェーズで依存を解決するため、`add_dependencies` の順序問題が起きない。ただし、autotools ベースの hts_engine_external は `FetchContent` 非互換のため、スタブ使用 (`USE_HTS_ENGINE_STUB=ON`) をデフォルトにするのが妥当。

プラットフォーム別の設定は `cmake/PiperPlatform.cmake` のようなモジュールに分離し、ルート CMakeLists.txt をシンプルに保つ。

---

## 7. 後続タスクへの連絡事項

- **M1-5 (ヘッダー):** `piper_plus.h` は `src/cpp/piper_plus.h` に配置すること。CMake の `PUBLIC_HEADER` プロパティで install 対象に含めている。
- **M1-6 (実装):** `piper_plus_c_api.cpp` は `src/cpp/piper_plus_c_api.cpp` に配置すること。CMake の `add_library(piper_plus SHARED ...)` のソースリストに含まれている。
- **M1-7 (テスト):** テストから共有ライブラリをリンクする場合、`target_link_libraries(test_c_api piper_plus)` で OK。ただし、M1-7 のモデル不要テストは共有ライブラリ API のヘッダー + 実装を直接コンパイルする方式も検討可能。
- **M1-8 (CI):** `-DPIPER_PLUS_BUILD_SHARED=ON` をビルドオプションに追加するだけで共有ライブラリがビルドされる。
- **M3-1 (install manifest):** GNUInstallDirs と EXPORT PiperPlusTargets は M1-4 で対応済み。M3-1 では ONNX Runtime 同梱 install、辞書 install、検証スクリプト等の配布固有ルールのみ追加すればよい。
- **M3-4 (RPATH):** piper_plus の RPATH (`$ORIGIN` / `@loader_path`) は M1-4 で対応済み。M3-4 では ONNX Runtime の install_name 修正 (macOS) と install 後の検証のみ対応すればよい。
- **`OPENJTALK_DIC_PATH` について:** `piper_plus` 共有ライブラリにはコンパイル時辞書パスを設定していない。利用者は `PiperPlusConfig.dict_dir` (M1-3) または `OPENJTALK_DICTIONARY_PATH` 環境変数で辞書パスを指定する必要がある。テストモデルが OpenJTalk 辞書を必要としないケース (英語のみ等) では問題にならない。
