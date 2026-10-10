# Zero-Shot base zs-v1 配布・検証記録

状態: baseの選定・両用途検証・一般公開と公開後consumer確認が完了。
同じbase由来のつくよみちゃん既存500 epoch FTの配布準備を進めている。
試聴・公開の状態は[つくよみちゃん配布準備・検証記録](tsukuyomi-zs-v1-release-2026-10-10.md)を参照。

## 採用する基準版

既存v7 epoch 32 / step 216326を`releases/zs-v1/`の基準版にする。
学習途中の実験用モデルであり、品質改善版の合格・完成を意味しない。
既存のつくよみちゃん500 epoch FT実績が同世代にあり、今回のv2.0.0
training sourceで重みを移せることを確認した。後続世代を最良モデルとして
選定する品質比較は未完了であり、v7を最新・最高品質と表現しない。

| 候補 | 今回確認した状態 | 選定判断 |
|---|---|---|
| 公開rootの旧base | 話者projectionなし。今回のCAM++方式のbaseとは異なる | 既存ファイルを保持 |
| v7 ep32 | 173音素、6言語、571話者、学習済み192次元projection。対応ONNXとFT実績あり | 初回の機能検証可能な基準版 |
| v10b ep79 | 現物checkpointは185音素、8言語の構造を持ち、resize upsampling/SNAC等がv2.0.0 training sourceと異なる | v7に混ぜない。品質改善版の別選定対象 |
| v11 | 既存記録では明瞭さ・品質上の問題で本走停止 | 初回公開に採用しない |

v7/v8系列には旧PQMF由来の音響的な制約があり、未知話者への転写も不完全。
ONNXだけを新PQMFへ置換する処置を行わず、学習済み重みと同世代のグラフを配布する。
この公開で、音声品質の問題が解決したと報告しない。

## 固定した入力

- 研究モデル: `ayousanz/piper-plus-zero-shot-multi-6lang-v7`
  revision `a9d47a14e9c035e0bacf6059c66ff40ea32f56c1`。
- checkpoint SHA256:
  `ebb660fcec781d1de9a04ae69a372f20ebd1e378d31570ec37e6866c39e9f728`。
- ONNX SHA256:
  `e9860701a941db02149c7cfbe19cfb578c235c5e25020f1f592131d9b3b30f84`。
- CAM++: `ayousanz/campplus-onnx`
  revision `bf19094352f4fff3a1599f08e0a77c28494b8592`、SHA256
  `a6ac6a63997761ae2997373e2ee1c47040854b4b759ea41ec48e4e42df0f4d73`。
- training source: GitHub `v2.0.0`
  commit `02d16e8b71e5830434565a04bc900f67133e9de4`の独立展開。
- 推論consumer: 独立venvへPyPIの`piper-plus==2.0.0`をインストール。
  ONNX Runtime 1.31.0、Windows x64 CPU。開発版の`piper_train.ort_utils`を読み込まない環境。

## 配布物の整形

`base.ckpt`は元のモデル重みとdecoder/話者projectionのEMAを保持し、optimizer、
callback/loop/training状態、学習データpath、研究用の絶対pathを除去する。
`weights_only=True`で読め、追加のunsafe globalsがないことを検査済み。
元runの完全resume用として案内しない。元ファイルは研究保存先に保持する。

ONNXは研究保存版と同じbytesを使用。グラフ内で照合可能なEMAの29 tensorは
元checkpointのEMAをFP16化した値と完全一致した。
configの音素IDは重みに対応する元の対応表を維持し、不要な話者識別mapを除去する。
CAM++はApache-2.0のライセンス文と変換元クレジットを同梱する。

MOE-Speechの現行一次規約は学習済みモデルの公開をdataset再配布から除外している。
データ音声、特定話者の識別名・対応情報、元の研究評価データは本配布に含めない。
旧`data-sources.yml`のCC BY-SA表記を公開可否の根拠に使わない。
出典は配布先の`NOTICE.md`に記載する。

## 機能検証と制約

実つくよみちゃん参照WAVからCAM++を実行し、192次元のL2正規化embeddingを抽出。
独立したPyPI consumerでja/en/zh/es/fr/ptの指定文からWAVを生成した。
これは音声出力の機能確認であり、6言語の読み・自然さ・話者類似の品質合格ではない。
今回の人手試聴による新しい品質承認は行っていない。

旧音素マップは現在の前処理の173音素マップと一部IDが異なる。
`scripts/prepare_single_speaker_finetune.py`は音素名とlanguage名を介してIDを変換し、
モデルの対応表を維持する。未知音素、キャッシュ欠損、既存出力への上書きを拒否する。
日本語100発話の既存キャッシュに適用できることと、異常入力のテストを確認した。
公開bundleにも同じスクリプトを同梱する。

推論例は旧マップにない空白・句読点を除外する。発音音素は黙って除外せずエラーにする。
フランス語`ɥ`等、現在のG2Pにあって旧マップにない音素があるため、任意の全テキストの
互換性を保証しない。直接runtimeを呼ぶ場合の欠損音素の警告も見落とさないこと。

追加学習の機能確認では、baseからsingle-speakerへ転移し、短いCUDA runで更新・
checkpoint保存・ONNX export・参照なし音声生成を確認する。
このsmoke成果物はつくよみちゃんの完成モデルとして公開しない。

