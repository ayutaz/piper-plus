# zero-shot既存実装の不具合監査（2026-10-09）

対象: `feat/zero-shot-v8-dataset-scaling`、監査開始時のHEAD
`9f6941eee8bb92151045b15956eaaa4ac24cc973`。
直前の[GPT-SoVITS改善調査](gpt-sovits-zero-shot-2026-10-09.md)を受け、
モデル・学習、データ・評価、独立反証レビューの3エージェントと統合担当で、
設計案と実装誤りを切り分けた。本調査では本番コードを変更していない。

次工程: [不具合修正・品質改善計画](../design/zero-shot-recovery-and-improvement-plan-2026-10-09.md)。

## 1. 結論と優先順位

**新しいモデルを導入する前に、manual optimizationの更新周期を修正する必要がある。**
実Lightning TrainerによるCPU再現で、WavLM discriminatorが一度も学習されない設定と、
D:G=2:1を指定してもGが毎batch更新される挙動を確認した。
WavLMの問題は保存済みv11の設定・ログとも整合する。

| 優先度 | 所見 | 判定 | 影響する条件 |
|---|---|---|---|
| P0 | G/D optimizerの合計stepをbatch周期として使用 | 確定した実装バグ、CPU再現済み | manual optimization。特に`d_update_interval=1/2`と`wavlm_every_n_steps=2` |
| P1 | 抽出失敗entryへ存在しないembedding pathを書き込む | 確定したmanifest生成バグ、CPU再現済み | missing音声のみ、または成功/失敗混在 |
| P1 | embedding cacheのbasename衝突・無検証再利用 | 確定したcache不具合、CPU再現済み | 別directoryの同名音声、空cache、encoder/設定変更 |
| P1 | validationがtraining KL異常カウンタを書き換える | 確定した状態管理バグ、CPU再現済み | validation/sanity + KL cap guard |
| P1 | 固定WandB音声に参照speaker embeddingが渡らない | 確定した評価経路の欠落 | fixed `test_utterances.jsonl` + zero-shot |
| P1 | validation lossがGT F0を使用 | 推論品質との評価条件不一致。reconstruction loss自体の誤りとは断定しない | `use_f0_path` + teacher forcing |
| P2 | Python runtimeのcaller embeddingを次元確認せずORTへ渡す | 入力検証不足、CPU mock再現済み | 192次元graphへ256次元などを渡す場合 |
| P2 | embedding抽出のcustom output directoryと相対音声pathの扱い | 確定したCLI/path不具合、CPU再現済み | custom `output_dir`、per-speaker dataset mode |
| P2 | CER CLIが評価欠損・3文未満を失敗にしない | 正式評価契約との検証不足、CPU再現済み | 欠損clip/参照、CLI結果を昇格gateへ使う場合 |

保存済みの音質・SECS低下を、この一件だけで説明できるとは判断していない。
更新周期修正後、同じデータ・初期条件・評価契約での比較が必要になる。

## 2. P0: G/Dのoptimizer stepとbatch周期の混同

### 2.1 原因

