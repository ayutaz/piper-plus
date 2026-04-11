> **Status: 完了 (2026-04-11)** — 全4マイルストーン (M1-M4) が完了しました。この文書は計画段階で作成されたものであり、実際の実装と差異がある箇所があります。最新の状態は [チケット一覧](tickets/README.md) を参照してください。

---

# HTS Voice 依存除去 — マイルストーン

> 参照: [docs/remove-hts-voice-dependency.md](remove-hts-voice-dependency.md)

## 概要

HTS voice 依存を 4 マイルストーンで段階的に除去する。
各マイルストーンは独立してマージ可能な単位であり、途中段階でもビルド・テストが通る。

```
M1  C++ ランタイム          ← 他に依存なし (最初に着手)
M2  WASM G2P + openjtalk-web ← M1 と並行可能
M3  CI / CMake              ← M1 完了後
M4  テスト追加 + クリーンアップ ← M1-M3 完了後
```

---

## M1: C++ ランタイムから HTS voice フォールバックを除去

### 目的

`get_openjtalk_voice_path()` 関数と、それを使う 4 つの呼び出し箇所を削除する。
phonemizer パスも open_jtalk フォールバックも voice なしで動作するようにする。

### 前提条件

なし (最初に着手可能)

### タスク

| # | タスク | ファイル | 対象行 | 変更内容 |
|---|--------|---------|--------|---------|
| 1.1 | HTS voice 定数削除 | `src/cpp/openjtalk_dictionary_manager.c` | L30-35 | `#define HTS_VOICE_URL` 等 6 定数を削除 |
| 1.2 | voice パス検索関数削除 | `src/cpp/openjtalk_dictionary_manager.c` | L423-427 | `get_openjtalk_voice_path()` 関数を削除 |
| 1.3 | 無効化済み DL コード削除 | `src/cpp/openjtalk_dictionary_manager.c` | L429-567 | `#if 0` ブロック全体を削除 |
| 1.4 | ヘッダー宣言削除 | `src/cpp/openjtalk_dictionary_manager.h` | L11-12 | `get_openjtalk_voice_path()` 宣言とコメントを削除 |
| 1.5 | wrapper 関数 1 簡素化 | `src/cpp/openjtalk_wrapper.c` | L405-433 | `openjtalk_text_to_phonemes()` の voice 分岐を除去。`-m <voice>` なしの単一コマンドに統一 |
| 1.6 | wrapper 関数 2 簡素化 | `src/cpp/openjtalk_wrapper.c` | L715-738 | `openjtalk_text_to_phonemes_with_prosody_binary()` の voice 分岐を除去。同上 |
| 1.7 | optimized Unix パス簡素化 | `src/cpp/openjtalk_optimized.c` | L244-254 | `execute_with_pipes_unix()` の voice 分岐を除去 |
| 1.8 | optimized Windows パス簡素化 | `src/cpp/openjtalk_optimized.c` | L390-401 | `execute_with_pipes_windows()` の voice 分岐を除去 |
| 1.9 | HTSVoicePath テスト削除 | `src/cpp/tests/test_dictionary_manager.cpp` | L252-270 | `HTSVoicePath` テストケースを削除 |

### 変更の依存順序

```
1.1-1.4 (定数・関数・ヘッダー削除) と 1.5-1.8 (呼び出し元削除) は同一コミットで実施。
リンクエラーを防ぐため、定義の削除と呼び出しの削除を分離しないこと。
```

### 影響範囲

| 項目 | 影響 |
|------|------|
| 内部 API | `get_openjtalk_voice_path()` が消滅。4 箇所の呼び出しを同時に削除 |
| 環境変数 | `OPENJTALK_VOICE` が C++ コードで参照されなくなる |
| 動作変更 | `open_jtalk` フォールバック時に `-m <voice>` が付かなくなる。音素抽出は影響なし |
| ビルド | コンパイル・リンク成功を確認すること |

### 受入基準

- [x] `cmake --build build` が成功する
- [x] `ctest` の既存テストが全て PASS/SKIP (FAIL なし)
- [x] `grep -r "get_openjtalk_voice_path" src/cpp/` が 0 件
- [x] `grep -r "HTS_VOICE_URL" src/cpp/` が 0 件

