# スウェーデン語対応 要求定義書

## 文書情報

| 項目 | 値 |
|------|-----|
| 作成日 | 2026-03-30 |
| ブランチ | `feature/swedish-language-support` |
| Issue | #296 |
| 関連 PR | #294 (espeak-ng依存のため Request Changes) |
| 関連文書 | `swedish-g2p-research.md` (調査), `swedish-g2p-design.md` (設計), `nst-dictionary-integration.md` (辞書) |

---

## 1. 目的

piper-plus に8番目の言語としてスウェーデン語 (sv) を追加する。espeak-ng (GPL) に依存せず、MIT ライセンスを維持しながら、既存 OSS (Epitran 31%, espeak-ng 70%) を超える精度 (~97-99%) を達成する。

---

## 2. スコープ

### 2.1 対象範囲 (In Scope)

| # | 項目 | 説明 |
|---|------|------|
| R-01 | Python Phonemizer | `SwedishPhonemizer` クラス (学習用 + 推論用) |
| R-02 | NST辞書統合 | CC0辞書 (822K語) の SAMPA→IPA 変換 + ルックアップ |
| R-03 | Rule-based フォールバック | OOV語向けのネイティブG2P規則エンジン |
| R-04 | 音素インベントリ | `sv_id_map.py` + PUA割り当て + `token_mapper.py` 更新 |
| R-05 | マルチリンガル統合 | `registry.py`, `multilingual.py`, `multilingual_id_map.py` への統合 |
| R-06 | テストスイート | 110+ テストケース、CI統合 |
| R-07 | SAMPA→IPA変換ツール | NST辞書の前処理スクリプト |

### 2.2 対象外 (Out of Scope)

| # | 項目 | 理由 | 将来対応 |
|---|------|------|---------|
| O-01 | Rust/C#/C++/WASM 実装 | Phase 2 で対応 | Phase 2 |
| O-02 | 声調アクセント (accent 1/2) | 機能負荷が低い、VITS が暗黙学習 | Phase 4 |
| O-03 | 数字・略語展開 | 別タスク | Phase 4 |
| O-04 | スウェーデン語TTSモデル学習 | 別タスク | Phase 3 |
| O-05 | 方言対応 (Skånska等) | Central Standard Swedish のみ対象 | 未定 |

---

## 3. 前提条件

