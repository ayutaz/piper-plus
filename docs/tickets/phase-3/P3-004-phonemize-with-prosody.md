# P3-004: phonemizeWithProsody() 追加

> Phase: 3 (JS/WASM)
> マイルストーン: v0.1.0
> 対応要求: FR-302
> 依存チケット: P3-001, P3-002
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

現在の JS/WASM 実装では、A1/A2/A3 prosody 情報は `PiperPlus._extractProsodyFromLabels()` でのみ抽出され、G2P レイヤーの API としては公開されていない。`japanese_phoneme_extract.js` は A1/A2/A3 の正規表現パース (`RE_A1`, `RE_A2`, `RE_A3`) を既に持っているが、韻律マーカー挿入の判定にのみ使用し、値自体は返していない。この値を `ProsodyInfo` として G2P API から返すことで、Python (`phonemize_with_prosody()`) / Rust (`phonemize_with_prosody()`) と同等の prosody 抽出 API を提供する。

### ゴール

- `G2P.phonemizeWithProsody(text, {language: 'ja'})` が `PhonemizeResult` を返し、`prosody` フィールドに per-token の `ProsodyInfo` (a1/a2/a3) を含む
- EN の `phonemizeWithProsody()` が `ProsodyInfo(a1=0, a2=stress_level, a3=word_phoneme_count)` を返す
- ZH/ES/FR/PT では prosody が全て null (prosody 情報なし)
- prosody が不要な位置 (BOS/EOS/ポーズ/韻律マーカー) は null
- Python 実装 (`phonemize_with_prosody()`) との出力一致テストが pass する

---

## 2. 実装詳細

### 作成/変更するファイル

| 操作 | パス | 説明 |
|------|------|------|
| 変更 | `src/wasm/g2p/src/ja/index.js` | `extractPhonemesFromLabels()` を拡張し prosody を返す |
| 新規 | `src/wasm/g2p/src/ja/prosody-extract.js` | A1/A2/A3 抽出ロジック (labels パーサーから分離) |
| 変更 | `src/wasm/g2p/src/en/index.js` | ストレスレベル + 単語音素数の ProsodyInfo 生成 |
| 変更 | `src/wasm/g2p/src/index.js` | `phonemizeWithProsody()` のルーティング |
| 参照 | `src/wasm/openjtalk-web/src/japanese_phoneme_extract.js` | 既存の A1/A2/A3 パースロジック |
| 参照 | `src/python/piper_train/phonemize/japanese.py` | Python JA prosody 実装 (一致検証用) |
| 参照 | `src/python/piper_train/phonemize/english.py` | Python EN prosody 実装 (一致検証用) |

### 実装手順

1. **JA prosody 抽出の拡張**: `extractPhonemesFromLabels()` の内部ループで既にパースしている A1/A2/A3 値を、各トークンに紐づける:

   ```javascript
   // 現在: 韻律マーカー挿入の判定にのみ使用
   const a1 = parseInt(mA1[1], 10);
   const a2 = parseInt(mA2[1], 10);
   const a3 = parseInt(mA3[1], 10);

   // 変更後: ProsodyInfo としても返す
   const prosodyInfo = { a1, a2, a3 };
   tokenProsodyPairs.push({ token: phoneme, prosody: prosodyInfo });
   ```

   注意点:
   - BOS (`^`) / EOS (`$`) には prosody: null
   - ポーズ (`_`) には prosody: null
   - 韻律マーカー (`]`, `#`, `[`) には prosody: null
   - `a1` は OpenJTalk のオリジナル値 (0 以上) をそのまま返す (Python の `int(mA1[1])` と同等)

2. **EN prosody 生成**: `SimpleEnglishPhonemizer` の音素化結果にストレス情報を付与:
   - ARPAbet のストレスマーカー (0/1/2) を `a2` に格納
   - 単語の音素数を `a3` に格納
   - `a1` は 0 固定 (EN では未使用)

3. **`phonemizeWithProsody()` のルーティング**: `G2P.phonemizeWithProsody()` が言語ごとに:
   - JA: `extractPhonemesWithProsody(labels)` を呼ぶ
   - EN: `phonemizeEnglishWithProsody(text)` を呼ぶ
   - ZH/ES/FR/PT: `phonemize()` と同一の結果を返し、prosody は全て null

4. **`encode()` の prosody 対応**: `encode()` が `PhonemizeResult.prosody` を受け取り、BOS/PAD/EOS 位置に null を挿入して `EncodeResult.prosodyFlat` (`[a1,a2,a3, a1,a2,a3, ...]`) を生成。

### API / インターフェース

