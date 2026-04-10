# M4-001: テスト追加 + クリーンアップ

## メタデータ
- マイルストーン: M4
- 依存チケット: M1-001, M2-001, M3-001
- ブロックするチケット: なし (最終マイルストーン)
- 状態: 未着手
- 推定削除行数: ~50行
- 新規テスト: 7件

## 1. 目的とゴール

M1-M3 で HTS voice 依存を除去した後、以下の 2 つの目的を達成する。

1. **動作保証テスト**: voice なしで正しく動作することを明示的に検証するテストを 7 件追加する。M1-M3 では既存テストの安全網に依存していたが、M4 では「voice がない状態が正常であること」を積極的に断言するネガティブテストを導入する。
2. **クリーンアップ**: M1-M3 の変更で不要になったファイル・ドキュメント参照・API バージョンを整理し、プロジェクト全体から HTS voice の痕跡を除去する。

**完了条件:**
- 新規テスト 7 件が全て PASS
- `grep -r "OPENJTALK_VOICE" src/ examples/` が 0 件
- `grep -r "voiceData\|includeVoice\|htsvoice" src/wasm/g2p/src/` が 0 件
- `@piper-plus/g2p` のバージョンが `0.3.0`
- `examples/test_japanese_tts.sh` が存在しない
- 全 CI ワークフローが GREEN

## 2. 実装内容の詳細

### 2.1 新規テスト (7件)

#### テスト 1: `PhonemeExtractionWithoutVoice` (C++)

- **ファイル**: `src/cpp/tests/test_openjtalk_optimized.cpp`
- **目的**: `OPENJTALK_VOICE` 環境変数が未設定の状態で `openjtalk_text_to_phonemes_optimized()` が正常に音素列を返すことを確認する。M1 で `get_openjtalk_voice_path()` と voice 分岐を削除した後、phonemizer パスが voice なしで完全に動作することを保証する。
- **アサーション**:
  - 返り値が `nullptr` でないこと (バイナリが存在しない環境では `GTEST_SKIP`)
  - 返り値が空文字列でないこと
  - 日本語音素 `"k"` が含まれること (「こんにちは」の先頭音素)
- **実装コード例**:

```cpp
// Windows 互換の unsetenv (test_gpu_device_id.cpp と同一パターン)
#ifdef _WIN32
static int unsetenv(const char* name) {
    return _putenv_s(name, "");
}
#endif

TEST_F(OpenJTalkOptimizedTest, PhonemeExtractionWithoutVoice) {
    // Ensure OPENJTALK_VOICE is not set — voice must not be required
    unsetenv("OPENJTALK_VOICE");

    char* result = openjtalk_text_to_phonemes_optimized("こんにちは");
    if (!result) {
        GTEST_SKIP() << "OpenJTalk binary not available";
    }

    EXPECT_NE(std::string(result), "");
    EXPECT_THAT(std::string(result), ::testing::HasSubstr("k"));

    openjtalk_free_phonemes(result);
}
```

#### テスト 2: `StreamingWithoutVoice` (C++)

- **ファイル**: `src/cpp/tests/test_openjtalk_optimized.cpp`
- **目的**: voice なしの状態で wrapper パス (`openjtalk_text_to_phonemes()`) も正常に動作することを確認する。M1 で `openjtalk_wrapper.c` の voice 分岐を簡素化した後、open_jtalk フォールバック時にも `-m <voice>` なしで音素抽出が成功することを保証する。
- **アサーション**:
  - 返り値が `nullptr` でないこと (バイナリが存在しない環境では `GTEST_SKIP`)
  - 返り値が空文字列でないこと
  - 日本語音素が含まれること
- **実装コード例**:

```cpp
// Windows 互換の unsetenv (test_gpu_device_id.cpp と同一パターン)
#ifdef _WIN32
static int unsetenv(const char* name) {
    return _putenv_s(name, "");
}
#endif

TEST_F(OpenJTalkOptimizedTest, StreamingWithoutVoice) {
    // Ensure OPENJTALK_VOICE is not set
    unsetenv("OPENJTALK_VOICE");

    // Use the wrapper (non-optimized) path to verify open_jtalk fallback
    char* result = openjtalk_text_to_phonemes("テスト");
    if (!result) {
        GTEST_SKIP() << "OpenJTalk binary not available";
    }

    EXPECT_NE(std::string(result), "");
    // "テスト" should produce phonemes containing 't' and 'e'
    EXPECT_THAT(std::string(result), ::testing::HasSubstr("t"));

    openjtalk_free_phonemes(result);
}
```

#### テスト 3: `JapaneseG2P initializes without voiceData` (JS)

- **ファイル**: `src/wasm/g2p/test/test-g2p-contract.js`
- **目的**: M2 で voiceData 要件を除去した後、`JapaneseG2P` コンストラクタが `dictData` のみで正常に初期化できることを確認する。voiceData が API から完全に不要になったことの契約テスト。
- **アサーション**:
  - `JapaneseG2P({ jaDict: { dictData: {...} } })` がエラーなく初期化できること
  - インスタンスが truthy であること
- **実装コード例**:

```javascript
it('should accept jaDict with dictData only (no voiceData required)', () => {
    // After M2, voiceData is no longer part of the API contract.
    // JapaneseG2P must initialize with dictData alone.
    const DICT_FILES = [
        'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
        'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def',
    ];
    const mockDict = {
        dictData: Object.fromEntries(
            DICT_FILES.map(f => [f, new ArrayBuffer(10)])
        ),
    };
    const ja = new JapaneseG2P({ jaDict: mockDict });
    assert.ok(ja, 'JapaneseG2P should initialize with dictData only');
});
```

#### テスト 4: `JapaneseG2P rejects missing dictData` (JS)

- **ファイル**: `src/wasm/g2p/test/test-g2p-contract.js`
- **目的**: M2 で voiceData バリデーションを削除した後、dictData の必須チェックが引き続き正しく機能することを確認する。voice を除去しても、辞書データなしの初期化は拒否されるべき。
- **アサーション**:
  - `_loadDict({})` が `dictData` に言及するエラーを投げること
- **実装コード例**:

```javascript
it('should throw when dictData is missing from jaDict', () => {
    // Create a JapaneseG2P with a mock WASM module to test _loadDict
    const ja = new JapaneseG2P({ jaDict: {} });
    // Manually set a mock module so _loadDict can be called
    ja._mod = {
        FS: { mkdir: () => {}, writeFile: () => {} },
        allocateUTF8: () => 1,
        _free: () => {},
        _openjtalk_initialize: () => 0,
    };
    assert.throws(
        () => ja._loadDict({}),
        (err) => err.message.includes('dictData'),
        '_loadDict({}) must throw an error mentioning dictData'
    );
});
```

#### テスト 5: `DictLoader returns without voiceData` (JS)

- **ファイル**: `src/wasm/g2p/test/test-g2p-contract.js`
- **目的**: M2 で DictLoader から voice DL ロジックを削除した後、`loadJaDict()` の返り値に `voiceData` プロパティが含まれないことを確認する。API 契約の破壊的変更を明示的に検証するテスト。
- **アサーション**:
  - `DictLoader` クラスがインポート可能であること
  - `DictLoader` インスタンスの `loadJaDict` メソッドが存在すること
  - (注: 実際の fetch はブラウザ環境依存のため、型・シグネチャレベルの検証)
- **実装コード例**:

