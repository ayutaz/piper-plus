# Zero-Shot v10b 品質改善計画 — 高域アーティファクト根治 + 話者類似の次段 (2026-08-16)

> **Status**: **Phase A 完了 (`76d42c57`) + Phase B 完了 (`f99316a9` デコーダ系 /
> `c7518499` 識別器系) + S-2 実装完了 (`2aa5ecbf`、設計 `5fcc9eb8`) + C-0
> ライセンス確定 (`245f8f49`、§7)、2026-08-18**。
> **実装は全て完了 — 残: Phase C (データ前処理: Emilia-YODAS ja/ko + CV ja +
> F0 抽出、instance 再レンタル) → Phase D (smoke + go/no-go) → Phase E (本走 80ep)**。
> v10a-r2 完走 (2026-08-16、
> [`zero-shot-v10-design.md`](zero-shot-v10-design.md) §11) を受け、4 系統の調査
> レポート — ①帯域解剖 (実測)、②評価ハーネス監査、③類似系文献調査、④高域ノイズ系
> 文献調査 — を統合した v10b の実行計画。既定計画 (R2 識別器形式 swap / R4 EMA flow
> 拡張 / データドメイン拡充) を**置換ではなく補強・具体化**する。
>
> 関連 doc: [`zero-shot-v10-design.md`](zero-shot-v10-design.md) (v10a 設計 +
> §10 swap-SCL インシデント + §11 r2 最終結果) /
> [`zero-shot-warm-restart-diagnostics-phase0-1.md`](zero-shot-warm-restart-diagnostics-phase0-1.md)
> (warm restart 全滅 + SCL Goodhart の実験的証拠) /
> [`docs/spec/zs-eval-contract.md`](../spec/zs-eval-contract.md) (評価契約) /
> [`zero-shot-noise-root-cause-pqmf.md`](zero-shot-noise-root-cause-pqmf.md)
> (v9 がびがび根治の canonical)
>
> **表記**: 本書は全主張を【実測】(本プロジェクトの測定)【文献】(一次文献の報告値)
> 【推測】(未検証の見込み) でラベルする。

## TL;DR

- **残存「ざらつき」の正体が特定できた**【実測】: 主犯はデコーダのフレーム格子由来の
  **定常・非調波トーンコム** (SR/64=344.5Hz 系列最強、4-8.5kHz、コム超過 +4.1〜4.7dB)。
  v9→v10a の全修正で**実質不変** — レベル系 loss (MRD/MR-STFT) はこの 10.8Hz 幅の
  コムに構造的に鈍感で、増強しても消えないことが実測で確定した。発生源の第 1 容疑は
  transposed conv checkerboard (格子周波数が実装と厳密一致)、第 2 容疑は PQMF 帯域
  境界のエイリアス非相殺 (ピーク 5512.5/8268.75Hz が 4-band 境界に一致)
- **「似ない」の音響的内訳も特定**【実測】: F0 ダイナミクスが GT の 55-65% に圧縮 +
  750-1000Hz の系統的包絡欠損 (-8.3dB、v9 と同符号 = 世代非依存) + 高域棚の音色歪み。
  そして評価監査により、**この 3 つを測る指標が現行ハーネスに 1 つも存在しない**ことが
  判明 — 「耳と数値の乖離」は指標の盲点 + 報告様式 (raw SECS headline) で説明できる
- **順序を明確化**: (1) 評価アップグレード (物差しを先に、~4 人日・GPU 不要) →
  (2) デコーダ格子対策 + JCU 条件付き識別器 + F0 経路の実装 → (3) データ拡充と束ねて
  from-scratch 80ep 本走。予算 ~$320-610 / 実装 3-4 週 / 判定基準は本書 §4.3 で事前登録
- **教訓①の制度化**: 本書で追加する全新指標 (帯域プロファイル / コム物理量 / prosody
  delta) は**学習 loss への流用を契約 + pre-commit gate で恒久禁止**。話者監督は
  frozen encoder cosine ではなく共進化する識別器形式 (JCU + adversarial speaker
  classifier、**classifier は生成音声でも敵対更新** — 実音声のみ学習の静的
  classifier は frozen encoder と同型の gaming 面を持つため不可) のみ

---

## 1. 実測サマリ — v10a-r2 ep79 の帯域解剖

対象: r2_ep79 / v9 / GT 計 17 ファイル、voiced フレーム限定、STFT n_fft=2048/hop=256、
全ファイル RMS 正規化 + 0-4kHz voiced power 基準。分析スクリプトは scratchpad
`quality_anatomy/{anatomy.py,verify_comb.py}` (§6 参照、v10b Phase A で
`piper_train.tools` へ移植する)。

### 1.1 残存アーティファクトのシグネチャ (3 種 + 無罪 1 種)

| # | シグネチャ | 実測値 (r2 / v9 / GT) | 知覚対応 |
|---|---|---|---|
| **A1** | **フレーム格子トーンコム** (定常・非調波)。172.27Hz=SR/128 の整数倍、**344.5Hz=SR/64 倍数が最強** (4479/4823/5168/5340/5512/6202/6546/7580/8269Hz 等)、4-8.5kHz に局所 +6〜12dB。>4kHz 残差の自己相関 lag128/256 (= hop 256 の半分/全体) に明確なピーク | コム超過: r2 +4.1〜4.7dB / v9 +3.6〜4.5dB / GT 0.65-0.76dB — **v10a の修正で実質不変**。autocorr: r2 0.10-0.24 / GT ≈0.006-0.13 (無構造)。5512.5Hz=SR/4・8268.75Hz=3SR/8 は PQMF 4-band 境界に一致【実測】 | F0 (~330Hz) と非調波のため声とビートし**金属的リンギング** — 最有力の「シャリシャリ」源 |
| **A2** | **5.5-8.5kHz レベル棚** | voiced +3.0〜+4.6dB (GT sd 1.8-2.7dB の ~2σ)、無声区間 +4.6〜+7.9dB (テキスト非統制の注意あり)。v9→r2 の「-7.6→-10.5dB 改善」は実際には 8.5-9.5kHz と無音部スパイクに現れており、**この棚は残存**【実測】。棚内 flatness は GT より tonal 側 (-0.9〜-1.0dB @6.5-8k) = 中身は純ノイズでなくコム混じり | 「明るすぎ / ざらつく別人の声」 |
| **A3** | **中域調波間ノイズ充填** | comb-HNR (調波/調波間電力比) が 1-3kHz で GT 比 -2.5〜-3.0dB (GT 6.0→r2 3.0 @1.5-2k)、flatness +1.0〜+2.6dB ノイズ寄り【実測】。5.5-9kHz は GT 自体がほぼノイズ性 (HNR 0.5-1.0dB) で合成も同等 → **高域の問題は「調波欠落」ではなく「レベル超過+コム」**と切り分け確定 | ブレシーなざらつき |
| — | **時間変調系は無罪** | フレーム間帯域 flux は合成 ≤ GT (中域 -0.1〜-0.3dB/frame)、変調スペクトル 30-170Hz 成分比も合成 0.003-0.006 < GT 0.007-0.010【実測】 | 対策は時間平滑化ではなく**周波数構造 (コム) 除去**が正解 |

### 1.2 類似を妨げる音響要因 (3 種)

