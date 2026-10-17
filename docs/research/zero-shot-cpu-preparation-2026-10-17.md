# Zero-Shot改善のCPU準備・実測記録

日付: 2026-10-17 (JST)。対象branch: `feat/zero-shot-v8-dataset-scaling`。
モデル生成・評価実装の固定点: `fed7f617ba72827f60216e14dc9ee3ac42036aca`。
[GPT-SoVITS候補監査](gpt-sovits-readiness-audit-2026-10-17.md)の後続実作業。
GPUレンタル、本学習、公開モデル更新、pushは実施していない。

## 1. 対象と状態

依頼されたCPU作業は、(1)入力固定、(2)データ/cache監査、(3)必須guard、
(4)参照処理比較、(5)実checkpoint基準評価・試聴資料、(6)GPU引き渡しの6項目。
全12条件のCPU評価と集計を完了し、試聴・GPU引き渡し資料を用意した。
CPU準備の完了を、品質改善・学習開始可・公開可の判定と混同しない。

検証物は`output/zero-shot-cpu-preparation-20261017/`に保存する。
正式比較は`comparison-final/`。`comparison/`は初期試行で、ネイティブECAPAの
出力shape不一致を修正する前の結果を含むため、正式結果と混ぜない。

## 2. 入力固定・実モデル読み込み

| 入力 | epoch | checkpoint SHA256 |
|---|---:|---|
| v10b | 79 | `c3a6019f983726284c278744814a1aa992c0df36c257cb6dfa62a78bc746f5c0` |
| v11 | 9 | `4ed939e9458a97ebc10dc33a754fbfc9d79520f1a68cd923c05869b7fb730904` |
| v11 | 19 | `cf6317a559e18919a0ed76a10affb27621fbffbf82af4e01a48ace9f0ed8314b` |

3 checkpointは185 symbols、sample rate 22050、8 language-ID枠、192次元CAM++条件。
既存EMA shadowを持つ。設定上のlanguage mapは7種類（0〜5と7、6は未使用）。
新しいtraining batch scheduleは持たず、旧optimizerの継続を認証できない。

Linux保存checkpointの`PosixPath`がWindowsでloadできないため、
`checkpoint_io.load_checkpoint`にpickleクラス解決時だけnative Pathへ変換する処理を追加。
`pathlib`や`torch.load`をglobalに置換しない。信頼済みlocal checkpoint専用。
実checkpoint3件のCPU generator読み込みと、現行共有`build_infer_forward`による
新規ONNX export、checker、shape inference、CPUExecutionProvider推論に成功。
exportのONNXは**既存EMA**、Torchはrawと既存EMAの両方を比較する。

encoder/ASRの固定:

| 対象 | revision / identity |
|---|---|
| CAM++ ONNX | SHA256 `a6ac6a63997761ae2997373e2ee1c47040854b4b759ea41ec48e4e42df0f4d73` |
| Torch CAM++ | `funasr/campplus@e4b6ede7ce16997aff4ae69fbca1f0175e2afede` |
| 独立ECAPA | `speechbrain/spkrec-ecapa-voxceleb@0f99f2d0ebe89ac095bcc5903c4dd8f72b367286` |
| ASR | `openai/whisper-small@973afd24965f72e36ca33b3055d56a652f456b4d`、日本語、CPU |

全ファイルhashと依存版は`environment-model-provenance.json`、
追加metrics環境は`metrics-environment-freeze.txt`に保存。
overlayを含む全169 packageの版は`installed-package-versions.json`、
実ASR pipelineの既定値（beam 5 / max_new_tokens 256）とsource hashは
`asr-execution-policy.json`へ保存した。実行途中で探索条件を変えていない。
主環境とuv.lockは変更していない。

## 3. データ・cache監査と修復候補

元データ・旧評価物を変更せず、読み取りで全件監査した。

| 対象 | 確認したこと | 判定 |
|---|---|---|
| 完全版local backup | 342,855件、3,682話者、ID最大3691、設定の名前→IDとの不一致0、旧holdoutとの話者重複0 | 7言語の復元元。v11絞り込み後と同一とは未証明 |
| HF回収v9-gated | 300,443件、3,734話者、ID最大3797、6 language IDs、旧holdoutと6話者/715件の同じaudio path | そのままheldout品質評価に使わない |
| 旧embedding archive | 342,855件すべてshape=(192,), finite, nonzero、norm 0.99999988〜1.00000012 | 数値形式正常、抽出来歴未認証 |
| 学習cache実体 | 正規化音声・spec・F0・音声本体の参照先は未配置 | 全件hash漏洩検査と学習ready判定は未達 |

