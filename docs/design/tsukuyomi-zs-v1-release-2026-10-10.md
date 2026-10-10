# Tsukuyomi zs-v1 配布準備・検証記録

作成: 2026-10-10。状態: 既存500 epoch FTの照合、配布物の整形、
Python consumer検証、公開前試聴資料の準備が完了。人手試聴と一般公開は未完了。
ベース側のマージ後CIは47 workflow成功、Docker Build and Pushが実行中。
この件数は本記録作成時のsnapshotで、最終結果ではない。

## 公開対象と来歴

公開先は`ayousanz/piper-plus-tsukuyomi-chan/releases/zs-v1/`。
既存rootのONNX・config・サンプルは保持し、世代別の配布物を追加する。
研究保存先のprivate/gate設定は変更しない。

今回は新しい本学習を始めず、既存の500 epoch FTを候補として再利用する。

| 対象 | 固定した値 |
|---|---|
| 採用ベース | `ayousanz/piper-plus-base`、revision `3620ed788667cb76f08bd6cf2db8152c1f4c8bd1`、`releases/zs-v1/base.ckpt` |
| 公開base checkpoint SHA256 | `86d0362241c2a3a898d23b9c4bce416ca97725024075fb844ae630e7f9b121f0` |
| FT研究保存先 | `ayousanz/piper-plus-zero-shot-tsukuyomi`、revision `c3f236e068b95356b871842b4ae7cec2a86c50ea` |
| 元FT checkpoint | `epoch=499-step=22000.ckpt`、927,048,022 bytes |
| 元FT checkpoint SHA256 | `f375c749caa2a707b3fc9ee672142bdc1441bcbcdd3b523dd9efdb18b017683e` |
| 元FT ONNX | `tsukuyomi-ft-epoch499-zs.onnx`、40,048,610 bytes |
| 元FT ONNX SHA256 | `5fcef335c2bd69a4d2b5512e46d971427a653bf252097e2fb73618e7a584f331` |

元checkpointのメタデータはepoch 499、global_step 22000、173音素、1話者、
6言語、`freeze_dp=true`。resume入力はv7 ep32の`singlespk.ckpt`を指す。
凍結したduration predictorの286 tensor、1,643,440値が公開baseと完全一致する。
同じshapeで共有される505 tensorにFTによる変更があり、音素embeddingも更新されている。
モデルカード、resumeメタデータ、凍結重みを合わせて同じbase世代の来歴を照合した。
歴史的runのsource commit、GPU型番、発話ごとのsplitは復元できていない。

## 配布物の整形

ONNXのbytesは研究保存版をそのまま保持する。opset 15、checker・shape inferenceに合格。
入力は`input`、`input_lengths`、`scales`、`lid`、`prosody_features`で、
`speaker_embedding`は存在しない。今回の音声生成に参照WAVやencoderは不要。
グラフから直接照合できるdecoder EMAの23 initializerが、元checkpointの
`shadow_params`をFP16化した値と完全一致する。

元FT configには、173音素の重みに存在しないID 173〜184が12個含まれていた。
これらを配布configから除去した。有効な173音素のIDは一切変更せず、公開baseと一致する。
検証時は`noise_scale=0.4`、`noise_w=0.5`、`length_scale=1.0`を使用した。
最適な音質パラメータの選定が完了したという意味ではない。

checkpointはモデル重み・decoder/話者projectionのEMA・必要なprimitive設定を保持し、
optimizer、callbacks、loops、lr scheduler、学習dataset/encoderの絶対pathを除去した。
`weights_only=True`で読め、unsafe pickle globalsはない。
現在の`piper_train.vits.lightning.VitsModel`へstrict loadできることを確認した。
元学習runの完全resume用としては案内しない。

| 配布候補 | bytes | SHA256 |
|---|---:|---|
| `tsukuyomi.ckpt` | 319079115 | `7d6a15c4cd9a3c208f71ddf604efb462a023dfc348e266fa5be018f3d9ddba82` |
| `tsukuyomi.onnx` | 40048610 | `5fcef335c2bd69a4d2b5512e46d971427a653bf252097e2fb73618e7a584f331` |
| `tsukuyomi.onnx.json` / `config.json` | 6517 | `055a837f6b77294789f8600ec0d0d6183b128e99023dca20f20f7f662b881b8b` |

## 生成・声質の検証

独立したPyPI `piper-plus==2.0.0`環境、Windows x64 CPUで生成した。
日本語3文は通常のテキストAPIで参照音声なしのWAV生成に成功。
EN/ZH/ES/FR/PT各1文は、言語を明示して音素の欠損を拒否する公開例の経路で成功した。
いずれも22050 Hz、有限値・非無音である。
公開例のスクリプトを同じconsumerで実行してWAV出力も確認した。
他runtime、他OS、Colab全工程の実モデル検証は今回の範囲に含めない。

日本語3文では、FT・旧公開モデル・公開baseのゼロショットを同じ文で生成した。
声質参照はローカルの`VOICEACTRESS100_001`録音。
CAM++のrevision/hash・抽出処理を固定して比較した。

| 評価文 | FT SECS | 旧公開モデル SECS | base Zero-Shot SECS |
|---|---:|---:|---:|
| こんにちは。今日は良い天気ですね。 | 0.6937 | 0.6413 | 0.6980 |
| これは公開モデルの音声を確認するための文章です。 | 0.6539 | 0.6693 | 0.6476 |
| 駅まで歩いてから、電車で会社に向かいます。 | 0.6373 | 0.6508 | 0.7411 |
| 平均 | 0.6617 | 0.6538 | 0.6956 |

今回の条件ではFTがbase Zero-Shotを上回ったとは言えない。
保存済みの評価embedding同士から過去のSECS 0.7749を再計算できるが、
これは今回の3文・参照条件で得た新しい評価結果ではない。
CAM++は学習にも使用されており、独立held-out encoder評価ではない。
参照録音はFTコーパスに含まれる。元runの発話ごとのsplitは確認できていない。
人手による読み・話者類似・自然さ・ノイズの評価は未完了。

Piperはfloat出力を正規化してPCM化するため、PCMのfull-scale近傍の値が
存在するだけでクリッピングが発生したとは判断しない。
任意の全テキストや6言語の音声品質合格も、生成成功だけでは宣言しない。

## 利用条件・公開前ゲート

利用条件は既存の一般公開先と同じ`other / tsukuyomi-chan-corpus`を使い、
[つくよみちゃんコーパスの公式規約](https://tyc.rei-yumesaki.net/material/corpus/#terms3)に
基づくクレジット・音声用途の条件をモデルカードとNOTICEへ記載する。
旧privateカードのCC BY-ND表記を公式コーパスのライセンスと同一視しない。
配布サンプルは新規合成WAVだけとし、元録音・研究用評価embeddingは同梱しない。

人手試聴用に、日本語3文のFT・旧公開モデル・base出力、6言語サンプル、
ローカル専用の参照録音を並べたページを用意した。
モデルカード、manifest、検証記録は現在`human_review_status=pending`。
公開済み・品質承認済みと表示せず、試聴結果を記録してから公開判断する。

公開前に20 manifest entryのhash/sizeとconfig pair、モデルカード、公開例、
試聴ページと全音声のHTTP取得を確認した。
公開後は新規保存先へ未認証で全ファイルを取得し、hash照合・通常生成・
公開checkpoint読み込みを再確認する。HF commit、旧rootの保持、研究保存先の
設定維持を確認してから完了とする。

証拠・配布候補・試聴資料は`output/public-tsukuyomi-release-20261010/`に保存。
