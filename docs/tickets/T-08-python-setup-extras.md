# T-08: Python setup.py extras_require 追加

**Milestone:** feat: Hardware EP 自動選択 (#382) — Milestone #16
**依存タスク:** なし（T-01 とほぼ並行実施可能。T-02/T-03 の完了は不要）
**後続タスク:** なし（独立したドキュメント/パッケージ変更）

---

## 1. タスク目的とゴール

`src/python_run/setup.py` の `extras_require` には現在 `"gpu"` グループ（`onnxruntime-gpu`）と `"http"` グループのみが定義されている。DirectML と OpenVINO の EP を使用するには別パッケージ（`onnxruntime-directml`, `onnxruntime-openvino`）が必要だが、`pip install piper-plus[directml]` のような形でインストールできる方法がない。

このタスクの目的は、ユーザーが目的の EP を明示的に選んでインストールできるよう、`extras_require` に `"directml"` と `"openvino"` グループを追加することである。CoreML は `onnxruntime`（標準パッケージ）に含まれるため追加不要。

**完了の定義（Done 基準）:**
- `src/python_run/setup.py` の `extras_require` に `"directml"` と `"openvino"` グループが追加されている
- 既存の `"gpu"` と `"http"` グループが変更されていない
- `python setup.py --version` または `pip install -e .` が正常に完了すること

---

## 2. 実装する内容の詳細

### 変更ファイル

`src/python_run/setup.py` の `extras_require` 辞書（65〜71 行目付近）を以下のように変更する。

**変更前:**

```python
    extras_require={
        "gpu": ["onnxruntime-gpu>=1.11.0,<2"],
        "http": [
            "fastapi>=0.110,<1",
            "uvicorn[standard]>=0.27,<1",
        ],
    },
```

**変更後:**

```python
    extras_require={
        "gpu": ["onnxruntime-gpu>=1.11.0,<2"],
        "directml": ["onnxruntime-directml"],
        "openvino": ["onnxruntime-openvino"],
        "http": [
            "fastapi>=0.110,<1",
            "uvicorn[standard]>=0.27,<1",
        ],
    },
```

### 追加するグループの説明

| グループ | パッケージ | 対象環境 | 備考 |
|---|---|---|---|
| `gpu` | `onnxruntime-gpu>=1.11.0,<2` | NVIDIA GPU / TensorRT | 既存 |
| `directml` | `onnxruntime-directml` | Windows DirectML | 新規追加 |
| `openvino` | `onnxruntime-openvino` | Intel CPU (OpenVINO) | 新規追加 |
| `http` | `fastapi`, `uvicorn` | HTTP サーバー | 既存 |

`onnxruntime-directml` と `onnxruntime-openvino` はバージョン制約を付けていない。これは PyPI の最新版に追随させるためで、`onnxruntime-gpu` との不整合（同一環境に複数の ORT パッケージが混在）を防ぐのはユーザーの責任とする。

### インストール方法（ユーザー向け）

```bash
# DirectML (Windows)
pip install piper-plus[directml]

# OpenVINO (Intel CPU)
pip install piper-plus[openvino]

# CUDA (NVIDIA GPU)
pip install piper-plus[gpu]

# CoreML は標準インストールで macOS 上で自動有効
pip install piper-plus
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|---|---|---|
| Implementation Agent | 1 | `setup.py` の `extras_require` に 2 行追加 |
| Review Agent | 1 | バージョン制約の妥当性、既存グループへの影響がないか確認 |
| QA Agent | 0 | 変更が 2 行追加のみのため不要 |

変更量は極めて小さく（2 行追加）、1 エージェントで完結する。

---

## 4. 提供範囲とテスト項目

### 提供範囲（スコープ）

- `src/python_run/setup.py` の `extras_require` に `"directml"` と `"openvino"` グループを追加
- `src/python_run/pyproject.toml` については本タスクのスコープ外（設計仕様書 Section 4 は `setup.py` を指定しているため）

### Unit テスト

setup.py の変更は通常の単体テスト対象外だが、以下で正常動作を確認する:

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus/src/python_run
python setup.py --version
```

Expected: バージョン番号が正常に出力される（例: `1.12.0`）。

また、`extras_require` の内容を確認する:

```bash
python -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('setup_check', 'setup.py')
# setup() をモックして extras_require を取得
from unittest.mock import patch, MagicMock
captured = {}
def mock_setup(**kwargs):
    captured.update(kwargs)
with patch('setuptools.setup', side_effect=mock_setup):
    try:
        import runpy
        runpy.run_path('setup.py')
    except SystemExit:
        pass
    except Exception:
        pass
extras = captured.get('extras_require', {})
print('directml' in extras, 'openvino' in extras, 'gpu' in extras, 'http' in extras)
"
```

Expected: `True True True True`

### E2E テスト

実際に DirectML / OpenVINO をインストールして動作確認するには対応 OS/ハードウェアが必要なため、CI の smoke test マトリクス（設計仕様書 Section 7）で実施する。本タスクのスコープ外。

---

## 5. 実装に関する懸念事項とレビュー項目

### 懸念事項

1. **複数 ORT パッケージの共存問題**: `onnxruntime`, `onnxruntime-gpu`, `onnxruntime-directml` を同一環境に同時インストールすると競合する。PyPI パッケージの命名上、これらは別パッケージとして扱われるため pip が警告を出さない。README またはインストールガイドに「一度に 1 つの ORT パッケージのみインストール」と明記することを推奨する（本タスクのスコープ外）。

2. **`onnxruntime-directml` のバージョン制約なし**: `onnxruntime-gpu` には `>=1.11.0,<2` の制約があるが、`directml` と `openvino` にはない。将来の大バージョンアップで非互換が生じる可能性がある。リリース時に制約を見直すことを推奨する。

3. **`pyproject.toml` との同期**: `src/python_run/` ディレクトリに `pyproject.toml` が存在する場合、`optional-dependencies` との二重管理になる可能性がある。T-08 の変更後に `pyproject.toml` との一貫性を確認すること（設計仕様書 Section 4 では `pyproject.toml` の `[project.optional-dependencies]` も言及しているため）。

4. **`onnxruntime-openvino` の Python バージョン対応**: `onnxruntime-openvino` は Python 3.12 未対応のバージョンが存在する場合がある。`python_requires=">=3.11"` のままで問題ないか確認が必要。

### レビューチェックリスト

- [ ] `"directml": ["onnxruntime-directml"]` のキー名が設計仕様書 Section 4 の `[project.optional-dependencies]` と一致しているか
- [ ] `"openvino": ["onnxruntime-openvino"]` が正しいパッケージ名であるか（PyPI で確認）
- [ ] 既存の `"gpu"` グループ（`onnxruntime-gpu>=1.11.0,<2`）が変更されていないか
- [ ] 既存の `"http"` グループが変更されていないか
- [ ] `python setup.py --version` が正常終了するか
- [ ] `pyproject.toml` が存在する場合に `optional-dependencies` との整合性が取れているか

---

## 6. 一から作り直すとしたら（Green Field Design）

### 設計思想

パッケージの optional dependencies は「インストール後に使う機能を有効にする」という目的に特化すべき。ORT パッケージの選択は「どのハードウェア EP を使うか」というランタイム選択であり、これをパッケージグループとしてユーザーに公開するのは正しい設計である。Green Field では、相互排他的なグループ（gpu/directml/coreml/openvino は一度に 1 つ）を `pip` が適切にハンドリングできる形式で定義することが理想。

### アーキテクチャ

```toml
# pyproject.toml (モダンな Python パッケージング)
[project.optional-dependencies]
# ハードウェア EP グループ（相互排他的）
gpu      = ["onnxruntime-gpu>=1.17,<2"]
directml = ["onnxruntime-directml>=1.17"]
openvino = ["onnxruntime-openvino>=1.17"]
# CoreML は onnxruntime に含まれるため追加不要（macOS で自動有効）

# 機能グループ（追加インストール可能）
http = ["fastapi>=0.110,<1", "uvicorn[standard]>=0.27,<1"]

# ドキュメント用のメタグループ（相互排他の注記をコメントで記述）
# Note: gpu/directml/openvino は相互排他。同一環境に複数インストール不可。
```

`setup.py` ではなく `pyproject.toml` への一本化（`setup.py` の廃止）が現代的な Python パッケージングのベストプラクティスであり、Green Field ではこちらを採用する。

### 実装アプローチ

1. `setup.py` を廃止して `pyproject.toml` に一本化
2. Hatch または Poetry でビルドバックエンドを管理
3. ORT パッケージの相互排他をドキュメントで明示（Python 標準パッケージングには `Conflicts` メタデータは存在しない。PEP 685 は extra 名の正規化を定めるもので Conflicts とは無関係。相互排他の実行時検証は `pip check` に委ねる）
4. CI で `pip install piper-plus[directml]` → `pip check` による競合検証を追加

### 現行実装との主な差異

| 観点 | 現行 | 理想形 |
|---|---|---|
| パッケージ定義 | `setup.py` + 可能性として `pyproject.toml` の二重管理 | `pyproject.toml` 単一管理 |
| バージョン制約 | gpu のみ制約あり、他はなし | 全グループに最低バージョン制約 |
| 相互排他表現 | なし（ユーザーが注意する必要あり） | `Conflicts` メタデータで宣言 |
| CoreML の記述 | extras に未記載（暗黙） | コメントで macOS 自動有効を明示 |

---

## 7. 後続タスクへの引き継ぎ事項

**完了した変更:**
- `src/python_run/setup.py` の `extras_require` に `"directml"` と `"openvino"` グループが追加された

**後続タスク担当者への注意点:**

1. **T-08 は独立したタスク**: Python ランタイムの EP 実装（T-02, T-03）とは独立しており、順序依存がない。T-02/T-03 が完了していなくても T-08 は実施できる。

2. **ドキュメント更新との連携**: T-09（ort-versions.md 更新）では EP の対応状況を記述するが、T-08 の `extras_require` グループ名（`gpu`, `directml`, `openvino`）が T-09 で参照される場合がある。T-09 の作業時に `pip install piper-plus[directml]` のようなインストールコマンドを記載する際は T-08 の変更内容と一致させること。

3. **`pyproject.toml` の確認**: `src/python_run/pyproject.toml` が存在する場合、`[project.optional-dependencies]` との二重管理になる可能性がある。設計仕様書 Section 4 では `pyproject.toml` への変更も言及されているため、T-08 完了後に `pyproject.toml` との整合性を確認することを推奨する（本タスクのスコープ外だが、次の担当者が意識すべき事項）。
