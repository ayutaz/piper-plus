# M3-001: CI / CMake から HTS voice 関連を除去

## メタデータ
- マイルストーン: M3
- 依存チケット: M1-001 (C++ ランタイムから `get_openjtalk_voice_path()` 削除済みであること)
- ブロックするチケット: M4-001 (テスト追加 + クリーンアップ)
- 状態: 未着手
- 推定削除行数: ~120行 (コード削除) + 93行 (HTSEngine_CMakeLists.txt ファイル削除) — 内訳: 実 HTS Engine ビルドパス 51行 + CI stub 手動作成 23行 + PiperLink 分岐 26行 + PiperPlusShared 分岐 9行 + CI 環境変数 1行 + tests/CMakeLists.txt 7行

## 1. 目的とゴール

piper-plus は VITS ニューラル TTS エンジンであり、HTS Engine による音声合成は一切使用しない。しかし歴史的経緯から、CI ワークフローには voice ファイルのダウンロード・環境変数設定が残存し、CMake ビルドシステムには実 HTS Engine をソースからビルドするパス (`USE_HTS_ENGINE_STUB=OFF`) が残存している。

M1 で C++ ランタイムから voice 依存コード (`get_openjtalk_voice_path()` 等) が除去された後、CI/CMake レイヤーに残る HTS voice 関連の設定を除去し、ビルドパイプラインを簡素化する。

**ゴール:**
1. CI ワークフローから voice ファイル DL/セットアップを完全除去する
2. CMake の `USE_HTS_ENGINE_STUB=OFF` パス (実 HTS Engine ビルド) を廃止し、`FATAL_ERROR` に置き換える
3. `build-piper.yml` の HTS Engine stub 手動作成ブロックを削除する (CMake が stub を自動処理するため不要)
4. テスト CMakeLists.txt からハードコードされた `hts_stub/include` パスを削除する (マクロ `link_openjtalk_to_test()` 経由で自動設定されるため)
5. stub ファイル (`hts_engine_stub.h`, `hts_engine_stub.c`) と stub ビルドロジック (ExternalDeps.cmake L97-139) は**維持**する

## 2. 実装内容の詳細

### 2.1 CI ワークフローの変更

#### 2.1.1 `_build-test-cpp.yml` — voice 環境変数の削除

**ファイル:** `.github/workflows/_build-test-cpp.yml`
**対象行:** L232

現状、Unix テスト実行時に `export OPENJTALK_VOICE="dummy.htsvoice"` が設定されている。M1 完了後は C++ コードが `OPENJTALK_VOICE` 環境変数を参照しなくなるため、この行は完全に不要になる。

```diff
          # Environment variables
          if [ "${{ runner.os }}" == "Windows" ]; then
            export ESPEAK_NG_DATA="${PWD}/espeak-ng-data"
            export PATH="${ONNXRUNTIME_ROOT_PATH}/lib:${PATH}"
          else
-           export OPENJTALK_VOICE="dummy.htsvoice"
            export OPENJTALK_SKIP_TESTS_IF_UNAVAILABLE=1
            export OPENJTALK_DICTIONARY_DIR="${PWD}/naist-jdic"
            export ESPEAK_NG_DATA="${PWD}/espeak-ng-data"
          fi
```

**削除行数:** 1行

#### 2.1.2 `build-piper.yml` — HTS Engine stub 手動作成ブロックの削除

**ファイル:** `.github/workflows/build-piper.yml`
**対象行:** L134-156

現状、`build-piper.yml` は CMake configure の**前に** HTS Engine stub のディレクトリと空ライブラリを手動で作成している。しかし `cmake/ExternalDeps.cmake` の stub ビルドロジック (L97-139) が `hts_engine_stub` ターゲットとしてディレクトリ作成・ヘッダーコピー・ライブラリビルドをすべて自動実行するため、この手動作成は完全に冗長である。

```diff
-     # Create HTS Engine stub
-     - name: Create HTS Engine stub (Unix)
-       if: runner.os != 'Windows'
-       run: |
-         # Create the HTS Engine stub
-         mkdir -p build/hts_stub/lib
-         mkdir -p build/hts_stub/include
-         cd build/hts_stub/lib
-         # Create empty object file for macOS compatibility
-         echo "" > empty.c
-         cc -c empty.c -o empty.o
-         ar rcs libHTSEngine.a empty.o
-         rm -f empty.c empty.o
-         cd -
-
-     - name: Create HTS Engine stub (Windows)
-       if: runner.os == 'Windows'
-       run: |
-         # Create the HTS Engine stub for Windows
-         New-Item -ItemType Directory -Force -Path build\hts_stub\lib
-         New-Item -ItemType Directory -Force -Path build\hts_stub\include
-         # Windows doesn't need actual HTS Engine stub
-       shell: pwsh
```

**削除行数:** 23行 (L134-156)

