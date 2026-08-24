# Zero-Shot v11 — 条件付け経路の容量改修 設計調査 (2026-08-20)

> **Status**: 診断完了 (§10、2026-08-20) + P0 (`--film-free-scale`) / P2 (enc_p AdaLN)
> 実装済み・v11 本走で稼働 (v11 の ONNX export バグの真因は P2 の AdaLN 断線だった)。
> v10b oracle 診断
> ([`zero-shot-v10b-quality-plan.md`](zero-shot-v10b-quality-plan.md) §8) で確定した
> 「アーキ (条件付け経路) 律速」— seen 話者ですら合成音の 20 択話者識別 top-1 43%
> (実音声 98.5%) — に対する v11 改修の設計調査。§9 で S-1 識別器圧力でも 0.60
> plateau が不変 = **学習信号では壁を越えられない**ことが確定済み。
> 文献調査: 本セッションの 3 並列 deep-research (YourTTS/HierSpeech++ 精読 /
> AdaLN 系 / flow 強化 + 多粒度)。
>
> **表記**: 【実測】= 本プロジェクトの測定、【コード】= 実装確認済み事実、
> 【文献】= 論文・公式実装で確認、【推測】= 未検証。

## TL;DR

1. **改修の前に $0 の診断を挟む**: 条件付けチェーン (192-d emb → spk_proj → 4 注入点)
   のどこで話者情報の 6 割が落ちるかは未分解。§3 の D-1〜D-9 (全て学習不要、
   ローカル CPU/GPU、既存 oracle ハーネス流用) で **「prior 彫刻不足 / flow 転写不足 /
   decoder 描画不足」の 3 分岐**に一意化してから改修を確定する
2. 文献精読で**設計前提が 3 つ更新された**:
   - **現行 decoder FiLM の scale = sigmoid+0.5 ∈ [0.5,1.5] は FiLM 原典が「有害」と
     実証した形** (γ を sigmoid/tanh に制限すると劣化、γ 側が条件付けの主役)【文献】
     — 無料で直せる欠陥
   - **SNAC 論文自身の ablation で「全モジュール注入」は SNAC を中和する**
     (FLOW のみ条件付け SECS 0.352 > 全点注入 0.320)【文献】— 現行構成
     (SNAC + decoder FiLM + enc_p + DP) は SNAC の**負け側 arm と同型**。
     注入点は「多いほど良い」ではなく、オーケストレーションが必要
   - **HierSpeech++ の AdaLN-Zero は flow coupling 限定** (T-Flow)。それ以外は
     VITS 型 WN 条件 + 射影加算のまま【文献】— 「全面 AdaLN 化」は文献の実像ではなく、
     **モジュール別の適正形式** (enc_p=AdaLN / decoder=AdaIN / flow=Transformer
     coupling + AdaLN-Zero) が実像
3. **推奨 (優先順)**: P0 無料修正 (FiLM scale 開放 + テレメトリ + EMA 拡張) →
   P1 診断 → P2 enc_p AdaLN 化 → P3 decoder per-resblock AdaIN 化 →
   P4 flow 強化 (診断 D-6 の分岐で形式選択) → P5 注入オーケストレーション A/B。
   全て ONNX [1,192] 契約内・CPU RTF 実質不変【コード+推測】
4. 参照系列を使う多粒度化 (Mega-TTS 2 MRTE / SEF-VC / XTTS Perceiver) は
   +0.08〜0.11 SIM の文献実測がある最強レバーだが **[1,192] 契約と非両立 → v12 の
   契約改定案として隔離** (§5.4)

---

## 1. 問題の定式化

oracle 診断 (§8) の確定事実【実測】:

| 事実 | 値 | 含意 |
|---|---|---|
| seen−holdout SECS 差 | +0.007 (実質ゼロ) | 汎化ではなく経路の問題 |
| 20 択話者識別 top-1 (合成音) | 43% (実音声 98.5%) | 経路は話者情報の約 4 割しか運ばない |
| 中心化後 top-1 | 73% | 目減りの一部は合成音共通のドメインオフセット (synth/real 間 cos 0.814) |
| cond→synth 回帰傾き | 0.66 / 話者間広がり保持 69.6% | 出力が平均声方向に圧縮されている |
| v10b S-1 (識別器圧力追加) | 0.60 plateau 不変 | 学習信号の増強では動かない |

つまり「条件は入力されているのに、出力の話者間分離が **一様に ~0.66 倍へ圧縮**される」
状態。これは (i) 変調の実効ゲイン不足 (学習均衡として条件を弱く使う)、
(ii) 注入形式の表現力不足 (加算 bias / 有界 FiLM は迂回・無視できる)、
(iii) 特定モジュールの転写ボトルネック (flow⁻¹ が音色を彫れない等)、の
いずれか/複合。**どれかで対策が違う**ため、§3 の診断で分解する。

なお条件付け経路の弱さは残存ノイズ A3 とも接続している: multi-spk zero-shot が
ε の調波ロック描画を獲得しない問題 (H-E 再定式化、
[`zero-shot-v10b-residual-noise-diagnosis.md`](zero-shot-v10b-residual-noise-diagnosis.md) §6)
は「decoder が話者条件を強く使えないことの別の現れ」の可能性【推測】。
v11 の改修が A3 に波及するかは Phase E の comb-HNR 追跡で確認する (§7.3)。

## 2. 現行条件付け経路の実測マップ【コード】

v10b 時点 (models.py / mb_istft.py / modules.py、quality=medium:
hidden=192、gin_channels=512、decoder ch 256→128→64):

| # | 注入点 | 機構 | パラメータ (概算) | 勾配が届く loss | 備考 |
|---|---|---|---|---|---|
| 0 | `spk_proj` | Linear(192→512)+LN+GELU+Linear(512→512) | 362k | SCL/SupCon + (FiLM/SNAC/enc_p 経由の全 loss) | 全注入点の共通幹 |
| 1 | `enc_p` (M2) | Conv1d(512→192) を transformer 第 3 層入口に**加算** | 99k | KL + dur (間接) | 全時刻一様 bias 1 本 |
| 2 | flow (M1 SNAC) | SN/SDN: `sn_linear` Conv1d(512→192)×4 段、話者統計のみ。WN は g_lang のみ | 394k | KL (+swap 系は切除済) | mean_only=True、時不変統計 |
| 3 | decoder (FiLM×3) | 入口 Conv1d(512→512) + 各 upsample 段 Conv1d(512→256/128)。**scale = sigmoid(·)+0.5 ∈ [0.5,1.5]** | 460k | mel/STFT/adv/fm/SCL | resblock 内部は無条件 |
| 4 | DP (M3) | `g_dp = g.detach() + spk_proj_dp(g.detach())` 残差ヘッド | ~262k | dur (残差ヘッドのみ) | YourTTS も detach (§4.1) |
| 5 | enc_q (学習時のみ) | WN cond_layer Conv1d(512→6144) | 3.15M | recon 系 | ONNX 非搭載 |
| — | `emb_lang` | g = g_spk + g_lang の加算共有 | 3.6k | — | init 時 lang ノルムが spk の 2.7 倍【実測 (v10 調査時)】、学習後は未測定 → D-2 |

