# M2-1: textToAudio の音素化ループを再利用可能関数に抽出

> **Phase:** 2 --- ストリーミング + テスト
> **見積り:** 中
> **依存:** Phase 1 完了 (M1-8)
> **ブロック:** M2-2, M2-3
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m2-1-texttoadio-の音素化ループを再利用可能関数に抽出)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

`textToAudio()` (piper.cpp L1050-1515) は 460 行超のモノリシック関数で、音素化 (L1067-1309)、phoneme_ids 変換 (L1319-1481)、合成 (L1469) がすべて単一関数内に収められている。

Phase 2 の Iterator パターン (M2-2) では「テキスト -> 文リスト -> 1文ずつ合成」という流れが必要だが、現在の `textToAudio()` は一括処理のみ。音素化ロジックを独立関数に抽出し、M2-2 / M2-3 から再利用可能にする。

**ゴール:**
- `textToAudio()` の音素化ロジックを `phonemizeText()` 関数に抽出する
- `textToAudioStreaming()` の文分割ロジック (L1689-1729) を `splitTextToSentences()` 関数に抽出する
- 既存の `textToAudio()` / `textToAudioStreaming()` は抽出関数を呼ぶようリファクタする
- 既存テストが回帰しないこと

---

## 2. 実装する内容の詳細

### 2.1 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/cpp/piper.hpp` | 新しい関数宣言を追加 |
| `src/cpp/piper.cpp` | 音素化ロジック抽出 + 文分割ロジック抽出 + 既存関数リファクタ |

### 2.2 抽出する関数 (1): `phonemizeText()`

`textToAudio()` の L1067-1309 を抽出。テキストを受け取り、音素列 (文単位) と prosody 特徴量を返す。

```cpp
// piper.hpp に追加
struct PhonemizeResult {
    std::vector<std::vector<Phoneme>> phonemes;        // 文ごとの音素列
    std::vector<std::vector<ProsodyFeature>> prosody;   // 文ごとの prosody (optional)
};

/// テキストを音素列に変換する (textToAudio の音素化ロジックを抽出)
///
/// @param voice        音声モデル設定
/// @param text         入力テキスト (UTF-8)
/// @param result       出力: 文ごとの音素列と prosody 特徴量
/// @param externalProsody  外部 prosody データ (nullptr なら内部生成)
///
/// @note voice.synthesisConfig.languageId を自動検出で変更する可能性がある。
///       呼び出し側で save/restore が必要。
void phonemizeText(Voice &voice, const std::string &text,
                   PhonemizeResult &result,
                   const std::vector<ProsodyFeature> *externalProsody = nullptr);
```

**抽出対象コード (piper.cpp L1067-1317):**

1. `parsePhonemeNotation(text)` によるテキストセグメント分割
2. 各セグメントの処理:
   - `isPhonemes == true`: `parsePhonemeString()` で直接音素変換
   - `OpenJTalkPhonemes`: `phonemize_openjtalk()` / `phonemize_openjtalk_with_prosody()`
   - `MultilingualPhonemes`: `UnicodeLanguageDetector` + 言語別音素化 + dominant language 検出
3. `externalProsody` による上書き処理

**注意点:**
- L1270-1284 の `detectDominantLanguage()` は `voice.synthesisConfig.languageId` を変更する副作用がある。この副作用は `textToAudio()` 側で `originalLanguageId` を save/restore する既存パターンで管理されている。`phonemizeText()` はこの副作用をそのまま残し、呼び出し側の責務とする。

### 2.3 抽出する関数 (2): `splitTextToSentences()`

`textToAudioStreaming()` の L1689-1729 を抽出。テキストを文境界で分割する。

```cpp
// piper.hpp に追加

/// テキストを文境界で分割する (textToAudioStreaming の文分割ロジックを抽出)
///
/// @param text         入力テキスト (UTF-8)
/// @param phonemeType  音素タイプ (日本語/マルチリンガル regex 切り替え用)
/// @param maxChunkSize 最大チャンクサイズ (0 = デフォルト 50)
/// @return 分割された文のリスト
std::vector<std::string> splitTextToSentences(
    const std::string &text,
    PhonemeType phonemeType,
    size_t maxChunkSize = 0);
```

**抽出対象コード (piper.cpp L1689-1729):**

1. `calculateDynamicChunkSize()` による動的チャンクサイズ計算
2. 日本語/英語の正規表現による文境界検出
3. 文分割とチャンク構築ループ

### 2.4 既存関数のリファクタ

**`textToAudio()` のリファクタ後:**

