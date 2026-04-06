# M1-2: `_textToPhonemeIds()` に日本語分岐追加

**マイルストーン**: M1 (PiperPlus に Rust WASM phonemizer を統合)
**依存チケット**: M1-1
**後続チケット**: M1-3, M2-2

## タスク目的とゴール

M1-1 で `this._wasmPhonemizer` がセットされるようになったが、`_textToPhonemeIds()` はまだ全言語を JS G2P (`this._g2p.encode()`) 経由で処理している。このチケットでは、日本語テキストの場合に Rust WASM の `phonemize()` を直接呼び出す分岐を追加する。

**完了条件:**
- `language === 'ja'` かつ `this._wasmPhonemizer` が non-null の場合、Rust WASM `phonemize()` が使われる
- 戻り値の `phonemeIds` が `number[]` 型 (BOS で始まり EOS で終わる)
- 戻り値の `prosodyFeatures` が `number[][]` 型 (各要素が `[a1, a2, a3]`)
- `result.free()` が呼ばれてメモリリークしない
- 他言語のパスが既存のまま動作する

## 実装する内容の詳細

### 変更ファイル: `src/wasm/openjtalk-web/src/index.js`

#### `_textToPhonemeIds()` メソッドの書き換え (L286-304)

現在の実装:

```javascript
async _textToPhonemeIds(text, language) {
  const phonemeIdMap = this._config.phoneme_id_map;
  if (!phonemeIdMap) {
    throw new Error('Model config is missing phoneme_id_map');
  }
  const result = this._g2p.encode(text, phonemeIdMap, { language });
  // ...prosody変換...
  return { phonemeIds: result.phonemeIds, prosodyFeatures };
}
```

変更後:

```javascript
async _textToPhonemeIds(text, language) {
  // 日本語: Rust WASM を直接使用
  if (language === 'ja' && this._wasmPhonemizer) {
    const result = this._wasmPhonemizer.phonemize(text, 'ja');
    const phonemeIds = Array.from(result.phonemeIds);

    let prosodyFeatures = null;
    const flat = result.prosodyFeatures;
    if (flat && flat.length > 0) {
      prosodyFeatures = [];
      for (let i = 0; i < flat.length; i += 3) {
        prosodyFeatures.push([flat[i], flat[i + 1], flat[i + 2]]);
      }
    }
    result.free();
    return { phonemeIds, prosodyFeatures };
  }

  // 他言語: 既存の JS G2P パス
  const phonemeIdMap = this._config.phoneme_id_map;
  if (!phonemeIdMap) {
    throw new Error('Model config is missing phoneme_id_map');
  }
  const result = this._g2p.encode(text, phonemeIdMap, { language });

  let prosodyFeatures = null;
  if (result.prosodyFlat && result.prosodyFlat.length > 0) {
    const flat = result.prosodyFlat;
    prosodyFeatures = [];
    for (let i = 0; i < flat.length; i += 3) {
      prosodyFeatures.push([flat[i], flat[i + 1], flat[i + 2]]);
    }
  }

  return { phonemeIds: result.phonemeIds, prosodyFeatures };
}
```

### データ型の変換詳細

| 項目 | Rust WASM の戻り値 | `_infer()` の期待 | 変換 |
|------|-------------------|------------------|------|
| `phonemeIds` | `Int32Array` | `number[]` (Array.from で BigInt64Array に変換) | `Array.from(result.phonemeIds)` |
| `prosodyFeatures` | `Int32Array` (flat: `[a1,a2,a3,a1,a2,a3,...]`) | `number[][]` (`[[a1,a2,a3], ...]`) | 3要素ずつグループ化 |
| メモリ管理 | `result.free()` 必須 | - | 変換後即座に `free()` |

### `_infer()` との整合性

`_infer()` (L316-359) は `phonemeIds` を `Array.from(phonemeIds, id => BigInt(id))` で `BigInt64Array` に変換する。Rust WASM から返る `Int32Array` の値は `Array.from()` で `number[]` に変換済みなので、既存の `_infer()` パスでそのまま処理される。

## エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装者 | 1 | `_textToPhonemeIds()` の分岐実装、型変換コード |
| レビュアー | 1 | 型互換性、メモリ管理 (`result.free()`)、既存パスへの影響確認 |

## 提供範囲

**提供するもの:**
- `_textToPhonemeIds()` の日本語分岐
- `Int32Array` → `number[]` の型変換
- prosody の flat → nested 変換
- `result.free()` によるメモリ解放

**提供しないもの:**
- ストリーミングパス (`synthesizeStreaming`) での prosody 対応 (既存と同じく省略)
- Rust WASM と JS G2P の phonemeIds 出力値の互換性検証 (M2 のテストスコープ)
- 言語検出 (M1-3)

## テスト項目

### ユニットテスト

