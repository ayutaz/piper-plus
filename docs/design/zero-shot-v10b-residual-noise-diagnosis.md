# v10b 残存ノイズ (がびがび) 診断レポート — 3 層構造の確定 (2026-08-20)

> **Status**: **診断完了 (deep-research 検証済み、2026-08-20)**。§6 の仮説
> 5 点は 6 エージェント (判別実験 3 + 文献 2 + 敵対的統合 1) で全て判定済み —
> **A3 の機序は「推論時 prior ノイズ ε の非調波ロック描画 + 経路盲目」と確定**。
> 関連: [`zero-shot-v10b-quality-plan.md`](zero-shot-v10b-quality-plan.md) §9-10
> (v10b 本走結果) / [`zero-shot-noise-root-cause-pqmf.md`](zero-shot-noise-root-cause-pqmf.md)
> (v9 コム根治の canonical) / [`zero-shot-v10b-s2-f0-design.md`](zero-shot-v10b-s2-f0-design.md)
> (S-2 設計 — §5 の対策本命の土台)
>
> **表記**: 【実測】= 本プロジェクトの測定、【聴感】= ユーザー確認、【推測】= 未検証。

## TL;DR

v10b 完走モデル (ep79 EMA) の聴感「まだざらつき・がびがびが残る」を切り分けた
結果、ノイズは **3 層構造**であり、v10b が根治したのは 1 層のみと確定した:

| 層 | 帯域 | 実測 | 状態 |
|---|---|---|---|
| **A1: フレーム格子コム** (金属的な鳴り) | 4-8.5kHz | comb 超過 3.2→**1.09dB** (GT 0.81) | **v10b で根治** 【実測】 |
| **A2': 高域ノイズ床** | 6-11kHz | GT 比 +4.5〜**+17.3dB** (10-11kHz) | 未解決 — 主因特定済み 【実測】 |
| **A3: 調波間ノイズ充填** (がびがびの主犯) | **1-3kHz** | comb-HNR **-8.6dB** vs GT | **未解決 — 聴感の主犯** 【実測+聴感】 |

- 聴感の「がびがび」は **8.5kHz lowpass でも消えない**【聴感】→ 中域測定で
  A3 を直接確認。声の芯の帯域で調波の間がノイズで埋まっている
- **似ている度合いは v10a より向上**【聴感】— SECS は僅かに低い (0.691 vs
  0.727) のに聴感は改善 = コム除去が知覚的な本人らしさに寄与 (SECS↔聴感の
  相関上限の実例)【聴感+実測】

## 1. 診断の経緯 (切り分けはしご)

1. v10b ep79 raw ckpt 合成 →「似ているが、ざらつきが残る」【聴感】
2. EMA 適用 ONNX 版 (コム 1.50→1.09dB に改善)【実測】→「まだ残る」【聴感】
3. noise_scale 0.4 / 0.2 掃引 → 帯域プロファイル実質不変 (コムはむしろ悪化
   1.09→2.83dB)。**推論ノブでは直らない = 学習/構造の問題**【実測】
4. 1kHz 刻み帯域ベクトル (E-1、GT アンカー) → 6-11kHz に +4.5〜+17.3dB の
   ノイズ床。**旧 4-9kHz 平均指標では 10-11kHz が死角だった**【実測】
5. 8.5kHz lowpass 診断サンプル →「がびがび消えず」【聴感】→ 主犯は中域
6. comb-HNR 直接測定 (調波 bin vs 中間 bin の voiced パワー比):

   | 帯域 | GT | v10b EMA | 差 |
   |---|---|---|---|
   | 1-3kHz | 13.21dB | 4.62dB | **-8.59dB** |
   | 3-5.5kHz | 2.39dB | 0.09dB | -2.30dB (GT 自体ほぼノイズ性) |

   → **A3 (1-3kHz) が聴感の主犯と確定**【実測】

## 2. A1 (コム) — v10b の成果、根治確認

