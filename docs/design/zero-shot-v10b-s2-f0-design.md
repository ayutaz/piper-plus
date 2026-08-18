# v10b S-2 設計スパイク — MB-iSTFT decoder への F0 明示経路 (2026-08-18)

> **Status**: 設計スパイク完了 (プロトタイプ検証まで。本実装は未着手)。
> [`zero-shot-v10b-quality-plan.md`](zero-shot-v10b-quality-plan.md) §3.2 S-2 が
> 要求した「注入機構の設計スパイク (2-3 日)」の成果物。plan は候補 3 案
> (a) frame 格子 concat / (b) subband 励振加算 / (c) iSTFT head への harmonic
> 位相特徴 を挙げ、**確定前の本走組込は不可**としていた。本書で **(c) を選定**する。
>
> **表記**: plan と同じく【実測】(本プロジェクトの測定)【文献】(一次文献の報告値)
> 【算術】(構成から導ける計算)【推測】(未検証の見込み) でラベルする。
>
> 関連: [`zero-shot-v10b-quality-plan.md`](zero-shot-v10b-quality-plan.md) §1.2 B1 /
> §3.2 S-2 / §4.3 判定基準 ・ [`docs/spec/zs-eval-contract.md`](../spec/zs-eval-contract.md)
> §2 禁止事項 4 (S-2 例外の境界定義) ・
> [`zero-shot-noise-root-cause-pqmf.md`](zero-shot-noise-root-cause-pqmf.md)

---

## TL;DR

- **選定は (c)**。ただし plan が想定した「sample-rate 励振を作って注入する」形では
  なく、**head 格子 (SR/16 = 1378.125Hz) で harmonic 位相テンプレート
  `[cos(2πmΦ), sin(2πmΦ)]` を直接与える形**に具体化する。根拠は構造 1 点に尽きる:
  **我々のデコーダで「周期性」が存在するのは head が出す per-frame 位相の frame 間
  整合だけ**であり、位相参照が意味を持つ格子は head 格子しかない【実測 (コード)】。
  (a) が注入する 86Hz 格子にはまだ位相が存在せず、(b) が加算する iSTFT 出力後には
  head がもう整形できない
- **情報充足性を実測で確認**: 合成有声信号の subband 複素スペクトルのうち、
  band0 (0-2.8kHz — A3 の「調波間ノイズ充填 1-3kHz」を含む帯域) の **82.5%
  (M=4) 〜 83.9% (M=8) が template の線形結合で張れる**【実測】。band1 以上は
  0.02-0.16 と低いが、そこは GT 自体がほぼノイズ性 (plan §1.1 A3) なので設計上の
  問題にならない
- **コストは gate 境界**。プロトタイプ実測 (ORT CPU、predictor 込み・単一 graph)
  で **decoder 単体 p50 +4〜13% / trim 構成で +2〜10%**【実測】。plan §4.3 の
  「+10% 以内」に対して余裕がないため、**trim 順序を事前登録**し Phase B 実装で
  ベンチ併走する。ONNX 入力契約 [1,192] は不変、FP16 増分は **+0.48MB** で
  40MB gate に影響なし【実測】
- **却下**: (b) の「iSTFT 出力への per-band 加算」は、励振が head の整形を一切
  受けずに出力へ素通りし decoder 自前の倍音と干渉するため棄却。(b) を NSF 忠実に
  「励振を*入力として*与える」形に直すと STFT head では (c) と数学的に同値になり、
  その解析版 (fullband 励振 → PQMF 解析 → subband STFT) は実測 **+18〜30%** で
  コスト gate を単独で割る【実測】
- **設計上の最大リスクは「decoder が F0 を無視する」**こと (z が既に音高を含む
  ため teacher forcing 下で F0 チャネルを使う勾配圧力が弱い)。Phase D に
  **F0 シフト追従テスト**(±2 semitone シフト → 出力実測 F0 の追従率) を単変量
  go/no-go として置く
- **契約適合**: pitch predictor の GT F0 回帰は zs-eval-contract §2 禁止事項 4 の
  **明示された例外**。ただし例外は「予測器出力 vs GT F0」に限られ、**生成音声の
  F0 統計を目的化する loss は依然禁止**。境界を §5.4 で明文化した

---

## 1. 前提 — 我々のデコーダで「位相」はどこに住んでいるか

Period VITS をそのまま移植できない理由は plan §3.2 が指摘済み (サンプルレートで
動く conv 段がない) だが、**では位相はどこにあるのか**を確定させないと注入点は
決まらない。コードから確定した格子は以下【実測 (`mb_istft.py` / `stft_onnx.py` /
`lightning.py` の hparams)】。

| 段 | サンプル/フレーム率 | 内容 |
|---|---|---|
| decoder 入力 `z_slice` | **SR/256 = 86.133 Hz** | `[B, 192, T]` |
| `conv_pre` → FiLM | 同上 | 256ch |
| `ups[0]` (×4) → ResBlocks | **SR/64 = 344.531 Hz** | 128ch ← plan §1.1 A1 の最強コム系列と一致 |
| `ups[1]` (×4) → ResBlocks | **SR/16 = 1378.125 Hz** | 64ch = **head 格子** |
| `subband_conv_post` | 同上 | `4 × (16+2) = 72ch` → mag/phase |
| `OnnxISTFT` (n_fft=16, hop=4) | **SR/4 = 5512.5 Hz** | subband 波形 |
| `PQMF.synthesis` (×4) | **SR = 22050 Hz** | fullband |