### 2.2 CMake の変更

#### 2.2.1 `cmake/ExternalDeps.cmake` — 実 HTS Engine ビルドパスの廃止

**ファイル:** `cmake/ExternalDeps.cmake`
**対象行:** L141-191

`USE_HTS_ENGINE_STUB=OFF` 時の `elseif` ブロックは実 HTS Engine v1.10 を SourceForge からダウンロードし、Windows では CMake ビルド、Unix では autotools ビルドを行う。コードベース分析上このパスの使用者は存在しない。`FATAL_ERROR` に置き換える。

```diff
  # Create dummy target for dependencies
  add_custom_target(hts_engine_external DEPENDS hts_engine_stub)

-elseif(NOT DEFINED HTS_ENGINE_DIR)
-    set(HTS_ENGINE_DIR "${CMAKE_CURRENT_BINARY_DIR}/he")
-    set(HTS_ENGINE_VERSION "1.10")
-
-    if(WIN32)
-      # Use CMake build for Windows
-      ExternalProject_Add(
-        hts_engine_external
-        ...
-      )
-    else()
-      # Use autotools for Unix platforms
-      ...
-      ExternalProject_Add(
-        hts_engine_external
-        ...
-      )
-    endif()
-endif()
+else()
+  message(FATAL_ERROR
+    "USE_HTS_ENGINE_STUB=OFF is no longer supported. "
+    "piper-plus uses neural network synthesis (ONNX), not HTS Engine. "
+    "The HTS Engine stub is required for OpenJTalk header compatibility.")
+endif()
```

**削除行数:** 51行 (L141-191)、追加 5行
**関連ファイル削除:** `cmake/HTSEngine_CMakeLists.txt` (93行) -- L159 の `PATCH_COMMAND` でのみ参照。実 HTS Engine パスの廃止に伴い不要。

#### 2.2.2 `cmake/PiperLink.cmake` — HTS 依存リンクの簡素化

**ファイル:** `cmake/PiperLink.cmake`

**(a) `hts_engine_external` 依存の削除 (L57-62):**

`hts_engine_external` は stub モードでは `hts_engine_stub` に依存するカスタムターゲットである。しかし `piper_common` / `piper` / `test_piper` は stub ライブラリを直接リンクしており、CMake の依存解決で自動的にビルド順序が保証される。`add_dependencies` による明示的依存は冗長だが、実 HTS Engine パスが廃止されれば `hts_engine_external` ターゲットの意味が stub 限定になるため、`add_dependencies` ではなく直接 `hts_engine_stub` をリンクするだけで十分になる。

```diff
-# Link HTS_Engine (required for OpenJTalk build)
-add_dependencies(piper_common hts_engine_external)
-if(TARGET piper)
-  add_dependencies(piper hts_engine_external)
-  add_dependencies(test_piper hts_engine_external)
-endif()
```

**削除行数:** 6行

**(b) 実 HTS Engine リンクパスの削除 (L64-89):**

`USE_HTS_ENGINE_STUB` が常に ON になるため、`else()` ブロック (L69-89) は到達不能コードになる。stub リンクのみ残す。

```diff
-if(USE_HTS_ENGINE_STUB)
-  if(TARGET piper)
-    target_link_libraries(piper PRIVATE hts_engine_stub)
-    target_link_libraries(test_piper PRIVATE hts_engine_stub)
-  endif()
-else()
-  if(WIN32)
-    if(TARGET piper)
-      target_link_libraries(piper PRIVATE
-        ${CMAKE_CURRENT_BINARY_DIR}/he/lib/HTSEngine.lib
-      )
-      target_link_libraries(test_piper PRIVATE
-        ${CMAKE_CURRENT_BINARY_DIR}/he/lib/HTSEngine.lib
-      )
-    endif()
-  else()
-    if(TARGET piper)
-      target_link_libraries(piper PRIVATE
-        ${CMAKE_CURRENT_BINARY_DIR}/he/lib/libHTSEngine.a
-      )
-      target_link_libraries(test_piper PRIVATE
-        ${CMAKE_CURRENT_BINARY_DIR}/he/lib/libHTSEngine.a
-      )
-    endif()
-  endif()
-endif()
+# Link HTS Engine stub (required for OpenJTalk header compatibility)
+if(TARGET piper)
+  target_link_libraries(piper PRIVATE hts_engine_stub)
+  target_link_libraries(test_piper PRIVATE hts_engine_stub)
+endif()
```

**削除行数:** 26行 (L64-89)、追加 4行

#### 2.2.3 `cmake/PiperPlusShared.cmake` — 共有ライブラリの HTS リンク簡素化

**ファイル:** `cmake/PiperPlusShared.cmake`

**(a) 依存リストから `hts_engine_external` を削除 (L22):**

