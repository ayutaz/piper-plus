# C API 共有ライブラリ — マイルストーン (Issue #295)

> **要求定義書:** [c-api-shared-library.md](c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](c-api-technical-investigation.md)
> **チケット:** [docs/tickets/](../tickets/)
> **Date:** 2026-04-03

---

## 概要

| Phase | 内容 | チケット数 | Status |
|-------|------|-----------|--------|
| Phase 1 | 基本 C API (MVP) — ワンショット合成 + 3 プラットフォームビルド | 8 | Open |
| Phase 2 | ストリーミング + テスト | 6 | Open |
| Phase 3 | 配布 | 6 | Open |
| Phase 4 | 拡張 (将来) | 6 | Open |
| **合計** | | **26** | |

---

## Phase 1: 基本 C API (MVP)

### 依存関係グラフ

```
M1-1 (-fPIC)  ──────────────────────────────┐
                                             v
M1-5 (piper_plus.h) ──┬──> M1-4 (CMake + OBJECT lib) ──┐
                       │                                 │
M1-2 (-static-libstdc++)                                 v
                                                  M1-6 (C API 実装)
M1-3 (dict_dir) ─────────────────────────────────┘      │
                                                         v
                                                  M1-7 (テスト)
                                                         │
                                                         v
                                                  M1-8 (CI)
```

---

### M1-1: ExternalProject に `-fPIC` を追加

> **チケット:** [M1-1-fpic.md](../tickets/M1-1-fpic.md)

**見積り:** 小

**変更対象:** `CMakeLists.txt`

**変更内容:**
- `openjtalk_external` の `OPENJTALK_CMAKE_ARGS` に `-DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON` 追加
- `spdlog_external` の `CMAKE_ARGS` に `-DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON` 追加
- `hts_engine_stub` に `set_target_properties(... POSITION_INDEPENDENT_CODE ON)` 追加
- `hts_engine_external` (autotools) の `CONFIGURE_ENV` に `CFLAGS=-fPIC` 追加

**依存関係:** なし (最初に着手)

**受け入れ基準:**
- Linux x86_64 で `-DPIPER_PLUS_BUILD_SHARED=ON` のビルドが `-fPIC` リンクエラーなしで成功
- macOS / Windows のビルドが回帰しない

---

### M1-2: `-static-libstdc++` を共有ライブラリに適用しない

> **チケット:** [M1-2-static-libstdcpp.md](../tickets/M1-2-static-libstdcpp.md)

**見積り:** 小

**変更対象:** `CMakeLists.txt`

**変更内容:**
- `-static-libgcc -static-libstdc++` を `piper` (実行ファイル) のみに適用
- `piper_plus` (共有ライブラリ) には適用しない

**依存関係:** M1-4 と同時に実装

**受け入れ基準:**
- `ldd libpiper_plus.so` で `libstdc++.so` が動的リンクされている
- `piper` 実行ファイルは従来通り静的リンク

---

### M1-3: `PiperPlusConfig` に `dict_dir` フィールド追加

> **チケット:** [M1-3-dict-dir.md](../tickets/M1-3-dict-dir.md)

**見積り:** 中

**変更対象:** `src/cpp/piper_plus.h`, `src/cpp/piper_plus_c_api.cpp`

**変更内容:**
- `PiperPlusConfig` に `const char *dict_dir` フィールド追加
- `piper_plus_create()` で `dict_dir` が非 NULL なら `setenv("OPENJTALK_DICTIONARY_PATH", ...)` を設定
- `dict_dir = NULL` の場合は既存の自動検出にフォールバック

**依存関係:** M1-5 (ヘッダー)

**受け入れ基準:**
- `dict_dir` を指定した場合、その辞書が使用される
- NULL の場合は既存の自動検出にフォールバック
- ヘッダーに「共有ライブラリ利用時は `dict_dir` の明示指定を推奨」と記載

**技術的背景:** 共有ライブラリでは `getExeDir()` がホストアプリのパスを返すため、辞書自動検出が機能しない (技術調査 5.1)

