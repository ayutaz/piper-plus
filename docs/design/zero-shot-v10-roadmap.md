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

- [ ] **a. 第 2 speaker encoder**: SpeechBrain `spkrec-ecapa-voxceleb` (Apache-2.0)
      を ONNX 化して SECS 並走 (Goodhart 検知器)。CAM++ と cosine スケール非互換の
      ため per-encoder ceiling/floor 正規化転写率で比較。repo 同梱 ECAPA は学習済み
      重みが存在しない (manifest pending) ため使わない
- [ ] **b. ckpt 診断スクリプト** (`piper_train.tools.diagnose_zs_ckpt`):
      spk_proj 出力ノルム vs emb_lang ノルム (lang 支配の実測)、FiLM 層の
      identity からの乖離 (「FiLM がどれだけ起きたか」)、2 つの embedding 間の
      FiLM 変調差 (話者に対する感度)
- [ ] **c. per-loss 勾配ノルム probe** (`--grad-probe-every N`、opt-in):
      SCL / MRD / full-band STFT / mel 等の勾配ノルムを共有 probe パラメータ上で
      比較 — 「希釈」仮説の直接測定
- [ ] **d. OOD holdout 常設**: つくよみ 5 発話 (取得済み、instance
      `/data/piper/tsukuyomi_ref/`)。JVS はライセンス実確認 (Phase 2 冒頭) まで保留
- [ ] **e. cross-utt SECS 評価ハーネス** (`piper_train.tools.eval_zs_secs`):
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

- [ ] baseline 再測定 (ep49、新ハーネス)
- [ ] Arm A 完走 + 評価
- [ ] Arm B 完走 + 評価
- [ ] Arm C 完走 + 評価
- [ ] Arm D 完走 + 評価
- [ ] 判定マトリクス適用 → Phase 1 構成決定

### A-3. DINO の扱い

c_dino チューニングによる SECS 改善は 3 調査 (C1/C2/L2) が独立に棄却 —
**探索方向として閉じる**。廃止 or view 分離 (student = 別発話 embedding) の判断は
Phase 1 で cross-utt SCL 化と同時に行う (単一変数原則のため Phase 0 arm には同乗させない)。

## Phase 1: v9.1 短期回収 (~$100-150、Phase 0 の結果を受けて)

- [ ] **B-1. SCL InfoNCE の cross-utterance 正例化** (最有力): losses.py の
      labels/mask を同一話者・別発話 index に再配線 (SupCon 形式 ~20 行 + unit test)。
      **footgun**: 対角 (same-utt) は負例化ではなく分母から除外 (neutral) —
      回帰テストで固定。初回は loss 再配線のみの単一変数 A/B (対照 arm 必須、
      SECS は ±0.01/ep 揺れるため対照なしの +0.03 は判定不能)
- [ ] **B-2. σ 縮小の本採用判断**: Arm D が control +0.015 以上なら採用。
      gap 拡大時は B-1 と同時投入に切替
- [ ] **B-3. z_slice.detach()**: SCL 計算時に posterior z を detach し「decoder が
      z から音色を読む」逃げ道を遮断 (数行)。B-1 の第 2 段 arm に同乗
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
