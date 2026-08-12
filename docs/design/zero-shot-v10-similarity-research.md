# piper-plus zero-shot 話者類似度改善 — 最終研究レポート

> **Status**: deep research 完了 (13 エージェント: コード監査 3 + 文献 4 + 提案 1 + 敵対的検証 4 + 統合 1)。
> 発端と実測の canonical は [zero-shot-speaker-similarity-root-cause.md](zero-shot-speaker-similarity-root-cause.md)。
> 本書は機構の結論・文献比較・検証済み介入候補・ロードマップを収める。


作成日: 2026-08-13 / 対象: v8 → v8.1 → v9 系 zero-shot TTS (`feat/zero-shot-v8-dataset-scaling`) / 調査体制: コード監査 3 系統 (C1/C2/C3) + 文献調査 4 系統 (L1/L2/L3/L4) + 介入候補 4 件の実装検証

---

## 1. エグゼクティブサマリ

v9 の SECS 退行 (zs_ja 0.712→0.652【実測 2026-08-12】) はデータでは説明できず (ja データは v8.1 と実質同一)、**MRD + full-band STFT 追加による SCL 勾配希釈と学習スケジュール非対称の複合**が主因 — ~$100 の 3-arm warm restart 診断で分離可能。一方 v8.1 でも転写率 ~0.4 で頭打ちの「上限」は、**SCL の same-utterance 正例・SCL 勾配が推論経路 (enc_p/flow) に届かない posterior leak・σ=0.05 の embedding blur** という学習信号の構造欠陥が主因で、いずれも ONNX 契約を壊さず修正可能。文献上 global-embedding 方式は死んでおらず (YourTTS 0.864 / HierSpeech++ 0.907)、GT-ceiling 正規化比で v8.1 は VALL-E 2 級 — ただし転写率 ~1.0 は prompt 系のみの領域で、[1,192] 契約下の現実目標は cross-utt SECS 0.80 前後、確実に似せる用途は FT が正道 (v7 実績 0.775)。推奨ロードマップ: 診断 (~$150-230) → 短期回収 v9.1 (~$100-150) → v10 本格 (構造 + データ、~$300-600)、総額 ~$550-980 で予算内。

---

## 2. 機構の結論 — 3 仮説の評価

### 2.1 仮説 1: loss バランス (MRD + full-band STFT が SCL を押し負けた) — **部分支持。v9 退行の第一容疑だが、スケジュール交絡と未分離**

**支持する事実:**
- 【実測】v8.1→v9 の ja 学習データは実質同一 (案 Z ゲートで ja は 99% 残存、削減の主体は Zeroth-ko 全除外)。同一データで zs_ja 0.712→0.652 / つくよみ 0.777→0.73 の退行が起きた以上、消去法でデータ仮説は退行の説明から除外される (C3 b-1、root-cause doc §5.6-5.7)。
- 【コード】希釈の機構は実在する: 全 loss は単一の `loss_gen_all` に加算され (lightning.py:1168-1352)、global grad-norm clip 1.0 (lightning.py:933) がノルム予算を再配分するため、v9 新設の MRD feature-matching (均衡が存在せず勾配を出し続ける) + full-band STFT が予算を消費した分だけ SCL の実効 LR が比例縮小する (C2 finding 3)。
- 【文献】YourTTS は SCL と音質のトレードオフを明記 (arXiv:2112.02418)、Cho+ 2023 は「VITS 系 zero-shot は loss バランスで性能が劇的に変わる」と明示 (arXiv:2305.16699)。がびがび解消と SECS 退行の同時発生はこの綱引きモデルと整合 (L3/L4)。

**留保 (重要):**
- 【コード】loss 値ベースの SCL シェア低下は ~1.5%→~1.2% と小さく、値シェアだけでは -0.06 を説明しにくい (C2 finding 2)。本体は勾配ノルム比であり、これは未計測。
- 【交絡・推測】最大の交絡は学習スケジュール非対称: v8.1 は累積 120ep 上の warm restart で SCL が 40ep フルに効いたのに対し、v9 は from scratch 50ep で序盤 ~10ep は SCL 勾配が実質無意味、かつ cosine LR が終盤 1e-5 に枯渇。ep49 の「飽和」(0.735→0.725) は LR 減衰と時期が一致し、**「学習不足説の棄却」は LR 一定条件下でしか成立しない** (C2 finding 5)。前提資料の「学習不足説は棄却」は再考が必要。

