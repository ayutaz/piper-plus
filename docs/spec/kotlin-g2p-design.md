# Kotlin G2P ライブラリ設計書 (Issue #388)

> **親 Issue**: [#388](https://github.com/ayutaz/piper-plus/issues/388) — 「Kotlin 向けの g2p ライブラリの提供」
> **作業ブランチ**: `feat/issue-388-kotlin-g2p`
> **要件定義書**: [kotlin-g2p-requirements.md](kotlin-g2p-requirements.md) (本書策定後の技術調査結果を反映)
> **対応 INDEX**: [docs/tickets/kotlin-g2p/README.md](../tickets/kotlin-g2p/README.md)
> **マイルストーン管理**: [docs/tickets/kotlin-g2p/MILESTONES.md](../tickets/kotlin-g2p/MILESTONES.md)
> **判定基準**: 自動化可能性 (CLI/CI で完結) を最優先。実装工数は評価軸から除外。

> ⚠️ **要件定義書による前提変更**: 本設計書策定後の技術調査で、`piper_plus_phonemize()` は ONNX モデル必須であることが判明 (要件定義書 §5)。Kotlin AAR は **C API に追加する engine-less G2P エントリポイント (FR-CAPI-1)** を呼ぶ前提に変更。本書 §5.4 の JNI bridge 設計は実装着手前に該当部分を更新する。

---

## 1. ゴール

`piper-plus-g2p` ファミリーに **Kotlin/Android 向けの公式 G2P ライブラリ**を追加し、Android アプリ開発者が他言語ランタイム (Python/Rust/Go/npm) と同じ G2P を Kotlin から呼び出せる状態を作る。

**主要 KPI**:
- Android アプリから `implementation("io.github.ayutaz:piper-plus-g2p-android:X.Y.Z")` 1 行で導入可能
- 8 言語 (JA/EN/ZH/KO/ES/FR/PT/SV) すべてで Python ランタイムと **byte-for-byte 一致** する IPA / PUA トークン列を返す
- 既存ランタイムと同じ `zh_en_loanword.json` を共有 (CI で同期検証)
- **CI で完結する自動テスト**: ユニットテスト (JVM) + Android instrumented test (Gradle Managed Devices) で実機なしに回帰検知
- Maven Central 公開も GitHub Actions で完全自動化 (人手介入ゼロ)

**スコープ外**:
- TTS フル機能 (合成エンジン) — 既存 `android/piper-plus/` の AAR 草案で別途扱う
- Android System TTS Engine 化 (`TextToSpeechService`) — G2P ライブラリ Issue とは別、必要なら別 Issue で扱う
- iOS 共通化 (KMP) — iOS は xcframework + SPM で既に対応済、Kotlin G2P と無関係

---

## 2. ユーザー視点と OSS コンセプト分析

### 2.1 piper-plus のコンセプト核心

[README.md](../../README.md) と既存ランタイム配布パターンから抽出した、ライブラリ提供時に踏襲すべき哲学:

| 哲学 | 根拠 | Kotlin G2P への影響 |
|------|------|---------------------|
| **MIT 唯一の Piper フォーク** | rhasspy/piper はアーカイブ済 (2025-10-06)、OHF-Voice 版は GPL-3.0。piper-plus が MIT 商用 OK の唯一選択 | Kotlin AAR も MIT 維持。GPL 依存 (espeak-ng) を絶対に持ち込まない |
| **espeak-ng 非依存の独自 G2P** | 規則ベース 4 言語 + g2p-en (Apache-2.0) + pypinyin (MIT) + pyopenjtalk-plus (MIT) + g2pk2 (Apache-2.0) | Kotlin でも同じ依存ツリーを再現する必要なし。C API 経由で既存の C++ 実装を呼ぶことで自動的に同じ哲学を維持 |
| **二段階パッケージ (フル TTS / G2P 単体)** | Python `piper-plus-g2p`、Rust crate `piper-plus-g2p`、npm `@piper-plus/g2p`、Go `phonemize` パッケージとして既に独立配布 | Kotlin/Android も TTS フル機能とは独立した G2P 専用 AAR を出すべき (既存 `android/piper-plus/` は将来 TTS フル AAR、新規は G2P 単体 AAR) |
| **モデルとコードの分離** | コード = レジストリ (PyPI/crates.io/NuGet/npm)、モデル = HuggingFace Hub | Kotlin G2P は AAR (Maven Central) に G2P コードのみ。日本語辞書 (~50MB) は AAR に含めず、消費者がオプション選択 |
| **ランタイム間の byte-for-byte 一致 (CI gate)** | `zh_en_loanword.json` 7 mirror、`scripts/check_loanword_consistency.py`、PUA fixture matrix | Kotlin AAR も同じ fixture を CI で読み、Python と byte 一致を強制 |

### 2.2 ターゲットユーザー像

Issue #388 の Use case「Android のアプリ対応時」+ 既存ランタイム README から推定するユーザー像:

1. **Android アプリ内 TTS 開発者** (主ターゲット) — オフライン読み上げ機能をアプリに組み込みたい。G2P → 自前の音響モデル推論パイプライン
2. **アクセシビリティアプリ開発者** — screen reader 代替、視覚障害支援アプリで多言語 phonemize が必要
3. **音声対話・ゲーム開発者** — Unity/Godot 経由の Android 配布、NPC セリフ phonemize
4. **音声処理研究者** — Android 端末で実機ベンチマーク

→ いずれも「**G2P をライブラリとして組み込みたい**」が共通。System TTS Engine 化はユースケースの一部 (#2 のみ) なので、AAR 配布が一次優先。

### 2.3 ユーザーが期待する導入体験

他ランタイム (`@piper-plus/g2p`、`piper-plus-g2p`) の README から逆算した「最小ハードル」:

```kotlin
// build.gradle.kts (アプリ側)
dependencies {
    implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")
}

// MainActivity.kt
val g2p = PiperPlusG2p.create(context)        // 辞書はオプション、デフォルトは規則ベース 7 言語
val result = g2p.phonemize("Hello world", "en")
println(result.phonemes)                       // "h ə l oʊ w ɜ ɹ l d"
g2p.close()
```

日本語辞書を使う場合のオプトイン:

```kotlin
val g2p = PiperPlusG2p.create(
    context,
    dictionary = OpenJTalkDictionary.fromAssets(context, "open_jtalk_dic")
)
```

---

## 3. 既存資産の整理

### 3.1 C API (`src/cpp/piper_plus.h`) — そのまま使える

| エントリポイント | 役割 | Kotlin G2P での利用 |
|----------------|------|---------------------|
| `piper_plus_phonemize()` | エンジン初期化後、音響モデル不要で G2P 単体実行可 | **そのまま JNI から呼ぶ** |
| `piper_plus_phonemize_embedded_english()` | 中英混在の埋め込み英語 phonemize (PUA tone marker 付き) | ZH-EN code-switching 対応のため JNI 公開 |
| `piper_plus_load_custom_dict()` | 動的辞書追加 | カスタム辞書 API として Kotlin 公開 |
| `piper_plus_available_languages()` | 利用可能言語列挙 | プロパティとして Kotlin 公開 |
| `piper_plus_loanword_load_default()` / `piper_plus_loanword_load_from_path()` | ZH-EN loanword JSON ロード | デフォルト埋め込みデータがあるので通常は呼ばない |

**スレッドセーフティ**: per-engine 単一スレッド (`piper_plus.h:76-77`)。Kotlin 側は `synchronized(this)` でガード。`piper_plus_get_last_error()` は thread-local。

**メモリ管理**: `PiperPlusPhonemeResult.phonemes` / `language` は **BORROWED ポインタ**。JNI で受け取った直後に `JNIEnv::NewStringUTF()` で Kotlin String にコピー必須。

### 3.2 Android NDK ビルド基盤 — 既に完成

| 資産 | 場所 | 状態 |
|------|------|------|
| 3 ABI ビルド CI | `.github/workflows/android-build.yml` | arm64-v8a / armeabi-v7a / x86_64 を NDK 26.1 + ORT 1.17.0 でビルド済 |
| Release artifact | `.github/workflows/release-shared-lib.yml:496-579` | **arm64-v8a 単体のみ配布** (拡張余地あり) |
| ZH-EN loanword embedding | `cmake/PiperCommon.cmake:103-132` | `PIPER_PLUS_EMBEDDED_LOANWORD` flag で iOS/Android に C-array 埋め込み |
| Android stub | `src/cpp/openjtalk_ios_stub.c` | iOS 専用、Android 用は不要 (Linux と同じビルド) |

### 3.3 既存 Kotlin AAR 草案 — TTS 用、G2P API 不在

`android/piper-plus/` には既にフル TTS AAR の草案がある:

```
android/
├── build.gradle.kts            # AGP 8.7.3, Kotlin 2.1.0
├── settings.gradle.kts
├── gradle.properties
└── piper-plus/                 # 既存 AAR モジュール (TTS フル)
    ├── build.gradle.kts        # namespace=com.piperplus, compileSdk=35, minSdk=24, arm64-v8a only
    ├── src/main/
    │   ├── AndroidManifest.xml
    │   ├── cpp/
    │   │   ├── CMakeLists.txt
    │   │   └── piper_plus_jni.cpp  # synthesize / synthesizeStream の JNI のみ
    │   └── java/com/piperplus/
    │       ├── PiperPlus.kt          # AutoCloseable, synthesize, Flow<ShortArray>
    │       ├── PiperPlusNative.kt    # external native fun 宣言
    │       └── PiperPlusException.kt
```

**ギャップ**:
- `phonemize()` JNI wrapper / Kotlin API なし
- `PhonemeResult` data class なし
- G2P 単体配布用の独立 Gradle module なし
- Maven Central 公開未設定 (`maven-publish` プラグインのみ、署名・公開先未設定)
- `arm64-v8a` のみ → エミュレータ自動テスト用に `x86_64` 必須

### 3.4 各ランタイムの G2P 単体配布パターン (Kotlin で踏襲すべき)

| ランタイム | 命名 | 言語選択 | 辞書 | 出典 |
|----------|------|---------|------|------|
| Python | `piper-plus-g2p` (PyPI) | extras: `[ja, en, zh, ko, all]` | pyopenjtalk-plus に同梱 | `src/python/g2p/pyproject.toml` |
| Rust | `piper-plus-g2p` (crates.io) | Cargo features: `japanese`, `english`, ... | `naist-jdic` feature | `src/rust/piper-plus-g2p/Cargo.toml` |
| Go | `github.com/ayutaz/piper-plus/src/go/phonemize` | パッケージ全体で全言語含む | testdata 参照 | `src/go/phonemize/` |
| npm | `@piper-plus/g2p` (npm) | subpath imports: `/ja`, `/en`, ... | WASM module 同梱 (`dist/openjtalk.wasm`) | `src/wasm/g2p/package.json` |

**Kotlin の選択**:
- **命名**: `piper-plus-g2p-android` (Maven artifactId) / Kotlin パッケージ `com.piperplus.g2p`
- **言語選択**: 単一 AAR に全言語コードを含む。日本語辞書だけ別 AAR (`piper-plus-g2p-android-openjtalk`) か Hugging Face DL でオプトイン
- **辞書**: AAR には含めない (assets として消費者が配置 or 初回 DL)

---

## 4. アプローチ比較

ユーザー指針「**自動化最優先 (CLI/CI で完結)、実装工数は無視**」で各案を再評価。

| # | アプローチ | 自動テスト性 | CI 配布性 | 既存資産活用 | espeak-ng-free 維持 | 総合 |
|---|----------|------------|---------|-----------|-------------------|------|
| **A** | **JNI + AAR (Maven Central)** | ◎ (JVM unit test + Gradle Managed Devices で emulator も完全自動) | ◎ (vanniktech plugin + GitHub Actions で署名・公開自動化) | ◎ (既存 `libpiper_plus.so`、JNI テンプレート、Android CI 流用) | ◎ | **★★★★★ 推奨** |
| B | Pure Kotlin / JVM 移植 | ◎ (JVM 単体テストのみ) | ◎ (Maven Central 公開シンプル) | △ (C++ 実装を Kotlin に再移植、OpenJTalk のみ困難) | ◎ | ★★★★ |
| C | Kotlin Multiplatform (KMP) + cinterop | △ (cinterop は JVM 不可、Android 側は結局 JNI) | × (multi-target metadata jar 管理が複雑) | △ | ◎ | ★★ |
| D | System TTS Engine 化 | × (実機 TTS API 経由のテストが必須) | × (アプリとして Play Store/F-Droid 配布) | △ (G2P 単体ライブラリ要件と一致しない) | ◎ | ★ (別 Issue で扱う) |
| E | Termux CLI 配布 | △ | × | × | ◎ | ★ (採用しない) |

### 4.1 A. JNI + AAR (推奨) — 詳細

**自動テスト戦略** (実機不要):

| テスト層 | ツール | CI 実行先 | 内容 |
|---------|--------|---------|------|
| **L1: Pure Kotlin unit test** | `./gradlew :piper-plus-g2p:test` | GitHub Actions Linux runner | data class、入力バリデーション、URL ヘルパー |
| **L2: Native JNI smoke test** | Robolectric or JVM with `System.load` | Linux runner (Linux .so をリンクしてテスト) | JNI シグネチャ整合性、メモリリーク |
| **L3: Android instrumented test** | **Gradle Managed Devices** (`./gradlew :piper-plus-g2p:pixel2api30DebugAndroidTest`) | Linux runner (KVM 利用、ヘッドレス emulator) | 実 Android 環境で C API 経由の G2P 動作確認 |
| **L4: Cross-runtime parity** | 既存 fixture (`tests/fixtures/g2p/*.json`) を Kotlin から読み込み Python と byte 一致確認 | Linux runner | ZH-EN loanword、PUA 含む全 8 言語パリティ |
| **L5: ABI 整合性** | `objdump -p` / `nm -D` で `.so` の symbol/ABI 検証 | Linux runner | 16 KB page size 対応 (`max-page-size=16384`) |

**配布自動化**:
- `vanniktech/gradle-maven-publish-plugin` (Sonatype Central Portal 対応) で GPG 署名・publish を 1 タスク化
- GitHub Actions secrets: `MAVEN_CENTRAL_USERNAME`, `MAVEN_CENTRAL_PASSWORD`, `SIGNING_IN_MEMORY_KEY`, `SIGNING_IN_MEMORY_KEY_PASSWORD`
- タグ `kotlin-g2p-v*` push で自動 release (既存の `release-*` ワークフローパターンを踏襲)

**Maven coordinates**:
```
groupId:    io.github.ayutaz
artifactId: piper-plus-g2p-android
version:    1.0.0
```

(`com.piperplus` は既存 AAR で使用中の Java/Kotlin パッケージ名 namespace。Maven Central groupId は `io.github.ayutaz` が DNS 検証不要で最も摩擦が少ない)

### 4.2 B. Pure Kotlin / JVM 移植 — 部分採用

**部分採用提案**: 規則ベース 4 言語 (ES/PT/FR/SV) は Pure Kotlin でも十分実装可能。ただし:
- **判断**: 既存 C++ 実装と byte 一致を保つには重複実装によるドリフトリスクあり (PUA 仕様の同期が 1 mirror 増えるだけで負荷増)
- **結論**: 全 8 言語を C API 経由に統一。AAR サイズ最適化のため将来的に「ルールベース言語のみ Pure Kotlin」を別 AAR (`piper-plus-g2p-pure`) として出す可能性は残す

### 4.3 C. KMP — 採用しない

**理由**:
- iOS は既に xcframework + SPM で完成。KMP で再構築するメリットなし
- cinterop は JVM ターゲットでは使えず、Android 側は結局 JNI を書くことになる
- multi-target metadata jar の Maven Central 公開は複雑で自動化難度が高い

### 4.4 D. System TTS Engine — 別 Issue で扱う

**理由**: G2P 単体ライブラリの範疇外。System TTS Engine は Service + Activity を含む「アプリ」として配布する形で、AAR 配布要件 (Issue #388) と直交する。sherpa-onnx も `SherpaOnnxAar` (ライブラリ) と `SherpaOnnxTtsEngine` (アプリ) を分離している。

将来扱う場合、本 Issue で作る AAR を依存に持つ形で **別 Issue / 別リポ** として実装。

---

## 5. 推奨アプローチ (採択案)

### 5.1 アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│ Consumer App (Kotlin/Java)                                  │
│   implementation("io.github.ayutaz:piper-plus-g2p-android") │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ AAR: piper-plus-g2p-android (新規モジュール)                │
│                                                              │
│  Kotlin API (com.piperplus.g2p)                             │
│   ├─ PiperPlusG2p (AutoCloseable)                           │
│   ├─ PhonemeResult (data class)                             │
│   ├─ PiperPlusG2pException                                  │
│   └─ OpenJTalkDictionary (オプション)                        │
│                                                              │
│  JNI Bridge                                                  │
│   ├─ PiperPlusG2pNative.kt (external fun 宣言)              │
│   └─ piper_plus_g2p_jni.cpp                                 │
│                                                              │
│  jniLibs/                                                    │
│   ├─ arm64-v8a/libpiper_plus.so                             │
│   ├─ arm64-v8a/libpiper_plus_g2p_jni.so                     │
│   ├─ armeabi-v7a/...                                        │
│   └─ x86_64/...     ← emulator テスト用                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ libpiper_plus.so (既存 C API)                               │
│   piper_plus_phonemize() / piper_plus_phonemize_embedded_   │
│   english() / piper_plus_load_custom_dict()                 │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Gradle module 構成

```
android/
├── build.gradle.kts
├── settings.gradle.kts                  # include(":piper-plus", ":piper-plus-g2p") に拡張
├── gradle.properties
├── piper-plus/                          # 既存 (フル TTS AAR、本 Issue ではノータッチ)
└── piper-plus-g2p/                      # ★ 新規モジュール
    ├── build.gradle.kts                 # vanniktech plugin、Maven Central 公開設定
    ├── consumer-rules.pro
    ├── proguard-rules.pro
    └── src/main/
        ├── AndroidManifest.xml
        ├── cpp/
        │   ├── CMakeLists.txt
        │   └── piper_plus_g2p_jni.cpp   # G2P 専用 JNI bridge
        └── java/com/piperplus/g2p/
            ├── PiperPlusG2p.kt
            ├── PiperPlusG2pNative.kt
            ├── PiperPlusG2pException.kt
            ├── PhonemeResult.kt
            └── OpenJTalkDictionary.kt
```

### 5.3 Kotlin パブリック API (案)

```kotlin
package com.piperplus.g2p

class PiperPlusG2p private constructor(
    private val nativeHandle: Long
) : AutoCloseable {
    companion object {
        @JvmStatic
        @JvmOverloads
        fun create(
            context: Context,
            dictionary: OpenJTalkDictionary? = null,
        ): PiperPlusG2p { ... }
    }

    @Synchronized
    fun phonemize(text: String, language: String? = null): PhonemeResult { ... }

    @Synchronized
    fun availableLanguages(): List<String> { ... }

    @Synchronized
    fun loadCustomDict(path: String) { ... }

    @Synchronized
    override fun close() { ... }
}

data class PhonemeResult(
    val phonemes: String,
    val phonemeList: List<String>,
    val language: String,
)

class PiperPlusG2pException(message: String, cause: Throwable? = null) : Exception(message, cause)

class OpenJTalkDictionary private constructor(internal val path: String) {
    companion object {
        fun fromAssets(context: Context, assetPath: String): OpenJTalkDictionary { ... }
        fun fromPath(path: String): OpenJTalkDictionary { ... }
    }
}
```

### 5.4 JNI bridge 設計

```cpp
// piper_plus_g2p_jni.cpp
extern "C" {

JNIEXPORT jlong JNICALL
Java_com_piperplus_g2p_PiperPlusG2pNative_nativeCreate(
    JNIEnv* env, jclass, jstring dict_dir);

JNIEXPORT jobject JNICALL  // Returns PhonemeResult
Java_com_piperplus_g2p_PiperPlusG2pNative_nativePhonemize(
    JNIEnv* env, jclass, jlong handle, jstring text, jstring language);

JNIEXPORT jobjectArray JNICALL  // Returns String[]
Java_com_piperplus_g2p_PiperPlusG2pNative_nativeAvailableLanguages(
    JNIEnv* env, jclass, jlong handle);

JNIEXPORT void JNICALL
Java_com_piperplus_g2p_PiperPlusG2pNative_nativeLoadCustomDict(
    JNIEnv* env, jclass, jlong handle, jstring path);

JNIEXPORT void JNICALL
Java_com_piperplus_g2p_PiperPlusG2pNative_nativeDestroy(
    JNIEnv* env, jclass, jlong handle);

} // extern "C"
```

**重要規約**:
- BORROWED ポインタは即座に `NewStringUTF()` でコピー
- `JNIStringGuard` RAII で UTF-8 文字列リーク防止 (既存 `android/piper-plus/src/main/cpp/piper_plus_jni.cpp` パターン踏襲)
- C API エラー時は `PiperPlusG2pException` を `ThrowNew()`
- `JNI_OnLoad` で例外クラス global ref をキャッシュ

### 5.5 ABI 戦略

| ABI | 配布 | テスト | 理由 |
|-----|------|--------|------|
| `arm64-v8a` | ✓ | ✗ (実機のみ) | 64bit 必須 (Google Play 強制 2019-08〜)、本番ターゲット |
| `armeabi-v7a` | ✓ | ✗ | 古い端末対応 (Android 7+ シェア低下中だが minSdk 24 なら含める) |
| `x86_64` | ✓ | **✓ Gradle Managed Devices で自動テスト** | エミュレータ用、CI 完結テストの要 |

`-Wl,-z,max-page-size=16384` を全 `.so` に適用 (Android 15+ 16 KB page size 対応)。

---

## 6. 実装ロードマップ

詳細チケットは [docs/tickets/kotlin-g2p/README.md](../tickets/kotlin-g2p/README.md) を参照。

```
Phase 1  ┃ JNI bridge + C API gluing                      [TICKET-01]
Phase 2  ┃ Kotlin API + data class                        [TICKET-02]
Phase 3  ┃ Gradle module + Maven publish 設定             [TICKET-03]
Phase 4  ┃ 自動テスト整備 (L1-L5)                         [TICKET-04]
Phase 5  ┃ 辞書配布戦略 (assets / HF Hub DL)              [TICKET-05]
Phase 6  ┃ Maven Central 公開自動化 (GitHub Actions)      [TICKET-06]
Phase 7  ┃ ドキュメント / サンプルアプリ                  [TICKET-07]
```

**並列着手可能箇所**:
- Phase 1 (JNI) + Phase 2 (Kotlin API) は並列着手可 (シグネチャ合意後)
- Phase 4 (テスト) は Phase 1 完了後すぐ開始可能
- Phase 6 (Maven 公開) は Phase 3 完了後すぐ準備可能 (タグ push まで dry-run)

**クリティカルパス**: Phase 1 → Phase 2 → Phase 3 → Phase 4 (instrumented test) → Phase 6 (Maven 公開)

---

## 7. 自動化戦略 (本設計の肝)

ユーザー指針「**実機テストが多いのは嫌、CLI/CI で完結したい**」に対する具体的な担保策。

### 7.1 CI で完結する全テスト一覧

| # | テスト | コマンド | 実行環境 | 依存物 |
|---|--------|---------|---------|--------|
| T1 | Pure Kotlin unit | `./gradlew :piper-plus-g2p:test` | GitHub Actions Linux | なし |
| T2 | JVM JNI smoke (Linux .so) | `./gradlew :piper-plus-g2p:linuxTest` | GitHub Actions Linux | Linux libpiper_plus.so |
| T3 | Android instrumented (x86_64 emulator) | `./gradlew :piper-plus-g2p:pixel6api34DebugAndroidTest` | GitHub Actions Linux + KVM | x86_64 .so |
| T4 | Cross-runtime parity | `./gradlew :piper-plus-g2p:parityTest` | GitHub Actions Linux | `tests/fixtures/g2p/*.json` |
| T5 | ABI 整合性 / page size | `objdump -p libpiper_plus_g2p_jni.so \| grep LOAD` | GitHub Actions Linux | ビルド成果物 |
| T6 | Maven publish dry-run | `./gradlew publishAllPublicationsToMavenCentralRepository --dry-run` | GitHub Actions Linux | GPG キー、Sonatype credentials |

### 7.2 GitHub Actions ワークフロー設計

新規 `.github/workflows/kotlin-g2p-ci.yml`:

```yaml
on:
  pull_request:
    paths: ['android/piper-plus-g2p/**', 'src/cpp/**']
  push:
    tags: ['kotlin-g2p-v*']

jobs:
  unit-test:        # T1 + T2
    runs-on: ubuntu-24.04
    steps: ...

  instrumented-test:  # T3 (Gradle Managed Devices)
    runs-on: ubuntu-24.04  # KVM サポート
    steps:
      - run: ./gradlew :piper-plus-g2p:pixel6api34DebugAndroidTest

  parity-test:      # T4
    runs-on: ubuntu-24.04
    steps: ...

  abi-check:        # T5
    runs-on: ubuntu-24.04
    steps: ...

  publish:          # T6 (タグ push 時のみ)
    if: startsWith(github.ref, 'refs/tags/kotlin-g2p-v')
    needs: [unit-test, instrumented-test, parity-test, abi-check]
    runs-on: ubuntu-24.04
    steps: ...
```

### 7.3 Gradle Managed Devices 採用根拠

Android instrumented test は従来「実機 or 手動エミュレータ」が必要だったが、**Gradle Managed Devices** (AGP 7.3+) で完全自動化可能:

```kotlin
// build.gradle.kts
android {
    testOptions {
        managedDevices {
            devices {
                create<com.android.build.api.dsl.ManagedVirtualDevice>("pixel6api34") {
                    device = "Pixel 6"
                    apiLevel = 34
                    systemImageSource = "aosp"
                }
            }
        }
    }
}
```

GitHub Actions の Ubuntu runner は KVM をサポートするため、ヘッドレス emulator が高速に起動。実機接続なしで `androidTest` を完全自動実行可能。

### 7.4 Maven Central 公開の自動化

`vanniktech/gradle-maven-publish-plugin` で:
- GPG 署名: `signing.in-memory.key`, `signing.in-memory.key.password`
- Sonatype Central Portal: `mavenCentralUsername`, `mavenCentralPassword`
- 自動 release: `publishToMavenCentral` タスク後 `closeAndReleaseRepository`
- → タグ push → CI が自動公開、人手介入ゼロ

### 7.5 既存 CI 拡張点

| 既存 CI | 拡張内容 |
|---------|---------|
| `.github/workflows/android-build.yml` | Gradle Managed Devices テストジョブを追加 (現状は `.so` ビルドのみ) |
| `.github/workflows/release-shared-lib.yml` | Android `armeabi-v7a` / `x86_64` artifact も release 配布に追加 (現状 arm64-v8a のみ) |
| ZH-EN Loanword Sync Gate (`scripts/check_loanword_consistency.py`) | Kotlin AAR は C API 経由で既存 mirror を参照、新規 mirror 追加なし |

---

## 8. リスクと対策

| リスク | 影響 | 対策 |
|-------|------|-----|
| **Gradle Managed Devices の CI 不安定性** | instrumented test がフレーキー | 公式ドキュメント通りの retry 設定、KVM 利用必須、API level は 30+ で固定 |
| **Maven Central 公開時の credentials 漏洩** | 一度漏れると immutable で取り消し不可 | GitHub Actions secrets に格納、エコー禁止、PR では publish ジョブ skip |
| **16 KB page size 非対応** | Android 15+ で `.so` ロード失敗 | `target_link_options(piper_plus_g2p_jni PRIVATE -Wl,-z,max-page-size=16384)` を CMakeLists で必須化、`abi-check` ジョブで検証 |
| **JNI BORROWED ポインタの寿命誤認** | クラッシュ / use-after-free | 受け取り直後の `NewStringUTF()` を必須化、`JNIStringGuard` RAII で fallback、AddressSanitizer ビルドで検証 |
| **OpenJTalk 辞書配布のサイズ問題** | 50MB を AAR に同梱すると Maven Central 上限近接 | AAR には含めない。`OpenJTalkDictionary.fromAssets()` または `fromPath()` で消費者選択 |
| **既存 `android/piper-plus/` (TTS フル) との namespace 衝突** | Java パッケージ重複でビルドエラー | G2P 専用は `com.piperplus.g2p` namespace、TTS フルは `com.piperplus`、AAR としては別 artifactId |
| **8 言語 × 既存 C++ 実装の同期ドリフト** | ZH-EN loanword JSON 等が乖離 | Kotlin AAR は **新規 mirror を作らず** C API 経由で既存埋め込みデータを参照 (mirror 数は既存 7 のまま) |
| **vanniktech plugin の Sonatype Central Portal 対応が beta** | publish 失敗 | `JReleaser` を fallback として準備、ドキュメント化 |
| **Issue #388 のスペル「Kotolin」** | タイポ。意図確認が必要 | Kotlin として進める。本設計書冒頭で明示 |

---

## 9. 受け入れ基準 (PR マージ条件)

- [ ] `./gradlew :piper-plus-g2p:test` 全 PASS
- [ ] `./gradlew :piper-plus-g2p:pixel6api34DebugAndroidTest` 全 PASS (CI emulator)
- [ ] Cross-runtime parity test で Python と byte 一致 (8 言語 × 代表ケース)
- [ ] ABI 整合性 (`max-page-size=16384`) 検証 PASS
- [ ] `./gradlew publishToMavenCentralRepository --dry-run` 成功
- [ ] AAR サイズ < 5MB (jniLibs/ 含めて、辞書を除く)
- [ ] README.md (`android/piper-plus-g2p/README.md`) でクイックスタート提示
- [ ] サンプルアプリ (`examples/android-g2p-sample/`) で実動作確認
- [ ] CHANGELOG / メイン README 更新 (8 言語 G2P が「Python/Rust/Go/JS-WASM/C#/C++/Kotlin」の 7 ランタイム対応に)

---

## 10. 関連ドキュメント

- [docs/tickets/kotlin-g2p/README.md](../tickets/kotlin-g2p/README.md) — 実装チケット INDEX
- [docs/spec/ios-shared-lib.md](ios-shared-lib.md) — iOS shared lib 設計 (xcframework パターン参考)
- [docs/spec/zh-en-loanword-runtime-rollout.md](zh-en-loanword-runtime-rollout.md) — クロスランタイム同期パターン
- [docs/spec/pua-contract.toml](pua-contract.toml) — PUA codepoint 仕様
- [android/README.md](../../android/README.md) — 既存 TTS フル AAR 草案
- [src/cpp/piper_plus.h](../../src/cpp/piper_plus.h) — C API ヘッダ
- [.github/workflows/android-build.yml](../../.github/workflows/android-build.yml) — Android NDK ビルド CI
- [Issue #388](https://github.com/ayutaz/piper-plus/issues/388) — 親 Issue

---

## 11. 競合事例の参考リンク

| プロジェクト | 参考にした点 | URL |
|------------|-----------|-----|
| **sherpa-onnx** (k2-fsa) | AAR モジュール分離、JNI 構造、Kotlin API 設計、release.sh によるアーカイブ | https://github.com/k2-fsa/sherpa-onnx/tree/master/android/SherpaOnnxAar |
| **Vosk Android** | Maven Central 公式公開パターン (`com.alphacephei:vosk-android`) | https://github.com/alphacep/vosk-api/tree/master/android |
| **espeak-ng Android** | NDK CMake 設定、`SpeechSynthesis.java` の JNI bridge 設計 | https://github.com/espeak-ng/espeak-ng/tree/master/android |
| **vanniktech/gradle-maven-publish-plugin** | Maven Central 公開自動化のリファレンス | https://github.com/vanniktech/gradle-maven-publish-plugin |
| **Android Gradle Managed Devices** | CI で完結する instrumented test | https://developer.android.com/studio/test/gradle-managed-devices |

---

## 12. 改訂履歴

| 日付 | 版 | 変更内容 |
|------|----|---------|
| 2026-05-07 | v1 | 設計書初版。3 エージェント並列調査 (codebase / concept / competitor) の結果を統合。アプローチ A (JNI + AAR + Maven Central) を採択、自動化最優先で 7 phase ロードマップを定義。 |