> **完了:** M1 全タスク (1.1-1.9) 完了。受入基準すべて充足。

### 既存テストによる安全網

| テスト | ファイル | カバー範囲 |
|--------|---------|-----------|
| `BasicConversion` | `test_openjtalk_optimized.cpp` | phonemizer パスの音素抽出 |
| `PerformanceComparison` | `test_openjtalk_optimized.cpp` | wrapper + optimized 両パスの動作確認 |
| `ConcurrentAccess` | `test_openjtalk_optimized.cpp` | スレッド安全性 |
| `CacheHitPerformance` | `test_openjtalk_optimized.cpp` | キャッシュ正確性 |

### 削除行数: ~230行

---

## M2: WASM G2P + openjtalk-web から voice 依存を除去

### 目的

`@piper-plus/g2p` の公開 API から voiceData 要件を除去し、
openjtalk-web のテスト・ビルドスクリプトから voice ファイル参照を除去する。

### 前提条件

M1 と並行可能 (C++ と WASM は独立)

### タスク — WASM G2P (`@piper-plus/g2p`)

| # | タスク | ファイル | 対象行 | 変更内容 |
|---|--------|---------|--------|---------|
| 2.1 | initialize() から voice 除去 | `src/wasm/g2p/src/ja/index.js` | L90-93 | voicePtr 割り当て・initialize 引数・free を削除。`_openjtalk_initialize(dictPtr)` のみに |
| 2.2 | _loadDict() から voice 除去 | `src/wasm/g2p/src/ja/index.js` | L177-205 | voiceData 検証・FS mkdir('/voice')・writeFile を削除。dictData のみ検証に変更 |
| 2.3 | JSDoc 更新 | `src/wasm/g2p/src/ja/index.js` | L38, L65, L173 | voiceData 記述を JSDoc から削除 |
| 2.4 | voice DL 定数削除 | `src/wasm/g2p/src/dict-loader.js` | L50-54 | `DEFAULT_VOICE_URL`, `VOICE_CACHE_KEY` を削除 |
| 2.5 | voice DL ロジック削除 | `src/wasm/g2p/src/dict-loader.js` | L349-409 | `includeVoice` 判定・voice fetch・キャッシュロジックを削除。常に `{ dictFiles }` を返す |
| 2.6 | JSDoc 更新 | `src/wasm/g2p/src/dict-loader.js` | L311-358 | voice 関連パラメータ・返り値の JSDoc を削除 |
| 2.7 | 型定義更新 | `src/wasm/g2p/types/index.d.ts` | L210, L220-228 | `voiceData`, `includeVoice`, `voiceUrl` を型定義から削除 |
| 2.8 | WASM ラッパー更新 | `src/wasm/openjtalk-web/src/simple_wrapper.cpp` | L43-46 | `openjtalk_initialize()` から `voice_path` パラメータ削除 |
| 2.9 | phonemizer ラッパー更新 | `src/wasm/openjtalk-web/src/phonemizer_wrapper.cpp` | L10, L106-107 | 宣言と実装から `voice_path` パラメータ削除 |

### タスク — openjtalk-web テスト・ビルドスクリプト

