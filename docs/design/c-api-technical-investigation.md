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
| `provider` | `useCuda` (bool) | `"cuda"` → true、他は false。CoreML/DirectML は将来対応 |
| `gpu_device_id` | `gpuDeviceId` | そのまま |
| `num_threads` | — | 現在の loadModel() に該当引数なし。将来 `Ort::SessionOptions` に設定 |

**PiperPlusEngine 内部構造体:**

```cpp
struct PiperPlusEngine {
    piper::PiperConfig config;   // 空 struct (API 互換のため保持)
    piper::Voice       voice;    // ONNX Session + config + 辞書。move-only
};
```

- `piper::Voice` は `Ort::Session` (move-only) を含むためコピー不可
- ヒープに `new` するので move の問題はない

### 1.2 piper_plus_synthesize() の実装方針

**speaker_id / language_id の設定:** `voice.synthesisConfig` フィールドを直接変更 → 合成 → 復元するパターン (main.cpp の processLine と同一)。

**音声データの変換:** ONNX 出力は float → `synthesize()` で int16 → C API で float に戻す 2 重変換。現状は `textToAudio()` が `vector<int16_t>` を返すため回避不可。将来の最適化候補。

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

---

## 2. CMake ビルドシステム

### 2.1 OBJECT ライブラリによるソース共有

現在 `piper` (実行ファイル) と `test_piper` で同じソースが **3 重複列挙**されている。共有ライブラリ追加で 4 重複になるため、OBJECT ライブラリ `piper_common` で一元管理を推奨。

```cmake
add_library(piper_common OBJECT ${PIPER_CORE_SOURCES})
set_target_properties(piper_common PROPERTIES POSITION_INDEPENDENT_CODE ON)

# 実行ファイル
add_executable(piper src/cpp/main.cpp src/cpp/model_manager.cpp)
target_link_libraries(piper PRIVATE piper_common ...)

# 共有ライブラリ
add_library(piper_plus SHARED src/cpp/piper_plus_c_api.cpp)
target_link_libraries(piper_plus PRIVATE piper_common ...)
```

除外ファイル: `main.cpp`, `model_manager.cpp` (CLI のみ)

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

### 5.1 レビューで追加発見されたリスク (高)

| リスク | 影響度 | 詳細 | 対策 |
|--------|--------|------|------|
| `textToAudio` が `languageId` を変更して復元しない | **高** | piper.cpp L1279 で `voice.synthesisConfig.languageId` を自動検出値に上書きし、関数終了まで復元しない。C API ラッパーで save/restore しないと次回呼び出しの自動検出が壊れる | C API ラッパーで `synthesisConfig` を呼び出し前に保存、呼び出し後に復元 |
| 辞書パス自動検出が共有ライブラリで機能しない | **高** | `getExeDir()` / `get_exe_relative_dict_path()` が `readlink("/proc/self/exe")` / `_NSGetExecutablePath` を使用し、ホストアプリのパスを返す。Flutter/Godot/Python から呼ぶと辞書が見つからない | `PiperPlusConfig` に `dict_dir` フィールドを追加。自動検出は `dladdr()` (Linux/macOS) / `GetModuleHandleEx(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS)` (Windows) でライブラリ自身のパスを取得する方式に変更 |
| Iterator / one-shot 合成の再入問題 | **高** | `PiperPlusEngine` の `iterState` と `voice.synthesisConfig` が共有される。Iterator 中に `synthesize()` を呼ぶと状態破壊 | エンジンに `inProgress` フラグを追加し、合成中の新規合成は `PIPER_PLUS_ERR` を返す。ヘッダーに「1エンジン1合成」制約を明記 |

### 5.2 レビューで追加発見されたリスク (中)

