# M5-10: getExeDir() 統一

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 低 -- 内部コード品質改善 (ユーザーへの直接影響なし)
> **見積り:** 小
> **依存:** Phase 1 完了 (M1-3)
> **ブロック:** なし
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

`getExeDir()` が `piper.cpp`, `model_manager.cpp` で重複定義されている。また `openjtalk_dictionary_manager.c` にも類似の実行パス取得コードがある。これらを `library_path.h` / `library_path.c` に統一し、コード重複を排除する。

**現状:**
- `src/cpp/piper.cpp` L492: `static std::filesystem::path getExeDir()` -- `/proc/self/exe` (Linux) / `_NSGetExecutablePath` (macOS) / `GetModuleFileName` (Windows)
- `src/cpp/model_manager.cpp` L97: `static fs::path getExeDir()` -- 同一ロジックの重複実装
- `src/cpp/library_path.h` / `library_path.c`: 既に `piper_plus_get_library_dir()` (共有ライブラリ向け `dladdr` ベース) を提供済み

**ゴール:** `library_path.h` に `piper_plus_get_exe_dir()` を追加し、`piper.cpp` と `model_manager.cpp` の `getExeDir()` を置き換える。

---

## 2. 実装する内容の詳細

### 2.1 library_path.h の変更

```c
/** Get the directory containing the current executable.
 *  Uses /proc/self/exe (Linux), _NSGetExecutablePath (macOS),
 *  GetModuleFileName (Windows).
 *
 *  @param buf    Output buffer for the directory path
 *  @param size   Buffer size in bytes
 *  @return 0 on success, -1 on failure */
int piper_plus_get_exe_dir(char *buf, int size);
```

### 2.2 library_path.c の変更

既存の `piper.cpp` / `model_manager.cpp` の `getExeDir()` ロジックを C 関数として移植。

### 2.3 各ファイルの変更

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/library_path.h` | `piper_plus_get_exe_dir` 宣言追加 |
| `src/cpp/library_path.c` | `piper_plus_get_exe_dir` 実装追加 |
| `src/cpp/piper.cpp` | `static getExeDir()` を削除、`piper_plus_get_exe_dir()` を使用 |
| `src/cpp/model_manager.cpp` | `static getExeDir()` を削除、`piper_plus_get_exe_dir()` を使用 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | 関数統一 + 既存テスト回帰確認 |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### ユニットテスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestGetExeDir` | `piper_plus_get_exe_dir()` 呼び出し | 非空のパスが返る |
| `TestGetExeDirSmallBuffer` | バッファサイズ 1 で呼び出し | -1 (エラー) |
| `TestGetExeDirNull` | NULL バッファで呼び出し | -1 (エラー) |

### 回帰テスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| 既存 CLI テスト | `piper.cpp` の辞書検出が引き続き動作 | パス検出成功 |
| 既存モデルマネージャテスト | `model_manager.cpp` のパス検出が動作 | パス検出成功 |

---

## 5. 懸念事項とレビュー項目

| リスク | 影響度 | 対策 |
|--------|--------|------|
| `std::filesystem::path` と `char*` の型変換 | 低 | `piper.cpp` / `model_manager.cpp` 側で `char buf[]` → `fs::path(buf)` に変換 |
| C と C++ の混合リンク | 低 | `library_path.h` は既に `extern "C"` ガード済み |

### レビュー時の確認項目

1. `piper.cpp` と `model_manager.cpp` の `static getExeDir()` が完全に削除されていること
2. `library_path.c` の各プラットフォーム分岐が既存実装と同等であること
3. CMakeLists.txt で `library_path.c` が CLI ビルドにもリンクされていること

---

## 6. 一から作り直すとしたら

`piper_plus_get_library_dir` と `piper_plus_get_exe_dir` の両方を提供するのではなく、用途別の高レベル関数 (`piper_plus_find_dict_dir`, `piper_plus_find_model_dir`) を提供する設計の方が利用者にとって分かりやすい。ただし Phase 5 では低レベル関数の統一に留め、高レベル API は将来検討。

---

## 7. 後続タスクへの連絡事項

- 共有ライブラリモードでは `piper_plus_get_library_dir()` (dladdr ベース) を使用し、CLI モードでは `piper_plus_get_exe_dir()` を使用する使い分けを明確にすること。