| # | 要因 | 実測値 | 備考 |
|---|---|---|---|
| **B1** | **F0 ダイナミクスの圧縮** | GT: mean 325-375Hz / std 47-74Hz / p5-95 レンジ 153-215Hz (n=11)。r2: mean 306-325Hz (-20〜-40Hz) / std 29-41Hz / レンジ 87-142Hz = **GT の約 55-65%**。v9 はさらに平板 (std 27-32)【実測】 | v8 から持ち越しの「韻律平板さ」の定量化。話者性の第一次手掛かりを欠く。構造的原因候補は DP g-detach (v10-design F4、M3 で v10a から修正済) — ただし r2 でも圧縮残存 = M3 単独では不足【実測+推測】 |
| **B2** | **750-1000Hz の系統的包絡欠損** | r2 -8.3dB (GT sd 2.5 → 3.3σ)、隣接 500-750Hz +3.6dB 過剰 = F1 帯域エネルギーの下方シフトで母音の色が変わる。**v9 も同符号 (-10.9dB) = 世代非依存の系統バイアス**【実測】 | データではなく loss / デコーダ帯域応答起因の可能性大【推測】→ from-scratch でも再発見込、学習前にユニットテスト化 (H-5)。付随: 0-250Hz +6.5dB (LF ランブル)、1750-2000/2250-2500Hz 各 -3.4dB。なお 500Hz 刻みの粗い見方では r2 は GT ±1.6dB 以内で v9 の中域欠損 (-3〜-5dB) はほぼ解消済 |
| **B3** | **高域音色の歪み (A1/A2 と同根)** | 女声の音色判別は 4-8kHz スペクトル傾斜に依存するため、5.5-8.5kHz 棚 + コムは類似度も直接毀損【実測+推測】 | **アーティファクト対策がそのまま類似改善に寄与する二重取り構造** |

### 1.3 発生源の容疑序列 (文献 × 実測の突き合わせ)

高域ノイズ系文献調査 (arXiv 一次文献 8 本精読 + ローカル実装読解) による容疑序列:

| 順位 | 容疑 | 実測との一致 | 出典 |
|---|---|---|---|
| 1 | **transposed conv の checkerboard / tonal artifact** — 「定常・一定周波数トーンで学習後も残存、無音部と OOD で顕著」 | 我々のデコーダは ConvTranspose1d ×2 段 (`mb_istft.py` L214-224、upsample_rates=(4,4))【実測 (コード)】。ups[0] 出力格子 = SR/64 = 344.5Hz が**観測コムの最強系列と厳密一致**【実測】。「定常・学習後も残存」のシグネチャも一致 | Pons ら (arXiv:2010.14356)【文献】 |
| 2 | **PQMF 帯域境界のエイリアス非相殺** — NN 生成 subband は解析フィルタバンク由来でないため QMF のエイリアス相殺前提が崩れる。taps=62 の広い遷移帯域が境界トーン + 5.5-8.5kHz 棚に寄与 | 観測ピーク 5512.5Hz (SR/4)・8268.75Hz (3SR/8) が 4-band 境界に一致【実測】 | 文献調査【文献+推測】 |
| 3 | **非線形性エイリアシング** — コムでなく棚 (A2) 成分に寄与 | 棚の存在と整合【推測】 | BigVGAN (arXiv:2206.04658) の指摘【文献】 |
| 4 | **iSTFT head の位相推定誤差** — 中域の調波間侵食 (A3) に対応 | A3 と整合【推測】 | 文献調査 |

「時間変調無罪」の実測 (§1.1) は「GAN の時変 musical noise」説を棄却し、
**定常構造 (conv 格子 + 固定フィルタ) 説を支持**する【実測】。

---

## 2. 評価アップグレード計画 (学習より先に実施)

**原則: 改善を測れる物差しを先に整える。** 評価監査の結論 — 「耳と数値の乖離」は
主に (1) 帯域指標の粒度不足 + 実音声アンカーなし、(2) 韻律を測る指標の完全な不在、
(3) raw SECS を headline にする報告様式 (0.753 は正規化転写率 ~0.2-0.25 で聴感と
実は一致)、(4) floor 集合の再現性不足 — の 4 盲点で説明できる【実測 (実装読解)】。

### 2.1 項目一覧

| # | 項目 | 内容 | コスト | 出所 |
|---|---|---|---|---|
| **E-1** | **実音声アンカー付き 1kHz 刻み帯域ベクトル** | `measure_band_noise` に `band_profile()` 追加: voiced 平均スペクトルの 1-11kHz / 1kHz 刻みベクトル (dB、1-3kHz 基準) + 同一話者実発話との差分 `band_delta_vs_real`。「どの 1kHz 帯が実声よりどれだけ高いか」を直接出す — 現行の 4-9kHz 幅 5kHz 平均 1 値では 5-6kHz 集中が最大 ~7dB 希釈される【推測 (算術)】。9-11.025kHz の完全死角 (SECS は 16kHz fbank で 8kHz 以上全盲【実測 (コード)】) も塞ぐ | ~1 人日 | 監査 P1 |
| **E-2** | **per-frame 分布出力** | エネルギー総和比に加え voiced フレームごとの hi/ref 比の median / p90 / 閾値超過フレーム率。時間局在ノイズの平均への希釈を塞ぐ | +0.25 人日 | 監査 P2 |
| **E-3** | **prosody_delta ブロック** | 合成 vs 同一話者実発話の F0 median / F0 std (semitone) / p5-p95 レンジ / voiced 率 / voiced エネルギー std (dB) / 話速の差分を JSON 併記。**「韻律平板さ」の初めての数値化**。Mega-TTS 2 の pitch DTW + 分布 moments (σ/skew/kurt) と同型で文献裏付けあり (arXiv:2307.07218)【文献】。類似スコアではなく統計差の記述であることを docstring 明記 | ~1 人日 | 監査 P3 + 類似調査 (iii) |
| **E-4** | **ゲーム不能なコム物理量 2 種の tools 化 + 帯域再照準** | (i) >4kHz 残差の自己相関 @lag128/256 (GT ≈0.01-0.13 / 現状 0.10-0.24)、(ii) SR/128 格子コム超過 dB (GT 0.65-0.76 / 現状 4.1-4.7)【実測】。scratchpad の `anatomy.py`/`verify_comb.py` を `piper_train.tools` へ移植。既存帯域指標は 8.5-9.5kHz 改善で飽和済のため **5.5-8.5kHz に再照準** + 無声区間同帯域を別枠測定 | ~0.5-1 人日 | 解剖 rec 2 |
| **E-5** | **再現性修繕 4 点** | (i) floor/ceiling/synth 全ファイルの相対パス + sha256 + 選定基準を JSON manifest 化 (floor 集合は HF に固定セットとして pin — floor ±0.02 で正規化転写率 ±10-13% 振れる【実測 (算術)】)。(ii) `--exclude-ref` を内容 sha256 一致でも除外 (same-utt 静か混入の防止)。(iii) `normalized_transfer` に ceiling>floor 符号ガード追加 + phase0 実装と定義統一 + 合成条件 (noise_scale/noise_scale_w/seed/texts) の `--meta-json` 記録 — **§4.3 の事前登録判定ではこの manifest 値への「固定」として運用** (記録のみでは eval-time knob の穴が残る)。(iv) `DEFAULT_HI_BAND` を (4000,9000) に統一し契約値と揃える (現状 CLI (5000,9000) vs 本走 (4000,9000) の不一致【実測 (コード)】) | ~0.5 人日 | 監査 P4 |
| **E-6** | **軽量 ABX 聴感プロトコル** | 固定 10 アイテム (話者×テキスト pin) の A/B ブラインド HTML (ローカル、順序ランダム化)。質問 2 つ: ①どちらが参照話者に近いか ②どちらが高域のざらつきが少ないか。回答 JSON を eval JSON の隣に保存、判定基準は事前登録 (10 中 7 以上) | 0.5-1 人日 | 監査 P6 + 類似調査 (iii) |
| **E-7** | **契約 + 報告様式の改訂** | (i) headline を raw SECS → **normalized_transfer (+floor/ceiling 併記)** に変更、eval-zs skill に「raw SECS を単独 headline にしない」を追記。(ii) 契約に「SECS↔人間類似の相関上限は utterance-level LCC≈0.75-0.78 (VoxSim arXiv:2407.18505: ECAPA LCC 0.768 / Deja et al. arXiv:2207.00344: Pearson 0.78)【文献】、±0.03 未満の SECS 差は人間類似の判定材料にしない」を明記。(iii) **SECS > ceiling を Goodhart flag に追加** (YourTTS の「録音特性複製」シグナル【文献 arXiv:2112.02418】) | ~0.25 人日 | 監査 P7 + 類似調査 (iii) |
| **E-8** | **教訓①の制度化 gate (全新指標の採用条件)** | 契約 §2 に禁止事項 4 を追加:「本契約の全メトリクス (band / band_delta / コム物理量 / prosody_delta / 変調指標含む) の学習 loss・reward・学習中の動的サンプル選別への流用を恒久禁止 (オフライン前処理のデータゲートは対象外)」。pre-commit の zs-prevention 系 gate を拡張し `piper_train/vits/` 配下から `tools.measure_band_noise` / `tools.eval_zs_secs` / 新 prosody・コムモジュールの import を機械的に block。根拠: frozen CAM++ cosine (swap-SCL) が prior 経路を ~6ep で崩壊させた v10a §10【実測】。**F0/エネルギー統計は微分可能化が容易で「韻律 loss」への流用誘惑が最も強い — 明示 ban list に入れる** | 0.25-0.5 人日 | 監査 P8 |
| **E-9** | (条件付き・優先度低) 時間変調指標 | 4-9kHz 帯域エネルギー軌跡の変調スペクトル (2-30Hz) 変調深度等。**解剖で「時間変調は無罪」が実測済のため優先度を降格** — 採用はラベル付き聴感サンプル (`v9_listen_samples` / `v10a_listen_samples`) で悪いクリップを良いクリップから分離できることを実証してから (分離できない指標の追加は PQMF 事故の goalpost 逆パターン = 指標増殖) | 1-1.5 人日 + 検証 | 監査 P5 (解剖により条件付き化) |

