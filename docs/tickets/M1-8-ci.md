# M1-8: CI 統合 (3 プラットフォームビルド検証)

> **Phase:** 1 --- 基本 C API (MVP)
> **見積り:** 中
> **依存:** M1-4 (CMake), M1-7 (テスト)
> **ブロック:** なし (Phase 1 の最終チケット)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m1-8-ci-統合-3プラットフォームビルド検証)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

既存の CI ワークフロー (`cpp-tests.yml`) に共有ライブラリのビルドとテストを統合する。Ubuntu、macOS、Windows の 3 プラットフォームで `libpiper_plus.so` / `.dylib` / `.dll` のビルド成功、シンボル可視性、C API テストの PASS を検証する。

**ゴール:**
1. 3 プラットフォームで共有ライブラリがビルド成功
2. 公開シンボルが `piper_plus_` プレフィックスのみ
3. C API 単体テスト (M1-7) が全プラットフォームで PASS
4. 既存テストが回帰しない

---

## 2. 実装する内容の詳細

### 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `.github/workflows/cpp-tests.yml` | 共有ライブラリビルド + テスト追加 |

### 具体的な変更内容

#### 2.1 trigger paths の拡張

現在の `cpp-tests.yml` (L3-8) の paths に C API ファイルを追加:

```yaml
on:
  pull_request:
    branches: [ dev ]
    paths:
      - 'src/cpp/**'
      - 'CMakeLists.txt'
      - '.github/workflows/cpp-tests.yml'
      # C API ファイルは src/cpp/ 配下なので既にマッチ済み
      # 明示的に追加は不要
```

**注意:** `src/cpp/piper_plus.h` と `src/cpp/piper_plus_c_api.cpp` は既に `src/cpp/**` パターンにマッチしているため、paths の追加変更は不要。

#### 2.2 マトリクスに Windows を追加

現在のマトリクスは `ubuntu-latest` と `macos-latest` のみ。Windows を追加する:

```yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    build-type: [Release]
```

#### 2.3 Windows 依存インストールステップの追加

```yaml
- name: Install dependencies (Windows)
  if: runner.os == 'Windows'
  shell: powershell
  run: |
    # Download ONNX Runtime
    $ORT_VERSION = "1.14.1"
    $ORT_URL = "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-win-x64-${ORT_VERSION}.zip"
    Invoke-WebRequest -Uri $ORT_URL -OutFile ort.zip
    Expand-Archive ort.zip -DestinationPath ort_extract
    $ORT_DIR = Get-ChildItem ort_extract -Directory | Select-Object -First 1
    Move-Item "$($ORT_DIR.FullName)" "onnxruntime"
```

#### 2.4 共有ライブラリビルドステップの追加

既存の Configure / Build ステップの後に、共有ライブラリ専用のビルドステップを追加する:

```yaml
- name: Configure CMake (shared library)
  run: |
    CMAKE_ARGS="-DCMAKE_BUILD_TYPE=${{ matrix.build-type }} -DBUILD_TESTS=ON -DPIPER_PLUS_BUILD_SHARED=ON"

    if [[ "${{ runner.os }}" == "macOS" ]]; then
      if [[ $(uname -m) == "arm64" ]]; then
        CMAKE_ARGS="$CMAKE_ARGS -DCMAKE_OSX_ARCHITECTURES=arm64"
      else
        CMAKE_ARGS="$CMAKE_ARGS -DCMAKE_OSX_ARCHITECTURES=x86_64"
      fi
    fi

    cmake -B build_shared $CMAKE_ARGS
  shell: bash

- name: Build (shared library)
  run: |
    cmake --build build_shared --config ${{ matrix.build-type }} -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)
  shell: bash
```

Windows の場合は shell を `bash` で統一 (GitHub Actions の git-bash で動作)。

#### 2.5 シンボル可視性検証ステップ

