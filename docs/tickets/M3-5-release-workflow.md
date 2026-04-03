# M3-5: リリースワークフロー拡張

> **Phase:** 3 — 配布
> **見積り:** 大
> **依存:** M3-1, M3-4
> **ブロック:** M3-6
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m3-5-リリースワークフロー拡張)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

piper-plus の C API 共有ライブラリをリリースアセットとして 4 プラットフォームで配布する。既存のリリースワークフロー (`dev-create-release.yml` / `dev-build-all.yml` / `build-piper.yml`) を拡張し、CLI バイナリに加えて共有ライブラリの tar.gz/zip を生成する。

**配布プラットフォーム:**

| プラットフォーム | アーキテクチャ | アセット名 |
|----------------|---------------|-----------|
| Linux | x86_64 | `piper-plus-shared-linux-x64.tar.gz` |
| Linux | aarch64 | `piper-plus-shared-linux-arm64.tar.gz` |
| macOS | arm64 | `piper-plus-shared-macos-arm64.tar.gz` |
| Windows | x64 | `piper-plus-shared-windows-x64.zip` |

**ゴール:**
- `dev-create-release.yml` のワークフロー実行で、上記 4 アセットが GitHub Release にアップロードされる
- 各アセットは M3-1 の install レイアウトに従った配布パッケージを含む
- CI で install layout 検証、RPATH 検証、pkg-config テスト、CMake Config テストを実行
- 既存の CLI バイナリ配布 (`piper-linux-x64.tar.gz` 等) に影響しない

---

## 2. 実装する内容の詳細

### 2.1 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `.github/workflows/build-piper.yml` | `build-shared` input 追加、共有ライブラリビルド + install ステップ追加 |
| `.github/workflows/dev-build-all.yml` | 共有ライブラリビルドジョブ追加 |
| `.github/workflows/dev-create-release.yml` | 共有ライブラリアセットのアップロードジョブ追加 |
| `.github/workflows/cpp-tests.yml` | 共有ライブラリのビルド + テストを CI に統合 |

### 2.2 build-piper.yml の拡張

`build-piper.yml` は reusable workflow で、各プラットフォームのビルドを共通化している。共有ライブラリビルドの input を追加する。

```yaml
on:
  workflow_call:
    inputs:
      # ... 既存の inputs ...
      build-shared:
        description: 'Build shared library (libpiper_plus)'
        required: false
        type: boolean
        default: false
```

ビルドステップ (Unix) に追加:

```yaml
      - name: Build shared library (Unix)
        if: runner.os != 'Windows' && inputs.build-shared
        run: |
          mkdir -p build-shared && cd build-shared
          CMAKE_FLAGS="-DCMAKE_BUILD_TYPE=${{ inputs.build-type }}"
          CMAKE_FLAGS="$CMAKE_FLAGS -DPIPER_PLUS_BUILD_SHARED=ON"
          CMAKE_FLAGS="$CMAKE_FLAGS -DCMAKE_INSTALL_PREFIX=${{ github.workspace }}/install"

          cmake .. $CMAKE_FLAGS
          make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu)
          cmake --install .

          # Install layout 検証
          cmake -P ../cmake/verify_install_layout.cmake -- \
            ${{ github.workspace }}/install

          # RPATH 検証 (Linux)
          if [ "${{ runner.os }}" = "Linux" ]; then
            readelf -d install/lib/libpiper_plus.so | grep -q 'RUNPATH.*\$ORIGIN' \
              || (echo "RPATH check failed" && exit 1)
          fi

          # RPATH 検証 (macOS)
          if [ "${{ runner.os }}" = "macOS" ]; then
            otool -l install/lib/libpiper_plus.dylib | grep -A2 LC_RPATH \
              | grep -q '@loader_path' \
              || (echo "RPATH check failed" && exit 1)
          fi

          # pkg-config テスト
          if command -v pkg-config &>/dev/null; then
            export PKG_CONFIG_PATH="${{ github.workspace }}/install/lib/pkgconfig"
            pkg-config --modversion piper_plus
            pkg-config --cflags piper_plus
            pkg-config --libs piper_plus
          fi

          # アーカイブ作成
          cd ${{ github.workspace }}
          tar -czf piper-plus-shared-${{ runner.os }}.tar.gz -C install .
```

ビルドステップ (Windows) に追加:

```yaml
      - name: Build shared library (Windows)
        if: runner.os == 'Windows' && inputs.build-shared
        run: |
          New-Item -ItemType Directory -Force -Path build-shared
          cd build-shared

          cmake .. -G "Visual Studio 17 2022" -A x64 `
            -DCMAKE_BUILD_TYPE=${{ inputs.build-type }} `
            -DPIPER_PLUS_BUILD_SHARED=ON `
            -DCMAKE_INSTALL_PREFIX="${{ github.workspace }}/install"

          cmake --build . --config ${{ inputs.build-type }} --parallel 2
          cmake --install . --config ${{ inputs.build-type }}

          # Install layout 検証
          cmake -P ../cmake/verify_install_layout.cmake -- `
            "${{ github.workspace }}/install"

          # アーカイブ作成
          cd ${{ github.workspace }}
          Compress-Archive -Path install/* `
            -DestinationPath piper-plus-shared-${{ runner.os }}.zip
```

アーティファクトのアップロード:

```yaml
      - name: Upload shared library artifact
        if: inputs.build-shared
        uses: actions/upload-artifact@v7
        with:
          name: ${{ steps.set-artifact-name.outputs.name }}-shared
          path: |
            piper-plus-shared-${{ runner.os }}.tar.gz
            piper-plus-shared-${{ runner.os }}.zip
          retention-days: 1
```

### 2.3 dev-build-all.yml の拡張

既存の CLI ビルドジョブに加えて、共有ライブラリビルドジョブを追加する。

```yaml
  # 既存: build_linux_x64, build_macos_arm64, build_windows_x64, ...

  # 追加: 共有ライブラリビルド
  build_shared_linux_x64:
    name: Build Shared Library Linux x86_64
    uses: ./.github/workflows/build-piper.yml
    with:
      os: ubuntu-22.04
      build-type: Release
      build-shared: true
      artifact-name: piper-plus-shared-linux-x64
      cache-key-prefix: piper-shared-linux-x64

  build_shared_macos_arm64:
    name: Build Shared Library macOS ARM64
    uses: ./.github/workflows/build-piper.yml
    with:
      os: macos-14
      build-type: Release
      build-shared: true
      artifact-name: piper-plus-shared-macos-arm64
      cache-key-prefix: piper-shared-macos-arm64

  build_shared_windows_x64:
    name: Build Shared Library Windows x64
    uses: ./.github/workflows/build-piper.yml
    with:
      os: windows-2022
      build-type: Release
      build-shared: true
      artifact-name: piper-plus-shared-windows-x64
      cache-key-prefix: piper-shared-windows-x64
```

Linux aarch64 は既存の Docker ベースビルド (`build_linux_arm64`) を拡張:

```yaml
  build_shared_linux_arm64:
    name: Build Shared Library Linux ARM64
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v6
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v4
        with:
          platforms: arm64
      - name: Build shared library in Docker
        run: |
          docker run --rm \
            --platform linux/arm64 \
            -v "$(pwd)":/workspace \
            -w /workspace \
            debian:bookworm \
            bash -c "
              apt-get update && apt-get install -y build-essential cmake wget pkg-config
              # ... (ORT ダウンロード、ビルド、install、検証)
              mkdir -p build-shared && cd build-shared
              cmake .. -DCMAKE_BUILD_TYPE=Release \
                -DPIPER_PLUS_BUILD_SHARED=ON \
                -DCMAKE_INSTALL_PREFIX=/workspace/install
              make -j\$(nproc)
              cmake --install .
              cd /workspace
              tar -czf piper-plus-shared-linux-arm64.tar.gz -C install .
            "
      - uses: actions/upload-artifact@v7
        with:
          name: piper-plus-shared-linux-arm64
          path: piper-plus-shared-linux-arm64.tar.gz
```

### 2.4 dev-create-release.yml の拡張

共有ライブラリアセットのリリースアップロードジョブを追加:

```yaml
  upload_shared_libs:
    name: Upload Shared Libraries
    needs: [create_release, build_all]
    if: needs.build_all.result == 'success'
    runs-on: ubuntu-22.04
    strategy:
      matrix:
        include:
          - artifact: piper-plus-shared-linux-x64
            asset_name: piper-plus-shared-linux-x64.tar.gz
          - artifact: piper-plus-shared-macos-arm64
            asset_name: piper-plus-shared-macos-arm64.tar.gz
          - artifact: piper-plus-shared-windows-x64
            asset_name: piper-plus-shared-windows-x64.zip
          - artifact: piper-plus-shared-linux-arm64
            asset_name: piper-plus-shared-linux-arm64.tar.gz
    steps:
      - uses: actions/checkout@v6
      - uses: actions/download-artifact@v8
        with:
          name: ${{ matrix.artifact }}
          path: dist/
      - name: Upload Release Asset
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh release upload "${{ needs.create_release.outputs.tag_name }}" \
            "dist/${{ matrix.asset_name }}" \
            --clobber