JSON schema は `zs-eval-v2` → **v3** (field 追加のみの後方互換、契約 §4 準拠) で
band / prosody_delta / comb ブロックを `eval_zs_secs` 出力に統合し、現在
/publish-model フェーズ 3.5 と phase0 ハーネスに散在する 4 点セットを
1 アーティファクトに集約する。

**合計 ~4-5 人日 (GPU 不要)。E-1〜E-8 完了後に v10a-r2 ep69/ep79・v9 ep49・GT を
新物差しで再測定し、v10b の baseline JSON を確定してから学習に進む。**

### 2.2 学習目標への流用禁止 (教訓①) の整理

| 信号の種類 | 学習への使用 | 根拠 |
|---|---|---|
| GT 波形との spectral distance (mel/STFT/MRD、H-3 の高分解能版含む) | **可** (従来通り) | frozen 測定器ではなく GT 参照 loss |
| 共進化する識別器 (MPD/MRD/JCU 分岐/adversarial speaker classifier) | **可 (条件付き)** | min-max で静的に game 不能なのは**識別器/分類器が生成分布上でも更新される場合のみ** (教訓①適合の条件)。実音声のみで学習する classifier は生成分布上の決定境界が静的 = frozen encoder と同型の gaming 面を持つため不可 (S-1 の仕様と Phase D 検証項目参照) |
| frozen encoder (CAM++/ECAPA) の cosine を直接目的化 | **禁止** (SupCon の正例構成等、既検証の限定形式を除き新規追加禁止) | same-utt SCL / c_spk 増 / swap-SCL cosine の 3 例で実証【実測】 |
| 本契約の評価メトリクス (band / コム / prosody_delta / ABX) | **恒久禁止** (E-8 gate) | 評価器を目的化した瞬間に検出器を失う |

---

## 3. 改善レバー (優先順)

### 3.1 高域系 (アーティファクト根治)

> 共通前提【実測】: v9→v10a-r2 で spectral loss を増強してもコム超過は
> +3.6-4.5 → +4.1-4.7dB と不変 = **レベル系 loss の追加増強ではコムは消えない**。
> 対策は生成構造 (格子) と固定フィルタ (PQMF) に直接手を入れる。

#### H-1: upsampler の resize+conv 化 (第 1 容疑への直撃) — 最優先

- **根拠**: 【実測】SR/64 格子 = ups[0] 出力格子の厳密一致 (§1.3)。【文献】Pons ら:
  transposed conv の tonal artifact は初期化直後から存在し学習後も残存
  (arXiv:2010.14356) → **smoke の初期 epoch でコム指標により検証可能**【推測 (我々の
  設定への適用)】
- **設計**: ConvTranspose1d を nearest/linear resize + Conv1d に置換 (両方 ONNX 標準
  op)。代替の低リスク案: ConvTranspose を温存し lowpass 初期化 (kernel を
  interpolation filter で初期化)
- **期待値**: コム超過 +4.1〜4.7dB → <1.5dB【推測、E-4 指標で検証】。A2 棚の
  コム混じり成分 (flatness tonal 側) も同時に減る見込み【推測】
- **コスト**: 実装 1-2 日 + from-scratch 学習前提。**CPU 推論コストは同一 kernel
  では同級にならない**【算術】: stride=4 の ConvTranspose1d (MACs ≈ L_in·k·C_in·C_out、
  入力長基準) を同一 kernel の resize(×4)+Conv1d に置換すると出力長基準で畳み込む
  ため **MACs は約 4 倍/段**。MB-iSTFT の採用根拠が CPU Decoder 2.21x 高速化である
  以上、upsampler 4x 増は CPU-RT を毀損しうる → **kernel 縮小 (k ∝ 1/stride) 込みで
  設計し、§4.3 の推論コスト gate (CPU p50 レイテンシ / ONNX サイズ) でベンチ必達**。
  ONNX [1,192] 契約は不変
- **リスク**: 表現力/音質の変化 → smoke でコム指標 + 帯域 + 聴感の単変量検証。
  lowpass 初期化 fallback を保持

#### H-2: PQMF / iSTFT 合成段の検証テスト + 帯域境界対策 (第 2 容疑)

- **根拠**: 【実測】5512.5Hz (SR/4)・8268.75Hz (3SR/8) ピークが PQMF 4-band 境界に
  一致。【文献+推測】NN 生成 subband は解析フィルタバンク由来でないため QMF の
  エイリアス相殺前提が崩れる (taps=62 の遷移帯域)
