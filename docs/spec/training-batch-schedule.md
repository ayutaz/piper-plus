# Training batch周期・状態復元の仕様

2026-10-09、[zero-shot改善計画の工程1](../design/zero-shot-recovery-and-improvement-plan-2026-10-09.md#4-工程1-trainingの確定バグを修正最初の実装)の実装仕様。
対象はPython `VitsModel`のmanual optimization。

## 1. 周期の基準

Lightningの`global_step`はmanual optimizationではoptimizer stepの進行を表す。
同一batch内のG/D間で値が変わるため、batch周期の判定には使用しない。

`training_batches_seen`は受領したtraining batch数で、初期値は0。
`training_step`の入口でその値を`_training_batch_index`へ固定してから1増やす。
そのbatchのG/D判定は同じ0始まりのindexを使う。
非有限loss、latent filling、precision pluginによるoptimizer skipでも受領数は進む。
validation/sanityはこの入口を通らず、受領数もindexも変更しない。

`d = d_update_interval`、`w = wavlm_every_n_steps`とすると、通常batchの予定は以下。

| 動作 | 判定 | 補償倍率 |
|---|---|---|
| G optimizer更新 | `index % d == 0` | — |
| D optimizer更新 | 各batch。非有限/LFではskip | — |
| WavLM G loss計算 | G更新対象かつ`index % w == 0` | `w / gcd(d, w)` |
| WavLM D loss計算 | D実行対象かつ`index % w == 0` | `w` |

Gの更新間隔とWavLMの交点は`lcm(d,w)` batch周期。
したがってG更新に対するWavLMの計算頻度は`gcd(d,w)/w`となる。
例えば`(d,w)=(1,2)`はGの2回に1回で倍率2、`(2,2)`はGの毎回で倍率1、
`(3,2)`はGの2回に1回で倍率2。
この補償は予定周期に対するもの。非有限/LFによる欠測分を後から追加更新しない。

WavLMのD headはD optimizerが所有する。
G loss計算とD loss計算の間でoptimizerが進んでも周期判定は変化しない。
validationでG lossを計算する場合はtrainingのG更新対象制約を外す。
validation lossは復元用lossであり、推論条件の品質評価は計画の工程3で扱う。

## 2. 関連機構のclock

| 機構 | 基準・挙動 |
|---|---|
| G/D/WavLM | 上記の固定batch index |
| latent fillingの抽選・補間seed | batch index。G更新対象のbatchに限定 |
| swap-SCLのpermutation seed | batch index。rampは従来どおりepoch |
| modulation telemetry | batch index。training限定 |
| gradient probe | batch indexの指定周期とG更新対象の交点。trainingかつgrad有効時のみ |
| EMACallback | **実際に成功したG optimizer更新数**。D-only/非有限/precision skipでは更新しない |
| EMA start/apply-every設定 | VitsModelではG更新数単位。他のLightningModuleは従来のglobal_step互換 |
| DINO teacher/center | 従来どおり通常trainingのG forward内。student/teacherのfinite guardを維持。G optimizer成功回数とは別 |
| LR scheduler | 従来どおりepoch末に各schedulerを進める |
| KL cap streak | trainingのraw KLのみ。validation/sanityでは増加・reset・abortしない。評価値は`val_kl_raw`へ別途記録 |
| Lightning global_step | Lightningの管理と既存logに残す。batch周期の判定には使わない |

DINOの構成上の退化懸念と`c_dino=0`推奨は既存設計どおり。
工程1ではDINOの学習機構やEMAの対象moduleを増やさない。

## 3. 更新回数とskip

`generator_updates`と`discriminator_updates`はraw optimizerのstep完了を
post hookで確認した場合だけ増やす。Lightning wrapperを呼んだだけでは増やさない。
これによりprecision pluginがraw stepを省いた場合も回数とEMAが整合する。
`generator_updated_this_batch`はbatch入口でFalseになり、成功したG stepだけTrueになる。

| log | 意味 |
|---|---|
| `training_batches_seen` | skipを含む受領batchの累積数 |
| `optimizer_updates_g` / `optimizer_updates_d` | 成功したraw optimizer更新の累積数 |
| `g_step_skipped` | G周期対象外 |
| `non_finite_skip` / `d_step_skipped_nonfinite_g` | G loss非有限のrankがありG/Dとも中止 |
| `d_step_skipped_nonfinite_d` | D loss非有限のrankがありDを中止 |
| `lf_step` / `d_step_skipped_latent_filling` | LF batchのDを省略 |
| `g_step_skipped_optimizer` / `d_step_skipped_optimizer` | precision plugin等がraw stepを実行しなかった |
| `val_kl_raw` | validation/sanityのclamp・weight適用前KL。training guardとは分離 |

G/D lossのfinite判定は既存のrank間all-reduceを使う。
G非有限で中止した場合もLF flagとgraph参照を解放する。
更新数はoptimizerの実行回数であり、音声品質や全parameterの重み変化を示す指標ではない。

## 4. Checkpointと旧形式

Lightning checkpointのトップレベルに次のmetadataを保存する。
モデルの`state_dict`へcounter bufferを追加しない。

```json
{
  "training_schedule_state": {
    "version": 1,
    "batches_seen": 8,
    "generator_updates": 4,
    "discriminator_updates": 8,
    "kl_cap_consecutive": 0
  }
}
```

復元後の次training batchは`batches_seen`をindexとして開始する。
未知version、欠落field、非整数/負数、受領数を超えるoptimizer更新数は明示エラー。
KL streakも保存・復元し、epoch途中の保存でも周期が連続する。

旧checkpointには受領数を特定できるmetadataがない。
**strict training resumeはエラーにし、`global_step`から逆算しない。**
旧checkpointから追加学習する場合は、既存CLIの`--resume-weights-only`と
`--resume_from_checkpoint <checkpoint>`を指定して、新しいrunとして開始する。
optimizer/scheduler/loop状態を継承せず、受領数・更新数・KL streakを0へ戻す。
旧checkpointの推論用weights読み込みは許可する。

互換性検査で、工程1開始前のHEADでも公開base checkpointのstrict loadが
追加STFT lossのbuffer欠落により失敗することを確認した。
`normalize_checkpoint_state_dict`で、欠落したfull/high-band STFTの
`window`と`band_weight`だけを現在の設定から復元する。
保存済みbufferは上書きせず、学習parameter等の別の欠落はstrict loadで拒否する。
公開checkpointのshape snapshotは変更していない。

checkpointのbatch周期復元とDataLoaderの厳密な位置/RNG復元は別の契約。
非stateful DataLoaderのepoch途中resumeで、入力の完全再現まで保証したとは扱わない。

## 5. 検証範囲

2026-10-09、下記とEMA、weights-only、telemetry、gradient probe、F0、speaker signal、
checkpoint互換性を含む関連12ファイルを実行し、**207 passed**を確認した。
CPU実行、coverage/cache plugin無効。GPU学習と音声品質の比較は未実施。

テスト: [test_training_batch_schedule.py](../../src/python/tests/test_training_batch_schedule.py)、
[test_kl_cap_guard.py](../../src/python/tests/test_kl_cap_guard.py)、
[test_checkpoint_film_migration.py](../../src/python/tests/test_checkpoint_film_migration.py)。

小型Linear G/Dを使い、productionの`training_step`/`training_step_d`と
実Lightning optimizer wrapperを実行する。
Gの数値forwardは置換するが、WavLMのG gate/loss式はproduction sourceから評価する。
WavLM pretrained modelのダウンロードは行わない。

| 確認項目 | 期待結果 |
|---|---|
| 8batch、d=2 | G4回/D8回 |
| 8batch、d=1・w=2 | WavLM G4回/D4回、D headの重み変化 |
| d=2・w=2、d=3・w=2 | G周期との交点、補償倍率が一致 |
| epoch末/epoch途中checkpoint | 次batchの周期と更新回数を復元 |
| G NaN、D NaN、LF skip | 受領数8、G3回/D5回、graphを解放 |
| precision pluginのG/D skip | raw stepの実行回数にcounter/EMAが一致 |
| 実Lightning sanity/validation | 受領数・index・KL streakが不変 |
| 2 CPU Gloo rank、片rankのみ非有限 | 両rankのskip判断・受領数・更新回数が一致 |
| 公開checkpoint互換性gate | pinned shapeからstrict load成功 |

Gloo検査はWindowsのnative library初期化を他テストから隔離し、OMP/MKL thread数を
1に固定したprocessで実施する。調査中にnative access violationが断続的に発生したため、
再発時のfault handler出力を保持し、worker失敗をretryやskipで隠さない。
これはfinite判定と周期のrank一致の検査であり、full-modelのDDP gradient同期検査ではない。
実GPUのAMP/DDP/full-model smokeと人手試聴は計画の工程5に残す。