```

### 2.5 cpp-tests.yml の拡張

PR 時の CI テストに共有ライブラリビルドを追加:

```yaml
  test-cpp:
    # ... 既存の matrix ...
    steps:
      # ... 既存のステップ ...

      - name: Build and test shared library
        run: |
          mkdir -p build-shared && cd build-shared
          cmake .. \
            -DCMAKE_BUILD_TYPE=${{ matrix.build-type }} \
            -DPIPER_PLUS_BUILD_SHARED=ON \
            -DBUILD_TESTS=ON \
            -DCMAKE_INSTALL_PREFIX=${{ github.workspace }}/install
          cmake --build . --config ${{ matrix.build-type }} \
            -j$(nproc 2>/dev/null || sysctl -n hw.ncpu)

          # C API テスト実行
          ctest --output-on-failure --verbose --timeout 60

          # Install + layout 検証
          cmake --install . --config ${{ matrix.build-type }}
          cmake -P ../cmake/verify_install_layout.cmake -- \
            ${{ github.workspace }}/install

          # シンボル可視性検証
          if [ "${{ runner.os }}" = "Linux" ]; then
            EXPORTS=$(nm -D ${{ github.workspace }}/install/lib/libpiper_plus.so \
              | grep ' T ' | grep -v 'piper_plus_' | wc -l)
            if [ "$EXPORTS" -gt 0 ]; then
              echo "Unexpected exported symbols found"
              nm -D ${{ github.workspace }}/install/lib/libpiper_plus.so \
                | grep ' T ' | grep -v 'piper_plus_'
              exit 1
            fi
          elif [ "${{ runner.os }}" = "macOS" ]; then
            EXPORTS=$(nm -gU ${{ github.workspace }}/install/lib/libpiper_plus.dylib \
              | grep -v '_piper_plus_' | grep ' T ' | wc -l)
            if [ "$EXPORTS" -gt 0 ]; then
              echo "Unexpected exported symbols found"
              exit 1
            fi
          fi
```

### 2.6 paths トリガーの更新

`cpp-tests.yml` の paths トリガーに C API 関連ファイルを追加:

```yaml
on:
  pull_request:
    branches: [ dev ]
    paths:
      - 'src/cpp/**'
      - 'CMakeLists.txt'
      - 'cmake/**'                        # 追加
      - 'src/cpp/piper_plus.h'            # 追加 (明示)
      - 'src/cpp/piper_plus_c_api.cpp'    # 追加 (明示)
      - '.github/workflows/cpp-tests.yml'
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| CI エンジニア | 1 | ワークフロー YAML の作成・修正 |
| QA | 1 | 4 プラットフォームでのワークフロー実行確認 |

---

## 4. 提供範囲とテスト項目

### 4.1 ビルドテスト (自動)

| テスト | プラットフォーム | 検証内容 |
|--------|----------------|---------|
| 共有ライブラリビルド | Linux x64, macOS ARM64, Windows x64, Linux ARM64 | `libpiper_plus.so` / `.dylib` / `.dll` が生成される |
| Install layout | 全プラットフォーム | `verify_install_layout.cmake` が PASS |
| RPATH | Linux, macOS | `readelf -d` / `otool -l` で正しい RPATH を確認 |
| シンボル可視性 | Linux, macOS | `piper_plus_` プレフィックス以外のシンボルが非公開 |
| pkg-config | Linux, macOS | `pkg-config --modversion` が `VERSION` ファイルと一致 |

### 4.2 E2E テスト (CI 内)

| テスト | 内容 |
|--------|------|
| CMake Config | `find_package(PiperPlus)` + ビルド + 実行 |
| pkg-config | `gcc $(pkg-config --cflags --libs piper_plus) -o test test.c` |
| C API テスト | `test_c_api` + `test_c_api_integration` (モデル依存はSKIP) |

### 4.3 リリースアセット検証

