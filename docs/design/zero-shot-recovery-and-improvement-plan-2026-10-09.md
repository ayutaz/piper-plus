# zero-shot不具合修正・品質改善計画（2026-10-09）

**状態: 計画策定済み。実装・追加学習は未着手。**

対象ブランチ: `feat/zero-shot-v8-dataset-scaling`。
計画開始時HEAD: `9629d68f`。
根拠: [GPT-SoVITS調査](../research/gpt-sovits-zero-shot-2026-10-09.md)、
[既存実装監査](../research/zero-shot-implementation-audit-2026-10-09.md)、
[評価契約](../spec/zs-eval-contract.md)。

本計画は、2026-10-09時点で確認した不具合と反証を踏まえた次工程の参照先とする。
旧[v11 roadmap](zero-shot-v11-roadmap.md)の過去の実測・成果物記録は維持するが、
「ep15で敵対ramp凍結」「CER CLIを呼べばgate完成」という実行判断は本計画で更新する。

## 1. 目的と判断の分離

目的は、日本語の読み・自然さ・話者類似を備え、CPU/ONNXで利用できるzero-shotモデルを作ること。
次の3段階を別々に判定する。

1. **実装の成立**: 更新周期、入力、cache、manifest、監視状態が仕様どおりに動く。
2. **学習の成立**: 有効な勾配とdiscriminator更新があり、復元・DDP・exportが正常に動く。
3. **品質の成立**: 固定評価契約と人手試聴で改善を確認する。

CPU再現やテスト成功だけで品質改善とは判定しない。
WavLM更新周期の不具合は確定しているが、v11の話者類似度低下の単独原因は未確定。
修正後の比較で原因を分離する。

## 2. 工程と依存関係

| 工程 | 作業 | 成果物 | 次工程へ進む条件 |
|---|---|---|---|
| 0 | source・データ・評価条件を固定 | run manifest、data/cache監査結果 | hash・入力条件・比較対象が揃う |
| 1 | G/D周期とKL監視状態を修正 | training修正、実Lightning回帰テスト | 周期・resume・skip・validationのテスト成功 |
| 2 | embedding抽出・cache・runtime検証を修正 | metadata付きcache、manifest、入力validator | 衝突/失敗/旧cache/不正入力を検出、既存経路の互換維持 |
| 3 | 推論条件で評価できるようにする | 固定話者参照、推論評価、strict CER集合検査 | 参照条件と期待clip全件を検証できる |
| 4 | 既存checkpoint再評価と低コスト比較 | 同条件のraw/EMA/ONNX比較、参照抽出比較 | 再現可能な修正後baselineとGPU実験の仕様が揃う |
| 5 | 修正後学習と単一要因実験 | smoke、原因分離run、v11b候補 | 機械検証・既存品質gate・人手評価を順に満たす |
| 6 | v12参照系列入力を設計・検証 | 新入力契約、小型参照encoder、A/B結果 | global-only対照に対する利得と配布/速度予算を確認 |

工程1と2は独立実装可能。工程3は両方の仕様が定まってから統合する。
工程4以降のモデル比較には工程1〜3が必要。
工程6の設計は先行可能だが、追加学習は工程5の基準評価を確立してから判断する。

## 3. 工程0: 比較条件とデータの固定

- source SHA、依存lock、training/eval設定、seed、speaker encoder ID/SHAを記録する。
- 既存checkpoint、ONNX、参照WAV、評価text、holdout/floor集合の所在とSHA256を確認する。
  手元にない成果物は「未回収」と記録し、過去のpathを存在確認済みとして扱わない。
- 学習/holdoutのspeaker IDと音声hashの交差、同名stem、missing file、embeddingの
  shape/finite/normをオフライン監査し、件数・対象IDを出す。
- cacheのencoder/前処理履歴が不明なものは「来歴不明」とし、正常なshapeだけで
  検証済みcacheへ昇格させない。必要な再抽出範囲を見積もる。
- 評価に使う全参照WAVをhashで固定する。複数参照の場合は全参照をcross-utterance集合から除外する。

旧データ・checkpointは保持し、修正後artifactと別のversion/pathへ保存する。
GPUの提供者・料金・現在の接続可否は本計画では確認していない。

## 4. 工程1: trainingの確定バグを修正（最初の実装）

### 4.1 G/D/WavLMの周期

永続training batch counterを導入し、batch開始時の同じ値でG更新・WavLM G/D計算を判定する。
`global_step`はLightningのoptimizer更新数として残し、batch周期の代用にしない。

