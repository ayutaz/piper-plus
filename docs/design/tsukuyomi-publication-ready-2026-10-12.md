# つくよみちゃん: 公開準備と公開後の検証記録

作成: 2026-10-12。公開先は`ayousanz/piper-plus-tsukuyomi-chan/releases/zs-v1/`。
同じ公開base由来の既存500 epoch FTを使う。
2026-10-15に日本語3文の試聴承認を受領し、HF公開と匿名consumer検証を完了した。
元の配布候補と試聴資料は`output/public-tsukuyomi-release-20261010/`に保持する。
準備コピーは`output/publication-ready-20261012/prepared/`。

過去の照合・比較結果は[検証記録のPR #793](https://github.com/ayutaz/piper-plus/pull/793)を参照。
ベースはrevision `3620ed788667cb76f08bd6cf2db8152c1f4c8bd1`で公開済み。
公開commitは[`93c1fb6d67c29accc9ddf52326bb4582b1b52a3d`](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/tree/93c1fb6d67c29accc9ddf52326bb4582b1b52a3d/releases/zs-v1)。
公開時の親revisionは`36b59c825c36bd386b8960cf3f604382f52f2a87`。
旧root model/configとbase・研究保存先のprivate/gate設定は保持する。

## 2026-10-15の公開結果

- ユーザーの実回答「okです。問題ないので残りの対応を進めてください」を記録した。
  読み・声の類似・自然さ・ノイズの確認依頼に対する一括承認として反映し、
  項目別の詳細コメントは未提供であることも保持した。任意の文章・言語への品質保証にはしない。
- 22ファイル、359,871,478 bytesを公開。ONNX/checkpoint/config/sampleは試聴候補から変更していない。
- 公開commitから新規directoryへ認証header・token・netrcなしで全22ファイルを取得し、
  size/hash、19件のmanifest、SHA256SUMSを照合した。
- 公開PyPI `piper-plus==2.0.0`で参照なしの通常text APIと配布例を実行した。
  checkpointは`weights_only=True`かつtraining modelの`strict=True`で読み込んだ。
- 旧root payloadと5件のbase/研究保存先のrevision・ファイル・private/gate設定を保持した。
  Hugging Faceが`.gitattributes`へ追加したのは、今回公開した日本語sample 2件のLFS ruleだけ。
  保持確認は旧ruleのbytesを固定し、receipt内かつLFS metadataのあるrelease fileへの追記だけを許可する。
- receipt: `output/publication-ready-20261012/prepared/publication-receipt.json`。
  匿名検証: 同directoryの`anonymous-public-verification.json`。
  重み・録音・認証情報をGitHubへ追加しない。

以下は公開時の手順の記録である。公開と匿名 consumer 検証は完了している。
同じ公開先への `publish_bundle --apply` や再 upload を現在の利用者へ促さない。
再現が必要な場合は receipt と匿名検証 JSON の hash/path を参照し、公開操作は新しい
release plan と明示的な承認の下で別途行う。

## 試聴前に完了させる作業

- 最終22ファイルのhash/size、対応config、モデルカード、固定source/baseを照合。
- 新規コピーで通常生成・配布例・checkpoint strict loadを確認。
- 公開先に対するdry-runと人手結果欠落時の停止を確認。
- 回答の不足、試聴WAVの変更、payloadの変更、HF親revision/設定の変更を拒否する。
- 元候補を保持し、試聴結果の反映前にmetadataをbackupする。
- 試聴ページでは日本語3文のFT・旧モデル・baseを比較できる。

準備helperはGitHubで管理する`scripts/tsukuyomi_release/`。
配布物・モデル重み・元録音・private評価embeddingをGitHubへ追加しない。
テストは一時directoryと架空の回答を使用し、実際の人手承認・HF公開を行わない。

## 試聴結果の反映と公開

1. 人手の実回答を確認し、`human-review-template.json`のコピーへ記録した。
   必須項目は`reading`、`similarity`、`naturalness`、`noise`、実際のユーザー発言、
   timezone付き記録日時、実験基準版の公開判断、試聴WAV 3件のhash。
   空欄を機械指標から埋めたり、未知の項目を「問題なし」にしない。
   問題があれば原因を調べ、修正した対象を再試聴する。
2. 重み・config・sample を変更せず、モデルカード・検証 JSON・manifest・SHA256SUMS
   を更新した。結果は `publication-receipt.json` と `anonymous-public-verification.json`
   に固定している。
3. 公開先への追加と receipt の revision 固定を完了し、未認証取得・生成・checkpoint
   読み込み・旧 root と research storage の保持を確認した。完了済み操作の command
   をこの文書から再実行しない。

機械検証と人手試聴の記録が全て揃い、公開後検証にも成功したため公開完了とする。
人手の回答反映後に古い`finalize_bundle.py`を実行しない。
これはpendingの準備候補を生成する旧helperで、回答を上書きする。
任意の全文章・全言語の品質承認や、FTによる声質改善をこの工程だけで宣言しない。

## 準備コピーの再作成

出力先が存在する場合は上書きせず停止する。
別の新規directoryを指定し、sourceの全hashを検査してから準備する。

```powershell
uv run --no-sync python -m scripts.tsukuyomi_release.prepare --source output/public-tsukuyomi-release-20261010 --output output/publication-ready-20261012/prepared
uv run --no-sync python -m scripts.tsukuyomi_release.consumer --workspace output/publication-ready-20261012/prepared --candidate
```

candidate検証は新規コピーによる事前確認で、匿名の公開取得とは区別する。
独立したPyPI 2.0.0 consumer環境とtraining環境は今回のworkspaceの既存環境を使う。
別workspaceで実行する場合は、同じ環境と配布物を用意してから実行する。
他runtime/OS・Colab GPU全工程の実モデル確認は別途の検証対象であり、
この準備helperの成功をその確認済み証拠として扱わない。

## 公開baseのruntime確認

`.github/workflows/public-base-runtime.yml`で、公開済みbaseとCAM++を上記の固定revisionから
未認証で取得し、固定SHA256を照合する。private/gated保存先は使用しない。
参照音声は旧つくよみちゃん公開先の固定revisionにある合成sampleで、元録音ではない。
CAM++からL2正規化した192次元embeddingを抽出し、日本語3文と他5言語の音素IDを作る。

Python/Rust/Go/C#/C++のCLIと、実際のORT Web WASM providerを使うPiperPlus推論に
同じ音素IDとembeddingを渡す。6runtimeの結果が全て揃わなければ集計は失敗する。
各WAVの長さ・sample rate・非無音を確認し、noiseを0にした同一入力の再生成が一致することと、
embeddingの符号だけを変えた場合に音声が変わることを確認する。
符号反転はconditioningが無視されていないことの確認用で、声質評価には使わない。

この工程は共通音素IDからの推論確認であり、native G2P、各OS、ブラウザUI、
Colab GPUの全工程や人手による音質評価は含まない。
WASMはNode host上の`onnxruntime-web`を使い、`onnxruntime-node`をWASMの証拠にしない。
既存npm Node CLIは256次元のzero embeddingとmaskを固定しているため、このbase確認では使わない。
結果はActions artifactの`public-base-summary.json`と各runtimeのWAV/logに保存する。

初回の実モデルCIではPython/Rust/C#/WASMが成功し、Go/C++はconfigの読み込みで停止した。
Goは`num_speakers=571`に対して話者名mapを必須にしていたが、名前は表示用metadataであり、
推論入力の`sid`/`speaker_embedding`はONNX graphから判定する。名前を省略できるようにする。
C++はraw IPAの`ɔɪ`/`œ̃`/`ɐ̃`を、それぞれ既知の内部PUA `U+E062`/`U+E063`/`U+E064`へ
解決し、modelの音素IDを保持する。未知の複数コードポイント音素や、raw/PUA間でIDが競合するconfigは拒否する。
公開済みmodel/configの変更は不要。GoのconfigテストとC++のparserテストを実モデルCIでも実行する。
修正後の[Actions run 38189966578](https://github.com/ayutaz/piper-plus/actions/runs/38189966578)で
全6runtimeが成功した。共通音素IDによる計60音声のhash/長さ/非無音とconditioningを照合済み。
これは固定 public base の source/runtime CI proof であり、独立 PyPI
`piper-plus==2.0.0` consumer proof や人手品質承認とは別の証拠である。

## Colabの確認状況

2026-10-12に実際のColabページを確認し、補助スクリプトの取得pathが
公開bundleの`examples/prepare_single_speaker_finetune.py`と一致していないことを発見した。
取得pathを修正し、`token=False`による未認証取得と、hash不一致時の明示的な停止を追加した。
ノートブックの実際のdownload関数を抽出するテストで、取得先・固定revision・未認証条件・
hash不一致時の停止を確認する。これはColab GPU実行の成功を意味しない。

2026-10-15に、定期購入・有料compute unitなしの無料Colab T4、費用上限0円で実環境検証を実施した。
接続時の承認上の問題は解消済み。データは公開baseから作成した合成音声8件のみで、元録音・研究データは使用していない。
セル内のファイル選択ではイベントが取得できなかったため、Colabのファイル欄から同じZIPをアップロードし、
SHA256 `c42c719d159696f63c288e31c0ba81dbccb3080fbadda11f9ffa838499af1d06` を照合して展開した。
Driveのmount・HF公開・有料リソースの購入は行っていない。

実行中に判明した次の3点をノートブックで修正した。

- v2.0.0の単一言語前処理は `language_id: null` を出力する。明示的な言語mapがない単一言語データに限りID 0を設定してから、固定公開helperで音素・言語IDを整合する。既存のmapは保持し、不明な非ゼロIDは拒否する。
- Colabが継承させる `MPLBACKEND=module://matplotlib_inline.backend_inline` は別のuv環境では読み込めないため、学習前に `Agg` を指定する。
- v2.0.0の明示的なModelCheckpointは `OUTPUT_DIR/checkpoints/` に保存する。旧Lightning loggerの保存先と両方を探索し、epoch・stepの数値で最新を選ぶ。未保存なら停止する。

確認結果:

| 項目 | 実際の結果 |
|---|---|
| 学習ソース | v2.0.0 / `61ac41b3d61d4f7a8856aa0bdd945d95e7f86515` |
| GPU | Tesla T4、CUDA利用可能、VRAM 14.6 GB |
| 環境 | Python 3.13、torch 2.11.0+cu128、Lightning 2.6.6、ONNX 1.23.0、ORT 1.30.0 |
| 前処理・整合 | 8件、173音素、1話者、ja/en/zh/es/fr/ptのID map保持 |
| 学習 | batch size 1、1 epoch、train上限2 batch、validation 0。ログとcheckpoint内のbatch completedが両方2 |
| 保存checkpoint | epoch 0、global_step 4（手動最適化で2 batch × 2 optimizer）、927,047,382 bytes |
| ONNX export | CPUで単一話者FP16、40,049,004 bytes。checker・shape inference成功 |
| ONNX入力 | input、input_lengths、scales、lid、prosody_features。speaker_embeddingなし |
| 参照なし生成 | 日本語2文、2.6006秒 / 2.8793秒、22050 Hz・mono・PCM16、有限値・非無音 |

checkpoint SHA256: `20c19c803c8b90258c46084ff7cbf0a0b88a02dce9eb8e61e0faef645d327308`。
ONNX SHA256: `d85753ce477f2e436c0ab246337150650f45c9e4717f46140cec8964eae52987`。
この短い実行は学習経路の動作確認であり、声質改善・人手の品質承認・500 epoch完走・他言語評価を意味しない。
公開済みモデルの置換も行っていない。
