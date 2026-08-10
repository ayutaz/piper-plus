# Zero-shot「がびがび」ノイズの根本原因調査 — PQMF 実装バグと 15 ヶ月見過ごされた経緯

> 調査日: 2026-08-10
> 対象ブランチ: `feat/zero-shot-v8-dataset-scaling`
> 調査手法: 信号分析 (スペクトログラム / 平均スペクトル / 波形 / HNR / CPPS / 変調解析) + 6 方向 multi-agent deep research (文献 5 + コード 1) + git 履歴のプロセス考古学
> 関連: [`zero-shot-v8-dataset-scaling-plan.md`](zero-shot-v8-dataset-scaling-plan.md) §3.15 (症状の一次調査) / §3.16 (v8.1 結果)

---

## 1. 症状 (確定した観測事実)

zero-shot 合成 (v8 / v8.1) の音声にユーザー聴感で「がびがび」ノイズ。信号分析で以下を確定:

| # | 観測 | 測定 |
|---|---|---|
| 1 | 有声音に広帯域ノイズが常時重畳 (波形の毛羽立ち、倍音間がノイズで埋まる) | 波形拡大 / スペクトログラム |
| 2 | 平均スペクトルで **5-9kHz に FT モデル比 +5〜10dB** の非構造エネルギー | active-frame 平均スペクトル |
| 3 | **同一アーキの single-speaker FT (Tsukuyomi 500ep) では消える** | 聴感 + スペクトル |
| 4 | WavLM discriminator 40ep 追加 (v8.1) でも不変 (UTMOS 1.43→2.01 と他面は改善) | v8 vs v8.1 平均スペクトル |
| 5 | 推論 noise_scale 0.2-0.667 掃引で不変 | UTMOS / スペクトル |
| 6 | 参照 embedding を学習話者 50 発話 centroid にしても不変 | UTMOS |
| 7 | UTMOS / HNR / jitter / shimmer / CPPS / 変調 roughness は FT との差を検出できない | 全指標実測 |

## 2. 根本原因 (最有力・実測確認済み): PQMF フィルタバンクの実装バグ

`src/python/piper_train/vits/mb_istft.py` の PQMF (4 帯域 pseudo-QMF) が canonical 設計
(Nguyen 1994 / kan-bayashi ParallelWaveGAN 実装) から逸脱している:

1. **コサイン変調の位相項 `(-1)^k·π/4` が欠落**、かつ**変調中心が `taps/2`(=31) でなく `subbands/2`(=2)** (mb_istft.py:66)

   ```python
   # 現行 (バグ):
   cos((2k+1) * π/(2M) * (n - M/2))
   # canonical:
   cos((2k+1) * π/(2M) * (n - taps/2) + (-1)^k * π/4)
   ```

2. この位相構造は隣接帯域のエイリアス (折り返し) 成分を合成時に打ち消すための必須条件であり、欠落により**エイリアスキャンセルが機能しない**

**実測 (roundtrip SNR、canonical 実装との比較、2 回独立に再現済み):**

| テスト信号 | piper 実装 | canonical 実装 |
|---|---|---|
| 白色雑音 | **7.5 dB** | 64.0 dB |
| 2756Hz トーン (帯域境界 1) | **-1.6 dB** (エラー > 信号) | 59.2 dB |
| 5512Hz トーン (境界 2) | **0.3 dB** | 59.2 dB |
| 8268Hz トーン (境界 3) | **12.1 dB** | 59.2 dB |

検証スクリプト: セッション scratchpad `pqmf_check.py` (torch 実装同士の A/B)。

**帯域境界 5512 / 8268 Hz が症状 2 の「5-9kHz」を正確にブラケットする** —
帯域特異性を直接説明できる唯一の仮説。合成経路は学習・推論・ONNX とも
`MBiSTFTGenerator.forward` → `self.pqmf.synthesis()` (mb_istft.py:333) を通るため、
v1.12.0 以降の**全 MB-iSTFT モデルがこの壊れたフィルタバンクを通っている**。

### なぜ single-speaker FT では消え、zero-shot では残り続けるのか

decoder はフィルタバンクの逆特性 (エイリアス事前補償) を学習できる。sub-band 出力の
位相は magnitude 系損失では拘束されないため、GAN/mel loss 経由で「合成後にエイリアスが
打ち消えるような sub-band 信号」を出力するよう適応する余地がある:

- **1 話者 FT**: その声の倍音配置専用の補償を decoder が獲得 → ノイズ消失
- **3,692 話者 zero-shot**: 補償は話者 (= g と倍音配置) ごとに異なる必要があるが、
  グローバル conditioning 経由では汎化せず → **未知話者で残留エイリアスがノイズとして露出**

これが「課題が残り続けた」メカニズムである。

### 症状との整合表

