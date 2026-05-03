# Multi-speaker checkpoint -> FT-base checkpoint converter

学習直後のマルチスピーカー `last.ckpt` (~938 MB) を、HuggingFace に公開できる
ファインチューニング用の軽量 ckpt (~316 MB) に変換するスクリプト。

## 何をしているか

| 処理 | 削減量 (典型) |
|------|--------------|
| `optimizer_states` 削除 | ~600 MB |
| `lr_schedulers` / `ema_discriminator_state` / `loops` / `callbacks` 削除 | 数 MB |
| `state_dict` から `model_g.emb_g.weight` 削除 | ~1 MB (= num_speakers x 512 x 4) |
| `hyper_parameters.num_speakers = 0` に書き換え | — |

`cond_layer` 系 (`model_g.dec.cond.*`, `dp.cond.*`, `enc_q.enc.cond_layer.*`,
`flow.flows.*.enc.cond_layer.*`, `enc_p.cond_layer.*`) は **保持** する。
学習側の `--resume-from-multispeaker-checkpoint` が起動時に動的に
`emb_g.mean()` を bias に吸収する設計のため。

`ema_generator_state` は decoder の `shadow_params` だけを保持しており
`emb_g` 系は元から EMA の対象外。そのまま残しても問題ないので clean-up しない。

> **Security**: `torch.load(weights_only=False)` を使用。Lightning ckpt は
> `hyper_parameters` に `pathlib.Path` をピクルするので weights_only=True では
> 読めない。**信頼できる ckpt にのみ使用すること**。Windows では Linux 由来の
> ckpt をロードするため `pathlib.PosixPath` の互換パッチを自動適用。

## 使い方

```bash
uv run python scripts/convert_multi_to_single_speaker.py \
  --input-checkpoint  /data/piper/output-multilingual-6lang-mb-istft/checkpoints/epoch=74-step=500034.ckpt \
  --output-checkpoint /data/piper/hf_upload/piper-plus-base/model.ckpt
```

環境変数経由でも可:

```bash
INPUT_CHECKPOINT=/path/to/last.ckpt \
OUTPUT_CHECKPOINT=/path/to/model.ckpt \
uv run python scripts/convert_multi_to_single_speaker.py
```

## config.json も合わせて更新

公開時には `num_speakers=0` に揃えた config.json も同時にアップロードする:

```python
import json
with open("dataset.../config.json") as f:
    cfg = json.load(f)
cfg["num_speakers"] = 0
cfg.pop("speaker_id_map", None)
with open("hf_upload/.../config.json", "w") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
```

## ファインチューニング側の使い方

変換した `model.ckpt` は通常 `--resume-from-multispeaker-checkpoint` で使う:

```bash
python -m piper_train \
  --dataset-dir /path/to/single-speaker-dataset \
  --resume-from-multispeaker-checkpoint /path/to/model.ckpt \
  --prosody-dim 16 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 500 --batch-size 4 --samples-per-speaker 4 \
  --base_lr 2e-5 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --max-phoneme-ids 400 \
  --no-wavlm
```

`--resume-from-multispeaker-checkpoint` は自動で `--freeze-dp` を有効化する。

## 履歴

PR #170 (2025-08-28) で初導入、PR #229 (M1+M1.5 リファクタ) で削除。
PR #320 (MB-iSTFT 統一 Decoder) のマージ後に取り残された再追加分として、
follow-up PR #369 で復活 + 現行アーキ向けに簡素化:

- 旧版: `cond_layer` 系も全部削除していた
- 現行版: `cond_layer` 系は保持 (`--resume-from-multispeaker-checkpoint` の
  動的吸収ロジックに任せる)
- 旧版: `optimizer_states` / `lr_schedulers` のみ top-level 削除
- 現行版: 加えて `ema_discriminator_state` / `loops` / `callbacks` も削除
- 旧版: 推測で `ema_generator_state["module"]` 内の `emb_g` キーを削除しようと
  していたが、現行 EMA 実装は `shadow_params` 形式 + decoder のみで `emb_g`
  対象外なのでそのブロックを削除
