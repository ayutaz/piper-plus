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
    --json-out <結果.json> \
    [--baseline-json <前回の結果.json>]
```

- **`--encoder2` は必須** (guard-bash hook が encoder2 なし実行を block する)。
  ECAPA は SCL への組み込み恒久禁止 (held-out 判定器を汚さない)
- モデル比較・改善判定時は **`--baseline-json` 必須** — encoder ごとの Δ と
  goodhart_flag が自動判定される
- 帯域検査 (4-9kHz、がびがび gate) を併走: `/publish-model` フェーズ 3.5 参照

### 3. 判定ルール (事前登録、変更禁止)

| ルール | 内容 |
|---|---|
| cross-utt のみ | same_utt_secs は参考値。判定への使用は**禁止** |
| 正規化転写率 | `(SECS - floor) / (ceiling - floor)` で解釈 (ja 女性 floor は 0.69-0.74 と高い) |
| dual-encoder 同調 | primary Δ >= +0.02 でも encoder2 Δ < +0.01 なら **Goodhart 棄却** (`goodhart_flag: true`) |
| gap 監視 | `gap_same_minus_cross` の拡大 = Goodhart 成分の増大。baseline 比 +0.01 以上で警告 |
| 対照必須 | SECS は ±0.01/ep 揺れる。**対照 run なしの +0.03 は判定不能** |
| 4 点セット | SECS 単独 go/no-go 禁止 — ①正規化転写率 ②encoder2 ③4-9kHz 帯域 ④聴感 (SNAC 論文: SECS で負け SMOS で勝つ系が実在) |

### 4. 報告フォーマット

結果は必ず「cross-utt SECS (正規化転写率) / encoder2 / gap / 帯域 / 聴感」を
併記し、baseline 比較なら goodhart_flag の値を明記する。

## 再発防止の多層ガード (本 skill 以外)

- hook `guard-bash.sh`: `--encoder2` なしの eval_zs_secs 実行を block
- pre-commit `zs-prevention-gate`: 防止テスト群と評価ガード面の削除・改名を検出
- `/publish-model` フェーズ 3.5: 公開前の帯域 + cross-utt SECS gate
- 単体テスト: `test_eval_zs_secs.py` (goodhart_flag 判定ロジック含む)