| # | タスク | ファイル | 対象行 | 変更内容 |
|---|--------|---------|--------|---------|
| 2.10 | ビルドスクリプト更新 | `prepare-assets.sh` | L28-35 | voice コピーセクション削除 |
| 2.11 | 辞書準備スクリプト更新 | `prepare-dictionary.sh` | L37-49, L68-74 | voice ディレクトリ作成 + assets.json の voices セクション削除 |
| 2.12 | アセット定義更新 | `assets/assets.json` | L16-22 | `"voices"` オブジェクト削除 |
| 2.13 | test-cli.js 更新 | `test/test-cli.js` | L109-128, L134, L136, L236 | `loadVoiceFile()` 関数・呼び出し削除、initializeOpenJTalk から voicePtr 削除 |
| 2.14 | test-cli.mjs 更新 | `test/test-cli.mjs` | L114-133, L139, L141, L351 | 同上 (ESM 版) |
| 2.15 | test-headless.js 更新 | `test/test-headless.js` | L167-177 | voice fetch + FS 書き込み + voicePtr 削除 |
| 2.16 | 検証スクリプト更新 | `test/verify-build.sh` | L40-42 | voice ファイルチェック削除 |
| 2.17 | 検証スクリプト更新 | `test/pre-check.sh` | L87-89 | voice ファイルチェック削除 |
| 2.18 | 検証スクリプト更新 | `test/quick-test.py` | L57 | required_files から voice パス削除 |
| 2.19 | 検査スクリプト更新 | `test/test-simple-node.js` | L51-61 | voice ファイルサイズ確認セクション削除 |
| 2.20 | ドキュメント更新 | `test/test-node-simple.js` | L31 | voice パス参照削除 |
| 2.21 | デモ HTML 更新 | `dist/simple-test.html` | L123-126 | voice パスの initialize 引数を削除 |

### 変更の依存順序

```
2.8-2.9 (WASM C++ ラッパーの ABI 変更) を先に行い、
2.1-2.7 (JS 側の呼び出し変更) と 2.13-2.15 (テストの呼び出し変更) を同時に更新。
WASM ABI と JS 呼び出しが一致しないとランタイムエラーになる。
```

### 影響範囲

| 項目 | 影響 |
|------|------|
| npm 公開 API | `JapaneseG2P` が voiceData を不要に。`DictLoader` が `includeVoice`/`voiceUrl` を受け付けなくなる |
| TypeScript 型 | `JaDictData` から `voiceData` 削除、`DictLoadOptions` から `includeVoice`/`voiceUrl` 削除 |
| WASM ABI | `_openjtalk_initialize` のパラメータ数が 2→1 に変更 |
| 下流 PiperPlus クラス | `src/wasm/openjtalk-web/src/index.js` — **変更不要** (voice を渡していない) |
| npm 配布物 | `.htsvoice` は元々含まれていない。影響なし |
| バージョン | `@piper-plus/g2p` を `0.2.0` → `0.3.0` にバンプ (breaking change, pre-1.0) |

### 受入基準

- [ ] `@piper-plus/g2p` のテスト (`npm test`) が全て PASS
- [ ] openjtalk-web のテスト (`test-cli.js` 等) が voice なしで PASS
- [ ] `grep -r "voiceData\|includeVoice\|VOICE_CACHE_KEY\|htsvoice" src/wasm/g2p/src/` が 0 件
- [ ] `grep -r "loadVoiceFile\|mei_normal" src/wasm/openjtalk-web/test/` が 0 件
- [ ] `verify-build.sh` が voice チェックなしで PASS

### 既存テストによる安全網

| テスト | ファイル | カバー範囲 |
|--------|---------|-----------|
| G2P 契約テスト | `test-g2p-contract.js` | JapaneseG2P コンストラクタ (voice 不使用) |
| 言語統合テスト | `test-g2p-integration.js` | 全非 JA 言語テスト (影響なし) |
| ゴールデンテスト | `test-g2p-golden.js` | 音素化精度 (voice 不使用) |

### 削除行数: ~200行

---

## M3: CI / CMake から HTS voice 関連を除去

### 目的

CI ワークフローから voice ファイル DL/セットアップを削除し、
CMake の `USE_HTS_ENGINE_STUB=OFF` パス (実 HTS Engine ビルド) を廃止する。

### 前提条件

M1 完了 (C++ コードから `get_openjtalk_voice_path()` が削除済みであること)

### タスク — CI ワークフロー

| # | タスク | ファイル | 対象行 | 変更内容 |
|---|--------|---------|--------|---------|
| 3.1 | voice 環境変数削除 | `_build-test-cpp.yml` | L232 | `export OPENJTALK_VOICE="dummy.htsvoice"` を削除 |
| 3.2 | stub 作成ブロック削除 | `build-piper.yml` | L135-156 | Unix/Windows の HTS Engine stub 手動作成を削除 (CMake が処理) |

### タスク — CMake

