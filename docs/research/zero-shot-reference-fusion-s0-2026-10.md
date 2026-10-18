# 参照融合計画 S0: 参照処理のCPU検証とG0判定

日付: 2026-10-17 (JST)。対象branch: `feat/zero-shot-v8-dataset-scaling`。
測定コードの固定点: (a)(b)は`eca569d39211c414cf5eb0c936656cfb6ed12380`。
(c)の分離度とR6のLDAプローブは`71f81026bcbd504df9519fbc10ed7eb87f9394ae`
（発話sha256とsource revisionを固定。tracked sourceの未コミット変更なし）。
[CPU準備記録](zero-shot-cpu-preparation-2026-10-17.md)の基準評価を読み取り専用で再利用した。
GPU、学習、公開、既定モデルの差し替えは実施していない。

## 1. 目的

GPUを借りる前に、既存のv10b ep79をCPUで使い、次の3点を決める（G0）。

- (a) 推論時の参照音声に、学習時と同じenergy VAD trimをかけるか。
- (b) 複数参照の平均を、埋め込み側とg側（`spk_proj`の出力）のどちらで取るか。
- (c) CAM++のpooling前統計（平均+標準偏差、1024次元）が、192次元のCAM++埋め込みに
  話者情報を上積みするか（判定はcontroller ruling R6の話者分割LDAプローブ）。

後続タスクは、G0で決めたfrontend文字列を既定値として記録する。

## 2. 入力と固定値

| 入力 | SHA256 |
|---|---|
| v10b ep79 checkpoint | `c3a6019f983726284c278744814a1aa992c0df36c257cb6dfa62a78bc746f5c0` |
| v10b ep79 ONNX（基準評価で新規export、既存EMA） | `d298f52191edde0e12b267a70303cb9c11f1c60a1172866dbd9c8d48ff505954` |
| CAM++ ONNX（`releases/zs-v1/campplus.onnx`と同一） | `a6ac6a63997761ae2997373e2ee1c47040854b4b759ea41ec48e4e42df0f4d73` |
| Torch CAM++ `campplus_cn_common.bin` | `funasr/campplus@e4b6ede7` |
| 基準 `comparison-final/experiment.json` | `c7f1ed2aacb4278ef29f09b6ae9cf3837bd3f83fb1bd862ff202e3adee6746f0` |
| 基準 `comparison-final/references.json` | `3ce83c902c3a7676f3f8f50327eea0faacb988d0e511cea03c4d19de7df31982` |
| 基準 `comparison-final/baseline.json`（変更なしを確認） | `5ddea714eadd2690a9fff2a4571ab87173315b83cb543ca59fd4016671556ed5` |

基準と同じ3文、seed 42（文ごとに+ordinal）、scales [0.4, 1.0, 0.5]、22050 Hz、
Whisper-small CPU（strict CER）、CAM++とnative ECAPAのcross-utt、
cross-realはつくよみちゃん003〜008、floorは基準で固定した別話者1件を使った。
ceiling/floorはCAM++ 0.880298 / 0.736056、ECAPA 0.808135 / 0.528286（基準と同値）。

固定3文の旧結果は上書きしていない。新しい測定は別manifestで行った。
出力は`output/zero-shot-reference-fusion-s0-20261017/`（Git対象外）。

| 条件 | manifest SHA256 | conditions_sha256 |
|---|---|---|
| a-wav001-trim-none | `df948a7ac9be53028be37a586ed1b0dda4dcd2158ffb9a806181fb8ab39a4812` | `270b7a1664722033ad912335a35696b8450ded36d6fc1a63fac33d5f2b9d0465` |
| a-wav001-trim-energy-vad | `867458747f2c6466e01886d54c98a7c34ef1d5f8a8d407589539f81a978dc867` | `5aff4d3cbc623e26b619865869cd30d7fb3672d3f6d820b41f43623b5148ae85` |
| a-wav001-pad-trim-none | `72e5450768c583aff3c1aca12cf95a241eb555a5db4dbc0b1c675cfa5309b6e3` | `56a50d8517fea87b3faec6b6930d5a5ab9a1c11e41ca945ff627deb635048fd5` |
| a-wav001-pad-trim-energy-vad | `3da319ec96fcc89f07b90225e820079fd2e07d581849bdf6e74b1c63e5d21137` | `70048d320aabc1b2e44d17db5ebf68bcab4cbd5309d2ff4a56a6eca6e0384012` |
| b-multi-embedding-average | `e8308b25d89d48ac72c41e9ca8b6916725dd78dc95b563b09e2650500084d2df` | `2165ec5ac1cf716a19db1a28d952a08d7f632ad641d1eec8cdc6652fa0220c2d` |
| b-multi-g-average | `e7b58bfbb5e501e847e053a838e28d7932f8c3de1c8980a0b94dca2d2485530c` | `27f38bd66cdc9f9d889cb309d30915875cd040c08d0c3e5ce2d22035eafc33ba` |

