# Zero-Shot v10 設計 — 故障機構への対策と実行計画 (2026-08-14)

> **Status**: **v10a 本走実行中 (2026-08-14 14:56 UTC launch、80ep from-scratch)**。
> v10a = v9 と同一データ (300,443 utts) で学習信号・構造修正の効果のみを検証する
> 単一変数 run (データ拡充は v10b に分離、本 doc 末尾の「v10a 実行記録」参照)。
> 2a 実装は commit `7b176d7a` (TDD)。Phase 0/1 診断
> ([`zero-shot-warm-restart-diagnostics-phase0-1.md`](zero-shot-warm-restart-diagnostics-phase0-1.md))
> で確定した故障機構に対し、追加文献調査 4 系統 (①推論経路 SCL / leak 対策
> ②構造介入の実装詳細 ③from-scratch レシピ ④軽量成功例の解剖) の結果を統合した
> v10 の設計と実行計画。進捗 tracking は
> [`zero-shot-v10-roadmap.md`](zero-shot-v10-roadmap.md) を継続使用。

## TL;DR

- 調査で**前提が 3 つ覆った**: (1) YourTTS の SECS 0.864 は **SCL なし**で達成
  (著者 erratum: 勾配バグで SCL は流れていなかった) — 効いたのは条件付け配線と
  データ。(2) 我々の総学習量は文献の **~1/10** (117k vs 1M+ step) — v8.1 優位は
  総学習量で説明可能。(3) 実コード監査で **enc_p の話者注入が transformer 全 6 層の
  「後」** / **DP が g を detach** という配線欠陥を新発見 — attention は話者を
  一度も見ておらず、韻律の話者性に学習圧力が存在しなかった
- v10 の核: **①配線修正 (M1-M3: SNAC flow / enc_p 層内注入 / DP un-detach)** +
  **②話者監督を推論経路に通す swap-SCL (ASCL 型、VITS 実証済)** +
  **③レシピ刷新 (80ep / SupCon 改良 / Latent Filling / DINO 廃止)** +
  **④データ話者多様性の回復**。全て ONNX 契約不変・CPU 推論コスト実質ゼロ
- 予算 ~$300-500 / 実装 ~2 週 + 学習 ~2 日。受け入れ基準は事前登録
  (cross-utt SECS 0.80 目標、**SECS 単独ゲート禁止** — SNAC 論文自身が SECS
  Goodhart の文献証拠)

## 1. 調査で確定した新事実 (v10 の前提)

| # | 事実 | 出典 | 含意 |
|---|---|---|---|
| F1 | YourTTS の SCL は実装バグで**勾配が流れていなかった** (erratum 明記)。ablation でも SECS ±0.007 で inconclusive | arXiv:2112.02418 / Coqui TTS #2348 | 0.864 は「g の 4 点注入 + データ」の成果。**SCL チューニングより配線とデータが支配的** — Phase 0 の係数全滅と整合 |
| F2 | 「decoder が z を読む」のは VITS の設計。真の病理は**「flow が推論時の音色注入 (flow⁻¹ の仕事) を学習していない」** | 成功例解剖 | 対策は「flow reverse に話者勾配を通す」= swap-SCL / SNAC に絞られる |
| F3 | **enc_p の g 注入は transformer 6 層通過後** (models.py:238-240)。self-attention は話者情報を一度も見ない | 実コード監査 | VITS2 は 3 層目入口に注入 (演算は同じ加算)。0.5 人日で修正可能 |
| F4 | **DP は g を detach** (models.py:78-81, 170-172)。duration loss の勾配が spk_proj に届かず、話速・リズムの話者性に学習圧力ゼロ | 実コード監査 | 既知の「韻律平板」の構造的原因候補。StyleTTS 2 は DP を style で AdaIN 変調 (style encoder 除去 CMOS -0.35) |
| F5 | 我々の総学習量 ~117k step は文献 (1M-2.2M) の **~1/10** | YourTTS / HierSpeech++ / arXiv:2506.20190 | v8.1 (累積 120ep) > v9 (50ep) は総学習量で説明可能。**80ep 化** |
| F6 | HierSpeech++ 実測: **ノイズ込みでもデータを増やすと similarity は単調増** (5x hours で SECS +0.021) | arXiv:2311.12454 Table V | 案 Z ゲート (ko 全除外含む) は SECS には逆方向。がびがび対策との再バランス要 |
| F7 | 我々の spk_emb_noise σ=0.05 は Latent Filling の文献値 σ=0.0001 の **500 倍**、かつ noise は効果の小さい成分 (補間が支配的: ablation CSMOS -0.115 vs -0.031) | arXiv:2310.03538 | σ noise 廃止 → Latent Filling (補間 + LFCL) に置換 |
| F8 | DINO-VITS の効果の本体は「ノイズ拡張 view + speaker encoder の joint FT の正則化」。我々の版 (frozen CAM++ / 同一入力 / 拡張なし) は**慣性項に退化** | arXiv:2311.09770 | **DINO 廃止** (c_dino=0)。cross-utt SupCon が機能的上位互換 |
| F9 | SNAC は **SECS で YourTTS に負け SMOS で +0.33 勝つ** — 論文自身が「YourTTS の高 SECS は SCL 直接最適化の結果」と指摘 | arXiv:2211.16866 | SECS 単独ゲート禁止の文献的裏付け。評価は SECS + ECAPA + 聴感 + 帯域の 4 点維持 |

