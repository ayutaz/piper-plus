# M3-5: リリースワークフロー拡張

> **Phase:** 3 — 配布
> **見積り:** 大
> **依存:** M3-1, M3-4
> **ブロック:** M3-6
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m3-5-リリースワークフロー拡張)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

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

## 7. CLI パッケージングの cmake --install 移行計画

> **背景 (Phase 3 振り返り反映):** 現在の `build-piper.yml` (L262-489) は 200+ 行の手動ファイルコピーロジックを含んでいる。共有ライブラリでは `cmake --install` を採用するが、CLI (`piper`) 側は既存の手動コピーのまま残す保守的な選択をした。

**現状:**

| 配布物 | パッケージング方式 | ファイル |
|--------|-----------------|---------|
| CLI (`piper`) | 手動ファイルコピー (200+ 行) | `build-piper.yml` L262-489 |
| 共有ライブラリ (`libpiper_plus`) | `cmake --install` | 本チケットで導入 |

**ロードマップ (Phase 3 スコープ外):**

1. **CLI の `cmake --install` 移行:** `piper` 実行ファイル + 辞書 + ORT を `cmake --install --prefix dist/piper` で配布パッケージに含める。`install(TARGETS piper ...)` + `install(FILES ...)` で手動コピーを置換。
2. **共有ライブラリとの install ルール共有:** ORT 同梱 (`install(FILES libonnxruntime...)`) と辞書 install (`install(DIRECTORY share/open_jtalk/...)`) は CLI と共有ライブラリで共通化できる。CMake の `install(TARGETS ...)` を条件分岐ではなくコンポーネント (`COMPONENT cli` / `COMPONENT shared`) で管理。
3. **`build-piper.yml` の簡素化:** 手動コピーロジックを `cmake --install --component cli --prefix dist/piper` に置換し、ワークフロー YAML を ~50 行に削減。

**Phase 3 での判断:** 共有ライブラリのみ `cmake --install` を使用。CLI の移行は後続タスクとして Issue 化を推奨。既存の CLI 配布に影響を与えないことを最優先とする。

---

## 8. ワークフロー設計の判断

> **背景 (Phase 3 振り返り反映):** `build-piper.yml` に `build-shared` フラグを追加する方式と、`build-piper-shared.yml` として分離する方式のトレードオフ。

**選択肢の比較:**

| 観点 | 選択肢 1: build-piper.yml に統合 | 選択肢 2: build-piper-shared.yml 分離 |
|------|-------------------------------|-------------------------------------|
| 保守コスト | 1 ファイルで完結 | 2 ファイルの同期が必要 |
| 可読性 | `if: inputs.build-shared` の条件分岐が増加 | 各ファイルが単一責任で明快 |
| セットアップ重複 | なし | ORT ダウンロード・OpenJTalk ビルド等が重複 |
| 回帰リスク | 共有ライブラリの変更が CLI ビルドに影響し得る | 完全分離で相互影響なし |
| テスト容易性 | 単一 workflow のテストが複雑化 | 独立テスト可能 |

**推奨:** composite action でセットアップを共有し、ワークフローは分離する。

```
.github/
├── actions/
│   └── setup-piper-build/    # composite action (ORT DL, OpenJTalk, deps)
│       └── action.yml
├── workflows/
│   ├── build-piper.yml       # CLI ビルド (既存)
│   └── build-piper-shared.yml  # 共有ライブラリビルド (新規)
```

**本チケットでの選択:** 本チケットでは選択肢 1 (build-piper.yml に統合) を採用する。理由:
- 初期実装コストが最も低い
- `build-shared: false` のデフォルトで既存動作に影響しない
- composite action への分離は後続リファクタリングとして実施可能

**後続リファクタリング:** CI の条件分岐が複雑化した場合、composite action + ワークフロー分離に移行する。この判断基準は `build-piper.yml` の条件分岐が 5 箇所を超えた時点。

---

## 9. リリースアセット検証ステップ

> **背景 (Phase 3 振り返り反映):** 現在の CI はビルド検証のみで、リリースアセットの tar.gz/zip を展開して動作確認するステップがない。

**検証パイプライン:**

```
ダウンロード → 展開 → verify_install_layout.cmake → サンプルビルド → モデル不要テスト
```

**`dev-create-release.yml` に追加する検証ジョブ:**