話者IDの注意: checkpointの`num_speakers=3692`は、この構造のlabel上限ではない。
生成器は`spk_proj`を使い、実分類器は`adv_spk_num_classes=3798`。
`__main__.py`もdataset最大ID+1から分類器枠を確保する。
初期監査の620件の範囲外判定は上限を3692と置いた過剰判定だったため、
`audit-effective-class-bound.json`では3798を使い、invalid records=0へ修正した。
旧`audit-final.json`は途中経過として保存している。

`dataset-gated-speaker-disjoint-candidate.jsonl`は元IDを維持してholdout話者715件を除き、
299,728件にした新subset候補。完全版7言語とは別の学習集合。
最初に別configへIDを振り直した`dataset-repair-candidate.jsonl`は**不採用**。
分類器labelの意味を変えるため、学習には使わない。
来歴不明cacheにsidecarを後付けして認証済みにせず、原音から再抽出する。

監査の根拠: `audit-aligned.json`、`audit-effective-class-bound.json`、
`full-backup-metadata-audit.json`、`metadata-identity-audit.json`、
`legacy-embedding-audit.json`、`gated-speaker-disjoint-repair-report.json`。
どちらの復元案も`training_ready=false`。欠損をGPUの有無と混同しない。
修復subsetも全299,728件を再監査し、invalid records=0、holdoutとの話者重複0を確認。
`audit-repaired-subset.json`は欠損cacheを理由にexit 2（NO_GO）となることを確認した。
不足物の件数・path例・復元順は`missing-inputs.json`にまとめた。

## 4. 学習前guard・回帰検証

- opt-inの`--strict-zero-shot`は、Torch encoder重み不足、非微分SCL設定、
  別発話正例がない実batch、重複発話、不正embeddingを停止する。
  DDPでは全rankのmetadataを集め、peerだけ失敗してcollectiveに取り残されないようにする。
  既存FT/通常学習のdefaultは変えない。
- `eval_zs_secs --exclude-ref`を繰り返し指定できるようにし、
  全参照のpath/hash別名をcross-realから除外する。
  cropの元発話除外はCPU比較側でも明示する。
- 学習→評価metricのimport隔離gateに新guardを追加。
  独立ECAPAと音響指標は学習lossへ導入しない。
- CUDA無効の回帰検証: **260 passed, 2 skipped**。
  2件は実CUDA page-lockとCUDA実checkpoint推論。
  CPUではpin_memoryのフィールド引き継ぎを検査し、OS allocatorを要求する実pin検査と分けた。
- read-only再利用driverは、最終hash再読と入力変更検出の**2テスト成功**。
- `.github/workflows/python-tests.yml`にCPU準備用の明示stepを追加。
  新規のunmarked testsとtestpaths外の`tests/scripts`も実行する。
  CIと同じ選択をCUDA無効で実行し、**68 passed, 1 skipped**（実page-lockのみ）。
  root CIのpath filterも更新した。workflow lintとpre-commitはローカル成功。
  未pushのため、GitHub上のCI実行成功は未確認。
  PyTorch不在もimport blockerで模擬し、新規3 moduleが収集エラーにならずskipされることを確認。

実重みのCPU単体検査:

- `scl-cpu-differentiability.json`: Torch/ONNX CAM++ cosine=1.0、
  入力勾配norm=56.38655、finite、encoder weightsは凍結かつgradなし。
- `wavlm-cpu-preflight.json`: 固定cache snapshotからWavLM teacherをCPU load/forward。
  13 hidden states、幅768、finite。GPUやdiscriminator更新の証明ではない。

## 5. 参照処理比較

つくよみちゃん実WAV001/002を使い、単一参照と複数参照の活動音声を4.8秒へ揃えた。
20ms RMS >= -40 dBFSの**活動proxy**であり、言語的な有声時間を保証するVADではない。
cropは連続区間で内部無音を維持し、gain変更をしない。

| 条件 | 活動時間合計 | crop全長合計 | wholeとchunk400の特徴量cosine |
|---|---:|---:|---:|
| 単一 | 4.8秒 | 6.58秒 | 0.993539 |
| 複数 | 2.4 + 2.4秒 | 4.00 + 3.04秒 | 0.996544 |

runtime frontendを固定し、wholeと学習の`_FbankDataset._to_chunks`（400 frames、
50% overlap、短発話のreflect/pad variant）を比較した。
追加で同じ原音区間を22050 cache→実training loaderの16000 resamplingに通した。
training経路のcosineはruntime whole比0.985448/0.991818、runtime chunk比0.992900/0.994035。
これはpooling以外のresampler差も含むため、単一原因へ帰属しない。

