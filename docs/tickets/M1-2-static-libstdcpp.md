# M1-2: `-static-libstdc++` を共有ライブラリに適用しない

> **Phase:** 1 --- 基本 C API (MVP)
> **見積り:** 小
> **依存:** なし (M1-4 と同時に実装)
> **ブロック:** M1-6
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m1-2--static-libstdc-を共有ライブラリに適用しない)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

現在の `CMakeLists.txt` (L461) では Linux ビルド時に `piper` 実行ファイルに `-static-libgcc -static-libstdc++` をリンクしている。これは実行ファイルの配布を容易にする目的で正しいが、共有ライブラリ (`libpiper_plus.so`) にも同じフラグを適用すると以下の問題が起きる:

1. **例外テーブルの分離**: ライブラリ内部の `libstdc++` コピーとホストアプリの `libstdc++` が二重に存在し、C++ 例外の `catch` が失敗する可能性がある
2. **不要な肥大化**: 共有ライブラリに `libstdc++` が内包され、ファイルサイズが増大する

**ゴール:** `-static-libgcc -static-libstdc++` を `piper` 実行ファイルのみに限定し、共有ライブラリには適用しないようにする。

---

## 2. 実装する内容の詳細

### 変更対象ファイル

`CMakeLists.txt` (ルート) --- 1 ファイルのみ

### 具体的な変更内容

#### 2.1 現在のコード (L454-464)

```cmake
if(APPLE)
  set(PIPER_EXTRA_LIBRARIES "pthread")
elseif(NOT MSVC)
  # Linux flags
  string(APPEND CMAKE_CXX_FLAGS " -Wall -Wextra -Wl,-rpath,'$ORIGIN'")
  string(APPEND CMAKE_C_FLAGS " -Wall -Wextra")
  target_link_libraries(piper PRIVATE -static-libgcc -static-libstdc++)

  set(PIPER_EXTRA_LIBRARIES "pthread")
endif()
```

#### 2.2 変更後のコード

`-static-libgcc -static-libstdc++` は既に `piper` ターゲットのみに `target_link_libraries` されているため、現在のコードは正しい。ただし、以下の修正が必要:

1. **L459 のグローバルリンカフラグ除去:** `-Wl,-rpath,'$ORIGIN'` はグローバル `CMAKE_CXX_FLAGS` に含まれているため、共有ライブラリにも適用される。これを `piper` ターゲット固有に移動する。

```cmake
if(APPLE)
  set(PIPER_EXTRA_LIBRARIES "pthread")
elseif(NOT MSVC)
  # Linux flags (compile flags only - no linker flags in global scope)
  string(APPEND CMAKE_CXX_FLAGS " -Wall -Wextra")
  string(APPEND CMAKE_C_FLAGS " -Wall -Wextra")

  # Static linking of C++ runtime for the piper executable only.
  # Shared library (piper_plus) must NOT use -static-libstdc++ to avoid
  # dual libstdc++ and exception table isolation issues.
  target_link_libraries(piper PRIVATE -static-libgcc -static-libstdc++)
  target_link_options(piper PRIVATE "-Wl,-rpath,$ORIGIN")

  set(PIPER_EXTRA_LIBRARIES "pthread")
endif()
```

2. **M1-4 実装時の注意:** `piper_plus` SHARED ターゲットには以下のフラグを設定する (M1-4 で実装):