## 公開・公開後の確認

公開先は`ayousanz/piper-plus-base`、gateなし。既存rootのcheckpoint/configは保持し、
新しい世代の配布一式とrootの案内を一つのHF commitで追加する。
公開前のparent revisionは`ce006e5da7851fdc469887026eeb3f2175e7e080`。
revisionが変わっていた場合は内容を再確認し、競合を無視して書き込まない。

公開後は認証なし・新規download先で全ファイルを取得してhashを照合し、
公開済みconsumerで音声生成する。公開revision、配布hash、FT実測はこの記録に追記する。
研究保存repoのprivate/gate設定は変更しない。

### 2026-10-10の完了結果

- 公開revision: [`3620ed788667cb76f08bd6cf2db8152c1f4c8bd1`](https://huggingface.co/ayousanz/piper-plus-base/commit/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1)。
  [公開bundleと手順](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)。
- 新規保存先へ、Authorization headerもnetrcも使わないHTTPで18ファイルを取得。
  全ファイルの元bytes/hash、配布manifest、SHA256SUMSを照合し、全て成功。
- 取得したencoderと公開例で実WAVのembeddingを抽出し、独立PyPI 2.0.0 consumerで生成。
  出力は22050 Hz、2.984秒、RMS 0.2013の非無音WAV。
  最終revision `3620ed78`の取得済みmodel/configと公開例による再生成も成功し、
  22050 Hz、2.868秒、RMS 0.2413。確率的生成のため初回と波形は一致しない。
- 公開checkpointは323,378,981 bytes、SHA256
  `86d0362241c2a3a898d23b9c4bce416ca97725024075fb844ae630e7f9b121f0`。
  未認証で取得した現物の`weights_only=True` loadとprojection `[512,192]`を確認。
- configは6,417 bytes、SHA256
  `d085681edaa5029c54ea8329f3f23ed347ba46ca15cd80e766de9a6a643dafc0`。
- FT: 2 train batchでG/D各2 optimizer step、`global_step=4`。
  generator 394 tensor、discriminator 111 tensorの更新を確認。
  凍結したDPの最大差分は0、非有限tensorなし。
- FT後のONNXは40,049,004 bytes、SHA256
  `fe8269535551cd86e29f23487fa0267b1a26b9234f107b0e4ddd285ead0eafba`。
  話者embedding入力を持たず、独立consumerで参照なし3文のWAV生成を確認。
  これをつくよみちゃん完成版として公開していない。
- GPU保存checkpointのexportにはCPU実行指定`CUDA_VISIBLE_DEVICES=-1`が必要だった。
  WindowsでのRich出力には`PYTHONUTF8=1`を設定し、短いrunは`--checkpoint-epochs 1`
  で保存を明示した。公開例に反映済み。
- 実参照2本で、確率ノイズを0にした同一入力の再生成は完全一致。
  参照を変更すると波形最大差分0.3223。これは入力が合成に作用する証拠であり、
  話者再現品質の合格判定ではない。
- 同一Windows CPUのwarm inference（52 IDs、G2P/loadを含まない）:
  warmup5回、測定30回、p50 46.0ms、p95 60.4ms、RTF median 0.0344。
  他機種・他モデルの過去benchmarkと直接の性能改善比較に使わない。
- 旧root checkpointのLFS SHA256は維持。v7研究repoとencoder repoはprivateのまま、
  v8研究repoはmanual gateのまま。つくよみちゃん公開revisionも元のまま。
- 関連テスト19件、ruff、ONNX export契約、音素世代契約、モデルmanifest構造gateに合格。
- 初回公開`4e1d7b83`のFT準備helperには、新規前処理のcwd基準相対cache pathを
  dataset基準として二重に解決する不備があった。失敗テストで再現し、source修正
  `aa370b9e`を公開revision `3620ed78`へ反映。model/config/encoderのbytesは維持し、
  helper・provenance・manifest・SHA256SUMSを同じHF commitで更新した。
- v2.0.0のCLIで実WAV8発話を新規前処理し、185音素の出力をbaseの173音素へ変換。
  修正後のhelperを未認証で取得して同じ準備経路を通し、8件のID/cache対応を確認。
  未認証で取得したbase checkpointから新規datasetを短くFTし、step4まで更新・保存した。
  そのcheckpointをv2.0.0 sourceでONNX化し、独立PyPI 2.0.0 consumerで参照なし3文を生成。
  新規経路のONNXは40,049,004 bytes、SHA256
  `d139db47f1a163feba33ebc257a39651df387951111b990ca7b616aecbabde9b`。
  全WAVは22050 Hz、1.846〜3.413秒、RMS 0.141〜0.176で非無音・有限値だった。
  機能確認用の短いFTであり、クリッピングを含む音質や声の類似を承認したものではない。
  公開後にも前処理から通した結果を、既存cacheだけでの検証と区別して残す。

今回の証拠は`output/public-base-release-20261010/`のreceipt・匿名取得結果・consumer結果・
FTログ/checkpoint・WAVに保存。機能検証と品質改善研究を分け、品質承認は未実施のまま記録する。