推論グラフ内の条件付けパラメータ合計 ≈ 1.6M / 全体 ~19M (**8%**)。
一方 flow の WN 本体は ~7M (全体の 37%) を占めるのに、SNAC 化後は
話者情報を**時不変の m/v 2 ベクトル (192 次元 ×2 ×4 段) 経由でしか**受け取らない —
「モデル最大の容量ブロックが話者条件にほぼ盲目」という非対称がある【コード】。

## 3. 診断設計 (タスク 1) — ボトルネックの分解、学習不要

全て v10b ep79 (または v10a-r2 ep69) の ckpt に対するローカル実験。
§8 oracle のハーネス (seen 20 話者 / 同一プロトコル) を流用。合成規模は
~20 話者 × 3-5 発話 × ~8 構成 ≈ 500-800 wav、CPU で数時間・**$0**。
評価は全て「20 択識別 top-1 (raw + 中心化) + cross-utt SECS」。

### D-1. spk_proj 出力の話者識別性 (合成不要、数分)

20 話者 × 各 10 発話の per-utterance CAM++ emb を `spk_proj` に通し、
g_spk [512] 上で最近傍 centroid 識別 + 有効ランク (共分散の participation ratio)。

- **期待**: spk_proj は決定的 MLP なので ~98% を維持するはず。ここが低ければ
  spk_proj 自体の rank collapse (改修候補 (b) が直撃)。高ければ
  「情報は g_spk まで届いている」ことが確定し、以降の注入点に容疑が絞られる

### D-2. lang/spk ノルム比 + 変調統計テレメトリ (合成不要、数分)

学習後の実測: (i) ‖g_lang‖/‖g_spk‖、(ii) decoder FiLM 各段の
scale spread = 話者 20 名間での sigmoid(scale_raw) の std (チャネル平均)、
(iii) SNAC sn_m/sn_v の話者間 std、(iv) enc_p cond(g) ノルム / hidden ノルム比、
(v) DP 残差 delta ノルム。

- **期待**: 「FiLM が眠っている (scale ≈ 1.0 ± ε)」「lang が g を支配」等の
  定量所見。v10a で観測した sn ノルム単調成長 (0.65→1.71) の定点にもなる。
  **v11 学習時テレメトリ (§7.3) の事前ベースライン**

### D-3. 注入点 leave-one-out ablation (合成あり、主力実験)

`infer()` を注入点別 g 上書き付きでラップし (models.py は g_spk/g_lang を
分離済みなので ~50 行の診断スクリプトで可能【コード】)、**1 点だけ**を
話者平均 ḡ (20 名平均 emb) に置換して合成 → top-1/SECS の低下量 Δ を測る。

対象: {dec FiLM (入口/段1/段2 個別も), enc_p, SNAC SN/SDN, DP}。

- Δ が大きい点 = その点が現に運んでいる話者情報。**全点の Δ 合計 vs 全点同時
  置換の Δ** で冗長性 (重複注入) も見える

### D-4. 注入点 isolation (only-one)

D-3 の逆: 1 点だけ目標話者、他は ḡ。各注入点の**単独転写容量**を測る。
SNAC 論文の「FLOW のみ > ALL」【文献】が我々の構成でも成り立つかの直接検証
(SNAC-only arm vs FiLM-only arm vs 現行 ALL)。

### D-5. recon 経路 oracle (decoder 描画能力の単離)

teacher-forced: GT 音声 → enc_q → posterior z → dec(z, FiLM(g)) の合成音で
top-1 を測る (§6 残タスク (i) の teacher-forced comb-HNR と同一バッチで実施可)。

- **判定**: recon top-1 ≈ 95%+ なら「z が話者を運び decoder は描画できる」=
  ボトルネックは prior 側 (enc_p→flow⁻¹)。recon も ~60% なら **decoder の
  描画自体が律速** → P3 (decoder AdaIN) の優先度が最上位に繰り上がる

### D-6. VC 経路 oracle (flow 転写能力の単離)

既存 `voice_conversion()` (models.py:1965)【コード】で
src 音声 → flow(g_src) → flow⁻¹(g_tgt) → dec(g_tgt) の 20×20 VC を合成し
target 話者の top-1 を測る。enc_p / DP / duration を経由しないため、
**flow⁻¹ + dec の音色注入能力だけ**が出る。

- **判定分岐 (D-5 と組で v11 の主形式を決める)**:
  - VC top-1 ≫ TTS top-1 (43%) → flow は彫れている。不足は **prior の話者特異性
    (enc_p の m_p/logs_p)** → P2 (enc_p AdaLN) を主軸
  - VC top-1 ≈ TTS top-1 → **flow⁻¹ が音色を注入できていない** → P4 (flow 強化) を主軸
  - D-5 も低い → P3 (decoder AdaIN) を主軸

### D-7. conditioning gain 外挿 (「容量」か「ゲイン」かの切り分け)

推論時に g_spk を話者方向へ外挿: g' = ḡ + α(g_spk − ḡ)、α ∈ {1.0, 1.25, 1.5, 2.0}。
top-1/SECS/UTMOS/帯域を測る。

- **判定**: α>1 で top-1 が単調に上がり品質が許容なら、経路の表現力はあるが
  **学習均衡として条件を弱く使っている** (= 注入形式の「無視されやすさ」問題、
  P0-1/P2/P3 の形式変更が効く筋)。上がらなければ表現力 (容量) の不足が本体
- 副産物: α 最適値は v11 を待たない**推論時の応急改善ノブ**になり得る【推測】
  (品質劣化と Goodhart 監視付きで)

### D-8. z_p / m_p の話者 probe (合成不要)

時間平均した m_p (prior mean) / z_p / posterior z に対する linear probe で
話者識別率を測る。prior が既に話者情報を失っているのか、prior は持っているが
decoder で消えるのかを D-5/D-6 と相互検証。

### D-9. ドメインオフセットの寄与分離 (集計のみ)

§8 の中心化 43→73% の再現 + 「synth 平均を real 平均へ平行移動した場合の
SECS 上限」を数値化 — decoder 実音声化 (H 系) が SECS に効く分の見積り。

### 判定マトリクス (事前登録)

| D-5 recon | D-6 VC | 主ボトルネック | v11 主軸 |
|---|---|---|---|
| 高 (≥90%) | 高 (≥80%) | prior 彫刻不足 (enc_p) | **P2** enc_p AdaLN + DP/F0 韻律経路 |
| 高 | 低 (≤55%) | flow⁻¹ 転写不足 | **P4** flow 強化 (T-Flow lite) |
| 低 (≤70%) | — | decoder 描画不足 | **P3** decoder AdaIN 全面化 |
| 中間 | 中間 | 複合 + D-7 陽性ならゲイン問題 | P0+P2+P3 同時、P4 は Phase D A/B |

