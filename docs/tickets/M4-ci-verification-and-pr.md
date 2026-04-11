# M4: CI 検証 + PR 作成

> **マイルストーン:** [M4](../milestones-346-cpp-cjk-closing-bracket.md#m4-ci-検証--pr-作成)
> **Issue:** [#346](https://github.com/ayutaz/piper-plus/issues/346)
> **ブランチ:** `fix/cpp-cjk-closing-bracket-346`
> **前提チケット:** [M3](M3-update-test-mirror-and-add-tests.md)
> **後続チケット:** なし

---

## 1. タスク目的とゴール

M1-M3 の全変更 (`isClosingPunctuation()` ヘルパー追加、閉じ括弧消費ループ追加、テストミラー更新 + 10テストケース追加) が CI 全環境で正常に動作することを検証し、PR を作成してレビュー依頼を行う。

### 完了の定義

- ローカルビルドで `test_split_sentences` の全テスト (既存 + 新規10個) が PASS
- ローカルで全 C++ テスト (integration/audio_regression 除く) がリグレッションなしで PASS
- PR が作成済み
- CI の全マトリックス (`ci.yml`: 3 OS x 2 BuildType = 6 パターン + `cpp-tests.yml`: 2 パターン) がグリーン

---

## 2. 実装する内容の詳細

### 2.1 ローカル検証手順

以下の3段階で検証する。

**Stage 1: 対象テストのみビルド・実行**

```bash
# ビルド (test_split_sentences のみ)
cmake -B build -DBUILD_TESTS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --target test_split_sentences

# テスト実行
ctest -R test_split_sentences -V --test-dir build
```

期待: 既存 26 テスト + 新規 10 テスト = 36 テスト全 PASS。

**Stage 2: 全 C++ テスト実行 (リグレッション確認)**

```bash
# 全テストビルド
cmake --build build

# integration/audio_regression を除く全テスト (モデルファイル不要)
ctest -E "test_c_api_integration|test_c_api_audio_regression" --test-dir build --output-on-failure -V
```

期待: `test_split_sentences`, `test_streaming_simple`, `test_c_api`, `test_phonemize`, `test_piper_core` 等の全ユニットテストが PASS。

**Stage 3: Debug ビルドでの確認 (任意)**

```bash
cmake -B build-debug -DBUILD_TESTS=ON -DCMAKE_BUILD_TYPE=Debug
cmake --build build-debug
ctest -R test_split_sentences -V --test-dir build-debug
```

期待: Debug ビルドでもアサーション違反なしで全テスト PASS。

### 2.2 PR 作成

**タイトル:**

```
fix(cpp): consume closing brackets after sentence terminators (#346)
```

**本文テンプレート:**

````markdown
## Summary

- `splitTextToSentences()` が文末記号 (。！？.!?) の後の CJK 閉じ括弧 (」『）等) を消費しないバグを修正
- Rust/C#/Go と同一の動作に統一

## Changes

- `isClosingPunctuation()` ヘルパー関数追加 (14文字の閉じ括弧文字セット)
- boundary punctuation 消費ループの直後に閉じ括弧消費ループを追加
- テストミラー更新 + 10個の新規テストケース追加

## Before/After

```
入力: 「こんにちは。」次の文。

Before: ["「こんにちは。", "」次の文。"]  -- 」が次文に漏れる
After:  ["「こんにちは。」", "次の文。"]  -- 正しい
```

## Test plan

- [x] `ctest -R test_split_sentences -V` で新規10テスト全 PASS
- [x] リグレッション確認: 既存26テスト全 PASS
- [x] 全 C++ ユニットテスト PASS (integration 除く)
- [ ] CI 全マトリックス (3 OS x 2 BuildType) グリーン

## Reviewer notes

- 変更ファイル: `src/cpp/piper.cpp` + `src/cpp/tests/test_split_sentences.cpp` の2ファイルのみ
- ヘッダー変更なし、CMake 変更なし、依存追加なし
- テストミラーパターンの制約 (ONNX Runtime リンク回避) によりテストファイルに同一ロジックのコピーあり
- Go の depth tracking 方式は採用していない (既存アーキテクチャとの整合性優先)
````

**レビューポイント:**

| # | 確認項目 | ファイル:行 (M1-M3 適用後の推定) |
|---|---------|------------|
| 1 | `isClosingPunctuation()` の14文字が Rust/C#/Go のスーパーセットであること | `piper.cpp`: `splitTextToSentences()` 直前 |
| 2 | 消費ループが `hasTerminator` ガード付きであること | `piper.cpp`: `i = punctEnd - 1` 直前 |
| 3 | テストミラーが `piper.cpp` と完全一致していること | `test_split_sentences.cpp` 匿名名前空間内 |
| 4 | テスト #10 (`NoTerminatorNoop`) が `hasTerminator` ガードの正しさを証明すること | `test_split_sentences.cpp` 末尾 |

### 2.3 CI マトリックス確認

PR を dev へ作成すると、2つのワークフローが同時起動する。

**`ci.yml` の `cpp-tests` ジョブ (6パターン):**

| # | OS | Build Type | ランナー | タイムアウト |
|---|-----|-----------|---------|------------|
| 1 | Ubuntu 22.04 | Release | `ubuntu-22.04` | 25分 |
| 2 | Ubuntu 22.04 | Debug | `ubuntu-22.04` | 25分 |
| 3 | macOS latest | Release | `macos-latest` (Apple Silicon) | 25分 |
| 4 | macOS latest | Debug | `macos-latest` (Apple Silicon) | 25分 |
| 5 | Windows latest | Release | `windows-latest` | 25分 |
| 6 | Windows latest | Debug | `windows-latest` | 25分 |

**`cpp-tests.yml` (standalone, 2パターン):**

| # | OS | Build Type | ランナー | タイムアウト |
|---|-----|-----------|---------|------------|
| 1 | Ubuntu latest | Release | `ubuntu-latest` | 25分 |
| 2 | macOS latest | Release | `macos-latest` (Apple Silicon) | 25分 |

> **Note:** `cpp-tests.yml` は Release のみ・Windows なしの軽量マトリックス。全6パターンの検証は `ci.yml` 側で行われる。ブランチ保護の required check は `ci.yml` の `ci-required` ジョブ。

**CI トリガー条件:**

`ci.yml` は `dorny/paths-filter` で変更検出を行い、`cpp` または `ci-config-cpp` が `true` のとき `cpp-tests` ジョブが起動する:

```yaml
# ci.yml の paths-filter (cpp 関連部分)
cpp:
  - 'src/cpp/**'
  - 'CMakeLists.txt'
  - 'cmake/**'
ci-config-cpp:
  - '.github/workflows/ci.yml'
  - '.github/workflows/_build-test-cpp.yml'
  - '.github/workflows/cpp-tests.yml'
  - '.github/workflows/cpp-lint.yml'
```

別途 `cpp-tests.yml` (standalone) も独自の `paths` トリガーを持つが、こちらは `cmake/**` を含まない:

```yaml
# cpp-tests.yml の paths トリガー
paths:
  - 'src/cpp/**'
  - 'CMakeLists.txt'
  - '.github/workflows/cpp-tests.yml'
  - '.github/workflows/_build-test-cpp.yml'
```

`src/cpp/piper.cpp` と `src/cpp/tests/test_split_sentences.cpp` の変更により、`ci.yml` の `cpp` フィルタと `cpp-tests.yml` の `paths` トリガーの両方がマッチし、CI が自動起動される。

**CI 実行内容** (`_build-test-cpp.yml`):

1. OS 別依存インストール (ONNX Runtime 1.14.1)
2. ビルドキャッシュ (ccache, Unix のみ)
3. CMake configure (`-DBUILD_TESTS=ON -DPIPER_PLUS_BUILD_SHARED=ON -DUSE_CUDA=OFF`)
4. ビルド (Windows は `--parallel 2` に制限)
5. OpenJTalk 辞書ダウンロード
6. espeak-ng-data ダウンロード
7. テストモデルキャッシュ/ダウンロード (`run-integration-tests: true` 時)
8. Dead code lint guard (`#if 0` チェック, Unix のみ)
9. `ctest -C <BuildType> --output-on-failure -V --timeout 120` で全テスト実行
10. 共有ライブラリインストール + シンボル検証 (Unix のみ)
11. C API サンプルコンパイル検証 (Unix のみ)

**CI で実行される test_split_sentences 以外の重要テスト:**

| テスト名 | 検証内容 | 本変更への関連 |
|---------|---------|-------------|
| `test_streaming_simple` | ストリーミングチャンキング + クロスフェードのユニットテスト | 影響なし (独自の分割ロジックを使用、`splitTextToSentences()` は呼ばない) |
| `test_c_api` | C API null safety + パラメータ検証 | 間接影響 (`piper_plus_synth_start` 経由) |
| `test_c_api_integration` | フル音声合成パイプライン | 間接影響 (文分割改善) |
| `test_c_api_audio_regression` | 音声出力の決定論的一貫性 | 影響なし (テスト入力に閉じ括弧パターンなし) |
| `test_streaming` | ストリーミング音声合成 E2E | 間接影響 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| **PR 作成エージェント** | 1名 | ローカル検証実行、コミットメッセージ作成、`gh pr create` による PR 作成 |
| **CI 結果確認エージェント** | 1名 | CI 全パターン (`ci.yml` 6 + `cpp-tests.yml` 2) のログ確認、失敗時の原因切り分け・修正 |
| **最終レビューエージェント** | 1名 | PR の diff レビュー、テストミラーと `piper.cpp` の一致確認、文字セット網羅性の最終チェック |

**合計: 3名**

**ワークフロー:**

1. PR 作成エージェントがローカル検証を完了し PR を作成
2. CI が自動起動、CI 結果確認エージェントが監視
3. CI 全グリーンを確認後、最終レビューエージェントが approve
4. CI 失敗時は CI 結果確認エージェントが原因を特定し、PR 作成エージェントが修正コミットを追加

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲

**含むもの:**

- ローカルビルド・テスト実行の結果確認
- PR の作成 (タイトル、本文、レビュー依頼)
- CI 結果の確認と必要な修正
- 最終レビュー承認

**含まないもの:**

- 新規コード変更 (M1-M3 で完了済み)
- テストケースの追加 (M3 で完了済み)
- ドキュメント更新 (変更が小規模のため不要)
- マージ後のリリースノート作成

### 4.2 ユニットテスト

M3 で追加された10テストが CI 全環境で PASS すること。

**新規テスト一覧:**

| # | テスト名 | 検証内容 |
|---|---------|---------|
| 1 | `CJKClosingBracket_BasicKakko` | 基本: `「...。」` が正しく1文に含まれる |
| 2 | `CJKClosingBracket_DoubleCornerBracket` | 二重鉤括弧: `『...！』` |
| 3 | `CJKClosingBracket_FullwidthParen` | 全角丸括弧: `（...。）` |
| 4 | `CJKClosingBracket_Sumitsuki` | 墨付き括弧: `【...。】` |
| 5 | `CJKClosingBracket_HalfwidthKakko` | 半角鉤括弧: `｢...。｣` |
| 6 | `CJKClosingBracket_MultipleBrackets` | 連続閉じ括弧: `「『OK。』」` |
| 7 | `WesternClosingQuote` | 英語引用符: `"Hello."` |
| 8 | `WesternClosingParen` | 英語丸括弧: `(ok.)` |
| 9 | `CJKClosingBracket_NoClosingNoop` | リグレッション: 閉じ括弧なしの文は既存動作と同一 |
| 10 | `CJKClosingBracket_NoTerminatorNoop` | `hasTerminator` ガード: 文末記号なしの括弧は消費しない |

**既存テスト (26個) も全 PASS であること:**

- `SplitSentencesTest` 系: 22テスト (Japanese, English, Multilingual, Chinese, Edge cases, Issue #343, Ellipsis)
- `DynamicChunkSizeTest` 系: 4テスト

### 4.3 E2Eテスト

以下の既存 E2E テストが全環境でリグレッションなしで PASS すること。

**Integration テスト (`test_c_api_integration`, 22テスト、主要なもの抜粋):**

| テスト名 | 関連性 |
|---------|--------|
| `OneShotProducesAudio` | 文分割 -> 音素化 -> 合成のフルパイプライン |
| `OneShotJapanese` | 日本語テキストの文分割を経由 |
| `IteratorProducesChunks` | ストリーミングで `splitTextToSentences()` を使用 |
| `IteratorVsOneShot` | one-shot とストリーミングの出力一致 |
| `CallbackInvoked` | コールバックストリーミングが正常動作 |

> 他 17 テスト (`CallbackUserData`, `QuerySampleRate`, `QueryNumSpeakers`, `QueryNumLanguages`, `LanguageIdLookup`, `BusyDuringIterator`, `IteratorReuse`, `CustomDictLoadAndCount`, `PhonemizeProducesOutput`, `AvailableLanguagesNonEmpty`, `TimingAfterSynthesis`, `IteratorCrossfadeSmoothBoundary`, `IteratorVsOneShotParityWithCrossfade`, `SingleSentenceNoCrossfadeEffect`, `CallbackCrossfadeApplied`, `IteratorDoneCanCarrySamples`, `IteratorAlwaysProcessSamplesBeforeCheckingDone`) は間接影響のみ。

**Audio Regression テスト (`test_c_api_audio_regression`, 5テスト):**

| テスト名 | 関連性 |
|---------|--------|
| `JA_Greeting` | 日本語合成のサンプル数・RMS が安定 |
| `EN_Greeting` | 英語合成の安定性 |
| `Streaming_vs_OneShot` | ストリーミングと one-shot の出力パリティ |
| `DeterministicConsistency` | 決定論的出力の一貫性 |
| `CallbackStreaming_vs_OneShot` | コールバック方式のパリティ |

**Streaming テスト (`test_streaming_simple`, 11テスト):**

| テスト名 | 関連性 |
|---------|--------|
| `TextChunkingEnglish` | 英語テキストのチャンキング (独自の regex 分割ロジック) |
| `TextChunkingJapanese` | 日本語テキストのチャンキング (独自の手動 UTF-8 パース) |
| `EmptyTextProducesNoChunks` | 空テキスト処理 |
| `SingleSentenceProducesOneChunk` | 単一文チャンキング |
| `DynamicChunkSizeCalculation` | チャンクサイズ計算 |
| `CrossfadeAudioChunks` | クロスフェード処理 |
| `LinearCrossfadeTwoChunks` | 2チャンクのクロスフェード |
| `ThreeChunksIntermediateCrossfade` | 3チャンクの中間クロスフェード |
| `ShortChunkSkipsCrossfade` | 短チャンクのクロスフェードスキップ |
| `SingleChunkNoCrossfade` | 単一チャンクではクロスフェードなし |
| `TotalSamplesPreserved` | 総サンプル数保存 |

---

## 5. 懸念事項とレビュー項目

### 5.1 CI タイムアウト

| リスク | レベル | 対策 |
|--------|-------|------|
| Windows Debug ビルドのタイムアウト | **中** | CI タイムアウトは 25分。Windows Debug は並列度 2 (`--parallel 2`) に制限済み。テスト追加10個はビルド時間に影響しない (同一バイナリ内) |
| ExternalProject ダウンロード遅延 | **低** | ONNX Runtime / OpenJTalk 辞書 / espeak-ng-data のダウンロードキャッシュが有効。2回目以降は高速 |

**対処:** タイムアウト発生時は CI ログの `cmake --build` ステップと `ctest` ステップの実行時間を確認。テストの追加はビルド時間に影響を与えないため (既存バイナリに追加されるだけ)、タイムアウトの原因は通常インフラ側。

### 5.2 Windows UTF-8 問題

| リスク | レベル | 理由 |
|--------|-------|------|
| テスト文字列の UTF-8 エンコーディング | **低** | `test_split_sentences.cpp` は `u8"..."` リテラルを使用。MSVC は `/utf-8` フラグなしでも `u8` リテラルを正しく処理する (C++11 以降) |
| ファイルの BOM 問題 | **低** | 既存の `test_split_sentences.cpp` が Windows CI で PASS しているため、既に問題なし |
| コンソール出力の文字化け | **なし** | テスト結果はバイト比較であり、コンソール表示のエンコーディングには依存しない |

**対処:** Windows CI で新規テストのみ FAIL する場合は、`u8` リテラルのバイト列を `EXPECT_EQ` のエラーメッセージで確認。

### 5.3 テストミラー乖離警告

| リスク | レベル | 理由 |
|--------|-------|------|
| 将来の `piper.cpp` 変更時にミラー更新忘れ | **中** | テストファイルは `piper.cpp` の `splitTextToSentences()` を匿名名前空間にコピーしているため、本体変更時にミラーが乖離するリスクがある |

**対処:**

- `test_split_sentences.cpp` の冒頭コメント (1-6行) で「piper.cpp のミラーである」ことを明記済み
- `piper.cpp` の `splitTextToSentences()` 直前にもテストミラーの存在を示すコメントを追加すべき (PR レビュー時に確認)
- 中期的には `piper_text_utils.hpp` への切り出しでミラーを廃止 (別 Issue で追跡)

### 5.4 レビューチェックリスト

- [ ] `piper.cpp` の `isClosingPunctuation()` とテストミラーの `isClosingPunctuation()` が文字セット・ロジックともに完全一致
- [ ] 消費ループのテストミラーが `piper.cpp` と完全一致 (`hasTerminator` ガード、`while` 条件、`punctEnd++`)
- [ ] 新規テスト10個が全て意味のある入力・期待出力を持つ
- [ ] テスト #10 (`NoTerminatorNoop`) が `hasTerminator` ガードの防御を証明している
- [ ] 既存テスト26個の期待出力が変更されていないこと (リグレッション防止)
- [ ] PR 本文に Before/After の具体例があること

---

## 6. ゼロから作り直すとしたら

CI 戦略とテスト設計を一から考える場合のアイデア。

### 6.1 言語横断テスト (Cross-runtime contract test)

全4ランタイム (C++/Rust/C#/Go) で同一入力に対して同一出力を検証する CI ジョブ。

```yaml
cross-runtime-split-test:
  runs-on: ubuntu-latest
  steps:
    - run: |
        # 各ランタイムで同じテストケースを実行
        echo '「こんにちは。」次の文。' | cpp-split
        echo '「こんにちは。」次の文。' | rust-split
        echo '「こんにちは。」次の文。' | csharp-split
        echo '「こんにちは。」次の文。' | go-split
        # 出力を diff で比較
```

**メリット:** ランタイム間の動作乖離を CI で自動検出
**コスト:** 各ランタイムの CLI ビルドが必要、CI 時間増加
**現実性:** 中期的に検討。現状は各ランタイムのテストが独立に同等のケースをカバーしている

### 6.2 Contract test CI (仕様駆動テスト)

`docs/spec/sentence-split-contract.toml` に全テストケースを定義し、各ランタイムの CI がこの仕様ファイルから自動生成したテストを実行する。

```toml
# docs/spec/sentence-split-contract.toml
[[test_cases]]
name = "CJK closing bracket basic"
input = "「こんにちは。」次の文。"
expected = ["「こんにちは。」", "次の文。"]
tags = ["cjk", "closing-bracket"]
```

**メリット:** Single Source of Truth、新テストケース追加時に全ランタイムに自動反映
**コスト:** TOML パーサー + テスト生成スクリプトの開発・保守
**現実性:** 高い。`docs/spec/ort-session-contract.toml` の前例あり。文分割は全ランタイム共通仕様であるべき

### 6.3 テストミラー自動同期

`piper.cpp` の `splitTextToSentences()` とその依存関数を抽出し、テストファイルに自動コピーするスクリプト。

```bash
# scripts/sync_test_mirror.sh
sed -n '/^static bool isClosingPunctuation/,/^}/p' src/cpp/piper.cpp \
  > /tmp/mirror_funcs.cpp
# ... テストファイルの匿名名前空間に注入
```

**メリット:** ミラー乖離を根本的に防止
**コスト:** スクリプト保守、CI での差分チェック追加
**現実性:** 低い (fragile)。ヘッダー分離のほうが本質的な解決

### 6.4 PR テンプレート標準化

`.github/pull_request_template.md` に C++ 変更用のチェックリストを追加:

```markdown
## C++ Changes Checklist
- [ ] テストミラーが piper.cpp と一致
- [ ] 3 OS x 2 BuildType の CI 全グリーン
- [ ] Dead code (#if 0) なし
- [ ] ヘッダー公開の必要性を検討
```

**現実性:** 高い。即座に導入可能。ただし Issue #346 のスコープ外

---

## 7. 後続タスクへの連絡事項

M4 は本 Issue (#346) の最終マイルストーン。PR マージ後の将来的な改善候補を記録する。

### 7.1 Depth tracking (Go 方式の括弧追跡)

Go の `text_splitter.go` は括弧の depth を追跡し、括弧内の文末記号では分割を抑制する。

```
入力: 彼は「元気です。」と言った。終わり。

Go:  ["彼は「元気です。」と言った。", "終わり。"]  -- 2文 (括弧内抑制)
C++: ["彼は「元気です。」", "と言った。", "終わり。"]  -- 3文 (抑制なし)
```

C++/Rust/C# の3ランタイムは depth tracking を実装していない。将来的に統一する場合は全ランタイム同時に対応すべき。

### 7.2 Python 対応

Python (`src/python_run/piper/phonemize/japanese.py`) は `re.compile(r"(?<=[。！？\n])")` による単純 regex 分割で、C++ と同じ閉じ括弧未消費問題を抱える。ストリーミング用途ではないため優先度は低いが、一貫性のために対応を検討。

### 7.3 テストミラー廃止 (ヘッダー分離)

`splitTextToSentences()` 周辺のヘルパー群を `piper_text_utils.hpp` に切り出し、テストファイルから直接 include 可能にする。

**対象関数:**
- `isPunctCodepoint()`
- `calculateDynamicChunkSize()`
- `isClosingPunctuation()`
- `isBoundaryPunct` (現在ラムダ)
- `isSentenceTerminator` (現在ラムダ)

**課題:** `isBoundaryPunct` と `isSentenceTerminator` は `phonemeType` に依存するため、関数化にはインターフェース設計が必要。

### 7.4 4ランタイム統一仕様

全ランタイム (C++/Rust/C#/Go) の文分割動作を `docs/spec/sentence-split-contract.toml` として文書化し、CI で横断検証する。

**統一すべき項目:**
- 閉じ括弧文字セット (現在14文字だが Go は8文字)
- 文末記号文字セット (Go のみ `．` U+FF0E を含む)
- Depth tracking の有無 (Go のみ実装)
- 略語認識の有無 (Rust `text_splitter.rs` のみ実装)

**推奨:** まず文字セットの統一から着手し、動作の統一は段階的に進める。
