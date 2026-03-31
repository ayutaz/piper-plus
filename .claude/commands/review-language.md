# 新言語実装レビュー

piper-plus の新言語実装を徹底的にレビューするスキルです。引数 `$ARGUMENTS` に言語コード (例: `sv`, `de`) を指定してください。

## 前提条件

- Python テストは `uv run python -m pytest` で実行
- 10エージェント並列でレビュー実施
- 全プラットフォーム (Python/Rust/C++/C#/JS) を検証

---

## レビュー手順

### Step 1: 10エージェント並列レビュー

以下の10エージェントを **並列** で起動してレビューを実施:

#### Agent 1: Python G2P 品質
- `src/python/piper_train/phonemize/$ARGUMENTS.py` を読み、全G2Pルールの正確性を検証
- 代表的な10単語のスポットチェック (言語固有の音韻規則に基づく)
- 例外語リストの完全性確認
- IPA シンボルの正確性 (ɡ≠g, ɧ≠ɕ 等)

#### Agent 2: Python 前処理・推論パス
- `src/python/piper_train/preprocess.py` — `--language $ARGUMENTS` が動作するか
- `src/python/piper_train/infer_onnx.py` — ヘルプテキスト、`_detect_dominant_language`
- `src/python/piper_train/tools/prepare_multilingual_dataset.py` — LANGUAGE_ID_MAP
- `src/python/piper_train/phonemize/registry.py` — 登録確認
- `src/python/piper_train/phonemize/multilingual_id_map.py` — LANGUAGE_PHONEMES
- config.json 生成パス (phoneme_id_map, language_id_map, num_languages)

#### Agent 3: PUA 整合性 (全5プラットフォーム)
- Python `token_mapper.py` — FIXED_PUA_MAPPING、_PUA_START
- Rust `token_map.rs` — FIXED_PUA_MAP、PUA カウントテスト
- C++ ソース — PUA 定数定義
- C# `OpenJTalkToPiperMapping.cs` — TokenToChar エントリ
- 全プラットフォームで同一コードポイントを使用しているか
- 既存言語との PUA 衝突がないか

#### Agent 4: Rust 実装完全性
- `src/rust/piper-core/src/phonemize/$ARGUMENTS.rs` — 全ルール実装
- `src/rust/piper-core/src/phonemize/mod.rs` — module export
- `src/rust/piper-core/src/voice.rs` — ケース処理 + default_latin
- `src/rust/piper-core/src/phonemize/multilingual.rs` — 言語検出
- `src/rust/piper-cli/src/main.rs` — SUPPORTED_LANGUAGES
- TODO/FIXME/unimplemented! の有無

#### Agent 5: C++ 実装完全性
- `src/cpp/$ARGUMENTS_phonemize.cpp/.hpp` — 全ルール実装
- `src/cpp/piper.cpp` — ディスパッチ + #include
- `src/cpp/language_detector.cpp/.hpp` — 言語検出
- `CMakeLists.txt` — ビルド設定
- `src/cpp/tests/CMakeLists.txt` — テストターゲット
- ASCII化されたダイアクリティカルマーク (ö→o 等) がないか **要注意**

#### Agent 6: C# 実装完全性
- G2P エンジン — Python の全ルールが移植されているか
- Phonemizer ラッパー — IPhonemizer 準拠
- PUA マッピング — OpenJTalkToPiperMapping
- UnicodeLanguageDetector — 言語検出
- CLI Program.cs — ケース処理
- スタブ実装でないことを確認 (TODO/character-level fallback 検出)

#### Agent 7: JS/WASM 実装確認
- `simple_unified_api.js` — 言語検出ロジック
  - **セグメントレベルスコアリング** を使用しているか (早期リターンではないか)
  - Python と同じ elif パターンか
  - Latin 文字範囲に × (U+00D7) と ÷ (U+00F7) が含まれていないか
- `types/index.d.ts` — Language 型に追加されているか
- テストファイルが存在するか

#### Agent 8: テスト網羅性
- Python: テスト数、カテゴリ網羅 (母音/子音/特殊ルール/ストレス/借用語/エッジケース)
- Rust: `#[cfg(test)]` テスト数
- C++: GoogleTest テスト数
- C#: xUnit テスト数
- JS: Node.js テスト数
- **最低テスト数目安**: Python 100+, Rust 30+, C++ 25+, C# 40+, JS 30+

#### Agent 9: CI 実行確認
- `.github/workflows/cpp-tests.yml` — テスト実行リストに含まれるか
- `.github/workflows/ci.yml` — テスト実行リストに含まれるか
- `.github/workflows/dev-build-all.yml` — スモークテストに含まれるか
- C#: `dotnet test` で自動検出されるか
- Rust: `cargo test` で自動検出されるか
- Python: `pytest` マーカーが正しいか
- **フォールバック通過ロジック** がないか (テスト未発見でもパスする CI)

#### Agent 10: ドキュメント + 学習パイプライン
- CLAUDE.md — フォネマイザーテーブル、ファイルパス
- README (4言語版) — 言語数更新
- npm README — 言語テーブル
- 学習パイプライン制約:
  - `num_languages` ハードコード制限がないか
  - `emb_lang` 次元制限がないか
  - language-balanced-sampling が N 言語で動作するか
  - ONNX エクスポートが N 言語に対応するか

---

### Step 2: レビュー結果集約

各エージェントの結果を以下のテーブルに集約:

| # | 領域 | 状態 | 問題数 | クリティカル |
|---|------|------|--------|------------|
| 1 | Python G2P | ? | ? | ? |
| 2 | Python 推論パス | ? | ? | ? |
| 3 | PUA 整合性 | ? | ? | ? |
| 4 | Rust | ? | ? | ? |
| 5 | C++ | ? | ? | ? |
| 6 | C# | ? | ? | ? |
| 7 | JS/WASM | ? | ? | ? |
| 8 | テスト網羅性 | ? | ? | ? |
| 9 | CI | ? | ? | ? |
| 10 | ドキュメント | ? | ? | ? |

---

### Step 3: 修正サイクル

クリティカル問題が見つかった場合:
1. 問題を修正
2. テスト実行 (`uv run python -m pytest`, `cargo test`, `dotnet test`, `node --test`)
3. 再レビュー (修正部分のみ)
4. コミット

---

### Step 4: 最終検証

全修正完了後:
1. `uv run python -m pytest src/python/tests/test_$ARGUMENTS_*.py -x -q` — Python テスト
2. `cargo test -p piper-plus` — Rust テスト
3. `dotnet test src/csharp/PiperPlus.sln` — C# テスト
4. `node --test src/wasm/openjtalk-web/test/js/test-$ARGUMENTS.js` — JS テスト
5. `git push` → CI 全ジョブ通過確認

---

## よくある問題パターン

### PUA 関連
- **衝突**: 既存言語の PUA 範囲と重複 → `_PUA_START` 確認
- **カウント不一致**: Rust/C# テストで PUA 総数アサーション失敗 → 全プラットフォーム更新

### ラテン文字言語の検出
- **早期リターン**: JS で最初の文字/単語で即判定 → セグメントレベルに修正
- **精算漏れ**: `infer_onnx.py` の `_detect_dominant_language` 未対応 → 精算追加
- **CLI 拒否**: Rust `SUPPORTED_LANGUAGES` に未登録 → 追加

### C++ 固有
- **ASCII化ダイアクリティカル**: 例外語リストの ö→o, ä→a → UTF-8 文字列確認
- **リンカエラー**: CMakeLists.txt にソース未追加 → 3ターゲットすべてに追加

### CI 固有
- **テスト未実行**: ハードコードされたテストリストに未追加 → whitelist 更新
- **フォールバック通過**: テスト未発見でも CI パス → ログ確認

### C# 固有
- **スタブ実装**: `DotNet[Lang]G2PEngine` が文字レベルフォールバック → フルエンジン実装