| # | タスク | ファイル | 対象行 | 変更内容 |
|---|--------|---------|--------|---------|
| 3.3 | 実 HTS Engine ビルドパス廃止 | `cmake/ExternalDeps.cmake` | L141-191 | `elseif` ブロックを `FATAL_ERROR` に置き換え |
| 3.4 | PiperLink HTS 依存削除 | `cmake/PiperLink.cmake` | L57-62 | `add_dependencies(... hts_engine_external)` 3行を削除 |
| 3.5 | PiperLink HTS リンク簡素化 | `cmake/PiperLink.cmake` | L64-89 | `else()` ブロック (実 HTS リンク) を削除。stub リンクのみ残す |
| 3.6 | PiperPlusShared 更新 | `cmake/PiperPlusShared.cmake` | L22, L35, L102-110 | `hts_engine_external` 依存・include・リンクを削除/簡素化 |
| 3.7 | テスト CMake 更新 | `src/cpp/tests/CMakeLists.txt` | L25, L252, L335, L456, L663, L747, L830 | `${CMAKE_BINARY_DIR}/hts_stub/include` を 7 箇所中 6 箇所から削除 (L25 のマクロ定義内は維持) |

### 変更の依存順序

```
3.3 (ExternalDeps) → 3.4-3.6 (PiperLink, PiperPlusShared) → 3.7 (tests CMake)
ExternalDeps のターゲット定義変更が先。リンク設定はそれに依存。
ただし stub ヘッダー (hts_engine_stub.h) のコピーは維持すること。
```

### 維持するもの

| ファイル | 理由 |
|---------|------|
| `cmake/hts_engine_stub.h` | OpenJTalk ヘッダーが `HTS_engine.h` を include するため、型定義の互換シムとして必要 |
| `cmake/hts_engine_stub.c` | stub ライブラリとしてリンク継続 (OpenJTalk のリンク要件) |
| `cmake/ExternalDeps.cmake` L97-139 | stub ビルド自体は維持。ヘッダーコピー + stub ライブラリ構築 |

### 影響範囲

| 項目 | 影響 |
|------|------|
| `USE_HTS_ENGINE_STUB=OFF` ユーザー | `FATAL_ERROR` で停止。コードベース分析上、使用者なし |
| CI ビルド時間 | 短縮 (voice DL ~50MB が不要に) |
| ビルド | stub パスは維持されるため影響なし |

### 受入基準

- [ ] `cmake -B build` (stub モード) が成功する
- [ ] `cmake -B build -DUSE_HTS_ENGINE_STUB=OFF` が `FATAL_ERROR` で停止する
- [ ] `cmake --build build` が成功する
- [ ] `ctest` が全て PASS/SKIP
- [ ] CI ワークフローが voice DL なしで正常完了する

### 削除行数: ~120行 (+93行ファイル削除)

---

## M4: テスト追加 + クリーンアップ

### 目的

voice 除去後の動作を明示的に保証するテストを追加し、残存する不要ファイル・参照をクリーンアップする。

### 前提条件

M1-M3 全て完了

### タスク — 新規テスト

| # | テスト名 | 実装先 | 目的 |
|---|---------|-------|------|
| 4.1 | `PhonemeExtractionWithoutVoice` | `src/cpp/tests/test_openjtalk_optimized.cpp` | `OPENJTALK_VOICE` 未設定で音素抽出が成功することを確認 |
| 4.2 | `StreamingWithoutVoice` | `src/cpp/tests/test_openjtalk_optimized.cpp` | ストリーミングパスが voice なしで動作することを確認 |
| 4.3 | `JapaneseG2P initializes without voiceData` | `src/wasm/g2p/test/test-g2p-contract.js` | dictData のみで JapaneseG2P 初期化が成功 |
| 4.4 | `JapaneseG2P rejects missing dictData` | `src/wasm/g2p/test/test-g2p-contract.js` | dictData なしでエラーを投げる |
| 4.5 | `DictLoader returns without voiceData` | `src/wasm/g2p/test/test-g2p-contract.js` | `loadJaDict()` の返り値に voiceData がないことを確認 |
| 4.6 | `No voice files in assets` | `src/wasm/openjtalk-web/test/verify-build.sh` | ビルド成果物に voice メタデータがないことを確認 |

