# 05. Stage 1 Smoke 学習 Runbook (GPU 実行手順)

> **前提**: RTF キルスイッチ判定済み (04 doc §2 追記) — 速度 gate は ❌ 確定のため、本 smoke の目的は**品質同等の確認のみ** (🟡 CONDITIONAL GO: SECS ≥ 0.6879 + JA/ZH サ行維持 → opt-in flag として維持)。
> **ベース手順**: [`docs/handoff/zero-shot-tts-handoff-2026-06-20.md`](../../handoff/zero-shot-tts-handoff-2026-06-20.md) (以下「handoff」) の §2 環境構築 / §4 HF 取得 / §6 データセット復元をそのまま使い、本書は **WaveNeXt 固有の差分のみ**を記す。
> **タイムライン**: v8 本走が 2026 年 8 月開始予定のため、それまでに完了させる (Phase A: 半日 / Phase B: 準備 1 日 + 学習 3-5 日 + 評価 1 日)。

---

## 0. handoff からの差分 (最重要)

| 項目 | handoff (v7 時代) | 本 smoke |
|------|-------------------|----------|
| ブランチ | `feat/zero-shot-tts` | **`feat/wavenext-decoder-ablation`** (dev v2.0 ベース) |
| torch | 2.2 系 | **2.11 + cu128** (pyproject が Linux で自動解決) |
| decoder | MB-iSTFT | **`--decoder-arch wavenext`** |
| decoder init | v7 ckpt 継承 | **`--wavenext-init` (BSC-LT) + encoder のみ v7 転移 (`--resume-encoder-only`)** |
| v7 ckpt の扱い | full resume | **weights-only 部分転移のみ** (torch 2.2 製 ckpt の optimizer resume は DR-006 で非保証だが、`--resume-encoder-only` は state_dict の部分ロードなので影響なし) |

追加ダウンロード (handoff §4.2 に加えて):

```bash
# BSC-LT WaveNeXt 事前学習重み (public, Apache-2.0, ~55MB)
hf download BSC-LT/wavenext-mel pytorch_model.bin \
  --local-dir /data/piper/hf/wavenext-mel-bsclt
# → --wavenext-init /data/piper/hf/wavenext-mel-bsclt/pytorch_model.bin
```

loader は 83 テンソル中 80 を転送する (`(loaded, skipped, dropped) = (80, 1, 2)` がログに出る。04 doc §7)。

---

## 1. 必要リソース (ユーザー作業: インスタンス調達)

| 項目 | 推奨 |
|------|------|
| GPU | **A100 40GB+ × 1** (bf16-mixed)。RTX 6000 Ada 48GB / RTX 5090 32GB でも可 |
| ディスク | Phase A のみ: 50GB / Phase B: **500GB+** (6-lang 生 wav + cache) |
| 調達先 | vast.ai / shadeform (~$1-2/h → Phase B 3-5 日で $80-250 目安) |
| OS image | CUDA 12.x + Ubuntu 22.04/24.04 |

インスタンス起動後、ssh 接続情報を共有してもらえれば以降の作業 (セットアップ〜学習起動〜監視〜評価) は Claude 側で実行可能。

---

## 2. Phase A: Tsukuyomi quick signal (~半日、Phase B の前哨戦)

**目的**: 6-lang 復元 (1 日仕事) に入る前に、「WaveNeXt decoder + BSC-LT init + encoder 転移」の組が**まともな音声を出すか**を数時間で確認する。データは公開 Tsukuyomi corpus 100 発話のみ (handoff §5.2)。

```bash
# 環境構築: handoff §2.3 をそのまま実行、ただし
#   git checkout feat/wavenext-decoder-ablation   # ← ブランチだけ変更
# HF 取得: handoff §4.2 の 1 (v7) と 3 (campplus) + 上記 BSC-LT

# データ準備: Tsukuyomi corpus DL → handoff §6 の preprocess (100 発話なので数分)
# (v7 期の dataset-tsukuyomi-finetune-6lang 相当を再生成)

# 学習 (Phase A): single-speaker FT 構成 + wavenext decoder
nohup /data/piper/.venv/bin/python -u -m piper_train \
    --dataset-dir /data/piper/dataset-tsukuyomi-finetune-6lang \
    --decoder-arch wavenext \
    --wavenext-init /data/piper/hf/wavenext-mel-bsclt/pytorch_model.bin \
    --resume-from-multispeaker-checkpoint /data/piper/hf/zero-shot-multi-6lang-v7/epoch=32-step=216326.singlespk.ckpt \
    --resume-encoder-only \
    --prosody-dim 16 \
    --accelerator gpu --devices 1 --precision bf16-mixed \
    --max_epochs 500 --batch-size 4 --samples-per-speaker 4 \
    --checkpoint-epochs 100 --quality medium \
    --base_lr 1e-4 --disable_auto_lr_scaling \
    --ema-decay 0.9995 --max-phoneme-ids 400 --no-wavlm \
    --c-mrd 0.1 --pretrain-mel-steps 2000 \
    --lr-scheduler cosine --lr-warmup-epochs 5 --lr-min 1e-5 \
    --val-every-n-epochs 50 --audio-log-epochs 50 \
    --default_root_dir /data/piper/output-wavenext-tsukuyomi-smoke \
    > wavenext-phase-a.log 2>&1 &
```

