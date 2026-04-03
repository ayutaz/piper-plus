# M5-11: Android armeabi-v7a / x86_64 対応

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 中 -- Flutter Android アプリで全デバイスカバレッジが必要
> **見積り:** 中
> **依存:** M4-4 (Android NDK arm64-v8a)
> **ブロック:** なし
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

現在の `android-build.yml` は `arm64-v8a` のみビルドしている。`armeabi-v7a` (32-bit ARM) と `x86_64` (エミュレータ) を追加し、Flutter Android アプリが全主要 ABI をカバーできるようにする。

**現状:** `android-build.yml` は `arm64-v8a` 単一 ABI。32-bit ARM デバイスや Android Emulator (x86_64) では動作しない。

**ゴール:** CI マトリクスに `armeabi-v7a` と `x86_64` を追加し、ONNX Runtime AAR から各 ABI の `.so` を抽出してリンクする。

---

## 2. 実装する内容の詳細

### 2.1 android-build.yml のマトリクス化

```yaml
jobs:
  build-android:
    strategy:
      matrix:
        abi: [arm64-v8a, armeabi-v7a, x86_64]
    name: Android ${{ matrix.abi }}
    runs-on: ubuntu-22.04

    steps:
      # ... checkout, NDK setup ...

      - name: Extract ORT AAR
        run: |
          unzip onnxruntime-android-*.aar -d ort-extracted
          cp ort-extracted/jni/${{ matrix.abi }}/libonnxruntime.so \
             $BUILD_DIR/lib/

      - name: CMake configure
        run: |
          cmake -B build \
            -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
            -DANDROID_ABI=${{ matrix.abi }} \
            -DANDROID_PLATFORM=android-${{ env.ANDROID_API_LEVEL }} \
            ...
```

### 2.2 armeabi-v7a 固有の対応

- `ANDROID_ARM_NEON=ON` を設定 (ORT が NEON を要求)
- `CMAKE_CXX_FLAGS` に `-mfloat-abi=softfp -mfpu=neon` を追加 (必要に応じて)

### 2.3 x86_64 固有の対応

- エミュレータ向けのため追加の設定は不要
- CI でエミュレータテストを実行する場合は別チケット

### 2.4 成果物のパッケージング

3 ABI を統合した ZIP ファイルをリリース成果物として出力:

```
piper-plus-android/
  arm64-v8a/
    libpiper_plus.so
    libonnxruntime.so
  armeabi-v7a/
    libpiper_plus.so
    libonnxruntime.so
  x86_64/
    libpiper_plus.so
    libonnxruntime.so
```

### 2.5 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `.github/workflows/android-build.yml` | マトリクス追加 (`armeabi-v7a`, `x86_64`) + ABI 別 ORT 抽出 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | CI ワークフロー修正 + ビルド確認 |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### CI テスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `build-arm64-v8a` | 既存 arm64-v8a ビルド | 成功 (回帰なし) |
| `build-armeabi-v7a` | 32-bit ARM ビルド | `libpiper_plus.so` 生成 |
| `build-x86_64` | x86_64 ビルド | `libpiper_plus.so` 生成 |
| `artifact-structure` | 成果物 ZIP の構造確認 | 3 ABI の `.so` が含まれる |

### ビルド検証 (手動)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `nm -D libpiper_plus.so` | シンボルテーブル確認 | `piper_plus_*` シンボルが export されている |
| `file libpiper_plus.so` | ELF ヘッダー確認 | 正しい ABI (ARM/x86_64) |

---

## 5. 懸念事項とレビュー項目

| リスク | 影響度 | 対策 |
|--------|--------|------|
| ONNX Runtime AAR に `armeabi-v7a` / `x86_64` の `.so` が含まれていない | 高 | ORT 1.14.1 AAR の内容を事前確認。含まれていない場合は ORT バージョンアップまたはソースビルドが必要 |
| 32-bit ARM での `int64_t` アライメント問題 | 低 | ONNX Runtime が 32-bit ARM を公式サポートしている限り問題なし |
| CI 時間の増加 (3 ABI x ビルド時間) | 中 | マトリクスは並列実行のため wall-clock 時間は同程度 |

### レビュー時の確認項目

1. ORT AAR から正しい ABI の `.so` が抽出されていること
2. `armeabi-v7a` で NEON フラグが設定されていること
3. 成果物の ZIP 構造が Flutter plugin の `jniLibs/` レイアウトと互換であること

---

## 6. 一から作り直すとしたら

`x86` (32-bit) も追加してエミュレータの完全カバレッジを確保する選択肢がある。ただし 32-bit x86 の Android デバイスは事実上絶滅しており、CI コストに見合わない。`x86_64` のみで十分。

---

## 7. 後続タスクへの連絡事項

- **M3-5 (リリースワークフロー):** Android 成果物を GitHub Release に含める場合、`build-all-platforms.yml` との統合が必要。
- **NNAPI EP:** `armeabi-v7a` / `x86_64` でも `"nnapi"` provider (M5-6 参照) が利用可能か検証が必要。