ここから 2 つの事実が出る。

1. **head の周波数分解能は F0 を分解できない**【算術】。subband の iSTFT は
   n_fft=16 / SR_sub=5512.5Hz なので **bin 幅 344.53Hz**、9 bin で 0-2756.25Hz を
   覆う。F0 ≈ 260-380Hz の倍音間隔は 1 bin 前後 — つまり**倍音の微細構造は bin では
   表現されていない**。
2. **周期性は frame 間の位相前進としてのみ表現される**【算術】。frame 間隔は
   1/1378.125 s = 0.7256ms。F0 = 300Hz の成分は 1 frame あたり
   2π·300/1378.125 = 1.368 rad 前進する。head はこの位相前進を**自力で積分**して
   出さなければならない — 現行アーキテクチャで音高が z 由来の暗黙情報に依存し、
   B1 (F0 std が GT の 55-65%) と A3 (1-3kHz の comb-HNR −2.5〜−3.0dB) が同居
   している構造的理由がここにある【推測 (機序の解釈)】。

> **設計上の帰結**: F0 を「conditioning 情報」として与えるだけでは head の位相
> 積分は楽にならない。**位相参照そのもの**を head 格子で与えることが、この構造で
> 唯一意味のある「励振注入」の形である。

---

## 2. 候補 3 案の設計と比較

### 2.1 (a) frame 格子への F0/harmonic 特徴 concat

```
f0 [B,1,T]  ──> [log f0 / V-UV] ──> Conv1d(2→d,1) ──┐
                                                     ├─> concat ─> conv_pre(192+d → 256)
z_slice [B,192,T] ───────────────────────────────────┘
                                          (格子 86.133 Hz)
```

| 観点 | 評価 |
|---|---|
| ONNX | `Log` / `Greater` / `Clip` / `Concat` / `Conv` のみ。opset 15 で完結【実測】 |
| 追加 MACs | `conv_pre` 入力 +8ch = 8·256·7 = **14,336 MACs/frame = +0.24%** (decoder 全体 5.92 MMACs/frame 比)【算術】 |
| 学習安定性 | ほぼゼロリスク。zero-init 相当の挙動から始められる |
| 先行例 | FastPitch (arXiv:2006.06873) / FastSpeech 2 の pitch conditioning【文献】 |
| **弱点** | **位相参照にならない**。86Hz 格子には周期性の表現が存在しない。teacher forcing 下では GT F0 は z と冗長なので、decoder が F0 チャネルを使う勾配圧力が構造的に弱い【推測】 |

**判定: 単独では不十分。ただし限りなく安価なので (c) と同梱する**
(F0 の「値」情報 — 話者の音域・帯域包絡の F0 依存 — は 86Hz 格子で十分)。

### 2.2 (b) subband レート (SR/4) での per-band 励振加算

plan の記述どおり「sine source を PQMF 解析して 4-band に分解し、**iSTFT 出力に
加算**」する形:

```
f0 ─> sine源 e[n] (SR) ─> PQMF.analysis ─> e_sub [B,4,T·64]
                                                   │
head ─> iSTFT ─> sub_wav [B,4,T·64] ──────────────(+)──> PQMF.synthesis ─> y
```

| 観点 | 評価 |
|---|---|
| ONNX | `CumSum`/`Sin`/`Conv` で表現可【実測】 |
| 追加 MACs | PQMF 解析 256·4·63 = 64,512 MACs/frame (+1.1%) + SR での sin 生成【算術】 |
| **致命的欠点** | **PQMF は線形なので `synthesis(sub + analysis(e)) ≈ synthesis(sub) + e`** (往復 SNR 64dB【実測、既存 `test_decoder_synthesis_chain.py`】)。つまり「出力に生の励振を足す」のと等価で、head の学習された整形を一切受けない。decoder が自前で作る倍音と位相の合わない励振が重畳するため、decoder は「自分の倍音を出さない」方向に追い込まれるか、干渉を残すかの二択になる【推測】 |
| 先行例 | なし。NSF (arXiv:1904.12088) / Period VITS は励振を**加算ではなく neural filter の入力**として与える【文献】 |

**判定: この形では棄却。** ただし steelman — 「NSF 忠実に励振を*入力として*渡す」
— を STFT head に適用すると、head の入力空間は per-band 複素スペクトルなので
**励振の subband STFT を head 入力に concat する = (c) と同値**になる。その解析版を
`c_full` としてプロトタイプ実装し、実測 **+18〜30%** でコスト gate 単独超過を確認した
(§3.3)。したがって (b) は原理ではなく**コストで落ちる**。

### 2.3 (c) iSTFT head 入力への harmonic 位相特徴付与 ← **選定**

```
f0 [B,1,T] ─(linear ×16)─> f0 [B,1,T·16]   (head 格子 1378.125 Hz)
   │
   ├─> Φ[t] = cumsum(f0 / 1378.125)   (float64、cycles 単位)
   ├─> frac = Φ − floor(Φ)            (倍音を掛ける前に取る = 位相精度保護)
   ├─> c1 = cos(2π·frac), s1 = sin(2π·frac)         ← 超越関数はここ 2 個だけ
   └─> Chebyshev 漸化式で m = 2..M を展開 (Mul/Sub のみ):
          cos(mθ) = 2cos(θ)·cos((m−1)θ) − cos((m−2)θ)
          sin(mθ) = 2cos(θ)·sin((m−1)θ) − sin((m−2)θ)

   template = [cos(mΦ), sin(mΦ)]_{m=1..M} ⊕ log f0 ⊕ V/UV   →  (2M+2) ch
                    │ × V/UV gate
                    v
              Conv1d(2M+2 → 8, 1)          (zero-init)
                    │
   decoder 64ch ──concat──> subband_conv_post(72 → 72, k=7) ─> mag/phase ─> iSTFT ─> PQMF
```