```cpp
void textToAudio(PiperConfig &config, Voice &voice, std::string text,
                 std::vector<int16_t> &audioBuffer, SynthesisResult &result,
                 const std::function<void()> &audioCallback,
                 const std::vector<ProsodyFeature> *externalProsody) {

  auto originalLanguageId = voice.synthesisConfig.languageId;

  // ---- 抽出関数呼び出し ----
  PhonemizeResult phonResult;
  phonemizeText(voice, text, phonResult, externalProsody);
  auto &phonemes = phonResult.phonemes;
  auto &allProsodyFeatures = phonResult.prosody;
  bool useProsody = !allProsodyFeatures.empty();

  // ---- ここから先は既存の合成ループ (L1319-1515) そのまま ----
  std::size_t sentenceSilenceSamples = ...;
  // ... synthesize 各文 ...
}
```

**`textToAudioStreaming()` のリファクタ後:**

```cpp
void textToAudioStreaming(...) {
  // ---- 抽出関数呼び出し ----
  auto chunks = splitTextToSentences(text,
                                     voice.phonemizeConfig.phonemeType,
                                     chunkSize);

  // ---- ここから先は既存のチャンク処理ループ (L1737-1863) ----
  for (size_t i = 0; i < chunks.size(); ++i) {
    // ... phonemize + synthesize + crossfade ...
  }
}
```

### 2.5 `textToAudioStreaming` のデッドコード問題

piper.cpp L1756-1761 の `else if (MultilingualPhonemes)` ブランチはデッドコードである。理由: `usesOpenJTalk(phonemeType)` が `MultilingualPhonemes` でも `true` を返す (piper.hpp L36) ため、L1749 の `if` で常にマッチし、`else if` に到達しない。

**対処方針:** `splitTextToSentences()` 抽出時にこのデッドコードは含めない。ただし、本チケットではデッドコード除去は**行わない** (M2-2 の Iterator 実装で `textToAudio` ベースの音素化を使うことで根本的に回避するため)。デッドコード警告コメントと将来の廃止に関する TODO コメントの両方を追加する。

```cpp
// WARNING: MultilingualPhonemes branch is dead code here because
// usesOpenJTalk() returns true for MultilingualPhonemes.
// Iterator pattern (M2-2) uses phonemizeText() instead, which
// handles multilingual phonemization correctly.
//
// TODO(Phase 4): textToAudioStreaming() should be deprecated in
// favor of the Iterator pattern (synth_start / synth_next).
// See M2-1 section 2.6 for the deprecation plan.
```

### 2.6 `textToAudioStreaming` 将来の廃止計画

理想的には `textToAudioStreaming()` を廃止し、Iterator パターン (M2-2: `synth_start` / `synth_next`) を唯一のストリーミング手段とすべきである。

**廃止すべき理由:**
1. **デッドコード問題**: `MultilingualPhonemes` ブランチが到達不能で、マルチリンガルストリーミングが正しく動作しない (2.5 参照)
2. **ロジック重複**: `textToAudioStreaming()` と Iterator が文分割+逐次合成という同じ処理を異なるコードパスで実装しており、保守コストが二重化している
3. **crossfade の局所性**: crossfade ロジック (L1836-1844) が `textToAudioStreaming` 内にハードコードされており、Iterator から再利用できない

**段階的廃止の計画:**
1. **Phase 2 (現在)**: `textToAudioStreaming` にデッドコード警告コメントと TODO を追加。Iterator は `textToAudio` ベースで実装。
2. **Phase 4 (将来)**: `textToAudioStreaming` の内部実装を Iterator 駆動に置き換え、レガシー API として互換性を維持。crossfade ロジックを Iterator の消費側に移動。
3. **将来メジャーバージョン**: `textToAudioStreaming` を `[[deprecated]]` としてマーク。十分な移行期間の後に API を削除。

**注意:** C++ の `textToAudioStreaming()` を直接呼び出している既存ユーザーがいるため、Phase 2 時点での削除は行わない。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装者 | 1 | piper.cpp / piper.hpp の関数抽出 + リファクタ |
| レビュアー | 1 | 既存テスト回帰確認 + 抽出境界の妥当性レビュー |

---

## 4. 提供範囲とテスト項目

### 4.1 テスト方針

本チケットは**純粋なリファクタリング**であるため、新規テストは最小限。既存テストの全パスが受け入れ基準。

### 4.2 既存テストの回帰確認

| テスト | 確認内容 |
|--------|---------|
| `test_streaming_simple` | `textToAudioStreaming` のリファクタ後も正常動作 |
| `test_streaming_raw_phonemes` | `phonemesToAudioStreaming` に影響なし |
| `test_piper_core` | `textToAudio` のリファクタ後も正常動作 |
| `test_text_input` | テキスト入力処理に回帰なし |
| `test_multilingual_g2p` | 多言語音素化に回帰なし |