集計ファイル:

| ファイル | SHA256 |
|---|---|
| `references.json` | `191197247d9f36f255c9c27eaf3d9f437d96a279bc05ab75f20b5ea13ce043e3` |
| `separability-pinned.json`（303発話のsha256・revision付き） | `7af5b4f8c5e02f46032000d1768016ed2f3e20ba00962abbc4d655af96f88004` |
| `separability-features.npz`（192・1024特徴、trimなし/あり） | `bea4ad7bd8c295bdcdd563cd6853519bb2de24c727c700d924b1440e65c6993c` |
| `lda-probe.json`（R6） | `10f20fc882db3ff9a2fbdb102a4470cc35920c1a786426b933b5246266c44415` |
| `summary.json` | `b0f9751ee0945444d788ee473c04dff705dcb879297c5137a677d7b393f3fb11` |

初回の`separability.json`（発話hashなし）と旧`summary.json`は、
`separability-unpinned-superseded.json` / `summary-superseded-cosine.json`として残した。
固定版は同じAUCを再現した。分離度・プローブのstageは既存結果を上書きしない。

## 3. 方法

runnerは`scripts/run_reference_fusion_s0.py`（stageはprepare → generate → evaluate →
separability → probe → summary）。evaluateは基準と同じmetrics環境
（`metrics-env`、SpeechBrain 1.0.3）で、基準と同じ評価関数を使った。
評価側のfrontend（CAM++はtrimなしwhole、ECAPAはnative波形）は変えていない。
変えたのは生成に渡す参照埋め込みだけである。

```bash
O=output/zero-shot-reference-fusion-s0-20261017
uv run --no-sync python scripts/run_reference_fusion_s0.py --output $O --stage prepare
uv run --no-sync python scripts/run_reference_fusion_s0.py --output $O --stage generate
HF_HUB_OFFLINE=1 uv run --no-sync python scripts/run_reference_fusion_s0.py --output $O --stage separability
uv run --no-sync python scripts/run_reference_fusion_s0.py --output $O --stage probe
PYTHONPATH="src/python;src/python_run;src/python/g2p" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  output/zero-shot-cpu-preparation-20261017/metrics-env/Scripts/python.exe \
  scripts/run_reference_fusion_s0.py --output $O --stage evaluate   # summaryも同じ環境
```

- (a) 参照はWAV001原音（6.91秒、VADで落ちるのは末尾0.04秒のみ）と、
  WAV001の前後に1秒ずつ-60 dBFS RMSの白色雑音（seed 20261017）を足した版の2種類。
  後者は前後に無音を含む利用者録音の代用で、合成した条件である。
  各参照でtrimなし/あり（`reference_embedding(..., trim=True)`）を作り、
  raw・EMA・ONNXの3 backendで生成・評価した。
- (b) 基準§5の2参照（multi-0/1のcrop）を使った。埋め込み平均は`L2(mean e_i)`
  （基準`multi-whole.npy`と一致を確認）、g平均は`mean_i spk_proj(e_i)`
  （`projected_average`）。g平均はTorchだけで測り、raw・EMAの2 backend。
  生成時は`_get_speaker_condition`を置き換え、manifestの名目埋め込みと一致することを検査した。
- (c) 手元にある実音声の全話者で、同話者対と別話者対のcosineを比べた（AUCは
  Mann-Whitney、同値は0.5）。192次元はL2正規化済みのcosine（raw）を基準とした。
  1024次元統計は、同じ集合で次元ごとにz-score化（平均0・分散1）してからcosineを取る。
  この標準化は評価集合そのもので計算した（transductive）。raw cosineも併記する。
  frontendは`preprocess_audio`（soxr HQ 16k、kaldi fbank80、CMN、発話全体）。
  trimなし/ありの両方を計算した。
  この教師なしcosineは診断として残すが、判定には使わない（§4.3、ruling R6）。
