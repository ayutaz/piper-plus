# M2-2: `_textToPhonemeIds` 分岐テスト

**マイルストーン**: M2
**依存チケット**: M1-2, M1-3, M1-4, M2-1
**後続チケット**: M2-3, M3-1

## タスク目的とゴール

M1-2 (`_textToPhonemeIds` の日本語分岐)、M1-3 (言語検出の統合)、M1-4 (dispose リソース解放) の3つの変更を組み合わせたテストを実装する。WASM phonemizer のモックを使い、日本語テキストが Rust WASM パスを通ること、他言語が既存の JS G2P パスを通ること、リソース解放が正しく行われることを検証する。

## 実装する内容の詳細

M2-1 で作成した `src/wasm/openjtalk-web/test/js/test-piper-plus-wasm-g2p.js` にテストケースを追加する。

### テストケース

1. **JA + WASM あり**: 日本語テキストで `_wasmPhonemizer.phonemize()` が呼ばれ、戻り値が正しい形式に変換されること
2. **JA + WASM なし (フォールバック)**: `_wasmPhonemizer` が null の場合、JS G2P `encode()` にフォールバックすること
3. **非 JA 言語 + WASM あり**: 英語テキストでは `_wasmPhonemizer.phonemize()` が呼ばれず、JS G2P `encode()` が使われること
4. **phonemeIds 形式変換**: `Int32Array` → `number[]` (`Array.from`) の変換が正しいこと
5. **prosodyFeatures 変換**: `Int32Array` (flat) → `number[][]` (3要素グループ) の変換が正しいこと
6. **`result.free()` 呼び出し**: phonemize 後に `result.free()` が確実に呼ばれること (メモリリーク防止)
7. **言語検出 (JA)**: `_wasmPhonemizer` がある場合、`detectLanguage('こんにちは')` が `'ja'` を返すこと
8. **言語検出 (非 JA)**: `_wasmPhonemizer` がある場合でも、`detectLanguage('Hello')` が `'en'` を返すこと
9. **言語検出 (WASM なし)**: `_wasmPhonemizer` が null の場合、JS G2P の `detectLanguage()` が使われること
10. **dispose 後の合成エラー**: `dispose()` 後に `synthesize()` を呼ぶとエラーになること

### モック戦略

リアルなデータを返す最小限の `WasmPhonemizer` モックを作成:

```javascript
function createRealisticWasmPhonemizerMock() {
  let freeCalled = false;
  return {
    phonemize(text, lang) {
      // 「こんにちは」の現実的な phonemeIds
      // BOS=1, k=42, o=43, N_n=44, n=45, i=46, ch=47, i=46, w=48, a=49, EOS=2
      const phonemeIds = new Int32Array([1, 42, 43, 44, 45, 46, 47, 46, 48, 49, 2]);
      const prosodyFeatures = new Int32Array([
        -2, 1, 5,  -2, 1, 5,  -2, 1, 5,  -2, 1, 5,  -2, 1, 5,
        -2, 1, 5,  -2, 1, 5,  -2, 1, 5,  -2, 1, 5,  -2, 1, 5,  -2, 1, 5,
      ]);
      return {
        phonemeIds,
        prosodyFeatures,
        phonemeCount: 11,
        free() { freeCalled = true; },
      };
    },
    detectLanguage(text) {
      if (/[\u3040-\u309F\u30A0-\u30FF]/.test(text)) return 'ja';
      if (/[\u4E00-\u9FFF]/.test(text)) return 'zh';
      return 'en';
    },
    free() {},
    get _freeCalled() { return freeCalled; },
    _resetFreeCalled() { freeCalled = false; },
  };
}
```

## エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| テストライター | 1 | テストケース実装、モックデータ設計、既存テストとの整合性確認 |

## 提供範囲

- `src/wasm/openjtalk-web/test/js/test-piper-plus-wasm-g2p.js` への追記 (M2-1 と同一ファイル)
- M1-2 (`_textToPhonemeIds` 分岐)、M1-3 (言語検出)、M1-4 (dispose) のテスト

## テスト項目

### ユニットテスト

