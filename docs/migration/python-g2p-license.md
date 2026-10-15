# Python 英語G2Pのライセンス対応

この変更はソース版のPython推論・G2P・学習・WebUIに適用されます。
公開済み `piper-plus==2.0.0` / `2.0.1` と `piper-plus-g2p==0.3.0` の
wheel、既存のDockerイメージは更新されません。新しい版を公開するまでは、
この修正を含むコミットからビルドしてください。版番号だけでは修正の有無を判別できません。

## 変更点

従来の英語依存は `g2p-en==2.1.0 → Distance>=0.1.3` でした。
`g2p-en` 自体はApache-2.0ですが、`Distance` はGPLです。
英語推論ではDistanceを使用していないため、必要な上流コード・重み・
同綴異音語表をprivate namespaceへ同梱しました。別リポジトリのforkは不要です。

公開API、IPA/PUAの変換、数値・未知語の推論は維持します。
`piper-plus-g2p[en]` / `[all]` は引き続き利用でき、NumPy・NLTK・joblib・
inflectを導入します。外部 `g2p_en` モジュールをアプリケーションから
直接importしている場合、その独自依存は利用者側で見直してください。
`piper_plus._vendor` / `piper_plus_g2p._vendor` は公開APIではありません。

## 環境の更新

既存環境にDistanceが残ることを避けるため、専用環境での再導入を推奨します。
ソースのチェックアウトで、必要な経路だけを選択します。

```bash
# CPU推論とHTTP API。GPUの場合は --extra cpu を --extra gpu に置き換える。
uv sync --locked --package piper-plus --extra cpu --extra http
uv run --locked --package piper-plus --extra cpu --extra http piper-plus --help

# 独立したWebUI環境（ルートから実行）
uv sync --locked --project environments/webui
uv pip check --python environments/webui/.venv

# 学習環境。librosa由来の学習専用soxr例外は従来どおり。
uv sync --locked --package piper-train --extra train
```

`uv sync` はその専用環境をlockfileの選択に合わせます。環境のパスと用途を
確認してから実行してください。上記はシステムPythonのパッケージを削除しません。
NLTKの `cmudict` / 品詞タグ用データは従来どおり別途ダウンロードが必要です。
ダウンロードデータの許諾表示も確認してください。

## 配布物の確認

実際にwheelをビルドし、新規環境へ導入して検査するコマンドです。
`--work-dir` には未使用のディレクトリを指定します。

```bash
python scripts/check_bundled_english.py
python scripts/run_python_license_consumer.py \
  --work-dir output/python-license-consumer --with-model
```

この検査はsdistからwheelを生成し、CPU/HTTP/G2P全言語の依存整合性・
ライセンスメタデータ・旧配布物の不在・英語24例と混在文4例の互換性を確認します。
`--with-model` は公開baseの固定revisionとSHA256を検証して4種類のWAVを生成します。
非空・非無音の確認は音質や話者類似性の承認を意味しません。

Python license CIはLinux・Windows・macOSのPython 3.11/3.13で導入を検証し、
Linux/Python 3.13では実モデル音声生成も行います。GPUとWebUIの依存経路は
consumer契約CIで検査します。詳細な出典・許諾文・検証範囲は
[監査記録](../design/python-g2p-license-2026-10-16.md)に記載しています。