---

### M1-4: CMake `PIPER_PLUS_BUILD_SHARED` + OBJECT ライブラリ

> **チケット:** [M1-4-cmake-shared.md](../tickets/M1-4-cmake-shared.md)

**見積り:** 大

**変更対象:** `CMakeLists.txt`

**変更内容:**
- `option(PIPER_PLUS_BUILD_SHARED "Build piper-plus shared library" OFF)` 追加
- `piper_common` OBJECT ライブラリ定義 (ソース一元管理、`POSITION_INDEPENDENT_CODE ON`)
- 既存 `piper` / `test_piper` を `piper_common` から構成するようリファクタ
- `OPENJTALK_DIC_PATH` コンパイル定義を `piper_common` から除外し、消費側で個別設定
- `piper_plus` SHARED ライブラリターゲット定義:
  - visibility: hidden デフォルト + `PIPER_PLUS_BUILDING_DLL`
  - SOVERSION 1, VERSION `${piper_version}`
  - プラットフォーム別 RPATH: Linux `$ORIGIN`, macOS `@loader_path`, Windows `copy_dlls_to_target`
- GNUInstallDirs 導入 (M3-1 から前倒し統合)
- EXPORT PiperPlusTargets (M3-1 / M3-3 から前倒し統合)
- install ターゲット: `${CMAKE_INSTALL_LIBDIR}` + `${CMAKE_INSTALL_INCLUDEDIR}`

**依存関係:** M1-1 (-fPIC)

**受け入れ基準:**
- `-DPIPER_PLUS_BUILD_SHARED=ON` で `.so` / `.dylib` / `.dll` がビルドされる
- `-DPIPER_PLUS_BUILD_SHARED=OFF` (デフォルト) で従来通り `piper` のみビルド
- 既存の `piper` / `test_piper` のビルドが回帰しない
- `nm -D libpiper_plus.so | grep ' T '` で `piper_plus_` プレフィックスのみエクスポート
- `cmake --install build --prefix /tmp/install` で `${CMAKE_INSTALL_LIBDIR}`, `${CMAKE_INSTALL_INCLUDEDIR}` に正しく配置される

---

### M1-5: `piper_plus.h` ヘッダー作成

> **チケット:** [M1-5-header.md](../tickets/M1-5-header.md)

**見積り:** 中

**変更対象:** `src/cpp/piper_plus.h` (新規)

**変更内容:**
- `PIPER_PLUS_API` export マクロ
- `PIPER_PLUS_API_VERSION 1` + ステータスコード定数 (`OK`, `ERR`, `ERR_MODEL`, `ERR_CONFIG`, `ERR_TEXT`, `ERR_BUSY`)
- `PiperPlusConfig`: `model_path`, `config_path`, `provider`, `num_threads`, `gpu_device_id`, `dict_dir`, `_reserved[7]`
- `PiperPlusSynthOptions`: `speaker_id`, `language_id`, `noise_scale`, `length_scale`, `noise_w`, `sentence_silence_sec`, `_reserved[8]`
- Phase 1 関数宣言: `create`, `free`, `synthesize`, `free_audio`, `default_options`, `version`, `api_version`, `get_last_error`, `sample_rate`, `num_speakers`, `num_languages`, `language_id`
- スレッドセーフティ・排他制約のドキュメントコメント

**依存関係:** なし (M1-4 と並行可能)

**受け入れ基準:**
- C (`gcc -std=c99`) と C++ (`g++ -std=c++17`) の両方でコンパイルエラーなし
- Dart `ffigen` 互換 (POD struct + opaque pointer のみ)

---

### M1-6: `piper_plus_c_api.cpp` 実装

> **チケット:** [M1-6-c-api-impl.md](../tickets/M1-6-c-api-impl.md)

**見積り:** 大

**変更対象:** `src/cpp/piper_plus_c_api.cpp` (新規)

