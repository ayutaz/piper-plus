# M2-001: WASM G2P + openjtalk-web から voice 依存を除去

## メタデータ
- マイルストーン: M2
- 依存チケット: なし (M1 と並行可能)
- ブロックするチケット: M4-001
- 状態: 完了
- 推定削除行数: ~200行
- 変更ファイル数: 17

---

## 1. 目的とゴール

piper-plus は VITS ニューラル TTS エンジンであり、OpenJTalk の**音素抽出機能のみ**を使用する。HTS voice (`.htsvoice`) による音声合成は一切行わない。

しかし WASM レイヤーには HTS voice への依存が 3 つの形態で残存している:

1. **API 契約依存** -- `@piper-plus/g2p` の `JapaneseG2P` クラスが `voiceData` を必須パラメータとして要求する。WASM 側 (`simple_wrapper.cpp`) は `voice_path` を受け取るが `return 0` で完全に無視している
2. **データフロー依存** -- `DictLoader` が `includeVoice` オプションで HTS voice ファイル (~50MB) のダウンロード・IndexedDB キャッシュ機能を持つ
3. **テスト/ビルドインフラ依存** -- openjtalk-web の 11 ファイルが voice ファイルの存在を前提とした検証・ロード・初期化を行う

**ゴール:**

- `@piper-plus/g2p` の公開 API から `voiceData` 要件を完全に除去する
- `DictLoader` から `includeVoice` / `voiceUrl` オプションと voice DL ロジックを除去する
- WASM ABI (`_openjtalk_initialize`) のパラメータ数を 2 から 1 に変更する
- openjtalk-web のテスト・ビルドスクリプトから voice ファイル参照を全て除去する
- 上記変更後、既存のテストスイートが全て PASS することを確認する

---

## 2. 実装内容の詳細

### 2.1 WASM G2P (`@piper-plus/g2p`) の変更

#### 2.1.1 `src/wasm/g2p/src/ja/index.js` -- JapaneseG2P クラス

**タスク 2.1 -- `initialize()` から voice 除去:**

`initialize()` メソッド (L88-99) で `voicePtr` の確保・`_openjtalk_initialize` への 2 引数呼び出し・`_free` を削除し、1 引数 (`dictPtr` のみ) に変更する。

```
対象行: L90-93
Before: voicePtr 確保 → _openjtalk_initialize(dictPtr, voicePtr) → _free(voicePtr)
After:  _openjtalk_initialize(dictPtr) のみ
```

**タスク 2.2 -- `_loadDict()` から voice 除去:**

`_loadDict()` メソッド (L175-206) から以下を削除する:
- `voiceData` のデストラクチャリング (L177)
- `!dictData || !voiceData` のバリデーション (L179-183) -- `!dictData` のみに変更
- `voiceData instanceof ArrayBuffer` チェック (L194-196)
- `/voice` ディレクトリ作成 (L200)
- voice ファイル書き込み (L205)

```
対象行: L177-205
削除: voiceData 検証 (~7行) + FS mkdir + writeFile (~3行)
変更: エラーメッセージを「jaDict must have { dictData: { [filename]: ArrayBuffer } }.」に修正
```

**タスク 2.3 -- JSDoc 更新:**

以下の JSDoc コメントから `voiceData` 記述を削除する:
- コンストラクタの `@param` (L38: `voiceData: ArrayBuffer` 記述)
- `initialize()` の `@param` (L65: `voiceData: ArrayBuffer` 記述)
- `_loadDict()` の `@param` (L173: `voiceData: ArrayBuffer` 記述)

#### 2.1.2 `src/wasm/g2p/src/dict-loader.js` -- DictLoader クラス

**タスク 2.4 -- voice DL 定数削除:**

```
対象行: L50-54
削除: DEFAULT_VOICE_URL 定数, VOICE_CACHE_KEY 定数
```

**タスク 2.5 -- voice DL ロジック削除:**

`loadJaDict()` メソッド (L360-410) から以下を削除する:
- `includeVoice` / `voiceUrl` のオプション取得 (L362-363)
- `if (!includeVoice) return { dictFiles }` の早期リターン分岐 -- 常に `return { dictFiles }` に変更
- voice fetch・キャッシュ・返り値への `voiceData` 追加 (L392-409)

