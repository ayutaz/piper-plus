# M5-20: Android AAR パッケージング

> **Phase:** 5 -- 低優先度改善
> **利用者視点の優先度:** 高 -- Android は Flutter/Unity の主要デプロイ先
> **見積り:** 大
> **依存:** M4-4 (Android NDK ビルド) 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

Gradle ベースの AAR パッケージを作成し、Android アプリから `implementation 'com.piperplus:piper-plus:x.y.z'` で piper-plus を利用可能にする。

**現状:** M4-4 で Android NDK ビルド (arm64-v8a の `libpiper_plus.so`) は対応予定だが、Android アプリへの統合には JNI ラッパー + AAR パッケージングが必要。現時点では開発者が手動で .so を配置し JNI を書く必要がある。

**ゴール:**
1. JNI ラッパーで C API を Java/Kotlin API に公開
2. AAR に `libpiper_plus.so` + `libonnxruntime.so` + OpenJTalk 辞書をバンドル
3. Maven Central / GitHub Packages で配布

---

## 2. 実装する内容の詳細

### 2.1 ディレクトリ構成

```
android/
  piper-plus/
    build.gradle.kts
    src/main/
      AndroidManifest.xml
      java/com/piperplus/
        PiperPlus.kt          # Kotlin 高レベル API
        PiperPlusNative.kt    # JNI ブリッジ
      jniLibs/
        arm64-v8a/            # M4-4 のビルド成果物を配置
          libpiper_plus.so
          libonnxruntime.so
      assets/
        open_jtalk_dic/       # OpenJTalk 辞書
    src/test/
      java/com/piperplus/
        PiperPlusTest.kt      # Unit テスト (Robolectric)
    src/androidTest/
      java/com/piperplus/
        PiperPlusInstrumentedTest.kt  # Instrumented テスト
  example/
    build.gradle.kts          # サンプルアプリ
    src/main/
      java/com/piperplus/example/
        MainActivity.kt
```

### 2.2 Kotlin API

```kotlin
class PiperPlus private constructor(private val nativeHandle: Long) : AutoCloseable {
    companion object {
        fun create(context: Context, modelName: String): PiperPlus
    }

    /** ワンショット合成 */
    fun synthesize(text: String, speakerId: Int = 0): ShortArray

    /** ストリーミング合成 */
    fun synthesizeStream(text: String, speakerId: Int = 0): Flow<ShortArray>

    override fun close()  // piper_plus_free
}
```

### 2.3 JNI ブリッジ (`PiperPlusNative.kt`)

```kotlin
internal object PiperPlusNative {
    init { System.loadLibrary("piper_plus_jni") }

    external fun nativeCreate(modelPath: String, configPath: String, dictDir: String): Long
    external fun nativeSynthesize(handle: Long, text: String, speakerId: Int): ShortArray
    external fun nativeSynthStart(handle: Long, text: String, speakerId: Int): Int
    external fun nativeSynthNext(handle: Long): ShortArray?  // null = done
    external fun nativeFree(handle: Long)
}
```

### 2.4 JNI C++ 実装 (`piper_plus_jni.cpp`)

C API の薄いラッパー。`piper_plus_create` / `piper_plus_synthesize` / `piper_plus_synth_start` / `piper_plus_synth_next` / `piper_plus_free` をそれぞれ JNI 関数に変換。

### 2.5 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `android/` (新規ディレクトリ) | AAR プロジェクト一式 |
| `.github/workflows/` | AAR ビルド + publish ワークフロー追加 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | JNI ラッパー + Kotlin API + Gradle 設定 |
| テストエージェント | 1 | Instrumented テスト + サンプルアプリ |

合計 2 名。JNI + Gradle + Android CI の知識が必要。

---

## 4. 提供範囲とテスト項目

### スコープ

- JNI ラッパー (`piper_plus_jni.cpp`)
- Kotlin 高レベル API (`PiperPlus.kt`)
- AAR ビルド (Gradle)
- サンプルアプリ
- CI ワークフロー (AAR ビルド + publish)

### ユニットテスト (Robolectric)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestCreateNull` | 不正なモデルパスで作成 | 例外スロー |
| `TestAutoCloseable` | `use {}` ブロック後の解放 | ネイティブリソース解放 |

### Instrumented テスト (Android 端末)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestSynthesizeJA` | 日本語テキスト合成 | ShortArray.size > 0 |
| `TestSynthesizeEN` | 英語テキスト合成 | ShortArray.size > 0 |
| `TestStreamFlow` | Flow で逐次受信 | collect で複数チャンク |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| AAR サイズ | 高 | `libpiper_plus.so` (~30MB) + `libonnxruntime.so` (~50MB) + 辞書 (~50MB) = ~130MB。ABI split で arm64-v8a のみにし、辞書は別途ダウンロードにすることを検討 |
| ONNX Runtime Android 版の互換性 | 中 | AAR 内の ORT バージョンとアプリ側の ORT が競合する可能性。`repackage` で namespace 分離を検討 |
| OpenJTalk 辞書のパス | 中 | assets から内部ストレージにコピーして `dict_dir` に指定。初回起動時のみ |

### レビュー時の確認項目

1. JNI のエラーハンドリング (`GetStringUTFChars` の NULL チェック等)
2. JNI グローバル参照のリーク防止
3. `piper_plus_free` がメインスレッド以外から呼ばれた場合の安全性
4. ProGuard / R8 のルールで JNI メソッドが難読化されないこと

---

## 6. 一から作り直すとしたら

ONNX Runtime の Android AAR (`onnxruntime-android`) を直接依存に追加し、`libonnxruntime.so` の二重バンドルを避ける設計が望ましい。ただし、piper-plus の C API が ORT の特定バージョンに依存するため、バージョン管理の複雑さとのトレードオフがある。

---

## 7. 後続タスクへの連絡事項

- **M5-18 (Dart FFI):** Flutter Android では AAR を `android/build.gradle` の `implementation` で追加するだけで利用可能になる。Dart FFI サンプルの Android 手順を AAR 方式に更新。
- **Maven Central 公開:** GPG 署名 + Sonatype アカウント設定が必要。初回は GitHub Packages で検証後に Maven Central に移行。