## 2. 故障機構 → 対策マッピング

| 故障機構 (Phase 0/1 + 監査で確定) | 対策 | 状態 |
|---|---|---|
| ① SCL 正例が same-utt (Goodhart、Arm B で実証) | B-1 cross-utt SupCon (**実装済**、L_out 形式確認済) + 改良 (§3.2) | 実装済 + 改良待ち |
| ② posterior leak / flow が音色注入を学ばない | **S1 swap-SCL** (§3.1、最有力) + M1 SNAC flow (§4) | 新規 |
| ③ 条件付け配線の欠陥 (enc_p 注入位置 / DP detach) | **M2 + M3** (§4) | 新規 (監査で発見) |
| ④ 総学習量不足 (文献の 1/10) | 80 epoch 化、単一 cosine | レシピ |
| ⑤ σ=0.05 noise は破壊的で効果なし (Arm D) | 廃止 → **Latent Filling** (§3.3) | 新規 |
| ⑥ DINO の退化 | 廃止 (c_dino=0) | 削除 |
| ⑦ ja ドメイン偏重 + 話者多様性の削りすぎ (F6) | C-0/C-1 データ拡充 + ゲート再バランス (§5) | roadmap 継承 |

## 3. 学習信号の設計

### 3.1 S1: swap-SCL — 話者監督を推論経路に通す (最有力の新規要素)

ASCL (arXiv:2210.05979、APSIPA 2022、**VITS 上で実証**: SMOS +0.30/+0.41) の翻案。
学習中に batch 内の別話者 embedding g_q で flow を逆走させて生成し、そこに
speaker loss を当てる:

```
z_p    = flow(z, g_s)              # posterior z を話者 s の統計で非依存化 (既存 forward)
z_swap = flow⁻¹(z_p, g_q)          # 別話者 q の統計で再注入
y_swap = dec(slice(z_swap), g_q)   # 既存 slice indices を流用
L_swap = 1 - cos(CAM++(y_swap), g_q)   # (または batch InfoNCE)
```

- **Goodhart 構造耐性**: z の中身は話者 s 由来なので decoder は z から目標話者 q の
  音色を読めない — same-utt Goodhart が経路的に不可能。**flow reverse + decoder
  FiLM に初めて話者勾配が届く** (機構②への直撃)
- duration/MAS 不要 (z 再利用)。コスト +15-25%/step (flow は軽く、実体は dec slice
  1 回 + CAM++ 1 回)。半バッチ / N step ごとの gating で調整可
- **ガード**: (a) 初期は**同一言語内でのみ swap ペア** (cross-lingual swap は VC
  として高難度、sampler 小改修)。(b) KL annealing 完了 (~10ep) 後に weight ramp
  (文献一致: StyleTTS 2 / DINO-VITS / arXiv:2207.04659)。(c) speaker-conditional
  discriminator (ASCL 原典の第 2 要素) は**第二段** — まず cosine 版で A/B
- 完全 prior 経路 cycle (text→enc_p→flow⁻¹、MulliVC 型) は**不採用**: コスト 3 倍級 +
  初期不安定、増分は enc_p の g 1 本のみ (M2 修正後は bias 1 本ではなくなるが、
  それでも swap-SCL 比の増分は小)

### 3.2 B-1 SupCon の改良 (実装済コードへの追加)

