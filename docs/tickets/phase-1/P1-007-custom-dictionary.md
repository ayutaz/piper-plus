# P1-007: カスタム辞書 + 入力バリデーション

> Phase: 1 (全言語展開)
> マイルストーン: v0.2.0
> 対応要求: FR-102
> 依存チケット: P0-003 (コア抽象)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

piper-g2p パッケージにカスタム辞書機能を追加する。技術用語や固有名詞の読みをユーザーが定義し、音素化前のテキスト前処理として適用できるようにする。JSON v1.0/v2.0 形式をサポートし、Rust/C++ 実装と互換性のあるフォーマットとする。セキュリティ上の入力バリデーション (ファイルサイズ制限、パストラバーサル拒否) も実装する。

### ゴール

- JSON v1.0 (シンプル key:value) と v2.0 (メタデータ付き) の両形式をロードできる
- 10MB を超える辞書ファイルの読み込みを拒否する
- パストラバーサル攻撃 (`../` を含むパス) を拒否する
- 大文字小文字の区別・非区別エントリを同時に扱える
- 優先度ベースのエントリ上書きが動作する
- `apply_to_text()` でテキスト中の単語を読みに置換できる

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/piper_g2p/custom_dict.py` | CustomDictionary クラス (バリデーション強化版) |
| `src/python/g2p/tests/test_custom_dict.py` | 単体テスト |
| `src/python/g2p/tests/fixtures/dict_v1.json` | v1.0 テスト辞書 |
| `src/python/g2p/tests/fixtures/dict_v2.json` | v2.0 テスト辞書 |

### 実装手順

1. 現在の `src/python/piper_train/phonemize/custom_dict.py` をベースにコピー
2. 以下のセキュリティ強化を追加:
   - ファイルサイズ制限 (10MB): `os.path.getsize()` で事前チェック
   - パストラバーサル拒否: `Path.resolve()` でパスを正規化し、`..` を含むパスを拒否
   - JSON パース時の例外ハンドリング強化
3. 以下の変更を適用:
   - `default_dict_dir` のハードコードパスを除去: 独立パッケージではデフォルト辞書ディレクトリを持たない。`load_defaults=True` のデフォルトを `False` に変更。
   - `_load_default_dictionaries()` は `dict_dir` パラメータを受け取る形に変更
4. 既存機能をそのまま移植:
   - JSON v1.0 / v2.0 パース
   - 大文字小文字の区別/非区別エントリ管理
   - 優先度ベースのエントリ上書き
   - `apply_to_text()`: 長い単語を先にマッチ、日本語/英語の境界処理
   - `add_word()` / `remove_word()` / `save_dictionary()`
   - `get_pronunciation()` / `get_stats()`
5. テストケースを作成

### API / インターフェース

```python
from piper_g2p.custom_dict import CustomDictionary

# 辞書のロード
dict = CustomDictionary(load_defaults=False)
dict.load_dictionary("my_dict.json")

# テキスト前処理
text = dict.apply_to_text("GPT-SoVITSは音声合成です")
# -> "ジーピーティーソヴィッツは音声合成です" (辞書にエントリがあれば)

# 動的エントリ追加
dict.add_word("OpenAI", "オープンエーアイ", priority=8)

# 読み取得
pronunciation = dict.get_pronunciation("OpenAI")
# -> "オープンエーアイ"

# 統計
stats = dict.get_stats()
# -> {"total_entries": 42, "case_insensitive_entries": 40, "case_sensitive_entries": 2}
```

**JSON v1.0 形式:**
```json
{
  "version": "1.0",
  "entries": {
    "GPT": "ジーピーティー",
    "TTS": "ティーティーエス"
  }
}
```

**JSON v2.0 形式:**
```json
{
  "version": "2.0",
  "description": "Custom TTS dictionary",
  "metadata": {"author": "user", "license": "MIT"},
  "entries": {
    "GPT": {"pronunciation": "ジーピーティー", "priority": 8},
    "TTS": {"pronunciation": "ティーティーエス", "priority": 5}
  }
}
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装エージェント | 1 | custom_dict.py の移植・セキュリティ強化 |
| テストエージェント | 1 | バリデーション・辞書適用のテスト |