| 観点 | 評価 |
|---|---|
| ONNX | 新規に必要な op は `CumSum` / `Floor` / `Sub` / `Log` / `Clip` / `Greater` のみ。全て opset ≤15 標準【実測、§3.2】 |
| 追加 MACs | `subband_conv_post` 入力 +8ch = 8·72·7·16 = **64,512 MACs/frame (+1.1%)** + `head_proj` 18→8 = 2,304 (+0.04%) + (a) の 14,336 (+0.24%)。**超越関数は head 格子で 2 個/サンプルのみ** (Chebyshev 化の効果: M=8 で 16→2)【算術】 |
| 学習安定性 | `head_proj` を zero-init すれば学習開始時は v10a と bit 互換の挙動 (既存 FiLM zero-init と同じ流儀)。zero-init でも入力側重みの勾配は非ゼロなので学習は進む |
| 先行例 | NSF (arXiv:1904.12088) / Period VITS (arXiv:2210.15964) の「明示的な位相源を与える」思想【文献】。**STFT head へ位相テンプレートを与える形の直接の先行例は見つけていない** — PQMF 4-band への注入と同じく独自設計【事実】 |
| **強み** | §1 の帰結どおり、位相が実際に消費される唯一の格子に参照を置く。情報充足性を実測で検証済 (§3.1) |

**M (倍音数) の選択**: §3.1 の実測で band0 の説明率は M=4 で 0.825、M=8 で 0.837、
M=16 以上で 0.838-0.839 と飽和する。Chebyshev 化により M のコストはほぼ線形かつ
微小なので **default M=8** (A3 の 1-3kHz を余裕を持って覆う)、trim 時に M=4。

### 2.4 比較サマリ