**寄与度の見立て【推測】:** v9 退行 (-0.05〜-0.06) のほぼ全てが「希釈 + スケジュール」の複合。両者の split は 3-arm warm restart (§4 Tier A) で一意に決着する。上限 (転写率 0.2-0.4) への寄与は小。

### 2.2 仮説 2: データ話者多様性 — **退行の説明としては棄却。上限側の「ドメイン被覆」要因として部分支持**

**退行については棄却【実測ベース】:** 上記の通り ja データは v8.1/v9 で実質同一。また v7 (ja 20 話者) → v8 (3,692 話者) で unknown-ja SECS は 0.688→0.649 と改善しなかった実測もあり (v8-plan §3.15、SCL 勾配ゼロ時代の比較という留保付き)、「話者数の素朴なスケーリング」は既に効かないことが示されている。

**上限については部分支持:**
- 【実測】v8.1 の in-domain holdout (moe-speech 学習除外話者) は 0.7117 で GT 天井 0.7183 の **99%** に到達済み (v8-plan §3.16) — 同ドメイン未知話者への汎化は 473 話者で実用上飽和しており、律速は「数」ではなく「ドメイン被覆」(C3 b-3)。
- 【実測】v9 つくよみ SECS 0.73 ≈ ja 女性 floor (0.69-0.74) — 出力が「学習分布の ja 平均女性声」に回帰している描像と整合 (C1/C3)。ja 学習データはゲーム演技声・若年女性偏重の単一ドメイン (moe-speech 473 話者) で、スタジオ朗読 (つくよみ型) は分布外。
- 【文献】Emilia の規模統制実験でドメイン一致だけで S-SIM ±0.03-0.07 (arXiv:2501.15907 Table V)。YourTTS ablation では話者 11 倍追加の利得が「追加ドメイン +0.078 / 既存ドメイン -0.012」と非対称 (arXiv:2112.02418)。Audiobox ではドメイン多様性の利得が OOD ターゲットに集中 (+0.04〜0.06、arXiv:2312.15821 Table 3)。

**寄与度の見立て【推測】:** 退行には寄与ゼロ。上限のうち「OOD 参照 (つくよみ型) への転写の弱さ」の中程度の部分を規定。対処は話者数ではなくドメイン軸 (スタジオ朗読・マイク読み上げ・属性多様性) の追加。

### 2.3 仮説 3: 構造上限 (global-g 加算条件付け) — **上限側の主因と評価。ただし「アーキテクチャの容量」より先に「学習信号の構造欠陥」**

コード監査 (C1) で、アーキテクチャ以前の学習信号レベルの欠陥が 3 点特定された。いずれも【コードで確認済の事実】:

1. **SCL の正例が same-utterance** (losses.py:133-140): cross-utterance 不変性を要求する損失が学習全体に存在しない。samples_per_speaker=4 で batch 内に必ずある同一話者の別発話 3 件は負例から除外されるだけ。same-utt SECS 0.775 誤報 (Goodhart) と cross-utt 0.73 の乖離、20 発話平均でも +0.035 しか改善しない事実と機構的に一対一対応。
2. **SCL 勾配が推論経路に届かない (posterior leak)**: 学習時 y_hat は posterior z (GT 音声由来) から生成されるため (models.py:1110/1167-1170)、SCL 勾配は dec/enc_q/g にのみ流れ、推論時に話者を運ぶ enc_p の g-cond と flow reverse には一切届かない — これらは KL loss のみで学習される。decoder は g を使わずとも z から音色を読んで SCL を満たせる (最小抵抗経路)。v8.1 の転写率 ~0.4 頭打ちの機構的説明。
3. **spk_emb_noise σ=0.05 は過大**: 192 次元で cos(clean, noised)=0.822【torch 実測】— 同一話者 cross-utt 変動 (ceiling 0.888 = 27°) を超える 34.8° の blur。モデルは cos ~0.82 球内の embedding を実質同一視するよう訓練される。

加えて条件付け容量の細さ【コード確認】: enc_p への g は全時刻一様 bias 1 本、flow は shift-only coupling (mean_only=True) 4 段、dec FiLM は時間一定 gain∈[0.5,1.5]。g = spk_proj + lang_emb の加算共有では init 時 lang_emb ノルムが spk_proj 出力の 2.7 倍【torch 実測 8.46 vs 22.4、学習後は未検証】。

