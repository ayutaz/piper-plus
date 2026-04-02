# M1-8: テスト・CI 対応

> **マイルストーン**: M1
> **前提チケット**: M1-7
> **後続チケット**: M4
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

M1-7 で旧 `piper_train.phonemize` ディレクトリが削除された後、テストスイートと CI パイプラインを更新し、全テストが `piper_g2p` 経由で正常に pass する状態にする。既存テストの import パス修正、`test_compat.py` の再構成、CI の依存インストールコマンド更新を行う。

## 実装する内容の詳細

### 1. CI ワークフローの更新

**対象ファイル:** `.github/workflows/python-tests.yml`

現在の install コマンド:
```bash
uv pip install --system -e ".[test,train]"
```

変更後:
```bash
uv pip install --system -e ".[test,train]" piper-g2p[all]
```

`piper-g2p[all]` を明示的に追加し、全言語の G2P 依存が CI 環境でインストールされることを保証する。

> **注意:** M1-1 で `pyproject.toml` に `piper-g2p` が追加されている場合は `.[test,train]` に含まれるため、この変更が不要な可能性がある。M1-1 の実装結果を確認すること。

### 2. test_compat.py の再構成

**対象ファイル:** `src/python/g2p/tests/test_compat.py`

現在の実装:
```python
try:
    import piper_train.phonemize  # noqa: F401
    _has_piper_train = True
except ImportError:
    _has_piper_train = False
```

M1-7 後は `piper_train.phonemize` が存在しなくなるため、`_has_piper_train = False` になり全互換テストがスキップされる。

変更方針:
- `piper_train.phonemize` の存在チェックを `piper_train` の存在チェックに変更
- 互換テストの対象を「旧 phonemize と新 g2p の出力一致」から「piper_g2p 単体の出力正当性」に変更
- M0-3 で追加された全言語テスト (JA/EN/ZH/KO/ES/FR/PT/SV) を含めて拡充
- `requires_piper_train` デコレータの条件を再定義

### 3. 既存テストの import 修正

M1-7 の削除により `piper_train.phonemize` を import しているテストが fail する。以下のファイルを調査・修正する:

**`test/` ディレクトリ (旧テスト):**

| ファイル | 参照対象 |
|---------|---------|
| `test/test_multilingual_phonemizer.py` | `piper_train.phonemize.multilingual` |
| `test/test_bilingual_phonemizer.py` | `piper_train.phonemize.bilingual` |
| `test/test_japanese_phonemizer.py` | `piper_train.phonemize.japanese` |
| `test/test_chinese_phonemizer.py` | `piper_train.phonemize.chinese` |
| `test/test_korean_phonemizer.py` | `piper_train.phonemize.korean` |
| `test/test_spanish_phonemizer.py` | `piper_train.phonemize.spanish` |
| `test/test_portuguese_phonemizer.py` | `piper_train.phonemize.portuguese` |
| `test/test_french_phonemizer.py` | `piper_train.phonemize.french` |
| `test/test_multilingual_id_map.py` | `piper_train.phonemize.multilingual_id_map` |
| `test/test_pua_mapping_consistency.py` | `piper_train.phonemize.*` |
| `test/test_non_ja_prosody.py` | `piper_train.phonemize.*` |
| `test/test_morphological_fallback.py` | `piper_train.phonemize.japanese` |

**`src/python/tests/` ディレクトリ:**

| ファイル | 参照対象 |
|---------|---------|
| `src/python/tests/test_phonemize.py` | `piper_train.phonemize.*` |
| `src/python/tests/test_phonemizer_registry.py` | `piper_train.phonemize.registry` |
| `src/python/tests/test_english_phonemizer.py` | `piper_train.phonemize.english` |
| `src/python/tests/test_custom_dict.py` | `piper_train.phonemize.custom_dict` |
| `src/python/tests/test_token_mapper_impl.py` | `piper_train.phonemize.token_mapper` |
| `src/python/tests/test_prosody_extraction.py` | `piper_train.phonemize.japanese` |
| `src/python/tests/test_intersperse_padding.py` | `piper_train.phonemize.*` |
| `src/python/tests/test_swedish_phonemizer.py` | `piper_train.phonemize.swedish` |
| `src/python/tests/test_swedish_m1_1_m1_2.py` | `piper_train.phonemize.swedish` |
| `src/python/tests/test_add_prosody_features.py` | `piper_train.phonemize.*` |

**`src/python_run/tests/` ディレクトリ:**

| ファイル | 参照対象 |
|---------|---------|
| `src/python_run/tests/test_multilingual_integration.py` | `piper_train.phonemize.*` |
| `src/python_run/tests/test_config_fallback.py` | `piper_train.phonemize.*` (要確認) |

