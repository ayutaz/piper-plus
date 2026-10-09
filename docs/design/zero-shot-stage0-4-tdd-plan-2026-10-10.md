# Zero-shot工程0・4の詳細計画とTDD記録

作成: 2026-10-10。開始HEAD: `f685762d`。
ユーザー指示: 工程4までをTDDで進め、学習はVast.aiで行う。
工程1〜3は実装済み。工程4は既存モデルの再評価・参照処理比較であり、追加学習は工程5。
全体方針は[改善計画](zero-shot-recovery-and-improvement-plan-2026-10-09.md)。

## 1. 実行条件と現在確認できた入力

- Pythonは`uv run`、依存追加は`uv add`。Torch処理はCUDA、配布ONNXの検証はCPU。
- 学習先はVast.ai。ローカルで本学習を開始しない。
- v11 ep9/ep19のcheckpoint、元ONNX、設定、過去ログが`piper-v11-local`にある。
- v10b ep79のcheckpoint/ONNX、CAM++は隣接する保持済みbackupにある。
  所在確認は済んだが、hash・checkpoint内部条件・encoder来歴の監査はこれから行う。
- つくよみの実WAVは`datasets/tsukuyomi-raw/wavs`に100発話ある。
  学習・評価への使用履歴と、他話者floor、held-out ECAPA、ASR revisionは未確定。
- 旧cache embeddingや`listen_onnx_BROKEN`は診断資料として保持する。
  新比較は新しいrun directoryへ生成し、過去の品質数値と同一系列だと仮定しない。
- Vast.aiの`show instances --raw`はHTTP 401 / Invalid user key。
  CLIは失敗JSONでもexit 0を返すため、JSONのstatus/errorも検査する。
  認証更新を依頼済み。確認後までレンタル・起動・停止は行わない。

## 2. 工程0: 棚卸しと実入力の固定

### 0A: artifact監査

checkpoint、元ONNX、設定、CAM++/ECAPA、ASRモデルrevision、参照WAV、実発話/floor、
入力JSONL、uv.lock、実sourceをrole付きで列挙し、path/size/SHA256/statusを保存する。
不足はmissingとして残す。古いpathの存在や拡張子だけでverifiedにしない。
checkpoint内部epoch/hparams/EMA scopeとONNX入出力を確認し、対応をmanifestへ記録する。
学習途中のep9/19はCER診断対象だが、ep40以降の昇格判定対象にはしない。

### 0B: データ/cache監査

dataset相対pathはJSONL親directory基準。missing音声、同名stem、speaker/hashの
train/holdout交差、embeddingのshape/finite/norm、cache sidecar/hash/encoder identityを記録する。
旧絶対pathや不明来歴は確認不能として数える。既存データを削除・上書きしない。
参照WAVはすべてcross-utterance集合からpathと内容hashの両方で除外する。

### 完了条件

実比較の全入力がhash付きで揃い、参照/real/floor/synthの取り違えがない。
学習dataset全量が未回収なら監査未完了と明記し、学習投入可能と判定しない。

## 3. 工程4: 実モデルの評価

### 4A: 固定baseline

v10b ep79を比較基準候補とし、v11 ep9/ep19は履歴の診断系列とする。
同じ評価text、参照、scales、seed、ASR revision/device、source/lockで
Torch raw/既存EMA/正しい現行exportのONNXを生成する。
モデル間で学習条件が違うことを記録し、構造変更の公平なA/Bとは呼ばない。
旧exportは履歴・差分診断に限定し、現在生成したONNXと混ぜない。

### 4B: 評価と比較report

既存strict CER、`eval_zs_secs`のdual-encoder/ceiling/floor、band/comb/comb-HNR/
prosodyを再利用する。manifest/generationの完全な集合・hash整合性を先に検査する。
比較対象間でtext/reference/生成条件、encoder hash、real/floor集合が違う結果は
同条件の改善量として比較しない。ASR/encoderのstubは品質証拠へ使わない。
normalized_transferをheadlineにし、Goodhart/above-ceiling、CER、物理量を併記する。
人手試聴用のWAV・比較表を作り、読み/類似/自然さ/ノイズの判定欄を別々に残す。
未試聴はpending。人手承認を自動生成しない。