- **設計**: (a) **合成パス単体 unit test** — 既知信号 (正弦波 sweep / 白色雑音) を
  iSTFT+PQMF 合成に通し、コム/境界エイリアスを E-4 と同じ物理量で測定。受け入れ
  基準は第一原理から導出し `# threshold-relaxed:` ルール (pre-commit
  `test-threshold-relaxation` gate) に従う — **-90dB→5dB の goalpost moving を
  15 ヶ月制度化した PQMF 事故の再発防止**。(b) taps 増 / 遷移帯域再設計 or
  **trainable synthesis filter** (PQMF 合成側 filter を学習可能化、noise 系調査の
  対策①に併記) の A/B
- **コスト**: テスト 0.5-1 日、filter A/B 実装 1-2 日。taps 増は推論の conv 1 本が
  63→127 tap になる程度【推測、軽微】
- **リスク**: trainable filter は完全再構成性を失う方向 → 合成テスト (a) を gate に
  して逸脱量を監視

#### H-3: 高周波数分解能 spectral 監督 (n_fft≥2048、4-9kHz 重点)

- **根拠**: 【実測】既存 MRD/MR-STFT の分解能では 10.8Hz 幅コムに鈍感 (§1.1 A1)。
  H-1/H-2 が構造対策、H-3 は「残ったコム/棚に勾配を当てる」補完
- **設計**: 既存 MRD に高分解能 resolution (n_fft 2048-4096) を 1 本追加、または
  4-9kHz 帯域重み付き高分解能 STFT loss (GT 比較 loss なので教訓①対象外 — §2.2)。
  **E-4 のコム指標そのもの (SR/128 格子超過) の loss 化は禁止** (E-8 gate)
- **コスト**: 0.5-1 日 + 学習 VRAM/速度微増【推測】
- **リスク**: 高分解能 STFT は時間分解能が犠牲 → 既存 resolution の置換でなく追加で

#### H-4 (条件付き): 非線形性エイリアシング対策 (BigVGAN 型 anti-aliased activation)

- 第 3 容疑 (A2 棚成分)【文献 arXiv:2206.04658】。up/down sampling filter による
  CPU 推論コスト増があるため【推測、要ベンチ】、**H-1/H-2 投入後も棚が残る場合のみ**
  検討する条件付きレバー

#### H-5: 750-1000Hz 包絡欠損 (B2) の原因調査 + 合成系帯域応答ユニットテスト

- **根拠**: 【実測】v9/r2 で同符号 (-10.9/-8.3dB) = 世代非依存 → from-scratch でも
  再発見込
- **設計**: 学習前に (a) upsampler+iSTFT+PQMF チェーンの白色雑音帯域応答を
  ユニットテスト化 (デコーダ起因の切り分け)、(b) mel loss の filterbank 帯域重みの
  検査 (loss 起因の切り分け)。原因確定後に対策を設計 (現時点で対策を事前確定しない)
- **コスト**: 0.5-1 日

### 3.2 類似系

#### S-1 (= 既定 R2 の具体形): MRD への JCU 条件分岐 + 共進化 adversarial speaker classifier — 最優先

- **根拠**: 【文献】GANSpeech の JCU (Joint Conditional & Unconditional) 判別器
  (arXiv:2106.15153、MOS 3.95→4.36): speaker embedding を FC→時間展開→中間層
  concat、無条件/条件分岐が body 共有。StarGANv2-VC (arXiv:2107.10394) の
  adversarial source classifier ablation: **話者分類精度 96.2%→63.9% (GT 98.67%)、
  pMOS 3.95→3.98 と不変** = 話者性のみを担う損失の直接証拠。【実測】v10a §10:
  frozen CAM++ cosine 形式は prior 経路を ~6ep で崩壊させた — 共進化形式が必須
- **設計**:
  - 既存 MRD の各 resolution に JCU 分岐を追加 (spk emb 192→FC→時間展開→中間層
    concat、LSGAN の無条件項+条件項を 1/2 ずつ)。**MPD は無条件のまま** (timbre が
    住む spectrogram 域に条件を集中)
  - 独立の adversarial speaker classifier C を追加。**C は生成音声でも敵対的に
    更新する** (StarGANv2-VC 忠実形【文献 arXiv:2107.10394】 — 原典の adversarial
    source classifier は C を変換後 (生成) サンプルで敵対的に更新する形式):
    (i) C は実音声で ~3.7k 話者分類 CE を学習 (AAM-softmax 可)、(ii) **C は生成
    音声に対しても更新される敵対項を持つ** (fake 入力に対する C の更新を仕様に
    含める)、(iii) G は生成音声が条件話者に分類されるよう CE 最小化。
    **実音声のみで C を学習する形式は禁止**: 生成分布上の C の決定境界が無防備 =
    更新が遅い frozen encoder と実質同じ adversarial-example gaming 面が残り、
    v10a §10 の崩壊機構 (「frozen encoder 狙いの adversarial 的特徴の蓄積」原因 2)
    がそのまま再現可能なため (§2.2 の「可」判定は生成分布上の更新が条件)。
    C の生成分布上の更新が機能していること (fake に対する C の話者分類精度の推移)
    を **Phase D smoke の検証項目 + 本走 R3 監視対象**に含める。
    閉集合 classifier は学習時のみで zero-shot 推論に影響しない【事実 (構造上)】
  - 安定化: (i) adversarial ramp は KL annealing 完了後 (v10a swap と同じ
    start10/ramp5 系)、(ii) GANSpeech の scaled FM loss (λFM = L_recon/L_FM 動的
    更新)、(iii) real 入力への弱 R1 penalty (γ 小さめから)
  - 適用先は swap 経路 (flow⁻¹ + dec) と recon 経路の両方が候補 — swap 経路に
    当てれば「flow reverse に話者勾配を通す」という R2 本来の目的 (v10-design §3.1)
    を frozen encoder なしで達成する
- **期待値**: in-domain 0.60 plateau の突破レバー。【文献】Meta-StyleSpeech
  (arXiv:2106.03153): frozen d-vector 条件付け baseline は unseen Sim 0.601-0.616 で
  停滞、joint 学習 style encoder + prototype 判別器で 0.738-0.815 — 我々の
  in-domain 0.603 と定量的に同型【ただし encoder/データが異なり数値の直接比較は
  不可 (推測)】
- **コスト**: 実装 3-5 日、学習 +10-20%/step【推測】、**推論コストゼロ・ONNX 契約
  不変**【事実 (構造上)】
- **リスク**: GAN 不安定 → ramp + R3 監視 (5ep 毎 prior 経路評価 + ECAPA abort、
  v10a-r2 で実装・運用済) を継承。projection 形式 (Miyato & Koyama
  arXiv:1802.05637) は音声 TTS では前例が薄いが、L2 正規化 192-d には有利な可能性
  【推測】— smoke で JCU concat と比較する optional arm

#### S-2: F0 明示経路 (Period VITS 参考: 話者条件付き frame pitch predictor + 励振注入) — 注入機構は要独自設計