- (c) R6の判定（LDAプローブ、`lda_speaker_probe`）: 上の拡張24話者・213発話
  （話者ごとにsha256順で先頭10発話。既に10発話以下なので全件）を使う。
  G0 frontend（trim=none）の特徴でAを192次元、Bを192次元と1024次元統計の連結とする。
  seed 0〜9の各回で、ソート済み話者IDを`default_rng(seed).permutation`で並べ、
  12話者を学習、12話者を評価に分けた。A・Bそれぞれ学習話者の発話で標準化し、
  `LinearDiscriminantAnalysis(solver="eigen", shrinkage="auto")`を学習話者で当てた。
  評価話者の発話を射影し、同話者対と別話者対のcosineでAUCを求めた。
  事前登録した合格条件は、AUC_B − AUC_Aの平均が+0.005以上、かつ10回中7回以上でAUC_B > AUC_A。
  LDAが例外を出した回は差0・Bの負けとして数える（今回は例外なし）。

判定規則は測定前に`trim_decision` / `averaging_decision` / `stats_decision`、
R6の規則は`lda_speaker_probe`として実装・テストした
（`tests/scripts/test_reference_fusion_s0.py`、`src/python/tests/test_cpu_reference_comparison.py`）。
`stats_decision`はruling R1に合わせ、10話者未満では弱い証拠として合格扱いにする
（初版は不合格を返していたため`71f81026`で修正）。

## 4. 結果

### 4.1 (a) 参照trim

| 参照 | backend | trim | CER中央値 | CAM++ cross | ECAPA cross |
|---|---|---|---:|---:|---:|
| WAV001 | raw | none | 0.1429 | 0.7238 | 0.5951 |
| WAV001 | raw | energy-vad | 0.2857 | 0.7180 | 0.5725 |
| WAV001 | EMA | none | 0.3810 | 0.7276 | 0.5959 |
| WAV001 | EMA | energy-vad | 0.3810 | 0.7261 | 0.5853 |
| WAV001 | ONNX | none | 0.1905 | 0.7082 | 0.5744 |
| WAV001 | ONNX | energy-vad | 0.1304 | 0.6952 | 0.6018 |
| WAV001+雑音 | raw | none | 0.0952 | 0.7144 | 0.5767 |
| WAV001+雑音 | raw | energy-vad | 0.1905 | 0.7276 | 0.6059 |
| WAV001+雑音 | EMA | none | 0.0952 | 0.6982 | 0.5909 |
| WAV001+雑音 | EMA | energy-vad | 0.1429 | 0.7355 | 0.6242 |
| WAV001+雑音 | ONNX | none | 0.0435 | 0.6882 | 0.5775 |
| WAV001+雑音 | ONNX | energy-vad | 0.0870 | 0.7298 | 0.5928 |

trimあり − trimなし:

| 参照 | backend | ΔCAM++ | ΔECAPA | ΔCER中央値 | 判定 |
|---|---|---:|---:|---:|---|
| WAV001 | raw | -0.0058 | -0.0226 | +0.1429 | 3指標とも退行 |
| WAV001 | EMA | -0.0014 | -0.0106 | +0.0000 | CAM++・ECAPA退行 |
| WAV001 | ONNX | -0.0130 | +0.0273 | -0.0600 | CAM++退行 |
| WAV001+雑音 | raw | +0.0132 | +0.0292 | +0.0952 | CER退行 |
| WAV001+雑音 | EMA | +0.0373 | +0.0333 | +0.0476 | CER退行 |
| WAV001+雑音 | ONNX | +0.0416 | +0.0153 | +0.0435 | CER退行 |

参照埋め込み同士のcosine: WAV001のtrimなし/ありは0.9999でほぼ同じ。
雑音付きtrimなしはWAV001比0.9765まで離れ、trimで0.9957まで戻る。
Goodhart flagとabove-ceilingは全12群でfalse。雑音付きONNXのtrimではECAPAのsame/cross gapが+0.01以上広がった。

WAV001では埋め込みがほぼ同じ（0.9999）なのに、CERは最大0.14、ECAPA crossは最大0.027動いた。
同じseedでも埋め込みの小さな差で長さと乱数の使われ方が変わるためで、
3文の測定ではこの程度の揺れが出る。雑音付き参照では、trimで両encoderのcrossが
3 backendとも上がった。一方、CERの中央値は3 backendとも悪化した（1〜2文字分）。

