# M5-8: phonemizeText 副作用除去

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 中 -- API 利用者にとって副作用は予測困難なバグ源
> **見積り:** 中
> **依存:** Phase 1 完了 (M1-6), M4-3 (G2P API)
> **ブロック:** なし
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

`phonemizeText()` は `Voice &voice` を非 const 参照で受け取り、`voice.synthesisConfig.languageId` を副作用として変更する (言語自動検出時)。この副作用を除去し、検出結果を `PhonemizeResult` に含めて返すようにする。

**現状:** `piper.hpp` のコメントに `/// @note May modify voice.synthesisConfig.languageId (auto-detect side effect).` と明記されている。C API 実装 (`piper_plus_phonemize`, `piper_plus_synthesize` 等) では呼び出し前後で `languageId` を save/restore している。

**ゴール:** `phonemizeText` が `const Voice &` を受け取り、副作用なしで動作する。検出された言語 ID は `PhonemizeResult.detectedLanguageId` で返す。

---

## 2. 実装する内容の詳細

### 2.1 piper.hpp の変更

```cpp
struct PhonemizeResult {
    std::vector<std::vector<Phoneme>> phonemes;
    std::vector<std::vector<ProsodyFeature>> prosody;
    std::optional<int64_t> detectedLanguageId;  // NEW: auto-detect result
};

void phonemizeText(const Voice &voice, const std::string &text,
                   PhonemizeResult &result,
                   const std::vector<ProsodyFeature> *externalProsody = nullptr);
```

### 2.2 piper.cpp の変更

`phonemizeText()` 内部で `voice.synthesisConfig.languageId` を直接変更する代わりに、ローカル変数で言語 ID を管理し、結果を `result.detectedLanguageId` に格納:

```cpp
void phonemizeText(const Voice &voice, const std::string &text,
                   PhonemizeResult &result, ...) {
    // 言語自動検出のロジック
    std::optional<int64_t> langId = voice.synthesisConfig.languageId;
    // ... 検出処理 (voice を変更しない) ...
    result.detectedLanguageId = langId;
}
```

### 2.3 呼び出し元の変更

`textToAudio`, `textToAudioFloat` 等の呼び出し元で、`PhonemizeResult.detectedLanguageId` を使って後続の処理 (phoneme_ids 変換の言語選択) を行う。C API 側の save/restore コードは不要になるため削除。

### 2.4 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper.hpp` | `PhonemizeResult` に `detectedLanguageId` 追加、`phonemizeText` を `const Voice &` に変更 |
| `src/cpp/piper.cpp` | `phonemizeText` 内部の副作用除去、`textToAudio` / `textToAudioFloat` の呼び出し元修正 |
| `src/cpp/piper_plus_c_api.cpp` | `piper_plus_phonemize` / `piper_plus_synthesize` の save/restore コード削除 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | リファクタリング + 既存テスト修正 |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### ユニットテスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestPhonemizeNoSideEffect` | `phonemizeText` 前後で `voice.synthesisConfig` が変化しないこと | languageId 不変 |
| `TestPhonemizeDetectedLang` | 自動検出テキストで `result.detectedLanguageId` が設定されること | 期待言語 ID |
| `TestPhonemizeExplicitLang` | 明示的言語指定時 | `detectedLanguageId` が指定値と一致 |

### 回帰テスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestSynthesizeAfterPhonesize` | `phonemize` -> `synthesize` の連続呼び出し | 合成結果が言語副作用で変化しないこと |
| `TestExistingTests` | 既存の全テストがパス | 回帰なし |

---

## 5. 懸念事項とレビュー項目

| リスク | 影響度 | 対策 |
|--------|--------|------|
| `const Voice &` への変更が `textToAudio` 内部の他の副作用と衝突 | 中 | `textToAudio` は `phonemizeText` の結果を使って言語 ID を設定するため、`Voice` を non-const で渡し続ける。`phonemizeText` のみ `const` 化 |
| CLI (`main.cpp`) が `phonemizeText` の副作用に依存している可能性 | 低 | CLI は `textToAudio` 経由で使用しており、直接 `phonemizeText` を呼んでいない |

### レビュー時の確認項目

1. `phonemizeText` の全呼び出し元が `detectedLanguageId` を正しく使用すること
2. C API の save/restore パターンが完全に除去されていること
3. マルチリンガルモデルでの言語自動検出が引き続き動作すること

---

## 6. 一から作り直すとしたら

`Voice` を設定 (`synthesisConfig`) とモデル状態 (`session`, `phonemizeConfig`) に分離し、設定は値渡しにする。これにより副作用の発生源自体を構造的に排除できる。ただし `piper.cpp` 全体のリファクタリングが必要で Phase 5 の範囲を超える。

---

## 7. 後続タスクへの連絡事項

- `textToAudio` / `textToAudioFloat` は引き続き `Voice &` (non-const) を受け取る。これらの副作用除去は将来のリファクタリングとして別チケット化を検討。
- この変更により C API の `piper_plus_phonemize` 実装が大幅に簡素化される。