---

## 4. テスト計画

### 提供範囲

CustomDictionary のロード・適用・バリデーションが正しく動作すること。

### Unit テスト

| テストケース | 入力 | 期待出力 (概要) |
|-------------|------|---------------|
| v1.0 ロード | v1.0 JSON | エントリが正しくロードされる |
| v2.0 ロード | v2.0 JSON | エントリ + メタデータが正しくロードされる |
| 10MB 制限 | 11MB ファイル | 例外が発生する |
| パストラバーサル | `"../etc/passwd"` | 例外が発生する |
| 存在しないファイル | `"nonexistent.json"` | `FileNotFoundError` |
| 不正 JSON | `"invalid json"` | `json.JSONDecodeError` |
| apply_to_text 基本 | テキスト + 辞書 | 単語が置換される |
| apply_to_text 境界 | `"GPTは"` | `"GPT"` のみ置換、`"は"` は保持 |
| 大文字小文字非区別 | `"gpt"` → dict has `"GPT"` | マッチする |
| 大文字小文字区別 | `"iPhone"` | 大文字小文字を区別してマッチ |
| 優先度上書き | 同一キーで priority 異なるエントリ | 高優先度が勝つ |
| add_word | 動的追加 | get_pronunciation で取得可能 |
| remove_word | 動的削除 | get_pronunciation が None を返す |
| save_dictionary | 保存 + 再ロード | エントリが保持される |
| コメント行スキップ | `"// comment"` key | スキップされる |

### E2E テスト

- 辞書ロード → apply_to_text → phonemize のパイプラインが動作すること
- 空の辞書でも apply_to_text がテキストをそのまま返すこと

---

## 5. 懸念事項とレビュー項目

### 懸念事項

- **デフォルト辞書ディレクトリ**: 現在の実装は `Path(__file__).parent.parent.parent.parent.parent / "data" / "dictionaries"` にハードコードされている。独立パッケージではこのパスは無効。`load_defaults=False` をデフォルトにし、明示的なパス指定を要求する。
- **正規表現キャッシュ**: `pattern_cache` は辞書エントリ数に比例してメモリを消費する。大規模辞書 (数万エントリ) での性能検証が必要。
- **日本語境界検出**: 英語単語の境界検出は `\b` (word boundary) に相当する lookbehind/lookahead で実装しているが、日本語テキスト内の英語単語の境界は Unicode 文字種の変化点で検出している。混在テキストでの精度を検証する必要がある。

### レビュー項目

- [ ] 10MB 制限が `load_dictionary()` の最初に適用されること
- [ ] パストラバーサル検出が `Path.resolve()` ベースで正しく動作すること
- [ ] デフォルト辞書ディレクトリのハードコードが除去されていること
- [ ] v1.0 / v2.0 の両形式が正しくパースされること
- [ ] 優先度ベースの上書きが正しく動作すること
- [ ] `apply_to_text()` が長い単語を先にマッチすること

---

## 6. 一から作り直すとしたら

現在の実装は辞書適用時にエントリを長さ順にソートして逐次 regex マッチしており、O(n*m) (n=エントリ数, m=テキスト長) の計算量になる。一から作り直すなら、Aho-Corasick アルゴリズムを使用して全エントリを一括マッチし、O(m+k) (k=マッチ数) に高速化する。また辞書フォーマットを TOML に変更して可読性を向上させることも検討する。

---

## 7. 後続タスクへの連絡事項

- P1-009 (ドキュメント): JSON v1.0/v2.0 のスキーマ仕様を README に記載
- P1-011 (API 凍結): CustomDictionary API が v1.0.0 に含まれるか検討 (別パッケージ化も選択肢)
- Rust/C# 互換: 辞書フォーマットは Rust (`src/rust/piper-core/`) と C# (`src/csharp/PiperPlus.Core/`) の実装と互換性を維持すること
