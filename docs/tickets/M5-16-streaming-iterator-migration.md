# M5-16: textToAudioStreaming Iterator 駆動移行

> **Phase:** 5 -- 低優先度改善
> **利用者視点の優先度:** 中 -- ストリーミング品質と保守性の改善
> **見積り:** 大
> **依存:** Phase 4 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

`piper.cpp` の `textToAudioStreaming()` 内部を Iterator (`synth_start` / `synth_next`) 駆動に置換し、`MultilingualPhonemes` デッドコード問題を根本解決する。

**現状の問題:** `textToAudioStreaming()` は `usesOpenJTalk()` が true を返す場合にカスタムの文分割・音素化ロジックを実行するが、`MultilingualPhonemes` タイプでも `usesOpenJTalk()` が true を返すため、マルチリンガルモデルでは本来の多言語音素化パスがバイパスされる。M2-2 の Iterator は `textToAudio` ベースで設計されており、この問題を回避しているが、`textToAudioStreaming()` 自体はデッドコードとして残存。

**ゴール:**
1. `textToAudioStreaming()` の内部を Iterator 駆動に書き換え
2. デッドコードとなっている `MultilingualPhonemes` 分岐を除去
3. C API の `piper_plus_synthesize_streaming` と内部 `textToAudioStreaming` を統一

---

## 2. 実装する内容の詳細

### 2.1 内部リファクタリング (`src/cpp/piper.cpp`)

**Step 1: 文分割の共通化**
- M2-1 で抽出済みの `splitTextToSentences()` を `textToAudioStreaming` でも利用
- 既存の行分割 + eSpeak ベースの文分割ロジックを削除

**Step 2: Iterator 駆動ループ**
```cpp
void textToAudioStreaming(PiperConfig &config, Voice &voice,
                          const std::string &text,
                          SynthesisConfig &synthConfig,
                          AudioCallback callback) {
    auto sentences = splitTextToSentences(config, voice, text);
    for (auto &sentence : sentences) {
        std::vector<int16_t> audioBuffer;
        textToAudio(config, voice, sentence, audioBuffer, synthConfig);
        callback(audioBuffer);
    }
}
```

**Step 3: デッドコード除去**
- `textToAudioStreaming` 内の `MultilingualPhonemes` 分岐を削除
- `usesOpenJTalk()` による条件分岐の整理

### 2.2 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper.cpp` | `textToAudioStreaming()` のリファクタリング |
| `src/cpp/piper.hpp` | シグネチャ変更があれば更新 |
| `src/cpp/piper_plus_c_api.cpp` | 内部呼び出しの統一 |
| `src/cpp/tests/test_c_api_integration.cpp` | 回帰テスト追加 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | リファクタリング + 回帰テスト |

合計 1 名。ただし `piper.cpp` の内部構造に精通している必要あり。

---

## 4. 提供範囲とテスト項目

### スコープ

- `textToAudioStreaming()` の Iterator 駆動化
- `MultilingualPhonemes` デッドコード除去
- C API ストリーミングの内部実装統一

### E2E テスト (モデル必要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| JA ストリーミング | 日本語テキストでストリーミング合成 | コールバック複数回 + 音声正常 |
| EN ストリーミング | 英語テキストでストリーミング合成 | コールバック複数回 + 音声正常 |
| 多文ストリーミング | 複数文テキスト | 文数と同数のコールバック |
| ワンショットとの一致 | 同一テキストでワンショット vs ストリーミング | サンプル数が近似 (±5%) |
| CLI ストリーミング | `piper` コマンドのストリーミングモード | 回帰なし |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| CLI (`piper`) の回帰 | 高 | `piper` コマンドも `textToAudioStreaming` を使用。CLI の動作確認を必須とする |
| crossfade の喪失 | 中 | 既存の `textToAudioStreaming` は eSpeak モードで crossfade を行うが、Iterator 駆動では `sentence_silence_sec` で代替 |
| eSpeak 専用パスの影響 | 中 | eSpeak (非マルチリンガル) モデルでの動作確認も必要 |

### レビュー時の確認項目

1. `textToAudioStreaming` の全呼び出し元を特定し、回帰がないこと
2. デッドコード除去が意図しないコードパスに影響していないこと
3. CLI の `--output-raw` (ストリーミング出力) が正常動作すること

---

## 6. 一から作り直すとしたら

`textToAudio` と `textToAudioStreaming` を最初から統一設計すべきだった。内部的に `textToAudio` が文単位の合成を行い、`textToAudioStreaming` はそのイテレータラッパーという設計が自然。現状は歴史的経緯で二重実装となっている。

---

## 7. 後続タスクへの連絡事項

- **M5-21 (音声回帰テスト):** ストリーミング出力の品質がワンショットと大きく乖離しないことを回帰テストで検証すべき。
- **crossfade 対応:** 将来の改善として、文間の crossfade を Iterator レベルで実装することを検討 (M2-2 懸念事項で既に言及)。
