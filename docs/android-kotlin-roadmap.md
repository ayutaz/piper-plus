# Android Kotlin/Java バインディング -- 実装ロードマップ

> Issue: [#257](https://github.com/ayutaz/piper-plus/issues/257)
> 技術設計書: [android-kotlin-binding.md](./android-kotlin-binding.md)
> ブランチ: `feat/android-kotlin-binding`

---

## Phase 1: プロジェクト構造・ビルドシステム (完了)

**目標:** Android Gradleプロジェクトの骨格を作り、C++コアをAndroid向けにクロスコンパイルできる状態にする。

### 1.1 Gradleプロジェクト初期化

| タスク | 成果物 | 依存 |
|--------|--------|------|
| `src/android/` ディレクトリ作成 | ディレクトリ構造 | - |
| `settings.gradle.kts` 作成 | モジュール定義 | - |
| ルート `build.gradle.kts` 作成 | AGP + Kotlin plugin | - |
| `gradle/libs.versions.toml` 作成 | バージョンカタログ | - |
| Gradle Wrapper 設定 | `gradlew`, `gradle-wrapper.properties` | - |

### 1.2 AARライブラリモジュール

| タスク | 成果物 | 依存 |
|--------|--------|------|
| `piper-android/build.gradle.kts` 作成 | ライブラリモジュール設定 | 1.1 |
| `AndroidManifest.xml` 作成 | namespace定義 | 1.1 |
| ONNX Runtime Android AAR依存追加 | `onnxruntime-android:1.24.2` | 1.1 |
| Kotlin Coroutines依存追加 | `kotlinx-coroutines-android` | 1.1 |
| `consumer-rules.pro` 作成 | ProGuard/R8ルール | 1.1 |
| ABIフィルタ設定 | arm64-v8a, armeabi-v7a, x86_64 | 1.1 |

### 1.3 CMake Android JNIビルド対応

| タスク | 成果物 | 依存 |
|--------|--------|------|
| `CMakeLists.txt` に `BUILD_ANDROID_JNI` オプション追加 | CMake設定 | - |
| JNI共有ライブラリターゲット (`libpiper_jni.so`) 定義 | CMakeターゲット | 上記 |
| Android NDK toolchainとの互換性確認 | ビルド成功 | 上記 |
| ONNX Runtime Android プリビルドライブラリのリンク設定 | CMake IMPORTED target | 上記 |

### 1.4 クロスコンパイルスクリプト

| タスク | 成果物 | 依存 |
|--------|--------|------|
| `scripts/build-android-arm64-v8a.sh` | ARM64ビルドスクリプト | 1.3 |
| `scripts/build-android-armeabi-v7a.sh` | ARMv7ビルドスクリプト | 1.3 |
| `scripts/build-android-x86_64.sh` | x86_64ビルドスクリプト | 1.3 |
| ローカルビルド成功確認 (少なくとも1 ABI) | `.so` ファイル | 上記 |

### 1.5 GitHub Actions CI

| タスク | 成果物 | 依存 |
|--------|--------|------|
| `.github/workflows/android-build.yml` 作成 | CIワークフロー | 1.2, 1.4 |
| ネイティブビルドジョブ (3 ABI matrix) | `.so` アーティファクト | 上記 |
| AARビルドジョブ | `.aar` アーティファクト | 上記 |
| ユニットテストジョブ | テスト結果 | 上記 |

**Phase 1 完了条件:**
- `./gradlew :piper-android:assembleRelease` がローカルで成功
- CI上で3 ABI全てのネイティブビルドが成功
- AARファイルが生成される

---

## Phase 2: JNIブリッジ + コア推論 (完了)

**目標:** KotlinからC++コアを呼び出し、テキストから音声を合成できる状態にする。

### 2.1 JNI C++実装

| タスク | 成果物 | 依存 |
|--------|--------|------|
| `piper_jni.cpp` 作成 | JNIエントリーポイント | Phase 1 |
| `PiperEngine` ラッパークラス (C++) | C++コア統合クラス | 上記 |
| `nativeCreate(modelPath, configPath)` → jlong | モデルロードJNI | 上記 |
| `nativeSynthesize(handle, text, language, speakerId)` → jshortArray | 合成JNI | 上記 |
| `nativeDestroy(handle)` | リソース解放JNI | 上記 |
| `PIPER_JNI_TRY_CATCH` 例外安全マクロ | エラーハンドリング | 上記 |
| `JNI_OnLoad` / `JavaVM*` グローバル保持 | スレッド管理基盤 | 上記 |

### 2.2 Kotlin API

| タスク | 成果物 | 依存 |
|--------|--------|------|
| `PiperConfig.kt` (data class) | 設定クラス | Phase 1 |
| `PiperAudio.kt` (data class + save()) | 音声データクラス | Phase 1 |
| `PiperTts.kt` (メインAPI) | TTS APIクラス | 2.1 |
| `NativeBridge.kt` (internal JNI宣言) | JNIブリッジ | 2.1 |
| `suspend synthesize()` 実装 | 非同期合成 | 上記 |
| `companion object { load() }` 実装 | ファクトリメソッド | 上記 |
| `AutoCloseable.close()` 実装 | リソース管理 | 上記 |

### 2.3 マルチスピーカー・マルチリンガル対応

| タスク | 成果物 | 依存 |
|--------|--------|------|
| Speaker ID パラメータ受け渡し | JNI → C++ sid設定 | 2.1 |
| Language ID パラメータ受け渡し | JNI → C++ lid設定 | 2.1 |
| Prosody features (A1/A2/A3) 対応 | JNI → C++ prosody入力 | 2.1 |
| config.json パース (話者リスト、言語リスト) | Kotlin側メタデータ | 2.2 |

### 2.4 テスト

| タスク | 成果物 | 依存 |
|--------|--------|------|
| Kotlin API ユニットテスト (モック) | JUnitテスト | 2.2 |
| JNI統合テスト (テストモデル使用) | テスト成功 | 2.1, 2.2 |
| メモリリークテスト (open/close サイクル) | テスト成功 | 上記 |

**Phase 2 完了条件:**
- テストモデルを使い `PiperTts.load() → synthesize("Hello") → PiperAudio` が成功
- 6言語全てのテキスト入力で音声生成が成功
- Speaker ID / Language ID 切り替えが動作

---

## Phase 3: Android統合 (完了)

**目標:** AndroidのシステムTTSエンジンとして登録でき、他アプリからPiper TTSを利用できる状態にする。

### 3.1 TextToSpeechService実装

| タスク | 成果物 | 依存 |
|--------|--------|------|
| `PiperTtsService.kt` 作成 | TTSサービスクラス | Phase 2 |
| `onIsLanguageAvailable()` 実装 (6言語) | 言語対応報告 | 上記 |
| `onLoadLanguage()` 実装 | 言語プリロード | 上記 |
| `onGetLanguage()` 実装 | 現在言語返却 | 上記 |
| `onSynthesizeText()` 実装 (callback.start/audioAvailable/done) | 合成コア | 上記 |
| `onStop()` 実装 | キャンセル処理 | 上記 |
| `AndroidManifest.xml` TTSエンジン登録 | intent-filter + meta-data | 上記 |
| `res/xml/tts_engine.xml` 作成 | TTSエンジン設定 | 上記 |

### 3.2 ストリーミング出力

| タスク | 成果物 | 依存 |
|--------|--------|------|
| `nativeSynthesizeStreaming` JNI実装 | C++ chunkCallback → JNI | Phase 2 |
| `synthesizeStream()` Kotlin実装 (callbackFlow) | Flow<ShortArray> API | 上記 |
| AudioTrack MODE_STREAM 再生ヘルパー | ストリーミング再生 | 上記 |
| バッファリング制御 (`.buffer(2)`) | 途切れ防止 | 上記 |

### 3.3 非同期・ライフサイクル統合

| タスク | 成果物 | 依存 |
|--------|--------|------|
| `Dispatchers.Default` による推論オフロード | CPU-bound最適化 | Phase 2 |
| `Dispatchers.IO` による AudioTrack 書き込み | I/Oオフロード | 3.2 |
| キャンセレーション対応 (`ensureActive()`, `invokeOnCancellation`) | 中断対応 | 上記 |
| `CoroutineExceptionHandler` 統合 | エラーUI通知 | 上記 |

### 3.4 モデル管理

| タスク | 成果物 | 依存 |
|--------|--------|------|
| Android Assets からのモデルロード | `load(context, assetPath)` | Phase 2 |
| 内部ストレージへのモデルコピー (大モデル用) | ファイルパスロード | 上記 |
| モデルキャッシュ管理 | 再起動時高速化 | 上記 |

**Phase 3 完了条件:**
- Androidの「設定 → テキスト読み上げ → エンジン選択」にPiper TTSが表示される
- 他アプリから `TextToSpeech` API経由でPiper TTSを利用できる
- ストリーミング再生が途切れなく動作する
- 言語切り替えが動的に動作する

---

## Phase 4: サンプルアプリ (完了)

**目標:** 開発者がPiper Android SDKの使い方を理解できるリファレンス実装を提供する。

### 4.1 プロジェクト設定

| タスク | 成果物 | 依存 |
|--------|--------|------|
| `sample-app/build.gradle.kts` 作成 | Jetpack Compose設定 | Phase 1 |
| Compose BOM依存追加 | Material3 + Lifecycle | 上記 |
| `piper-android` モジュール参照 | `implementation(project(":piper-android"))` | 上記 |

### 4.2 UIスクリーン

| タスク | 成果物 | 依存 |
|--------|--------|------|
| テキスト入力フィールド | TextField + 送信ボタン | 4.1 |
| 言語セレクター (6言語ドロップダウン) | 言語切り替えUI | 4.1 |
| 話者セレクター (マルチスピーカーモデル用) | Speaker ID切り替えUI | 4.1 |
| 再生状態表示 (Idle/Synthesizing/Playing/Error) | StateFlow → UI | 4.1 |
| 音声パラメータ調整 (noise_scale, length_scale) | Slider UI | 4.1 |

### 4.3 ViewModel + 推論統合

| タスク | 成果物 | 依存 |
|--------|--------|------|
| `TtsViewModel` 作成 | viewModelScope統合 | Phase 3 |
| `speak()` メソッド (合成 + 再生) | ワンタップ合成 | 上記 |
| `stop()` メソッド (キャンセル) | 再生中断 | 上記 |
| WAVファイル保存機能 | `PiperAudio.save()` | 上記 |

**Phase 4 完了条件:**
- サンプルアプリでテキスト入力→音声合成→再生が動作する
- 6言語の切り替えが動作する
- エラー時に適切なUIフィードバックが表示される

---

## Phase 5: 配布・ドキュメント (進行中)

**目標:** Maven Centralに公開し、他の開発者がGradle依存で利用できる状態にする。

### 5.1 Maven Central公開設定

| タスク | 成果物 | 依存 | 状態 |
|--------|--------|------|------|
| Sonatype Central Portal アカウント作成 | namespace検証済み | - | 未着手 |
| GPG鍵ペア生成 + キーサーバー登録 | 公開鍵登録 | 上記 | 未着手 |
| vanniktech maven-publish plugin設定 | `build.gradle.kts` | Phase 1 | ✅ |
| POMメタデータ設定 (license, scm, developers) | Maven要件充足 | 上記 | ✅ |
| GitHub Secrets設定 (MAVEN_CENTRAL_*, GPG_*) | CI用シークレット | 上記 | 未着手 |

### 5.2 CI/CD自動リリース

| タスク | 成果物 | 依存 | 状態 |
|--------|--------|------|------|
| `.github/workflows/android-build.yml` 作成 | ビルドワークフロー | Phase 1 | ✅ |
| Debug + Release AARビルド | CIでAAR生成 | 上記 | ✅ |
| Android Lint | コード品質チェック | 上記 | ✅ |
| ユニットテスト (testDebugUnitTest) | テスト結果 | 上記 | ✅ |
| サンプルアプリビルド + Lint | sample-app CI検証 | 上記 | ✅ |
| AARアーティファクトアップロード (debug + release) | GitHub Artifacts | 上記 | ✅ |
| `.github/workflows/android-publish.yml` 作成 | 公開ワークフロー | 5.1 | ✅ |
| Secrets バリデーション (MAVEN_CENTRAL_*, GPG_*) | 公開前チェック | 上記 | ✅ |
| Version バリデーション (gradle.properties vs tag) | バージョン整合性チェック | 上記 | ✅ |
| Build + Lint + Test before publish | 公開前品質ゲート | 上記 | ✅ |
| `publishAndReleaseToMavenCentral` タスク | Maven Central公開 | 上記 | ✅ |
| ビルドスクリプト修正 (CMake source dir, 依存変数) | ビルド安定化 | Phase 1 | ✅ |
| NDK CI環境セットアップ | ネイティブビルドCI対応 | 上記 | 未着手 |
| Instrumented tests (androidTest) | デバイステスト | 上記 | 未着手 |
| テスト公開 (beta版) | `1.0.0-beta01` on Maven Central | 5.1 | 未着手 |
| 正式リリース | `1.0.0` on Maven Central | 上記 | 未着手 |

**CI/CD 実装メモ:**
- ビルドワークフロー (`android-build.yml`): push/PR時に `src/android/**`, `src/cpp/**`, `CMakeLists.txt` 変更で自動トリガー。Debug/Release AAR, Lint, Unit Tests, Sample Appビルドを実行。
- 公開ワークフロー (`android-publish.yml`): `android-v*` タグの GitHub Release 作成時にトリガー。Secrets検証 → Version整合性チェック → Build+Lint+Test → Maven Central公開 の安全なパイプライン。
- 残作業: Sonatype Central Portalアカウント作成、GPG鍵生成、GitHub Secrets登録、NDK CI環境構築、Instrumented tests追加。

### 5.3 ドキュメント

| タスク | 成果物 | 依存 |
|--------|--------|------|
| KDoc APIドキュメント (PiperTts, PiperConfig, PiperAudio) | KDoc | Phase 2 |
| README.md (クイックスタート、Gradle依存追加方法) | README | Phase 4 |
| サンプルコードスニペット (Kotlin + Java) | README | Phase 4 |
| CHANGELOG.md | リリースノート | 5.2 |

**Phase 5 完了条件:**
- `implementation("io.github.ayousanz:piper-android:1.0.0")` でGradle依存追加可能
- Maven CentralにAAR + sources + javadoc + POM + 署名が公開
- GitHub Releaseから自動公開が動作

---

## 全体タイムライン

```
Phase 1: プロジェクト構造・ビルドシステム
  ├── 1.1 Gradle初期化
  ├── 1.2 AARモジュール
  ├── 1.3 CMake JNIビルド
  ├── 1.4 クロスコンパイル
  └── 1.5 CI

Phase 2: JNIブリッジ + コア推論
  ├── 2.1 JNI C++実装
  ├── 2.2 Kotlin API
  ├── 2.3 マルチスピーカー・マルチリンガル
  └── 2.4 テスト

Phase 3: Android統合
  ├── 3.1 TextToSpeechService
  ├── 3.2 ストリーミング
  ├── 3.3 非同期・ライフサイクル
  └── 3.4 モデル管理

Phase 4: サンプルアプリ
  ├── 4.1 プロジェクト設定
  ├── 4.2 UIスクリーン
  └── 4.3 ViewModel統合

Phase 5: 配布・ドキュメント (進行中)
  ├── 5.1 Maven Central設定 (一部完了: plugin設定済み、アカウント未作成)
  ├── 5.2 CI/CD自動リリース (ワークフロー完了 ✅、実公開は未着手)
  └── 5.3 ドキュメント
```

---

## リスク・注意事項

| リスク | 影響 | 対策 |
|--------|------|------|
| OpenJTalk辞書のAndroid NDKビルド | JA phonemizerが動作しない | sherpa-onnxのOpenJTalkビルド設定を参考にする |
| ONNX Runtime Android AARサイズ | APKが大きくなる (~30MB/ABI) | `arm64-v8a` のみに絞る選択肢を文書化 |
| FP16モデルのNNAPI互換性 | 特定デバイスで推論失敗 | CPU fallbackを確保、NNAPIはオプション |
| JNIメモリリーク | 長時間使用でOOM | `AutoCloseable` + `finalize()` セーフティネット |
| TextToSpeechService の多言語同時リクエスト | スレッド競合 | `synchronized` / `Mutex` で推論を排他制御 |
