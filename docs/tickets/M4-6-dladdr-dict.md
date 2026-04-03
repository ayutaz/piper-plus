# M4-6: dladdr による辞書自動検出改善

> **Phase:** 4 -- 拡張 (将来)
> **利用者視点の優先度:** 高 -- DX (Developer Experience) に直結。Phase 3 完了直後に着手推奨。
> **見積り:** 中
> **依存:** Phase 3 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m4-6-dladdr-による辞書自動検出改善)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

共有ライブラリ (`libpiper_plus.so/dylib/dll`) 利用時に `dict_dir = NULL` でも辞書が自動検出されるようにする。ライブラリ自身のファイルパスを基準として相対パスで辞書を検索する `dladdr()` ベースの自動検出を実装する。

**現状の問題:** 辞書自動検出は 3 箇所で `getExeDir()` / `get_exe_relative_dict_path()` / `getDictExeDir()` を使っているが、これらは全て「実行ファイルのパス」を基準とする:

| ファイル | 関数 | 手段 | 問題 |
|----------|------|------|------|
| `piper.cpp` L492 | `getExeDir()` | `readlink("/proc/self/exe")` / `_NSGetExecutablePath` / `GetModuleFileNameW(NULL, ...)` | Flutter/Godot/Python からの呼び出しでホストアプリのパスが返る |
| `openjtalk_dictionary_manager.c` L193 | `get_exe_relative_dict_path()` | 同上 (C 版) | 同上 |
| `custom_dictionary.cpp` L29 | `getDictExeDir()` | 同上 | 同上 |

Phase 1 では `PiperPlusConfig.dict_dir` の明示指定で回避しているが、`dict_dir = NULL` の場合は辞書が見つからない。

**ゴール:** `dladdr()` (Linux/macOS) / `GetModuleHandleEx(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS, ...)` (Windows) で `libpiper_plus` 自身のパスを取得し、そこからの相対パスで辞書を自動検出する。これにより、以下の配布レイアウトで `dict_dir = NULL` のまま辞書が自動的に利用可能になる:

```
lib/libpiper_plus.so          <-- dladdr() でこのパスを取得
lib/libonnxruntime.so
share/open_jtalk/dic/          <-- ../share/open_jtalk/dic/ で検出
share/piper/dicts/             <-- ../share/piper/dicts/ で検出
include/piper_plus.h
```

---

## 2. 実装する内容の詳細

### 2.1 共通ヘルパー関数の追加 (`src/cpp/library_path.h` 新規)

3 箇所で重複している「自身のパス取得 + 辞書検索」ロジックを統一する C ヘルパー:

```c
#ifndef PIPER_PLUS_LIBRARY_PATH_H
#define PIPER_PLUS_LIBRARY_PATH_H

#ifdef __cplusplus
extern "C" {
#endif

/** Get the directory containing the piper-plus shared library itself.
 *  Uses dladdr() on Linux/macOS, GetModuleHandleEx() on Windows.
 *  Falls back to getExeDir() if dladdr fails (static linking case).
 *
 *  @param buf   Buffer to write the path into
 *  @param size  Buffer size
 *  @return 0 on success, -1 on failure */
int piper_plus_get_library_dir(char *buf, int size);

#ifdef __cplusplus
}
#endif

#endif /* PIPER_PLUS_LIBRARY_PATH_H */
```

### 2.2 実装 (`src/cpp/library_path.c` 新規)

