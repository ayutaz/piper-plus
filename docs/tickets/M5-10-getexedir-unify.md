# M5-10: getExeDir() 統一

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 低 -- 内部コード品質改善 (ユーザーへの直接影響なし)
> **見積り:** 小
> **依存:** Phase 1 完了 (M1-3)
> **ブロック:** なし
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Closed

---

## 1. タスク目的とゴール

`getExeDir()` が `piper.cpp`, `model_manager.cpp` で重複定義されている。これらを `library_path.h` / `library_path.c` に統一し、コード重複を排除する。

**重要:** `getExeDir()` と既存の `piper_plus_get_library_dir()` は**根本的に異なる目的の関数**であり、単純な統一はできない。

| 関数 | 目的 | 取得対象 | 使用 API | 用途 |
|------|------|----------|----------|------|
| `getExeDir()` | **実行可能ファイル**の場所を取得 | CLI バイナリのディレクトリ | `/proc/self/exe` (Linux), `_NSGetExecutablePath` (macOS), `GetModuleFileName(NULL, ...)` (Windows) | CLI から辞書・モデルを exe 相対パスで検索 |
| `piper_plus_get_library_dir()` | **共有ライブラリ自身**の場所を取得 | `libpiper_plus.so/.dylib/.dll` のディレクトリ | `dladdr` (Unix), `GetModuleHandleEx(FROM_ADDRESS, ...)` (Windows) | C API ユーザーがライブラリ同梱リソースを検索 |

**現状:**
- `src/cpp/piper.cpp` L492: `static std::filesystem::path getExeDir()` -- `/proc/self/exe` (Linux) / `_NSGetExecutablePath` (macOS) / `GetModuleFileName` (Windows)
- `src/cpp/model_manager.cpp` L97: `static fs::path getExeDir()` -- 同一ロジックの重複実装
- `src/cpp/library_path.h` / `library_path.c`: 既に `piper_plus_get_library_dir()` (共有ライブラリ向け `dladdr` ベース) を提供済み

**ゴール:** `library_path.h` に `piper_plus_get_exe_dir()` を**追加**し、`piper.cpp` と `model_manager.cpp` の `getExeDir()` を置き換える。`piper_plus_get_library_dir()` はそのまま残し、両関数は並列に共存する。

---

## 2. 実装する内容の詳細

### 2.1 設計方針: 2つの低レベル関数の共存

`library_path.h` は「パス取得ユーティリティ」ヘッダーとして、用途の異なる2つの関数を提供する。

```
library_path.h
├── piper_plus_get_library_dir()  -- 既存: 共有ライブラリの場所 (dladdr ベース)
└── piper_plus_get_exe_dir()      -- 新規: 実行可能ファイルの場所 (/proc/self/exe ベース)
```

両者は**取得対象が異なる**ため、置き換え不可能である。

- CLI バイナリ (`piper`, `model_manager`) は `piper_plus_get_exe_dir()` を使用する
- 共有ライブラリ (`libpiper_plus`) 経由の C API 呼び出し元は `piper_plus_get_library_dir()` を使用する

### 2.2 library_path.h の変更

既存の `piper_plus_get_library_dir` 宣言の下に追加:

```c
/** Get the directory containing the current executable.
 *  Uses /proc/self/exe (Linux), _NSGetExecutablePath (macOS),
 *  GetModuleFileName(NULL) (Windows).
 *
 *  NOTE: This returns the *executable* path, NOT the shared library path.
 *  For the shared library directory, use piper_plus_get_library_dir().
 *
 *  @param buf    Output buffer for the directory path
 *  @param size   Buffer size in bytes
 *  @return 0 on success, -1 on failure */
int piper_plus_get_exe_dir(char *buf, int size);
```

### 2.3 library_path.c の変更

既存の `piper.cpp` / `model_manager.cpp` の `getExeDir()` ロジックを C 関数として移植。既存の `piper_plus_get_library_dir()` 実装とは完全に独立した関数として追加する。