```javascript
it('DictLoader.loadJaDict should not include voiceData in its contract', async () => {
    // Import DictLoader to verify the API surface
    const { DictLoader } = await import('../src/dict-loader.js');
    const loader = new DictLoader();

    // Verify the class exists and has the expected method
    assert.equal(typeof loader.loadJaDict, 'function',
        'DictLoader must have loadJaDict method');

    // Verify that the source code no longer references voice constants
    // (structural check — the actual fetch requires a browser environment)
    const { default: fs } = await import('node:fs');
    const src = fs.readFileSync(
        new URL('../src/dict-loader.js', import.meta.url), 'utf-8'
    );
    assert.ok(
        !src.includes('VOICE_CACHE_KEY'),
        'dict-loader.js must not contain VOICE_CACHE_KEY after M2 cleanup'
    );
    assert.ok(
        !src.includes('includeVoice'),
        'dict-loader.js must not contain includeVoice option after M2 cleanup'
    );
});
```

**改善案:** ソースコード文字列検索は脆弱 (リファクタリングでパスが変わると壊れる)。より堅牢な代替案として、`DictLoader` を実際にインスタンス化して `loadJaDict()` の返り値に `voiceData` プロパティが存在しないことを検証するアプローチを検討:

```javascript
it('DictLoader.loadJaDict() returns without voiceData', async () => {
    // DictLoader のモック or 実インスタンスで返り値を検証
    const result = await dictLoader.loadJaDict({ /* mock options */ });
    assert.ok(result.dictFiles, 'dictFiles should be present');
    assert.strictEqual(result.voiceData, undefined, 'voiceData should not be present');
});
```

#### テスト 6: `No voice files in assets` (shell)

- **ファイル**: `src/wasm/openjtalk-web/test/verify-build.sh`
- **目的**: M2 でビルドスクリプトから voice コピーを削除した後、ビルド成果物に voice メタデータ/ファイルが含まれないことを確認する。assets.json から `"voices"` セクションが除去されていることの検証。
- **アサーション**:
  - `assets/voice/` ディレクトリにファイルが存在しないこと
  - `assets/assets.json` に `"voices"` キーが含まれないこと
- **実装コード例** (既存の voice ファイルチェックを置換):

```bash
# === Voice files should NOT be present (HTS voice dependency removed) ===
echo ""
echo "Checking that voice files are absent..."
if [ -d "assets/voice" ] && [ "$(find assets/voice -type f 2>/dev/null | wc -l)" -gt 0 ]; then
    echo -e "  ${RED}FAIL${NC}: Voice files found in assets/voice (should be removed)"
    FAILED=1
else
    echo -e "  ${GREEN}OK${NC}: No voice files in assets/"
fi

if grep -q '"voices"' assets/assets.json 2>/dev/null; then
    echo -e "  ${RED}FAIL${NC}: assets.json still contains \"voices\" section"
    FAILED=1
else
    echo -e "  ${GREEN}OK${NC}: assets.json does not contain \"voices\" section"
fi
```

#### テスト 7: `CommandWithoutVoiceFlag` (C++)

- **ファイル**: `src/cpp/tests/test_openjtalk_optimized.cpp`
- **目的**: 構築されるコマンド文字列に `-m` フラグが含まれないことを確認する。
- **アサーション**:
  - voice なしで音素抽出が成功すること (バイナリが存在しない環境では `GTEST_SKIP`)
  - 返り値が空文字列でないこと
- **実装コード例**:

```cpp
TEST_F(OpenJTalkOptimizedTest, CommandWithoutVoiceFlag) {
    unsetenv("OPENJTALK_VOICE");
    // open_jtalk フォールバックで構築されるコマンドに -m が含まれないことを確認
    // 注: openjtalk_wrapper.c のコマンド構築は内部関数のため、
    // 実際の音素抽出結果が得られること (voice なしで動作すること) で間接的に検証
    auto result = openjtalk_text_to_phonemes_optimized("テスト");
    if (!result) {
        GTEST_SKIP() << "OpenJTalk binary not available";
    }
    EXPECT_NE(std::string(result), "");
}
```

### 2.2 クリーンアップ

#### 2.2.1 不要ファイル削除

| ファイル | 理由 | 操作 |
|---------|------|------|
| `examples/test_japanese_tts.sh` | HTS voice を SourceForge から DL し、`open_jtalk -m <voice>` で実行する前提のスクリプト。M1 で voice 分岐が除去されたため完全に不要。phonemizer ベースの動作確認は CI テストがカバーしている。 | 削除 |

