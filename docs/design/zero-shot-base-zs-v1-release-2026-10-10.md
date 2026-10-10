# Zero-Shot base zs-v1 配布・検証記録

状態: 公開前検証中。対象はbaseの選定・両用途検証・一般公開まで。
つくよみちゃんの本追加学習と公開は次工程。

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