D-3/D-4 の注入点別 Δ は上記と独立に「SNAC 中和が起きているか」を判定し、
P5 (オーケストレーション) の要否を決める。

## 4. 文献精読の結果 (タスク 3: 固定 global embedding 方式の上限再確認)

### 4.1 YourTTS / HierSpeech++ / piper v10b の注入構造 差分表【文献+コード】

3 並列調査 (公式実装まで裏取り) の統合。出典: arXiv:2112.02418 + Coqui TTS 実装 /
arXiv:2311.12454 + 公式実装 / 本 repo。

| モジュール | **YourTTS** (SECS 0.864*) | **HierSpeech++** (SECS 0.907*) | **piper v10b** (0.60/0.69) |
|---|---|---|---|
| 話者表現 | H/ASP 512-d、L2 正規化、**固定** | StyleEncoder (mel→256-d global)、**joint 学習** | CAM++ 192-d、L2 正規化、**固定** + spk_proj (joint) |
| text encoder | **無条件** (lang 4-d concat のみ) | 射影加算 (TTV 側) | 第 3 層入口に加算 (M2) |
| flow | 全 4 coupling の **WN 内 global conditioning** (Conv1d(512→2·h·n_layers) gated 加算) | **Transformer coupling (DiTConVBlock) + AdaLN-Zero** — norm1/norm2 を shift/scale/gate 変調、zero-init。双方向学習 (Bi-Flow) | SNAC SN/SDN (時不変統計 2 本/段)、WN は lang のみ |
| posterior enc | WN global conditioning | WN global conditioning (dual-audio) | WN global conditioning |
| decoder/vocoder | **入口 1 点の射影加算のみ** | 入口 1 点の射影加算 (+F0 経路加算) | 入口 + 2 段 FiLM (sigmoid 有界 scale) |
| DP | 射影加算、**g detach** | 射影加算 | detach + 残差ヘッド (M3) |
| F0/source | なし | PitchPredictor に射影加算 + F0 を generator 入口へ | S-2 は v10b で除外 (v10c 再設計) |
| 追加の話者 loss | SCL α=9 — **ただし erratum: 勾配が流れていなかった** | なし (Bi-Flow が実質の推論経路正則化) | cross-utt SupCon + (v10b: JCU 識別器) |

\* SECS は **Resemblyzer 測定で我々の CAM++ 値と直接比較不能**。さらに
YourTTS 0.864 は **GT の SECS 0.824 を上回る** (VCTK 11 unseen)【文献】—
正規化転写率が 1.0 超になる測定系であり、絶対値は当てにならない。
HierSpeech++ 0.907 も Resemblyzer (LibriTTS test-clean unseen)。
**「彼我の差 0.86 vs 0.61」をそのまま容量差と読むのは誤り**で、比較可能なのは
構造と ablation の差分のみ。

### 4.2 差分表から読める「我々に欠けているもの」

1. **flow の条件付け容量**: YourTTS は flow の WN 全層に gated conditioning
   (512→2·h·n_layers = 段あたり ~786k param 級)、HierSpeech++ は
   transformer coupling + AdaLN-Zero (**T-Flow 除去で EER 4.86→7.50、+14M param
   で類似度の主寄与**【文献: Table IV】)。我々の SNAC は段あたり 192×2 の
   時不変統計のみ — **3 者で最も細い**。§2 末尾の「flow 7M param が話者盲目」
   と合わせ、最有力の容量ギャップ
2. **decoder の多点注入は我々だけ** — YourTTS/HierSpeech++ とも decoder は
   入口 1 点。にもかかわらず彼らの類似度が高い = decoder 多点 FiLM は
   必要条件ではなく、SNAC 中和 (§4.3) を考えると**過剰注入が flow の学習を
   阻害している可能性すらある**【推測 → D-3/D-4 で検証】
3. **joint 学習の style encoder** (HierSpeech++/SNAC ablation): SNAC 論文では
   固定 pre-trained encoder (H/ASP) が joint GST に SMOS 4.19→3.61 で負ける
   【文献】。我々の固定 CAM++ + joint spk_proj は中間形態。192-d ボトルネック
   通過後の情報しか使えない制約は (d)/v12 の論点 (§5.4)

### 4.3 条件付け形式の効果序列 (文献総括)

| 知見 | 数値 | 出典 |
|---|---|---|
| 形式の一般序列: concat/加算 < AdaLN < **AdaLN-Zero** | DiT: FID 35.2 (in-context) / 25.2 (adaLN) / **19.5 (adaLN-Zero)**、計算コストは adaLN 系が最小 | arXiv:2212.09748【文献】 |
| **連続特徴 (音響 decoder) では AdaIN > AdaLN** | StyleTTS: AdaIN→AdaLN CMOS **−0.21**、AdaIN→concat −0.17、concat では energy 相関 0.91→**0.19** (= 加算/concat は無視される、の定量証拠) | arXiv:2205.15439 Table VII/VIII【文献】 |
| encoder 側の conditional norm も効く | AdaSpeech 4: encoder CLN 除去 CMOS −0.21、encoder+decoder 両除去 −0.36 | arXiv:2204.00436【文献】 |
| 加算→SALN (FS2 系) | unseen cos 0.775→0.791、**話者分類 acc 72.6%→83.5%** (我々の oracle top-1 と同型の指標) | arXiv:2106.03153 Table 4【文献】 |
| FiLM は γ (乗算) が主役、**γ の sigmoid/tanh 制限は劣化** | CLEVR: γ 固定 −65.4% vs β 固定 −1.0% | arXiv:1709.07871【文献】 |
| **SNAC は他所の話者注入で中和される** | FLOW のみ条件付け SECS 0.352/SMOS 4.19 > 全点注入 0.320/4.07 | arXiv:2211.16866 Table I【文献】 |
| 正規化 coupling 単独は逆効果になり得る | LNACont: LNAC 単独 SECS 0.419→0.405 (contrastive 併用で 0.559) | LNACont, EUSIPCO 2024 (arXiv なし)【文献】 |
| weight/kernel 生成型 (hyperconditioning) は加算より強い | Blow: spoofing 66.2% vs 加算 39.5% (尤度ほぼ不変で転写だけ激変) | arXiv:1906.00794【文献】 |
| 参照系列 → K token 化 (契約外) | PFluxTTS: 単一 emb SIM 0.47 → 16 token **0.57**; Mega-TTS 2 w/o MRTE 0.841→0.905; SEF-VC 0.711→0.825 | arXiv:2602.04160 / 2307.07218 / 2312.08676【文献】 |
| [1,192]→K learned token 展開 (契約内) | **文献空白** — 前例発見できず。系列版の利得はボトルネック迂回由来の可能性 | 3 調査とも【文献 (不存在確認)】 |

