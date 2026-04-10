# HTS Voice 依存の除去

## 目的

piper-plus は VITS ニューラル TTS エンジンであり、音声合成に HTS voice (`.htsvoice`) ファイルを使用しない。
しかし歴史的経緯から、OpenJTalk 連携部分に HTS voice への依存が残存している。

本ドキュメントでは各依存箇所の依存構造・実装変更・影響範囲・テスト網羅性を詳細にまとめる。

## 背景

OpenJTalk は本来「テキスト → フルコンテキストラベル → HTS 音声合成」のパイプラインを持つ。
piper-plus が必要とするのは前半の「テキスト → フルコンテキストラベル（音素列）」のみであり、
HTS 音声合成は一切使わない。

現状、ビルドシステムでは HTS Engine を**スタブ化済み** (`USE_HTS_ENGINE_STUB=ON` がデフォルト) であり、
ランタイムでも phonemizer バイナリがメインパスとして使用されている。
残存する HTS voice 依存はすべて **フォールバック/dead code** である。

---

## 依存箇所一覧

| # | 領域 | 依存度 | 依存の性質 |
|---|------|--------|-----------|
| 1 | C++ ランタイム | 低 | ランタイム・オプショナル: `open_jtalk` バイナリフォールバック時のみ |
| 2 | WASM G2P (`@piper-plus/g2p`) | 中 | API 契約 + データフロー: voice パスが API に組み込まれているが内部未使用 |
| 3 | openjtalk-web (npm `piper-plus`) | 高 | テスト/ビルドインフラ: テスト・ビルドスクリプトが voice ファイル前提 |
| 4 | CI / CMake | 低 | テスト環境セットアップ: voice ファイル DL。なくてもスキップで動作 |
| 5 | Python / Rust / C# / Go | なし | 依存なし |

---

## 依存箇所 1: C++ ランタイム

### 1.1 依存の構造

#### `openjtalk_dictionary_manager.c` — voice パス検索

**依存の性質:** ランタイム・オプショナル。voice ファイルが見つからなくても NULL を返すだけ。

```
get_openjtalk_voice_path() の検索順序:
  1. 環境変数 OPENJTALK_VOICE (access() で存在確認)
  2. /usr/share/hts-voice/nitech-jp-atr503-m001/nitech_jp_atr503_m001.htsvoice
  3. /usr/local/share/hts-voice/...
  4. /opt/homebrew/share/hts-voice/...
  → 全て見つからない場合 NULL を返す
```

**関連コード:**

| ファイル | 行 | 内容 |
|---------|-----|------|
| `openjtalk_dictionary_manager.c` | L30-35 | `HTS_VOICE_URL`, `HTS_VOICE_FILENAME` 等の `#define` |
| `openjtalk_dictionary_manager.c` | L441-464 | `get_openjtalk_voice_path()` 関数本体 |
| `openjtalk_dictionary_manager.c` | L466-603 | `#if 0` で無効化済みの HTS voice DL コード |
| `openjtalk_dictionary_manager.h` | L12 | `get_openjtalk_voice_path()` 関数宣言 |

#### `openjtalk_wrapper.c` — コマンド構築での voice 使用

**依存の性質:** ランタイム・オプショナル。phonemizer バイナリ優先、open_jtalk バイナリはフォールバック。

**バイナリ検索順序 (L122-153):**
```
1. open_jtalk_phonemizer (優先) → HTS voice 不要
2. open_jtalk (フォールバック) → voice があれば -m <voice> を付与、なくても動作
```

**voice 使用箇所:**

| 関数 | 行 | voice の使われ方 |
|------|-----|-----------------|
| `openjtalk_text_to_phonemes()` | L406-432 | `open_jtalk -m <voice>` フォールバック |
| `openjtalk_text_to_phonemes_with_prosody_binary()` | L715-737 | 同上 (prosody 取得版) |

**コマンド構築の分岐 (L406-432):**
```c
if (is_phonemizer) {
    // phonemizer パス: HTS voice 不要
    snprintf(command, ..., "%s -x %s -ot %s %s", ...);
} else {
    // open_jtalk フォールバック: voice があれば使う
    const char* voice_path = get_openjtalk_voice_path();
    if (voice_path) {
        snprintf(command, ..., "%s -x %s -m %s -ow /dev/null -ot %s %s", ...);
    } else {
        snprintf(command, ..., "%s -x %s -ow /dev/null -ot %s %s", ...);
    }
}
```

#### `openjtalk_optimized.c` — ストリーミングパスでの voice 使用

**依存の性質:** wrapper.c と同一パターン。パイプベースのストリーミング処理。

| 関数 | 行 | voice の使われ方 |
|------|-----|-----------------|
| `execute_with_pipes_unix()` | L242-256 | `execlp()` で `-m <voice>` 付与 |
| `execute_with_pipes_windows()` | L386-403 | `CreateProcess()` で `-m <voice>` 付与 |