- **根拠**: 【実測】B1 (F0 std/レンジが GT の 55-65%) + A3 (1-3kHz comb-HNR
  -2.5〜-3.0dB) に直撃。【文献】Period VITS (arXiv:2210.15964): frame prior network
  → frame pitch predictor (F0+V/UV) → sample-level sine source を decoder に注入、
  日本語 15 話者感情コーパスで **MOS 2.78→4.66** (sine source 単独でも 4.63) —
  VITS の「韻律多様データで pitch 不安定化」への直撃解。predictor への話者条件は
  spk_proj 出力を FiLM/concat (Daft-Exprt arXiv:2108.02271 の FiLM 注入が先行例)
- **構造的不整合 — 引用のままの移植は不可**【実測 (コード)】: Period VITS の
  sine source 注入は HiFi-GAN 型時間領域 upsampler の各段に downsample した sine
  励振を加算する設計。対して我々の MB-iSTFT decoder (`mb_istft.py` forward) は
  全 conv がフレーム格子 (SR/256→SR/64→SR/16) で動作し、OnnxISTFT が subband
  波形 (SR/4) を生成、固定 PQMF synthesis で初めて SR に到達する — **サンプル
  レートで動作する conv 段が 1 つも存在せず、sine source を加算できる注入点が
  ない**。NSF+iSTFT の先行例 (HiFTNet 系) も single-band であり、PQMF 4-band への
  励振注入は先行例のない独自設計になる。**Phase B 冒頭に注入機構の設計スパイク
  (2-3 日) を置き**、候補 — (a) frame 格子への F0/harmonic 特徴の concat、
  (b) subband レート (SR/4) での per-band 励振加算、(c) iSTFT head 入力への
  harmonic 位相特徴付与 — を比較確定してから実装に入る。確定前の本走組込は不可
- **前処理コスト (従来未計上、明示)**: frame pitch predictor の学習には GT
  frame-level F0 が必要だが、dataset/前処理に F0 抽出は一切存在しない【実測
  (コード、`dataset.py` に f0/pitch 参照 0 件)】。**~300k utts 分の F0 抽出 +
  キャッシュ形式設計を Phase C に計上する** (CPU バッチで実行可の見込み【推測、
  要見積】)
- **契約適合**: F0 はテキスト + 話者条件から内部予測されるため **ONNX 入力 [1,192]
  不変**【事実 (構造上)】、cumsum+sin は ONNX 標準 op【事実】。CPU コスト増は
  §4.3 の推論コスト gate でベンチ必達【要ベンチ】
- **先行床測定 (Phase A、学習不要)**: noise_scale / noise_scale_w 掃引を E-3 の F0
  指標 (std ≥ 45Hz / p5-95 ≥ 150Hz) で再評価し、確率経路だけでどこまで回復するかの
  床を測る。**掃引は探索専用** — §4.3 の判定は manifest に固定した合成条件で行う
- **コスト**: 設計スパイク 2-3 日 + 実装 1-2 週 + F0 前処理 (Phase C 計上)
- **リスク・干渉**: decoder 改変 (H-1/H-2) と干渉するため**実装・検証順序は
  H 系 → S-2 の単変量**。v10b 本走への組込は Phase D smoke の単独 arm 検証 pass が
  条件 (未達なら v10c 送り)

#### S-3: データドメイン拡充 (既定 C-1 の継承)

- Tier 1 JVS (+100 スタジオ朗読、つくよみ同ドメイン) / Tier 2 Emilia-YODAS ja
  (+1000 話者級) / Tier 3 Common Voice ja + **ko 復活検討** (v10-design §5 を継承。
  language-balanced sampling の最小言語問題 = 356 utts 事故の回避設計が前提)
- **根拠**: 【文献】YourTTS: 学習話者 ~1.2k 化で SECS +0.10 (arXiv:2112.02418)。
  HierSpeech++: ノイズ込みでも 5x hours で SECS +0.021 (arXiv:2311.12454、
  v10-design F6)
- **ガード**: ゲート緩和は帯域メトリクス (既存 hi_ratio/fmax + 新 E-1 band profile)
  での再検証付きで段階的に — がびがび再発リスクと表裏
- **コスト**: ~$100-250 (v10-design §6 継承) + C-0 ライセンス実確認を最初に

#### S-4: 多参照 embedding 平均 (推論側 quick win、学習不要)

- 3-5 発話の CAM++ embedding の L2 正規化平均。ONNX 契約 [1,192] 内で実装可能。
  **r2 ep69/ep79 で即 A/B 可能** (Phase A で実施)
- 【文献】Mega-TTS 2 (arXiv:2307.07218): prompt 3s→300s で SIM 0.898→0.932 の参照
  情報量スケーリングの最小移植 — ただし直接実証は multi-sentence encoder であり
  平均ではない【推測】。期待 +0.01-0.02【推測】— 動けば無料の改善
- **判定への使用禁止**: §4.3 の事前登録判定は**単一参照 embedding** で行い、S-4 の
  多参照平均は**別枠報告のみ** — つくよみ必達 gap は +0.013 (ep69 0.767→0.78) で
  S-4 の期待値だけで大半を埋められる余地があり、判定 eval に混ぜると eval-time
  knob で必達を満たす穴になるため (§4.3 で固定)

#### S-5 (= 既定 R4): EMA 対象を flow / enc_p に拡張

- 【実測】v10a §10 所見 5: 現行 EMA は dec+spk_proj のみで flow/enc_p/dp が対象外 —
  SNAC 導入後の必須整備。実装 0.5 日

---

## 4. v10b 実行計画への統合

### 4.1 既定計画との束ね方

| 既定 (v10-design §11 の結論) | 本調査による具体化・追加 |
|---|---|
| R2: swap の識別器形式再実装 | → **S-1** (JCU 条件分岐 + adversarial speaker classifier、文献 2 本の実証形式に確定) |
| R4: EMA の flow 拡張 | → **S-5** (そのまま) |
| データドメイン拡充 (C-1) | → **S-3** (帯域ゲート付き段階投入、E-1 で監視解像度を上げる) |
| (なし — 新規) | **高域系 H-1〜H-5**: 解剖でコムの正体と発生源容疑が特定されたため新設。「がびがび残滓」はデータでも loss 係数でもなく**生成構造の問題**なので、v10b の from-scratch を待たずに直せるものは直してから学習する |
| (なし — 新規) | **評価アップグレード E-1〜E-8**: 全レバーの効果測定の前提。最初に実施 |
| v10a-r2 実証済みの土台 (M1-M3 / SupCon 改良 / DINO 廃止 / σ=0) | **維持** (v10-design §11: OOD +0.03 両 encoder 同調 + 帯域 -2.9dB で実証済)。**LF は本リストから除外** (下行) |
| LF (Latent Filling) — **未検証、実証済みではない** | **v10b では τ=0 (off) のまま維持し、有効化は v10c 送り**。LF は v10a/r2 で一度も有効化されていない (v10-design §9 の実行記録に「LF off」と明記。r2 は同 run の ep27 resume + swap OFF のみの変更 = 全期間 off) ため「実証済みの土台」ではない。さらに現行 LFCL 実装 (`lightning.py`: LF step は recon/mel/KL/GAN/D 更新を全て skip し、**frozen CAM++ cosine のみ**で G を更新) は品質・自然性の対抗信号がゼロ = swap-SCL 崩壊の機構 (v10-design §10 原因 3) と構造的に同型の**教訓①未検証ハザード**。将来の有効化は (i) 共進化形式への再設計または対抗信号の追加、(ii) Phase D 相当の単独 arm smoke 検証 pass、の両方を条件とする |