```
対象行: L349-409
削除: ~30行 (includeVoice 判定 + voice fetch + キャッシュ + return)
変更: dictFiles 返却のみのシンプルな return 文に統一
```

**タスク 2.6 -- JSDoc 更新:**

- `DictLoader` クラスの JSDoc (L310-326) から voice 関連の `@example` と記述を削除
- `loadJaDict()` の `@param` (L348-358) から `includeVoice`, `voiceUrl` を削除
- `@returns` / `@typedef JaDictData` から `voiceData` を削除

#### 2.1.3 `src/wasm/g2p/types/index.d.ts` -- TypeScript 型定義

**タスク 2.7 -- 型定義更新:**

```
L210-211: JaDictData から voiceData?: ArrayBuffer を削除 (L210: JSDoc コメント, L211: プロパティ宣言)
L221-226: DictLoadOptions から includeVoice?: boolean を削除 (L221-225: JSDoc ブロック, L226: プロパティ宣言)
L227-228: DictLoadOptions から voiceUrl?: string を削除 (L227: JSDoc コメント, L228: プロパティ宣言)
```

#### 2.1.4 `src/wasm/openjtalk-web/src/simple_wrapper.cpp` -- WASM ラッパー

**タスク 2.8 -- WASM ABI 変更:**

`openjtalk_initialize()` のシグネチャから `voice_path` パラメータを削除する。

```
対象行: L42-46
Before: int openjtalk_initialize(const char* dic_dir, const char* voice_path) { return 0; }
After:  int openjtalk_initialize(const char* dic_dir) { return 0; }
```

#### 2.1.5 `src/wasm/openjtalk-web/src/phonemizer_wrapper.cpp` -- Phonemizer ラッパー

**タスク 2.9 -- forward 宣言と実装の更新:**

```
対象行: L10  -- extern "C" の forward 宣言から voice_path を削除
対象行: L106-107 -- phonemizer_initialize_openjtalk() から voice_path を削除
```

#### 2.1.6 WASM リビルド

`simple_wrapper.cpp` と `phonemizer_wrapper.cpp` の C++ シグネチャ変更は、Emscripten による WASM リビルドなしには反映されない。以下の手順が必要:

1. WASM ビルドスクリプト (`build-wasm.sh` 等) を実行して `.wasm` バイナリを再生成
2. `g2p-wasm-ci.yml` のトリガーパスに `src/wasm/openjtalk-web/src/` が含まれていることを確認（含まれていない場合は追加）
3. リビルド後の WASM バイナリで `_openjtalk_initialize` のエクスポートシグネチャが 1 引数に変更されていることを検証

### 2.2 openjtalk-web テスト・ビルドスクリプトの変更

#### 2.2.1 ビルドスクリプト (2 ファイル)

**タスク 2.10 -- `prepare-assets.sh` (L28-35):**

voice コピーセクション全体を削除する:
```
削除: "Copying voice files..." echo + if/else ブロック (~8行)
```

**タスク 2.11 -- `prepare-dictionary.sh` (L37-49, L68-74):**

- voice ディレクトリ作成 + ファイルコピー (L37-49) を削除 (~13行)
- assets.json 生成テンプレートから `"voices"` セクションを削除 (L68-74)

#### 2.2.2 アセット定義 (1 ファイル)

**タスク 2.12 -- `assets/assets.json` (L16-22):**

`"voices"` オブジェクトを削除する。dictionary セクションのみ残す。

```json
{
  "dictionary": {
    "version": "1.11",
    "format": "utf-8",
    "files": ["char.bin", "matrix.bin", "sys.dic", "unk.dic",
              "left-id.def", "pos-id.def", "rewrite.def", "right-id.def"]
  }
}
```

#### 2.2.3 テストファイル (6 ファイル)

**タスク 2.13 -- `test/test-cli.js`:**

- `loadVoiceFile()` 関数全体 (L109-128) を削除
- `loadVoiceFile(Module)` 呼び出し (L236) を削除
- `initializeOpenJTalk()` (L130-147) から voicePtr 関連を削除:
  - `voicePtr` 確保 (L134)、`_openjtalk_initialize(dictPtr, voicePtr)` を 1 引数に (L136)、`_free(voicePtr)` (L139)