#### `openjtalk_api.c` — C API (参考: 依存なし)

**voice 依存なし。** `openjtalk_initialize()` は引数なしで MeCab 辞書のみ使用。
NJD + JPCommon パイプラインのみで音素化が完結する。

### 1.2 実装変更

#### 変更 A: `openjtalk_dictionary_manager.c` — 関数・定数の削除

**削除対象:**

| 行 | 内容 | 変更 |
|----|------|------|
| L30-35 | `#define HTS_VOICE_URL` 等 6 定数 | 削除 |
| L441-464 | `get_openjtalk_voice_path()` 関数 | 削除 |
| L466-603 | `#if 0` の DL コード | 削除 |

**削除行数:** ~170行

#### 変更 B: `openjtalk_dictionary_manager.h` — 宣言削除

```diff
- // Get the path to the HTS voice file
- const char* get_openjtalk_voice_path();
```

#### 変更 C: `openjtalk_wrapper.c` — フォールバック分岐の簡素化

**2 箇所 (L406-432, L715-737) を同一パターンで変更:**

Before:
```c
if (is_phonemizer) {
    snprintf(command, ..., "\"%s\" -x \"%s\" -ot \"%s\" \"%s\"",
             openjtalk_bin, dic_path, output_file, input_file);
} else {
    const char* voice_path = get_openjtalk_voice_path();
    if (voice_path) {
        snprintf(command, ..., "\"%s\" -x \"%s\" -m \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
                 openjtalk_bin, dic_path, voice_path, output_file, input_file);
    } else {
        snprintf(command, ..., "\"%s\" -x \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
                 openjtalk_bin, dic_path, output_file, input_file);
    }
}
```

After:
```c
if (is_phonemizer) {
    snprintf(command, ..., "\"%s\" -x \"%s\" -ot \"%s\" \"%s\"",
             openjtalk_bin, dic_path, output_file, input_file);
} else {
    // open_jtalk fallback: voice なしで phoneme extraction のみ
    snprintf(command, ..., "\"%s\" -x \"%s\" -ow /dev/null -ot \"%s\" \"%s\"",
             openjtalk_bin, dic_path, output_file, input_file);
}
```

**削除行数:** ~30行 (2 箇所合計)

#### 変更 D: `openjtalk_optimized.c` — ストリーミングパスの簡素化

**Unix パス (L242-256):**

Before:
```c
if (is_phonemizer) {
    execlp(openjtalk_bin, openjtalk_bin, "-x", dic_path, "-ot", "/dev/stdout", "/dev/stdin", NULL);
} else {
    const char* voice_path = get_openjtalk_voice_path();
    if (voice_path) {
        execlp(openjtalk_bin, ..., "-m", voice_path, "-ow", "/dev/null", ...);
    } else {
        execlp(openjtalk_bin, ..., "-ow", "/dev/null", ...);
    }
}
```

After:
```c
if (is_phonemizer) {
    execlp(openjtalk_bin, openjtalk_bin, "-x", dic_path, "-ot", "/dev/stdout", "/dev/stdin", NULL);
} else {
    execlp(openjtalk_bin, openjtalk_bin, "-x", dic_path,
           "-ow", "/dev/null", "-ot", "/dev/stdout", "/dev/stdin", NULL);
}
```

Windows パス (L386-403) も同一パターンで簡素化。

**削除行数:** ~30行 (Unix + Windows)

### 1.3 影響範囲

| 影響 | 詳細 |
|------|------|
| API 破壊 | `get_openjtalk_voice_path()` の削除。外部から呼ぶコードがあればコンパイルエラー |
| 内部呼び出し元 | `openjtalk_wrapper.c` (2 箇所)、`openjtalk_optimized.c` (2 箇所) — 同時に変更 |
| 動作変更 | `open_jtalk` フォールバック時に `-m <voice>` が付かなくなる。音素抽出自体は影響なし |
| 環境変数 | `OPENJTALK_VOICE` が意味を持たなくなる |

### 1.4 既存テストの状況

#### テスト済みの範囲

| テストファイル | テスト名 | voice 関連 | 状況 |
|--------------|---------|-----------|------|
| `test_openjtalk_optimized.cpp` | `BasicConversion` | 間接的 | voice なしでも GTEST_SKIP で通過 |
| `test_openjtalk_optimized.cpp` | `PerformanceComparison` | なし | voice 無関係 |
| `test_openjtalk_optimized.cpp` | `ConcurrentAccess` | なし | voice 無関係 |
| `test_openjtalk_optimized.cpp` | `CacheEviction` | なし | voice 無関係 |
| `test_dictionary_manager.cpp` | `HTSVoicePath` (L263-280) | **直接** | ダミー voice ファイル作成するが `get_openjtalk_voice_path()` を呼ばない不完全テスト |

#### テストされていない範囲

**voice 除去後に必要なテスト:**