- **勾配が通る DDP all_gather** (`torch.distributed.nn.all_gather`) で 4 GPU 分の
  embedding を結合 — 負例 28 → **124** (通信 数十 KB/step)。素の `dist.all_gather`
  は勾配を切る既知の footgun (テストで固定)
- **温度 0.07 → 0.1** (SupCon 全実験値)
- samples_per_speaker=4 維持 (正例 3 は SupCon 的に正しい、負例は all_gather で稼ぐ)
- L_out 形式は実装済みコードで確認済 (log の外で正例平均)
- recon 経路の SupCon は**補助**に格下げ (主軸は S1)。B-3 (`--scl-detach-z`) は
  recon 経路 SCL を残す場合のみ併用 (swap 経路では構造的に不要)

### 3.3 Latent Filling (σ noise の置換、arXiv:2310.03538)

- 確率 **τ=0.25** の iteration で発動: **同一言語**の 2 話者を λ~Beta(0.5,0.5) で
  補間 (確率 0.5) or N(0, σ=1e-4) noise (確率 0.5)
- LF iteration は再構成 loss なし、**LFCL のみ**: 補間 embedding で生成した音声の
  CAM++ embedding を条件 embedding に戻す cosine (微分可能 CAM++ 資産を流用)
- 実測: SECS +0.009/SMOS +0.14 (intra)、ablation で補間成分が支配的
- `--spk-emb-noise-sigma` は v10 で default 0 (廃止)

### 3.4 スケジュール (80ep、単一 cosine)

| loss | 0-10ep | 10-15ep | 15ep- | 備考 |
|---|---|---|---|---|
| mel / KL / dur / adv / fm / MRD / full-STFT | 通常 | 通常 | 通常 | v9 のがびがび対策は全維持 |
| S1 swap-SCL | 0 | 0→目標 ramp | 目標値 | KL annealing 完了後 |
| B-1 SupCon (recon、補助) | 0 | 0→目標 ramp | 目標値 | |
| Latent Filling τ | 0 | 0 | 0.25 | |
| DINO | 0 | 0 | 0 | 廃止 |

- 係数の絶対値は smoke で **`--grad-probe-every` (実装済) の勾配ノルム比**を見て
  「speaker 系合計 = mel の 5-15%」に較正してから確定 (GradNorm/CoV 等の自動均衡は
  不採用 — GAN loss が前提外、hand-tuned と同等の文献実測)
- warmup 5ep / base 2e-4 / min 1e-5。段階分割はしない (2 段が偉いのではなく累積が
  効いていたという解釈)

## 4. 構造介入 (M1-M3 + E1/E2、全て ONNX 契約不変)

投入順序: **M2 → M3 → M1** (低リスクから。M1 は logdet 変更を伴う唯一の危険な
変更なので最後に単独投入し、KL 異常時に原因を一意化)。

| # | 介入 | 工数 | 効果根拠 | リスクと必須ガード |
|---|---|---|---|---|
| **M2** | enc_p の g 注入を **transformer 3/6 層目の入口**に移動 (既存 cond_layer 流用、加算位置を移すだけ) | 0.5 日 | VITS2 同構成 (F3)。費用対効果最良 | ほぼ無し |
| **M3** | DP の **g detach 解除** (x の detach は維持) + `spk_proj_dp` 軽量残差ヘッド経由で spk_proj 本体を保護 | 0.5-1 日 | F4 + StyleTTS 2 (CMOS -0.35) | DP 勾配の spk_proj 撹乱 → 別ヘッドで緩和。FP16 +0.5MB |
| **M1** | flow 4 段を **SNAC 化**: coupling 入口で `SN(x;g)=(x-m(g))/exp(v(g))`、inverse 出口で `SDN`。**WN は gin_channels=0 化** (g は SN/SDN 経由のみ — 置換であって追加ではない) | 1.5-2.5 日 | SNAC 実測 SMOS +0.18 / MOS +0.40。「加算バイアスは NN が無視できるが正規化は迂回不能」 | **logdet=-Σv≠0 → KL への配線必須** (現行は logdet 破棄、漏らすと KL が静かに壊れる)。可逆性 unit test (`flow⁻¹(flow(z))≈z`) 必須。`v` clamp [-4,4] (bf16)。パラメータはむしろ減 |
| **E1** | zero-init 群 (sn_linear / dec FiLM / spk_proj_dp) を **N(0,1e-3)** small-Gaussian に | 0.2 日 | AdaLN-Zero 分析 (arXiv:2608.09438): 同等品質に ~46% 少ない学習時間 | 低 |
| **E2** | SNAC の SN 統計を **話者のみ**から予測 (lang_emb は加算経路に残す) — `g=spk+lang` の和を SN に渡すと正規化統計に言語が混入 | 0.5 日 (M1 と同時設計) | LNACont (EUSIPCO 2024) が同問題の直系 follow-up | LNACont 本文は未入手 (追跡) |

