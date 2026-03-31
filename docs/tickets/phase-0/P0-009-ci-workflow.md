# [P0-009] CI ワークフロー

> Phase: 0 (MVP)
> マイルストーン: v0.1.0 -- Python MVP (JA+EN)
> 対応要求: NFR-004
> 依存チケット: P0-002, P0-008
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
`piper-g2p` Python パッケージの品質を PR ごとに自動検証する GitHub Actions ワークフローを提供する。lint、型チェック、テスト、カバレッジを 3 OS x 2 Python で実行し、タグ push 時に PyPI への自動 publish を行う。

### ゴール
- `.github/workflows/g2p-python-ci.yml` が `src/python/g2p/**` の変更で起動する
- テストマトリクス: 3 OS (ubuntu-latest, macos-latest, windows-latest) x 2 Python (3.11, 3.13)
- lint: `ruff check` + `ruff format --check` が pass する
- 型チェック: `mypy --ignore-missing-imports` が pass する
- テスト: `pytest` + カバレッジ 90%+ が pass する
- タグ `python-g2p-v*` で PyPI publish ジョブが起動する
- uv ベース (`astral-sh/setup-uv@v6`)

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `.github/workflows/g2p-python-ci.yml` | CI ワークフロー定義 |
| `src/python/g2p/pyproject.toml` | `[tool.ruff]`, `[tool.mypy]` セクション追加 |

### 実装手順

1. **ワークフロー定義の作成**

   ```yaml
   # .github/workflows/g2p-python-ci.yml
   name: G2P Python CI

   on:
     push:
       branches: [dev, main]
       paths:
         - 'src/python/g2p/**'
         - '.github/workflows/g2p-python-ci.yml'
       tags:
         - 'python-g2p-v*'
     pull_request:
       paths:
         - 'src/python/g2p/**'
         - '.github/workflows/g2p-python-ci.yml'

   jobs:
     lint:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: astral-sh/setup-uv@v6
           with:
             python-version: "3.13"
         - name: Install dependencies
           run: |
             cd src/python/g2p
             uv sync --extra dev
         - name: Ruff check
           run: |
             cd src/python/g2p
             uv run ruff check piper_g2p/ tests/
         - name: Ruff format
           run: |
             cd src/python/g2p
             uv run ruff format --check piper_g2p/ tests/
         - name: Mypy
           run: |
             cd src/python/g2p
             uv run mypy --ignore-missing-imports piper_g2p/

     test:
       runs-on: ${{ matrix.os }}
       strategy:
         fail-fast: false
         matrix:
           os: [ubuntu-latest, macos-latest, windows-latest]
           python-version: ["3.11", "3.13"]
       steps:
         - uses: actions/checkout@v4
         - uses: astral-sh/setup-uv@v6
           with:
             python-version: ${{ matrix.python-version }}
         - name: Install dependencies
           run: |
             cd src/python/g2p
             uv sync --extra all --extra dev
         - name: Run tests
           run: |
             cd src/python/g2p
             uv run pytest --cov=piper_g2p --cov-report=term-missing --cov-fail-under=90 -v
         - name: Upload coverage
           if: matrix.os == 'ubuntu-latest' && matrix.python-version == '3.13'
           uses: actions/upload-artifact@v4
           with:
             name: coverage-report
             path: src/python/g2p/htmlcov/

     build:
       runs-on: ubuntu-latest
       needs: [lint, test]
       steps:
         - uses: actions/checkout@v4
         - uses: astral-sh/setup-uv@v6
           with:
             python-version: "3.13"
         - name: Build package
           run: |
             cd src/python/g2p
             uv build
         - name: Verify wheel
           run: |
             cd src/python/g2p
             ls -la dist/
             uv pip install dist/*.whl
             python -c "import piper_g2p; print(piper_g2p.__version__)"

     publish:
       if: startsWith(github.ref, 'refs/tags/python-g2p-v')
       runs-on: ubuntu-latest
       needs: [build]
       environment: pypi
       permissions:
         id-token: write
       steps:
         - uses: actions/checkout@v4
         - uses: astral-sh/setup-uv@v6
           with:
             python-version: "3.13"
         - name: Build package
           run: |
             cd src/python/g2p
             uv build
         - name: Publish to PyPI
           run: |
             cd src/python/g2p
             uv publish
           env:
             UV_PUBLISH_TOKEN: ${{ secrets.PYPI_TOKEN }}
   ```

2. **pyproject.toml にツール設定追加**

   ```toml
   [tool.ruff]
   target-version = "py311"
   line-length = 88

   [tool.ruff.lint]
   select = ["E", "F", "W", "I", "UP", "B", "SIM", "PLC", "PLE", "PLW"]

   [tool.mypy]
   python_version = "3.11"
   ignore_missing_imports = true
   warn_return_any = true
   warn_unused_configs = true

   [tool.pytest.ini_options]
   testpaths = ["tests"]
   ```

