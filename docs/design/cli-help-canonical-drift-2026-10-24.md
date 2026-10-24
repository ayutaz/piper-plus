# CLI help の正本を CI の取得に固定する (Issue #813)

週次の `cli-help-extract.yml` (2026-10-19) で、6 ランタイム中 3 つが一致しないと報告されました。

| ランタイム | 状態 | 原因 |
|---|---|---|
| rust | DRIFT | 正本 `docs/reference/cli-help/rust.txt` が Windows で取得されていた (`piper-plus-cli.exe`)。4 行のヘッダーもない |
| csharp | DRIFT | 正本が日本語 UI の環境で取得されていた (`使用法:` `オプション:` `バージョン情報を表示する`)。`--output-dir` の既定値に手元のパスが入り、ヘッダーもない |
| cpp | CAPTURE_FAILED | ワークフローの C++ の手順が空ファイルを書くだけで、ビルドしていなかった |

加えて、置き換え規則の誤りで csharp の取得結果が `[default: <RUNNER_PATH>` となり、閉じ括弧が消えていました。

## 根本原因

- **正本の形式を検査するテストが CI で走っていなかった。** `tests/scripts/test_sanitize_cli_help.py` は正本の 4 行ヘッダーを検査しますが、`tests/scripts` のテストはどの CI ジョブも実行していませんでした。そのため、ヘッダーのない手元での取得結果がそのままマージされました (#800)。
- **ずれは報告だけだった。** drift-check の比較は `continue-on-error` で、PR を落としませんでした。古い正本が dev に入り、週次の Issue で初めて見つかりました。
- **C++ の取得が未実装だった。** 初回の PR で後回しにした手順が、そのまま残っていました。

## 変更

- **ワークフロー (`cli-help-extract.yml`)**
  - C++ の CLI (`piper` ターゲット、出力名 `piper-plus`) をビルドし、`./build/piper-plus --help` を取得します。
  - 取得は `LANG` / `LC_ALL` = `C.UTF-8` で行い、UI の言語を英語にそろえます。
  - drift-check で正本の形式テストとワークフローのテストを実行し、PR でずれがあれば失敗させます。
- **置き換え規則 (`sanitize_cli_help_rules.toml`)**
  - runner のパスは `]` の手前で止めます。
  - rust の `piper-plus-cli.exe` は `piper-plus-cli` にします。
- **テスト**
  - `test_sanitize_cli_help.py` で、正本に `.exe`・日本語などの UI 文字列・手元のパスがないことを検査します。
  - `test_cli_help_extract_workflow.py` で、ワークフローが C++ を取得すること、英語の UI で取得すること、形式テストを実行すること、PR でずれを落とすことを検査します。
  - pre-commit (`cli-help-canonical`) でも同じテストを実行します。
- **正本**: rust / csharp / cpp を、このワークフローの Linux での取得結果で置き換えます。

## 運用

正本はワークフローの成果物 `cli-help-<runtime>-<run_id>` から取ります。手元で取得すると Windows や日本語 UI の差が入るため使いません。CLI の help を変える PR では drift-check が失敗するので、その実行の成果物で正本を更新します。