### 4.2 フェーズ分け + 予算

| Phase | 内容 | 期間 / コスト |
|---|---|---|
| **A: 評価整備 + 無学習 A/B** | E-1〜E-8 実装 (E-9 は条件付き) → v10a-r2 ep69/ep79・v9 ep49・GT を新物差しで再測定し **baseline JSON 確定** → S-4 多参照平均 A/B → noise_scale/noise_scale_w 掃引の F0 指標再評価 (S-2 の床測定) → H-2a/H-5 の合成段ユニットテスト (デコーダ起因の切り分け) | ~1-1.5 週、GPU ほぼ不要 (CPU 推論で可)、$0 |
| **B: 実装** | H-1 (resize+conv) → H-2b (filter A/B) → H-3 (高分解能監督) → S-1 (JCU+classifier) → S-5 (EMA 拡張) → S-2 着手 (H 系の後)。全て単体テスト付き (TDD、閾値は第一原理から) | ~2-3 週 (実装 ~10-14 人日)、GPU 不要 |
| **C: データ** (B と並行) | C-0 ライセンス実確認 → C-1 前処理 (JVS / Emilia ja / CV ja、ko 判断) + ゲート再バランス (帯域メトリクス再検証付き) + **S-2 用 GT frame-level F0 抽出 (~300k utts + 追加データ分、S-2 を Phase D arm に載せる場合のみ。§3.2 S-2 参照)** | ~$100-250 (+F0 抽出は CPU バッチ見込【推測、要見積】) |
| **D: smoke + 較正** | 2-3ep smoke: ①H-1 のコム指標検証 (初期 epoch から測定可【文献+推測】— pass しなければ本走に進まない)、②grad-probe 較正 (speaker 系 = mel の 5-15%、v10a 実績手順)、③JCU+classifier の安定性 + **classifier C の生成分布上の更新が機能していることの確認 (fake に対する C の話者分類精度の推移、§3.2 S-1)**、④VRAM / sec/step。optional arm: S-2 単独 / projection vs JCU concat | ~$40-80 |
| **E: 本走** | from-scratch **80ep** (4x A100、S-1 コスト込 ~40-48h 見込)、**5ep 毎中間評価 (R3 継承: prior 経路定点 + ECAPA 乖離 abort + goodhart_flag)**。ep39 で平坦なら打ち切り (v10a 方式) | ~$180-280 |
| 合計 | | **~$320-610、実装 3-4 週 + 学習 ~2 日** |

### 4.3 事前登録判定基準 (v10b、変更禁止)

> **判定 baseline は単一 ckpt に固定: v10a-r2 ep69** (v10-design §11 の推奨 ckpt、
> dual-encoder バランス最良。HF `checkpoints-v10a-r2/epoch=69-step=93520.ckpt`)。
> 全行の比較対象を ep69 に統一し、Phase A で新物差し再測定した値を baseline JSON
> manifest (E-5) に pin する。ep79 の数値は参考併記のみで**判定には使わない**
> (つくよみ ECAPA は ep69=0.653 / ep79=0.634 と 0.019 差があり、baseline の選択
> だけで Δ≥+0.01 の pass/fail が反転しうるため【実測、v10-design §11】)。
> 下表の「現状」列のうち解剖系数値 (F0/コム/棚) は r2 **ep79** ファイルでの実測 —
> ep69 の対応値は Phase A 再測定で確定し manifest に記載する。
>
> **判定時の合成条件も固定**: 判定 eval は baseline JSON manifest に pin した
> 合成条件 (**noise_scale / noise_scale_w / seed / テキスト manifest**) を baseline
> 測定と同一にして行い、参照は**単一参照 embedding** とする (E-5(iii) は「記録」
> ではなく判定時の「固定」として運用)。noise_scale 掃引 (S-2 床測定) は探索専用、
> S-4 多参照平均は別枠報告 — いずれも必達判定には使えない (eval-time knob で
> 必達を満たす穴を塞ぐ)。
>
> 報告 headline は normalized_transfer (E-7)。**raw SECS 単独・CAM++ 単独・
> same-utt の判定使用は禁止** (契約 §2 継承)。

**類似系**:

| 指標 | 必達 | 目標 | baseline (v10a-r2 **ep69**) |
|---|---|---|---|
| zs_ja holdout cross-utt SECS (CAM++) | **≥ 0.65** | 0.70 | 0.603 (ep69。参考: ep79 も 0.603)【実測】 |
| つくよみ OOD cross-utt SECS (CAM++) | **≥ 0.78** | 0.80 | 0.767 (ep69。参考: ep79 0.753)【実測】 |
| ECAPA 同調 | 必須 (goodhart_flag=false かつ ECAPA Δcross ≥ +0.01 **vs ep69** — zs_ja 0.518 / つくよみ 0.653【実測、v10-design §11】) | — | 契約 §3 |
| same/cross gap | **ep69 baseline 比** +0.01 以内 (ep69 値は Phase A 再測定で確定し manifest に pin) | 縮小 | 参考: ep79 0.078【実測】 |
| F0 ダイナミクス (つくよみ参照合成、判定は manifest 固定の合成条件) | std ≥ 45Hz かつ p5-95 ≥ 150Hz | GT 帯 (std 47-74 / 153-215Hz) | std 29-41 / 87-142Hz (ep79 解剖【実測】、ep69 値は Phase A で確定) |
| ABX (質問①話者類似、vs r2 ep69) | 10 中 7 以上 | — | 新設 (E-6) |

> 注: v10-design §6 の「zs_ja 0.70 必達 / 0.80 目標」は v10a 用の登録で、v10a-r2 は
> 0.603 で未達だった (§11)。v10b は残レバー (S-1 識別器 + S-3 データ) の文献期待値
> から**必達 0.65 / 目標 0.70** に再登録し、0.80 は v11 以降の到達目標に繰り延べる。
> 未達なら次の構造介入 (v10-design §7: CAM++ torch 化 + joint FT 等) を再設計し、
> 基準の事後緩和はしない。

**高域系** (E-4 の新物理量 — ゲーム不能量として登録、学習 loss 流用は E-8 で禁止):

| 指標 | 必達 | 現状 (r2 ep79 解剖) | GT |
|---|---|---|---|
| SR/128 格子コム超過 | **< 1.5dB** | 4.1-4.7dB | 0.65-0.76dB【実測】 |
| >4kHz 残差 autocorr @lag128/256 | **< 0.05** | 0.10-0.24 | ≈0.01-0.13【実測】 |
| 5.5-8.5kHz voiced 棚 (vs GT) | **≤ +2.0dB** (~1σ) | +3.0〜4.6dB | sd 1.8-2.7dB【実測】 |
| 同帯域・無声区間 (別枠、テキスト非統制の参考値) | ≤ +3.0dB | +4.6〜7.9dB | —【実測】 |
| 4-9kHz 帯域 (旧指標、互換維持) | **ep69 baseline (Phase A 再測定値) 比非悪化** | -10.5dB (ep79)【実測】 | — |
| ABX (質問②ざらつき、vs r2 ep69) | 10 中 7 以上 | — | 新設 (E-6) |

