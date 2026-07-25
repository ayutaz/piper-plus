# piper-plus Android TTS エンジン 設計書

> **ステータス**: 設計 (未実装)
> **ブランチ**: `feat/android-tts-engine`
> **作成日**: 2026-07-25

Android のシステム TTS エンジンとして piper-plus を提供し、任意のアプリ (読み上げアプリ、
アクセシビリティ機能、TalkBack など) からオフライン日本語音声合成を利用可能にする。

---

## 1. ゴール

| # | 目標 | 達成基準 |
|---|------|---------|
| G-1 | Android システム TTS として piper-plus を選択できる | 設定 → 言語と入力 → テキスト読み上げ で「piper-plus」が選択肢に出る |
| G-2 | 6 言語 (ja/en/zh/es/fr/pt) を喋る | `Locale` から `language_id` を解決し、対応言語で合成される |
| G-3 | 完全オフライン動作 | 初回のモデル取得後、ネットワーク不要 |
| G-4 | F-Droid + GitHub Releases で配布 | tag push で両方に配信される |

**非目標 (YAGNI):**

- カスタムモデルのサイドロード — 初版では扱わない。標準モデルの選択のみ
- Voice Cloning (speaker embedding) — CLI / SDK 経路で提供済み
- pitch 制御 — VITS に該当パラメータがない (§8 参照)

---

## 2. 背景

### 2.1 きっかけ