| テスト名 | 目的 | アサーション |
|---------|------|------------|
| `test_phonemize_without_voice` | voice なしで音素抽出が成功することを確認 | `openjtalk_text_to_phonemes("テスト")` が非 NULL を返す |
| `test_optimized_streaming_without_voice` | ストリーミングパスが voice なしで動作することを確認 | `openjtalk_text_to_phonemes_optimized("テスト")` が有効な音素列を返す |
| `test_command_without_voice_flag` | 構築されるコマンドに `-m` が含まれないことを確認 | コマンド文字列に `-m` が存在しない |

**実装方針:** `test_openjtalk_optimized.cpp` に追加。既存テストが `openjtalk_is_available()` でスキップ判定する仕組みを流用。

```cpp
TEST_F(OpenJTalkOptimizedTest, PhonemeExtractionWithoutVoice) {
    // OPENJTALK_VOICE を未設定にして phonemize が成功することを確認
    unsetenv("OPENJTALK_VOICE");
    auto result = openjtalk_text_to_phonemes_optimized("こんにちは");
    if (!result) {
        GTEST_SKIP() << "OpenJTalk binary not available";
    }
    EXPECT_NE(std::string(result), "");
    // 有効な音素パターンが含まれることを確認
    EXPECT_THAT(std::string(result), ::testing::HasSubstr("k"));
}
```

---

## 依存箇所 2: WASM G2P (`@piper-plus/g2p`)

### 2.1 依存の構造

#### `ja/index.js` — JapaneseG2P クラス

**依存の性質:** API 契約。`initialize()` が voiceData を必須として要求する。

**データフロー:**
```
コンストラクタ({ jaDict: { dictData, voiceData } })
  └→ initialize()
       ├→ _loadDict(dict)
       │    ├→ dictData 検証 + 書き込み (必須・機能的)
       │    └→ voiceData 検証 + 書き込み (必須だが未使用)
       └→ _openjtalk_initialize(dictPtr, voicePtr)
            └→ WASM 側: voice_path を受け取るが無視 (return 0)
```

**voice が関わるコード:**

| 行 | コード | 実際の動作 |
|----|--------|-----------|
| L90 | `const voicePtr = mod.allocateUTF8('/voice/voice.htsvoice')` | WASM メモリにパス文字列確保 |
| L91 | `mod._openjtalk_initialize(dictPtr, voicePtr)` | 2引数で呼び出し (voice は無視される) |
| L93 | `mod._free(voicePtr)` | メモリ解放 |
| L179-181 | `if (!dictData \|\| !voiceData) throw Error(...)` | voiceData が必須バリデーション |
| L187-189 | `if (!(voiceData instanceof ArrayBuffer)) throw Error(...)` | 型バリデーション |
| L199 | `try { mod.FS.mkdir('/voice'); } catch (_) {}` | ディレクトリ作成 |
| L205 | `mod.FS.writeFile('/voice/voice.htsvoice', ...)` | WASM FS に voice 書き込み |

#### `dict-loader.js` — DictLoader クラス

**依存の性質:** オプショナル機能。`includeVoice` はデフォルト `false`。

| 行 | コード | 動作 |
|----|--------|------|
| L50-52 | `DEFAULT_VOICE_URL = 'https://huggingface.co/...'` | voice DL 先 URL |
| L54 | `VOICE_CACHE_KEY = 'voice/mei_normal.htsvoice'` | IndexedDB キャッシュキー |
| L362 | `const includeVoice = options.includeVoice \|\| false` | フラグ判定 |
| L390-409 | voice DL + キャッシュロジック | includeVoice=true 時のみ実行 |

**DictLoader の返り値:**
```javascript
// includeVoice=false (デフォルト): { dictFiles }         — voice なし
// includeVoice=true:               { dictFiles, voiceData } — voice あり
```

#### `types/index.d.ts` — 型定義

| 行 | 型 | 内容 |
|----|-----|------|
| L210 | `voiceData?: ArrayBuffer` | JaDictData の optional プロパティ |
| L222 | `includeVoice?: boolean` | DictLoadOptions |
| L227 | `voiceUrl?: string` | カスタム voice URL |

#### WASM C/C++ レイヤー

**`simple_wrapper.cpp`:**
```cpp
EMSCRIPTEN_KEEPALIVE
int openjtalk_initialize(const char* dic_dir, const char* voice_path) {
    return 0;  // スタブ: voice_path を完全に無視
}
```

**`phonemizer_wrapper.cpp` (L106-108):**
```cpp
int phonemizer_initialize_openjtalk(const char* dict_dir, const char* voice_path) {
    return openjtalk_initialize(dict_dir, voice_path);  // 転送するだけ
}
```

**C API (`openjtalk_api.c`):** `openjtalk_initialize()` は引数なし。voice パラメータは存在しない。

### 2.2 実装変更

#### 変更 A: `ja/index.js` — voice 関連コードの削除