**変更内容:**
- `PiperPlusEngine` 内部構造体: `PiperConfig`, `Voice`, `inProgress` フラグ
- `thread_local std::string g_last_error`
- `PIPER_PLUS_TRY` / `PIPER_PLUS_CATCH` マクロ
- **`piper_plus_create`**: NULL チェック → dict_dir 設定 → config_path 自動生成 → `loadVoice()`
- **`piper_plus_synthesize`**: 再入チェック → `synthesisConfig` save/restore → `textToAudio()` → int16→float32 → `malloc()` 確保
- **`piper_plus_free_audio`**: `free()`
- **クエリ関数**: `sample_rate`, `num_speakers`, `num_languages`, `language_id`

**依存関係:** M1-5 (ヘッダー), M1-4 (CMake)

**受け入れ基準:**
- create → synthesize → free のライフサイクルが正常動作
- `synthesisConfig` が呼び出し後に復元される (`languageId` 未復元バグの回避)
- 合成中の再入は `PIPER_PLUS_ERR_BUSY` を返す
- 不正なモデルパスで `create` → NULL + `get_last_error()` でメッセージ取得可能
- NULL ポインタを全関数に渡してもクラッシュしない

---

### M1-7: C API 単体テスト (モデル不要)

> **チケット:** [M1-7-unit-tests.md](../tickets/M1-7-unit-tests.md)

**見積り:** 中

**変更対象:** `src/cpp/tests/test_c_api.cpp` (新規), `src/cpp/tests/CMakeLists.txt`

**テストケース:**
- `TestVersion`: `version()` が非 NULL、`api_version()` が定数と一致
- `TestDefaultOptions`: デフォルト値の確認
- `TestNullSafety`: `create(NULL)` → NULL、`synthesize(NULL)` → ERR、`free(NULL)` → クラッシュなし
- `TestInvalidModelPath`: 存在しないパス → NULL + エラーメッセージ
- `TestErrorMessage`: エラー発生後に `get_last_error()` が非 NULL
- `TestQueryNullEngine`: `sample_rate(NULL)` → 0

**依存関係:** M1-6 (実装)

**受け入れ基準:**
- 全テストが 3 プラットフォームで PASS
- モデルファイル不要

---

### M1-8: CI 統合 (3 プラットフォームビルド検証)

> **チケット:** [M1-8-ci.md](../tickets/M1-8-ci.md)

**見積り:** 中

**変更対象:** `.github/workflows/cpp-tests.yml`

**変更内容:**
- trigger paths に `piper_plus.h`, `piper_plus_c_api.cpp` 追加
- 共有ライブラリビルドステップ追加 (`-DPIPER_PLUS_BUILD_SHARED=ON`)
- シンボル可視性検証 (`nm -D` / `nm -gU` / `dumpbin /EXPORTS`)
- C API テスト実行

**依存関係:** M1-4 (CMake), M1-7 (テスト)

**受け入れ基準:**
- ubuntu-latest, macos-latest, windows-latest で CI GREEN

### Phase 1 振り返り: 一から設計するなら