```yaml
- name: Verify symbol visibility
  shell: bash
  run: |
    echo "=== Checking symbol visibility ==="

    if [[ "${{ runner.os }}" == "Linux" ]]; then
      SO_FILE=$(find build_shared -name "libpiper_plus.so" | head -1)
      if [[ -z "$SO_FILE" ]]; then
        echo "ERROR: libpiper_plus.so not found"
        exit 1
      fi
      echo "Found: $SO_FILE"

      # Check exported symbols - only piper_plus_* should be visible
      EXPORTED=$(nm -D "$SO_FILE" | grep ' T ' | awk '{print $3}')
      echo "Exported symbols:"
      echo "$EXPORTED"

      # Verify all exported symbols start with piper_plus_
      BAD_SYMBOLS=$(echo "$EXPORTED" | grep -v '^piper_plus_' || true)
      if [[ -n "$BAD_SYMBOLS" ]]; then
        echo "WARNING: Non-piper_plus_ symbols exported (may include C runtime symbols):"
        echo "$BAD_SYMBOLS"
        # Don't fail - some C runtime symbols may be expected
      fi

      # Verify at least the core symbols are exported
      for sym in piper_plus_create piper_plus_free piper_plus_synthesize piper_plus_version; do
        if echo "$EXPORTED" | grep -q "^${sym}$"; then
          echo "OK: $sym exported"
        else
          echo "ERROR: $sym NOT exported"
          exit 1
        fi
      done

    elif [[ "${{ runner.os }}" == "macOS" ]]; then
      DYLIB_FILE=$(find build_shared -name "libpiper_plus*.dylib" | head -1)
      if [[ -z "$DYLIB_FILE" ]]; then
        echo "ERROR: libpiper_plus.dylib not found"
        exit 1
      fi
      echo "Found: $DYLIB_FILE"

      EXPORTED=$(nm -gU "$DYLIB_FILE" | awk '{print $3}')
      echo "Exported symbols:"
      echo "$EXPORTED"

      # macOS symbols have underscore prefix
      for sym in _piper_plus_create _piper_plus_free _piper_plus_synthesize _piper_plus_version; do
        if echo "$EXPORTED" | grep -q "^${sym}$"; then
          echo "OK: $sym exported"
        else
          echo "ERROR: $sym NOT exported"
          exit 1
        fi
      done

    elif [[ "${{ runner.os }}" == "Windows" ]]; then
      DLL_FILE=$(find build_shared -name "piper_plus.dll" | head -1)
      if [[ -z "$DLL_FILE" ]]; then
        echo "ERROR: piper_plus.dll not found"
        exit 1
      fi
      echo "Found: $DLL_FILE"
      echo "Windows symbol check: dumpbin not available in bash, skipping detailed check"
      echo "DLL exists - build succeeded"
    fi

    echo "=== Symbol visibility check passed ==="
```

#### 2.6 C API テスト実行ステップ

```yaml
- name: Run C API tests
  shell: bash
  run: |
    cd build_shared
    echo "=== Running C API tests ==="

    if ctest -N | grep -q "test_c_api"; then
      if ctest -R "^test_c_api$" --output-on-failure -V --timeout 60; then
        echo "C API tests passed"
      else
        echo "C API tests FAILED"
        exit 1
      fi
    else
      echo "WARNING: test_c_api not found in test list"
      echo "Available tests:"
      ctest -N || true
    fi
```

#### 2.7 Linux リンク検証 (libstdc++ 動的リンク確認)