**推論コスト系** (必達 gate — 推論グラフに触るレバーが複数ある以上必須: H-1
resize+conv / H-2b taps 63→127 / S-2 pitch predictor + 励振 / 条件付き H-4。
製品制約は CPU リアルタイム + FP16 ~38MB + speaker_embedding [1,192]):

| 指標 | 必達 | baseline |
|---|---|---|
| CPU 推論レイテンシ p50 (固定ベンチ: 固定テキスト set + warmup 込み、decoder 単体と e2e の両方) | **v10a-r2 ep69 ONNX 比 +10% 以内** | Phase A でベンチし manifest に pin |
| ONNX ファイルサイズ (FP16) | **≤ 40MB** | 38MB (v10a-r2)【実測】 |
| ONNX 入力契約 | speaker_embedding [1,192] 不変 | 契約 |

> gate 超過時は該当レバーを不採用に戻す (fallback: H-1 は lowpass 初期化案、
> H-2b は taps 62 維持、S-2 は v10c 送り、H-4 は見送り)。gate の事後緩和はしない。
> H-1 は kernel 縮小 (k ∝ 1/stride) 込みで設計しないと MACs 約 4 倍/段になる
> (§3.1 H-1【算術】) ため、Phase B の実装時点でベンチを併走させる。

**中間監視** (本走中、R3 継承): 5ep 毎に prior 経路定点評価 (CAM++/ECAPA cross-utt +
コム 2 指標 + goodhart_flag)。ECAPA 乖離 abort は v10a-r2 の実装をそのまま使用。

### 4.4 交絡管理 (単変量原則との折り合い)

v10a は「v9 と同一データで学習信号のみ変更」の単一変数 run だったが、v10b は
from-scratch のコスト上、複数レバーを束ねざるを得ない。以下で切り分け可能性を担保:

| レバー群 | 分離検証の方法 |
|---|---|
| H-1/H-2 (デコーダ格子) | **学習前後で分離可能**: コム物理量は初期化直後から測定でき【文献 Pons ら + 推測】、合成段ユニットテスト (H-2a/H-5) は学習と独立。Phase D smoke でコム指標 pass が本走の前提条件 |
| S-1 (JCU + classifier) | ramp 開始 (KL annealing 後) の前後比較 + 5ep 毎 prior 経路監視で発症を時間的に分離 (v10a §10 の検出実績と同じ機構) |
| S-3 (データ) | 帯域ゲート (hi_ratio/fmax + E-1) で投入前に品質を統制。追加は Tier 単位の段階投入 |
| S-2 (F0 経路) | **本走に入れるのは Phase D の単独 arm smoke pass が条件** — 唯一、時期をずらして単変量を守るレバー |
| 万一の全体退行 | v10a-r2 ep69 が新ハーネス系列の対照として恒久保存済 (HF `checkpoints-v10a-r2/`) |

---

## 5. 不採用リスト (理由付き)

| # | 施策 | 不採用理由 |
|---|---|---|
| 1 | frozen-encoder cosine 形式の swap-SCL 再投入 | v10a §10 で prior 経路崩壊 (~6ep で発症、ECAPA 0.117) を実証【実測】。教訓①違反。話者監督は共進化識別器形式 (S-1) のみ |
| 2 | レベル系 spectral loss (MRD/MR-STFT) の係数増強のみでのコム除去 | v9→r2 でコム超過が +3.6-4.5 → +4.1-4.7dB と不変【実測】。周波数分解能が 10.8Hz 幅コムに構造的に鈍感 |
| 3 | 時間平滑化 / anti-flutter 系の対策 | 解剖で時間変調系は無罪と実測 (flux/変調とも GT 以下)【実測】。ざらつきは定常系 |
| 4 | UTMOS 等の参照フリー MOS を gate に追加 | クリーン FT 1.592 < がびがび v8.1 2.014 の逆転を実証済【実測、zero-shot-noise-root-cause-pqmf.md】 |
| 5 | F0/エネルギー統計・帯域・コム指標の学習 loss 化 (「韻律 loss」含む) | 教訓①。評価器の目的化は検出器の喪失。E-8 gate で機械的に block |
| 6 | E-9 時間変調指標の無条件契約入り | ラベル付きサンプルでの分離実証なしの指標増殖は PQMF 事故 (goalpost moving) の逆パターン。実証後のみ |
| 7 | 完全 prior 経路 cycle (MulliVC 型 text→enc_p→flow⁻¹) | コスト 3 倍級 + 初期不安定 (v10-design §3.1 の不採用を継承) |
| 8 | NaturalSpeech 3 型 factorization | 38MB / CPU-RT 制約下で大工事。v11 以降の検討事項【文献 arXiv:2403.03100】 |
| 9 | GRL / SC-CNN / mean_only=False / flow の Transformer+AdaLN 化 | v10-design §4 の不採用理由を継承 (λ 感度 / ORT 非適合 / 行列式爆発 / CPU コスト) |
| 10 | warm restart による v10a-r2 への後付け介入 | 教訓④: Phase 0/1 で計 7 介入全滅【実測】。v10b は from-scratch |
| 11 | raw SECS / same-utt / CAM++ 単独での判定・報告 | 契約 §2 + E-7。0.775 誤報事故 + v10a Goodhart の再発防止 |

**保留 (不採用ではない)**: StyleTTS 2 型 speaker-aware SLM-D (frozen WavLM 特徴 +
共進化 head + CAM++ emb concat、arXiv:2306.07691)【文献】 — 教訓①と両立する設計
(勝敗を決める head は共進化) だが学習 VRAM +数 GB。**S-1 が Phase D/E で不発の場合の
置換候補**として温存。H-4 (BigVGAN 型 anti-aliasing) も条件付き (§3.1)。

---

## 6. 出典

- **①帯域解剖 (実測)**: r2_ep79 / v9 / GT 計 17 ファイルの voiced 限定分析。
  スクリプト: scratchpad `quality_anatomy/{anatomy.py,verify_comb.py}`
  (Phase A の E-4 で `piper_train.tools` へ移植予定)。聴感サンプル: ローカル
  `piper-v8-dataset-backup/v10a_listen_samples/r2_ep79_tsukuyomi/`
- **②評価ハーネス監査**: `src/python/piper_train/tools/eval_zs_secs.py` /
  `measure_band_noise.py` / HF `diag-phase0/scripts/phase0_eval_arm.py` /
  `docs/spec/zs-eval-contract.md` の実装読解 (行番号は監査時点)
- **③類似系文献調査**: arXiv API + PDF 直接抽出 15 本 (WebSearch 予算枯渇時の代替、
  抽出テキストは scratchpad `papers/` に保存)。主要: GANSpeech 2106.15153 /
  StarGANv2-VC 2107.10394 / Meta-StyleSpeech 2106.03153 / StyleTTS 2 2306.07691 /
  Period VITS 2210.15964 / Daft-Exprt 2108.02271 / Mega-TTS 2 2307.07218 /
  VoxSim 2407.18505 / Deja et al. 2207.00344 / YourTTS 2112.02418 /
  Cooper et al. 1910.10838 / NaturalSpeech 3 2403.03100 / Seed-TTS 2406.02430 /
  BASE TTS 2402.08093 / HierSpeech++ 2311.12454