**C++ テスト実装例 (4.1):**
```cpp
TEST_F(OpenJTalkOptimizedTest, PhonemeExtractionWithoutVoice) {
    unsetenv("OPENJTALK_VOICE");
    auto result = openjtalk_text_to_phonemes_optimized("こんにちは");
    if (!result) {
        GTEST_SKIP() << "OpenJTalk binary not available";
    }
    EXPECT_NE(std::string(result), "");
    EXPECT_THAT(std::string(result), ::testing::HasSubstr("k"));
}
```

**JS テスト実装例 (4.3):**
```javascript
it('should accept jaDict without voiceData', () => {
    const mockDict = {
        dictData: Object.fromEntries(
            DICT_FILE_NAMES.map(f => [f, new ArrayBuffer(10)])
        )
    };
    const ja = new JapaneseG2P({ jaDict: mockDict });
    assert.ok(ja);
});
```

**verify-build.sh 追加 (4.6):**
```bash
# Voice files should NOT be present
if grep -q '"voices"' assets/assets.json 2>/dev/null; then
    echo "FAIL: assets.json still contains voices section"
    FAILED=1
fi
```

### タスク — クリーンアップ

| # | タスク | ファイル | 変更内容 |
|---|--------|---------|---------|
| 4.7 | サンプルスクリプト削除 | `examples/test_japanese_tts.sh` | HTS voice 前提のスクリプトを削除 |
| 4.8 | 環境変数ドキュメント更新 | `docs/getting-started/environment-variables.md` | `OPENJTALK_VOICE` の記述を削除または deprecated に |
| 4.9 | `@piper-plus/g2p` バージョンバンプ | `src/wasm/g2p/package.json` | `0.2.0` → `0.3.0` (breaking change) |
| 4.10 | CHANGELOG 更新 | `src/wasm/g2p/CHANGELOG.md` | voice 依存除去の breaking change を記載 |

### 受入基準

- [ ] 新規テスト 9 件が全て PASS
- [ ] `examples/test_japanese_tts.sh` が削除されている
- [ ] `@piper-plus/g2p` のバージョンが `0.3.0`
- [ ] 全 CI ワークフローが GREEN

---

## 全体スケジュール

```
M1 (C++ ランタイム) ── M3 (CI/CMake) ──┐
                                        ├── M4 (テスト + クリーンアップ) ── dev マージ
M2 (WASM G2P + openjtalk-web) ─────────┘
```

| マイルストーン | 変更ファイル数 | 削除行数 | 新規テスト |
|--------------|-------------|---------|-----------|
| M1 | 5 | ~230 | 0 (既存テストで安全網) |
| M2 | 17 | ~200 | 0 (既存テストで安全網) |
| M3 | 7 | ~120 (+93行ファイル削除) | 0 |
| M4 | 8 | ~50 | 9 |
| **合計** | **~25** (重複除く) | **~600 (+93行ファイル削除)** | **9** |

## リスク一覧

| リスク | マイルストーン | 影響度 | 緩和策 |
|--------|-------------|--------|--------|
| リンクエラー (定義削除と呼び出し削除の不一致) | M1 | 高 | 1.1-1.8 を同一コミットで実施 |
| WASM ABI 不一致 (C++ 引数変更と JS 呼び出しの不一致) | M2 | 高 | 2.8-2.9 と 2.1, 2.13-2.15 を同一コミットで実施 |
| CMake ターゲット参照エラー | M3 | 中 | ExternalDeps → PiperLink の順で変更 |
| `USE_HTS_ENGINE_STUB=OFF` ユーザー | M3 | 極低 | コードベース分析上、使用者なし |
| `@piper-plus/g2p` API 破壊 | M2 | 中 | マイナーバージョンアップ (pre-1.0 なので minor = breaking OK) |

---

## 横断的な改善提案

M1-M4 の設計レビューから抽出された、マイルストーン横断の改善提案。
今回の HTS voice 除去スコープには含まれないが、後続の技術的負債解消に適用すべき知見。

### 1. 静的解析 CI の導入

