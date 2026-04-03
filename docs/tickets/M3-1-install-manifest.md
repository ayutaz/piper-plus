# M3-1: 配布ファイルマニフェスト + install ターゲット整備

> **Phase:** 3 — 配布
> **見積り:** 中
> **依存:** Phase 2 完了
> **ブロック:** M3-2, M3-3, M3-4, M3-5
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m3-1-配布ファイルマニフェスト--install-ターゲット整備)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

> **注意 (振り返り反映):** GNUInstallDirs 導入、`EXPORT PiperPlusTargets`、および piper_plus の基本 install ターゲット (`LIBRARY`, `ARCHIVE`, `RUNTIME`, `PUBLIC_HEADER`) は **M1-4 で対応済み**。本チケットでは M1-4 のスコープ外である配布固有の install ルール (ONNX Runtime 同梱、辞書 install、検証スクリプト等) を追加する。

Phase 2 までで `libpiper_plus.so` / `.dylib` / `.dll` のビルドと API テストが完成している。しかし、`cmake --install` で生成される配布パッケージのレイアウト (ONNX Runtime 同梱、辞書配布) がまだ整備されていない。

**ゴール:** `cmake --install --prefix <dir>` を実行した際に、以下の配布レイアウトが 3 プラットフォームで正しく生成されること。

```
<prefix>/
├── lib/
│   ├── libpiper_plus.so -> libpiper_plus.so.1         (Linux)
│   ├── libpiper_plus.so.1 -> libpiper_plus.so.1.10.0  (Linux)
│   ├── libpiper_plus.so.1.10.0                        (Linux)
│   ├── libpiper_plus.1.dylib                          (macOS)
│   ├── piper_plus.dll + piper_plus.lib                (Windows)
│   ├── libonnxruntime.so.1.14.1 / .dylib / .dll      (プラットフォーム別)
│   ├── pkgconfig/                                     (M3-2 で追加)
│   └── cmake/PiperPlus/                               (M3-3 で追加)
├── include/
│   └── piper_plus.h
├── share/
│   ├── open_jtalk/dic/                                (OpenJTalk 辞書)
│   └── piper/dicts/                                   (CMU, pinyin)
└── bin/
    └── piper                                          (既存 CLI, optional)
```

このレイアウトは sherpa-onnx の配布レイアウトと整合しており、vcpkg / Conan での将来配布にも互換性がある。

---

## 2. 実装する内容の詳細

### 2.1 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `CMakeLists.txt` | install ターゲットの追加・整備、`GNUInstallDirs` 導入 |
| `cmake/verify_install_layout.cmake` (新規) | install レイアウト検証スクリプト |

### 2.2 CMakeLists.txt への変更

#### A. GNUInstallDirs の導入 (M1-4 で対応済み)

> `include(GNUInstallDirs)` は M1-4 で導入済み。本チケットでの追加作業は不要。

#### B. 共有ライブラリ本体 + ヘッダー install (M1-4 で対応済み)

> `install(TARGETS piper_plus EXPORT PiperPlusTargets ...)` と `PUBLIC_HEADER` install は M1-4 で対応済み。本チケットでの追加作業は不要。

#### C. ONNX Runtime 同梱 install (本チケットのスコープ)

```cmake
if(PIPER_PLUS_BUILD_SHARED)
  # --- ONNX Runtime 同梱 ---
  if(WIN32)
    if(ONNXRUNTIME_DLL)
      install(FILES "${ONNXRUNTIME_DLL}" DESTINATION ${CMAKE_INSTALL_BINDIR})
      get_filename_component(_ort_dir "${ONNXRUNTIME_DLL}" DIRECTORY)
      file(GLOB _ort_provider_dlls "${_ort_dir}/onnxruntime_providers*.dll")
      if(_ort_provider_dlls)
        install(FILES ${_ort_provider_dlls} DESTINATION ${CMAKE_INSTALL_BINDIR})
      endif()
    endif()
  else()
    install(
      DIRECTORY ${ONNXRUNTIME_DIR}/lib/
      DESTINATION ${CMAKE_INSTALL_LIBDIR}
      FILES_MATCHING
        PATTERN "libonnxruntime*"
        PATTERN "cmake" EXCLUDE
        PATTERN "pkgconfig" EXCLUDE
    )
  endif()

  # --- OpenJTalk 辞書 ---
  if(EXISTS "${OPENJTALK_DIC_DIR}")
    install(
      DIRECTORY "${OPENJTALK_DIC_DIR}/"
      DESTINATION share/open_jtalk/dic
    )
  endif()

  # --- G2P 辞書 (英語 CMU, 中国語 Pinyin) ---
  install(FILES
    ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/cmudict_data.json
    ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/pinyin_single.json
    ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/pinyin_phrases.json
    DESTINATION share/piper/dicts
  )
endif()
```

