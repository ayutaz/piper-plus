# [P0-002] パッケージ構造作成

> Phase: 0 (MVP)
> マイルストーン: v0.1.0 -- Python MVP (JA+EN)
> 対応要求: FR-006
> 依存チケット: P0-001
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
`piper-g2p` Python パッケージのディレクトリ構造と `pyproject.toml` を作成する。後続チケット (P0-003 ~ P0-009) の土台となるパッケージスケルトンを確立する。

### ゴール
- `src/python/g2p/` にパッケージディレクトリが存在する
- `uv build` が成功し、wheel が生成される
- `uv pip install ./src/python/g2p` でインストールできる
- `python -c "import piper_g2p; print(piper_g2p.__version__)"` が動作する
- `uv pip install ./src/python/g2p[ja,en]` で optional deps がインストールされる

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/pyproject.toml` | パッケージメタデータ、依存定義 |
| `src/python/g2p/piper_g2p/__init__.py` | パブリック API の re-export |
| `src/python/g2p/piper_g2p/base.py` | (P0-003 で実装、ここでは空ファイル) |
| `src/python/g2p/piper_g2p/registry.py` | (P0-003 で実装、ここでは空ファイル) |
| `src/python/g2p/piper_g2p/japanese.py` | (P0-004 で実装、ここでは空ファイル) |
| `src/python/g2p/piper_g2p/english.py` | (P0-005 で実装、ここでは空ファイル) |
| `src/python/g2p/piper_g2p/encode/__init__.py` | (P0-006 で実装、ここでは空ファイル) |
| `src/python/g2p/piper_g2p/py.typed` | PEP 561 型情報マーカー |
| `src/python/g2p/LICENSE` | MIT ライセンス |
| `src/python/g2p/README.md` | PyPI 用 README (最小限) |

### 実装手順

1. **ディレクトリ構造の作成**
   ```
   src/python/g2p/
   ├── pyproject.toml
   ├── LICENSE
   ├── README.md
   └── piper_g2p/
       ├── __init__.py
       ├── py.typed
       ├── base.py
       ├── registry.py
       ├── japanese.py
       ├── english.py
       └── encode/
           └── __init__.py
   ```

2. **pyproject.toml の作成**
   ```toml
   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"

   [project]
   name = "piper-g2p"
   version = "0.1.0"
   description = "Multilingual G2P (Grapheme-to-Phoneme) for TTS — eSpeak-ng free, MIT licensed"
   requires-python = ">=3.11"
   license = "MIT"
   authors = [
       {name = "piper-plus contributors"},
   ]
   keywords = ["g2p", "grapheme-to-phoneme", "tts", "phonemizer", "ipa"]
   classifiers = [
       "Development Status :: 3 - Alpha",
       "Intended Audience :: Developers",
       "Intended Audience :: Science/Research",
       "License :: OSI Approved :: MIT License",
       "Programming Language :: Python :: 3",
       "Programming Language :: Python :: 3.11",
       "Programming Language :: Python :: 3.12",
       "Programming Language :: Python :: 3.13",
       "Topic :: Multimedia :: Sound/Audio :: Speech",
       "Topic :: Scientific/Engineering :: Artificial Intelligence",
       "Typing :: Typed",
   ]
   readme = "README.md"

   [project.optional-dependencies]
   ja = ["pyopenjtalk-plus"]
   en = ["g2p-en>=2.1.0"]
   all = ["pyopenjtalk-plus", "g2p-en>=2.1.0"]

   [project.urls]
   Homepage = "https://github.com/yousan/piper-plus"
   Repository = "https://github.com/yousan/piper-plus"
   Issues = "https://github.com/yousan/piper-plus/issues"

   [tool.hatch.build.targets.wheel]
   packages = ["piper_g2p"]
   ```

3. **`__init__.py` の作成**
   ```python
   """piper-g2p: Multilingual G2P for TTS."""

   __version__ = "0.1.0"

   from .base import Phonemizer, ProsodyInfo
   from .registry import available_languages, get_phonemizer, register_language

   __all__ = [
       "__version__",
       "Phonemizer",
       "ProsodyInfo",
       "get_phonemizer",
       "register_language",
       "available_languages",
   ]
   ```

4. **ビルド確認**
   ```bash
   cd src/python/g2p
   uv build
   uv pip install .
   python -c "import piper_g2p; print(piper_g2p.__version__)"
   ```

### API / インターフェース

```python
import piper_g2p

