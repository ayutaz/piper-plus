# M5-15: CMakeLists.txt ファイル分割

> **Phase:** 5 -- 低優先度改善
> **利用者視点の優先度:** 低 -- 開発者体験の改善 (エンドユーザーには不可視)
> **見積り:** 中
> **依存:** Phase 4 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

1,080 行超のルート `CMakeLists.txt` を機能単位で 8 ファイルに分割し、保守性と可読性を向上させる。

**現状の問題:** ルート `CMakeLists.txt` にコンパイラ設定、外部依存 (ExternalProject)、OBJECT ライブラリ、共有ライブラリ、実行ファイル、テスト、install ルールが全て混在。Phase 1-4 の機能追加で肥大化が加速している。

**ゴール:** `cmake/` ディレクトリに分割し、ルート `CMakeLists.txt` は `include()` のみの ~50 行に縮小する。

---

## 2. 実装する内容の詳細

### 2.1 分割構成

| ファイル | 内容 | 推定行数 |
|----------|------|----------|
| `cmake/CompilerSettings.cmake` | C/C++ 標準、警告フラグ、-fPIC、-static-libstdc++ | ~60 |
| `cmake/ExternalDeps.cmake` | ExternalProject (OpenJTalk, spdlog, hts_engine) + FetchContent | ~250 |
| `cmake/OnnxRuntime.cmake` | ONNX Runtime ダウンロード + プラットフォーム分岐 | ~150 |
| `cmake/PiperCommon.cmake` | piper_common OBJECT ライブラリ定義 | ~80 |
| `cmake/PiperPlusShared.cmake` | piper_plus SHARED ライブラリ + RPATH + install | ~120 |
| `cmake/PiperExecutable.cmake` | piper 実行ファイルターゲット | ~80 |
| `cmake/Testing.cmake` | テストターゲット (test_c_api, test_c_api_integration) | ~100 |
| `cmake/Install.cmake` | 配布 install ルール (ORT 同梱、辞書等) | ~80 |

### 2.2 ルート CMakeLists.txt (分割後)

```cmake
cmake_minimum_required(VERSION 3.14)
project(piper VERSION 1.10.0 LANGUAGES C CXX)

option(PIPER_PLUS_BUILD_SHARED "Build shared library" ON)
option(PIPER_PLUS_BUILD_TESTS  "Build tests"          ON)
# ... (他の option)

include(cmake/CompilerSettings.cmake)
include(cmake/ExternalDeps.cmake)
include(cmake/OnnxRuntime.cmake)
include(cmake/PiperCommon.cmake)

if(PIPER_PLUS_BUILD_SHARED)
    include(cmake/PiperPlusShared.cmake)
endif()

include(cmake/PiperExecutable.cmake)

if(PIPER_PLUS_BUILD_TESTS)
    include(cmake/Testing.cmake)
endif()

include(cmake/Install.cmake)
```

### 2.3 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `CMakeLists.txt` | 大幅縮小 (~50行) |
| `cmake/*.cmake` (8ファイル新規) | 機能別に分割 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | CMake 分割 + 全プラットフォームビルド検証 |

合計 1 名。ロジック変更なし、ファイル分割のみ。

---

## 4. 提供範囲とテスト項目

### スコープ

- ルート CMakeLists.txt の分割
- 新規 cmake/ ファイル 8 つの作成
- 既存ビルドの回帰なし

### テスト項目

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| Linux ビルド | `cmake -B build && cmake --build build` | 成功 (既存テスト全 PASS) |
| macOS ビルド | 同上 | 成功 |
| Windows ビルド | 同上 | 成功 |
| 共有ライブラリ OFF | `-DPIPER_PLUS_BUILD_SHARED=OFF` | piper 実行ファイルのみビルド |
| テスト OFF | `-DPIPER_PLUS_BUILD_TESTS=OFF` | テストターゲットなし |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| 変数スコープの変化 | 中 | `include()` は呼び出し元スコープを共有するので影響なし。`add_subdirectory()` とは異なる |
| CI キャッシュ無効化 | 低 | CMakeLists.txt のハッシュ変更で CI キャッシュが無効になるが一時的 |
| ExternalProject のパス依存 | 中 | `CMAKE_CURRENT_SOURCE_DIR` / `CMAKE_CURRENT_BINARY_DIR` が正しいか全箇所で確認 |

### レビュー時の確認項目

1. 分割前後で `cmake --build` の出力 (ターゲット一覧) が同一であること
2. `include()` 順序の依存関係が正しいこと (ExternalDeps が CompilerSettings の後等)
3. 変数定義が分割ファイル間で意図せず上書きされていないこと

---

## 6. 一から作り直すとしたら

Phase 1 の M1-4 で共有ライブラリターゲットを追加した時点で分割すべきだった。CMake のベストプラクティスでは 200 行を超えたら分割を検討する。1,080 行は明らかに遅すぎる。

---

## 7. 後続タスクへの連絡事項

- **M5-20 (Android AAR):** Android NDK のクロスコンパイル設定は `cmake/` に新ファイルとして追加しやすくなる。
- **新ターゲット追加:** 分割後は対応する cmake/ ファイルに追記するルールを CONTRIBUTING.md に記載すること。