```diff
-add_dependencies(piper_plus fmt_external spdlog_external openjtalk_external hts_engine_external)
+add_dependencies(piper_plus fmt_external spdlog_external openjtalk_external)
```

`hts_engine_stub` ライブラリは `target_link_libraries` 経由で依存関係が自動解決される。

**(b) include ディレクトリ (L35) -- 維持:**

`${HTS_ENGINE_DIR}/include` は stub モードでも `HTS_engine.h` を提供するため維持する。変更なし。

**(c) HTS Engine リンクの簡素化 (L101-110):**

```diff
-# Link HTS Engine
-if(USE_HTS_ENGINE_STUB)
-  target_link_libraries(piper_plus PRIVATE hts_engine_stub)
-else()
-  if(WIN32)
-    target_link_libraries(piper_plus PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/he/lib/HTSEngine.lib)
-  else()
-    target_link_libraries(piper_plus PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/he/lib/libHTSEngine.a)
-  endif()
-endif()
+# Link HTS Engine stub (required for OpenJTalk header compatibility)
+target_link_libraries(piper_plus PRIVATE hts_engine_stub)
```

**削除行数:** 10行 (L101-110)、追加 2行

#### 2.2.4 `src/cpp/tests/CMakeLists.txt` — ハードコードされた hts_stub include パスの削除

**ファイル:** `src/cpp/tests/CMakeLists.txt`
**対象行:** L25, L252, L335, L456, L663, L747, L830 (合計 7箇所)

`link_openjtalk_to_test()` マクロ (L21-38) が既に `${CMAKE_BINARY_DIR}/hts_stub/include` を `target_include_directories` に追加し、`hts_engine_stub` をリンクしている。各テストの個別設定でハードコードされた `${CMAKE_BINARY_DIR}/hts_stub/include` は冗長であり、削除しても動作に影響しない。

**対象テスト:**
| 行 | テスト |
|----|--------|
| L25 | `link_openjtalk_to_test` マクロ定義内 -- **維持** (このマクロが正規の include パス設定) |
| L252 | `test_streaming` |
| L335 | `test_streaming_simple` |
| L456 | `test_streaming_raw_phonemes` |
| L663 | `test_c_api` |
| L747 | `test_c_api_integration` |
| L830 | `test_c_api_audio_regression` |

**注意:** L25 のマクロ定義内の `${CMAKE_BINARY_DIR}/hts_stub/include` は**維持**する。これが全テストに stub ヘッダーを提供する正規のパスである。L252, L335, L456, L663, L747, L830 の 6箇所のみ削除する。

```diff
        # Include directories (test_streaming 例)
        target_include_directories(${test_name} PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/..
            ${CMAKE_BINARY_DIR}/fi/include
            ${CMAKE_BINARY_DIR}/si/include
            ${ORT_INCLUDE_DIR}
            ${CMAKE_BINARY_DIR}/oj/include
            ${CMAKE_BINARY_DIR}/oj/include/openjtalk
-           ${CMAKE_BINARY_DIR}/hts_stub/include
        )
```

**削除行数:** 6行 (各テスト 1行 x 6箇所)

### 2.3 維持するもの (変更しないもの)

| ファイル | 理由 |
|---------|------|
| `cmake/hts_engine_stub.h` | OpenJTalk ヘッダー (`open_jtalk/mecab.h` 等) が `#include "HTS_engine.h"` しており、型定義 (`HTS_Engine` 等) の互換シムとして必要。削除するとコンパイルエラーになる。 |
| `cmake/hts_engine_stub.c` | stub ライブラリの実装。OpenJTalk のリンク要件 (シンボル解決) を満たすため維持。合成関数は呼ばれたら `exit(1)` で安全に終了する。 |
| `cmake/ExternalDeps.cmake` L97-139 | stub ビルドロジック。`hts_engine_stub` ターゲット定義、ヘッダーコピー (`HTS_engine.h` -> `hts_stub/include/`)、stub ライブラリ構築を行う。これは OpenJTalk ビルドの前提条件である。 |
| `cmake/PiperPlusShared.cmake` L35 | `${HTS_ENGINE_DIR}/include` の include ディレクトリ設定。stub モードでも `HTS_engine.h` ヘッダーを提供するため維持。 |
| `cmake/PiperLink.cmake` L131-137 | `${HTS_ENGINE_DIR}/include` の include ディレクトリ設定 (piper/test_piper 向け)。同上。 |
| `src/cpp/tests/CMakeLists.txt` L25 | `link_openjtalk_to_test` マクロ内の `${CMAKE_BINARY_DIR}/hts_stub/include`。各テストに stub ヘッダーを提供する正規パス。 |

## 3. エージェントチームの役割と人数

本チケットは単一エージェントで実施可能。変更ファイル数は 7 (+ 1 ファイル削除) で相互依存が小さい。

