# Kotlin G2P ライブラリ — チケット INDEX

> **親 Issue**: [#388](https://github.com/ayutaz/piper-plus/issues/388) — 「Kotlin 向けの g2p ライブラリの提供」
> **設計書**: [docs/spec/kotlin-g2p-design.md](../../spec/kotlin-g2p-design.md)
> **作業ブランチ**: `feat/issue-388-kotlin-g2p`
> **判定基準**: 自動化可能性 (CLI/CI で完結) を最優先。実装工数は評価軸から除外。

このドキュメントは [Kotlin G2P 設計書](../../spec/kotlin-g2p-design.md) から派生したチケット群の進捗ハブです。

---

## 1. ゴール

`piper-plus-g2p` ファミリーに **Kotlin/Android 向けの公式 G2P ライブラリ** を追加。Android アプリ開発者が `implementation("io.github.ayutaz:piper-plus-g2p-android:X.Y.Z")` 1 行で導入可能にする。

**主要 KPI**: [設計書 §1](../../spec/kotlin-g2p-design.md#1-ゴール) を参照。

---

## 2. 推奨アプローチの結論

調査エージェント 3 体 (codebase / concept / competitor) の並列調査結果を踏まえ、**アプローチ A: JNI + AAR + Maven Central 公開** を採択。

**根拠サマリー**:
- 既存資産 (`libpiper_plus.so` の Android NDK ビルド CI、JNI テンプレート、C API の `piper_plus_phonemize()`) がほぼそのまま使える
- 自動化最優先の判定基準で全アプローチ中 ◎ × 4 (自動テスト / CI 配布 / 既存資産 / espeak-ng-free 維持)
- 競合 sherpa-onnx と同じパターンだが、Maven Central 公式公開 (Vosk スタイル) を採用することで品質を一段上げる

詳細比較: [設計書 §4](../../spec/kotlin-g2p-design.md#4-アプローチ比較)

---

## 3. 全体ロードマップ

```
Phase 1  ┃ JNI bridge + C API gluing                      [TICKET-01]
Phase 2  ┃ Kotlin API + data class                        [TICKET-02]
Phase 3  ┃ Gradle module + 公開設定                       [TICKET-03]
Phase 4  ┃ 自動テスト整備 (L1-L5)                         [TICKET-04]
Phase 5  ┃ 辞書配布戦略                                   [TICKET-05]
Phase 6  ┃ Maven Central 公開自動化                       [TICKET-06]
Phase 7  ┃ ドキュメント / サンプルアプリ                  [TICKET-07]
```

**並列着手可能**: Phase 1 (JNI) ↔ Phase 2 (Kotlin API) (シグネチャ合意後)、Phase 4 ↔ Phase 5 ↔ Phase 6 準備

**クリティカルパス**: Phase 1 → Phase 2 → Phase 3 → Phase 4 (instrumented test) → Phase 6 (Maven 公開)

---

## 4. チケット概要

各チケットの詳細仕様は本 INDEX 内に直接記載 (zh-en-loanword と異なり規模が小さいため個別ファイル分割せず)。

### TICKET-01: JNI bridge + C API gluing

**目的**: 既存 C API (`piper_plus_phonemize` 等) を Kotlin から呼べる JNI 層を追加。

**変更箇所**:
- `android/piper-plus-g2p/src/main/cpp/piper_plus_g2p_jni.cpp` — 新規
- `android/piper-plus-g2p/src/main/cpp/CMakeLists.txt` — 新規
- 既存 `libpiper_plus.so` をリンク (現状の `cmake/PiperPlusShared.cmake` 参照)

**API**:
- `nativeCreate(dictDir: String?): Long`
- `nativePhonemize(handle: Long, text: String, language: String?): PhonemeResult`
- `nativeAvailableLanguages(handle: Long): Array<String>`
- `nativeLoadCustomDict(handle: Long, path: String)`
- `nativeDestroy(handle: Long)`

**重要規約**:
- BORROWED ポインタは即座に `NewStringUTF()` でコピー
- `JNIStringGuard` RAII で UTF-8 文字列リーク防止 (既存 `android/piper-plus/src/main/cpp/piper_plus_jni.cpp` パターン踏襲)
- C API エラー時は `PiperPlusG2pException` を `ThrowNew()`
- `JNI_OnLoad` で例外クラス global ref をキャッシュ

**自動テスト**: L2 (JVM JNI smoke on Linux .so) で関数シグネチャ整合性、メモリリーク、ASan 検証

**受け入れ基準**:
- [ ] CMake が arm64-v8a / armeabi-v7a / x86_64 すべてでビルド成功
- [ ] `nm -D libpiper_plus_g2p_jni.so` で必要 symbol 露出確認
- [ ] AddressSanitizer ビルドで実行時エラーなし

---

### TICKET-02: Kotlin パブリック API + data class

**目的**: ユーザーが触る Kotlin API を提供。`AutoCloseable` / `synchronized` / `data class` で Kotlin idiomatic に。

**変更箇所**:
- `android/piper-plus-g2p/src/main/java/com/piperplus/g2p/PiperPlusG2p.kt` — 新規
- `android/piper-plus-g2p/src/main/java/com/piperplus/g2p/PiperPlusG2pNative.kt` — 新規
- `android/piper-plus-g2p/src/main/java/com/piperplus/g2p/PiperPlusG2pException.kt` — 新規
- `android/piper-plus-g2p/src/main/java/com/piperplus/g2p/PhonemeResult.kt` — 新規
- `android/piper-plus-g2p/src/main/java/com/piperplus/g2p/OpenJTalkDictionary.kt` — 新規

**API スケッチ** ([設計書 §5.3](../../spec/kotlin-g2p-design.md#53-kotlin-パブリック-api-案) 参照):

```kotlin
class PiperPlusG2p : AutoCloseable {
    companion object {
        fun create(context: Context, dictionary: OpenJTalkDictionary? = null): PiperPlusG2p
    }
    @Synchronized fun phonemize(text: String, language: String? = null): PhonemeResult
    @Synchronized fun availableLanguages(): List<String>
    @Synchronized fun loadCustomDict(path: String)
    @Synchronized override fun close()
}

data class PhonemeResult(
    val phonemes: String,
    val phonemeList: List<String>,
    val language: String,
)
```

**自動テスト**: L1 (Pure Kotlin unit test) — data class、入力バリデーション、エラーケース

**受け入れ基準**:
- [ ] `@Synchronized` が全 native 呼び出しに適用
- [ ] `AutoCloseable` 実装で `use { }` ブロック対応
- [ ] Kotlin 2.1.0 + JDK 17 で警告なしビルド
- [ ] dokka でドキュメント生成成功

---

### TICKET-03: Gradle module + 公開設定

**目的**: `android/piper-plus-g2p/` を独立 Gradle module として構成、Maven Central 公開設定を追加。

**変更箇所**:
- `android/settings.gradle.kts` — `include(":piper-plus-g2p")` 追加
- `android/piper-plus-g2p/build.gradle.kts` — 新規 (`vanniktech/gradle-maven-publish-plugin` 採用)
- `android/piper-plus-g2p/consumer-rules.pro` — 新規
- `android/piper-plus-g2p/proguard-rules.pro` — 新規
- `android/piper-plus-g2p/src/main/AndroidManifest.xml` — 新規

**重要設定**:

```kotlin
plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
    id("com.vanniktech.maven.publish") version "0.30.0"
}

android {
    namespace = "com.piperplus.g2p"
    compileSdk = 35
    defaultConfig {
        minSdk = 24
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
        externalNativeBuild {
            cmake {
                cppFlags("-std=c++17")
                arguments(
                    "-DANDROID_STL=c++_shared",
                    "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384"
                )
            }
        }
    }
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

mavenPublishing {
    publishToMavenCentral(SonatypeHost.CENTRAL_PORTAL)
    signAllPublications()
    coordinates("io.github.ayutaz", "piper-plus-g2p-android", project.version.toString())
    pom {
        name = "piper-plus-g2p (Android)"
        description = "Multi-lingual G2P (text-to-phoneme) library for Android"
        url = "https://github.com/ayutaz/piper-plus"
        licenses { license { name = "MIT"; url = "https://opensource.org/licenses/MIT" } }
        // ...
    }
}
```

**ABI 戦略**:
- 配布: `arm64-v8a`, `armeabi-v7a`, `x86_64` (3 ABI)
- テスト用: `x86_64` (Gradle Managed Devices で必須)
- 16 KB page size 対応: 全 ABI で `max-page-size=16384`

**自動テスト**: ビルドのみ。テストは TICKET-04。

**受け入れ基準**:
- [ ] `./gradlew :piper-plus-g2p:assembleRelease` で AAR 生成
- [ ] AAR 構造に `jni/{arm64-v8a, armeabi-v7a, x86_64}/lib*.so` が含まれる
- [ ] AAR サイズ < 5MB (辞書を除く)
- [ ] `./gradlew :piper-plus-g2p:publishToMavenLocal` でローカル publish 成功
- [ ] `objdump -p libpiper_plus_g2p_jni.so | grep LOAD` で `align 2**14` (16 KB)

---

### TICKET-04: 自動テスト整備 (L1-L5)

**目的**: ユーザー指針「実機テスト最小化、CLI/CI で完結」を実現する自動テスト群を整備。

**変更箇所**:
- `android/piper-plus-g2p/src/test/java/...` — JVM unit test
- `android/piper-plus-g2p/src/androidTest/java/...` — instrumented test
- `tests/fixtures/g2p/kotlin-parity/*.json` — クロスランタイム parity fixture (既存共有 fixture を参照)
- `.github/workflows/kotlin-g2p-ci.yml` — 新規

**テスト 5 層** ([設計書 §7.1](../../spec/kotlin-g2p-design.md#71-ci-で完結する全テスト一覧) 参照):

| 層 | コマンド | 実行環境 |
|---|---------|---------|
| L1: Pure Kotlin unit | `./gradlew :piper-plus-g2p:test` | GitHub Actions Linux |
| L2: JVM JNI smoke | `./gradlew :piper-plus-g2p:linuxTest` (Linux .so をリンク) | GitHub Actions Linux |
| L3: Android instrumented | `./gradlew :piper-plus-g2p:pixel6api34DebugAndroidTest` | GitHub Actions Linux + KVM |
| L4: Cross-runtime parity | カスタム Gradle task で fixture 比較 | GitHub Actions Linux |
| L5: ABI / page size | `objdump -p` / `nm -D` 検証 script | GitHub Actions Linux |

**Cross-runtime parity 仕様**:
- 8 言語 × 各 5-10 ケース (= ~50-80 ケース)
- Python ランタイムを gold standard、Kotlin 出力と byte 一致を要求
- ZH-EN loanword、PUA codepoint、prosody features (A1/A2/A3) を含む
- 既存 `tests/fixtures/g2p/*.json` を再利用

**Gradle Managed Devices 設定** (TICKET-03 で完了済を利用):
- Pixel 6, API 34, AOSP system image
- KVM 必須: GitHub Actions `ubuntu-24.04` runner で利用可能

**受け入れ基準**:
- [ ] 5 層すべて GitHub Actions で全 PASS
- [ ] L4 で 8 言語 × 50+ケース byte 一致
- [ ] L3 が emulator のみで完走 (実機接続なし)
- [ ] CI 全体の wall-clock time < 30 分
- [ ] フレーキー率 < 1% (10 回連続 PASS で merge 許可)

---

### TICKET-05: 辞書配布戦略

**目的**: OpenJTalk 辞書 (~50MB) を AAR に含めず、消費者がオプションで利用できる仕組みを提供。

**変更箇所**:
- `android/piper-plus-g2p/src/main/java/com/piperplus/g2p/OpenJTalkDictionary.kt` — TICKET-02 で雛形作成、ここで実装完成
- `android/piper-plus-g2p/src/main/java/com/piperplus/g2p/DictionaryDownloader.kt` — 新規 (HF Hub からの DL)
- `docs/guides/android-g2p-dictionary.md` — 新規 (ユーザー向け手順)

**3 つの配布パターン**:

1. **App assets バンドル** — 消費者が辞書を APK の `assets/open_jtalk_dic/` に配置 (`OpenJTalkDictionary.fromAssets`)
2. **Play Asset Delivery (install-time)** — 50MB なら install-time pack 推奨。消費者が自前で `AssetPackManager` を使う
3. **Runtime DL** — 初回起動時に Hugging Face Hub から DL (`DictionaryDownloader.downloadFromHuggingFace`)。F-Droid フレンドリ (Anti-Feature: "Non-Free Network Services" 必要)

**API 設計**:

```kotlin
class OpenJTalkDictionary {
    companion object {
        fun fromAssets(context: Context, assetPath: String = "open_jtalk_dic"): OpenJTalkDictionary
        fun fromPath(absolutePath: String): OpenJTalkDictionary
        suspend fun downloadFromHuggingFace(
            context: Context,
            repo: String = "ayousanz/piper-plus-base",
            destDir: File = context.filesDir.resolve("open_jtalk_dic"),
            onProgress: (bytesRead: Long, total: Long) -> Unit = { _, _ -> },
        ): OpenJTalkDictionary
    }
}
```

**自動テスト**: L3 (instrumented) で各パターンの動作確認。HF Hub DL は `WireMock` でモック化 (CI で外部依存を避ける)。

**受け入れ基準**:
- [ ] 3 パターンすべての instrumented test PASS
- [ ] `assets/open_jtalk_dic/` 自動展開ロジックが既存 TTS フル AAR (`android/piper-plus/src/main/java/com/piperplus/PiperPlus.kt:81`) と整合
- [ ] HF Hub DL のチェックサム検証 (`SHA-256`) 実装
- [ ] ドキュメントで 3 パターン使い分けを明示

---

### TICKET-06: Maven Central 公開自動化

**目的**: タグ push → CI が自動で Maven Central 公開、人手介入ゼロ。

**変更箇所**:
- `.github/workflows/release-kotlin-g2p.yml` — 新規 (もしくは既存 `release-shared-lib.yml` に統合)
- GitHub Actions secrets 登録 (手順を docs に明記)
- `android/piper-plus-g2p/build.gradle.kts` の publishing 設定完成

**Workflow 概要**:

```yaml
on:
  push:
    tags: ['kotlin-g2p-v*']

jobs:
  publish:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v6
        with: { submodules: true }
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: 17 }
      - name: Build native libs
        run: |  # 3 ABI クロスコンパイル
          ./scripts/build-android-jnilibs.sh
      - name: Publish to Maven Central
        env:
          ORG_GRADLE_PROJECT_mavenCentralUsername: ${{ secrets.MAVEN_CENTRAL_USERNAME }}
          ORG_GRADLE_PROJECT_mavenCentralPassword: ${{ secrets.MAVEN_CENTRAL_PASSWORD }}
          ORG_GRADLE_PROJECT_signingInMemoryKey: ${{ secrets.SIGNING_IN_MEMORY_KEY }}
          ORG_GRADLE_PROJECT_signingInMemoryKeyPassword: ${{ secrets.SIGNING_IN_MEMORY_KEY_PASSWORD }}
        run: ./gradlew :piper-plus-g2p:publishAndReleaseToMavenCentral
```

**前提準備**:
1. Sonatype Central Portal 登録 (`io.github.ayutaz` namespace)
2. GitHub Actions secrets: `MAVEN_CENTRAL_USERNAME`, `MAVEN_CENTRAL_PASSWORD`, `SIGNING_IN_MEMORY_KEY`, `SIGNING_IN_MEMORY_KEY_PASSWORD`
3. PR ジョブでは `--dry-run` で検証 (実 publish せず)

**バージョニング規則**:
- `kotlin-g2p-v1.0.0` のような git tag (既存 `csharp-v*`, `wasm-g2p-v*` パターン踏襲)
- SemVer 厳守、Maven Central は immutable

**自動テスト**: T6 (publish dry-run) を PR 時に実行

**受け入れ基準**:
- [ ] PR で `--dry-run` 成功
- [ ] タグ push → 5 分以内に Maven Central で検索可能
- [ ] GPG 署名検証 PASS (`./gradlew :piper-plus-g2p:checkMavenCentralPublicationSignature`)
- [ ] バージョン乖離 (POM vs git tag) を検知する CI gate

---

### TICKET-07: ドキュメント / サンプルアプリ

**目的**: ユーザーが迷わず導入できる状態にする。CLAUDE.md / README / CHANGELOG 同期。

**変更箇所**:
- `android/piper-plus-g2p/README.md` — 新規 (クイックスタート、API リファレンス、辞書配布 3 パターン)
- `examples/android-g2p-sample/` — 新規 (Compose で 8 言語 phonemize デモ)
- `CLAUDE.md` — Kotlin G2P を「ランタイム別パッケージ」表に追加 (Maven Central 行)
- `README.md` (ルート) — Kotlin/Android 行を G2P 単体パッケージ表に追加
- `CHANGELOG.md` — `## [Unreleased]` に追加
- `docs/guides/android-g2p-integration.md` — 新規 (本文)

**サンプルアプリ仕様**:
- Compose UI、minSdk 24
- 8 言語タブ切り替え
- TextField で文字列入力 → phonemize → 結果表示
- カスタム辞書ロードオプション
- HF Hub からの初回 DL デモ

**ドキュメント整合性チェック**:
- ルート README の「主要追加機能 (全ランタイム共通)」表に Kotlin 追加
- CLAUDE.md の「ランタイム別パッケージ」表で全 7 ランタイム揃う

**自動テスト**: 既存 docs link checker、サンプルアプリビルド (CI gate)

**受け入れ基準**:
- [ ] `android/piper-plus-g2p/README.md` で 3 ステップで動作開始できる
- [ ] サンプルアプリが CI で `assembleDebug` 成功
- [ ] CLAUDE.md / README / CHANGELOG が一貫
- [ ] dokka 生成 javadoc が Maven Central に同梱

---

## 5. 進捗ダッシュボード

```
[Phase 0] 設計書 + INDEX     ████████████████████  100%  ✅ Done (3 エージェント並列調査結果統合)
[Phase 1] JNI bridge         ░░░░░░░░░░░░░░░░░░░░    0%  📋 Ready
[Phase 2] Kotlin API         ░░░░░░░░░░░░░░░░░░░░    0%  📋 Ready
[Phase 3] Gradle module      ░░░░░░░░░░░░░░░░░░░░    0%  📋 Ready
[Phase 4] 自動テスト         ░░░░░░░░░░░░░░░░░░░░    0%  📋 Ready
[Phase 5] 辞書配布           ░░░░░░░░░░░░░░░░░░░░    0%  📋 Ready
[Phase 6] Maven 公開         ░░░░░░░░░░░░░░░░░░░░    0%  📋 Ready
[Phase 7] Docs / サンプル    ░░░░░░░░░░░░░░░░░░░░    0%  📋 Ready
```

**ステータス凡例**: 📝 Draft / 📋 Ready / 🚧 In Progress / 👀 Review / ✅ Done / ⏸ Blocked

---

## 6. 依存グラフ

```
              ┌──────────────────────────────────────┐
              │  Phase 0: 設計書 + INDEX (本書)      │
              └──────────────┬───────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
          TICKET-01       TICKET-02      TICKET-03
          (JNI)           (Kotlin API)   (Gradle)
                                              │
                             ┌────────────────┼─────────────┐
                             ▼                ▼             ▼
                         TICKET-04       TICKET-05      TICKET-06
                         (Tests)         (Dict)         (Maven Pub)
                             │                │             │
                             └────────────────┼─────────────┘
                                              ▼
                                         TICKET-07
                                         (Docs)
```

**並列着手可能**:
- TICKET-01 / TICKET-02 はシグネチャ合意後に並列着手可
- TICKET-04 / TICKET-05 / TICKET-06 は TICKET-03 完了後に並列着手可

---

## 7. 自動化チェックリスト (本設計の核)

ユーザー指針「実機テスト最小化、CLI/CI で完結」に対する具体的な担保:

| 項目 | 自動化手段 | 実機要否 |
|------|----------|---------|
| Pure Kotlin unit test | `./gradlew test` | 不要 |
| JNI smoke test | `./gradlew linuxTest` (Linux .so) | 不要 |
| Android instrumented test | Gradle Managed Devices (Pixel 6 API 34 emulator) | **不要 (KVM emulator)** |
| 8 言語 cross-runtime parity | `./gradlew parityTest` | 不要 |
| ABI / 16 KB page size | `objdump -p` script | 不要 |
| Maven Central publish | vanniktech plugin + GitHub Actions | 不要 (タグ push のみ) |
| Sonatype credentials 検証 | publish dry-run on PR | 不要 |
| サンプルアプリ動作 | `./gradlew assembleDebug` + instrumented test | 不要 |

**実機が必要な場面**: 製品リリース前の最終手動検証のみ (オプション)。CI 緑なら基本マージ可能。

---

## 8. リスクと対策

[設計書 §8](../../spec/kotlin-g2p-design.md#8-リスクと対策) を参照。主要リスク:

| リスク | 対策 |
|-------|-----|
| Gradle Managed Devices CI 不安定性 | retry 設定、KVM 必須、API 30+ 固定 |
| Maven Central credentials 漏洩 | Secrets 格納、PR では publish skip |
| 16 KB page size 非対応 | `max-page-size=16384` 必須化 + `abi-check` |
| JNI BORROWED ポインタ寿命誤認 | `NewStringUTF()` 即コピー、ASan ビルド |
| OpenJTalk 辞書 50MB 同梱 | AAR 非同梱、3 配布パターン提供 |
| 既存 `android/piper-plus/` namespace 衝突 | `com.piperplus.g2p` で分離 |
| 8 言語 cross-runtime ドリフト | mirror 増やさず C API 経由で既存埋め込みデータ参照 |

---

## 9. 受け入れ基準 (PR マージ条件)

[設計書 §9](../../spec/kotlin-g2p-design.md#9-受け入れ基準-pr-マージ条件) を参照。主要:

- [ ] 全 7 チケット完了
- [ ] 5 層全自動テスト PASS (CI 完結)
- [ ] AAR < 5MB (辞書除く)
- [ ] Maven Central 公開成功 (dry-run 含む)
- [ ] サンプルアプリ動作
- [ ] ドキュメント一貫性

---

## 10. 関連ドキュメント

- [Kotlin G2P 設計書](../../spec/kotlin-g2p-design.md) — 本書の親
- [iOS shared lib 仕様](../../spec/ios-shared-lib.md) — Apple 側の参考設計
- [ZH-EN loanword runtime rollout](../../spec/zh-en-loanword-runtime-rollout.md) — クロスランタイム同期パターン
- [既存 Android TTS フル AAR](../../../android/README.md)
- [Issue #388](https://github.com/ayutaz/piper-plus/issues/388)

---

## 11. 改訂履歴

| 日付 | 版 | 変更内容 |
|------|----|---------|
| 2026-05-07 | v1 | INDEX 初版作成。3 エージェント並列調査の結果から JNI + AAR + Maven Central 案を採択、7 チケット (Phase 1-7) のロードマップを定義。ユーザー指針「自動化最優先 / 実機テスト最小化」に沿って Gradle Managed Devices + vanniktech plugin で完全 CI 自動化を志向。 |