### 4.3 追加する単体テスト (モデル不要)

| テスト | 内容 |
|--------|------|
| `TestSplitTextJapanese` | 日本語テキスト「こんにちは。今日は良い天気です。」が 2 文に分割される |
| `TestSplitTextEnglish` | 英語テキスト "Hello world. How are you?" が 2 文に分割される |
| `TestSplitTextEmpty` | 空文字列で空のベクタが返る |
| `TestSplitTextSingleSentence` | 区切り文字なしの単一文が 1 要素で返る |

### 4.4 受け入れ基準

- 既存の C++ テスト (23 個) が全て PASS
- `phonemizeText()` と `splitTextToSentences()` が `piper.hpp` で宣言されている
- `textToAudio()` が `phonemizeText()` を内部で呼んでいる
- `textToAudioStreaming()` が `splitTextToSentences()` を内部で呼んでいる
- 3 プラットフォーム (Linux / macOS / Windows) でビルドが通る

---

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| 懸念 | リスク | 対策 |
|------|--------|------|
| `phonemizeText()` の副作用 (`languageId` 変更) | 中 | 関数 docstring に明記。呼び出し側で save/restore する既存パターンを維持 |
| `splitTextToSentences()` の正規表現パフォーマンス | 低 | `static const std::regex` を関数内 static 変数として維持 (既存の L1690-1691 と同等) |
| `textToAudioStreaming` の phonemize 処理がチャンク単位 | 低 | `splitTextToSentences()` は文分割のみ。チャンク内の phonemize は既存のまま残す |
| OBJECT ライブラリ (M1-4) との統合 | 低 | 新関数は `piper.cpp` 内に追加するだけなので OBJECT ライブラリのソースリストに影響なし |
| 文分割の多言語対応不足 | 中 | `splitTextToSentences()` は日本語/英語の 2 パターンの正規表現しか持たず、`MultilingualPhonemes` では常に日本語パターンが使われる。中国語・フランス語等の文末マーカーは日本語パターンで近似的にカバーされるが、精度に限界がある。根本改善は Phase 4 候補 (多言語文分割) として検討する |

### 5.2 レビュー項目

- [ ] `phonemizeText()` が `textToAudio()` の L1067-1317 と完全に等価であること
- [ ] `splitTextToSentences()` が `textToAudioStreaming()` の L1689-1729 と完全に等価であること
- [ ] `PhonemizeResult` 構造体が move semantics で効率的に返せること
- [ ] 抽出後の `textToAudio()` が `originalLanguageId` の save/restore を維持していること
- [ ] デッドコードコメントが正確であること

---

## 6. 一から作り直すとしたら

`textToAudio()` の設計を見直すなら、以下の 3 層に分離する:

1. **Phonemizer 層**: テキスト -> 音素列 (言語検出 + G2P)。副作用なし。`languageId` は戻り値で返す。
2. **Encoder 層**: 音素列 -> phoneme_ids (ID マッピング + padding + prosody 整形)
3. **Synthesizer 層**: phoneme_ids -> 音声波形 (ONNX 推論)

現在の `textToAudio()` は 1-3 が密結合しており、特に 1 と 2 の間で `PhonemeIdConfig` の設定 (BOS/EOS フラグ、interspersePad) が散在している。理想的には Phonemizer が `PhonemeIdConfig` を知らない設計にすべきだが、OpenJTalk / Multilingual で BOS/EOS の取り扱いが異なるため、現状では完全分離が困難。

本チケットでは実用的な妥協として、1 (音素化) のみを抽出し、2-3 は `textToAudio()` 内に残す。

---

## 7. 後続タスクへの連絡事項

### M2-2 (Iterator パターン) への申し送り

- `phonemizeText()` は `voice.synthesisConfig.languageId` を変更する副作用がある。Iterator の `synth_start()` では呼び出し前に `synthesisConfig` を保存し、Iterator 終了時に復元すること。
- `splitTextToSentences()` は Iterator の文分割に直接使用可能。ただし Iterator では `textToAudio` ベースの音素化を使うため、`splitTextToSentences()` で分割した各文を個別に `phonemizeText()` + `synthesize()` する流れになる。
- `PhonemizeResult` の `phonemes` は文ごとのベクタだが、マルチリンガルの場合は全テキストが 1 つの「文」に結合される (L1286-1288)。Iterator で文単位に分割したい場合は、`splitTextToSentences()` で先に分割してから各文を個別に `phonemizeText()` に渡す設計が正しい。

### M2-4 (テスト) への申し送り

- `splitTextToSentences()` のテストは本チケットで追加する。M2-4 ではストリーミング固有のテストに集中してよい。