#### 2.2.2 ドキュメント更新

| ファイル | 変更内容 |
|---------|---------|
| `docs/getting-started/environment-variables.md` (L37-44) | `### OPENJTALK_VOICE` セクションを削除。代わりに「`OPENJTALK_VOICE` は v0.3.0 で廃止されました。piper-plus は phonemizer-only モードで動作し、HTS voice ファイルは不要です。」の注記を残す |
| `docs/getting-started/windows-setup.md` (L445) | 環境変数テーブルから `OPENJTALK_VOICE` 行を削除 |

#### 2.2.3 バージョンバンプ

| ファイル | 変更 |
|---------|------|
| `src/wasm/g2p/package.json` | `"version": "0.2.0"` -> `"version": "0.3.0"` |

M2 で `JapaneseG2P` の voiceData 要件除去と `DictLoader` の `includeVoice`/`voiceUrl` 削除は breaking change (API 契約変更) である。pre-1.0 の SemVer 規約に従い、minor バージョンを `0.2.0` -> `0.3.0` にバンプする。

#### 2.2.4 CHANGELOG 更新

`src/wasm/g2p/CHANGELOG.md` に以下を追記:

```markdown
## [0.3.0] - 2026-XX-XX

### Breaking Changes

- **JapaneseG2P**: `voiceData` is no longer required or accepted in `jaDict`. Pass `{ dictData }` only.
- **DictLoader**: `includeVoice` and `voiceUrl` options removed from `loadJaDict()`. Return value no longer includes `voiceData`.
- **TypeScript types**: `voiceData` removed from `JaDictData`, `includeVoice`/`voiceUrl` removed from `DictLoadOptions`.
- **WASM ABI**: `_openjtalk_initialize()` now takes 1 parameter (dict path only), not 2.

### Removed

- HTS voice file dependency: `.htsvoice` files are no longer downloaded, cached, or referenced.
- `DEFAULT_VOICE_URL`, `VOICE_CACHE_KEY` constants from `dict-loader.js`.
- Voice-related validation in `JapaneseG2P._loadDict()`.

### Added

- Contract tests verifying voice-free initialization (`test-g2p-contract.js`).
```

## 3. エージェントチームの役割と人数

本チケットは 1 名のエージェントで実施可能。作業量が限定的 (テスト 7 件 + クリーンアップ ~50 行) であり、並行作業の余地はない。

| 役割 | 人数 | 担当 |
|------|------|------|
| 実装担当 | 1 | テスト追加 (C++ 3 件、JS 3 件、shell 1 件) + クリーンアップ (ファイル削除、ドキュメント更新、バージョンバンプ、CHANGELOG) |

**作業順序:**
1. テスト 7 件を追加して GREEN を確認
2. `examples/test_japanese_tts.sh` を削除
3. ドキュメント更新 (`environment-variables.md`, `windows-setup.md`)
4. バージョンバンプ + CHANGELOG 更新
5. 全 CI ワークフローの GREEN 確認
6. 残存チェック (`grep` で voice 関連文字列が残っていないことを確認)

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (スコープ)

**スコープ内:**
- C++ テスト 3 件追加 (`test_openjtalk_optimized.cpp`)
- JS テスト 3 件追加 (`test-g2p-contract.js`)
- shell 検証スクリプト 1 件更新 (`verify-build.sh`)
- `examples/test_japanese_tts.sh` 削除
- `docs/getting-started/environment-variables.md` の `OPENJTALK_VOICE` セクション更新
- `docs/getting-started/windows-setup.md` の環境変数テーブル更新
- `src/wasm/g2p/package.json` バージョンバンプ
- `src/wasm/g2p/CHANGELOG.md` 更新