```diff
 // initialize() メソッド内
 const dictPtr = mod.allocateUTF8('/dict');
-const voicePtr = mod.allocateUTF8('/voice/voice.htsvoice');
-const result = mod._openjtalk_initialize(dictPtr, voicePtr);
+const result = mod._openjtalk_initialize(dictPtr);
 mod._free(dictPtr);
-mod._free(voicePtr);
```

```diff
 // _loadDict() メソッド内
-const { dictData, voiceData } = dict;
-if (!dictData || !voiceData) {
-    throw new Error('jaDict must have { dictData, voiceData }.');
-}
-if (!(voiceData instanceof ArrayBuffer)) {
-    throw new Error('voiceData must be an ArrayBuffer.');
-}
+const { dictData } = dict;
+if (!dictData) {
+    throw new Error('jaDict must have { dictData: { [filename]: ArrayBuffer } }.');
+}

 try { mod.FS.mkdir('/dict'); } catch (_) {}
-try { mod.FS.mkdir('/voice'); } catch (_) {}

 for (const file of DICT_FILE_NAMES) {
     mod.FS.writeFile(`/dict/${file}`, new Uint8Array(dictData[file]));
 }
-mod.FS.writeFile('/voice/voice.htsvoice', new Uint8Array(voiceData));
```

#### 変更 B: `dict-loader.js` — voice DL ロジックの削除

```diff
-const DEFAULT_VOICE_URL =
-  'https://huggingface.co/ayousanz/piper-plus-base/resolve/main/voice/mei_normal.htsvoice';
-const VOICE_CACHE_KEY = 'voice/mei_normal.htsvoice';
```

```diff
 // loadJaDict() メソッド内
-const includeVoice = options.includeVoice || false;
-const voiceUrl = options.voiceUrl || DEFAULT_VOICE_URL;

-if (!includeVoice) {
-    return { dictFiles };
-}
-
-let voiceData;
-const cachedVoice = await this._getFromCache(db, VOICE_CACHE_KEY);
-if (cachedVoice) {
-    voiceData = cachedVoice;
-} else {
-    voiceData = await fetchWithProgress(voiceUrl, onProgress);
-    await this._putToCache(db, VOICE_CACHE_KEY, voiceData);
-}
-
-return { dictFiles, voiceData };
+return { dictFiles };
```

#### 変更 C: `types/index.d.ts` — 型定義の更新

```diff
 export interface JaDictData {
     dictFiles: Record<string, ArrayBuffer>;
-    voiceData?: ArrayBuffer;
 }

 export interface DictLoadOptions {
-    includeVoice?: boolean;
-    voiceUrl?: string;
     onProgress?: (progress: { loaded: number; total: number }) => void;
 }
```

#### 変更 D: WASM ラッパー — voice_path パラメータ削除

**`simple_wrapper.cpp`:**
```diff
 EMSCRIPTEN_KEEPALIVE
-int openjtalk_initialize(const char* dic_dir, const char* voice_path) {
+int openjtalk_initialize(const char* dic_dir) {
     return 0;
 }
```

**`phonemizer_wrapper.cpp`:**
```diff
-int phonemizer_initialize_openjtalk(const char* dict_dir, const char* voice_path) {
-    return openjtalk_initialize(dict_dir, voice_path);
+int phonemizer_initialize_openjtalk(const char* dict_dir) {
+    return openjtalk_initialize(dict_dir);
 }
```

### 2.3 影響範囲

| 影響 | 詳細 |
|------|------|
| npm 公開 API 破壊 | `JapaneseG2P` の `jaDict` から `voiceData` が不要に。既存コードで `includeVoice: true` を使用している場合は修正が必要 |
| DictLoader API | `includeVoice`, `voiceUrl` オプション削除 |
| WASM ABI | `_openjtalk_initialize` のパラメータ数が 2→1 に変更 |
| 下流の PiperPlus クラス | `src/wasm/openjtalk-web/src/index.js` — `jaDict` を JapaneseG2P に渡す箇所。voice なしの dict を渡すだけなので**変更不要** |
| Rust WASM | `piper-wasm` — HTS voice に一切依存しない。**影響なし** |

**破壊的変更の緩和策:**

| 戦略 | 内容 |
|------|------|
| **即時除去** | voiceData を渡すコードはコンパイル/実行時エラー。マイナーバージョンアップで対応 |
| **段階的移行** | Phase 1: voiceData を受け取るが無視 + 非推奨警告。Phase 2: 完全削除 |

### 2.4 既存テストの状況

#### テスト済みの範囲

| テストファイル | 内容 | voice 関連 |
|--------------|------|-----------|
| `src/wasm/g2p/test/test-g2p-contract.js` | JapaneseG2P コンストラクタ契約テスト | voice 不使用 (コンストラクタのみ) |
| `src/wasm/g2p/test/test-g2p.js` | G2P.create テスト | SKIP (WASM 必要) |
| `src/wasm/g2p/test/test-g2p-integration.js` | 全非 JA 言語テスト | JA を除外しているため無関係 |

#### テストされていない範囲