### 4.2 (b) 複数参照の平均位置（Torchのみ）

| backend | 平均位置 | CER中央値 | CAM++ cross | ECAPA cross |
|---|---|---:|---:|---:|
| raw | 埋め込み | 0.0556 | 0.7279 | 0.5955 |
| raw | g | 0.1905 | 0.7276 | 0.6286 |
| EMA | 埋め込み | 0.1304 | 0.7141 | 0.6049 |
| EMA | g | 0.1905 | 0.7141 | 0.6137 |

g − 埋め込み: rawはΔCAM++ -0.0003、ΔECAPA +0.0331、ΔCER +0.1349。
EMAはΔCAM++ -0.0000（-4e-5）、ΔECAPA +0.0087、ΔCER +0.0600。
ECAPAは上がったが、CAM++は上がらず、CERは両backendで悪化した。Goodhart flagはfalse。

### 4.3 (c) CAM++統計1024と192の分離度

#### R6 LDAプローブ（判定に使う）

| seed | AUC_A（192） | AUC_B（192+1024） | B − A |
|---:|---:|---:|---:|
| 0 | 0.8953 | 0.8851 | -0.0101 |
| 1 | 0.8556 | 0.8158 | -0.0398 |
| 2 | 0.8995 | 0.9047 | +0.0052 |
| 3 | 0.8585 | 0.8681 | +0.0096 |
| 4 | 0.9073 | 0.8944 | -0.0128 |
| 5 | 0.8838 | 0.9191 | +0.0353 |
| 6 | 0.8871 | 0.8674 | -0.0197 |
| 7 | 0.8535 | 0.8162 | -0.0373 |
| 8 | 0.8325 | 0.8223 | -0.0103 |
| 9 | 0.8997 | 0.8971 | -0.0027 |

B − Aの平均は**-0.0083**、Bが上回ったのは**10回中3回**。合格条件（平均+0.005以上かつ7回以上）を満たさず、**不合格**。
LDAの例外はなかった。sklearnは単発話話者（3話者）が学習側に入る回で
「Only one sample available」の警告を出したが、計算は完了している。
学習話者の線形射影を許しても、統計1024を足して未知話者の分離が上がるとは言えない。

#### 教師なしcosine（診断。判定はR6に置き換え）

CAM++の192次元埋め込みは、この1024次元統計をLinearと推論時のBNで写したアフィン射影である。
そのため、統計のcosineが学習済み射影より分離しないのは予想どおりで、
統計を捨てる根拠にならない（ruling R6）。以下は記録として残す。

集合は次の2つ。話者数と発話数を示す。

- R1（指示の範囲）: つくよみちゃん100発話、基準のfloor候補2話者（各1発話）、
  ローカルbackupの韓国語1話者（1発話）。4話者・103発話、同話者対4950、別話者対303。
  同話者対はすべてつくよみちゃんである。v9試聴の`tsukuyomi_zeroshot`参照は
  つくよみちゃん本人のため別話者として数えない（初回集計で別話者扱いの誤りがあり、`2020ad26`で修正・再計算した）。
- 拡張: 上の単発話3話者、つくよみちゃん10発話（100発話から等間隔）、
  ローカルHF cacheに既にある`ayousanz/moe-speech-20speakers-ljspeech`の20話者×10発話
  （新規ダウンロードなし、話者ごとに等間隔）。24話者・213発話、同話者対945、別話者対21633。
  output/外の資産だが、手元にある実音声の全話者を使うという指示に沿って加えた。

| 集合 | trim | 192 raw AUC / gap | 192 標準化 AUC / gap | 1024 raw AUC / gap | 1024 標準化 AUC / gap |
|---|---|---|---|---|---|
| 拡張 | none | 0.9271 / 0.254 | 0.9724 / 0.448 | 0.8425 / 0.012 | 0.8929 / 0.374 |
| 拡張 | energy-vad | 0.9229 / 0.255 | 0.9709 / 0.442 | 0.8337 / 0.012 | 0.8920 / 0.367 |
| R1 | none | 0.9981 / 0.367 | 0.5537 / 0.026 | 0.9955 / 0.020 | 0.5407 / 0.024 |
| R1 | energy-vad | 0.9968 / 0.362 | 0.5577 / 0.028 | 0.9941 / 0.020 | 0.5487 / 0.030 |

