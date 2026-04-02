# M1-7: 旧 phonemize ディレクトリ削除

> **マイルストーン**: M1
> **前提チケット**: M1-2, M1-3, M1-4, M1-5, M1-6
> **後続チケット**: M1-8, M4-3
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

`src/python/piper_train/phonemize/` ディレクトリ全体 (24 ファイル、約 4,000 行) を削除する。M1-2 から M1-6 で全ての内部参照が `piper_plus_g2p` に移行済みであることが前提条件。この削除により、G2P ロジックの重複が解消され、piper_plus_g2p が唯一の G2P 実装となる。

## 実装する内容の詳細

### 前提条件 (チェックリスト)

以下が全て完了し、全テストが pass していること:

- [ ] M1-2: `__main__.py`, `export_onnx.py`, `infer_onnx.py` 等の drop-in import 置換完了
- [ ] M1-3: `vits/lightning.py` の import 移行完了
- [ ] M1-4: `vits/dataset.py` の import 移行完了
- [ ] M1-5: `tools/` スクリプト 3 本の import 移行完了
- [ ] M1-6: `inference_utils.py` (dead code) 削除完了

### 削除対象ファイル一覧 (24 ファイル)

**基盤モジュール (5 ファイル):**

| ファイル | 行数 (概算) | 内容 |
|---------|-----------|------|
| `__init__.py` | - | パッケージ初期化 |
| `base.py` | ~100 | Phonemizer 抽象基底クラス |
| `registry.py` | ~50 | 言語レジストリ (`get_phonemizer()`) |
| `token_mapper.py` | ~150 | PUA トークンマッピング |
| `custom_dict.py` | ~100 | カスタム辞書処理 |

**言語別 Phonemizer (8 ファイル):**

| ファイル | 行数 (概算) | 言語 |
|---------|-----------|------|
| `japanese.py` | ~500 | 日本語 (pyopenjtalk 依存) |
| `english.py` | ~200 | 英語 (g2p-en 依存) |
| `chinese.py` | ~300 | 中国語 (pypinyin 依存) |
| `korean.py` | ~200 | 韓国語 (g2pk2 依存) |
| `spanish.py` | ~150 | スペイン語 (規則ベース) |
| `portuguese.py` | ~150 | ポルトガル語 (規則ベース) |
| `french.py` | ~150 | フランス語 (規則ベース) |
| `swedish.py` | ~150 | スウェーデン語 (規則ベース) |

**ID マップ (9 ファイル):**

| ファイル | 行数 (概算) | 対象 |
|---------|-----------|------|
| `jp_id_map.py` | ~200 | 日本語 ID マップ |
| `zh_id_map.py` | ~100 | 中国語 ID マップ |
| `ko_id_map.py` | ~100 | 韓国語 ID マップ |
| `es_id_map.py` | ~100 | スペイン語 ID マップ |
| `pt_id_map.py` | ~100 | ポルトガル語 ID マップ |
| `fr_id_map.py` | ~100 | フランス語 ID マップ |
| `sv_id_map.py` | ~100 | スウェーデン語 ID マップ |
| `bilingual_id_map.py` | ~100 | バイリンガル ID マップ |
| `multilingual_id_map.py` | ~150 | マルチリンガル ID マップ |

**マルチリンガル/バイリンガル (2 ファイル):**

| ファイル | 行数 (概算) | 内容 |
|---------|-----------|------|
| `multilingual.py` | ~300 | マルチリンガル Phonemizer |
| `bilingual.py` | ~200 | バイリンガル Phonemizer |

### 実行手順

1. **削除前の最終 grep 確認**:
   ```bash
   grep -r "from piper_train.phonemize" src/python/ --include="*.py" | grep -v "phonemize/"
   grep -r "import piper_train.phonemize" src/python/ --include="*.py" | grep -v "phonemize/"
   ```
   上記コマンドの出力がゼロ行であることを確認

2. **ディレクトリ削除**:
   ```bash
   git rm -r src/python/piper_train/phonemize/
   ```