【文献】global vs cross-attention の直接 ablation では 0.06-0.11 SECS の方式ペナルティ (SEF-VC 0.711 vs 0.825、Mega-TTS 2 0.841 vs 0.905)。ただし global vector でも注入方式次第で YourTTS 0.864 / HierSpeech++ 0.907 (63M) に到達しており、方式そのものは死んでいない。一方、GT 同等 (転写率 ~1.0) を報告した系は例外なく「参照音響系列そのもの」を見せる prompt/masked-infilling 系のみで、[1,192] 圧縮系での報告例は確認できない — **転写率 1.0 は現契約では構造的に届かない**のは事実として受け入れるべき (L1)。

**寄与度の見立て【推測】:** 上限 (0.73-0.78 плато) の主因。ただし内訳は「アーキテクチャの容量不足」より「学習信号の欠陥 (1)(2)(3)」が先で、これらは学習時のみの変更で修正可能。容量増強 (SNAC/AdaLN) は学習信号を直した後でなければ z-leak に吸われる公算が大きい (C1)。

### 2.4 総括表

| 現象 | 仮説 1 (loss) | 仮説 2 (データ) | 仮説 3 (構造) |
|---|---|---|---|
| v9 退行 (-0.06) | **主因** (スケジュール交絡込、3-arm で分離) | 棄却 (ja データ同一) | 小 |
| 上限 (転写率 0.2-0.4) | 小 | 中 (ドメイン被覆) | **主因** (学習信号 > 容量) |
| 韻律平板 (聴感) | — | 小 | 中 (DP の g detach + CAM++ が韻律情報を持たない、C1 finding 9) |

---

## 3. 文献から見た我々の立ち位置

### 3.1 SECS の絶対値は論文間比較不能 — 正規化比では v8.1 は SOTA 級

測定 encoder が異なるため絶対値は比較できない (XTTS は ECAPA2 測定で en 0.64、VALL-E 2 は WavLM-TDNN 測定で 0.687 など)。**GT-ceiling 正規化比**で見ると:

| システム | 条件 | SIM / ceiling | 比率 |
|---|---|---|---|
| VALL-E 2 (arXiv:2406.05370) | LibriSpeech test-clean | 0.687 / 0.779 | 0.88 |
| VALL-E 2 | VCTK 3s prompt (OOD 寄り) | 0.508 / 0.623 | 0.815 |
| **piper v8.1** | つくよみ cross-utt【実測】 | 0.777 / 0.888 | **0.875** |
| **piper v9** | 同上 | 0.73 / 0.888 | 0.82 |

v8.1 の比率は VALL-E 2 の test-clean と同水準、v9 の退行は VALL-E 2 の OOD 条件相当への「実退行」。cross-utt + ceiling/floor 併記という我々の評価プロトコルは文献ベストプラクティスと一致しており継続すべき (L1)。

### 3.2 global-embedding 方式の上限

- 方式ペナルティは実測 0.06-0.11 SECS (SEF-VC arXiv:2312.08676 / Mega-TTS 2 arXiv:2307.07218)。
- ただし注入方式の工夫で global vector のまま YourTTS 0.864 (flow coupling 含む全モジュール注入 + SCL α=9)、HierSpeech++ 0.907 (AdaLN-Zero、推論 63M) に到達 — **方式より「どこに・どの形式で」注入するかと損失バランスが支配的** (L1)。
- SNAC (arXiv:2211.16866) は coupling 層内の明示正規化/逆正規化で未知話者転写を改善した直接研究で、ONNX graph 内部変更のみで導入可能。
- 参照情報量のスケーリングは飽和する: Mega-TTS 2 で参照 100 倍にして +0.034、我々の 20 発話平均 +0.035【実測】は文献パターンの正確な再現 — 参照側への追加投資は回収不能。

### 3.3 SOTA との差と製品戦略

- FP16 38MB・CPU リアルタイムで zero-shot をやる公開システムは 2026 年時点で piper-plus 以外に確認できず、最軽量競合でも HierSpeech++ 63M+107M、他は 0.4-0.5B (L1)。他所のレシピの直輸入は不可能で、輸入可能な要素技術は SNAC/AdaLN・flow 専任 timbre 変換 (OpenVoice)・SCL 重み/スケジュールに限られる。
- ZeSTA (arXiv:2603.04219) の測定では SOTA ZS-TTS ですら実データ FT 基準に 0.04-0.07 届かない — **「特定話者を確実に似せる用途は FT が正道」という現結論は文献的に正しい** (v7 つくよみ FT 0.775 が製品導線)。
- 現実的な目標設定: v9.1 で v8.1 水準 (0.712/0.777) 回復、v10 で cross-utt SECS 0.80 前後 (正規化転写率 ~0.5-0.6)。それ以上を zero-shot で狙うのは非現実的。

