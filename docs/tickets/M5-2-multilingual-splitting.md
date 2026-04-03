# M5-2: 多言語文分割の改善

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 高 -- ZH/FR/ES/PT ユーザーの合成品質に直結
> **見積り:** 中
> **依存:** Phase 4 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

`splitTextToSentences()` が JA/EN の正規表現のみで文分割を行っており、ZH/FR/ES/PT のテキストが近似処理されている問題を改善する。

**現状:** `piper.cpp` の `splitTextToSentences()` は日本語の句読点 (`。！？`) と英語のピリオド・疑問符・感嘆符 (`.!?`) をベースに文分割を行っている。中国語の句点 (`。`)、フランス語のギュメ、スペイン語の逆疑問符 (`?`) などは正規表現に含まれておらず、長いテキストが 1 文として処理される場合がある。

**ゴール:** `PhonemeType::MultilingualPhonemes` 使用時に、6 言語全ての句読点を正しく認識する統合正規表現パターンを適用し、各言語のテキストが正しく文分割されること。

---

## 2. 実装する内容の詳細

### 2.1 統合正規表現パターン

`PhonemeType::MultilingualPhonemes` の場合に使用する統合パターン:

```cpp
// 多言語対応の文末・区切りパターン
// - 。！？ (JA/ZH fullwidth)
// - .!? (EN/ES/FR/PT ASCII)
// - ; (semicolon)
// - ... / …  (ellipsis)
static const std::regex multilingualSentenceEnd(
    u8"([。！？.!?]+|[…]+|[\\.]{3,})"
);
```

### 2.2 分岐ロジック

```cpp
void splitTextToSentences(const PiperConfig &config,
                          const Voice &voice,
                          const std::string &text,
                          std::vector<std::string> &sentences) {
    const auto &phonemeType = voice.synthesisConfig.phonemeType;

    if (phonemeType == PhonemeType::MultilingualPhonemes) {
        // 多言語統合パターンで分割
        splitWithPattern(text, multilingualSentenceEnd, sentences);
    } else {
        // 既存の JA/EN パターンを維持
        // (OpenJTalkPhonemes / その他)
        splitWithExistingLogic(config, voice, text, sentences);
    }
}
```

### 2.3 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper.cpp` | `splitTextToSentences` に `MultilingualPhonemes` 分岐と統合正規表現を追加 |
| `src/cpp/tests/test_c_api.cpp` | ZH/FR テキスト分割テストケース追加 |
| `src/cpp/tests/test_c_api_integration.cpp` | 多言語テキスト分割の E2E テスト追加 |

**変更不要:** `piper_plus.h` (C API の公開インターフェースに変更なし)、`piper_plus_c_api.cpp`。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | 正規表現パターン追加 + テスト |

合計 1 名。既存関数の分岐追加で新規アーキテクチャは不要。

---

## 4. 提供範囲とテスト項目

### スコープ

- `splitTextToSentences` に多言語統合正規表現パターンを追加
- `PhonemeType::MultilingualPhonemes` の場合のみ新パターンを使用
- 既存の JA/EN (OpenJTalkPhonemes) パターンは維持

### ユニットテスト (モデル不要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestSplitChineseSentences` | `"你好。今天天气很好。谢谢。"` を分割 | 3 文に分割される |
| `TestSplitFrenchSentences` | `"Bonjour. Comment allez-vous? Merci!"` を分割 | 3 文に分割される |
| `TestSplitSpanishSentences` | `"Hola. ?Como estas? Bien!"` を分割 | 3 文に分割される |
| `TestSplitMixedLanguage` | JA/EN/ZH 混合テキスト | 句読点ごとに正しく分割 |
| `TestSplitEllipsis` | `"Wait... Really?"` を分割 | 2 文に分割される |
| `TestExistingJaEnUnchanged` | 既存 JA/EN テストケース | 既存の分割結果と同一 (非回帰) |

### E2E テスト (モデル必要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestChineseMultiSentence` | 中国語 3 文テキストを合成 | 合成成功 + 音声長が 1 文時より長い |
| `TestFrenchMultiSentence` | フランス語 3 文テキストを合成 | 合成成功 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| 正規表現のパフォーマンス | 低 | 統合パターンは既存の JA/EN パターンと同程度の複雑さ。`static const` で 1 回だけコンパイル |
| 中国語の読点 (、) での過剰分割 | 中 | 読点は文区切りではなく節区切り。統合パターンには文末句読点 (。！？.!?) のみを含め、読点は含めない |
| 既存 OpenJTalkPhonemes の動作変更 | 低 | `PhonemeType` で明示的に分岐するため、既存の JA/EN 処理に影響なし |
| Unicode 正規化 | 低 | 全角・半角の混在 (例: `！` vs `!`) は両方をパターンに含めることで対応 |

### レビュー時の確認項目

1. `PhonemeType::MultilingualPhonemes` の分岐条件が正しいこと
2. 統合正規表現が UTF-8 リテラル (`u8""`) で定義されていること
3. 既存の JA/EN テストが全て PASS すること (非回帰)
4. 空文字列・空白のみ・句読点なしテキストの edge case が処理されること
5. `static const` で正規表現が 1 回だけコンパイルされること

---

## 6. 一から作り直すとしたら

**言語ごとの文分割ルールを分離する設計。** 現在の `splitTextToSentences` は単一の正規表現で全言語を処理しようとしているが、理想的には言語ごとの `SentenceSplitter` インターフェースを定義し、`MultilingualPhonemizer` と同様のレジストリパターンで言語固有の分割ロジックを提供する方が拡張性が高い。ただし、文分割は句読点ベースで十分実用的であり、言語固有のロジック (例: タイ語の空白なし文分割) が必要になるまでは統合正規表現で十分。

---

## 7. 後続タスクへの連絡事項

- **M5-3 (Iterator crossfade):** 文分割の改善により、ストリーミング時のチャンク数が増える可能性がある。crossfade の処理回数が増えるが、パフォーマンスへの影響は軽微。
- **将来の言語追加:** 新言語 (例: タイ語、アラビア語) を追加する場合、統合正規表現にその言語の句読点を追加すること。タイ語のように句読点に依存しない言語は別途 `SentenceSplitter` の導入を検討。
- **M2-6 で記載済み:** マイルストーン M2-6 の後続タスクに「多言語文分割の精度向上」が Phase 4 候補として記載されていた。本チケットがその対応。