| テスト | 内容 |
|--------|------|
| アセット名 | `piper-plus-shared-{platform}.{tar.gz|zip}` の命名規則 |
| アセットサイズ | 各プラットフォームで概ね期待通り (Linux ~80MB, macOS ~70MB, Windows ~60MB -- ORT 込み) |
| アセット内容 | tar.gz/zip を展開して `verify_install_layout.cmake` で検証 |

---

## 5. 懸念事項とレビュー項目

| 懸念 | 詳細 | 対策 |
|------|------|------|
| CI 実行時間の増加 | 共有ライブラリビルドが追加で ~10-15分/プラットフォーム | `build-piper.yml` は既にキャッシュ機構あり。共有ライブラリ専用のキャッシュキーで分離 |
| Linux ARM64 の QEMU ビルド | ARM64 ビルドは QEMU エミュレーションで遅い (~30-60分) | `timeout-minutes: 90` を設定。ARM64 は release 時のみビルド |
| アーティファクトサイズ | ORT 込みで ~60-80MB/プラットフォーム | GitHub Actions のアーティファクト容量に収まる (リテンション 1 日) |
| 既存ワークフローへの回帰 | `build-piper.yml` の変更が CLI ビルドに影響する可能性 | `build-shared: false` がデフォルト。既存の呼び出し元は影響なし |
| Windows CI で `dumpbin` | シンボル可視性検証に `dumpbin /EXPORTS` が必要 | MSVC Developer Command Prompt (`ilammy/msvc-dev-cmd`) で `dumpbin` が利用可能。CI で既に設定済み |

**レビュー項目:**
- [ ] 既存の CLI バイナリ配布 (`piper-linux-x64.tar.gz` 等) が変更されていないこと
- [ ] 共有ライブラリアセットが 4 プラットフォーム全てで GitHub Release にアップロードされること
- [ ] CI 実行時間が許容範囲内 (全体 +30分以内)
- [ ] `build-piper.yml` の `build-shared: false` (デフォルト) で既存動作が変わらないこと

---

## 6. 一から作り直すとしたら

1. **共有ライブラリ専用の reusable workflow を分離する。** `build-piper.yml` に `build-shared` フラグを追加する方式は条件分岐が増えて可読性が下がる。`build-piper-shared.yml` を別ワークフローとして定義し、CLI ビルドと完全に分離する方が保守しやすい。ただし、依存ライブラリのセットアップ (ORT ダウンロード、OpenJTalk ビルド等) が重複するトレードオフがある。

2. **`cmake --install` ベースのパッケージングを CLI ビルドにも適用する。** 現在の `build-piper.yml` (L262-392) は手動でファイルをコピーして tar.gz を作成している。`cmake --install --prefix dist/piper` に統一すれば、共有ライブラリと CLI の両方を同じ install ロジックでパッケージングできる。本チケットでは共有ライブラリのみ `cmake --install` を使い、CLI 側は既存のまま残す。

3. **リリースアセットの naming convention を最初から統一する。** 現在のリリースでは CLI が `piper-linux-x64.tar.gz`、C# CLI が `piper-plus-cli-linux-x64.tar.gz`、Rust CLI が `piper-plus-rs-cli-linux-x64.tar.gz` と命名がばらばら。共有ライブラリは `piper-plus-shared-linux-x64.tar.gz` とするが、将来的には `piper-plus-{component}-{platform}-{arch}.{ext}` の統一規則が望ましい。

4. **matrix strategy で全プラットフォームを統一する。** 現在は Linux ARM64 / ARMv7 のみ Docker ベースで、他は直接ビルド。GitHub Actions の ARM64 ランナーが一般提供されれば、全プラットフォームを同じ `runs-on` matrix で処理できる。

---

## 7. 後続タスクへの連絡事項

- **M3-6 (使用例):** リリースアセットのダウンロード先 URL 形式は `https://github.com/ayutaz/piper-plus/releases/download/v{version}/piper-plus-shared-{platform}.tar.gz`。使用例ドキュメントにこの URL パターンを記載する。
- **dev-create-release.yml のリリースノート:** `release_summary` ジョブに共有ライブラリのアセット情報を追加する。
- **既存ワークフローの互換性:** `build-all-platforms.yml` (PR 時の全プラットフォームビルド) にも共有ライブラリビルドを追加する検討。ただし PR 時は CI 時間を抑えるため、`cpp-tests.yml` での検証で十分かもしれない。
