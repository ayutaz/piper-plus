# Zero-Shot 話者評価契約 (zs-eval-contract)

> **Status**: v10 で制定 (2026-08-14)。zero-shot 話者類似度の評価は本契約に従う。
> ツール実装: `src/python/piper_train/tools/eval_zs_secs.py` (schema `zs-eval-v2`)。
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

## 1. 必須メトリクス

zero-shot モデルの話者類似度を報告・判定する際は、以下を**全て**測ること:

| メトリクス | 定義 | 測定手段 |
|---|---|---|
| **cross-utt SECS** (主指標) | synth と「同一話者の**別発話**」(exclude-ref 除外後) の平均 cosine | `eval_zs_secs` `cross_utt_secs` |
| **ceiling / floor** | 同一話者の実発話同士 / 近い声質の別話者との平均 cosine (cosine スケールの encoder 非互換を吸収) | `eval_zs_secs` `ceiling` / `floor` (`--floor-refs`) |
| **正規化転写率** | `(cross_utt − floor) / (ceiling − floor)` | `eval_zs_secs` `normalized_transfer` |
| **same/cross gap** | `same_utt_secs − cross_utt_secs`。SCL Goodhart で膨らむ成分の直接観測 | `eval_zs_secs` `gap_same_minus_cross` |
| **第 2 encoder** | held-out encoder (ECAPA) での同上指標。SCL に組み込むことは**恒久禁止** (held-out 判別器として維持) | `eval_zs_secs` `--encoder2` (+ `--require-encoder2`) |
| **4-9kHz 帯域** | PQMF 帯域境界近傍の非構造エネルギー (がびがび gate)。UTMOS/HNR はこのノイズに全盲 | `/publish-model` フェーズ 3.5 の帯域スペクトル検査 |

## 2. 禁止事項

1. **same-utt SECS 単独判定の禁止**: 条件付けに使った発話と同じ発話との cosine は、
   SCL が「生成音の embedding を参照 embedding に一致させる」よう学習しているため、
   話者が似ていなくても高く出る (0.775 誤報事故)。`same_utt_secs` は参考値のみ。
2. **primary encoder (CAM++) 単独判定の禁止**: SCL と同型の encoder は Goodhart に
   脆弱 (Phase 0 Arm B)。go/no-go には held-out 第 2 encoder の同調が必須。
   publish/CI ゲートでは `--require-encoder2` を付ける (未指定は exit 2)。
3. **ECAPA (第 2 encoder) の SCL への組み込み禁止**: held-out 判別器として
   機能し続けるための恒久ルール (診断 doc §5-4)。

## 3. goodhart_flag の定義

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

## 4. JSON schema (`zs-eval-v2`)

v1 からは **field 追加のみ**の後方互換 (v1 の読み手は追加 field を無視できる。
v2 の読み手は v1 JSON の欠落 field を null 扱いで読める)。未計測の指標は
**キー欠落ではなく null 明示**。

```jsonc
{
  "schema": "zs-eval-v2",
  "goodhart_flag": null,            // baseline 比較時のみ true/false、それ以外 null
  "encoders": {
    "campplus": {
      "cross_utt_secs": 0.6521,
      "same_utt_secs": 0.7103,      // 参考値のみ (判定使用禁止)
      "gap_same_minus_cross": 0.0582,
      "ceiling": 0.8880,
      "floor": 0.5210,
      "normalized_transfer": 0.3572,
      "n_synth": 10,
      "n_refs": 9
    },
    "encoder2": { /* 同構造 (ECAPA) */ }
  },
  "baseline_comparison": {          // --baseline-json 指定時のみ
    "baseline_path": "prev_report.json",
    "goodhart_flag": false,
    "gap_widened_encoders": [],
    "deltas": {
      "campplus": { "cross_utt_secs": 0.0034, "gap_same_minus_cross": -0.0021 },
      "encoder2": { "cross_utt_secs": 0.0028, "gap_same_minus_cross": null }
    }
  }
}
```

## 5. publish / CI ゲートでの使い方

```bash
python -m piper_train.tools.eval_zs_secs \
    --synth-dir synth/ --speaker-utts spk/ --exclude-ref spk/ref.wav \
    --floor-refs floor/ \
    --encoder models/campplus.onnx \
    --encoder2 models/ecapa.onnx --require-encoder2 \
    --baseline-json prev_report.json \
    --json-out report.json
```

- `--require-encoder2`: encoder2 未指定なら exit 2 (ゲートを素通りさせない)。
  encoder2 未指定かつ本フラグなしの場合も「Goodhart 検知不能」警告を stderr に出す
- `--baseline-json`: 前回リリース/前 epoch の eval JSON。goodhart_flag が `true`
  なら SECS 上昇を改善と報告してはならない (聴感 + 帯域 + ECAPA で再検証)
- テスト: `src/python/tests/test_eval_zs_secs.py` が本契約の数値定義
  (閾値・null 明示・exit code) を pin する
