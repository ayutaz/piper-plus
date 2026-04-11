# M1-001: C++ ランタイムから HTS voice フォールバックを除去

## メタデータ
- マイルストーン: M1
- 依存チケット: なし (最初に着手可能)
- ブロックするチケット: M3-001, M4-001
- 状態: 完了
- 推定削除行数: ~230行

## 1. 目的とゴール

### なぜこの変更が必要か

piper-plus は VITS ニューラル TTS エンジンであり、OpenJTalk の「テキスト → フルコンテキストラベル (音素列)」変換機能のみを使用する。HTS 音声合成は一切使わない。

しかし歴史的経緯から、C++ ランタイムの 4 ファイルに HTS voice (`.htsvoice`) への依存が残存している。具体的には:

1. **`get_openjtalk_voice_path()` 関数** -- 常に `NULL` を返すだけの dead code (L424-427)
2. **`#if 0` で無効化済みの voice DL コード** -- 140行近い dead code (L429-567)
3. **`open_jtalk` フォールバック時の `-m <voice>` 分岐** -- phonemizer バイナリが優先パスであり、フォールバックパスでも `voice_path` は常に `NULL` なので dead branch

これらはすべて実行されないコードだが、ビルド時間・可読性・保守コストに悪影響を与えている。

### 完了後の状態

- `get_openjtalk_voice_path()` が C++ コードベースから完全に消滅する
- `open_jtalk` フォールバック時のコマンド構築が voice 不要の単一パスに統一される
- 環境変数 `OPENJTALK_VOICE` が C++ コードで参照されなくなる
- 既存の音素抽出機能は全く影響を受けない

## 2. 実装内容の詳細

### 2.1 タスク一覧

| # | タスク | ファイル | 対象行 | 削除行数 |
|---|--------|---------|--------|---------|
| 1.1 | HTS voice 定数削除 | `src/cpp/openjtalk_dictionary_manager.c` | L30-35 | 6行 |
| 1.2 | voice パス検索関数削除 | `src/cpp/openjtalk_dictionary_manager.c` | L422-427 | 6行 |
| 1.3 | 無効化済み DL コード削除 | `src/cpp/openjtalk_dictionary_manager.c` | L429-567 | 139行 |
| 1.4 | ヘッダー宣言削除 | `src/cpp/openjtalk_dictionary_manager.h` | L11-12 | 2行 |
| 1.5 | wrapper 関数 1 簡素化 | `src/cpp/openjtalk_wrapper.c` | L405-433 | ~20行 |
| 1.6 | wrapper 関数 2 簡素化 | `src/cpp/openjtalk_wrapper.c` | L715-738 | ~17行 |
| 1.7 | optimized Unix パス簡素化 | `src/cpp/openjtalk_optimized.c` | L244-254 | ~7行 |
| 1.8 | optimized Windows パス簡素化 | `src/cpp/openjtalk_optimized.c` | L390-401 | ~8行 |
| 1.9 | HTSVoicePath テスト削除 | `src/cpp/tests/test_dictionary_manager.cpp` | L252-270 | 19行 |
| | **合計** | | | **~224行** |

### 2.2 変更対象ファイルと Before/After コード差分

#### タスク 1.1: HTS voice 定数削除

**ファイル:** `src/cpp/openjtalk_dictionary_manager.c` L30-35

```diff
- // HTS voice download URL (Using direct link from SourceForge)
- #define HTS_VOICE_URL "https://sourceforge.net/projects/open-jtalk/files/HTS%20voice/hts_voice_nitech_jp_atr503_m001-1.05/hts_voice_nitech_jp_atr503_m001-1.05.tar.gz/download"
- #define HTS_VOICE_FILENAME "hts_voice_nitech_jp_atr503_m001-1.05.tar.gz"
- #define HTS_VOICE_DIR "hts_voice_nitech_jp_atr503_m001-1.05"
- #define HTS_VOICE_FILE "nitech_jp_atr503_m001.htsvoice"
- #define HTS_VOICE_SHA256 "2e555c88482267b2931c7dbc7ecc0e3df140d6f68fc913aa4822f336c9e0adfc"
```

#### タスク 1.2: voice パス検索関数削除

**ファイル:** `src/cpp/openjtalk_dictionary_manager.c` L422-427

```diff
- // Get the path to the HTS voice file
- const char* get_openjtalk_voice_path() {
-     // HTS voice not needed for phonemizer-only mode
-     // This function is kept for backward compatibility but returns NULL
-     return NULL;
- }
```

#### タスク 1.3: 無効化済み DL コード削除

**ファイル:** `src/cpp/openjtalk_dictionary_manager.c` L429-567

`#if 0` ... `#endif` ブロック全体 (139行) を削除する。このブロックは `get_openjtalk_voice_path_old()` という旧関数で、voice ファイルの自動ダウンロード・SHA256 検証・tar.gz 展開ロジックを含むが、既に無効化されている。

```diff
- #if 0
- // Original HTS voice download code - kept for reference but disabled
- static const char* get_openjtalk_voice_path_old() {
-     ... (139 lines)
- }
- #endif
```

#### タスク 1.4: ヘッダー宣言削除

**ファイル:** `src/cpp/openjtalk_dictionary_manager.h` L11-12

