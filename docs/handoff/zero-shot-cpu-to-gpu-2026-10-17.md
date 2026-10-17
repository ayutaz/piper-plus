# Zero-Shot CPU準備からGPU smokeへの引き渡し

作成日: 2026-10-17。対象は`feat/zero-shot-v8-dataset-scaling`。
CPU評価の実装固定点は`fed7f617ba72827f60216e14dc9ee3ac42036aca`。
本書のGPU操作は**未実行の手順**。今回GPUレンタル・学習・モデル公開は行わない。

## 1. 現在の開始判定

**NO_GO: 実音声・cacheの再配置と来歴検証が済むまでsmokeも開始しない。**
`output/zero-shot-cpu-preparation-20261017/`に読み取り監査、回収物、修復候補、
モデル・参照・ASR/encoderの固定情報を保持している。モデルと大規模データはGitへ入れない。

- 完全版の復元元は隣接backupの`local-demo/dataset.jsonl`（342,855件）。
  checkpoint設定との話者名→IDの不一致は0件、ID最大3,691、実話者3,682名。
  設定の3,692名との差10名はholdoutで、旧holdoutとの話者重複は0件。
  language IDは0〜5と7の7種類で、checkpointのID枠は8（6は未使用）。
  これがv11の300,443件への絞り込み後manifestと同一であるとは認定しない。
- HFから回収した`v9-data/dataset.v9-gated.jsonl`は300,443件で、language IDは0〜5の6種類。
  checkpointの`num_speakers`は3,692だが、当該manifestの話者IDは最大3,797。
  **620件が3,692以上であること自体は不正ではない**。生成器は`emb_g`でなく`spk_proj`を使い、
  実際の`adv_spk_num_classes`は3,798。`__main__.py`もdataset最大IDから分類器枠を確保する。
  `audit-spec-final.json`の3,692上限による620件のinvalid判定は過剰な初期判定で、
  `audit-spec-effective-class-bound.json`では有効な上限3,798へ修正した。
  件数・分類器枠は旧レシピと整合するが、これだけでv11の学習実体と認定しない。
- このHF回収物では旧holdout 1,200件のうち、同じ話者が715件、同じ`audio_path`も715件ある。
  音声実体は未配置のため、音声hashによる全件照合は未完了。
- `dataset-gated-speaker-disjoint-candidate.jsonl`は元IDを保持し、holdout話者715件だけを
  除いた299,728件。元metadataは変更していない。新しい学習subsetの候補であり、
  学習準備完了ではない。7言語完全版から再構築する案とは学習集合が違うため、混同しない。
- 初期の`dataset-repair-candidate.jsonl`は別configへのID振り直しを含むため**不採用**。
  分類器ラベルの意味を変える危険がある。監査履歴として保持し、学習に使わない。
- 学習音声、正規化音声、spectrogram、F0 cacheはローカル未配置。
  旧archiveの342,855 embedding全件は192次元・finite・非零・norm約1を確認した。
  ただし現在の来歴sidecarがなく、無条件に再利用しない。archiveのまま保持している。

データホストで以下を満たした監査JSONが必要:

1. checkpointと`config.json`のsymbol・language対応、および話者ラベルと実分類器の対応を固定。
   話者の人数と最大ID+1を混同しない。`num_speakers`だけで全経路のID上限を決めない。
2. Zero-Shot heldoutはtrainと学習内validationの両方に対し、話者・実音声hashの交差がない。
   学習内validationは同一話者の別発話でもよいが、同じ音声hashを重複させない。
   通常の発話random splitを未知話者heldoutの証拠として扱わない。
   話者名は言語ごとに別人扱いせず、実際の人物IDで照合する。
3. loaderが読む音声・spec・F0の全件配置、shape、finite、長さ対応を確認。
   F0は`use_f0_path=True`のレシピだけで必須。v10bのF0無効レシピに不要なF0抽出を強制しない。
4. CAM++ Torch重みとONNXの系統、音声hash・resampler・fbank・pooling・次元・embedding hashを
   sidecarで認証。来歴不明分はCPUで再抽出する。単にsidecarを後付けして認証済みにしない。
5. 監査の`training_ready=true`に加え、上記shape/長さ・系統の確認を保存する。
   本ツールのファイル存在検査だけでtensor内容すべての正常を保証しない。

## 2. CPU評価の再実行

