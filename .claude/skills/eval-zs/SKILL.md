---
name: eval-zs
description: zero-shot TTS の話者類似度 (SECS) 評価を正しい方法論 (cross-utterance + dual-encoder + ceiling/floor + Goodhart 検知 + 帯域 + 聴感) で実行する標準手順。ckpt/ONNX の評価・モデル比較・go/no-go 判定はすべて本 skill 経由で行う。same-utt 単独判定の 0.775 誤報事故 (2026-08) の再発防止。
argument-hint: "<model.onnx|ckpt> [--baseline <前回 eval JSON>] [--refs <参照 wav dir>]"
disable-model-invocation: false
allowed-tools: Bash(uv run *) Bash(ls *) Bash(python *) Read Grep
---

# Zero-Shot SECS 評価 Skill

zero-shot モデルの話者類似度評価・比較・判定の標準手順。契約は
[docs/spec/zs-eval-contract.md](../../../docs/spec/zs-eval-contract.md)、背景は
[docs/design/zero-shot-warm-restart-diagnostics-phase0-1.md](../../../docs/design/zero-shot-warm-restart-diagnostics-phase0-1.md)。

## なぜこの手順が必須か (2 つの実事故)

1. **same-utt 0.775 誤報**: 条件付けに使った発話と同じ発話で SECS を測ると、
   SCL (訓練目的関数) の再測定になり「全然似ていない」モデルでも高く出る
2. **Phase 0 Arm B の偽改善**: c_spk 増で CAM++ (訓練と同型) だけ +0.023、
   held-out の ECAPA は横ばい — 単一 encoder では改善と Goodhart を区別できない

## 手順

### 1. 参照の準備 (cross-utterance の担保)

- 条件付け (embedding 抽出) に使う発話と、SECS を測る同一話者発話は**別**にする
  (`--exclude-ref` が自動で除外)。できれば複数発話の平均
- ceiling 用: 同一話者の実発話ペア / floor 用: 声質の近い別話者 (`--floor-refs`)

### 2. 評価実行 (canonical CLI)

```bash
uv run python -m piper_train.tools.eval_zs_secs \
    --synth-dir <合成 wav dir> \
    --speaker-utts <同一話者の実発話 dir> \
    --exclude-ref <条件付けに使った wav> \
    --floor-refs <近い声質の別話者 wav dir> \
    --encoder <campplus.onnx> \
    --encoder2 <ecapa.onnx> \
    --require-encoder2 \
    --meta-json <合成条件.json> \
    --json-out <結果.json> \
    [--baseline-json <前回の結果.json>]
```

- **`--encoder2` は必須** (guard-bash hook が encoder2 なし実行を block する)。
  ECAPA は SCL への組み込み恒久禁止 (held-out 判定器を汚さない)
- モデル比較・改善判定時は **`--baseline-json` 必須** — encoder ごとの Δ と
  goodhart_flag が自動判定される (v3 baseline なら音響 Δ も情報表示)
- **`--meta-json` で合成条件 (noise_scale / noise_scale_w / seed / texts) を固定**
  — v10b §4.3 の事前登録判定は manifest に pin した合成条件・ファイル集合で行う
  (noise_scale 掃引や多参照平均は探索専用、判定には使えない)
- 帯域 (E-1/E-2) ・コム (E-4) ・韻律 (E-3) は eval JSON の band/comb/prosody
  ブロックに**内蔵** (default ON、v10b Phase A で `/publish-model` フェーズ 3.5
  併走から移行)。SECS だけ欲しい高速 run のみ `--skip-acoustics`

### 3. 判定ルール (事前登録、変更禁止)