**voice 関連テストは一切存在しない:**
- `includeVoice: true` のテストなし
- voiceData バリデーションのテストなし
- WASM ラッパーの引数テストなし
- voice ファイル書き込みのテストなし

**voice 除去後に必要なテスト:**

| テスト名 | 目的 | 実装先 |
|---------|------|-------|
| `JapaneseG2P initializes with dictFiles only` | voiceData なしで初期化成功を確認 | `test-g2p-contract.js` に追加 |
| `JapaneseG2P rejects missing dictData` | dictData なしでエラーを確認 | `test-g2p-contract.js` に追加 |
| `JapaneseG2P ignores voiceData if provided` | 後方互換: voiceData を渡しても無視 (段階的移行時) | `test-g2p-contract.js` に追加 |
| `DictLoader returns dictFiles without voiceData` | loadJaDict() の返り値に voiceData がないことを確認 | `test-dict-loader.js` (新規) |
| `WASM initialize accepts single parameter` | WASM ABI の引数変更を確認 | `test-wasm-wrapper.js` (新規) |

**実装例:**

```javascript
// test-g2p-contract.js に追加
describe('JapaneseG2P voice-free initialization', () => {
    it('should accept jaDict without voiceData', () => {
        const mockDict = {
            dictData: {
                'char.bin': new ArrayBuffer(10),
                'matrix.bin': new ArrayBuffer(10),
                'sys.dic': new ArrayBuffer(10),
                'unk.dic': new ArrayBuffer(10),
                'left-id.def': new ArrayBuffer(10),
                'pos-id.def': new ArrayBuffer(10),
                'rewrite.def': new ArrayBuffer(10),
                'right-id.def': new ArrayBuffer(10),
            }
        };
        const ja = new JapaneseG2P({ jaDict: mockDict });
        assert.ok(ja);
    });

    it('should throw when dictData is missing', () => {
        const ja = new JapaneseG2P({ jaDict: {} });
        const mockModule = {
            FS: { mkdir: () => {}, writeFile: () => {} },
            allocateUTF8: () => 1,
            _free: () => {},
            _openjtalk_initialize: () => 0
        };
        assert.throws(() => ja._loadDict({}), /dictData/);
    });
});
```

---

## 依存箇所 3: openjtalk-web (npm `piper-plus` パッケージ)

### 3.1 依存の構造

**依存の性質:** テスト/ビルドインフラストラクチャ。プロダクションコードには依存なし。

**メインエントリーポイント `src/index.js` (PiperPlus クラス):** HTS voice への参照なし。
ONNX モデル + Rust WASM G2P で完結。npm 配布物にも `.htsvoice` は含まれない。

#### テスト・ビルドスクリプトの voice 使用

全ファイルが voice ファイルを**ロードするが、音声合成には使わない**。
`openjtalk_initialize()` がスタブ (`return 0`) であるため、voice は WASM FS に書き込まれるだけで参照されない。

| ファイル | voice の使い方 | 実際の機能 |
|---------|---------------|-----------|
| `test/test-cli.js` (L109-128) | `loadVoiceFile()` で WASM FS に書き込み | dead code |
| `test/test-cli.mjs` (L114-133) | 同上 (ESM 版) | dead code |
| `test/test-headless.js` (L166-177) | fetch → WASM FS に書き込み | dead code |
| `test/test-node-simple.js` (L31) | voice パスを initialize に渡す | dead code |
| `test/quick-test.py` (L57) | voice ファイル存在チェック | 検証スクリプト |
| `test/pre-check.sh` (L89) | voice ファイル存在チェック | 検証スクリプト |
| `test/verify-build.sh` (L42) | voice ファイル存在チェック | 検証スクリプト |
| `test/test-simple-node.js` (L53) | voice ファイルサイズ確認 | 検査スクリプト |
| `dist/simple-test.html` (L123-126) | voice パスで initialize | デモ HTML |
| `prepare-assets.sh` (L28-35) | `mei_normal.htsvoice` をアセットにコピー | ビルドスクリプト |
| `prepare-dictionary.sh` (L37-49) | voice ディレクトリ作成 + ファイルコピー | ビルドスクリプト |
| `assets/assets.json` (L16-22) | `"voices"` メタデータ | 設定ファイル |

### 3.2 実装変更

#### 変更 A: ビルドスクリプト

**`prepare-assets.sh`** — voice コピーセクション削除 (L28-35):
```diff
-# Copy voice files
-echo "Copying voice files..."
-if [ -f "$REFERENCE_DIR/etc/mei/mei_normal.htsvoice" ]; then
-    cp "$REFERENCE_DIR/etc/mei/mei_normal.htsvoice" "$ASSETS_DIR/"
-else
-    echo "Warning: Voice file not found in reference repository"
-fi
```