| 役割 | 人数 | 担当範囲 |
|------|------|---------|
| 実装エージェント | 1 | CI yml 変更 2件 + CMake 変更 4件 + ファイル削除 1件 |

**作業順序:**
1. `cmake/ExternalDeps.cmake` -- 実 HTS Engine パスを `FATAL_ERROR` に置き換え
2. `cmake/PiperLink.cmake` -- 依存・リンク簡素化
3. `cmake/PiperPlusShared.cmake` -- 依存・リンク簡素化
4. `src/cpp/tests/CMakeLists.txt` -- 重複 include パス削除 (6箇所)
5. `.github/workflows/_build-test-cpp.yml` -- 環境変数削除
6. `.github/workflows/build-piper.yml` -- stub 手動作成ブロック削除
7. `cmake/HTSEngine_CMakeLists.txt` -- ファイル削除

ステップ 1-4 は CMake ターゲット定義の変更順序に依存があるため直列実行。ステップ 5-7 は独立して並行可能。

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (スコープ)

**IN スコープ:**
- CI ワークフローから voice 関連の環境変数設定・stub 手動作成を除去
- CMake の `USE_HTS_ENGINE_STUB=OFF` パスを廃止
- CMake のリンク設定を stub 限定に簡素化
- テスト CMakeLists.txt の重複 include パスを整理
- `cmake/HTSEngine_CMakeLists.txt` の削除

**OUT スコープ:**
- C++ ランタイムコードの変更 (M1 の範囲)
- WASM G2P / openjtalk-web の変更 (M2 の範囲)
- 新規テストの追加 (M4 の範囲)
- stub ファイル (`hts_engine_stub.h`, `hts_engine_stub.c`) の変更

### 4.2 ユニットテスト

M3 は新規テストを追加しない。既存テストの通過をもって受入基準とする。

**既存テストによる安全網:**

| テスト | ファイル | カバー範囲 |
|--------|---------|-----------|
| `test_c_api` | `test_c_api.cpp` | C API ユニットテスト。stub リンクが正しいことを検証 |
| `test_c_api_integration` | `test_c_api_integration.cpp` | ONNX モデル使用の統合テスト。voice 不使用 |
| `test_c_api_audio_regression` | `test_c_api_audio_regression.cpp` | 音声回帰テスト。voice 不使用 |
| `test_openjtalk_optimized` | `test_openjtalk_optimized.cpp` | phonemizer パスの音素抽出。voice なしで動作 |
| `test_streaming` | `test_streaming.cpp` | ストリーミング合成。stub リンクが正しいことを検証 |
| `test_streaming_simple` | `test_streaming_simple.cpp` | 同上 |
| `test_streaming_raw_phonemes` | `test_streaming_raw_phonemes.cpp` | 同上 |

### 4.3 E2Eテスト

**CI パイプラインによる検証:**

| 検証項目 | ワークフロー | 期待結果 |
|---------|------------|---------|
| CMake configure 成功 | `_build-test-cpp.yml` | `cmake -B build` が 3 OS で成功 |
| CMake build 成功 | `_build-test-cpp.yml` | `cmake --build build` が 3 OS で成功 |
| ctest 全 PASS/SKIP | `_build-test-cpp.yml` | FAIL なし |
| `USE_HTS_ENGINE_STUB=OFF` 拒否 | ローカル検証 | `cmake -B build -DUSE_HTS_ENGINE_STUB=OFF` が `FATAL_ERROR` |
| 共有ライブラリビルド | `_build-test-cpp.yml` | `PIPER_PLUS_BUILD_SHARED=ON` が成功 |
| シンボル検証 | `_build-test-cpp.yml` | 全必須 C API シンボルが存在 |
| 配布パッケージ作成 | `build-piper.yml` | Unix/Windows でパッケージ作成が成功 |

**受入基準:**
- [ ] `cmake -B build` (stub モード) が 3 OS (Linux/macOS/Windows) で成功する
- [ ] `cmake -B build -DUSE_HTS_ENGINE_STUB=OFF` が `FATAL_ERROR` で停止する
- [ ] `cmake --build build` が 3 OS で成功する
- [ ] `ctest` が全て PASS/SKIP (FAIL なし)
- [ ] CI ワークフロー (`_build-test-cpp.yml`, `build-piper.yml`) が voice DL なしで正常完了する
- [ ] `grep -r "dummy.htsvoice" .github/` が 0 件
- [ ] `cmake/HTSEngine_CMakeLists.txt` が削除されている

## 5. 懸念事項とレビュー項目

### 5.1 `build-piper.yml` の stub 手動作成削除の安全性

`build-piper.yml` の手動 stub 作成 (L134-156) は `cmake ..` の**前**に実行されているため、CMake configure 時に `build/hts_stub/` ディレクトリが既に存在する前提でロジックが組まれている可能性がある。しかし `ExternalDeps.cmake` の stub ロジック (L97-139) は `file(MAKE_DIRECTORY ...)` と `add_library()` で自己完結しており、事前のディレクトリ存在を前提としていない。したがって手動作成の削除は安全である。