- counterはtraining batch受領ごとに1回進める。loss非有限skipでも進める仕様を固定する。
- validation/sanityはcounterを進めない。
- 実際のG/D optimizer更新数も別に記録し、latent fillingなどDを省く経路はskip理由を記録する。
- scheduler、EMA、DINO、swap-SCL、latent filling、telemetry、gradient probeについて、
  batch周期かoptimizer更新周期かを一覧化して、意図に沿うcounterへ接続する。
- WavLMの周期補償倍率は、実際の計算頻度と整合させる。
  Gの更新周期との組合せも確認し、lossの過大/過小適用を防ぐ。

checkpointへcounterとschedule versionを保存する。
旧checkpointには正確なbatch counterがないため、optimizer合計stepから無条件に逆算しない。
旧checkpointの推論は維持し、追加学習はweights-only開始と厳密resumeを明示的に区別する。
復元不能な旧状態を「完全に同じresume」と報告しない。

### 4.2 KL監視

training時だけKL cap streakを更新する。validation/sanityがstreakを増加・reset・abortしない仕様にする。
abort閾値と検知内容は維持し、validationのKLは別の監視値として記録する。

### 完了条件

TDDで現行不具合を失敗テストにしてから修正する。

- 実Lightningで8batch、D:G=2:1 → **G4回/D8回**。
- D:G=1:1、WavLM 2batch周期 → **WavLM G/Dとも4回**、D headの重み変化あり。
- D:G=2:1とWavLM周期の組合せを追加確認する。
- checkpoint途中保存/復元後も周期が連続する。
- G/Dの非有限loss、latent fillingのD skip、DDP rank間の判断を確認する。
- validation/sanityでtraining counter・KL streakが変化しない。

まずCPUの小型モデルで検証し、DDP/AMP/full modelは工程5のsmokeで確認する。

## 5. 工程2: embedding pipelineとruntime入力を修正

### 5.1 manifest/path

- 成功したembeddingファイルをatomic保存・検証してから、そのentryへpathを設定する。
- missing-only早期return、一部成功、全件失敗、shard空/失敗、再実行をテストする。
- shard抽出とmanifest確定を分け、未完了shardのpathを成功扱いにしない。
- dataset相対pathの基準を統一し、per-speaker/per-utteranceをdataset directory外から実行して検証する。
- `output_dir`を反映し、custom directoryへ保存したpathもdataset loaderから解決できるようにする。

### 5.2 cache

- keyに音声hashまたは一意の相対pathを含め、`a/foo.pt`と`b/foo.pt`の衝突を防ぐ。
- metadataにencoder/model SHA、入力hash、前処理version、resampler、chunk/pooling設定を保存する。
- 空/破損ファイル、shape異常、NaN/Inf、ゼロnorm、metadata不一致を再利用しない。
- 旧cacheの移行はdry-runで対象件数と再抽出量を表示してから実施する。自動で全cacheを削除しない。
- `--workers`は動作を実装するか未対応値を明示的に拒否し、無言のno-opをなくす。

### 5.3 入力validation

CLI、JSONL per-utterance、Python Voice、HTTP、training loaderで同じ検証仕様を使う。
次元はgraph/encoder契約に合わせ、legacy 256次元graphとCAM++ 192次元graphを混同しない。
caller embeddingのshape、finite、normを確認し、有効な参照vectorの正規化方針を統一する。
参照なしfallbackのゼロvector＋mask=0と、不正なcaller vector＋mask=1を区別する。

### 完了条件

監査probeで確認した各不具合の回帰テストが成功する。
正しい旧入力、speaker-IDモデル、参照なしfallback、既存ONNX入力schemaの互換性を確認する。
修正後dataset manifestの全embedding参照が存在し、契約に適合する。

## 6. 工程3: 評価経路を修正

- 固定WandB textに固定参照WAV/embeddingを対応付け、非ゼロの話者条件がinferへ渡ることをテストする。
  参照未設定のゼロ条件音声は、その条件を明示して記録する。
- reconstruction validation lossは用途を明記して残す。
  **予測F0・予測duration・実参照embeddingでの推論評価**を別経路で追加する。
- KL guard等のtraining状態をevaluationが変更しないことを確認する。
- CER score CLIへstrict mode、または独立のgate wrapperを追加する。
  pinned manifestとWAV/text IDの一致、missing/余分なclip、最低3文、ASR model/正規化条件を検証する。
