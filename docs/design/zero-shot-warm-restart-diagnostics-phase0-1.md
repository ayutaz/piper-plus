# Zero-Shot 話者転写 warm restart 診断 — Phase 0/1 結果レポート (2026-08-13/14)

> **Status**: 完了。本書は Phase 0 (4-arm 係数診断) + Phase 1 (学習信号修正 B-1/B-3
> + dose 延長) の統合結果レポート。
> 実行計画・チェックリストは [`zero-shot-v10-roadmap.md`](zero-shot-v10-roadmap.md)、
> 症状と測定訂正の canonical は
> [`zero-shot-speaker-similarity-root-cause.md`](zero-shot-speaker-similarity-root-cause.md)、
> 機構仮説の出所 (deep research) は
> [`zero-shot-v10-similarity-research.md`](zero-shot-v10-similarity-research.md)。
> 生データ: HF `ayousanz/piper-plus-zero-shot-multi-7lang-v8` の `diag-phase0/` +
> `diag-phase1/` (評価 JSON 15 本 + arm ckpt 7 本 + matrix 3 本 + 再現スクリプト)。

## TL;DR

- v9 ep49 からの **warm restart 計 7 介入が全て事前登録閾値未達** —
  「収束済みモデルへの後付け介入では zero-shot 話者転写能力は回収できない」を確定
- 最大の成果は **Arm B (c_spk 2.0) が「SCL same-utt 正例 = Goodhart」の直接の
  実験的証拠になった**こと: SCL と同型の CAM++ だけ +0.023 上がり、held-out の
  ECAPA は無反応 (+0.002)、same/cross gap は拡大 — 損失は「参照発話の embedding
  への一致」だけを最適化しており「話者に似せる」勾配になっていない
- 修正 (B-1 cross-utt 正例化 / B-3 posterior z detach) は実装・検証済みで
  **機構としては正しく働く** (Goodhart 成分の単調縮小 + OOD 参照で両 encoder
  同調の改善 + 帯域ノイズ改善) が、50ep 焼き付いた挙動の retrofit は遅く、
  24ep でも閾値未達 → **v10 from-scratch レシピに最初から組み込むのが正解**
- 総コスト ~$120 (Phase 0 ~$65 + Phase 1 ~$55)。v10 の $300-600 投資の前に
  「何が効かないか」を安く確定できた

## 1. 背景

v9 (PQMF 修正 + MRD + full-band STFT でがびがび解消) は zero-shot 話者類似度が
退行した (cross-utt SECS: v8.1 0.712 → v9 0.652、つくよみ OOD 0.777 → 0.73)。
deep research (13 エージェント) は機構候補として ①SCL InfoNCE の正例が
same-utterance ②posterior leak (SCL 勾配が enc_p/flow に届かず、decoder が GT
由来の z から音色を読む) ③spk_emb_noise σ=0.05 過大 ④MRD/full-band STFT による
SCL 勾配希釈 ⑤LR スケジュール交絡 を挙げた。本診断はこれらを warm restart A/B で
一意化する。

## 2. プロトコル (全 arm 共通)

- **ベース**: v9 ep49 (`epoch=49-step=66800.ckpt`)、`--resume-weights-only`
  (fresh optimizer)、fresh cosine LR 2e-4→1e-5、**`--lr-warmup-epochs 0
  --kl-annealing-epochs 0`** (8ep 中 5ep がランプで消える偽陰性の防止)、
  8 epoch、他の全フラグは v9 本走と同一。4x A100 SXM4、~3.5-4h/arm
- **ガード**: v9 学習 clone は不変のまま温存 (Phase 1 は実装 commit `6777cb3d`
  に固定した別 clone)。launch 後 watchdog が warm-restart キー検査
  (model_d_mrd / scl_encoder / spk_proj の silent drop 検知) + Phase 1 では
  SCL flag 伝播検証 (学習ログの `spk_loss_positives=` 行) を実施
- **評価** (`diag-phase0/scripts/phase0_eval_arm.py`、固定条件):
  - **zs_ja holdout** (主指標): 学習除外 ja 話者の cross-utt SECS
  - **つくよみ** (OOD 副指標、n=1): cross-utt + ceiling/floor + 正規化転写率
  - **dual encoder**: CAM++ (SCL と同型 = Goodhart に脆弱) と ECAPA
    (SpeechBrain、SCL への組み込み恒久禁止 = held-out 判別器) を並走
  - **same/cross gap**: same-utt SECS − cross-utt SECS。SCL Goodhart で膨らむ
    成分の直接観測
  - **4-9kHz 帯域**: がびがび回帰の gate
