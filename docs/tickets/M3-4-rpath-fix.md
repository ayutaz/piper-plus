# M3-4: macOS RPATH 修正 + プラットフォーム別リンク設定

> **Phase:** 3 — 配布
> **見積り:** 小
> **依存:** M3-1
> **ブロック:** M3-5
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m3-4-macos-rpath-修正--プラットフォーム別リンク設定)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

> **注意 (振り返り反映):** `piper_plus` の RPATH 設定 (Linux `$ORIGIN`, macOS `@loader_path`) は **M1-4 で対応済み**。本チケットでは M1-4 のスコープ外である ONNX Runtime の install_name 修正 (macOS) と install 後の RPATH 検証のみを対象とする。

M3-1 で install レイアウトが整備された後、install された ONNX Runtime の install_name が正しく設定されていないと、RPATH 経由の解決が失敗する。

**M1-4 で対応済みの項目:**
- macOS: `piper_plus` の `INSTALL_RPATH "@loader_path"`, `INSTALL_NAME_DIR ""`
- Linux: `piper_plus` の `INSTALL_RPATH "$ORIGIN"`

**本チケットで対応する項目:**
- macOS: ONNX Runtime dylib の `install_name` を `@rpath/...` に修正
- install 後の RPATH 検証テスト

**ゴール:**

| プラットフォーム | 設定 | 動作 |
|----------------|------|------|
| Linux | (M1-4 で設定済み) | `lib/libpiper_plus.so` が同じ `lib/` 内の `libonnxruntime.so` を見つける |
| macOS | ORT install_name 修正 | `lib/libpiper_plus.dylib` が同じ `lib/` 内の `libonnxruntime.dylib` を RPATH 経由で見つける |
| Windows | N/A (DLL 検索パスで解決) | `piper_plus.dll` と `onnxruntime.dll` が同じディレクトリにあれば動作 |

---

## 2. 実装する内容の詳細

### 2.1 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `CMakeLists.txt` | `piper_plus` ターゲットの RPATH 設定修正、ONNX Runtime install name 修正 |

### 2.2 piper_plus の RPATH 設定 (M1-4 で対応済み)

> `piper_plus` の RPATH 設定 (`INSTALL_RPATH`, `BUILD_RPATH`, `MACOSX_RPATH`, `INSTALL_NAME_DIR`) は M1-4 で対応済み。本チケットでの変更は不要。

### 2.3 ONNX Runtime の install_name 修正 (macOS) --- 本チケットのスコープ

install 時に ONNX Runtime の install_name を `@rpath` ベースに修正する。これにより `piper_plus` が RPATH で ORT を解決できる。

```cmake
if(APPLE AND PIPER_PLUS_BUILD_SHARED)
  # ONNX Runtime dylib の install_name を修正するカスタムコマンド
  install(CODE "
    file(GLOB _ort_dylibs \"\${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_LIBDIR}/libonnxruntime*.dylib\")
    foreach(_dylib \${_ort_dylibs})
      get_filename_component(_name \${_dylib} NAME)
      execute_process(
        COMMAND install_name_tool -id \"@rpath/\${_name}\" \"\${_dylib}\"
      )
      message(STATUS \"Fixed install_name: \${_name}\")
    endforeach()
  ")
endif()
```

**背景:** ONNX Runtime のプリビルドバイナリは install_name が絶対パス (`/onnxruntime-osx-arm64-1.14.1/lib/libonnxruntime.1.14.1.dylib`) に設定されている。これを `@rpath/libonnxruntime.1.14.1.dylib` に変更することで、RPATH 経由の解決が可能になる。

### 2.4 既存 piper (CLI) の RPATH との共存

既存の `piper` 実行ファイル (CMakeLists.txt L145-157) の RPATH 設定は変更しない。`piper` は `@executable_path/../lib` でライブラリを検索し、`piper_plus` は `@loader_path` で検索する。両者は独立して正しく動作する。

### 2.5 build-piper.yml との整合

`build-piper.yml` (L316-343) には macOS RPATH を手動修正する `install_name_tool` コマンドが既にある。本チケットの CMake 設定が正しく機能すれば、このワークフローの手動修正は不要になる。ただし M3-5 で確認するまでは残しておく。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| CMake エンジニア | 1 | RPATH 設定修正、install_name_tool 統合 |

---

## 4. 提供範囲とテスト項目

### 4.1 ユニットテスト

| テスト | プラットフォーム | 検証方法 |
|--------|----------------|---------|
| RPATH (Linux) | Linux | `readelf -d lib/libpiper_plus.so \| grep RUNPATH` に `$ORIGIN` が含まれる |
| RPATH (macOS) | macOS | `otool -l lib/libpiper_plus.dylib \| grep -A2 LC_RPATH` に `@loader_path` が含まれる |
| install_name (macOS) | macOS | `otool -D lib/libpiper_plus.dylib` が `@rpath/libpiper_plus.1.dylib` を返す |
| ORT install_name (macOS) | macOS | `otool -D lib/libonnxruntime.1.14.1.dylib` が `@rpath/libonnxruntime.1.14.1.dylib` を返す |
| ORT リンク (macOS) | macOS | `otool -L lib/libpiper_plus.dylib` で ORT が `@rpath/...` で参照されている |

