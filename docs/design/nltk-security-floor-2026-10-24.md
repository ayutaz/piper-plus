# nltk の下限を 3.10.4 に上げ、修正済みの advisory の抑止を外す (Issue #709)

## 経緯

GHSA-8mgp-746c-j5xp (CVE-2026-81726) は、nltk の model-artifact API が許可されたディレクトリの外のファイルに触れる脆弱性です。対象は `<= 3.10.3` で、公開時は修正版がありませんでした。そのため、次の 2 か所で抑止していました。

- pip-audit: `--ignore-vuln` で 2 か所 (root と `src/python_run`)
- dependency-review: `allow-ghsas` で 2 か所 (`security-audit.yml` と `dependency-review.yml`。後者は後に #884 で `lint-gates.yml` の dependency-review step に統合)

nltk 3.10.4 (2026-10-21) はこの脆弱性を修正した版です。この版では、ファイルの読み書き、展開、URL の取得をデータディレクトリの中に限ります。また、pickle を制限付きで読みます。

## 変更

- `nltk>=3.10.0` を `nltk>=3.10.4` に上げました。対象は次のとおりです。
  - `pyproject.toml` の 4 か所
  - `src/python/pyproject.toml`
  - `src/python/g2p/pyproject.toml` の 2 か所
  - `src/python_run/requirements.txt`
  - `huggingface-space/requirements.txt`
  - workflow の `pip install` の 2 か所
- 3 つの uv.lock (root、`src/python/g2p`、`environments/webui`) を 3.10.4 に更新しました。変わったのは nltk だけです。
- 上記の抑止をすべて外し、コメントは「解除済み」の履歴に移しました。

## 影響の確認

- **英語 G2P**: g2p_en は nltk の `pos_tag` と cmudict を使います。nltk 3.10.4 の環境で Python の golden (`tools/generate_g2p_golden.py`) を作り直したところ、韓国語を除く 346 件すべてが既存の golden と一致しました。韓国語は g2pk2 が手元にないため対象外です。
- **pip-audit**: `src/python_run/requirements.txt` は抑止なしで「No known vulnerabilities found」でした。
- **Docker**: nltk 3.10.4 は、ほかのアカウントが書き込めるデータディレクトリを読み飛ばします。イメージは root で `/usr/share/nltk_data` に取得するため、この条件には当たりません。`docker-build.yml` の `build-python-train` ジョブの「NLTK data availability test」で確認します (PR のとき)。

## 再発防止

`scripts/check_dependency_floors.py` (pre-commit `dependency-floors`) は、`docs/spec/dependency-floors.toml` の下限について次を検査します。

1. pyproject / requirements / workflow の `<package>>=X` が下限以上であること。コメント行は数えません。
2. uv.lock で解決した版と、uv.lock に記録された各パッケージの要求 (`specifier = ">=X"`) が下限以上であること。
3. 宣言が 1 つ以上見つかること。何も検査しないまま成功しないようにするためです。
4. 修正済みの advisory (`fixed_advisories`) を、workflow が `--ignore-vuln` や `allow-ghsas` で抑止し続けていないこと。

2 の要求の記録は、PR #852 の CI で見つかった漏れを塞ぐためのものです。`src/python_run` の依存は requirements.txt から動的に読まれます。手元の uv 0.12.20 は、その変化を検出しないまま `uv lock --check` を通しました。そのため root と `environments/webui` の lock に `nltk>=3.10.0` の記録が残り、CI の uv 0.13.5 の `uv lock --check` で失敗しました。解決した版は 3.10.4 だったので、版の検査だけでは見つけられません。

4 は #588 の穴を塞ぐためのものです。#588 では下限 `nltk>=3.9.4` が対象範囲 `<= 3.9.4` の内側にありました。それでも抑止があったので、監査は脆弱な版に解決されても成功していました。

このゲートは pre-commit と、`security-audit.yml` の pip-audit の直前の step で走ります。workflow の `paths:` には、ゲートと、それが読む pyproject / lock / requirements を加えました。

新しい advisory で下限を上げるときは、`dependency-floors.toml` に版と advisory を書き足します。