ユーザーが Android のオフライン日本語 TTS を探し、SherpaTTS (F-Droid) で
piper-plus つくよみちゃんモデルを発見したものの、sherpa-onnx で読み込めず断念した
事例が報告された ([note 記事](https://note.com/huge_lynx6067/n/n9fccdbc081ab))。

### 2.2 sherpa-onnx 経路の調査結果

同記事のケースを再現し、piper-plus モデルを sherpa-onnx で動かす検証を行った。
結論として **推論自体は成立するが、記事のユースケースは解決しない**。

| 層 | 内容 | 検証結果 |
|---|------|---------|
| ONNX I/F | piper-plus は `lid` / `prosody_features` / `speaker_embedding` / `speaker_embedding_mask` を持つ (計 7 入力)。sherpa-onnx は `input` / `input_lengths` / `scales` / `sid` / `langid` しか渡さない | graph surgery による 3 入力化が **bit-identical** (max abs diff = 0.0) で成立 |
| metadata | piper-plus の ONNX は `metadata_props` が空。sherpa-onnx は `model_type` / `sample_rate` / `add_blank` 等を ONNX 内部から読む | `phoneme_id_map` からの `tokens.txt` 生成 + metadata 埋め込みで解決 |
| G2P | sherpa-onnx に日本語 frontend が存在しない。espeak-ng 経路は piper-plus の OpenJTalk 音素セットと非互換 | **未解決**。sherpa-onnx 側に日本語 G2P を追加しない限り、生テキストからは合成できない |

加えて sherpa-onnx 側の制約を 2 点実測した (いずれも piper-plus とは独立した上流の問題):

- `offline-tts-character-frontend.cc` が UTF-8 バイト列に `std::tolower` を**バイト単位**で適用しており、
  非 ASCII 音素 (PUA / IPA) が破壊される。実測: PUA 8 文字 → ほぼ無音 (1484 samples)、ASCII 8 文字 → 8704 samples
- `OfflineTtsConfig.silence_scale` が `GenerationConfig` に伝播せず、常に既定の 0.2 が使われる

これらの理由から、**sherpa-onnx 経由ではなく自前の TTS エンジンを提供する**方針を採る。
sherpa-onnx への上流貢献は本設計のスコープ外とし、別途 Issue として扱う。

---

## 3. 既存資産の整理

本設計が新規に書く量は少ない。既存資産の再利用が前提となる。

| 資産 | 場所 | 状態 | 本設計での役割 |
|------|------|------|--------------|
| C++ 推論 + G2P | `libpiper_plus.so` | 3 ABI ビルド済 (CI) / **未配布** | 推論・音素化の実体 |
| C API | `src/cpp/piper_plus.h` | 完成 | `PiperPlusSynthOptions` に `language_id` / `length_scale` / `noise_scale` / `sentence_silence_sec` を保持 |
| Android AAR | `android/piper-plus/` | 646 LOC、`create` / `synthesize` / `synthesizeStream` 実装済 | エンジンの推論層。**合成オプションの露出が不足** (§6.2) |
| 辞書ダウンローダ | `android/piper-plus-g2p/.../DictionaryDownloader.kt` | HF host allowlist 付き実装済 | OpenJTalk 辞書取得に流用 |
| 3 ABI ビルド CI | `.github/workflows/release-shared-lib.yml` | `build-android` job あり (arm64-v8a / armeabi-v7a / x86_64)、16 KB page 対応済 | `.so` の供給元。**リリース配布の追加が必要** |

配布可能な推論用モデルは `piper-core` の組込みレジストリ
(`src/rust/piper-core/src/model_download.rs:builtin_registry`) に定義された 2 つ
([pretrained-models.md](../guides/development/pretrained-models.md))。

| モデル | レジストリ名 | HF リポジトリ / ファイル | サイズ | 言語 |
|-------|------------|----------------------|-------|------|
| **CSS10 JA 6lang (既定)** | `css10-6lang` | `ayousanz/piper-plus-css10-ja-6lang` / `css10-ja-6lang-fp16.onnx` | 39,652,717 B | 6 言語すべて |
| つくよみちゃん 6lang | `tsukuyomi-6lang-v2` | `ayousanz/piper-plus-tsukuyomi-chan` / `tsukuyomi-chan-6lang-fp16.onnx` | 39,652,717 B | 6 言語すべて |

**既定モデルは `css10-6lang`** とする。キャラクター固有の利用規約を持たないため、
初回起動時の同意フローを省け、導線が短くなる。端末上のディレクトリ名にもこの
レジストリ名をそのまま使い、他ランタイムとモデル ID を揃える。

> **注**: `pretrained-models.md` はつくよみちゃんを「ONNX size 75 MB」と記載しているが、
> HF 配布ファイル `tsukuyomi-chan-6lang-fp16.onnx` の実測は 38 MB (FP16) だった。
> 本設計はレジストリの `size_bytes` を採る。カタログ側の記述は FP32 時代の値が
> 残っている可能性があり、別途確認する。

**重要**: 6lang モデルは 1 つで 6 言語を喋る。言語切替は `language_id` の変更であり、
モデルの入れ替えではない。したがって「モデル選択」= 話者選択、「言語選択」= `language_id` 解決となる。

---

## 4. アプローチ比較

| 案 | 構成 | 判定 |
|---|------|------|
| **A (採択)** | 既存 AAR (`libpiper_plus.so` JNI) に依存する TTS エンジンアプリを `android/` 配下に追加 | Kotlin 実装は Service + UI のみ。推論も G2P も実績ある C++ をそのまま使う |
| B | ONNX Runtime Android AAR + `piper-plus-g2p-android` で Kotlin から再構成 | native の配布フローは不要になるが、scales 決定・文分割・短テキスト戦略を Kotlin で再実装することになり、`docs/spec/*.toml` の契約を 2 箇所で守る必要が生じる |
| C | アプリを別リポジトリへ独立 | リリースサイクルは分離できるが AAR 公開フローと CI 同期のコストが増える。sherpa-onnx も `SherpaOnnxAar` / `SherpaOnnxTtsEngine` を同一リポジトリ内で分離しており、モノレポ内分離が定石 |

**A を採択**。実装の二重化を避けられることが決め手。

---

## 5. アーキテクチャ

```text
┌─────────────────────────────────────────────┐
│ Android システム (TalkBack / 読み上げアプリ)  │
└───────────────────┬─────────────────────────┘
                    │ TextToSpeech API
┌───────────────────▼─────────────────────────┐
│ android/piper-plus-tts-engine  (新規)        │
│                                             │
│  PiperPlusTtsService : TextToSpeechService  │
│    ├─ LocaleResolver     Locale → language_id│
│    ├─ VoiceRegistry      モデル ↔ Voice      │
│    └─ EngineHolder       PiperPlus の生存管理 │
│                                             │
│  ModelManager            DL / 検証 / 削除     │
│  SettingsActivity        モデル選択・DL UI    │
└───────────────────┬─────────────────────────┘
                    │ project dependency
┌───────────────────▼─────────────────────────┐
│ android/piper-plus  (既存 / §6.2 で拡張)      │
│    PiperPlus.kt ─ JNI ─ libpiper_plus.so    │
└─────────────────────────────────────────────┘
```

### 5.1 モジュール構成

```text
android/
  settings.gradle.kts          ← :piper-plus-tts-engine を追加
  piper-plus/                  (既存 AAR)
  piper-plus-g2p/              (既存 G2P AAR)
  piper-plus-tts-engine/       ← 新規 (application module)
    build.gradle.kts
    src/main/
      AndroidManifest.xml      TextToSpeechService の intent-filter
      java/com/piperplus/tts/
        PiperPlusTtsService.kt
        LocaleResolver.kt
        VoiceRegistry.kt
        EngineHolder.kt
        model/
          ModelManager.kt
          ModelCatalog.kt
          ModelDownloader.kt
        ui/
          SettingsActivity.kt
      res/xml/tts_engine.xml   エンジンメタデータ
```

---

## 6. コンポーネント設計

### 6.1 責務分割

| コンポーネント | 責務 | 依存 |
|--------------|------|------|
| `PiperPlusTtsService` | Android TTS のライフサイクル実装。`SynthesisRequest` をほどいて `SynthesisSession` に渡すだけのアダプタ | すべて |
| `SynthesisSession` | 1 発話分の合成。可用性判定 → `SynthOptions` 組み立て → ストリーム収集 → `callback` への通知。停止フラグを所有。サンプルレートはモデルの実値を申告する (固定値だと 22050Hz 以外のモデルで全発話のピッチがずれる) | `EngineHolder`, `PcmEmitter` |
| `PcmEmitter` | `ShortArray` を little-endian のバイト列にして `maxBufferSize` 以下に分割 | なし (Android 型は `SynthesisCallback` のみ) |
| `LocaleResolver` | `(lang, country, variant)` → `language_id` / 可用性判定。純関数、副作用なし | なし |
| `VoiceRegistry` | インストール済みモデルと `Voice` オブジェクトの対応付け | `ModelManager` |
| `EngineHolder` | `PiperPlus` インスタンスの生成・キャッシュ・破棄。スレッド安全 | `android/piper-plus` |
| `ModelCatalog` | 配布モデルの静的定義 (HF repo / ファイル名 / SHA256 / サイズ) | なし |
| `ModelDownloader` | HF からの取得、進捗通知、チェックサム検証 | `ModelCatalog` |
| `ModelManager` | インストール状態の管理、パス解決、削除 | `ModelDownloader` |
| `SettingsActivity` | モデル一覧・DL 操作・削除 UI | `ModelManager` |

各コンポーネントは単体でテスト可能な粒度に保つ。特に `LocaleResolver` は
Android 依存を持たない純粋な Kotlin にして JVM ユニットテストで網羅する。

`SynthesisSession` と `PcmEmitter` が `PiperPlusTtsService` から分かれているのは、
テスト可能性のための意図的な分割である。理由は
[§10.1](#101-テスト可能性のための設計上の制約) を参照。

### 6.2 AAR の拡張 (前提作業)

現状の JNI 境界は `nativeSynthesize(handle, text, speakerId)` のみで、
C API が持つ合成オプションを露出していない。Android TTS はシステム設定の
`speechRate` を渡してくるため、**`length_scale` の露出が必須**。

```kotlin
// android/piper-plus/src/main/java/com/piperplus/PiperPlus.kt
data class SynthOptions(
    val speakerId: Int = 0,
    val languageId: Int = -1,       // -1 = auto-detect (C API 既定)
    val lengthScale: Float = 1.0f,
    val noiseScale: Float = 0.4f,
    val noiseW: Float = 0.5f,
    val sentenceSilenceSec: Float = 0.2f,
)

fun synthesize(text: String, options: SynthOptions): ShortArray
fun synthesizeStream(text: String, options: SynthOptions): Flow<ShortArray>
```

⚠️ **`options` に既定値を付けないこと。** 既存の `synthesize(text, speakerId: Int = 0)`
と併存するため、両方に既定値があると `synthesize("text")` がどちらにも解決でき
コンパイルエラーになる。

既存の `synthesize(text, speakerId)` はそのまま残す。**`@Deprecated` は付けない** —
単一話者モデルを既定設定で鳴らす用途では今も最短の書き方であり、非推奨にすると
既存利用者に移行の実益がない警告を出すことになる。

呼び出し側は named argument で書く。`SynthOptions` の末尾 4 フィールドはすべて
`Float` で、位置引数のままだと並べ替えても型検査を通ってしまう
(`lengthScale` と `noiseScale` が入れ替わると常時 2.5 倍速になる)。

JNI 側は `PiperPlusSynthOptions` 構造体を組み立てて `piper_plus_synthesize` に渡す。
`_reserved[5]` はゼロ埋めを厳守する (ヘッダの規約)。この Kotlin ↔ C++ の対応は
`PiperPlusNativeBridgeTest` がソース照合で固定している。

### 6.3 TextToSpeechService

```kotlin
class PiperPlusTtsService : TextToSpeechService() {
    override fun onIsLanguageAvailable(lang: String, country: String, variant: String): Int
    override fun onLoadLanguage(lang: String, country: String, variant: String): Int
    override fun onGetLanguage(): Array<String>
    override fun onSynthesizeText(request: SynthesisRequest, callback: SynthesisCallback)
    override fun onStop()
}
```

`onSynthesizeText` の流れ:

1. `LocaleResolver` で `request.language` (ISO-3) → `language_id` を解決
2. `request.speechRate` (100 = 等速) → `lengthScale = 100f / speechRate`
3. `callback.start(sampleRate, AudioFormat.ENCODING_PCM_16BIT, 1)`
4. `EngineHolder.engine.synthesizeStream(text, options)` を collect し、
   `callback.getMaxBufferSize()` 以下に分割して `callback.audioAvailable()`
5. `callback.done()`

ストリーミング API を使う理由は、長文でも最初の音が早く鳴り、`onStop()` に即応
できるため。`onStop()` は collect 中のフラグを落として打ち切る。

### 6.4 言語解決 (`LocaleResolver`)

`language_id_map` は全 6lang モデル共通で `{ja:0, en:1, zh:2, es:3, fr:4, pt:5}`。

| ISO-3 | ISO-1 | language_id | 備考 |
|-------|-------|-------------|------|
| `jpn` | ja | 0 | |
| `eng` | en | 1 | |
| `zho` / `cmn` | zh | 2 | Android は `zho` を返す。`cmn` も受理 |
| `spa` | es | 3 | |
| `fra` | fr | 4 | |
| `por` | pt | 5 | BR/EU の区別は初版では行わない |

戻り値の規約:

- モデル導入済 + 対応言語 → `LANG_AVAILABLE`
- 対応言語だがモデル未導入 → `LANG_MISSING_DATA`
- 非対応言語 → `LANG_NOT_SUPPORTED`

`LANG_COUNTRY_AVAILABLE` は返さない。6lang モデルは国・方言差を区別しないため、
`ja-JP` と `ja` を同一に扱う。

### 6.5 モデル管理

**取得物と保存先** (すべて内部ストレージ `context.filesDir`):

| 対象 | 保存先 | サイズ |
|------|-------|-------|
| ONNX + config.json | `models/<model-id>/` | 約 38 MB |
| OpenJTalk 辞書 | `open_jtalk_dic/` | 約 102 MB |

初回は合計約 140 MB。辞書は日本語合成にのみ必要だが、初版では常に取得する
(言語ごとの遅延取得は複雑さに見合わない)。

**取得フロー:**

1. `SettingsActivity` でモデルを選択し「ダウンロード」
2. `ModelDownloader` が HF から取得。`DictionaryDownloader` と同じ host allowlist を適用
3. SHA256 を `ModelCatalog` の期待値と照合。不一致なら破棄してエラー
4. 一時ファイルへ書き出し、検証後に `models/<model-id>/` へ atomic move
5. 完了を `ModelManager` に記録

途中終了・電源断に備え、検証前のファイルは必ず一時ディレクトリに置く。
部分ダウンロードのファイルが正規パスに残る状態を作らない。

**ライセンス表示**: モデルごとにライセンス・利用規約を UI に表示する。既定の
`css10-6lang` はキャラクター固有の規約を持たないため同意フローは不要だが、
つくよみちゃんのように規約を持つモデルでは、初回ダウンロード前に規約への
リンクと同意チェックを表示し、同意なしにはダウンロードを開始しない。

---

## 7. データフロー

```text
読み上げアプリ
   │ speak("こんにちは")
   ▼
PiperPlusTtsService.onSynthesizeText(request, callback)
   │
   ├─ LocaleResolver.resolve("jpn") ─────────► language_id = 0
   ├─ speechRate 100 ────────────────────────► lengthScale = 1.0
   ├─ EngineHolder.get() ────────────────────► PiperPlus (キャッシュ済)
   │
   ▼
PiperPlus.synthesizeStream(text, SynthOptions(languageId=0, lengthScale=1.0))
   │ JNI
   ▼
libpiper_plus.so
   ├─ G2P (OpenJTalk)     "こんにちは" → k o [ N_n n i ch i w a
   ├─ phoneme → ID        PUA マップ + BOS/EOS/pad
   └─ ONNX 推論           22050 Hz float32
   │
   ▼ ShortArray チャンク (PCM 16bit)
callback.audioAvailable(...) × N → callback.done()
```

---

## 8. エラー処理

| 事象 | 挙動 |
|------|------|
| モデル未導入で合成要求 | `onLoadLanguage` が `LANG_MISSING_DATA`。`onSynthesizeText` は `callback.error(ERROR_NOT_INSTALLED_YET)` |
| 非対応言語 | `LANG_NOT_SUPPORTED` / `callback.error(ERROR_INVALID_REQUEST)` |
| ネイティブ初期化失敗 | `callback.error(ERROR_SERVICE)`。`PiperPlusException` をログに残しクラッシュさせない |
| 非対応 ABI でのライブラリロード失敗 | 同上。`System.loadLibrary` は `UnsatisfiedLinkError` / `NoClassDefFoundError` を投げ `catch (Exception)` をすり抜けるため、`catch (LinkageError)` を併記する。`Throwable` にはしない (`OutOfMemoryError` まで飲み込む) |
| ダウンロード失敗 | UI にエラー表示 + リトライ。一時ファイルを削除 |
| チェックサム不一致 | 破棄してエラー表示。正規パスには一切書かない |
| ストレージ不足 | ダウンロード開始前に必要容量を確認し、不足なら事前に通知 |
| `onStop()` 中の合成 | ストリーム collect を `takeWhile` で打ち切り、`callback.done()` で正常終了扱い。停止フラグは次の発話の入口でリセットする |
| 打ち切られた iterator | `PiperPlus.synthesizeStream` の `finally` から `piper_plus_synth_abort` を呼ぶ。`synth_start` は engine を busy にしたまま返り、解放するのは `synth_next` が終端に達したときだけなので、これが無いと停止ボタン 1 回で以降の全合成が `ERR_BUSY` になる |

**pitch について**: Android TTS はユーザー設定の `request.pitch` を渡してくるが、
VITS に対応するパラメータがない。初版では**無視する**。設定画面に「ピッチ設定は
このエンジンでは効果がありません」と明記し、ユーザーの混乱を防ぐ。

---

## 9. 配布戦略

### 9.1 前提作業: `libpiper_plus.so` の供給

`android/piper-plus/src/main/cpp/CMakeLists.txt` は `libpiper_plus.so` を `IMPORTED`
として宣言しており、AAR のビルド時点で `jniLibs/<abi>/libpiper_plus.so` が既に
存在している必要がある (CMake がソースからビルドするのは JNI ラッパーのみ)。

前提作業は 2 段階に分かれる。

**(a) CI 内での供給 — M1、必須**

`android-build.yml` の `build-android` job が artifact として上げている `.so` を
`jniLibs/<abi>/` へ展開してから Gradle を回す。これがないと APK をビルドできない。

**(b) リリースアセットとしての配布 — M5、任意**

外部の開発者が AAR を単体で利用する場合に必要。3 ABI をリリースに添付する。

```text
piper-plus-android-<abi>.tar.gz      (arm64-v8a / armeabi-v7a / x86_64)
piper-plus-android-<abi>.tar.gz.cosign.bundle
```

既存の cosign 署名フローに合わせる。(b) はエンジンアプリの成立条件ではないため
M5 に置く。

### 9.2 GitHub Releases

`release-shared-lib.yml` に APK ビルド job を追加し、tag push で
`piper-plus-tts-<version>.apk` を添付する。署名鍵は GitHub Secrets で管理。

### 9.3 F-Droid

F-Droid は開発者が APK をアップロードする仕組みではなく、**F-Droid 側の
ビルドサーバーがソースからビルドし F-Droid の鍵で署名**する。初回のみ
`fdroiddata` への Merge Request が必要で、以降は自動化できる。

SherpaTTS (`org.woheller69.ttsengine`) の実績ある構成に倣う:

```yaml
AutoUpdateMode: Version
UpdateCheckMode: Tags V.*
```

これにより **git tag の push だけで F-Droid が自動検出 → 自動ビルド → 自動配信**する。

モデルを実行時に取得する構成には `AntiFeatures: NonFreeNet` が付くが、
SherpaTTS も同条件で掲載されており、掲載自体の障害にはならない。

---

## 10. テスト戦略

音声の正しさは既存の C++ / Python テストが担保しているため、エンジン側は
**橋渡しが正しいか**に絞る。合成結果の音響的検証は再実装しない。

ただし「橋渡し」には、壊れても静かに通り抜ける箇所が集まっている。
PCM のバイト順、8 引数 JNI の並び、`SynthesisCallback` の呼び出しプロトコル、
manifest の配線は、いずれも**壊しても型検査もリンクも APK ビルドも成功する**。
テストの重みはそこに置く。

| 層 | 対象 | 実行環境 |
|---|------|---------|
| JVM ユニット | `PcmEmitter` — little-endian 詰め替え、`maxBufferSize` 分割、中断 | `./gradlew :piper-plus-tts-engine:testDebugUnitTest` |
| JVM ユニット | `SynthesisSession` — 早期エラーの判定順、callback プロトコル、`SynthOptions` 配線、停止フラグ、例外/`LinkageError` の遮断 | 同上 |
| JVM ユニット | `LocaleResolver` の全 6 言語 + 非対応言語 + 大文字小文字 | 同上 |
| JVM ユニット | `EngineHolder` の生存管理と、ロード失敗時に古いインスタンスを残さないこと | 同上 |
| JVM ユニット | `ModelPaths` のパス解決とインストール判定 | 同上 |
| JVM ユニット | `speechRate` → `lengthScale` 変換 (境界値: 0, 負値, 100, 400) | 同上 |
| JVM 契約 | `ManifestWiringTest` — `android:name` が実在の `TextToSpeechService` に解決し、TTS の intent-filter が正しいこと | 同上 |
| JVM 契約 | `PiperPlusNativeBridgeTest` — Kotlin `external` 宣言 ↔ `piper_plus_jni.cpp` の C++ 定義をソース照合 | `./gradlew :piper-plus:testDebugUnitTest` |
| JVM 契約 | `SynthOptionsTest` — 既定値を `piper_plus_default_options()` の実ソースと突き合わせ | 同上 |
| C++ 統合 | iterator を途中で放棄しても engine が busy のまま残らないこと | `test_c_api_integration` |
| CI | Kotlin ユニットテスト (native ビルドに従属しない独立 job) | `android-build.yml` の `kotlin-unit-tests` |
| CI | 3 ABI ビルド + APK 生成 | `android-build.yml` の `build-tts-engine` |

### 10.1 テスト可能性のための設計上の制約

`android.speech.tts.SynthesisRequest` は final で、全 getter が
`RuntimeException("Stub!")` を投げるスタブしか持たない。reflection でも
中身を詰められないため、`onSynthesizeText(request, callback)` を直接呼ぶ形では
JVM ユニットテストが**「非対応言語 → error」の 1 分岐にしか到達できない**。

このため合成の本体は [`SynthesisSession`](#61-責務分割) に切り出し、
`PiperPlusTtsService` は request をほどくだけのアダプタに保つ。
Robolectric や mockk は導入しない — この境界があれば手書きの fake で足りる。

### 10.2 ミューテーションによる検証

テストが「通ること」は価値の証明にならない。上記のテストは、対応する
production コードに以下の変異を入れて**実際に落ちること**を確認してある。

バイト順の反転 / `shr 8` を `/ 256` に / `audioAvailable` の offset 落とし /
`maxBufferSize` 下限ガードの除去 / 停止フラグのリセット除去 /
`takeWhile` を collect 内 return に / エラーコードの取り違え / 判定順の入れ替え /
`catch (LinkageError)` の除去 / `speechRate` の無視 / `isBlank` を `isEmpty` に /
JNI 引数の並べ替え / JNI 側だけの rename / `opts` 代入の取り違え /
呼び出し側 named argument の取り違え / フィールドの配線落とし / 引数型の変更 /
Kotlin 宣言だけの引数追加 / `EngineHolder` の失敗時クリア除去 /
manifest のクラス名タイポ / intent action の綴りミス /
C 側と Kotlin 側の既定値の片側変更

---

## 11. リスクと対策

| リスク | 影響 | 対策 |
|-------|------|------|
| 初回 140 MB のダウンロード | 離脱要因 | 進捗表示、Wi-Fi 推奨の明示、中断・再開に耐える設計 |
| `.so` 配布フロー未整備 | 着手のブロッカー | §9.1 を最初のマイルストーンに置く |
| 16 KB page size (Pixel 8a / Android 15+) | 起動失敗 | 既存 CI の `readelf` PT_LOAD アライメント検査が既に gate 済 |
| モデル固有の利用規約 (つくよみちゃん等) | ライセンス違反 | モデルごとのライセンス表示と同意フロー (§6.5)。既定の `css10-6lang` は該当しない |
| F-Droid のビルド失敗 | 配信されない | GitHub Releases を並行提供し、F-Droid は追従扱いにする |
| pitch 未対応への不満 | ユーザー混乱 | 設定画面に明記 (§8) |

---

## 12. 段階的リリース

| マイルストーン | 内容 | 完了条件 |
|--------------|------|---------|
| M1 | CI での `.so` 供給と AAR の 3 ABI 対応 (§9.1a) | CI で TTS エンジン APK がビルドできる |
| M2 | AAR の合成オプション拡張 (§6.2) | `SynthOptions` 経由で `language_id` / `lengthScale` が効く |
| M3 | TTS Service 最小実装 (日本語のみ、モデルは手動配置) | システム TTS で日本語が喋る |
| M4 | モデル管理 + 設定 UI (§6.5) | アプリ内で DL → 6 言語が喋る |
| M5 | 配布 (GitHub Releases → F-Droid MR) | tag push で両方に配信 |

M3 の時点で「Android で piper-plus が喋る」ことは検証できる。M4 以降は
配布性の作り込みであり、M3 を先に通して方式の妥当性を確認する。

---

## 13. 関連ドキュメント

- [Kotlin G2P 設計書](../reference/kotlin-g2p-design.md) — AAR 分離方針の先行事例
- [Android G2P 辞書配布](../guides/platform/android-g2p-dictionary.md) — OpenJTalk 辞書の取得手順
- [Android G2P 統合ガイド](../guides/platform/android-g2p-integration.md)
- [学習済みモデル一覧](../guides/development/pretrained-models.md) — HF 配布モデルの canonical source
- `src/cpp/piper_plus.h` — C API と `PiperPlusSynthOptions` の規約