| 症状 | 整合 | 理由 |
|---|---|---|
| 1 有声音に常時ノイズ | ○ | 倍音が帯域境界を跨ぐたびミラー像 (2·f_edge − f) が倍音間に落ちる |
| 2 5-9kHz +5-10dB | ○ | 境界 5512/8268Hz がブラケット (帯域特異性を直接説明) |
| 3 FT で消える | ○ | 話者専用のエイリアス事前補償を decoder が学習 |
| 4 WavLM-D 不変 | ○ | WavLM は 16kHz リサンプル入力 (models.py:538 付近) で 8kHz 以上不可視 + 位相微細構造に鈍感 |
| 5 noise_scale 不変 | ○ | 決定論的なフィルタ段で発生 |
| 6 centroid 不変 | ○ | embedding と無関係 |
| 7 指標で検出不能 | ○ | 帯域限定エイリアス床は UTMOS(16kHz) / HNR(低域自己相関) 等と直交 |

## 3. 副次要因 (複合、v9 で併せて対処)

1. **5kHz 以上の敵対的監督の構造的不在**: MPD+MSD+WavLM のいずれも高域スペクトル微細
   構造の判別器ではない。multi-speaker mel L1 の one-to-many 平均化で高域が「平均
   エネルギーだけ合ったノイズ」に落ちる (Universal MelGAN / UnivNet / GANSpeech が
   MRSD/MRD 追加で解消した既知パターン)
2. **VITS train-inference mismatch**: decoder は posterior z のみで学習、推論は flow
   逆変換 prior (NaturalSpeech が指摘)。multi-speaker で gap 拡大。帯域特異性は説明
   できないため副次
3. **データ品質**: Zeroth-Korean の 16kHz ブラインドアップサンプル、CML-TTS の宅録
   品質、CV の可変ローパス — コーパス平均ノイズ床の学習 (増幅因子)

**棄却済み仮説**: prior sampling ノイズ単独 (症状 5)、slice 長過適合 (FT も同一 slice)、
FP16 export (FT も同一 export でクリーン、量子化床 -60dB は実測 -10dB 級より 5 桁小)、
embedding OOD (症状 6)。

## 4. なぜ実装が間違い、なぜ 15 ヶ月見過ごされたか (プロセス考古学)