### 3.4 軽量制約下でのベストプラクティス (文献の一致点)

1. SCL は「品質土台ができてから遅延導入 + 勾配ノルム整合」(YourTTS fine-tune 段のみ / DMOSpeech λ warmup 5k iter)。話者系 loss を先に強くする成功報告は不在 (L2)。
2. 正例は別発話 (SV 学習の GE2E 以降の標準)。same-utt 最適化の Goodhart は DMOSpeech (SIM が GT 超え) で明示報告済み。
3. 評価 encoder は学習 encoder と分離 (SV 最強 encoder が知覚類似最良とは限らない、arXiv:2506.20190)。
4. データは量よりドメイン被覆 (Emilia / YourTTS / Audiobox、§2.2)。
5. utterance-level embedding は話者以外 (言語・パラ言語) を漏らし韻律を害する (CosyVoice 2 が embedding を意図的に削除、arXiv:2412.10117)。

---

## 4. 検証済み介入候補 (優先度順、3 段構成)

介入候補 9 件のうち上位 4 件に実装検証 (ONNX 影響・ランタイム影響・コスト・リスクの監査) を実施。**4 件全てが「条件付き採用 (conditional)」判定**。全候補が speaker_embedding [1,192] / 出力 [B,1,T] の契約・7 ランタイム無改修・CPU RTF 不変をコードレベルで確認済み。

### Tier A: 診断実験 (即実行、v10 投資判断の前提)

#### A-1. 診断・評価基盤の整備【候補 2、検証済: conditional】
- **内容**: (a) 第 2 speaker encoder による SECS 並走 (Goodhart 検知器)、(b) ckpt 診断スクリプト (spk_proj/emb_lang/FiLM ノルム + FiLM 変調差 + z_p speaker probing + VC-SECS)、(c) per-loss 勾配ノルム logging、(d) スタジオドメイン holdout 常設。
- **検証で判明した要修正点**: 「repo 同梱 ECAPA (256d)」の**学習済み重みは存在しない** (manifest で publish_status="pending") — SpeechBrain spkrec-ecapa-voxceleb (Apache-2.0) 等の off-the-shelf を ONNX 化して pin する方式に差し替え必須。ECAPA と CAM++ の cosine スケールは非互換のため、生 SECS 乖離ではなく **per-encoder ceiling/floor 正規化転写率**で比較する。VC-SECS はハーネスが legacy sid ベースで zero-shot ckpt では動かないため、embedding ベース改修 + 既知話者サニティを先に通す。JVS は評価専用ローカル利用に限定 (HF 評価再現セットに upload しない)。
- **効果**: SECS 直接改善ゼロだが、lang 支配 / FiLM 起き具合 / 希釈仮説が定量決着し、以降全実験の誤 go を排除。第 2 encoder は SCL への組み込みを恒久禁止 (held-out ルール)。
- **コスト**: 実装 2-3 人日 + GPU <$50。ckpt ノルム/FiLM/probing はローカル即日。

#### A-2. 3-arm (+1) warm restart 診断【候補 3、検証済: conditional】
- **内容**: v9 ep49 から `--resume-weights-only` (v8→v8.1 で実走前例あり) で 8ep × 4 arm を同一 4x A100 で逐次実行: **Arm A** = 係数据え置き + fresh cosine (control) / **Arm B** = c_spk 2.0 / **Arm C** = c_mrd 0.5 + c_full_stft 0.25 / **Arm D** = spk_emb_noise σ 0.01 (候補 4 同乗)。
- **検証で判明した必須条件**:
  - 全 arm に `--lr-warmup-epochs 0` `--kl-annealing-epochs 0` を明示 (warmup default 5 のまま 8ep run すると 5/8 が LR ランプで消え全 arm 偽陰性化 — lightning.py:1704-1717 で確認済)。
  - v9 の全 architecture フラグ (`--use-mrd`、`--c-full-stft`、`--segment-size 16384`、WavLM、disc fp32) + `--speaker-encoder-torch-path` を再指定し、launch 直後に missing/unexpected keys ログを目視 (strict=False load は silent drop する — missing に `model_d_mrd.*` / `scl_encoder.*` が出たら即中断)。
  - arm ごとに output dir 分離 + onstart 自動レジューム無効化 (v9 launch 事故の再発防止)。
  - 判定閾値の事前登録: zs_ja +0.02 未満は「効果なし」、ep4/ep8 の 2 点で単調性確認。Arm B は ECAPA 第 2 SECS で CAM++↑/ECAPA→ を棄却 gate に、Arm C は平均スペクトル目視 + 聴感を gate に (がびがび再発 arm は SECS が良くても不採用)。