**スコープ外:**
- M1-M3 のコード変更 (事前完了が前提)
- npm publish (dev マージ後に別途実施)
- Rust/C#/Go/Python ランタイム (HTS voice 依存なし、変更不要)

### 4.2 ユニットテスト

| # | テスト名 | ファイル | フレームワーク | 前提条件 |
|---|---------|---------|-------------|---------|
| 1 | `PhonemeExtractionWithoutVoice` | `test_openjtalk_optimized.cpp` | GoogleTest | OpenJTalk バイナリが利用可能 (不在時は GTEST_SKIP) |
| 2 | `StreamingWithoutVoice` | `test_openjtalk_optimized.cpp` | GoogleTest | 同上 |
| 3 | `JapaneseG2P initializes without voiceData` | `test-g2p-contract.js` | Node.js test runner | なし (モック使用) |
| 4 | `JapaneseG2P rejects missing dictData` | `test-g2p-contract.js` | Node.js test runner | なし (モック使用) |
| 5 | `DictLoader returns without voiceData` | `test-g2p-contract.js` | Node.js test runner | なし (ソースコード静的検証) |
| 6 | `No voice files in assets` | `verify-build.sh` | shell (exit code) | ビルド成果物が存在 |
| 7 | `CommandWithoutVoiceFlag` | `test_openjtalk_optimized.cpp` | GoogleTest | OpenJTalk バイナリが利用可能 (不在時は GTEST_SKIP) |

**テスト追加後の期待結果:**

| CI ワークフロー | 期待 |
|---------------|------|
| `_build-test-cpp.yml` | テスト 1, 2, 7 が PASS (またはバイナリ不在時 SKIP) |
| `g2p-wasm-ci.yml` | テスト 3, 4, 5 が PASS |
| `wasm-build.yml` | テスト 6 が PASS (`verify-build.sh` 内) |

### 4.3 E2Eテスト

ユニットテスト以外に、以下の E2E レベルの検証を実施する。

**CI GREEN 検証:**
- 全 CI ワークフロー (`_build-test-cpp.yml`, `g2p-wasm-ci.yml`, `wasm-build.yml`, `csharp-ci.yml`, `rust-tests.yml`, `go-ci.yml`) が GREEN であること

**残存チェック (grep):**

```bash
# C++ ソースに voice 関連が残っていないこと
grep -r "get_openjtalk_voice_path\|HTS_VOICE_URL\|OPENJTALK_VOICE" src/cpp/ && echo "FAIL" || echo "OK"

# WASM G2P ソースに voice 関連が残っていないこと
grep -r "voiceData\|includeVoice\|VOICE_CACHE_KEY\|htsvoice" src/wasm/g2p/src/ && echo "FAIL" || echo "OK"

# openjtalk-web テストに voice 関連が残っていないこと
grep -r "loadVoiceFile\|mei_normal\|voicePtr" src/wasm/openjtalk-web/test/ && echo "FAIL" || echo "OK"

# examples に HTS voice スクリプトが残っていないこと
test -f examples/test_japanese_tts.sh && echo "FAIL" || echo "OK"
```

**注意:** `CHANGELOG.md` や `docs/` 内の歴史的記録 (過去リリースの変更履歴) は除外する。grep パターンに `--exclude=CHANGELOG.md` を追加するか、`src/` 配下のみを対象とする:

```bash
# 歴史的参照を除外した残存チェック
grep -r "htsvoice\|HTS_VOICE\|mei_normal" src/ examples/ .github/ cmake/ --include="*.{js,ts,cpp,c,h,yml,json,sh,py}"
```

## 5. 懸念事項とレビュー項目

### 懸念事項