| # | テストケース | 検証内容 |
|---|------------|----------|
| 1 | JA + WASM パス | `phonemize()` の呼び出し + 戻り値の形式 |
| 2 | JA フォールバック | JS G2P `encode()` への委譲 |
| 3 | 非 JA 言語分離 | WASM が呼ばれず JS G2P が使われる |
| 4 | phonemeIds 変換 | `Int32Array` → `number[]` |
| 5 | prosodyFeatures 変換 | flat `Int32Array` → `number[][]` (3要素グループ) |
| 6 | `result.free()` 呼び出し | メモリリーク防止の確認 |
| 7 | 言語検出 (JA) | ひらがな/カタカナ → `'ja'` |
| 8 | 言語検出 (非 JA) | 英語/中国語の正しい検出 |
| 9 | 言語検出フォールバック | WASM なし → JS G2P |
| 10 | dispose 後エラー | 解放後の合成が失敗すること |

### E2E テスト

M2-2 では E2E テストは対象外。phonemeIds の妥当性は実際の ONNX 推論なしでは完全に検証できないため、以下の代替手法を用いる:

- **形式検証**: BOS (1) で始まり EOS (2) で終わること、長さが妥当であること
- **prosody 形式検証**: 3の倍数であること、phonemeIds と長さが一致すること
- **スナップショットテスト**: 特定の入力テキストに対する期待出力をハードコードし、Rust WASM の振る舞い変更を検知する (ただしモック環境ではモックの出力を検証するのみ)

## 懸念事項

- **phonemeIds の妥当性検証**: 実際の ONNX 推論を行わずに phonemeIds が有効であることを検証するのは困難。モック環境ではデータ形式 (型、BOS/EOS、長さ) の検証に限定される。本当の互換性検証は M3-1 のブラウザ E2E で実施する
- **スナップショットテストの維持コスト**: Rust WASM の内部変更 (辞書更新、エンコーディング変更) でスナップショットが壊れる可能性がある。モック環境では問題にならないが、将来的に実 WASM を使うテストに移行した場合に注意が必要
- **JS G2P フォールバックの動作確認**: JA + WASM なしのフォールバック時、JS G2P が `'ja'` を受け取ると `openjtalkModule is required` エラーが発生する。フォールバック時は `'ja'` を除外してから JS G2P に渡す必要がある

## レビュー項目

- [ ] 全10テストケースが実装されていること
- [ ] モック (`createRealisticWasmPhonemizerMock`) が M1 の実装 API に合致していること
- [ ] `result.free()` の呼び出し確認が含まれていること
- [ ] phonemeIds が `number[]` (not `Int32Array`) に変換されていることの検証
- [ ] prosodyFeatures の3要素グループ化の検証
- [ ] 既存テスト (`npm test`) が壊れていないこと

## 一から作り直すとしたら

phonemeIds の妥当性検証方法を再検討すべきである。現在のモック戦略ではモック自体の出力を検証しているに過ぎず、実際の Rust WASM と JS G2P 間の互換性は保証できない。

改善案:
- **スナップショットテスト**: 実 WASM バイナリを使って特定テキストの phonemeIds をキャプチャし、ゴールデンファイルとして保存。CI で回帰検知する。ただし WASM バイナリの CI ビルドが前提
- **互換性テスト**: 同一テキストに対して Rust WASM と JS G2P の出力を比較するテスト (JS G2P が JA 対応している場合)。現状では JS G2P の JA は未統合のため不可
- **推論結果テスト**: phonemeIds を実際の ONNX モデルに通し、音声出力のサンプルレートや長さが妥当であることを検証。M3-1 のブラウザテストでカバーする

## 後続タスクへの連絡事項

- M2-3 で CI ワークフローにテストファイルを追加する際、このファイルが M2-1 と同一であることに注意 (追加作業は不要)
- M3-1 のブラウザ E2E テストで、モック環境では検証できない phonemeIds の実際の妥当性を確認すること
- `createRealisticWasmPhonemizerMock()` を将来的にヘルパーファイルに切り出す場合、M2-1 のモックと統合して一元管理すること