C++ CI に `cppcheck --enable=unusedFunction` と `clang-tidy` を導入し、dead code 蓄積を構造的に防止する。今回の `get_openjtalk_voice_path()` のような「定義はあるが呼び出し元がない関数」を自動検出可能。C++ カバレッジ CI (gcov/lcov) も未導入であり、dead branch の可視化ができていない。

**推奨優先度:** cppcheck CI > C++ カバレッジ > clang-tidy

### 2. Strategy パターンによる音素抽出バックエンド抽象化

C API 直接呼び出し / phonemizer バイナリ / open_jtalk フォールバックの 3 パスが `if-else` チェーンでインラインに共存。共通インターフェース (`PhonemeBackend`) を定義し、バックエンド選択を起動時の一回限りに統一すべき。jpreprocess (Rust FFI) 統合時の拡張性も確保される。

### 3. fullcontext パース処理の統合

`openjtalk_wrapper.c`、`openjtalk_optimized.c`、`openjtalk_api.c` の 3 箇所に重複する fullcontext ラベルパース処理を `fullcontext_parser.c` として一箇所に集約。`atoi()` / `strtol()` 混在による微妙な差異を解消する。

### 4. C++ / C# ゴールデンテスト参加

`tests/fixtures/g2p/phoneme_test_cases.json` に Python/Rust/Go/WASM が参加しているが、C++ と C# が不参加。特に C++ の `openjtalk_api.c` は NJD 後処理を独自 C ポートしており、Python 側との出力差異が検出されない。5 ランタイムの音素化一貫性保証が不完全。

### 5. migration-lifecycle.toml による卒業条件管理

段階的移行の「卒業条件」を `docs/spec/migration-lifecycle.toml` で宣言的に管理。CI で自動監視し、条件充足時に旧パス削除の PR を自動提案する仕組みを検討。Feature Flag ライフサイクル (導入→移行→卒業→削除) の制度化。

### 6. フィーチャーフラグ 2 層設計

CMake の `option()` を「機能フラグ」(ユーザー向け) と「実装フラグ」(ビルドシステム内部) の 2 層に分離。`target_compile_definitions` で C++ コードに自動伝播させ、CI ビルドマトリクスで ON/OFF 両方をテストする。次回の段階的移行から適用。

### 7. 第2回設計レビュー結果 (2026-04-11)

M1/M2 完了後に 5 チーム (アーキテクチャ / セキュリティ・信頼性 / コード品質 / ビルドシステム / API 互換性) によるエージェントレビューを実施。以下の横断的知見を追加。

#### 7.1 `#if 0` CI lint ガード (M3 に追加: タスク 3.8)

C++ ソースの `#if 0` ブロックを CI で自動検出する grep lint を導入。139 行の dead code が長期残存した根本原因への直接対策。

#### 7.2 `openjtalk_initialize` 名前衝突の解消

3 つの異なるシグネチャが同名を共有。バージョン付き共有 ABI ヘッダー (`openjtalk_phonemize_abi.h`) の導入を検討。M3/M4 のスコープ外だが、次回の ABI 変更時に対処すべき。

#### 7.3 テスト順序の非理想性の認識

「削除 → テスト追加」は理想の逆順だが、dead branch 除去という性質上リスクは受容可能。M4 作業着手前に既存テスト PASS の確認を必須とする。

#### 7.4 Docker `cpp-dev` HTS Engine ビルド除去 (M3 に追加: タスク 3.9)

Docker 開発環境が実 HTS Engine をビルドする無駄を除去。

#### 7.5 `hts_engine_stub` 残存理由のインラインコメント (M3 に追加: タスク 3.10)

stub リンク箇所に「なぜ必要か」のコメントを追加し、将来のメンテナーの混乱を防止。

#### 7.6 M3/M4 タスク数更新

| マイルストーン | 旧タスク数 | 追加タスク | 新タスク数 |
|--------------|----------|----------|----------|
| M3 | 7 | +4 (3.8-3.11) | 11 |
| M4 | 10 | +3 (4.11-4.13) | 13 (うち 4.12, 4.13 は考慮事項) |