不採用: mean_only=False (VITS 固有証拠ゼロ + 行列式爆発リスク + M1 と変数重複) /
SC-CNN (動的 conv が ORT 非適合) / flow の Transformer+AdaLN-Zero 化 (CPU コスト
制約に抵触、4-6 人日) / GRL (λ 感度 +「似た話者に写すだけ」問題) / posterior 入力
摂動 (FreeVC SR の TTS 翻案) は**文献先例なしのため optional A/B arm 止まり**
(採用は smoke A/B で KL 副作用がないことを確認できた場合のみ)。

## 5. データ (C-0/C-1 の再バランス)

- **C-0 ライセンス実確認** (実装と並行で最初に): JVS / Emilia-YODAS ja の規約原文
- **C-1**: Tier 1 JVS (+100 スタジオ朗読、つくよみ同ドメイン) / Tier 2
  Emilia-YODAS ja (+1000 話者級) / Tier 3 Common Voice ja (CC0、属性補完)
- **F6 を受けた方針変更**: 「クリーンに絞る」より話者多様性。**ko 復活を検討**
  (v10 で高品質 ko 調達 or Zeroth を帯域条件付きで部分復活 — ただし
  language-balanced sampling の最小言語問題 (356 utts 事故) の回避設計が前提)。
  案 Z ゲートの緩和はがびがび再発リスクと表裏のため、**帯域メトリクス
  (hi_ratio/fmax) での再検証付き**で段階的に
- 評価 holdout: zs_ja (既存) + つくよみ + (JVS がライセンス OK なら JVS holdout
  常設 — 1 話者過適合の防止)

## 6. 実行計画

| 段 | 内容 | 期間/コスト |
|---|---|---|
| **2a 実装** (ローカル、GPU 不要) | M2/M3/E1 → M1+E2 (可逆性テスト込) → S1 swap-SCL (同一言語 sampler 込) → SupCon all_gather+τ → Latent Filling → DINO 廃止 flag → 単体テスト | ~2 週 (実装 ~6-8 人日 + テスト) |
| **2b データ** (並行) | C-0 ライセンス → C-1 前処理 (JVS/Emilia/CV ja、ko 判断) + ゲート再バランス | ~$100-250 |
| **2c smoke + 較正** (GPU 再レンタル) | 2-3ep smoke: VRAM / sec/step / 勾配ノルム較正 (speaker 系 = mel の 5-15%) / KL 曲線 (M1 logdet 配線の検証) / swap-SCL 安定性。optional: posterior 摂動 A/B | ~$30-60 |
| **2d 本走** | from-scratch **80ep** (4x A100、~35-40h、swap-SCL コスト込) + 評価 (固定ハーネス + ECAPA + 帯域 + 聴感) | ~$150-200 |
| 合計 | | **~$300-500、~1 ヶ月** |

**受け入れ基準 (事前登録、変更禁止)**:

- 主指標: zs_ja holdout cross-utt SECS (CAM++) **0.70 以上** (v8.1 水準回復) を
  必達、**0.80 到達で目標達成**。つくよみ (OOD) cross-utt **0.75 以上**
- **ECAPA 正規化転写率の同調必須** (CAM++ 単独判定禁止 — F9)
- 4-9kHz 帯域 v9 比非悪化 (がびがび gate) + 聴感確認
- 中間評価: ep20/40/60/80 の 4 点で軌跡確認 (ep35 型飽和の早期検知)

## 7. リスク表

| リスク | 影響 | 緩和 |
|---|---|---|
| M1 logdet→KL 配線漏れ | KL が静かに壊れ学習全損 | 可逆性 unit test + KL cap abort ガード (実装済) + M1 を単独で最後に投入 |
| swap-SCL の cross-lingual 難度 | 初期発散 / 品質低下 | 同一言語 swap 限定 + ramp + cosine 版から (D 追加は第二段) |
| bf16 での exp(v) overflow | NaN | v clamp [-4,4] + 既存 NaN skip 機構 |
| ゲート緩和でがびがび再発 | v9 の主目的毀損 | 帯域メトリクス再検証付きの段階的緩和、悪化なら差し戻し |
| 80ep でも飽和 | 目標未達 | ep20/40/60 中間評価で軌跡確認、飽和なら延長せず構造の追加介入 (E3 等) を再設計 |
| CAM++ frozen が天井 (F8 の系) | 0.80 未達の残存要因 | v10 では受容。v11 候補: CAM++ torch 化 + joint FT (DINO-VITS 型正則化付き) |

