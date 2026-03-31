# P1-011: API 凍結 + v1.0.0 安定版リリース

> Phase: 1 (全言語展開)
> マイルストーン: v1.0.0
> 対応要求: FR-100, FR-101, FR-102, FR-103, NFR-100, NFR-101
> 依存チケット: P1-001 ~ P1-010 (Phase 1 全チケット)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

Phase 1 で追加した全機能のフィードバックを反映し、API を確定して v1.0.0 安定版をリリースする。SemVer に基づくバージョン管理を導入し、v1.0.0 以降は後方互換性を保証する。piper_train からの移行パスを提供し、DeprecationWarning による段階的な移行を促す。

### ゴール

- API 確定: `phonemize()` / `phonemize_with_prosody()` / `PiperEncoder` の公開インターフェースが凍結される
- piper_train 互換シムに DeprecationWarning が追加される
- README と API ドキュメントが v1.0.0 品質に整備される
- TTS フレームワーク統合ガイドが提供される
- PyPI に v1.0.0 が publish される

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/pyproject.toml` | バージョンを `1.0.0` に更新 |
| `src/python/g2p/piper_g2p/__init__.py` | `__version__ = "1.0.0"` |
| `src/python/g2p/piper_g2p/_compat.py` | piper_train 互換シム (DeprecationWarning 付き) |
| `src/python/g2p/README.md` | v1.0.0 向け最終整備 |
| `src/python/g2p/docs/integration-guide.md` | TTS フレームワーク統合ガイド |
| `src/python/g2p/CHANGELOG.md` | v0.1.0 → v0.2.0 → v1.0.0 の変更履歴 |

### 実装手順

#### 2.1 API 凍結チェックリスト

以下の公開 API を凍結する (v1.0.0 以降は後方互換性を保証):

**コア API (`piper_g2p`)**:

| API | シグネチャ | 凍結 |
|-----|-----------|------|
| `Phonemizer` ABC | 2 abstract methods | 凍結 |
| `ProsodyInfo` | `dataclass(a1, a2, a3)` | 凍結 |
| `get_phonemizer(lang)` | `str -> Phonemizer` | 凍結 |
| `register_language(code, phonemizer)` | `str, Phonemizer -> None` | 凍結 |
| `available_languages()` | `-> list[str]` | 凍結 |

**言語 Phonemizer (7 言語)**:

| クラス | `phonemize()` | `phonemize_with_prosody()` |
|--------|-------------|--------------------------|
| `JapanesePhonemizer` | 凍結 | 凍結 |
| `EnglishPhonemizer` | 凍結 | 凍結 |
| `ChinesePhonemizer` | 凍結 | 凍結 |
| `KoreanPhonemizer` | 凍結 | 凍結 |
| `SpanishPhonemizer` | 凍結 | 凍結 |
| `FrenchPhonemizer` | 凍結 | 凍結 |
| `PortuguesePhonemizer` | 凍結 | 凍結 |
| `MultilingualPhonemizer` | 凍結 | 凍結 |

**エンコード API (`piper_g2p.encode`)**:

| API | シグネチャ | 凍結 |
|-----|-----------|------|
| `PiperEncoder(phoneme_id_map, pua_table)` | constructor | 凍結 |
| `PiperEncoder.encode(tokens, eos_token)` | `list[str] -> list[int]` | 凍結 |
| `PiperEncoder.encode_with_prosody(tokens, prosody, eos_token)` | `-> (list[int], list[dict\|None])` | 凍結 |
| `get_phoneme_id_map(lang)` | `str -> dict` | 凍結 |
| `FIXED_PUA_MAPPING` | `dict[str, int]` | 凍結 |

**カスタム辞書 (`piper_g2p.custom_dict`)**:

| API | 凍結 |
|-----|------|
| `CustomDictionary(dict_paths, load_defaults)` | 凍結 |
| `CustomDictionary.load_dictionary(path)` | 凍結 |
| `CustomDictionary.apply_to_text(text)` | 凍結 |
| `CustomDictionary.add_word(word, pronunciation, priority)` | 凍結 |
| `CustomDictionary.remove_word(word)` | 凍結 |

#### 2.2 piper_train 互換シム

```python
# src/python/g2p/piper_g2p/_compat.py
"""Compatibility shim for piper_train.phonemize migration."""
import warnings

def emit_deprecation(old_path: str, new_path: str):
    warnings.warn(
        f"'{old_path}' is deprecated and will be removed in piper-g2p v2.0.0. "
        f"Use '{new_path}' instead.",
        DeprecationWarning,
        stacklevel=3,
    )
```

piper_train 側の互換モジュール (別チケット):
```python
# src/python/piper_train/phonemize/base.py (互換版)
from piper_g2p._compat import emit_deprecation
from piper_g2p.base import Phonemizer, ProsodyInfo