```yaml
  verify_shared_assets:
    name: Verify Shared Library Assets
    needs: [upload_shared_libs]
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        include:
          - os: ubuntu-22.04
            asset: piper-plus-shared-linux-x64.tar.gz
            extract: tar -xzf
          - os: macos-14
            asset: piper-plus-shared-macos-arm64.tar.gz
            extract: tar -xzf
          - os: windows-2022
            asset: piper-plus-shared-windows-x64.zip
            extract: Expand-Archive -Path
    steps:
      - uses: actions/checkout@v6

      # 1. リリースアセットをダウンロード
      - name: Download release asset
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh release download "${{ needs.create_release.outputs.tag_name }}" \
            --pattern "${{ matrix.asset }}" --dir dist/

      # 2. 展開
      - name: Extract asset (Unix)
        if: runner.os != 'Windows'
        run: |
          mkdir -p /tmp/piper-plus-install
          ${{ matrix.extract }} dist/${{ matrix.asset }} -C /tmp/piper-plus-install

      - name: Extract asset (Windows)
        if: runner.os == 'Windows'
        run: |
          New-Item -ItemType Directory -Force -Path $env:TEMP/piper-plus-install
          Expand-Archive -Path dist/${{ matrix.asset }} `
            -DestinationPath $env:TEMP/piper-plus-install

      # 3. Install layout 検証
      - name: Verify install layout
        run: |
          cmake -P cmake/verify_install_layout.cmake -- \
            /tmp/piper-plus-install

      # 4. サンプルビルド (CMake find_package)
      - name: Build examples
        run: |
          cmake -B /tmp/ex-build \
            -S examples/c-api \
            -DCMAKE_PREFIX_PATH=/tmp/piper-plus-install
          cmake --build /tmp/ex-build

      # 5. モデル不要テスト (エラーハンドリング確認)
      - name: Smoke test (no model required)
        if: runner.os != 'Windows'
        run: |
          LD_LIBRARY_PATH=/tmp/piper-plus-install/lib \
            /tmp/ex-build/basic nonexistent.onnx /tmp/dict "test" /dev/null \
            2>&1 | grep -q "Error:" && echo "Error handling OK"
```

**検証項目:**

| ステップ | 検証内容 | 失敗時のアクション |
|---------|---------|----------------|
| ダウンロード | アセットが GitHub Release に存在する | ジョブ失敗 → リリースをドラフトに戻す |
| 展開 | tar.gz/zip が破損なく展開できる | ジョブ失敗 |
| Layout 検証 | `verify_install_layout.cmake` が全必須ファイルを確認 | ジョブ失敗 |
| サンプルビルド | `find_package(PiperPlus)` + ビルド成功 | ジョブ失敗 |
| Smoke テスト | エラーメッセージが正しく出力される | ジョブ失敗 |

**M3-6 (使用例) との連携:** サンプルビルドのステップは M3-6 で作成する `examples/c-api/CMakeLists.txt` を使用する。M3-6 が先に完了している必要がある。

---

## 10. 将来拡張: Android ビルド (M4-4 参照)

> **Phase 4 振り返りで追加 (2026-04-03)**

Flutter 最大ターゲットが Android であるため、本ワークフローに Android ビルドをオプショナルステップとして追加することを推奨。M4-4 ([M4-4-android-ndk.md](M4-4-android-ndk.md)) の実装完了時に以下の拡張を行う:

- `build-piper.yml` に `build-android` input (デフォルト `false`) を予約
- M4-4 完了時にフラグを有効化し、`piper-plus-shared-android-arm64.tar.gz` をリリースアセットに追加
- 対象 ABI: `arm64-v8a` のみ (最小スコープ)

詳細は M4-4 のセクション 7「Phase 3 M3-5 への統合オプション」を参照。

---

## 11. 後続タスクへの連絡事項

- **M3-6 (使用例):** リリースアセットのダウンロード先 URL 形式は `https://github.com/ayutaz/piper-plus/releases/download/v{version}/piper-plus-shared-{platform}.tar.gz`。使用例ドキュメントにこの URL パターンを記載する。
- **dev-create-release.yml のリリースノート:** `release_summary` ジョブに共有ライブラリのアセット情報を追加する。
- **既存ワークフローの互換性:** `build-all-platforms.yml` (PR 時の全プラットフォームビルド) にも共有ライブラリビルドを追加する検討。ただし PR 時は CI 時間を抑えるため、`cpp-tests.yml` での検証で十分かもしれない。