拡張集合では、標準化1024のAUC 0.893が192 rawの0.927を0.034下回った（判定の許容幅0.02を超える）。
同じ標準化どうしで比べると、差は0.080（0.972 vs 0.893）とさらに広がる。
1024のraw cosineは全対が0.97前後に集まり、gapは0.012しかない。
R1の標準化値は、100発話がつくよみちゃんのため、標準化がほぼその話者の中心化になり、
192でも0.55まで落ちる。R1の標準化値は分離度の指標として使えない。
旧規則では拡張集合が不合格（AUC差0.034）、R1は4話者のため弱い証拠として合格扱いとなる。
初版の本書はR1も不合格と書いたが、ruling R1の読み違いで、修正した。

## 5. G0判定

| 項目 | 判定 | 根拠 |
|---|---|---|
| (a) 参照trim | **採用しない（trim=none）** | 採用条件はCAM++・ECAPA cross・CER中央値がすべてのbackendで非退行であること。WAV001では3 backendすべて、雑音付きでも3 backendすべて（CER）が退行した |
| (b) 平均位置 | **埋め込み側平均を維持** | g側は両encoderで改善しなかった（CAM++は-0.0003/-0.00004）。CERはraw・EMAとも悪化した。g側を採るにはONNX入力の変更も要る |
| (c) 統計特徴 | **不合格（R6）** | 24話者・10分割のLDAプローブで、192+1024は192に対し平均-0.0083、勝ちは3/10。旧cosine判定（拡張は不合格、R1は弱い証拠で合格）は判定から外した |

後続タスクが記録するfrontend文字列:

```text
kaldi-fbank80-cmn@16k;trim=none
```

同じ文字列を`.superpowers/sdd/zero-shot-reference-fusion-plan-2026-10-17/g0.txt`の1行目に置いた。

(c)の不合格は、「線形判別（LDA）で学習話者から重みを付けても、統計1024の追加で
未知話者の分離は192次元単独より上がらなかった」という意味である。
計画の融合経路はzero-init MLP（非線形・TTS損失で学習）なので、この結果は効果の上限を示さない。
ただし、CPU段階でF-statsの上積みを支持する根拠は得られなかった。融合経路を続けるかは計画側で判断する。

## 6. 制約と注意

- 話者転写の評価は1話者・3文。WAV001のtrimなし/ありのように埋め込みがほぼ同じでも、
  CERは0.14、ECAPA crossは0.027動いた。(a)(b)の差の多くはこの揺れと同程度である。
  判定規則は退行を丸めずに適用したため、揺れでも不採用になり得る。
- 雑音付き参照は合成条件。実際の利用者録音の無音・残響・雑音を代表しない。
  雑音付きではtrimで両encoderのcrossが上がったので、実録音で再測する価値はある。
  ただし既定値は上の規則に従いtrim=noneとする。
- trimの効果は生成側の参照埋め込みだけで測った。評価側のCAM++ frontendはtrimなしで固定した。
- (b)はTorchだけ。ONNXでg平均を使うには入力schemaの変更が必要で、今回は測っていない。
- (c)の拡張集合は学習で使われた日本語20話者を含む。測っているのは事前学習済みCAM++の性質で、
  TTSの学習とは独立だが、日本語の女性声が多く、言語・性別の幅は狭い。
  floor候補の2話者がMOE-Speech 20話者と同一人物でないことは確認できていない。
  旧cosine診断の標準化は評価集合で計算したもので、別集合への一般化は保証しない。
  R6プローブは学習話者だけで標準化・LDAを当てたが、評価話者は各回12話者・最大120発話と少なく、
  分割ごとのAUCの揺れ（B − Aが-0.040〜+0.035）は大きい。
- 人手による試聴・品質合格の判定はしていない。

## 7. 変更したファイル

| ファイル | 目的 |
|---|---|
| `src/python/piper_train/tools/cpu_reference_comparison.py` | `reference_embedding(..., trim=False)`、`projected_average`、`pairwise_separability`、`lda_speaker_probe` |
| `src/python/tests/test_cpu_reference_comparison.py` | trim同値、1参照のg平均一致、AUC計数、LDAプローブ（情報次元で合格・雑音で不合格・例外は負け扱い）のテスト |
| `scripts/run_reference_fusion_s0.py`、`tests/scripts/test_reference_fusion_s0.py` | S0測定runner（分離度の入力固定、probe stage）とG0判定規則のテスト |
| 本書 | 結果とG0判定 |