固定したcheckoutと学習依存を用い、`comparison-final/experiment.json`のpathを実環境へ設定した
**新しいspec・新しい出力directory**を用意する。既存結果を上書きして別実験と混ぜない。
新しい実験の`source_revision`は実行checkoutの`git rev-parse HEAD`に合わせる。
記録済みの比較は上記固定SHAで生成したもの。後続のdocs/CI commit上で再実行する場合も、
既存manifestを書き換えず、新しいrevisionを記録した別実験にする。

```bash
export CUDA_VISIBLE_DEVICES=-1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --no-sync python -m piper_train.tools.audit_zero_shot_inputs \
  --spec audit-spec.json --output audit.json
# 終了コード2はNO_GO。dataset未配置や来歴不明を成功扱いしない。

uv run --no-sync python -m piper_train.tools.prepare_zero_shot_cpu \
  --spec experiment-spec.json --output comparison --stage references
uv run --no-sync python -m piper_train.tools.prepare_zero_shot_cpu \
  --spec experiment-spec.json --output comparison --stage export
uv run --no-sync python -m piper_train.tools.prepare_zero_shot_cpu \
  --spec experiment-spec.json --output comparison --stage generate
```

`evaluate`はSpeechBrain 1.0.3 / hyperpyyaml 1.2.2 / ruamel.yaml 0.18.16 /
sentencepiece 0.2.1を追加した独立metrics環境で実行する。
Windows実行環境は`metrics-env`の`.pth`で既存依存を参照し、`PYTHONPATH`に
`src/python`、`src/python_run`、`src/python/g2p`を明示した。主環境・uv.lockは変更していない。
依存一覧・モデルrevisionは結果directoryに保存する。

```bash
python -m piper_train.tools.prepare_zero_shot_cpu \
  --spec experiment-spec.json --output comparison --stage evaluate
python -m piper_train.tools.prepare_zero_shot_cpu \
  --spec experiment-spec.json --output comparison --stage html
```

大きいcheckpointの繰り返しhash読み取りと、同じcross-real群の繰り返し解析は
`scripts/run_zero_shot_cpu_evaluation.py --spec ... --output ...`で再利用できる。
これは上記`evaluate`だけを実行するdriverで、評価式とASR decodingは変更しない。
file identityが変化した場合は再hashし、終了時にも全対象をcacheなしで再照合する。
成功の証拠は`evaluation-execution.json`の`status=VERIFIED`とbaseline hash。
今回の独立した参照3条件は、同じevaluatorを呼ぶ別CPU processでも並行計算した。
その実行元hashと全対象の再照合は`reference-lane-execution.json`に記録し、
最終的な全12条件の比較・判定はcanonical runnerで集約する。

CAM++はCPUExecutionProvider、ECAPAはネイティブSpeechBrain waveform frontend、
Whisper-smallもCPU。ECAPA ONNXのCAM++ fbank流用はネイティブcosineが0.903/0.936に留まり、
今回の正式比較には採用しない。torchaudioの廃止APIをSpeechBrainがprobeするため、
評価プロセス内だけで`list_audio_backends -> soundfile`互換処理を使う。

参照比較は20ms RMS活動frameを4.8秒に一致させる。言語的な有声時間の保証ではない。
元発話とcropの両方をcross-realから除き、同一内容hashの別名も除外する。
floorは利用可能な日本語別話者候補のCAM++類似度から事前固定する。
候補が限られるため母集団で較正したfloorではない。

## 3. 学習レシピと再開方式

CPU比較で読むcheckpointはv10b ep79、v11 ep9、v11 ep19。機械的な最高指標だけで
継続元を決めず、CER・独立ECAPA・音響指標と試聴を照合する。
今回の全12条件ではv11の改善を支持しなかったため、初回の回復smokeは
v10b ep79のraw checkpointを継続元候補とする。旧optimizer/EMA履歴は継承せず新runを開始する。
既存EMAはCPU比較の評価対象であり、raw warm restartへ暗黙に混ぜない。
各checkpointの実hyperparametersを`recipe-candidates/`へ保存し、
回収した`v11_train.sh`をそのまま実行しない。

`scl-cpu-differentiability.json`では実CAM++重みを読み、Torch/ONNX cosine=1.0、
入力音声へのfinite/nonzero勾配、encoderパラメータの凍結を確認した。
`wavlm-cpu-preflight.json`では、既存cacheの固定snapshotから実WavLM teacherをCPUで読み、
1秒音声のforward（13 hidden states、幅768、finite）を確認した。
remoteでも同じsnapshotと各ファイルSHAを先に配置し、別のmain revisionを暗黙downloadしない。
これらはencoder/teacher単体の確認で、full-modelの更新・GPU/AMP確認を代替しない。