[training_step](../../src/python/piper_train/vits/lightning.py#L1501)は、
Gの更新要否を`self.global_step % d_update_interval == 0`で判定する（L1509）。
Gの`opt_g.step()`（L1565）後、Dのlossを計算し、`opt_d.step()`（L1616）する。
Lightningのmanual optimizationでは、**それぞれのoptimizer stepでglobal_stepが進む**。
今回の環境ではLightning 2.6.6、PyTorch 2.11.0+cu128をCPU上で使用した。

WavLMも、[G側](../../src/python/piper_train/vits/lightning.py#L2332)（L2334）と
[D側](../../src/python/piper_train/vits/lightning.py#L2419)（L2421）が
`global_step % wavlm_every_n_steps`を個別に参照する。
同じbatchでも、G側判定とD側判定の間にG optimizer stepが入る。

`d_update_interval=1, wavlm_every_n_steps=2`の場合、両optimizer更新が成功する通常batchでは:

```text
batch     G入口のglobal_step     G WavLM     G更新後 / D入口     D WavLM
0                   0             実行              1             skip
1                   2             実行              3             skip
2                   4             実行              5             skip
...
```

したがって、2batchに1回を想定するWavLM G lossが毎batch計算され、
WavLM D lossは計算されない。G側には周期補償の`* wavlm_every_n_steps`もあるため、
通常の間引き平均を前提にした倍率2が毎batch適用される。
G lossによってWavLM側に生じた勾配も、D計算前の`opt_d.zero_grad()`で消去される。
[configure_optimizers](../../src/python/piper_train/vits/lightning.py#L2675)では
WavLM discriminatorはD optimizerに属し、G optimizerには属さない。

ここで「WavLM側が学習されない」は、事前学習済みWavLMの全パラメータがランダムという意味ではない。
[WavLMDiscriminator](../../src/python/piper_train/vits/models.py#L966)は事前学習済みモデルに
classifierを追加する。問題は、このdiscriminatorに設定したD学習が実行されないことにある。

### 2.2 実コードを用いたCPU再現

[再現スクリプト](zero-shot-implementation-audit-2026-10-09-probe.py)と
[生結果JSON](zero-shot-implementation-audit-2026-10-09-probe.json)を保存した。

- 実`VitsModel.training_step`と実`training_step_d`を使用。
- 実Lightning Trainer、manual optimization、8batch。
- 重い音響生成部分とdiscriminatorを小さなLinear層に置換。
- WavLM G gateは元`training_step_g`のASTから抽出し、条件式を再実装していない。
- WavLM D側のloss/backwardと重み更新は元コードを通す。
- pretrained model取得、音声生成、GPU学習、ネットワークアクセスは実施しない。

| `d_update_interval` | `wavlm_every_n_steps` | G更新 | D更新 | 最終global_step | WavLM G計算 | WavLM D計算 | WavLM head重みの最大絶対変化 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2 | 8 | 8 | 16 | 8 | **0** | **0.0** |
| 2 | 2 | **8** | 8 | 16 | 8 | **0** | **0.0** |
| 3 | 2 | 4 | 8 | 12 | 4 | 4 | 0.213657 |
| 1 | 1（対照） | 8 | 8 | 16 | 8 | 8 | 0.203778 |

`d_update_interval=2`の想定は8batchでG4回/D8回であり、実測G8回とは一致しない。
`d_update_interval=3`もbatch周期の3ではなく、別の更新比になる。
有限lossのみの再現であり、NaN skip、DDP、AMPによる追加の分岐は検証していない。

再実行（repo root、PowerShell）:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe docs/research/zero-shot-implementation-audit-2026-10-09-probe.py --output docs/research/zero-shot-implementation-audit-2026-10-09-probe.json --v11-archive piper-v11-local/box-evac/box-final-evac.tar.gz
```

archiveが手元にない場合は`--v11-archive`を省略すればCPU周期再現だけを実行できる。
JSONには監査対象`lightning.py`のSHA256も収録した。

### 2.3 保存済みv11による裏付け

archive `piper-v11-local/box-evac/box-final-evac.tar.gz`のSHA256:
`23890ff5d3783844cb0d10e150392fa42a2e155ab4930bd6338746c28102fc2f`。
展開せず、hparamsと2つのTensorBoard event fileを読み取った。
TFRecord framingとprotobufを読んでおり、CRC再検証は行っていない。

両runの保存設定は、`d_update_interval=1`、`wavlm_every_n_steps=2`、
`use_wavlm_discriminator=true`、`c_wavlm=0.5`。

| run | `loss_gen_wavlm`記録数 | `loss_fm_wavlm`記録数 | `loss_disc_wavlm`記録数 |
|---|---:|---:|---:|
| version_0 | 325 | 325 | **0** |
| version_1 | 57 | 57 | **0** |

設定・ログはCPU再現と一致する。ただしログは全batchのgradient記録ではない。
今回固定した現在のsourceと、保存ラン当時の全sourceの同一性まで証明したわけではないため、
当時の全optimizer更新履歴や音質低下の単独原因は断定しない。

### 2.4 修正方針と必要な回帰テスト

独立した永続training batch counterを設け、batch開始時の値をG/Dの両方に渡す。
G更新周期、WavLM計算周期を同じbatch単位で判定する。
checkpoint再開時もcounterを復元し、epochごとの`batch_idx`リセットに依存しない設計が必要。
実optimizer updateを周期の基準にする項目はG/D個別counterを用い、意味を分ける。

同じ`global_step`を使うDINO、swap-SCL、telemetry、gradient probe、latent fillingも
周期の意味を確認する。これらすべてにWavLMと同一の無更新不具合があるとは断定しない。

修正後の最低限のテスト:

1. 実Lightning manual optimizationで8batch、D:G=2:1がG4/D8になる。
2. WavLMの2batch周期でG/D両方が4回計算され、D側重みが変化する。
3. checkpoint再開前後で周期が継続する。
4. G/Dそれぞれの非有限loss skipを入れても周期とDDP rank間の判断が一致する。

既存[test_ddp_synced_finite.py](../../src/python/tests/test_ddp_synced_finite.py#L147)は、
fake optimizerの`step()`が呼出回数だけを増やし、`global_step`を進めない。
テスト側でstepを手動設定するため、実Lightningの複数optimizer挙動を検出できなかった。

## 3. 固定WandB音声が参照speaker条件を持たない

[_load_test_dataset](../../src/python/piper_train/vits/lightning.py#L803)が作る
`Utterance`（L867–876）には、`speaker_embedding`も`speaker_embedding_path`も設定されない。
[on_validation_epoch_end](../../src/python/piper_train/vits/lightning.py#L2533)は、
zero-shot時にembeddingが無ければゼロベクトルを作る（L2547–2565）。

そのため固定WandB音声は参照話者の声を評価する経路になっていない。
speaker IDがあっても、zero-shot embedding条件の代替にはならない。
固定テキストと固定の参照音声/embeddingを対応付け、非ゼロの話者条件が実inferに渡ることを
テストする必要がある。参照が未設定なら、ゼロ条件の監視音声であることをログに明記する。

これは固定監視音声の問題であり、別経路のholdout/CAM++評価が同じ誤りを含むとはいえない。
v11の外部SECS/CER結果を、この所見だけで無効としない。

## 4. validation lossと推論のF0条件不一致

[validation_step](../../src/python/piper_train/vits/lightning.py#L2473)は
`training_step_g()`と`training_step_d()`を直接呼ぶ。
G側はvalidation中でもepochに応じたF0 teacher forcing確率を計算する（L1857–1862）。
[SynthesizerTrn._f0_for_decoder](../../src/python/piper_train/vits/models.py#L1665)にも
evalモードで予測F0のみを選ぶ分岐がなく、GTと予測F0をBernoulliで混ぜる。
実inferは予測F0を使用する。

既定設定ではepoch 20以降も予測F0率は最大0.5であり、GT F0を含むreconstruction条件が残る。
これはreconstruction監視の目的なら成立するため、loss計算自体を確定バグとは分類しない。
ただし実推論品質、checkpoint順位付け、予測F0の頑健性を表す指標には不足する。

既存のreconstruction validationを明示的に区別し、GT F0を使わない推論条件の評価を追加する。
F0予測、duration予測、reference speaker embeddingを実runtimeと揃えて検証する。
予測F0のみへの変更だけでdecoder全体が決定的になるとは限らないため、乱数を固定した比較も必要。

## 5. caller embeddingのruntime検証不足

[voice.py](../../src/python_run/piper_plus/voice.py#L1108)は、callerのembeddingを
`reshape(1, -1)`してORT feedに渡す。graph入力次元の確認はゼロ埋め作成時には使うが、
callerから渡されたembeddingの確認には使わない。
独立エージェントのCPU mockでは192次元graphに対し、256次元caller embeddingが
`(1, 256)`のままfeedされることを再現した。実ORTでは次元不一致エラーになる。

[infer_onnx.pyのJSONL per-utterance経路](../../src/python/piper_train/infer_onnx.py#L1076)も
入力embeddingの次元確認がない。
HTTPは192次元の確認を持つため、入口によって検証が異なる。

graphのspeaker embedding入力次元に合わせて早期検証し、次元・NaN/Inf・ゼロnormを
一貫したエラーにする。192次元でもencoderが同じとは限らないので、encoder IDと正規化仕様は
別に契約を管理する。別encoderの同一次元vectorが安全だとは判断しない。

## 6. validationによるKL異常カウンタの汚染

`training_step_g`はraw KL計算後に
[_update_kl_cap_guard](../../src/python/piper_train/vits/lightning.py#L1971)を無条件で呼ぶ。
[guard本体](../../src/python/piper_train/vits/lightning.py#L1351)にも`self.training`判定がない。
validationはGのloss関数を再利用するため、training用の連続capカウンタがvalidationでも変わる。

元`validation_step`と元guardを使用し、数値G/D lossだけを代替したCPU再現:

```text
self.training=False、abort threshold=3、validation raw KL=20000
validation 1: counter=1
validation 2: counter=2
validation 3: counter=3、RuntimeErrorで停止
続いて低いvalidation raw KL=1: counter=0へリセット
```

再現では閾値を3に下げた。既定の300到達を実測したという意味ではない。
productionの無条件G呼出はsource確認、validation/guardの状態変化は実行確認である。
結果は[CPU probe JSON](zero-shot-implementation-audit-2026-10-09-probe.json)の
`evaluation_checks`に保存した。

sanity/validationだけのKLがtraining abortに数えられたり、逆にtraining中の異常streakが
低いvalidation KLで消えたりする。training連続stepを監視する仕様と一致しない。
G側のguard呼出をtraining時に限定し、validationが増加・reset・abortのどれも起こさない
回帰テストを追加する。既存`test_kl_cap_guard.py`はguard単体の状態遷移を確認するが、
validationから呼ぶ経路を確認していない。

## 7. embedding抽出のmanifest・cache・path不具合

独立エージェントがtempfile datasetとfake ONNX sessionで既存関数を呼び、以下を再現した。
対象は[extract_speaker_embedding.py](../../src/python/piper_train/extract_speaker_embedding.py)。
実際のv11 datasetでこれらの条件が発生した証拠はなく、適用条件を限定して扱う。
再現は同じ[統合CPU probe](zero-shot-implementation-audit-2026-10-09-probe.py)へ収録し、
JSONの`pipeline_probes`に結果を保存した。

### 7.1 抽出失敗時に壊れたmanifestを書き込む

L546で`utt["speaker_embedding_path"]`を設定してから、音声ファイルを確認する（L553–559）。
抽出対象が空の場合、L581–585の早期return側でJSONLを書き換える。
後段の「success=0ならJSONL更新を止める」guardには到達しない。
一部成功の場合も全entryを書き戻すため、missing entryのパスも保存される。

```text
missing-only: speaker_embeddings/missing.npyをJSONLへ記録、実ファイル無し
valid+missing: ok.npyとmissing.npyを記録、実在は[True, False]
```

下流`PiperDataset.__getitem__()`はそのパスを`np.load`するため、該当entryで失敗する。
ファイルを正常に保存・検証したentryだけへパスを設定する必要がある。
shard処理では全shardの成功を確認してからmanifestを確定する方式も検討する。

### 7.2 basenameのみのcache keyが衝突する

L540–551で音声pathのstemだけから`speaker_embeddings/<stem>.npy`を作る。
`a/foo.pt`と`b/foo.pt`を登録すると、両entryは同じ`foo.npy`を参照し、保存先は1個になる。
異なる発話・話者のembeddingを上書き/共有し得る。
音声の正規化相対pathまたは内容hashを含めた一意keyが必要。
現行preprocessが常に一意stemを生成するdatasetでは衝突は起きないため、全datasetへの
影響や既存v11学習への汚染を断定しない。

### 7.3 空cache・別encoderのcacheをそのまま使う

L531–551は`.npy`のstemが存在するだけでskipする。
空ファイルでもskipし、下流`np.load()`は`EOFError`になる。
既存[test_extract_speaker_embedding.py](../../src/python/tests/test_extract_speaker_embedding.py#L342)も
`touch()`した空cacheを再利用成功として扱い、内容検証をテストしていない。

encoder Aで抽出後、encoder Bと別`fixed_frames`で再実行してもfake sessionの呼出数は
1回目1回、2回目0回で、同じcacheを再利用した。
model SHA256、encoder ID、前処理/pooling設定、入力音声hashをcache metadataに含め、
shape・finite・normを読み取り検証する。保存はatomicに行い、中断cacheを再利用しない。

### 7.4 `output_dir`とper-speaker相対path

`extract_per_utterance()`は`output_dir`引数を受ける（L461–474）が、実保存先を
`dataset_dir / "speaker_embeddings"`へ固定する（L518–519）。
`output_dir=<tmp>/custom`の再現ではcustomは作られず、default directoryへ保存された。
引数どおりの保存と、dataset loaderから解決できるmanifest pathの双方をテストする必要がある。

`extract_from_dataset()`のper-speaker modeはL199–215、L237–241でJSONLの相対pathを
cwd基準で読む。`dataset_dir/cache/u.pt`が存在し、JSONLが`cache/u.pt`でも、repo rootから
実行するとmissing扱いで話者embeddingを出力しない。
一方`PiperDataset`はdataset directory基準で相対pathを解決するため、契約が一致しない。
per-utterance modeにはdataset directory基準の解決があり、両modeで扱いが異なる。

`--workers`もper-speaker CLIで引数が処理関数へ渡されず、関数内にも並列処理がない。
指定値が効かない性能面の不具合であり、音質劣化を示すものではない。

## 8. 不正embeddingとCER欠損の検出不足

### 8.1 192次元でもNaNを受け入れる

[infer_onnx._resolve_speaker_embedding](../../src/python/piper_train/infer_onnx.py#L459)は
直接`.npy`入力のshapeを確認するが、finiteとnormを確認しない。
192次元vectorの先頭をNaNにしたCPU再現で、shape `(192,)`、`finite=False`、norm NaNの
embeddingを返した。HTTPも次元確認はあるがfinite/norm確認がない。
実ORTによる音声生成への影響は未検証である。

trainingのdataset loaderは1-D shapeと次元を確認するが、finite/normは確認しない。
shape検証に加えてfinite/norm検証を追加し、training/runtime入口へ共通化する。
未知のencoderを同一次元というだけで混ぜることは避け、入力異常とencoder互換性を別に検証する。

### 8.2 CER CLI単体では正式gate条件を担保しない

[eval_cer.py](../../src/python/piper_train/tools/eval_cer.py#L141)は参照テキストのないWAVを
warningだけでskipする。参照TSVに存在するのにWAVが欠損したIDも検出しない。
最低件数のチェックはなく、1件以上の集計ができれば終了code 0を返す。

CPU fake ASRで`a.wav, b.wav`、参照はaのみを与えた結果、bをskipし、
CER median=0.000、n=1、return code=0となった。
[正式評価契約](../spec/zs-eval-contract.md#L255)はCER median≤0.30かつ固定参照合成3文以上を要求する。

このCLIはCER scoreの算出器であり、終了code 0だけを「品質gate合格」とみなす仕様ではない。
正式gateに使う側で、manifest ID全件の一致・最低3文・CER閾値を検証する必要がある。
CLIにstrict modeを追加すると、missing WAV/参照を早期に発見できる。
過去v11評価の件数欠損や、不正な昇格実行が起きたことまでは確認していない。

## 9. バグと断定しない項目

| 項目 | 今回の扱い |
|---|---|
| F0 predictor / F0 projectionがextended EMA対象外 | 現行のscope定義とテストに沿う設計。効果比較が必要で、実装ミスとは断定しない |
| carrier decoderのeval時ノイズ | sourceとONNX testが乱数演算を契約に含める。決定的比較にはnoise注入/seed管理が必要 |
| ONNX speaker encoder経路の`no_grad` | 生成音声へのidentity gradientを与えない条件は存在。v11のTorch CAM++経路とは分ける |
| 同話者の別発話positiveがない場合のSCL fallback | same-utteranceへ戻る現行仕様。v11でそのfallbackが起きた証拠は得ていない |
| DINOの同一view/frozen teacher | sourceにも退化の警告がある設計上の弱点。未知のコーディングエラーとは分類しない |
| rebase起因のruntime破損 | 今回の差分・関連テストからは確認できない。更新周期の問題はrebaseが原因と判断しない |
| training/runtimeのresampler・chunk pooling差 | torchaudio対soxr、chunk平均対全発話推論の差は確認。fake encoderの差から実CAM++の品質低下までは推定しない。共通化のA/B候補 |

## 10. 検証範囲

独立エージェントがCPUで実施した既存テスト:

- **39 passed**: `src/python/tests/test_ddp_synced_finite.py`、
  `test_carrier_f0_stability.py`、`test_ema_scope_extended.py`。
- **20 passed**: `src/python/tests/test_infer_onnx_speaker_embedding_mask.py`、
  `test_infer_onnx_speaker_embedding_integration.py`、`test_build_infer_forward.py`、
  `src/python_run/tests/test_voice_speaker_embedding.py`。
- **33 passed**: 上のDDP finite skipとEMA extendedのみ（39件と重複）。

コマンド: `.venv/Scripts/python.exe -m pytest -o addopts= -q --no-cov -p no:cacheprovider <対象ファイル>`。

これらの件数を足してユニークなテスト総数とは扱わない。
対象限定の実行では全体coverage閾値が対象外コードを含めて失敗するため、
テスト結果の確認には`--no-cov`を使用した。全体coverage達成の主張はしていない。
既存テスト成功は上記の未カバー経路の正しさを保証しない。

追加のCPU probeは4設定とも完走し、WavLM D更新あり/なしの対照を確認した。
固定loader/F0/KL状態遷移と、path/cache/不正embedding/CERの小規模fixtureも完走した。
再現スクリプトのRuff check/formatも成功している。
本監査では本番学習、音声の人手試聴、修正前後のSECS/CER比較、GPU/DDP実行、
大型モデル取得は実施していない。調査結果と再現証拠を保存し、修正は別工程とする。

### caller embedding次元の独立CPU再現

repo rootのPowerShellから実行。実ORT sessionをmockに置換し、実runtimeのfeedを確認する。
モデル推論とphonemizer実行は行わない。

```powershell
$env:PYTHONPATH="$PWD/src/python_run"
$env:PYTHONDONTWRITEBYTECODE='1'
@'
from unittest.mock import MagicMock
import numpy as np
from piper_plus.voice import PiperVoice
from piper_plus.config import PiperConfig, PhonemeType

def inp(name, shape):
    x = MagicMock()
    x.name, x.shape = name, shape
    return x

session = MagicMock()
session.get_inputs.return_value = [
    inp("input", ["batch", "seq"]), inp("input_lengths", ["batch"]),
    inp("scales", [3]), inp("speaker_embedding", ["batch", 192]),
    inp("speaker_embedding_mask", ["batch", 1]),
]
out = MagicMock()
out.name = "output"
session.get_outputs.return_value = [out]
session.run.return_value = [np.zeros((1, 1, 22050), dtype=np.float32)]
config = PiperConfig(
    num_symbols=100, num_speakers=1, sample_rate=22050,
    length_scale=1.0, noise_scale=0.4, noise_w=0.5,
    phoneme_id_map={"_":[0], "^":[1], "$": [2], "a":[10]},
    phoneme_type=PhonemeType.MULTILINGUAL,
)
voice = PiperVoice(session=session, config=config)
voice.synthesize_ids_to_raw([1, 10, 2], speaker_embedding=np.ones(256, dtype=np.float32))
print(session.run.call_args[0][1]["speaker_embedding"].shape)
'@ | .venv/Scripts/python.exe -
```

出力: `(1, 256)`。graph入力の192次元に対する早期検証は実行されていない。
