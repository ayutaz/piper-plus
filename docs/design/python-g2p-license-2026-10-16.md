# Python 英語G2Pのライセンス監査と対応

調査日: 2026-10-16。対象はPython推論・独立G2P wheel・学習・WebUI・HF Spaceの
英語依存経路です。公開モデルの重みや他ランタイムの発音方式は変更しません。

## 確認した問題

公開済み `piper-plus==2.0.0` / `2.0.1` と `piper-plus-g2p==0.3.0` の
英語extraには `g2p-en>=2.1.0 → Distance>=0.1.3` が含まれています。
`g2p-en==2.1.0` 自体のwheelはApache-2.0ですが、
`Distance-0.1.3.tar.gz` の `distance/LICENSE` はGPLv2本文を含み、
`setup.py` にもGPLの著作権ヘッダーがあります。PyPIの `License: UNKNOWN`
だけを見て許可できる依存ではありません。

上流wheelの全Pythonソースを確認した結果、推論コードはDistanceをimportしていません。
別候補 `espnet-g2p-en==2.1.0.post1` にも同じ依存があり、その置換では解消しません。

一次資料:

- [g2p-en 2.1.0の配布メタデータ](https://pypi.org/pypi/g2p-en/2.1.0/json)
- [Distance 0.1.3の配布メタデータ](https://pypi.org/pypi/Distance/0.1.3/json)
- [上流g2p-en](https://github.com/Kyubyong/g2p)
- [Distanceのソース](https://github.com/doukremt/distance)

## 選択した方式

既存Rust G2Pを `english,ffi,bundled-dicts` でビルドしてPythonと比較しました。
英語24例中、トークン列が一致したのは7例で、数値・金額・同綴異音語・未知語に差がありました。
今回のライセンス修正で発音方式も変えることを避けるため、Python上流の必要なファイルを
private namespaceへ同梱します。新しいforkリポジトリや別名のPyPI依存は作りません。

- `src/python_run/piper_plus/_vendor/g2p_en/`
- `src/python/g2p/piper_plus_g2p/_vendor/g2p_en/`

2つのwheelは独立して導入可能なので、片方からもう片方への依存を追加せず、
同一のファイルを含めます。`checkpoint20.npz` は各wheelで約3.3 MB（圧縮前）です。
pre-commitの大容量制限では、この2つの固定パスだけを除外し、代わりにハッシュを検査します。

同梱対象は `__init__.py` / `g2p.py` / `expand.py` / `checkpoint20.npz` /
`homographs.en` / Apache-2.0の `LICENSE.txt` です。Distanceのソースは含めません。
NLTKのcmudictや品詞タグ用データも同梱しません。

`expand.py` はKeith ItoのTacotron数値正規化に由来するため、
[固定コミットのMIT許諾文](https://github.com/keithito/tacotron/blob/d26c763342518d4e432e9c4036a1aff3b4fdaa1e/LICENSE)
を `TACOTRON-LICENSE.txt` に保持しました。`NOTICE.txt` に出典と変更を記載し、
`provenance.json` に取得URLと全ファイルのSHA256を記録します。

唯一の上流コード変更は、`g2p.py` の正規表現文字列にraw prefixを付けたことです。
正規表現の値は変わらず、Pythonのinvalid escape警告を防ぎます。
重みはGRUによる未知語推論用です。辞書仕様のBiLSTMという旧記載も修正しました。

| 対象 | SHA256 |
| --- | --- |
| 上流 `g2p_en-2.1.0-py3-none-any.whl` | `2a7aabf1fc7f270fcc3349881407988c9245173c2413debbe5432f4a4f31319f` |
| `checkpoint20.npz` | `b8af35e4596d8dd5836dfd3fe9b2ba4f97b9c311efe8879544cbcfcbd566d8c6` |
| 上流 `g2p.py` | `fc2548b855e102f774506a6afe4f4bc88424229b69701ab6040aa16710ddff3a` |
| 同梱 `g2p.py` | `429862b36b7d6d1068257250aa40ff92d97fd68324af03e9bf12eb05edc60509` |
| Tacotron `LICENSE` | `f89accd9d66f6a011f19997d7a21cf71a35ffe2e2d0911b5460cbd0cab52a581` |

再取得・検査:

```bash
python scripts/check_bundled_english.py --wheel /path/to/g2p_en-2.1.0-py3-none-any.whl
python scripts/check_bundled_english.py
```

このツールは上流コードを実行せず、固定したwheel SHA256、ファイル内容、許諾表示、
2つのコピーの一致、余分なファイルの不在を検査します。

## 依存定義とライセンス検査

runtime requirements、G2P `en` / `all` extra、root / training pyproject、
root / WebUI / 独立G2Pのlockfile、CIの直接install、HF Spaceを更新します。
対応するlockfileは `uv.lock`、`environments/webui/uv.lock`、
`src/python/g2p/uv.lock` の3つです。必要なNumPy・NLTK・joblib・inflectは明示依存として残します。

学習パッケージのメタデータは依存名として `piper-plus-g2p` を宣言します。
チェックアウト外で `pip install src/python` だけを実行すると、pipはuv workspaceの
ローカル参照を使わず、公開済みPyPI版の `piper-plus-g2p` を解決する可能性があります。
ソース版の修正を含めるには、チェックアウトのルートで下記のworkspaceコマンドを使うか、
2つのローカルwheelを同じ環境へ導入してください。runtimeの `piper-plus` は独自の
vendor backendを持つため、G2P wheelとの同時導入は必要ありません。

```bash
# checkout root
uv sync --locked --package piper-train --extra train

# pip/uvでworkspaceを使わない場合は、G2Pとtrainingのwheelを同じ成果物から入れる
uv build --package piper-plus-g2p --out-dir dist/local
uv build --package piper-train --out-dir dist/local
uv pip install dist/local/piper_plus_g2p-*.whl dist/local/piper_train-*.whl
# 導入済みのローカルwheelにextraを追加する（--upgradeは付けない）
uv pip install "piper-plus-g2p[all]" "piper-train[train]"
```

別途、既存のライセンスCIで次のscanner判定が見つかりました。
対象版のPyPIソースアーカイブと許諾文を確認し、既存の方針に合わせて
`allow-dependencies-licenses` をパッケージ単位で追加します。
GPLを許可するリスト変更や、Distanceを検査から除外する変更はしません。

| パッケージ | 確認した配布物内の許諾 | 対応 |
| --- | --- | --- |
| [audioop-lts 0.2.2](https://pypi.org/pypi/audioop-lts/0.2.2/json) | PSF-2.0、Pythonの歴史的許諾表示 | package単位のscanner補正 |
| [protobuf 7.36.2](https://pypi.org/pypi/protobuf/7.36.2/json) | BSD-3-Clause、元Google protobuf著作権表示 | package単位のscanner補正 |
| [regex 2026.9.29](https://pypi.org/pypi/regex/2026.9.29/json) | Apache-2.0 AND CNRI-Python | package単位のscanner補正 |

`dependency-review.yml` と `security-audit.yml` の両方を同期します。
既存の学習専用 `soxr` 例外は変更しません。

## テストとCI

`tests/fixtures/english_g2p_compat.json` は変更前の外部g2p-enを使って記録した
英語24例・日英/中英混在4例です。ARPAbet、IPA、韻律、runtimeのPUAを固定し、
実装同士の一致だけでなく、変更前の出力に一致することを検査します。

`scripts/run_python_license_consumer.py` は次を行います。

1. 2パッケージのsdistを作り、sdistからwheelをビルドする。
2. 新規venvへruntime `[cpu,http]` とG2P `[all]` のwheelを導入する。
3. `uv pip check` と、選択したextraの推移依存のメタデータ監査を行う。
4. `python -I` でwheelをimportしたことを確認し、旧配布物の不在と互換性を検査する。
5. オプションで公開baseのrevision/ハッシュを検証し、4種類の音声を生成する。

実配布物の検査で、runtimeのsdistにはリポジトリの `VERSION` が入らず、
wheel再ビルド時に0.0.0へ変わる問題も確認しました。`setup.py` がsdistの
`PKG-INFO` のVersionを読むよう修正し、sdistとwheelの版を維持します。

新しい `python-license.yml` はLinux・Windows・macOS、Python 3.11/3.13の
6環境で導入・依存監査・28例の比較を行い、Linux/Python 3.13で実モデル検査を行います。
既存の `g2p-python-ci.yml` はLinux・macOS・WindowsとPython 3.11/3.12/3.13の
9環境でG2Pテストを実行し、別ジョブでlint・mypy・配布物ビルドとextras smoke testを行います。
GPUとWebUIは `consumer-contracts.yml` の専用環境で依存監査を行います。
新規の推移依存にも監査を適用し、宣言されたGPL/LGPL/AGPL、ライセンス情報欠落、
依存不足、旧 `g2p-en` / `Distance` の残存を失敗にします。
この検査は配布物全体の法的判定やダウンロードコーパスの自動監査を代替しません。
ソースの回帰テストは全extraとHF Spaceの依存定義、および3つのPython lockfileから
旧 `g2p-en` / `Distance` が除去されていることも検査します。

ローカルでは英語24例・混在4例の互換性、および公開baseによる英語・未知語・
日英混在・中英混在の4つのWAVが非空・非無音であることを確認しました。
最終コミットの各OSでの結果はPRのCI結果を参照してください。
固定した192次元の非ゼロ埋め込みを使う機械的検証であり、音質・話者類似性の承認ではありません。

## 配布の境界

今回のPRはソースとCIの修正です。既存のPyPI版やDockerイメージの内容は変わりません。
新しいパッケージ公開、タグ付け、モデル再公開はこのPRでは行いません。
利用者向けの環境更新手順は[移行ガイド](../migration/python-g2p-license.md)にまとめています。