WavLMは現実装が`microsoft/wavlm-base-plus`を名前で読むため、smoke専用の
`HF_HUB_CACHE`に`models--microsoft--wavlm-base-plus/snapshots/<固定SHA>/`の実ファイルと
`refs/main`（内容は`wavlm-cpu-preflight.json`のrevision）を配置する。
`HF_HUB_OFFLINE=1`と`TRANSFORMERS_OFFLINE=1`で起動し、CPU loadを先に確認する。
ユーザーのHF認証ファイルをcache転送物へ含めない。ASRも固定revisionのsnapshotを保持する。

新runの必須設定:

| 項目 | 設定・検査 |
|---|---|
| ソース・環境 | 検証済みGit SHA、uv.lock SHA、実行script SHA、Torch/CUDA/driverを固定。container使用時はdigestも固定 |
| 継続元 | checkpoint SHA256を照合。モデル構造・条件付け・F0・carrier等は該当hyperparametersと一致 |
| 再開 | 旧checkpointには新batch scheduleがないため`--resume-weights-only`で新run。epoch/optimizer/LRを引き継いだと扱わない |
| SCL | `--strict-zero-shot --spk-loss-type infonce --spk-loss-positives cross_utt --speaker-encoder-torch-path ...`、`c_spk>0`。`use_zero_shot=True`はモデルhparamで、`--use-zero-shot`というCLI flagはない |
| 正例 | `--samples-per-speaker 4`、batch sizeは4の倍数、最低2話者。各anchorに別発話正例。重複発話・fallbackは0 |
| 分散 | 本学習がDDPなら`--spk-loss-gather`を使用。全rankの実metadataと勾配を検証 |
| WavLM | 実teacherを固定し、無効化しない。`--c-wavlm`と`--wavlm-every-n-steps`を明示 |
| 更新 | `--d-update-interval 1`、G/DおよびWavLM Dの実更新を計測。batch数とLightning global_stepを混同しない |
| 推論 | 固定参照を使用、GT F0/durationなし、raw/既存EMA/fresh ONNXを同条件で比較 |
| 変更範囲 | F0込みEMA、新しい参照系列モデル、参照処理の本番default変更はこのsmokeに混ぜない |

旧重みのwarm restartは`strict=False`なので、missing/unexpected keysを全件レビューする。
想定外のencoder、decoder、言語embedding等の欠落をwarningのまま続行しない。
新scheduleを含むsmoke checkpointからの2回目以降は、同じモデル・設定の
`--resume_from_checkpoint`を使う。両resumeオプションは併用しない。

最初のsmoke候補は、元の話者IDを維持する6言語speaker-disjoint subsetとする。
7言語完全版へ切り替える場合は別実験として扱う。分類器のlabel対応が違う場合、
形状が同じでも旧分類器重みを継承しない。headサイズが違えば`strict=False`でも
size mismatchは無視されないため、明示的な分類器再初期化・較正を準備してから進める。
本作業ではその別実験のweight変換や学習は行っていない。

## 4. 100〜300 batchのsmoke計画（未実行）

`recipe-candidates/*-smoke-A.args.json`に、各checkpointの実hyperparametersを反映した
100 batch用CLI引数を保存済み。3件とも`create_parser().parse_args(...)`を通している。
その証拠は`gpu-smoke-recipe-preflight.json`。`grad_probe_every=25`を明示する。
remoteのdataset/model/output pathは意図的に固定placeholderなので、配置とSHAを合わせる。
引数の構文成功をモデル構築・学習成立の証拠にしない。
モデル構築後のhparams・読み込みkeysも保存する。
未解決のデータ系統や、任意のデフォルト係数を残したまま起動しない。
epoch数を縮めた本走ではなく、`--limit-train-batches`で**受信batch数**を制限する。

`gpu-handoff/test_utterances.jsonl`と`fixed-reference.npy`も用意済み。
検証済みの新smoke dataset directoryへ配置し、`gpu-handoff/manifest.json`のhashを照合する。
既存の監視入力は別途保存する。これにより学習中のサンプルもゼロ話者条件にしない。
モデルの`_parse_test_utterances`が読むのは`dataset_dir/test_utterances.jsonl`であり、
架空の参照用CLI flagを追加しない。

