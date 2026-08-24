# v11 設計スパイク — 担体化 harmonic-plus-noise head (A3 がびがび根治) (2026-08-20)

> **Status**: 実装・本走検証済み — v11 本走 (ep29 で R3 正規停止) で carrier head の
> 調波構造保証を実証 (comb-HNR 14.6dB = GT 超え)。技術検証成功、実用は学習量不足
> ([`zero-shot-v11-roadmap.md`](zero-shot-v11-roadmap.md) §5 が canonical)。
> Phase B smoke での盲点と修正は §11。
> [`zero-shot-v10b-residual-noise-diagnosis.md`](zero-shot-v10b-residual-noise-diagnosis.md)
> §5-1 が要求した「担体化 harmonic-plus-noise head」の具体設計と構造検証の成果物。
> S-2 (F0 明示経路) の設計スパイク
> [`zero-shot-v10b-s2-f0-design.md`](zero-shot-v10b-s2-f0-design.md) の直接の後継 —
> S-2 実装 (S-2a/S-2p/S-2r + F0 キャッシュ) はそのまま土台として使い、
> **S-2c (concat 注入) を担体化 head で置換**する。
>
> **表記**: 【実測】= 本スパイク/本プロジェクトの測定、【文献】= 一次文献の報告値、
> 【算術】= 構成から導ける計算、【推測】= 未検証の見込み。

---

## TL;DR

- **選定は案 A′: 解析重み付き 2-band 担体描画 + 拘束付き noise 枝**。
  倍音 m·F0 を「PQMF 解析フィルタの複素応答 conj(H_k(m·F0)) を固定重みとして
  band0/band1 の両 subband に描画する oscillator bank」で合成し、非調波成分は
  「粗い周波数格子 (bin 幅 344.5Hz) の振幅包絡 σ × frame ごと独立なランダム位相」
  の noise 枝だけが出せる、という構造に head を制限する
- **構造保証を実測で確認**: 敵対的 (i.i.d. ランダム) ゲインでも担体枝の
  comb-HNR@1-3kHz は **26-58dB** (F0≥120Hz、ゲイン平滑込みなら F0=90Hz でも
  **36.8dB**)。noise 枝は F0 同期 AM という最悪ケースの σ でも **0.19-0.54dB**
  しか出せない = **トーンを構造的に偽造できない**【実測 §5.1】
- **タスク指定の素朴な「band0 のみ担体化」は band 端 alias で不成立** — band0
  単独描画は 2.4kHz の倍音で既に鏡像 spur が親比 −9.7dB、2.7kHz で −1.4dB
  【実測 §5.2】。解析重み 2-band 描画に修正すると **−98〜−112dB** に消え、
  1-3kHz 全域 (A3 の全帯域) を担体で被覆できる【実測 §5.2】
- **F0 予測誤差に頑健**: ±20〜50 cent ずれても出力自身の F0 格子で測る
  comb-HNR は 18.5dB 不変 = **がびがびは戻らない** (誤差はピッチ精度の問題に
  転化する)。ただし GT 格子で測る comb-HNR は ±20 cent で 0.7dB に崩壊するため
  **Phase D の comb-HNR gate は必ず出力自身の F0 トラック (pyin) で測る**【実測 §5.3】
- **ONNX**: opset 15 標準 op のみ (新規は CumSum/Floor/Greater/ReduceSum/
  RandomNormalLike 等 — RandomNormalLike は既存 piper graph の z サンプリングに
  前例あり)。入力契約 [1,192] 不変。torch↔ORT parity は長さ非依存で ~2e-5
  (float64 位相)【実測 §5.4】
- **コストは実装形が支配する**: 素朴実装は **+61〜72%** で問題外、**MatMul 融合形
  で M=40 +18% / M=24 +13%** (decoder 単体 p50、開発機)【実測 §5.5】。
  担体の純増分 (vs v10b-S2) は M=24 で +4〜8%。e2e では相対増分が縮む【算術】ため
  M=24〜32 なら +10% gate 内が現実的見込み【推測 — Phase B の pin ベンチ機で判定】。
  パラメータ +292k (+0.59MB fp16、predictor 込み)【実測】。MACs 集計 (+0.6%) は
  コスト予測として無意味だった (per-op オーバーヘッド支配) — S-2 の教訓を更新
- **teacher forcing の「無視」は構造的に不可能**: v10b smoke の追従率 0.0 は
  concat 注入 (係数ゼロで F0 と無関係な出力が可能) だから起きた。担体化では
  voiced 帯域 (≤3kHz) の調波エネルギーを出す経路が担体しかなく、
  「無視 = band0/1 が noise のみ = recon loss 破綻」。F0 シフト追従は構造的に
  成立するため Phase D gate を 0.8 → **0.95** に引き上げる【§7】

---

## 1. 前提 — 診断の確定機序と「構造保証」の要件

診断 doc §6 の確定連鎖: A3 (1-3kHz 調波間ノイズ充填、がびがびの主犯) は
**推論時 prior ノイズ ε を decoder が調波非ロックの広帯域ノイズとして描画**する
ことで生じ、**全損失が recon 経路のみを監督する経路盲目**により ε 描画には
学習圧力が一切かからない【実測 (診断 doc)】。損失の追加では原理的に届かないため、
「decoder が何を出せるか」自体を制限する構造保証が唯一の直撃手段。

要件を明文化する:

| # | 要件 | 検証 |
|---|---|---|
| R1 | voiced 帯域 (≤~3kHz) の調波エネルギーは「F0 位相への複素ゲイン」経由でしか出せない | §5.1 (敵対的ゲインでも comb 維持) |
| R2 | 非調波成分は noise 枝経由のみ、かつ noise 枝はトーンを構造的に生成できない | §5.1 (敵対的 σ で 0.2dB) |
| R3 | 推論時 ε が触れる自由度 (ゲイン/σ) は「レベル・音色」であり「調波構造の破壊」に届かない | R1+R2 の帰結【算術】 |
| R4 | ONNX [1,192] 不変 / opset 15 標準 op / CPU p50 +10% gate | §5.4, §5.5 |
| R5 | gaming 経路 (noise バイパス / ゲイン高速変調 / band 端) の全数分析 | §4 |

**decoder の格子の再掲** (S-2 doc §1): 位相が消費されるのは head 格子
(SR/16 = 1378.125Hz) の frame 間整合のみ、subband iSTFT の bin 幅 344.5Hz は
F0 の倍音間隔を分解できない。担体化はこの構造認識の帰結で、「head に位相参照を
*渡す*」(S-2c) から「head の出力を位相参照の*線形結合に制限する*」への強化。