- **判定マトリクス (修正版)**: A のみで回収 → スケジュール問題 (継続学習で回収) / B↑かつC↑ → 希釈確定 (リバランスで回収) / 全 arm 平坦 → 「この dose では不十分」まで — **構造上限と即断せず**、最良 arm の 16ep 延長 (+$25) を挟む。
- **コスト**: 現実総額 **$80-120** (学習実費 ~$67 + instance セットアップ/HF データ復元/中間評価。当初見積 $60 は過小)。Arm D 込みで +$25-30。約 2 日。

#### A-3. DINO の view 分離または廃止【候補 9、未検証・低リスク】
- 現 DINO は student/teacher が同一入力で augmentation 不変性を学ばない EMA 自己蒸留に退化 (lightning.py:1262-1264【コード確認】)。**c_dino チューニングによる SECS 改善は C1/C2/L2 の 3 調査が独立に棄却** — 探索方向として閉じる。resume run に数行で同乗可 (student = 別発話 embedding 化、または c_dino=0)。全廃時は spk_proj ノルム監視を残す。

### Tier B: 短期 (v9.1 — 診断結果を受けて、上限突破の第一手)

#### B-1. SCL InfoNCE の cross-utterance 正例化【候補 1、検証済: conditional、最有力】
- **内容**: losses.py の labels/mask を同一話者・別発話 index に再配線 (SupCon 形式 ~15-20 行 + unit test)。batch 内に別発話 3 件が既に存在するためデータ変更不要。学習目的関数が評価指標 (cross-utt SECS) と初めて整合し、same-utt Goodhart の構造原因を除去。
- **検証で判明した必須条件**:
  - **単一変数 A/B**: 初回は loss 再配線のみ。all_gather 負例拡張・言語内 InfoNCE・conditioning 別発話化は同梱しない (第 2 段へ)。
  - **対照 arm 必須**: v9 ep49 から同 epoch 数の loss 不変 resume を並走 (SECS は ±0.01/ep 揺れるため対照なしで +0.03 は判定不能)。
  - **実装 footgun**: 対角 (same-utt) を負例化すると自 conditioning embedding から遠ざける破壊的挙動 — 分母から除外 (neutral) が必須、回帰テストで固定。
  - **期待値の修正**: これは **v9 退行の是正策ではなく上限突破策** (same-utt 設計は v8.1/v9 共通で退行を説明しない)。判定は事前登録基準 (例: zs_ja ≥0.68 かつ つくよみ ≥0.75 で go)、same-utt SECS は判定に使用禁止。帯域スペクトル検査でがびがび再発を gate。
- **期待効果【推測】**: cross-utt SECS +0.03〜0.06 (直接の文献数値なし、resume A/B で即白黒)。
- **コスト**: 実装 0.5 日 + **$60-100** (介入 arm + 対照 arm + データ復元。当初 $20-40 は過小)。

#### B-2. spk_emb_noise σ 縮小の本採用判断【候補 4、検証済: conditional】
- Arm D (Tier A) の結果を受けて判断。**σ=0.05 は v8.1/v9 共通のため退行原因ではない** — 天井解除の screening と位置付ける。判定は「σ=0.01 arm が control を cross-utt SECS で +0.015 以上上回るか」。
- **新規リスク (検証で特定)**: σ=0.01 の blur (7.9°) は話者内変動 (27.4°) を大きく下回るため、utterance 固有成分 (チャネル/韻律) まで解像する utterance-level overfit の新チャネルが開く — same-utt/cross-utt gap を新規に監視し、gap 拡大時は B-1 との同時投入に切替。予算が許せば σ=0.03 (話者内変動と同スケール、cos 0.888) の中間 arm (+$25-30) が v10 の Latent Filling 設計の事前情報として有価値。
- DINO との依存は無し (現状も view 差が実質存在しないため、σ 縮小で DINO は崩壊しない — A-3 を待たず投入可)。

#### B-3. z_slice.detach() の先行投入【候補 6 の (i)、未検証・低リスク】
- SCL 計算時に z_slice を detach し、decoder が posterior z から話者を読む逃げ道を遮断 (数行)。posterior leak (§2.3) への最小対処として B-1 の第 2 段 arm に同乗可。cycle SCL (prior 経路生成 + SCL) は step 時間 +10-20% と品質ゲートが必要なため v10 送り。

