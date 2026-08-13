# Zero-Shot 話者類似度改善ロードマップ (Phase 0-2)

> **Status**: Phase 0 実装中 (2026-08-13 開始)。
> 根拠: [`zero-shot-v10-similarity-research.md`](zero-shot-v10-similarity-research.md)
> (deep research 最終レポート) /
> [`zero-shot-speaker-similarity-root-cause.md`](zero-shot-speaker-similarity-root-cause.md)
> (実測の canonical)。
> 本書は実行計画と進捗の tracking を担う。各項目のチェックボックスを更新すること。

## 運用原則 (全フェーズ共通、違反した評価は無効)

1. **SECS は cross-utterance のみ**。ceiling (同一話者実発話同士) / floor (近い声質の
   別話者) を併記し、正規化転写率 `(SECS - floor) / (ceiling - floor)` で判定する。
   same-utt SECS は判定使用禁止 (0.775 誤報の既知事故)
2. **CAM++ 単独での go/no-go 禁止** — ①CAM++ 正規化転写率 ②第 2 encoder (ECAPA、
   SCL への組み込み恒久禁止 = held-out) ③4-9kHz 帯域スペクトル ④聴感、の 4 点セット
3. **がびがび指標が悪化した arm は SECS が良くても不採用** (v9 の主目的を毀損しない)
4. zero-shot の目標は cross-utt SECS 0.80 (正規化転写率 ~0.5-0.6) まで。
   「確実に似せる」需要は FT 経路 (v7 実績 0.775) を製品導線として案内する

## Phase 0: 診断 (~$150-230、1-2 週) — v9 退行の原因を一意化

### A-1. 診断・評価基盤

- [x] **a. 第 2 speaker encoder**: SpeechBrain `spkrec-ecapa-voxceleb` (Apache-2.0)
      を ONNX 化して SECS 並走 (Goodhart 検知器)。CAM++ と cosine スケール非互換の
      ため per-encoder ceiling/floor 正規化転写率で比較。repo 同梱 ECAPA は学習済み
      重みが存在しない (manifest pending) ため使わない
      — exporter 実装済み (`piper_train.tools.export_ecapa_onnx`、前処理差を
      graph 内吸収 + cosine >0.999 自己検証)。instance での実 export は実行時
- [x] **b. ckpt 診断スクリプト** (`piper_train.tools.diagnose_zs_ckpt`):
      spk_proj 出力ノルム vs emb_lang ノルム (lang 支配の実測)、FiLM 層の
      identity からの乖離 (「FiLM がどれだけ起きたか」)、2 つの embedding 間の
      FiLM 変調差 (話者に対する感度) — 実装済み (テスト 9 件)
- [x] **c. per-loss 勾配ノルム probe** (`--grad-probe-every N`、opt-in):
      SCL / MRD / full-band STFT / mel 等の勾配ノルムを共有 probe パラメータ上で
      比較 — 「希釈」仮説の直接測定。`grad_probe/ratio_spk_to_spectral` を含む
      (実装済み、テスト 10 件、default off でオーバーヘッドゼロ)
- [x] **d. OOD holdout 常設**: つくよみ 5 発話 (取得済み、instance
      `/data/piper/tsukuyomi_ref/`)。JVS はライセンス実確認 (Phase 2 冒頭) まで保留
- [x] **e. cross-utt SECS 評価ハーネス** (`piper_train.tools.eval_zs_secs`):
      dual-encoder + ceiling/floor + 正規化転写率を 1 コマンドで出す標準ツール。
      **arm 比較の前に v9 ep49 baseline を同一ハーネスで再測定する**
      (既存 eval_results.json の 0.652 は測定方法が異なる可能性)

### A-2. 4-arm warm restart 診断 (8ep × 4 arm、逐次、4x A100 SXM4)

| Arm | 変更 | 検証する仮説 |
|---|---|---|
| A (control) | 係数据え置き + fresh cosine LR | スケジュール問題 (LR 枯渇) |
| B | `--c-spk 2.0` | SCL 勾配希釈 (話者側から) |
| C | `--c-mrd 0.5 --c-full-stft 0.25` | SCL 勾配希釈 (スペクトル側から) |
| D | `--spk-emb-noise-sigma 0.01` | σ=0.05 blur 天井 |