```c
#include "library_path.h"

#include <string.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#elif defined(__APPLE__) || defined(__linux__)
#include <dlfcn.h>
#endif

// Reference symbol inside the shared library (used by dladdr)
static void piper_plus_anchor_symbol(void) {}

int piper_plus_get_library_dir(char *buf, int size) {
    if (!buf || size <= 0) return -1;
    buf[0] = '\0';

#ifdef _WIN32
    // Windows: GetModuleHandleEx with GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS
    HMODULE hModule = NULL;
    BOOL ok = GetModuleHandleExA(
        GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
        GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        (LPCSTR)piper_plus_anchor_symbol,
        &hModule);
    if (!ok || !hModule) return -1;

    char path[MAX_PATH] = {0};
    DWORD len = GetModuleFileNameA(hModule, path, MAX_PATH);
    if (len == 0 || len >= MAX_PATH) return -1;

    // Remove filename, keep directory
    char *last_sep = strrchr(path, '\\');
    if (!last_sep) last_sep = strrchr(path, '/');
    if (last_sep) *last_sep = '\0';

    if ((int)strlen(path) >= size) return -1;
    strncpy(buf, path, size - 1);
    buf[size - 1] = '\0';
    return 0;

#elif defined(__APPLE__) || defined(__linux__)
    // Linux/macOS: dladdr() to find shared library path
    Dl_info info;
    if (dladdr((void *)piper_plus_anchor_symbol, &info) == 0) {
        return -1;  // dladdr failed
    }
    if (!info.dli_fname) return -1;

    // Copy full path and remove filename
    char path[4096];
    strncpy(path, info.dli_fname, sizeof(path) - 1);
    path[sizeof(path) - 1] = '\0';

    char *last_sep = strrchr(path, '/');
    if (last_sep) *last_sep = '\0';

    // Resolve symlinks to get canonical path
    char resolved[4096];
    if (realpath(path, resolved)) {
        if ((int)strlen(resolved) >= size) return -1;
        strncpy(buf, resolved, size - 1);
    } else {
        if ((int)strlen(path) >= size) return -1;
        strncpy(buf, path, size - 1);
    }
    buf[size - 1] = '\0';
    return 0;

#else
    return -1;  // Unsupported platform
#endif
}
```

### 2.3 既存コードへの統合

**`openjtalk_dictionary_manager.c` の `get_exe_relative_dict_path()` 修正:**

```c
static const char* get_exe_relative_dict_path() {
    static char exe_dict_path[1024] = {0};
    char lib_dir[1024] = {0};

    // 優先: ライブラリ自身のパスから検索 (共有ライブラリの場合)
    if (piper_plus_get_library_dir(lib_dir, sizeof(lib_dir)) == 0) {
        snprintf(exe_dict_path, sizeof(exe_dict_path),
                 "%s/../share/open_jtalk/dic", lib_dir);
        if (access(exe_dict_path, F_OK) == 0) {
            return exe_dict_path;
        }
    }

    // フォールバック: 実行ファイルのパスから検索 (静的リンクの場合)
    // ... 既存の readlink("/proc/self/exe") ロジック ...
}
```

**`piper.cpp` の `getExeDir()` 修正:**

```cpp
static std::filesystem::path getExeDir() {
    // 優先: ライブラリ自身のパス
    char libDir[4096];
    if (piper_plus_get_library_dir(libDir, sizeof(libDir)) == 0) {
        return std::filesystem::path(libDir);
    }

    // フォールバック: 既存の実行ファイルパスロジック
    // ... 既存コード ...
}
```

**`custom_dictionary.cpp` の `getDictExeDir()` 修正:**

```cpp
static fs::path getDictExeDir() {
    // 優先: ライブラリ自身のパス
    char libDir[4096];
    if (piper_plus_get_library_dir(libDir, sizeof(libDir)) == 0) {
        return fs::path(libDir);
    }

    // フォールバック: 既存の実行ファイルパスロジック
    // ... 既存コード ...
}
```

### 2.4 CMake の変更

```cmake
# library_path.c をリンクフラグ付きでコンパイル
if(PIPER_PLUS_BUILD_SHARED)
    target_sources(piper_plus PRIVATE src/cpp/library_path.c)
    if(NOT WIN32)
        target_link_libraries(piper_plus PRIVATE dl)  # dladdr() は libdl
    endif()
endif()

# 静的リンク時 (piper 実行ファイル) はスタブを提供
# dladdr は共有ライブラリでのみ意味がある
if(NOT PIPER_PLUS_BUILD_SHARED)
    # 静的ビルドでは library_path.c は不要 (getExeDir のフォールバックを使う)
endif()
```