**`prepare-dictionary.sh`** — voice セクション削除 (L37-49) + assets.json 更新:
```diff
-VOICE_DIR="$ASSETS_DIR/voice"
-mkdir -p "$VOICE_DIR"
-if [ -d "$WASM_OPEN_JTALK_DIR/etc/mei" ]; then
-    cp "$WASM_OPEN_JTALK_DIR/etc/mei/"*.htsvoice "$VOICE_DIR/" || true
-else
-    echo "MEI voice files not found."
-fi
```

assets.json 生成部分:
```diff
   "files": [...]
-  },
-  "voices": {
-    "mei_normal": {
-      "name": "MEI Normal",
-      "file": "mei_normal.htsvoice",
-      "language": "ja"
-    }
   }
```

**`assets/assets.json`** — voices オブジェクト削除 (L16-22)

#### 変更 B: テストファイル (6 ファイル)

**`test-cli.js`:**
- `loadVoiceFile()` 関数全体を削除 (L109-128)
- `loadVoiceFile(Module)` の呼び出しを削除 (L236)
- `initializeOpenJTalk()` から voicePtr 関連を削除 (L133-134)

**`test-cli.mjs`:**
- 同上パターン (L114-133, L351)

**`test-headless.js`:**
- voice fetch + FS 書き込みセクション削除 (L166-177)

**`test-node-simple.js`:**
- voice パス参照を削除 (L31)

**`test-simple-node.js`:**
- voice ファイルサイズ確認を削除 (L53-60)

**`dist/simple-test.html`:**
- voice パスの initialize 引数を削除 (L123-126)

#### 変更 C: 検証スクリプト (3 ファイル)

**`verify-build.sh`:** voice ファイルチェック削除 (L42)
**`pre-check.sh`:** voice ファイルチェック削除 (L89)
**`quick-test.py`:** required_files から voice パス削除 (L57)

### 3.3 影響範囲

| 影響 | 詳細 |
|------|------|
| npm パッケージ本体 | **影響なし** — `src/index.js` (PiperPlus) は voice 無関係 |
| npm 配布物 | **影響なし** — `.htsvoice` は配布に含まれていない |
| テスト実行 | テスト成功率は変わらない (voice は dead code だったため) |
| ビルドパイプライン | アセット準備が簡素化される |

### 3.4 既存テストの状況

#### テスト済みの範囲

全テストが voice **なしで** 機能する。テストが検証しているのは:
- WASM モジュールのロードと関数エクスポート
- 辞書ファイルの WASM FS へのロード
- `openjtalk_synthesis_labels()` による音素ラベル生成
- パフォーマンス測定

#### テストされていない範囲

**voice 除去後に必要なテスト:**

| テスト名 | 目的 | 実装先 |
|---------|------|-------|
| `assets.json has no voices section` | ビルド成果物に voice メタデータがないことを確認 | CI ステップまたは `verify-build.sh` に追加 |
| `initialize succeeds without voice path` | WASM initialize が dict のみで成功することを確認 | `test-cli.js` の既存テストが暗黙的にカバー |

**実装例 (verify-build.sh に追加):**
```bash
# Voice files should NOT be present
if [ -d "assets/voice" ] && [ "$(find assets/voice -type f | wc -l)" -gt 0 ]; then
    echo "FAIL: Voice files found in assets/voice (should be removed)"
    FAILED=1
fi

# assets.json should not contain voices section
if grep -q '"voices"' assets/assets.json 2>/dev/null; then
    echo "FAIL: assets.json still contains voices section"
    FAILED=1
fi
```

---

## 依存箇所 4: CI / CMake

### 4.1 依存の構造

#### CI ワークフロー `_build-test-cpp.yml`

**依存の性質:** テスト環境セットアップ。ソフトオプショナル (なくてもテスト通過)。

| 行 | 内容 | 依存の性質 |
|----|------|-----------|
| L50 | `apt-get install hts-voice-nitech-jp-atr503-m001` | パッケージインストール (Ubuntu のみ) |
| L234-261 | voice ファイル検索 + SourceForge DL | ランタイム環境構築 |
| L268-269 | `OPENJTALK_VOICE` 環境変数設定 | テスト用 |
| L275 | `OPENJTALK_SKIP_TESTS_IF_UNAVAILABLE=1` | テストスキップフラグ |

**テストの動作:**
```
OPENJTALK_VOICE が設定されている場合:
  → open_jtalk が -m <voice> 付きで実行される (フォールバック時)
  
OPENJTALK_VOICE が未設定の場合:
  → openjtalk_is_available() が false を返す可能性
  → GTEST_SKIP() でテストがスキップされる
  → テスト自体は PASS (スキップ)
```

#### CMake ビルドシステム

**HTS Engine stub (デフォルト):**

| ファイル | 内容 |
|---------|------|
| `cmake/ExternalDeps.cmake` L92-140 | `USE_HTS_ENGINE_STUB=ON` (デフォルト) でスタブライブラリを構築 |
| `cmake/hts_engine_stub.h` | HTS Engine API 1.10 の最小型宣言。OpenJTalk ヘッダーの型参照を満たす |
| `cmake/hts_engine_stub.c` | 全関数が no-op またはエラー終了。合成関数は呼ばれたら `exit(1)` |