LNACont の補足: 彼らは**言語を正規化 (LN/LDN)・話者を WN gin** に入れる —
我々の E2 (話者を SN/SDN・言語を WN) と**役割が逆**の構成も公刊されている。
同一 coupling 内で「正規化」+「WN gin」の 2 チャンネル併用が成立する先例
として P4-c2 の根拠になる【文献】。

## 5. 改修候補の比較 (タスク 2)

前提: ONNX 入力契約 [1,192] 不変 / FP16 ≤ 40MB gate (現 38.8MB、残り ~1.2MB
しかないため**パラメータ相殺の設計が必須**) / CPU RTF 実質不変。
なお global 条件の AdaLN/AdaIN/FiLM 射影は全て [B,512,1]→[B,C,1] を
**発話あたり 1 回**計算して時間軸へ broadcast するため、RTF への影響は
変調の elementwise 積和のみ ≈ ゼロ【コード+推測】。

### 5.1 候補 (a): 「全面 AdaLN 化」→ 修正版「モジュール別適正 norm 化」

文献の実像 (§4.3) に合わせて (a) を再定義する:
**enc_p = AdaLN(-Zero)、decoder = AdaIN、flow = §5.3 で別扱い**。

- **(a-1) enc_p AdaLN 化**: transformer 6 層 × 2 norm = 12 箇所の LayerNorm を
  条件付き化。γ/β は raw 192-d emb (または共有 128-d trunk) から低ランク射影、
  `(1+γ̂)` 形式 + zero-init (AdaLN-Zero / StyleTTS 2 と同思想)。
  - 効果根拠: AdaSpeech 4 encoder CLN −0.21 CMOS【文献】/ Meta-StyleSpeech
    acc +11pt【文献】/ VITS2 の「テキストに無い話者固有発音を text encoder
    条件付けで表現」の動機と同線
  - パラメータ: 共有 trunk 案で **+0.66M ≈ +1.3MB fp16**【推測】
  - ONNX: LayerNorm の γ/β を計算値に置換するだけ、export 影響なし【コード+推測】
  - リスク: 低。zero-init なら初期挙動は現行一致。M2 (加算) は残置 or 廃止を
    smoke A/B (加算と AdaLN の重複は SNAC 中和の相似形になり得る)
- **(a-2) decoder AdaIN 化 (per-resblock)**: 現行 3 点 FiLM を、StyleTTS 2 の
  実装テンプレート (`AdaIN → 活性 → Conv`、`(1+γ)·IN(x)+β`) どおり
  **各 resblock 内の conv 前**へ移す/追加する (medium: 2 段 × 3 resblock × 2 conv
  = 12 箇所)。
  - 効果根拠: StyleTTS concat→AdaIN CMOS +0.17 + 音響相関 0.19→0.91【文献】/
    StyleTTS-ZS の global style (AdaIN 経路) 除去で SIM 0.47→0.34【文献】
  - パラメータ: 192-d から直射影で **+0.45M ≈ +0.9MB**【推測】
  - リスク: 中。IN は発話内統計を消すため iSTFT head 直前段では位相・帯域の
    整合に副作用があり得る【推測】→ Phase D smoke で帯域指標 gate。
    SNAC 中和の観点 (§4.3) から、**flow 強化 (P4) と同時に盛らない**
    (D-3/D-4 の結果で入れる側を決める)

### 5.2 候補 (b): spk_proj 容量増 + 注入多重化 (FiLM 広帯域化)

- **(b-1) FiLM scale の開放 (P0-1)**: `sigmoid+0.5` → `1+γ̂` (無界、zero-init)。
  FiLM 原典が「γ の sigmoid/tanh 制限は劣化」を実証済み【文献】。
  実装は 2 行 + opt-in flag。**費用対効果が全候補中最良**。既存 ckpt と
  bit 非互換なので from-scratch / 明示 flag
- **(b-2) spk_proj の widening/deepening**: D-1 で rank collapse が出た場合のみ。
  情報は決定的 MLP を素通りするため、**単独では効かない公算大**【推測】。
  優先度低
- **(b-3) 注入点の追加増設** (resblock 単位 FiLM 等): (a-2) と同じ方向だが
  IN なしの素 FiLM。AdaIN との差は D-5 が decoder 律速を示した場合に
  smoke A/B で決める

### 5.3 候補 (c): flow の条件付け強化

現行 SNAC の時不変統計 2 本/段は 3 システム中最細 (§4.2-1)。選択肢 3 形式:

- **(c-1) T-Flow lite (HierSpeech++ 型)**: coupling の WN を小型 transformer
  block (hidden 96-192、1-2 block/段) + **AdaLN-Zero (g_spk 条件)** に置換。
  - 効果根拠: HierSpeech++ T-Flow で EER 7.50→4.86 (+14M)、Bi-Flow 併用で
    4.23【文献】。彼我のスケール差はあるが、類似度への主寄与が flow 側で
    出た唯一の統制 ablation
  - パラメータ: **WN 置換なら差し引き負にできる** (現行 flow WN ≈ 7M。
    hidden 96 の 1-block 置換で −4〜5M も可能)【推測】— 40MB gate 内で
    唯一「容量を増やしながらサイズを減らせる」候補
  - CPU RTF: self-attention O(T²h) だが T≈430 (5 秒) で WN の conv 積和と
    同オーダー【推測】→ Phase D で実測 gate
  - リスク: 高 (可逆性・logdet 配線・KL 安定性)。v10 M1 と同じ「単独・最後に
    投入」原則 + 可逆性 unit test + KL cap abort を踏襲
- **(c-2) 二重チャンネル (LNACont 型)**: SNAC (SN/SDN) を維持したまま
  WN の gin conditioning に **g_spk を再接続** (現行は g_lang のみ)。
  - 効果根拠: LNACont が「正規化 + WN gin」併用の公刊先例【文献】。
    YourTTS の高類似度も WN gin 形式
  - パラメータ: Conv1d(512→2·192·4)×4 段 = +3.1M (+6.3MB) は gate 超過 →
    **192-d 直結で +1.2M (+2.4MB)** に絞る【推測】
  - リスク: 中。SNAC の設計思想 (forward で話者除去) と WN 話者注入は
    理論上衝突し得る (SNAC 論文の中和と同型)【推測】— LNACont の実例が
    あるため一概に否定はできないが、**c-1 と排他で A/B**
  - 注意: LNACont は「LNAC 単独は逆効果、contrastive 併用が前提」【文献】—
    我々は cross-utt SupCon 維持が前提条件