```cmake
# piper_plus 共有ライブラリ: -static-libstdc++ を適用しない
# RPATH は $ORIGIN (ライブラリ自身の位置) に設定
if(NOT MSVC AND NOT APPLE)
  set_target_properties(piper_plus PROPERTIES
    INSTALL_RPATH "$ORIGIN"
    BUILD_WITH_INSTALL_RPATH TRUE
  )
endif()
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | CMakeLists.txt のリンカフラグ修正 |

合計: 1 名。M1-4 と同時に実装するため、M1-4 担当エージェントと同一人物が望ましい。

---

## 4. 提供範囲とテスト項目

### スコープ

- `-Wl,-rpath,'$ORIGIN'` をグローバル `CMAKE_CXX_FLAGS` から `piper` ターゲット固有に移動
- `-static-libgcc -static-libstdc++` が `piper` のみに適用されることを明示的にコメント記載

### スコープ外

- `piper_plus` SHARED ターゲットの作成 (M1-4)
- macOS / Windows の変更 (影響なし)

### テスト項目

| テスト | 方法 | 期待結果 |
|--------|------|----------|
| `piper` 実行ファイルの静的リンク確認 | `ldd build/piper \| grep libstdc++` | 出力なし (静的リンクされている) |
| `piper_plus` の動的リンク確認 (M1-4 後) | `ldd build/libpiper_plus.so \| grep libstdc++` | `libstdc++.so.6 => ...` が表示される |
| `piper` の RPATH 確認 | `readelf -d build/piper \| grep RPATH` | `$ORIGIN` を含む |
| macOS ビルド回帰 | `cmake -B build && cmake --build build` | 成功 |
| Windows ビルド回帰 | CI で確認 | 成功 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | 影響度 | 対策 |
|------|--------|------|
| `CMAKE_CXX_FLAGS` から `-Wl,-rpath` を除去する影響 | 低 | `piper` ターゲットには `target_link_options` で同等のフラグを設定。`test_piper` には既存の `CMAKE_INSTALL_RPATH` 設定 (L45-47) が適用される |
| `test_piper` の RPATH | 低 | `test_piper` は CTest 経由で実行されるため、`LD_LIBRARY_PATH` またはビルドディレクトリ内のライブラリパスが使われる。CI では ONNX Runtime をシステムディレクトリにインストール済み |

### レビュー項目

- [ ] `piper` 実行ファイルに `-static-libgcc -static-libstdc++` が適用されているか
- [ ] `CMAKE_CXX_FLAGS` からリンカ固有フラグ (`-Wl,-rpath`) が除去されているか
- [ ] `piper` に `target_link_options` で RPATH が設定されているか
- [ ] M1-4 実装時に `piper_plus` に `-static-libstdc++` が**適用されない**ことが明示されているか

---

## 6. 一から作り直すとしたら

`CMAKE_CXX_FLAGS` にリンカフラグ (`-Wl,-rpath`) を追加するのは CMake のアンチパターンである。最初からターゲット固有の `target_link_options` / `target_compile_options` を使い、グローバルフラグは警告レベル (`-Wall -Wextra`) のみに限定すべきだった。

また、`-static-libstdc++` はターゲット種別 (実行ファイル vs 共有ライブラリ) で自動判定するヘルパー関数を用意すると、ターゲット追加時の見落としを防げる:

```cmake
function(piper_set_runtime_linkage target)
  get_target_property(target_type ${target} TYPE)
  if(target_type STREQUAL "EXECUTABLE" AND NOT MSVC AND NOT APPLE)
    target_link_libraries(${target} PRIVATE -static-libgcc -static-libstdc++)
  endif()
endfunction()
```

---

## 実装推奨

> **M1-4 と同一 PR で対応すること。** M1-2 (-static-libstdc++) は M1-4 (CMake SHARED + OBJECT ライブラリ) のリンカフラグ分離であり、同一の CMakeLists.txt 変更に含めた方が整合性が高い。振り返りで「M1-1 + M1-2 + M1-4 は統合可能だった」と指摘されている (c-api-milestones.md Phase 1 振り返り参照)。

---

## 7. 後続タスクへの連絡事項

- **M1-4 (CMake SHARED):** `piper_plus` SHARED ターゲットを追加する際、以下を確認すること:
  1. `-static-libgcc -static-libstdc++` が `piper_plus` に適用されて**いない**こと
  2. Linux RPATH は `$ORIGIN` を `INSTALL_RPATH` で設定すること (グローバル `CMAKE_CXX_FLAGS` ではなく)
  3. macOS RPATH は `@loader_path` を使用すること (`@executable_path` ではない)
- **M1-8 (CI):** CI の Linux ジョブで `ldd libpiper_plus.so` を実行し、`libstdc++.so` が動的リンクされていることを検証するステップを追加すること