3. **PyPI publish 設定**

   - GitHub repository settings -> Environments -> `pypi` を作成
   - `PYPI_TOKEN` シークレットを設定 (Trusted Publisher 方式の場合は `id-token: write` のみ)

### API / インターフェース

なし (CI 設定のみ)。

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| CI 設計 | 1 | ワークフロー定義、マトリクス設計 |
| リリース設定 | 1 | PyPI publish ジョブ、シークレット設定 |

---

## 4. テスト計画

### 提供範囲
CI ワークフロー自体の動作確認。

### Unit テスト
なし (CI 設定ファイルのため)。

### E2E テスト

```bash
# ローカルでの CI 再現テスト

# lint
cd src/python/g2p
uv run ruff check piper_g2p/ tests/
uv run ruff format --check piper_g2p/ tests/
uv run mypy --ignore-missing-imports piper_g2p/

# test
uv run pytest --cov=piper_g2p --cov-report=term-missing --cov-fail-under=90 -v

# build
uv build
uv pip install dist/*.whl
python -c "import piper_g2p; print(piper_g2p.__version__)"
```

PR を作成して GitHub Actions が正しく起動・完了することを確認:
1. `src/python/g2p/` 配下のファイルを変更した PR でワークフローが起動すること
2. 3 OS x 2 Python の 6 ジョブが全て green であること
3. lint ジョブで ruff + mypy が pass すること
4. build ジョブで wheel が正しく生成されること

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **pyopenjtalk の Windows CI ビルド**: pyopenjtalk-plus は Windows wheel を提供しているが、CI 環境で wheel が利用できない場合、C++ ビルドが必要になりビルド時間が大幅に増加する。`pip install --only-binary :all:` を使い、ビルドが失敗する場合は JA テストをスキップする戦略が必要。
- **macOS ARM64 の互換性**: `macos-latest` は ARM64 (M1/M2) ランナー。pyopenjtalk-plus の ARM64 wheel が存在しない場合、JA テストがスキップされカバレッジが下がる。
- **PyPI Trusted Publisher**: uv publish は Trusted Publisher (OIDC) をサポートしているか確認が必要。サポートしない場合はトークンベースで publish する。
- **既存 CI との衝突**: piper-plus リポジトリには既に複数の CI ワークフローが存在する。`g2p-python-ci.yml` がパスフィルタで正しく分離されていること。

### レビュー項目
- パスフィルタが `src/python/g2p/**` に正しく限定されていること
- テストマトリクスが 3 OS x 2 Python であること
- `fail-fast: false` が設定されていること (1 ジョブの失敗で他を止めない)
- カバレッジ閾値 (`--cov-fail-under=90`) が設定されていること
- publish ジョブがタグ `python-g2p-v*` でのみ起動すること
- publish ジョブに `needs: [build]` が設定されていること (テスト通過が前提)

---

## 6. 一から作り直すとしたら

- **reusable workflow 化**: `.github/workflows/python-package-ci.yml` のような汎用ワークフローを作成し、`g2p-python-ci.yml` はパラメータを渡すだけにする。piper-plus には `csharp-ci.yml`, `rust-tests.yml`, `ci.yml` (npm) 等の既存ワークフローがあり、共通部分 (checkout, setup-uv 等) をテンプレート化できる。ただし Phase 0 では単一ワークフローで十分。
- **nox / tox によるマトリクス管理**: GitHub Actions のマトリクスではなく `nox` でテストマトリクスを管理すると、ローカルでも CI と同じマトリクスを再現できる。ただし uv + pytest の直接実行で十分シンプルなため不採用。
- **publish を別ワークフローに分離**: テスト CI と publish を別ファイルにすると、publish ワークフローの権限を最小化できる。ただし単一ファイルのほうが管理しやすいため、Phase 0 では統合する。

---

## 7. 後続タスクへの連絡事項

- **Phase 1**: 新言語 (ZH, KO, ES, PT, FR) を追加した際、CI の依存インストール (`--extra all`) に新しい optional deps が自動的に含まれることを確認する。
- **Phase 1**: `mypy --strict` への移行を検討する。Phase 0 の `--ignore-missing-imports` は pyopenjtalk / g2p-en の型スタブが不足しているための暫定措置。
- **Phase 2 (Rust)**: `rust-g2p-ci.yml` を別途作成する。`g2p-python-ci.yml` とは独立。
- **リリース手順**: バージョン番号は `pyproject.toml` の `version` フィールドを手動更新 -> git tag `python-g2p-vX.Y.Z` -> push で自動 publish。`python-g2p-v0.1.0` が最初の実リリースタグ。
