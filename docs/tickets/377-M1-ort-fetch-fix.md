# [M1] ORT 取得経路の修復 (release ジョブの解凍)

> **iOS Shared Library Distribution 仕様 ([#377](https://github.com/ayutaz/piper-plus/issues/377)) のマイルストーン M1 実装チケット**
> 関連仕様: [`docs/spec/ios-shared-lib.md §8 M1`](../spec/ios-shared-lib.md#m1-取得経路の修復-release-ジョブの解凍)

---

## 1. メタ情報

| 項目 | 値 |
|------|-----|
| マイルストーン | **M1** ([取得経路の修復 / release ジョブの解凍](../spec/ios-shared-lib.md#m1-取得経路の修復-release-ジョブの解凍)) |
| 親 Issue | [#377](https://github.com/ayutaz/piper-plus/issues/377) |
| ブランチ | `fix/ios-shared-lib-build-377` |
| 状態 | [README 表 を SoT として参照](README.md) |
| 想定 PR | 1 PR (中、~60-80 行 diff) |
| 想定所要 (Claude Code 実行ベース) | 実装 1-2 時間 + `workflow_dispatch` CI ~20 分 (1 サイクル) + 仮想 tag push 検証 ~30 分 |
| 環境制約 | Apple Silicon Mac は本セッションで使用不可。ローカル CMake 連携検証 (§3.4) は **CI 内 `workflow_dispatch` で代替**、シンボル解決検証 (`nm -u` / `nm -gU`) は同 CI 内で実施 |
| 関連仕様 | [docs/spec/ios-shared-lib.md §2.1 ORT 取得経路](../spec/ios-shared-lib.md#21-ort-取得経路), [§8 M1](../spec/ios-shared-lib.md#m1-取得経路の修復-release-ジョブの解凍) |
| 対象ワークフロー | `.github/workflows/release-shared-lib.yml` (`build-ios` ジョブ L123-206) |

> **依存関係:** なし (M0 相当)。ただし [⚠️ 配布形態の前提が変わる重大な発覚](#3-実装する内容の詳細) のため、当初想定の「URL 1 行 swap」より作業範囲が広い。

---

## 2. タスク目的とゴール

### 目的 (Why)

v1.11.0 〜 v1.12.0 のリリースサイクルで `Build iOS arm64` ジョブが `unzip: cannot find zipfile directory` で連続失敗している。原因は ONNX Runtime の GitHub Releases から iOS xcframework 配布物が削除され、Microsoft が CocoaPods/SPM/CDN 配布へ一本化したこと。

`release-shared-lib.yml` の `release` ジョブは `needs: [build-shared, build-ios, build-android]` で iOS に依存しているため、**iOS の単一ジョブ失敗で Linux/Windows/macOS/Android shared-lib も含む全 OS の成果物が GitHub Releases に上がっていない**。これが本対応の最大優先度根拠であり、表層の取得経路修正のみで release パイプライン全体を復旧できる。

### ゴール (DoD)

- [ ] `workflow_dispatch` 実行で `Build iOS arm64` ジョブが PASS する (tag なしでも単独動作)
- [ ] tag push (`v[0-9]*`) で `Create Release` ジョブが起動し、Linux/Windows/macOS/Android/iOS の全 shared-lib artifact が Releases にアップロードされる
- [ ] iOS artifact `libpiper_plus-ios-arm64-${VERSION}.tar.gz` が生成され、中身は `lib/libpiper_plus.a` + `lib/onnxruntime.framework/` + `include/piper_plus.h`
- [ ] `checksums-sha256.txt` に iOS artifact の sha256 が記録される
- [ ] CDN から取得した zip の sha256 が事前定義値と一致することが workflow 内で検証される

---

## 3. 実装する内容の詳細

### 3.1 編集ファイル

| ファイル | 編集箇所 | 変更内容 |
|---------|---------|---------|
| `.github/workflows/release-shared-lib.yml` | L144-176 (`Download ONNX Runtime iOS` ステップの単一 `run:` ブロック) | URL を Microsoft 公式 CDN に差し替え (L146-148)、sha256 検証ロジック追加 (新規挿入)、後続の `find` 抽出 (L150-174) を **`.a` から `.framework` ベースに書き換え** |
| `.github/workflows/release-shared-lib.yml` | L194-200 (`Package` ステップ) | tar.gz に `onnxruntime.framework/` を同梱するよう `cp -R` を追加 |

> **YAML 構造の補足:** `Download ONNX Runtime iOS` は単一 `run: |` ブロック (L145-176) であり、curl と find は同じ shell スクリプトの中に書かれている。「L144-148 を差し替え、L150-176 を流用」という当初記述は誤り (run ブロック内の **行範囲** を指しており、step 単位の置換ではない)。本チケットでは run ブロック全体を再編集する。

### 3.2 ⚠️ 配布形態の前提が変わる重大な発覚 (2026-05-04 検証)

旧 `https://github.com/microsoft/onnxruntime/releases/download/v1.17.0/onnxruntime-ios-xcframework-1.17.0.zip` と現行 `https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.17.0.zip` は **zip 内構造が完全に異なる**:

| 項目 | 旧 GitHub Releases zip | 現行 CDN zip |
|------|---------------------|------------|
| iOS slice 配布形態 | `ios-arm64/onnxruntime.a` (static archive) | `ios-arm64/onnxruntime.framework/onnxruntime` (Mach-O **dynamic library**, 拡張子なし) |
| Headers 配置 | `Headers/` 直下 (xcframework root) | `<slice>/onnxruntime.framework/Headers/` (slice ごと) |
| 同梱 macOS slice | なし | `macos-arm64_x86_64/onnxruntime.framework/` も含まれる (~69MB) |
| 想定リンク方式 | static (`-Wl,-force_load`) | dynamic (`Embed & Sign Frameworks`) |
| App Store 適合性 | ✓ static は適合 | △ dylib は **再配布側 (利用者) で Embed Frameworks への追加が必須** |

実機検証コマンド:
```bash
$ curl -sL -o ort-cdn.zip "https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.17.0.zip"
$ shasum -a 256 ort-cdn.zip
1623e1150507d9e50554e3d3e5cf9abf75e1bfd8324b74a602acfe45343db871

$ unzip -l ort-cdn.zip | grep "ios-arm64/onnxruntime.framework"
0           onnxruntime.xcframework/ios-arm64/onnxruntime.framework/
31080664    onnxruntime.xcframework/ios-arm64/onnxruntime.framework/onnxruntime    ← Mach-O dylib
0           onnxruntime.xcframework/ios-arm64/onnxruntime.framework/Headers/
107925      .../Headers/onnxruntime_cxx_api.h                                      ← C++ API 同梱
```

**配布形態の選択肢:**

| 案 | 概要 | M1 採用 |
|----|------|---------|
| **A. CDN zip + `.framework` を CMake に dynamic link + tar.gz に同梱配布** | 現行 CDN を素直に使う。`onnxruntime.framework` を artifact に同梱、利用者は Xcode で `Embed & Sign Frameworks` に追加 | **✓ 採用** |
| B. ORT ソースビルドで `.a` を自前生成 | 旧来の static `.a` を維持できるが、ビルド時間 30〜45 分。M1 のスコープを大きく逸脱 | × 不採用 (M5 候補) |
| C. CDN zip の dylib を ar archive に変換 | **不可能** (Mach-O dylib と ar archive はフォーマットが完全に別物) | × 物理的に不可 |

本 M1 では **案 A** を採用する。これは事実上「device-only `.a` 配布の継続」を諦め、`.framework` 配布に切り替える判断であり、仕様書 §2.3「互換性維持」の前提も併せて修正済み (`.tar.gz` 命名は維持、中身は `.framework` 同梱)。

### 3.3 具体的な差分案

**Before (L144-148, 旧 URL + 旧 zip 構造前提):**

```yaml
      - name: Download ONNX Runtime iOS
        run: |
          curl -L -o onnxruntime-ios.zip \
            "https://github.com/microsoft/onnxruntime/releases/download/v${ONNXRUNTIME_VERSION}/onnxruntime-ios-xcframework-${ONNXRUNTIME_VERSION}.zip"
          unzip -q onnxruntime-ios.zip -d onnxruntime-ios
          # 以下、find -name "onnxruntime.a" で .a を探すロジック (L150-176)
```

**After (~50 行、case A 採用):**

```yaml
      - name: Download ONNX Runtime iOS (Microsoft CDN)
        env:
          # 1.17.0 sha256 (検証日: 2026-05-04, Content-Length: 40,771,813 bytes)
          # 取得元: https://download.onnxruntime.ai/pod-archive-onnxruntime-c-1.17.0.zip
          # Last-Modified: Wed, 31 Jan 2024 19:39:25 GMT
          ORT_IOS_SHA256: "1623e1150507d9e50554e3d3e5cf9abf75e1bfd8324b74a602acfe45343db871"
        run: |
          set -euo pipefail
          PRIMARY_URL="https://download.onnxruntime.ai/pod-archive-onnxruntime-c-${ONNXRUNTIME_VERSION}.zip"

          curl -L --fail --retry 3 -o onnxruntime-ios.zip "${PRIMARY_URL}"

          # sha256 検証 (再現性確保 / サプライチェーン最低限)
          ACTUAL_SHA256=$(shasum -a 256 onnxruntime-ios.zip | awk '{print $1}')
          echo "Expected: ${ORT_IOS_SHA256}"
          echo "Actual:   ${ACTUAL_SHA256}"
          if [ "${ACTUAL_SHA256}" != "${ORT_IOS_SHA256}" ]; then
            echo "::error::ONNX Runtime iOS zip sha256 mismatch"
            exit 1
          fi

          unzip -q onnxruntime-ios.zip -d onnxruntime-ios

          # CDN zip は ios-arm64/onnxruntime.framework/onnxruntime (Mach-O dylib) を含む。
          # static .a は同梱されない (旧 GitHub Releases zip との非互換)。
          ORT_FW_ROOT=$(find onnxruntime-ios -name "onnxruntime.xcframework" -type d | head -1)
          IOS_SLICE="${ORT_FW_ROOT}/ios-arm64"
          ORT_FW_DIR="${IOS_SLICE}/onnxruntime.framework"

          if [ ! -d "${ORT_FW_DIR}" ]; then
            echo "::error::onnxruntime.framework not found at ${ORT_FW_DIR}"
            exit 1
          fi

          ORT_DYLIB="${ORT_FW_DIR}/onnxruntime"            # Mach-O dylib (拡張子なし)
          file "${ORT_DYLIB}"                              # 期待: Mach-O 64-bit dynamic library arm64

          # CMake に渡す形に整形
          mkdir -p ort-ios/lib ort-ios/include
          cp -R "${ORT_FW_DIR}/Headers/." ort-ios/include/
          # framework ディレクトリを丸ごと保持 (Embed & Sign に必要な Info.plist 込み)
          cp -R "${ORT_FW_DIR}" ort-ios/lib/onnxruntime.framework
          # CMake が単一ファイル指定を期待する場合の参照用シンボリックリンク
          ln -sf onnxruntime.framework/onnxruntime ort-ios/lib/libonnxruntime.dylib

          echo "ORT_IOS_DIR=${{ github.workspace }}/ort-ios" >> "$GITHUB_ENV"
          echo "ORT_IOS_LIB=${{ github.workspace }}/ort-ios/lib/libonnxruntime.dylib" >> "$GITHUB_ENV"
          echo "ORT_IOS_FRAMEWORK=${{ github.workspace }}/ort-ios/lib/onnxruntime.framework" >> "$GITHUB_ENV"
```

**Package ステップの拡張 (L194-200):**

```yaml
      - name: Package
        run: |
          mkdir -p artifacts/lib artifacts/include
          cp build-ios/libpiper_plus.a artifacts/lib/
          cp src/cpp/piper_plus.h artifacts/include/
          # ORT framework も同梱 (利用者が Embed & Sign する)
          cp -R "${ORT_IOS_FRAMEWORK}" artifacts/lib/
          cd artifacts
          tar -czf ${{ github.workspace }}/libpiper_plus-ios-arm64.tar.gz .
```

### 3.4 CMake 連携検証 (CI 内で完結)

> **環境制約:** ローカル Apple Silicon Mac は本セッションで使用不可。PR 起票前のローカル CMake 検証は実施せず、`workflow_dispatch` 起動による CI 内検証で代替する。CI で失敗した場合は CMake 側の修正をその場で行うか、不整合の規模が大きい場合のみ M2 統合に切替判断する。

#### CI 内 検証ステップ案 (M1 PR の `release-shared-lib.yml` に追加)

`Build (iOS)` ステップ後、`Verify symbol resolution` ステップを新設:

```yaml
- name: Verify symbol resolution against ORT framework
  run: |
    set -euo pipefail

    # piper-plus static archive の未解決シンボル一覧
    nm -u build-ios/libpiper_plus.a 2>/dev/null \
      | grep -v '^$' \
      | awk '{print $NF}' \
      | sort -u > undefined-syms.txt
    echo "undefined symbols in libpiper_plus.a:"
    wc -l undefined-syms.txt

    # ORT framework が export するシンボル一覧
    nm -gU "${ORT_FW_DIR}/onnxruntime" 2>/dev/null \
      | awk '$2 == "T" || $2 == "D" || $2 == "S" {print $NF}' \
      | sort -u > ort-exports.txt
    echo "exported symbols in onnxruntime framework:"
    wc -l ort-exports.txt

    # ORT で解決される expected: Ort* / OrtApi* で始まる ORT C API シンボル
    # Apple/libc 関数 (___stack_chk_*, _memcpy 等) は最終リンク時に解決されるため除外
    comm -23 undefined-syms.txt ort-exports.txt \
      | grep -E '^_(Ort|OrtApi|GetVersionString|OrtRelease|OrtCreate|OrtSession)' \
      > ort-related-unresolved.txt || true

    if [ -s ort-related-unresolved.txt ]; then
      echo "::error::ORT-related symbols unresolved against onnxruntime framework"
      cat ort-related-unresolved.txt
      exit 1
    fi
    echo "✓ all ORT-related symbols resolve against onnxruntime framework"
```

> **注:** `nm -u` の出力フォーマットは Mach-O ar archive に対しては `_<symbol>` 形式 (アンダースコア prefix)。`nm -gU` は dylib に対して `<address> <type> <symbol>` 形式を返す。grep 範囲は ORT 関連シンボルに絞り、Apple/libc 由来は除外する (これらは利用者アプリの最終リンク段階で解決されるため piper-plus xcframework 段階での未解決は正常)。

#### 検証失敗時の判断

- **ORT 関連シンボルのみ未解決** → ORT C API のリンク経路に問題、`cmake/PiperPlusShared.cmake` の iOS 分岐に framework 探索パス (`-F`) または `target_link_libraries` の syntax 修正
- **CMake が dylib path 指定を受理しない** → M1 PR を取下げ、M2 統合に切替

#### ローカル参考 (Apple Silicon Mac 環境を持つ contributor 向け)

```bash
# Apple Silicon Mac でローカル再現する場合の参考
unzip pod-archive-onnxruntime-c-1.17.0.zip
cmake -B build-ios-test \
  -DCMAKE_TOOLCHAIN_FILE=cmake/ios.toolchain.cmake \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=15.0 \
  -DPIPER_PLUS_BUILD_SHARED=ON \
  -DBUILD_SHARED_LIBS=OFF \
  -DONNXRUNTIME_DIR="$(pwd)/onnxruntime.xcframework/ios-arm64/onnxruntime.framework" \
  -DONNXRUNTIME_LIB="$(pwd)/onnxruntime.xcframework/ios-arm64/onnxruntime.framework/onnxruntime" \
  -DONNXRUNTIME_INCLUDE_DIR="$(pwd)/onnxruntime.xcframework/ios-arm64/onnxruntime.framework/Headers"
cmake --build build-ios-test --config Release
file build-ios-test/libpiper_plus.a   # 期待: ar archive (Mach-O arm64)
```

### 3.5 触らないファイル (M1 スコープ外)

- `cmake/ios.toolchain.cmake` (M2 で simulator slice 対応時に編集)
- `cmake/PiperPlusShared.cmake` (M1 では原則編集しない、§3.4 検証で必要なら最小修正)
- `examples/dart/README.md`, `examples/godot/README.md`, `docs/spec/ort-versions.md` (M3 で一括更新)

---

## 4. 担当者と Agent 並列レビュー観点

> **実行体制:** 本タスクは Claude Code が単独で実装・検証・コミットを行う。レビューは Agent ツール (subagent) で複数観点を並列起動して補強する。「人数」表記は廃止。

| 観点 (subagent role) | 数 | 主担当 | 責務 |
|---------------------|----|------|------|
| **実装** | - | Claude Code (主) | curl URL 差替、sha256 検証ロジック、`.framework` extraction 書換、Package ステップ拡張、`workflow_dispatch` 起動、PR 起票、commit |
| **整合性レビュー** | 1 観点 | Agent (general-purpose) | spec ↔ チケット ↔ workflow YAML 間の数値・URL・用語整合性 |
| **技術検証レビュー** | 1 観点 | Agent (general-purpose) | YAML / shell / sha256 / シンボル解決 (`nm -u`/`nm -gU`) の正当性、CDN URL の HTTP 200 実証 |
| **構造レビュー** | 1 観点 | Agent (general-purpose) | PR スコープ / DoD / rollback 妥当性 |

実装後 `Agent` ツールで 1-3 観点を並列起動し、指摘は本チケット内に反映してから commit。`gh pr merge --auto` で CI 完了マージ。

---

## 5. 提供範囲

### Included (M1 で扱う)

- `.github/workflows/release-shared-lib.yml` の `Download ONNX Runtime iOS` および `Package` ステップ修正
- 公式 CDN URL `https://download.onnxruntime.ai/pod-archive-onnxruntime-c-${ONNXRUNTIME_VERSION}.zip` への切替
- sha256 検証ステップの追加 (1.17.0 sha256 をハードコード)
- `find -name "onnxruntime.framework"` ベースの extraction 書換
- `onnxruntime.framework` を `libpiper_plus-ios-arm64-${VERSION}.tar.gz` に同梱
- §3.4 のローカル CMake 連携検証
- `release` ジョブの完走確認

### Excluded (本 M1 では扱わない)

| 範囲 | 担当マイルストーン |
|------|------------------|
| `build-ios` の `matrix.slice` 化 (device + simulator) | **M2** |
| `assemble-xcframework` ジョブ追加と `xcodebuild -create-xcframework` | **M2** |
| `cmake/ios.toolchain.cmake` の simulator slice パラメータ化 | **M2** |
| `libpiper_plus-ios-${VERSION}.xcframework.zip` artifact 追加 | **M2** |
| csukuangfj/onnxruntime-libs ミラーへの `\|\|` フォールバック | **M2 以降検討** (CDN が安定する前提なら不要、§9 C1) |
| `examples/dart/README.md` / `examples/godot/README.md` の iOS 統合手順刷新 (`Embed & Sign` 案内含む) | **M3** |
| `docs/spec/ort-versions.md` の iOS 行更新 | **M3** |
| `CHANGELOG.md` v1.13.0 エントリ追加 | **M3** |
| `docs/spec/ios-shared-lib.md` 冒頭 Status 更新 | **M3** |
| Swift Package Manager 連動 repo (`piper-plus-swift-package-manager`) | **M4** (別 issue) |
| ORT バイナリの自前ソースビルド | **M5 (候補)** (§11 検討事項) |

---

## 6. テスト項目

| # | 観点 | 期待結果 |
|---|------|---------|
| T1 | `workflow_dispatch` で `Build iOS arm64` ジョブを単独実行 | PASS。`libpiper_plus.a` が build-ios/ に生成される |
| T2 | sha256 検証 (一致時) | `Expected/Actual` がログに表示され、後続ステップに進む |
| T3 | sha256 検証 (不一致時、意図的に書き換え) | `::error::ONNX Runtime iOS zip sha256 mismatch` で fail-stop |
| T4 | `onnxruntime.framework` が CDN zip 内に存在することの動的アサート | `::error::onnxruntime.framework not found` のガードが効く (構造変更検知) |
| T5 | artifact 中身の検証 | `lib/libpiper_plus.a`, `lib/onnxruntime.framework/onnxruntime`, `include/piper_plus.h` がすべて存在 |
| T6 | `lipo -info` での arch 確認 | `libpiper_plus.a` と `onnxruntime.framework/onnxruntime` の両方が `arm64` |
| T7 | `release` ジョブ完走 (仮想 tag push) | 全 OS (Linux/Windows/macOS/Android/iOS) の artifact + `checksums-sha256.txt` が Releases にアップロード |
| T8 | 非 iOS ジョブへの影響なし | `build-shared` (linux-x64/macos-arm64/windows-x64) と `build-android` の挙動が現行と完全一致 |

---

## 7. Unit テストの内容

YAML / bash パッチに対する従来型 unit テストは限定的だが、以下のローカル静的検査を CI Engineer がローカル実行する:

| ツール | 対象 | コマンド例 |
|-------|------|----------|
| `yamllint` | `.github/workflows/release-shared-lib.yml` の構文 | `yamllint .github/workflows/release-shared-lib.yml` |
| `actionlint` | GitHub Actions 固有の構文 (`uses:`/`needs:`/`env:` の参照妥当性) | `actionlint .github/workflows/release-shared-lib.yml` |
| `shellcheck` | run ブロック内の bash 構文 | `shellcheck -s bash <(yq '.jobs.build-ios.steps[2].run' release-shared-lib.yml)` |
| `act` (nektos/act) | macOS runner image の取得が困難なため `--list` レベルの構文確認のみ | `act --list -W .github/workflows/release-shared-lib.yml` |

> **注:** `act` は macos runner を完全エミュレートできないため、実機検証は `workflow_dispatch` (E2E §8) で行う。本 §7 はあくまで静的検査ゲート。

---

## 8. E2E テストの内容

### 8.1 ローカル CMake 連携検証 (PR 起票前、必須)

[§3.4](#34-cmake-連携の事前検証-pr-起票前に必須) のコマンドを macOS で実行し、`libpiper_plus.a` が dylib リンクで生成できることを確認。失敗時は M1 を取下げ、M2 統合に切替。

### 8.2 `workflow_dispatch` による iOS ジョブ単独実行 (tag なし)

```bash
gh workflow run release-shared-lib.yml --ref fix/ios-shared-lib-build-377
gh run watch
```

確認:
- `Build iOS arm64` が PASS
- `Build linux-x64` / `Build macos-arm64` / `Build windows-x64` / `Build Android arm64-v8a` も PASS
- `Create Release` は `if: startsWith(github.ref, 'refs/tags/')` のため tag なしではスキップ
- artifact (`libpiper_plus-ios-arm64`) が Actions の Artifacts セクションに表示される

### 8.3 仮想 tag push による release ジョブ完走確認 (drypath)

```bash
git tag v1.13.0-rc1
git push origin v1.13.0-rc1
gh run watch
```

確認:
- 全 5 ジョブ (`build-shared` x3 + `build-ios` + `build-android`) PASS
- `release` ジョブが起動し PASS
- GitHub Releases ページに以下が並ぶ:
  - `piper-plus-shared-linux-x64.tar.gz`
  - `piper-plus-shared-macos-arm64.tar.gz`
  - `piper-plus-shared-windows-x64.zip`
  - `libpiper_plus-ios-arm64-v1.13.0-rc1.tar.gz`
  - `libpiper_plus-android-arm64-v8a-v1.13.0-rc1.tar.gz`
  - `checksums-sha256.txt`

### 8.4 artifact 中身の検証

```bash
gh release download v1.13.0-rc1 -p 'libpiper_plus-ios-arm64-*.tar.gz'
tar -tzf libpiper_plus-ios-arm64-*.tar.gz
# 期待: lib/libpiper_plus.a, lib/onnxruntime.framework/..., include/piper_plus.h
file lib/libpiper_plus.a                         # 期待: ar archive (Mach-O arm64)
file lib/onnxruntime.framework/onnxruntime       # 期待: Mach-O 64-bit dynamic library arm64
lipo -info lib/libpiper_plus.a                   # 期待: arm64
lipo -info lib/onnxruntime.framework/onnxruntime # 期待: arm64
```

### 8.5 失敗時の roll back 手順

- 仮想 tag を削除: `gh release delete v1.13.0-rc1 --yes && git push --delete origin v1.13.0-rc1`
- ブランチを `dev` HEAD に戻す: `git reset --hard origin/dev` (ローカルのみ)

---

## 9. 懸念事項

| # | 懸念 | 確度 | 対応方針 |
|---|------|------|---------|
| C1 | Microsoft が CDN URL スキーム (`download.onnxruntime.ai/pod-archive-onnxruntime-c-*`) を将来変更する可能性 | 低 (CocoaPods/SPM が共有しているため不変条件強) | M1 ではフォールバック追加せず、CDN 失効時に csukuangfj ミラー (URL は `onnxruntime.xcframework-${VERSION}.tar.bz2`、構造異なるため別 extraction 経路要) を M2 以降で組込む |
| C2 | 特定パッチバージョンが CDN に未公開 (例: 過去事例として 1.20.1 が欠番との報告あり) | 中 | `ONNXRUNTIME_VERSION` を `1.17.0` で pin し続ける。アップグレード時は事前に CDN HEAD で 200 確認を `docs/spec/ort-versions.md` 更新フローに組込む (M3) |
| C3 | sha256 をどう取得・管理するか | 中 (運用問題) | **方針:** 本チケット内に 1.17.0 の値 (`1623e115...db871`) を確定済み。ORT バージョン更新時のみ手動更新する旨をコメントで明示。Renovate / Dependabot 連携は M3 以降の検討事項 |
| C4 | dylib 配布が App Store ガイドラインで利用者に Embed 責務を負わせる | 高 | **M3 で利用者ガイドに `Embed & Sign Frameworks` 追加手順を必ず記載**。M1 段階では artifact 同梱のみ、ガイドは M3 |
| C5 | CDN zip に macOS slice (~69MB) も含まれており artifact が肥大化する可能性 | 低 | iOS slice のみを `find` で選択しているため、artifact には iOS slice の ~31MB のみ含まれる。zip ダウンロード時の通信は ~40MB だがビルド時のみ |
| C6 | `cmake/PiperPlusShared.cmake` が dylib リンクを想定していない場合 | 中 | §3.4 の事前検証で確認、必要なら `cmake/PiperPlusShared.cmake` の iOS 分岐に最小修正を追加。修正範囲が大きい場合は M2 統合判断 |
| C7 | sha256 不一致時の運用 | 低 | fail-stop。CI ログから手動で再計算し PR で値更新。誤更新による silent corruption を避ける |
| C8 | ORT 1.17.0 (2024-01) 固定の正当性 | 中 | iOS 単独で bump 不可: `release-shared-lib.yml` の `env.ONNXRUNTIME_VERSION` は **iOS / Android で共有**、`docs/spec/ort-versions.md` で C++/iOS/Android が 1.17.0 で揃っている。1.20.0 (44MB, 2024-10) / 1.22.0 (47MB, 2025-05) とも CDN HTTP 200 確認済 (2026-05-04)。M1 では bump せず、**全 OS 横断 bump (例: 1.17.0 → 1.22.0) を別 issue として起票**することを M3 §12.2 の運用課題に追加 |

---

## 10. レビュー項目

レビュアー (Workflow Reviewer + Supply Chain Reviewer + CMake Engineer) は以下のチェックリストを順に確認する。

### 10.1 Workflow YAML 妥当性

- [ ] `actionlint` / `yamllint` のローカル PASS が PR 説明に記載されている
- [ ] `Download ONNX Runtime iOS` および `Package` ステップ以外に変更がない (diff の最小性)
- [ ] `set -euo pipefail` が run ブロック先頭にある (失敗時 fail-stop)
- [ ] `curl --fail --retry 3` のフラグが付与され、404/5xx で確実に exit code != 0 になる

### 10.2 URL 構造の version 互換性

- [ ] URL に `${ONNXRUNTIME_VERSION}` 変数が使われ、env 単一ソースから driven されている
- [ ] 1.17.0 で動作確認済みであることが PR 本文に明記されている
- [ ] 将来のバージョン bump 手順 (sha256 の再計算が必要な旨) がコメントに残っている

### 10.3 sha256 埋込方法

- [ ] sha256 値が `env:` ブロックでステップローカルに定義されている (workflow グローバル env を汚染しない)
- [ ] sha256 値 (`1623e115...db871`) が PR 本文で `shasum -a 256` 実行ログとともに記録されている
- [ ] 検証コマンドが `shasum -a 256` (macOS 標準コマンド) を使っている。`sha256sum` は GNU coreutils 由来で macos-15 runner では PATH 上にない場合がある

### 10.4 `.framework` extraction ロジック

- [ ] `find -name "onnxruntime.framework" -type d` で取得し、不在時に `::error::` で fail-stop している
- [ ] `file ${ORT_DYLIB}` で「Mach-O 64-bit dynamic library arm64」が出力されることをアサートまたは表示
- [ ] `cp -R "${ORT_FW_DIR}" ort-ios/lib/onnxruntime.framework` で framework 全体 (Info.plist 込み) を保持
- [ ] `ln -sf` でシンボリックリンク `libonnxruntime.dylib` を作成 (CMake が単一ファイル指定を期待する場合のため)

### 10.5 `Package` ステップでの framework 同梱

- [ ] `cp -R "${ORT_IOS_FRAMEWORK}" artifacts/lib/` で `onnxruntime.framework/` が tar.gz 内にコピーされる
- [ ] tar.gz サイズが ~35MB 前後 (libpiper_plus.a + onnxruntime.framework iOS arm64) に収まる
- [ ] `tar -tzf libpiper_plus-ios-arm64.tar.gz` の出力に `lib/onnxruntime.framework/onnxruntime` がある

### 10.6 `workflow_dispatch` トリガ動作

- [ ] tag なしで `gh workflow run` から起動可能
- [ ] `Validate version tag` ステップが `if: startsWith(github.ref, 'refs/tags/')` で正しく分岐し、`workflow_dispatch` 時は skip される

### 10.7 既存ジョブへの非破壊性

- [ ] `build-shared` (Linux/macOS/Windows) のステップに変更がない
- [ ] `build-android` のステップに変更がない (Maven CDN 使用は別 URL ロジックのため独立)
- [ ] `release` ジョブの `needs:` / `files:` パターンが変わっていない
- [ ] `permissions: contents: write` が維持されている

### 10.8 観測性

- [ ] sha256 不一致時のエラーが `::error::` 形式で GitHub Actions UI に赤表示される
- [ ] `onnxruntime.framework` 不在時のエラーが `::error::` 形式で表示される

---

## 11. 一から作り直すとしたら

> 本セクションは「実装する PR スコープ」ではなく、**シニアアーキテクト視点での反省的検討**である。M1 (curl URL の swap + `.framework` extraction 書換) は意図的に保守的な現実解を採ったが、その選択を批判的に評価し、白紙からなら何を選ぶかを記録する。
>
> **⚠️ 指示子スコープ注記:** 本節の「案 X / 案 Y / 案 Z」は **M1 文脈に閉じた指示子** であり、他チケット (M2/M3/M4) の §11 で同名の案とは指す内容が異なる。M1 §11.2 では: 案 X = ORT ソースビルド + xcframework 統合、案 Y = 自前 ORT ミラー repo、案 Z = iOS 公式サポート廃止 を指す。文書横断で「案 X」を使用する際は必ずチケット名を併記すること。

---

### 11.1 そもそも何を作るべきか

M1 が修復しようとしている `build-ios` ジョブの「プリミティブ」を分解すると、3 つの暗黙の前提が積み重なっている:

1. **「device-only `.a` を CI で生成する」** という配布形態の前提 — 2026-05 検証で **CDN zip に `.a` は同梱されない** ことが判明、強制的に `.framework` 配布へ移行
2. **「ORT を毎ビルドで CDN から取得する」** という依存解決の前提
3. **「release ジョブが iOS 成功に強結合する」** というワークフロー設計の前提

仕様書 §1 の「層の階層構造」は (1) を「根本問題」と正しく指摘している。device-only `.a` も `.framework` 単独配布も、Dart FFI / Godot / Swift の用途と完全には噛み合わない (xcframework が望ましい)。M1 はこの (1) には触れず、(2) の取得経路修復と最小限の `.a→.framework` 書換のみ行う。

白紙から設計するなら最初の問いは「iOS 利用者はそもそも何を欲しいのか」である。Dart FFI ユーザーは Flutter プロジェクトに drag-and-drop できる `.xcframework`、Swift ユーザーは `import` 可能な SPM パッケージ、Godot ユーザーは GDExtension が `.framework` として参照できる構造を望む。**3 者すべて `.xcframework` で満たせる**。device-only single-slice 配布を欲しがる利用者は (CI 上で再リンクするライブラリ作者を除けば) おそらく少数だが、**観測手段がない以上「ゼロ」と断定するのはバイアス** である (§11.5 の永遠負債リスト参照)。

したがって白紙設計の自然な結論は **「M1 と M2 を統合し、最初から xcframework しか作らない」** になる。M1 で `.framework` 同梱 tar.gz を出す判断は、**v1.11.0〜v1.12.0 で iOS artifact が一度も Releases に届いていないため、後方互換の対象が観測不能** という事実を踏まえると、過剰な妥協かもしれない。1 リリース分の延命 (v1.13.0) で xcframework 化に切り替える価値は十分ある。

### 11.2 代替アーキテクチャ案

#### 案 X: xcframework + ORT ソースビルド + キャッシュ統合 (M1+M2+D の融合)

最初から `xcodebuild -create-xcframework` を中心に据え、ORT は `build_apple_framework.py` でソースビルドして GitHub Actions cache (`actions/cache@v4`) にキャッシュする。キャッシュキーは `onnxruntime-${ORT_VERSION}-${runner.os}-${XCODE_VERSION}-${PROTOBUF_REV}`。

**キャッシュ便益の現実的見積もり:**
- **初回ミス**: 30〜45 分 (CI Engineer の体感コストとして PR 待ち時間に直結)
- **cache hit 時**: 公称 10 秒、**実測 30〜60 秒** (~150MB の DL/解凍 + CMake 再構成、sherpa-onnx 実測ログ参照)
- **cache eviction**: 7 日未使用で削除、10 GB/repo 上限を ORT slice ごとに圧迫
- **macOS minutes コスト試算** (private repo 想定): $0.08/min × 10x multiplier × 30 min × ORT 更新 4 回/年 ≒ **$96/年**。PR ごとのキャッシュミスを加味すると ~$200/年規模

| 観点 | 評価 |
|------|------|
| **メリット** | (a) Microsoft **CDN 依存** をゼロに、(b) ORT 設定でバイナリサイズ最適化 (`--minimal_build`, `--use_xnnpack`)、(c) M1/M2 を 1 PR に統合、(d) サプライチェーン上 sigstore/cosign で自前署名可 |
| **デメリット** | (a) ORT のソース依存 (protobuf / abseil / flatbuffers / eigen / pytorch) を四半期ごとに追跡、(b) 「依存先の数」はむしろ増加、(c) ORT メジャー更新時に Xcode 互換性検証が必要、(d) キャッシュミス時の CI 30〜45 分は PR 体験を損ねる、(e) macOS runner 時間で月額 ~$10〜$20 を恒常的に消費 |
| **採用条件 (定量)** | (1) iOS Issue 受信頻度 ≥ 月 2 件 (3 ヶ月平均)、(2) download metrics で iOS artifact ≥ 100 DL/月、(3) メンテナの ORT 互換性検証に四半期 8 時間以上を割ける |

仕様 §4 で「30〜45 分」「保守コスト過大」を理由に却下されているが、これは **「初回」コスト** であり、キャッシュ前提なら定常コストは 1〜2 分/ビルドに収束する。ただし「**Microsoft 依存ゼロ**」は **CDN 依存ゼロの誤訳**であり、ORT のソース取得自体は依然として `github.com/microsoft/onnxruntime` から行うため、Microsoft repo の archive 化や API 変更には影響を受け続ける。仕様の却下理由は「初回コスト」と「定常コスト」を区別していない点で評価が荒い。

#### 案 Y: 自前 ORT ミラー repo (`ayousanz/onnxruntime-ios-builder`) — VOICEVOX 方式

別 repo で ORT を月次 build → GitHub Releases に xcframework.zip を置き、piper-plus 側はそこから取得する。VOICEVOX/onnxruntime-builder と同じ構造。

| 観点 | 評価 |
|------|------|
| **メリット** | (a) ORT ビルドコストを piper-plus CI から完全分離、(b) 他プロジェクトに横展開可 (Mozc 系/Rust audio 系で流用)、(c) Microsoft CDN 失効/値上げリスクを構造的に排除 |
| **デメリット** | (a) 2 repo メンテ、(b) ORT 上流のセキュリティパッチ追従責任を自分で負う、(c) piper-plus と独立にバージョン整合性を管理、(d) コミュニティから見て「もう一つの非公式ミラー」が増えるだけ |
| **採用条件 (定量)** | (1) Microsoft CDN の失効/帯域制限が観測的に発生 (HTTP 429 / 503 を 3 回以上)、または (2) piper-plus 以外に少なくとも 1 つの依存プロジェクトが現れる |

仕様 §4 で「過剰」と却下されているが、**プロジェクト規模ではなくリスク許容度の問題**。仮に Microsoft が ORT iOS の CocoaPods/SPM 配布を停止する判断をした場合 (Microsoft 自身も .NET MAUI / Xamarin の CocoaPods 配布を縮小した前例あり、ORT iOS は SPM 中心に既に動いている)、案 Y は唯一のオプションになる。仕様の却下理由は「平時の」過剰さしか見ていない。

#### 案 Z: iOS 公式サポート廃止 + SPM コミュニティ任せ

`build-ios` ジョブを削除し、`docs/spec/ios-shared-lib.md` を deprecation notice に書き換える。「コミュニティが SPM パッケージを作って維持してください」と明記し、piper-plus 本体は Linux/Windows/macOS/Android のみ公式サポートする。

| 観点 | 評価 |
|------|------|
| **メリット** | (a) メンテ負荷ゼロ、(b) macOS runner コストゼロ、(c) 「壊れた配布を出し続ける」負債の即時解消 |
| **デメリット** | (a) 利用者裾野の縮小、(b) コミュニティ SPM が現れない可能性、(c) Issue #377 を closed-as-wontfix にすることへの政治的コスト (利用者の「提供してほしい」コメントが定量データなしに残る) |
| **採用条件 (定量)** | (1) §11.2 案 X 採用条件をすべて未達、かつ (2) 6 ヶ月連続で iOS Issue ゼロ、(3) CI 失敗対応工数が他 OS の 2 倍超 |

仕様 §4 で「メンテナは将来 iOS 提供を望む」を理由に却下しているが、**「望む」と「実際に維持できる」は別問題**。CI 失敗を 2 リリースに渡って放置していた事実 (v1.11.0〜v1.12.0) は、現状のリソース配分では iOS を維持できていない強い証拠である。案 Z は感情ではなく実績ベースの選択肢。

### 11.3 配布フォーマットの根本選択

| フォーマット | iOS で許可 | piper-plus 適合度 | 評価 |
|--------------|----------|----------------|------|
| `.dylib` (shared) | App Store 直接配布は不可、`.framework` 同梱なら可 | △ (M1 はこれを採用) | 単独配布は実質不可、消費者側で Embed 必須 |
| `.a` (static archive, fat/thin) | 可 | △ | 旧 GitHub Releases zip で提供されていたが、現行 CDN zip には同梱されない |
| `.framework` (single slice) | 可 (deprecated for binary distribution) | △ | 単一 slice のみ、xcframework に置換すべき |
| `.xcframework` | **推奨** | **◎** | multi-slice、Module map、SPM/CocoaPods/手動 drag-and-drop すべて対応 |

`.a` 単独配布は 2018 年以降のプラクティスとして既に時代遅れだが、現実には **CDN zip 自体が `.a` を提供しなくなっている** ため、選択肢が `.framework` 配布 (M1 採用) または xcframework (M2 採用) に二択化されている。Apple は `xcodebuild -create-xcframework` を 2019 年 (Xcode 11) から提供しており、Dart FFI/Flutter/Godot/Swift エコシステムはこの 5 年間で xcframework 前提に収束した。**白紙設計なら `.a` を成果物として出す選択肢自体が無い**。

bitcode は **Xcode 14.3 (2023-03) でデフォルト無効化、Xcode 15 (2023-09) で完全削除**。最初から除外で正しい。

Module map (`module.modulemap`) は Swift から `import` する場合に必須だが、SPM 化 (M4) を見越すなら xcframework 内の `Headers/module.modulemap` 自動生成を CMake または手書きで提供すべき。M1/M2 では現状 module map に触れていないが、これは M4 で必ず必要になる。

LTO (Link Time Optimization) は piper-plus 側コードに局所適用可能だが、**piper-plus C API のソースサイズが小さい (~数千行) ため、最終 .a バイナリへの寄与は数 KB 〜数十 KB レベル**。ORT バイナリが 30MB 規模であるため、xcframework 全体では計測誤差レベル。優先度: 極めて低い。

### 11.4 CI / セキュリティ / ライセンス戦略

| 観点 | 白紙設計の選択 | 理由 |
|------|--------------|------|
| **CI ホスト** | GitHub Actions (`macos-15`、Apple Silicon、Xcode 16.4 デフォルト) で開始、月次予算超過時に self-hosted Mac mini に移行 | 案 X (ORT ソースビルド) を採るなら macOS minutes が ~10x になるため自前ホストが射程に入る |
| **キャッシュ戦略** | `actions/cache@v4` + sha256 ピン留め、月次手動 invalidate | ORT バイナリ ~50MB × 3 slice = キャッシュ容量上問題なし |
| **配布チャネル** | tag-based release (現状維持)、nightly は不要 | piper-plus はライブラリであり nightly 利用者が想定されない |
| **Artifact ホスト** | GitHub Releases (現状維持) | OCI image (ghcr.io) は iOS では消費側がない、CDN 自前 (R2/S3) は運用負荷に対して便益が薄い |
| **sha256 検証** | バージョンごとに `release-shared-lib.yml` 内に literal で記録 | M1 で実装済み (`1623e115...db871`) |
| **SLSA target** | Level 2 (signed provenance) を 2026 Q3 までに、Level 3 は M5 以降 | GitHub-hosted runner + tag protection で L2 は近い |
| **provenance 検証** | Microsoft 側 ORT バイナリは `gpg --verify` 提供無し、sigstore/cosign は採用されていない | Microsoft 公式 CDN を信頼ルートとせざるを得ず、案 Y (自前ミラー) で sigstore 署名を載せるのが唯一の本格的解 |
| **ライセンス継承** | 自前ビルド時 (案 X / Y) は MIT 表記を `xcframework/LICENSE` または `NOTICE` で同梱、third-party (protobuf BSD-3, abseil Apache-2.0, etc.) もすべて同梱 | App Store の Privacy Manifest にも反映が必要 |
| **SBOM** | CycloneDX / SPDX 形式で自動生成 (M5 以降) | SLSA L3 の前提条件 |

**iOS 配布固有の署名フロー (M1 で見過ごしやすい点):**

- **xcframework 自体に codesign は不要** (Apple 仕様、消費プロジェクト側で再署名)
- **notarization は macOS 配布のみ必要**、iOS App Store 審査では不要
- **`.dSYM` 同梱は推奨**: クラッシュレポートの symbolication に必須。M2 以降で xcframework と並べて配布検討
- 消費者側 (Flutter/Godot) の **embed signing** (`codesign --force --sign`) を妨げないよう、xcframework 内バイナリは unsigned のまま配布
- **Privacy Manifest (`PrivacyInfo.xcprivacy`)** が iOS 17+ で必須。ONNX Runtime の Privacy Manifest 対応状況は要追跡 (2026-05 時点で公式提供なし、利用者側で追加が必要)

ORT バイナリの provenance は **現実的には未解決**。Microsoft は ORT iOS バイナリに署名を提供しておらず (Windows DLL は Authenticode、Linux/macOS は無署名)、sha256 ピン留めが事実上の唯一の安全弁。これは Microsoft 全体のセキュリティ姿勢の問題で piper-plus 単独では解決できない。

### 11.5 現 M1 (curl URL swap + `.framework` extraction) とのギャップ

| 観点 | 白紙最適解 | 現 M1 | ギャップ評価 |
|------|----------|-------|------------|
| **配布形態** | xcframework のみ | `.framework` 同梱 tar.gz (M1 で発覚した CDN zip 構造に強制された妥協) | 大: M2 で解消 |
| **取得経路** | 自前ビルド or 自前ミラー | Microsoft CDN | 中: CDN 失効リスクが残る、§5/§9 のフォールバックは M2 以降で組込み |
| **CI 構造** | matrix slice + assemble job | 単一 device-only ジョブ | 大: M2 で解消 |
| **provenance** | sigstore/cosign 署名 | sha256 verification のみ | 大: 構造上 piper-plus 単独で解決不能、案 Y 採用が前提条件 |
| **module map** | 自動生成 + SPM ready | 提供なし | 中: M4 で必須、現時点で未着手 |
| **bitcode** | 除外 (正解) | 除外 (正解) | ゼロ |
| **後方互換負債** | 無 (新規設計のため) | tar.gz 命名のみ v1.14.0 まで維持 (中身は変化) | 小: 観測上の利用者なし、形式的負債 |
| **CDN 依存** | 無 | 有 (Microsoft) | 中: 失効時の復旧コストは半日〜1 日 |
| **ライセンス継承** | LICENSE 同梱 + SBOM | 未対応 (CDN zip の LICENSE のみ流用) | 中: M3 で `cp LICENSE artifacts/` 追加で局所対応可 |

**現 M1 を選んだ正当化 (限定的):**

1. **時間制約**: release ジョブ全体が iOS で巻き添え停止しており、Linux/Windows/macOS/Android の利用者を待たせている。1 日の URL swap + `.framework` extraction で全 OS の利用者を救える ROI は高い (ただし「圧倒する」とまでは言えない)。
2. **リスク回避**: M1+M2 統合 (案 X) はキャッシュ設計・ORT ソースビルドのデバッグで PR が膨らむ。1 PR を中規模 (~80 行) に保つことで失敗時のロールバックコストを最小化。
3. **後方互換の再評価**: device-only `.a` 利用者は v1.11.0〜v1.12.0 で artifact 自体が届いていないため、観測上の「既存利用者」はゼロ。とはいえ反証不能なので、tar.gz 命名のみ v1.13.0 で維持し v1.14.0 で xcframework に集約するのが穏当。
4. **学習コスト**: xcframework / SPM / sigstore を一気にやると PR レビューが困難。M1〜M4 で段階的に学習・検証する方が長期的に堅牢。

**永遠に埋まらない技術的負債:**

- **Microsoft CDN への構造的依存**: M2/M3 を完了しても、ORT 取得経路は Microsoft の運用判断に依存する。完全脱却は案 Y (自前ミラー) または案 X (ソースビルド) を採らない限り不可能。
- **ORT バイナリの provenance ギャップ**: 上流が署名を提供しないため、sha256 ピン以上のサプライチェーン保証は piper-plus 単独で実現不可。
- **iOS 利用者の実数不明**: 観測手段がなく、配布形態の最適化判断 (案 Z 採用可否) を実績ベースで下せない。`download metrics` や Discord 言及の収集は M3 以降の運用課題。

### 11.6 競合 iOS 配布サイズ比較

**(2026-05 時点 概算、xcframework device + simulator slices):**

| プロジェクト | 配布形態 | バイナリサイズ | ORT/推論基盤 |
|------------|--------|-------------|-----------|
| sherpa-onnx | xcframework (csukuangfj 自前ビルド) | ~80MB (CPU) | ORT カスタムビルド (xnnpack 有効) |
| whisper.cpp | xcframework (公式) | ~30MB (small モデル除く) | GGML 自前 (ORT 不使用) |
| VOICEVOX | xcframework + ONNX (別配布) | ~60MB (Core) | ORT 自前ビルド |
| **piper-plus 現状 (M1 後)** | `.framework` 同梱 tar.gz | ~35MB (`libpiper_plus.a` ~3MB + ORT ~31MB) | Microsoft 公式 ORT |
| **piper-plus 案 X 想定** | xcframework | 推定 ~50〜70MB (device + simulator) | ORT 自前ビルド |

案 X で「優位」と言うには、ORT カスタムビルドフラグ (`--minimal_build`, `--use_xnnpack`, `--disable_exceptions`) を駆使しても sherpa-onnx 並みが上限。**whisper.cpp は ORT 自体を使わないため別軸の競合**であり「優位」の意味を再定義する必要あり。

### 11.7 他 Apple プラットフォーム拡張の射程

xcframework の本来の便益は単一 zip で **iOS / macOS / visionOS / tvOS / watchOS / Mac Catalyst** を一括配布できる点にある。piper-plus が現在カバーしているのは iOS device + (M2 以降) iOS simulator のみ。

| プラットフォーム | ORT サポート (2026-05 時点) | piper-plus 適合度 |
|----------------|--------------------------|----------------|
| iOS | 公式サポート | M2 で対応予定 |
| macOS | 公式サポート | shared lib で別途対応済 (CDN zip にも同梱されているが、未使用) |
| Mac Catalyst | 部分サポート (xnnpack 一部不可) | 検討余地あり、利用者ゼロ |
| visionOS | **未サポート** (2026 Q1 確認) | 不可、ORT 待ち |
| tvOS | 非公式 (community ports のみ) | 不可、リスク高 |
| watchOS | 非公式、Apple Watch のメモリ制約から不適 | 不可 |

**判断:** xcframework に拡張する射程は実質 **iOS + macOS + Mac Catalyst** が上限。visionOS は ORT サポート次第で 2026 後半に検討可。**watchOS / tvOS はメモリ制約 / ORT 非対応により永続的に非対象**。

したがって xcframework 化 (M2) で「将来 visionOS にも展開できる柔軟性」を主張するのは過大評価。現実には iOS slice 2 つ (device + simulator) + macOS arm64 slice の 3 slice 構造が当面の上限。

### 11.8 App Store / App Extension のサイズ制約

piper-plus + ORT を iOS アプリに統合する際の **実効サイズ予算**:

| 配布先 | サイズ上限 (uncompressed, slice) | 影響 |
|-------|------------------------------|------|
| 通常 iOS アプリ (App Store) | 4 GB / slice | piper-plus + ORT (~35MB) は余裕 |
| iOS App Extension | 32 MB | **piper-plus + ORT 単独で超過**、Extension 内部使用は不可 |
| App Clip | 10 MB (uncompressed install size) | **絶対不可**、piper-plus 単独でも超過 |
| watchOS Watch App | 75 MB | ORT 非対応で議論不要 |

**判断:**

- 通常アプリ統合は問題なし
- **App Extension / App Clip 利用は構造的に不可**。これを CONTRIBUTING や README に明記する義務がある (利用者が実装後に発覚すると trust 損失)
- 案 X の「バイナリ最適化」便益は App Extension では **依然として不可** (32MB を ORT minimal_build で達成できる根拠が薄い)

したがって配布サイズを語る際は **「アプリ本体統合用」** という限定を明記すべき。「優位」の文脈は「アプリ本体間の比較」に閉じる。

### 11.9 もし今から始めるなら (推奨)

**著者個人の推奨: 案 X (xcframework + ORT ソースビルド + キャッシュ統合)**

| 推奨度 | ★★★★☆ (4/5) |
|--------|-------------|

**主便益は 2 つ:**
1. **CDN 失効耐性** (確率低、ただし発生時のコスト大)
2. **バイナリ最適化** (平時に顕在、ただし sherpa-onnx 並みが上限で「圧倒的優位」までは行かない)

**この推奨を採用しない合理的理由:**

1. **メンテ可処分時間が不足している場合** (定量: 四半期 8 時間以上を ORT 互換性検証に割けない): ORT の Xcode 16/17 互換性追従、protobuf/abseil バージョン管理は四半期に 1 回のメンテを要求する。これを担えないなら案 X は崩壊し、結果として案 Z (iOS 廃止) が誠実な選択になる。
2. **iOS 利用者数が観測上ゼロのまま続く場合** (定量: 6 ヶ月連続 Issue ゼロ): 投資対効果が見合わない。1 年経過時点で案 Z へピボット。
3. **Microsoft CDN が安定し続ける場合**: 平時の現 M1 + M2 で十分。案 X の便益 (1) は CDN 失効時にしか顕在化せず、(2) は ORT 公式バイナリでもオプション次第で同程度。

**最終所感:**

現 M1 は「**時間制約下の最短妥協**」であり、**最適解ではない**。release パイプライン全体の停止を即時解消する短期的価値はあるが、§11.1 で指摘した負債 (壊れた配布形態の延命、Microsoft CDN 依存の固定化、provenance ギャップ) はそのまま M2 / M3 に持ち越される。**M1 を完了した瞬間から、案 X か案 Z かの判断クロックが回り始める** ことを明記する。

具体的には、**M3 完了 PR マージ日を起点として 6 ヶ月以内** に iOS 利用者の実数把握 (download metrics、Issue 受信頻度、Discord 言及) を行い、案 X (ORT ソースビルド) か案 Z (iOS 廃止) かを判断することを強く推奨する。起点規約と判断ゲートは `docs/tickets/README.md §利用者観測タイムライン` で統一管理されている。負債は時間で利息が増える。M1 の URL swap が 1 年間「とりあえず動いている」状態で放置されることが、最も避けたいシナリオである。

---

## 12. 後続タスクへの連絡事項

### 12.1 M2 (xcframework 化) への引き継ぎ

> 担当チケット: [`docs/tickets/377-M2-xcframework.md`](377-M2-xcframework.md)

M1 で確立する以下の前提を M2 が継承する:

- **CDN URL は固定:** `https://download.onnxruntime.ai/pod-archive-onnxruntime-c-${ONNXRUNTIME_VERSION}.zip` を M2 でも継続使用。slice ごとの DL は不要 (1 回の DL で device + simulator + macOS の 3 slice が含まれる zip)。
- **`Download ONNX Runtime iOS` ステップの共通化:** M2 で `build-ios` を `matrix.slice` に分割する際、本ステップを composite action か reusable workflow に切り出す候補。M1 で先取りはしないが、構造的に切り出しやすいよう変数 (`PRIMARY_URL` / `ORT_IOS_SHA256`) を上部に集約済み。
- **`.framework` ベース extraction は M1 で確立:** `find -name "onnxruntime.framework" -type d` パターンが M2 でも simulator slice (`ios-arm64_x86_64-simulator`) に適用可能。
- **sha256 値の管理:** 同一 zip を扱うため M2 でも同じ sha256 (`1623e115...db871`) を再利用可。共通化のため env (`ORT_IOS_SHA256`) を workflow レベルに昇格させる選択肢があるが、M2 のリファクタ時に判断する。
- **xcodebuild -create-xcframework:** M2 で各 slice の `libpiper_plus.a` を組み合わせる際、ORT framework は xcframework 内のヘッダ提供のみとし、最終 xcframework に ORT framework を埋め込むかは利用者ガイドで判断 (Embed & Sign を促すなら xcframework に含めない方が clean)。
- **csukuangfj fallback:** M1 では実装せず、M2 以降で組込み (URL は `onnxruntime.xcframework-${VERSION}.tar.bz2`、構造異なるため別 extraction 経路要)。

### 12.2 M3 (docs / 移行ガイド) への引き継ぎ

> 担当チケット: [`docs/tickets/377-M3-docs-migration.md`](377-M3-docs-migration.md)

M1 完了時点で以下のドキュメント更新は **意図的にスキップ** している。M3 でまとめて反映する:

- [ ] `docs/spec/ort-versions.md:19` の iOS 行を `xcframework (Microsoft CDN: download.onnxruntime.ai)` に更新 (M2 完了後の表記が確定してから)
- [ ] `docs/spec/ios-shared-lib.md` 冒頭 Status を `Proposed` → `M1 完了 / M2 進行中` などに更新
- [ ] `CHANGELOG.md` v1.13.0 セクションに「iOS shared-lib 取得経路を Microsoft CDN に変更、配布形式が `.framework` ベースに変化 (Issue #377)」を追加
- [ ] `examples/dart/README.md` および `examples/godot/README.md` に **`onnxruntime.framework` の Embed & Sign 手順** を追記 (M1 で配布形式が変わった結果、利用者の組込み手順も変わる)
- [ ] 本書 README (`docs/tickets/README.md`) の表の状態列を `pending` → `done (PR #XXX, YYYY-MM-DD)` に更新

### 12.3 横断的な観測点

- **CI 実行時間:** M1 の修正で `Build iOS arm64` ジョブの実行時間が現状の失敗時 (~1 分で fail) から成功時 (~10〜15 分) に伸びる。`timeout-minutes: 30` は十分マージンあり。M2 で matrix 化すると最遅 slice が律速になる点は M2 で再評価。
- **artifact サイズ:** M1 後の tar.gz は ~35MB (libpiper_plus.a ~3MB + onnxruntime.framework iOS arm64 ~31MB)。GitHub Actions の artifact retention (デフォルト 90 日) には収まる。
- **Renovate 連携:** ORT バージョン bump 時に sha256 の手動更新が必要になる。本チケットでは Renovate 設定は範囲外だが、M3 以降で `regexManagers` を使った自動更新を別 issue で検討する。
- **iOS 利用者観測:** §11.5 で言及した永遠負債 (利用者実数不明) を解消するため、download metrics / Issue 頻度 / Discord 言及の集計を M3 以降の運用課題として記録。
- **VOICEVOX 方式 (`onnxruntime-ios-builder` 別 repo)** は M1〜M3 で採用しない。CDN 失効時の最終手段としてのみ §9 C1 で温存。

### 12.4 マージ後アクション

- [ ] `docs/tickets/README.md` 表の M1 行を `pending` → `done (PR #XXX, YYYY-MM-DD)` に更新
- [ ] `docs/spec/ios-shared-lib.md §8 M1` のチェックボックスを `[x] 完了` に更新
- [ ] M2 着手前に最低 1 回 `workflow_dispatch` で iOS ジョブ単独 PASS を確認
- [ ] (任意) v1.12.x の hotfix リリースとして cherry-pick するかを別途判断 (現状 v1.13.0 投入予定)
- [ ] §11.9 の「6 ヶ月以内に案 X (ORT ソースビルド) か案 Z (iOS 廃止) かを判断」のリマインダーをカレンダー登録 (起点: **M3 完了 PR マージ日**、`docs/tickets/README.md §利用者観測タイムライン` に統一規約あり、担当: メンテナ)