### 4C: 参照抽出・前処理比較

同じCAM++・同じ実参照からruntime全発話抽出とtraining chunk poolingを比較する。
resampler/fbank/CMVN/chunk/pooling/正規化の実条件とvector差を記録し、
生成した音声の両encoder/CER/音響指標で比較する。embedding cosineだけで改善と判定しない。
単一/複数参照は総有声時間を揃え、使った全参照をcross集合から除外する。
参照のduration、有声時間、無音率、peak/clipping等を記録し、品質閾値は事前較正する。
学習入力が変わる提案はcache version更新・再抽出・再学習を含めて別変更へ分ける。

### 完了条件

hashで再現できるbaseline JSON/WAV/manifest、抽出条件比較、試聴記録と未確認点、
統一前処理の仕様案、Vast.ai学習候補と計算量見積りが揃う。
実モデルの入力・評価器が不足した場合は工程4完了にせず、実装・fixture成功と区別する。

## 4. TDDの単位と順序

| 順 | 対象 | 先に確認する失敗 | 完了の証拠 |
|---|---|---|---|
| 1 | 複数参照の評価除外 | 2件目の参照がcross集合へ残る、同内容別名を除外できない | 単一参照互換、複数path/hash除外、必要real数、全参照pin |
| 2 | artifact/data監査CLI | missingを成功扱い、相対path基準違い、重複speaker/hash見逃し | 異常fixtureと実artifact監査JSON、入力無変更 |
| 3 | 同条件比較report | 異なる条件・encoder・集合を同じ改善量として受理 | mismatch拒否、3backend整合、実結果の比較表 |
| 4 | 実参照抽出の比較 | 全参照の来歴欠落、長さ不公平、pooling設定未記録 | 実encoder・実WAVで抽出→生成→全評価 |
| 5 | baseline実行と試聴資料 | 旧/破損export混入、ASR部分成功、欠落指標を合格扱い | hash付き実結果、機械gateと人手状態の分離 |

各単位で失敗→最小の修正→関連回帰→必須hook→scoped commit。
機能単位のfixtureを実品質の代用にせず、最後に実入力で経路を通す。

## 5. Vast.aiへの学習受け渡し（工程5、工程4の後）

認証復旧後、最新offerとcompute/storage/transferの料金を読み取り、必要VRAM/空きdisk/
CUDA環境と照合する。repo/source/lock、dataset/cache、recipe、seed、schedule/EMA単位をpin。
まず100〜300 batchのsmokeを計画し、学習更新・AMP・保存/再開/exportを測る。
短いcold測定とwarm測定を分け、steadyな学習速度を起動直後から外挿しない。
候補GPU数、smoke/本走の上限、費用上限、停止条件、成果物回収先を具体化してから実行する。
本走は全armを一括開始せず、修正後基準Cの結果を見て必要な一因子比較を選ぶ。

運用は[remote-train-ops](../../.claude/skills/remote-train-ops/SKILL.md)に従う。
起動後ログ確認、ERR marker、pin照合、監視経路の動作確認、running中の成果物回収と
停止後のactual/intended状態検査を行う。保存済みの他sessionのinstanceは変更しない。
停止後もstorage課金が残り得るため、費用見積りに保持期間を含める。
公式資料: [CLI](https://github.com/vast-ai/vast-cli)、
[管理](https://docs.vast.ai/guides/instances/manage-instances.md)、
[料金](https://docs.vast.ai/guides/instances/pricing.md)。

## 6. 実施記録

2026-10-10: 計画・現物所在調査・Vast.ai認証の読み取り確認を実施。
工程0/4は進行中。最初のTDD単位は複数参照のcross集合除外。