| | (a) frame concat | (b) 出力加算 | (b') NSF 忠実 = c_full | **(c) 位相テンプレート** |
|---|---|---|---|---|
| 注入格子 | 86.1 Hz | SR/4 (head 後) | head 格子 (解析経由) | **head 格子 1378 Hz** |
| 位相参照になるか | ✗ | — (整形不可) | ○ | **○** |
| 追加 MACs【算術】 | +0.24% | +1.1% + SR sin | +5〜7% + SR sin | **+1.4%** |
| ORT CPU 実測 (decoder 単体)【実測】 | +1〜6% | 未測定 | **+18〜30%** | **+2〜10%** |
| ONNX 標準 op のみ | ○ | ○ | ○ | ○ |
| 主リスク | 無視される | 干渉 | コスト gate | 無視される (§6) |

---

## 3. プロトタイプ検証 (実測)

スクリプト: `<scratchpad>/s2_spike/{proto.py, proto2.py, proto3.py, bench.py … bench9.py}`
(使い捨て。既存コードは未変更)。環境: Windows / torch 2.11.0+cu128 / onnxruntime 1.26.0 /
onnx 1.21.0、CPU EP。medium quality 相当の decoder (inter=192, upsample_initial=256,
resblock="2", `upsample_mode="resize"` = H-1 適用後) を baseline とした。

### 3.1 位相テンプレートの情報充足性 — 一番重要な検証

「head が位相を自力で積分せずに済むか」を、**合成有声信号の subband 複素スペクトル
`X[t,b]` を template の線形結合でどこまで張れるか (R²)** で測った。理屈上
`X[t,b] = Σ_h A_h(b)·exp(j·2π·h·Φ(t))` は template の**厳密な線形結合**なので、
R² が高いほど「head は位相を積分せず、テンプレートの線形結合として出せる」。
信号は F0 260-330Hz スイープ + 42 倍音 + 簡易フォルマント包絡、~7 秒。

| M | ch 数 | band0 0-2.8kHz | band1 2.8-5.5kHz | band2 5.5-8.3kHz | band3 8.3-11kHz |
|---|---|---|---|---|---|
| 4 | 10 | **0.825** | 0.001 | 0.001 | 0.000 |
| 8 | 18 | **0.837** | 0.019 | 0.001 | 0.001 |
| 16 | 34 | 0.838 | 0.146 | 0.004 | 0.004 |
| 32 | 66 | 0.839 | 0.159 | 0.074 | 0.040 |
| 42 | 86 | 0.839 | 0.161 | 0.086 | 0.081 |

【実測、`bench5.py`】読み方:

- **band0 で 0.83 前後に飽和**。残り ~16% は係数 `A_h(b)` が F0 変化に伴って
  変わる (倍音が bin をまたぐ) ぶんで、**線形到達性の下限**を測っているに過ぎない
  — head は conv なので非線形結合も作れる。つまり 0.83 は下界【算術】
- **band1 以上は M を増やしても伸びない**。理由も判明している: 高次倍音は F0 が
  ±70Hz 動くと bin を数個またぐので `A_h(b)` が急変し、「係数一定の線形結合」という
  前提自体が崩れる【実測 + 算術】。ただし plan §1.1 A3 が「5.5-9kHz は GT 自体が
  ほぼノイズ性 (HNR 0.5-1.0dB)」と実測しているとおり、**高域に調波位相参照は必要
  ない** — 高域の問題は「レベル超過 + コム」であり、そちらは H-1/H-2b/H-3 の担当
- 従って **(c) は A3 (1-3kHz の調波間ノイズ充填) に狙いを絞った施策**として位置づけ、
  高域への効果は主張しない

**Chebyshev 漸化式の fp32 精度**【実測】: M=4 で 7.6e-07、M=8 で 2.9e-06、
M=16 で 1.1e-05、M=32 で 3.5e-05、M=48 で 8.3e-05。M ≤ 16 なら直接評価と実用上同一。

### 3.2 ONNX export

- `torch.onnx.export`(opset 15, `dynamic_axes` あり) が **全バリアントで成功**、
  `onnx.checker` も pass【実測】
- baseline に対して**新規に必要な op**: `CumSum` / `Floor` / `Sub` / `Log` /
  `Clip` / `Greater`。(c_full のみ追加で `ReduceSum`)。全て ONNX 標準・opset 15
  以下・全 EP でサポート【実測】
- 励振の**noise 成分を落とした決定論設計**にしたため `RandomNormalLike` は不要
  (既存 `onnx_export_mode` が z のサンプリングを平均で置換する方針と整合)【設計判断】
- **ONNX 入力契約は不変**: F0 は内部予測なので graph 入力は
  `speaker_embedding [1,192]` のまま。7 ランタイム無改修【事実 (構造上)】

**FP16**: `piper_train.tools.convert_fp16` は **initializer だけを fp16 化し、
各消費ノードの手前に Cast(fp16→fp32) を挿入する実装**で、計算グラフは fp32 のまま
【実測 (コード読解 + 変換実行)】。したがって**位相 cumsum が fp16 に落ちる精度
ハザードは存在しない**。変換後サイズは 6.57 → 3.31MB (decoder 部分のみ)、
パラメータ増分は **+239,130 = +0.48MB @fp16**【実測】 — plan §4.3 の ≤40MB gate に
対して無視できる。

### 3.3 レイテンシ (ORT CPU)

測定機がノイズ源を抱えていたため、**全バリアントを 1 run ずつラウンドロビンで
回すインターリーブ測定** (150-200 ラウンド) に切り替え、p50 と min の両方を出した。
**p50/min の 2 系列が同符号で一致する範囲のみを信用する**。

**(A) 注入方式の比較** (F0 predictor 込み・別 graph、intra=1、60 ラウンド)【実測、`bench3.py`】

| 長さ | baseline | (a) | (c) 直接 sin M=8 | (c) Chebyshev M=8 | (b') c_full |
|---|---|---|---|---|---|
| 1.0s | 20.85 ms | +3.9% | +7.7% | +8.7% | **+29.7%** |
| 2.0s | 38.36 ms | +6.1% | +8.8% | +7.1% | **+23.6%** |
| 5.0s | 94.31 ms | +1.1% | +3.1% | +2.8% | **+18.0%** |
| 10.0s | 198.30 ms | +2.0% | +11.7% | +7.5% | **+26.6%** |

→ **c_full (fullband 励振 + PQMF 解析 + subband STFT) は単独で gate を割る**。
内訳 (torch, 5s): 励振生成 5.0ms / PQMF 解析 +5.8ms / STFT+proj +1.3ms。
サンプルレートで 6 倍音 × 110k サンプルの `Sin` と 63-tap 4ch conv を回すのが効く。

**(B) 推奨構成の最終測定** (predictor を **同一 graph** に統合、150-200 ラウンド)
【実測、`bench8.py` / `bench9.py`】

| | intra=1 Δp50 / Δmin | intra=4 Δp50 / Δmin |
|---|---|---|
| s2 (M=8, hidden=96, f0_ch=8, head_ch=8) | +3.8〜+9.4% / +5.0〜+9.8% | +5.6〜+13.3% / +8.4〜+18.7% |
| **s2_trim (M=8, hidden=64, f0_ch=4, head_ch=4)** | **+2.1〜+6.3% / +1.7〜+4.6%** | +2.5〜+10.6% / +4.9〜+9.7% |

**評価**: 標準構成は decoder 単体で **gate 境界 (+10%) に張り付く**。trim 構成なら
1 スレッドで +2〜6% と余裕が出る。注意点 2 つ:

1. これは **decoder 単体**の比。plan §4.3 は e2e も測るが、e2e は enc_p (6 層
   Transformer) + flow + DP を含むので**相対増分は必ず小さくなる**【算術】
2. 測定機のノイズが大きく (IQR が差分の数倍)、**この数値で gate 判定してはいけない**。
   Phase A で pin するベンチ機での再測定が必要

### 3.4 位相累積の精度 — 発見と対策

fp32 で位相を累積すると **torch と ORT で cumsum の加算順序が異なり、出力が長さと
ともに乖離**する【実測、`bench6.py`】:

| T (frames) | 43 | 172 | 431 | 1000 | 2000 |
|---|---|---|---|---|---|
| fp32 位相: torch vs ONNX 相対誤差 | 5.7e-04 | 4.1e-03 | 1.6e-02 | 7.0e-02 | **1.7e-01** |
| **float64 位相**: 同上 | 6.0e-06 | 1.1e-05 | 1.7e-05 | 3.0e-05 | **2.5e-05** |

位相そのものの誤差は 10 秒で ~1.5e-03 rad = 可聴閾以下【算術】なので音質問題では
ないが、**波形 allclose の ONNX parity テストが長尺で書けなくなる**。
**位相累積のみ float64 にすると誤差が長さに依存せず 3e-05 に収まり、レイテンシ
コストは測定誤差以下 (−0.7〜0.0%)**【実測、`bench7.py`】。→ **採用**。

---

## 4. F0 predictor 側の設計

### 4.1 置き場所

**MAS 展開後の frame 格子**に置く (Period VITS の frame prior network 相当)【文献】。

```
enc_p ─> x [B,192,T_phone]      m_p, logs_p
            │                       │
         (attn 展開)  ←── MAS ──────┘         学習時: attn は MAS
            v                                 推論時: attn は generate_path(w_ceil)
       x_frame [B,192,T_frames]
            │
            ├──> F0Predictor ──> log f0 [B,1,T] , V/UV logit [B,1,T]
            │       ^
            │       └── g_f0 = spk_proj_f0(g.detach()) + g.detach()   (話者条件)
            v
      (§4.4 の prior 残差 / decoder 注入へ)
```

- **入力を `x_frame` (展開済み enc_p hidden) にする理由**: (i) 学習・推論で同一の
  情報源 (z は推論時に prior 由来なので学習時 posterior z を使うと leak になる)、
  (ii) prosody_features (A1/A2/A3、日本語アクセント) が enc_p を経由して既に
  入っている — JA の音高アクセントを予測する材料が揃っている【実測 (コード)】
- **`x` の展開が必要**: 現行 `forward` は `m_p` / `logs_p` しか展開していない
  (`models.py:1490-1491`)。`x` にも同じ `attn` を掛ける matmul を 1 本足す
  (学習時のみ、+1 matmul【算術】)。推論側は `generate_path` の `attn` を流用
- **構造**: `Conv1d(192→h, k=5) → GroupNorm → ReLU` ×2 → `Conv1d(h→1)` ×2 heads。
  h=96 で 187.6 kMACs/frame (decoder 比 +3.2%)、h=64 で 114.7 kMACs/frame (+1.9%)
  【算術】。**予測器が S-2 の CPU コストの最大項**なので trim 対象の筆頭

### 4.2 話者条件

**default は `g.detach()` + 専用残差ヘッド `spk_proj_f0`** とする。v10 M3 の
`spk_proj_dp` と同じ流儀 (`models.py:1231-1248` — duration 勾配を `spk_proj` 本体
から隔離するために新設された軽量ヘッド) を踏襲する。

ただしここには**意図的なトレードオフ**がある【推測】:

- 話者の音域 (F0 の中心と幅) は話者性そのものなので、F0 loss の勾配を `spk_proj`
  本体に通すことは**類似度に効く可能性がある**
- 一方 v10a の教訓は「spk_proj への余計な勾配圧力は prior 経路を壊しうる」

→ **`--f0-spk-grad` フラグで `spk_proj` 本体への勾配を opt-in 可能にし、Phase D の
optional arm で A/B する**。default は保護側 (detach + 専用ヘッド)。

FiLM か加算かは、既存 decoder の FiLM (`_apply_film`: `sigmoid(scale)+0.5` で
[0.5,1.5] にクランプ) と同型にすると挙動が読みやすい。予測器は小さいので
**1×1 conv の加算条件付け**で十分【推測】(Daft-Exprt arXiv:2108.02271 の FiLM 注入は
先行例だが、本件は 2 層の小規模予測器なので差は小さいと見る)。

### 4.3 Loss

```
L_f0  = λ_f0 · L1( log f0_pred , log f0_gt )   over voiced frames
L_vuv = λ_vuv · BCE( vuv_logit , vuv_gt )
```

- **log 領域**の L1 (話者間の音域差を乗法的に扱う。semitone 換算で解釈可能)
- voiced フレームのみで正規化 (無声フレームの f0 は未定義)
- **予測器出力は decoder 注入へ渡す時に detach する** (FastPitch / FastSpeech 2 の
  標準)。mel/GAN 勾配が予測器を汚さないようにし、予測器は純粋に GT 回帰で学習する
- **λ の較正**は v10a の grad-probe 手順を流用 (speaker 系 = mel の 5-15% に合わせた
  実績手順)。初期値は【推測】で置き、Phase D smoke で確定

**明示的に禁止する形** (§5.4 と重複するが loss 設計の一部として先に書く):

- ✗ F0 の std / p5-95 レンジ等**分布モーメントを目的化する項** — plan §4.3 の
  登録 gate そのものであり、追加した瞬間に gate が検出器として死ぬ
- ✗ **生成波形から F0 を推定して GT F0 と比べる項** — 契約 §2 の例外は
  「予測器出力 vs GT F0」に限られる。生成音声の分析は評価器の目的関数化に当たる
- △ Δlog F0 (1 階差分) の L1 は per-frame の GT 回帰なので契約上は可だが、
  「dynamics を直接押す」意図に近く gate 隣接。**default off、必要なら Phase D の
  optional arm** とする

### 4.4 注入 (teacher forcing / 推論時の切替)

2 系統に分けて、それぞれ別の規則にする。

| 経路 | 学習時 | 推論時 | 理由 |
|---|---|---|---|
| **decoder 注入** ((a)+(c)) | **GT F0** (teacher forcing) → epoch K 以降 **予測 F0 (detach) へ確率 p でアニール** | 予測 F0 | クリーンな位相参照で head を学習させたい。ただし GT F0 は目標波形由来の leak なので、アニールで train/infer の齟齬と依存を同時に減らす |
| **prior 残差** (§4.5) | **常に予測 F0 (detach)** | 予測 F0 | prior は学習・推論で同じ入力を見るべき。GT を入れると KL が「GT 音高を知っている prior」で下がり推論時に崩れる |

- アニール: `p_pred = clamp((epoch − K) / R, 0, p_max)`、default `K=10, R=10,
  p_max=0.5`【推測、Phase D で較正】
- **位相の初期オフセット**: 学習は `segment_size//hop = 32` フレームのスライスで
  行う (`models.py:1504`)。cumsum をスライス先頭から始めると「frame 0 の位相は常に
  0」を模型が学習しうるので、**学習時のみ一様乱数の初期位相 `U(0,1)` を加える**。
  推論時は 0。これで模型は位相オフセット不変になる【設計判断】
- F0 も `ids_slice` で **z と同一区間にスライス**する必要がある (`slice_segments`
  を f0 に適用)

### 4.5 prior 側 F0 残差 (推奨、plan の 3 案の外)

**B1 (F0 std が GT の 55-65%) を実際に動かすのはこの経路**だと考える【推測】。
decoder 注入だけでは、推論時に z (prior+flow 由来) が持つ音高と、予測 F0 が示す
音高が**食い違う**。学習時は z が posterior 由来 = GT 音高なので齟齬が出ず、
モデルは「z を信じる」方針を学ぶ余地がある。

対策は FastPitch 型の最小介入:

```
m_p ← m_p + Conv1d(2 → 192, k=1)( [log f0_pred.detach(), vuv_pred.detach()] )
                    ↑ zero-init
```

- MAS 展開後の `m_p` に**零初期化の残差**を足すだけ (192·2 = 384 MACs/frame、
  実質ゼロ【算術】)
- KL loss が「F0 を使ったほうが z_p をよく説明できる」という勾配圧力を与える
  ため、**decoder 注入と違って使われる理由がある**【推測】
- zero-init なので導入直後は v10a と bit 互換。ramp は自然に起きる

**この項目は plan §3.2 の 3 案には無いため、採否は本書の提案として明示する**
(採用推奨、`--f0-prior-residual` で opt-in、Phase D の単変量 arm で有無を A/B)。

### 4.6 GT frame-level F0 の前処理 (Phase C)

現行 dataset/前処理に F0 は一切存在しない【実測、plan §3.2 が指摘済み】。

| 項目 | 設計 |
|---|---|
| 格子 | spectrogram と同一 (SR 22050 / hop 256)。フレーム数は spec と一致させる |
| 推定器 | **pyworld DIO + StoneMask を第一候補**【推測、要実測】。Harvest は精度は上だが ~0.3-0.5× RT で 300k utts では 33 h/32core 級、DIO は 5-20× RT で 1.5-3 h/32core 級 |
| **評価器との分離** | 評価側 (`acoustic_frames` / `measure_prosody`) は **librosa.pyin** を使っている【実測 (コード)】。**学習ターゲットには別実装 (pyworld) を使う**ことを推奨する — 同一推定器だと「pyin が高分散と読む音」を作る方向の gaming チャネルが (弱いが) 開く。推定器を分けておけば §4.3 の F0 gate は独立性を保つ【推測 (ハザード評価)、cheap hedge】 |
| 依存 | `pyworld` は現在未依存。WORLD 本体は modified BSD、pyworld ラッパは MIT の見込み【推測、**Phase C の C-0 ライセンス実確認に含めること**】。不可なら librosa.pyin にフォールバック (分離の利点は失う) |
| キャッシュ | `{cache_id}.f0.npy` (fp16, `[T_frames]`, 無声は 0.0)。`precomputed_mel` の規約 (`PiperDataset._precomputed_mel_path_for` / `_MEL_STRIP_SUFFIXES`) をそのまま踏襲し、writer/reader の 2 箇所同期という既存の注意書きも継承する【実測 (コード)】 |
| サイズ | 300k utts × ~430 frames × 2B ≈ **260MB**【算術】 |
| 品質ガード | オクターブエラー対策として (i) 話者ごとの F0 中央値から ±1 オクターブ外れの連続区間を検出してログ、(ii) 有声率 / F0 レンジのヒストグラムを前処理レポートに出す。**この統計はオフライン前処理のデータ品質検査であり、契約 §2 の「オフライン前処理のデータゲートは対象外」に該当する**【契約引用】 |
| 配線 | `Utterance` / `UtteranceTensors` / `Batch` に `f0` フィールド追加 + `pin_memory()` に 1 行 + collate のパディング。既存の `speaker_embedding` と同型で、後方互換 (欠落時 None → S-2 無効) |

---

## 5. 契約適合 (zs-eval-contract §2)

### 5.1 該当条項 (引用)

> **境界定義 (S-2 例外)**: GT 波形・GT frame-level F0 など「GT を教師とする
> 回帰 loss」(mel / STFT / MRD / S-2 の pitch predictor 回帰) は本禁止の対象外 —
> 禁止対象は「評価器 (frozen encoder / 本契約の統計量) を目的関数化する」ことで
> あり、GT 参照 loss は評価器を消費しない (v10b plan §2.2 の表を normative とする)。
> — [`docs/spec/zs-eval-contract.md`](../spec/zs-eval-contract.md) §2 禁止事項 4

### 5.2 適合するもの

- `L1(log f0_pred, log f0_gt)` / `BCE(vuv)` — GT frame-level F0 を教師とする
  per-frame 回帰。例外条項に**明示的に列挙されている形そのもの**
- 前処理での F0 品質統計・データゲート — 「オフライン前処理のデータゲートは対象外」

### 5.3 適合しないもの (S-2 実装で作ってはいけない)

1. 生成波形から F0 を推定して GT と比べる loss (推定器が微分可能かどうかに関わらず)
2. F0/エネルギーの **分布統計** (std / レンジ / skew / kurt) を目的化する項
3. `piper_train.tools.measure_prosody` / `acoustic_frames` を `piper_train/vits/**`
   または `__main__.py` から import すること — `scripts/check_zs_metric_isolation.py`
   (pre-commit `zs-metric-isolation-gate`) が **Rule A で機械的に block** する【実測
   (コード)】。S-2 の F0 抽出は `tools/extract_f0.py` (role: 対象外) に置き、学習側は
   **キャッシュ済み `.npy` を読むだけ**にする — これで gate に触れずに済む

### 5.4 実装時に足すべきガード

- `tools/extract_f0.py` の docstring に「本モジュールは**学習ターゲット生成**であり
  EVAL-ONLY メトリクスではない。評価の F0 は `measure_prosody` (librosa.pyin) が
  独立に測る」を明記し、両者の推定器が違うことを意図として固定する
- 新設 loss のテストに「F0 の std/レンジを参照する項が存在しない」ことを構造的に
  示すコメントを置く (レビュー時の checklist)

---

## 6. 確定判断

### 6.1 選定

**(c) harmonic 位相テンプレートの head 入力注入** を採用する。付随して:

| # | 項目 | 採否 | 備考 |
|---|---|---|---|
| S-2a | frame 格子 F0/V-UV concat (= 案 (a)) | **採用** (同梱) | +0.24% MACs。F0 の「値」情報担当 |
| S-2c | head 格子 harmonic 位相テンプレート (= 案 (c)) | **採用** | M=8 default、Chebyshev + float64 位相 |
| S-2p | frame prior F0/VUV predictor + GT 回帰 | **採用** | h=96 default (trim で 64) |
| S-2r | prior 側 F0 残差 (zero-init) | **採用推奨** (opt-in) | B1 を動かす主経路と見る【推測】 |
| — | 案 (b) iSTFT 出力への per-band 加算 | **不採用** | 線形性より出力への素通りと等価 |
| — | (b') fullband 励振 + PQMF 解析 (c_full) | **不採用** | +18〜30%、コスト gate 単独超過【実測】 |

### 6.2 根拠 (要約)

1. **構造的必然**: 我々の decoder で位相が消費される格子は head 格子のみ (§1)。
   他の 2 案はその格子に触らない
2. **情報充足性を実測**: band0 の複素スペクトルの 83% が線形到達可能 (§3.1)。
   しかも A3 の 1-3kHz を覆う
3. **コストが唯一 gate 内に収まる注入形**: c_full +18〜30% に対し (c) は +2〜10%
4. **契約の例外条項に正面から乗る**唯一の形 (GT 教師の per-frame 回帰、§5)
5. **退避経路がある**: `head_proj` zero-init なので、smoke 失敗時は
   「テンプレート経路を切って (a) だけ残す」縮退が bit レベルで安全

### 6.3 実装工数【推測】

| 作業 | 人日 |
|---|---|
| `tools/extract_f0.py` (DIO+StoneMask、品質統計、テスト) | 1.5 |
| dataset / collate / Batch の f0 配線 + 後方互換テスト | 1.0 |
| `F0Predictor` + loss + CLI + grad-probe 連携 + テスト | 1.5 |
| decoder 注入 (a)+(c) + `MBiSTFTGenerator` 分岐 + zero-init 互換テスト | 1.5 |
| ONNX (export / dynamic 長 parity / fp16 / 契約テスト) | 1.0 |
| prior 残差 (S-2r) + teacher forcing アニール | 1.0 |
| F0 シフト追従 ablation ツール (§6.4 の go/no-go 用) | 0.5 |
| **合計** | **~8 人日** (plan §3.2 の「実装 1-2 週」に収まる) |

前処理実行: 300k utts の F0 抽出 **1.5-3 h / 32 core** 見込【推測、要実測】。
Phase C に計上済 (plan §4.2)。

### 6.4 Phase D smoke の検証項目 (S-2 単独 arm)

plan §3.2 / §4.4 の「S-2 は Phase D の単独 arm smoke pass が本走組込の条件」を
具体化する。**(1) と (3) は go/no-go**、他は監視。

| # | 項目 | 判定 |
|---|---|---|
| **1** | **推論コスト**: decoder 単体 + e2e の CPU p50 を baseline ONNX と同一ベンチで測定 | **+10% 以内** (plan §4.3)。超過時は §6.6 の trim 順序を上から適用し、それでも超過なら **v10c 送り** |
| **2** | 予測器の学習: voiced F0 の L1 (log Hz) と V/UV accuracy の推移 | 単調改善。絶対閾値は smoke で較正【推測】 |
| **3** | **注入が無視されていないか (最重要)**: 学習済み smoke ckpt で **予測 F0 を ±2 semitone シフト**して合成し、出力の実測 F0 (measure_prosody、評価専用) がどれだけ追従するか | **追従率 ≥ 0.8**。~0 なら「decoder が F0 を無視」= 本案の失敗機序が発現 → v10c 送り。**学習を長く回さずに判定できる単変量テスト** |
| 4 | テンプレート経路が使われているか | `head_proj` の重みノルムが zero-init から単調成長 |
| 5 | 交絡していないか (単変量原則) | コム 2 指標 (`comb_excess_db` / `hf_autocorr`) が H-1/H-2b 単独 arm の達成値から**非悪化** |
| 6 | 安定性 | non-finite skip 率 ≤ 3%、KL の cap 貼り付きなし、G/D loss 発散なし |
| 7 | (optional arm) | `--f0-spk-grad` on/off、`--f0-prior-residual` on/off、M=4 vs 8 |

### 6.5 リスクと緩和

| # | リスク | 機序 | 緩和 |
|---|---|---|---|
| **R1** | **decoder が F0 を無視する** | teacher forcing 下では GT F0 が z と冗長 → F0 チャネルを使う勾配圧力が弱い【推測】 | (i) 位相テンプレートは z から作るのが難しい情報なので冗長性が低い (§1)、(ii) prior 残差 (S-2r) で z 自体を F0 依存にする、(iii) 予測 F0 へのアニール、(iv) **Phase D 検証 3 で直接検出** |
| **R2** | teacher forcing leak → train/infer 齟齬 | GT F0 は目標波形由来 | アニール + prior 側は常に予測 F0 |
| **R3** | 予測器の平滑化で F0 std が伸びない | L1 回帰は平均回帰し contour が鈍る (FastPitch でも既知)【文献 + 推測】 | gate は std ≥ 45Hz / p5-95 ≥ 150Hz (plan §4.3)。未達なら分布回帰系は **v10c**。Δlog F0 項は gate 隣接なので安易に足さない (§4.3) |
| **R4** | H 系 (H-1/H-2b) との干渉 | decoder 構造を同時に触る | plan §3.2 の順序 (H 系 → S-2 の単変量) を厳守。検証 5 でコム非悪化を確認 |
| **R5** | F0 抽出のオクターブエラー | 学習ターゲット汚染 | 前処理の品質統計 + 話者中央値からの外れ検出 (§4.6) |
| **R6** | 評価器との Goodhart 隣接 | 学習ターゲットと評価 F0 が同一推定器だと gaming チャネル | 推定器を分離 (pyworld vs librosa.pyin)。ライセンス不可なら**リスクを明記して受容** |
| **R7** | ONNX 長尺での再現性 | fp32 cumsum の順序依存【実測】 | **float64 位相累積** (コスト実測ゼロ)。parity テストは float64 前提で書く |

### 6.6 コスト gate 超過時の trim 順序 (事前登録)

plan §4.3 の「gate 超過時は該当レバーを不採用に戻す。事後緩和はしない」に従い、
**縮退の順序を先に決めておく** (測ってから基準をいじらないため):

1. `head_ch` 8 → 4 (`subband_conv_post` の追加入力を半減、−0.55% MACs)
2. predictor `hidden` 96 → 64 (−1.2% MACs)
3. `f0_ch` 8 → 4 (−0.12% MACs)
4. M 8 → 4 (情報充足性は 0.837 → 0.825 とほぼ不変【実測】)
5. ここまでで未達なら **S-2 を v10c 送り** (plan §3.2 の既定どおり)

---

## 7. 未解決事項 / deviation

- **plan からの逸脱 1**: 案 (c) を「sample-rate 励振を PQMF 解析して head へ」では
  なく「head 格子で位相テンプレートを解析的に生成」に具体化した。前者もプロトタイプ
  化して測り、**コストで落とした**上での選択 (§3.3)
- **plan からの逸脱 2**: 3 案に無い **prior 側 F0 残差 (S-2r)** を追加提案した。
  B1 を動かす主経路と考えるが、prior/flow/KL の配線に触るため opt-in + 単変量 A/B
- **未検証 (学習が要る)**: (i) 位相テンプレートを head が実際に使うか、(ii) F0
  予測器の std が gate (45Hz) に届くか、(iii) A3 の comb-HNR が改善するか。
  いずれも Phase D smoke の担当
- **未確認**: `pyworld` のライセンスと実 throughput (Phase C の C-0 に統合)
- **測定環境**: レイテンシは開発機 (Windows、ノイズ大) の実測。**gate 判定は
  Phase A で pin するベンチ機の再測定で行う**

---

## 8. 出典

- **本スパイクの実測**: `<scratchpad>/s2_spike/` の `proto.py` (c_full) /
  `proto2.py` (a, c-lite) / `proto3.py` (Chebyshev) と `bench.py`〜`bench9.py`。
  主要結果は §3.1 (`bench5.py` 情報充足性) / §3.2 (`bench6.py` fp16 + export) /
  §3.3 (`bench3.py`, `bench8.py`, `bench9.py` レイテンシ) / §3.4 (`bench7.py` 位相精度)
- **コード読解 (実測)**: `src/python/piper_train/vits/mb_istft.py` (格子・PQMF・
  H-1 resize) / `stft_onnx.py` (iSTFT 基底と framing) / `models.py`
  (`SynthesizerTrn.forward` の展開と slice、`spk_proj_dp` の M3 流儀) /
  `dataset.py` (キャッシュ規約) / `tools/convert_fp16.py` (initializer のみ fp16) /
  `scripts/check_zs_metric_isolation.py` (E-8 gate の scope)
- **文献**: Period VITS (arXiv:2210.15964) / NSF (arXiv:1904.12088) /
  FastPitch (arXiv:2006.06873) / Daft-Exprt (arXiv:2108.02271) /
  Pons ら upsampling artifacts (arXiv:2010.14356)
- **契約・計画**: [`zero-shot-v10b-quality-plan.md`](zero-shot-v10b-quality-plan.md)
  §1.2 B1 / §3.2 S-2 / §4.2 Phase C-D / §4.3 事前登録判定 ・
  [`docs/spec/zs-eval-contract.md`](../spec/zs-eval-contract.md) §2