- seedだけで全経路が決定的になると仮定せず、carrier noise等の乱数条件・seed・生成artifact hashを記録する。
  必要な複数seed比較は、既存主評価とは別の診断欄で報告する。

### 完了条件

missing clipや参照欠損、n=1のCER結果が正式gateを通過しない。
同じmanifestからTorch/raw、既存EMA、ONNXを比較できる。
ONNX exporterは既存infer共通実装を使い、独自コピーを増やさない。

## 7. 工程4: 既存モデル再評価・学習不要の比較

### 7.1 基準評価

利用可能なv10b/v11 checkpointについて、工程3の固定条件でrawと既存EMAを再評価する。
TorchとONNXの差を確認し、旧評価と新評価で入力条件が異なる場合は別系列として記録する。
既存checkpointの再評価は、過去に無効だったWavLM D学習を回復させるものではない。

### 7.2 参照音声の抽出条件

GPT-SoVITSから参考にする最初の要素は、参照音声処理と参照情報の管理である。

- 同じCAM++/同じ参照WAVで、training chunk poolingとruntime全発話抽出を比較する。
- resampler・fbank・chunk・正規化を共通APIへ寄せる案を準備する。
  学習側のembeddingを変える場合はcache version更新と再学習が必要で、推論だけの変更と分ける。
- 既実装の複数参照平均＋L2を利用し、単一参照/複数参照を同じ総有声時間で比較する。
  二重実装せず、inferへの接続と評価の有効性を確認する。
- 過短、無音中心、clipping等の参照品質情報を記録する。閾値は対象音声で較正してから固定し、
  GPT-SoVITSの秒数制限をPiperへ無検証に強制しない。

### 完了条件

固定baseline JSON/WAV/manifest、extractor仕様、追加学習候補、計算量の見積りが揃う。
実encoderでの品質比較を行い、fake encoderの差を改善量の根拠にしない。

## 8. 工程5: 機械smoke → 原因分離 → v11b候補

### 8.1 機械smoke

工程1〜3の修正、監査済みdataset、同じ生成器構造で基準recipeを固定する。
まず100〜300 training batch程度を上限とするfull-model smokeを計画し、実測で費用を見積もる。
G/D/WavLM更新数、head重み変化、module別grad、SCLの実encoder/positive数/fallback、
F0予測率、非有限skip、save/resume/exportを確認する。
DDP/AMPは使用予定の設定で追加確認する。
この短いsmokeではCER/自然さの到達を要求せず、学習機構の成立だけを判定する。

### 8.2 修正後基準runと単一要因比較

旧不具合を含むrecipeを再学習せず、**修正後コードを全arm共通の基準**にする。
旧v11ログは歴史的比較であり、公平な同時A/Bとは扱わない。

| arm | 基準から変える要因 | 狙い |
|---|---|---|
| C | なし。v11相当recipe＋確定バグ修正＋検証済み入力 | 正常化した学習の経過を測る |
| W | WavLM寄与のみ`c_wavlm=0` | 正しく更新されるWavLMの有効性/競合を分離する |
| A | 生成器への話者敵対lossのみ`c_adv_spk=0` | classifier圧力の影響を分離する |
| F | F0予測切替開始のみ10→20epoch、ramp10/max0.5は維持 | teacher forcing切替との交絡を分離する |

arm Wはloss寄与を切る比較であり、module削除/前処理/他のloss係数を同時に変えない。
zero係数で実装上の副作用が残るかもsmokeで確認する。
arm A/Fも意図した一因子だけ変わることを、実hparamsとactive pathのログで確認する。

まずCを実行する。pilot上限は**30epoch案**とし、ep9/15/19/25/29を評価節目にする。
実際のGPU時間・上限は事前登録時に決定する。R3等の異常停止は継続する。
Cの更新/grad/品質経過に応じてW→A→Fのうち必要なarmを順に選び、全armを無条件に走らせない。
比較armは同じdataset/hash、初期seed、batch順、学習上限、評価条件を使いfrom-scratchで行う。
旧ep19からのwarm resumeは診断に限定する。

「ep15相当でramp凍結」は現行上限と同じため実験armにしない。
predicted F0率を1.0へ増やす案は、切替遅延とは別の後続実験にする。

### 8.3 本走とEMA

pilotで機構が正常なら、選定recipeを既存の80epoch案まで延長するか、
同recipeで本走するかをoptimizer/data状態と再現条件を確認して決める。
早期CER不合格だけではabortせず、既存契約どおりep40以降の昇格gateへ使う。