**共通ガード (全 arm 必須、1 つでも欠けたら偽陰性リスク)**:

- `--resume-weights-only <ep49 ckpt>` (fresh optimizer/LR。v8→v8.1 で実走前例あり)
- **`--lr-warmup-epochs 0 --kl-annealing-epochs 0`** (default warmup 5 のままだと
  8ep 中 5ep が LR ランプで消え全 arm 偽陰性化)
- v9 の全 architecture フラグを再指定 (`--use-mrd --c-mrd --c-full-stft
  --segment-size 16384 --speaker-encoder-torch-path --spk-loss-type infonce
  --disc-precision 32-true --attn-drop-rel-v --channels-last` 等、v9_train.sh 準拠)
- launch 直後に missing/unexpected keys ログを確認 (`model_d_mrd.*` /
  `scl_encoder.*` が missing に出たら即中断 — strict=False は silent drop する)
- arm ごとに output dir 分離 + **onstart 自動レジューム無効** (v9 launch 事故の再発防止)
- 判定は ep4 / ep8 の 2 点で単調性確認

**事前登録の判定基準** (実行前に固定、後から動かさない):

- zs_ja holdout cross-utt SECS が control 比 **+0.02 未満は「効果なし」**
- Arm B: ECAPA 第 2 SECS が CAM++ と乖離 (CAM++↑ / ECAPA→) なら Goodhart として棄却
- Arm C: 平均スペクトル目視 + 聴感でがびがび再発なら SECS が良くても不採用
- Arm D: same-utt / cross-utt gap の拡大を監視 (utterance-level overfit の新チャネル)

**判定マトリクス**:

| 結果 | 解釈 | 次の一手 |
|---|---|---|
| A のみで回収 | スケジュール問題 | 継続学習 (fresh LR) で回収、リバランス不要 |
| B↑ かつ C↑ | 希釈確定 | Phase 1 でリバランス本採用 |
| D↑ | σ blur 天井 | Phase 1 で σ 縮小本採用 (gap 監視付き) |
| 全 arm 平坦 | dose 不足 or 構造 | **即断せず**勝ち arm 16ep 延長 (+$25) → なお平坦なら構造介入 (Phase 2 C-2) へ |

- [x] baseline 再測定 (ep49、新ハーネス) — zs_ja CAM++ 0.6098 / ECAPA 0.5156、
      つくよみ CAM++ 0.7245 / ECAPA 0.6005、帯域 -7.58dB
- [x] Arm A 完走 + 評価 — **横ばい** (ep8: zs_ja 0.6063 / つくよみ 0.7211)
      → スケジュール (LR 枯渇) 単独説を棄却
- [x] Arm B 完走 + 評価 — **Goodhart 棄却パターン検出** (ep8: zs_ja CAM++
      +0.023↑ / ECAPA +0.002→、つくよみ CAM++ +0.041↑ / ECAPA +0.010→)。
      第 2 encoder が事前登録どおり機能。same/cross gap も拡大 (0.048→0.068)
- [x] Arm C 完走 + 評価 — **効果なし** (ep8: zs_ja 0.6114 = control 比 +0.005
      < +0.02 閾値、つくよみも ep4→ep8 で非単調)。スペクトル側からの
      勾配希釈説は単独では不成立
- [x] Arm D 完走 + 評価 — **効果なし** (ep8: zs_ja 0.6070 = control 比 +0.0007
      < +0.02 閾値、ep4→ep8 減少)。same/cross gap が control 比 +0.013 拡大
      (事前登録の utterance-level overfit 監視が発火) → **σ 縮小 (B-2) は不採用**
- [x] 判定マトリクス適用 → Phase 1 構成決定 (2026-08-13、下記「Phase 0 最終判定」)

### Phase 0 最終判定 (2026-08-13)

全数値: HF `ayousanz/piper-plus-zero-shot-multi-7lang-v8` の `diag-phase0/`
(評価 JSON 9 本 + matrix.txt + 各 arm ep8 ckpt + 合成 wav tar)。