**タスク 2.14 -- `test/test-cli.mjs`:**

タスク 2.13 と同一パターンの変更 (ESM 版):
- `loadVoiceFile()` 関数 (L114-133) 削除
- 呼び出し (L351) 削除
- `initializeOpenJTalk()` (L135-152) から voicePtr 削除

**タスク 2.15 -- `test/test-headless.js`:**

`createTestHTML()` 内のテスト HTML テンプレートから voice 関連を削除:
- voice fetch + FS mkdir('/voice') + writeFile (L167-177)
- voicePtr 確保・initialize 引数・free (L175-179)

**タスク 2.16 -- `test/verify-build.sh` (L40-42):**

```
削除: echo "Checking voice files..." + check_file "assets/voice/mei_normal.htsvoice"
```

**タスク 2.17 -- `test/pre-check.sh` (L87-89):**

```
削除: echo "5. Checking voice files..." + check_file "assets/voice/mei_normal.htsvoice"
```
セクション番号のリナンバリングも行う (5→削除、6→5、7→6、...)。

**タスク 2.18 -- `test/quick-test.py` (L57):**

`required_files` リストから `"/assets/voice/mei_normal.htsvoice"` を削除する。

**タスク 2.19 -- `test/test-simple-node.js` (L51-61):**

voice ファイルサイズ確認セクション ("Check voice file" + voicePath + fs.statSync) を削除する。

**タスク 2.20 -- `test/test-node-simple.js` (L31):**

voice パス参照 (`'5. Call openjtalk_initialize("/dict", "/voice/mei_normal.htsvoice")'`) を `'5. Call openjtalk_initialize("/dict")'` に変更する。

#### 2.2.4 デモ HTML (1 ファイル)

**タスク 2.21 -- `dist/simple-test.html` (L123-126):**

`_openjtalk_initialize` 呼び出しから voice パス引数を削除する:
```
Before: _openjtalk_initialize(allocateUTF8("/dict"), allocateUTF8("/voice/test.htsvoice"))
After:  _openjtalk_initialize(allocateUTF8("/dict"))
```

#### 2.2.5 デモドキュメント (1 ファイル)

**タスク 2.22 -- `test/multilingual-demo/github-pages-setup.md` (L35, L97):**

`voicePath` 参照と `voice/` ディレクトリツリー記載を削除する:
- L35: `voicePath: deploymentConfig.getPath('../assets/voice/mei_normal.htsvoice')` を削除
- L97: `│   └── voice/` を削除

### 2.3 変更の依存順序

```
Phase 1: WASM C++ ABI 変更 (タスク 2.8, 2.9)
  simple_wrapper.cpp と phonemizer_wrapper.cpp の openjtalk_initialize() シグネチャ変更
  |
  v
Phase 2: JS 呼び出し側の同時更新 (タスク 2.1-2.7, 2.13-2.15, 2.21)
  ja/index.js, dict-loader.js, types/index.d.ts の API 変更
  + test-cli.js, test-cli.mjs, test-headless.js, simple-test.html の呼び出し変更
  |
  v
Phase 3: ビルド/検証スクリプトの更新 (タスク 2.10-2.12, 2.16-2.20)
  prepare-assets.sh, prepare-dictionary.sh, assets.json
  + verify-build.sh, pre-check.sh, quick-test.py, test-simple-node.js, test-node-simple.js
```

**重要な制約:** Phase 1 と Phase 2 は**同一コミットで実施**すること。WASM ABI (引数の数) と JS 呼び出し (渡す引数の数) が不一致だと、WASM 側で引数がスタック上の不定値を読み取り、ランタイムエラーまたは未定義動作が発生する。Phase 3 は Phase 1-2 と別コミットでも安全だが、CI の voice ファイルチェックが失敗する可能性があるため、同一 PR に含めること。

---

## 3. エージェントチームの役割と人数

| # | エージェント | 担当範囲 | タスク番号 |
|---|------------|---------|-----------|
| 1 | WASM ABI + G2P API エージェント | WASM C++ ラッパー変更 + JS API 変更 + 型定義 | 2.1-2.9 |
| 2 | テスト/ビルドインフラ エージェント | テストファイル 6 件 + 検証スクリプト 3 件 + ビルドスクリプト 2 件 + assets.json + デモ HTML | 2.10-2.21 |