F0 predictor/projection/prior residualを含む新EMA scopeは、確定バグ修正とは別のopt-in実験にする。
raw/既存extended/新scopeを同じ学習run・同じ評価条件で比較し、旧scopeを自動変更しない。
旧checkpointから未蓄積F0 EMAを捏造せず、scope/version/更新回数を保存する。

### 完了条件

CAM++とheld-out ECAPA、CER、音響gate、export、CPU性能と人手試聴で採否を決める。
不合格の場合は「未達」と記録し、データ増量やv12へ進む原因判断に使う。
品質gateを下げて採用しない。

## 9. 工程6: v12の参照系列入力

GPT-SoVITSから借りる主な構造は、global speaker vectorとは別に実参照音声の時間系列情報を渡すこと。
CAM++192次元を維持しつつ、小さな参照encoderから固定K個のstyle tokenを作り、
encoder/decoderのconditioningへ渡す案を設計する。

- 参照tokenは実WAV/mel系列から抽出し、既存vectorをK個へ展開するだけの案と区別する。
- reference/targetの別発話ペア、情報リーク回避、推論時の参照cacheを定義する。
- K、token次元、注入位置は小規模な単一要因実験で絞る。
- 同等のモデル規模を持つglobal-only対照を置き、容量増加と参照情報の利得を分離する。
- ONNX入力、schema/version、runtime対応範囲、モデルサイズ、CPU速度予算を学習前に決める。
- CFM/大型semantic predictor/新vocoderの移植は、軽量参照token案の結果を見て別研究として判断する。

新契約の予算は事前登録し、既存40MB/+10% gateの事後緩和として扱わない。
GPT-SoVITSでの公式SIM改善量をPiperの期待改善量に転用しない。

## 10. 評価条件と費用の確認点

[zs-eval-contract](../spec/zs-eval-contract.md)の閾値・定義・基準セットを維持する。

- cross-utterance SECSをCAM++/held-out ECAPAの両方で測り、ceiling/floor、正規化転写率、
  same/cross gap、Goodhart/above-ceiling flagを報告する。
- raw出力でcomb/band、comb-HNR、F0/energy/話速の記述統計を測る。
  登録済みコム<1.5dB、autocorr<0.05、voiced棚≤+2dB等を維持する。
- CER median≤0.30、固定3文以上、指定ASR/正規化、ep40以降の昇格判定を維持する。
- 既存契約内ではONNX `[1,192]`、FP16≤40MB、pinしたCPUでp50増加≤10%を確認する。
- 学習用CAM++と評価専用ECAPAを分離し、評価統計をloss/rewardへ流用しない。
- 読みの一致・話者類似・自然さ・ノイズを人手で別々に確認する。ASR一致だけで品質承認しない。

工程0〜3はGPUなしで進める。工程4は手元の成果物と計算環境に合わせて実行方法を決める。
工程5/6の有料GPU利用・本走は、候補provider、GPU数、step/epoch上限、実測時間、
費用上限、停止条件、成果物回収先を提示して実行前に確認する。
過去の価格・学習時間を現在の確定見積りとして扱わない。

## 11. 実装単位と着手順

| 順 | PR/commit単位 | 主な対象 |
|---|---|---|
| 1 | training counter・KL状態修正 | `vits/lightning.py`、実Lightning回帰テスト |
| 2 | 抽出manifest/path・cache | `extract_speaker_embedding.py`、dataset fixture tests |
| 3 | embedding入力の共通検証 | `infer_onnx.py`、Python Voice/HTTP、dataset loader |
| 4 | 固定参照・推論評価・strict CER | validation/audio logging、`tools/eval_cer.py`、gate tests |
| 5 | 比較harness・前処理契約・事前登録 | eval CLI、run manifests、training recipe、計測結果 |
| 6 | opt-in EMA scope、v12設計/実装 | それぞれ独立した変更とA/B |

最初に着手するのは**PR1相当: 更新周期とKL監視状態のTDD修正**。
各単位で失敗テスト→修正→対象テスト/CI→意味あるcheckpoint commitを行う。
依存追加が必要ならuvで管理する。feature branchからdev向けPRでレビューする。
大型model/build/DDP検証は対応可能なCIまたは事前に決めたGPU環境へ寄せる。
本計画作成では実装・学習・PR作成・公開は行わず、計画を保存する。