```javascript
// ProsodyInfo (per-token)
// {
//   a1: number,  // JA: アクセント核からの相対位置, EN: 0
//   a2: number,  // JA: モーラ位置 (1-based), EN: ストレスレベル (0/1/2)
//   a3: number,  // JA: アクセント句モーラ数, EN: 単語音素数
// }

// PhonemizeResult (phonemizeWithProsody の戻り値)
// {
//   tokens: string[],                   // IPA トークン配列
//   prosody: (ProsodyInfo | null)[],    // per-token prosody
//   language: Language,
// }

// EncodeResult (encode の戻り値、prosody 対応)
// {
//   phonemeIds: number[],
//   prosodyFlat: number[] | null,       // [a1,a2,a3, ...] BOS/PAD/EOS 位置は 0,0,0
// }
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| フロントエンドエンジニア | 1 | JA/EN prosody 抽出実装、encode 対応 |
| テストエンジニア | 1 | Python 実装との一致テスト、prosody 値の網羅テスト |

---

## 4. テスト計画

### 提供範囲

- JA の A1/A2/A3 prosody 抽出が Python 実装と一致
- EN のストレスレベル + 単語音素数が Python 実装と一致
- ZH/ES/FR/PT で prosody が全て null
- BOS/EOS/ポーズ/韻律マーカー位置の prosody が null
- `encode()` の prosodyFlat 生成

### Unit テスト

| テスト | 内容 | ケース数 |
|--------|------|---------|
| JA prosody | 「こんにちは」の per-token a1/a2/a3 値が Python と一致 | 3 |
| JA アクセント句境界 | 「東京都に行きます」など複数アクセント句のテスト | 2 |
| JA 疑問文 | 「何ですか？」の疑問マーカー位置 prosody が null | 1 |
| JA BOS/EOS/ポーズ | `^`, `$`, `_` の prosody が null | 1 |
| JA 韻律マーカー | `]`, `#`, `[` の prosody が null | 1 |
| EN stress | "Hello" の primary stress (2) が a2 に入る | 2 |
| EN 機能語 | "the", "a" のストレス除去 (a2=0) | 2 |
| EN 単語音素数 | 各単語の a3 が正しい音素数を返す | 2 |
| ZH/ES/FR/PT null | 各言語で prosody が全て null | 4 |
| encode prosodyFlat | BOS/PAD/EOS 位置が [0,0,0] | 2 |

### E2E テスト

| テスト | 内容 |
|--------|------|
| JA フルパイプライン | テキスト → `phonemizeWithProsody()` → `encode()` → prosodyFlat が推論に使える形式 |
| Python 一致 | JA/EN の同一テキストで Python `phonemize_with_prosody()` と prosody 値を比較 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

1. **A1 値の範囲**: Python 実装では `a1 = int(mA1[1])` で -5 ~ 10+ の範囲がある。現在の `PiperPlus._extractProsodyFromLabels()` では `Math.max(0, Math.min(10, parseInt(mA1[1]) + 5))` とクランプ + オフセットしている。G2P パッケージとしてはオリジナルの値 (Python と同じ) を返し、クランプは encode 層またはアプリケーション層の責務とすべき。
2. **prosody と tokens の長さ不一致**: `extractPhonemesFromLabels()` の返す tokens 数と OpenJTalk labels 行数は 1:1 対応しない (sil/pau が ^ や _ に変換され、韻律マーカーが挿入される)。prosody 配列の長さを tokens 配列と正確に一致させる必要がある。
3. **EN prosody の精度**: `SimpleEnglishPhonemizer` は辞書ベースの簡易実装であり、Python の `g2p-en` とストレスパターンが異なる可能性がある。テストでは一致しないケースを許容する必要があるかもしれない。

### レビュー項目

- [ ] JA の A1/A2/A3 値が Python `phonemize_with_prosody()` と一致する (最低 3 テストケース)
- [ ] `len(tokens) == len(prosody)` が全言語で保証されている
- [ ] BOS/EOS/ポーズ/韻律マーカーの prosody が null である
- [ ] `encode()` の `prosodyFlat` 長が `phonemeIds` 長 * 3 である
- [ ] A1 のクランプ/オフセットが G2P 層で行われていない (生値を返す)

---

## 6. 一から作り直すとしたら

現在の実装では prosody 情報が 3 箇所に分散している:
1. `japanese_phoneme_extract.js`: A1/A2/A3 パース (韻律マーカー判定用)
2. `PiperPlus._extractProsodyFromLabels()`: A1/A2/A3 抽出 (推論用、別の正規表現で再パース)
3. `PiperPlus._textToPhonemeIds()`: prosody 有無の判定ロジック

一から作り直すなら:
- **prosody 抽出は phoneme 抽出と同時に行う**。OpenJTalk labels のパースは 1 回だけ行い、tokens と prosody を同時に返す。現在の 2 回パース (extractPhonemesFromLabels + _extractProsodyFromLabels) は無駄。
- **prosody の意味を型で表現する**。`{a1, a2, a3}` の意味は言語によって異なる (JA: アクセント位置、EN: ストレスレベル)。`JaProsodyInfo extends ProsodyInfo`, `EnProsodyInfo extends ProsodyInfo` のような型分けを検討する。

---

## 7. 後続タスクへの連絡事項

- **P3-005 (互換レイヤー)**: `piper-plus` の `PiperPlus._extractProsodyFromLabels()` は G2P パッケージの `phonemizeWithProsody()` に置き換え可能。ただし現在の実装はクランプ (`Math.max(0, Math.min(10, ...))`) を行っているため、互換レイヤーでクランプを適用する必要がある。
- **P3-006 (TypeScript 型定義)**: `ProsodyInfo`, `PhonemizeResult`, `EncodeResult` の型定義は本チケットの API に基づく。
- **P3-008 (安定版リリース)**: prosody API のユーザーフィードバックに基づき、A1 のクランプ/オフセットを G2P 層で行うべきか、encode 層で行うべきかを最終決定する。