**推奨: 2 エージェント構成。**

エージェント 1 が Phase 1-2 (ABI + API) を完了した後、エージェント 2 が Phase 3 (インフラ) を実施する。ただし Phase 1-2 の変更が Phase 3 のファイルに影響しない (voice 参照の削除は独立) ため、並列作業も可能。最終的に同一コミットにまとめるときにコンフリクトがないことを確認する。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (スコープ)

**スコープ内:**
- `@piper-plus/g2p` パッケージの voice 依存除去 (API, DictLoader, 型定義)
- WASM C++ ラッパーの ABI 変更 (simple_wrapper.cpp, phonemizer_wrapper.cpp)
- openjtalk-web のテスト・ビルドスクリプトの voice 参照除去 (11 ファイル)
- `assets/assets.json` から voices セクション削除

**スコープ外:**
- `@piper-plus/g2p` のバージョンバンプ (M4 で実施)
- 新規テストの追加 (M4 で実施)
- `PiperPlus` クラス (`src/wasm/openjtalk-web/src/index.js`) -- 変更不要 (voice を渡していない)
- Rust WASM (`src/rust/piper-wasm/`) -- HTS voice 依存なし
- C++ ランタイム -- M1 のスコープ

### 4.2 ユニットテスト

M2 では**新規テストを追加しない**。既存テストによる安全網で変更の正当性を保証する。

| 既存テスト | ファイル | カバー範囲 | M2 変更後の期待動作 |
|-----------|---------|-----------|-------------------|
| G2P 契約テスト | `src/wasm/g2p/test/test-g2p-contract.js` | JapaneseG2P コンストラクタ | PASS (voice 不使用のテスト) |
| 言語統合テスト | `src/wasm/g2p/test/test-g2p-integration.js` | EN/ZH/KO/ES/FR/PT/SV | PASS (JA 除外、影響なし) |
| ゴールデンテスト | `src/wasm/g2p/test/test-g2p-golden.js` | 音素化精度 | PASS (voice 不使用) |
| エンコードテスト | `src/wasm/g2p/test/test-encode.js` | phoneme ID エンコード | PASS (voice 無関係) |
| PUA マップテスト | `src/wasm/g2p/test/test-pua-map.js` | PUA 変換 | PASS (voice 無関係) |

### 4.3 E2E テスト

M2 完了後の受入基準として以下を実行する:

- [ ] `@piper-plus/g2p` のテスト (`npm test`) が全て PASS
- [ ] openjtalk-web のテスト (`test-cli.js` 等) が voice なしで PASS (WASM ビルドが利用可能な環境)
- [x] `grep -r "voiceData\|includeVoice\|VOICE_CACHE_KEY\|htsvoice" src/wasm/g2p/src/` が 0 件
- [x] `grep -r "loadVoiceFile\|mei_normal" src/wasm/openjtalk-web/test/` が 0 件
- [ ] `verify-build.sh` が voice チェックなしで PASS

---

## 5. 懸念事項とレビュー項目

### 5.1 WASM ABI 不一致リスク (重大度: 高)

`_openjtalk_initialize` の引数を 2 から 1 に変更するため、WASM C++ 側と JS 呼び出し側が不一致になると実行時にクラッシュまたは未定義動作が発生する。

**緩和策:** タスク 2.8-2.9 (C++ 側) とタスク 2.1 + 2.13-2.15 + 2.21 (JS 側の全呼び出し) を**同一コミット**で実施する。WASM のリビルドが不要な環境 (simple_wrapper.cpp がスタブのため) では JS 側の変更のみでもテストが通るが、本番の Emscripten ビルドでは ABI 一致が必須。

### 5.2 npm API 破壊 (重大度: 中)

`@piper-plus/g2p` の公開 API から以下が削除される:

| 削除される API | 影響を受けるコード |
|---------------|-----------------|
| `JaDictData.voiceData` | `includeVoice: true` で辞書をロードしている利用者 |
| `DictLoadOptions.includeVoice` | 同上 |
| `DictLoadOptions.voiceUrl` | カスタム voice URL を指定している利用者 |
| `_openjtalk_initialize` 2引数 ABI | 直接 WASM 関数を呼んでいる利用者 |