**実 HTS Engine (オプション):**

| ファイル | 内容 |
|---------|------|
| `cmake/ExternalDeps.cmake` L141-191 | `USE_HTS_ENGINE_STUB=OFF` 時に実 HTS Engine をビルド |
| `cmake/HTSEngine_CMakeLists.txt` | Windows 用 HTS Engine ビルド設定 |

**リンク構成:**

| ファイル | 行 | 内容 |
|---------|-----|------|
| `cmake/PiperLink.cmake` L57-89 | piper / test_piper に hts_engine をリンク |
| `cmake/PiperPlusShared.cmake` L102-110 | 共有ライブラリに hts_engine をリンク |
| `src/cpp/tests/CMakeLists.txt` L25-34 | テスト実行可能ファイルに hts_stub をリンク |

**重要:** テストは全て `hts_engine_stub` でビルドされている。実 HTS Engine を使うテストは存在しない。

#### サンプルスクリプト

**`examples/test_japanese_tts.sh`:**
- HTS voice を SourceForge から DL (L24-31)
- `open_jtalk -m nitech_jp_atr503_m001.htsvoice` で実行 (L43)
- `OPENJTALK_VOICE` を設定 (L54)
- phonemizer アプローチと互換性なし

### 4.2 実装変更

#### 変更 A: CI ワークフロー `_build-test-cpp.yml`

**apt パッケージ (L50):**
```diff
 sudo apt-get install -y \
-  build-essential cmake ccache wget open-jtalk \
-  hts-voice-nitech-jp-atr503-m001
+  build-essential cmake ccache wget open-jtalk
```

**voice 検索・DL ブロック (L234-273):**
```diff
-# Find HTS voice file (needed by open_jtalk binary)
-VOICE_FOUND=""
-for vp in \
-  "/usr/share/hts-voice/..." \
-  "/usr/local/share/hts-voice/..." \
-  "/opt/homebrew/share/hts-voice/..."; do
-  if [ -f "$vp" ]; then VOICE_FOUND="$vp"; break; fi
-done
-if [ -z "$VOICE_FOUND" ]; then
-  echo "HTS voice not found on system, downloading from SourceForge..."
-  ...DL と展開ロジック (~20行)...
-fi
-if [ -n "$VOICE_FOUND" ]; then
-  export OPENJTALK_VOICE="$VOICE_FOUND"
-else
-  echo "Warning: HTS voice not available"
-fi
+# HTS voice is no longer required (phonemizer-only mode)
```

**環境変数ログ (L287):**
```diff
-echo "OpenJTalk env: DICTIONARY_PATH=$OPENJTALK_DICTIONARY_PATH VOICE=${OPENJTALK_VOICE:-<unset>}"
+echo "OpenJTalk env: DICTIONARY_PATH=$OPENJTALK_DICTIONARY_PATH"
```

#### 変更 B: CMake — `USE_HTS_ENGINE_STUB=OFF` パスの廃止

**`cmake/ExternalDeps.cmake` L141-191:**
```diff
-else()
-  # Build real HTS Engine from source
-  ...50行の ExternalProject_Add...
-endif()
+else()
+  message(FATAL_ERROR
+    "USE_HTS_ENGINE_STUB=OFF is no longer supported. "
+    "piper-plus uses neural network synthesis (ONNX), not HTS Engine.")
+endif()
```

**stub と stub の参照コードは維持** (OpenJTalk ヘッダーが HTS 型を要求するため)。

#### 変更 C: サンプルスクリプト

**`examples/test_japanese_tts.sh`** — 削除または phonemizer ベースに書き換え。

### 4.3 影響範囲

| 影響 | 詳細 |
|------|------|
| CI ビルド時間 | 短縮 (voice DL ~50MB の削除) |
| テスト結果 | 変化なし (テストは既に voice なしで通過可能) |
| `USE_HTS_ENGINE_STUB=OFF` ユーザー | FATAL_ERROR。コードベース分析上、このオプションの使用者はいない |
| HTS Engine stub | 維持 (ビルド互換性のため) |

### 4.4 既存テストの状況

#### テスト済みの範囲

| テスト | voice 依存 | 状況 |
|--------|-----------|------|
| `test_openjtalk_optimized` | オプショナル | `GTEST_SKIP()` で voice なし時にスキップ |
| `test_dictionary_manager` / `HTSVoicePath` | **直接** | ダミー voice ファイル作成テスト → **削除対象** |
| `test_c_api_integration` | なし | ONNX モデル使用、HTS voice 不要 |
| `test_c_api_audio_regression` | なし | ONNX モデル使用、HTS voice 不要 |
| その他全 C++ テスト (~62 ファイル) | なし | hts_engine_stub でリンク、voice 不使用 |

#### テストされていない範囲

**CI レベルで必要なテスト:**

