# Zero-Shot 話者評価契約 (zs-eval-contract)

> **Status**: v10 で制定 (2026-08-14)、Phase A (v10b) で音響メトリクスへ拡張
> (2026-08-16)。zero-shot 話者類似度・音質の評価は本契約に従う。
> ツール実装: `src/python/piper_train/tools/eval_zs_secs.py` (schema `zs-eval-v3`)
> + `measure_comb_artifacts.py` / `measure_band_noise.py` / `measure_prosody.py` /
> `acoustic_frames.py` (いずれも EVAL-ONLY)。
>
> **根拠**:
> - [`docs/design/zero-shot-warm-restart-diagnostics-phase0-1.md`](../design/zero-shot-warm-restart-diagnostics-phase0-1.md)
>   — Phase 0 Arm B が「SCL same-utt 正例 = Goodhart」の直接の実験的証拠
>   (CAM++ +0.023 / held-out ECAPA +0.002 / gap 拡大)
> - [`docs/design/zero-shot-v10-design.md`](../design/zero-shot-v10-design.md) §1 F9
>   — SNAC 論文自身が「YourTTS の高 SECS は SCL 直接最適化の結果」と指摘
>   (SECS 単独ゲート禁止の文献的裏付け)
> - [`docs/design/zero-shot-speaker-similarity-root-cause.md`](../design/zero-shot-speaker-similarity-root-cause.md)
>   — same-utt SECS 0.775 誤報事故 (cross-utt では 0.73 = floor すれすれ)
> - [`docs/design/zero-shot-v10b-quality-plan.md`](../design/zero-shot-v10b-quality-plan.md)
>   — §1 実測解剖 (フレーム格子トーンコム = ざらつき / F0 std が GT の 6 割 =
>   平板さ) と §2 評価アップグレード E-1〜E-8、§4.3 事前登録判定基準

## 1. 必須メトリクス

zero-shot モデルの話者類似度・音質を報告・判定する際は、以下を**全て**測ること:

| メトリクス | 定義 | 測定手段 |
|---|---|---|
| **cross-utt SECS** (主指標) | synth と「同一話者の**別発話**」(exclude-ref 除外後) の平均 cosine | `eval_zs_secs` `cross_utt_secs` |
| **ceiling / floor** | 同一話者の実発話同士 / 近い声質の別話者との平均 cosine (cosine スケールの encoder 非互換を吸収) | `eval_zs_secs` `ceiling` / `floor` (`--floor-refs`) |
| **正規化転写率** (報告 headline) | `(cross_utt − floor) / (ceiling − floor)`。**この定義が normative** — 散在ハーネス (HF diag-phase0 等) は今後 `eval_zs_secs.compute_secs_report` を import して使うこと (定義の 1 アーティファクト化)。`ceiling <= floor` では未定義 (null + 警告、floor 選定を疑う) | `eval_zs_secs` `normalized_transfer` |
| **same/cross gap** | `same_utt_secs − cross_utt_secs`。SCL Goodhart で膨らむ成分の直接観測 | `eval_zs_secs` `gap_same_minus_cross` |
| **第 2 encoder** | held-out encoder (ECAPA) での同上指標。SCL に組み込むことは**恒久禁止** (held-out 判別器として維持) | `eval_zs_secs` `--encoder2` (+ `--require-encoder2`) |
| **4-9kHz 帯域** | PQMF 帯域境界近傍の非構造エネルギー (がびがび gate)。UTMOS/HNR はこのノイズに全盲 | `eval_zs_secs` band ブロック `voiced_hi_excess_db_median` / `measure_band_noise` |
| **SR/128 格子コム超過** | highpass(4kHz) 後平均スペクトルのフレーム格子周波数 (172.266Hz 整数倍、4-8.5kHz の 26 bins) の peak (±1bin) − 近傍 (±4〜8bin) median [dB] の算術平均 (`comb_excess_db`)。フレーム格子トーンコムのゲーム不能量 | `eval_zs_secs` comb ブロック / `measure_comb_artifacts` |
| **>4kHz 残差 autocorr @128/256** | highpass(4kHz) 後全長 autocorr の `abs(ac[128])` / `abs(ac[256])` (lag = hop//2, hop) | 同上 |
| **帯域プロファイル + 5.5-8.5kHz 照準値** | 1kHz ベクトル (rel 1-3kHz voiced) + shelf max Δ vs real (rel 0-4kHz voiced、500Hz bin 6 本の max) + 無声別枠 + per-frame 分布 (バースト希釈の防止) | `eval_zs_secs` band ブロック / `band_profile` |
| **prosody_delta** | F0 (std / p5-95 レンジ / median / moments) ・エネルギー・話速 proxy の記述統計差 (synth − real)。**類似スコアではない** — 単一スカラーへ潰さない | `eval_zs_secs` prosody ブロック / `measure_prosody` |

## 2. 禁止事項

1. **same-utt SECS 単独判定の禁止**: 条件付けに使った発話と同じ発話との cosine は、
   SCL が「生成音の embedding を参照 embedding に一致させる」よう学習しているため、
   話者が似ていなくても高く出る (0.775 誤報事故)。`same_utt_secs` は参考値のみ。
2. **primary encoder (CAM++) 単独判定の禁止**: SCL と同型の encoder は Goodhart に
   脆弱 (Phase 0 Arm B)。go/no-go には held-out 第 2 encoder の同調が必須。
   publish/CI ゲートでは `--require-encoder2` を付ける (未指定は exit 2)。
3. **ECAPA (第 2 encoder) の SCL への組み込み禁止**: held-out 判別器として
   機能し続けるための恒久ルール (診断 doc §5-4)。
4. **評価メトリクスの学習流用の恒久禁止**: 本契約の全メトリクス (cross/same SECS、
   band / band_delta / voiced_hi_excess / コム物理量 (`comb_excess_db` /
   hf_autocorr) / prosody_delta / 変調系を含む) を学習 loss・reward・学習中の
   動的サンプル選別に流用することを恒久禁止する (オフライン前処理のデータゲートは
   対象外)。**F0/エネルギー統計の「韻律 loss」化は明示 ban** (微分可能化が容易で
   流用誘惑が最も強い)。機械的強制: `scripts/check_zs_metric_isolation.py`
   (pre-commit `zs-metric-isolation-gate`) が `piper_train/vits/` と
   `piper_train/__main__.py` からのメトリクスモジュール import を block し、
   メトリクスモジュール自身の torch / `piper_train.vits` import も block する
   (微分可能化の入口を構造的に閉じる)。加えて各モジュール docstring の
   `EVAL-ONLY` マーカー + 本条項で三重固定。
   **境界定義 (S-2 例外)**: GT 波形・GT frame-level F0 など「GT を教師とする
   回帰 loss」(mel / STFT / MRD / S-2 の pitch predictor 回帰) は本禁止の対象外 —
   禁止対象は「評価器 (frozen encoder / 本契約の統計量) を目的関数化する」ことで
   あり、GT 参照 loss は評価器を消費しない (v10b plan §2.2 の表を normative と
   する)。
5. **raw 出力での測定規則**: band / comb / prosody は export 済み ONNX (または
   ckpt infer) の**素の出力 wav** で測る。測定前の EQ / デノイズ / ラウドネス
   正規化 / トリム等の後処理を挟むことを禁止 (ツール内部の RMS 正規化と
   22.05kHz への resample のみ許可)。gate 回避目的の後段フィルタは PQMF 事故
   ([docs/design/zero-shot-noise-root-cause-pqmf.md](../design/zero-shot-noise-root-cause-pqmf.md))
   と同型の偽装であり、発見した場合は測定無効。

## 3. goodhart 系 flag (flag family)

goodhart 系 flag は 2 本ある: `goodhart_flag` (baseline Δ 判定) と
`above_ceiling_flag` (録音特性複製シグナル)。**どちらか true なら改善と報告して
はならない**。

### 3.1 goodhart_flag

`--baseline-json <過去の eval JSON>` 指定時、encoder ごとの Δ (現在 − baseline)
を計算し、以下で機械判定する (Phase 0/1 の事前登録閾値をそのまま制度化):

| 条件 | goodhart_flag |
|---|---|
| primary (campplus) Δcross **>= +0.02** かつ encoder2 Δcross **< +0.01** | `true` (+ stderr 警告)。「SCL と同型の encoder だけが動いた」= 改善と判定しないこと |
| 両 Δ が計算可能で上記条件を満たさない | `false` |
| どちらかの Δ が計算不能 (encoder2 欠落など) | `null` (判定不能) |

付随警告: いずれかの encoder の `gap_same_minus_cross` が baseline 比 **+0.01 以上
拡大**した場合も stderr に警告し、`gap_widened_encoders` に encoder 名を列挙する
(same-utt 過適合の兆候)。

### 3.2 above_ceiling_flag (E-7(iii))

encoder ブロックの `cross_exceeds_ceiling` = `cross_utt_secs > ceiling`
(ceiling が null なら null)。トップレベル `above_ceiling_flag` は primary
(campplus) の値。true = 「synth が実発話ペアより参照に近い」— 話者類似ではなく
**録音特性 (チャネル・部屋・マイク) の複製**の疑い (YourTTS arXiv:2112.02418 で
既知のパターン)。stderr 警告が出る。`goodhart_flag` の意味 (baseline Δ 判定、
baseline なしなら null) は v2 から**不変更** — 2 本は独立の field。

### 3.3 SECS↔人間類似の相関上限 (E-7(ii))

SECS と人間の類似判定の相関上限は utterance-level LCC≈0.75-0.78
(VoxSim arXiv:2407.18505 / Deja et al. arXiv:2207.00344)。**±0.03 未満の SECS 差は
人間類似の判定材料にしない** (encoder ノイズと区別できない)。判定には正規化転写率
+ 聴感 (ABX) を併用する。

## 4. JSON schema (`zs-eval-v3`)

v1 → v2 → v3 は **field 追加のみ**の後方互換 (v2 の読み手は追加 field を無視
できる。v3 の読み手は v1/v2 JSON の欠落 field を null 扱いで読める)。未計測の
指標は**キー欠落ではなく null 明示**。

```jsonc
{
  "schema": "zs-eval-v3",
  "goodhart_flag": null,              // baseline 比較時のみ true/false、それ以外 null
  "above_ceiling_flag": false,        // v3 新設 (§3.2)。primary の cross > ceiling
  "encoders": {
    "campplus": {
      "cross_utt_secs": 0.6521,
      "same_utt_secs": 0.7103,        // 参考値のみ (判定使用禁止)
      "gap_same_minus_cross": 0.0582,
      "ceiling": 0.8880,
      "floor": 0.5210,
      "normalized_transfer": 0.3572,
      "cross_exceeds_ceiling": false, // v3 新設 (§3.2)
      "n_synth": 10,
      "n_refs": 9
    },
    "encoder2": { /* 同構造 (ECAPA) */ }
  },
  "manifest": {                       // v3 新設 (E-5(i)): 事前登録判定の「固定」
    "synth":        {"dir": "synth/", "files": [{"file": "t0.wav", "sha256": "..."}]},
    "speaker_utts": {"dir": "spk/", "files": [/* 除外後の cross set */]},
    "excluded_by_hash": [{"file": "ref.wav", "sha256": "..."}],
    "floor_refs":   {"dir": "floor/", "files": [/* ... */]},   // なければ null
    "floor_selection_note": "same-lang 近接話者 5 名",          // なければ null
    "exclude_ref":  {"file": "ref.wav", "sha256": "..."},       // なければ null
    "encoders": {"campplus": {"path": "...", "sha256": "..."}, "encoder2": null},
    "synthesis": { /* --meta-json の verbatim 埋め込み */ }     // なければ null
  },
  "band": {                           // v3 新設 (E-1/E-2)。--skip-acoustics / 解析不能なら null
    "params": {"sr": 22050, "n_fft": 2048, "hop": 256,
               "profile_ref_band_hz": [1000, 3000], "shelf_ref_band_hz": [0, 4000],
               "shelf_band_hz": [5500, 8500], "hi_band_hz": [4000, 9000]},
    "synth": { /* band_group_summary + voiced_hi_excess_db_median */ },
    "real":  { /* 同上 (anchor = 除外後 speaker-utts) */ },
    "delta": { /* band_delta_vs_real: band_delta_vs_real_1khz[11] +
                  shelf_voiced_max_delta_db + shelf_unvoiced_max_delta_db 等 */ }
  },
  "comb": {                           // v3 新設 (E-4)
    "params": {"grid_hz": 172.265625, "band_hz": [4000, 8500], "highpass_hz": 4000,
               "n_fft": 2048, "hop": 256, "autocorr_lags": [128, 256]},
    "per_file": [{"file": "t0.wav", "comb_excess_db": 4.31,
                  "hf_autocorr_lag128": 0.18, "hf_autocorr_lag256": 0.12}],
    "synth": {"comb_excess_db_median": 4.31, "hf_autocorr_lag128_median": 0.18,
              "hf_autocorr_lag256_median": 0.12},
    "real":  { /* GT anchor の文脈表示用 (gate は synth のみ、§6) */ }
  },
  "prosody": {                        // v3 新設 (E-3)
    "params": {"f0_estimator": "librosa.pyin", "fmin": 70, "fmax": 600,
               "frame_length": 2048, "hop": 256},
    "synth": { /* prosody_group_summary (median across clips) */ },
    "real":  { /* 同上 */ },
    "delta": { /* prosody_delta = synth − real の記述統計差 */ }
  },
  "baseline_comparison": {            // --baseline-json 指定時のみ
    "baseline_path": "prev_report.json",
    "goodhart_flag": false,
    "gap_widened_encoders": [],
    "deltas": {
      "campplus": { "cross_utt_secs": 0.0034, "gap_same_minus_cross": -0.0021 },
      "encoder2": { "cross_utt_secs": 0.0028, "gap_same_minus_cross": null }
    },
    "acoustics": {                    // v3 新設 (§4.6): baseline が v1/v2 なら null
      "comb_excess_db_median": -0.42, "hf_autocorr_lag128_median": -0.03,
      "hf_autocorr_lag256_median": -0.02, "voiced_hi_excess_db_median": -1.1,
      "shelf_voiced_max_delta_db": -0.8
    }
  }
}
```

## 5. publish / CI ゲートでの使い方

```bash
python -m piper_train.tools.eval_zs_secs \
    --synth-dir synth/ --speaker-utts spk/ --exclude-ref spk/ref.wav \
    --floor-refs floor/ --floor-selection-note "same-lang 近接話者 5 名" \
    --encoder models/campplus.onnx \
    --encoder2 models/ecapa.onnx --require-encoder2 \
    --meta-json synthesis_conditions.json \
    --baseline-json prev_report.json \
    --json-out report.json
```

- `--require-encoder2`: encoder2 未指定なら exit 2 (ゲートを素通りさせない)。
  encoder2 未指定かつ本フラグなしの場合も「Goodhart 検知不能」警告を stderr に出す
- `--baseline-json`: 前回リリース/前 epoch の eval JSON。goodhart_flag が `true`
  なら SECS 上昇を改善と報告してはならない (聴感 + 帯域 + ECAPA で再検証)
- `--meta-json`: 合成条件 (noise_scale / noise_scale_w / seed / texts) を
  manifest に verbatim 記録。**§6 の事前登録判定は manifest に pin した合成条件・
  ファイル集合で行う** (eval-time knob で必達を満たす穴を塞ぐ)
- `--exclude-ref` は path 一致に加え **sha256 (内容) 一致**でも cross 集合から
  除外される。synth と実音声 (speaker/floor) の sha256 一致は取り違えとして
  SystemExit (eval 無効)
- `--skip-acoustics`: SECS だけ欲しい高速 run 用 (band/comb/prosody は null)
- テスト: `src/python/tests/test_eval_zs_secs.py` が本契約の数値定義
  (閾値・null 明示・exit code) を pin する

## 6. 音響メトリクスの事前登録値 (v10b、事後緩和禁止)

登録の canonical は
[v10b plan §4.3](../design/zero-shot-v10b-quality-plan.md#43-事前登録判定基準-v10b変更禁止)
— **事後緩和禁止**。ツールは測るだけで pass/fail 判定はしない (stdout に登録値を
参考表示するのみ)。判定は `/eval-zs` skill と `/publish-model` の責務。

| 指標 | 必達 (v10b) | 現状 (r2 ep79 解剖) | GT anchor |
|---|---|---|---|
| SR/128 格子コム超過 (`comb_excess_db`) | **< 1.5dB** (目標: GT 帯 0.65-0.76dB) | 4.1-4.7dB | 0.65-0.76dB |
| >4kHz 残差 autocorr @lag128/256 | **< 0.05** | 0.10-0.24 | ≈0.006-0.13 (per-file で 0.13 まで出る) |
| 5.5-8.5kHz voiced 棚 (max Δ vs real) | **≤ +2.0dB** (~1σ、GT per-bin sd 1.8-2.7dB) | +3.0〜4.6dB | — |
| 同帯域・無声区間 (別枠、テキスト非統制の参考値) | ≤ +3.0dB | +4.6〜7.9dB | — |
| 4-9kHz 帯域 (`voiced_hi_excess_db_median`、旧指標・互換維持) | **ep69 baseline (Phase A 再測定値) 比非悪化** | -10.5dB (ep79) | — |
| F0 ダイナミクス (`prosody` synth 側) | std **≥ 45Hz** かつ p5-95 range **≥ 150Hz** | std 29-41 / 87-142Hz | std 47-74 / 153-215Hz |

運用規則:

- **測定は raw decoder 出力** (§2 禁止事項 5)。gate は **manifest に pin した
  synth セットの median** (band 棚は group-mean delta の bin max) に適用する。
- **GT / real anchor は文脈表示のみ** — gate は synth 側にのみ適用する
  (GT の per-file autocorr は 0.13 まで出る実測があるため、GT に gate を当てると
  偽陽性になる)。
- 判定 baseline は **v10a-r2 ep69** に固定。baseline 測定 (ep69) の manifest JSON
  への pin が Phase A の完了条件 (plan §4.3)。
- 比較の定義変更 (帯域・正規化基準・格子定義) は事前登録を無効化する — 変更する
  場合は新指標として別名で登録し直すこと (goalpost moving の禁止、
  pre-commit `test-threshold-relaxation` gate と同思想)。
