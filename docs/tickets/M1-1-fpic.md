# M1-1: ExternalProject に `-fPIC` を追加

> **Phase:** 1 --- 基本 C API (MVP)
> **見積り:** 小
> **依存:** なし
> **ブロック:** M1-4
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m1-1-externalproject-に--fpic-を追加)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

Linux x86_64 で共有ライブラリ (`libpiper_plus.so`) をビルドする際、OpenJTalk / spdlog / hts_engine_stub の静的ライブラリが `-fPIC` なしでコンパイルされているため、リンク時に「relocation R_X86_64_32 against `.text` can not be used when making a shared object」エラーが発生する。このチケットでは、全ての ExternalProject と内部スタブライブラリに Position Independent Code (PIC) フラグを追加し、共有ライブラリビルドの前提条件を満たす。

**ゴール:** `-DPIPER_PLUS_BUILD_SHARED=ON` を指定したとき、Linux x86_64 で `-fPIC` 関連のリンクエラーが発生しないようにする。macOS / Windows のビルドが回帰しないことも確認する。

---

## 2. 実装する内容の詳細

### 変更対象ファイル

`CMakeLists.txt` (ルート) --- 1 ファイルのみ

### 具体的な変更内容

#### 2.1 OpenJTalk ExternalProject (L384-390 付近)

`OPENJTALK_CMAKE_ARGS` に `-DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON` を追加する。

```cmake
# 変更前
set(OPENJTALK_CMAKE_ARGS
  -DCMAKE_INSTALL_PREFIX:PATH=${OPENJTALK_DIR}
  -DCMAKE_BUILD_TYPE:STRING=${CMAKE_BUILD_TYPE}
  -DBUILD_SHARED_LIBS:BOOL=OFF
  -DCHARSET:STRING=utf8
  ${EXTERNAL_CMAKE_ARGS}
)

# 変更後
set(OPENJTALK_CMAKE_ARGS
  -DCMAKE_INSTALL_PREFIX:PATH=${OPENJTALK_DIR}
  -DCMAKE_BUILD_TYPE:STRING=${CMAKE_BUILD_TYPE}
  -DBUILD_SHARED_LIBS:BOOL=OFF
  -DCHARSET:STRING=utf8
  -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON
  ${EXTERNAL_CMAKE_ARGS}
)
```

#### 2.2 spdlog ExternalProject (L212-230 付近)

`CMAKE_ARGS` に `-DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON` を追加する。

```cmake
# 変更前
ExternalProject_Add(
  spdlog_external
  ...
  CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${SPDLOG_DIR}
             -DSPDLOG_BUILD_SHARED:BOOL=OFF
             -DSPDLOG_FMT_EXTERNAL:BOOL=ON
             -DCMAKE_PREFIX_PATH:PATH=${FMT_DIR}
             -DFMT_HEADER_ONLY:BOOL=ON
             ${EXTERNAL_CMAKE_ARGS}
)

# 変更後
ExternalProject_Add(
  spdlog_external
  ...
  CMAKE_ARGS -DCMAKE_INSTALL_PREFIX:PATH=${SPDLOG_DIR}
             -DSPDLOG_BUILD_SHARED:BOOL=OFF
             -DSPDLOG_FMT_EXTERNAL:BOOL=ON
             -DCMAKE_PREFIX_PATH:PATH=${FMT_DIR}
             -DFMT_HEADER_ONLY:BOOL=ON
             -DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON
             ${EXTERNAL_CMAKE_ARGS}
)
```

#### 2.3 hts_engine_stub 静的ライブラリ (L289 付近)

`set_target_properties` で `POSITION_INDEPENDENT_CODE ON` を設定する。

```cmake
# 変更前
add_library(hts_engine_stub STATIC ${CMAKE_CURRENT_SOURCE_DIR}/cmake/hts_engine_stub.c)
target_include_directories(hts_engine_stub PUBLIC ${HTS_ENGINE_DIR}/include)

# 変更後
add_library(hts_engine_stub STATIC ${CMAKE_CURRENT_SOURCE_DIR}/cmake/hts_engine_stub.c)
target_include_directories(hts_engine_stub PUBLIC ${HTS_ENGINE_DIR}/include)
set_target_properties(hts_engine_stub PROPERTIES POSITION_INDEPENDENT_CODE ON)
```

#### 2.4 hts_engine_external (autotools, L343-368 付近)

autotools ビルドの `CONFIGURE_ENV` に `CFLAGS=-fPIC` を追加する。既存の `CONFIGURE_ENV` にアーキテクチャ別フラグが設定されている場合はそれに追加する。

```cmake
# 変更前 (x86_64 Linux の場合)
set(CONFIGURE_HOST "")
set(CONFIGURE_ENV "")

# 変更後
set(CONFIGURE_HOST "")
set(CONFIGURE_ENV "CFLAGS=-fPIC")
```

ARM64 / Apple Silicon の場合は既存の `CFLAGS` に `-fPIC` を追記する:

```cmake
# 変更前
set(CONFIGURE_ENV "CFLAGS=-arch arm64" "CXXFLAGS=-arch arm64" "LDFLAGS=-arch arm64")

# 変更後
set(CONFIGURE_ENV "CFLAGS=-arch arm64 -fPIC" "CXXFLAGS=-arch arm64" "LDFLAGS=-arch arm64")
```