---

## 2. 候補案の比較

### 2.1 案 A (タスク指定): band0 のみ素朴担体化

band0 (0-2756.25Hz) の subband 信号を直接次で置換する:

```
band0[n] = s_h[n] + s_n[n]                                     (SR/4 = 5512.5Hz)
s_h[n]   = Σ_{m=1..M} ā_m[n]·cos(2πmΦ[n]) + b̄_m[n]·sin(2πmΦ[n])
           Φ = cumsum(f0_up / 5512.5)  (float64、S-2c と同じ)
s_n[n]   = iSTFT( σ[k,t]·(n_r + j·n_i)/√2 )    n ~ N(0,1) i.i.d./(bin,frame)
band1-3  = 現行 head (mag/phase 自由) のまま
```

ゲイン ā,b̄ は frame 格子 (86.1Hz) の学習出力を ×64 linear upsample したもの。
head の band0 用出力は mag 9ch + phase 9ch → **log σ 9ch のみ**に減る。

| 観点 | 評価 |
|---|---|
| パラメータ | gain_net Conv1d(256→2M, k=3) = 61.5k、post は −4k (band0 の 18→9ch)【算術】 |
| MACs | +22k/frame ≈ **+0.4%** (predictor 除く、§3.6 の内訳から 1-band 分)【算術】 |
| ONNX | 全て標準 op【実測 §5.4】 |
| **致命的欠点** | **band 端 alias**。band0 単独に置いたトーンの鏡像 (2·2756.25−f) は PQMF 合成フィルタの遷移帯域でしか減衰されず、**f=2400Hz で親比 −9.7dB、2700Hz で −1.4dB**【実測 §5.2】。正常時は band1 が解析対の alias 相殺成分を持つが、自由 head の band1 は位相積分ができない (S-2 doc §1) ため相殺を学習できる保証がない。回避するには担体の上限を ~2.2kHz (alias −17dB) まで下げるしかなく、**A3 帯域 1-3kHz の上部 800Hz が未被覆**になる |

**判定: この形では不成立。A′ に修正する。**

### 2.2 案 A′ (選定): 解析重み付き 2-band 担体描画

倍音 f_m = m·F0 を、**PQMF 解析フィルタの複素周波数応答を固定重みとして
band0 と band1 の両方に描画**する:

```
s_k[n] = Σ_m (a_m·ReH_k(f_m) − b_m·ImH_k(f_m))·cos(2πmΦ[n])
       + (a_m·ImH_k(f_m) + b_m·ReH_k(f_m))·sin(2πmΦ[n])        (k = 0, 1)

H_k(f) = Σ_τ h_k[τ]·e^{−j2πfτ/SR}     h_k = PQMF 解析フィルタ (63 tap、固定)
```

これは「理想 fullband 倍音 Re{g·e^{jθ(t)}} を PQMF.analysis に通した結果」の
解析形そのもの (F.conv1d = 相関のため重みは conj(H_k)、共通位相 e^{−j·31ω} は
両 band 同一で省略可)【算術】。したがって synthesis の隣接 band alias 相殺
(±(−1)^k·π/4 modulation 位相対) が**構造的に**働く。実測で鏡像 spur は
−98〜−112dB (NPR 床) に消え、主峰レベルは band 端をまたいで平坦【実測 §5.2】。

- H_k(f) は 1D lookup テーブル (513 点、線形補間、buffer) — ONNX Gather【実測】
- m·f0 > 2756.25 の倍音も**そのまま**正しく描画される: SR/4 サンプリングの
  cos/sin は Nyquist 超で自動的に折り返し、それが band1 の正しい subband 表現に
  一致する (cosine-modulated filterbank の decimation と同じ機構)【算術+実測 §5.2
  (f=2800-3100 の主峰が正しい周波数に出る)】