### Tier C: v10 本格 (from-scratch 1 回に同梱、診断ゲート付き)

#### C-1. ja ドメイン被覆拡充【候補 5、未検証】
- **方針**: 話者「数」ではなくドメイン軸の追加。Tier 1: **JVS** (+100 スタジオ朗読話者、つくよみ同ドメイン) — ただし**ライセンスは findings 間で矛盾** (C3「商用可」vs L3「CC BY-NC-SA 4.0 で不可」) のため**規約原文確認を最初のタスクに置く** (NC 確定なら学習除外、評価ローカル利用のみ検討)。Tier 2: **Emilia-YODAS ja** (CC BY 4.0 表記、~800-1.1k h、+1000 話者級) — Amphion card と KRAFTON README でライセンス表記が矛盾しており取得時 LICENSE 現物確認必須。Tier 3: **Common Voice ja** (CC0、UTMOS≥2.5 + ≥20clips + cap60 で +200-500 話者、男性・年配の属性補完、既存 exporter ミラーで ~1 日)。
- **除外確定**: ReazonSpeech (16kHz 帯域不足 + 著作権法 30 条の 4 建付けで商用 open-model 非両立)、J-CHAT (CC BY-NC 明示)、gol-dataset (同ドメインのため被覆効果確認後の第 2 弾へ)。
- **サンプラー注意**: ドメイン層別サンプリングは最小ドメインが epoch サイズを決める既知の罠 (ko 356 utts → 38 step 事故) を回避する設計にする。
- **コスト**: データ費ゼロ、前処理 (UTMOS/DNSMOS/帯域 gate/embedding 抽出) ~$100-250。

#### C-2. 構造介入: flow の SNAC 化 + enc_p 中間 block への AdaLN 注入【候補 7、未検証】
- SNAC (coupling 内の speaker 明示正規化/逆正規化) + mean_only=False 化 + VITS2 型 encoder 中間注入。全て ONNX graph 内部変更のみ、FP16 サイズ増 <1MB、推論コスト増ほぼゼロ。**投入ゲート**: Tier A の VC-SECS / 3-arm 全 arm 平坦 (dose 増でも) の結果を根拠とし、**学習信号修正 (B-1/B-3) とセットで投入** — 容量だけ増やすと z-leak に吸われる (C1)。期待 +0.02-0.05【文献ベース推測】。
- **コスト**: 実装 3-5 日、v10 from-scratch 50ep ~$140-300 (v9 実費 ~$140/50ep 参照) に同梱。

#### C-3. lang_emb と speaker 条件の分離【候補 8、未検証】
- 注入点分離 (lang → enc_p/dp、speaker → flow/dec) または cos² 直交化正則 + dp 用 spk_proj_dp 別ヘッド (韻律平板と両取り)。**投入ゲート**: A-1 の学習後ノルム比診断で lang 支配が実測確認された場合のみ (現状 init 実測のみ)。cross-lingual 品質への影響を smoke で確認。

#### C-4. v10 学習レシピの修正 (診断結果に基づく)
- SCL の遅延導入 + ramp (ep0-5 off → ep5-15 linear ramp、YourTTS/DMOSpeech パターン)、c_spk の勾配ノルム比較正 (2-3 まで、それ以上は Goodhart 域)、Latent Filling 型補間 augmentation + LFCL への σ 置換、DINO の廃止/統合。

### 不採用 (rejected) 一覧

| 候補 | 不採用理由 |
|---|---|
| c_dino チューニング | DINO は同一入力の EMA 自己蒸留に退化し y_hat 非経由 — C1/C2/L2 が独立に棄却 |
| CAM++ の joint fine-tune | encoder が TTS に迎合する Goodhart + 学習安定性リスク、現予算外 (L2) |
| Perceiver / cross-attention 可変長参照 | ONNX [1,192] 契約の breaking change — v10 スコープ外として明確に棄却 (L1/L2) |
| 参照の延長・多発話平均への追加投資 | 飽和実証済み: 我々 +0.035【実測】、Mega-TTS 2 は参照 100 倍で +0.034 (L1) |
| BigVGAN 等 decoder 交換 | 類似度便益の証拠なし + RTF 悪化 (L4)。MB-iSTFT 維持 |
| MRD / full-band STFT の削除 | がびがび再発リスク (v9 の主目的毀損)。半減 arm (Tier A) のみ許容 |
| SSL prompt 化 (GPT-SoVITS / P-Flow / HierSpeech++ 系) | AR または大型 SSL が CPU リアルタイム / 38MB 予算外 (L4) |
| c_spk の大幅増 (>3) | CAM++ 単一系 Goodhart の中〜高リスク (C2)。2.0 arm のみ実施 |
| ReazonSpeech / J-CHAT / KsponSpeech | ライセンス (30 条の 4 / CC BY-NC / research-only) が public 商用 open-model 方針と非両立 |

