# Zero-shot推論評価の入力・生成・CER仕様

更新: 2026-10-10。工程3の機能仕様。
全体の順序は[改善計画](../design/zero-shot-recovery-and-improvement-plan-2026-10-09.md)、
閾値は[評価契約](zs-eval-contract.md)を参照する。
本仕様のCPU/CUDA fixture成功は実装の証拠であり、学習済みモデルの品質承認ではない。

## 1. Training中の音声監視

`VitsModel._load_test_dataset`は固定JSONLの参照embeddingを保持する。
`speaker_embedding`の明示vectorを優先し、未指定なら`speaker_embedding_path`のnpyを読む。
相対pathの基準はそのJSONLの親directory。有効な参照は共通validatorで検証・L2正規化する。
欠損、不正vector、参照conditioningを使えないモデルでの明示参照は設定エラーとする。
旧entryに参照指定がなければ既存の無参照条件を維持する。

`on_validation_epoch_end`は`model_g.infer`で予測duration/F0から生成し、GT F0/durationを渡さない。
固定prosody情報がある場合は`[1,T,3]`のint64で渡す。
既存のreconstruction validation lossとは用途を分け、KL guard・training clockの契約を維持する。

推論はeval/no_grad内で行い、終了時には各moduleの混在したtrain/eval flag、
Torch CPU/使用CUDA device、NumPy、PythonのRNGを復元する。例外時も復元する。
この経路はoptimizer、EMA更新callback、DINO teacher/center更新を呼ばない。
DDPの既存rank0監視と全rank barrierは維持する。
既存のメトリクス隔離gateは共有`inference_eval.py`もtraining scopeとして検査し、
CERのimportを禁止する。CER側のTorch/VITS importも禁止し、WAV検査には既存SciPy依存を使う。
helper/CERだけの変更でもpre-commitの隔離gateが動く。

WandB音声は従来の表示用振幅正規化を維持し、captionへ`display-normalized`を付ける。
参照指定は`zero-shot`、参照なしzero vectorは`no-reference`と記録する。
正式評価用のraw WAVは次のoffline CLIで生成する。

## 2. 固定入力JSONLとmanifest

固定JSONLの例（1行を1entryとする。strict CERには最低3entry必要）:

```json
{"id":"t0","text":"こんにちは","phoneme_ids":[1,10,10,2],"language_id":0,"speaker_embedding_path":"refs/reference.npy","reference_audio_paths":["refs/reference.wav"]}
```

- `id`: 一意なASCII英数字から始まり、英数字、`_`、`.`、`-`だけを使う。WAV名へ使う。
- `text`、非空の非負整数`phoneme_ids`が必須。language/speaker IDは既定0。
- 明示参照が必須。npy pathまたはinlineの`speaker_embedding`を使う。
  inlineを優先し、L2正規化したfloat32相当のlistとそのcanonical JSON SHA256を保存する。
- optional `reference_audio_paths`は全参照WAVのpath/hashを固定する。
  CERの機能検証だけなら省略可能だが、工程0/4のcross-utterance品質評価では実参照WAVを揃える。
- optional `prosody_features`はphoneme数と同じ長さのlist。
  各要素はnullまたは整数の`a1/a2/a3`を持つobjectとする。
- 相対pathはJSONLの親directory基準。manifestには解決後の絶対pathを保存する。

`evaluation_manifest.create_manifest`は検証後にversion 1 manifestをatomic保存する。
失敗時に未完成manifestを公開しない。次を固定する。

| 対象 | 固定する内容 |
|---|---|
| source | Git revision、入力JSONLとuv.lockのpath/SHA256、training/runtime/G2Pの実Python sourceとpackage設定のpath/SHA256 |
| clips | ID、textとhash、phoneme IDs、language/speaker ID、embeddingとhash、全参照WAVとhash、prosody |
| generation | sample rate、embedding次元、scales `[noise,length,noise_w]`、seed、training epoch |
| ASR | model名、40桁commit revision、language、device、`nfkc-strip-PZS-v1` |
| models | `torch-raw`、`torch-ema`、`onnx`ごとのpath/SHA256 |