- **事前登録判定** (実行前に固定): control 比 CAM++ **+0.02 未満 = 効果なし** /
  CAM++↑ だが ECAPA 不同調 (+0.01 未満) = **Goodhart 棄却** / 帯域悪化 = 不採用 /
  ep4/ep8 の単調性確認

## 3. Phase 0: 係数 4-arm 診断 (2026-08-12/13)

| Arm | 変更 | zs_ja Δctrl (CAM++) | ECAPA | 判定 |
|---|---|---|---|---|
| A (control) | fresh LR のみ | baseline 比 -0.004 | → | **スケジュール説 棄却** |
| B | c_spk 2.0 | **+0.023** | **+0.002 (→)** | **Goodhart 棄却** (gap 0.048→0.068 拡大、ep4→ep8 非単調) |
| C | c_mrd 0.5 + c_full_stft 0.25 | +0.005 | → | **希釈説 (スペクトル側) 棄却** |
| D | σ 0.01 | +0.001 | → | **σ blur 説 棄却** + gap +0.013 拡大で不採用 |

- 絶対値 (baseline): zs_ja 0.6098 / ECAPA 0.5156 / つくよみ 0.7245 / gap 0.048
- **Arm B の含意が本診断の核心**: 勾配は 8ep で CAM++ を +0.023 動かせる =
  dose 不足ではない。動く先が「same-utt embedding 一致」(訓練目的関数の再現)
  であって話者類似ではない。deep research 機構①の直接証拠
- スクリプト自動判定の「B のみ↑ = 希釈の部分確証」は CAM++ 単独の見方で、
  ECAPA 基準適用後は係数リバランス系 4 arm 全滅 = 「全 arm 平坦」

## 4. Phase 1: 学習信号修正 B-1/B-3 (2026-08-13/14)

### 実装 (commit `6777cb3d`、default off で v9 再現性不変)

- **B-1** `--spk-loss-positives cross_utt`: InfoNCE の正例を同一話者・**別発話**の
  参照 embedding に再配線 (SupCon 形式)。対角 (same-utt) は負例化ではなく
  **分母から除外 (neutral)**。正例なし行は損失から除外、全行正例なしは same_utt
  フォールバック。brute-force 参照実装との一致を含む回帰テスト 11 件
- **B-3** `--scl-detach-z`: SCL 専用に posterior z を detach した decoder
  re-forward (`SynthesizerTrn.scl_waveform_detached_z`)。SCL 勾配を spk_proj +
  decoder に制限し、posterior leak (機構②) を遮断。勾配隔離 (enc_q grad=0) を
  実モデルでテスト化。decoder forward +1 回/step のコスト
- テスト: `src/python/tests/test_scl_differentiable.py` (計 13 件追加、
  関連 83 件回帰 pass)

### 結果 (対照 = Phase 0 Arm A)

| Arm (累計 ep) | zs_ja CAM++ | ECAPA | gap | つくよみ CAM++/ECAPA | band |
|---|---|---|---|---|---|
| A ctrl (+8) | 0.6063 | 0.5245 | 0.0581 | 0.7211 / 0.6033 | -7.73dB |
| E: B-1 (+8) | 0.6092 (+0.003) | 0.5165 | 0.0456 | 0.7377 / 0.5958 | -8.09dB |
| F: B-1+B-3 (+8) | 0.5984 (-0.008) | 0.5238 | 0.0404 | 0.7439 / 0.6138 | -8.38dB |
| Fx: F 延長 (+16) | 0.6054 | 0.5175 | 0.0440 | **0.7592 / 0.6442** | -10.52dB |
| Fx: F 延長 (+24) | 0.6205 (+0.014) | 0.5260 (+0.002) | **0.0390** | 0.7513 / 0.6282 | -9.36dB |