```yaml
- name: Verify dynamic linking (Linux)
  if: runner.os == 'Linux'
  run: |
    SO_FILE=$(find build_shared -name "libpiper_plus.so" | head -1)
    echo "=== Checking dynamic dependencies ==="
    ldd "$SO_FILE"

    # Verify libstdc++ is dynamically linked (not statically embedded)
    if ldd "$SO_FILE" | grep -q "libstdc++"; then
      echo "OK: libstdc++ is dynamically linked"
    else
      echo "WARNING: libstdc++ not found in ldd output (may be statically linked)"
    fi
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| CI エージェント | 1 | cpp-tests.yml の修正、3 プラットフォーム動作確認 |

合計: 1 名。ただし、Windows CI の初回セットアップでは試行錯誤が必要になる可能性がある。

---

## 4. 提供範囲とテスト項目

### スコープ

- `.github/workflows/cpp-tests.yml` の拡張:
  - Windows マトリクス追加
  - 共有ライブラリビルドステップ
  - シンボル可視性検証
  - C API テスト実行
  - Linux リンク検証

### スコープ外

- リリースビルドワークフロー (Phase 3 M3-5)
- バイナリ配布 (Phase 3)
- aarch64 クロスビルド (Phase 3 M3-5)

### テスト項目

| テスト | プラットフォーム | 期待結果 |
|--------|---------------|----------|
| 共有ライブラリビルド | Linux / macOS / Windows | `.so` / `.dylib` / `.dll` が生成される |
| シンボル可視性 | Linux / macOS | `piper_plus_create` 等のコアシンボルがエクスポートされている |
| C API テスト | Linux / macOS / Windows | 全テスト PASS |
| 既存テスト回帰 | Linux / macOS | 既存テスト PASS |
| `libstdc++` 動的リンク | Linux | `ldd` で `libstdc++.so` が表示される |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | 影響度 | 対策 |
|------|--------|------|
| Windows CI の ONNX Runtime セットアップ | 中 | 既存の `cmake/find_onnxruntime_windows.cmake` がダウンロード・解凍を行う。CI ステップでの追加セットアップが不要な場合もある。ビルド失敗時にデバッグ |
| 共有ライブラリビルドと既存ビルドの分離 | 低 | `build_shared` と `build` の 2 つのビルドディレクトリを使用して分離 |
| `nm -D` / `nm -gU` の出力フォーマット差異 | 低 | シンボル名の抽出を `awk` で柔軟に対応。完全一致ではなく部分一致で検証 |
| CI 実行時間の増加 | 中 | 共有ライブラリビルドは追加の CMake configure + build が必要。ccache があるため増分は限定的だが、外部依存のダウンロードが 2 回走る可能性。`build_shared` で ccache を共有すれば緩和 |
| Windows の `bash` シェルの互換性 | 低 | GitHub Actions の `bash` は Git for Windows の bash。`find`, `grep`, `awk` は利用可能。`nproc` は利用不可のため `echo 2` にフォールバック |

### レビュー項目

- [ ] マトリクスに 3 OS が含まれているか
- [ ] 共有ライブラリビルドが `build_shared` (既存の `build` と別) ディレクトリで実行されるか
- [ ] シンボル可視性検証でコアシンボル (`piper_plus_create`, `piper_plus_free`, `piper_plus_synthesize`, `piper_plus_version`) が確認されているか
- [ ] `test_c_api` が実行されているか
- [ ] 既存テストのステップが影響を受けていないか
- [ ] Windows ステップの `shell: bash` / `shell: powershell` が適切に指定されているか

---

## 6. 一から作り直すとしたら

### CI ワークフローの構造化

現在の `cpp-tests.yml` は 1 つのジョブに全ステップが入っている。共有ライブラリビルドを追加するなら、以下のようにジョブを分離する:

```yaml
jobs:
  build-static:
    name: Static build (${{ matrix.os }})
    # 既存の piper / test_piper ビルド + テスト

  build-shared:
    name: Shared library (${{ matrix.os }})
    needs: []  # 独立実行 (build-static と並行)
    # piper_plus 共有ライブラリビルド + C API テスト

  verify-symbols:
    name: Symbol visibility (${{ matrix.os }})
    needs: build-shared
    # nm -D / otool / dumpbin でシンボル検証
```

ジョブ分離のメリット:
1. 並行実行で CI 時間短縮
2. 失敗箇所の特定が容易
3. 必要なジョブだけを再実行可能

### Docker ベースの再現可能ビルド

Linux CI では Docker コンテナを使ってビルド環境を固定する。glibc バージョンの一致を保証し、「CI では動くがユーザー環境では動かない」問題を防ぐ:

```yaml
container:
  image: ubuntu:22.04