Linux ARM64 の場合も同様:

```cmake
# 変更前
set(CONFIGURE_ENV "CC=aarch64-linux-gnu-gcc" ...)

# 変更後
set(CONFIGURE_ENV "CC=aarch64-linux-gnu-gcc" "CFLAGS=-fPIC" ...)
```

**注意:** macOS は常に PIC であり、Windows は MSVC CMake ビルドで `CMAKE_POSITION_INDEPENDENT_CODE` を渡す (L327-342)。autotools の `-fPIC` 追加は Unix 系のみ。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | CMakeLists.txt の 4 箇所を修正 |

合計: 1 名。変更箇所は 1 ファイル内の 4 箇所で、全て CMake 設定の追加のみ。

---

## 4. 提供範囲とテスト項目

### スコープ

- `CMakeLists.txt` の ExternalProject / スタブライブラリに `-fPIC` / `POSITION_INDEPENDENT_CODE ON` を追加

### スコープ外

- `piper_plus` 共有ライブラリターゲットの作成 (M1-4)
- `-static-libstdc++` の分離 (M1-2)

### テスト項目

| テスト | 方法 | 期待結果 |
|--------|------|----------|
| Linux x86_64 ビルド (静的リンク) | `cmake -B build && cmake --build build` | 既存の `piper` / `test_piper` が回帰なくビルド成功 |
| macOS ARM64 ビルド | `cmake -B build && cmake --build build` | 既存ビルドが回帰しない |
| PIC 確認 (手動) | `readelf -d build/oj/lib/libopenjtalk.a \| grep TEXTREL` | TEXTREL なし |
| PIC 確認 (手動) | `readelf -d build/si/lib/libspdlog.a \| grep TEXTREL` | TEXTREL なし |

**注意:** 実際の共有ライブラリビルドでの検証は M1-4 以降。このチケットでは静的ライブラリの `-fPIC` 付与のみを確認する。

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | 影響度 | 対策 |
|------|--------|------|
| `-fPIC` によるパフォーマンス低下 | 低 (1% 未満) | TTS の推論は ONNX Runtime がボトルネックであり、G2P ライブラリの `-fPIC` オーバーヘッドは無視できる |
| autotools ビルドの `CFLAGS` 追加方法 | 低 | 既存の `CONFIGURE_ENV` にリスト項目として追加するのみ。CMake の `list(APPEND)` ではなく直接文字列に `-fPIC` を付加 |
| Windows MSVC への影響 | なし | MSVC は常に PIC 相当。`CMAKE_POSITION_INDEPENDENT_CODE` は MSVC では無視される |

### レビュー項目

- [ ] `OPENJTALK_CMAKE_ARGS` に `-DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON` が追加されているか
- [ ] `spdlog_external` の `CMAKE_ARGS` に同フラグが追加されているか
- [ ] `hts_engine_stub` に `POSITION_INDEPENDENT_CODE ON` が設定されているか
- [ ] `hts_engine_external` (autotools) の全アーキテクチャ分岐で `CFLAGS=-fPIC` が追加されているか
- [ ] 既存の `piper` / `test_piper` ビルドが回帰しないか

---

## 6. 一から作り直すとしたら

プロジェクト初期に全ての静的ライブラリを `CMAKE_POSITION_INDEPENDENT_CODE=ON` でビルドするポリシーを設定する。CMake のグローバル変数 `set(CMAKE_POSITION_INDEPENDENT_CODE ON)` をルート `CMakeLists.txt` の冒頭に置けば、全ての `add_library(STATIC ...)` と ExternalProject の CMake ビルドに自動適用される。ただし、autotools ベースの ExternalProject (hts_engine_external) には適用されないため、個別の `CFLAGS` 指定は依然として必要。

最初から共有ライブラリビルドを想定していれば、ExternalProject 定義時に PIC フラグを含めており、この修正チケット自体が不要だった。

---

## 実装推奨

> **M1-4 と同一 PR で対応すること。** M1-1 (fPIC) は M1-4 (CMake SHARED + OBJECT ライブラリ) のビルド前提条件であり、ビルドシステム変更を 1 つの PR に集約した方がレビュー効率が高い。振り返りで「M1-1 + M1-2 + M1-4 は統合可能だった」と指摘されている (c-api-milestones.md Phase 1 振り返り参照)。

---

## 7. 後続タスクへの連絡事項

- **M1-4 (CMake SHARED):** このチケットの完了により、`piper_plus` SHARED ライブラリターゲットから OpenJTalk / spdlog / hts_engine_stub を `-fPIC` エラーなしでリンクできるようになる。M1-4 では `piper_common` OBJECT ライブラリの `POSITION_INDEPENDENT_CODE ON` を別途設定すること。
- **fmt_external について:** fmt はヘッダーオンリー (`FMT_HEADER_ONLY=ON`) でビルドされているため、`-fPIC` の追加は不要。ただし、将来ヘッダーオンリーからライブラリビルドに切り替える場合は同様の対応が必要。