**レビューポイント:** `build-piper.yml` の `cmake ..` が `cd build` の後に実行されることを確認し、CMake がビルドディレクトリ内に stub を正しく生成するフローを検証すること。

### 5.2 `hts_engine_external` ターゲットの残存参照

`ExternalDeps.cmake` L139 の `add_custom_target(hts_engine_external DEPENDS hts_engine_stub)` は stub ビルド内で定義されており、維持される。しかし `PiperPlusShared.cmake` L22 から `hts_engine_external` を削除するため、このターゲットを参照するのは `PiperLink.cmake` のコメント (L4) のみになる。

**レビューポイント:** `hts_engine_external` ターゲットが本当に他から参照されていないか、`grep -r "hts_engine_external" cmake/ .github/` で確認すること。L139 の定義自体を削除すべきかどうかも要検討。ただし、サードパーティが `add_dependencies(... hts_engine_external)` で使用する可能性を考慮し、M3 では維持して M4 で再評価する方針を推奨。

### 5.3 `USE_HTS_ENGINE_STUB` オプション自体の残存

M3 完了後、`USE_HTS_ENGINE_STUB=ON` が唯一の有効パスになるが、`option()` 宣言と `if(USE_HTS_ENGINE_STUB)` 分岐は残る。これは意図的であり、M4 で `option()` を削除して stub をデフォルト (かつ唯一) のパスにするかどうかを検討する。M3 では`OFF` を `FATAL_ERROR` にするのみとし、オプション自体は残す。

### 5.4 CMake キャッシュ残存

| CMake キャッシュ残存 | 低 | ローカル開発者が以前に `-DUSE_HTS_ENGINE_STUB=OFF` で configure した `build/` の `CMakeCache.txt` に `USE_HTS_ENGINE_STUB:BOOL=OFF` が残存する。`FATAL_ERROR` メッセージに「`rm -rf build && cmake -B build` で再 configure してください」とガイダンスを含めること |

### 5.5 Windows CI でのテスト網羅性

`_build-test-cpp.yml` の Windows パスでは `OPENJTALK_VOICE` が設定されていない (L228-230)。つまり Windows CI は元から voice なしで動作しており、M3 の変更は Unix パス (L232) のみに影響する。Windows で問題が発生するリスクは低い。

## 6. ゼロから作り直すとしたら

### 6.1 stub 戦略は正しかったか

stub 戦略 (`hts_engine_stub.h` / `hts_engine_stub.c`) は「OpenJTalk のヘッダーが `HTS_engine.h` を require する」という制約に対する実用的な解決策であり、基本的に正しいアプローチだった。OpenJTalk のソースコードを fork して `#include` を削除する方法もあるが、上流への追従コストと fork の保守コストを考えると、インターフェースレベルでの互換シムの方が持続可能である。

ただし、現在の stub はリンクレベルの互換性まで提供している (全関数の no-op 実装を含む)。`hts_engine_stub.c` は 20 以上の関数実装を含み、その大半が `exit(1)` で即座に終了するか `(void)param;` で引数を捨てるだけである。OpenJTalk のビルド設定で `HTS_engine.h` が include されるのはヘッダー内の型参照のみであり、リンク時にシンボルが要求されるのは OpenJTalk の `open_jtalk` コマンドラインバイナリをビルドする場合のみである。piper-plus は OpenJTalk をライブラリ (`libopenjtalk.a`) としてのみ使用するため、理想的には**ヘッダーオンリーの stub** (`hts_engine_stub.h` のみ、`.c` なし) でリンク要件を回避できる可能性がある。

**ヘッダーオンリー stub の検証方法:**
```bash
# hts_engine_stub.c をリンクせずにビルドできるか検証
cmake -B build-test -DUSE_HTS_ENGINE_STUB=ON
# hts_engine_stub.c を空ファイルに置き換え
echo "" > cmake/hts_engine_stub.c
cmake --build build-test 2>&1 | grep "undefined reference\|unresolved external"
# リンクエラーが出なければ .c は不要
```

この検証は M4 で実施を推奨する。`.c` が不要と判明すれば、stub の保守範囲が型定義のみに縮小される。

### 6.2 コンパイル時除去 vs ランタイム除去 (M1 との整合)

M1 のランタイムコード修正では「voice 分岐をソースから物理削除する」アプローチを取っている。M3 の CMake 修正では「`USE_HTS_ENGINE_STUB=OFF` パスを `FATAL_ERROR` に置き換える」アプローチを取っている。両方とも「不要なパスを除去する」という同一の思想に基づいているが、除去の手法が異なる。

