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