- **公式判定: 平坦** (ep24 でも CAM++ +0.014 < +0.02、ECAPA +0.002 < +0.01)
- **機構は設計どおり動いている**:
  - gap (Goodhart 成分) が control 0.058 → E 0.046 → F 0.040 → Fx 0.039 と
    介入強度に応じ単調縮小 = same-utt 一致への過適合は実際に止まった
  - つくよみ (OOD) は F 系で唯一**両 encoder 同調**の改善 (+0.030/+0.025 @ep24、
    ep16 では +0.038/+0.041)
  - 4-9kHz 帯域も -1.6〜-2.8dB 改善 (副次効果)
  - zs_ja CAM++ は 0.598→0.605→0.621 と単調増だが遅く、ECAPA が追随しない
- **解釈**: 50ep かけて焼き付いた「z から音色を読む」decoder 挙動の retrofit は
  この速度 (~+0.007-0.015/8ep、ECAPA 無反応) では費用対効果が成立しない。
  修正自体は有効なので from-scratch で最初から正しい信号で学習させる

## 5. 何がわかったか (learnings)

1. **v9 SECS 退行の機構が確定**: SCL same-utt 正例の Goodhart (Arm B が直接証拠)
   + posterior leak。係数バランス (希釈) / LR スケジュール / σ blur は全て棄却
2. **warm restart という枠組みの限界**: 収束済み ckpt への後付け介入 7 種が
   全て平坦。転写能力は「学習全体で条件付け経路に何を学ばせるか」で決まり、
   後から係数や損失をいじっても短期では動かない
3. **B-1/B-3 は v10 の学習レシピとして妥当**: Goodhart 経路の遮断・OOD 転写の
   改善兆候・帯域非悪化を実測。from-scratch 組込の前提が揃った
4. **測定方法論が確立し、2 回機能した**: cross-utt + dual-encoder (held-out
   ECAPA) + ceiling/floor + gap + 帯域 + 事前登録閾値。Arm B と armFx の
   「CAM++ だけ上がる」を 2 回とも Goodhart として正しく棄却できた —
   ECAPA を SCL に組み込まない原則は今後も維持
5. **診断の値段**: $120 で「何が効かないか」を確定。v10 の $300-600 を
   誤った方向 (係数チューニング) に使うリスクを消した

## 6. 今後 (v10 = Phase 2 の設計指針)

roadmap Phase 2 の投入ゲート「全 arm 平坦 (dose 増でも)」は正式に開いた。

1. **C-0 ライセンス実確認** (最初のタスク): JVS / Emilia-YODAS ja の規約原文
2. **C-1 ja ドメイン被覆拡充**: 話者数ではなくドメイン軸 (スタジオ朗読 /
   多話者多環境 / 属性補完)。最小ドメインが epoch サイズを決める罠に注意
3. **C-2 構造介入**: flow の SNAC 化 + enc_p への AdaLN 注入 (ONNX 契約不変)。
   **B-1/B-3 とセットで**入れる (容量だけ増やすと z-leak に吸われる)
4. **C-4 v10 レシピ**: B-1 (cross_utt) + B-3 (detach z) を最初から ON、
   SCL 遅延導入 + ramp、c_spk の勾配ノルム比較正、DINO の廃止/統合判断
5. **評価は本診断のハーネスを固定条件のまま流用** (HF `diag-phase0/scripts/`)
   — v9/診断 arm との数値直接比較を可能に保つ
6. **並行 (GPU 不要)**: FT ladder (embedding 最適化 → LoRA → full FT) の実装。
   zero-shot の目標は 0.80 (正規化転写率 ~0.5-0.6) まで、「確実に似せる」は
   FT 経路で拾う製品方針は不変

## 7. 再現方法

- 全 runner + 評価ハーネス: HF `diag-phase0/scripts/`
  (`phase0_arms.sh` / `phase1_arms.sh` / `phase1_ext.sh` / `phase0_eval_arm.py` /
  `v9_train.sh`)
- 評価 JSON schema: `phase0-eval-v1` (phase0_eval_arm.py docstring 参照)
- arm ckpt: `diag-phase0/arm{A..D}/` + `diag-phase1/arm{E,F,Fx}/` (各 ep8/ep24)
- 判定マトリクス原文: `diag-phase0/matrix.txt` + `diag-phase1/matrix.txt` +
  `diag-phase1/matrix_ext.txt` (末尾の「判定保留」表記は verdict 分岐バグ、
  正しくは「両 arm 平坦」 — 本書 §4 が正)