**判断:** 即時除去を採用する。理由:

1. パッケージは pre-1.0 (`0.2.0`) -- SemVer の慣例で minor バンプ = breaking change OK
2. `includeVoice` のデフォルトは `false` -- 大多数のユーザーは voice を使っていない
3. voice データの実態は piper-plus では一切使用されていないデッドコード -- 段階的移行のメンテナンスコストが利益に見合わない
4. バージョンバンプ (`0.2.0` -> `0.3.0`) は M4 で実施する (本チケットのスコープ外)

### 5.3 段階的移行 vs 即時除去の判断

| 戦略 | メリット | デメリット |
|------|--------|----------|
| **即時除去 (採用)** | コードベースがクリーン、メンテナンスコストゼロ | 既存利用者のコードが壊れる |
| 段階的移行 | 後方互換を一時的に維持 | 非推奨コードのメンテナンス、テストの二重化、除去タイミングの管理コスト |

piper-plus の npm ダウンロード数と `includeVoice: true` の使用事例を考慮すると、即時除去が合理的。`CHANGELOG.md` に breaking change を明記することで対応する (M4 で実施)。

### 5.4 レビュー項目チェックリスト

- [x] WASM C++ シグネチャと JS 呼び出しの引数数が一致しているか
- [x] `_loadDict()` のエラーメッセージが `voiceData` を要求しなくなっているか
- [x] TypeScript 型定義が実装と一致しているか
- [x] `prepare-dictionary.sh` の assets.json テンプレートから voices が削除されているか
- [x] `pre-check.sh` のセクション番号がリナンバリングされているか
- [x] `test-headless.js` の生成 HTML テンプレート内の voice 参照が全て除去されているか
- [x] `simple-test.html` の `_openjtalk_initialize` 呼び出しが 1 引数になっているか

### 5.5 WASM ビルド CI トリガー (重大度: 低)

`wasm-build.yml` のトリガーパスに `src/wasm/openjtalk-web/src/` が含まれていない場合、M2 の C++ 変更が自動ビルドをトリガーしない。手動トリガーまたはパス追加が必要。

---

## 6. ゼロから作り直すとしたら

### 6.1 WASM G2P の API 設計原則

**「不要パラメータを API に含めない」** という原則を初日から適用すべきだった。

現在の `openjtalk_initialize(dic_dir, voice_path)` は OpenJTalk の本来の API (テキスト -> HTS 音声合成パイプライン) をそのままエクスポートした結果である。しかし piper-plus は音素抽出のみが目的であり、HTS 音声合成は使わない。ゼロから設計するなら:

```cpp
// Bad: 上流の API をそのまま露出
int openjtalk_initialize(const char* dic_dir, const char* voice_path);

// Good: 利用者の目的に合った最小 API
int openjtalk_phonemizer_init(const char* dic_dir);
```

WASM バイナリの公開 API は**利用者のユースケースに基づいて設計**すべきであり、上流ライブラリの内部 API をそのまま転送してはならない。上流に追加のパラメータがあっても、利用者が使わないなら WASM レイヤーで吸収する。これにより:

- 利用者は不要な依存 (voice ファイル ~50MB) を持ち込まずに済む
- API の表面積が小さくなり、breaking change のリスクが低減する
- テスト・ビルドインフラが不要な前提条件を持たなくなる

この原則は M4 のテスト設計にも直結する。M4 の「ネガティブテストの先行導入」(6.1) が主張する「依存の有無をパラメータ化テストで網羅する」アプローチは、本原則が初日から適用されていれば、voice パラメータ自体が API に入らなかったためテスト側での補完も不要だった。つまり **API 設計の最小化がテスト負荷の最小化に直結する**。

### 6.2 WASM ABI のバージョニング戦略

WASM 関数の ABI (引数の型・数・順序) は C の関数シグネチャそのものであり、バイナリ互換性が破壊されるとランタイムクラッシュする。従来の C 共有ライブラリと同様のバージョニング戦略が必要:

1. **ABI バージョン定数をエクスポートする:**
   ```cpp
   EMSCRIPTEN_KEEPALIVE
   int openjtalk_abi_version() { return 2; }
   ```
   JS 側で `mod._openjtalk_abi_version()` を呼び、期待するバージョンと一致しない場合は明示的なエラーメッセージを出す。

2. **新しい関数名で拡張する (既存を壊さない):**
   ```cpp
   // v1: 互換維持
   int openjtalk_initialize(const char* dic_dir, const char* voice_path);
   // v2: 新 API
   int openjtalk_initialize_v2(const char* dic_dir);
   ```
   ただしこの方式は dead code が蓄積するため、pre-1.0 では非推奨。

3. **WASM と JS のバージョン同期を CI で強制する:**
   WASM ビルドのハッシュと JS ラッパーの期待ハッシュを突き合わせるテストを追加し、不一致を PR マージ前にブロックする。

ゼロからなら方式 1 (ABI バージョン定数) を初日から導入し、引数変更時にバージョンをインクリメントする運用とする。

#### 6.2.1 Emscripten `EXPORTED_FUNCTIONS` とセマンティックバージョニングの紐付け

現在の piper-plus WASM ビルドでは `EMSCRIPTEN_KEEPALIVE` マクロで関数を個別にエクスポートしているが、エクスポート関数の一覧を一元管理するメカニズムがない。ゼロからなら:

1. **エクスポート関数を宣言的に管理する:**
   ```json
   // wasm-exports.json (ABI contract file)
   {
     "abi_version": 2,
     "functions": [
       "_openjtalk_phonemizer_init",
       "_openjtalk_synthesis_labels",
       "_openjtalk_clear",
       "_openjtalk_free_string",
       "_openjtalk_abi_version"
     ]
   }
   ```
   Emscripten ビルド時に `-s EXPORTED_FUNCTIONS=@wasm-exports.json` で参照し、JS 側の契約テスト (M4 テスト 3-5 に相当) もこのファイルをインポートして ABI 一致を検証する。

2. **ABI バージョンと npm バージョンの連動ルール:**
   - ABI の引数追加/削除/型変更 -> npm minor バンプ (pre-1.0) -> `wasm-exports.json` の `abi_version` インクリメント
   - 関数の新規追加のみ -> npm patch バンプ -> `abi_version` 据え置き
   - これにより `npm install @piper-plus/g2p@0.3.0` した時点で ABI v2 のバイナリが含まれることが保証される

3. **CI での ABI 一致テスト:**
   ```bash
   # CI step: wasm-abi-check
   node -e "
     const expected = require('./wasm-exports.json').functions;
     const wasm = require('./dist/rust-wasm/openjtalk.js');
     for (const fn of expected) {
       if (typeof wasm[fn] !== 'function') {
         console.error('Missing WASM export: ' + fn);
         process.exit(1);
       }
     }
   "
   ```
   M4 のテスト戦略 (6.2) が主張する「ビルド検証スクリプトのチェック項目を設定ファイルで管理」と同じ思想を ABI レベルにも適用する。

### 6.3 テスト/ビルドインフラの依存分離設計

今回最も修正量が多いのは openjtalk-web のテスト/ビルドスクリプト (11 ファイル) である。これらが voice ファイルに依存した根本原因は、**テストフィクスチャがプロダクション依存と分離されていなかった**ことにある。

ゼロから設計するなら:

1. **テストフィクスチャの明示的宣言:**
   テストが必要とする外部リソースを `test/fixtures/manifest.json` に宣言し、テストランナーがマニフェストに基づいてセットアップする。voice が不要なテストはマニフェストに voice を含めない。

2. **ビルドスクリプトの関心分離:**
   `prepare-dictionary.sh` は辞書のみを扱い、voice は `prepare-voice.sh` (もし必要なら) として分離する。1 つのスクリプトが辞書と voice の両方を扱うと、片方の除去がもう片方に波及する。

3. **アセット定義の最小化:**
   `assets.json` に voice メタデータを含めない。piper-plus が voice を使わないなら、メタデータファイルにも含めるべきではない。メタデータは**実際に使用されるリソースのみ**を記述する。

4. **npm パッケージの breaking change 管理:**
   pre-1.0 パッケージであっても、公開 API の型シグネチャ変更には `CHANGELOG.md` のエントリと migration guide を付ける。今回のように `JaDictData` から `voiceData` を削除する場合、型チェックで検出できるため実害は小さいが、利用者のアップグレードパスを文書化しておくべきである。