```diff
  // Get the path to the OpenJTalk dictionary
  const char* get_openjtalk_dictionary_path();

- // Get the path to the HTS voice file
- const char* get_openjtalk_voice_path();
-
  // Ensure the OpenJTalk dictionary is available (download if necessary)
  int ensure_openjtalk_dictionary();
```

#### タスク 1.5: wrapper 関数 1 簡素化

**ファイル:** `src/cpp/openjtalk_wrapper.c` L405-433 (`openjtalk_text_to_phonemes()` 内)

Before (L405-433):
```c
    } else {
        // Fall back to regular open_jtalk with HTS voice
        const char* voice_path = get_openjtalk_voice_path();
        if (!voice_path) {
            fprintf(stderr, "Warning: HTS voice not found, attempting phoneme extraction only\n");
        }

#ifdef _WIN32
        if (voice_path) {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -m \"%s\" -ow NUL -ot \"%s\" \"%s\"",
                     openjtalk_bin, dic_path, voice_path, output_file, input_file);
        } else {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -ow NUL -ot \"%s\" \"%s\"",
                     openjtalk_bin, dic_path, output_file, input_file);
        }
#else
        if (voice_path) {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -m \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
                     openjtalk_bin, dic_path, voice_path, output_file, input_file);
        } else {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
                     openjtalk_bin, dic_path, output_file, input_file);
        }
#endif
    }
```

After:
```c
    } else {
        // open_jtalk fallback: phoneme extraction only (no HTS voice needed)
#ifdef _WIN32
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -ow NUL -ot \"%s\" \"%s\"",
                 openjtalk_bin, dic_path, output_file, input_file);
#else
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
                 openjtalk_bin, dic_path, output_file, input_file);
#endif
    }
```

#### タスク 1.6: wrapper 関数 2 簡素化

**ファイル:** `src/cpp/openjtalk_wrapper.c` L715-738 (`openjtalk_text_to_phonemes_with_prosody_binary()` 内)

Before (L715-738):
```c
    } else {
        const char* voice_path = get_openjtalk_voice_path();
#ifdef _WIN32
        if (voice_path) {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -m \"%s\" -ow NUL -ot \"%s\" \"%s\"",
                     openjtalk_bin, dic_path, voice_path, output_file, input_file);
        } else {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -ow NUL -ot \"%s\" \"%s\"",
                     openjtalk_bin, dic_path, output_file, input_file);
        }
#else
        if (voice_path) {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -m \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
                     openjtalk_bin, dic_path, voice_path, output_file, input_file);
        } else {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
                     openjtalk_bin, dic_path, output_file, input_file);
        }
#endif
    }
```

After:
```c
    } else {
        // open_jtalk fallback: phoneme extraction only (no HTS voice needed)
#ifdef _WIN32
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -ow NUL -ot \"%s\" \"%s\"",
                 openjtalk_bin, dic_path, output_file, input_file);
#else
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
                 openjtalk_bin, dic_path, output_file, input_file);
#endif
    }
```

#### タスク 1.7: optimized Unix パス簡素化

**ファイル:** `src/cpp/openjtalk_optimized.c` L244-254 (`execute_with_pipes_unix()` 内)

Before (L244-254):
```c
        if (is_phonemizer) {
            execlp(openjtalk_bin, openjtalk_bin, "-x", dic_path, "-ot", "-", "-", NULL);
        } else {
            // Need HTS voice for regular open_jtalk
            const char* voice_path = get_openjtalk_voice_path();
            if (voice_path) {
                execlp(openjtalk_bin, openjtalk_bin, "-x", dic_path, "-m", voice_path, 
                       "-ow", "/dev/null", "-ot", "-", "-", NULL);
            } else {
                execlp(openjtalk_bin, openjtalk_bin, "-x", dic_path, 
                       "-ow", "/dev/null", "-ot", "-", "-", NULL);
            }
        }
```

After:
```c
        if (is_phonemizer) {
            execlp(openjtalk_bin, openjtalk_bin, "-x", dic_path, "-ot", "-", "-", NULL);
        } else {
            // open_jtalk fallback: phoneme extraction only (no HTS voice needed)
            execlp(openjtalk_bin, openjtalk_bin, "-x", dic_path,
                   "-ow", "/dev/null", "-ot", "-", "-", NULL);
        }
```

#### タスク 1.8: optimized Windows パス簡素化

**ファイル:** `src/cpp/openjtalk_optimized.c` L390-401 (`execute_with_pipes_windows()` 内)

Before (L390-401):
```c
    if (is_phonemizer) {
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -ot - -",
                 openjtalk_bin, dic_path);
    } else {
        const char* voice_path = get_openjtalk_voice_path();
        if (voice_path) {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -m \"%s\" -ow NUL -ot - -",
                     openjtalk_bin, dic_path, voice_path);
        } else {
            snprintf(command, sizeof(command),
                     "\"%s\" -x \"%s\" -ow NUL -ot - -",
                     openjtalk_bin, dic_path);
        }
    }
```

After:
```c
    if (is_phonemizer) {
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -ot - -",
                 openjtalk_bin, dic_path);
    } else {
        // open_jtalk fallback: phoneme extraction only (no HTS voice needed)
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -ow NUL -ot - -",
                 openjtalk_bin, dic_path);
    }
```

#### タスク 1.9: HTSVoicePath テスト削除