- **(c-3) hyperconditioning (Blow/SC-CNN 型)**: g_spk から coupling 第 1 conv の
  kernel を生成。効果の文献値は最強クラス (spoofing +27pt)【文献】だが、
  動的 weight は ONNX/ORT 上 matmul 展開が必要で export 複雑度が高い
  (v10 で SC-CNN を「動的 conv が ORT 非適合」として不採用にした判断を維持)。
  **v11 では不採用、c-1/c-2 が不発だった場合の v12 候補**

### 5.4 候補 (d): reference encoder の多粒度化

- **契約内変種 ([1,192] → K learned token 展開 + cross-attention)**: 文献空白
  【文献 (不存在確認)】。系列版の利得 (+0.08〜0.11) は「192-d ボトルネックの
  迂回」に由来する可能性が高く、ボトルネック通過後の展開で再現する根拠なし。
  **不採用** (research arm としても優先度最下位)
- **【v12 で契約改定するなら】の隔離枠**: 参照 mel 系列を第 2 入力に取る
  (XTTS Perceiver 32 token / Mega-TTS 2 MRTE / SEF-VC)。文献実測
  SIM +0.08〜+0.11【文献】で、固定 192-d の構造上限 (方式ペナルティ
  0.06〜0.11、v10 調査 §3.2) を正面から解除する唯一の道。ONNX 入力追加 =
  全 7 ランタイム改修 + 契約 version bump が必要。**v11 では検討しない**。
  同枠に「joint style encoder への置換」(SNAC ablation で固定 encoder 敗北
  【文献】) も入る — こちらは speaker-encoder ONNX の差し替えで契約次元は
  保てるが、CAM++ 資産 (SCL/評価系) との整合再設計が要る

### 5.5 候補 (e): 注入オーケストレーション (追加候補)

SNAC 中和【文献】と YourTTS/HierSpeech++ の「decoder は入口 1 点」事実 (§4.2-2)
から、**「増やす」のではなく「配分し直す」**独立軸がある: 例えば
decoder FiLM を入口 1 点に減らし、その分 flow (c-1/c-2) に寄せる。
D-3/D-4 で現行の注入点別寄与と冗長性を測ってから、Phase D smoke で
「現行 ALL」vs「flow 重心」を A/B する。実装コストゼロ (flag の組合せ)。

### 比較表 (まとめ)