4条件の生成音声はv11 ep19 rawで各3文を保存。
**1話者の比較からruntime defaultを変更しない**。wholeの現行動作を維持する。
結果は`comparison-final/references.json`、`training-reference-frontend-comparison.json`。

## 6. 基準評価・試聴資料

3 checkpoint × raw/既存EMA/fresh ONNX × 3文=27 WAV、
参照処理の追加3条件 × 3文=9 WAV、**合計36 WAV**を生成済み。
22050 Hz、mono float32 raw、seed=42（文ごとに+ordinal）、scales=[0.4,1.0,0.5]。
GT F0/duration、EQ、trim、音量補正は使わない。
Torch/ORTの乱数実装が異なるため同じseedから同じ波形になるとは扱わない。
`raw-waveform-integrity.json`で36件のfinite・非零RMS・形式と振幅を確認。
ep19 / multi-whole / raw / t1には±1超過が10 samples（約0.0104%、peak 1.25608）ある。
float WAVの値を保存したまま評価しており、音量補正で隠していない。

独立ECAPAはnative waveform frontendを用いる。
既存ECAPA exporterのCAM++ fbank流用はnative比cosine=0.903/0.936に留まったため、
この比較には採用しない。legacy ONNX export自体のPyTorch 2.11互換は確認済み。

指標は既存`eval_cer`のstrict入力検査と実Whisper、
`eval_zs_secs.compute_secs_report`のcross/ceiling/floor/normalized transfer、
band/comb/prosody/comb-HNRの既存定義を使う。
conditioning元発話001/002を外し、003〜008の6件をcross-realへ固定。
floorは保存済み日本語別話者2候補から、生成前にCAM++類似度最大の候補を固定する。
匿名speaker IDの2候補に限る診断で、母集団・話者同一性を独立較正したfloorではない。

| checkpoint | backend | CER中央値 | CAM++ cross | ECAPA cross | CAM++正規化転写 | ECAPA正規化転写 |
|---|---|---:|---:|---:|---:|---:|
| v10b-ep79 | torch-raw | 0.1905 | 0.7205 | 0.5999 | -0.1081 | 0.2559 |
| v10b-ep79 | torch-ema | 0.0952 | 0.7165 | 0.5998 | -0.1359 | 0.2554 |
| v10b-ep79 | onnx | 0.0870 | 0.7104 | 0.6001 | -0.1777 | 0.2565 |
| v11-ep9 | torch-raw | 1.5652 | 0.6077 | 0.4051 | -0.8896 | -0.4401 |
| v11-ep9 | torch-ema | 1.3810 | 0.6404 | 0.3959 | -0.6635 | -0.4732 |
| v11-ep9 | onnx | 1.1905 | 0.6053 | 0.4366 | -0.9065 | -0.3277 |
| v11-ep19 | torch-raw | 19.3043 | 0.6228 | 0.4167 | -0.7854 | -0.3989 |
| v11-ep19 | torch-ema | 1.1905 | 0.5608 | 0.3241 | -1.2151 | -0.7295 |
| v11-ep19 | onnx | 1.5714 | 0.6079 | 0.3680 | -0.8887 | -0.5729 |

ceiling/floorはCAM++が0.880298/0.736056、ECAPAが0.808135/0.528286。
正規化転写は負値もそのまま示す。encoder間で生のcosineや転写率を同一尺度とみなさない。
CERは反復・挿入により1を超える。長い認識文も保存し、探索条件や結果を切り詰めていない。

**今回の1話者・3文ではv11の改善を支持しない。** v10bに比べCERと独立ECAPAが悪化した。
同じ3文でのF0 stdもv10bの27.38〜30.29 Hzに対し、v11は6.73〜8.14 Hzと小さい。
cross-realの記述統計は60.93 Hzだが文は異なるため、これとの一致自体を合格条件にしない。
v11の高域過剰指標は同backendのv10b比+4.72〜+10.33 dB。
原因をこの評価だけで特定せず、次の回復smokeはv10b ep79を対照・継続元候補にする。
v11 ep9/ep19はepoch<40で、CER値にかかわらず既存昇格gateの対象外。

