# GPT-SoVITS参照候補とZero-Shot学習準備の再監査

調査日: 2026-10-17 (JST)。Piper対象: `feat/zero-shot-v8-dataset-scaling`、
`29d8065f87176577c32bbb4e4b63339793abb6cc`。
本書はこのSHAでの監査記録。後続の実装・CPU実測・不足物は
[CPU準備・実測記録](zero-shot-cpu-preparation-2026-10-17.md)を参照する。
今回は公式ソースと既存実装の照合、保存物の読み取り、状態判定を実施した。
モデル・学習コードの追加実装、追加学習、GPUレンタル、品質比較は実施していない。

## 1. 結論

**「参考にできるものをすべて取り込み済み」「残りは本学習だけ」のどちらも未達。**
既存構造の学習・入力・評価の不具合修正は進んでいるが、GPT-SoVITSにある参照音響系列の
利用は未実装。実データの監査、修正後ソースでの基準評価、実モデルの学習smokeも残る。
テスト成功は経路・互換性の証拠であり、実モデルの話者類似度向上の証拠ではない。

新しい参照系列モデルは別実験として扱う。現行構造の修正効果を測る基準実験まで、
すべての新アーキテクチャ案の実装完了を待つ必要はない。

## 2. 上流の現在地と調査範囲