emit_deprecation("piper_train.phonemize.base", "piper_g2p.base")
# 従来の API も維持 (get_phoneme_id_map, post_process_ids)
```

#### 2.3 TTS フレームワーク統合ガイド

```markdown
# piper-g2p Integration Guide

## For VITS / VITS2 Users
(eSpeak-ng の置き換え手順)

## For Coqui TTS Users
(phonemizer パッケージの置き換え手順)

## For Custom TTS Pipelines
(PiperEncoder を使わない場合の IPA 直接利用)

## Migration from piper_train.phonemize
(互換シムの利用方法と移行スケジュール)
```

#### 2.4 リリース手順

1. 全テストが pass することを確認
2. CHANGELOG.md を更新
3. `pyproject.toml` の version を `1.0.0` に更新
4. `__init__.py` の `__version__` を `1.0.0` に更新
5. Git タグ `python-g2p-v1.0.0` を作成
6. CI が自動的に PyPI に publish
7. GitHub Release を作成

### API / インターフェース

上記「API 凍結チェックリスト」参照。

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| リリースエージェント | 1 | バージョン更新、CHANGELOG、タグ作成 |
| ドキュメントエージェント | 1 | 統合ガイド作成、README 最終整備 |
| テストエージェント | 1 | 全テスト実行、互換シムのテスト |

---

## 4. テスト計画

### 提供範囲

全 API が凍結された状態で正しく動作すること、互換シムが DeprecationWarning を発行すること。

### Unit テスト

| テストケース | 検証内容 |
|-------------|---------|
| 全言語 phonemize | 7 言語全ての `phonemize()` が動作 |
| 全言語 phonemize_with_prosody | 7 言語全ての `phonemize_with_prosody()` が動作 |
| MultilingualPhonemizer | 複合コードで自動生成・音素化が動作 |
| PiperEncoder.encode | IPA → phoneme_ids 変換が動作 |
| PiperEncoder.encode_with_prosody | prosody 付きエンコードが動作 |
| CustomDictionary | ロード・適用・保存が動作 |
| 互換シム DeprecationWarning | `piper_train.phonemize` からの import で Warning |
| バージョン | `piper_g2p.__version__ == "1.0.0"` |

### E2E テスト

- `uv pip install piper-g2p[all]` → 全言語テスト pass
- `uv pip install piper-g2p` (コアのみ) → コアテスト pass
- README のコード例が全て動作

---

## 5. 懸念事項とレビュー項目

### 懸念事項

- **API 凍結のタイミング**: v1.0.0 リリース後に API 変更が必要になった場合、SemVer に基づき v2.0.0 が必要になる。ユーザーフィードバック収集期間として v0.2.0 での beta 期間を設けるべきか検討。
- **互換シムの範囲**: piper_train 側の互換シムは piper_train リポジトリの変更が必要。piper-g2p パッケージ側で提供できるのは `_compat.py` の DeprecationWarning ヘルパーのみ。
- **PiperEncoder の安定性**: PiperEncoder は Piper TTS の config.json フォーマットに依存しており、config.json のスキーマ変更に追従する必要がある。
- **リリース自動化**: `python-g2p-v*` タグで PyPI publish が自動実行される CI ワークフロー (P0 で整備済み) が正しく動作することを確認する。

### レビュー項目

- [ ] 全公開 API が凍結チェックリストに含まれていること
- [ ] 非公開 API (アンダースコア始まり) が凍結対象外であること
- [ ] DeprecationWarning のメッセージが具体的な移行先を含むこと
- [ ] CHANGELOG に全変更が記載されていること
- [ ] 統合ガイドが少なくとも 2 つの TTS フレームワークをカバーすること
- [ ] バージョン番号が pyproject.toml と __init__.py で一致していること

---

## 6. 一から作り直すとしたら

v1.0.0 リリースまでに beta 期間 (v0.9.x) を設け、早期ユーザーからのフィードバックを反映する。特に `phonemize()` の戻り値型 (`list[str]`) と prosody の構造 (`ProsodyInfo dataclass`) は一度凍結すると変更コストが高いため、beta 期間での検証が重要。また、async 対応 (`async def phonemize()`) の需要を beta 期間で調査する。

---

## 7. 後続タスクへの連絡事項

- Phase 2 (Rust crate): Python API と同一のインターフェースを Rust trait で定義する
- Phase 3 (JS/WASM): npm パッケージの API 設計に v1.0.0 の Python API を参考にする
- piper_train: 互換シムの実装と DeprecationWarning テストを piper_train 側で実施する
- エコシステム: v1.0.0 リリース後、Coqui TTS / StyleTTS 2 等のコミュニティへの周知活動を行う
