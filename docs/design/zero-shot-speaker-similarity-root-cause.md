# Zero-Shot 話者類似度の根本原因調査 (v9、2026-08-12/13)

> **Status**: 調査完了 (層の特定 + 機構の絞り込みまで)。対策は未着手 — deep research
> の結果を踏まえて v10 / 継続学習で対応する。
> がびがび (ノイズ) 側の canonical は
> [`zero-shot-noise-root-cause-pqmf.md`](zero-shot-noise-root-cause-pqmf.md)、
> 時系列の文脈は
> [`zero-shot-v8-dataset-scaling-plan.md`](zero-shot-v8-dataset-scaling-plan.md) §3.19。

## TL;DR

- v9 zero-shot は OOD 参照 (つくよみちゃん) で **cross-utterance SECS 0.73** —
  同一話者 ceiling 0.888 / 日本語女性別話者 floor 0.69-0.74 に対して **floor すれすれ**。
  聴感「全然似ていない、多少女性っぽいだけ」と一致
- 当初報告した 0.775 は **same-utterance 測定による誤報** (SCL Goodhart で膨張)。
  以後、SECS は cross-utterance + ceiling/floor 併記を必須とする
- **無罪確定**: EMA / FP16 / ONNX export graph (4-way A/B) / embedding 抽出 /
  参照音声の質・量。**有罪**: v9 モデル本体の話者転写能力
- epoch 軌跡は **ep35 で飽和** (0.672 → 0.735 → 0.725) — 同一 config の追加学習
  では回収不可。主因候補は loss バランス (MRD+full-band STFT が SCL/DINO を押し負けた)
  とデータ話者多様性

## 1. 症状と発端

つくよみちゃんコーパス VOICEACTRESS100_094 (96kHz float / スタジオ品質 / 学習
コーパス外) を参照に v9 ep49 ONNX で zero-shot 合成 → ユーザー聴感:
「まだがびがびが出ている」「リファレンスに全然似ていない。多少女性っぽい程度」。

一方、事前に報告していた SECS は 0.759-0.797 (平均 0.775) で「FT モデル同水準」—
聴感と数値の重大な乖離が発端。

## 2. 測定方法の訂正 — same-utterance SECS は無効 (最重要の教訓)

当初の 0.775 は「**条件付けに使った同じ発話** (094) の embedding」と「合成音の
embedding」の cosine だった。v8.1/v9 は SCL (InfoNCE) で
*生成音声の CAM++ embedding ≈ 条件 embedding* を直接最適化しているため、
この測定は**訓練目的関数そのものの再測定**になり、話者が似ていなくても高く出る
(Goodhart)。

**正しい測定 (canonical rule)**:

1. **cross-utterance**: 参照とは別の同一話者発話 (できれば複数の平均) との cosine
2. **ceiling 併記**: 同一話者の実発話同士の cosine (今回 0.888)
3. **floor 併記**: 声質の近い別話者との cosine (今回 ja 女性 holdout で 0.69-0.74。
   ja 女性声は CAM++ 空間で密集しており floor が想像より高い)
4. 判断は正規化転写率 `(SECS - floor) / (ceiling - floor)` で行う

ルールは `.claude/skills/publish-model/SKILL.md` フェーズ 3.5 に成文化済み。

**正直な測定値 (2026-08-12、他 4 発話平均)**:

| 測定 | cross-utt SECS | 正規化転写率 |
|---|---|---|
| 同一話者 ceiling | 0.888 | 1.0 |
| v8.1 ep39 zero-shot | 0.777 | ~0.4 |
| v9 ep49 zero-shot | **0.73** | **~0.2** |
| 別話者 floor | 0.69-0.74 | 0.0 |
| v9 + 20 発話平均 emb | 0.765 | ~0.3 (改善僅か) |

## 3. 容疑者の排除 (すべて実測)

### 3.1 推論経路 — 4-way A/B で無罪

同一 embedding (094)・同一テキスト 3 文・同一 scales (ns=0.667/nsw=0.8)、
instance A100 上で実施:

| 経路 | same-utt | cross-utt | 4-9kHz 帯域 |
|---|---|---|---|
| raw ckpt fp32 (torch) | 0.734 | 0.725 | -15.5 dB |
| EMA fp32 (torch) | 0.747 | 0.743 | -15.9 dB |
| ONNX fp32 (EMA 込み export) | 0.766 | 0.759 | -17.7 dB |
| ONNX fp16 (配布物) | 0.755 | 0.731 | -17.6 dB |