**ファイル:** `src/cpp/tests/test_dictionary_manager.cpp` L252-270

```diff
- // Test HTS voice path resolution
- TEST_F(DictionaryManagerTest, HTSVoicePath) {
-     const char* custom_voice = "/tmp/custom_voice_test.htsvoice";
-     
-     // Create dummy voice file
-     FILE* fp = fopen(custom_voice, "w");
-     if (fp) {
-         fprintf(fp, "dummy hts voice");
-         fclose(fp);
-     }
-     
-     setenv("OPENJTALK_VOICE", custom_voice, 1);
-     
-     const char* voice_path = nullptr;
-     // This test might fail due to network in CI, so we just test the path resolution
-     // In a real test environment, we'd mock the download functionality
-     
-     unlink(custom_voice);
- }
```

このテストは `get_openjtalk_voice_path()` を実際には呼び出しておらず、ダミーファイルを作成して環境変数を設定するだけの不完全なテストである。関数本体の削除とともに除去する。

### 2.3 変更の依存順序

**すべてのタスク (1.1-1.9) は同一コミットで実施すること。**

理由: タスク 1.2 (関数定義の削除) とタスク 1.4 (ヘッダー宣言の削除) を先に行い、タスク 1.5-1.8 (呼び出し元の削除) を後にすると、中間状態でリンクエラーが発生する。逆順でも、宣言があるが定義がない状態でリンクエラーとなる。分離するメリットがないため、同一コミットで原子的に変更する。

推奨する編集順序 (レビュー上の読みやすさ):
1. まず 1.5-1.8 (呼び出し元) を編集 -- voice 分岐を削除して単一パスに統一
2. 次に 1.1-1.4 (定義・宣言) を削除 -- 呼び出し元がなくなった関数/定数を除去
3. 最後に 1.9 (テスト) を削除 -- 削除された関数に対応するテストを除去

## 3. エージェントチームの役割と人数

このチケットの実装には以下の 3 役割を想定する。

### 役割 1: 実装担当 (1名)

**責務:**
- 2.2 節の Before/After 差分に従い、5 ファイルのコード変更を実施する
- 2.3 節の依存順序を遵守し、すべての変更を同一コミットにまとめる
- 変更後にローカルで `cmake --build build` のコンパイル成功を確認する
- `#include "openjtalk_dictionary_manager.h"` を含む全ファイルで `get_openjtalk_voice_path` への参照が残っていないことを grep で確認する

**スキル要件:** C言語、CMake ビルドシステム、`#ifdef _WIN32` プラットフォーム分岐の理解

### 役割 2: レビュー担当 (1名)

**責務:**
- diff が 2.2 節の仕様と一致していることを照合する
- `get_openjtalk_voice_path` のシンボルがコードベース全体から消滅していることを `grep -r` で確認する
- `HTS_VOICE_URL` 等の定数が残存していないことを確認する
- wrapper 関数の `#ifdef _WIN32` / `#else` 分岐が対称的であることを確認する
- 5.1 節の懸念事項に基づくチェックリストを通過させる

**スキル要件:** C コードレビュー経験、リンクエラーパターンの知識

### 役割 3: テスト実行担当 (1名)

**責務:**
- 4.3 節の E2E テスト (受入基準) をすべて実行し、結果を記録する
- CI 環境 (GitHub Actions) でのビルド・テスト通過を確認する
- `ctest` の全テストが PASS/SKIP であり FAIL がないことを確認する
- voice なしでの音素抽出パスが正常に動作することを、既存テスト (`BasicConversion` 等) の通過で確認する

**スキル要件:** CI/CD、CTest の実行経験

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (スコープ)

**変更するもの:**

| ファイル | 変更内容 |
|---------|---------|
| `src/cpp/openjtalk_dictionary_manager.c` | HTS voice 定数 (L30-35)、`get_openjtalk_voice_path()` 関数 (L422-427)、`#if 0` ブロック (L429-567) を削除 |
| `src/cpp/openjtalk_dictionary_manager.h` | `get_openjtalk_voice_path()` 宣言 (L11-12) を削除 |
| `src/cpp/openjtalk_wrapper.c` | 2 箇所の voice 分岐 (L405-433, L715-738) を単一パスに簡素化 |
| `src/cpp/openjtalk_optimized.c` | 2 箇所の voice 分岐 (L244-254, L390-401) を単一パスに簡素化 |
| `src/cpp/tests/test_dictionary_manager.cpp` | `HTSVoicePath` テスト (L252-270) を削除 |

**変更しないもの:**

| ファイル/領域 | 理由 |
|-------------|------|
| `src/cpp/openjtalk_api.c` | HTS voice 依存なし。MeCab + NJD + JPCommon パイプラインのみ |
| `cmake/hts_engine_stub.h`, `cmake/hts_engine_stub.c` | OpenJTalk ヘッダーが `HTS_engine.h` を include するため、stub は維持が必要 (M3 スコープ) |
| `cmake/ExternalDeps.cmake`, `cmake/PiperLink.cmake` | CMake の HTS Engine 関連変更は M3 スコープ |
| CI ワークフロー | CI の voice DL 削除は M3 スコープ |
| WASM / npm パッケージ | M2 スコープ |
| Python / Rust / C# / Go | HTS voice 依存なし |

### 4.2 ユニットテスト

**既存テストによる安全網 (変更不要):**