| 層 | M1 の手法 | M3 の手法 |
|----|----------|----------|
| ランタイム (C++) | voice 分岐を物理削除 | - |
| ビルドシステム (CMake) | - | `else()` → `FATAL_ERROR` に置換 |
| CI (yml) | - | 環境変数・手動 stub 作成を削除 |

ゼロから設計するなら、この 3 層の除去を最初から `#ifdef` / `cmake option()` で統一的に制御すべきだった:

```cmake
# CMakeLists.txt (理想)
option(PIPER_ENABLE_HTS_VOICE "Enable HTS voice synthesis fallback" OFF)

if(PIPER_ENABLE_HTS_VOICE)
  # 実 HTS Engine のビルド
else()
  # stub のみ
endif()
```

```c
// C++ ランタイム (理想)
#ifdef PIPER_ENABLE_HTS_VOICE
    const char* voice_path = get_openjtalk_voice_path();
    // ...
#endif
```

CMake の `option()` が C++ の `#ifdef` を自動的に伝播する仕組み (`target_compile_definitions`) を最初から使っていれば、M1 と M3 を分ける必要すらなかった。

### 6.3 依存の透明性: 依存グラフの可視化と監査

現在のプロジェクトでは依存関係が暗黙的に複雑化している (`hts_engine_external` → `hts_engine_stub` → OpenJTalk ヘッダー → piper バイナリ)。次回は以下を CI に組み込むべきだった:

**依存グラフの可視化:**
```bash
# CMake の組み込み機能で依存グラフを DOT 形式で出力
cmake -B build --graphviz=build/deps.dot
dot -Tsvg build/deps.dot -o build/deps.svg
```

**CI での依存監査 (新規ターゲット追加時の自動検出):**
```yaml
# .github/workflows/_build-test-cpp.yml に追加すべきだったステップ
- name: Audit dependency graph
  run: |
    cmake -B build --graphviz=build/deps.dot
    # HTS Engine への新規依存が追加されていないことを検証
    if grep -q "hts_engine_external" build/deps.dot | grep -v "hts_engine_stub"; then
      echo "FAIL: Unexpected dependency on real HTS Engine detected"
      exit 1
    fi
```

これにより、誰かが誤って `target_link_libraries(... hts_engine_external)` を追加しても CI で検出できる。M4 でこの監査ステップの導入を検討すべきである。

ゼロから設計するなら:
1. **ビルドシステムレベル:** OpenJTalk の CMakeLists.txt にパッチを当て、HTS Engine 依存を `OPENJTALK_BUILD_HTS_ENGINE=OFF` のようなオプションで制御可能にする。現在の `cmake/patch_r9y9_openjtalk.cmake` の仕組みを拡張して `#include "HTS_engine.h"` を条件付きにする。
2. **CI レベル:** voice ファイルの DL は最初から不要だった。phonemizer バイナリが音素抽出のみを行うのであれば、`open_jtalk -m <voice>` フォールバックをランタイムに組み込む設計自体が誤りだった (M1 の「単一パス原則」と一貫)。フォールバックなし (phonemizer 専用) の設計を最初から採用すべきだった。

### 6.4 OpenJTalk 自体のフォーク検討 (M1 6.6 との統一見解)

M1 の 6.6 節で OpenJTalk フォーク検討を記述しているが、これは M3 のビルドシステム設計と密接に関係するため、統一見解をここにも記す。

**現状の依存チェーン:**
```
piper (C++) → libopenjtalk.a → HTS_engine.h (型定義のみ) → hts_engine_stub
```

**根本的な解決策の選択肢:**

| 選択肢 | ビルドシステムへの影響 | 実現コスト |
|--------|---------------------|-----------|
| stub 維持 (現状) | `ExternalDeps.cmake` の stub ロジック ~40行を永続的に保守 | 低 |
| pyopenjtalk-plus のパッチ拡張 | `patch_r9y9_openjtalk.cmake` に `#include "HTS_engine.h"` 除去パッチを追加。stub 不要になる | 中 |
| jpreprocess (Rust) 完全移行 | CMake の OpenJTalk ビルドが不要になる。代わりに Rust ビルド (`cargo build`) の統合が必要 | 高 |

**pyopenjtalk-plus パッチ拡張の具体案:**
```cmake
# cmake/patch_r9y9_openjtalk.cmake に追加
# OpenJTalk ヘッダーから HTS_engine.h include を条件付き除去
file(GLOB_RECURSE OJ_HEADERS "${SOURCE_DIR}/lib/open_jtalk/src/*/include/*.h")
foreach(HEADER ${OJ_HEADERS})
  file(READ ${HEADER} CONTENT)
  string(REPLACE "#include \"HTS_engine.h\"" "/* HTS_engine.h removed by piper-plus */" CONTENT "${CONTENT}")
  file(WRITE ${HEADER} "${CONTENT}")
endforeach()
```