- 担体上限: **hard cap f_max = 3000Hz** (mask=0、構造的)。2700-3000Hz は線形
  taper (これは gameable な prior にすぎない — §4.1 #4)。cap 以深 (3kHz+) は
  GT 自体がノイズ性 (comb-HNR 2.4dB @3-5.5kHz【実測 (診断 doc)】) なので
  band1-3 の自由 head + noise が担当
- **これはタスクの案 (c) (fullband 励振 → PQMF 解析) の解析的等価物**: c_full が
  SR レートの sin 生成と 63-tap conv を実行時に払うのに対し、A′ は解析結果を
  周波数応答テーブルに先計算して frame 格子の lookup で済ませる。数学的に同値、
  コストは c_full +18〜30%【実測 (S-2 doc §3.3)】に対し §5.5 の実測どおり

その他の構成要素:

- **ゲイン格子 = frame 格子 (86.1Hz) + 固定 Hann k=5 depthwise 平滑**。
  ゲイン変調の帯域が担体の「コムからの逸脱可能量」を決める (§4.1 #3)。
  head 格子ゲインでは構造保証が消える (comb-HNR 0.5dB)【実測 §5.1】
- **noise 枝 (band0)**: log σ 9ch (bin 幅 344.5Hz の粗い包絡) × frame ごと独立な
  複素正規ノイズ → 既存 OnnxISTFT。**frame 間位相コヒーレンスが存在しないため
  トーン (調波) を構造的に生成できない**。表現できるのは「344.5Hz より粗い
  スペクトル包絡 × 689Hz までの時間変調をもつノイズ」 = 気息・摩擦成分の
  モデルクラスに一致【算術 + 実測 §5.1】
- band1-3 の自由 head は現行のまま (subband_conv_post 出力 9 + 3×18 = 63ch)

### 2.3 案 B: 全 band 担体化

s_k を k=0..3 に拡張 (band2/3 も担体+noise 化)。

| 観点 | 評価 |
|---|---|
| M | band3 上端 11kHz まで F0=70Hz を覆うには M≈157。ゲイン 314ch、gain_net だけで +4.1% MACs【算術】 |
| 期待効果 | ほぼ無い: GT 自体 3kHz 以上は comb-HNR 2.4dB (3-5.5kHz)、0.5-1.0dB (5.5-9kHz)【実測 (plan §1.1)】 = 高域は正しくノイズ性。担体で覆うべき調波構造が GT に存在しない |
| リスク | **「担体が強すぎる」方向の失敗が構造化される**: 高域の自然なノイズ性を担体+noise の 2 枝分解に無理に押し込み、buzzy (過調波) な高域になる。v9 が根治した高域は触らないのが単変量原則にも適合 |

**判定: 不採用。** A3 は 1-3kHz の問題であり、A′ の f_max=3000 で全被覆できる。

### 2.4 案 C: fullband 励振 → PQMF 解析 → 4-band 担体 (帯域限定版)

S-2 スパイクの c_full (+18〜30%) の帯域限定版 (励振を ≤3kHz に制限)。

- 帯域限定してもコスト構造は変わらない: 支配項は SR レートの励振生成
  (5.0ms@5s) と 63-tap 4ch PQMF 解析 conv (+5.8ms@5s)【実測 (S-2 doc §3.3 内訳)】
  であり、倍音数の削減はどちらも消さない。**+12〜20% 見込【推測】で gate 超過**
- かつ ≤3kHz に限定した c_full の出力は **A′ と数学的に同値** (§2.2) —
  高い方を選ぶ理由が存在しない

**判定: 不採用 (A′ に dominated)。**

### 2.5 比較サマリ

| | A (素朴 band0) | **A′ (解析重み 2-band)** | B (全 band) | C (c_full 帯域限定) |
|---|---|---|---|---|
| A3 帯域 (1-3kHz) 被覆 | ~1-2.2kHz のみ | **全域** | 全域 | 全域 |
| band 端 alias【実測】 | −1.4〜−9.7dB | **−98dB 以下** | (同 A′ 機構) | −98dB 以下 (NPR) |
| 追加 MACs (predictor 除く)【算術】 | +0.4% | **+0.6%** | +5〜6% | +6〜8% + SR 演算 |
| ORT CPU 実測 (decoder 単体 Δp50) | — | **M=40 +18% / M=24 +13% (MatMul 融合形、§5.5)** | 未測定 | +12〜20%【推測】(c_full 実測 +18〜30% から) |
| ONNX 標準 op | ○ | **○【実測】** | ○ | ○ |
| 高域 buzzy 化リスク | 低 | **低** | 高 | 中 |

---

## 3. 設計詳細 (案 A′)

### 3.1 全体データフロー

```
enc_p → (MAS 展開) → F0Predictor (S-2p、実装済み) → log f0, vuv
                          │ (detach、teacher forcing は §7)
z_slice [B,192,T] ─┬─ concat f0_feat(log f0, uv) ── conv_pre ─ FiLM ─→ x_frame [B,256,T]
                   │                                            │
                   │                    ┌───────────────────────┤
                   │                    │ gain_net(256→2M, k=3) │ ups ×2 + ResBlocks
                   │                    │ 固定 Hann k=5 平滑     │      ↓
                   │                    │ × mask(m·f0<3000)·uv  │ subband_conv_post
                   │                    │ × H_k(m·f0) lookup    │ (64 → 9+54ch)
                   │                    ↓                       ↓
                   │           eff gains [B,4M,T]      band0 logσ 9ch / band1-3 mag·phase 54ch
                   │                    │ ×64 linear up          │
                   │                    ↓                        ↓
                   │         oscillator bank (SR/4)      σ·(n_r+j n_i)/√2 → OnnxISTFT
                   │         s_0, s_1 [B,1,T·64]         noise0 / band1-3 subband 波形
                   │                    └────────(+)────────────┘
                   │                                    ↓
                   └──────────────────────────→  PQMF.synthesis → fullband [B,1,T·256]
```

### 3.2 ゲイン設計 — frame 格子 + 固定平滑が構造保証の本体

複素ゲイン g_m = a_m − j·b_m は**担体の唯一の学習自由度**。その変調帯域が
「担体枝がコムからどこまで逸脱できるか」を決める:

- ゲインが帯域 W で変調されると各倍音の周囲 ±W に側帯波が立つ。
  **W < F0_min/2 なら調波中間点にエネルギーが構造的に届かない**【算術】
- frame 格子 (86.1Hz、W≈43Hz) の i.i.d. 敵対ゲインで comb-HNR 25.9dB (F0=220)、
  12.9dB (F0=120)。**F0=90Hz では 5.2dB に落ちる** (中間点 45Hz ≈ W)【実測 §5.1】
- → **固定 Hann k=5 depthwise conv でゲインを平滑** (実効帯域 ~±20Hz、
  Nyquist で応答 0)。F0=90Hz の敵対ゲインが **36.8dB** に回復し、低 F0 話者でも
  保証が立つ【実測 §5.1】。固定フィルタなのでモデルは Nyquist 近傍を復元できない
  (構造的)。包絡の時間分解能は ~25ms に落ちるが、急峻なオンセット・気息の
  高速変調は noise 枝 (σ は head 格子 = 689Hz まで変調可) が担当する分業【推測】
- ゲインは x_frame (conv_pre 出力 256ch、FiLM 済 = 話者条件済) から
  Conv1d(256→2M, k=3) で出す。init は small-Gaussian (N(0, 1e-2))【推測 — §8 #2
  の「学習初期から comb が出る」を成立させるため。zero-init は S-2c と違い
  bit 互換退避の意味がない (post の ch 数が変わる時点で非互換)】

M = 40 (f_max 3000Hz を F0 ≥ 75Hz で被覆)。trim: 32 (F0≥94)、24 (F0≥125)。

### 3.3 noise 枝 — 「拘束付き自由度」の設計

```
σ[k,t] = exp(clamp(head 出力 9ch, −9, 6))        (bin 幅 344.5Hz、head 格子)
X_n[k,t] = σ[k,t]·(n_r[k,t] + j·n_i[k,t])/√2     n ~ N(0,1) i.i.d.
s_n = OnnxISTFT(X_n)                              (既存基底をそのまま使用)
```

- 位相が frame ごと独立 → OLA 後も frame 間コヒーレンス皆無 → **持続トーン不可能**
- σ の表現力: 周波数方向 344.5Hz 分解能 (スペクトル包絡のみ)、時間方向 689Hz
  まで (glottal cycle 同期の気息変調も表現可 — これは実音声の特徴で必要な自由度)
- **VUV の扱い**: noise 枝は hard gate **しない**。GT の 1-3kHz comb-HNR は
  13.2dB と有限【実測 (診断 doc)】 = voiced 中にも正常な調波間成分 (breathiness)
  が実在するため。uv は f0_feat 経由で trunk に入っており σ は voiced/unvoiced の
  レベル差を学習できる。担体側は従来どおり hard gate (f0=0 で消灯)

### 3.4 損失との接続 (追加 loss なしで成立)

- 学習時 `decoder_subbands` に s_0/s_1 が加算済みで返る → **既存 sub-band STFT
  loss (c_sub_stft) の GT target (PQMF.analysis(GT)) には、まさに H_k 重み付きの
  調波対が入っている** — 担体のパラメータ化と教師表現が一致しており、ゲインは
  既存 loss だけで直接監督される【算術 (構成から)】
- mel / MR-STFT / MRD / D 系は fullband で従来どおり
- F0Predictor の GT 回帰 (S-2p、実装済み) はそのまま。契約適合も S-2 doc §5 の
  整理から変更なし (担体は loss を追加しない。§4.3 の optional 正則化のみ新規)

### 3.5 ONNX / 推論

- graph 入力 [1,192] 不変 (F0 は内部予測)。新規 op: CumSum / Floor / Greater /
  Clip / ReduceSum / **RandomNormalLike** (noise 枝) — 全て opset ≤15 標準。
  RandomNormalLike は既存 piper graph の z サンプリング
  (`export_onnx.py:680` の randn_like) に前例があり全ランタイム ORT で動作実績
  【実測 §5.4 + コード】
- 位相累積 float64 (S-2c と同じ) → parity 長さ非依存 ~2e-5【実測 §5.4】
- H lookup は Gather ×4 + lerp (frame 格子、コスト無視可)【実測 §5.4 (export 通過)】
- fp16 変換は initializer のみ (convert_fp16 の既知挙動【実測 (S-2 doc §3.2)】) —
  位相・テーブルの精度ハザードなし

### 3.6 コスト集計【算術】

decoder 5.92 MMACs/frame (S-2 doc) 比、frame 格子 1 frame あたり:

| 項 | MACs | 増分 |
|---|---|---|
| gain_net Conv1d(256→80, k=3) | +61,440 | +1.04% |
| ゲイン平滑 (depthwise k=5) | +400 | +0.01% |
| H lookup + eff ゲイン合成 (4M mul ×4) | +640 | +0.01% |
| oscillator bank (Chebyshev + 2-band mul-add、64 サンプル/frame) | +20,480 | +0.35% |
| noise 枝 (σ mul + randn) | +288 | +0.00% |
| subband_conv_post 72→63ch 出力 | −64,512 | −1.09% |
| S-2a (f0_feat + conv_pre 幅) | +14,336 | +0.24% |
| **小計 (S-2p predictor 除く)** | **+33k** | **+0.56%** |
| S-2p predictor h=96 (共通、担体固有でない) | +187,648 | +3.17% |

パラメータ実測: baseline 1,617,480 → 1,909,905 (**+292,425 = +0.59MB fp16**、
predictor/gain_net/f0_feat/post 差分/テーブル込み)【実測 §5.4】。40MB gate に対し
無視できる。v10b-S2 構成比では S-2c (head concat +8ch) が消える分、MACs は
ほぼ相殺 (−0.5%〜+0.6%)【算術】。

> **実装形の指定 (E4→E5 の教訓)**: 上の MACs 集計は実コストを予測しない。
> **正式実装は MatMul 融合形** (ゲイン適用 = per-frame batched MatMul、
> 4M-ch の Resize と mul-reduce を作らない) とし、素朴な elementwise 実装
> (+61〜72%【実測 §5.5】) を禁止する。融合形の数値は素朴形と補間の定義
> (セグメント端点 vs align_corners=False) だけが異なり、ゲイン帯域制限 =
> 構造保証は同一【算術】。

---

## 4. gaming 面の分析 (最重要)

### 4.1 バイパス経路の全数調査

「voiced エネルギーが noise 枝に迂回して担体が形骸化する」系統的検査。
trainable PQMF の教訓 (制約なき自由度は学習圧力で必ず使われる、gaming 4 例目)
を前提に、**「学習に任せる」と「構造で塞ぐ」を経路ごとに明示的に選ぶ**:

| # | 経路 | 塞ぎ方 | 根拠 |
|---|---|---|---|
| 1 | noise 枝がトーンを描く | **構造** (ランダム位相) | frame 独立位相はコヒーレント合成不能。敵対的 σ (F0 同期 AM) でも comb-HNR 0.19-0.54dB【実測 §5.1 #4】 |
| 2 | noise 枝の σ 変調で疑似周期性 (循環定常ノイズ) | **構造 + 性質上無害** | AM ノイズの期待スペクトルは平坦でコム構造なし【算術】+ 上記実測。知覚上は「声のざらつき (roughness)」で、レベルは σ 経由 = recon 監督下 |
| 3 | ゲイン高速変調で調波間を埋める | **構造** (frame 格子 + 固定 Hann k=5) | head 格子ゲインだと comb-HNR 0.5dB まで崩壊【実測 §5.1 #2】→ 格子選択が保証の本体。平滑は固定 conv でモデルが復元不能 |
| 4 | taper 域 (2700-3000Hz) のゲイン増幅で taper 打消し | **許容** (hard cap のみ構造) | mask は乗算なので (0,1) 区間は学習ゲインで打ち消せる = taper は prior にすぎない。構造境界は mask=0 の 3000Hz。打ち消しても A′ は alias を相殺済み【実測 §5.2】なので実害なし |
| 5 | band1-3 自由 head が 3kHz 未満に描く | **構造** (PQMF stopband −99dB) | band 割当は合成フィルタで固定【実測 (v9 canonical)】 |
| 6 | trainable PQMF synthesis での帯域 gain 改変 | **前提条件** | v11 は trainable filter 封印 (診断 doc §5-2)。**担体の alias 相殺は canonical filter が前提** — 封印は A′ の成立条件でもある |
| 7 | voiced band0 の noise 氾濫 (レベル過剰) | **学習 + 監視** (§4.3/§8) | σ は recon 経路上にあり mel/STFT が直接監督 (ε と違い経路盲目でない)。ε 感度は残る (σ(prior z) の OOD) が、効果は「息っぽさの増減」= 2 次的。comb-HNR は枝エネルギー比 ρ で連続に決まる (ρ=4 で 12dB、8 で 14.7dB【実測 §5.1 #3】) ため監視可能 |
| 8 | 担体ゲインを z 経由の ε が乱す | **性質上限定** | ゲインは ±20Hz 帯域制限 = ε が乱せるのは倍音の振幅包絡のみ。調波構造は不変 (R3) |

**「無視」方向 (担体形骸化) の総括**: 経路 1-3, 5 が構造的に閉じているため、
band0/1 の voiced 調波エネルギー (GT の支配成分) を出す方法は担体しかない。
担体を使わない解は recon loss で強く罰される — **形骸化は「損失が許さない」
のではなく「形骸化した瞬間に音が出ない」**。これが concat 注入 (S-2c 単体) との
本質的な差【算術 (構成から)】。

### 4.2 VUV ゲートの設計

| 枝 | ゲート | 理由 |
|---|---|---|
| 担体 | **hard** (f0 = 0 で消灯、既存 `_predicted_f0_hz` の voiced 閾値 0.5 を継承) | 無声区間の偽トーン防止。decoder→vuv の勾配は最初から存在しない (F0 detach) ため soft にする動機がない |
| noise 枝 | **ゲートなし** (uv は特徴量として供給) | GT comb-HNR 13dB 有限 = voiced 中の調波間成分は正常な信号。hard gate は breathiness を殺す (§4.4) |

### 4.3 uSFGAN 型 source 正則化 — 構造が本来の役割を代替、残りは hinge を事前登録

uSFGAN (arXiv:2104.04668) の source 正則化は「**自由な** source-network の出力を
励振らしいスペクトルに拘束する」loss【文献】。A′ では source (担体) が解析形で
自由度がゲインしかないため、**この正則化の本来の役割は構造が先に果たしている**。

残る唯一のレベル系リスク (§4.1 #7: 推論時 σ 氾濫) に対しては、**default off の
hinge 正則化を事前登録**しておく (Phase D で監視指標が発火した場合のみ arm):

```
L_src = λ_src · mean_{voiced frames}( ReLU( log E_n[t] − log E_h[t] − τ ) )
  E_h[t] = Σ_band0,1 s_k^2 の frame 内エネルギー (担体枝、graph 内で直読)
  E_n[t] = 同 noise 枝
  τ      = GT の band0 noise/harmonic 比の p95 から Phase C で校正 (余裕付き上限)
```

- hinge + 緩い τ なので正常な breathiness には勾配ゼロ、病的な氾濫のみ罰する
- 参照するのは**枝エネルギーと GT 由来定数のみ** — 評価器 (frozen encoder /
  契約統計量) を消費しないため zs-eval-contract §2 に非抵触【契約引用 (S-2 doc §5 と同整理)】

### 4.4 逆方向リスク:「担体が強すぎて breathy 成分が死ぬ」

noise 枝に帯域制限・レベル上限を**設けない**根拠 (タスク要求の明示):

1. **GT が noise 枝を要求する**: 1-3kHz comb-HNR 13.2dB = 調波間に −13dB の
   実エネルギーがある【実測 (診断 doc)】。上限はこれを表現不能にし得る
2. **noise レベルは経路盲目でない**: A3 の病理は「ε 描画がどの損失にも見えない」
   ことだった。σ は学習時 recon 経路上にあり、mel/STFT/MRD が調波間 bin の
   magnitude を直接測る → 学習圧力が正しい場所に既にかかっている【算術 (H-C の
   再定式化の裏返し)】
3. **2 枝はスペクトル的にほぼ直交** (コム台 vs 平滑台) → 「担体が noise の仕事を
   奪う」シーソーが起きない。担体は調波間を物理的に埋められない (§5.1) ので、
   GT の調波間成分を再現する唯一の手段が noise 枝 = 使われる理由が構造的にある
4. **上限のハードコードは PQMF 閾値緩和事故と同型の誤り** (向きが逆なだけ):
   worst-case を定数で固定すると、正しい HNR が話者・音素で大きく動く現実
   (breathy voice / falsetto) を殺す。動的な正しさは学習が知っている

緩和は §4.3 の hinge (病的領域のみ) と §8 の監視で足りる【推測 — Phase D で検証】。

---

## 5. プロトタイプ検証 (実測)

スクリプト: `<scratchpad>/v11_head_spike/{common.py, e1_structural.py, e1b_edge.py,
e1c_twoband.py, e2_f0_error.py, e3_export.py, e4_bench.py, e5_opt.py, e5b_mscale.py}` (使い捨て、既存コード
未変更・read-only import)。環境: Windows / torch 2.11.0+cu128 / ORT 1.26.0 /
onnx 1.21.0、CPU EP — S-2 スパイクと同一機。comb-HNR は診断 doc と同方式
(調波 bin ±1 vs 中間 bin ±1 の voiced 電力比、n_fft 4096)。

### 5.1 構造 comb-HNR (E1) — 本スパイクの中心的検証

**担体枝のみ、i.i.d. N(0,1) ゲイン (= 敵対的最悪ケース)、1-3kHz、3 seed median:**

| F0 | 平滑なし | Hann k=5 | Hann k=9 |
|---|---|---|---|
| 90 Hz | 5.24 dB | **36.82 dB** | 47.24 dB |
| 120 Hz | 12.93 dB | 35.62 dB | 51.48 dB |
| 220 Hz | 25.95 dB | 42.43 dB | 57.63 dB |
| 320 Hz | 38.19 dB | — | — |
| sweep 260-330 | 24.51 dB | — | — |

→ **タスクの成立基準「ランダム初期化でも ≥10dB@1-3kHz」は F0≥120Hz で素通し、
ゲイン平滑 (k=5、採用) 込みなら F0=90Hz でも +26.8dB のマージンで成立**。

**ゲイン格子の比較 (F0=220、格子選択が保証の本体であることの実証):**

| ゲイン格子 | comb-HNR |
|---|---|
| frame (86Hz) | **25.95 dB** |
| ups[0] (345Hz) | 0.81 dB |
| head (1378Hz) | 0.53 dB |

**noise 枝の敵対的検査 (σ を F0 同期 AM、noise 単独):** F0=220Hz → **0.19 dB**、
F0=320Hz → **0.54 dB** = 循環定常ノイズではコムを偽造できない (バイパス #2 閉鎖)。

**枝エネルギー比 ρ = E_h/E_n (1-3kHz) → 合成 comb-HNR:**

| ρ | 0.5 | 1 | 2 | 4 | 8 | 16 | ∞ |
|---|---|---|---|---|---|---|---|
| comb-HNR [dB] | 4.79 | 6.90 | 9.36 | 12.00 | 14.69 | 17.32 | 25.94 |

→ 合成 comb-HNR は枝比で連続に決まる = GT (13.2dB) の再現は ρ≈5-6 の**レベル
問題**に還元され、それは recon 損失の監督下 (§4.1 #7 の定量根拠)。

### 5.2 band 端 alias (E1b/E1c) — 案 A → A′ 修正の根拠

**band0 単独描画の鏡像 spur (親倍音比):**

| f | 2000 | 2200 | 2400 | 2500 | 2600 | 2700 |
|---|---|---|---|---|---|---|
| alias 比 [dB] | −27.5 | −17.1 | −9.7 | −6.7 | −3.9 | −1.4 |

**解析重み 2-band 描画 (A′) の同じ測定:**

| f | 2400 | 2500 | 2600 | 2700 | 2800 | 2900 | 3000 | 3100 |
|---|---|---|---|---|---|---|---|---|
| alias 比 [dB] | **−98.6** | −102.5 | −111.9 | −99.2 | −98.6 | −107.9 | −103.8 | −98.6 |

主峰レベルは band 端をまたいで ±0.6dB で平坦 (帯域内コントロール f=1500 は
1-band と bit 一致)。**alias は NPR 床まで消え、担体は band 境界を自由に
またげる**。なお符号規約に注意: `F.conv1d` は相関のため重みは conj(H_k) —
H_k のまま使うと alias が**逆に強め合い** +16dB になる (スパイク中に踏んだ罠、
実装時のテスト必須項目)。

### 5.3 F0 予測誤差への頑健性 (E2)

GT = 担体 (F0=220、a_m=1/m) + noise 床 (comb-HNR 18.7dB)。出力 = 同ゲインで
F0 を cent シフト:

| 誤差 [cent] | comb-HNR @GT 格子 | @自 F0 格子 | LSD 1-3kHz [dB] |
|---|---|---|---|
| 0 | 18.69 | 18.69 | 0.00 |
| +20 | 0.74 | 18.58 | 6.76 |
| −20 | 6.85 | 18.60 | 6.78 |
| ±50 | 0.36 | 18.5-18.9 | ~7.0 |
| +1200 (oct↑) | 20.83 | 24.17 | 3.86 |
| −1200 (oct↓) | 0.76 | 12.36 | 3.83 |

読み方:

1. **構造は F0 誤差で壊れない**: 自格子 comb-HNR は ±50 cent まで不変。
   予測誤差は「がびがび再発」ではなく「ピッチ精度・スペクトル距離 (LSD ~7dB)」
   の問題に転化する — A3 対策としての担体化は predictor 品質に依存しない
2. **測定プロトコルへの含意 (重要)**: GT 格子の comb-HNR は ±20 cent の系統誤差で
   0.7dB に崩壊する。**Phase D の comb-HNR gate は必ず出力自身の F0 トラック
   (pyin、評価専用) で測る** — 診断 doc の測定 (合成音自身の F0) と整合
3. **オクターブエラーの破綻モード**: oct↓ はサブハーモニック挿入 (period-doubling
   のガラガラ声、GT 格子 0.8dB で検出可能)、oct↑ は奇数倍音欠落 (中抜けの hollow、
   GT 格子では**ほぼ不可視** 20.8dB — 偶数倍音が一致するため)。検出は F0
   予測器の GT 回帰 loss と前処理の品質統計 (S-2 doc §4.6) が担当
4. 位相は cumsum で連続なので F0 ジャンプ自体はクリックを生まない。ゲイン側の
   不連続は固定平滑 (§3.2) が抑える【算術】

### 5.4 ONNX export / parity (E3)

- export (opset 15, dynamic T) + checker: **pass**。baseline に無い op:
  `Clip / CumSum / Floor / Greater / InstanceNormalization / RandomNormalLike /
  ReduceSum / Relu / Sub` — 全て標準。InstanceNormalization はプロトタイプ
  predictor の GroupNorm 由来 (実装は S-2p の LayerNorm を使うため出ない)
- RandomNormalLike 入り graph の ORT CPU 実行: **OK**
- parity (noise を入力に固定): T=172 → 2.6e-5、T=431 → 2.0e-5、T=2000 →
  1.2e-5。**長さ非依存** (float64 位相の効果、S-2c と同水準)
- パラメータ: +292,425 (+0.59MB fp16、predictor 込み)

### 5.5 ORT CPU レイテンシ (E4/E5) — 実装形が MACs より支配的

**素朴実装 (E4) は gate を大幅超過し、MatMul 融合 (E5) で 3-5 倍改善した。**
教訓: MACs 集計 (+0.6%、§3.6) は当てにならず、支配項は **ORT の per-op
オーバーヘッドと中間テンソルのメモリ traffic** だった。

| 実装形 | Δp50 (intra=1, 1-10s, decoder 単体) | 備考 |
|---|---|---|
| 素朴 (Chebyshev ループ + 4M-ch Resize + mul-reduce) | **+61〜72%** | 不採用。1s でも +66% = サイズ非依存 → per-op 支配【実測 E4/E5】 |
| Chebyshev → broadcast Cos/Sin 化のみ | +61〜80% (改善なし) | ループ (op 数) は主犯ではなかった — 4M-ch Resize + mul-reduce の traffic が主犯【実測 E5】 |
| **MatMul 融合** (ゲイン適用を per-frame batched MatMul [B,T,4,M]@[B,T,M,64] に、線形補間はランプ重みで表現、4M-ch Resize 除去) | 下表 | **採用**【実測 E5】 |

**MatMul 融合形の M スケーリング (E5b、intra=1、80 ラウンド、Δp50 vs baseline):**

| 長さ | s2 (v10b S-2、参照) | mm M=40 | M=32 | M=24 | M=16 | M=24+pred trim |
|---|---|---|---|---|---|---|
| 1.0s | +4.9% | +18.0% | +16.1% | +12.8% | +10.0% | +11.4% |
| 5.0s | +9.8% | +18.1% | +15.1% | +13.4% | +12.9% | +12.4% |
| 10.0s | +6.9% | +18.9% | +19.7% | +13.9% | +11.2% | +12.6% |

読み方 (S-2 doc §3.3 の注意 2 点をそのまま継承):

1. これは **decoder 単体**の比。e2e (enc_p 6 層 Transformer + flow + DP 込み) の
   相対増分は必ず小さくなる【算術】— mm24 で e2e +7〜9%、mm40 で +11〜13% 程度
   の見込み【推測】。**gate 判定は Phase B で pin するベンチ機の e2e 再測定で行う**
2. 開発機のノイズは ±3〜5% (s2 の測定値が E4 で +3.8〜9.4%、E5b で +4.9〜9.8% と
   振れる)。この表で gate 判定してはいけない
3. **担体の純増分 (vs s2)** は M=40 で +8〜12%、M=24 で +4〜8%。v10b-S2 の
   S-2c を担体で置換する差分としてはこれが正味のコスト
4. intra=4 は素朴形で +127〜179% と激烈に悪化する (小テンソル op の thread sync)。
   mm 形は +18〜51% (E5)。1 スレッド運用 (ort-session-contract の既定) が前提

残りの最適化余地 (trim 順序に組込、§7 #5): ゲインの ZOH 化 (MatMul 半減、
comb-HNR 保証への影響は Hann 平滑済みのため限定的【推測、要実測】)、
oscillator の log-doubling 複素回転化 (Cos/Sin 2 op → Mul ~12 op、透過数削減)。

---

## 6. teacher forcing 設計 — 「無視」の構造的不可能性

S-2 doc §4.4 の設計 (GT F0 → 予測 F0 detach への確率アニール、prior 残差は常に
予測 F0) を**そのまま継承**する。担体化で変わるのは「無視の可能性」だけ:

| | S-2c (concat) | 担体化 (A′) |
|---|---|---|
| F0 経路を使わない解 | head_proj 係数 ~0 で存在 (v10b smoke: シフト追従 0.0) | **存在しない**: band0/1 の調波エネルギーは担体経由のみ。ゲイン 0 → voiced 帯域が noise のみ → recon 大破綻 |
| F0 への出力依存 | 学習圧力に依存 (弱い) | **構造** (出力ピッチ = 注入 F0、恒等的) |
| 勾配の行き先 | mel→head_proj (使われれば) | mel/STFT/D → gain_net・σ head (常時)。**F0 predictor へは流れない** (detach、FastPitch 型) — predictor は純粋に GT 回帰で学習し、decoder は「与えられた F0 を使う」ことしか学べない |

なお「decoder が F0 を無視して z の音高で鳴らす」抜け道も消えている: z は
trunk 経由でゲイン・σ に触れるが、どちらも調波の**位置**を動かせない (§4.1 #8)。
band1-3 (2756Hz+) の自由 head は z の音高で鳴らせるが、GT の 3kHz+ はノイズ性で
調波を置く動機が薄く、pyin のピッチ判定は低次倍音優勢【推測 — Phase D #1 で検証】。

---

## 7. Phase D 検証項目 (事前登録案)

v10b plan §4.3 の流儀 (測ってから基準をいじらない) に従い先に固定する。
**#1, #2, #5 が go/no-go**、他は監視。

| # | 項目 | gate | 根拠 |
|---|---|---|---|
| **1** | **F0 シフト追従率** (±2 semitone、出力 F0 は pyin) | **≥ 0.95** (S-2 案の 0.8 から引上げ) | 構造的にほぼ 1 のはず (§6)。未達なら実装バグ (配線・スライス位相) を疑う — 学習圧力の問題ではない |
| **2** | **comb-HNR@1-3kHz** (voiced、**出力自身の F0 トラックで測定** — §5.3 #2) | **≥ 10dB を 400 batch までに** | 構造下限 (担体優勢時 26dB+【実測】) は学習を要さず、必要なのはゲインが小 init から育つ時間のみ。400 batch で届かなければ縮退経路 (下記) が発動している |
| 3 | ns 掃引安定性: ns ∈ {0.667, 0.4, 0.2} で comb-HNR 変動 | ≤ 2dB (監視→本走前に gate 化判断) | **A3 根治の決定的テスト**: v10b は 4.77→12.28dB と ns に用量反応 (H-B)。担体化で ε の触れる自由度は調波構造に届かない (R3) ため依存が消えるはず |
| 4 | F0 predictor 系 (S-2 §6.4 継承): voiced L1 単調改善 / vuv acc ≥ 0.9 / F0 std ≥ 45Hz | S-2 と同じ | 変更なし |
| 5 | **CPU コスト**: decoder 単体 + e2e p50、pin したベンチ機、**MatMul 融合形で測る** | **+10% 以内** (v9 baseline 比、e2e)。超過時 trim 順 (事前登録): (1) M 40→32→24 (24 で decoder 単体 +13%【実測 §5.5】、被覆は F0≥125Hz で 3kHz / F0=90 で 2.16kHz に後退)、(2) ゲイン ZOH 化 (MatMul 半減、comb-HNR 再測定必須)、(3) predictor h96→64 + f0_ch 8→4 (−1〜2%【実測 §5.5 mm24t】)、(4) M=16 (低 F0 被覆をほぼ放棄 — A3 主対象の F0~200+ 話者には残る)、(5) それでも超過なら S-2c (concat) へ縮退し担体は v12 送り | plan §4.3 |
| 6 | 縮退監視 (a): voiced band0,1 の枝エネルギー比 ρ (graph 内直読) | GT 校正値 (Phase C で comb-HNR 分布から) の [p5, p95] 内 | ρ→comb-HNR 曲線【実測 §5.1】。下振れ = noise 氾濫 (§4.3 hinge を arm)、上振れ = breathy 死 (聴感 A/B へ) |
| 7 | 縮退監視 (b): 2.7-3.0kHz 狭帯域ピーク検出 (alias regression) | spur なし | A′ の相殺は canonical PQMF 前提 (§4.1 #6)。重み符号バグは +16dB で即見える【実測 §5.2】 |
| 8 | 縮退監視 (c): 低 F0 話者 (F0 中央値 < 130Hz) の comb-HNR 別集計 | 監視のみ | 全実測が F0~300 素材という診断 doc 残タスク (ii) への対応。E1 は合成で F0=90 を検証済みだが実データで確認 |
| 9 | A1 非退行: comb_excess_db / hf_autocorr | H-1 達成値から非悪化 | 単変量原則 (v10b plan) |

---

## 8. リスクと緩和

| # | リスク | 機序 | 緩和 |
|---|---|---|---|
| R1 | 担体の音色が「ブザー的」になる (過剰にクリーンな調波) | ゲイン帯域 ±20Hz では shimmer / 微細な調波揺らぎが表現しきれない【推測】 | noise 枝の glottal 同期変調 (689Hz まで可) が知覚的 roughness を供給。聴感 A/B を Phase D に含める。悪ければ平滑 k=5→3 (保証は F0≥120 に後退) |
| R2 | 推論時 σ 氾濫 (ε 感度の残滓) | σ(prior z) の OOD | 監視 #6 + hinge 正則化 (事前登録、default off、§4.3) |
| R3 | F0 predictor 品質が聴感を律速 | 構造化により F0 誤差が全て出力ピッチに直結 (±20cent で LSD 6.8dB【実測】) | S-2p の GT 回帰 gate (§7 #4)。オクターブエラーは前処理品質統計で遮断 (S-2 §4.6) |
| R4 | 解析重みの符号/位相バグ | conj 忘れで alias が +16dB 強め合い【実測 §5.2】 | 単体テスト必須: 単一トーン 2400-3100Hz 掃引で spur ≤ −90dB を CI に固定 (E1c がそのまま fixture になる) |
| R5 | canonical PQMF 前提の崩れ | trainable synthesis と併用すると相殺が壊れる | v11 は trainable filter 封印 (診断 §5-2 と同一決定)。コード上も相互排他 assert を推奨 |
| R6 | 学習初期の G/D 不均衡 (band0 が小 init 担体 + noise のみ) | D が「初期の G はノイズ声」を過学習【推測】 | small-Gaussian init (§3.2) で調波が最初から微弱に存在。smoke で G/D loss 監視 (§7 は S-2 の安定性項を継承) |
| R7 | VC (voice_conversion) 経路 | S-2 実装が既に NotImplementedError (models.py) | 変更なし (v10c 以降の課題のまま) |

---

## 9. 未解決事項 / deviation

- **タスクからの逸脱 1**: 指定案 (a)「band0 のみ担体化」は band 端 alias
  (−1.4〜−9.7dB) で不成立と実測し、**解析重み付き 2-band 描画 (A′) に修正**した。
  A′ はタスク案 (c) の解析的等価物でもあるため、実質「(a) と (c) の合流点」
- **タスクからの逸脱 2**: 低 F0 (90Hz) の worst-case が素朴形で 5.2dB と
  基準割れ → **固定 Hann k=5 ゲイン平滑を設計に追加** (36.8dB に回復)
- **タスクからの逸脱 3**: レイテンシは「S-2 実測 +2-10% への増分」に収まらず、
  素朴実装で +61〜72% を検出 → **MatMul 融合を実装形として指定**して M=40
  +18% / M=24 +13% (decoder 単体) まで回収。gate 成立は e2e 測定 (Phase B)
  + trim 順序に委ねる — S-2 と同じ「gate 境界」着地
- **タスクへの追加知見**: comb-HNR gate は GT/予測 F0 格子で測ると ±20cent で
  崩壊する (§5.3) — Phase D の測定プロトコルに「出力自身の F0 トラック」を明記
- **未検証 (学習が要る)**: (i) 実データでの枝分業 (ρ が GT 域に収束するか)、
  (ii) ns 掃引不変性 (§7 #3 — A3 根治の本丸)、(iii) ブザー化リスク R1 の聴感。
  いずれも Phase D smoke の担当
- **未測定**: bf16 学習時の autocast 挙動 (S-2c は fp32 固定で解決済み — 担体の
  oscillator も同じ fp32 固定を踏襲すれば同型のはず【推測】)。intra=4 は E4 で
  参考測定のみ (gate は pin ベンチ機)
- 実装時の設計余地: noise 枝を band1 にも置くか (現設計は band0 のみ σ 化、
  band1 は自由 head のまま)。band1 の自由 head が担体と冗長な調波を出す抜け道は
  理論上残る (2756-3000Hz の重複域のみ、位相積分できないので実害は限定的
  【推測】)。Phase D #7 の alias 監視が兼ねる

---

## 10. 出典

- **本スパイクの実測**: `<scratchpad>/v11_head_spike/` の `e1_structural.py`
  (構造 comb-HNR / ゲイン格子 / ρ 曲線 / 敵対的 σ)、`e1b_edge.py` (band 端 alias
  周波数依存 + ゲイン平滑)、`e1c_twoband.py` (解析重み 2-band の alias 相殺)、
  `e2_f0_error.py` (F0 誤差頑健性)、`e3_export.py` (export/op/parity)、
  `e4_bench.py` (素朴形レイテンシ)、`e5_opt.py` / `e5b_mscale.py` (MatMul 融合 +
  M スケーリング)。出力: 各 `*_out.txt`。**scratchpad はセッション限定 — 本実装
  時に E1c (alias 掃引) と E1 (構造 comb-HNR) はテスト fixture として
  `src/python/tests/` に移植すること** (§8 R4)
- **コード読解 (実測)**: `src/python/piper_train/vits/mb_istft.py`
  (HarmonicPhaseTemplate / subband_conv_post / PQMF canonical)、`stft_onnx.py`
  (OnnxISTFT 基底)、`models.py` (F0Predictor / `_f0_for_decoder` / `_predicted_f0_hz`)、
  `export_onnx.py:680` (RandomNormalLike 前例)
- **設計・診断**: [`zero-shot-v10b-residual-noise-diagnosis.md`](zero-shot-v10b-residual-noise-diagnosis.md)
  §5-6 / [`zero-shot-v10b-s2-f0-design.md`](zero-shot-v10b-s2-f0-design.md) /
  [`zero-shot-v10b-quality-plan.md`](zero-shot-v10b-quality-plan.md) §1.1, §4.3 /
  [`docs/spec/zs-eval-contract.md`](../spec/zs-eval-contract.md) §2 /
  [`zero-shot-noise-root-cause-pqmf.md`](zero-shot-noise-root-cause-pqmf.md)
- **文献**: NSF (arXiv:1904.12088) / uSFGAN (arXiv:2104.04668) / SiFi-GAN
  (arXiv:2210.15533) / SiFiSinger (arXiv:2410.12536) / DDSP (arXiv:2001.04643、
  frame-rate 包絡 × oscillator bank の系譜) / Period VITS (arXiv:2210.15964) /
  Nguyen 1994 (near-perfect-reconstruction pseudo-QMF、解析重みの根拠) /
  FastPitch (arXiv:2006.06873、predictor detach の流儀)

## 11. Phase B smoke で発見した盲点と修正 (2026-08-21)

arm H 初回 smoke が担体 gate で不合格 (comb-HNR 2.27dB / 追従率 0.0)。統合配線は
シロ (一定 F0 なら full forward で 51dB、ピークは正確に m·F0)【実測】。真因は
本 doc §5.3 E2 の盲点:

- **E2 は静的 cent シフトのみ検証**していたが、実際の予測 F0 は undertrained
  段階で frame 単位ジッタ (|ΔF0| median 12-26Hz/frame) + 孤立 1-frame V/UV
  明滅を持ち、担体がそれを**忠実に FM/AM 描画**して倍音 m で m 倍に拡大 →
  調波が潰れる (carrier 単独 5.2dB)【実測】
- 修正: `_stabilize_predicted_f0` — **固定 58ms box 平滑 (voiced マスク付き) +
  V/UV 多数決 k=5** を推論時の予測 F0 にのみ適用 (GT teacher forcing 不適用 /
  carrier off は bit 不変 / 固定・学習不能 = §3.2 ゲイン平滑と同じ構造保証)。
  実測 2.67→14.17dB (E2E、predictor 級ノイズ較正)【実測】
- 副発見: 追従率 0.0 は **f0_shift_ablation が pyin 欠測時に 0.0 を捏造**して
  いた測定バグ (実際は平滑後 ±2st に対し出力 197.99/249.45Hz = 追従 ~1.0)。
  欠測は `insufficient_data` として顕在化するよう修正 (verdict は保守側維持)
- 教訓: 構造保証の検証には**入力の動的な汚さ (時間微分)** も敵対条件に含める。
  新テスト `test_carrier_f0_stability.py` が predictor 級ノイズの E2E を恒久 pin