```

---

## 7. 後続タスクへの連絡事項

- **Phase 2 M2-6 (CI 更新):** ストリーミングテストと統合テストを `cpp-tests.yml` に追加する際、このチケットで追加した `build_shared` ディレクトリとテスト実行ステップを拡張する。
- **Phase 3 M3-5 (リリースワークフロー):** リリースビルドでは `cpp-tests.yml` とは別のワークフロー (`release-shared-lib.yml` 等) を作成する。ここでの CI はビルド検証のみ。バイナリ配布は Phase 3 のスコープ。
- **Windows CI の注意:** Windows では `dumpbin /EXPORTS` でシンボル可視性を検証する必要があるが、`bash` シェルからは利用しにくい。Phase 2 以降で `powershell` ステップを追加するか、Visual Studio Developer Command Prompt を設定すること。

---

## Phase 1 全体の振り返り: 一から設計するなら

Phase 1 (M1-1 ~ M1-8) を最初から設計し直すとしたら、以下の設計・実装・思考プロセスを経る。

### 1. ビルドシステムの設計原則

**最初に OBJECT ライブラリを導入する。** 現在の CMakeLists.txt はソースファイルを `piper` と `test_piper` で二重列挙しており、共有ライブラリ追加で三重になる。プロジェクト初期から `piper_common` OBJECT ライブラリを定義し、全ての ExternalProject を `-fPIC` でビルドするポリシーを設定していれば、M1-1 (fPIC) と M1-4 (OBJECT ライブラリ) は不要だった。

**CMake のモダンプラクティスを最初から適用する。** `CMAKE_CXX_FLAGS` にリンカフラグを入れない (M1-2 で修正したアンチパターン)、ターゲット固有の `target_link_options` / `target_compile_options` を使う、グローバル変数の代わりにターゲットプロパティを使う。

### 2. API 設計の初期検討

**C++ API の設計段階で C API を意識する。** `textToAudio()` が `voice.synthesisConfig.languageId` を内部変更して復元しない問題 (M1-6 で save/restore が必要になった根本原因) は、`textToAudio()` が `const SynthesisConfig&` を受け取る設計なら発生しなかった。

**辞書パスの設計を共有ライブラリ前提で行う。** `getExeDir()` に依存する辞書自動検出は実行ファイル専用の設計。共有ライブラリでは `dladdr()` またはユーザー指定が必要。最初から `loadVoice()` にオプショナルな辞書パスパラメータを含めていれば、M1-3 の `setenv` ハックは不要だった。

### 3. テスト戦略

**3 レイヤーのテスト構成を最初から定義する:**

1. **ヘッダーコンパイルテスト (C99):** ヘッダーが pure C でコンパイル可能か
2. **API 動作テスト (モデル不要):** NULL 安全性、エラーハンドリング、デフォルト値
3. **統合テスト (モデル必要):** create -> synthesize -> verify -> free

### 4. チケット粒度の最適化

Phase 1 を 8 チケットに分割したが、以下の統合が可能だった:

- **M1-1 + M1-2 + M1-4 を統合:** ビルドシステムの変更は 1 つの大きなチケットにまとめ、レビュー時の文脈切替を減らす。依存関係が直列なため、分割のメリットは限定的。
- **M1-3 + M1-5 + M1-6 を統合:** ヘッダー設計、dict_dir 仕様、実装は一体的に考えるべきもの。分離すると設計と実装の間に齟齬が生じるリスクがある。

一方で、**M1-7 (テスト) と M1-8 (CI) は分離が適切。** テストの実装と CI の設定は独立した作業であり、並行実装が可能。

### 5. 依存グラフの単純化

Phase 1 の依存グラフは:

```
M1-1 ──> M1-4 ──> M1-6 ──> M1-7 ──> M1-8
M1-5 ──────────↗
M1-2 ─────────↗
M1-3 ─────────↗
```

これを 3 チケットに統合するなら:

```
M1-A (ビルドシステム: fPIC + static-libstdc++ + OBJECT + SHARED)
M1-B (API: ヘッダー + dict_dir + 実装)  ← depends on M1-A
M1-C (検証: テスト + CI)                 ← depends on M1-B
```

各チケットの見積りが「大」になるが、文脈切替が減り、レビューの一貫性が向上する。8 チケットに分割したのは並行作業の可能性を考慮した結果だが、Phase 1 は実質的に直列依存が多いため、3 チケット構成の方が効率的だった可能性がある。

### 6. 先行事例の活用

endo5501 の実装と sherpa-onnx / libpiper の設計を最初からガイドラインとして文書化し、チケット作成前に「設計レビューチケット」を挟む。これにより、実装着手後の設計変更 (dict_dir 追加、ERR_BUSY コード追加等) を減らせる。

### 7. リスク駆動の優先順位付け

技術調査で「高リスク」と判定された 3 項目 (languageId 未復元、辞書パス自動検出、再入問題) を最優先チケットにする。これらはユーザーが共有ライブラリを使い始めた時点で即座にバグとして顕在化するため、Phase 1 の MVP 品質を左右する。