これが成功すれば `hts_engine_stub.h`, `hts_engine_stub.c`, `ExternalDeps.cmake` の stub ビルドロジック全体が不要になる。ただし、OpenJTalk の内部構造体が `HTS_Engine` 型をメンバーに持つ場合はこのパッチだけでは不十分であり、事前調査が必要。M4 以降の将来課題とする。

### 6.5 CI での voice DL は本当に必要だったか

**構造的原因の分析:** M1 のランタイムフォールバック設計が CI 設定の voice 前提を誘導した。ランタイムに voice フォールバックパスがある以上、「CI でもテストするべき」という推論は自然だった。しかしランタイムの voice パスが実質 dead branch (phonemizer バイナリが常に優先される) だったため、CI の voice 設定も dead config に過ぎなかった。これは M1 の「フォールバック設計のアンチパターン」(M1 6.1) と同根の問題であり、ランタイムの dead code が CI 設定にまで波及した例と言える。

不要だった。piper-plus の全テストは phonemizer パス (`open_jtalk_phonemizer`) または C API (`openjtalk_api.c` 経由の直接呼び出し) で動作しており、`open_jtalk` バイナリのフォールバックパスはCIで一度もテストされていなかった。`OPENJTALK_VOICE="dummy.htsvoice"` の設定は、実際には存在しないファイルを指しており、voice パス検索が NULL を返す結果、テストは voice なしで実行されていた。つまり CI における voice 関連の設定は全て dead code だった。

**教訓:** CI に環境変数を追加するときは、その変数を削除してもテストが通るかを検証すべき。通るならその変数は不要である。

### 6.6 ExternalProject パターンの長所短所

**長所:**
- ビルド時にソースを取得するため、リポジトリにサードパーティコードを含める必要がない
- バージョンピン (`URL_HASH`) で再現性を保証
- `BUILD_BYPRODUCTS` でターゲット成果物を宣言でき、Ninja 等のビルドシステムと互換
- 異なるビルドシステム (autotools, CMake) のライブラリを統一的に扱える

**短所:**
- CI でのネットワーク依存。SourceForge の可用性に左右される (`DOWNLOAD_TRIES 3` で緩和)
- Windows と Unix でビルド方法が分岐する (`if(WIN32)` / `else()`)。HTS Engine では CMake vs autotools の2パスが必要だった
- ビルドキャッシュが効きにくい。ccache はリビルドを高速化するが、ExternalProject の download + configure は毎回実行される
- 依存間の並列 download でレースコンディションが発生する (MEMORY.md に記載の既知問題)

**改善案:** CMake の `FetchContent` (3.11+) を使えば、ExternalProject よりもターゲット統合が自然になる。ただし FetchContent は configure フェーズでダウンロードを行うため、ビルド時ダウンロードが必要な場合は ExternalProject の方が適切。piper-plus の場合、依存ライブラリ (fmt, spdlog, OpenJTalk) はすべて CMake 対応であり、FetchContent への移行が可能。ただし OpenJTalk は pyopenjtalk-plus の tar.gz から SOURCE_SUBDIR で取り出す特殊なパターンを使っており、FetchContent では対応が難しい。

### 6.7 第2回設計レビュー結果からの追加タスク (2026-04-11)

5 チームによる M1/M2 設計レビューから M3 に追加すべきタスクが特定された。

#### 追加タスク 3.8: `#if 0` CI lint ガード :white_check_mark:

**ファイル:** `.github/workflows/_build-test-cpp.yml`
**状態:** 完了 (commit fcea77a2)
**目的:** C++ ソースコードでの `#if 0` ブロック蓄積を CI で自動検出し、dead code の長期残存を構造的に防止する。M1 で除去された 139 行の `#if 0` ブロックの再発を防止する。

```yaml
- name: Check for dead code markers
  run: |
    if grep -rn '#if 0' src/cpp/ --include="*.c" --include="*.cpp" --include="*.h"; then
      echo "FAIL: #if 0 blocks found in C++ source. Remove dead code or use feature flags."
      exit 1
    fi
```

**優先度:** 高 — 根本原因 (静的解析 CI の不在) に対する即効的対策

#### 追加タスク 3.9: Docker `cpp-dev` HTS Engine ビルドに用途説明追加 :white_check_mark:

**ファイル:** `docker/cpp-dev/Dockerfile`
**状態:** 完了 (commit fcea77a2) — コメント追加。ビルド自体はシステム `open_jtalk` バイナリに必要なため維持。
**目的:** Docker 開発環境の HTS Engine ビルドの用途を明確にし、将来の除去判断を容易にする。

#### 追加タスク 3.10: `hts_engine_stub` 残存理由のインラインコメント :white_check_mark:

**ファイル:** `src/cpp/tests/CMakeLists.txt`, `cmake/PiperLink.cmake`
**状態:** 完了 (commit fcea77a2)
**目的:** stub リンク箇所に「なぜ stub が必要か」のコメントを追加し、将来のメンテナーの混乱を防止する。