| テスト名 | 検証内容 | モック方針 |
|---------|---------|-----------|
| `JA with wasmPhonemizer calls phonemize()` | `language === 'ja'` かつ `_wasmPhonemizer` あり → `phonemize('text', 'ja')` が呼ばれる | `_wasmPhonemizer.phonemize` をスパイ化。戻り値は `{ phonemeIds: Int32Array.from([1,8,5,2]), prosodyFeatures: Int32Array.from([-2,1,5,-2,1,5,-2,1,5,-2,1,5]), phonemeCount: 4, free: () => {} }` |
| `JA converts Int32Array to number[]` | 戻り値の `phonemeIds` が `number[]` 型 | `Array.isArray(result.phonemeIds)` で検証 |
| `JA groups prosody flat to nested` | `[a1,a2,a3,a1,a2,a3]` → `[[a1,a2,a3],[a1,a2,a3]]` | 固定値で入出力を比較 |
| `JA calls result.free()` | `phonemize()` 戻り値の `free()` が必ず呼ばれる | `free` のスパイでカウント検証 |
| `JA without wasmPhonemizer falls back to JS G2P` | `_wasmPhonemizer` が null → `_g2p.encode()` が呼ばれる | `_g2p.encode` をスパイ化 |
| `EN with wasmPhonemizer uses JS G2P` | `language === 'en'` → `_wasmPhonemizer` があっても `_g2p.encode()` が使われる | 両方のスパイを設定し、呼び出し先を検証 |
| `JA with empty prosody returns null` | `prosodyFeatures` が空の `Int32Array` → `prosodyFeatures: null` | `Int32Array.from([])` を返すモック |

### E2E テスト

1. デモページで「こんにちは、つくよみちゃんです。」を入力して音声合成
2. 生成された音声が無音やノイズでないこと
3. コンソールに型エラーが出ないこと
4. 英語テキスト "Hello" でも正常に合成されること (回帰確認)

## 懸念事項

- **`Int32Array` → `number[]` の変換コスト**: `Array.from()` は大きな配列で O(n) のコピーが発生する。通常の phonemeIds は数百要素なので問題ないが、極端に長いテキストでは注意。将来的に `_infer()` 側で `Int32Array` を直接受け取れるようにすることも検討
- **prosody フォーマットの整合性**: Rust WASM の `prosodyFeatures` は `Int32Array` の flat 配列 (`[a1,a2,a3,...]`) で、JS G2P の `prosodyFlat` と同じフォーマット。ただし Rust 側の値域 (A1/A2/A3 の範囲) が JS 側と一致するかはテストで検証が必要
- **`result.free()` の呼び忘れ**: 変換処理中に例外が発生すると `free()` が呼ばれない。`try/finally` パターンの導入を検討すべき

## レビュー項目

- [ ] `result.free()` が全パスで呼ばれるか (例外パスを含む)
- [ ] `Array.from(result.phonemeIds)` で `Int32Array` → `number[]` が正しく変換されるか
- [ ] prosody の 3要素グループ化で配列長が3の倍数でない場合の挙動
- [ ] `_infer()` に渡る `phonemeIds` の型が `BigInt` 変換と互換か
- [ ] ストリーミングパスの phonemize コールバック (L148-150) に影響がないか

## 一から作り直すとしたら

現在の設計では Rust WASM パスと JS G2P パスで戻り値の型が異なり (`Int32Array` vs `number[]`)、変換レイヤーが必要。

**理想形**: 両パスが同じインターフェースを返すように統一する:

```typescript
interface PhonemeResult {
  phonemeIds: number[];
  prosodyFeatures: number[][] | null;
}
```

Rust WASM 側で `number[]` を直接返すか、あるいは `_infer()` 側で `Int32Array` も受け取れるようにすれば、変換コストと `free()` の管理が不要になる。

ただし Rust WASM (`wasm-bindgen`) は `Int32Array` を返す設計が自然であり、JS 側での `Array.from()` 変換は十分軽量なため、現時点ではこのアプローチで妥当。

## 後続タスクへの連絡事項

- **M1-3 への連絡**: `_textToPhonemeIds()` は `language` 引数を受け取る。言語検出 (M1-3) はこのメソッドの呼び出し元 (`synthesize()`, `synthesizeStreaming()`) で行われる。phonemeIds のフォーマットは JA (Rust WASM) と他言語 (JS G2P) で同じ `number[]` に統一される
- **M2-2 への連絡**: テストでは `_wasmPhonemizer.phonemize()` のモック戻り値として `{ phonemeIds: Int32Array, prosodyFeatures: Int32Array, phonemeCount: number, free: Function }` の形式を使用すること。`free()` の呼び出し検証を忘れずに
- **ストリーミングパスの注意**: `synthesizeStreaming()` 内の phonemize コールバック (L148-150) は `_textToPhonemeIds()` を呼ぶため、日本語ストリーミングも自動的に Rust WASM パスを経由する。ただし prosody は使用されない (L154)