### 2.5 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/library_path.h` | 新規: `piper_plus_get_library_dir()` ヘッダー |
| `src/cpp/library_path.c` | 新規: `dladdr()` / `GetModuleHandleEx()` による実装 |
| `src/cpp/openjtalk_dictionary_manager.c` | `get_exe_relative_dict_path()` にライブラリパス優先ロジック追加 |
| `src/cpp/piper.cpp` | `getExeDir()` にライブラリパス優先ロジック追加 |
| `src/cpp/custom_dictionary.cpp` | `getDictExeDir()` にライブラリパス優先ロジック追加 |
| `CMakeLists.txt` | `library_path.c` のビルド + `libdl` リンク |
| `src/cpp/tests/test_c_api.cpp` | 辞書自動検出テスト追加 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | `library_path.c` 実装 + 3 箇所への統合 |
| テストエージェント | 1 | 3 プラットフォームでの動作検証 |

合計 2 名。`dladdr()` は Linux/macOS で挙動が異なる場合があり (特に macOS の Framework バンドル)、プラットフォーム固有のテストが重要。

---

## 4. 提供範囲とテスト項目

### スコープ

- `piper_plus_get_library_dir()` ヘルパー関数の実装 (3 プラットフォーム)
- `getExeDir()` / `get_exe_relative_dict_path()` / `getDictExeDir()` への統合
- `dict_dir = NULL` 時の自動検出が共有ライブラリから正しく動作すること
- 既存の実行ファイル (`piper`) からの辞書検出が回帰しないこと

### ユニットテスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestGetLibraryDir` | `piper_plus_get_library_dir()` の戻り値 | 0 (成功) + 有効なパス文字列 |
| `TestGetLibraryDirNullBuf` | NULL バッファ | -1 (失敗) + クラッシュなし |
| `TestGetLibraryDirSmallBuf` | サイズ 1 のバッファ | -1 (失敗) |
| `TestLibraryDirContainsLib` | 返却パスに `lib` が含まれる (インストールレイアウトの場合) | パスが存在するディレクトリ |
| `TestStaticLinkFallback` | 静的リンク時 (`piper` 実行ファイル) | `getExeDir()` のフォールバックが動作 |

### E2E テスト (モデル必要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestAutoDetectDictFromLib` | `dict_dir = NULL` で `piper_plus_create()` → JA テキスト合成 | OpenJTalk 辞書が `libpiper_plus` からの相対パスで検出され、合成成功 |
| `TestAutoDetectCustomDict` | `dict_dir = NULL` でカスタム辞書のデフォルト検出 | `share/piper/dicts/` 内の辞書が検出される |
| `TestExplicitDictDirOverride` | `dict_dir` を明示指定 | 明示指定が優先され、`dladdr` パスは使われない |
| `TestPiperExeUnchanged` | `piper` 実行ファイルで辞書検出 | 既存の動作が変わらない |

### プラットフォーム固有テスト

| テスト | プラットフォーム | 内容 |
|--------|-----------------|------|
| `TestDladdrLinux` | Linux | `dladdr` が `libpiper_plus.so` のパスを返す |
| `TestDladdrMacOS` | macOS | `dladdr` が `libpiper_plus.dylib` のパスを返す |
| `TestGetModuleHandleExWindows` | Windows | `GetModuleHandleEx` が `piper_plus.dll` のパスを返す |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| `dladdr` が静的リンク時に失敗 | 中 | 静的リンク (`piper` 実行ファイル) では `dladdr` がライブラリパスを返さない。フォールバックとして既存の `readlink("/proc/self/exe")` ロジックを維持する。`piper_plus_get_library_dir()` が `-1` を返した場合のみフォールバック |
| macOS の `@rpath` 解決とシンボリックリンク | 中 | macOS では `dladdr` が `@rpath` 解決前のパスを返す場合がある。`realpath()` で正規化する |
| `openjtalk_dictionary_manager.c` の static 変数の初期化順序 | 中 | `dict_path[1024]` は `static` で初回呼び出し時に初期化される。`dladdr` の結果をキャッシュする際、マルチスレッドの初回呼び出しでレース条件が理論的に発生。ただし Phase 1 で「初回 create は単一スレッド」と文書化済み |
| Windows の `GetModuleHandleExA` と Unicode パス | 低 | ASCII パスのみ対応。Unicode パスが必要な場合は `GetModuleHandleExW` + `WideCharToMultiByte` が必要。ただし、`openjtalk_dictionary_manager.c` は既に ASCII ベース (`char[]`) なので整合する |
| Android (`__ANDROID__`) の動作 | 低 | Android の `dladdr` は利用可能で、`libpiper_plus.so` のパスを返す (`/data/app/.../lib/arm64-v8a/libpiper_plus.so`)。ただし、辞書は APK 内にないため `../share/` パスは存在しない。`dict_dir` 明示指定にフォールバック |
| `libdl` のリンク依存 | 低 | Linux では `-ldl` が必要。`CMakeLists.txt` で `target_link_libraries(piper_plus PRIVATE dl)` を追加。macOS は `libdl` がデフォルトで利用可能。Windows は Win32 API を使うため不要 |