### 2.4 各ファイルの変更

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/library_path.h` | `piper_plus_get_exe_dir` 宣言追加 (既存の `piper_plus_get_library_dir` はそのまま) |
| `src/cpp/library_path.c` | `piper_plus_get_exe_dir` 実装追加 (既存の `piper_plus_get_library_dir` はそのまま) |
| `src/cpp/piper.cpp` | `static getExeDir()` を削除、`piper_plus_get_exe_dir()` を使用 |
| `src/cpp/model_manager.cpp` | `static getExeDir()` を削除、`piper_plus_get_exe_dir()` を使用 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | 関数追加 + 既存テスト回帰確認 |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### ユニットテスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestGetExeDir` | `piper_plus_get_exe_dir()` 呼び出し | 非空のパスが返る |
| `TestGetExeDirSmallBuffer` | バッファサイズ 1 で呼び出し | -1 (エラー) |
| `TestGetExeDirNull` | NULL バッファで呼び出し | -1 (エラー) |
| `TestGetLibraryDirStillWorks` | `piper_plus_get_library_dir()` が変更後も動作 | 既存動作を維持 |

### 回帰テスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| 既存 CLI テスト | `piper.cpp` の辞書検出が引き続き動作 | パス検出成功 |
| 既存モデルマネージャテスト | `model_manager.cpp` のパス検出が動作 | パス検出成功 |

---

## 5. 懸念事項とレビュー項目

| リスク | 影響度 | 対策 |
|--------|--------|------|
| `std::filesystem::path` と `char*` の型変換 | 低 | `piper.cpp` / `model_manager.cpp` 側で `char buf[]` -> `fs::path(buf)` に変換 |
| C と C++ の混合リンク | 低 | `library_path.h` は既に `extern "C"` ガード済み |
| 実行可能ファイルパスとライブラリパスの混同リスク | 中 | `piper_plus_get_exe_dir()` と `piper_plus_get_library_dir()` は名前が類似しているため、誤って逆の関数を使うリスクがある。ヘッダー内のドキュメントコメントで用途の違いを明記し、レビュー時に呼び出し元の文脈が正しいことを確認する |

### レビュー時の確認項目

1. `piper.cpp` と `model_manager.cpp` の `static getExeDir()` が完全に削除されていること
2. `library_path.c` の各プラットフォーム分岐が既存実装と同等であること
3. CMakeLists.txt で `library_path.c` が CLI ビルドにもリンクされていること
4. `piper_plus_get_exe_dir()` と `piper_plus_get_library_dir()` が混同されていないこと -- CLI コードは前者、C API コードは後者を使用していること

---

## 6. 一から作り直すとしたら

`piper_plus_get_library_dir()` と `piper_plus_get_exe_dir()` の2つの低レベル関数を基盤として、用途別の高レベル関数を提供する設計の方が利用者にとって分かりやすい。

```
高レベル API (将来検討)
├── piper_plus_find_dict_dir()   -- 辞書検索: exe相対 or lib相対 or 環境変数
└── piper_plus_find_model_dir()  -- モデル検索: exe相対 or lib相対 or 環境変数

低レベル API (本チケットで整備)
├── piper_plus_get_exe_dir()     -- 実行可能ファイルのディレクトリ
└── piper_plus_get_library_dir() -- 共有ライブラリのディレクトリ
```

高レベル関数は内部で呼び出し元のコンテキストに応じて適切な低レベル関数を選択する。例えば `piper_plus_find_dict_dir()` は以下の優先順で検索する:

1. 環境変数 `PIPER_DICTIONARIES_PATH` (明示指定)
2. モデルと同じディレクトリ (モデルローカル)
3. `piper_plus_get_exe_dir()` 相対パス -- CLI 利用時 (`<exe>/../share/piper/dicts/`)
4. `piper_plus_get_library_dir()` 相対パス -- 共有ライブラリ利用時 (`<lib>/../share/piper/dicts/`)

ただし Phase 5 では低レベル関数の重複排除に留め、高レベル API は将来検討とする。

---

## 7. 後続タスクへの連絡事項

- 共有ライブラリモードでは `piper_plus_get_library_dir()` (`dladdr` ベース) を使用し、CLI モードでは `piper_plus_get_exe_dir()` (`/proc/self/exe` ベース) を使用する。この使い分けを明確にすること。
- 両関数は**異なるパスを返す**ことに注意。CLI バイナリから直接呼び出す場合は同じパスを返すこともあるが、共有ライブラリ経由でホストアプリから呼び出す場合は異なるパスを返す。