- 発生源 = ConvTranspose1d の格子 (v10b-quality-plan §1.3 #1)。H-1 resize+conv
  化で初期化直後から発生源を除去 (transposed 8.37dB → resize 2.08dB、3 seed)
- 完走後実測: **1.09dB (EMA)** — GT 帯 0.65-0.81 とほぼ同等。>4kHz 残差
  autocorr@128 も 0.003-0.047 (GT ≈0.01)【実測】
- **金属的リンギングの層は消えた。これが「似ている度合いが上がった」聴感の
  一因でもある**【聴感+推測】

## 3. A2' (高域ノイズ床) — 主因は trainable PQMF synthesis のドリフト

- ep79 の合成フィルタは canonical から **rel-norm 42% ドリフト**。周波数応答:
  **band3 (8.3-11kHz) の passband gain +6.9dB** (peak 1.00→2.22)、他 band も
  阻止帯域が -110dB → -39〜-66dB に劣化【実測】
- **GAN が「制約のない学習可能フィルタ」を高域増幅に使った** — same-utt SCL /
  c_spk 増 / swap-SCL cosine に続く「制約なき自由度の gaming」4 例目。
  canonical 初期化は保証にならない (学習圧力で壊れる)
- 外科的検証 (フィルタのみ canonical に復元して再 export): 10-11kHz は
  +17.3→+11.8dB に部分改善するが 9-10kHz が +8.5→+17.2dB に**悪化** —
  **decoder が band3 にノイズを生成しており、ドリフト済みフィルタと共適応**。
  post-hoc 修理は不可【実測】
- 対策 (v10c/v11): (i) trainable filter を外す (PR 正則化を実装するまで封印)、
  (ii) 6-11kHz (特に 9-11kHz) を重み付けした GT 参照 band-weighted MR-STFT 項
  (契約 §2 例外の GT 教師回帰。mel/既存 STFT loss はこの帯域に実質盲目)

## 4. A3 (調波間ノイズ充填) — がびがびの主犯、v9 から持ち越し

- v10a-r2 の帯域解剖 (v10b-quality-plan §1.1 A3) が -2.5〜-3.0dB @1.5-2kHz と
  記録していた成分。今回の測定 (調波 bin vs 中間 bin) では **-8.6dB @1-3kHz**
  — コム (A1) という派手な層が消えたことで聴感の主犯に昇格した【実測】
- H-3 (n_fft 4096 の hires MRD、Δf=5.4Hz) を v10b で有効化したにもかかわらず
  改善していない → **識別器の解像度不足ではない**【実測】
- 構造的背景 (S-2 設計 doc §1 の分析): subband iSTFT head は n_fft=16 /
  SR_sub=5512.5Hz で **bin 幅 344.5Hz** — F0 (~300Hz) の調波微細構造を bin で
  表現できず、調波は「frame 間位相の整合」としてのみ存在する。head の位相
  整合誤差がそのまま調波間ノイズになる【実測 (コード) + 推測】

## 5. 対策の帰結 — v11 で 3 本柱が 1 本の線につながった (2026-08-20 deep-research 反映)

1. **A3 の本修理 = 担体化 harmonic-plus-noise head** (S-2c の拡張)。§6 の検証で
   A3 の機序が「推論時 prior ノイズ ε の非調波ロック描画 + 全損失が recon 経路
   のみ監督 (経路盲目) で ε に圧力ゼロ」と確定したため、損失ベースの対策は
   原理的に届かず、**構造保証**が唯一の直撃手段: head の voiced 帯域出力を
   「S-2c 位相テンプレートへの複素ゲイン + VUV ゲート付き noise 枝」に制限する
   (NSF/uSFGAN/SiFi-GAN の担体化系譜。concat 注入は SiFi-GAN baseline で崩壊が
   実証済み = v10b smoke シフト追従率 0.0 と同型)【実測+文献】。
   **noise 枝バイパス対策 (VUV ゲート + uSFGAN 型 source 正則化) は同梱必須** —
   band0 テンプレート被覆 83% の残り 17% が新たな gaming 自由度になり得る
   (trainable PQMF と同型のリスク)【実測+推測】。
   次点: posterior F0 分離 (SiFiSinger 型、z から音高を奪う) — E2E VITS での
   励振無視根治の公刊実績はこちらが上だが全再学習が必要、§5-3 と一括なら候補。
   暫定緩和: ns default 引き下げ (0.2 で A3 差 -2.2dB) は A1 悪化 (1.09→2.83dB)
   + 韻律平板化とのトレードオフのため聴感 A/B 通過が条件【実測】。
2. A2' の修理 = trainable filter 除去 + 高域重み付き GT 参照 loss (変更なし)
3. 話者類似の壁 (0.60 plateau) = 条件付け経路の容量改修 (変更なし)。
   H-E 再定式化 (§6) により A3 とも接続: multi-spk zero-shot で ε の調波ロック
   描画が獲得されない問題は条件付けの弱さと同根の可能性【推測】

## 6. 仮説検証結果 (deep-research 完了、2026-08-20)

5 系統 (M1: FT モデル判別 / M2: noise_scale 判別 / M3: 損失分解能 /
R1: iSTFT 位相文献 / R2: source-filter 配線文献) + 敵対的統合の判定:

| 仮説 | 判定 | 根拠 |
|---|---|---|
| **H-A: head 構造限界説** | **棄却** (強形) | v10b 本体が ns=0.0 で comb-HNR 12.28dB = GT 級 (GT 13.29)【実測】。同型 head の single-speaker FT (v7 系 zs-FT で代替、n=3) も 11.61dB【実測】。弱形「保証機構なし → 条件付けが弱い zero-shot で最初に破綻する自由度」は存続 (iSTFTNet C8C8I 同 regime、Vocos periodicity 最悪値、CARGAN)【文献】 |
| **H-B: z ノイズ説** | **確定** (エネルギー源として) | ns 用量反応 0.667/0.4/0.2/0.0 → 4.77/6.13/11.07/12.28dB (単調、-8.6dB 差のほぼ全量)【実測】。限定: 同じ ε でも FT は 11.6dB を出す (ns=0.4 マッチド比較) → 病理は「ε の非調波ロック描画」であり ε の存在自体ではない【実測】 |
| **H-C: 損失盲目説** | **原形棄却 → 「経路盲目」に再定式化して確定** | 周波数分解能は十分 (F0~300 の谷 150Hz を mel/full-STFT/MRD が分解可能)【算術】。真の盲目 = 学習時 decoder は posterior z のみ decode (`models.py` L1740-1749、コード検証済)、推論時 prior ε は全損失の監督外。A3 が ε にのみ存在 (H-B) + 配線事実 → どの損失も A3 を罰し得なかったと演繹確定。**H-3 hires MRD 無効の説明もこれ** (D の入力 = 綺麗な recon → 勾配ゼロ)。副次: c_mel は F0≲175Hz 話者の 2-3kHz に盲目 (圧力希釈)【算術】 |
| **H-D: 位相損失欠如説** | **棄却** (A3 の原因として) | deterministic 経路は位相損失なしで GT 級の位相整合を達成済み (ns=0.0)【実測】。文献の anti-wrapping loss は bin 幅 < F0 の full-resolution head 専用 (APNet/APNet2/NSPP) で n_fft=16 subband head に適用対象なし【文献】。head 全面改修 (Vocos/APNet2 型) 時の設計指針としてのみ有効 |
| **H-E: multi-speaker 希釈説** | **原形棄却 → 再定式化して部分確定、機序は未決** | 「調波構造がぼやける」は ns=0.0 GT 級で棄却【実測】。FT/multi-spk 差はマッチド ns で実在 (11.61 vs 6.13dB) → 「multi-spk zero-shot は ε の調波ロック描画を獲得しない (FT は獲得する)」に再定式化【実測】。希釈 (平均化) vs 条件付け容量の切り分けは未実施 — v11 条件付け改修 (§5-3) の検証項目に接続 |

**確定した A3 の因果連鎖**: 推論時 prior ノイズ ε (ns·N(0,1) → flow 逆変換) を
decoder が調波非ロックの広帯域ノイズとして 1-3kHz 調波間に描画する。
deterministic 骨格は無罪。ε 描画は経路盲目により学習圧力ゼロ。single-speaker
FT は decoder 補償でロックを獲得、zero-shot multi-spk では獲得されない。

残タスク (安価、結論を左右しない確認): (i) teacher-forced recon 波形の
comb-HNR 測定 (GT 級の予測 — v10c 着手前に演繹の残穴を塞ぐ)、(ii) v11 評価
セットに低 F0 話者を 1 名追加 (全測定が F0~300Hz 素材のため、c_mel 盲目域の
A3 実態が未測定)、(iii)「v10b からの FT でも ε ロックを獲得するか」は担体化
head の Phase D smoke が事実上兼ねる。

## 7. 資産

- 聴感サンプル: `piper-v8-dataset-backup/v10b_listen_samples/`
  (`tsukuyomi_ema*` / `lpf_ladder_{4000,5500,7000}` / `tsukuyomi_pqmfcanon` /
  `tsukuyomi_ema_lowpass_diag`)
- パッチ ckpt (フィルタ canonical 復元): 同 dir `ep79_pqmf_canon.ckpt`
- 測定コード: 本セッションのインライン (comb-HNR は
  `piper_train.tools` 未収載 — v10c で E 系に追加予定)
- モデル: HF `ayousanz/piper-plus-zero-shot-multi-7lang-v8`
  (`checkpoints-v10b/` + `onnx/v10b-zs-ep79.onnx`)
- deep-research 測定 (2026-08-20): comb-HNR スクリプト + FT/ns 掃引合成 wav は
  session scratchpad (`noise_dr/` 等) — **セッション限定のため、v10c で
  comb-HNR を `piper_train.tools` に E 系メトリクスとして収載する際に移植**
- 代替 FT モデル: HF `ayousanz/piper-plus-zero-shot-tsukuyomi`
  (`tsukuyomi-ft-epoch499-zs.onnx`、v7 系 = pre-v9 PQMF + FiLM の交絡あり)
- 文献アンカー: iSTFTNet 2203.02395 / MB-iSTFT-VITS 2210.15975 / Vocos
  2306.00814 / APNet2 2311.11545 / CARGAN 2110.10139 / NSF 1904.12088 /
  uSFGAN 2104.04668 / SiFi-GAN 2210.15533 / HiFTNet 2309.09493 /
  VISinger2 2211.02903 / SiFiSinger 2410.12536

## 8. 残タスク (i) の実測結果 — 「経路盲目」の前提修正 (2026-08-20)

§6 の残タスク (i) teacher-forced recon の comb-HNR を実測した結果、**deep-research
統合結論の前提の一部が棄却された**。事前登録した検証が結論の穴を実際に塞いだ形。

| 対象 (すべて同一測定系、GT アンカー再現確認済み) | comb-HNR@1-3kHz |
|---|---|
| GT | 13.29dB |
| **teacher-forced recon (z = m_q + ε·σ_q — 学習時に損失が見ていた波形)** | **6.71dB** |
| recon (m_q のみ、ε=0) | 5.73dB |
| recon (+0.667ε) | 6.63dB |
| 推論 ns=0.0 (flow⁻¹(m_p)) | 16.44dB (n=3) |
| 推論 ns=0.667 | 7.71dB (n=3) |

### 修正される結論

1. **「損失は綺麗な recon しか見ていない (経路盲目)」は不支持**【実測】:
   損失が直接見ていた recon 自体が -6.6dB 汚い。学習圧力は「なかった」のでは
   なく「**~6.7dB で平衡した**」— mel スメアリングによる感度不足 or GAN 平衡
   (M3 の (b)(c) が副次から再昇格)
2. **posterior 側の ε は無罪**【実測】: m_q のみでも同水準に汚い。汚れの実体は
   「**posterior z の微細内容を decoder が調波非ロックに波形化する**」こと。
   ns=0 推論が例外的に綺麗 (16.4dB) なのは flow⁻¹(m_p) が滑らかな低エントロピー
   z で微細内容を持たないため【実測+推測】
3. **機序の一般化**: 「prior ε の非調波ロック描画」→「**z の微細内容 (ε 由来か
   posterior 由来かを問わず) の非調波ロック描画**」。ns 用量反応 (§6 H-B) は
   「ε が微細内容を増やす」ことの現れとして両立
4. **対策への含意 — 担体化 head の価値はむしろ上がる**【推測】: 損失ベースの
   対策が届かない結論は不変 (現に損失は見ていて直せなかった)。z の内容に
   よらず調波ロックを強制する構造保証 (§5-1) が recon/推論の両経路に効く
   唯一の手段。S-2 の F0 明示経路の必要性も同時に補強される

生データ: scratchpad `recon_check/` (スクリプト + JSON + 各変種 wav)。