### レビュー時の確認項目

1. `piper_plus_anchor_symbol` が `library_path.c` 内に定義されており、`dladdr` が確実にこのライブラリのパスを返すこと
2. 静的リンク時のフォールバックが正しく動作すること (`piper` 実行ファイルの回帰なし)
3. `realpath()` による正規化が全プラットフォームで安全であること
4. 3 箇所の統合 (`openjtalk_dictionary_manager.c`, `piper.cpp`, `custom_dictionary.cpp`) が一貫していること
5. `library_path.h` / `library_path.c` が C99 互換であること (`.c` ファイルのため)
6. Windows の `GetModuleHandleExA` が `piper_plus.dll` を正しく検出すること

---

## 6. 一から作り直すとしたら

**Phase 1 で `dladdr` を導入すべきだったか:** Phase 1 では `dict_dir` 明示指定を選択した。`dladdr` は共有ライブラリでのみ動作し、静的リンク時のフォールバックが必要なため、Phase 1 のシンプルな明示指定は妥当。ただし、利用者にとっては「`dict_dir = NULL` でも辞書が見つかる」方が明らかに使いやすい。Phase 1 の時点で両方実装しておけば、初期体験が向上した。

**3 箇所の `getExeDir` の統一:** 現在 `piper.cpp`, `openjtalk_dictionary_manager.c`, `custom_dictionary.cpp` にほぼ同一のコードが 3 重複している。`library_path.h/c` はこれを統一するチャンスだが、既存の `getExeDir()` を完全に置き換えるには各ファイルの `#include` と呼び出し箇所を変更する必要がある。理想的には `getExeDir()` 自体を `library_path.h` に移動し、全箇所から共通関数を呼ぶべき。

**配布レイアウトの前提:** `dladdr` で得たパスから `../share/open_jtalk/dic/` を探す設計は M3-1 (配布ファイルマニフェスト) のレイアウトに依存する。M3-1 と M4-6 を合わせて設計していれば、辞書パスの候補リストを一元管理できた。

---

## 7. 後続タスクへの連絡事項

- **M4-1 (カスタム辞書):** M4-6 完了後、カスタム辞書のデフォルト辞書 (`data/dictionaries/`) も `dladdr` ベースで自動検出可能になる。`CustomDictionary()` のデフォルトコンストラクタが共有ライブラリからも正しく動作する。
- **M4-4 (Android NDK):** Android では `dladdr` が利用可能だが、辞書は APK 内にないため `../share/` パスは存在しない。`dict_dir` 明示指定が引き続き必要。
- **M3-1 (配布マニフェスト):** M3-1 の配布レイアウトで辞書が `lib/../share/open_jtalk/dic/` に配置されることが前提。M3-1 のレイアウト変更時は M4-6 の検索パスも更新する必要がある。
- **`getExeDir()` の統合:** 将来的に `piper.cpp` / `custom_dictionary.cpp` の `getExeDir()` / `getDictExeDir()` を `piper_plus_get_library_dir()` に統一することで、コード重複を解消できる。

---

## Phase 4 全体の振り返り: 一から設計するなら

Phase 4 を最初から設計し直すとしたら、以下の 3 点を再考する:

### 1. 拡張 API の優先順位は正しいか

Phase 4 の 6 チケットは「利用者フィードバック前」に定義されたものであり、実際の利用パターンに基づく優先順位付けではない。