Git revisionは基点の記録であり、未コミット変更を含む実コードは`source.files`のhashで固定する。
`conditions_sha256`はmodel一覧と自身を除くmanifest全体のcanonical JSON hash。
同一manifestの各backendは同じ条件hashを持つ。backend/model hashは生成結果へ別途記録する。
読み込み時にはsource、lock、参照、modelのhashも再検査する。
実ファイルや生成条件を変更した比較は新しいmanifestで行う。

seedは非負整数。clip順の`base seed + ordinal`が63bit範囲に収まることを検査する。
epochは非負整数またはnull。未知epochを品質昇格に使わない。

## 3. CLIでの準備と生成

Pythonはuvで管理する。依存の追加は`uv add`、実行は`uv run`を使う。
以下はrepo rootの既存uv環境を使うPowerShell例。Torch処理はCUDAで実行する。
ASR revisionは利用するモデルの確認済み40桁commit SHAへ置換する。
prepare/generateはASR・speaker encoderのdownloadを行わない。

```powershell
uv run --no-sync python -m piper_train.tools.generate_eval_audio prepare `
  --test-jsonl evaluation/test.jsonl --output evaluation/manifest.json `
  --checkpoint checkpoints/model.ckpt --onnx models/model.onnx `
  --asr-revision <40桁commit-SHA> --asr-device cuda --epoch 40 `
  --sample-rate 22050 --embedding-dimension 192 --seed 42 --scales 0.4 1.0 0.5

uv run --no-sync python -m piper_train.tools.generate_eval_audio generate `
  --manifest evaluation/manifest.json --backend torch-raw --device cuda --output-dir evaluation/raw
uv run --no-sync python -m piper_train.tools.generate_eval_audio generate `
  --manifest evaluation/manifest.json --backend torch-ema --device cuda --output-dir evaluation/ema
uv run --no-sync python -m piper_train.tools.generate_eval_audio generate `
  --manifest evaluation/manifest.json --backend onnx --output-dir evaluation/onnx
```

prepareの`--source-revision`未指定時は現在のGit HEADを記録する。
checkpointだけ、ONNXだけを登録することも可能。ASRの既定は`openai/whisper-small`、languageは`ja`。
ONNXのepochはexport元から確認して`--epoch`へ指定する。
Torchではcheckpointの実epochと指定epochの不一致を生成前に拒否する。
Torchの`--device auto`はCUDAを優先する。上記の明示`cuda`指定はGPUがなければ失敗し、
CPUへfallbackしない。ASRはCUDA既定で、deviceもmanifestの比較条件へ含める。
CPU互換用の指定は残すが、本作業のTorch検証・運用はCUDAを使う。

各backendの処理:

- Torch raw: 既存checkpoint移行処理を経てGをstrict loadする。外部teacherは読み込まない。
  モデル構築によるRNG消費も復元し、参照を使えないGは拒否する。
- Torch EMA: 既存exportの`apply_ema_scope_from_checkpoint`を再利用する。
  checkpointが持つlegacy/extended shadowを適用し、適用件数を記録する。
  shadowなし・対応なし・skipped parameterありをrawのEMAとして扱わない。
  成功・失敗どちらでも元の重みを復元する。新EMA scopeを追加しない。
- ONNX: pinした元graphをCPUで読み、clipごとにORT seedを設定して新しいsessionを作る。
  音声は名前`output`で取得し、先頭の補助出力を音声にしない。
  graph次元を検査し、参照mask入力があれば1、language/prosodyの必要な入力がなければエラーにする。

ORTにはRNG snapshot/restore APIがないため、このツールは独立したoffline processとして実行する。
学習processからONNX生成関数を呼ばない。fresh sessionと同じseedの再生成を実graphで検証しているが、
TorchとONNXのbit一致や異なるORT/provider環境間の完全一致を保証しない。
graph自身が明示seedを持つ乱数nodeやdeterministic exportの条件もmodel hashに含まれる。

export処理は既存`build_infer_forward`を維持する。推論の手書き複製は追加していない。
WAVはfinite・非空・monoのfloat32 raw出力。振幅正規化・clip・int16化を行わない。
output directoryは空であることが必須。各WAVをatomic保存し、全clip成功後だけ`generation.json`を公開する。
途中失敗したdirectoryは正式結果にならず、再試行には新しい空directoryを使う。

`generation.json`はmanifest/conditions/model hash、source、backend、sample rate、scales、seed、
実epoch、実行device、EMA適用件数、`ground_truth_f0_or_duration=false`、`audio_encoding=float32-raw`と、
各clipの参照/text/WAV hash・実seedを持つ。

## 4. Strict CERと自由診断

```powershell
uv run --no-sync python -m piper_train.tools.eval_cer `
  --manifest evaluation/manifest.json --clips-dir evaluation/raw --json-out evaluation/raw-cer.json
```

