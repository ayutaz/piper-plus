# WASM-G2P-FR: フランス語 G2P JS ルールベース移植

> **Phase:** 2 | **ステータス:** 未着手 | **並列:** Phase 1, 3 と同時実行可能
> **マイルストーン:** [wasm-g2p-implementation-milestones.md](../wasm-g2p-implementation-milestones.md#phase-2-フランス語-fr--js-ルールベース移植)
> **ブランチ:** `fix/wasm-g2p-fr`

---

## 1. タスク目的とゴール

**目的:** `@piper-plus/g2p` のフランス語 G2P を、文字パススルー (68行) からルールベース IPA 変換 (~680行) に置き換える。

**ゴール:**
- `"bonjour"` → `b ɔ̃ ʒ u ʁ` (鼻母音 PUA E058 + uvular r)
- `"français"` → ɑ̃ (PUA E057) 含む IPA 列
- 鼻母音 3 種 (ɛ̃/ɑ̃/ɔ̃)、黙字、二重字、y_vowel が正しく処理される
- golden test 3 件 + 個別テスト 40+ 件が全通過

**非ゴール:**
- liaison 処理 (Python 固有、Rust にもない)
- elision merging (l'ami → 2トークン分離のまま)

---

## 2. 実装する内容の詳細

### 2-1. テキスト正規化・単語分割 (~60行)

| 移植元関数 (Rust) | JS関数名 | 概要 |
|------------------|---------|------|
| `collapse_nfd(cps)` | `collapseNfd(cps)` | NFD結合文字 → NFC (acute, grave, circumflex, diaeresis, cedilla, tilde) |
| `to_lower_fr(c)` | `toLowerFr(c)` | ç, é, è, ê, ë 等保持の小文字化 |
| `normalize(text)` | `normalize(text)` | NFC + lowercase + 空白圧縮 |
| `normalize_apostrophes(cps)` | `normalizeApostrophes(cps)` | curly quotes → space |
| `split_words(cps)` | `splitWords(cps)` | Word/Punct トークン分割 |

### 2-2. convert_word() コア (~400行) — 最大・最複雑の関数

Rust `convert_word()` (L396-1076, 680行) の線形スキャナを JS に移植。ルール優先順序が重要。

#### Phase A: マルチ文字シーケンス (最長一致)

| パターン | 出力 | 条件 |
|---------|------|------|
| `-er` (語末) | /e/ | `countVowels >= 2` かつ `!isErAsEhr(word)` |
| `eau` | o | — |
| `ouille` | uj | — |
| `aille` | aj | — |
| `euille` | œj | 語末のみ |
| `eil` (語末) | ɛj | — |
| `eille` | ɛj | — |
| `ain/aim` | PUA ɛ̃ (E056) | — |
| `ein/eim` | PUA ɛ̃ (E056) | — |
| `oin` | w + PUA ɛ̃ | — |
| `ien` | j + PUA ɛ̃ | — |
| `tion` | s + j + PUA ɔ̃ (E058) | ルックバック: word[i-1] === 's' の場合のみ t + j + ɔ̃ (先行 s は既に処理済み) |
| `ille` | ij or il | `isIlleAsIl()` 例外チェック |
| `gn` | ɲ | — |
| `ph` | f | — |
| `th` | t | — |
| `ch` | ʃ | — |
| `qu` | k | — |
| `gu` + 前舌母音 | ɡ (u 無音) | — |

#### Phase B: 鼻母音 (5母音群)

| 母音 + n/m | 出力 PUA | 条件 |
|-----------|---------|------|
| a/e + n/m | ɑ̃ (E057) | 後続が子音 or 語末、かつ nn/mm でない |
| i + n/m | ɛ̃ (E056) | 同上 |
| o + n/m | ɔ̃ (E058) | 同上 |
| u + n/m | ɛ̃ (E056) | 同上 |
| y + n/m | ɛ̃ (E056) | 同上 |

**重要ガード (3条件AND):**
1. `i + 2 >= word.length` → 語末なら鼻母音化する (separate branch)
2. `!isVowelChar(word[i + 2])` → 後続が母音ならスキップ ("anime" の "an" は鼻母音化しない)
3. `word[i + 2] !== word[i + 1]` → nn/mm ならスキップ ("bonne" の "on" は鼻母音化しない)

#### Phase C: 母音二重字

| パターン | 出力 |
|---------|------|
| `ou` | u |
| `au` | o |
| `oi` | wa |
| `ai/ei` | ɛ |
| `eu/oeu` | ø (閉) or œ (開)。判定: 直後の1文字 word[i+2] が子音かつ isSilentFinal でない場合 → 開 (œ)、それ以外 → 閉 (ø) |

#### Phase D: 単母音 (コンテキスト依存)

| 母音 | ルール |
|------|--------|
| i + 母音 | → j (半母音化)、ただし語末 silent e 前は除外 |
| o | 開 (ɔ: 後続に発音子音) / 閉 (o: その他) |
| u + i | → ɥi (半母音 turned-h) |
| e (語末) | 黙字 (削除) |
| e (閉音節) | → ɛ (開) |
| e (その他) | → ə (schwa) |
| u | → y_vowel (PUA E01E) |

#### Phase E: 子音

| 子音 | ルール |
|------|--------|
| c + 前舌母音 | → s |
| c + その他 | → k |
| ç | → s |
| g + 前舌母音 | → ʒ |
| g + その他 | → ɡ |
| j | → ʒ |
| r (重複 rr 除去) | → ʁ |
| s (母音間) | → z |
| x (語末) | 黙字 |
| x + e (語末) | 黙字 ("luxe" の x) |
| x + es (語末) | 黙字 |
| x (ex+母音) | → ɡz |
| x (その他) | → ks |
| h | 常に黙字 |
| 語末黙字子音 | d,g,h,m,n,p,s,t,x,z → 削除 |
| 重複子音 | → 単一化 |

### 2-3. 例外辞書

```javascript
const ILLE_AS_IL = new Set(['ville', 'mille', 'tranquille']);
const ER_AS_EHR = new Set([
    'hiver', 'enfer', 'amer', 'cancer', 'super', 'laser',
    'hamster', 'master', 'poster', 'cluster', 'starter',
    'leader', 'transfer', 'fer',
]);
```

### 2-4. PUA マッピング

| トークン | PUA | 用途 |
|---------|-----|------|
| ɛ̃ (`\u025B\u0303`) | `\uE056` | 鼻母音 (in, ain, ein, un, yn) |
| ɑ̃ (`\u0251\u0303`) | `\uE057` | 鼻母音 (an, am, en, em) |
| ɔ̃ (`\u0254\u0303`) | `\uE058` | 鼻母音 (on, om, tion) |
| y_vowel | `\uE01E` | 前舌円唇母音 [y] (u, ù, û) |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 |
|------|------|------|
| **実装エージェント** | 1 | `fr/index.js` フル実装 (convert_word が主作業) |
| **テストエージェント** | 1 | `test-french.js` 作成 + Rust 38 テスト移植 |

**合計: 2 エージェント**

---

## 4. 提供範囲とテスト

### Unit テスト (`test-french.js`)

Rust **38** テストケースの移植 + FR 固有テスト:

| カテゴリ | テスト | 検証 |
|---------|--------|------|
| 鼻母音 | `"bonjour"` | ɔ̃ (PUA E058) |
| 鼻母音 | `"français"` | ɑ̃ (PUA E057) |
| 鼻母音 | `"vin"` | ɛ̃ (PUA E056) |
| 鼻母音ガード | `"bonne"` | 鼻母音化しない (nn) |
| 黙字 | `"petit"` | 末尾 t 削除 |
| 黙字 e | `"porte"` | e 前の t は発音 |
| -er 語尾 | `"parler"` | /e/ |
| -er 例外 | `"mer"` | /ɛʁ/ |
| ch | `"chambre"` | ʃ |
| gn | `"montagne"` | ɲ |
| 母音間 s | `"maison"` | z |
| y_vowel | `"tu"` | PUA E01E |
| oi | `"trois"` | wa |
| -ille | `"fille"` | ij |
| -ille 例外 | `"ville"` | il |
| tion | `"nation"` | sj + ɔ̃ |

### E2E テスト

- `IPA_OUTPUT_LANGUAGES` に `'fr'` 追加
- golden test 3 件の `expected_contains` 有効化

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | リスク | 対策 |
|------|--------|------|
| `convert_word()` のルール順序 | 順序違いで誤マッチ (eau vs au vs e+a) | Rust と同一順序を厳守 |
| 鼻母音の false positive | `"bonne"` で nn ガード漏れ | `word[i+2] !== word[i+1]` チェック |
| `-er` heuristic | 単音節語 (mer, fer) で誤判定 | `countVowels >= 2` + 例外辞書 |
| `eu` 開/閉判定 | 後続子音の silent 判定が必要 | `isSilentFinal()` を正確に移植 |
| `e` muet 判定 | 語中 e の schwa/open-e 判定 | 閉音節判定ロジックを正確に移植 |
| `x` + `-xe`/`-xes` の黙字化漏れ | 語末 x だけでなく x+e, x+es も黙字 | Phase E の x ルールで `-xe`/`-xes` パターンもチェック |
| `oi` vs `oin` のルール順序 | Phase C の oi だけ移植して Phase A の oin を忘れると鼻母音化失敗 | Phase A で oin を先に処理することを厳守 |

### レビュー項目

- [ ] `convert_word()` のルール適用順序が Rust と一致
- [ ] 鼻母音 nn/mm ガードの正確性
- [ ] 例外辞書 (ILLE_AS_IL: 3語, ER_AS_EHR: 14語) の完全移植
- [ ] PUA 4種 (E056, E057, E058, E01E) の正確な出力
- [ ] 語末黙字子音 10文字 (d,g,h,m,n,p,s,t,x,z) の処理
- [ ] golden test 3 件通過

---

## 6. 一から作り直すとしたら

### convert_word() の設計選択

**現在の Rust 実装:** 線形スキャナ + 優先順序付き if-chain (680行)。

**もし一から設計するなら:**

1. **状態マシンアプローチ:**
   - 状態: `INITIAL`, `IN_NASAL_CHECK`, `IN_DIGRAPH`, `IN_VOWEL_SEQUENCE`
   - ルールを状態遷移テーブルで管理
   - **利点:** ルール追加が宣言的、テスト容易
   - **欠点:** Rust との差分が大きくなり、クロスプラットフォームテスト困難
   - **判断:** 不採用。Rust 線形スキャナの直訳が最もリスクが低い

2. **鼻母音検出の独立モジュール化:**
   ```javascript
   function tryNasalVowel(word, i, ch) {
       // 5母音群の鼻母音チェックを1関数に集約
       const nasalMap = { 'a': PUA_AN, 'e': PUA_AN, 'i': PUA_EIN, 'o': PUA_ON, 'u': PUA_EIN, 'y': PUA_EIN };
       if (i + 1 >= word.length) return null;
       const next = word[i + 1];
       if (next !== 'n' && next !== 'm') return null;
       if (i + 2 < word.length && (isVowelChar(word[i + 2]) || word[i + 2] === next)) return null;
       return { phoneme: nasalMap[ch], skip: 2 };
   }
   ```
   - Rust では各母音で同一パターンを繰り返している。JS では抽出して DRY にできる
   - **判断:** 採用推奨。セマンティクスは同一、コード量 ~30% 削減

3. **例外辞書の外部 JSON 化:**
   - 現在: ソースコード内に `Set` で定義
   - 代替: `fr-exceptions.json` として外部化
   - **判断:** 不採用。3+14=17語のためファイル分割は過剰

### FR 固有のバグパターン (開発時の注意)

1. **鼻母音 false positive:** `"bonne"` → nn ガード漏れ (最頻バグ)
2. **黙字 vs 発音子音:** `"porte"` の t は発音 (silent e 前), `"petit"` の t は黙字 (語末)
3. **ルール順序:** `eau` > `au` > `e`+`a`、`tion` > `t`+`i`+`on`、`ouille` > `ou`+`ille`
4. **`-er` heuristic:** `countVowels >= 2` チェック漏れ → `"mer"` が /e/ になる
5. **`eu` 開/閉:** `isSilentFinal()` 判定ミス → ø/œ 逆転
6. **`x` + `-xe`/`-xes` の黙字化漏れ:** 語末 x だけでなく x+e, x+es も黙字
7. **`oi` vs `oin` のルール順序:** Phase A で oin が先に処理されるため安全だが、Phase C の oi だけ移植して Phase A の oin を忘れると鼻母音化が失敗

---

## 7. 後続タスクへの連絡事項

### Phase 3 (PT) への連絡

- FR の鼻母音処理パターン (`tryNasalVowel` 抽出した場合) を参考にできる
- ただし PT は「母音 + n/m 吸収」方式で FR と異なる → 共通関数は `isNasalContext()` 判定のみ
- NFD/NFC 正規化は ES/FR で同一パターン → PT でもコピー可能

### Phase 5 (テスト統合) への連絡

- `IPA_OUTPUT_LANGUAGES` に `'fr'` 追加
- `g2p-wasm-ci.yml` に `test/test-french.js` 追加
- FR の鼻母音 PUA (E056, E057, E058) がテストで正しく検証されることを確認