**再優先度の提案:**

| 現在の順位 | チケット | 利用者視点の優先度 | 理由 |
|-----------|---------|------------------|------|
| 1 | M4-1 カスタム辞書 | **高** | 技術用語の発音修正は全利用者に必要 |
| 2 | M4-2 Phoneme timing | **高** | Godot/Unity のリップシンクが主要ユースケース |
| 3 | M4-6 dladdr 辞書検出 | **高** | DX (Developer Experience) に直結。`dict_dir = NULL` での自動検出は初期体験の改善 |
| 4 | M4-4 Android NDK | **高** | Flutter 最大ターゲットが Android |
| 5 | M4-5 float32 直接出力 | **低** | 精度差は聴覚上無視可能。パフォーマンス改善も限定的 |
| 6 | M4-3 G2P 単独 API | **低** | TTS 利用者の多くは G2P 単独利用を必要としない |

M4-6 (dladdr) と M4-4 (Android) は Phase 3 完了直後に着手すべき。M4-5 と M4-3 は利用者からの具体的要望が出てから実装しても遅くない。

### 2. Android NDK は Phase 3 の一部にすべきだったか

**結論: Phase 3 に含めるべきだった (ただし最小スコープで)。**

理由:
- C API の最大ユースケースは Flutter/Dart であり、Flutter 最大ターゲットは Android
- Phase 3 (配布) のリリースワークフロー (M3-5) に Android ビルドを含めれば、`v1.0.0` リリース時点で Android バイナリが即座に利用可能
- Phase 3 の `armeabi-v7a` なし、`arm64-v8a` のみの最小スコープであれば、M3-5 に +1 日程度で統合可能

ただし、Phase 3 のスコープが既に大きい (6 チケット、うち大 x1) ため、独立チケットとした判断も合理的。妥協案として「M3-5 のリリースワークフロー内に Android ビルドをオプショナルステップとして含める」が最適だったかもしれない。

### 3. G2P 単独 API は既存の Rust piper-g2p FFI とどう整合するか

**現状の二重実装:**

| 側 | API | ハンドル | 辞書管理 | 言語 |
|----|-----|---------|---------|------|
| Rust `piper-plus-g2p` FFI | `piper_plus_g2p_create/phonemize/free` | `PiperG2pHandle` (モデル非依存) | レジストリ内で自動ロード | EN, ES, FR, PT, SV, KO, JA (feature flag) |
| C++ C API (M4-3) | `piper_plus_phonemize` | `PiperPlusEngine` (モデル依存) | エンジン作成時にロード済み | モデルがサポートする全言語 |

**整合性の課題:**
- Rust FFI はモデル非依存で G2P のみ提供。C++ C API はモデルロード済みエンジンに紐づく
- 同一プロセスで両方使う場合、シンボル名が異なる (`piper_plus_g2p_*` vs `piper_plus_*`) ため衝突しない
- ただし、「C API の G2P」と「Rust FFI の G2P」が異なる音素を返す可能性がある (辞書バージョン差異等)

**理想的な設計:**
- C++ C API の M4-3 は廃止し、Rust `piper-plus-g2p` の FFI を唯一の G2P C API とする
- C++ 共有ライブラリからも Rust FFI を呼び出す (Rust を C++ にリンク)
- ただし、これは C++ ビルドに Rust ツールチェインへの依存を追加するため、ビルドの複雑さが大幅に増加

**現実的な判断:** Phase 4 では C++ エンジンベースの G2P (`piper_plus_phonemize`) を提供し、Rust FFI とは独立して運用する。将来的に Rust FFI が成熟すれば、C++ 版を deprecated にする選択肢も残す。

### まとめ

Phase 4 全体として、6 チケットの独立実装可能な設計は正しい。ただし、M4-6 (dladdr) と M4-4 (Android) は利用者視点での優先度が高く、Phase 3 直後に着手すべき。M4-3 (G2P) と M4-5 (float32) は利用者フィードバックを待ってからでも遅くない。Rust FFI との二重実装問題は、エコシステム全体の G2P 統合方針として別途議論が必要。