GitHub APIで確認した最新mainは
[`1b47ca07ef43a284e0b8bd7f29d3e1e3ff76082a`](https://github.com/RVC-Boss/GPT-SoVITS/commit/1b47ca07ef43a284e0b8bd7f29d3e1e3ff76082a)。
commit日時は2026-10-08 16:27:04 UTC。
これは[前回調査](gpt-sovits-zero-shot-2026-10-09.md)の固定SHAと同じ。
最新正式releaseも[`20250606v2pro`](https://github.com/RVC-Boss/GPT-SoVITS/releases/tag/20250606v2pro)で同じだった。
mainにはV5の`v5dev` / `v5turbo`がある。正式releaseとmain上のモデル系列を区別する。

今回、当該SHAのtree一覧を取得し、VITS/CFMモデル、参照処理、推論、AR dataset、
学習・LoRA、設定、exporter、LICENSEの20ファイルを固定取得した。
上流重みはdownloadしておらず、上流の品質・速度を再現した調査ではない。
全ファイル・全将来案の有効性を保証するものではなく、下表はこの範囲での候補台帳。

取得ソース・URL・SHA256は`output/gpt-sovits-audit-20261017/source-manifest.json`、
treeは同directoryの`tree.json`へ保存した。ライセンスファイルはMITだが、
将来ソースや重みを取り込む場合は対象物ごとに出典・依存・許諾を確認する。

## 3. 参考候補と実装状況

「既存」は以前からPiperにある機能。「修正済み」はPiper側の修正であり、
GPT-SoVITSのコードを直接移植したという意味ではない。

| 候補 | 上流・ローカルの根拠 | 現在の判断 |
|---|---|---|
| global話者特徴と参照音響特徴の併用 | 上流`module/models.py`の`ref_enc`と`sv_emb` | 未実装の構造候補。CAM++への単純な差し替えではない |
| 実参照の音響系列・melによる条件付け | 上流`models_v5.py`の`reference_features` / `reference_mel` | Piperのv12候補。小型参照encoder・style tokenの実装と対照実験は未着手 |
| semantic prompt、HuBERT/VQ、GPTの二段構成 | 上流`TTS.py`とARモデル経路 | 現VITSへの部分追加では成立しない。別モデル研究として保留 |
| 長文で元参照と直前chunkの文脈を保持 | 上流`models_v5.py`の元参照＋32frame tail | 未実装。Piperの長文で症状を確認してから実験する |
| 複数参照の平均 | 上流`models.py`の参照埋め込み平均、Piper`extract_from_files` | 抽出helperは既存。全CLI・評価への複数参照接続は完了していない |
| 参照のmono化・resampling・正規化 | Piper`extract_speaker_embedding.py` | 既存。上流の3〜10秒制約をPiperへそのまま移さない |
| 無音・有声時間・clipping・異話者混入の参照検査 | 前回調査§4.2、工程4C | 品質条件を較正した実比較は未実施 |
| runtime全長抽出とtraining chunk poolingの統一 | Piperの単一`session.run`と400frame pooling | 分布差が残る。実encoder・実WAVでの比較と採否は未実施 |
| 入力/cacheの来歴・破損・衝突検査 | `embedding_cache.py`、`embedding.py`、抽出・loader | 修正済み。実学習dataset全量を通した監査は別途必要 |
| 音声・テキスト長とphoneme/秒の事前検査 | 上流`AR/data/dataset.py` | Piperの言語・韻律記号に合わせた全データ監査は未完了。上流閾値3〜25はコピーしない |
| 固定参照を使った推論監視 | Piper`lightning.py`、`inference_eval.py` | 修正済み。ゼロ条件サンプルと参照話者評価を区別する |
| 予測F0・durationでのraw/EMA/ONNX比較 | `inference_eval.py`、`evaluation_manifest.py` | 機能実装済み。固定実モデル群の基準評価は未完了 |
| strict CERと入力集合・hashの固定 | `strict_cer.py`、`evaluation_manifest.py` | 実装済み。実ASRを含む正式基準評価は未実施 |
| 学習clockとG/D/WavLM/EMA更新の整合 | `training_batch_schedule`仕様、`lightning.py` | 修正済み。full-model GPU/AMP/DDP smokeは未完了 |
| F0関連モジュールを含めたEMA | `ema.py`のextended対象はflow/enc_p/spk_proj_dp | F0込みscopeは未実装。raw/現EMAの基準評価後に独立比較する候補 |
| 微分可能な話者lossとcross-utterance正例 | Torch CAM++、SupCon、DDP gather | 既存。厳格な学習レシピの事前guard・実batch検査は未完了 |
| BF16、勾配制御、bucketing、freeze、EMA等の学習運用 | 上流trainerとPiperの既存trainer | 多くは既存。新規取り込み済みの改善として重複計上しない |
| LoRAによる小規模FT | 上流`s2_train_v3_lora.py` | モデル構成に依存。現VITSへ無条件に追加する対象にはしない |
| CFM、CFG、turbo蒸留、sampling step削減 | 上流`CFMV5` | 現VITSには同じsampling loopがない。CFM等を採用する別実験で扱う |
| CUDA Graph、static cache等の高速化 | 上流V5推論経路 | GPU/対象モデルに依存。CPU/ONNXの利得として未検証のまま採用しない |

上流コードの例:
[V2Proの参照条件](https://github.com/RVC-Boss/GPT-SoVITS/blob/1b47ca07ef43a284e0b8bd7f29d3e1e3ff76082a/GPT_SoVITS/module/models.py#L913-L1018)、
[V5参照系列・chunk保持](https://github.com/RVC-Boss/GPT-SoVITS/blob/1b47ca07ef43a284e0b8bd7f29d3e1e3ff76082a/GPT_SoVITS/module/models_v5.py#L7-L84)、
[AR dataset](https://github.com/RVC-Boss/GPT-SoVITS/blob/1b47ca07ef43a284e0b8bd7f29d3e1e3ff76082a/GPT_SoVITS/AR/data/dataset.py#L146-L170)。

## 4. 学習開始前に残る具体的な点

### 4.1 学習設定が意図した経路に届くこと

`lightning.py`は`--speaker-encoder-torch-path`のファイルがなければwarning後に
微分可能SCLを無効化する。`cross_utt`でもspeaker IDsがなければsame-uttへfallbackする。
`losses.py`もcross-utterance正例がないbatchではsame-uttへfallbackする。
一般の学習・FT互換と、Zero-Shot研究レシピでの必須条件を分け、後者では重み・正例数・
有効な勾配・fallback数を開始前とsmokeで検査する必要がある。
これが過去v11の品質低下の原因だったとは、この静的監査からは断定しない。

### 4.2 複数参照を使う評価経路

`eval_zs_secs.py --exclude-ref`は単一pathを受け取り、当該path/hashをcross集合から除外する。
抽出helperの複数参照平均を使う際は、全参照path/hashを除外する接続が必要。
現在の単一参照評価を、複数参照でも完全な漏れ防止が実装済みと扱わない。

### 4.3 実入力と基準評価

保存物の存在確認結果を`output/gpt-sovits-audit-20261017/local-inventory.json`へ保存した。

- v11 ep9/ep19のcheckpointとONNXは存在する。
- 隣接backupにv10b ep79 checkpoint/ONNXとCAM++ ONNXが存在する。
- ローカルdatasetsにはつくよみちゃん生WAV100件とFT用JSONLがある。
- 旧参照embedding 3件は192次元・finite・norm約1で、今回SHA256も記録した。
  抽出元音声・encoder/前処理の来歴を認証したものではない。
- checkpoint内部設定・全モデルhash・ECAPA/ASR revision・floor/held-out集合・
  学習dataset全量のpath/hash/cache整合を固定した実験入力は未完成。

FT用directoryにraw WAVがないことだけで欠損とは判定しない。前処理cacheや外部pathを
含めたloader入力の監査が必要。remote学習環境の現在のdataset配置・認証は今回未確認。
過去のVast.ai 401記録を現在の接続状態と断定しない。

### 4.4 GPU学習と品質

過去の小型CUDAモデルの監視・export確認と、full-modelでの学習成立を分ける。
full-modelで実WavLM/SCL・AMP・G/D更新・保存/再開・exportが成立するsmokeは未完了。
旧checkpointの新scheduleへのstrict resumeには制約があり、旧重みから新runにする場合は
既存の`--resume-weights-only`方針を使い、optimizer/clockを継承したと扱わない。

直前のリベース検証では学習/評価280 passed・8 skipped、補助ツール34 passed・1 skipped、
runtime51 passed、計365 passed・9 skipped。今回はこれを再実行した結果ではない。
これはGPU本学習、実ASRでの基準評価、人手品質評価の完了を意味しない。

## 5. 次の順序

1. **工程0を完了**: モデル・encoder・参照・実発話/floor・学習/holdout・cacheを固定し、
   不足、話者/音声hashの交差、来歴不明cacheを一覧化する。
2. **既存構造の必須guardを補完**: Zero-ShotレシピのSCL/positive条件、
   複数参照を使う場合の全参照除外を検証する。
3. **工程4を完了**: 同条件のv10b/v11 raw・現EMA・現export ONNXを比較し、
   実ASR/dual-encoder/音響指標と試聴資料を用意する。参照抽出条件も比較する。
4. **工程5のsmoke**: 確定した修正後レシピを学習先で100〜300 batch検査する。
   更新・勾配・AMP・保存/再開・exportと成果物回収を確認してから本学習へ進む。
5. **独立した研究実験**: F0込みEMA、参照crop、v12参照系列を一因子ずつ比較する。
   実装前に入力契約・配布サイズ・CPU予算とglobal-only対照を決める。

現状は**本学習の開始可と判定できない**。必要な作業順は
[工程0/4計画](../design/zero-shot-stage0-4-tdd-plan-2026-10-10.md)および
[改善計画](../design/zero-shot-recovery-and-improvement-plan-2026-10-09.md)と整合する。