| # | 前提 |
|---|------|
| P-01 | NST/OpenSLR Swedish Lexicon (CC0) が利用可能 (https://www.openslr.org/29/) |
| P-02 | ターゲット方言は Central Standard Swedish (Rikssvenska) |
| P-03 | espeak-ng をランタイム依存として使用しない (MIT ポリシー) |
| P-04 | 既存の Phonemizer ABC (`base.py`) のインターフェースに準拠 |
| P-05 | 既存6言語 (JA/EN/ZH/ES/FR/PT) の動作に影響を与えない |

---

## 4. 機能要件

### FR-01: NST辞書ルックアップ

| 項目 | 要件 |
|------|------|
| 説明 | NST辞書 (822K語, CC0) をSAMPA→IPA変換し、単語入力からIPA発音を返す |
| 入力 | 小文字正規化済みのスウェーデン語単語 |
| 出力 | IPA文字列 (ストレスマーカー含む) |
| 辞書フォーマット | JSON (Python dict) — ロード時に全メモリ展開 |
| 辞書ティア | Core (238K単純語, ~2.3 MB gzip) をデフォルト |
| 複数発音語 | 最初の発音を採用 (2,105語が複数発音を持つ) |
| 受入基準 | 辞書内の語に対して100%正確なIPA出力 |

### FR-02: SAMPA→IPA 変換ツール

| 項目 | 要件 |
|------|------|
| 説明 | NST辞書のSAMPA表記を piper-plus IPA 表記に変換するスクリプト |
| 入力 | OpenSLR `lexicon.txt` (TSV: WORD\tSAMPA) |
| 出力 | JSON dict (`{word: ipa}`) |
| 変換対象 | 43 SAMPA音素 → IPA (`nst-dictionary-integration.md` の変換テーブル準拠) |
| ストレス | `"` → `ˈ` (主), `%` → `ˌ` (副) |
| 大文字→小文字 | NST辞書は全大文字 → 小文字に正規化 |
| 特殊エントリ | `!SIL`, `<UNK>`, ハイフン接頭断片を除外 |
| 受入基準 | 変換後の辞書でスポットチェック20語全正解 |

### FR-03: Rule-based G2P フォールバック

辞書に存在しない語 (OOV) に対して、規則ベースのG2P変換を提供する。

#### FR-03a: Soft/Hard 子音分岐

| 項目 | 要件 |
|------|------|
| 前母音 | e, i, y, ä, ö |
| 後母音 | a, o, u, å |
| sk + 前母音 → /ɧ/ | `sked` → /ɧeːd/, `sky` → /ɧyː/ |
| sk + 後母音 → /sk/ | `skola` → /skuːla/, `skog` → /skuːɡ/ |
| k + 前母音 → /ɕ/ | `kind` → /ɕɪnd/, `köp` → /ɕøːp/ |
| g + 前母音 → /j/ | `genom` → /jenom/ |
| 規則順序 | 最長一致: skj > stj > sk+V > sj > tj > kj > k+V > g+V |
| 例外リスト | k例外 ~80語, g例外 ~60語 (設計書 §2.4) |
| 形態論ヒューリスティック | 語尾剥がし (-er/-en/-et/-ar) で語幹の硬い子音を検出 |
| 受入基準 | テスト15語で全問正解 (Epitranの逆転バグなし) |

#### FR-03b: レトロフレックス同化

| 項目 | 要件 |
|------|------|
| r+t → /ʈ/ | `kort` → /kɔʈ/ |
| r+d → /ɖ/ | `bord` → /buːɖ/ |
| r+s → /ʂ/ | `fors` → /fɔʂ/ |
| r+n → /ɳ/ | `barn` → /bɑːɳ/ |
| r+l → /ɭ/ | `karl` → /kɑːɭ/ |
| カスケード | r+s+t → /ʂʈ/ (först → fœʂʈ) |
| rr ブロック | `rr` + 歯茎音 → レトロフレックス化しない |
| ɭ 停止 | /ɭ/ の後は連鎖しない |
| 処理ステージ | ベースG2P後、ストレス付与前 |
| 受入基準 | テスト12語で全問正解 (Epitranの0%を解消) |

#### FR-03c: sj-sound (/ɧ/) パターン

| 項目 | 要件 |
|------|------|
| 無条件パターン | sj, skj, stj, sch, sh, ch → /ɧ/ |
| 条件付き | sk + 前母音 → /ɧ/ (FR-03a と統合) |
| 接尾辞 | -tion → /ɧuːn/, -sion → /ɧuːn/, -age → /ɑːɧ/ |
| /ɕ/ との区別 | tj, kj → /ɕ/、k + 前母音 → /ɕ/ (別音素) |
| 受入基準 | テスト20語で正答率 ≥ 90% |

#### FR-03d: 母音長 (Complementary Quantity)

| 項目 | 要件 |
|------|------|
| 長母音 | 単子音前/語末 → 長母音 (glas → ɡlɑːs) |
| 短母音 | 重子音/子音クラスタ前 → 短母音 (glass → ɡlas) |
| r+C 例外 | r + 子音の前では母音が長いまま (bord → buːrd) |
| 語末 m 例外 | 語末 m は重子音化されないが母音は短い (hem → hɛm) |
| 機能語 | 機能語リスト (~30語) は短母音 + 短子音を許容 |
| 受入基準 | 母音長テスト10語で正答率 ≥ 90% |

#### FR-03e: 非強勢母音短縮

| 項目 | 要件 |
|------|------|
| 語末 -a | 常に短い [a] (gata → ɡɑːta、NOT ɡɑːtɑː) |
| 語末 -e | 短い [ɛ] (pojke → pɔjkɛ) |
| 語末 -en, -er, -el | 短い [ɛn], [ɛr], [ɛl] |
| 語末 -ar, -or | 短い [ar], [ɔr] |
| 語末 -ig, -lig | 短い [ɪɡ] |
| シュワー | **使用しない** (Central Standard Swedish) |
| 受入基準 | 非強勢テスト8語で全問正解 (Epitranの0%を解消) |

#### FR-03f: ストレス検出

| 項目 | 要件 |
|------|------|
| デフォルト | 第1音節に主ストレス |
| 非ストレス接頭辞 | be-, för-, ge-, er-, an- → 第2音節にストレス |
| ストレス吸引接尾辞 | -tion, -itet, -eri, -era, -ist, -ör → 接尾辞にストレス |
| 複合語 | (Phase 2) 第1要素に主、第2要素に副ストレス |
| 受入基準 | ストレステスト10語で正答率 ≥ 80% |

#### FR-03g: ローンワード規則

| 項目 | 要件 |
|------|------|
| 接尾辞前処理 | -tion/ɧuːn/, -sion/ɧuːn/, -age/ɑːɧ/ (ネイティブ規則の前) |
| 接頭辞/字母 | sch→/ɧ/, ch→/ɧ/, sh→/ɧ/, ph→/f/, th→/t/ |
| 処理順序 | ローンワード規則 → ネイティブ規則 |
| 受入基準 | ローンワードテスト10語で正答率 ≥ 80% |

### FR-04: 音素インベントリ

| 項目 | 要件 |
|------|------|
| `sv_id_map.py` | `SWEDISH_PHONEMES` リストをエクスポート |
| 新規単一コードポイント | ɧ, ɕ, ɖ, ʈ, ɳ, ɭ, ɵ (7音素) |
| 新規PUA (多文字) | iː, yː, eː, ɛː, øː, ɑː, oː, uː, ʉː (9音素) |
| PUA開始位置 | 0xE059 から割り当て、`_PUA_START` を更新 |
| 既存との衝突 | PR #294 の PUA 0xE059-0xE060 を考慮し、互換性を維持 |
| 受入基準 | 全PUA割り当てがユニーク、既存言語のIDと衝突しない |

### FR-05: Phonemizer ABC 準拠

| 項目 | 要件 |
|------|------|
| `phonemize(text)` | `list[str]` を返す (IPA音素列。BOS/EOS/PAD は `post_process_ids()` で付与) |
| `phonemize_with_prosody(text)` | `tuple[list[str], list[ProsodyInfo \| None]]` を返す |
| `get_phoneme_id_map()` | `None` を返す (multilingual_id_map に委譲) |
| `post_process_ids()` | デフォルト実装を使用 (BOS `^`, EOS `$`, PAD) |
| ProsodyInfo | a1=0 (未使用), a2=ストレス (0/1/2), a3=単語音素数 |
| 受入基準 | `Phonemizer` ABC の全抽象メソッドを正しく実装 |

### FR-06: マルチリンガル統合

| 項目 | 要件 |
|------|------|
| `registry.py` | `_auto_register()` に `SwedishPhonemizer` を `"sv"` で登録 |
| `multilingual.py` | `_latin_languages` に `"sv"` を追加 |
| `multilingual_id_map.py` | `LANGUAGE_PHONEMES["sv"]` を登録 |
| `token_mapper.py` | 9個のPUA割り当てを `FIXED_PUA_MAPPING` に追加 |
| マルチリンガルキー | `"en-sv"`, `"ja-sv"`, `"ja-en-zh-es-fr-pt-sv"` 等が動作 |
| 受入基準 | `"en-sv"` で英語/スウェーデン語混在テキストが正しく音素化 |

### FR-07: テストスイート

| 項目 | 要件 |
|------|------|
| テスト数 | 110+ テストケース |
| カテゴリ | 基本母音(10), soft/hard(15), retroflex(12), sj-sound(20), 母音長(10), "o"曖昧性(10), 非強勢(8), ストレス(10), ローンワード(10), エッジ(5) |
| マーカー | `@pytest.mark.unit`, `@pytest.mark.integration` |
| 辞書不在時 | rule-based のみのテストも動作 (`@pytest.mark.no_dict`) |
| CI | `python-tests.yml` に追加、Ubuntu/macOS/Windows |
| 受入基準 | 全テスト PASS |

---

## 5. 非機能要件

### NFR-01: ライセンス

| 項目 | 要件 |
|------|------|
| プロジェクトライセンス | MIT を維持 |
| NST辞書 | CC0 (パブリックドメイン) — 制約なし |
| espeak-ng | ランタイム依存として **使用禁止** (GPL-3.0) |
| 前処理での espeak-ng 使用 | 許容 (学習データ生成時のみ) |
| 受入基準 | `LICENSE.md` に変更なし、GPL依存なし |

### NFR-02: パフォーマンス

| 項目 | 要件 |
|------|------|
| 辞書ロード時間 | Core辞書 (238K語) ≤ 3秒 |
| 単語あたり音素化 | 辞書ヒット: ≤ 0.01ms, Rule-based: ≤ 1ms |
| メモリ使用量 | Core辞書 ≤ 50 MB (展開後) |
| 受入基準 | 既存言語の音素化速度と同等以上 |

### NFR-03: 精度

| 項目 | 要件 |
|------|------|
| 辞書内語 | **100%** (辞書の正確さに依存) |
| OOV語 (rule-based) | ≥ 88% (soft/hard + retroflex + 母音長 + sj-sound) |
| 総合 (辞書 + rule) | ≥ **95%** (ランニングテキストベース) |
| 比較ベースライン | Epitran (31%), espeak-ng (70%) を超過 |
| 受入基準 | テストスイート110+ケースで正答率 ≥ 95% |

### NFR-04: 互換性

| 項目 | 要件 |
|------|------|
| 既存言語への影響 | JA/EN/ZH/ES/FR/PT の動作に変更なし |
| Python バージョン | 3.11+ |
| 新規外部依存 | なし (辞書はビルドイン JSON) |
| 受入基準 | 既存テストスイート全 PASS |

### NFR-05: 保守性

| 項目 | 要件 |
|------|------|
| コード構造 | `spanish.py` / `french.py` と同等のパターン |
| ファイルサイズ | `swedish.py` ≤ 1,500行 |
| 例外リスト | コード内定数として定義 (外部ファイル不要) |
| ドキュメント | 各規則にコメント付き (言語学的根拠を記載) |
| 受入基準 | コードレビューで可読性・保守性を確認。`wc -l src/python/piper_train/phonemize/swedish.py` が 1,500 以下であることを CI で検証 |

---

## 6. 成果物一覧

| # | 成果物 | パス | 説明 |
|---|--------|------|------|
| D-01 | SwedishPhonemizer | `src/python/piper_train/phonemize/swedish.py` | メインG2Pモジュール |
| D-02 | 音素インベントリ | `src/python/piper_train/phonemize/sv_id_map.py` | SWEDISH_PHONEMES |
| D-03 | SAMPA→IPA変換ツール | `src/python/piper_train/tools/convert_nst_dictionary.py` | 辞書前処理 |
| D-04 | Core辞書 | ダウンロード+変換で生成 (gitに含めない) | 238K語 JSON |
| D-05 | テストスイート | `test/test_swedish_phonemizer.py` | 110+ テストケース |
| D-06 | registry.py 変更 | `src/python/piper_train/phonemize/registry.py` | sv 登録 |
| D-07 | multilingual.py 変更 | `src/python/piper_train/phonemize/multilingual.py` | sv 追加 |
| D-08 | multilingual_id_map.py 変更 | `src/python/piper_train/phonemize/multilingual_id_map.py` | sv 追加 |
| D-09 | token_mapper.py 変更 | `src/python/piper_train/phonemize/token_mapper.py` | PUA 追加 |

---

## 7. 受入テストケース (主要)

以下のテストが全て PASS することが受入条件。

### AT-01: 辞書ルックアップ

```python
# NST辞書に存在する語は100%正確
assert phonemize("barn") == [..., "b", "ɑː", "ɳ", ...]
assert phonemize("sjukhus") == [..., "ɧ", "ʉː", "k", ...]  # sj-sound
assert phonemize("station") == [..., "s", "t", "a", "ɧ", "uː", "n", ...]  # -tion
```

### AT-02: Soft/Hard (Epitranバグの解消確認)

```python
# sk + 前母音 = /ɧ/ (NOT /sɕ/)
assert "ɧ" in phonemize("sked")     # spoon
assert "ɧ" in phonemize("sky")      # sky
assert "ɧ" in phonemize("skön")     # nice

# sk + 後母音 = /sk/ (NOT /ɧ/)
assert phonemize("skola") does not contain "ɧ"   # school
assert phonemize("skog") does not contain "ɧ"    # forest

# k + 前母音 = /ɕ/ (NOT /ɧ/)
assert "ɕ" in phonemize("kind")     # cheek
assert "ɕ" in phonemize("köp")      # buy

# k + 前母音の例外 = /k/
assert "k" in phonemize("kille")    # guy (exception)
```

### AT-03: レトロフレックス (Epitran 0%の解消確認)

```python
assert "ɳ" in phonemize("barn")     # rn → ɳ
assert "ɖ" in phonemize("bord")     # rd → ɖ
assert "ʂ" in phonemize("fors")     # rs → ʂ
assert "ɭ" in phonemize("karl")     # rl → ɭ
assert "ʈ" in phonemize("kort")     # rt → ʈ

# rr はブロック
assert "ʂ" not in phonemize("borrs")  # rr + s → NOT ʂ
```

### AT-04: 文字 "o" の区別

```python
# /uː/ (デフォルト長)
assert "uː" in phonemize("sol")     # sun

# /oː/ (例外)
assert "oː" in phonemize("son")     # son

# /ɔ/ (短、クラスタ前)
assert "ɔ" in phonemize("om")       # about
assert "ɔ" in phonemize("komma")    # come
```

### AT-05: 非強勢母音 (Epitran 0%の解消確認)

```python
# 語末 -a は短い [a] (NOT [ɑː])
result = phonemize("gata")
assert result does not end with "ɑː"  # NOT ɡɑːtɑː

# 語末 -e は短い [ɛ]
result = phonemize("pojke")
assert result ends with "ɛ" or "e"   # NOT eː
```

### AT-06: マルチリンガル

```python
# sv 単独で登録される
from piper_train.phonemize.registry import get_phonemizer
sv = get_phonemizer("sv")
assert sv is not None

# en-sv マルチリンガルが動作
ensv = get_phonemizer("en-sv")
result = ensv.phonemize("Hello, jag heter Anna")
assert len(result) > 0
```

### AT-07: 既存言語への非影響

```python
# 既存の全テストが PASS (regression なし)
# JA, EN, ZH, ES, FR, PT の既存テストスイートに変更なし
```

---

## 8. 制約事項

| # | 制約 | 影響 |
|---|------|------|
| C-01 | NST辞書はSAMPA表記のみ — 声調アクセント情報なし | Phase 1 では声調非対応 |
| C-02 | NST辞書はOOV非対応 — 新語/固有名詞にrule-basedフォールバック | OOV精度 ~88% |
| C-03 | "o" の /uː/ vs /oː/ 区別は辞書なしでは不可能 | OOV の "o" 含有語は ~70% 精度 |
| C-04 | 複合語分割は Phase 1 未対応 | 辞書に無い新規複合語のストレス精度が低い |
| C-05 | ラテン文字言語の自動判別は限定的 | en-sv では `default_latin_language` が en になる |

---

## 9. リスク

| # | リスク | 影響度 | 発生可能性 | 緩和策 |
|---|--------|--------|-----------|--------|
| RK-01 | NST辞書の機械生成エントリに誤りがある | 中 | 低 | スポットチェックで品質確認済み (10/10正解) |
| RK-02 | PUA割り当てが既存モデルと衝突 | 高 | 低 | PR #294 のPUA範囲と整合させる |
| RK-03 | Core辞書 (238K語) のカバー率が不十分 | 中 | 低 | Full辞書 (822K語) へのアップグレードパスあり |
| RK-04 | rule-based OOV精度が期待未満 | 中 | 中 | NST辞書カバー率 ~95% で緩和 |
| RK-05 | en-sv でスウェーデン語テキストが英語と誤判定 | 中 | 中 | ラテン文字判別の改善 (å/ä/ö 検出) |