| テストファイル | テスト名 | カバー範囲 |
|--------------|---------|-----------|
| `test_openjtalk_optimized.cpp` | `BasicConversion` | phonemizer パスの音素抽出。voice なしでも動作 |
| `test_openjtalk_optimized.cpp` | `PerformanceComparison` | wrapper + optimized 両パスの動作確認 |
| `test_openjtalk_optimized.cpp` | `ConcurrentAccess` | スレッド安全性 (voice 無関係) |
| `test_openjtalk_optimized.cpp` | `CacheHitPerformance` | キャッシュ正確性 (voice 無関係) |

これらのテストは phonemizer バイナリ経由のパスを検証しており、voice 分岐の除去による影響を受けない。phonemizer バイナリが利用できない CI 環境では `GTEST_SKIP` で安全にスキップされる。

**M4 で追加すべき検証テスト:**

- `test_command_without_voice_flag`: 構築されるコマンド文字列に `-m` フラグが含まれないことを確認するテスト。M4-001 のテスト仕様に含める

**削除すべきテスト:**

| テストファイル | テスト名 | 削除理由 |
|--------------|---------|---------|
| `test_dictionary_manager.cpp` | `HTSVoicePath` | `get_openjtalk_voice_path()` 関数の削除に伴い不要。なお、このテストはダミーファイル作成と `setenv()` を行うだけで関数呼び出しがなく、もともと不完全だった |

### 4.3 E2E テスト (受入基準)

以下のすべてを満たすこと:

- [ ] **ビルド成功**: `cmake --build build` がエラーなく完了する
- [ ] **テスト通過**: `ctest` の全テストが PASS または SKIP (FAIL なし)
- [x] **シンボル残存確認 1**: `grep -r "get_openjtalk_voice_path" src/cpp/` が 0 件
- [x] **シンボル残存確認 2**: `grep -r "HTS_VOICE_URL" src/cpp/` が 0 件
- [x] **シンボル残存確認 3**: `grep -r "HTS_VOICE_FILENAME\|HTS_VOICE_DIR\|HTS_VOICE_FILE\|HTS_VOICE_SHA256" src/cpp/` が 0 件
- [x] **ヘッダー確認**: `src/cpp/openjtalk_dictionary_manager.h` に `voice` を含む行がないこと
- [x] **dead code 確認**: `grep -r "#if 0" src/cpp/openjtalk_dictionary_manager.c` が 0 件

## 5. 懸念事項とレビュー項目

### 5.1 リンクエラーリスク

**リスク:** `get_openjtalk_voice_path()` の定義削除 (1.2) と呼び出し元削除 (1.5-1.8) が別コミットになると、中間状態でリンクエラーが発生する。

**対策:** すべての変更を同一コミットで原子的に実施する。レビュー時に diff に含まれるファイルが 5 つ (`.c` x 3, `.h` x 1, `.cpp` x 1) であることを確認する。

### 5.2 `#include` 経由の間接参照

**懸念:** `openjtalk_dictionary_manager.h` を include しているファイルが、`get_openjtalk_voice_path()` を間接的に参照している可能性。

**確認方法:** `grep -r "get_openjtalk_voice_path" src/cpp/` で全参照を列挙し、タスク 1.5-1.8 のカバー範囲と一致することを確認する。ヘッダーを include しているが関数を呼んでいないファイル (例: `openjtalk_api.c`) は影響なし。

### 5.3 Windows / Unix 分岐の対称性

**懸念:** タスク 1.5, 1.6 の wrapper 関数は `#ifdef _WIN32` / `#else` で分岐しており、片方だけ変更漏れが発生しやすい。

**確認方法:** After コードで Windows パス (`-ow NUL`) と Unix パス (`-ow /dev/null`) が対称的であることをレビューで目視確認する。

### 5.4 `open_jtalk` フォールバックの動作

**懸念:** `open_jtalk` バイナリ (phonemizer ではないオリジナル版) が `-m <voice>` なしで正しく動作するか。

**確認結果:** 既存コードの L408-410 に `if (!voice_path) { fprintf(stderr, "Warning: HTS voice not found, attempting phoneme extraction only\n"); }` という warning があり、voice なしでの動作は既に想定されている。また、`get_openjtalk_voice_path()` が常に `NULL` を返す現状で、voice なし動作が本番で常時使われている。

### 5.5 追加リスク一覧

| リスク | 重大度 | 詳細 |
|--------|--------|------|
| `open_jtalk` バイナリの `-m` なし動作 | 低 | システムの `open_jtalk` (apt 版等) は `-m` なしでエラーコード 1 を返す可能性がある。piper-plus ビルドの phonemizer バイナリが優先パスなので影響は限定的。フォールバック時のエラーメッセージに「phonemizer バイナリの使用を推奨」と表示することを検討 |

### 5.6 レビュー時チェックリスト

- [x] 変更が 5 ファイルのみであること (スコープ超過がないこと)
- [x] `get_openjtalk_voice_path` シンボルが `src/cpp/` 配下で完全に消滅していること
- [x] HTS voice 関連の 6 定数 (`HTS_VOICE_URL` 等) が消滅していること
- [x] `#if 0` ブロックが `openjtalk_dictionary_manager.c` から消滅していること
- [x] wrapper/optimized の `#ifdef _WIN32` 分岐が After コードと一致していること
- [x] `openjtalk_dictionary_manager.h` のエクスポート関数が `get_openjtalk_dictionary_path()` と `ensure_openjtalk_dictionary()` の 2 つのみであること
- [x] `HTSVoicePath` テストが削除されていること
- [x] コミットが 1 つであること (分割されていないこと)