| 段階 | 起動時の追加設定 | 期待する証拠 |
|---|---|---|
| A: 100 batch | `--accelerator gpu --devices 1 --precision bf16-mixed --limit-train-batches 100 --max_epochs 1 --checkpoint-epochs 1 --save-top-k -1 --resume-weights-only <旧ckpt>` | 実encoder/WavLM、finite loss/grad、G/D更新、保存、新schedule、固定参照の生成 |
| B: 追加100 batch | Aと同じ設定。旧resumeを外し`--resume_from_checkpoint <Aの最新ckpt> --max_epochs 2` | batch時計100→200、G/D更新・optimizer moments・EMAの継続。Aの新scheduleをstrict復元 |
| C: DDP 100 batch | 次の本学習が複数GPUの場合だけ。別出力の新runとして`--devices 2 --spk-loss-gather --max_epochs 1 --limit-train-batches 100 --resume-weights-only <固定元ckpt>` | 各rank別発話正例、all_gather、rank間clock一致、全rank失敗時の終了、分散下の更新 |

本学習が1 GPUならCを不要と明記し、200 batchで切り上げる。
bf16非対応GPUを選んだ場合は32-trueで別条件として記録し、bf16検証済みとしない。
最初の25 batchは起動・cold速度・メモリのsanityにのみ使う。
cuDNN探索の影響があるので、この短いsmokeから定常速度・費用を外挿しない。
定常比較が必要なら同一processの300 batch以後の窓を別途計測する。

合格条件:

- 起動後30秒のログで次の処理へ進んだことを確認。実SCL/WavLM/参照設定が有効。
- 全anchorの`strict_scl_min_positives>=1`、`strict_scl_fallbacks=0`。
  loss/gradにNaN/Infなし。G/D更新数と既定間隔が対応し、WavLM Dの重みが実際に変化。
- checkpointの`training_schedule_state`、G/D optimizer state、既存EMAを保存・復元。
  再開後のbatch clockが巻き戻らず、過去checkpointを誤選択していない。
- 固定文3件以上をraw/EMA/fresh ONNXで生成し、実CER、dual encoder、音響指標、試聴資料を回収。
  新runのepoch 0〜1はCER昇格gateのepoch>=40を満たさない。smoke成立とモデル昇格を分ける。
- 独立encoder悪化、読めない音声、極端な無音・clipping等があれば、本走へ進む前に原因を切り分ける。
  旧評価値と定義が違う場合に、旧watchdog閾値をそのまま適用しない。

即時停止条件: データ／hash／hparams不一致、想定外weight欠落、SCL無効化、正例不足、
nonfinite、継続的な更新skip、WavLM D未更新、OOM、参照未設定、保存／復元不成立。
停止理由は指標名・値とともに中央markerログへ記録する。

## 5. 起動・保存・停止の運用

[remote-train-ops](../../.claude/skills/remote-train-ops/SKILL.md)の運用条件を使う。
shellは`set -euo pipefail`、ERR/EXIT trapで失敗markerを残す。
checkpoint、JSON、音声、script、環境、監視ログ、TensorBoardを同じrun IDで関連付ける。
重要な完了待ちは実PID・exit code・最新起動以後のDONE/FAILEDを照合し、
古いmarkerや通知だけで稼働状態を判定しない。監視経路には試験markerを流して検知確認する。

停止／destroyの前に、running中に成果物を回収し、転送元・転送先SHA256を照合する。
smokeの機械的検査と保存/再開、固定音声・export、成果物回収を済ませた後は、
長いCPU ASR評価や人手試聴を待つためにGPUを遊休させない。
A/Bの200 batchと必要なDDP確認を回収してGPUを停止し、残りのCPU指標をlocalで集計する。
その判定が済むまで本学習を開始しない。再起動後のcold/warm条件は分けて記録する。
外部保存先へのuploadは、その時点のユーザー承認・研究用の公開範囲に従う。
`last.ckpt`だけでなく`last-v1.ckpt`等もmtime/内部epoch/clock/hashで確認する。
異常終了時はtrain・eval・watchdog・uploader・中央markerを横断して原因を調べ、blind resumeしない。
停止後はproviderのactual/intended statusとqueued startを照合する。

未検証のままGPUへ引き渡す事項は、実勾配、AMP、DDP、更新時計、保存／再開、速度・VRAM、
人手による品質判断。これらはCPUテスト成功から推定しない。