3. **削除後のテスト実行**:
   ```bash
   uv run python -c "import piper_train"
   uv run pytest src/python/tests/ -x
   ```

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装担当 | 1 | 最終 grep 確認、ディレクトリ削除、ローカルテスト実行 |
| CI 検証担当 | 1 | 全 CI マトリクス (3 OS) の pass 確認 |

## 提供範囲とテスト

### 提供範囲

- `src/python/piper_train/phonemize/` ディレクトリの完全削除 (24 ファイル)

### テスト項目

- 削除後にリポジトリ全体で `piper_train.phonemize` への import が存在しないこと
- 既存の全テストスイートが pass すること
- piper_train パッケージの import が正常に動作すること

**削除前チェックリスト:**
1. `grep -rn "from.*phonemize\|import.*phonemize" src/python/piper_train/` で残存 import がゼロであること
2. `uv run pytest src/python/tests/ -x` が全て PASS
3. `uv run pytest src/python/g2p/tests/ -x` が全て PASS
4. `uv run python -c "import piper_train"` がエラーなしで完了

### Unit テスト

- `grep -r "from piper_train.phonemize" src/ test/ --include="*.py"` の出力がゼロ行であること
- `grep -r "import piper_train.phonemize" src/ test/ --include="*.py"` の出力がゼロ行であること
- `uv run python -c "import piper_train"` が成功すること

### E2E テスト

- CI マトリクス全エントリ (ubuntu-22.04, windows-latest, macos-latest) で全テストが pass すること
- `test/` ディレクトリ配下の phonemizer テスト (31 ファイル) が `piper_plus_g2p` 経由で動作すること

## 懸念事項とレビュー項目

### 懸念事項

1. **不可逆操作**: ディレクトリ削除は git 履歴があるため復元可能だが、心理的には大きな変更。M1-2 から M1-6 の完了を厳密に確認してから実行すること
2. **リポジトリ外の依存者**: piper_train.phonemize を直接 import している外部プロジェクトやスクリプトが存在する可能性がある。CLAUDE.md の「重要なファイルパス」セクションに旧パスが多数記載されており、M4-3 で更新が必要
3. **test/ ディレクトリのテスト**: `test/test_multilingual_phonemizer.py`、`test/test_bilingual_phonemizer.py` 等が `piper_train.phonemize` を直接 import している可能性がある。M1-8 で対応するが、本チケット実行時に一時的にテストが fail する可能性がある
4. **`test_compat.py` の `import piper_train.phonemize`**: `src/python/g2p/tests/test_compat.py` の L17 で `import piper_train.phonemize` を使用して piper_train の存在確認をしている。削除後は `_has_piper_train = False` になり、互換テストがスキップされる。M1-8 で対応方針を決定する
5. **`vits/dataset.py` の import 確認**: `vits/dataset.py` が `piper_train.phonemize` を import している場合は、M1-2 または M1-4 のスコープに追加する必要がある。削除前に `grep -rn "from.*phonemize" src/python/piper_train/vits/` で確認すること。

### レビュー項目

1. 削除前の grep 結果がゼロ行であることの確認 (スクリーンショットまたはログ)
2. `git rm -r` で削除されたファイル数が 24 であることの確認
3. CI の全マトリクスエントリが pass していることの確認
4. `src/python/g2p/tests/test_compat.py` の動作影響の確認

## 一から作り直すとしたら

piper_plus_g2p を設計する時点で、piper_train.phonemize は薄いラッパー (re-export のみ) にリファクタリングし、段階的に参照を移行する戦略を取る。これにより、最終削除がリスクの低い機械的作業になる。

## 後続タスクへの連絡事項

- M1-8 (テスト・CI 対応): 本チケットの削除により fail するテストがあれば M1-8 で修正すること。特に `test/` ディレクトリ配下の phonemizer テストと `test_compat.py` の `requires_piper_train` デコレータの動作を確認すること
- M4-3 (CLAUDE.md 更新): 「重要なファイルパス」セクションの phonemize 関連パスを piper_plus_g2p のパスに更新すること
- pyproject.toml から旧 G2P 依存 (pyopenjtalk-plus, g2p-en, pypinyin, g2pk2) の直接参照を削除するかどうかは M1-1 の後続判断に委ねる
