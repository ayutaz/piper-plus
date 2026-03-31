# スウェーデン語 G2P 調査レポート

## 概要

piper-plus にスウェーデン語 (sv) を7番目の言語として追加するにあたり、G2P (Grapheme-to-Phoneme) の実装方式を選定するための包括的な調査を実施した。プロジェクトの MIT ライセンスポリシーに準拠し、espeak-ng (GPL-3.0) を回避しつつ、最高精度を達成するアプローチを特定することが目的。

**調査日**: 2026-03-30
**関連 Issue**: #296
**関連 PR**: #294 (espeak-ng 依存のため Request Changes)

---

## 目次

1. [スウェーデン語音韻の概要](#1-スウェーデン語音韻の概要)
2. [既存 OSS G2P ライブラリ調査](#2-既存-oss-g2p-ライブラリ調査)
3. [Epitran 品質評価](#3-epitran-品質評価)
4. [espeak-ng 品質評価](#4-espeak-ng-品質評価)
5. [品質比較サマリー](#5-品質比較サマリー)
6. [利用可能なデータ資源](#6-利用可能なデータ資源)
7. [実装方式の比較と推奨](#7-実装方式の比較と推奨)
8. [推奨アーキテクチャ](#8-推奨アーキテクチャ)
9. [参考資料](#9-参考資料)

---

## 1. スウェーデン語音韻の概要

### 1.1 音素インベントリ

**母音 (17-18 音素):** 9つの母音質それぞれに長短の区別がある。

| 文字 | 長母音 | 短母音 | 備考 |
|------|--------|--------|------|
| a | ɑː | a | |
| e | eː | ɛ | |
| i | iː | ɪ | |
| o | uː / oː | ɔ / ʊ | **最大の課題**: 4音素に対応 |
| u | ʉː | ɵ | |
| y | yː | ʏ | |
| å | oː | ɔ | |
| ä | ɛː | ɛ | |
| ö | øː | œ | |

**子音 (18 音素):**

| 音素 | 説明 | 備考 |
|------|------|------|
| b, d, f, ɡ, h, j, k, l, m, n, p, r, s, t, v | 基本子音 | |
| ŋ | 軟口蓋鼻音 | ng, nk |
| ɕ | 無声歯茎硬口蓋摩擦音 (tj-sound) | tj, kj, k+前母音 |
| ɧ | 無声唇軟口蓋摩擦音 (sj-sound) | sj, sk+前母音, stj, skj, -tion, sch |

**レトロフレックス子音 (5 音素):**

| 音素 | 綴り | 例 |
|------|------|-----|
| ʈ | rt | kort → kɔʈ |
| ɖ | rd | bord → buːɖ |
| ʂ | rs | fors → fɔʂ |
| ɳ | rn | barn → bɑːɳ |
| ɭ | rl | karl → kɑːɭ |

### 1.2 正書法の規則性

| 特徴 | スペイン語 | フランス語 | ポルトガル語 | **スウェーデン語** | 英語 |
|------|-----------|-----------|-------------|-----------------|------|
| 正書法の深さ | 非常に浅い | 深い | 中程度 | **中程度** | 非常に深い |
| 母音の規則性 | 非常に高い | 中 (多くの二重母音字) | 高い | **中~高** | 低い |
| 子音の規則性 | 非常に高い | 中 (黙字多数) | 高い | **中** | 低い |
| ストレスの予測可能性 | 高い (アクセント記号+2規則) | 固定 (最終音節) | 高い | **中 (位置は中, 声調は低)** | 低い |
| rule-based推定精度 | ~98-99% | ~90-93% | ~90-93% | **~85-88% (辞書なし)** | ~60-70% |

### 1.3 主な音韻規則 (rule-based 可能)

#### 子音 Soft/Hard 分岐

前母音 (e, i, y, ä, ö) の前で口蓋化が発生:

| 子音 | 硬母音 (a, o, u, å) の前 | 軟母音 (e, i, y, ä, ö) の前 |
|------|------------------------|--------------------------|
| k | /k/ (katt → kat) | /ɕ/ (kind → ɕɪnd) |
| g | /ɡ/ (gata → ɡɑːta) | /j/ (göra → jøːra) |
| sk | /sk/ (skola → skuːla) | /ɧ/ (sked → ɧeːd) |

#### 母音長 (Complementary Quantity)

強勢音節で予測可能:
- **長母音**: 単子音の前、母音の前、語末 (例: `glas` → ɡlɑːs)
- **短母音**: 二重子音・子音クラスタの前 (例: `glass` → ɡlas)

#### レトロフレックス同化

綴りから100%予測可能:
- rt → /ʈ/, rd → /ɖ/, rs → /ʂ/, rn → /ɳ/, rl → /ɭ/

#### sj-sound (/ɧ/)

主要パターンは規則化可能:
- `sj` → /ɧ/ (常に)
- `sk` + 前母音 → /ɧ/
- `skj` → /ɧ/
- `stj` → /ɧ/
- `-tion`, `-sion` → /ɧ/ (接尾辞認識)

ローンワード由来のパターン (ch, sh, ge-) は辞書が必要。

### 1.4 rule-based で解決困難な課題

| 課題 | 難易度 | 説明 |
|------|--------|------|
| **文字 "o" の4音素対応** | 致命的 | `sol`=/suːl/, `son`=/soːn/, `om`=/ɔm/, `ost`=/uːst/ — 綴りだけでは区別不能 |
| **声調アクセント** | 高 | accent 1 vs accent 2 は綴りに現れない。~300の最小対があるが、機能負荷は低い |
| **ローンワード** | 中 | フランス語/英語/ドイツ語由来の不規則発音 (garage, juice, chef) |

---

## 2. 既存 OSS G2P ライブラリ調査

### 2.1 候補一覧

| # | ライブラリ | ライセンス | 方式 | SV対応 | 精度 | 備考 |
|---|-----------|----------|------|--------|------|------|
| 1 | **Epitran** | **MIT** | rule-based (CSV 60規則) | `swe-Latn` | **31%** | 致命的バグ多数 |
| 2 | **Gruut** | **MIT** | 辞書21K語 + CRF G2P | `sv-se` | 未計測 | **archived** (2025-10) |
| 3 | **DeepPhonemizer** | **MIT** | Neural Transformer | 要学習 | (推定95-98%) | ONNX化実績あり |
| 4 | **CharsiuG2P** | **MIT** | ByT5 100言語 | 対応済み | 中~高 | 巨大モデル (~1GB) |
| 5 | espeak-ng | **GPL-3.0** | rule-based + 辞書 | 対応 | **70%** | **ライセンス不可** |
| 6 | bootphon/phonemizer | **GPL-3.0** | espeak-ng wrapper | 対応 | - | **ライセンス不可** |
| 7 | Sequitur-G2P | **GPL-2.0** | データ駆動 | - | - | **ライセンス不可** |
| 8 | MaryTTS | **LGPL-3.0** | Java | 対応 | - | **ライセンス不適合** |
| 9 | Transphone | **MIT** | Epitran + Neural | 経由 | - | Epitran依存 |
| 10 | MFA G2P | CC-BY-4.0/Apache | wFST (Pynini) | 辞書あり | - | ONNX不可、重い依存 |
| 11 | NVIDIA NeMo G2P | Apache-2.0 | ByT5/Conformer | 不明 | - | 巨大フレームワーク |

### 2.2 各候補の詳細

#### Epitran (MIT)

- **リポジトリ**: https://github.com/dmort27/epitran
- **バージョン**: 1.34.0 (2025-10-16)
- **スウェーデン語データ**: `swe-Latn.csv` (60 grapheme→phoneme マッピング) + `swe-Latn.txt` (23 前処理規則)
- **依存**: `panphon`, `marisa-trie`, `regex`
- **メンテナンス**: アクティブ (1,506 commits)
- **品質**: **31% (45語テスト)** — 致命的バグにより本番使用不可 (詳細は[第3章](#3-epitran-品質評価))

#### Gruut (MIT, archived)

- **リポジトリ**: https://github.com/rhasspy/gruut
- **作者**: Michael Hansen (Piper TTS の原作者)
- **スウェーデン語データ**:
  - `lexicon.db`: 21,108語 (Folkets lexikon 由来, **CC-BY-SA 2.5**)
  - `g2p/model.crf`: 1.5MB CRF G2P モデル
  - espeak variant: 27,192語 (espeak-ng生成, GPL汚染リスク)
- **phoneme 表記**: `²` prefix で声調アクセント2をマーク
- **依存**: `pycrfsuite`, `num2words`, `Babel`, `gruut-ipa`
- **メンテナンス**: **archived** (2025-10-06, read-only)
- **注意**: native lexicon の元データは Folkets lexikon (**CC-BY-SA 2.5** — ShareAlike制約あり)

#### DeepPhonemizer (MIT)

- **リポジトリ**: https://github.com/as-ideas/DeepPhonemizer
- **バージョン**: 0.0.19 (2023-02)
- **アーキテクチャ**: Forward Transformer + CTC / Autoregressive
- **対応言語**: en_us, en_uk, de, fr, es (スウェーデン語の事前学習モデルなし)
- **推定モデルサイズ**: ~5-20MB (ONNX)
- **依存**: PyTorch (学習時のみ)
- **ONNX化**: [Babylon.cpp](https://github.com/Mobile-Artificial-Intelligence/babylon) (MIT) が DeepPhonemizer→ONNX変換の実績あり
- **Rust実装**: [deepphonemizer-rs](https://github.com/ExpressiveLabs/deepphonemizer-rs) (MIT, TorchScript JIT)
- **メンテナンス**: 低アクティブ (344 commits)

#### CharsiuG2P (MIT)

- **リポジトリ**: https://github.com/lingjzhu/CharsiuG2P
- **HuggingFace**: `charsiu/g2p_multilingual_byT5_small_100` (67K+ monthly downloads)
- **アーキテクチャ**: ByT5 (byte-level T5 Transformer)
- **スウェーデン語**: Sprakbanken Swedish pronunciation dictionary で学習済み
- **モデルサイズ**: ~1.1GB (ByT5-small, ~299M params)
- **ONNX化**: `optimum-cli export onnx` で可能
- **問題**: サイズが大きすぎ、推論が遅い。piper-plus への統合には不向き

#### espeak-ng (GPL-3.0 — ライセンス不可)

- **リポジトリ**: https://github.com/espeak-ng/espeak-ng
- **バージョン**: 1.52.0
- **スウェーデン語**: `dictsource/sv_rules` (823行の規則ファイル)
- **品質**: **70% (46語テスト, sx→ɧ補正含む)** — 詳細は[第4章](#4-espeak-ng-品質評価)
- **ライセンス**: **GPL-3.0 — piper-plus の MIT ポリシーと不整合のため直接使用不可**

---

## 3. Epitran 品質評価

### 3.1 テスト環境

- **Epitran**: v1.34.0
- **Python**: 3.11 (Windows 11, `PYTHONUTF8=1`)
- **テスト語数**: 45語、7カテゴリ
- **評価方法**: ストレスマーカーを除外した IPA 文字列の完全一致

### 3.2 Epitran 規則ファイルの構造

`swe-Latn.csv` (60エントリ):

```
子音マッピング: b,d,f,g,h,j,k,l,m,n,p,r,s,t,v,w,x,z + 二重子音 (bb,dd,...) + 特殊 (ch→ɧ, ck→k, dj→j, sj→ɧ, sk→ɧ, skj→ɧ, stj→ɧ, tj→ɕ, kj→ɕ, hj→j, lj→j, gj→j, gn→gn, ng→ŋ)
母音マッピング: a→ɑː, e→eː, i→iː, o→uː, u→ʉː, y→yː, å→oː, ä→ɛː, ö→øː, och→ɔk
```

`swe-Latn.txt` (23 前処理規則):

```
口蓋化: c → s / _ front_vowel, g → j / _ front_vowel, k → ɕ / _ front_vowel
母音短縮: a → ɐ / _ CC, e → ɛ / _ CC, i → ɪ / _ CC, o → ɔ / _ CC, u → ɵ / _ CC, y → ʏ / _ CC, å → ɔ / _ CC, ä → ɛ / _ CC, ö → œ / _ CC
軟口蓋鼻音: gn → ŋn / . _, ng → ŋ / _
```

### 3.3 テスト結果

| カテゴリ | 正解数 | 精度 | 深刻度 |
|---------|--------|------|--------|
| 基本単語 | 5/8 | 62% | 中 |
| **Soft/Hard (sk/k/g)** | **1/9** | **11%** | **致命的** |
| **レトロフレックス** | **0/6** | **0%** | **致命的** |
| sj-sound | 1/3 | 33% | 高 |
| 母音長 | 6/7 | 86% | 低 |
| **o の曖昧性** | **1/8** | **12%** | **致命的** |
| **非強勢母音** | **0/4** | **0%** | **致命的** |
| **総合** | **14/45** | **31.1%** | — |

### 3.4 致命的バグの詳細

#### バグ1: `sk` の処理が Soft/Hard 逆転

CSVの `sk,ɧ` が全ての `sk` にマッチし、前処理の `k → ɕ / _ front_vowel` が `sk` 内の `k` に先行適用されるため、結果が完全に逆:

| 入力 | Epitran出力 | 正解 | 問題 |
|------|-----------|------|------|
| skola (sk+硬母音o) | ɧuːlɑː | skuːla | 硬母音の前で /ɧ/ (逆) |
| sked (sk+軟母音e) | sɕeːd | ɧeːd | 軟母音の前で /sɕ/ (逆) |
| sky (sk+軟母音y) | sɕyː | ɧyː | 同上 |
| skam (sk+硬母音a) | ɧɑːm | skɑːm | 硬母音の前で /ɧ/ (逆) |

**原因**: 前処理で `k → ɕ / _ front_vowel` が発火 → `sked` が `sɕed` に → CSVの `sk→ɧ` がマッチしない。一方 `skola` では `k` が前母音の前でないので変換されず `sk` が残り → CSVの `sk→ɧ` がマッチ。

#### バグ2: レトロフレックス処理が完全欠落

`r+C → retroflex` の規則が前処理・CSV・後処理のいずれにも存在しない:

| 入力 | Epitran出力 | 正解 |
|------|-----------|------|
| barn | bɐrn | bɑːɳ |
| bord | bɔrd | buːɖ |
| fors | fɔrs | fɔʂ |
| karl | kɐrl | kɑːɭ |
| kort | kɔrt | kɔʈ |
| fart | fɐrt | fɑːʈ |

全6語不正解 (0%)。

#### バグ3: `o` が常に `/uː/` にマッピング

CSVに `o,uː` のみ。前処理で二重子音前のみ `o → ɔ` に短縮されるが、`/oː/` への分岐や単独子音前の `/ɔ/` は処理不可:

| 入力 | Epitran出力 | 正解 | 問題 |
|------|-----------|------|------|
| son | suːn | soːn | /oː/ → /uː/ に誤変換 |
| om | uːm | ɔm | 短母音 /ɔ/ → 長母音 /uː/ に誤変換 |
| som | suːm | sɔm | 同上 |

#### バグ4: 語末非強勢母音の長母音化

非強勢位置の母音が長母音のまま出力される:

| 入力 | Epitran出力 | 正解 |
|------|-----------|------|
| gata | ɡɑːtɑː | ɡɑːta |
| flicka | flɪkɑː | flɪka |
| vatten | vɐteːn | vatən |
| pojke | puːjɕeː | pɔjkə |

### 3.5 結論

Epitran のスウェーデン語サポートは **出発点としても使用不可能** なレベル (31%)。`sk` soft/hard の反転は構造的バグであり、修正よりスクラッチ実装の方が効率的。

---

## 4. espeak-ng 品質評価

### 4.1 テスト環境

- **espeak-ng**: v1.52.0 (Windows 11)
- **コマンド**: `espeak-ng -v sv --ipa -q <word>`
- **テスト語数**: 46語、7カテゴリ
- **評価方法**: ストレスマーカー (`ˈ`, `ˌ`) を除外した IPA 文字列の完全一致 + `sx→ɧ`/`ʃ→ɧ` 記号補正

### 4.2 テスト結果

| カテゴリ | 完全一致 | sx→ɧ補正含む | 備考 |
|---------|---------|-------------|------|
| 基本単語 | 7/8 (88%) | 7/8 (88%) | `hus` の長母音マーク漏れ |
| Soft/Hard (sk/k/g) | 6/9 (67%) | **9/9 (100%)** | sx→ɧ 補正で全問正解 |
| レトロフレックス | 1/6 (17%) | 1/6 (17%) | `fors`→`fɔʂ` のみ正解 |
| sj-sound | 0/3 (0%) | 1/3 (33%) | sx記号問題 + `schema` 誤り |
| 母音長 | 7/8 (88%) | 7/8 (88%) | `ful` の長母音マーク漏れ |
| **o の曖昧性** | **6/8 (75%)** | **6/8 (75%)** | Epitran (12%) を大幅超過 |
| 非強勢母音 | 1/4 (25%) | 1/4 (25%) | ジェミネートマーク不一致 |
| **総合** | **28/46 (60.9%)** | **32/46 (69.6%)** | — |

### 4.3 カテゴリ別詳細

#### Soft/Hard (sk/k/g) — sx→ɧ補正で100%

espeak-ng は soft/hard 分岐を正しく処理するが、sj-sound に独自記号 `sx` を使用:

| 入力 | espeak-ng出力 | 正解 | 判定 |
|------|-------------|------|------|
| katt | kˈat | kat | OK |
| kind | ɕˈɪnd | ɕɪnd | OK |
| gata | ɡˈɑːta | ɡɑːta | OK |
| skola | skˈuːla | skuːla | OK (正しく硬) |
| sked | sxˈeːd | ɧeːd | sx→ɧ で一致 |
| sky | sxˈyː | ɧyː | sx→ɧ で一致 |
| sko | skˈuː | skuː | OK (正しく硬) |
| skam | skˈɑːm | skɑːm | OK |
| skinn | sxˈɪn | ɧɪn | sx→ɧ で一致 |

#### レトロフレックス — 17% (大きな弱点)

espeak-ng 1.52.0 はレトロフレックス同化を**ほぼ処理しない**:

| 入力 | espeak-ng出力 | 正解 | 判定 |
|------|-------------|------|------|
| barn | bˈɑːrn | bɑːɳ | NG (rn→ɳ 未変換) |
| bord | bˈuːrd | buːɖ | NG (rd→ɖ 未変換) |
| fors | fˈɔʂ | fɔʂ | **OK** (rs→ʂ は変換) |
| karl | kˈarl | kɑːɭ | NG (rl→ɭ 未変換 + 母音長誤り) |
| kort | kˈɔt | kɔʈ | NG (rt→ʈ 未変換、r消失のみ) |
| fart | fˈɑːt | fɑːʈ | NG (同上) |

`rs→ʂ` のみ変換され、`rn, rd, rl, rt` は未処理。これは espeak-ng の既知のバグ (upstream PR #2391 に関連)。

#### o の曖昧性 — 75% (espeak-ng の強み)

espeak-ng は内部辞書により `o` の多義性をかなり正しく解決:

| 入力 | espeak-ng出力 | 正解 | 判定 |
|------|-------------|------|------|
| sol | sˈuːl | suːl | OK (/uː/) |
| son | sˈoːn | soːn | **OK** (/oː/ — Epitranは不可) |
| om | ˈɔm | ɔm | **OK** (/ɔ/ — Epitranは不可) |
| som | sˈɔm | sɔm | **OK** (/ɔ/ — Epitranは不可) |
| komma | kˈɔma | kɔma | OK |
| blomma | blˈɔma | blɔma | OK |
| ost | ˈʊst | uːst | NG (/ʊ/ vs /uː/) |
| ord | ˈuːrd | uːɖ | NG (レトロフレックス未処理) |

#### 非強勢母音 — 25%

espeak-ng は schwa 還元 (`ə`) を正しく生成するが、ジェミネートマーク (`kː`) が不一致:

| 入力 | espeak-ng出力 | 正解 | 問題 |
|------|-------------|------|------|
| flicka | flˈɪkːa | flɪka | `kː` ジェミネート |
| vatten | vˈatːən | vatən | `tː` ジェミネート |
| pojke | pˈɔjkə | pɔjkə | OK |
| vacker | vˈakːər | vakər | `kː` ジェミネート |

### 4.4 espeak-ng の sj-sound 記号問題

espeak-ng 1.52.0 はスウェーデン語の sj-sound に `/ɧ/` (正式 IPA) ではなく独自記号 `/sx/` を使用:

| 入力 | espeak-ng出力 | 正解 | 後処理 |
|------|-------------|------|--------|
| sjuk | sxˈʉk | ɧʉːk | sx→ɧ + 母音長修正が必要 |
| sjö | sxˈuː | ɧøː | sx→ɧ + 母音修正が必要 |
| skjorta | ɕˈuːta | ɧɔʈa | ɕ→ɧ + 母音修正 + レトロフレックス |
| chef | sxˈɛːf | ɧɛːf | sx→ɧ で概ね一致 |

単純な `sx→ɧ` 置換で部分改善可能だが、母音やレトロフレックスの複合問題は残る。

### 4.5 文レベルの出力

```
"Hej, hur mår du?" → hˈɛj hˈʉr mˈar dʉ
"Jag heter Anna."  → jɑːɡ hˈeːtər ˈana
"Det är en vacker dag." → deːt ˈar ɛn vˈakːər dˈɑːɡ
"Var är stationen?" → vɑːr ˈar stasxˈuːnən
"Jag älskar Sverige." → jɑːɡ ˈalskar svˈɛrjə
```

文レベルでは概ね自然だが、ストレスの配置やsj-sound記号の問題が残る。

### 4.6 難しい単語

```
meteorologiskt  → mˌeːtəˌuːruːlˈoːɡɪskt
sjuksköterska   → sxˈʉkskuːtˌɛʂka
köttbullar      → kˈɔtbɵlˌar
människor       → mˈanɪskˌuːr
```

複合語やストレスの複雑な語でも概ね正しい出力を生成。

### 4.7 結論

espeak-ng は Epitran の約2.2倍の精度 (70% vs 31%) だが、レトロフレックスの処理が大きな弱点。`o` の曖昧性解決は辞書ベースのため良好。ただし **GPL-3.0 のため直接使用不可**。

---

## 5. 品質比較サマリー

### 5.1 カテゴリ別比較

| カテゴリ | Epitran (MIT) | espeak-ng (GPL) | 差分 |
|---------|--------------|-----------------|------|
| 基本単語 | 62% | **88%** | +26pp |
| Soft/Hard (sk/k/g) | 11% | **100%** (sx補正) | +89pp |
| レトロフレックス | 0% | **17%** | +17pp |
| sj-sound | 33% | **33%** (sx補正) | ±0 |
| 母音長 | **86%** | 88% | +2pp |
| o の曖昧性 | 12% | **75%** | +63pp |
| 非強勢母音 | 0% | **25%** | +25pp |
| **総合** | **31%** | **70%** (sx補正) | +39pp |

### 5.2 問題カテゴリ別の解決難易度

| 問題 | rule-basedで解決可能? | 辞書で解決可能? | Neural G2Pで解決可能? |
|------|---------------------|---------------|---------------------|
| Soft/Hard 分岐 | **はい** (100%) | - | はい |
| レトロフレックス | **はい** (100%) | - | はい |
| 母音長 | **はい** (~95%) | - | はい |
| sj-sound (主要パターン) | **はい** (~85%) | 残りを辞書で | はい |
| o の曖昧性 | **いいえ** (~40%) | **はい** (~95%) | **はい** (~98%) |
| 声調アクセント | いいえ (~75%) | はい | はい |
| 非強勢母音短縮 | 部分的 (~70%) | はい | はい |
| ローンワード | いいえ | はい | はい |

---

## 6. 利用可能なデータ資源

### 6.1 発音辞書

| リソース | 語数 | 表記形式 | ライセンス | URL |
|----------|------|---------|----------|-----|
| **NST/OpenSLR Swedish** | **~822,000** | SAMPA | **CC0** (パブリックドメイン) | https://www.openslr.org/29/ |
| NST Sprakbanken (完全版) | ~927,167 | SAMPA | CC0 | https://www.nb.no/sprakbanken/ |
| Folkets lexikon | ~21,000 | IPA | **CC-BY-SA 2.5** (ShareAlike) | https://folkets-lexikon.csc.kth.se/ |
| ipa-dict (sv) | ~21,106 | IPA | CC-BY-SA 2.5 (Folketsから) | https://github.com/open-dict-data/ipa-dict |
| Wiktionary Swedish IPA | ~5,432 | IPA | CC-BY-SA 3.0 | https://en.wiktionary.org/ |
| MFA Swedish dictionaries | 不明 | phoneme分割 | CC-BY-4.0 | https://github.com/MontrealCorpusTools/mfa-models |
| LanguageNet G2Ps (UIUC) | 不明 | FST model | MIT | https://github.com/uiuc-sst/g2ps |

**推奨**: **NST/OpenSLR (CC0, 822K語)** がライセンス・サイズの両面で最適。SAMPA→IPA変換が必要だが、変換表は公開されている。

### 6.2 SAMPA→IPA 変換

NST辞書はSAMPA表記を使用。スウェーデン語SAMPAの主要マッピング:

| SAMPA | IPA | 説明 |
|-------|-----|------|
| A: | ɑː | 長い開前舌母音 |
| E: | ɛː | 長い半開前舌母音 |
| I | ɪ | 短い近前舌母音 |
| O | ɔ | 短い半開後舌母音 |
| U | ʊ | 短い近後舌母音 |
| u: | ʉː | 長い中舌円唇母音 |
| }: | ɵ | 短い中舌円唇母音 |
| y: | yː | 長い前舌円唇母音 |
| Y | ʏ | 短い前舌円唇母音 |
| 2: | øː | 長い半閉前舌円唇母音 |
| 9 | œ | 半開前舌円唇母音 |
| rt | ʈ | レトロフレックス破裂音 |
| rd | ɖ | レトロフレックス破裂音 |
| rs | ʂ | レトロフレックス摩擦音 |
| rn | ɳ | レトロフレックス鼻音 |
| rl | ɭ | レトロフレックス側面音 |
| s\` | ɕ | 無声歯茎硬口蓋摩擦音 (tj-sound) |
| x\\ | ɧ | スウェーデン語 sj-sound |

参照: https://www.phon.ucl.ac.uk/home/sampa/swedish.htm

---

## 7. 実装方式の比較と推奨

### 7.1 方式比較

| 方式 | 推定精度 | モデルサイズ | クロスプラットフォーム | ライセンス | 工数 |
|------|---------|------------|---------------------|----------|------|
| **A. Rule-based独自 + NST辞書** | ~92-95% | 辞書 ~10-20MB | 各言語で個別実装 | MIT + CC0 | 中 |
| **B. DeepPhonemizer + NST学習** | **~95-98%** | **~5-20MB (ONNX)** | **全プラットフォーム共有** | MIT + CC0 | 中-高 |
| C. Rule-based + DeepPhonemizer併用 | ~97-99% | ~25-40MB | ONNX + 規則 | MIT + CC0 | 高 |
| D. CharsiuG2P (ByT5) | ~90-95% | ~1.1GB | ONNX可能 | MIT | 低 |
| E. Gruut lexicon + 独自CRF | ~88-92% | ~3MB | CRF要再実装 | MIT + CC-BY-SA 2.5 | 中 |
| F. espeak-ng + 後処理 | ~85-90% | N/A | N/A | **GPL不可** | — |
| G. Epitran (現状) | ~31% | 0 | 各言語で個別実装 | MIT | — |

### 7.2 各方式の詳細

#### 方式A: Rule-based独自実装 + NST辞書ルックアップ

```
入力テキスト
  ↓
[1] NST辞書ルックアップ (CC0, 822K語, SAMPA→IPA変換済み)
  → ヒット → IPA返却
  → ミス ↓
[2] Rule-based G2P (独自実装)
  → soft/hard分岐, レトロフレックス, 母音長, sj-sound等
  ↓
IPA出力
```

**利点**:
- piper-plus の既存パターン (Spanish/French/Portuguese) と整合
- 外部依存なし (辞書はビルドイン)
- デバッグ・修正が容易

**欠点**:
- Python/C#/Rust/C++/WASM 全てで辞書ロード実装が必要
- rule-based 部分の精度に限界 (o曖昧性, ローンワード)
- 辞書サイズがバイナリに含まれる (~10-20MB)

#### 方式B: DeepPhonemizer + NST辞書で学習 (推奨)

```
[学習時 (1回のみ)]
NST辞書 822K語 (CC0, SAMPA→IPA変換)
  → DeepPhonemizer Forward Transformer + CTC で学習
  → ONNX エクスポート (~5-20MB)

[推論時]
入力テキスト → 単語分割 → ONNX推論 → IPA出力
```

**利点**:
- 822K語の正解データから全パターンを学習 (o曖昧性, sj-sound, レトロフレックス, 声調)
- **単一ONNXモデルを全プラットフォームで共有** (onnxruntime は Python/C#/Rust/C++/WASM 全対応)
- piper-plus は既に onnxruntime に依存 (VITS推論)
- 小型モデル (~5-20MB) で高速推論
- Babylon.cpp (MIT) がDeepPhonemizer→ONNX変換の実績あり

**欠点**:
- モデル学習の初期コスト (1回のみ)
- G2Pモデルのバンドルサイズ追加
- rule-basedと比べてデバッグが困難

#### 方式C: Rule-based + DeepPhonemizer 併用

方式A + 方式B のハイブリッド。規則で処理できる部分は規則で、oの曖昧性等はNeural G2Pで処理。最高精度だが最高工数。

#### 方式D: CharsiuG2P

既成の100言語モデルを使用。~1.1GBのByT5モデルはpiper-plusのTTSモデル (~75MB) の15倍。G2Pのためだけにこのサイズは非現実的。

### 7.3 推奨

**最高精度を目指す場合: 方式B (DeepPhonemizer + NST辞書)** を推奨。

理由:
1. NST辞書 (CC0, 822K語) が全パターンをカバー
2. 単一ONNXモデルで全プラットフォーム対応
3. piper-plus は既に onnxruntime 依存
4. 推定精度 95-98% は rule-based (~92-95%) を上回る
5. o曖昧性・声調アクセントも学習データから獲得

---

## 8. 推奨アーキテクチャ

### 8.1 DeepPhonemizer + NST辞書 (方式B) の実装計画

#### Phase 1: データ準備
1. NST/OpenSLR Swedish Lexicon (CC0) をダウンロード
2. SAMPA→IPA 変換スクリプト作成
3. DeepPhonemizer 学習フォーマットに変換 (word\tphonemes)
4. 学習/検証/テスト分割 (80/10/10)

#### Phase 2: モデル学習
1. DeepPhonemizer Forward Transformer + CTC でスウェーデン語モデル学習
2. 精度評価 (Phone Error Rate, Word Error Rate)
3. ハイパーパラメータ調整

#### Phase 3: ONNX エクスポート
1. 学習済みモデルを ONNX にエクスポート
2. ONNX Runtime での推論検証
3. FP16 量子化によるサイズ最適化

#### Phase 4: piper-plus 統合
1. Python phonemizer (`SwedishPhonemizer`) に ONNX G2P を統合
2. `sv_id_map.py` に音素インベントリ定義
3. `registry.py` に登録
4. `multilingual.py` / `multilingual_id_map.py` 更新
5. テスト作成

#### Phase 5: クロスプラットフォーム
1. Rust: `piper-core` に ONNX G2P ローダー追加
2. C#: `PiperPlus.Core` に ONNX G2P ローダー追加
3. C++: ONNX Runtime C API で G2P 推論
4. WASM: onnxruntime-web で G2P 推論

### 8.2 代替: Rule-based + 辞書 (方式A)

DeepPhonemizerの学習コストを避けたい場合の代替:

1. `swedish.py` (~900-1100行): 独自 rule-based G2P
   - soft/hard分岐、レトロフレックス、母音長、sj-sound
   - 語末非強勢母音短縮
2. NST辞書サブセット (~50K高頻度語): JSON/バイナリで同梱
3. 辞書ヒット → IPA返却、ミス → rule-based フォールバック

---

## 9. 参考資料

### 言語学リソース
- [Swedish phonology — Wikipedia](https://en.wikipedia.org/wiki/Swedish_phonology)
- [Swedish orthography — Wikipedia](https://en.wikipedia.org/wiki/Swedish_orthography)
- [Help:IPA/Swedish — Wikipedia](https://en.wikipedia.org/wiki/Help:IPA/Swedish)
- [Sj-sound — Wikipedia](https://en.wikipedia.org/wiki/Sj-sound)
- [SAMPA for Swedish](https://www.phon.ucl.ac.uk/home/sampa/swedish.htm)
- [Appendix: Swedish pronunciation — Wiktionary](https://en.wiktionary.org/wiki/Appendix:Swedish_pronunciation)
- [Swedish Phonology — Glottopedia](http://www.glottopedia.org/index.php/Swedish_Phonology)
- [The Phonology of Swedish — Oxford Academic](https://academic.oup.com/book/35369/chapter/301110225)
- [Swedish speech synthesis — KBLab Blog](https://kb-labb.github.io/posts/2023-05-24-swedish-text-to-speech/)

### データ資源
- [NST Pronunciation Lexicon for Swedish — OpenSLR](https://www.openslr.org/29/)
- [NST Sprakbanken — Full Lexicon](https://www.nb.no/sprakbanken/en/resource-catalogue/oai-nb-no-sbr-22/)
- [open-dict-data/ipa-dict](https://github.com/open-dict-data/ipa-dict)
- [Folkets lexikon — KTH](https://folkets-lexikon.csc.kth.se/folkets/om.en.html)

### ソフトウェア
- [Epitran — GitHub](https://github.com/dmort27/epitran) (MIT)
- [Gruut — GitHub (archived)](https://github.com/rhasspy/gruut) (MIT)
- [Gruut-IPA — GitHub](https://github.com/rhasspy/gruut-ipa) (MIT)
- [DeepPhonemizer — GitHub](https://github.com/as-ideas/DeepPhonemizer) (MIT)
- [Babylon.cpp — GitHub](https://github.com/Mobile-Artificial-Intelligence/babylon) (MIT, DeepPhonemizer ONNX実績)
- [deepphonemizer-rs — GitHub](https://github.com/ExpressiveLabs/deepphonemizer-rs) (MIT)
- [CharsiuG2P — GitHub](https://github.com/lingjzhu/CharsiuG2P) (MIT)
- [espeak-ng — GitHub](https://github.com/espeak-ng/espeak-ng) (GPL-3.0)
- [LanguageNet G2Ps — GitHub](https://github.com/uiuc-sst/g2ps) (MIT)

### 学術論文
- [A knowledge-based G2P for Swedish — Högskolan i Skövde](http://www.diva-portal.org/smash/record.jsf?pid=diva2:3134)
- [The predictive function of Swedish word accents — Frontiers](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2022.910787/full)
- [CharsiuG2P: Multilingual G2P in 100+ Languages — Interspeech 2022](https://github.com/lingjzhu/CharsiuG2P)