各テストについて:
- import パスを `piper_train.phonemize.xxx` から `piper_g2p.xxx` に書き換え
- API の差異がある場合はテストコードを修正
- piper_g2p に対応する機能がない場合はテストを削除または skip に変更

### 4. 全テストスイートの pass 確認

以下のテストカテゴリすべてが pass することを確認:

| カテゴリ | パス | マーカー |
|---------|------|---------|
| Unit テスト | `src/python/tests/` | - |
| G2P テスト | `src/python/g2p/tests/` | - |
| 旧テスト | `test/` | - |
| ランタイムテスト | `src/python_run/tests/` | - |
| 学習テスト | `src/python/tests/` | `@pytest.mark.training` |
| 推論テスト | `src/python/tests/` | `@pytest.mark.inference` |
| ベンチマーク | `src/python/tests/` | `@pytest.mark.benchmark` |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| CI 専門担当 | 1 | CI ワークフロー更新、マトリクス全エントリの pass 確認 |
| テスト担当 | 1 | テストファイルの import 修正、test_compat.py 再構成 |

## 提供範囲とテスト

### 提供範囲

- `.github/workflows/python-tests.yml` の更新
- `src/python/g2p/tests/test_compat.py` の再構成
- `test/` および `src/python/tests/` 配下のテストファイルの import 修正
- `src/python_run/tests/` 配下のテストファイルの import 修正 (該当がある場合)

### テスト項目

- 全既存テストが pass すること
- CI マトリクス全エントリ (3 OS x Python 3.11) で pass すること
- 旧 `piper_train.phonemize` への import がテストコード内に残っていないこと (test_compat.py の skip 条件を除く)

**注意**: 更新が必要なテストファイルのリストは実装前に以下のコマンドで確定すること:
```bash
grep -rn "from piper_train.phonemize\|from.*\.phonemize\." src/python/tests/ src/python_run/tests/
```
上記の結果に基づき、import パスを piper_g2p に変更する。調査時点のリストはあくまで参考値である。

CI ワークフローファイル (`.github/workflows/python-tests.yml`) の構造は実装時に確認すること。

### Unit テスト

- 全言語の phonemizer テスト (8 言語) が piper_g2p 経由で pass すること
- ID マップテストが piper_g2p 経由で pass すること
- test_compat.py の互換テストが正しく動作すること (skip ではなく実行されること)

### E2E テスト

- CI マトリクス全エントリ:
  - ubuntu-22.04 / Python 3.11
  - windows-latest / Python 3.11
  - macos-latest / Python 3.11
- 各エントリで unit, training, benchmark, inference の全マーカーが pass すること

## 懸念事項とレビュー項目

### 懸念事項

1. **test_compat.py の `@requires_piper_train` デコレータ**: M1-7 後は `piper_train.phonemize` が存在しないため、旧方式の互換テストは実行不可能になる。テストの目的を「旧実装との比較」から「piper_g2p の出力正当性確認」に変更する必要がある。変更後のテストが十分なカバレッジを持つか確認すること
2. **テスト数の増減**: import 修正に伴いテストが削除される場合、テストカバレッジが低下しないよう代替テストを追加する
3. **OS 固有の問題**: Windows での pyopenjtalk-plus のインストール、macOS での g2pk2 の依存解決など、OS 固有の問題が piper-g2p[all] で顕在化する可能性がある
4. **テストの二重管理**: `test/` (旧) と `src/python/tests/` (新) に同じ言語のテストが存在する。この機会に統合するか、最低限 import パスの一貫性を確保する

### レビュー項目

1. CI ログで全マトリクスエントリの pass を確認
2. `grep -r "from piper_train.phonemize" test/ src/python/tests/ src/python_run/tests/ --include="*.py"` の結果が test_compat.py の skip 条件のみであること
3. test_compat.py の新しいテスト構成が全言語をカバーしていること
4. テスト数が M1-7 前と同等以上であること

## 一から作り直すとしたら

テストコードを最初から `piper_g2p` の公開 API のみに依存するよう設計する。`piper_train.phonemize` の内部実装に直接依存するテストは作成せず、G2P 機能のテストは piper_g2p パッケージ側に集約する。piper_train 側のテストは学習パイプラインの統合テスト (G2P 出力 -> phoneme_ids -> モデル入力) に限定する。

## 後続タスクへの連絡事項

- M4 (検証マイルストーン): 本チケット完了をもって M1 (Python 移行) が完了となる。M4 では全体的な回帰テストと CLAUDE.md の更新を行う
- テスト修正により API の不整合が発見された場合は、piper_g2p 側の修正が必要になる可能性がある。その場合は M0 に追加チケットを起票する
- CI で `piper-g2p[all]` のインストールに時間がかかる場合は、キャッシュ戦略の検討を M4 で行う