| ep19 rawの参照条件 | CER中央値 | CAM++ cross | ECAPA cross |
|---|---:|---:|---:|
| single-whole | 19.3043 | 0.6228 | 0.4167 |
| single-chunks400 | 1.2174 | 0.5848 | 0.3935 |
| multi-whole | 1.1429 | 0.5887 | 0.3697 |
| multi-chunks400 | 1.2857 | 0.5739 | 0.3470 |

参照変更でASRの反復は減る条件もあるが、ECAPA crossはwhole単一の0.4167から
chunk単一0.3935、whole複数0.3697、chunk複数0.3470へ低下した。
この結果からruntime defaultを変更しない。
全12条件でGoodhart flagとabove-ceilingはfalseだが、品質合格を意味しない。
複数参照2条件ではCAM++のsame/cross gapが+0.0321/+0.0229拡大した。
独立encoderの改善がなく、話者転写の改善と報告しない。

全12 groupのCER transcript、dual-encoder、band/comb/prosody/comb-HNRと差分は
`comparison-final/baseline.json`と各`audio/.../metrics.json`に保存。
canonical runnerは243入力をcacheなしで再hashし、`evaluation-execution.json`がVERIFIED。
独立した参照/EMA/ONNX processの記録も保存し、全groupの保存JSONと集計値の一致を確認した。
canonical baseline SHA256は`5ddea714eadd2690a9fff2a4571ab87173315b83cb543ca59fd4016671556ed5`。

`comparison-final/audio-preview.html`はChromeで12行・36 audioを確認し、
全件readyState=4、duration>0、decode errorなし。
これは読込・表示の検証で、人手による声質合格ではない。
最終`index.html`には指標と参照条件・JSON・振幅検査へのリンクを揃えた。
最終ページもChromeで12行・39 audio（生成36＋参照3）を確認し、
全件duration>0、readyState=4、decode error=0。根拠は`browser-verification.json`。
6項目の入力・実測・試聴・引き渡しを`verify-delivery.py`で照合し、
260ファイルをcacheなしで再hashして`completion-audit.json`の全項目PASSを確認した。

## 7. 引き渡しと残る作業

[GPU引き渡し手順](../handoff/zero-shot-cpu-to-gpu-2026-10-17.md)に、
実hyperparameters、構文検査済み3種類のsmoke引数、固定参照の監視入力、
100+100 batch保存/strict再開、必要ならDDP追加100 batch、合格/停止条件、
起動30秒確認、ERR/EXIT marker、回収・hash・actual status確認を記載した。

CPU準備の完了と本学習開始可は別判定。データホストで音声/cacheを復元・認証し、
同じ評価を引き継ぎ、実GPUで勾配・AMP・G/D/WavLM・DDP・保存/再開を確認する必要がある。
F0込みEMAや新しい参照系列モデルはこの作業に混ぜていない。

## 8. 変更したファイルと目的

| ファイル群 | 目的 |
|---|---|
| `checkpoint_io.py`、`tools/generate_eval_audio.py` | trusted checkpointのPath互換とCPUでのraw/EMA生成 |
| `zero_shot_requirements.py`、`__main__.py`、`vits/lightning.py`、`vits/dataset.py` | strictレシピと実batchの別発話正例・識別情報検査 |
| `tools/eval_zs_secs.py` | 複数参照をすべて除外し、全参照hashを保存 |
| `tools/audit_zero_shot_inputs.py` | artifact/dataset/cache来歴・有効ID範囲・不足・重複の読み取り監査 |
| `tools/cpu_reference_comparison.py`、`tools/prepare_zero_shot_cpu.py` | 参照条件固定、fresh export、CPU生成・実ASR/dual encoder/音響評価、HTML |
| `tools/export_ecapa_onnx.py` | PyTorch 2.11でlegacy exporterを明示。前処理不一致は別に検証し、正式評価はnative ECAPA |
| `scripts/run_zero_shot_cpu_evaluation.py`と専用テスト | 同じ入力のhash/音響解析を再利用し、最後に全hashを再読する |
| `scripts/check_zs_metric_isolation.py`、`.pre-commit-config.yaml`、回帰テスト | 新guardも学習と評価の隔離対象に追加 |
| `.github/workflows/ci.yml`、`python-tests.yml`、CPUテスト | markerによる検査漏れを防ぎ、GPUなしの検査とWindows軽量収集を保証 |
| 本書、候補監査への後続リンク、Research index、GPU handoff | 実測・未検証・不足物・次の開始条件を区別して保存 |

上表のPythonファイルは`src/python/piper_train/`配下（テストは`src/python/tests/`）。
model/checkpoint/WAV、大規模metadata、環境と詳細JSONはignored `output/`に保存し、Gitへ含めない。