| Arm | zs_ja Δcontrol (CAM++) | ECAPA | 判定 |
|---|---|---|---|
| A (fresh LR) | baseline 比 -0.004 | → | スケジュール説 **棄却** |
| B (c_spk 2.0) | **+0.023** | **+0.002 (→)** | **Goodhart 棄却** (事前登録基準どおり CAM++/ECAPA 乖離 + same/cross gap 0.048→0.068 拡大 + ep4→ep8 非単調) |
| C (MRD 半減) | +0.005 | → | 希釈 (スペクトル側) **棄却** |
| D (σ 0.01) | +0.001 | → | σ blur 天井 **棄却** + gap 拡大で不採用 |

- スクリプトの自動 VERDICT (CAM++ 単独) は「B のみ↑ = 希釈の部分確証」だが、
  事前登録の ECAPA 基準適用後は **係数リバランス系 4 arm 全滅** = 実効的に
  「全 arm 平坦」行
- 事前登録の「勝ち arm 16ep 延長」は**適用対象なし** (B は Goodhart で勝ち arm
  ではない)。dose 不足説も否定的 — B が 8ep で CAM++ を +0.023 動かせた以上、
  勾配は十分届いており、**最適化している目的関数が間違っている**
- **Arm B の挙動 (CAM++↑ / ECAPA→ / gap 拡大) は deep research の構造欠陥①
  (SCL 正例が same-utterance) の直接的な実験的証拠**: c_spk を盛ると「条件に
  使った発話の CAM++ embedding への一致」だけが最適化され、話者としての
  類似 (ECAPA / cross-utt) は動かない
- **結論: Phase 1 は学習信号修正 (B-1 cross-utt SCL 化 + B-3 z_slice.detach)
  を主戦線とする**。B-2 (σ 縮小) は不採用確定。構造介入 (Phase 2 C-2) は
  B-1/B-3 の A/B が平坦だった場合の次段
- Phase 0 実コスト: ~19h GPU ≈ $65 + 評価・基盤 (見積 $150-230 内)

### A-3. DINO の扱い

c_dino チューニングによる SECS 改善は 3 調査 (C1/C2/L2) が独立に棄却 —
**探索方向として閉じる**。廃止 or view 分離 (student = 別発話 embedding) の判断は
Phase 1 で cross-utt SCL 化と同時に行う (単一変数原則のため Phase 0 arm には同乗させない)。

## Phase 1: v9.1 短期回収 (~$100-150、Phase 0 の結果を受けて)

### Phase 1 A/B 結果 (2026-08-13 完走、判定: 両 arm 平坦)

v9 ep49 から 8ep warm restart、対照 = Phase 0 Arm A。全数値: HF
`diag-phase1/` (JSON + matrix.txt + ep8 ckpt)。

| Arm (ep8) | zs_ja Δctrl (CAM++) | ECAPA | gap (same-cross) | つくよみ (CAM++/ECAPA) | 判定 |
|---|---|---|---|---|---|
| E: B-1 単独 | +0.003 | -0.008 | **0.046 (縮小)** | +0.017 / -0.008 | **効果なし** |
| F: B-1+B-3 | -0.008 (ep4→ep8 減少) | -0.001 | **0.040 (縮小)** | **+0.023 / +0.011 (両 encoder 同調)** | **主指標は効果なし** |

- **事前登録の主指標 (zs_ja holdout cross-utt) は両 arm とも +0.02 未満で平坦**
  (matrix.txt 末尾の「判定保留」は集計スクリプトの verdict 分岐バグ — 正しくは
  「両 arm 平坦」)
- 機構面は設計どおり動いた: same/cross gap は control 0.058 → E 0.046 → F 0.040
  と単調に縮小 (= same-utt Goodhart 経路の遮断は効いている)。帯域も非悪化
  (F ep4 -9.8dB)
- F はつくよみ (OOD 1 話者) で唯一、CAM++ +0.023 / ECAPA +0.011 の**両 encoder
  同調の改善**を示した — ただし n=1 のため判定には使わない