## 6. ゼロから作り直すとしたら

### 6.1 なぜ HTS voice フォールバックが生まれたか

OpenJTalk は元来「テキスト → 音素 → HTS 音声合成」の完結型 TTS エンジンとして設計された。piper-plus が OpenJTalk を「音素抽出器」としてのみ利用し始めた時点で、本来なら HTS 合成パイプライン全体を切り離すべきだった。

しかし初期実装では以下の理由からフォールバックが残った:

1. **段階的移行の名残:** 最初は `open_jtalk` バイナリをそのまま呼び出していた。phonemizer バイナリ (`open_jtalk_phonemizer`) は後から追加された。移行期間中に `open_jtalk` フォールバックが「安全網」として残された
2. **防御的プログラミングの過剰適用:** 「phonemizer がない環境でも動くように」と voice 付きの `open_jtalk` フォールバックが追加された。しかし実際には phonemizer なし環境でも voice なしの `open_jtalk` で音素抽出は可能であり、voice フォールバックは二重の冗長だった
3. **Dead code の放置:** `get_openjtalk_voice_path()` が `return NULL` になった時点で voice 分岐は dead branch になったが、呼び出し元の条件分岐は残されたままだった

### 6.2 コンパイル時除去 vs ランタイム除去

今回の M1 では「ランタイムで NULL チェックしていた voice 分岐をソースコードから物理削除する」アプローチを取る。これは正しい判断だが、そもそも最初の設計段階で以下の 2 つの戦略を比較検討すべきだった:

**戦略 A: `#ifdef` によるコンパイル時除去 (推奨)**

```c
// CMakeLists.txt: option(PIPER_ENABLE_HTS_VOICE "Enable HTS voice fallback" OFF)

#ifdef PIPER_ENABLE_HTS_VOICE
    const char* voice_path = get_openjtalk_voice_path();
    if (voice_path) {
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -m \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
                 openjtalk_bin, dic_path, voice_path, output_file, input_file);
    } else
#endif
    {
        snprintf(command, sizeof(command),
                 "\"%s\" -x \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
                 openjtalk_bin, dic_path, output_file, input_file);
    }
```

- コンパイル時に HTS コードが完全に除外される。バイナリサイズ削減、dead code 分析ツールのノイズ排除
- CI で `PIPER_ENABLE_HTS_VOICE=OFF` ビルドを常時テストすれば、新たな HTS 依存の混入を自動検出できる
- 移行完了後に `#ifdef` ブロックごと削除するだけで済む

**戦略 B: ランタイム NULL チェック (現状)**

```c
const char* voice_path = get_openjtalk_voice_path();  // 常に NULL を返す
if (voice_path) { /* dead branch */ } else { /* 実際のパス */ }
```

- コードが残り続けるため、dead branch であることが自明でない
- 静的解析ツールが「到達可能だが到達しない」コードとして警告を出す可能性がある
- 新規開発者が「voice_path が NULL でない場合もあるのか」と混乱する

**教訓:** オプショナルな機能は最初から `#ifdef` またはビルドオプションで制御すべき。「関数が NULL を返すから実質無効」という暗黙の無効化は、コードの意図を不透明にする。

### 6.3 フォールバック設計のアンチパターン

今回の事例は「段階的移行で生まれたフォールバックが dead code 化する」という典型的なアンチパターンを示している。

**パターン:** 新パス (phonemizer) と旧パス (open_jtalk + voice) の共存期間に、旧パスの依存物 (voice) を「なくても動く」形で残す。その結果:
- 旧パスの依存物が必要なのか不要なのかがコードから読み取れなくなる
- 「あった方が良いかもしれない」という不確実性から削除が先送りされる
- 3段階ネスト (`is_phonemizer` > `voice_path != NULL` > `#ifdef _WIN32`) がコードの可読性を著しく損なう

**対策としてのフィーチャーフラグ方式:** 移行期間中は `#ifdef PIPER_LEGACY_OPEN_JTALK` のようなコンパイル時フラグで旧パスを明示的にガードし、移行完了後にフラグごと削除する。これなら:
- dead code が「レガシーフラグ内」として明示される
- `grep -r "PIPER_LEGACY_OPEN_JTALK"` で残存確認ができる
- CI でフラグ OFF ビルドを常時テストすることで、旧パスへの新たな依存追加を防げる

**Strangler Fig パターンの適用:** 今回の移行は本質的に Strangler Fig パターン (旧システムを新システムで徐々に置き換える) に該当する。しかし、このパターンを意識的に適用していなかったため、「旧パスがいつ完全に不要になったか」を判定する基準がなかった。次回の段階的移行では以下を実践すべき:
1. 移行開始時に「旧パスの削除条件」を明文化する (例: 「phonemizer バイナリが全 CI 環境で利用可能になった時点で削除」)
2. 旧パスの呼び出し回数をメトリクスとして計測する (例: `PIPER_LEGACY_FALLBACK_COUNT` カウンター)
3. 削除条件を満たしたら即座に削除する PR を作成する。「次のリリースで」と先送りしない

