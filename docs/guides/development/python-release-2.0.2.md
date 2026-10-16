# Python 2.0.2 / G2P 0.3.1 リリース準備

この文書は公開前のチェックリストです。`piper-plus==2.0.2` と
`piper-plus-g2p==0.3.1` は準備中で、版番号の更新やPRのマージだけでは公開されません。
既存のPyPI wheelや公開済みDockerタグは置き換えません。

## 対象

| 配布物 | 準備する版 | 版番号の定義 | 公開経路 |
|---|---|---|---|
| Python runtime | 2.0.2 | ルート `VERSION` | `dev-create-release.yml`、既存 `v2.0.2` タグを選択して手動実行 |
| Python G2P | 0.3.1 | `src/python/g2p/pyproject.toml` と `__init__.py` | `g2p-python-ci.yml`、`python-g2p-v0.3.1` タグのpush、または既存タグを指定して手動実行 |

runtimeは独自の英語backendを同梱し、独立G2Pへの依存はありません。
学習環境で独立G2Pを使う利用者にも修正を届けるため、両方の配布物を準備します。
学習パッケージやRust・npm・NuGet等の独立した版番号は変更しません。

## PRで完了させること

1. devから準備ブランチを作り、上記の版番号と3つのlockfileを同期する。
2. 既存の[ライセンス監査](../../design/python-g2p-license-2026-10-16.md)を
   公開ワークフローからも必須で実行する。失敗・中断・スキップ時は公開しない。
3. sdistからwheelをビルドして新規環境へ導入する。旧英語依存の不在、
   ライセンス、英語24例・混在文4例、公開baseによる4種類の非空・非無音WAVを確認する。
4. 公開するwheelそのものの名前・版番号・依存定義を検査し、同梱backendの
   コード・重み・許諾文・出典をチェックアウトの検証済みファイルと照合する。
5. PRのCIが完了し、失敗・未完了がないことを確認してdevへマージする。

ローカルでの検査例です。既存環境を再利用しないディレクトリを指定します。

```bash
uv run --no-sync python scripts/check_version_manifest_sync.py --strict
uv run --no-sync python scripts/check_bundled_english.py
uv run --no-sync python scripts/run_python_license_consumer.py \
  --work-dir output/python-2.0.2-consumer --with-model
```

CIはLinux・Windows・macOSのPython 3.11/3.13で実施し、
Linux/Python 3.13で実モデル音声生成を行います。音質の追加承認や性能測定ではありません。

## 公開時に別途行うこと

この準備PRではタグ作成・公開ワークフローの手動実行・PyPI公開を行いません。
公開操作の前に、対象コミットと未使用の版番号、PyPIのTrusted Publisher設定を
確認します。両パッケージの公開ジョブは `pypi` environmentを使い、
workflow名はそれぞれ `dev-create-release.yml` と `g2p-python-ci.yml` です。
PyPI側の設定はリポジトリのCI成功だけでは確認できません。

- 独立G2Pは `python-g2p-v0.3.1` を使います。公開完了後、PyPIから新規導入して
  依存閉包を再検査します。タグを付け直して既存版を上書きしません。
- runtimeは既存のネイティブ配布と同じ `v2.0.2` を使います。このタグのpushは
  Docker・shared library等も起動するため、rootリリースの全前提を満たしてから行います。
  `Package.swift` の版番号・URL・checksum、ネイティブ成果物、署名と公開後検査も
  対象です。PythonだけのCI成功をrootリリース全体の承認として扱いません。
- `dev-create-release.yml` は準備済みタグと同じref、入力 `version=2.0.2` で
  実行します。タグが存在しないdevから先に実行する手順は使いません。
- CHANGELOGのUnreleased項目を実際の公開日で確定し、公開先から取得した
  パッケージの版番号・ライセンス・依存閉包・音声生成を再検証します。

移行方法は[英語G2Pの移行ガイド](../../migration/python-g2p-license.md)と
[provider環境の移行ガイド](../../migration/provider-environments.md)を参照してください。