### 4.2 E2E テスト

```bash
# Linux: LD_LIBRARY_PATH なしで動作確認
cmake --install build --prefix /tmp/pp
cd /tmp
cat > test_rpath.c << 'EOF'
#include <piper_plus.h>
#include <stdio.h>
int main(void) {
    printf("%s\n", piper_plus_version());
    return 0;
}
EOF

# pkg-config でコンパイル (M3-2 依存)
PKG_CONFIG_PATH=/tmp/pp/lib/pkgconfig \
  gcc $(pkg-config --cflags --libs piper_plus) -o test_rpath test_rpath.c

# LD_LIBRARY_PATH は piper_plus の lib/ のみ指定
# ORT は RPATH ($ORIGIN) で自動解決されるべき
LD_LIBRARY_PATH=/tmp/pp/lib ./test_rpath
```

```bash
# macOS: DYLD_LIBRARY_PATH なしで動作確認
DYLD_LIBRARY_PATH= ./test_rpath  # 空にしてRPATHのみで解決
```

### 4.3 piper (CLI) の回帰テスト

```bash
# 既存の piper CLI が回帰しないことを確認
cmake --install build --prefix /tmp/pp
/tmp/pp/bin/piper --version  # 正常に動作
```

---

## 5. 懸念事項とレビュー項目

| 懸念 | 詳細 | 対策 |
|------|------|------|
| macOS コード署名 | `install_name_tool` でバイナリを変更すると署名が無効になる | CI では署名不要。配布時は `codesign --force --sign` で再署名。CMake 3.19+ の `CMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED` で制御可能 |
| ORT の install_name が変化するバージョン | ORT 1.14.1 前提の `libonnxruntime.1.14.1.dylib` | `file(GLOB)` でバージョン非依存にマッチ。将来の ORT アップデートでも動作 |
| `BUILD_WITH_INSTALL_RPATH FALSE` | ビルドツリーでのテスト時に ORT が見つからない可能性 | `BUILD_RPATH` で `${CMAKE_CURRENT_BINARY_DIR}/ort/lib` を指定。M1-4 で既に設定済み |
| `@loader_path` と `@rpath` の使い分け | macOS で混乱しやすい | `INSTALL_RPATH` に `@loader_path` を設定し、`INSTALL_NAME_DIR` を空にすることで `install_name` が `@rpath/<name>` になる。RPATH の1エントリ (`@loader_path`) が `@rpath` を解決する |

**レビュー項目:**
- [ ] macOS で `otool -L libpiper_plus.dylib` の出力に絶対パスが含まれないこと
- [ ] Linux で `ldd libpiper_plus.so` が全依存を解決できること
- [ ] 既存の `piper` CLI の RPATH が変更されていないこと
- [ ] `build-piper.yml` の手動 RPATH 修正 (L316-343) が不要になることを確認

---

## 6. 一から作り直すとしたら

1. **Phase 1 (M1-4) の時点で `@loader_path` を設定すべきだった。** 共有ライブラリの RPATH は実行ファイルとは根本的に異なるため、最初から分離して設定すべき。`@executable_path` をデフォルトにすると、後から修正する際にテスト範囲が広がる。

2. **ONNX Runtime を CMake IMPORTED ターゲットとして管理し、`install(IMPORTED_RUNTIME_ARTIFACTS onnxruntime)` を使う。** これにより RPATH と install_name の設定が CMake に統合され、プラットフォーム別の `install_name_tool` コマンドが不要になる。ただし ORT のプリビルドバイナリが IMPORTED ターゲットを提供していないため、自前で `add_library(onnxruntime SHARED IMPORTED)` を定義する必要がある。

3. **RPATH のテストを CI で自動化する仕組みを最初から用意する。** `otool -l` / `readelf -d` の出力をパースしてアサートする CMake スクリプトを、M1-4 と同時に作成しておけば、RPATH の問題を早期発見できた。

---

## 7. 後続タスクへの連絡事項

- **M3-5 (リリースワークフロー):** 本チケットの RPATH 修正が正しく機能すれば、`build-piper.yml` の手動 `install_name_tool` コマンド (L316-343) を `cmake --install` に置き換えられる。ただし、既存の `piper` CLI 配布用の RPATH 修正は残す必要がある。
- **M3-6 (使用例):** ドキュメントに「共有ライブラリと ONNX Runtime を同じディレクトリに配置すること」と明記する。`LD_LIBRARY_PATH` / `DYLD_LIBRARY_PATH` なしでの動作確認手順も記載する。
- **M4-6 (`dladdr` 辞書自動検出):** 本チケットの `@loader_path` 設定は M4-6 の辞書自動検出とは独立。M4-6 は `dladdr()` でライブラリパスを取得し、そこから辞書の相対パスを算出する。