| テスト名 | 目的 | 実装先 |
|---------|------|-------|
| `Verify phonemizer-only mode` | voice なしでフル CI パイプラインが通ることを確認 | `_build-test-cpp.yml` に検証ステップ追加 |
| `USE_HTS_ENGINE_STUB=OFF rejection` | OFF 設定がエラーになることを確認 | CMake テスト (オプション) |

**実装例 (CI ステップ):**
```yaml
- name: Verify phonemizer-only mode
  run: |
    echo "Verifying HTS voice is not required..."
    # Confirm no voice files on system
    ls /usr/share/hts-voice 2>/dev/null && echo "WARNING: hts-voice package still installed" || true
    # Run core tests
    cd build && ctest --output-on-failure -R "test_openjtalk"
```

---

## テスト網羅性の全体まとめ

### 既存テストで除去後もカバーされる範囲

| テスト | ファイル | カバー範囲 |
|--------|---------|-----------|
| OpenJTalk 基本変換 | `test_openjtalk_optimized.cpp` | phonemizer パスの音素抽出 |
| 辞書管理 | `test_dictionary_manager.cpp` | 辞書パス検索・ダウンロード |
| C API 統合 | `test_c_api_integration.cpp` | ONNX モデルによる合成パイプライン |
| セキュリティ | `test_openjtalk_security.cpp` | コマンドインジェクション防止 |
| ストリーミング | `test_streaming.cpp` | パイプベース音素抽出 |
| G2P 契約 | `test-g2p-contract.js` | JapaneseG2P コンストラクタ |

### 除去に伴い削除するテスト

| テスト | ファイル | 理由 |
|--------|---------|------|
| `HTSVoicePath` | `test_dictionary_manager.cpp` L263-280 | テスト対象の関数を削除するため |

### 新規テストが必要な箇所

| # | テスト名 | 対象領域 | 目的 | 優先度 |
|---|---------|---------|------|--------|
| 1 | `PhonemeExtractionWithoutVoice` | C++ | voice なしで `openjtalk_text_to_phonemes()` が成功 | 高 |
| 2 | `StreamingWithoutVoice` | C++ | voice なしでストリーミング音素抽出が成功 | 高 |
| 3 | `JapaneseG2P initializes without voiceData` | WASM G2P | dictData のみで初期化成功 | 高 |
| 4 | `JapaneseG2P rejects missing dictData` | WASM G2P | dictData なしでエラー | 中 |
| 5 | `DictLoader returns without voiceData` | WASM G2P | loadJaDict() の返り値検証 | 中 |
| 6 | `assets.json has no voices section` | openjtalk-web | ビルド成果物の検証 | 低 |
| 7 | `CI phonemizer-only mode` | CI | voice なしで CI パイプライン通過 | 高 (CI ステップとして) |

### テスト実装の指針

**C++ テスト** — `test_openjtalk_optimized.cpp` に追加:
```cpp
TEST_F(OpenJTalkOptimizedTest, PhonemeExtractionWithoutVoice) {
    unsetenv("OPENJTALK_VOICE");
    auto result = openjtalk_text_to_phonemes_optimized("こんにちは");
    if (!result) GTEST_SKIP() << "OpenJTalk binary not available";
    EXPECT_NE(std::string(result), "");
    EXPECT_THAT(std::string(result), ::testing::HasSubstr("k"));
}
```

**WASM G2P テスト** — `test-g2p-contract.js` に追加:
```javascript
it('should accept jaDict without voiceData', () => {
    const mockDict = { dictData: { 'char.bin': new ArrayBuffer(10), ... } };
    const ja = new JapaneseG2P({ jaDict: mockDict });
    assert.ok(ja);
});
```

**CI テスト** — `_build-test-cpp.yml` にステップ追加:
```yaml
- name: Verify phonemizer-only mode
  run: |
    unset OPENJTALK_VOICE
    cd build && ctest --output-on-failure -R "test_openjtalk"
```

---

## リスク評価

| リスク | 影響度 | 緩和策 |
|--------|--------|--------|
| phonemizer バイナリが存在しない環境 | 低 | open_jtalk フォールバックは voice なしで継続動作。ドキュメントで phonemizer 推奨を明示 |
| `@piper-plus/g2p` API 破壊 | 中 | voiceData を渡しても無視する deprecation フェーズを設けるか、マイナーバージョンアップで対応 |
| `USE_HTS_ENGINE_STUB=OFF` ユーザー | 極低 | コードベース上で使用者なし。FATAL_ERROR メッセージで移行案内 |
| CI でのテストスキップ増加 | 低 | 新規テスト追加で voice なしパスの明示的カバレッジを確保 |

## 見積もり

| 項目 | 数値 |
|------|------|
| 変更対象ファイル | ~25 ファイル |
| 削除行数 | ~400-500 行 |
| 新規テスト | ~7 テスト |
| 機能への影響 | なし (phonemizer-only が既にメインパス) |