### 6.4 IndexedDB キャッシュの破壊的変更対策

M2 で `VOICE_CACHE_KEY` (`voice/mei_normal.htsvoice`) を削除すると、`0.2.x` で `includeVoice: true` を使っていたユーザーの IndexedDB には ~50MB の voice データが残留する。`DictLoader.clearCache()` は `store.clear()` で全エントリを削除するが、ユーザーが明示的に呼ばない限り voice データは永久に IndexedDB を占有する。

ゼロから設計するなら:

1. **キャッシュのバージョニング:**
   IndexedDB の `DB_VERSION` (現在 `1`) を ABI 変更時にインクリメントし、`onupgradeneeded` ハンドラで旧データを自動クリーンアップする:
   ```javascript
   // dict-loader.js
   const DB_VERSION = 2; // bumped for voice removal

   function openDB(dbName) {
     return new Promise((resolve, reject) => {
       const req = indexedDB.open(dbName, DB_VERSION);
       req.onupgradeneeded = (event) => {
         const db = event.target.result;
         // DB_VERSION 1 -> 2: voice キャッシュを自動削除
         if (event.oldVersion < 2) {
           const tx = event.target.transaction;
           const store = tx.objectStore('files');
           store.delete('voice/mei_normal.htsvoice');
         }
       };
       // ...
     });
   }
   ```
   これなら `0.2.x` -> `0.3.0` にアップデートした時点で、旧 voice キャッシュが自動的に除去される。

2. **キャッシュキーにバージョンプレフィックスを付与する:**
   `dict/v1/char.bin` のようにキャッシュキーにバージョン情報を埋め込み、API 変更時にプレフィックスを変更すれば旧キャッシュを自然に無効化できる。ただし旧データの自動削除は別途必要。

3. **ユーザー向けマイグレーション手順の文書化:**
   M4 の CHANGELOG に以下を追記すべき:
   ```
   ### Migration from 0.2.x
   If you previously used `includeVoice: true`, call `dictLoader.clearCache()`
   once after upgrading to remove the ~50MB cached voice file from IndexedDB.
   ```

### 6.5 npm deprecation ワークフロー

M2 の API 破壊的変更を `0.3.0` として publish した後、`0.2.x` ユーザーへの通知が必要である。現在のチケットでは CHANGELOG への記載のみだが、npm エコシステムの標準的な deprecation ワークフローが欠けている。

ゼロからなら以下を publish フローに組み込む:

1. **`0.2.x` の deprecation 通知:**
   ```bash
   npm deprecate "@piper-plus/g2p@<0.3.0" \
     "voiceData/includeVoice API removed in 0.3.0. See CHANGELOG for migration guide."
   ```
   これにより `npm install @piper-plus/g2p@0.2.0` 実行時に警告が表示される。

2. **README に Migration Guide セクションを追加:**
   ```markdown
   ## Upgrading from 0.2.x to 0.3.0

   ### Breaking Changes
   - `voiceData` is no longer accepted in `jaDict`. Remove the property.
   - `includeVoice` / `voiceUrl` options removed from `DictLoader.loadJaDict()`.
   - If you cached voice data, call `dictLoader.clearCache()` once to free ~50MB from IndexedDB.

   ### Before (0.2.x)
   const dict = await loader.loadJaDict({ includeVoice: true });
   const ja = new JapaneseG2P({ jaDict: dict });

   ### After (0.3.0)
   const dict = await loader.loadJaDict();
   const ja = new JapaneseG2P({ jaDict: dict });
   ```

3. **npm-publish.yml に deprecation ステップを追加:**
   タグ `g2p-v0.3.0` で publish が成功した後、自動的に `0.2.x` を deprecate する CI ステップを追加する。

### 6.6 Contract Testing (消費者駆動契約テスト) の導入

M2 の WASM ABI 変更と M4 のテスト追加を横断して見ると、WASM C++ 側 (Provider) と JS 呼び出し側 (Consumer) の間の契約が暗黙的であるという構造的問題が見える。M4 のテスト 5 (`DictLoader returns without voiceData`) はソースコードの静的検証で代替しているが、これはテストが脆く、リファクタリングに弱い。

