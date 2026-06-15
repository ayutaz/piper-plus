# AI-07: FLY-TTS PoC 学習 50 epoch

## メタ情報

- ID: AI-07
- 親マイルストーン: [M3](../milestones/M3-fly-tts-parallel-harness.md)
- 工数見積: 1.5 日
- 依存チケット: AI-06 (FLY-TTS ConvNeXt6 decoder 実装)
- 後続チケット: AI-12 (3 variant benchmark 統合)、 AI-05 (iSTFTNet2-MB PoC 学習) 失敗時の保険切替先
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items AI-07 / §4.5 FLY-TTS 並走 / §4.4 Training Plan](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

本チケットは A-1 (iSTFTNet2-MB 1D-2D backbone) の **保険ライン** として FLY-TTS (ConvNeXt × 6 + 単一帯域 iSTFT、 Guo et al. Interspeech 2024、 MOS 4.12 実証済み) を CSS10 JA 単一話者で 50 epoch 学習し、 A-1 失敗時の即時切替先を確保する。 計画 §1 Executive Summary と §4.5 で示されたとおり、 Q13 (iSTFTNet2 + VITS2 統合の MOS 一般則 0.2-0.5 ドロップ + iSTFTNet2 specific zero prior art) のリスクヘッジとして本 PoC を **A-1 と同条件・同期間で並走** させることが必須。

上流の AI-06 から `src/python/piper_train/vits/fly_decoder.py` (~200 LoC、 ConvNeXt × 6 + Conv1d(256→1026) + OnnxISTFT(n_fft=1024, hop=256)、 PQMF 不使用) と関連 unit test が引き渡される。 本チケットはこれを `decoder_type='fly_convnext6'` config 分岐経由で起動し、 CSS10 JA dataset (AI-01 で整備済) に対して `--c-sub-stft 0.0` (sub-band loss 無効) で 50 epoch 学習を完走する。 下流の AI-12 には FLY-TTS variant の checkpoint + ONNX export + WandB audio log + proxy MOS を引き渡し、 3 variant (css10-ja-1d-baseline / istftnet2-mb / fly-convnext6) 比較の入力データとする。

加えて、 計画 §7 R3 (Q13 zero prior art) の Day 4 評価で A-1 が proxy MOS -0.3 以上の劣化または CPU RTF 退化を示した場合、 本 PoC の checkpoint をそのまま FLY-TTS 100 epoch 延長 (R3 mitigation) の warm start として連続使用できるよう、 ckpt と学習設定を再現可能な形で残す。

## 実装内容の詳細

学習スクリプト本体は新規実装を最小化し、 既存 `piper_train` Template B (CLAUDE.md 単一話者 FT) を `decoder_type='fly_convnext6'` で起動する形に集約する。 計画 §3 Conflict Map の `src/python/piper_train/vits/stft_onnx.py` (vs PR #222 LOW / vs PR #537 NONE) / `src/python/piper_train/vits/models.py` (vs PR #222 HIGH / vs PR #537 NONE) のうち、 本チケットは models.py の `dec` 選択分岐のみを read-only で利用する (AI-06 で実装済の前提)。

### 学習起動コマンド

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
    --dataset-dir /data/piper/dataset-css10-ja-poc/ \
    --prosody-dim 16 \
    --accelerator gpu --devices 1 --precision 32-true \
    --max_epochs 50 --batch-size 4 --samples-per-speaker 4 \
    --checkpoint-epochs 10 --quality medium \
    --base_lr 2e-5 --disable_auto_lr_scaling \
    --ema-decay 0.9995 --max-phoneme-ids 400 --no-wavlm \
    --val-every-n-epochs 10 --audio-log-epochs 10 \
    --decoder-type fly_convnext6 \
    --c-sub-stft 0.0 \
    --default_root_dir /data/piper/output-fly-convnext6-poc/ \
    > /data/piper/output-fly-convnext6-poc/training.log 2>&1 &
```

### 主要差分 (Template B vs 本 PoC)

- `--decoder-type fly_convnext6` (AI-06 で `__main__.py` argparse に新規追加された CLI 引数を起動側で指定)
- `--c-sub-stft 0.0` (FLY-TTS は単一帯域 iSTFT で sub-band STFT loss 不要、 計画 §4.5 明記)
- `--max_epochs 50` (Template B の 500 ではなく PoC スコープに合わせる)
- `--val-every-n-epochs 10 --audio-log-epochs 10` (50 epoch 中 5 回の validation で WandB audio log を AI-12 評価に渡す)
- `--no-wavlm` (V100 想定で GPU OOM 回避、 PoC 段階では perceptual quality は proxy MOS で評価)
- `--samples-per-speaker 4` (CSS10 JA 単一話者 6,200 utt、 「ピー音」回避のため `--disable_auto_lr_scaling` と組み合わせ)

### 編集対象ファイル

| パス | 編集内容 | LoC | G-1.x 制約 |
|------|---------|----|---------|
| `src/python/piper_train/__main__.py` | `--decoder-type` 既存値リストに `fly_convnext6` 追加確認 (AI-06 で実装済が前提) | 0 (read-only) | G-1.9 後方互換 (default='mb_istft_1d' 不変) |
| `src/python/piper_train/vits/lightning.py` | FLY-TTS 用 LR / EMA 設定が `_collect_g_params` hook 経由で動作するか smoke 確認 | 0-5 (確認用) | AI-09 (MEDIUM conflict vs PR #222 WavLM-D 拡張) と非衝突に維持 |
| `/data/piper/output-fly-convnext6-poc/` | 新規 output directory | — | — |
| `docs/research/fly-tts-training-log.md` | 50 epoch 学習ログ (loss curve / val audio sample / GPU 使用率 / 推定残時間) を WandB run URL と合わせて記録 | ~80 | 後続 AI-12 が proxy MOS 算出時の参照 |

### PR #222 / PR #537 conflict 回避策

計画 §3 Conflict Map から本チケット該当行:

- `stft_onnx.py` 行: 「OnnxISTFT 追加 instance (FLY-TTS / A-2 用)、 vs PR #222 LOW、 vs PR #537 NONE、 **A-1/A-2 先行で OK**」 — AI-06 で stft_onnx.py に `OnnxISTFT(n_fft=1024, hop=256)` を新規 instance 化済の前提を引き継ぎ、 本チケットでは触らない
- `models.py` 行: 「`dec_wavehax` sibling 追加、 `decoder_type` 受領、 vs PR #222 HIGH (spk_proj 統合点)、 **A-1/A-2 先行で隔離**」 — 本チケットは `dec` 選択分岐の read-only 利用のみで spk_proj 周辺には触らない (PR #222 rebase 時の AI-17 で FiLM rank-aware 化に合わせて再吸収)
- `lightning.py` 行: 「`_collect_g_params` hook、 wavehax LR、 vs PR #222 MEDIUM (WavLM-D + DINO 拡張)、 vs PR #537 LOW (bf16-mixed)」 — FLY-TTS の vocoder LR は base_lr=2e-5 で既存 generator opt にそのまま乗せ、 PR #222 の opt_d/opt_g 拡張と非衝突 (AI-09 で hook 整備済)

### 設定 default と新規 CLI フラグ

- 新規 CLI フラグなし (AI-06 の `--decoder-type` と既存 `--c-sub-stft` のみで完結)
- 暫定 default は `mb_istft_1d` 不変 (G-1.9 後方互換 gate)
- 学習中の `decoder_type` は config.json に記録され、 ONNX export 時に `export_onnx.py:--decoder-branch fly` 経路に分岐 (AI-06 で実装済)

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|----------|---------|
| ML Training Lead | 1 | PyTorch / VITS / WandB / V100 (32-true) 経験 | 50 epoch 学習の完走、 loss curve 監視、 「ピー音」検出時の base_lr / samples-per-speaker 調整、 WandB audio log の validation epoch 5 回分確保 |
| Infra / GPU Engineer | 1 | nvidia-smi / NCCL / Linux nohup / disk quota | GPU 占有スケジュール調整 (計画 §7 R8 mitigation)、 ゾンビプロセス監視、 disk ~8.3GB の dataset + ~3GB の checkpoint 保管確保 |
| QA / Evaluation Engineer | 1 | proxy MOS / UTMOS / 音声品質聴感評価 | 学習中 / 完了時の val sample 聴感チェック、 AI-12 への引き渡し前の sanity (ckpt が load 可能、 forward が `[1,1,T]` を返す) |

合計 3 名。 学習自体は ML Training Lead 1 名で完走可能だが、 計画 §7 R8 の GPU 競合リスクを Infra Engineer がバックアップする体制とする。 AI-05 (iSTFTNet2-MB PoC 学習) と GPU を直列共有する場合は ML Training Lead を AI-05 と兼務させ、 同一 1 GPU を 2 学習 直列で回す (合計 ~72h、 計画 §4.4 推定)。

## 提供範囲 (Scope)

### 含むもの

- CSS10 JA dataset を入力とする FLY-TTS (`decoder_type='fly_convnext6'`) 50 epoch 学習の完走
- 学習 checkpoint: `/data/piper/output-fly-convnext6-poc/last.ckpt` + 10 epoch ごとの中間 ckpt
- WandB run URL + audio log (5 epoch 間隔の validation sample × 5 回)
- 学習ログサマリ `docs/research/fly-tts-training-log.md` (loss curve / GPU 使用率 / 残時間推定)
- val loss / train loss / sub-band loss=0 が weights & biases に記録されていること
- 完了時の最終 ckpt の forward smoke (CPU 1 utt で `[1,1,T]` float32 を返すこと)

### 含まないもの (Out of Scope)

- ONNX export 実行 (AI-06 で smoke 済、 本格 export と benchmark は AI-12 に統合)
- proxy MOS 算出 (AI-12 で 3 variant 比較として実施)
- 7 ランタイム smoke / pairwise SNR 検証 (AI-13)
- `audio-parity-contract.toml` への `[fly_convnext6]` section 追加 (AI-14)
- PR #222 / #537 rebase 後の bf16-mixed + TF32 再学習 (AI-16)
- FLY-TTS 100 epoch 延長 (R3 mitigation): A-1 失敗判定後に AI-07 の追加 phase として再起動

## テスト項目

### Unit Tests

- `src/python/tests/test_fly_decoder.py::test_forward_output_shape` (AI-06 で実装済)
  - assert: forward 出力 shape == `[B, 1, T]`、 params 0.63M ± 0.05M、 PQMF instance 不在
- `src/python/tests/test_fly_decoder.py::test_no_sub_stft_loss`
  - assert: `c_sub_stft=0.0` で `sub_stft_loss` が 0 になり backward gradient が iSTFT loss と adversarial のみから流入
- `src/python/tests/test_decoder_type_routing.py::test_fly_convnext6_dispatch`
  - assert: `decoder_type='fly_convnext6'` で `model.dec` が `FlyConvNeXtDecoder` instance になり、 default 経路の `MBiSTFTGenerator._forward_1d` は呼ばれない
- 既存 `src/python/tests/test_mb_istft_generator.py` は **touch しない** (G-1.9 後方互換 gate、 G-1.2 baseline 編集禁止)

### E2E Tests

- 1 epoch sanity (本学習起動前)
  - `--max_epochs 1` で 1 epoch だけ走らせ、 WandB audio log と val loss が記録されること
  - 50 epoch 学習開始前の dry run として `/data/piper/output-fly-convnext6-poc-sanity/` に分離出力
- 50 epoch 学習完走 smoke
  - `last.ckpt` を `torch.load` で読み込み、 `model.dec.__class__.__name__ == 'FlyConvNeXtDecoder'` を assert
  - CPU forward 1 utt (`text="こんにちは"`, language=ja, speaker_id=0) で `[1, 1, T]` float32 が返る
- 中間 ckpt の resume 互換性 smoke
  - epoch 10 ckpt から `--resume_from_checkpoint` で 1 step 追加学習が走ること (計画 §7 R8 GPU 競合時の中断/再開耐性)
- WandB audio log の聴感 sanity
  - epoch 10/20/30/40/50 の 5 サンプルが「ピー音」でなく日本語として聞き取れること (QA Engineer subjective)

### 受入基準 (Acceptance Criteria)

計画 §4.6 / §5 (Milestone 3 Exit Criteria) から該当する数値目標:

- **50 epoch 学習完走** (GPU OOM / ピー音 / NaN loss が起きないこと)
- **params 0.63M ± 0.05M** (FLY-TTS 公称値、 計画 §4.5)
- **val loss が学習途中で発散しない** (epoch 5-10 で local minimum に到達、 epoch 50 まで monotonic に近い減少)
- **WandB audio log 5 サンプル全てが日本語として聞き取れる** (QA Engineer subjective、 0/5 で失敗判定 → AI-12 評価入力から除外)
- **`last.ckpt` の CPU forward smoke pass** (`[1,1,T]` float32 / 1 utt 5 秒以内)
- **後続 AI-12 への引き渡し成果物完備** (ckpt パス・WandB run URL・学習ログサマリ docs)

数値目標 (proxy MOS / CPU RTF / 7 ランタイム smoke) の本判定は AI-12 / AI-13 で実施。 本チケットは「学習が正常完走したこと」のみを受入基準とする。

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

計画 §7 Risk Register から該当項目:

- **R3 (Q13 zero prior art)**: 50 epoch 投資後に proxy MOS -0.3 以上の劣化 / CPU RTF 退化 → FLY-TTS 100 epoch 延長判断 (AI-12 評価後に AI-07 second phase として再起動)
- **R8 (1 GPU 直列スケジュール 7 日)**: AI-05 と GPU 共有時に直列化で 5 日 → 7 日に伸びる、 並走 2 GPU 確保できれば 2 日短縮
- **R5 (PR #537 の TF32-on + bf16-mixed default + NumPy 2.x の影響)**: 本 PoC は PR #537 merge 前の現行 dev (torch 2.2 / py3.11) で完走、 merge 後の再学習は AI-16 で別途実施

本チケット固有の細かい懸念:

- **ConvNeXt × 6 の receptive field**: DepthwiseConv1d k=7 × 6 で receptive field は ~37 frame、 22050 Hz / hop=256 で約 430ms。 CSS10 JA の長文 (>30 phoneme) で文脈把握が足りるか PoC で観察
- **iSTFT n_fft=1024 / hop=256 の高周波再現**: MB-iSTFT の (n_fft=16, hop=4) × 4 band と異なる時間/周波数解像度。 高周波 (sibilant /s/, /sh/) の再現を WandB audio log で重点聴取
- **`--c-sub-stft 0.0` の loss balance**: sub-band STFT loss 不在で full-band iSTFT loss の重みが相対的に増加、 既存 hparams の `c_mel`, `c_kl`, `c_dur` との balance を 1 epoch sanity で確認
- **ckpt 容量**: 0.63M params の decoder + 既存 acoustic model + DP + EMA shadow で ~250MB / ckpt、 10 epoch ごと × 6 ckpt = ~1.5GB の disk

### レビュー項目 (チェックリスト)

- [ ] default `decoder_type` 不変 (`mb_istft_1d`、 G-1.9 後方互換 gate)
- [ ] `[mb_istft_1d]` audio parity 不変 (G-1.2 baseline 編集禁止、 本 PoC は別 ckpt として完全分離)
- [ ] ONNX I/O 不変 (本チケットは ONNX export 自体を実行しないが、 AI-06 で実装された FLY-TTS export 経路が PR #222 ABI 同期と二重同期にならないこと)
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響を **本 PoC では未反映** (AI-16 で再学習)、 audio-parity-contract tolerance への反映も AI-16 担当
- [ ] `--c-sub-stft 0.0` が config.json に記録され、 AI-12 で再現可能なこと
- [ ] WandB run の `decoder_type / c_sub_stft / dataset` tag が AI-12 集計の grouping key として読み取れること
- [ ] CSS10 JA dataset の version hash (AI-01 で記録予定) が config.json に embed され、 再現可能な学習であること
- [ ] `_collect_g_params` hook が FLY-TTS decoder param を含めることを 1 epoch sanity で確認 (AI-09 mitigation の維持)
- [ ] `text_splitter.py` を一切編集していないこと (decoder-agnostic 維持、 計画 §3 Conflict Map 「触らない」)

## 一から作り直すとしたら (Ticket-level rethinking)

現実解として本チケットは「**A-1 の保険ライン**」と位置づけ、 50 epoch / 1.5 日工数で同条件・同期間並走する設計を採用した。 代替案として 3 つのアーキテクチャを検討した:

**代替案 A: FLY-TTS を本命に昇格し A-1 を保険化** — FLY-TTS は MOS 4.12 実証済 (Guo 2024 Interspeech) で iSTFTNet2 の zero prior art (Q13) を回避できる。 ConvNeXt × 6 は 1D-CNN のみで mobile EP 互換性 (NNAPI / CoreML / QNN) も iSTFTNet2 より高い。 ただし piper-plus 既存の MB-iSTFT 資産 (PQMF / sub-band loss / `subband_conv_post`) を完全に捨てることになり、 6lang base ckpt からの warm start も不可能 (構造が異なる)。 採用案では A-1 を本命に置くことで warm start 利点を確保しつつ、 FLY-TTS を保険として並走する形に落ち着いた。 代替案 A は A-1 が Day 4 評価で失敗した場合に発動する 「fall-back 昇格」 として温存。

**代替案 B: ConvNeXt × 6 ではなく ConvNeXt × 3 + WavLM Discriminator 強化** — block 数を半減して params 0.32M に圧縮し、 浮いた GPU 予算を WavLM Discriminator (CLAUDE.md 実装済) に振り向ける構成。 perceptual quality を WavLM 側で稼ぐ。 ただし FLY-TTS 論文値 MOS 4.12 は ConvNeXt × 6 構成の数字であり、 block 数を変えると「論文再現」の意味が薄れ、 PoC の比較対象が曖昧になる。 また WavLM Discriminator は V100 (32GB) では `--no-wavlm` 推奨 (CLAUDE.md トラブルシューティング表) のため本 PoC では使えない。 採用案では論文構成を忠実に再現する優先度を選択。

**代替案 C: TDD 先行ではなく integration-test 先行 (1 epoch sanity + WandB audio log subjective を最優先)** — unit test (forward shape / params 数) は AI-06 で書かれており、 本チケットは学習という長時間プロセスのため、 TDD よりも 「1 epoch sanity を走らせて WandB audio log を聴く」 ことを最初の gate にする方が PoC の価値が早く判明する。 採用案では 「テスト項目」 セクションで 1 epoch sanity を E2E Tests の先頭に置くことでこの観点を取り込んだ。 一方で integration-test 先行に完全切り替えると 0.63M params / decoder dispatch routing といった structural assert が抜け落ち、 AI-06 由来の regression を見逃すリスクがあるため、 unit test (AI-06) + 1 epoch sanity (本チケット) + 50 epoch 完走の 3 段ゲートに組み立てた。

採用案の「A-1 本命 + FLY-TTS 並走保険」は **piper-plus 既存資産 (MB-iSTFT base ckpt warm start) を最大限活用しつつ、 zero prior art リスクを 1.5 日 / 1 GPU の追加投資で吸収する** バランスを優先したもの。 並走 GPU 確保ができない場合のみ代替案 A への昇格を検討。

## 後続タスクへの連絡事項

AI-12 (3 variant benchmark + UTMOS proxy MOS) への引き渡し:

- **ckpt パス**: `/data/piper/output-fly-convnext6-poc/last.ckpt` (epoch 50)
- **中間 ckpt パス**: `/data/piper/output-fly-convnext6-poc/epoch={10,20,30,40,50}/checkpoints/last.ckpt`
- **config.json パス**: `/data/piper/output-fly-convnext6-poc/config.json` (`decoder_type='fly_convnext6'`, `c_sub_stft=0.0` 記録)
- **WandB run URL**: 学習ログサマリ `docs/research/fly-tts-training-log.md` 内に明記
- **暫定 ONNX path 仮置き**: `out/fly-convnext6-poc.onnx` (AI-12 で `export_onnx.py --decoder-branch fly` で生成、 本チケットは export 自体を実行しない)
- **`tools/benchmark/models.yaml` 追記用 entry**: `fly-convnext6` (path: `/data/piper/output-fly-convnext6-poc/last.ckpt`、 decoder_type: `fly_convnext6`、 dataset: `css10-ja-poc`)

AI-05 (iSTFTNet2-MB PoC 学習) 失敗時の保険切替先として:

- **失敗判定 gate**: AI-12 完了時 (Day 4 評価) に A-1 の proxy MOS -0.3 以上劣化 / CPU RTF 退化が確定した場合
- **発動アクション**: 本 ckpt を warm start として **FLY-TTS 100 epoch 延長** を AI-07 second phase として再起動 (計画 §7 R3 mitigation)
- **延長時の設定変更**: `--max_epochs 100` / `--resume_from_checkpoint /data/piper/output-fly-convnext6-poc/last.ckpt` / その他は本 PoC と同一
- **出力分離**: `/data/piper/output-fly-convnext6-poc-100ep/` に separate directory で出力 (50 epoch ckpt との混在を回避)

AI-13 (7 ランタイム smoke) / AI-14 (audio-parity-contract.toml) への注意点:

- 本 PoC の ckpt は ONNX export 未実施。 AI-13 が 7 ランタイム smoke を走らせる前に AI-12 経由で ONNX export を完了させる必要がある
- `[fly_convnext6]` section の `audio-parity-contract.toml` 追加は AI-14 が担当、 本チケットでは contract 自体を編集しない (G-1.2 baseline 編集禁止 gate)
- pairwise SNR ≥ 30 dB の検証は AI-13 で全 7 ランタイム間で実施、 本チケットでは Python forward smoke のみで十分

PR #222 / #537 rebase (AI-16 / AI-17) 時の注意:

- 本 PoC で記録された WandB run / proxy MOS / RTF は PR #537 merge 前の **torch 2.2 / py3.11** baseline。 PR #537 merge 後の bf16-mixed 再学習は AI-16 で別途実施し、 数値ドリフトを `audio-parity-contract.toml` tolerance に反映
- PR #222 merge 時に `models.py` の `dec` 選択分岐が FiLM rank-aware 化と再構成される (AI-17)。 本 PoC の `FlyConvNeXtDecoder` instance は spk_proj / FiLM を使用しないため rebase 影響は最小、 ただし `decoder_type='fly_convnext6'` の dispatch 経路だけ AI-17 で再 verify が必要

## 関連ドキュメント

- 親マイルストーン: [../milestones/M3-fly-tts-parallel-harness.md](../milestones/M3-fly-tts-parallel-harness.md)
- 親計画 §6: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- Decoder Upgrade deep-dive §2.5 Phase 3 Q13: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 改善調査統合 §G-A1 / §H Track 7: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- 既存学習テンプレート: [/Users/s19447/Documents/piper-plus/CLAUDE.md](../../../CLAUDE.md) §「学習テンプレート」Template B
- 既存仕様: [docs/spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml) (AI-14 で `[fly_convnext6]` section 追加)
- 論文: [FLY-TTS PDF (Guo Interspeech 2024)](https://www.isca-archive.org/interspeech_2024/guo24c_interspeech.pdf) ConvNeXt × 6 + iSTFT (nfft=1024, hop=256)、 MOS 4.12
- 影響 PR: [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) (AI-16 で再 baseline 化)
- 依存チケット: [AI-06 FLY-TTS ConvNeXt6 decoder 実装](AI-06-fly-decoder-impl.md)
- 後続チケット: [AI-12 3 variant benchmark + UTMOS proxy MOS](AI-12-benchmark-3-variants.md) / [AI-05 iSTFTNet2-MB PoC 学習](AI-05-istftnet2-training.md) (失敗時の保険切替先)