| ルール | 内容 |
|---|---|
| cross-utt のみ | same_utt_secs は参考値。判定への使用は**禁止** |
| 正規化転写率 | `(SECS - floor) / (ceiling - floor)` で解釈 (ja 女性 floor は 0.69-0.74 と高い) |
| **headline** | 報告の headline は **normalized_transfer** (+floor/ceiling 併記)。raw SECS / CAM++ 単独 / same-utt を headline にすることは**禁止** (契約 §2、stdout の HEADLINE 行がそのまま使える) |
| dual-encoder 同調 | primary Δ >= +0.02 でも encoder2 Δ < +0.01 なら **Goodhart 棄却** (`goodhart_flag: true`) |
| **above_ceiling** | `above_ceiling_flag: true` (cross > ceiling) は録音特性複製シグナル — goodhart 同様**改善と報告しない** (契約 §3.2) |
| gap 監視 | `gap_same_minus_cross` の拡大 = Goodhart 成分の増大。baseline 比 +0.01 以上で警告 |
| 対照必須 | SECS は ±0.01/ep 揺れる。**対照 run なしの +0.03 は判定不能** |
| **相関上限** | SECS↔人間類似の相関上限は LCC≈0.75-0.78。**±0.03 未満の SECS 差は人間類似の判定材料にしない** (契約 §3.3) |
| 4 点セット | SECS 単独 go/no-go 禁止 — ①正規化転写率 ②encoder2 ③帯域/コム物理量 ④聴感 (SNAC 論文: SECS で負け SMOS で勝つ系が実在)。①〜③は eval_zs_secs の **1 JSON に集約済み** (v3: encoders + band/comb/prosody ブロック) |

### 3.5 音響ブロックの読み方 (v3、事前登録値は契約 §6)

| JSON パス | 指標 | v10b 事前登録 (synth median に適用) |
|---|---|---|
| `comb.synth.comb_excess_db_median` | SR/128 格子コム超過 (ざらつきのゲーム不能量) | **< 1.5dB** (GT 帯 0.65-0.76dB) |
| `comb.synth.hf_autocorr_lag128/256_median` | >4kHz 残差のフレーム周期性 | **< 0.05** |
| `band.delta.shelf_voiced_max_delta_db` | 5.5-8.5kHz voiced 棚 (vs real anchor) | **≤ +2.0dB** (無声別枠 ≤ +3.0dB) |
| `band.synth.voiced_hi_excess_db_median` | 4-9kHz 旧指標 (互換維持) | ep69 baseline 比**非悪化** |
| `prosody.synth.f0_std_hz` / `f0_range_p5_p95_hz` | 韻律の平板さ (絶対値) | **≥ 45Hz / ≥ 150Hz** (GT: 47-74 / 153-215Hz) |
| `prosody.delta.*` | synth − real の記述統計差 (類似スコアではない) | 診断用 (負の f0_std delta = synth が平板) |

- gate は **synth 側のみ** (real/GT は文脈表示 — GT の per-file autocorr は 0.13
  まで出る)。測定は**素の出力 wav** (後処理禁止 — 契約 §2 禁止事項 5)
- **教訓①**: これらのメトリクスを学習 loss に流用することは恒久禁止
  (契約 §2 禁止事項 4、pre-commit `zs-metric-isolation-gate` が機械 block)

### 4. 報告フォーマット

結果は必ず「**normalized_transfer (headline)** / cross-utt SECS / encoder2 /
gap / 帯域・コム / 聴感」を併記し、baseline 比較なら goodhart_flag と
above_ceiling_flag の値を明記する。

## 再発防止の多層ガード (本 skill 以外)

- hook `guard-bash.sh`: `--encoder2` なしの eval_zs_secs 実行を block
- pre-commit `zs-prevention-gate`: 防止テスト群と評価ガード面の削除・改名を検出
- pre-commit `zs-metric-isolation-gate`: 学習コードからの評価メトリクス import
  + メトリクスモジュールの torch import を block (教訓①の機械的強制)
- `/publish-model` フェーズ 3.5: 公開前の帯域 + cross-utt SECS gate
- 単体テスト: `test_eval_zs_secs.py` (goodhart_flag 判定ロジック含む) +
  `test_measure_comb_artifacts.py` / `test_measure_prosody.py` /
  `test_measure_band_noise.py` (音響メトリクスの数学 pin)
