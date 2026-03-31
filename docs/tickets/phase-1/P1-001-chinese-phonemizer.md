# P1-001: ChinesePhonemizer (pypinyin)

> Phase: 1 (全言語展開)
> マイルストーン: v0.2.0
> 対応要求: FR-100
> 依存チケット: P0-003 (コア抽象)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

piper-g2p パッケージに中国語 (Mandarin) の G2P 機能を追加する。pypinyin を用いて漢字をピンインに変換し、ピンイン→IPA 変換ルールによって IPA トークン列を返す。Phase 0 で確立した IPA-first / エンコード分離の設計方針に従い、PUA 変換や BOS/EOS を含まない純粋な IPA 出力を提供する。

### ゴール

- `get_phonemizer("zh").phonemize("你好世界")` が IPA トークン列を返す
- `phonemize_with_prosody()` が声調情報を `ProsodyInfo.a1` に含む prosody を返す
- 声調サンドヒ (T3+T3, 一, 不) が適用される
- 儿化音 (erhua) が正しく処理される
- pypinyin 未インストール時は `ImportError` (利用時に発生)

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/piper_g2p/chinese.py` | ChinesePhonemizer 実装 (IPA-first) |
| `src/python/g2p/piper_g2p/registry.py` | `_auto_register()` に zh を追加 |
| `src/python/g2p/tests/test_chinese.py` | 単体テスト |

### 実装手順

1. 現在の `src/python/piper_train/phonemize/chinese.py` をベースにコピー
2. 以下の変更を適用:
   - `map_sequence()` (PUA 変換) の呼び出しを削除
   - `token_mapper` への依存を除去
   - `phonemize()` と `phonemize_with_prosody()` が IPA トークン列をそのまま返すように変更
   - `get_phoneme_id_map()` メソッドを削除 (Phase 0 で確立した 2-method ABC に準拠)
   - `from .base import Phonemizer, ProsodyInfo` のインポートパスを `piper_g2p.base` に変更
3. 声調サンドヒルール (`_apply_tone_sandhi`) をそのまま移植:
   - T3+T3 → T2+T3
   - 一 (T1) → T2 before T4, T4 before T1/T2/T3
   - 不 (T4) → T2 before T4
4. `registry.py` の `_auto_register()` に pypinyin の try/except ブロックを追加
5. テストケースを作成

### API / インターフェース

```python
from piper_g2p import get_phonemizer

phonemizer = get_phonemizer("zh")

# 基本音素化
tokens = phonemizer.phonemize("你好")
# -> ["n", "i", "tone2", "x", "aʊ", "tone3"]
# (T3+T3 サンドヒ適用: 你 nǐ → ní)

# prosody 付き音素化
tokens, prosody = phonemizer.phonemize_with_prosody("你好世界")
# prosody[i].a1 = tone number (1-5)
# prosody[i].a2 = syllable position in word (1-based)
# prosody[i].a3 = word length in syllables
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装エージェント | 1 | chinese.py の移植・IPA-first 化、registry 更新 |
| テストエージェント | 1 | テストケース作成、声調サンドヒの網羅テスト |

---

## 4. テスト計画

### 提供範囲

ChinesePhonemizer の音素化出力が IPA トークン列であること、声調サンドヒが正しく適用されること、prosody 情報が正しいことを検証する。

### Unit テスト

| テストケース | 入力 | 期待出力 (概要) |
|-------------|------|---------------|
| 基本漢字 | `"你好"` | `["n", "i", "tone2", "x", "aʊ", "tone3"]` (T3 sandhi) |
| 声調サンドヒ T3+T3 | `"你好"` | 你: tone2 (not tone3) |
| 声調サンドヒ 一 | `"一定"` | 一: tone2 (before T4) |
| 声調サンドヒ 一 | `"一般"` | 一: tone4 (before T1) |
| 声調サンドヒ 不 | `"不对"` | 不: tone2 (before T4) |
| 儿化音 | `"花儿"` | ɚ トークンが含まれる |
| 句読点 | `"你好，世界！"` | `,` と `!` が含まれる |
| 空白処理 | `"你 好"` | スペーストークンが含まれる |
| prosody a1 | `"好"` | a1 = 3 (tone3) |
| PUA なし | 任意 | PUA 文字 (U+E000-U+F8FF) が含まれない |
| BOS/EOS なし | 任意 | `"^"` `"$"` が含まれない |

### E2E テスト

- `get_phonemizer("zh")` でインスタンスが取得できること
- pypinyin 未インストール時に `ImportError` が発生すること (CI 環境でモック検証)

---

## 5. 懸念事項とレビュー項目

### 懸念事項

- **再帰的声調サンドヒ未実装**: 3 連続以上の三声 (e.g., 你买火) では左から右への pairwise 適用のみ。言語学的に正確な bracketed sandhi (syntactic structure に基づく再帰的適用) は未実装。これは既知制限として文書化する。
- `phonemize_from_pinyin_syllables()` の移植要否: AISHELL-3 データセット用のバイパス関数。独立パッケージでは需要が低いため、初期リリースでは省略を検討。

### レビュー項目

- [ ] IPA トークンに PUA 文字が混入していないこと
- [ ] `"^"` / `"$"` が出力に含まれていないこと
- [ ] 声調サンドヒの 4 ルールが全てテストされていること
- [ ] 儿化音のトークン位置が正しいこと (tone marker の前)
- [ ] `registry.py` で pypinyin 未インストール時にスキップされること

---

## 6. 一から作り直すとしたら

pypinyin の Style.TONE3 出力をパースする現在の方式は堅牢だが、`_normalize_pinyin()` と `_split_pinyin()` のエッジケースが多い (y/w の正規化、j/q/x 後の u→ü 変換など)。一から作り直すなら、pypinyin の Style.INITIALS + Style.FINALS を組み合わせて初声・韻母を直接取得し、正規化ステップを省略する設計を検討する。ただし現在の実装は 508K 発話で検証済みのため、移植が現実的。

---

## 7. 後続タスクへの連絡事項

- P1-006 (MultilingualPhonemizer): 中国語の登録が完了次第、`"ja-en-zh"` 等の複合コードで自動生成可能になる
- P1-008 (pyproject.toml): `[zh]` extra に `pypinyin>=0.50` を追加する必要がある
- P1-010 (テストフィクスチャ): 中国語テストケースを `phoneme_test_cases.json` に追加する
- P1-009 (ドキュメント): 再帰的声調サンドヒの制限を既知制限セクションに記載する