| # | 懸念 | 影響度 | 緩和策 |
|---|------|--------|--------|
| 1 | C++ テスト (1, 2) が CI 環境で GTEST_SKIP になる可能性 | 低 | OpenJTalk バイナリが CI に存在しない場合はスキップとなるが、これは既存テスト (`BasicConversion` 等) と同じ挙動。phonemizer バイナリが存在する CI 環境では PASS する。 |
| 2 | JS テスト (3, 4) が JapaneseG2P の内部 `_loadDict` メソッドに依存 | 中 | `_loadDict` はプレフィックス `_` 付きの内部メソッドだが、公開コンストラクタ経由のテストでは WASM モジュール全体が必要。モック + 内部メソッド直接呼び出しは現実的な妥協。リファクタリング時にテスト破壊の可能性がある。 |
| 3 | `@piper-plus/g2p` 0.3.0 の npm publish タイミング | 低 | dev マージ後にタグ付きリリースで publish。M2 の API 変更と M4 のバージョンバンプを同一リリースに含める。 |
| 4 | `verify-build.sh` の voice チェック置換が WASM ビルド環境でのみ有効 | 低 | ローカル開発ではビルド成果物が存在しない場合がある。スクリプト自体が `set -e` で保護されており、ファイル不在時は既存チェックで FAIL する。 |
| 5 | `unsetenv` Windows 互換性 | 中 | `unsetenv` は POSIX 関数であり Windows には存在しない。テストコードに `#ifdef _WIN32` の互換実装 (`_putenv_s` ベース) を追加するか、`test_gpu_device_id.cpp` の実装をプロジェクト共通ヘッダーに抽出する。CI の Windows ビルドでコンパイルエラーになるリスク |

### レビュー項目

- [ ] 新規テスト 7 件が M1-M3 の変更内容と整合しているか
- [ ] `unsetenv("OPENJTALK_VOICE")` が他のテストに副作用を与えないか (GoogleTest はテストごとにプロセス分離しないため、SetUp/TearDown での環境変数復元を検討)
- [ ] `examples/test_japanese_tts.sh` 削除後に `examples/` ディレクトリ内の他のファイルへの参照が壊れないか
- [ ] CHANGELOG のバージョン日付が dev マージ日と一致しているか
- [ ] TypeScript 型定義 (`types/index.d.ts`) から voiceData 関連が M2 で既に削除されていることの再確認

## 6. ゼロから作り直すとしたら

### テスト戦略の観点

もし最初から「HTS voice は将来除去する可能性がある」と想定したテスト設計をしていたなら、以下の設計原則を採用していたはずである。

#### 6.1 ネガティブテストの先行導入

今回の M4 で追加する「voice なしで動作する」テストは、本来 voice 依存がコードに入った時点で同時に書くべきだった。具体的には:

- **依存の有無をパラメータ化テスト (GoogleTest `INSTANTIATE_TEST_SUITE_P`) で網羅**: `WithVoice` / `WithoutVoice` の 2 パラメータで全音素化テストを実行し、voice なしパスが常に GREEN であることを保証する。これにより、voice 関連コードが dead code であることが最初から可視化される。
- **API 契約テストに「不要なプロパティを渡した場合」のケースを含める**: `JapaneseG2P` に `voiceData` が追加された時点で、「voiceData なしでも初期化できる」テストを同時に書いていれば、voice が必須バリデーションに組み込まれること自体を防止できた。

なお M2 (6.1) が主張する「不要パラメータを API に含めない」原則が初日から適用されていれば、そもそも `voiceData` パラメータが API に存在せず、ネガティブテスト自体も不要だった。つまり **API 設計の最小化 (M2) とテスト負荷の最小化 (M4) は表裏一体**であり、テスト戦略だけを改善しても API 設計が肥大していれば根本解決にはならない。

#### 6.2 テスト/ビルドインフラの依存をプロダクションコードから分離

openjtalk-web の `test-cli.js` や `verify-build.sh` が voice ファイルに依存していたのは、テストインフラがプロダクション依存を暗黙的に取り込んだ典型例である。理想的には:

- **テストフィクスチャの依存を `test/fixtures/` に隔離**: voice ファイルが必要なテストがあるなら、テスト専用のミニマル voice stub を `test/fixtures/` に配置し、プロダクションの voice DL パスとは独立させる。テスト用の stub が不要になれば fixtures を削除するだけで済む。
- **ビルド検証スクリプトのチェック項目を設定ファイルで管理**: `verify-build.sh` がハードコードで `assets/voice/mei_normal.htsvoice` をチェックするのではなく、`build-manifest.json` のような宣言的ファイルで必要アセットを定義し、スクリプトはそれを読んで検証する。アセット構成が変わったら manifest を更新するだけで済む。この思想は M2 (6.2.1) が提案する `wasm-exports.json` による ABI 契約管理と同じであり、**宣言的な契約ファイルでテスト/ビルドの前提条件を管理する**という共通原則に帰結する。

#### 6.3 テストピラミッドにおける WASM テストの位置付け

M4 で追加する 7 件のテストは、テストピラミッドの異なるレイヤーに分散している。ゼロから設計するなら、各テストがどのレイヤーに位置するかを明示的に分類し、カバレッジの偏りを可視化すべきだった:

| テスト | レイヤー | 検証対象 | 実行速度 |
|--------|---------|---------|---------|
| テスト 1: `PhonemeExtractionWithoutVoice` | Unit | C++ phonemizer 単体 | < 100ms |
| テスト 2: `StreamingWithoutVoice` | Unit | C++ wrapper フォールバック | < 100ms |
| テスト 3: `JapaneseG2P initializes without voiceData` | Integration | JS <-> WASM ABI 境界 | < 50ms |
| テスト 4: `JapaneseG2P rejects missing dictData` | Integration | JS バリデーション | < 50ms |
| テスト 5: `DictLoader returns without voiceData` | Integration (静的) | ソースコード構造検証 | < 50ms |
| テスト 6: `No voice files in assets` | E2E | ビルド成果物検証 | < 1s |
| テスト 7: `CommandWithoutVoiceFlag` | Unit | C++ コマンド構築 `-m` 不在 | < 100ms |

**不足しているレイヤー:**

- **Contract テスト (WASM ABI):** テスト 3-5 は JS 側からの単方向検証に過ぎない。M2 (6.6) が提案する消費者駆動契約テストを導入すれば、WASM C++ 側 (Provider) と JS 側 (Consumer) の双方向で ABI 一致を検証できる。具体的には、`wasm-exports.json` から期待される関数シグネチャを読み込み、WASM バイナリのエクスポートと突き合わせるテストを追加する:
  ```javascript
  // test-wasm-contract.js
  import { strict as assert } from 'node:assert';
  import { it } from 'node:test';
  import contract from '../contracts/wasm-js-contract.json' with { type: 'json' };

  it('WASM exports match contract', async () => {
      const mod = await import('../dist/rust-wasm/openjtalk.js');
      for (const interaction of contract.interactions) {
          assert.equal(
              typeof mod[interaction.function], 'function',
              `Missing WASM export: ${interaction.function}`
          );
      }
  });
  ```
- **Performance regression テスト:** voice 除去後に WASM の初期化時間が短縮されることを数値で検証するベンチマークテスト。`performance.now()` で計測し、しきい値を超えたら FAIL とする。

テスト 5 の現在の実装 (ソースコードを `fs.readFileSync` で読み込んで文字列検索) は特に脆い。リファクタリングで変数名が変わるとテストが壊れる。契約テストに置き換えることで、実装の内部構造ではなく外部契約に対してテストできる。

#### 6.4 破壊的変更のバージョニング / CHANGELOG 管理の理想的なフロー

今回 `@piper-plus/g2p` のバージョンバンプと CHANGELOG 更新を M4 で行っているが、理想的には M2 (API 変更) のコミット時点で同時に行うべきだった。以下が理想的なフロー:

1. **API 変更コミット = バージョンバンプコミット**: M2 で `voiceData` を除去するコミットに `package.json` のバージョンバンプを含める。これにより、git bisect で「どのコミットで API が壊れたか」を追跡した際に、バージョン番号と変更内容が 1:1 で対応する。
2. **CHANGELOG は API 変更の PR 説明から自動生成**: `conventional-changelog` や `changesets` のようなツールを導入し、PR のコミットメッセージ (`feat!:`, `BREAKING CHANGE:`) から CHANGELOG エントリを自動生成する。手動での CHANGELOG 更新忘れを防止する。
3. **pre-release タグで段階的移行**: M2 完了時点で `0.3.0-alpha.1` をタグ付けして npm に publish し、下流ユーザーに移行期間を与える。M4 完了後に正式な `0.3.0` をリリースする。

もしこのフローが最初から確立されていれば、M4 は「テスト追加のみ」のチケットとなり、バージョニング作業は不要だった。

### 6.5 npm deprecation と IndexedDB キャッシュクリーンアップ

> 詳細は M2-001 セクション 6.4 (IndexedDB キャッシュ) および 6.5 (npm deprecation ワークフロー) を参照。

M4 固有の実施事項:
- CHANGELOG に IndexedDB キャッシュの手動クリア手順を記載 (`Application` > `Storage` > `IndexedDB` から `piper-g2p-cache` を削除)
- `npm-publish.yml` の post-publish ステップに `npm deprecate "@piper-plus/g2p@<0.3.0" "voiceData API removed in 0.3.0, see migration guide"` を追加

## 7. 後続タスクへの連絡事項

### dev マージ時の注意点

1. **マージ順序の厳守**: M1 -> M2 -> M3 -> M4 の順序でマージする。M4 は M1-M3 全ての完了を前提とする。M4 のテストは M1-M3 の変更が適用された状態でのみ PASS する。
2. **squash マージ推奨**: M4 のコミットは「テスト追加」と「クリーンアップ」を分離した 2 コミット構成が理想的。ただし、CI GREEN を維持するために全変更を 1 コミットにまとめることも許容。
3. **リベース時の競合**: `test_openjtalk_optimized.cpp` と `test-g2p-contract.js` はテスト末尾への追記のため、他の PR で同ファイルにテストが追加されていると競合する可能性がある。

### npm publish 手順

M4 マージ後、以下の手順で `@piper-plus/g2p` 0.3.0 を publish する:

```bash
cd src/wasm/g2p
# バージョンが 0.3.0 であることを確認
node -e "console.log(require('./package.json').version)"  # => 0.3.0

# npm publish は CI (npm-publish.yml) がタグトリガーで自動実行
git tag g2p-v0.3.0
git push origin g2p-v0.3.0
```

**注意:** `npm-publish.yml` は `g2p-v*` タグで起動する。タグ名の prefix を間違えないこと。

### 他の同種依存が将来発生した場合のガイドライン

HTS voice 除去で得られた教訓を、将来の不要依存除去に適用するためのガイドライン:

1. **依存追加時にネガティブテストを同時に書く**: 新しい外部依存を追加する PR では、「その依存がない状態でも基本機能が動作する」テストを必ず含める。これは依存が optional であることの文書化にもなる。
2. **マイルストーン分割テンプレートの再利用**: 本件の M1-M4 の分割パターン (ランタイム -> WASM/npm -> CI/ビルド -> テスト/クリーンアップ) は、他の依存除去にもそのまま適用可能。
3. **API 破壊的変更は即座にバージョンバンプ**: npm パッケージの公開 API を変更するコミットでは、同一コミット内で `package.json` のバージョンバンプと CHANGELOG 更新を行う。M4 に積み残さない。
4. **grep による残存チェックを CI に組み込む**: 除去対象のキーワード (`htsvoice`, `voiceData` 等) を CI ステップで grep し、0 件であることを assert する。人間のレビューだけに依存しない。
5. **依存追加時のガードレール**: 新しい外部依存を追加する PR には、(a) 依存が不要になる条件の明記、(b) 不要時の除去計画、(c) 依存の有無を検証するネガティブテストの同時追加 を必須とする。ADR (Architecture Decision Records) の導入も検討する