- **④高域ノイズ系文献調査**: arXiv 8 本精読 + ローカル実装読解。主要: Pons ら
  2010.14356 (upsampling artifacts) / BigVGAN 2206.04658。
  ※本レポートは要約 + 容疑序列 + 対策①までの受領 (伝送で後半欠落)。対策②③は
  解剖レポートの推奨 (iSTFT/PQMF 合成検証テスト、高分解能 discriminator/penalty の
  4-9kHz 限定追加) と整合するため、それらで補完した
- **v10a 実測**: [`zero-shot-v10-design.md`](zero-shot-v10-design.md) §9-11
  (係数較正 / swap-SCL インシデント / r2 最終スコア)、HF
  `ayousanz/piper-plus-zero-shot-multi-7lang-v8` の `v10a-results/` +
  `checkpoints-v10a-r2/`

## 7. Phase C-0: ライセンス実確認の結果 (2026-08-18、原文ベース)

| 候補 | 判定 | 根拠 (原文要旨) | 規模 |
|---|---|---|---|
| JVS | **不採用** (学習除外。評価もローカル参照のみ、合成サンプル公開不可) | 公開版は「非商用目的の研究に限り使用可能」+ 再配布不可。過去調査の「商用可」は**東大 TLO 経由の有償ライセンス営業案内の誤読**と決着 | 100 spk / 30h |
| **Emilia-YODAS (ja/ko)** | **採用可** (CC BY 4.0、attribution + 品質ゲート必須) | 権利者 Amphion が 3 文書 + HF タグで一貫して YODAS split = CC BY 4.0。KRAFTON README の逆表記は**行の取り違え** (上流 espnet/yodas2 が cc-by-3.0 の系譜とも整合)。残余リスク: YouTube 自己申告 CC 依存 (espnet が削除受付明記) / モデルカードでのデータセット単位帰属が義務 | ja ~0.8k h / ko ~7.2k h / 24kHz |
| Emilia 本体 (非 YODAS) | 不採用 | CC BY-NC 4.0 明記 | — |
| Common Voice ja | **採用可** | CC0 (HF メタデータ + 明文) | validated 380h / 7,859 voices |
| Zeroth-Korean | 不採用 (品質) | ライセンスは CC BY 4.0 で可だが fmax99 中央値 3.0kHz で案 Z ゲート不通過 (v9 事故の再現になる) | — |
| Pansori-TEDxKR | 不採用 | CC BY-NC-ND | — |
| CV ko | 補助のみ | CC0 だが validated 2.2h | — |
| KSS/MSSS 系 | 未確認 (調査打ち切り — ko は Emilia-YODAS で充足見込) | — | — |

**v10b データ構成案**: 現行 300,443 utts / 6 lang + **Emilia-YODAS ja (話者多様性)
+ Emilia-YODAS ko (7 lang 復活、pt と同オーダーの ≥30k utts を必須条件に cap 設計)
+ CV ja (CC0 属性補完)**。投入時の必須ゲート 3 点:

1. **案 Z ゲートを新データへ同一適用** (YODAS は低ビットレート AAC の 11-12kHz
   遮断が 22.05kHz Nyquist と接する — fmax999/hi_ratio を投入前に必ず測定)
2. **DNSMOS ≥ 3.0 で切る** (Emilia-Large 拡張分は 2.4 閾値で低品質が混入)
3. **擬似話者ラベルの post-filter** (Emilia の speaker はダイアライゼーション由来で
   誤マージあり — cross-utt SCL の正例定義を直撃するため、話者あたり発話数下限 +
   embedding クラスタ内分散でフィルタ)

設計原則: in-the-wild (YODAS) は**話者多様性用**、スタジオ品質 (moe-speech-plus)
は**音質の教師**として役割を分け、discriminator の real 定義を汚さない。

## 8. Oracle 診断 — アーキ律速の確定 (2026-08-18、ローカル CPU / $0)

「データを足す前にアーキの限界を測るべき」というユーザー指摘を受けた切り分け実験。
v10a-r2 ep69 で seen (学習話者 20) / holdout (未学習 ja 10) / つくよみ (OOD) を
同一プロトコル測定。生データ: scratchpad `oracle_diag/` (JSON 9 本 + 合成 103 wav)。

### 結論: **汎化律速ではなくアーキ (条件付け経路) 律速**

| 群 | cross-utt SECS | ceiling | 正規化転写率 |
|---|---|---|---|
| seen (学習済 20 名) | 0.610 | 0.787 | 0.372 |
| holdout (未学習 10 名) | 0.603 | 0.745 | 0.408 |
| つくよみ (OOD) | 0.767 | 0.884 | 0.639 |

- **seen − holdout = +0.007 (実質ゼロ)**。学習に入っていた話者を学習時と同一の
  embedding で条件付けしても実音声の 4 割しか話者性が出ない — 汎化の問題ではない
- **最強の証拠 (20 択話者識別)**: 実音声 top-1 98.5% → **合成音 43%**。中心化後も
  73% (分離度は実音声の 49%)。条件付け経路は「運べていないのではなく約 4 割しか
  運べない」(実話者間広がりの 69.6% 保持 / cond→synth 回帰傾き 0.66)
- **embedding 被覆はシロ**: つくよみの最近傍学習話者 cos 0.880 = 学習話者
  最近傍分布の 50.1 %ile — 「未知領域だから転写できない」は不成立
- **in-domain は最近傍インポスタ floor (0.662) を下回る (0.610)** — 合成音は目標
  話者より「最も似た別の学習話者」に近い。moe-speech ja 463 名が CAM++ 空間で
  密集していることが in-domain の見かけの難しさの正体 (つくよみが良く見えるのは
  疎な位置にいるため)
- 副次所見: 中心化で 43→73% に跳ねる = 目減りの一部は「合成音共通のドメイン
  オフセット」(synth/real クラウド間 cos 0.814) — デコーダ実音声化 (H 系) も
  SECS に効く二重取り構造

### Caveat

CAM++ 単独 (seen 群に実音声なし、群間差分診断としてのみ有効)。seen−holdout の
95% CI [−0.06, +0.07] — 上限を全部汎化に帰しても不足 0.142 の半分でありアーキ
律速の結論は不変。OOD は 1 話者。

### 分岐判断への含意 (§4 の実行計画は不変、解釈枠が更新される)

1. **gol-game (同ドメイン話者スケール) の優先度は下がる**: 学習済み話者すら識別
   できない状態で密集ドメインに話者を足しても改善しない (v7→v8 の失敗の機構的
   説明でもある)
2. **Emilia の位置づけを再定義**: 「汎化のため」ではなく「話者空間の広がりを
   増やして対比・敵対損失の学習信号の識別性を上げるため」— S-1 が信号を使える
   ことを確認してから
3. **v10b-lite の S-1 (JCU + 共進化 classifier) が本丸**: 「合成音から話者が
   識別できない (43%)」に対する直接の対抗圧力。v10b-lite の結果が
   「S-1 で識別性が上がるか」の単一検証になる — 上がれば信号不足だった、
   上がらなければ v11 で条件付け容量の本格改修 (注入の全面 AdaLN 化等)
4. **新診断の標準化**: seen 話者 20 択識別 top-1 は「条件付け経路の容量」を
   直接測るアーキ診断として v10b 以降の評価に加える価値あり (Phase E 中間評価
   で追跡すれば S-1 の効果が直接見える)
