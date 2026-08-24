# Zero-Shot v11 ロードマップ — 構造保証による品質改修 (2026-08-20)

> **Status**: 設計完了 (設計スパイク 2 本 + 診断 3 本の統合)。実装未着手。
>
> 子 doc (詳細はそちらが正):
> - [`zero-shot-v10b-residual-noise-diagnosis.md`](zero-shot-v10b-residual-noise-diagnosis.md)
>   — 診断 canonical (3 層構造 + deep-research 検証 §6 + recon 修正 §8)
> - [`zero-shot-v11-harmonic-head-design.md`](zero-shot-v11-harmonic-head-design.md)
>   — A3 対策の設計 (案 A′、プロトタイプ実測済み)
> - [`zero-shot-v11-conditioning-design.md`](zero-shot-v11-conditioning-design.md)
>   — 話者類似対策の設計 (診断 D-1〜D-9 + 改修 P0-P5)
> - [`zero-shot-v10b-quality-plan.md`](zero-shot-v10b-quality-plan.md) §8 (oracle) /
>   §9 (v10b 結果) — v11 の動機
>
> **表記**: 【実測】【文献】【推測】ラベルは子 doc に従う。

## TL;DR — v11 は「損失で誘導する」から「構造で保証する」への転換

v10b の教訓: 損失・識別器をいくら強化しても、(i) 調波間ノイズは直らず
(損失は汚れた recon を見ていて ~6.7dB で平衡【実測】)、(ii) 話者類似の
0.60 壁も動かない (識別器圧力でも不変【実測】)。v11 は 3 本柱すべてを
**アーキテクチャの構造変更**で攻める:

| 柱 | 問題 | v11 の対策 | 根拠 doc |
|---|---|---|---|
| 1 | がびがび (A3、1-3kHz 調波間ノイズ -8.6dB) | **担体化 head (案 A′)**: 調波エネルギーは F0 位相テンプレート担体からしか出せない構造。敵対的ゲインでも comb-HNR 26dB を構造保証【実測】 | harmonic-head §3-5 |
| 2 | 高域ノイズ床 (A2'、6-11kHz +17dB) | **trainable PQMF 封印** (gaming 4 例目の元凶除去 — A′ の alias 相殺の成立条件でもある) + 高域重み付き GT 参照 loss | diagnosis §3 |
| 3 | 話者類似の壁 (in-domain 0.60 / seen 話者識別 43%) | **診断 D-1〜D-9 で律速点を一意化 → P0 (FiLM 形式修正) + モジュール別条件付け改修 (P2-P5)** | conditioning §3/§5/§7 |

## 1. 実行フェーズ

### Phase 0: ローカル診断 ($0、GPU 不要、~2-3 日)

改修の的を絞る。conditioning doc §3 の D 系バッテリを v10b ep79 ckpt で実行:

- **D-5 recon oracle / D-6 VC oracle** が主判定: decoder 律速 / flow 律速 /
  prior 彫刻不足の 3 分岐に一意化 (判定マトリクスは conditioning §3.2)
- D-3/D-4 (注入点 leave-one-out — 「全点注入が SNAC を中和」仮説の直接検証)、
  D-7 (conditioning gain 外挿 — 応急ノブ候補)、D-1/D-2/D-8/D-9
- 規模 ~500-800 wav、oracle ハーネス (quality-plan §8) 流用

### Phase A: 実装 (TDD、GPU 不要、~2-3 週)

1. **柱 1: 担体化 head (案 A′)** — harmonic-head §3 の仕様で実装。
   要点: 解析重み conj(H_k) lookup / MatMul 融合形 (素朴実装は 3-5 倍遅い) /
   固定 Hann k=5 ゲイン平滑 (低 F0 保護) / noise 枝 = log σ 9ch /
   L_src hinge は default off で実装のみ。S-2 実装 (F0 predictor + キャッシュ)
   は土台としてそのまま、S-2c concat を置換。E1c (conj 罠) をテスト fixture 化
2. **柱 2**: `--trainable-pqmf-synthesis` を deprecated 化 (v11 では拒否) +
   band-weighted MR-STFT 項 (6-11kHz、CLI opt-in)
3. **柱 3**: P0 (FiLM scale 開放 1+γ̂ zero-init — 2 行 + テスト) は無条件実装。
   P2 (enc_p AdaLN) / P3 (decoder AdaIN) / P4 (T-Flow lite) / P5 (注入再配分)
   は **Phase 0 の分岐結果で採否確定** (全部盛りは SNAC 中和の再演リスク)
4. 評価系: comb-HNR を `piper_train.tools` に E 系収載 (**出力自身の F0
   トラックで測る** — harmonic-head deviation 4 の測定罠) + seen 話者 20 択
   識別 top-1 を Phase E 中間評価に追加 (診断専用、go/no-go 不使用) +
   低 F0 話者を評価セットに 1 名追加

### Phase B: smoke (instance、~$30-60)

v10b と同じ 2-arm 方式 + 事前登録 gate (harmonic-head §7):

- **arm H (担体化 head)**: F0 シフト追従 **≥0.95** / comb-HNR **≥10dB@400batch**
  (構造保証なら学習初期から出る) / **ns 掃引不変性 ≤2dB** (A3 根治の決定的
  テスト — v10b は ns 用量反応 4.8→12.3dB があった) / 枝比 ρ 監視 /
  alias regression / VRAM・速度
- **arm C (条件付け改修)**: 可逆性 / grad-probe / 変調テレメトリ / seen-ID 疎通
- CPU p50 +10% gate は pin ベンチ機の e2e ONNX で判定 (M=24〜32 trim 順序は
  harmonic-head §7 #5 に事前登録済み)

### Phase C: 本走 80ep (instance、~$180-250) + 判定

- データ: v9/v10b と同一 (300,443 utts、単一変数原則の継続)。Emilia は
  「v11 でも 0.70 未達なら話者空間の広がり不足」と確定してから (C-0 済み)
- 事前登録 gate (v10b §4.3 の系譜 + 新規):
  - **A3**: 推論 ns=0.667 で comb-HNR ≥10dB (GT 13.2) + 聴感「がびがび」解消
  - A1 非退行: コム <1.5dB 維持 / A2': 10-11kHz Δ ≤+3dB + 棚 ≤+2dB
  - 類似: zs_ja 0.662 / つくよみ 0.740 (v10b から据置) + seen top-1 43%→
    (診断参考値、gate ではない)
  - 韻律: F0 std ≥45Hz (担体化で F0 経路が生きるため v10b より有利のはず)
  - 契約: ONNX [1,192] 不変 / FP16 ≤40MB / CPU p50 +10% 以内

## 2. 予算・工程見込み【推測】

| フェーズ | 期間 | 費用 |
|---|---|---|
| Phase 0 診断 | 2-3 日 | $0 |
| Phase A 実装 | 2-3 週 | $0 |
| Phase B smoke | 1-2 日 | ~$30-60 |
| Phase C 本走 + 評価 | ~3 日 | ~$180-250 |
| **計** | **~4-5 週** | **~$210-310** |

## 3. 事前登録の失敗分岐 (goalpost moving 防止)

- **arm H が ns 掃引不変性を満たさない** → 担体化の実装バグか設計欠陥。
  本走に進まず設計に戻る (A3 未解決のまま本走しない)
- **Phase C で類似 gate 未達だが A3/A2' 達成** → 品質面は v11 を採用し、
  類似は (i) Emilia 投入 (話者空間の広がり)、(ii) v12 契約改定枠
  (参照系列入力、conditioning §5 の隔離枠) の 2 択を再評価
- **seen top-1 が ep20 で +10pt 未満** → 条件付け改修の不発シグナル
  (conditioning §6)。P アームの構成を Phase 0 診断に照らして見直し

## 4. 積み残し (v11 スコープ外)

- Emilia-YODAS ja/ko 投入 (ライセンス確定済み、v10b plan §7) — v11 結果待ち
- 参照系列入力 (契約改定必須、SIM +0.08-0.11【文献】) — v12 枠
- gol-game (同ドメイン話者スケール) — oracle 診断により優先度低のまま
- FT ladder (embedding 最適化 / LoRA) — 「確実に似せる」用途の正道、別トラック

## 5. 最終結論 (2026-08-25 確定)

**v11 本走は R3 安全装置 (held-out ECAPA 急落検知) により ep29/80 で正規停止。
調波構造の技術検証は成功、実用モデルとしては学習量不足で不成立。**

### 実測サマリ

| 指標 | ep9 | ep19 | ep25 | ep29 | gate |
|---|---|---|---|---|---|
| comb-HNR (A3) | **14.6** | 12.9 | 7.8 | 3.8 | ≥10 (GT 13.2、v10b 4.6) |
| つくよみ CAM++/ECAPA | 0.672/**0.458** | **0.697**/0.389 | 0.607/0.148 | 0.605/0.231 | 0.740 |
| zs_ja CAM++ | 0.484 | 0.498 | 0.561 | 0.531 | 0.662 |
| seen-ID raw/cent | 8/30% | 30/33% | 22/40% | 17/35% | 追跡 |

- **成功**: carrier head (A′) は合成音の調波性を GT 超え (14.6 vs 13.2dB、
  v10b 比 +10dB) に到達 — A3 (がびがび残存成分) の構造保証は実証
- **崩壊**: ep19→25 で ECAPA 急落 (0.389→0.148) + comb-HNR 崩壊 (12.9→7.8)。
  CAM++ は高いままの dual-encoder 乖離 = 敵対 ramp / SCL 圧による
  「encoder を騙す」逸脱の 6 例目。R3 が 2 度発動し正しく停止
  (1 度目を外因死と誤診して blind resume した — remote-train-ops skill §7 参照)
- **聴感 (2026-08-24/25 ローカル torch 合成、ユーザー確認)**: ep9/ep19 は
  日本語として聞き取れない (12k-27k step は VITS の明瞭発話獲得 ~100k step の
  はるか手前)。同一経路で v10b ep79 は「明瞭だが がびがび残存」— つまり
  明瞭さ (学習量) × ノイズ根治 (carrier head) の両立は v11 系の完走が必要

### 露呈した盲点・バグ (v11b 前に対処)

1. **評価系に明瞭度指標が無い**: SECS / comb-HNR / seen-ID はどれも
  「読めているか」を測らない → v11b は **ASR ベース CER を gate に追加**
2. **ONNX export が v11 carrier head を壊す (2 問題) — 2026-08-25 修理完了**:
   (a) EMA 自動適用が有害 (早期打ち切り ckpt では EMA が劣化重み、torch A/B:
   raw 14.9dB vs EMA 6.2dB) → `--no-ema` フラグ追加 (commit 67adc5f7)。
   (b) trace 後の ONNX の調波崩壊 — 真因は **main() 内の infer 手書き複製が
   v11 P2 の `enc_p(g_spk)` (AdaLN) に追従せず、ONNX だけ話者条件が断線**
   していたこと (carrier 単体は legacy trace でも parity 完全一致 = 無罪を
   probe で確定)。複製を `build_infer_forward` (models.infer の wrapper) に
   一本化し、位置束縛 parity テスト + 複製再導入禁止の構造テストで pin
   (commit 84e5fe4e)。**修理後の FP16+no-EMA export で 14.38dB を実測回復**
   — v11 系の ONNX 配布は可能になった (早期打ち切り ckpt は --no-ema 必須)
3. 敵対 ramp スケジュール: ep15 の谷 → ep19 回復 → ep19 以降崩壊の経過から、
  ramp 進行が崩壊の駆動因の第一容疑。v11b では ramp 凍結/減速 + R3 継続

### 成果物の所在

- ckpt (ep1-29 奇数 + last): HF `checkpoints-v11/` / 評価 JSON: `v11-results/`
- 学習ログ + TensorBoard events (崩壊解析用): ローカル
  `piper-v11-local/box-evac/box-final-evac.tar.gz` (rotated ep0-25 train log 含む)
- 聴感 wav: `piper-v11-local/listen_torch/` (torch 直合成のみ有効 —
  `listen_onnx_BROKEN/` は export バグの証拠品)
- instance 48459366 は 2026-08-24 14:49 UTC destroy 済み (残高 $76.80)

### v11b への引き継ぎ (次の一手)

1. export 修理 (--no-ema flag + carrier trace バグ、TDD) — v11b 完走前まで
2. v11b 設計判断: ep19 warm 継続 (60ep ≈ ~$73) vs from-scratch (~$108+)。
  warm は ep19 が健全である前提 (聴感未成熟だが指標上は崩壊前)。
  残高 $76.80 では warm がぎりぎり、from-scratch は来月
3. gate 追加: CER (明瞭度) + R3 継続 + ramp 凍結条件の事前登録