### 6.4 理想的なアーキテクチャ: Phonemizer-only 設計

ゼロから設計するなら、OpenJTalk 連携は以下の原則に従うべきだった:

**原則 1: 単一パス原則**

音素抽出には唯一のパスのみ用意する。フォールバック用の別パスは作らない。

```
テキスト → phonemizer バイナリ → 音素列
```

`open_jtalk` バイナリへのフォールバックは最初から設けない。phonemizer がなければ明確なエラーメッセージを出して停止する。「動くかもしれない代替パス」より「動かないなら即座に教える」の方がユーザーにとって有益である。

**原則 2: ビルド時依存の最小化**

HTS Engine はスタブで十分なら、最初からスタブのみをサポートする。`USE_HTS_ENGINE_STUB=OFF` のような「実 HTS Engine ビルド」オプションは設けない。必要になった時点で追加する (YAGNI)。この原則は M3 の CMake 変更 (実 HTS Engine パスの `FATAL_ERROR` 化) と一貫している。M3 で stub が唯一のパスになるのは、この原則を事後的に適用した結果である。

**原則 3: 環境変数は明示的に文書化し、不要になったら即座に削除**

`OPENJTALK_VOICE` のような環境変数は、参照コードの削除と同時にドキュメントからも削除する。「将来使うかもしれない」で残さない。

### 6.5 stub 戦略の評価

現在のプロジェクトでは `cmake/hts_engine_stub.h` と `cmake/hts_engine_stub.c` でHTS Engine の型定義を互換シムとして提供している。この戦略は以下の点で合理的である:

- OpenJTalk のヘッダー (`mecab.h` 等) が `HTS_engine.h` を `#include` するため、型定義がないとコンパイルできない
- stub は関数の実体を持たず、型定義のみ提供するため、リンク時に HTS Engine の実コードが不要になる
- stub ファイルは ~50行程度で保守コストが極めて低い

ただし、現状の stub は型定義だけでなく 20 以上の関数実装 (大半が `exit(1)` で即座に終了) を含んでおり、ヘッダーオンリーの stub よりも保守範囲が広い。M3 の stub 戦略評価 (ヘッダーオンリー化の検討) と合わせて、将来的に `.c` ファイルの削減が可能か検証すべきである。

### 6.6 OpenJTalk 自体のフォーク検討

根本的な解決策として、OpenJTalk のフォーク版で `HTS_engine.h` への依存自体を除去する方法がある。piper-plus が使う NJD + JPCommon パイプラインは HTS Engine と無関係であり、ヘッダーの include は歴史的な経緯にすぎない。

**選択肢の比較:**

| 選択肢 | メリット | デメリット |
|--------|---------|----------|
| 現状維持 (stub) | 上流追従が容易、変更最小 | stub の保守が永続的に必要 |
| pyopenjtalk-plus フォーク拡張 | 既に fork 済み、パッチ機構 (`patch_r9y9_openjtalk.cmake`) あり | OpenJTalk 内部の `#include` 除去は広範囲の変更 |
| jpreprocess (Rust) 完全移行 | HTS Engine 依存が構造的に存在しない。Rust 実装で型安全 | C++ ランタイムから Rust FFI を呼ぶ必要があり、ビルド複雑性が増す。辞書形式が lindera 形式で MeCab 形式と非互換 |

**現実的な推奨:** 現時点では stub 維持が最もコスト対効果が高い。jpreprocess は Rust ランタイム (`piper-core`) では既に使用しており、C++ ランタイムでも将来的に採用する場合は、Rust の C FFI エクスポート (`extern "C"`) 経由で統合する設計が考えられる。ただし、これは本マイルストーン群のスコープを大きく超えるため、別途検討する。

### 6.7 やってはいけないこと / 次回はこうする

**やってはいけないこと:**

1. **関数を `return NULL` にして「無効化した」と見なす。** 呼び出し元の分岐が残る限り dead code は消えない。無効化するなら `#ifdef` で物理的に囲むか、関数ごと削除する
2. **「念のため残しておく」フォールバック。** `get_openjtalk_voice_path()` が常に NULL を返す状態で voice 分岐を残すのは、コードの意図を不透明にするだけ
3. **定義の削除と呼び出しの削除を別コミットにする。** 中間状態でリンクエラーが発生する (本チケット 2.3 節参照)
4. **CI に実際に使われていない環境変数を設定する。** `OPENJTALK_VOICE="dummy.htsvoice"` は存在しないファイルを指しており、テストの意図を読み取れない

**次回はこうする:**

1. オプショナル機能は最初から `cmake option()` + `#ifdef` で制御する。ビルドマトリクスに ON/OFF 両方を含める
2. 段階的移行には明示的な「卒業条件」を設定する。条件を満たしたら旧パスを即座に削除する
3. dead code 検出を CI に組み込む。`-Wunreachable-code` や static analysis (例: `cppcheck --enable=unusedFunction`) を活用する

### 6.8 可逆性の判断

HTS voice 対応を将来的に復活させるコストについて、意識的に判断を記録する:

- **物理的な可逆性**: git history から削除コードを復元可能。`git revert` で全マイルストーンを巻き戻せる
- **stub の維持 (M3)**: `hts_engine_stub.h/c` を維持する判断自体が、OpenJTalk のヘッダー互換性という形で部分的な可逆性を担保している
- **復活が不要な根拠**: piper-plus は VITS アーキテクチャによるニューラル合成を採用しており、HTS パラメトリック合成は品質・アーキテクチャの両面で不要。この前提が変わらない限り、HTS voice 対応の復活は不要
- **判断**: 完全除去を選択する。復活が必要になった場合は git history からの復元で対応可能

### 6.9 Strategy パターンによるバックエンド抽象化

現在 3 つの音素抽出パスが `if-else` チェーンでインラインに共存している: (a) C API 直接呼び出し (`openjtalk_api.c`)、(b) phonemizer バイナリ経由、(c) open_jtalk バイナリフォールバック。共通インターフェースが定義されておらず、パスの追加・削除・テストが構造的に困難である。

ゼロから設計するなら、Strategy パターンで音素抽出バックエンドを抽象化すべきだった:

```c
typedef struct {
    const char* name;
    int  (*init)(const char* dic_path);
    OpenJTalkProsodyResult* (*extract)(const char* text);
    void (*cleanup)(void);
} PhonemeBackend;

PhonemeBackend* phoneme_backend_capi(void);    // openjtalk_api.c
PhonemeBackend* phoneme_backend_binary(void);  // phonemizer/open_jtalk
```

**利点:**
- バックエンドごとに独立したユニットテストが書ける
- jpreprocess (Rust FFI) バックエンドの追加が `PhonemeBackend` 実装の追加だけで完結する
- 使用されないバックエンドはリンクされないため、dead code が構造的に発生しない

**フォールバックの設計原則:** binary fallback は本質的にデバッグ/開発用途であり、`#ifdef PIPER_ENABLE_BINARY_FALLBACK` でコンパイル時に除外すべきである。「API が失敗したら暗黙的に binary に落ちる」挙動はデバッグを困難にする。

### 6.10 fullcontext パース処理の統合

fullcontext ラベルのパース処理 (`-phoneme+` の抽出、`/A:a1+a2+a3/` の抽出) が `openjtalk_wrapper.c`、`openjtalk_optimized.c`、`openjtalk_api.c` の 3 箇所にほぼ同一のコードとして重複している。`atoi()` と `strtol()` の混在 (wrapper.c L1119 vs api.c L554) など、実装の微妙な差異がバグの温床になっている。

ゼロから設計するなら `fullcontext_parser.c` として一箇所に集約すべきだった。現状の重複は M1 のスコープ外だが、後続のリファクタリングで統合を検討すべきである。

### 6.11 openjtalk_wrapper.c と openjtalk_optimized.c の統合検討

`openjtalk_wrapper.c` は `system()` ベース、`openjtalk_optimized.c` は `fork+exec` / `CreateProcess` + LRU キャッシュという最適化版だが、両方が公開 API (`openjtalk_text_to_phonemes` と `openjtalk_text_to_phonemes_optimized`) を提供しており、呼び出し側がどちらを使うべきか不明瞭である。

6.9 の Strategy パターンを導入すれば、キャッシュは decorator として独立させ、パス選択と直交する関心事として扱える。これにより wrapper と optimized の重複が解消される。

### 6.12 フィーチャーフラグ 2 層設計

現在の `USE_HTS_ENGINE_STUB` は「どの実装を使うか」というインフラレベルのフラグであり、「HTS voice 機能を有効にするか」という意味論が欠如している。ゼロから設計するなら 2 層のフラグが望ましい:

```cmake
# 層1: 機能フラグ (ユーザー向け)
option(PIPER_ENABLE_HTS_VOICE "Enable HTS voice synthesis fallback" OFF)

# 層2: 実装フラグ (内部) — 層1に従属
if(NOT PIPER_ENABLE_HTS_VOICE)
  target_compile_definitions(piper_common PUBLIC PIPER_NO_HTS_VOICE=1)
endif()
```

CI ビルドマトリクスに ON/OFF 両方を含めることで、依存混入を自動検出できる:

```yaml
strategy:
  matrix:
    hts_voice: [ON, OFF]
steps:
  - run: cmake -B build -DPIPER_ENABLE_HTS_VOICE=${{ matrix.hts_voice }}
```

`OFF` マトリクスで HTS 依存シンボルへのリンクが発生すれば即座にリンクエラーとなり、新たな依存混入を自動検出できる。移行完了後は `ON` マトリクスを削除して最終的にフラグ自体を削除する。

### 6.13 stub INTERFACE ライブラリ化

現在の `hts_engine_stub` は STATIC ライブラリとして `exit(1)` 関数実装を含む。OpenJTalk のパッチ (`patch_r9y9_openjtalk.cmake`) を拡張して HTS Engine リンク依存を除去すれば、ヘッダーオンリーの INTERFACE ライブラリに軽量化可能:

```cmake
# 理想形: ヘッダーオンリー stub
add_library(hts_engine_stub INTERFACE)
target_include_directories(hts_engine_stub INTERFACE cmake/stub_include)
add_library(hts_engine_external ALIAS hts_engine_stub)
```

これにより ExternalDeps.cmake の HTS Engine セクション (~95行) が ~10行に縮小し、POST_BUILD コマンド、プラットフォーム別の出力名設定、`add_custom_target` が全て不要になる。ALIAS により既存の `add_dependencies(... hts_engine_external)` が変更なしで動作する。