> 詳細は [M1-8-ci.md](../tickets/M1-8-ci.md#phase-1-全体の振り返り-一から設計するなら) を参照。

**設計判断の再検討:**

1. **チケット粒度**: M1-1 (fPIC) と M1-2 (static-libstdc++) は独立チケットにしたが、M1-4 (CMake) の前提条件として同一チケットにまとめても良かった。ビルドシステムの変更を1箇所に集約できる。
   > **対応済み:** M1-1, M1-2 に「M1-4 と同一 PR で対応すること」の注記を追加。M1-3, M1-5 に「M1-6 と同一 PR で対応すること」の注記を追加。

2. **依存グラフの簡素化**: M1-5 (ヘッダー) → M1-6 (実装) → M1-7 (テスト) → M1-8 (CI) の直列チェーンは、ヘッダーのレビューと実装を並行できる構造に変えられた。

3. **リスク駆動の優先順位**: `-fPIC` は Linux でしか問題にならないが、最初に着手する設計は正しい。ビルドが通らなければ何も始まらない。
   > **対応済み:** M1-6 の実装詳細セクション先頭に「高リスク項目 (最優先)」として languageId 未復元・辞書パス自動検出・再入問題の 3 項目を明示配置。

4. **RPATH / install を Phase 1 に含めるべきだったか**: Phase 3 の M3-1 (install) と M3-4 (RPATH) は M1-4 の一部として設計できた。Phase 1 を「ビルドできる + テストできる」に限定したのは MVP としては妥当だが、配布を考えると早期に install を整備した方が手戻りが少ない。
   > **対応済み:** M1-4 に RPATH 設定 (`$ORIGIN` / `@loader_path`)、GNUInstallDirs 導入、EXPORT PiperPlusTargets を統合。M3-1 は配布固有の install ルール (ORT 同梱、辞書) のみに縮小。M3-4 は ORT install_name 修正 + 検証のみに縮小。

---

## Phase 2: ストリーミング + テスト

### 依存関係グラフ

```
M1-8 (Phase 1 完了)
    │
    v
M2-1 (音素化ループ抽出) ──> M2-2 (Iterator) ──┬──> M2-4 (ストリーミングテスト)
                                                │         │
                                          M2-3 (Callback) │
                                                          v
                                                   M2-5 (統合テスト)
                                                          │
                                                          v
                                                   M2-6 (CI 更新)
```

---

### M2-1: `textToAudio` の音素化ループを再利用可能関数に抽出

> **チケット:** [M2-1-phonemize-extract.md](../tickets/M2-1-phonemize-extract.md)

**見積り:** 中

**変更対象:** `src/cpp/piper.cpp`, `src/cpp/piper.hpp`

**変更内容:**
- `textToAudio()` (L1067-1309) の音素化 → phoneme_ids 変換ループを `phonemizeText()` 関数に抽出
- 文分割ロジック (`textToAudioStreaming` L1689-1729) も再利用可能に
- 既存の `textToAudio` / `textToAudioStreaming` は抽出関数を呼ぶようリファクタ

**依存関係:** Phase 1 完了

**受け入れ基準:**
- 既存テストが回帰しない
- 抽出関数が `piper.hpp` で宣言され、C API から利用可能

**技術的背景:** Iterator パターンでは文単位の逐次合成が必要だが、`textToAudio` は一括処理。音素化ループの抽出が前提 (技術調査 5.2)

---

### M2-2: Iterator パターン (`synth_start` / `synth_next`)

> **チケット:** [M2-2-iterator.md](../tickets/M2-2-iterator.md)

**見積り:** 大

**変更対象:** `src/cpp/piper_plus.h`, `src/cpp/piper_plus_c_api.cpp`

**変更内容:**
- `PiperPlusAudioChunk` 構造体をヘッダーに追加
- `PiperPlusEngine` に `IteratorState` (文分割結果キュー、currentChunkSamples) 追加
- `piper_plus_synth_start`: テキスト文分割 → キュー保持、`synthesisConfig` save
- `piper_plus_synth_next`: 1 文ずつ `textToAudio` → float 変換 → チャンク返却、最終チャンクで `is_last=1` + `PIPER_PLUS_DONE`

**依存関係:** M2-1 (音素化ループ抽出)

**受け入れ基準:**
- `synth_start` → 複数回 `synth_next` → `PIPER_PLUS_DONE` のフローが正常動作
- `out_chunk->samples` が次の `synth_next` まで有効
- Iterator 中の `synthesize` 呼び出しは `PIPER_PLUS_ERR_BUSY`

---

### M2-3: コールバック合成 (`synthesize_streaming`)

> **チケット:** [M2-3-callback-streaming.md](../tickets/M2-3-callback-streaming.md)

**見積り:** 小

**変更対象:** `src/cpp/piper_plus.h`, `src/cpp/piper_plus_c_api.cpp`

**変更内容:**
- `PiperPlusAudioCallback` typedef をヘッダーに追加
- `piper_plus_synthesize_streaming`: M2-2 の Iterator を内部で駆動し、チャンクごとにコールバック呼び出し

**依存関係:** M2-2 (Iterator)

**受け入れ基準:**
- コールバックがチャンクごとに呼ばれる
- `user_data` が正しく転送される

---

### M2-4: ストリーミング単体テスト (モデル不要)

> **チケット:** [M2-4-streaming-tests.md](../tickets/M2-4-streaming-tests.md)

**見積り:** 中

**変更対象:** `src/cpp/tests/test_c_api.cpp`

**テストケース:**
- `TestSynthStartNullEngine`: NULL エンジン → ERR
- `TestSynthNextWithoutStart`: start なしの next → ERR
- `TestStreamingNullCallback`: NULL コールバック → ERR
- `TestSynthStartBusyDuringSynthesize`: one-shot 合成中の start → ERR_BUSY
- `TestAudioChunkStruct`: `PiperPlusAudioChunk` のフィールドサイズ・アラインメント確認

**依存関係:** M2-2, M2-3

**受け入れ基準:**
- 全テストが 3 プラットフォームで PASS

---

### M2-5: 統合テスト (モデル必要)

> **チケット:** [M2-5-integration-tests.md](../tickets/M2-5-integration-tests.md)

**見積り:** 中

**変更対象:** `src/cpp/tests/test_c_api_integration.cpp` (新規)

**テストケース:**
- ワンショット合成 → 音声サンプル数 > 0、サンプルレート確認
- Iterator → 全チャンクのサンプル数合計 ≈ ワンショットのサンプル数
- ストリーミング → コールバック呼び出し回数 ≥ 1
- speaker_id 変更 → 異なる音声出力
- language_id 自動検出 → 日本語/英語テキストで正常動作
- `language_id("ja")` → 0 (つくよみちゃんモデル基準)
- シンボル可視性 (`nm -D` で内部シンボル非公開を確認)

**依存関係:** M2-4

**受け入れ基準:**
- テストモデル (`test/models/multilingual-test-medium.onnx`) で全テスト PASS
- モデル未存在時は SKIP (`return 77`)

---

### M2-6: CI 統合更新

> **チケット:** [M2-6-ci-update.md](../tickets/M2-6-ci-update.md)

**見積り:** 中

**変更対象:** `.github/workflows/cpp-tests.yml`

**変更内容:**
- ストリーミングテスト追加
- 統合テスト (モデルあり) の追加
- テストモデルのキャッシュ設定

**依存関係:** M2-4, M2-5

**受け入れ基準:**
- 3 プラットフォームで CI GREEN

### Phase 2 振り返り: 一から設計するなら

> 詳細は [M2-6-ci-update.md](../tickets/M2-6-ci-update.md#phase-2-全体の振り返り-一から設計するなら) を参照。

**設計判断の再検討:**

1. **`textToAudioStreaming` のマルチリンガルデッドコード**: `usesOpenJTalk()` が `MultilingualPhonemes` でも true を返すためデッドコード。Iterator を `textToAudio` ベースにした判断は正しい。
   > **対応済み:** M2-1 にデッドコード警告コメント + 将来の廃止計画セクション (2.6) を追加。M2-6 後続タスクに `textToAudioStreaming` の Iterator 駆動移行を Phase 4 候補として記載。

2. **文分割ロジックの抽出**: M2-1 で音素化ループの抽出を前提としたが、`textToAudio` を文単位で呼ぶだけの方がシンプルだった可能性がある。抽出のリファクタリングコストと、文分割の正確性のトレードオフ。
   > **対応済み:** M2-1 懸念事項に「文分割の多言語対応不足」を追記。M2-6 後続タスクに多言語文分割の精度向上を Phase 4 候補として記載。

3. **Iterator vs Callback の優先順位**: Iterator (M2-2) を先にし Callback (M2-3) を薄いラッパーにした設計は、実装の重複を避ける点で正しい。ただし Flutter/Dart (主要ユースケース) は Callback を使うので、M2-3 のテスト密度を上げるべき。

4. **Iterator の crossfade 非対応**: `textToAudio` ベースの Iterator は crossfade を行わず、ワンショットとの音質差が出る可能性がある。
   > **対応済み:** M2-2 懸念事項に crossfade 非対応の音質差リスクと `sentence_silence_sec` による対策を明記。M2-6 後続タスクに crossfade 対応 Iterator を Phase 4 候補として記載。

---

## Phase 3: 配布

### 依存関係グラフ

```
Phase 2 完了
    │
    v
M3-1 (install manifest) ──┬──> M3-2 (pkg-config) ──────┬──> M3-6 (examples)
                           │                             │
                           ├──> M3-3 (CMake Config) ─────┤
                           │                             │
                           └──> M3-4 (RPATH fix) ────────┘
                                    │
                                    v
                              M3-5 (release workflow) ──> M3-6 (examples)
```

---

### M3-1: 配布ファイルマニフェスト + install ターゲット整備

> **チケット:** [M3-1-install-manifest.md](../tickets/M3-1-install-manifest.md)
>
> **注意 (振り返り反映):** GNUInstallDirs 導入、EXPORT PiperPlusTargets、piper_plus 基本 install ターゲットは M1-4 で対応済み。本チケットは配布固有の install ルール (ONNX Runtime 同梱、辞書 install、検証スクリプト) のみを対象とする。

**見積り:** 中

**変更対象:** `CMakeLists.txt`

**配布レイアウト:**
```
lib/libpiper_plus.so(.1)(.1.10.0) | .dylib | .dll + .lib  (M1-4 で install 済み)
lib/libonnxruntime.so | .dylib | .dll                      (本チケット)
include/piper_plus.h                                        (M1-4 で install 済み)
share/open_jtalk/dic/                                       (本チケット)
share/piper/dicts/ (CMU, pinyin)                            (本チケット)
lib/pkgconfig/piper_plus.pc                                 (M3-2)
lib/cmake/PiperPlus/                                        (M3-3)
```

**依存関係:** Phase 2 完了

---

### M3-2: pkg-config ファイル生成

> **チケット:** [M3-2-pkg-config.md](../tickets/M3-2-pkg-config.md)

**見積り:** 小

**変更対象:** `cmake/piper_plus.pc.in` (新規), `CMakeLists.txt`

**依存関係:** M3-1

---

### M3-3: CMake Config パッケージ生成

> **チケット:** [M3-3-cmake-config.md](../tickets/M3-3-cmake-config.md)

**見積り:** 中

**変更対象:** `cmake/PiperPlusConfig.cmake.in` (新規), `CMakeLists.txt`

利用側: `find_package(PiperPlus)` + `target_link_libraries(app PiperPlus::piper_plus)`

**依存関係:** M3-1

---

### M3-4: macOS RPATH 修正 + プラットフォーム別リンク設定

> **チケット:** [M3-4-rpath-fix.md](../tickets/M3-4-rpath-fix.md)
>
> **注意 (振り返り反映):** piper_plus の RPATH 設定 (Linux `$ORIGIN`, macOS `@loader_path`) は M1-4 で対応済み。本チケットは ONNX Runtime の install_name 修正 (macOS) と install 後の RPATH 検証のみを対象とする。

**見積り:** 小

**変更対象:** `CMakeLists.txt`

**変更内容:**
- ~~macOS: `INSTALL_RPATH "@loader_path"`~~ (M1-4 で対応済み)
- ~~Linux: `INSTALL_RPATH "$ORIGIN"`~~ (M1-4 で対応済み)
- macOS: ONNX Runtime dylib の install_name を `@rpath/...` に修正
- install 後の RPATH 検証テスト

**依存関係:** M3-1

---

### M3-5: リリースワークフロー拡張

> **チケット:** [M3-5-release-workflow.md](../tickets/M3-5-release-workflow.md)

**見積り:** 大

**変更対象:** `.github/workflows/` (新規 or 既存 `dev-build-all.yml` 拡張)

**配布プラットフォーム:**
- Linux x86_64, Linux aarch64
- macOS arm64
- Windows x64

**依存関係:** M3-1, M3-4

---

### M3-6: 使用例ドキュメント

> **チケット:** [M3-6-examples.md](../tickets/M3-6-examples.md)

**見積り:** 中

**変更対象:** `examples/c-api/` (新規)

**サンプル:**
- `basic.c`: create → synthesize → WAV 保存 → free
- `streaming.c`: streaming callback で逐次再生
- `multi_language.c`: 多言語合成デモ

**依存関係:** M3-2, M3-3

### Phase 3 振り返り: 一から設計するなら

> 詳細は [M3-6-examples.md](../tickets/M3-6-examples.md#phase-3-全体の振り返り-一から設計するなら) を参照。

**設計判断の再検討:**

1. **RPATH / install を Phase 1 に含めるべきだった**: M3-1 (install) と M3-4 (RPATH) は M1-4 の一部として設計できた。Phase 3 は実質 4 チケットで済んだはず。
   > **対応済み:** RPATH 設定、GNUInstallDirs、EXPORT PiperPlusTargets を M1-4 に統合。M3-1 は配布固有ルール (ORT 同梱、辞書) のみ、M3-4 は ORT install_name 修正 + 検証のみに縮小。

2. **pkg-config + CMake Config 両方の必要性**: Godot GDExtension (SCons) のために pkg-config は必須。CMake Config は CMake ユーザー向け。両方の提供コストは低いので両立は正しい。

3. **リリースワークフローの自動化範囲**: 既存の `build-piper.yml` に input 追加するのが最も低コスト。独立ワークフローを作ると保守が二重化する。
   > **対応済み (3a):** M3-5 にセクション 7「CLI パッケージングの cmake --install 移行計画」を追加。共有ライブラリのみ `cmake --install` を使い、CLI 側は後続タスクとして記載。
   > **対応済み (3b):** M3-5 にセクション 8「ワークフロー設計の判断」を追加。統合 vs 分離のトレードオフを明記し、初期は統合、将来的に composite action + 分離を推奨。
   > **対応済み (3c):** M3-5 にセクション 9「リリースアセット検証ステップ」を追加。ダウンロード → 展開 → layout 検証 → サンプルビルド → smoke テストのパイプラインを記載。

---

## Phase 4: 拡張 (将来)

全チケット独立実装可能。優先度は利用者フィードバックに基づく。

### M4-1: カスタム辞書 API

> **チケット:** [M4-1-custom-dict.md](../tickets/M4-1-custom-dict.md)

**見積り:** 中

`piper_plus_load_custom_dict(engine, path)` / `piper_plus_clear_custom_dict(engine)` を追加。既存の `custom_dictionary.cpp` を C API でラップ。

---

### M4-2: Phoneme timing 出力

> **チケット:** [M4-2-phoneme-timing.md](../tickets/M4-2-phoneme-timing.md)

**見積り:** 中

`piper_plus_get_phoneme_timing(engine, ...)` で合成後の音素タイミング情報を取得。`SynthesisResult.phonemeTimings` をラップ。

---

### M4-3: G2P 単独利用 API

> **チケット:** [M4-3-g2p-api.md](../tickets/M4-3-g2p-api.md)

**見積り:** 中

`piper_plus_phonemize(engine, text, language)` でテキスト→音素変換のみ実行。Rust `piper-plus-g2p` の `ffi.rs` を参考設計。

---

### M4-4: Android NDK ビルド

> **チケット:** [M4-4-android-ndk.md](../tickets/M4-4-android-ndk.md)

**見積り:** 大

CMake ツールチェインファイルで Android arm64-v8a ビルド対応。ONNX Runtime Android 版 (aar) との統合。

---

### M4-5: int16/float32 二重変換の解消

> **チケット:** [M4-5-float32-direct.md](../tickets/M4-5-float32-direct.md)

**見積り:** 中

`piper::synthesize()` に float 出力バリアントを追加し、int16→float32 の変換ステップを排除。精度向上 + CPU コスト削減。

---

### M4-6: `dladdr` による辞書自動検出改善

> **チケット:** [M4-6-dladdr-dict.md](../tickets/M4-6-dladdr-dict.md)

**見積り:** 中

`dict_dir = NULL` 時に `dladdr()` (Linux/macOS) / `GetModuleHandleEx(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS)` (Windows) でライブラリ自身のパスを取得し、相対パスで辞書を検索。Phase 1 の `dict_dir` 明示指定から自動検出への改善。

### Phase 4 振り返り: 一から設計するなら

> 詳細は [M4-6-dladdr-dict.md](../tickets/M4-6-dladdr-dict.md#phase-4-全体の振り返り-一から設計するなら) を参照。

**設計判断の再検討:**

1. **拡張 API の優先順位**: 利用者フィードバック前に全 6 チケットの優先度を決めるのは難しい。M4-6 (dladdr) は Phase 1 の UX 改善として高優先、M4-5 (float32) は性能改善として中優先。

   > **対応済み (1):** 全 6 チケットのヘッダーに「利用者視点の優先度: 高/低」を追加。M4-6, M4-4 に「Phase 3 完了直後に着手推奨」注記。M4-5, M4-3 に「利用者フィードバック待ちでも可」注記。

2. **Android NDK は Phase 3 の一部にすべきだったか**: 配布プラットフォームの追加と見れば Phase 3 に含められるが、NDK 固有の課題 (ExternalProject クロスコンパイル) が大きいため独立は妥当。

   > **対応済み (2):** M4-4 にセクション 7「Phase 3 M3-5 への統合オプション」を追加。M3-5 にセクション 10「将来拡張: Android ビルド (M4-4 参照)」を追加。M3-5 の `build-android` フラグ予約 + M4-4 完了時の有効化を推奨。

3. **G2P 単独 API と Rust piper-g2p FFI の整合**: Rust 版はモデル非依存、C++ 版はエンジン依存。設計哲学が異なるため、将来的に C++ G2P を独立ライブラリ化するか検討が必要。

   > **対応済み (3):** M4-3 にセクション 7「Rust FFI との整合性」を追加。二重実装のトレードオフ (メリット・デメリット) と長期的な統合方針 (短期: 独立運用、中期: Rust FFI 呼び出し移行、長期: C++ 版 deprecated 検討) を明記。

---

## 全体スケジュール

```
Phase 1 (MVP)         Phase 2 (ストリーミング)   Phase 3 (配布)          Phase 4 (拡張)
M1-1 → M1-4 ──────→ M2-1 → M2-2 ──────────→ M3-1 ──────────────→ M4-1〜M4-6
M1-5 ↗   ↘ M1-6     M2-3 ↗  ↘ M2-4          M3-2, M3-3, M3-4      (独立)
M1-2 ↗     ↘ M1-7        M2-5 → M2-6       M3-5 → M3-6
M1-3 ↗       ↘ M1-8
```

## Phase 別サマリ

| Phase | チケット | 見積り (小/中/大) | 主要成果物 |
|-------|---------|-----------------|-----------|
| Phase 1 | M1-1〜M1-8 | 小×2 + 中×4 + 大×2 | `libpiper_plus.so/dylib/dll` + `piper_plus.h` + ワンショット合成 |
| Phase 2 | M2-1〜M2-6 | 小×1 + 中×4 + 大×1 | Iterator + callback 合成 + テストスイート |
| Phase 3 | M3-1〜M3-6 | 小×2 + 中×3 + 大×1 | バイナリ配布 + pkg-config + ドキュメント |
| Phase 4 | M4-1〜M4-6 | 中×5 + 大×1 | カスタム辞書、タイミング、G2P、Android |
