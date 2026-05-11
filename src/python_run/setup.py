#!/usr/bin/env python3
# Issue #418: メタデータの大部分 (name / description / authors / classifiers /
# entry_points / extras_require / package_data / urls) は pyproject.toml に
# 移行済み。 setup.py が残している責務は **pyproject の dynamic = ["version",
# "dependencies"] の実解決のみ**:
#   - リポジトリルートの VERSION ファイル (パッケージ外、 setuptools の
#     `_assert_local` で `[tool.setuptools.dynamic]` の file 参照では弾かれる)
#   - requirements.txt の解釈 (空行 / コメント行のフィルタリング)
from pathlib import Path

from setuptools import setup


this_dir = Path(__file__).parent

# VERSION ファイル: リポジトリルート canonical
version_file = this_dir.parent.parent / "VERSION"
if version_file.is_file():
    version = version_file.read_text(encoding="utf-8").strip()
else:
    # フォールバック: src/python/piper_train/VERSION
    version_file_alt = this_dir.parent / "python" / "piper_train" / "VERSION"
    if version_file_alt.is_file():
        version = version_file_alt.read_text(encoding="utf-8").strip()
    else:
        version = "0.0.0"

# requirements.txt: コメント / 空行を除去して install_requires に流す
requirements: list[str] = []
requirements_path = this_dir / "requirements.txt"
if requirements_path.is_file():
    with open(requirements_path, encoding="utf-8") as requirements_file:
        requirements = [
            line.strip()
            for line in requirements_file
            if line.strip() and not line.strip().startswith("#")
        ]

setup(
    version=version,
    install_requires=requirements,
)
