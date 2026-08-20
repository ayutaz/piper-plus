# v10b 残存ノイズ (がびがび) 診断レポート — 3 層構造の確定 (2026-08-20)

> **Status**: 診断確定 (聴感 × 測定の突き合わせ完了)。deep-research による追加
> 検証が本 doc の §6 (未検証仮説) を対象に進行中。
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

## 5. 対策の帰結 — v11 で 3 本柱が 1 本の線につながった

1. **A3 の本修理 = F0 明示経路の「無視できない配線」** (S-2 の本来の狙い)。
   v10b smoke で「decoder が F0 を無視する」(シフト追従率 0.0) 失敗を確認済み
   のため、オプション特徴の追加ではなく**励振を担体として飲み込ませる
   source-filter 型** (または prior 残差の強制) で再設計する【推測、v11 設計対象】
2. A2' の修理 = trainable filter 除去 + 高域重み付き GT 参照 loss
3. 話者類似の壁 (0.60 plateau) = 条件付け経路の容量改修 (oracle 診断 §8 の帰結)

3 つとも decoder / アーキテクチャの改修であり、v11 として一括設計する。

## 6. 未検証仮説 (deep-research の対象)

A3 の機序について、以下は**まだ検証されていない**:

- **H-A: head 構造限界説** — bin 幅 344.5Hz の iSTFT head では位相整合の学習が
  原理的に困難。反証可能: 同一 head 構造の single-speaker FT モデル
  (tsukuyomi MB-iSTFT FT) が GT 級の comb-HNR を出すなら、構造ではなく
  学習信号/条件付けの問題
- **H-B: z ノイズ説** — posterior/prior の stochastic z が調波間ノイズとして
  透過する。noise_scale 掃引で帯域プロファイルは不変だったが comb-HNR は
  未測定 (掃引サンプルはローカルにあり測定可能)
- **H-C: 損失盲目説** — mel (80 bins) の 1-3kHz でのフィルタ幅と調波間隔の
  関係で、mel loss が調波間ノイズを分解できない。MRD hires が効かなかった
  事実との整合の説明が必要
- **H-D: 位相損失欠如説** — magnitude 系 loss のみで位相整合への直接圧力が
  無い (anti-wrapping phase loss 等の文献対策の適用可能性)
- **H-E: multi-speaker 希釈説** — 3.7k 話者の平均化で調波構造がぼやける
  (FT で消える A1 の前例と同型)

## 7. 資産

- 聴感サンプル: `piper-v8-dataset-backup/v10b_listen_samples/`
  (`tsukuyomi_ema*` / `lpf_ladder_{4000,5500,7000}` / `tsukuyomi_pqmfcanon` /
  `tsukuyomi_ema_lowpass_diag`)
- パッチ ckpt (フィルタ canonical 復元): 同 dir `ep79_pqmf_canon.ckpt`
- 測定コード: 本セッションのインライン (comb-HNR は
  `piper_train.tools` 未収載 — v10c で E 系に追加予定)
- モデル: HF `ayousanz/piper-plus-zero-shot-multi-7lang-v8`
  (`checkpoints-v10b/` + `onnx/v10b-zs-ep79.onnx`)