| 候補 | 文献の効果実測 | param (fp16) | ONNX 契約 | RTF | リスク | 判定 |
|---|---|---|---|---|---|---|
| (b-1) FiLM scale 開放 | FiLM 原典 (γ 制限は有害) | ±0 | 適合 | ±0 | 低 | **P0 で即採用** |
| (a-1) enc_p AdaLN | CLN 除去 −0.21 CMOS / acc +11pt | +1.3MB | 適合 | ≈0 | 低 | **P2 採用** |
| (a-2) dec AdaIN | concat→AdaIN +0.17 / SIM 0.34→0.47 (除去逆算) | +0.9MB | 適合 | ≈0 | 中 (帯域副作用) | **P3 条件付き採用** (D-5 分岐) |
| (c-1) T-Flow lite | EER 7.50→4.86 | **−3〜+1MB** (WN 置換) | 適合 | 要実測 | 高 (可逆性/KL) | **P4 第一候補** (D-6 分岐) |
| (c-2) WN gin 再接続 | LNACont 0.297→0.413 (cross、複合) | +2.4MB | 適合 | ≈0 | 中 (SNAC 中和) | P4 対抗 arm |
| (c-3) hyperconditioning | spoofing +27pt | +1MB 級 | ORT 非適合リスク | ? | 高 | v12 送り |
| (b-2) spk_proj 増強 | 直接根拠なし | +0.5MB | 適合 | ≈0 | 低 | D-1 陽性時のみ |
| (d) K-token 展開 | **文献空白** | +2MB 級 | 適合 | 小 | 高 (根拠なし) | 不採用 |
| (d') 参照系列入力 | SIM +0.08〜0.11 | +4MB 級 | **破壊** | 中 | — | **v12 隔離枠** |
| (e) 注入再配分 | SNAC Table I (ALL<FLOW) | ±0 | 適合 | ±0 | 低 | D-3/D-4 後に A/B |

## 6. oracle 追跡指標の Phase E 組込 (タスク 4)

**seen 話者 20 択識別 top-1** を v11 の中間評価 (5ep 毎) に常設する。

### プロトコル (事前固定、JSON で pin)

- 話者: §8 oracle と同一の seen 20 名 (moe-speech)。話者 ID + 参照発話 ID +
  centroid 用発話 ID (各 10、参照と非重複) を manifest 化
- 合成: 各話者 × 固定 3 文 (ja) = 60 発話。学習 instance の GPU 1 枚で
  torch infer (EMA 適用前の raw で統一 — EMA 差は終点評価で別掲)
- 測定 (CAM++ torch 資産流用):
  1. **raw top-1**: 実音声 centroid への最近傍
  2. **centered top-1**: synth 側は synth 平均、real 側は real 平均を引いた後の
     最近傍 (ドメインオフセット除去後の分離度)
  3. cond→synth 回帰傾き + 話者間広がり保持率 (§8 と同定義)
- 参考ベースライン【実測】: 実音声 98.5% / v10a-r2 ep69 = raw 43%・centered 73%

### コストと搭載可否

- 合成 60 発話 ≈ 1-2 分 (A100 1 枚) + CAM++ embedding + 集計 ≈ **合計 3-5 分/ckpt**
  【推測 — §8 oracle は CPU のみで 103 wav を処理できた実績があり、GPU なら
  余裕で 5ep 毎に載る】。既存の 5ep 毎中間評価 (R3 で常設済) への追加は
  wall-clock +5 分未満で許容
- 実装: `piper_train/tools/` に `eval_seen_speaker_id.py` を新設 (または
  eval harness にモード追加)。契約は
  [`docs/spec/zs-eval-contract.md`](../spec/zs-eval-contract.md) に追記

### 運用ルール (Goodhart 防止)

- **go/no-go ゲートには使わない** (判定は従来の 4 点セット: cross-utt SECS
  dual-encoder + 帯域 + 聴感)。本指標は**アーキ診断の追跡専用**
- 逆方向の早期シグナルとしては使える: 「ep20 時点で raw top-1 が v10b 系
  (43%) から +10pt 動いていなければ、条件付け改修は効いていない」= 早期
  打ち切り判断の補助【推測 — 閾値は v11 事前登録時に確定】
- **学習 loss への流用は恒久禁止** (frozen encoder 狙い撃ちの gaming 事例 4 件)

## 7. v11 推奨構成 (タスク 5)

### 7.1 優先順位リスト

| 優先 | 項目 | 予想効果 (根拠) | 費用 |
|---|---|---|---|
| **P0** (即、学習前) | (1) FiLM scale 開放 `1+γ̂` zero-init (b-1)、(2) EMA 対象を flow/enc_p へ拡張 (v10a R4)、(3) 変調統計テレメトリ常設 (D-2 と同項目を学習 log に) | 単独 SECS +0.00〜0.02【推測】+ 以降の全介入の土台 | 実装 0.5-1 日 |
| **P1** (学習前、$0) | 診断 D-1〜D-9 (§3) → 判定マトリクスで P2-P4 の重心決定 | 改修の誤投資防止 | ローカル 1-2 日 |
| **P2** | enc_p AdaLN 化 (a-1、12 norm、zero-init、低ランク trunk) | SECS +0.02〜0.04【推測、AdaSpeech 4 / Meta-StyleSpeech より外挿】 | 実装 1-2 日 / +1.3MB |
| **P3** | decoder per-resblock AdaIN 化 (a-2、StyleTTS 2 テンプレート) — D-5 が decoder 律速を示した場合は P2 より繰上げ | oracle top-1 の主改善候補【推測、StyleTTS Table VII より】 | 実装 1-2 日 / +0.9MB |
| **P4** | flow 強化: **c-1 T-Flow lite を第一候補**、c-2 (WN gin 再接続) を対抗 arm — D-6 の分岐で採否・形式決定。単独・最後に投入 (M1 の原則踏襲) | 類似度の主寄与になり得る (HierSpeech++ EER −2.6pt)【文献→推測】 | 実装 3-5 日 / −3〜+2.4MB |
| **P5** | 注入オーケストレーション A/B (e): 「現行 ALL」vs「decoder 1 点 + flow 重心」 | SNAC 中和が実在すれば無料で +α【推測】 | flag 組合せのみ |
| 別線 | S-2 F0 担体化 head (A3 の本修理、[`zero-shot-v10b-residual-noise-diagnosis.md`](zero-shot-v10b-residual-noise-diagnosis.md) §5-1) と trainable PQMF 除去 + 高域 GT 参照 loss は v10c/v11 で並走 (本 doc のスコープ外) | — | — |
| **v12 隔離** | 参照系列入力 (Perceiver/MRTE 型、契約改定必須) / joint style encoder / hyperconditioning (c-3) | SIM +0.08〜0.11【文献】 | 契約 bump + 7 ランタイム |

**予想合計効果【推測】**: in-domain zs_ja 0.60 → 0.65-0.70、seen top-1 43% →
70%+ (centered 90%+) を中間目標とする。文献に「この組合せで +0.10」を保証する
直接実測はない (最も近い統制実験は HierSpeech++ T-Flow と StyleTTS の形式
ablation)。0.70 必達は約束できず、**D 診断で主ボトルネックに改修を集中させる
ことが予想効果の前提条件**。

### 7.2 レシピ上の前提 (v10 からの継承)

- cross-utt SupCon + detach-z 維持 (LNACont の「正規化 coupling は分離損失と
  併用が前提」とも整合)。DINO 廃止・σ noise 0 維持
- swap-SCL cosine / frozen encoder 直接最適化 / 制約なし trainable filter は
  再導入しない (gaming 4 事例)
- 全介入は opt-in flag、default は v10b 挙動 (bit 互換)。ONNX [1,192] 不変

### 7.3 Phase D smoke での検証項目 (事前登録案)

1. **可逆性 unit test** (P4 採用時): `flow⁻¹(flow(z)) ≈ z` + logdet→KL 配線
   (M1 と同基準)。KL cap abort 有効
2. **grad-probe 較正**: speaker 系 loss = mel の 5-15% (v10 手順)
3. **変調テレメトリ**: FiLM/AdaLN γ の話者間 spread が smoke 中に単調成長する
   こと (ゼロ貼り付き = 条件未獲得の早期検知)、SNAC v ノルムの発散監視
   (v10a の 0.65→1.71 型)
4. **VRAM / sec/step**: 現行比 +15% 以内
5. **ONNX export**: FP16 ≤ 40MB + CPU RTF 現行比 +10% 以内 (T-Flow の
   attention 実測を含む) + parity テスト
6. **帯域 gate**: 4-9kHz + 6-11kHz ノイズ床 + comb-HNR (1-3kHz) が v10b 比
   非悪化 (P3 AdaIN の IN 副作用の検知)
7. **seen-ID ハーネスの疎通**: smoke ckpt で §6 の指標が計測できること
   (値は未収束で無意味、配線確認のみ)
8. Phase E で **FT vs zero-shot の comb-HNR gap** を追跡 (H-E 検証: 条件付け
   強化で ε 調波ロックが zero-shot でも獲得されるか)

## 8. リスク表

| リスク | 影響 | 緩和 |
|---|---|---|
| D 診断が「複合律速」を返し重心が絞れない | 改修の焦点喪失 | 判定マトリクスの中間行 (P0+P2+P3 同時 + P4 は smoke A/B) を事前定義済み |
| AdaIN の発話内統計除去が帯域/位相を乱す | がびがび再発 | Phase D 帯域 gate (7.3-6)。IN→LN 差し替え fallback (StyleTTS は AdaLN でも −0.21 止まり) |
| T-Flow の KL/可逆性事故 | 学習全損 | M1 の投入原則 (単独・最後・unit test・KL abort) を踏襲 |
| 注入点を増やして SNAC 中和を悪化させる | 効果相殺 | P5 の再配分 A/B + D-3/D-4 で事前に冗長性を測る |
| param 合計が 40MB gate 超過 | 配布サイズ契約違反 | c-1 の WN 置換で相殺 / 低ランク trunk / 採用候補の取捨は smoke 後 |
| 予想効果が文献外挿 (直接実測なし) | 0.70 未達 | §6 の top-1 を 5ep 毎追跡し ep20 で軌跡判定 → 早期打ち切り。「確実に似せる用途は FT が正道」の製品導線は不変 |

## 9. 出典

- 本 repo:
  [`zero-shot-v10b-quality-plan.md`](zero-shot-v10b-quality-plan.md) §8-10 /
  [`zero-shot-v10-design.md`](zero-shot-v10-design.md) /
  [`zero-shot-v10b-residual-noise-diagnosis.md`](zero-shot-v10b-residual-noise-diagnosis.md) /
  [`zero-shot-v10-similarity-research.md`](zero-shot-v10-similarity-research.md) /
  `src/python/piper_train/vits/{models,mb_istft,modules,lightning}.py`
- YourTTS: arXiv:2112.02418 (+erratum、Coqui TTS 実装: `vits.py` /
  `networks.py` / `wavenet.py` / `hifigan_generator.py`、d_vector 512-d、
  SECS は Resemblyzer で GT 0.824 / 合成 0.864)
- HierSpeech++: arXiv:2311.12454 (+公式実装 `hierspeechpp_speechsynthesizer.py` /
  `modules.py` DiTConVBlock — AdaLN-Zero は flow coupling 限定、
  Table IV: T-Flow 除去 EER 4.86→7.50)
- SNAC: arXiv:2211.16866 (Table I: +FLOW 0.352 > +ALL 0.320、joint GST >
  固定 H/ASP) / LNACont: EUSIPCO 2024 proceedings pp.391-395 (arXiv なし)
- StyleTTS: arXiv:2205.15439 (Table VII/VIII) / StyleTTS 2: arXiv:2306.07691
  (+公式実装 AdainResBlk1d、style_dim=128) / StyleTTS-ZS: arXiv:2409.10058
- AdaSpeech: arXiv:2103.00993 / AdaSpeech 4: arXiv:2204.00436 /
  Meta-StyleSpeech: arXiv:2106.03153 / Grad-StyleSpeech: arXiv:2211.09383
- DiT (AdaLN-Zero): arXiv:2212.09748 / PixArt-α (adaLN-single 共有):
  arXiv:2310.00426 / FiLM: arXiv:1709.07871 / Attention Beats Concatenation:
  arXiv:2209.10684
- Blow (hyperconditioning): arXiv:1906.00794 / SC-CNN: IEEE SPL vol.30 (2023)、
  IEEE 10129023 (arXiv なし) / FreeVC: arXiv:2210.15418 / OpenVoice:
  arXiv:2312.01479 / VITS2: arXiv:2307.16430
- 多粒度 (v12 隔離枠): Mega-TTS 2: arXiv:2307.07218 / Attentron:
  arXiv:2005.08484 / SEF-VC: arXiv:2312.08676 / XTTS: arXiv:2406.04904 /
  PFluxTTS: arXiv:2602.04160

## 10. Phase 0 診断結果 — 律速点の一意化 (2026-08-20、D-1〜D-9 完了)

> **Status**: §3 の診断 9 本を完了、§3 末尾の判定マトリクス (事前登録) を適用して
> 律速点を確定した。対象 ckpt: **v10b ep79** (`checkpoints-v10b/epoch=79-step=106880.ckpt`、
> state_dict 704/704 検証、EMA 非適用 = oracle §8 と同条件)。4 独立ハーネス全てが
> v10a-r2 ep69 の既知アンカー (raw top-1 43% / synth-real cos 0.814) を数値一致で
> 再現してから測定【実測】。D-3 の infer() 再実装は `gen.infer` と bit 一致を確認済。

### 10.1 チェーン会計 — 話者情報はどこで死ぬか【実測】

20 択 seen 話者識別 (raw top-1) の段別追跡:

```
CAM++ emb 98.5% → (spk_proj) → g_spk 98.5%     [D-1: 落ち 0]
  → (enc_p / MAS) → m_p 99% → z_p 97%           [D-8: 落ち 0、ただし振幅は微小 (sep 0.034)]
  → (flow⁻¹ SNAC) → z 78% (centered 93%)        [D-8: 情報破壊なし]
  → (decoder 描画 → wav → CAM++) → 39-40%       [−60pt がここに全集中]
       うち合成音共通ドメインオフセット: ~41pt   (centered で 80-83% まで回復)
       うち per-speaker 描画歪み:        ~19pt   (98.5 → 80)
```

SECS 会計 (D-5 lite、つくよみ OOD、cross-utt 中央値):

```
GT 実音声 0.859 → teacher-forced recon (enc_q z + 現行 decoder) 0.714   [decoder 段 −0.145 = 78%]
  → TTS フルパス 0.673                                                   [prior/flow/duration 上流 −0.041 = 22%]
```

**recon bound (本診断の最重要数値)**: 実音声由来の posterior z (= flow/prior を
完璧にした場合の上界) を現行 decoder に入れても cross-utt SECS 0.714 /
NTR 0.135 (ja 女性 floor 0.689 すれすれ) にしか届かない【実測】。
= **decoder を直さない限り、上流 (P2/P4) の完璧化による利得は +0.04 が上限**。
一方 D-9 のオフセット除去上限は +0.13 (0.607→0.737、ceiling 0.797)。
なお合成音を enc_q→dec に往復させるとほぼ無損失 (roundtrip cos 0.969、top-1 不変)
— enc_q→dec の往復自体は壊れておらず、**実音声由来の z を decoder が自分の
「合成ドメイン」へ写像する時に話者性が潰れる**【実測+解釈】。

### 10.2 各診断の要点

| 診断 | 結果 | 判定 |
|---|---|---|
| D-1 spk_proj | g_spk raw top-1 98.5%、Fisher 比 1.35→1.98 (増加)、rank collapse なし | **シロ**。(b-2) 棄却 |
| D-2 テレメトリ | FiLM scale が sigmoid 上限に飽和 (max 0.4998)、変調の 8-9 割は話者共通の固定変換 (話者依存分 10-16%)。sn_v 話者間 std ~4% (死亡)。cos(g_spk, g_lang) = **−0.56** (spk_proj が lang 打ち消しに容量消費)。lang/spk ノルム比 1.56 | P0-1 の直接傍証 + lang 干渉という新規論点 |
| D-3 LOO | Δtop-1: **dec FiLM −0.233 ≧ enc_p −0.217** ≫ DP −0.033 > SNAC −0.017。dec 内は s1 (128ch) 0.150 ≫ s2 0.067 > 入口 0.033 | 実効キャリアは dec+enc_p の 2 点のみ。入口 FiLM は最弱 |
| D-4 isolation | pair_dec_encp = base の 92% (cross gain 95%) を回収。iso_flow / iso_dp = chance。ISO 和 (0.20) ≪ pair (0.317) = **dec と enc_p は相補・超加法的** | SNAC 中和 実在 (推論時分解として)。P2+P3 同時投入を支持 |
| D-5 lite | recon NTR 0.135 / recon−TTS 差 +0.04 のみ / autoencode (合成入力) は無損失 0.969 | **decoder 描画不足が律速に含まれる** (proxy 測定、10.4 の限定参照) |
| D-6 VC oracle | VC raw **17%** ≪ TTS 42.5% (同 ckpt)。identity-VC 0.755 vs cross-target leak 0.729 → **g 差し替えの実効注入振幅 0.026 ≈ 0**。予測は source 近傍 6 話者に崩壊 | **flow⁻¹ は音色を注入できていない** (現状の均衡で寄与ゼロ) |
| D-7 gain 外挿 | 入力マージン +44% に対し出力 separation +2% (平坦)、SECS は単調悪化 (7/10 話者)。α は応急ノブに**ならない** | **ゲイン不足を棄却** — 形式・容量問題 |
| D-8 probe | m_p 99% (sep 0.034 = 存在するが薄い) / z 78% (centered 93%) | 情報破壊なし。ただし「存在 ≠ 使用」(10.3-1) |
| D-9 offset | v10b raw 39% / centered 80% / translated 56%。SECS 0.607 → translated 0.737 (ceiling 0.797)。offset は剛体平行移動 1 本ではなく per-speaker 歪み残存 | オフセット除去 = +0.13 SECS の頭金 (H 系の射程)。**Δ 検出は centered 指標を主指標に** |

### 10.3 敵対的検証で解消した見かけの矛盾

1. **D-8「z まで生きている」vs D-4「iso_flow = chance」**: 矛盾ではない。SNAC sn_m
   の時不変シフトは z 上の probe には見える (separation ×10) が、decoder はそれを
   音色として描画しない。D-2 の「SNAC が最も話者差を運搬」も入力側分散の話であり
   出力効果とは別物。**教訓: 変調テレメトリの分散量を効果と読み替えない**
   (Phase E テレメトリは LOO 型 probe と対で解釈する)。
2. **D-7 α=3.0 の top-1 +0.10**: n=20 で ±2 サンプル内のノイズ。separation 平坦 +
   SECS 単調悪化が実体で、「飽和」判定が正しい。
3. **baseline 群 (43/39/40/42.5/30%)**: プロトコル差 (話者数×文数×conditioning) で
   全て整合。TTS-A 30% の低さは単発 emb conditioning 由来 → 10.6-1 の所見に転化。
4. **「dec FiLM は最大キャリア」と「decoder が律速」の両立**: dec は話者性が
   入る場所でも死ぬ場所でもある — 通り抜けた僅かな情報の最大搬送者が dec FiLM で、
   かつ描画段が最大損失点。P3 はこの同一段を狙う。

### 10.4 判定マトリクスの適用 (§3 事前登録)

- **D-6 = 低 (17% ≤ 55%) 確定**。行 2 (P4 主軸) の前提「D-5 高」は不成立。
- **D-5 = 低い側** — ただし proxy (OOD 1 話者 SECS ベース、seen recon top-1 は
  GT wav 不在で未測定)。独立 3 系統 (D-5 lite recon / D-6 identity-VC /
  D-9 offset) が全て decoder 段を指すため判定は頑健と評価するが、
  **seen recon top-1 の本測定を実装フェーズ冒頭 (GT wav のある instance 上) で
  追試して確認する** (~30 分、判定を覆す場合は本節を改訂)。
- **D-7 陰性** → 行 4 の「ゲイン問題」枝を棄却。

**確定判定: 行 3 (decoder 描画不足 → P3 繰上げ) を主、行 4 の複合処方
(P0+P2+P3 同時、P4 は Phase D A/B) を併用。**
律速比率: decoder 段 ~78% (SECS 会計) — うちドメインオフセット分は H 系の射程、
per-speaker 描画分が P3 の射程。prior 彫刻 ~22% (P2、dec と超加法)。
flow の推論時寄与 0% (P4 は「強化」ではなく Phase D A/B)。ゲイン不足 0% (棄却)。

### 10.5 P アーム採否 (確定) と §7 優先順位の改訂

| アーム | 採否 | Phase 0 根拠 | §7 からの変更 |
|---|---|---|---|
| P0-1 FiLM scale 開放 | **採用** | D-2 飽和貼り付き (直接傍証) | 変更なし |
| P0-4 (新規) lang/spk 干渉の設計検討 | 検討 | cos(g_spk,g_lang) −0.56、lang/spk 1.56 | 新規: g_lang の注入分離 or 直交化を P2 実装時に併せて検討 |
| P2 enc_p AdaLN | **採用** | LOO −0.217 / dec と相補。単独上限 +0.04 (recon bound) | P3 と同時投入が条件 |
| P3 dec per-resblock AdaIN | **採用・最優先** | 律速の主座 (78%)。**s1 (中解像度) 重心**で設計 (LOO: s1 ≫ s2 > 入口) | P2 より繰上げ (マトリクス行 3)。帯域 gate 必須 |
| P4 flow 強化 | **Phase D A/B に降格** | 現状寄与 0 だが recon bound により P3 前の投資は無効。実施時は **c-1 T-Flow lite + SNAC 除去のセット arm**。c-2 は fallback に降格 | 「D-6 分岐で主軸」→「P3/P2 後の A/B」へ |
| P5 注入再配分 | **採用 (再定義)** | SNAC 除去 = 無害軽量化 (LOO −0.017、−394k param)。**当初案「dec 1 点 + flow 重心」は廃案** (入口 FiLM 最弱の実測が反証)。DP head 残置 (centered −0.133 の実寄与) | A/B から「SNAC 除去 flag」へ縮退 |
| (b-2) spk_proj 増強 | **不採用確定** | D-1 シロ | 事前登録どおり |

**期待効果の改訂【推測】**: conditioning 改修 (P0+P2+P3) の射程は per-speaker
描画分 (~19pt top-1 / SECS +0.04〜) + 形式改善による均衡シフト。
ドメインオフセット分 (+0.13 SECS 上限) は H 系 (decoder 実音声化) の射程で
本 doc のスコープ外 — **§7 の「0.60→0.65-0.70」のうち 0.70 到達には H 系の
並走が必要**という条件を明示する。

### 10.6 副次所見 (学習不要の改善・評価プロトコル改訂)

1. **参照 centroid conditioning**: 単発 emb → 話者 centroid で raw 30→42.5% /
   centered 67.5→82.5%【実測】。学習不要の推論時レシピとして採用し、評価
   manifest にも pin する (§6 ハーネスは centroid 条件で統一)。
2. **α 外挿はノブにならない** (D-7: 単調悪化) — §3 D-7 の「応急改善ノブ」候補は棄却。
3. **Δ 検出の主指標は centered top-1 / centered separation** (D-9: raw は共通
   オフセット変動に埋もれる)。v10b ep79 の pin 値: 20spk×3文 protocol で
   raw 0.400 / centered 0.833 / separation 0.1147 / cross-SECS mean 0.588。
4. Phase E テレメトリには変調の**話者依存分散比** (D-2 定義) を含める — 総量
   だけでは死荷重 (SNAC 型) を検知できない (10.3-1)。

### 10.7 成果物 (ローカル scratchpad、要アーカイブ)

`.../scratchpad/v11_phase0/` 配下: `d_probes/` (D-1/2/8/9 + 合成 100 wav) /
`d3_d4_injection/` (18 arm 1,080 wav + bit-parity 検証) / `d6_vc_oracle/` (185 wav) /
`d7_gain/` + `d5_lite/`。スクリプト・JSON 生値・wav 全数を含む。session temp のため
**HF `diag-phase0-v11/` への退避を実装フェーズ開始前に実施** (v10 の diag 慣行踏襲)。

**限定事項**: CAM++ 単独判定 (診断用途、学習未使用のため指標汚染なし) / ja のみ /
seen 20 話者 (D-5 lite・D-6 anchor は OOD つくよみ) / 推論時分解であり再学習後の
各点容量とは別物 (SNAC「FLOW のみで学習すれば強いか」は未解決のまま P4 A/B に持越)。