- **解釈**: Phase 0 (係数 4 arm) + Phase 1 (信号修正 2 arm) の計 6 介入が
  8ep warm restart で全て平坦 → 「収束済み v9 からの 8ep warm restart」という
  枠組み自体が転写能力を動かせない可能性が高い。50ep かけて焼き付いた
  posterior leak 依存の decoder 挙動を、8ep で g 依存に再学習させるのは
  dose 不足の疑いが残る (F の OOD 兆候と gap 縮小がその傍証)
- ~~次の分岐: Arm F を 24ep へ延長~~ → **実施済み (2026-08-14 完走、下記)**

### Phase 1 延長 (Arm F +16ep = 累計 24ep) 結果 — warm restart 回収不能を確定

| label (累計) | zs_ja CAM++ | ECAPA | gap | つくよみ CAM++/ECAPA | band |
|---|---|---|---|---|---|
| armA_ep8 (ctrl) | 0.6063 | 0.5245 | 0.0581 | 0.7211 / 0.6033 | -7.73dB |
| armF_ep8 | 0.5984 | 0.5238 | 0.0404 | 0.7439 / 0.6138 | -8.38dB |
| armFx_ep16 | 0.6054 | 0.5175 | 0.0440 | **0.7592 / 0.6442** | -10.52dB |
| armFx_ep24 | 0.6205 | 0.5260 | **0.0390** | 0.7513 / 0.6282 | -9.36dB |

- **公式判定 (事前登録)**: ep24 で CAM++ +0.0142 (<+0.02) / ECAPA +0.0015 (<+0.01)
  → **平坦。計 7 介入 (係数 4 + 信号修正 2 + dose 増 1) 全て閾値未達 —
  「収束済み v9 からの warm restart では zero-shot 転写能力は回収できない」を確定**
- 正直な注記: zs_ja CAM++ は 0.5984→0.6054→0.6205 と単調増 (ECAPA は平坦)、
  つくよみ (OOD n=1) は両 encoder 同調で +0.03/+0.025 改善、gap は 0.039 まで縮小、
  4-9kHz 帯域も -1.6〜-2.8dB 改善 — **B-1+B-3 は機構として正しく働いており、
  ゆっくり正しい方向に動いている**。ただしこの速度 (~+0.007/8ep、ECAPA 無反応)
  で閾値到達を追うのは費用対効果が悪く、from-scratch で最初から正しい信号で
  学習させる方が筋が良い
- **Phase 2 投入ゲート (「全 arm 平坦 (dose 増でも)」) は正式に開いた**:
  v10 は C-2 (構造介入) + B-1/B-3 (from-scratch レシピ組込、C-4) + C-1 (ja
  ドメイン被覆) をセットで設計する
- Phase 1 実コスト (延長込): ~$55。成果物: HF `diag-phase1/` (JSON 6 + ckpt 3 +
  matrix 2)

- [ ] **B-1. SCL InfoNCE の cross-utterance 正例化** (最有力): losses.py の
      labels/mask を同一話者・別発話 index に再配線 (SupCon 形式 ~20 行 + unit test)。
      **footgun**: 対角 (same-utt) は負例化ではなく分母から除外 (neutral) —
      回帰テストで固定。初回は loss 再配線のみの単一変数 A/B (対照 arm 必須、
      SECS は ±0.01/ep 揺れるため対照なしの +0.03 は判定不能)
      — **実装済み** (2026-08-13): `--spk-loss-positives cross_utt`。
      brute-force SupCon 参照実装との一致 + 対角 neutral 固定 + 正例なし行の
      除外 + 全行正例なし時の same_utt フォールバックを回帰テスト化
      (`test_scl_differentiable.py`)。A/B run 済 (上記結果表、8ep では平坦)
- [x] **B-2. σ 縮小の本採用判断**: **不採用確定** (Phase 0 Arm D: control 比
      +0.0007 で効果なし、かつ same/cross gap +0.013 拡大 = utterance-level
      overfit の兆候。σ=0.05 を維持)