**重要:** `EXPORT PiperPlusTargets` は M3-3 (CMake Config パッケージ) で使用する。本チケットで事前に含めておくことで、M3-3 での差分を最小化する。

#### D. VERSION / SOVERSION の確認

Phase 1 (M1-4) で設定済みの以下を確認:

```cmake
set_target_properties(piper_plus PROPERTIES
  VERSION   ${piper_version}    # 1.10.0 (VERSION ファイルから読み込み)
  SOVERSION 1                   # ABI バージョン
)
```

Linux では `libpiper_plus.so.1.10.0` (実体) + `libpiper_plus.so.1` (SONAME symlink) + `libpiper_plus.so` (dev symlink) が CMake の install で自動生成される。

### 2.3 配布レイアウト検証スクリプト

`cmake/verify_install_layout.cmake` を新規作成し、CTest から呼び出す:

```cmake
# cmake/verify_install_layout.cmake
# Usage: cmake -P cmake/verify_install_layout.cmake -- <install_prefix>
cmake_minimum_required(VERSION 3.15)

set(PREFIX "${CMAKE_ARGV3}")
if(NOT PREFIX)
  message(FATAL_ERROR "Usage: cmake -P verify_install_layout.cmake -- <prefix>")
endif()

# 必須ファイルの存在確認
set(REQUIRED_FILES
  "include/piper_plus.h"
  "share/piper/dicts/cmudict_data.json"
  "share/piper/dicts/pinyin_single.json"
  "share/piper/dicts/pinyin_phrases.json"
)

foreach(f ${REQUIRED_FILES})
  if(NOT EXISTS "${PREFIX}/${f}")
    message(FATAL_ERROR "Missing: ${PREFIX}/${f}")
  endif()
  message(STATUS "OK: ${f}")
endforeach()

# プラットフォーム別ライブラリ確認
if(WIN32)
  if(NOT EXISTS "${PREFIX}/bin/piper_plus.dll")
    message(FATAL_ERROR "Missing: bin/piper_plus.dll")
  endif()
  if(NOT EXISTS "${PREFIX}/lib/piper_plus.lib")
    message(FATAL_ERROR "Missing: lib/piper_plus.lib")
  endif()
elseif(APPLE)
  file(GLOB _dylibs "${PREFIX}/lib/libpiper_plus*.dylib")
  if(NOT _dylibs)
    message(FATAL_ERROR "Missing: lib/libpiper_plus*.dylib")
  endif()
else()
  file(GLOB _sos "${PREFIX}/lib/libpiper_plus.so*")
  if(NOT _sos)
    message(FATAL_ERROR "Missing: lib/libpiper_plus.so*")
  endif()
endif()

message(STATUS "Install layout verification passed")
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| CMake エンジニア | 1 | install ターゲットの実装、GNUInstallDirs 導入、検証スクリプト作成 |
| QA | 1 | 3 プラットフォームでの install layout 検証 |

---

## 4. 提供範囲とテスト項目

### 4.1 ユニットテスト (CMake レベル)

| テスト | 内容 | 検証方法 |
|--------|------|---------|
| install layout | 全必須ファイルの存在 | `verify_install_layout.cmake` |
| SOVERSION symlink | Linux で `libpiper_plus.so` -> `.so.1` -> `.so.1.10.0` | `readlink` で確認 |
| macOS dylib ID | `@rpath/libpiper_plus.1.dylib` | `otool -D` |
| Windows import lib | `piper_plus.lib` の存在 | ファイル存在確認 |
| ヘッダー | `include/piper_plus.h` のインストール | ファイル存在確認 |
| 辞書 | `share/open_jtalk/dic/` と `share/piper/dicts/` | ディレクトリ存在確認 |
| EXPORT 句 | `PiperPlusTargets.cmake` が生成される | M3-3 で検証 |

### 4.2 E2E テスト

| テスト | 内容 |
|--------|------|
| install + link | install 先から C プログラムをコンパイル・リンクして `piper_plus_version()` 呼び出し |
| 辞書パスの動作 | `dict_dir` に install 先の `share/open_jtalk/dic` を指定して `piper_plus_create` が成功 |

### 4.3 CI テスト (M3-5 で統合)

```bash
cmake --install build --prefix /tmp/piper-plus-install
cmake -P cmake/verify_install_layout.cmake -- /tmp/piper-plus-install
```

---

## 5. 懸念事項とレビュー項目

| 懸念 | 詳細 | 対策 |
|------|------|------|
| ONNX Runtime の同梱サイズ | libonnxruntime は ~60MB (Linux)。tar.gz で ~20MB | リリースノートにサイズを明記。将来は ORT を optional にする余地を残す |
| 辞書の同梱サイズ | OpenJTalk 辞書は ~50MB | 必須。辞書なしでは JA G2P が機能しない |
| GNUInstallDirs と既存 install の互換性 | 既存の `install(TARGETS piper DESTINATION bin)` と矛盾しないか | `piper` (CLI) の install は既存のままで影響なし。`piper_plus` (共有ライブラリ) のみ GNUInstallDirs を適用 |
| Windows DLL の配置先 | `bin/` と `lib/` のどちらか | Windows 慣習に従い DLL は `bin/`, import lib は `lib/`。CMake の `RUNTIME DESTINATION bin` がこれを処理 |
| ONNX Runtime のバージョン固定 | 1.14.1 を同梱するが、ユーザーが別バージョンを使いたい場合 | pkg-config (M3-2) で `-L` パスを提供し、ユーザーの ORT を優先できるようにする |

**レビュー項目:**
- [ ] `cmake --install` の出力ディレクトリ構造が 3 プラットフォームで一致 (パス区切りを除く)
- [ ] SOVERSION symlink が正しく生成される (Linux)
- [ ] ONNX Runtime の同梱がプラットフォーム別に正しく動作する
- [ ] 既存の `piper` CLI ビルドが回帰しない
- [ ] `EXPORT PiperPlusTargets` が正しく生成される

---

## 6. 一から作り直すとしたら

1. **配布レイアウトは最初から `GNUInstallDirs` ベースにする。** Phase 1 でハードコードされた `DESTINATION lib` / `DESTINATION bin` を後から差し替えるのは diff が大きくなる。初期設計で `${CMAKE_INSTALL_LIBDIR}` を使うべきだった。

2. **ONNX Runtime の同梱を CMake の `IMPORTED` ターゲットで管理する。** 現在は `target_link_directories` + `target_link_libraries` でパスを直接指定しているが (CMakeLists.txt L269-270, L517-519)、`find_package(onnxruntime)` 互換の `IMPORTED` ターゲットにすれば、install 時のファイルコピーも `install(IMPORTED_RUNTIME_ARTIFACTS)` で自動化できる。

3. **辞書の install を ExternalProject の `INSTALL_COMMAND` に統合する。** 現在は `openjtalk_dic_download` ExternalProject (CMakeLists.txt L434-449) がビルドツリー内にしか辞書をコピーしない。install ルールと二重管理になっている。

---

## 7. 後続タスクへの連絡事項

- **M3-2 (pkg-config):** `GNUInstallDirs` の `CMAKE_INSTALL_LIBDIR` / `CMAKE_INSTALL_INCLUDEDIR` を `.pc.in` テンプレートで参照すること。`${prefix}/lib` ではなく `${libdir}` を使う。
- **M3-3 (CMake Config):** 本チケットで `EXPORT PiperPlusTargets` を install ルールに含めてある。M3-3 では `install(EXPORT PiperPlusTargets ...)` と Config ファイルテンプレートを追加するだけでよい。
- **M3-4 (RPATH):** 本チケットの ONNX Runtime install ルールと連動して、RPATH が `$ORIGIN` / `@loader_path` で ORT を見つけられるようにする。
- **M3-5 (リリースワークフロー):** `cmake --install` の出力をそのまま tar/zip する方式を採用すること。`build-piper.yml` の手動ファイルコピーロジック (L262-392) を `cmake --install` に置き換えられる。
