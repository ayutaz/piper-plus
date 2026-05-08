# Kotlin G2P ライブラリ 要件定義書 (Issue #388)

> **ステータス**: Implemented (Issue #388, PR #400 / dev に merge 済み)
> **親 Issue**: [#388](https://github.com/ayutaz/piper-plus/issues/388) — 「Kotlin 向けの g2p ライブラリの提供」
> **設計書**: [kotlin-g2p-design.md](kotlin-g2p-design.md)
> **判定基準** (実装着手前): 自動化可能性 (CLI/CI で完結) を最優先。実装工数は評価軸から除外。

> **注**: 本書は実装着手前の要件定義。受け入れ基準チェックリスト (§14) / オープンクエスチョン (§15) / リスク表 (§13) / 改訂履歴 (§18) は実装完了に伴い削除済み (詳細は git log と PR #400)。残置されているのは「核心的な技術的決定事項」「機能要件」「非機能要件」「制約条件」「テスト要件」「インターフェース要件」「スコープ外」など、後続メンテで規範性を持つセクション。

---

## 0. このドキュメントの位置づけ

**設計書との関係**:
- 設計書 (kotlin-g2p-design.md) は「**どう作るか** (アーキテクチャ、API 例、実装ロードマップ)」を整理した。
- 本要件定義書は「**何を作るか** (機能要件、非機能要件、制約、受け入れ基準)」を実装着手前に確定させる。
- 設計書策定後に技術調査 (4 並列エージェント) で得た新事実 — **特に「`piper_plus_phonemize()` は ONNX モデル必須」** — を反映し、設計書ではぼかしていた前提を明示化した。

**読み順**: 本書 → 設計書 → チケット INDEX。
本書のセクション §5「核心的な技術的決定事項」を読むと、設計書 §4「アプローチ比較」の前提が変わる箇所があるため、必要に応じて設計書を改訂する。

---

## 1. 概要・目的

### 1.1 ゴール

Android アプリ開発者が `implementation("io.github.ayutaz:piper-plus-g2p-android:X.Y.Z")` の 1 行で、piper-plus の **8 言語 G2P (text-to-phoneme)** を Kotlin から呼び出せる状態を作る。

### 1.2 背景

- piper-plus はマルチランタイム G2P ライブラリを既に Python / Rust / Go / npm / C# / C API で公開済 (`piper-plus-g2p` ファミリー)。
- Issue #388 は「Kotlin 向け G2P ライブラリの欠落を埋める」というユーザー要望に基づく。
- Android アプリでオフライン読み上げ機能 (TTS / アクセシビリティ / 音声対話) を実装したい開発者が、espeak-ng-free + MIT ライセンス + 8 言語対応の G2P を Kotlin から利用できるようにする。

### 1.3 KPI (測定可能な成功基準)

| KPI | 測定方法 | 合格ライン |
|-----|---------|----------|
| 導入容易性 | `implementation()` 1 行追加で動くサンプルアプリ | サンプルアプリで成功 |
| クロスランタイム整合性 | Python ランタイムと byte-for-byte 一致テスト | 8 言語 × 50 ケース全 PASS |
| 自動テスト網羅率 | CI で完結する 5 層テスト | 全層 PASS、フレーキー率 < 1% |
| AAR サイズ | `du -sh` (辞書を除く) | < 10 MB (3 ABI バンドル時)、目標 < 5 MB |
| 公開自動化 | タグ push → Maven Central 反映時間 | < 30 分、人手介入ゼロ |
| 16 KB page size 対応 | `objdump -p` で `align 2**14` | 全 `.so` で OK |

---

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| **G2P** | Grapheme-to-Phoneme。テキスト (書記素) を音素 (phoneme) 列に変換する処理。 |
| **Phoneme (音素)** | IPA (国際音声記号) 文字列。本ライブラリでは UTF-8 / 空白区切り / PUA 含む。 |
| **PUA** | Private Use Area (U+E000..U+F8FF)。中国語の有気音・複母音・声調などを単一 codepoint で表現するために使用。本プロジェクトでは U+E020..U+E04A を中国語、U+E016..U+E01C を日本語に割当。 |
| **AAR** | Android Archive。Android ライブラリの配布形式。`classes.jar` + `jni/{abi}/lib*.so` + manifest 等を ZIP 化したもの。 |
| **ABI** | Application Binary Interface。Android では `arm64-v8a` (本番)、`armeabi-v7a` (旧端末)、`x86_64` (エミュレータ) の 3 種を主に使う。 |
| **JNI** | Java Native Interface。Kotlin/Java から C/C++ を呼ぶための仕組み。 |
| **Engine-less G2P** | ONNX モデル (.onnx) を必要とせずに G2P 処理を実行できる API。**本要件定義の核心トピック**。 |
| **Maven Central** | Java/Kotlin の公式パッケージレジストリ (Sonatype Central Portal 経由)。 |
| **Gradle Managed Devices** | AGP 7.3+ 機能。CI 上で Android emulator を自動起動・破棄して instrumented test を実行する仕組み。 |

---

## 3. ステークホルダー / ターゲットユーザー

### 3.1 一次ターゲット (主要開発者像)

| ペルソナ | 想定シナリオ | 期待すること |
|---------|-----------|-----------|
| **Android アプリ開発者** | アプリ内オフライン TTS の組込 (G2P → 自前の音響モデル推論) | Kotlin idiomatic API、5 ステップ以内の導入手順 |
| **アクセシビリティアプリ開発者** | screen reader / 視覚障害支援アプリでの多言語 phonemize | F-Droid 対応、ライセンスクリーン (MIT 維持) |
| **音声対話・ゲーム開発者** | Unity/Godot の Android 配布で NPC セリフ phonemize | サイズの小さい AAR、辞書のオプトイン |
| **音声処理研究者** | Android 端末で実機ベンチマーク取得 | 既存ランタイム (Python) との byte 一致保証 |

### 3.2 二次ターゲット (間接利用者)

- Issue #388 で言及された「Android アプリ対応時に G2P を使いたい人」全般
- 既存 piper-plus の他ランタイムユーザーで、Android にも展開したい開発者

### 3.3 非ターゲット (本 Issue で扱わない)

- iOS 開発者 — `xcframework + SPM` で別途対応済 (Apple-embedded)
- Android System TTS Engine 化したい人 — 別 Issue で扱う (Service + Activity 配布)
- TTS フル機能 (合成エンジン) を求める人 — `android/piper-plus/` (既存 AAR 草案) で別途扱う

---

## 4. 既存資産の整理 (要件への入力)

技術調査 (2026-05-07 4 並列エージェント) で得た既存資産:

### 4.1 完全再利用可能 (拡張不要)

| 資産 | パス | 状態 |
|------|------|------|
| Android NDK ビルド CI | `.github/workflows/android-build.yml` | 3 ABI (arm64-v8a / armeabi-v7a / x86_64)、NDK 26.1、ORT 1.17.0、API 24 |
| ZH-EN loanword embedding | `cmake/PiperCommon.cmake:103-146` | `PIPER_PLUS_EMBEDDED_LOANWORD` flag、Android branch 対応済 |
| Android クロスコンパイル設定 | `cmake/CompilerSettings.cmake:37-49` | NDK toolchain propagation 済 |
| 既存 JNI パターン | `android/piper-plus/src/main/cpp/piper_plus_jni.cpp` | `JNIStringGuard` RAII、`JNI_OnLoad` キャッシュ、例外スロー |
| C API バインディング | `src/cpp/piper_plus.h` (445 行) | 全関数シグネチャ、メモリ規約、スレッドセーフティ規約完備 |
| Voice Cloning / Speaker Encoder | `src/cpp/piper_plus.h:402-438` | EXPERIMENTAL 扱い、本 Issue では非依存 |

### 4.2 拡張要 (要件で明示)

| 資産 | 現状 | 拡張要件 |
|------|------|---------|
| Release shared lib | arm64-v8a のみ配布 | armeabi-v7a / x86_64 も artifact 化 (FR-DIST-2) |
| 16 KB page size 対応 | 未設定 | 全 ABI で `-Wl,-z,max-page-size=16384` (CONSTRAINT-1) |
| GitHub Actions secrets | Maven 系未登録 | `MAVEN_CENTRAL_USERNAME` / `MAVEN_CENTRAL_PASSWORD` / `SIGNING_IN_MEMORY_KEY` / `SIGNING_IN_MEMORY_KEY_PASSWORD` 追加 (NFR-PUB-2) |
| C API | engine 必須 | **engine-less G2P API 追加** ← §5 で詳述 |

### 4.3 部分再利用 / 参考のみ

| 資産 | パス | 扱い |
|------|------|------|
| 既存 TTS フル AAR 草案 | `android/piper-plus/` | namespace 衝突回避のため `com.piperplus.g2p` で独立モジュール作成 (CONSTRAINT-2) |
| 他言語 G2P API シグネチャ | `src/python/g2p/`, `src/rust/piper-plus-g2p/`, `src/go/phonemize/`, `src/wasm/g2p/`, `src/csharp/PiperPlus.Core/Phonemize/` | Kotlin API 命名・引数の参考 (FR-API-1) |
| Release ワークフロー パターン | `g2p-rust-publish.yml`, `npm-publish.yml`, `g2p-go-publish.yml` | タグトリガー / version check / dry-run の踏襲 (NFR-PUB-1) |

---

## 5. 核心的な技術的決定事項 (要件への前提)

### 5.1 問題: 既存 C API は ONNX モデルを必須要求する

#### 5.1.1 発見の根拠

`src/cpp/piper_plus_c_api.cpp:977-1074` の `piper_plus_phonemize()` 実装は以下を要求:

```cpp
// piper_plus_c_api.cpp:990-1005 (要約)
if (language && engine->voice.modelConfig.languageIdMap) {  // ← config.json 由来
    auto it = engine->voice.modelConfig.languageIdMap->find(language);
    // ...
}
piper::phonemizeText(engine->voice, processedText, phonResult);  // ← Voice = ONNX + config.json
```

`Voice` は `piper_plus_create()` で構築される際、`PiperPlusConfig.model_path` (.onnx ファイル) と `config_path` (.json) を必須とする。
**結論**: 現在の C API では「ONNX モデルなしで G2P する」ことができない。

#### 5.1.2 他ランタイムとの比較

| ランタイム | G2P 単体パッケージで ONNX 不要か | 備考 |
|----------|------------------------|------|
| Python `piper-plus-g2p` (PyPI) | ✓ 不要 | Phonemizer インスタンスを直接生成 |
| Rust `piper-plus-g2p` (crates.io) | ✓ 不要 | `Phonemizer` trait 実装を直接呼ぶ |
| Go `phonemize` パッケージ | ✓ 不要 | 関数呼び出しのみ |
| npm `@piper-plus/g2p` | ✓ 不要 | WASM module 単体 |
| C# `PiperPlus.Core` G2P | ✓ 不要 | `IPhonemizer` インターフェース |
| **C API (現状)** | **✗ 必要** | **engine = Voice = ONNX 必須** |

C API のみが engine 経由を強制している。これは Kotlin AAR が C API 経由で実装する場合、Python/Rust/Go と同じ「G2P 単体ライブラリ」体験を提供できないことを意味する。

### 5.2 採択する解決アプローチ

#### 5.2.1 選択肢の評価

| # | 案 | 概要 | 自動化 | 既存資産活用 | クロスランタイム整合性 | 採否 |
|---|-----|-----|------|----------|------------------|------|
| **B-1** | **C API に engine-less G2P エントリポイント追加** | `piper_plus_g2p_create()` (model 不要、languageIdMap 内蔵) を新規追加 | ◎ | ◎ (C++ multilingual phonemizer 流用) | ◎ (既存 phonemize ロジック共用) | **★ 採択** |
| A-1 | ONNX モデル必須路線 | Kotlin ユーザーが小型 multilingual モデル (~10MB) を用意 | △ (モデル DL or assets bundle で UX 低下) | ◎ | ◎ | △ |
| C-1 | Pure Kotlin G2P 完全移植 | 8 言語すべて Kotlin で再実装 | ◎ | × (再実装) | △ (drift リスク高) | × |
| C-2 | Pure Kotlin で規則ベース 4 言語のみ + JA/EN/ZH/KO は engine 経由 | ハイブリッド | △ | △ | △ | × |

**採択**: **B-1** を採用。

#### 5.2.2 採択理由

1. **クロスランタイム整合性**: C API レベルで engine-less G2P を提供すれば、Kotlin / Dart FFI / Godot / Unity すべてが同じパスを使える (将来性)。
2. **既存資産活用**: C++ の `piper::phonemizeText()` ロジックは `Voice` に依存するが、`languageIdMap` を内蔵データに置き換える形で再利用可能。完全な再実装は不要。
3. **自動化**: 既存 CI (`android-build.yml`) で `libpiper_plus.so` をビルドする際に新 API もまとめてビルド。新規 CI 不要。
4. **espeak-ng-free 維持**: C++ 実装は既に espeak-ng 非依存。Pure Kotlin 移植では g2p-en (英語) 相当を再実装する必要があり、ライセンス検証が複雑化する。
5. **将来の Voice Cloning 拡張**: engine-less G2P があれば、speaker encoder (`piper_plus_speaker_encoder_*`) と組み合わせて軽量な「テキスト解析専用」用途にも展開できる。

#### 5.2.3 派生する追加要件

採択 B-1 により、以下が要件として追加される:

- **FR-CAPI-1**: C API に engine-less G2P エントリポイント追加 (詳細 §6.1)
- **FR-CAPI-2**: `languageIdMap` 内蔵データの仕様定義 (8 言語の language code → ID mapping を C 側で持つ)
- **NFR-CAPI-1**: 既存 `piper_plus_phonemize()` (engine ベース) との出力 byte 一致保証
- **CONSTRAINT-CAPI-1**: 新 API は既存 ABI と互換性を保つ (PIPER_PLUS_API_VERSION 1 内で追加)

### 5.3 ライセンス・依存関係の確認

| コンポーネント | ライセンス | Kotlin G2P での扱い |
|------------|----------|----------------|
| piper-plus C API (`libpiper_plus.so`) | MIT | そのまま使用 |
| ONNX Runtime | MIT | shared lib として AAR に含む (~2MB/ABI) |
| pyopenjtalk-plus 由来辞書 | Modified BSD (naist-jdic) | AAR には含まない (オプトイン) |
| g2p-en | Apache-2.0 | C++ 実装内に既に組込済 |
| pypinyin | MIT | C++ 実装内 |
| g2pk2 | Apache-2.0 | C++ 実装内 |
| ZH-EN loanword JSON | MIT (本リポジトリ) | C array として `.so` に embed (~5.6KB) |

→ **AAR の効果ライセンス**: MIT (本リポジトリ) + 同梱 third-party は LICENSE ファイルに集約 (NFR-LICENSE-1)。

---

## 6. 機能要件 (Functional Requirements)

### 6.1 C API レベルの追加要件

#### FR-CAPI-1: Engine-less G2P エントリポイント

C API に以下を追加すること:

```c
/* ===== Engine-less G2P (Issue #388) ===== */

typedef struct PiperPlusG2pHandle PiperPlusG2pHandle;

/** Create a G2P handle without an ONNX model.
 *  Uses built-in language ID map (en/fr/ja/ko/es/pt/sv/zh).
 *  @param dict_dir  Optional OpenJTalk dict dir (NULL = no JA support).
 *  @return Handle on success, NULL on failure (call piper_plus_get_last_error()).
 *  @threading Per-handle single-threaded; multiple handles are independent. */
PIPER_PLUS_API PiperPlusG2pHandle *piper_plus_g2p_create(const char *dict_dir);

/** Free a G2P handle. Safe to pass NULL. */
PIPER_PLUS_API void piper_plus_g2p_free(PiperPlusG2pHandle *handle);

/** Phonemize text without synthesis. language=NULL for auto-detect. */
PIPER_PLUS_API PiperPlusStatus piper_plus_g2p_phonemize(
    PiperPlusG2pHandle      *handle,
    const char              *text,
    const char              *language,
    PiperPlusPhonemeResult  *out_result);

/** Available language codes (e.g. "en,fr,ja,ko,es,pt,sv,zh"). BORROWED. */
PIPER_PLUS_API const char *piper_plus_g2p_available_languages(
    PiperPlusG2pHandle *handle);

/** Custom dictionary load (M4-1 互換)。Optional. */
PIPER_PLUS_API PiperPlusStatus piper_plus_g2p_load_custom_dict(
    PiperPlusG2pHandle *handle,
    const char         *dict_path);
```

**注**: 既存の engine ベース API (`piper_plus_phonemize`) は維持する。Kotlin AAR は新 API を呼ぶが、Dart FFI / Godot / Unity が既存 API を引き続き使えるようにする。

#### FR-CAPI-2: 内蔵言語 ID Mapping

`piper_plus_g2p_create()` は以下の language code を内部で解決可能とすること:

| language code | language ID | 備考 |
|--------------|------------|------|
| `ja` | 0 | OpenJTalk 辞書必須 |
| `en` | 1 | 内蔵 |
| `zh` | 2 | 内蔵 (loanword 込み) |
| `es` | 3 | 内蔵 (規則) |
| `fr` | 4 | 内蔵 (規則) |
| `pt` | 5 | 内蔵 (規則) |
| `ko` | (拡張) | 内蔵 (g2pk2 由来) |
| `sv` | (拡張) | 内蔵 (規則) |

ID は学習済 6lang モデルと一致させる (ja=0, en=1, zh=2, es=3, fr=4, pt=5)。ko/sv は 6lang モデル外なので拡張 ID を割り当てる (例: ko=6, sv=7)。

#### FR-CAPI-3: 既存 API と新 API の出力 byte 一致

同一テキスト・同一言語で `piper_plus_phonemize()` と `piper_plus_g2p_phonemize()` が返す phoneme 文字列が **byte-for-byte 一致** すること。

検証: `tests/fixtures/g2p/*.json` を共有 fixture として両 API で実行し diff 0 を CI gate に。

### 6.2 Kotlin パブリック API (`io.github.ayutaz:piper-plus-g2p-android`)

#### FR-API-1: クラス構成

以下の Kotlin 公開 API を提供すること (詳細シグネチャは設計書 §5.3 参照):

| API 要素 | 役割 |
|---------|------|
| `class PiperPlusG2p : AutoCloseable` | エントリクラス |
| `companion object PiperPlusG2p.create(context, dictionary?)` | ファクトリ |
| `fun phonemize(text: String, language: String? = null): PhonemeResult` | G2P 実行 |
| `fun availableLanguages(): List<String>` | 利用可能言語 |
| `fun loadCustomDict(path: String)` | カスタム辞書ロード |
| `data class PhonemeResult(phonemes: String, phonemeList: List<String>, language: String)` | G2P 結果 |
| `class PiperPlusG2pException : Exception` | エラー型 |
| `class OpenJTalkDictionary` (companion: `fromAssets`, `fromPath`) | 日本語辞書ハンドル |

#### FR-API-2: 命名規約

- Kotlin パッケージ: `com.piperplus.g2p` (既存 `com.piperplus` (TTS フル) との衝突回避)
- Maven coordinates: `io.github.ayutaz:piper-plus-g2p-android:VERSION`
- ファイル/クラス名: PascalCase、メソッド/プロパティ: camelCase
- 引数名: 他ランタイムと整合 (`text`, `language`, `dictionary`)

#### FR-API-3: スレッドセーフティ

- 全 `phonemize()` 呼び出しは `@Synchronized` で保護
- 内部 native handle は `volatile`、`close()` で `nativeHandle = 0L` に設定して以後の呼び出しを `IllegalStateException` で reject
- 複数インスタンスを別スレッドで使うのは安全

#### FR-API-4: AutoCloseable と use ブロック

```kotlin
PiperPlusG2p.create(context).use { g2p ->
    val result = g2p.phonemize("Hello world", "en")
    println(result.phonemes)
}  // close() 自動呼出
```

#### FR-API-5: エラー伝搬

- C API がエラーを返した場合は `PiperPlusG2pException(message)` を throw
- 引数バリデーション失敗は `IllegalArgumentException`
- close 後の操作は `IllegalStateException`

### 6.3 言語サポート

#### FR-LANG-1: 8 言語のサポート

以下の 8 言語の G2P を Kotlin から実行できること:

| code | 言語 | データ依存 | 動作要件 |
|------|------|----------|--------|
| `ja` | 日本語 | OpenJTalk 辞書 (~102 MB) | `OpenJTalkDictionary.fromAssets()` または `fromPath()` を渡す |
| `en` | 英語 | 内蔵 (g2p-en 由来データ、`.so` に static link) | デフォルトで動作 |
| `zh` | 中国語 (Mandarin) | 内蔵 (pypinyin 由来 + loanword JSON) | デフォルトで動作 |
| `ko` | 韓国語 | 内蔵 (g2pk2 由来 Hangul decomposition) | デフォルトで動作 |
| `es` | スペイン語 | 規則のみ (依存なし) | デフォルトで動作 |
| `fr` | フランス語 | 規則のみ | デフォルトで動作 |
| `pt` | ポルトガル語 | 規則のみ | デフォルトで動作 |
| `sv` | スウェーデン語 | 規則のみ | デフォルトで動作 |

#### FR-LANG-2: 言語自動検出

`phonemize(text, language=null)` のとき、`UnicodeLanguageDetector` (C++ 既存) で文字種から自動検出すること。検出結果は `PhonemeResult.language` で返す。

#### FR-LANG-3: ZH-EN code-switching

- 中国語コンテキストで隣接する英単語 (acronym/loanword) を Mandarin pinyin で発音する `MultilingualPhonemizer` の `[zh, en, zh]`/`[zh, en]`/`[en, zh]` パターン自動検出を Kotlin AAR でも有効にすること。
- 設定 toggle: `setZhEnDispatch(enabled: Boolean)` / `isZhEnDispatchEnabled(): Boolean`
- デフォルトは有効 (Issue #384 と整合)
- 内蔵 `zh_en_loanword.json` を `.so` に embed (`PIPER_PLUS_EMBEDDED_LOANWORD` flag、既存パターン)

### 6.4 辞書配布 (FR-DICT-*)

#### FR-DICT-1: AAR には日本語辞書を含めない

- AAR サイズ最適化のため、OpenJTalk 辞書 (~102 MB) は AAR に含めない
- 消費者アプリが以下のいずれかで辞書を提供:
  1. **App assets**: `assets/open_jtalk_dic/` に配置 → `OpenJTalkDictionary.fromAssets(context)` でロード
  2. **任意パス**: `OpenJTalkDictionary.fromPath(absolutePath)` で外部ストレージから
  3. **HF Hub DL**: `DictionaryDownloader.downloadFromHuggingFace(context, repo, onProgress)` (suspend)

#### FR-DICT-2: 辞書展開ロジック

- assets からの展開時、既存 `android/piper-plus/src/main/java/com/piperplus/PiperPlus.kt:80-146` のロジックと整合 (空ディレクトリチェックで再展開を回避)
- HF Hub DL は SHA-256 チェックサム検証を必須化

#### FR-DICT-3: 規則ベース言語の辞書不要保証

ES/PT/FR/SV/EN/ZH/KO は **辞書ファイル無しで動作** すること。`PiperPlusG2p.create(context)` (引数なし) で 7 言語が動く状態を担保。

### 6.5 Custom Dictionary

#### FR-DICT-CUSTOM-1: JSON 形式のカスタム辞書サポート

C API `piper_plus_load_custom_dict()` 互換の JSON 辞書を Kotlin から渡せること:

```kotlin
g2p.loadCustomDict("/path/to/custom_dict.json")
```

JSON v1.0 / v2.0 schema は既存 (`docs/spec/custom-dictionary-schema.toml` 等を参照、技術調査未確定で次フェーズで再確認)。

---

## 7. 非機能要件 (Non-Functional Requirements)

### 7.1 パフォーマンス

| ID | 要件 | 測定方法 | 合格ライン |
|----|------|--------|----------|
| **NFR-PERF-1** | phonemize レイテンシ (英語 100 文字) | Pixel 6 emulator API 34 で 100 回平均 | < 50ms |
| **NFR-PERF-2** | phonemize レイテンシ (日本語 100 文字、辞書ロード済) | 同上 | < 100ms |
| **NFR-PERF-3** | 初回起動 (`PiperPlusG2p.create()` 〜 phonemize 可) | cold start | < 2 秒 (ja 辞書展開除く) |
| **NFR-PERF-4** | 辞書展開時間 (assets → filesDir、~102MB) | Pixel 6 emulator | < 30 秒 |
| **NFR-PERF-5** | メモリ使用量 (引数言語 = en、phonemize 単発) | dumpsys meminfo | < 50 MB RSS |

### 7.2 互換性

| ID | 要件 |
|----|------|
| **NFR-COMPAT-1** | minSdk = 24 (Android 7.0+) |
| **NFR-COMPAT-2** | compileSdk = 35 |
| **NFR-COMPAT-3** | Kotlin 2.1.0+、Java 17+ |
| **NFR-COMPAT-4** | Android 15 (API 35) の 16 KB page size 対応 |
| **NFR-COMPAT-5** | Google Play 64bit 強制 (2019-08〜) — arm64-v8a を必須 ABI とする |

### 7.3 サイズ

| ID | 要件 |
|----|------|
| **NFR-SIZE-1** | AAR 単体サイズ (3 ABI バンドル、辞書除く) < 10 MB、目標 < 5 MB |
| **NFR-SIZE-2** | アプリ APK への寄与 (1 ABI、splits 適用後) < 4 MB |
| **NFR-SIZE-3** | 各 `.so` は strip + LTO 適用済 |

### 7.4 公開・配布 (NFR-PUB-*)

| ID | 要件 |
|----|------|
| **NFR-PUB-1** | タグ `kotlin-g2p-v*` push → Maven Central で検索可能になるまで < 30 分 |
| **NFR-PUB-2** | GPG 署名 (in-memory key) を全公開 artifact に適用 |
| **NFR-PUB-3** | groupId は `io.github.ayutaz` (DNS 検証不要、GitHub org namespace) |
| **NFR-PUB-4** | バージョン規則: SemVer (MAJOR.MINOR.PATCH)、Maven Central は immutable |
| **NFR-PUB-5** | PR 時に `--dry-run` (publishToMavenLocal) を CI gate に含める |
| **NFR-PUB-6** | リリースワークフローは既存 `g2p-rust-publish.yml` / `npm-publish.yml` パターンを踏襲 (タグ trigger / version check / dry-run) |

### 7.5 ライセンス・コンプライアンス

| ID | 要件 |
|----|------|
| **NFR-LICENSE-1** | AAR の効果ライセンス: MIT。同梱 third-party LICENSE は AAR の `META-INF/LICENSES/` 配下にバンドル |
| **NFR-LICENSE-2** | espeak-ng (GPL-3.0) を依存に持ち込まない |
| **NFR-LICENSE-3** | OpenJTalk naist-jdic (Modified BSD) は AAR 同梱しない (FR-DICT-1) ため、AAR ライセンスへの影響なし |
| **NFR-LICENSE-4** | F-Droid 配布対応: HF Hub DL 機能は Anti-Feature: "Non-Free Network Services" を明記してドキュメント化 |

### 7.6 セキュリティ

| ID | 要件 |
|----|------|
| **NFR-SEC-1** | カスタム辞書 JSON のパースで Path Traversal / JSON injection に対する入力検証 |
| **NFR-SEC-2** | HF Hub DL のチェックサム検証 (SHA-256) を必須化 |
| **NFR-SEC-3** | JNI 層で BORROWED ポインタ寿命誤認による use-after-free を起こさない (NewStringUTF コピー必須) |
| **NFR-SEC-4** | AddressSanitizer ビルドで実行時エラーゼロ (CI gate) |

### 7.7 国際化・ローカライズ

| ID | 要件 |
|----|------|
| **NFR-I18N-1** | UTF-8 / UTF-16 変換は JNI 層で適切に行う (PUA codepoint 保持) |
| **NFR-I18N-2** | Java String (UTF-16) から JNI に渡す際の surrogate pair 取扱 (PUA U+E020..U+E04A は BMP なので surrogate 不要) |
| **NFR-I18N-3** | エラーメッセージは英語固定 (i18n は将来課題) |

---

## 8. 制約条件 (Constraints)

| ID | 制約 | 根拠 |
|----|------|------|
| **CONSTRAINT-1** | 全 `.so` で `-Wl,-z,max-page-size=16384` 必須 | Android 15+ 16 KB page size 対応 |
| **CONSTRAINT-2** | Kotlin namespace は `com.piperplus.g2p` (既存 `com.piperplus` との衝突回避) | 既存 TTS フル AAR との両立 |
| **CONSTRAINT-3** | AAR は新規モジュール `android/piper-plus-g2p/` として独立配置 | 既存 `android/piper-plus/` とは別 artifact、同 settings.gradle 配下 |
| **CONSTRAINT-4** | C API ABI (PIPER_PLUS_API_VERSION 1) を破壊しない | 既存 Dart FFI / Godot / Unity 利用者への影響回避 |
| **CONSTRAINT-5** | mirror 数を増やさない (ZH-EN loanword JSON 等) | 既存 7 mirror + 6 fixture の同期コストを増やさず C API 経由で参照 |
| **CONSTRAINT-6** | Maven Central は immutable: 一度公開した version は取消不可 | バージョニング・署名運用を慎重に |
| **CONSTRAINT-7** | Gradle Managed Devices は KVM 必須 | GitHub Actions `ubuntu-24.04` runner で利用 |
| **CONSTRAINT-8** | Gradle / AGP / Kotlin バージョン: 既存 `android/build.gradle.kts` (AGP 8.7.3, Kotlin 2.1.0) と整合 | バージョン分岐の運用コスト回避 |
| **CONSTRAINT-CAPI-1** | 新 engine-less G2P API は既存 ABI と互換性を保つ (PIPER_PLUS_API_VERSION 1 内で追加) | FR-CAPI-1 から派生 |

---

## 9. テスト要件

### 9.1 5 層自動テスト (実機不要、CI 完結)

| 層 | コマンド | 目的 | 実行環境 |
|---|---------|------|---------|
| **L1** | `./gradlew :piper-plus-g2p:test` | Pure Kotlin unit (data class、入力バリデーション、URL ヘルパー) | GitHub Actions Linux |
| **L2** | `./gradlew :piper-plus-g2p:linuxTest` | JVM JNI smoke test (Linux .so をリンクして JNI シグネチャ整合性、メモリリーク検証) | GitHub Actions Linux |
| **L3** | `./gradlew :piper-plus-g2p:pixel6api34DebugAndroidTest` | Android instrumented test (Gradle Managed Devices で KVM emulator) | GitHub Actions Linux + KVM |
| **L4** | `./gradlew :piper-plus-g2p:parityTest` | Cross-runtime parity test (Python ランタイムと byte 一致) | GitHub Actions Linux |
| **L5** | `objdump -p` / `nm -D` script | ABI / 16 KB page size 検証 | GitHub Actions Linux |

### 9.2 テスト網羅率 (FR-TEST-*)

| ID | 要件 |
|----|------|
| **FR-TEST-1** | L4 で 8 言語 × 50 ケース以上の Python parity 検証、byte-for-byte 一致 |
| **FR-TEST-2** | L4 fixture には ZH-EN loanword、PUA codepoint、prosody features (A1/A2/A3)、SSML `<break>` を含める |
| **FR-TEST-3** | L1 で `data class` の `equals/hashCode/toString` カバー率 100% |
| **FR-TEST-4** | L3 で 3 つの辞書配布パターン (assets / fromPath / HF Hub DL モック) 全て PASS |
| **FR-TEST-5** | L5 で `align 2**14` (16 KB page size) を 3 ABI 全てで検証 |
| **FR-TEST-6** | フレーキー率 < 1% (10 回連続 PASS で merge 許可) |
| **FR-TEST-7** | CI 全体の wall-clock time < 30 分 |

### 9.3 サンプルアプリ動作確認

| ID | 要件 |
|----|------|
| **FR-TEST-SAMPLE-1** | `examples/android-g2p-sample/` を `./gradlew assembleDebug` で CI ビルド成功 |
| **FR-TEST-SAMPLE-2** | サンプルアプリは Compose UI、minSdk 24、8 言語タブ切り替え、TextField 入力 → phonemize → 結果表示 |
| **FR-TEST-SAMPLE-3** | カスタム辞書ロードと HF Hub からの辞書 DL デモを含む |

### 9.4 公開検証 (FR-TEST-PUB-*)

| ID | 要件 |
|----|------|
| **FR-TEST-PUB-1** | PR で `./gradlew publishToMavenLocal --dry-run` 成功 (実 publish せず) |
| **FR-TEST-PUB-2** | タグ push 後に `./gradlew :piper-plus-g2p:checkMavenCentralPublicationSignature` で GPG 署名検証 PASS |
| **FR-TEST-PUB-3** | バージョン乖離 (POM vs git tag) を検知する CI gate |

---

## 10. インターフェース要件

### 10.1 開発者向けインターフェース (Kotlin API)

設計書 §5.3 を要件として確定 (FR-API-1 で参照)。

### 10.2 ビルド・配布インターフェース

| 観点 | 仕様 |
|------|-----|
| Maven coordinates | `io.github.ayutaz:piper-plus-g2p-android:VERSION` |
| Gradle DSL | `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")` |
| Git tag | `kotlin-g2p-v{semver}` (例: `kotlin-g2p-v1.0.0`) |
| GitHub Actions trigger | `on: push: tags: ['kotlin-g2p-v*']` |
| 必要 GitHub Actions secrets | `MAVEN_CENTRAL_USERNAME`, `MAVEN_CENTRAL_PASSWORD`, `SIGNING_IN_MEMORY_KEY`, `SIGNING_IN_MEMORY_KEY_PASSWORD` |
| ビルド成果物パス (CI) | `android/piper-plus-g2p/build/outputs/aar/piper-plus-g2p-release.aar` |

### 10.3 ドキュメント要件

| ID | 要件 |
|----|------|
| **FR-DOCS-1** | `android/piper-plus-g2p/README.md`: クイックスタート、API リファレンス、辞書配布 3 パターン |
| **FR-DOCS-2** | `docs/guides/android-g2p-integration.md`: 詳細統合ガイド |
| **FR-DOCS-3** | `docs/guides/android-g2p-dictionary.md`: 辞書配布ガイド (assets / PAD / HF Hub DL の使い分け、F-Droid 制約) |
| **FR-DOCS-4** | dokka で javadoc 自動生成し Maven Central に同梱 |
| **FR-DOCS-5** | ルート `README.md` の「ランタイム別パッケージ」表に Kotlin/Android 行追加 |
| **FR-DOCS-6** | `CLAUDE.md` の「ランタイム別パッケージ」表に Kotlin/Android 行追加 |
| **FR-DOCS-7** | `CHANGELOG.md` の `## [Unreleased]` に追加 |

---

## 11. スコープ外 (Out of Scope)

明示的に本 Issue / 本ライブラリでは扱わない:

| 項目 | 理由 |
|------|------|
| TTS フル機能 (合成エンジン) の Kotlin AAR 化 | 既存 `android/piper-plus/` が別 issue で対応 |
| Android System TTS Engine 化 (`TextToSpeechService`) | サービスとアクティビティが必要、AAR 配布要件と直交 |
| iOS / KMP 対応 | iOS は xcframework + SPM で対応済 |
| Android Auto / Wear OS 専用最適化 | 別 issue で扱う |
| Voice Cloning (Speaker Encoder) の Kotlin API | C API 側が EXPERIMENTAL、本 issue では非対象 |
| Phoneme Timing 出力の Kotlin API | G2P 単独では timing 不要 (合成時の出力)、別 issue で扱う |
| SSML 完全パース | G2P レベルで必要な `<break>` のみ対応、`<prosody>` 等は要望次第 |
| Termux CLI 配布 | スコープ外 |
| ストリーミング phonemize (文単位 yield) | G2P 用途では一括処理で十分 |

---

## 12. 依存関係マトリクス

| 機能要件 | 依存する機能 | 依存する制約/技術 |
|--------|-----------|--------------|
| FR-CAPI-1 | — (新規) | CONSTRAINT-CAPI-1 (ABI 互換性) |
| FR-CAPI-2 | FR-CAPI-1 | 6lang モデル language ID 整合 |
| FR-API-1 | FR-CAPI-1 | JNI bridge 完成 |
| FR-LANG-1 (ja) | FR-API-1, FR-DICT-1 | OpenJTalk 辞書ロードロジック |
| FR-LANG-3 (ZH-EN) | FR-CAPI-1 | `PIPER_PLUS_EMBEDDED_LOANWORD` flag |
| FR-DICT-1 | FR-API-1 | `OpenJTalkDictionary` クラス |
| L3 (instrumented) | FR-API-1 | Gradle Managed Devices (CONSTRAINT-7) |
| L4 (parity) | FR-CAPI-3 | `tests/fixtures/g2p/*.json` 共有 fixture |
| 公開自動化 | NFR-PUB-1〜6 | vanniktech plugin、GitHub secrets |

---

---

## 13. 関連ドキュメント

- [kotlin-g2p-design.md](kotlin-g2p-design.md) — 設計書 (本書の親)
- [src/cpp/piper_plus.h](../../src/cpp/piper_plus.h) — C API ヘッダ (445 行)
- [src/cpp/piper_plus_c_api.cpp](../../src/cpp/piper_plus_c_api.cpp) — C API 実装
- [android/piper-plus/](../../android/) — 既存 TTS フル AAR 草案
- [.github/workflows/android-build.yml](../../.github/workflows/android-build.yml) — Android NDK ビルド CI
- [docs/spec/ios-shared-lib.md](ios-shared-lib.md) — iOS shared lib 設計 (xcframework パターン参考)
- [docs/spec/zh-en-loanword-runtime-rollout.md](zh-en-loanword-runtime-rollout.md) — クロスランタイム同期パターン
- [docs/spec/pua-contract.toml](pua-contract.toml) — PUA codepoint 仕様
- [Issue #388](https://github.com/ayutaz/piper-plus/issues/388) — 親 Issue

---

<!-- 改訂履歴は git log に統合 (実装完了に伴い削除、2026-05-08) -->