```cmake
# hts_engine_stub: OpenJTalk ヘッダーが HTS_engine.h を transitively include するため、
# 型定義互換シムとしてリンクが必要。HTS 合成機能は一切使用しない。
target_link_libraries(${TEST_NAME} PRIVATE hts_engine_stub)
```

#### 追加タスク 3.11: CompilerSettings.cmake の `USE_HTS_ENGINE_STUB` 強制設定の除去 :white_check_mark:

**ファイル:** `cmake/CompilerSettings.cmake` (L41, L57), `cmake/ios.toolchain.cmake` (L25)
**状態:** 完了 (commit fcea77a2)
**目的:** Android/iOS の `set(USE_HTS_ENGINE_STUB ON CACHE BOOL "" FORCE)` は冗長 (ON がデフォルト)。除去して CMake の統一性を向上させる。

### 6.8 やってはいけないこと / 次回はこうする

**やってはいけないこと:**

1. **CI に「存在しないファイルを指す」環境変数を設定する。** `OPENJTALK_VOICE="dummy.htsvoice"` は意図が不明瞭で、テスト結果の解釈を困難にする
2. **CMake の `option()` を「いつか使うかもしれない」理由で残す。** `USE_HTS_ENGINE_STUB=OFF` パスは誰も使っていなかったが、オプションが存在するだけで「OFF にすれば実 HTS Engine が使える」という誤解を招いた
3. **ExternalProject の手動前処理を CI に書く。** `build-piper.yml` の stub 手動作成は、CMake 側が自動処理する内容と完全に重複していた。ビルドシステムの責務を CI yml に漏洩させない
4. **`add_dependencies()` と `target_link_libraries()` を冗長に両方指定する。** `target_link_libraries` で CMake が依存解決するため、`add_dependencies` は ExternalProject ターゲット (CMake 管理外) にのみ使う

**次回はこうする:**

1. ビルドオプションを追加する際は、ON/OFF 両方の CI ビルドマトリクスを設定する。使われないパスを検出できる
2. `cmake --graphviz` を CI に組み込み、依存グラフの変化を PR diff で確認できるようにする
3. stub やシムを導入する際は、不要になる条件を Issue に記録し、定期的にレビューする

### 6.8 パフォーマンス正の影響

HTS voice 依存除去による定量的な改善を計測すべき:

| 項目 | Before | After (予測) | 計測方法 |
|------|--------|-------------|---------|
| CI ビルド時間 | HTS Engine DL + ビルド ~30s | 0s | CI ログの該当ステップ時間を比較 |
| voice ファイル DL | ~50MB (SourceForge) | 0MB | CI ネットワーク転送量 |
| `cmake --build` 時間 | HTS Engine ビルド含む | stub のみ (差分は微小) | `time cmake --build build` |

**注意:** これらは M3 単体の効果。M1/M2 の効果 (dead code 除去によるバイナリサイズ変化) は微小と予測される。

## 7. 後続タスクへの連絡事項

### M4 (テスト追加 + クリーンアップ) への連絡

1. **`USE_HTS_ENGINE_STUB` オプションの完全除去を検討:** M3 完了後、`USE_HTS_ENGINE_STUB` は常に ON でなければならない。M4 で `option()` 宣言を削除し、stub ビルドを無条件化することを検討する。その場合、`if(USE_HTS_ENGINE_STUB)` ガードも除去する。

2. **`hts_engine_external` ターゲットの除去を検討:** M3 では `ExternalDeps.cmake` L139 の `add_custom_target(hts_engine_external DEPENDS hts_engine_stub)` を維持している。M4 でこのターゲットを削除し、全ての `add_dependencies(... hts_engine_external)` を直接 `hts_engine_stub` に置き換えることを検討する。

3. **`PiperLink.cmake` L4 のコメント更新:** `HTS_ENGINE_DIR` への言及がコメントに残っている。M4 でコメントを更新する。

4. **CI 検証ステップの追加:** M4 で `_build-test-cpp.yml` に `USE_HTS_ENGINE_STUB=OFF` の拒否テストを追加することを推奨:
   ```yaml
   - name: Verify HTS Engine stub is required
     run: |
       if cmake -B build-test-off -DUSE_HTS_ENGINE_STUB=OFF 2>&1 | grep -q "FATAL_ERROR"; then
         echo "PASS: USE_HTS_ENGINE_STUB=OFF correctly rejected"
       else
         echo "FAIL: USE_HTS_ENGINE_STUB=OFF should be rejected"
         exit 1
       fi
   ```

5. **`examples/test_japanese_tts.sh` の削除:** このスクリプトは HTS voice を前提としており、M3 のスコープ外とした。M4 で削除または phonemizer ベースに書き換える。