piper_g2p.__version__  # "0.1.0"
```

(コア API は P0-003 以降で実装)

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| パッケージ設計 | 1 | pyproject.toml 作成、ディレクトリ構造設計 |
| ビルド検証 | 1 | uv build / install の動作確認 |

---

## 4. テスト計画

### 提供範囲
ビルドとインストールの成功確認のみ。

### Unit テスト
```python
def test_version():
    import piper_g2p
    assert piper_g2p.__version__ == "0.1.0"

def test_public_api_importable():
    from piper_g2p import Phonemizer, ProsodyInfo
    from piper_g2p import get_phonemizer, register_language, available_languages
```

### E2E テスト
```bash
# コアのみインストール
uv pip install ./src/python/g2p
python -c "from piper_g2p import available_languages; print(available_languages())"
# -> [] (JA/EN 依存未インストールのため空)

# JA+EN 付きインストール
uv pip install "./src/python/g2p[ja,en]"
python -c "from piper_g2p import available_languages; print(available_languages())"
# -> ["ja", "en"]
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **ビルドバックエンド選択**: `hatchling` は設定がシンプルだが、`setuptools` + `pyproject.toml` のほうが CI 環境での互換性が高い場合がある。uv は hatchling をネイティブサポートしているため問題ないと判断。
- **pyopenjtalk-plus vs pyopenjtalk**: `pyopenjtalk-plus` は Windows 互換の fork だが、PyPI での availability を事前確認する必要がある。フォールバック記述 (`pyopenjtalk-plus; pyopenjtalk`) は pyproject.toml の optional-dependencies では直接記述できないため、ランタイムの import fallback で対応する (P0-004 の責務)。

### レビュー項目
- `requires-python = ">=3.11"` が適切か (3.10 サポートの要否)
- `piper_g2p` パッケージ名のインポートが `piper-g2p` PyPI 名と整合しているか
- `py.typed` マーカーが含まれていること (PEP 561)
- ライセンスファイルの内容が正しいこと

---

## 6. 一から作り直すとしたら

- **src layout 採用**: `src/piper_g2p/` のような src layout にすると、開発時の implicit import 問題を避けられる。ただし piper-plus リポジトリ内の `src/python/g2p/piper_g2p/` は既に十分にネストされており、src layout の追加ネストはかえって混乱を招く。
- **`piper_g2p` ではなく `g2p` にインポート名を短縮する案**: 汎用名すぎて名前衝突のリスクが高い。`piper_g2p` が適切。
- **モノレポツール (uv workspace)**: piper-plus の `src/python/piper_train/` と `src/python/g2p/` を uv workspace で管理すると、ローカル開発時の依存解決がスムーズになる。Phase 0 では独立パッケージとして扱い、workspace 化は P0-007 (互換シム) で検討する。

---

## 7. 後続タスクへの連絡事項

- **P0-003**: `base.py` と `registry.py` のスケルトンファイルがこのチケットで作成されるが、中身は空。P0-003 で実装を追加すること。
- **P0-004, P0-005**: `japanese.py`, `english.py` のスケルトンが用意されるが、同様に空。
- **P0-006**: `encode/__init__.py` のスケルトンが用意される。
- **P0-009**: `pyproject.toml` に lint / test の設定セクション (`[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`) を追加する可能性がある。P0-002 の段階ではビルドに必要な最小限の設定のみとし、ツール設定は P0-009 で追加する。
