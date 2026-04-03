# C API 共有ライブラリ — 技術調査レポート

> **Issue:** [#295](https://github.com/ayutaz/piper-plus/issues/295)
> **要求定義書:** [c-api-shared-library.md](c-api-shared-library.md)
> **Date:** 2026-04-03

---

## 1. C API → C++ API マッピング

### 1.1 piper_plus_create() の実装方針

**重要な発見:** `piper::initialize()` は現状 **no-op** (spdlog::info のみ)。`PiperConfig` も空 struct。実質的な初期化は全て `loadVoice()` が行う。

**引数マッピング:**

| C API (PiperPlusConfig) | C++ API (loadVoice) | 備考 |
|---|---|---|
| `model_path` | `modelPath` | そのまま |
| `config_path` | `modelConfigPath` | NULL なら `model_path + ".json"` |
| `provider` | `useCuda` (bool) + ORT Session options | `"cuda"` → useCuda=true、`"coreml"` / `"directml"` も **実装済み (M5-6)** |
| `gpu_device_id` | `gpuDeviceId` | そのまま |
| `num_threads` | `Ort::SessionOptions::SetIntraOpNumThreads()` | **実装済み (M5-5):** 0 = ORT デフォルト (自動選択) |

**PiperPlusEngine 内部構造体:**

```cpp
struct PiperPlusEngine {
    piper::PiperConfig config;   // 空 struct (API 互換のため保持)
    piper::Voice       voice;    // ONNX Session + config + 辞書。move-only
    bool               inProgress; // 合成中フラグ (BusyGuard で自動管理, M5-1)
    IteratorState       iterState; // 文分割結果キュー + currentChunkSamples
    // ... (phoneme timing, G2P result 等の内部バッファ)
};
```

- `piper::Voice` は `Ort::Session` (move-only) を含むためコピー不可
- ヒープに `new` するので move の問題はない
- **M5-1:** `ConfigGuard` (synthesisConfig save/restore) と `BusyGuard` (inProgress 管理) の RAII ガードで例外安全性を保証

### 1.2 piper_plus_synthesize() の実装方針

**speaker_id / language_id の設定:** `voice.synthesisConfig` フィールドを直接変更 → 合成 → 復元するパターン (main.cpp の processLine と同一)。

**音声データの変換:** ONNX 出力は float → `synthesize()` で int16 → C API で float に戻す 2 重変換。~~現状は `textToAudio()` が `vector<int16_t>` を返すため回避不可。将来の最適化候補。~~ **解決済み (M4-5):** `textToAudioFloat()` / `synthesizeFloat()` で float32 直接出力パスを実装。int16 変換ステップを排除し精度向上 + CPU コスト削減。

**メモリ管理:** `malloc()` で確保 → `piper_plus_free_audio()` で `free()` 。DLL 境界越えで安全。

### 1.3 language_id = -1 (自動検出) の実装

`textToAudio()` 内部に `detectDominantLanguage()` が**既に実装済み** (piper.cpp L1270-1284)。`voice.synthesisConfig.languageId` をデフォルト値 (0) のまま渡すだけで自動検出が有効になる。追加実装不要。

### 1.4 ストリーミング (callback) の実装

`textToAudioStreaming()` の `std::function<void(const vector<int16_t>&)>` をラムダで捕捉し、`PiperPlusAudioCallback` に変換。チャンク単位で int16→float32 変換。

**注意:** `textToAudioStreaming()` は同期関数。コールバックは同じスレッドで呼ばれる。

### 1.5 Iterator パターン (synth_start/synth_next)

`textToAudioStreaming()` 内の文分割ロジックを抽出して使用:
1. `synth_start()`: テキストを文単位に分割してキューに保持
2. `synth_next()`: 1 文ずつ `textToAudio()` で合成して返す

**内部キュー不要** — コールバック→キュー変換ではなく、文分割→逐次合成の設計。libpiper (OHF-Voice) と同一パターン。

**ポインタ寿命:** `out_chunk->samples` は `IteratorState.currentChunkSamples` の内部バッファ。次の `synth_next()` まで有効。

### 1.6 textToAudioStreaming のマルチリンガル制約

**発見:** piper.cpp L1756-1761 で、マルチリンガルストリーミングが **TODO** になっている。`textToAudio()` (one-shot) は完全対応済み。

→ Iterator パターンは `textToAudio()` ベースで実装するのが安全。

> **解決済み (M5-16):** `textToAudioStreaming()` 内部を Iterator ベースに置換し、`MultilingualPhonemes` デッドコード問題を根本解決。多言語文分割も M5-2 で改善済み。

---

## 2. CMake ビルドシステム

### 2.1 OBJECT ライブラリによるソース共有

> **実装済み (M1-4, M5-15):** OBJECT ライブラリ `piper_common` で一元管理。さらに M5-15 で CMakeLists.txt を 9 つの `cmake/*.cmake` モジュールに分割。

```cmake
# cmake/PiperCommon.cmake
add_library(piper_common OBJECT ${PIPER_CORE_SOURCES})
set_target_properties(piper_common PROPERTIES POSITION_INDEPENDENT_CODE ON)

# cmake/PiperExecutable.cmake
add_executable(piper src/cpp/main.cpp src/cpp/model_manager.cpp)
target_link_libraries(piper PRIVATE piper_common ...)

# cmake/PiperPlusShared.cmake
add_library(piper_plus SHARED src/cpp/piper_plus_c_api.cpp)
target_link_libraries(piper_plus PRIVATE piper_common ...)
```

**CMake モジュール一覧 (M5-15):** `CompilerSettings.cmake`, `ExternalDeps.cmake`, `OnnxRuntime.cmake`, `PiperCommon.cmake`, `PiperPlusShared.cmake`, `PiperExecutable.cmake`, `PiperLink.cmake`, `Testing.cmake`, `Install.cmake`

### 2.2 -fPIC 問題 (最重要技術課題)

**OpenJTalk / spdlog / hts_engine_stub が `-fPIC` なしで静的ビルドされている。** Linux x86_64 で共有ライブラリにリンクするとエラーになる。

**修正:** 全 ExternalProject に `-DCMAKE_POSITION_INDEPENDENT_CODE=ON` を追加:

```cmake
# OpenJTalk
set(OPENJTALK_CMAKE_ARGS ... -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON)

# spdlog
ExternalProject_Add(spdlog_external ... CMAKE_ARGS ... -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON)

# hts_engine_stub
set_target_properties(hts_engine_stub PROPERTIES POSITION_INDEPENDENT_CODE ON)
```

macOS/Windows は影響なし (常に PIC)。パフォーマンスオーバーヘッドは 1% 未満。

### 2.3 プラットフォーム別設定

| 設定 | Linux | macOS | Windows |
|------|-------|-------|---------|
| export | `-fvisibility=hidden` | `-fvisibility=hidden` | `PIPER_PLUS_BUILDING_DLL` define |
| C++ runtime | `-static-libstdc++` | system | MSVC DLL (既存設定) |
| RPATH | `$ORIGIN` | `@rpath` + `INSTALL_NAME_DIR` | N/A |
| SOVERSION | `libpiper_plus.so.1` | `libpiper_plus.1.dylib` | `piper_plus.dll` + `.lib` |
| ORT DLL コピー | 不要 | 不要 | 既存 `copy_dlls_to_target` 流用 |

### 2.4 install ターゲット

- ヘッダー: `include/piper_plus.h`
- ライブラリ: `lib/libpiper_plus.so` (+ .1 + .1.10.0)
- pkg-config: `lib/pkgconfig/piper_plus.pc`
- CMake Config: `lib/cmake/PiperPlus/` (Phase 3)

---

## 3. スレッドローカルエラーと内部状態

### 3.1 thread_local の互換性

| コンパイラ | 対応状況 | DLL 制約 |
|-----------|---------|---------|
| MSVC 2022 | 完全対応 | .cpp 内部使用なら問題なし |
| GCC 4.8+ | 完全対応 | -fPIC 共有ライブラリで正常動作 |
| Clang 3.3+ | 完全対応 | GCC と同等 |

**piper-plus に前例あり:** `openjtalk_wrapper.c` で `__declspec(thread)` / `__thread` を既に使用。

**実装:**

```cpp
static thread_local std::string g_last_error;  // .cpp 内部に閉じる

const char* piper_plus_get_last_error(void) {
    return g_last_error.empty() ? nullptr : g_last_error.c_str();
}
```

ライフタイム: 次の API 呼び出しまで有効 (SQLite `sqlite3_errmsg()` と同じ規約)。

### 3.2 例外捕捉パターン

全 API 関数を try-catch でラップ:

```cpp
#define PIPER_PLUS_TRY try {
#define PIPER_PLUS_CATCH(retval) \
    } catch (const std::exception& e) { \
        g_last_error = e.what(); return retval; \
    } catch (...) { \
        g_last_error = "Unknown error"; return retval; \
    }
```

### 3.3 複数エンジン並行利用

- `PiperConfig` は空 struct — グローバルステートなし
- `initialize()` / `terminate()` は no-op
- 各 `Voice` が独立した `Ort::Session` + `Ort::Env` を保持
- **ほぼ安全** — 唯一の懸念は `openjtalk_dictionary_manager.c` の `static char dict_path[1024]` (初回書き込み時の理論的レース)

---

## 4. テストと CI 統合

### 4.1 既存テストの構成

- Google Test v1.14.0 (FetchContent で自動ダウンロード)
- テスト総数: 23 個
- モデルなしで実行可能なテスト多数 (phoneme_parser, security, gpu_device_id 等)
- テストモデル: `test/models/multilingual-test-medium.onnx` (存在しなければ SKIP)

### 4.2 C API テスト方針

**モデル不要のテスト (Phase 1):**

| テスト | 内容 |
|--------|------|
| NULL safety | create(NULL), synthesize(NULL, ...), free(NULL) |
| エラーメッセージ | 存在しないモデルパス → get_last_error() 確認 |
| デフォルトオプション | default_options() の値確認 |
| バージョン | version() / api_version() の戻り値確認 |
| create + free | エンジン作成→即破棄でクラッシュしないこと |

**モデル必要のテスト (Phase 2):**

| テスト | 内容 |
|--------|------|
| ライフサイクル | create → synthesize → free |
| ストリーミング | synthesize_streaming + callback 呼び出し確認 |
| Iterator | synth_start → synth_next → DONE |
| シンボル可視性 | `nm -D` で公開 API のみエクスポートされていること |

### 4.3 CI 統合方針

既存の `cpp-tests.yml` に共有ライブラリビルドオプションを追加:

```yaml
strategy:
  matrix:
    os: [ubuntu-22.04, macos-latest, windows-latest]
    build_type: [Release]
    include:
      - shared_lib: ON
```

---

## 5. 発見された技術的リスク

### 5.1 レビューで追加発見されたリスク (高) -- 全て解決済み

| リスク | 影響度 | 対策 | 解決状況 |
|--------|--------|------|---------|
| `textToAudio` が `languageId` を変更して復元しない | **高** | C API ラッパーで `synthesisConfig` を呼び出し前に保存、呼び出し後に復元 | **解決済み (M1-6 + M5-1):** `ConfigGuard` RAII で自動 save/restore。さらに M5-8 で `phonemizeText` 自体の副作用も除去 |
| 辞書パス自動検出が共有ライブラリで機能しない | **高** | `PiperPlusConfig` に `dict_dir` フィールドを追加 + `dladdr()` による自動検出 | **解決済み (M1-3 + M4-6):** `dict_dir` フィールド追加 + `library_path.h/c` で `dladdr()` / `GetModuleHandleEx` による自動検出を実装 |
| Iterator / one-shot 合成の再入問題 | **高** | エンジンに `inProgress` フラグを追加し `PIPER_PLUS_ERR_BUSY` を返す | **解決済み (M1-6 + M5-1):** `BusyGuard` RAII で自動管理。`PIPER_PLUS_ERR_BUSY` (-5) をステータスコードに追加 (M5-13) |

### 5.2 レビューで追加発見されたリスク (中) -- 全て解決済み

| リスク | 影響度 | 対策 | 解決状況 |
|--------|--------|------|---------|
| 言語名→ID 変換 API の欠如 | **中** | `piper_plus_language_id(engine, "ja")` クエリ関数を追加 | **解決済み (M1-6):** `piper_plus_language_id()` + `piper_plus_available_languages()` (M4-3) を実装 |
| `-static-libstdc++` の共有ライブラリ競合 | **中** | 共有ライブラリには `-static-libstdc++` を適用しない | **解決済み (M1-2):** `piper` (CLI) のみに適用。共有ライブラリは動的リンク |
| macOS RPATH が `@executable_path` | **中** | `INSTALL_RPATH "@loader_path"` に修正 | **解決済み (M1-4):** `@loader_path` に設定。M3-4 で ORT install_name も修正 |
| Iterator の文分割が想定より複雑 | **中** | `textToAudio` の音素化ループを再利用可能関数に抽出 | **解決済み (M2-1):** `phonemizeText()` / `splitTextToSentences()` を抽出。M5-2 で多言語文分割も改善 |
| `OPENJTALK_DIC_PATH` コンパイル定義が OBJECT ライブラリと非互換 | **中** | 消費側 target で個別設定 | **解決済み (M1-4):** OBJECT ライブラリから除外、消費側で個別設定 |

### 5.3 初回調査で発見済みのリスク -- 全て解決済み

| リスク | 影響度 | 対策 | 解決状況 |
|--------|--------|------|---------|
| OpenJTalk/spdlog の -fPIC 不足 | **高** | ExternalProject に `CMAKE_POSITION_INDEPENDENT_CODE=ON` 追加 | **解決済み (M1-1)** |
| int16→float32 2 重変換 | 低 | float 出力バリアントを追加 | **解決済み (M4-5):** `textToAudioFloat()` / `synthesizeFloat()` で float32 直接出力パスを実装 |
| textToAudioStreaming のマルチリンガル未対応 | 中 | Iterator は textToAudio ベースで実装 | **解決済み (M5-16):** `textToAudioStreaming()` 内部を Iterator ベースに置換し根本解決 |
| 辞書パス初期化のレース条件 | 低 | ドキュメントで「初回 create は単一スレッドから」と記載 | **対策済み:** ヘッダーに排他制約を明記 |
| num_threads の未対応 | 低 | PiperPlusConfig に含める | **解決済み (M5-5):** `Ort::SessionOptions::SetIntraOpNumThreads()` に反映 |

---

## 6. レビュー指摘事項と正誤表

### 6.1 正誤表

| セクション | 元の記述 | 正しい内容 |
|-----------|---------|-----------|
| 1.3 言語自動検出 | 「languageId をデフォルト値 (0) のまま渡すだけで自動検出が有効」 | 正確には「`synthesisConfig.languageId` が `textToAudio` 入口時点の `originalLanguageId` と一致していれば自動検出が発動」。デフォルト 0 なら `originalLanguageId` も 0 なので実質的には正しいが、メカニズムは「unchanged from original」 |
| 1.6 ストリーミングのマルチリンガル | 「piper.cpp L1756-1761 で TODO」 | TODO は存在するが、`usesOpenJTalk()` が `MultilingualPhonemes` でも true を返すため、この `else if` ブランチは**デッドコード**。結論 (textToAudio ベースが安全) は変わらないが、理由が異なる |
| 3.3 グローバルステート | `dict_path` と `g_openjtalk_bin_path` のみ列挙 | 追加: `data_dir` (L143), `exe_dict_path` (L194), `warnedNoCmuDict` (piper.cpp L1219, static bool) |

### 6.2 要求定義書への反映推奨事項 -- 全て対応済み

1. **`PiperPlusConfig` に `dict_dir` フィールド追加** -- **実装済み (M1-3)**
2. **`textToAudioStreaming` マルチリンガル制約** -- **解決済み (M5-16):** Iterator 駆動に移行
3. **`-fPIC` 前提条件** -- **実装済み (M1-1)**
4. **合成の排他制約をヘッダーに明記** -- **実装済み (M1-6):** `BusyGuard` + `PIPER_PLUS_ERR_BUSY` (M5-1, M5-13)
5. **`piper_plus_language_id(engine, name)` クエリ関数** -- **実装済み (M1-6)**
6. **共有ライブラリに `-static-libstdc++` を適用しない** -- **実装済み (M1-2)**

---

## 7. Phase 5 実装結果サマリ

Phase 5 で実装された 21 チケット (M5-1〜M5-21) の技術的成果を以下にまとめる。

### 7.1 API 基盤改善

| チケット | 内容 | 技術的影響 |
|---------|------|-----------|
| M5-1 | RAII ガード (ConfigGuard / BusyGuard) | 例外安全性の保証。`synthesisConfig` 復元と `inProgress` フラグ管理を自動化 |
| M5-5 | `num_threads` ORT 設定 | `Ort::SessionOptions::SetIntraOpNumThreads()` に反映。モバイル環境でのスレッド数制御が可能に |
| M5-6 | CoreML / DirectML provider | macOS CoreML / Windows DirectML による GPU 推論対応。`provider` 文字列で 4 パターン選択可能 |
| M5-9 | ゼロ初期化安全対策 | `memset(&opts, 0, sizeof(opts))` でも安全動作。`noise_scale` 等 0.0 をデフォルト値に自動置換 |
| M5-12 | `PiperPlusPhonemeResult._reserved[4]` | 出力 struct の ABI 拡張ポイント確保 |
| M5-13 | `PiperPlusStatus` enum 化 | `#define` から `typedef enum` に変更。`ERR_BUSY` (-5) / `ERR_ORT` (-6) 追加 |
| M5-14 | `piper_plus_create` status+out パターン | エラー種別 (`ERR_MODEL` / `ERR_CONFIG` / `ERR_ORT`) の正確な返却が可能に |

### 7.2 ストリーミング + 内部改善

| チケット | 内容 | 技術的影響 |
|---------|------|-----------|
| M5-2 | 多言語文分割改善 | CJK + Latin 句読点の両方に対応。混在テキストの正確な文境界検出 |
| M5-3 | Iterator crossfade | 文間のクロスフェードで Iterator とワンショットの音質差を解消 |
| M5-7 | ストリーミング中断 API | `PiperPlusAudioCallbackEx` (int 戻り) + `synthesize_streaming_ex()` で合成中断可能 |
| M5-8 | `phonemizeText` 副作用除去 | `phonemizeText()` / `splitTextToSentences()` が純粋関数に。ConfigGuard と二重安全策 |
| M5-10 | `getExeDir()` 統一 | M4-6 (dladdr) で解決済みのためクローズ |
| M5-16 | `textToAudioStreaming` Iterator 駆動 | `MultilingualPhonemes` デッドコード問題の根本解決 |

### 7.3 ビルド + CI

| チケット | 内容 | 技術的影響 |
|---------|------|-----------|
| M5-15 | CMake 分割 (9ファイル) | 保守性向上。`cmake/` 以下に機能別モジュール分離 |
| M5-17 | CI reusable workflow | `_build-test-cpp.yml` で `cpp-tests.yml` / `ci.yml` のテスト定義重複解消 |
| M5-11 | Android multi-ABI | `android-build.yml` で arm64-v8a / armeabi-v7a / x86_64 の 3 ABI |
| M5-21 | 音声回帰テスト | deterministic 合成の SHA-256 ハッシュ比較 |

### 7.4 エコシステムサンプル

| チケット | 内容 | 成果物 |
|---------|------|--------|
| M5-4 | 多言語合成サンプル | `examples/c-api/multi_language.c` |
| M5-18 | Dart FFI サンプル | `examples/dart/` (Flutter バインディング + ワンショット/ストリーミング例) |
| M5-19 | Godot GDExtension サンプル | `examples/godot/` (TTS ノード + SConstruct ~30行) |
| M5-20 | Android AAR | JNI ラッパー + Kotlin API + Gradle 配布準備 |