**結論: テストは存在した (形式上 TDD だった) が、テストが red になった時に実装のバグを
疑わず「理論限界」と誤認して受け入れ基準の側を実測値に合わせて書き換えた** (goalpost
moving)。git 履歴 (PR #320、commit `29415b9e`、2026-05-03) に全経緯が残っている:

1. **要求定義 (正しかった)**: 当初の `mb-istft-vits2-requirements.md` には
   「**PQMF 残存 (エイリアス) -90dB**」という canonical 相当の受け入れ基準が書かれていた
2. **実装**: 参考実装 (MB-iSTFT-VITS / ParallelWaveGAN 系) からの移植時、
   「scipy 依存を削除、numpy.kaiser() に統一」するリライトの過程で変調式から
   位相項 `(-1)^k·π/4` が脱落し、変調中心も `taps/2` → `subbands/2` に化けた
3. **テスト実行 → red**: roundtrip SNR は 7-8dB しか出ない
4. **誤った合理化 (分岐点)**: レビュー対応コミットに
   「**D2: 要求定義 PQMF SNR 基準を -90dB → 5dB に修正 (理論限界文書化)**」
   「**requirements.md: PQMF 残存 -90dB → SNR > 5dB に統一**」と記録。
   *pseudo*-QMF の「near-perfect reconstruction」という用語を「数 dB の残留は正常」と
   誤解釈し、バグ実装の実測値 (7-8dB) を理論限界として要求定義とテストの両方に固定した。
   テスト docstring には「The neural network compensates for residual aliasing during
   training」という合理化がそのまま残った (test_pqmf.py:14-19)
   — 実際の cosine-modulated PQMF の理論限界は同一 Kaiser プロトタイプで **~60dB** であり、
   7-8dB は「理論限界」ではなく実装バグの実測値だった
5. **15 ヶ月の見過ごし**: 以後の全学習 (6lang base MB-iSTFT / Tsukuyomi FT / v7 / v8 /
   v8.1) がこのフィルタバンクで走った。**single-speaker 系では decoder 補償が効いて
   高品質に聴こえたため「decoder は正常」という信念が強化され続け**、multi-speaker
   zero-shot で初めて顕在化した。顕在化後も既製品質指標 (UTMOS 等) が全盲だった (症状 7)
   ため、聴感報告 (ユーザー) → 専用信号分析まで特定されなかった

### 再発防止の教訓

1. **テストが red になったとき、基準を実測に合わせて緩める前に「参照実装との数値比較」を
   必須とする** — 今回なら kan-bayashi PQMF と 5 分比較すれば 60dB vs 7dB で即バレした
2. **「NN が補償する」という合理化は、補償が汎化する条件 (単一話者) と汎化しない条件
   (zero-shot) を区別しない限り採用しない**
3. **DSP コンポーネント (フィルタバンク / STFT) は参照実装との bit/dB 一致テストを標準に**
   — 独自リライト (scipy→numpy 等) は逸脱の入口
4. **知覚品質のゲートには帯域別・機構別の専用メトリクスを併設** (UTMOS だけでは 5-9kHz
   エイリアスは永遠に不可視)。→ band-limited inter-harmonic SNR を評価 harness に常設

## 5. 確定のための検証実験 (優先順)

1. **subband ダンプ比較** (GPU 数分、最重要): zero-shot と FT の推論で PQMF 合成前の
   4 subband (`SynthesizerOutput.decoder_subbands` 経路) をダンプし、(a) 各 subband
   単体スペクトル vs (b) 合成後スペクトルを比較。ノイズが「合成後にのみ 5.5k/8.3k
   境界近傍に出る」なら PQMF 説確定
2. **copy synthesis (flow バイパス)**: `voice_conversion` 経路 (models.py:1167-1188)
   を同一話者 emb で呼び enc_q→dec 直結。残存→decoder/PQMF 側、消失→flow/prior 側
3. **band-limited inter-harmonic SNR のスクリプト化** (F0 整数倍 ±50Hz を harmonic と
   する 5-9kHz SNR) — 以後の全実験の追跡指標
4. noise_scale 0.0 / 1.0 の追加測定 (確率成分の完全排除)
5. 合成音の無音区間フロア + 学習 corpus 別 5-9kHz 分布 (データ説の分離)

## 6. 対策

### 検証確定前でも安全に入れられるもの (no-regret)

| 優先 | 対策 | 備考 |
|---|---|---|
| P0 | **PQMF を canonical 実装に修正** (位相項 + 変調中心 taps/2 + cutoff 見直し) + **テスト gate を SNR ≥ 55dB / 帯域端トーン ≥ 50dB に引き上げ** | コード修正自体は安全。ただし**既存 v8 系 ckpt は壊れたバンク前提で学習済みのため、修正バンクへの単純差し替えは音が崩れる** — 再学習または decoder 再適応 FT が必須 |
| P1 | full-band 線形周波数 MR-STFT loss (`c_full_stft`) を o vs y に追加 | `MultiResolutionSTFTLoss` 実装済で配線のみ |
| P2 | UnivNet 型 MRD (multi-resolution spectrogram discriminator) を **22.05kHz ネイティブ**で追加 | WavLM-D の増強は打ち切り (16kHz 盲点が構造的) |
| P3 | speaker embedding の学習時 null dropout (10%) | 数行、CFG 的効果 |
| P4 | band-limited inter-harmonic SNR を eval harness に常設 | |
| P5 | FP16 export の keep 対象に PQMF/iSTFT 係数を追加 | バンク修正後に効く微修正 |

### 原因確定後 (v9 設計)

- **修正バンク + MRD + full-band loss での v9 再学習** (v8 ckpt からは decoder +
  subband_conv_post の再適応 FT を先に検証 — 成功すれば全損回避)
- F0 条件付き sine source (Period VITS / VISinger2 型) — voiced 帯域のノイズ充填を
  構造的に禁止
- データ 4 層ゲート: bandwidth 推定 (fmax ≥ ~10.5kHz、Zeroth のアップサンプル遮断) →
  per-utterance UTMOS/DNSMOS → 落選話者は restoration 救済 → 品質メタを jsonl に保存
- 条件付け更新: CFG dropout (即効) → 参照 mel style encoder → (長期) mel + universal
  vocoder の 2-stage 化
- 製品仕様として「zero-shot (プレビュー) + 少量 FT (production)」の 2 段構えを明文化
  (Tsukuyomi FT SECS 0.775 で実証済み)

## 7. 参照

- 実装: `src/python/piper_train/vits/mb_istft.py` (バグ: L60-67 変調式 / 合成経路: L333)
- テスト: `src/python/tests/test_pqmf.py` (誤った 5dB gate: L13-32)
- プロセス記録: commit `29415b9e` (PR #320) メッセージ内
  「D2: 要求定義 PQMF SNR 基準を -90dB → 5dB に修正 (理論限界文書化)」
- canonical 参照: kan-bayashi/ParallelWaveGAN `parallel_wavegan/layers/pqmf.py`
  (Nguyen 1994, "Near-perfect-reconstruction pseudo-QMF banks")
- 文献: Universal MelGAN / UnivNet (MRD) / NaturalSpeech (train-inference mismatch) /
  BigVGAN (anti-aliasing) / HiFiTTS-2 (bandwidth filtering)