## 8. 調査の出典サマリ

4 レポートの全文は本セッションの調査エージェント出力 (要点は §1 の F1-F9 に凝縮)。
主要文献: ASCL 2210.05979 / SNAC 2211.16866 / StyleTTS 2 2306.07691 / FreeVC
2210.15418 / HierSpeech++ 2311.12454 / Latent Filling 2310.03538 / DINO-VITS
2311.09770 / SupCon 2004.11362 / VITS2 2307.16430 / YourTTS 2112.02418 (+erratum
Coqui TTS #2348) / AdaLN-Zero 分析 2608.09438 / DMOSpeech 2410.11097 /
MulliVC 2408.04708 / NANSY 2110.14513 / OpenVoice 2312.01479。
追跡課題: LNACont (EUSIPCO 2024) 本文入手 (E2 設計の裏付け) / SNAC Table I
baseline 確定値。

## 9. v10a 実行記録 (2026-08-14)

- **構成**: v9 CLI + v10 差分 (M1+E2 SNAC / M2 layer-3 注入 / M3 DP head / E1
  1e-3 init / cross_utt SupCon + gather + τ0.1 / detach-z / swap-SCL start10
  ramp5 / DINO off / σ=0 / LF off) / 80ep 単一 cosine / batch 32×4 GPU。
  instance: vast.ai 47698156 (4x A100 SXM4 40GB、NVLink NV12、$3.73/hr)
- **係数較正 (smoke 400 step の grad-probe 実測)**: mel ノルム中央値 23.24 /
  SupCon 18.28 (c=1 で mel の 79%!) / swap 2.69 → 設計目標 (speaker 系 = mel の
  10%、spk:swap = 1:2) から **c_spk=0.0424 / c_swap_spk=0.577**。
  副産物: v9 の c_spk=1.0 は「希釈」どころか mel 級の勾配だった (Phase 0 の
  希釈説棄却と整合する事後証拠)
- **smoke 実測**: sec/step 10.48 (序盤 I/O 込) / non-finite 0% / loss_kl 2.96
  (**SNAC logdet→KL 配線の実地検証 pass**) / VRAM 定常 32-35GB
- **事前登録 gate からの逸脱 2 件 (記録)**: ①VRAM peak 40.3GB > 38GB は起動時
  一過性スパイク (定常 32-35GB、OOM なし、本走起動時は swap 無効でさらに軽い)
  として override。②c_spk=0.042 が事前範囲 [0.1,4.0] 外 — 範囲が当てずっぽう
  だっただけで較正の正しい出力として採用
- **データ復旧 2 件 (バックアップ欠落、教訓)**: HF の v8ds tar は 7lang dir のみ
  で、①ja/en の audio cache 150,379 utts 分 (dataset-bilingual-ja-en-v8) と
  ②speaker_embeddings 10,652 件が欠落していた。cache 名 = sha256(audio_path)
  の決定論性を利用し、raw 再取得 (moe-speech-plus + LibriTTS-R、export は
  default パラメータで 100% カバレッジ再現) → cache_norm_audio_no_vad で再生成
  → 全 300,443 行 × 全パス種別の存在 + 実 load 検証で完全復旧。
  **再発防止 TODO: dataset.jsonl のパス相対化 + バックアップの復元検証**
- **判断点**: ep19/39/59/79 で CPU 中間評価 (v9 ep49 baseline 比、goodhart 判定
  付き)。**ep39 で平坦なら打ち切り** (支出 ~$120-170)。完走時 ~$280-400。
  成果物: HF `checkpoints-v10a/` に自動退避

## 10. v10a インシデント分析 — swap-SCL の prior 経路 Goodhart (2026-08-15)

**要約**: v10a は ep27 まで健全に改善した後、ep28-33 で prior 経路 (推論経路) の
話者性が崩壊し部分回復する振動に入った。学習を ep39 で停止。原因は
**swap-SCL の frozen-CAM++ cosine 目的関数**と結論。

### 実測トレース (全て HF `v10a-results/` に JSON 保存)

| ep | zs_ja CAM++/ECAPA | つくよみ CAM++/ECAPA | 備考 |
|---|---|---|---|
| 19 | 0.568 / 0.466 | 0.703 / 0.550 | 健全 (v9 同時期を上回る軌跡) |
| 27 | **0.589 / 0.487** | 0.697 / 0.563 | **ピーク。v9 完走 (0.610/0.516) まで -0.02** |
| 33 | 0.503 / **0.265** | 0.479 / **0.117** | 崩壊 (ECAPA が特に激しい) |
| 39 | 0.528 / 0.382 | 0.670 / 0.292 | 部分回復 |
| 33 EMA | 0.478 / 0.217 | 0.440 / 0.109 | **EMA でも救われない = 実態** |
| 39 EMA | 0.529 / 0.378 | 0.634 / 0.270 | 同上 |

### 原因分析 (証拠ベース)

1. **学習側 loss は完全に平穏**: ep18-40 の gen/disc/mel/swap/spk/fm 全系列に
   スパイクなし。KL も滑らかに ~2.7 でプラトー (v9 定常 ~2.6 と同水準、
   swap 開始 ep10 に変曲点なし)。**崩壊は posterior 経路の学習信号からは
   不可視** — 唯一 dur loss だけが緩やかに悪化 (1.91→2.00)
2. **ECAPA ≫ CAM++ の非対称崩壊**: ep33 つくよみで CAM++ 0.479 に対し ECAPA
   0.117。出力が「CAM++ を部分的に満足させる特徴」を保ったまま実際の話者性を
   失っている = **frozen encoder 狙いの adversarial 的特徴の蓄積**
3. **機構**: swap 経路 (flow⁻¹ + dec) への学習信号は「CAM++ cosine を上げろ」
   **のみ**で、品質・自然性の対抗信号が存在しない。flow は SNAC スケールを
   使ってこれを満たしに行き (sn ノルムが単調成長: flow6 の v 0.65→1.71)、
   prior 経路が CAM++-gaming の方向に彫刻される。posterior 経路 (全学習 loss)
   はこれを検知できない
4. **ASCL 原典との差が敗因**: 原典は speaker-conditional **discriminator**
   (共進化するため静的に game 不能) + α=0.3。我々の cosine 簡略版 (較正値
   0.577) は frozen encoder 相手なので gameable — 文献の設計選択には理由があった
5. EMA 救済不能の追加所見: 現行 EMA は dec+spk_proj のみをカバーし
   flow/enc_p/dp は対象外 (SNAC 導入後は EMA 対象の再設計が必要)

### 副次的成果 (v10a は無駄ではない)

- **ep27 時点で v9 完走の -0.02 まで到達** (v9 は 50ep 完走、v10a は 27ep 時点、
  LR 未減衰) — M1-M3 配線修正 + SupCon 改良の土台は機能している可能性が高い
- 中間評価チェーン (prior 経路の定点観測) が崩壊を検知した — この監視は
  learning signal が見えない故障モードに対する唯一の検出器だった
- がびがび指標は全期間で v9 より良好 (-9〜-12dB)

### 改善案 (議論用、優先度順)

| 案 | 内容 | コスト | 期待 / リスク |
|---|---|---|---|
| R1 | **ep27 から swap OFF で再開** (c_swap=0、他は不変、80ep まで) | ~$95 (53ep) | M1-M3+SupCon の綺麗な検証。ep27 の軌跡が続けば v9 超えの可能性。leak 対策は失うが土台の判定が最優先 |
| R2 | swap を **識別器形式** (ASCL 忠実) で再実装 → v10b で投入 | 実装 2-3 日 | 文献実証形式。共進化するため gaming 不能。v10a では入れない (単一変数原則) |
| R3 | prior 経路の監視強化: 中間評価の頻度を上げ (10ep→5ep 毎) + ECAPA 乖離での自動 abort | 実装 0.5 日 | 今回型の故障の早期検出 (今回は ep33 検出 → ep28 頃発症) |
| R4 | EMA 対象を flow/enc_p に拡張 (SNAC 時代の必須整備) | 実装 0.5 日 | 振動耐性。v10b から |
| R5 | 完全打ち切り → v10b 設計へ直行 | $0 | ep27 の好軌跡を検証しないまま次へ (情報損失大、非推奨) |