| リスク | 影響度 | 詳細 | 対策 |
|--------|--------|------|------|
| 言語名→ID 変換 API の欠如 | **中** | ユーザーが `"ja"` → `0` の変換を自力でやる必要がある | `piper_plus_language_id(engine, "ja")` クエリ関数を追加 |
| `-static-libstdc++` の共有ライブラリ競合 | **中** | 共有ライブラリと消費側アプリで `libstdc++` のコピーが二重になり、例外テーブルが分離してキャッチ失敗の可能性 | 共有ライブラリには `-static-libstdc++` を**適用しない** (実行ファイル `piper` のみ) |
| macOS RPATH が `@executable_path` | **中** | 共有ライブラリには `@loader_path` (ライブラリ自身の位置) が必要 | `INSTALL_RPATH "@loader_path"` に修正 |
| Iterator の文分割が想定より複雑 | **中** | `textToAudio` は全テキストを一括処理し文分割しない。Iterator には `textToAudioStreaming` の文分割ロジックの抽出、またはフォネマイズループの分離が必要 | Phase 2 で `textToAudio` の音素化ループ (L1067-1309) を再利用可能関数に抽出 |
| `OPENJTALK_DIC_PATH` コンパイル定義が OBJECT ライブラリと非互換 | **中** | 現在 target ごとに異なる相対パスを設定。OBJECT ライブラリでは単一定義しか持てない | OBJECT ライブラリから除外し、消費側 target で個別設定。または実行時検出に切り替え |

### 5.3 初回調査で発見済みのリスク

| リスク | 影響度 | 対策 |
|--------|--------|------|
| OpenJTalk/spdlog の -fPIC 不足 | **高** (Linux でビルド失敗) | ExternalProject に `CMAKE_POSITION_INDEPENDENT_CODE=ON` 追加 |
| int16↔float32 2 重変換 | 低 (精度劣化 + CPU コスト) | 将来 float 出力バリアントを追加 |
| textToAudioStreaming のマルチリンガル未対応 | 中 (該当 else-if はデッドコード) | Iterator は textToAudio ベースで実装 |
| 辞書パス初期化のレース条件 | 低 (実害は起きにくい) | ドキュメントで「初回 create は単一スレッドから」と記載 |
| num_threads の未対応 | 低 | PiperPlusConfig に含めるが Phase 1 では無視 |

---

## 6. レビュー指摘事項と正誤表

### 6.1 正誤表

| セクション | 元の記述 | 正しい内容 |
|-----------|---------|-----------|
| 1.3 言語自動検出 | 「languageId をデフォルト値 (0) のまま渡すだけで自動検出が有効」 | 正確には「`synthesisConfig.languageId` が `textToAudio` 入口時点の `originalLanguageId` と一致していれば自動検出が発動」。デフォルト 0 なら `originalLanguageId` も 0 なので実質的には正しいが、メカニズムは「unchanged from original」 |
| 1.6 ストリーミングのマルチリンガル | 「piper.cpp L1756-1761 で TODO」 | TODO は存在するが、`usesOpenJTalk()` が `MultilingualPhonemes` でも true を返すため、この `else if` ブランチは**デッドコード**。結論 (textToAudio ベースが安全) は変わらないが、理由が異なる |
| 3.3 グローバルステート | `dict_path` と `g_openjtalk_bin_path` のみ列挙 | 追加: `data_dir` (L143), `exe_dict_path` (L194), `warnedNoCmuDict` (piper.cpp L1219, static bool) |

### 6.2 要求定義書への反映推奨事項

1. **`PiperPlusConfig` に `dict_dir` フィールド追加** — 共有ライブラリでは辞書自動検出が機能しないため必須
2. **Phase 2 に `textToAudioStreaming` マルチリンガル制約の注記追加**
3. **Phase 1 に `-fPIC` 前提条件を追記**
4. **合成の排他制約 (1エンジン1合成) をヘッダーコメントに明記**
5. **`piper_plus_language_id(engine, name)` クエリ関数の追加検討**
6. **共有ライブラリに `-static-libstdc++` を適用しないことを明記**