> Note: decoder が (BSC-LT init とはいえ) 入力 embed スクラッチなので、MB-iSTFT FT (`base_lr 2e-5`) より高めの `1e-4` から。v7 の Tsukuyomi FT は 51 分/500ep だった — WaveNeXt は decoder が 8.6x 重いため **2-4 時間**見込み。

**Phase A 判定 (GO → Phase B へ)**:

1. 破綻なし: validation audio (500ep 時点) が明瞭な音声 (「ピー」音・ノイズ床でない)
2. SECS 参考値: `tsukuyomi/eval/compute_secs.py` (handoff §4.3) で MB-iSTFT FT の 0.7749 と比較 — **0.70 以上なら十分な前哨シグナル** (ベース学習量が違うため直接比較ではない)
3. head bias floor: 無音区間の出力 RMS < 正規化ピーク比 1% (04 doc §8 Unknown #8 残余)
4. FP16 export: `python -m piper_train.export_onnx <ckpt> out.onnx` が通り、opset 17 / LayerNormalization ×10 / `convert_fp16 --validate` 通過

Phase A で破綻 (loss 発散 / 無音 / ノイズのみ) → 原因調査してから Phase B。**Phase B の GPU 代を無駄にしないための門番**。

---

## 3. Phase B: 6-lang smoke 本番 (準備 1 日 + 学習 3-5 日)

**目的**: 03 doc の GO/NO-GO 判定 (SECS ≥ 0.6879 = v7 zero-shot 未知話者 baseline)。

1. データセット復元: handoff §6 (生 wav DL 半日 + 前処理)。497,519 発話 / 571 話者
2. 学習コマンド: **03 doc「Stage 1 実装 + smoke 学習」節のコマンドをそのまま使用** (`--decoder-arch wavenext` / `--wavenext-init` / `--resume-encoder-only` / `--c-mrstft 1.0 --c-mrd 0.1` / `--pretrain-mel-steps 5000`)
3. 監視項目 (v7 の教訓、CLAUDE.md): NCCL timeout / dino_center 汚染 / non-finite skip 率 (v7 実績 2.5%)。**bf16 × DINO × CAM++ SCL × WaveNeXt は前例なし (Unknown #5)** — 最初の 1000 step は loss curve を注視
4. 評価: `v7/eval/compute_secs.py` + 参照 emb で既知/未知話者 SECS、JA/ZH サ行 PESQ/STOI、聴感 A/B (03 doc 評価節)

**判定は 03 doc の GO/NO-GO 表に従う** (✅ GO 行は速度 gate ❌ により到達不能。🟡 CONDITIONAL GO = opt-in flag 維持、❌ NO-GO = `docs/research/` に知見をログして close)。

---

## 4. トラブルシューティング (WaveNeXt 固有)

| 症状 | 対処 |
|------|------|
| `--wavenext-init` で shape mismatch | BSC-LT repo のファイルが更新された可能性 → ログの `(loaded, skipped, dropped)` を確認、(80,1,2) 以外なら `load_bsc_lt_generator_weights` の rename map を点検 |
| ckpt 読み込みで decoder_arch mismatch エラー | 意図した動作 (tri-state 検証)。encoder だけ欲しい場合は `--resume-encoder-only` を付ける |
| loss_gen_mrd が序盤発散 | `--pretrain-mel-steps` を増やす (2000→5000)、`--c-mrd` を 0.05 に |
| bf16 で NaN skip 頻発 | DDP-synced NaN skip は実装済 (v7 由来)。skip 率 >5% なら `--precision 32-true` で切り分け |
| WaveNeXt ckpt に `model_g.dec.pqmf.*` が混入 | あってはならない (gate 済み + テスト有)。見つけたら即報告 — tri-state 誤分類の前兆 |

## 5. 完了後のアーカイブ

- ckpt / ONNX / SECS ログ / TensorBoard events を HF (private) にアップロード (`ayousanz/piper-plus-wavenext-smoke` 等、handoff §4 の形式踏襲)
- 結果を 03 doc の GO/NO-GO 表に記入し、README のステータス更新
- Phase B が NO-GO の場合も `docs/research/` に負の結果を記録 (iSTFTNet2-MB / Matcha-TTS 検討時の再利用価値)
