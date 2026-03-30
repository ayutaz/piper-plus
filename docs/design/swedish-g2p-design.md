# スウェーデン語 G2P 設計書

## 概要

Epitran (31%) と espeak-ng (70%) の品質テスト結果を踏まえ、piper-plus 独自のスウェーデン語 G2P の設計方針を定める。

**推奨方式: NST辞書ルックアップ + Rule-based フォールバック**

**調査日**: 2026-03-30
**関連**: `swedish-g2p-research.md` (調査レポート), Issue #296, PR #294

---

## 目次

1. [設計方針の決定](#1-設計方針の決定)
2. [Soft/Hard 子音分岐](#2-softhard-子音分岐)
3. [レトロフレックス同化](#3-レトロフレックス同化)
4. [文字 "o" の4音素問題](#4-文字-o-の4音素問題)
5. [sj-sound (/ɧ/) 処理](#5-sj-sound-ɧ-処理)
6. [母音長と非強勢母音](#6-母音長と非強勢母音)
7. [声調アクセント](#7-声調アクセント)
8. [ローンワード処理](#8-ローンワード処理)
9. [NST辞書統合](#9-nst辞書統合)
10. [音素インベントリとPUA割り当て](#10-音素インベントリとpua割り当て)
11. [piper-plus 統合アーキテクチャ](#11-piper-plus-統合アーキテクチャ)
12. [実装ロードマップ](#12-実装ロードマップ)

---

## 1. 設計方針の決定

### 1.1 方式比較 (最終結論)

| 方式 | 推定精度 | バイナリサイズ | クロスプラットフォーム | 複雑度 |
|------|---------|-------------|---------------------|--------|
| **A. NST辞書 + Rule-based** | **~97-99%** | **~2.3 MB (gzip)** | JSON/バイナリ各言語で実装 | **中** |
| B. DeepPhonemizer ONNX | ~95-98% | ~22 MB (FP16) | ONNX全プラットフォーム共有 | 高 |
| C. Rule-based のみ | ~88-92% | ~10 KB | 各言語で実装 | 中 |
| D. Epitran (現状) | 31% | - | - | - |
| E. espeak-ng | 70% | - | GPL不可 | - |

### 1.2 方式A (NST辞書 + Rule-based) を推奨する理由

1. **辞書ルックアップは100%正確** — 辞書内の語はそのまま返すだけ
2. **NST辞書 (CC0, 822K語)** のスポットチェックで全10語正解 (soft/hard, retroflex, "o" 区別, sj-sound 全てクリア)
3. **Rule-based フォールバック** で OOV (新語、複合語) をカバー → 有効カバー率 ~99%+
4. **DeepPhonemizer より軽量** — 辞書 2.3 MB vs ONNX 22 MB
5. **実装がシンプル** — JSON/HashMap ルックアップは全プラットフォームで自明
6. **piper-plus の既存パターンと整合** — Spanish/French/Portuguese と同じ rule-based ベース

### 1.3 処理フロー

```
入力テキスト
  │
  ▼
[Stage 0] 正規化 & トークン化
  │
  ▼
[Stage 1] NST辞書ルックアップ (822K語, CC0)
  → ヒット → SAMPA→IPA変換済み発音を返却
  → ミス ↓
[Stage 2] ローンワード接尾辞規則 (-tion, -sion, -age)
  │
  ▼
[Stage 3] ローンワード接頭辞規則 (sch-, ch-, sh-, ph-, th-)
  │
  ▼
[Stage 4] ネイティブ G2P 規則
  - Soft/Hard 子音分岐 (sk, k, g + 前母音/後母音)
  - 母音長 (Complementary Quantity)
  - sj-sound ネイティブパターン (sj-, skj-, stj-)
  - 非強勢母音短縮
  │
  ▼
[Stage 5] 後処理
  - レトロフレックス同化 (r+C → retroflex)
  - ストレス付与
  │
  ▼
IPA出力 → phoneme_ids + prosody
```

---

## 2. Soft/Hard 子音分岐

### 2.1 Epitran のバグ (致命的)

Epitranの `sk` 処理は **Soft/Hard が完全に逆転**:
- CSV規則 `sk,ɧ` が全ての `sk` にマッチ → `skola` (硬) が `/ɧuːla/` に
- 前処理 `k → ɕ / _ front_vowel` が先に発火 → `sked` (軟) が `/sɕeːd/` に

**解決策**: 最長一致の規則順序を厳密に守る。

### 2.2 前母音/後母音の定義

| カテゴリ | 文字 | 備考 |
|---------|------|------|
| **前母音 (軟)** | e, i, y, ä, ö | 口蓋化を引き起こす |
| **後母音 (硬)** | a, o, u, å | 口蓋化なし |

### 2.3 規則 (最長一致順)

以下の順序を **必ず** 守ること:

```
1.  skj  → /ɧ/  (常に、無条件)
2.  stj  → /ɧ/  (常に、無条件)
3.  sk + 前母音 → /ɧ/  (skの2文字をkの前に評価)
4.  sk + 後母音 → /sk/
5.  sk + 子音   → /sk/
6.  sj   → /ɧ/  (常に、無条件)
7.  tj   → /ɕ/  (常に、無条件)
8.  kj   → /ɕ/  (常に、無条件)
9.  k + 前母音  → /ɕ/  (例外リスト確認)
10. k + 後母音  → /k/
11. dj   → /j/  (語頭のみ)
12. gj   → /j/  (語頭のみ)
13. hj   → /j/  (語頭のみ)
14. lj   → /j/  (語頭のみ)
15. ng   → /ŋ/
16. g + 前母音  → /j/  (例外リスト確認)
17. g + 後母音  → /ɡ/
```

### 2.4 例外リスト

#### K + 前母音で硬い /k/ を保持する語 (~80語)

**ローンワード**: kille, kebab, kennel, keps, ketchup, kick, kilt, kimono, kitsch, kibbutz, kiwi

**語幹が /k/ で終わる活用形**: leker, steker, söker, tänker, dyker, ryker, röker, smeker, läker, märker, räcker, väcker, viker, stryker, sjunker, sticker

**語中の -ke-/-ki-**: pojke, fröken, onkel, sockel, socker, ocker, märke, mörker, tecken, vacker, naken, säker, enkel, paket, raket, staket, silke, vinkel, skelett

#### G + 前母音で硬い /ɡ/ を保持する語 (~60語)

**名詞**: bagel, bageri, bygel, bygge, båge, dager, flygel, gecko, hage, hagel, lager, läge, läger, mage, nagel, regel, segel, seger, stege, tagel, tegel, tiger, tygel

**活用形**: duger, flyger, ligger, ljuger, lägger, stiger, suger, tiger, tigger, väger, äger

**-era 動詞**: agera, delegera, reagera, segregera, tangera

### 2.5 形態論ヒューリスティック

活用語尾 (-er, -en, -et, -ar, -or, -ade, -ande, -ning) を剥がして語幹が /k/ か /g/ で終わるか確認:

```python
for suffix in ("erna", "arna", "ade", "ande", "ning", "er", "en", "et", "ar", "or"):
    if word.endswith(suffix):
        stem = word[:-len(suffix)]
        if stem and stem[-1] in ('k', 'g') and stem in KNOWN_STEMS:
            return HARD  # 硬い発音を保持
```

### 2.6 精度推定

| 方式 | sk | k + 例外 | g + 例外 | 総合 |
|------|-----|---------|---------|------|
| 規則のみ | ~99% | ~70-75% | ~65-70% | ~75-80% |
| + 例外リスト (~200語) | ~99.5% | ~92-95% | ~90-93% | ~93-96% |
| + 形態論ヒューリスティック | ~99.5% | ~96-98% | ~95-97% | ~96-98% |
| **+ NST辞書** | **~100%** | **~100%** | **~100%** | **~100%** |

---

## 3. レトロフレックス同化

### 3.1 問題

- Epitran: **0/6 (0%)** — 規則が完全欠落
- espeak-ng: **1/6 (17%)** — rs→ʂ のみ、rn/rd/rl/rt は未処理

### 3.2 規則 (>98% 規則的)

| 綴り | 変換 | 例 |
|------|------|-----|
| r + t | → /ʈ/ | kort → kɔʈ |
| r + d | → /ɖ/ | bord → buːɖ |
| r + s | → /ʂ/ | fors → fɔʂ |
| r + n | → /ɳ/ | barn → bɑːɳ |
| r + l | → /ɭ/ | karl → kɑːɭ |

### 3.3 カスケード規則

レトロフレックスは連鎖する。/r/ → retroflex後、次の歯茎音もレトロフレックス化:

```
r + s + t → /ʂ/ + /ʈ/  (först → fœʂʈ)
r + n + s → /ɳ/ + /ʂ/  (garns → ɡɑːɳʂ)
```

**例外**: /ɭ/ は連鎖を停止 (rl → ɭ だが、ɭ の後は伝播しない)

### 3.4 ブロッキング規則

- **rr (重子音)**: レトロフレックス化しない。`borrs` → [bɔrːs], NOT [bɔʂ]
- **語境界**: 連続発話では語境界を跨いで適用 (`har du` → [haɖʉ])
- **複合語境界**: 透過的 — 適用される (`barndom` → [bɑːɳduːm])

### 3.5 処理ステージ

**ベース G2P の後、ストレス付与の前** に適用。音素列を左から右にスキャンし、/r/ + 歯茎音パターンを検出して変換。

```python
RETROFLEX_MAP = {'t': 'ʈ', 'd': 'ɖ', 's': 'ʂ', 'n': 'ɳ', 'l': 'ɭ'}
PROPAGATING = {'ʈ', 'ɖ', 'ʂ', 'ɳ'}  # ɭ は伝播しない

def apply_retroflex(phonemes):
    result = []
    i = 0
    while i < len(phonemes):
        if phonemes[i] == 'r' and i+1 < len(phonemes):
            # rr チェック
            if phonemes[i+1] == 'r':
                result.append('rː')
                i += 2
                continue
            # retroflex チェック
            if phonemes[i+1] in RETROFLEX_MAP:
                j = i + 1
                while j < len(phonemes) and phonemes[j] in RETROFLEX_MAP:
                    retro = RETROFLEX_MAP[phonemes[j]]
                    result.append(retro)
                    j += 1
                    if retro not in PROPAGATING:
                        break
                i = j
                continue
        result.append(phonemes[i])
        i += 1
    return result
```

---

## 4. 文字 "o" の4音素問題

### 4.1 問題 (最大の課題)

| 音素 | 例 | パターン |
|------|-----|---------|
| /uː/ (長・閉) | sol, stol, bok, bro, ko | **デフォルト** (長い "o") |
| /oː/ (長・中) | son, mor, lov, dom | 閉じたクラス (~30-50語) |
| /ɔ/ (短・開) | om, som, komma, blomma | 子音クラスタ/重子音の前 |
| /ʊ/ (短・閉) | ost (変種) | 非常にまれ、/ɔ/ と統合可 |

### 4.2 Rule-based で解決できる部分

**短/長の区別** (~95% 正確):
- 重子音/子音クラスタの前 → 短い /ɔ/: komma, blomma, kopp, folk, tolv, kort
- 単子音の前/語末 → 長い /uː/ or /oː/: sol, stol, bok, bro

**長い "o" の /uː/ vs /oː/ 区別** — 規則だけでは **不可能**:
- 後続子音によるパターンは不安定 (kon=/kuːn/, son=/soːn/ — 同じ +n)
- /oː/ は stora vokaldansen (大母音推移) の例外語のみ

### 4.3 /oː/ 例外語リスト (~30語)

歴史的に古い基本語彙が /uː/ への推移を免れた閉じたクラス:

```
son /soːn/, mor /moːr/, lov /loːv/, dom /doːm/,
ton /toːn/, zon /soːn/, fon /foːn/, ion /joːn/,
bror /bruːr/ (変種: /broːr/), ...
```

### 4.4 解決方針

**NST辞書で100%解決**。辞書に822K語の正確な発音が含まれており、"o" の4方向分岐は全て学習データから取得済み。

OOV語のフォールバック:
1. 子音クラスタ/重子音前 → /ɔ/ (短)
2. /oː/ 例外リスト確認 → ヒットなら /oː/
3. デフォルト → /uː/ (長)

---

## 5. sj-sound (/ɧ/) 処理

### 5.1 問題

- Epitran: `sk` が逆転 + `-tion`/`sch` 未対応
- espeak-ng: 独自記号 `sx` 使用 + `schema`→`ʃɛma` 誤り

### 5.2 綴りパターンの完全一覧

#### 100% 規則予測可能 (無条件)

| パターン | 例 | 備考 |
|---------|-----|------|
| sj | sjö, sjuk, sjunga | 常に /ɧ/ |
| skj | skjorta, skjuta | 常に /ɧ/ |
| stj | stjärna, stjälk | 常に /ɧ/ |
| sch | schema, schack | 常に /ɧ/ (ドイツ語借用) |
| sh | show, shopping | 常に /ɧ/ (英語借用) |
| ch | chef, choklad, chans | スウェーデン語では /ɧ/ がデフォルト |

#### 条件付き (前母音の前)

| パターン | 条件 | 例 /ɧ/ | 例 /sk/ |
|---------|------|---------|---------|
| sk + 前母音 | e, i, y, ä, ö の前 | sked, sky, skön | - |
| sk + 後母音 | a, o, u, å の前 | - | skola, skog, skatt |

#### 接尾辞ベース (100%)

| パターン | 発音 | 例 |
|---------|------|-----|
| -tion | /ɧuːn/ | station, nation, information |
| -sion | /ɧuːn/ | passion, version, mission |
| -ssion | /ɧuːn/ | permission |
| -age (語末) | /ɑːɧ/ | garage, massage, sabotage |

#### 辞書必須 (フランス語借用)

| パターン | 問題 | 例 |
|---------|------|-----|
| g + 前母音 (仏語) | ネイティブは /j/、仏語は /ʒ/ or /ɧ/ | genre, giraff, generös |
| j (仏語) | ネイティブは /j/、仏語は /ʒ/ | journalist, jalusi, jour |

### 5.3 /ɧ/ vs /ɕ/ の区別 (重要)

| 文脈 | 音素 | パターン |
|------|------|---------|
| sk + 前母音 | **/ɧ/** (sj-sound) | sked, sky, skön |
| k + 前母音 | **/ɕ/** (tj-sound) | kind, köp, kör |

この区別は **必須** — 混同するとネイティブには別の音に聞こえる。

### 5.4 精度推定

| カテゴリ | カバー率 | 規則精度 |
|---------|---------|---------|
| sj, skj, stj (無条件) | ~35% | 100% |
| sk + 前母音 (条件付き) | ~25% | ~98% |
| -tion, -sion (接尾辞) | ~20% | ~99% |
| ch, sch, sh (借用デフォルト) | ~8% | ~95% |
| -age (仏語接尾辞) | ~3% | ~95% |
| g/j 仏語借用 (辞書) | ~9% | 辞書で ~90% |
| **合計** | **100%** | **規則のみ ~85-88%, 辞書込み ~98-99%** |

---

## 6. 母音長と非強勢母音

### 6.1 母音インベントリ (18音素)

| 文字 | 長母音 | 短母音 | 長の例 | 短の例 |
|------|--------|--------|--------|--------|
| a | ɑː | a | glas [ɡlɑːs] | glass [ɡlas] |
| e | eː | ɛ | vet [veːt] | vett [vɛt] |
| i | iː | ɪ | vit [viːt] | vitt [vɪt] |
| o | uː | ʊ/ɔ | bok [buːk] | bott [bʊt] |
| u | ʉː | ɵ | hus [hʉːs] | hund [hɵnd] |
| y | yː | ʏ | ny [nyː] | sylt [sʏlt] |
| å | oː | ɔ | åt [oːt] | ått [ɔt] |
| ä | ɛː | ɛ | säl [sɛːl] | säll [sɛl] |
| ö | øː | œ | öl [øːl] | öst [œst] |

### 6.2 Complementary Quantity 規則 (~95%)

**強勢音節**:
- **長母音** + 短子音: 単子音の前/語末 (`glas`, `tak`, `fil`)
- **短母音** + 長子音/クラスタ: 重子音/子音クラスタの前 (`glass`, `tack`, `fill`, `hand`)

### 6.3 例外

| 例外 | 説明 | 例 |
|------|------|-----|
| **機能語** | 短母音 + 短子音 | han, hon, den, men, om, som |
| **語末 m** | 重子音化されないが短母音 | hem [hɛm], rum [rɵm], fem [fɛm] |
| **r + 子音** | 母音が長いまま | bord [buːrd], fart [fɑːrt], barn [bɑːrn] |

### 6.4 非強勢母音短縮

**設計判断: Central Standard Swedish ではシュワーを使わない。** 非強勢位置では各母音の短い変種を使用。

| 語末パターン | 発音 | 例 |
|------------|------|-----|
| -a | [a] (短い) | gata → [ˈɡɑːta], flicka → [ˈflɪka] |
| -e | [ɛ] | pojke → [ˈpɔjkɛ], vacker → [ˈvakɛr] |
| -en | [ɛn] | vatten → [ˈvatɛn], liten → [ˈliːtɛn] |
| -er | [ɛr] | söker → [ˈsøːkɛr] |
| -ar | [ar] | bilar → [ˈbiːlar] |
| -or | [ɔr] | flickor → [ˈflɪkɔr] |
| -ig / -lig | [ɪɡ] | viktig → [ˈvɪktɪɡ] |

### 6.5 ストレス検出

**優先順位**:
1. 例外辞書
2. 複合語検出 → 第1要素に主ストレス、第2要素に副ストレス
3. ストレス吸引接尾辞 (-tion, -itet, -eri, -era, -ist, -ör)
4. 非ストレス接頭辞 (be-, för-, ge-, er-, an-)
5. **デフォルト: 第1音節** (ゲルマン語パターン)

---

## 7. 声調アクセント

### 7.1 設計判断: Phase 1 では省略

| 根拠 | 詳細 |
|------|------|
| 機能負荷が低い | ~357 の最小対のみ。文脈で100%解消可能 |
| VITS が暗黙的に学習 | 既存の piper sv_SE-nst-medium モデルが音声データから声調を学習済み |
| PR #294 のアプローチは誤り | ストレスと声調を混同 (別の独立特徴) |
| 他言語との一貫性 | EN/ES/FR/PT は全て a1=0 |

### 7.2 Prosody マッピング

**Phase 1 (推奨)**:

| 次元 | 意味 | 値 |
|------|------|-----|
| a1 | 未使用 | 0 (全トークン) |
| a2 | ストレスレベル | 0=非強勢, 1=副, 2=主 |
| a3 | 単語音素数 | 整数 |

**Phase 2 (将来の拡張)**:

| 次元 | 意味 | 値 | ソース |
|------|------|-----|--------|
| a1 | 声調アクセント型 | 0=不明, 1=accent 1, 2=accent 2 | NST辞書のSAMPA `"` vs `""` |
| a2 | ストレスレベル | 0/1/2 | 規則ベース |
| a3 | 単語音素数 | 整数 | G2P出力から計算 |

---

## 8. ローンワード処理

### 8.1 頻度

スウェーデン語テキストの **~10-15%** がローンワード。そのうち **~5-8%** がネイティブ規則を破る。

### 8.2 規則予測可能なパターン (Stage 2)

**接尾辞規則** (Stage 2, ネイティブ規則の前に適用):

| パターン | 発音 | 例 | 精度 |
|---------|------|-----|------|
| -tion | /ɧuːn/ | station, nation | 100% |
| -sion | /ɧuːn/ | passion, version | 100% |
| -ssion | /ɧuːn/ | mission | 100% |
| -age (語末) | /ɑːɧ/ | garage, massage | ~95% |
| -eur | /øːr/ | (respelled -ör が多い) | ~90% |
| -eum | /eːɵm/ | museum | ~90% |
| -ium | /ɪɵm/ | stadium | ~90% |

**接頭辞/字母規則** (Stage 3):

| パターン | 発音 | 例 | 精度 |
|---------|------|-----|------|
| sch- | /ɧ/ | schema, schack | ~95% |
| ch- | /ɧ/ | chef, choklad | ~90% |
| sh- | /ɧ/ | show, shopping | ~95% |
| ph- | /f/ | filosofi (respelled) | 100% |
| th- | /t/ | teater (respelled) | 100% |

### 8.3 辞書必須パターン (~200語)

| カテゴリ | 語数 | 例 |
|---------|------|-----|
| 仏語 ch- | ~10 | chef, choklad, champagne |
| 仏語 -age | ~15 | garage, massage, sabotage |
| 仏語 g→/ʒ/ | ~10 | genre, giraff, generös |
| 仏語 j→/ʒ/ | ~5 | journalist, jalusi, jour |
| 英語 sh→/ɧ/ | ~5 | show, shopping |
| 英語 j→/j/ | ~10 | juice, jeans, job (Swedified) |
| 地名 | ~20 | Stockholm, Göteborg, Malmö |

**全てNST辞書でカバー済み。** OOV のローンワードは接尾辞/接頭辞規則でフォールバック。

### 8.4 設計判断: /ʒ/ 音素

/ʒ/ はネイティブスウェーデン語に存在しない (仏語借用のみ)。

**推奨**: /ʒ/ を /ɧ/ にマップ。多くの話者が自然に置換しており、音素インベントリをシンプルに保てる。精度重視の場合は /ʒ/ を別音素として追加可能。

---

## 9. NST辞書統合

### 9.1 辞書の特性

| 項目 | 値 |
|------|-----|
| ソース | OpenSLR 29 (Emelie Kullmann 改善版) |
| ライセンス | **CC0** (パブリックドメイン) |
| 語数 | 822,740 エントリ (820,572 ユニーク語) |
| フォーマット | 2カラム TSV (WORD\tSAMPA) |
| 複合語率 | 70.9% (583K) |
| 複数発音語 | 2,105語 |
| 声調情報 | **なし** (簡略版で失われた) |

### 9.2 SAMPA→IPA 変換テーブル (主要43音素)

| SAMPA | IPA | 説明 |
|-------|-----|------|
| A: | ɑː | 長い開後舌母音 |
| E: | ɛː | 長い半開前舌母音 |
| I | ɪ | 短い近前舌母音 |
| O | ɔ | 短い半開後舌母音 |
| U | ʊ | 短い近後舌母音 |
| }: | ʉː | 長い中舌円唇母音 |
| 8 | ɵ | 短い中舌円唇母音 |
| y: | yː | 長い前舌円唇母音 |
| Y | ʏ | 短い前舌円唇母音 |
| 2: | øː | 長い半閉前舌円唇母音 |
| 9 | œ | 半開前舌円唇母音 |
| rt | ʈ | レトロフレックス破裂音 (無声) |
| rd | ɖ | レトロフレックス破裂音 (有声) |
| rs | ʂ | レトロフレックス摩擦音 |
| rn | ɳ | レトロフレックス鼻音 |
| rl | ɭ | レトロフレックス側面音 |
| s\` | ɕ | tj-sound |
| x\\ | ɧ | sj-sound |
| " | ˈ | 主ストレス |
| % | ˌ | 副ストレス |

### 9.3 ティアード辞書戦略

| ティア | 語数 | gzip サイズ | カバー率 | 用途 |
|--------|------|-----------|---------|------|
| **Core** | ~238K (単純語) | **~2.3 MB** | ~95% | CLI/WASM デフォルト |
| **Full** | ~821K (全語) | ~10.6 MB | ~99%+ | Python 学習パイプライン |
| Rule fallback | OOV | 0 | 残り ~1% | 新語/複合語 |

### 9.4 ストレージフォーマット (プラットフォーム別)

| プラットフォーム | フォーマット | ロード方式 |
|----------------|-----------|----------|
| Python | JSON dict or TSV | `dict` に全ロード |
| Rust | バイナリ HashMap or FST | メモリマップ可能 |
| C# | `Dictionary<string,string>` from JSON | デシリアライズ |
| C++ | `unordered_map` from バイナリ | 起動時ロード |
| WASM | IndexedDB キャッシュ + JSON | 遅延ロード |

---

## 10. 音素インベントリとPUA割り当て

### 10.1 スウェーデン語専用音素 (新規)

**単一コードポイント (PUA不要)**:

| 音素 | Unicode | 説明 |
|------|---------|------|
| ɧ | U+0267 | sj-sound (スウェーデン語固有) |
| ɕ | U+0255 | tj-sound (ZH と共有可) |
| ɖ | U+0256 | レトロフレックス有声 |
| ʈ | U+0288 | レトロフレックス無声 |
| ɳ | U+0273 | レトロフレックス鼻音 |
| ɭ | U+026D | レトロフレックス側面音 |
| ɵ | U+0275 | 短い中舌円唇母音 |

**PUA割り当てが必要な多文字トークン (9個 + 2 reserved)**:

| トークン | PUA | 説明 |
|---------|------|------|
| iː | 0xE059 | 長い前舌母音 |
| yː | 0xE05A | 長い前舌円唇 |
| eː | 0xE05B | 長い半閉前舌 |
| ɛː | 0xE05C | 長い半開前舌 |
| øː | 0xE05D | 長い半閉前舌円唇 |
| ɑː | 0xE05E | 長い開後舌 |
| oː | 0xE05F | 長い半閉後舌 |
| uː | 0xE060 | 長い閉後舌 |
| ʉː | 0xE061 | 長い閉中舌円唇 |
| (reserved) | 0xE062 | 予備 (将来の拡張用) |
| (reserved) | 0xE063 | 予備 (将来の拡張用) |

**`_PUA_START` を 0xE064 に更新** (動的割り当ての開始位置)

**二重母音 (aʊ, ɛʊ) について**: NST辞書には二重母音を含むエントリが 3,625件存在する (aʊ: 3,092件, ɛʊ: 533件)。これらは PUA を割り当てず、2つの独立した音素トークン (例: `a` + `ʊ`) として表現する。これは piper-plus の他言語における二重母音の扱い (中国語の `aɪ`/`eɪ` 等も構成音素の組み合わせで表現) と一貫している。0xE062/0xE063 は当初二重母音用に検討されたが、不要と判断し reserved とした。

### 10.2 既存言語との共有

| 音素 | SV | ZH | EN | ES | FR | PT | JA |
|------|----|----|----|----|----|----|-----|
| ʂ | ✓ | ✓ | - | - | - | - | - |
| ɕ | ✓ | ✓ | - | - | - | - | - |
| ŋ | ✓ | - | ✓ | - | - | - | - |
| ɪ | ✓ | - | ✓ | - | - | - | - |
| ɔ | ✓ | - | - | - | ✓ | - | - |
| ʊ | ✓ | - | ✓ | - | - | - | - |

---

## 11. piper-plus 統合アーキテクチャ

### 11.1 新規作成ファイル

```
src/python/piper_train/phonemize/
├── swedish.py              # SwedishPhonemizer クラス (~900-1100行)
└── sv_id_map.py           # 音素インベントリ (~50行)

tools/
└── convert_nst_dictionary.py  # NST SAMPA→IPA 変換ツール

data/
└── sv_dict_core.json      # Core辞書 (238K語, ~2.3 MB gzip)

test/
└── test_swedish_phonemizer.py  # テスト (~100+ テストケース)
```

### 11.2 変更が必要な既存ファイル

| ファイル | 変更内容 |
|---------|---------|
| `registry.py` | `_auto_register()` に SwedishPhonemizer 登録 |
| `multilingual.py` | `_latin_languages` に `"sv"` 追加 |
| `multilingual_id_map.py` | `LANGUAGE_PHONEMES["sv"]` 登録 |
| `token_mapper.py` | 9個のPUA割り当て追加, `_PUA_START` 更新 |

### 11.3 SwedishPhonemizer クラス設計

```python
class SwedishPhonemizer(Phonemizer):
    def __init__(self, dict_path: str | None = None):
        self._dict: dict[str, str] = {}
        if dict_path:
            self._load_dict(dict_path)

    def phonemize(self, text: str) -> list[str]: ...

    def phonemize_with_prosody(self, text: str) -> tuple[list[str], list[ProsodyInfo | None]]:
        # 1. 正規化 & トークン化
        # 2. 辞書ルックアップ (ヒット → IPA返却)
        # 3. ローンワード接尾辞規則
        # 4. ネイティブ G2P 規則 (soft/hard, 母音長, sj-sound)
        # 5. レトロフレックス同化 (後処理)
        # 6. ストレス付与
        # 7. ProsodyInfo 構築 (a1=0, a2=stress, a3=count)
        ...

    def get_phoneme_id_map(self) -> dict[str, list[int]] | None:
        return None  # multilingual_id_map に委譲
```

### 11.4 テスト戦略

| カテゴリ | テスト数 | 内容 |
|---------|---------|------|
| 基本母音 | 10 | 長短9対 + schwa |
| Soft/Hard | 15 | sk/k/g + 前母音/後母音 + 例外 |
| レトロフレックス | 12 | rt/rd/rs/rn/rl + カスケード + rr ブロック |
| sj-sound | 20 | sj/skj/stj/sch/sh/ch/sk+前母音/-tion/-sion |
| 母音長 | 10 | 最小対 (glas/glass, tak/tack) |
| "o" 曖昧性 | 10 | /uː/ vs /oː/ vs /ɔ/ |
| 非強勢 | 8 | -a, -e, -en, -er, -ar, -or, -ig, -lig |
| ストレス | 10 | 第1音節, 複合語, 接頭辞, 接尾辞 |
| ローンワード | 10 | 仏語/英語/独語借用 |
| エッジケース | 5 | 空文字, 数字, 句読点 |
| **合計** | **~110** | |

---

## 12. 実装ロードマップ

### Phase 1: データ準備 + Python 実装

1. NST辞書ダウンロード & SAMPA→IPA変換スクリプト作成
2. Core辞書 (238K語) の JSON/バイナリ生成
3. `swedish.py` 実装 (辞書ルックアップ + rule-based フォールバック)
4. `sv_id_map.py` + `token_mapper.py` PUA追加
5. `registry.py`, `multilingual.py`, `multilingual_id_map.py` 統合
6. テスト 110+ ケース

### Phase 2: クロスプラットフォーム

7. Rust: `swedish.rs` (辞書ロード + 規則)
8. C#: `SwedishPhonemizer.cs`
9. C++: `swedish_phonemize.cpp`
10. WASM/JS: `swedish.js` (IndexedDB辞書キャッシュ)

### Phase 3: モデル学習 & リリース

11. スウェーデン語TTSデータセット準備
12. 6langベースからのファインチューニング
13. ONNX エクスポート + テスト
14. ドキュメント & リリース

### Phase 4 (将来): 品質向上

15. 声調アクセント対応 (NST辞書から a1 に追加)
16. 複合語分割ヒューリスティック改善
17. 数字/略語展開

---

## 参考資料

調査レポート `docs/design/swedish-g2p-research.md` に全参考資料を記載。