---

## 5. 推奨ロードマップ (コスト付き)

| フェーズ | 期間目安 | 内容 | コスト | go/no-go |
|---|---|---|---|---|
| **Phase 0: 診断** | 1-2 週 | A-1 診断基盤 (ckpt ノルム/FiLM/probing はローカル即日、第 2 encoder 整備、勾配計装) + A-2 4-arm warm restart (control / c_spk 2.0 / mrd 半減 / σ 0.01) + A-3 DINO 同乗 | **~$150-230** | 判定マトリクスで v9 退行の原因 (希釈 vs スケジュール) が一意化。全 arm 平坦時は勝ち arm 16ep 延長 (+$25) を挟んでから構造判断 |
| **Phase 1: 短期回収 (v9.1)** | 2-4 週目 | B-1 cross-utt SCL 化 A/B (対照 arm 込) + B-3 z_slice.detach 第 2 段 + Phase 0 勝ち構成の統合・延長 | **~$100-150** | 事前登録基準: zs_ja ≥0.70 かつ つくよみ cross-utt ≥0.75 (正規化転写率併記)、帯域スペクトル非悪化、ECAPA 乖離なし → v9.1 として ONNX export・公開判断 |
| **Phase 2: v10 本格** | 2 ヶ月目〜 | C-1 データ (ライセンス実確認 → CV ja / Emilia-YODAS ja / JVS) + C-2 SNAC/AdaLN + C-3 lang 分離 (診断ゲート通過分のみ) + C-4 レシピ修正、from-scratch 50ep | 前処理 ~$100-250 + 学習 ~$140-300 = **~$300-600** | 目標: cross-utt SECS 0.80 前後 / 正規化転写率 ~0.5-0.6。JVS holdout 常設で つくよみ 1 話者過適合を防止 |
| **合計** | ~2.5 ヶ月 | | **~$550-980** | 数百ドル予算内 (Phase 2 のデータ規模で調整可) |

**運用上の原則** (全フェーズ共通):
1. SECS は cross-utterance のみ、ceiling/floor 併記の正規化転写率で判定。same-utt SECS は判定使用禁止 (既知の 0.775 誤報)。
2. CAM++ 単独での go/no-go 禁止 — 第 2 encoder (正規化比較) + 4-9kHz 帯域スペクトル + 聴感の 4 点セット。
3. がびがび指標が悪化した arm は SECS が良くても不採用 (v9 の主目的を毀損しない)。
4. 「確実に似せる」需要には FT 経路 (v7 実績 0.775) を製品導線として正式案内 — zero-shot の目標を 0.80 超に置かない。

---

## 6. 参考文献リスト

**VITS 系 / 条件付けアーキテクチャ**
- YourTTS: Casanova et al., ICML 2022, arXiv:2112.02418
- VITS2: Kong et al., Interspeech 2023, arXiv:2307.16430
- SNAC (Speaker-Normalized Affine Coupling): Choi et al., IEEE SPL 2022, arXiv:2211.16866
- SC-GlowTTS: Casanova et al., Interspeech 2021, arXiv:2104.05557
- HierSpeech++: Lee et al., 2023, arXiv:2311.12454
- P-Flow: Kim et al., NeurIPS 2023 (openreview zNA7u7wtIN)
- FreeVC: Li et al., 2022, arXiv:2210.15418
- OpenVoice: Qin et al., 2023, arXiv:2312.01479
- Automatic Tuning of Loss Trade-offs in ZS-TTS/VC: Cho et al., 2023, arXiv:2305.16699
- THU-HCSI LIMMITS'24: Zhang et al., ICASSP GC 2024, arXiv:2404.16619