ASRを作る前に次を検査する。

1. manifestのschema/hashと全pinned fileが有効。
2. 最低3文、重複なし、正規化後の非空text。
3. 期待ID、WAV集合、generation report集合が完全一致。
   optional `--texts`を指定した場合はそのTSVも全ID/textが完全一致。
4. generationのmanifest/model/conditions hash、sample rate/scales/seed、
   参照/text hash、clip別seed、epoch、raw/predicted条件がmanifestと一致。
5. WAV hashがreportと一致し、実WAVが指定sample rate・mono float32・非空・finite。
6. CLIでASR model/revision/language/deviceを指定した場合、manifestと完全一致。

ASRはmanifestのrevision/deviceで初期化する。全件のCERを記録し、完全成功時だけmedian/meanを集計する。
ASR初期化失敗やclipごとの失敗は`failed_clips`へ残し、部分成功を正式合格にしない。
結果JSONはatomic保存し、manifest/conditions hash、ASR条件、normalization、epoch、
期待/成功件数、transcript、gate判定を記録する。

| exit | 意味 |
|---|---|
| 0 | 全条件有効、全件ASR成功、epoch≥40、CER median≤0.30 |
| 1 | 正式昇格不合格。高CER、早期/未知epoch、clipのASR失敗 |
| 2 | 入力/生成条件不整合、ASR初期化失敗など評価実行エラー |

早期CER不合格はtraining abort条件ではない。閾値・最低文数・epoch条件は変更しない。
`--manifest`なしの従来TSV診断は1文でも実行でき、参照のないWAVを警告してskipする。
結果は`mode=diagnostic`、`gate_passed=null`とし、正式合格とは扱わない。
診断でも明示`--asr-revision`は実際のASR初期化へ渡す。

## 5. 検証範囲

工程3の初回CPU検証は関連4ファイル72 passed。隔離gate補完後は95 passed。
CUDA対応後は関連5ファイル99 passed（2026-10-10）。
RTX 4070 Ti SUPER / Torch 2.11.0+cu128で、実小型モデルのraw/EMA生成・監視・exportと
CPU/CUDA RNGの正常時・例外時復元を確認した。ONNXはCPUで検証する。
実小型Synthesizerの通常/compile形式checkpoint、既存EMA、抽出wrapper→loader→固定監視→
prepare/generate CLI→strict CER、実ONNXの補助出力順・seed再現、失敗時復元を含む。
encoder/frontendとASRのfixtureは接続・gateの機能検証用。
実encoderの抽出品質、実WhisperのCER、学習済みモデルの音声品質は未評価。
ASRのCUDA指定はdownloadを伴わないmodule stubで検証し、回帰実行時もoffline設定を使った。
既存uv.lockの整合性も`uv lock --check --offline`で確認。追加依存は不要だった。
実データ固定・品質比較・full-model GPU学習検証は工程0/4/5で行う。