ゼロから設計するなら、WASM ABI と JS 呼び出しの間に Consumer-Driven Contract Testing を導入する:

1. **契約定義ファイル:**
   ```json
   // contracts/wasm-js-contract.json
   {
     "provider": "openjtalk-wasm",
     "consumer": "@piper-plus/g2p",
     "interactions": [
       {
         "description": "initialize with dict path only",
         "function": "_openjtalk_initialize",
         "args": ["string"],
         "returns": "number"
       },
       {
         "description": "synthesize labels from text",
         "function": "_openjtalk_synthesis_labels",
         "args": ["string"],
         "returns": "string_ptr"
       }
     ]
   }
   ```

2. **Provider 側テスト (WASM ビルド後):**
   契約ファイルを読み込み、エクスポートされた関数のシグネチャが契約と一致することを検証する。

3. **Consumer 側テスト (JS):**
   M4 のテスト 3-5 を契約ファイルから自動生成する。これにより、WASM 側の引数変更が JS 側のテストに自動的に反映され、M2 で発生した「同一コミットで ABI と JS を同時に変更しなければならない」というリスクが CI レベルで検出可能になる。

M4 のテストピラミッドの観点から言えば、テスト 1-2 (C++ GoogleTest) は unit テスト、テスト 3-5 (JS contract) は integration テスト、テスト 6 (shell verify-build) は E2E テストに相当する。契約テストはこの unit/integration の境界に位置し、WASM ABI という境界面を明示的にカバーするレイヤーである。

---

## 7. 後続タスクへの連絡事項

| 後続チケット | 連絡内容 |
|------------|---------|
| **M4-001** (テスト追加 + クリーンアップ) | M2 完了後に以下を実施すること: (1) `test-g2p-contract.js` に voice-free 初期化テスト 3 件を追加 (タスク 4.3-4.5)、(2) `verify-build.sh` に voice 不在の逆テスト (タスク 4.6)、(3) `@piper-plus/g2p` を `0.2.0` -> `0.3.0` にバンプ (タスク 4.9)、(4) `CHANGELOG.md` に breaking change 記載 (タスク 4.10) |
| **M1-001** (C++ ランタイム) | M2 は M1 と独立して並行作業可能。WASM C++ ラッパー (`simple_wrapper.cpp`) は C++ ランタイム (`openjtalk_wrapper.c`, `openjtalk_optimized.c`) とは別のコードパスであり、相互に影響しない |
| **M3-001** (CI/CMake) | M2 の変更は CI ワークフロー (`wasm-build.yml`) に間接的に影響する可能性がある。WASM ビルド CI が voice ファイルを前提としている場合、M3 で対応が必要。ただし `wasm-build.yml` の voice 依存は M2 のスコープ内で除去されるため、M3 では追加対応不要の見込み |
| **npm publish** | M2 完了後に `@piper-plus/g2p` を publish する場合、M4 のバージョンバンプ完了後とすること。M2 の変更だけでは `package.json` の version が `0.2.0` のままであり、breaking change が既存バージョンで配布されるリスクがある |

### M4-001 への引き継ぎ

1. **WASM ABI 変更**: `_openjtalk_initialize` のパラメータ数が 2→1 に変更済み。M4 のテスト 4.3-4.5 はこの変更を前提とする
2. **DictLoader API 変更**: `includeVoice`, `voiceUrl` オプションが除去済み。M4 のテスト 4.5 (DictLoader 契約テスト) の前提
3. **TypeScript 型定義変更**: `JaDictData.voiceData`, `DictLoadOptions.includeVoice`, `DictLoadOptions.voiceUrl` が削除済み
4. **`@piper-plus/g2p` バージョンバンプ未実施**: M2 ではバージョンバンプを行わない。M4 で `0.2.0` → `0.3.0` にバンプすること
5. **WASM リビルド済み**: `simple_wrapper.cpp`, `phonemizer_wrapper.cpp` の ABI 変更は WASM リビルドにより反映済み

### dev マージ時の注意

- M2 は M1 と並行開発可能だが、dev へのマージは M1 完了後を推奨 (M3 の前提条件と整合させるため)