**Zero-shot TTS 一般 / SOTA 系**
- VALL-E: arXiv:2301.02111 / VALL-E 2: arXiv:2406.05370
- XTTS: arXiv:2406.04904 (Interspeech 2024)
- Mega-TTS 2: arXiv:2307.07218 (ICLR 2024)
- NaturalSpeech 2: arXiv:2304.09116 / NaturalSpeech 3: arXiv:2403.03100
- Voicebox: arXiv:2306.15687 / F5-TTS: arXiv:2410.06885 / MaskGCT: arXiv:2409.00750 (ICLR 2025)
- CosyVoice 2: arXiv:2412.10117 / CosyVoice 3: arXiv:2505.17589
- Fish-Speech: arXiv:2411.01156 / GPT-SoVITS (RVC-Boss) / Zonos (Zyphra, 2025) / NeuTTS Air
- StyleTTS 2: NeurIPS 2023 / StyleTTS-ZS: arXiv:2409.10058
- MobileSpeech: arXiv:2402.09378 (ACL 2024) / DiFlow-TTS: arXiv:2509.09631
- Seed-TTS: arXiv:2406.02430 / WavTTS: arXiv:2606.03455
- SEF-VC: arXiv:2312.08676 / Attentron: arXiv:2005.08484

**Speaker embedding / 損失設計 / Goodhart**
- SV2TTS: Jia et al., NeurIPS 2018, arXiv:1806.04558
- GE2E: Wan et al., 2018
- DMOSpeech: arXiv:2410.11097 / FlowTTS-GRPO: arXiv:2606.23190
- Latent Filling: ICASSP 2024, arXiv:2310.03538
- DINO-VITS: Pankov et al., Interspeech 2024, arXiv:2311.09770
- Chien et al. (M2VoC 話者表現比較): ICASSP 2021, arXiv:2103.04088
- ECAPA-TDNN/x-vector Exploration in ZS-TTS: 2025, arXiv:2506.20190
- ASCL: Choi et al., 2022, arXiv:2210.05979
- Cycle consistency VC: SLT 2021, arXiv:2011.08548 / MulliVC: arXiv:2408.04708
- SANE-TTS: arXiv:2206.12132 / DSE-TTS: arXiv:2306.14145
- Cross-lingual voice cloning (GRL): Zhang et al., 2019, arXiv:1907.04448 / Domain-adversarial TTS: arXiv:2006.06942
- GradNorm: Chen et al., ICML 2018 / CoV weighting: arXiv:2009.01717
- SSL 条件付け ZS-TTS: arXiv:2304.11976 / noise-robust 版: arXiv:2401.05111
- SSL-TTS (kNN retrieval): arXiv:2408.10771 / Semantic KD masked TTS: arXiv:2409.11003
- Attention Beats Concatenation for Conditioning Neural Fields: TMLR 2022 (openreview GzqdMrFQsE)
- ControlNeXt (zero-init sudden convergence): arXiv:2408.06070 / Zero-Initialized Attention: arXiv:2502.03029

**データ / スケーリング / 評価**
- Emilia / Emilia-Large: arXiv:2501.15907
- Audiobox: arXiv:2312.15821
- Cooper et al. (seen/unseen gap): arXiv:1910.10838
- ZeSTA: arXiv:2603.04219 / ZMM-TTS: arXiv:2312.14398
- JVS corpus: arXiv:1908.06248 / Common Voice (Mozilla) / LibriTTS-R / LibriHeavy / VoxPopuli / People's Speech / KRAFTON Raon-OpenTTS-Pool (ライセンス一覧)
- Low-Resource SSL with SSL-Enhanced TTS: arXiv:2309.17020 / DDPM oversmoothing & ASR: arXiv:2410.12279 / Inter/intra speaker variability: arXiv:2411.07754

**内部資料 (piper-plus)**
- docs/design/zero-shot-v8-dataset-scaling-plan.md (§3.7/§3.15/§3.16/§3.19)
- docs/design/zero-shot-noise-root-cause-pqmf.md (§2/§4/§5.6/§5.7/§6)
- docs/design/zero-shot-speaker-similarity-root-cause.md
- MEMORY: secs_cross_utterance_rule.md / v8_zero_shot_scaling.md
- コード実測: losses.py:89-140 / lightning.py:928-934, 1058-1065, 1168-1352 / models.py:1013-1023, 1110, 1167-1170, 1283-1289 / mb_istft.py:251-322 / campplus_torch.py:400-465 / export_onnx.py:656-735

---

*事実 (【実測】【コード】【文献】ラベル付きおよび出典付き数値) と推測 (【推測】ラベル、寄与度の見立て・期待効果) を区別して記載した。検証済み候補 4 件の「conditional」条件は検証エージェントの監査結果をそのまま反映しており、採用時は各条件を実装チェックリストとして扱うこと。*