- [ ] **B-3. z_slice.detach()**: SCL 計算時に posterior z を detach し「decoder が
      z から音色を読む」逃げ道を遮断 (数行)。B-1 の第 2 段 arm に同乗
      — **実装済み** (2026-08-13): `--scl-detach-z`。SCL 専用の decoder
      re-forward (`SynthesizerTrn.scl_waveform_detached_z`) として実装 —
      主経路 y_hat の mel/GAN loss は従来どおり enc_q を学習し、SCL 勾配
      のみ spk_proj + decoder に制限される。勾配隔離 (enc_q grad = 0) を
      実モデルで回帰テスト化。decoder forward +1 回/step のコスト増に注意
- [ ] Phase 0 勝ち構成 + B-1/B-2/B-3 の統合 run
- [ ] **v9.1 go 基準** (事前登録): zs_ja ≥ 0.70 かつ つくよみ cross-utt ≥ 0.75
      (正規化転写率併記) + 帯域スペクトル非悪化 + ECAPA 乖離なし
      → ONNX export + 公開判断

## Phase 2: v10 本格 (~$300-600、2 ヶ月目〜)

- [ ] **C-0. ライセンス実確認を最初のタスクに置く**: JVS (findings 間で商用可否が
      矛盾 — 規約原文確認、NC 確定なら学習除外・ローカル評価のみ) /
      Emilia-YODAS ja (Amphion card と KRAFTON README で表記矛盾 — LICENSE 現物確認)
- [ ] **C-1. ja ドメイン被覆拡充**: 話者「数」ではなくドメイン軸。
      Tier 1: JVS (+100 スタジオ朗読) / Tier 2: Emilia-YODAS ja (+1000 話者級) /
      Tier 3: Common Voice ja (CC0、属性補完 +200-500 話者、既存 exporter ~1 日)。
      除外確定: ReazonSpeech (16kHz + 30 条の 4)、J-CHAT (CC BY-NC)。
      **サンプラー注意**: 最小ドメインが epoch サイズを決める罠 (ko 356 utts 事故) を回避
- [ ] **C-2. 構造介入**: flow の SNAC 化 (speaker-normalized coupling) +
      enc_p 中間 block への AdaLN 注入。ONNX graph 内部変更のみ (契約不変、
      サイズ +<1MB)。**投入ゲート**: Phase 0 全 arm 平坦 (dose 増でも) の場合のみ、
      **学習信号修正 (B-1/B-3) とセットで** (容量だけ増やすと z-leak に吸われる)
- [ ] **C-3. lang_emb / speaker 条件の分離**: 注入点分離 or 直交化正則 +
      dp 用 spk_proj 別ヘッド (韻律平板と両取り)。**投入ゲート**: A-1b の
      学習後ノルム診断で lang 支配が実測された場合のみ
- [ ] **C-4. v10 レシピ**: SCL 遅延導入 + ramp (ep0-5 off → ep5-15 linear)、
      c_spk の勾配ノルム比較正 (≤2-3、それ以上は Goodhart 域)、
      Latent Filling 型補間 augmentation、DINO の廃止/統合
- [ ] v10 from-scratch 50ep + 評価 (目標: cross-utt SECS 0.80 / 転写率 0.5-0.6)

## 不採用 (再検討しない、理由は research doc §4 末尾)

c_dino チューニング / CAM++ joint FT / cross-attention 化 (ONNX 契約破壊) /
参照増量 (飽和実証済み) / decoder 交換 (RTF 悪化) / MRD・full-band STFT 削除
(がびがび再発) / c_spk >3 / ReazonSpeech・J-CHAT・KsponSpeech (ライセンス)

## コスト集計

| フェーズ | 内訳 | 金額 |
|---|---|---|
| Phase 0 | 4 arm × 8ep (~5.5h/arm × $3.43/hr ≈ $75) + 評価 + 基盤 GPU | ~$150-230 |
| Phase 1 | A/B (介入 + 対照) + 統合 run | ~$100-150 |
| Phase 2 | 前処理 ~$100-250 + from-scratch 50ep ~$140-300 | ~$300-600 |
| **合計** | | **~$550-980** |