- 全経路で cross-utt が横並び → **EMA も FP16 も export graph も類似度を毀損していない**
- 高域エネルギーはむしろ ONNX が ~2dB 低い → **がびがびも export 起因ではない**
- 聴感確認用 wav: `piper-v8-dataset-backup/v9_listen_samples/tsukuyomi_ab/`

### 3.2 embedding 抽出 — 無罪

- 判別力サニティ: cos(つくよみ, ko 男性) = **0.14** (適切に低い)、
  cos(ja 女性 holdout 同士) = 0.63
- 96kHz 入力の経路差: 直行 96k→16k vs 22.05k 経由 = cos **0.9999**
- クリッピングなし (peak 0.459、+12dB 版でも float WAV)

### 3.3 参照音声の質・量 — 無罪

20 発話の平均 embedding (cos(avg20, 094) = 0.941) でも v9: 0.73 → 0.765、
v8.1: 0.777 → 0.782 と改善は僅か。**参照を増やしても ceiling には近づかない**。

## 4. epoch 軌跡 — ep35 で飽和 (学習不足説の棄却)

raw ckpt、同一条件でのつくよみ cross-utt SECS:

| epoch | cross-utt SECS |
|---|---|
| ep23 | 0.672 |
| ep35 | **0.735** |
| ep49 | 0.725 |

ep23→35 で +0.06 伸びた後、**最後の 15 epoch は横ばい〜微減**。v8.1 の 0.777 に
届かないまま飽和 → 同一 config で epoch を積んでも回収の見込みは薄い。

### 機構仮説 (deep research で検証予定)

1. **loss バランス** (有力): v9 で新設した MRD + full-band MR-STFT がスペクトル
   忠実度に生成器容量と勾配を割き、話者条件付け (SCL InfoNCE / DINO) が相対的に
   押し負けた。「がびがび改善」と「SECS 退行 (0.712→0.652)」が v9 で同時に起きた
   ことと整合
2. **データ話者多様性**: 案 Z ゲートで 346k→300k utts に絞った際の話者分布変化
3. **構造上の上限**: v8.1 でも正規化転写率 ~0.4 — global-g 条件付け
   (`g = spk_proj(emb) + lang_emb` を enc_p / dp / flow / dec-FiLM に注入) の
   表現力の限界。lang_emb と話者条件が**加算で同一チャネルを共有**している点も
   干渉候補

## 5. 対策オプション

| 案 | 内容 | コスト | 期待値 / リスク |
|---|---|---|---|
| A | c_spk / c_dino 強化で ep49 から warm restart +20-30ep | ~$60-90 | 飽和の主因が loss バランスなら効く。v8.1 水準 (0.78) 止まりのリスク |
| B | つくよみ FT (v9 ベース、100 発話) | ~1h / 数ドル | 特定話者の正道。がびがび残存も decoder 適応で軽減見込み |
| C | v10 で条件付け構造 + データ + 韻律を本格改修 | 要設計 | deep research の結果待ち |

プロダクト設計は従来どおり「**FT 主、zero-shot 補完**」— zero-shot は「参照に
寄った声」まで、確実に似せる用途は FT。

## 6. 教訓

1. **SECS は cross-utterance でしか測らない** (§2)。訓練目的関数と同型の指標を
   評価に使うと Goodhart で必ず膨張する
2. がびがび同様、**単一数値指標は聴感の代替にならない** — ceiling/floor の
   ない類似度スコアは解釈不能
3. 「良かったサンプル」と「悪いサンプル」の生成条件 (推論経路 / embedding /
   scales) が揃っていない比較から結論を出さない — 今回は 3 交絡を A/B で分離して
   初めて層を特定できた

## 7. 再現方法

- 分離実験 (ローカル): scratchpad `tsukuyomi_debug.py` (帯域指標 + 正直 SECS +
  抽出経路検証)
- 4-way A/B (instance): scratchpad `v9_ab_test.py` → `/data/piper/eval-v9-ab/`
- epoch 軌跡 (instance): scratchpad `v9_secs_trajectory.py`
- モデル: HF `ayousanz/piper-plus-zero-shot-multi-7lang-v8` (`checkpoints-v9/` +
  `onnx/v9-zs-ep49.onnx`)