**前提条件:** OpenJTalk パッチで HTS Engine リンク依存を除去する必要がある。M3 スコープでの検証を推奨。

### 6.14 静的解析 CI の導入

C++ の CI に `clang-format` しかなく、**cppcheck / clang-tidy / カバレッジ計測がゼロ**。これが dead code 長期残存の根本原因である。

**推奨導入優先度:**

1. `cppcheck --enable=unusedFunction` — `get_openjtalk_voice_path()` のような「定義はあるが呼び出し元がない関数」を直接検出可能
2. `clang-tidy` の `clang-analyzer-deadcode.DeadStores` — 定数伝播で dead branch を検出
3. C++ カバレッジ CI (gcov/lcov) — dead branch の可視化、0% カバレッジ関数の警告
4. grep ベースの卒業条件監視 — 除去対象キーワードを CI で自動チェック

```yaml
# cppcheck CI ステップ例
- name: Run cppcheck
  run: |
    cppcheck --enable=unusedFunction,style \
      --suppress=missingIncludeSystem \
      --error-exitcode=1 \
      --inline-suppr \
      src/cpp/
```

### 6.15 C++ / C# ゴールデンテスト参加

`tests/fixtures/g2p/phoneme_test_cases.json` を Python/Rust/Go/WASM が共有テストフィクスチャとして使用しているが、**C# と C++ が不参加**。特に C++ の `openjtalk_api.c` は pyopenjtalk-plus 互換の NJD 後処理を独自に C ポートしており、Python 側との出力差異が検出されない状態にある。

**最優先改善:** C# と C++ をゴールデンテストに参加させ、5 ランタイムの音素化一貫性を保証する。これは OpenJTalk 脱却の長期ロードマップにおいても「移行前後で出力が変わらない」ことの検証基盤になる。

### 6.16 migration-lifecycle.toml による卒業条件管理

段階的移行の「卒業条件」を宣言的に管理するための仕組み:

```toml
# docs/spec/migration-lifecycle.toml
[migration.hts-voice-removal]
status = "in-progress"  # planned | in-progress | graduated | archived
introduced = "2026-04-11"
graduation_conditions = [
  "grep -r 'get_openjtalk_voice_path' src/cpp/ returns 0 hits",
  "grep -r 'HTS_VOICE' src/ returns 0 hits (stub除く)",
  "grep -r 'htsvoice' src/wasm/ returns 0 hits",
  "CI matrix に USE_HTS_ENGINE_STUB=OFF が存在しない",
]
reversibility = "git-revert"
rationale = "VITS architecture makes HTS parametric synthesis unnecessary"
```

**Feature Flag ライフサイクル:**
1. **導入**: `cmake option()` + ON/OFF 両方の CI マトリクス + lifecycle.toml にエントリ追加
2. **移行**: 旧パスのコード除去が進行。OFF ビルドで旧パスのカバレッジが 0% になる
3. **卒業**: 卒業条件を全て満たす。ON オプションを `FATAL_ERROR` に変更
4. **削除**: 卒業から 1 リリース後。`cmake option()` 自体を削除。stub 要否を再評価

## 7. 後続タスクへの連絡事項

### M3 (CI / CMake) への引き継ぎ

M3 は本チケット (M1) の完了を前提とする。以下の条件を確認してから M3 に着手すること:

1. **`get_openjtalk_voice_path()` の完全消滅:** M3 の CI ワークフロー変更 (voice 環境変数削除) は、C++ コードが voice パスを参照しなくなっていることが前提。`grep -r "get_openjtalk_voice_path" src/cpp/` が 0 件であることを M3 着手前に確認する

2. **`HTS_VOICE_*` 定数の消滅:** M3 の CMake 変更は、これらの定数がコンパイル単位から消えていることが前提。M3 で `ExternalDeps.cmake` の実 HTS Engine ビルドパスを `FATAL_ERROR` に置き換える際、C++ コードから voice 参照がないことを前提とする

3. **stub ファイルは維持:** M1 では `cmake/hts_engine_stub.h`, `cmake/hts_engine_stub.c` に一切手を加えない。M3 でも stub 自体は維持し、実 HTS Engine ビルドパスのみを廃止する

### M4 (テスト追加 + クリーンアップ) への引き継ぎ

M4 は M1-M3 全完了を前提とする。M4 のテストが検証すべき点:

1. **voice なしでの音素抽出テスト (4.1, 4.2):** `OPENJTALK_VOICE` 環境変数が未設定の状態で `openjtalk_text_to_phonemes_optimized()` が正常に音素列を返すことを検証する。M1 で除去した voice 分岐が、実際の音素抽出に影響を与えていないことの回帰テストとなる

2. **環境変数ドキュメント更新 (4.8):** M1 で C++ コードから `OPENJTALK_VOICE` 参照がなくなるため、M4 でドキュメントからも削除する。ただし WASM 側 (M2) でも完全に除去されていることを確認してから行う

3. **HTSVoicePath テスト削除の影響:** M1 で `HTSVoicePath` テストを削除するが、このテストはもともと不完全 (関数を呼び出していない) だった。M4 で代替テスト `PhonemeExtractionWithoutVoice` を追加することで、voice なし動作のカバレッジを実質的に向上させる
