# AI-05: iSTFTNet2-MB PoC 学習 50 epoch

## メタ情報

- ID: AI-05
- 親マイルストーン: [M2](../milestones/M2-istftnet2-mb-backbone.md)
- 工数見積: 1.5 日
- 依存チケット: AI-03 (iSTFTNet2-MB 1D-2D backbone 実装), AI-04 (`test_istftnet2_generator.py` 新規)
- 後続チケット: AI-12 (`tools/benchmark/` に 3 variant 追加 + UTMOS proxy MOS), AI-08 (MS-Wavehax vocoder 実装 — 本チケット成果の A-1 baseline ckpt が wavehax FT の acoustic 元として消費される)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items AI-05 / §4 PoC 設計 / §4.4 Training Plan / §4.6 Benchmarks 目標値](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

本チケットは M2 (iSTFTNet2-MB 1D-2D backbone PoC 動作確認) の数値的 Exit gate を確定させる「学習実行」工程である。 AI-03 で実装された `_forward_1d2d` 経路と AI-04 の単体テストが正しく forward path を保証しただけでは、 Q13 (iSTFTNet2-MB に関する zero prior art) のリスクは消えない。 50 epoch 学習を CSS10 JA 単一話者で完走させて初めて、 計画 §4.6 の 4 指標 (UTMOS proxy MOS / CPU RTF / params footprint / 7 ランタイム smoke の前段) のうち品質指標 2 件 (MOS と RTF) に一次データを与えられる。

計画 §6 AI-05 は本タスクを「`decoder_type='istftnet2_mb_1d2d'`、 6lang base ckpt から 1D 部分のみ warm start」と規定しており、 親計画 §4.2 の互換性制約 (出力 shape `[B,1,T]` 不変 / `subband_conv_post` / `OnnxISTFT` / `PQMF` 完全流用) を維持しながら、 既存 6lang MB-iSTFT base ckpt (`/data/piper/output-multilingual-6lang-mb-istft/multilingual-6lang-mb-istft-scratch-75epoch.onnx` 由来 ckpt) の `conv_pre` / `cond` / `iSTFT` / `PQMF` 重みを warm start として流用する。 2D Block × 4 の新規 layer のみ random init される設計を実機で検証することが目的である。

上流からは AI-03 が `decoder_type` 分岐済み `mb_istft.py`、 AI-04 が forward path 緑の単体テストを引き渡す。 下流への引き渡しは大別して 2 系統あり、 (1) AI-12 (benchmark harness) へは 50 epoch ckpt + ONNX export + WandB run id を渡し proxy MOS / RTF 計測の対象とし、 (2) AI-08 (MS-Wavehax) へは本チケットで得た A-1 baseline ckpt を acoustic model として freeze する形で vocoder-only FT の起点を提供する。 M4 の dual vocoder PoC が成立するかどうかは本チケットで warm start が機能するかどうかにかかっている。

## 実装内容の詳細

本チケットは新規実装ではなく「学習スクリプト起動 + 監視 + ckpt 提出」の運用工程だが、 起動前に幾つかの設定整備が必要である。

**起動コマンド (CLAUDE.md Template B 派生):**

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
    --dataset-dir /data/piper/dataset-css10-ja-poc \
    --prosody-dim 16 \
    --accelerator gpu --devices 1 --precision 32-true \
    --max_epochs 50 --batch-size 4 --samples-per-speaker 4 \
    --checkpoint-epochs 10 --quality medium \
    --base_lr 2e-5 --disable_auto_lr_scaling \
    --ema-decay 0.9995 --max-phoneme-ids 400 --no-wavlm \
    --val-every-n-epochs 5 --audio-log-epochs 5 \
    --decoder-type istftnet2_mb_1d2d \
    --resume-from-multispeaker-checkpoint /data/piper/output-multilingual-6lang-mb-istft/last.ckpt \
    --default_root_dir /data/piper/output-css10-ja-istftnet2-mb-poc \
    > training-istftnet2-mb-poc.log 2>&1 &
```

**編集対象ファイル:**

- `src/python/piper_train/__main__.py` (関数 `main` / 引数定義部、 行範囲は AI-03 で増加するため目安として L80-L160 付近)
  - AI-03 で導入される `--decoder-type {mb_istft_1d, istftnet2_mb_1d2d}` CLI フラグが本チケットの起動で初めて `istftnet2_mb_1d2d` 値で消費される。 default は `mb_istft_1d` (G-1.9 後方互換 gate)。
  - 本チケットで CLI フラグ自体は追加しないが、 起動コマンドが受理されることを smoke で確認する。
- `src/python/piper_train/vits/lightning.py` (関数 `load_multispeaker_checkpoint` / 既存 1D 部分のみ warm start するロジックは AI-03 で追加されている前提)
  - 本チケットでは編集しない。 ただし warm start 失敗時 (state_dict key mismatch) は `--from-scratch` fall back を起動する判断を本チケット内で行う (Risk R2)。

**新規ファイル:**

- `docs/runbooks/ai-05-istftnet2-mb-training.md` (~80 LoC、 任意 — 起動手順 / WandB project 名 / Day-by-Day Exit 判定基準を runbook 化)
- ckpt 配置先: `/data/piper/output-css10-ja-istftnet2-mb-poc/` 配下に `epoch=10-step=...ckpt` / `last.ckpt` / `best.ckpt` (val_loss minimum) / WandB run metadata

**既存 default 値 / 互換維持の制約:**

- 6lang base ckpt の resume が機能することが本チケットの暗黙の前提。 `_forward_1d2d` の 2D Block × 4 は random init、 `conv_pre` / `subband_conv_post` / `iSTFT` / `PQMF` は state_dict 一致で読み込まれる。 AI-03 の実装が両経路で共有重みを正しく登録していることが pre-flight smoke (1 step) で確認できる。
- G-1.9 後方互換 gate: 本チケット起動中に `decoder_type='mb_istft_1d'` の既存 1D 学習が回せること (regression なし) を別ターミナルで 1 epoch sanity 走らせて確認する。

**PR #222 / PR #537 との conflict 回避策 (計画 §3 Conflict Map 該当行抜粋):**

- 計画 §3 の `lightning.py` 行: 「`_collect_g_params` hook、 wavehax LR、 MEDIUM (WavLM-D + DINO 拡張)、 LOW (bf16-mixed)、 A-1/A-2 先行で hook 化」 — 本チケットは `lightning.py` を編集しないため PR #222 / #537 とも conflict ゼロ。
- 計画 §3 の `models.py` 行: 「`dec_wavehax` sibling 追加、 `decoder_type` 受領、 HIGH (spk_proj 統合点)、 NONE、 A-1/A-2 先行で隔離」 — 本チケットは学習起動のみで `models.py` も touch しない。 AI-03 が既に `decoder_type` 受領を完了している前提。
- 数値ドリフト: 本チケットは PR #537 merge 前の現行 dev (torch 2.2 / py3.11 / CUDA 12.6) で実施。 `--precision 32-true` を強制して TF32-on / bf16-mixed の影響を回避し、 M6 (AI-16) で PR #537 merge 後に再 benchmark する際の参照点を確保する。
- ONNX export は本チケットでは学習完了後の smoke 用に 1 回行うのみ。 PR #222 の ONNX I/O 変更 (sid→speaker_embedding[192]) は本チケット範囲外で、 export 経路の I/O 同期は M6 AI-17 で行う。

**設定 default 値、 新規 CLI フラグ:**

- 本チケットでは新規 CLI フラグは追加しない。 AI-03 で追加される `--decoder-type` を `istftnet2_mb_1d2d` 値で起動するのみ。
- `noise_scale=0.667` 固定 (PR #222 の noise_scale デフォルト変更影響を排除、 計画 §6 AI-02 の baseline と同条件)。
- `--max-phoneme-ids 400` (Template B 既定)、 `--no-wavlm` (V100 想定で GPU メモリ節約)、 `--audio-log-epochs 5` で WandB に val 音声を 10 回 upload。

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|-----------|---------|
| Training Operator (ML) | 1 | PyTorch Lightning / WandB / NCCL / pyopenjtalk / piper_train 内部知識 | 起動コマンド作成と nohup 監視、 OOM/NCCL エラーの一次対応、 Day-by-Day Exit 判定 (proxy MOS / forward p50 中間計測)、 warm start 失敗時の `--from-scratch` fall back 判断 |
| Test Engineer | 1 | pytest / ONNX runtime / UTMOS v2 / Xeon ベンチ環境構築 | 50 epoch ckpt の ONNX export smoke、 forward shape `[B,1,T]` assert、 既存 1D 経路 regression test (G-1.9 gate)、 UTMOS proxy MOS スクリプトの先行利用と baseline 計測 |
| ML Researcher (Reviewer) | 1 | iSTFTNet2 論文 (arXiv 2308.07117) / MB-iSTFT / pixel-shuffle / Q13 zero prior art の文脈把握 | 中間 ckpt の audio 聴感レビュー、 proxy MOS -0.2 未満かつ p50 +10% 以上で打ち切り判断、 R3 早期失敗指標の発火確認、 50 epoch 完走時の採否一次レポート |

合計 3 名。 学習が 1 GPU 約 40 時間なので Training Operator は実質非同期監視 (nohup + WandB 通知) で済むが、 Day 0 (warm start smoke) と Day 4 (中間 ckpt 評価) は 3 名同時参加が望ましい。

## 提供範囲 (Scope)

### 含むもの

- CSS10 JA 単一話者データセット (`/data/piper/dataset-css10-ja-poc/`) に対する `decoder_type='istftnet2_mb_1d2d'` での 50 epoch 学習完走
- 6lang MB-iSTFT base ckpt からの warm start 起動と pre-flight smoke (1 step + 1 epoch)
- 学習中の WandB audio log (5 epoch ごと、 計 10 回)、 train/val loss 推移、 GPU 利用率モニタ
- 50 epoch 最終 ckpt + best.ckpt (val_loss min) の `/data/piper/output-css10-ja-istftnet2-mb-poc/` への配置
- ONNX export smoke (`uv run python -m piper_train.export_onnx` で `istftnet2-mb-1d2d-50epoch.onnx` 生成、 forward smoke pass)
- Xeon E5-2650 v4 / 25 phoneme 英文での CPU p50 単発計測 (warmup 5 + 30 runs、 詳細 RTF benchmark は AI-12 に委譲)
- 中間 ckpt (25 epoch 相当) での Day 4 proxy MOS と forward p50 の一次計測 (R3 早期失敗指標の機械化)
- 学習 hparam (precision / no-wavlm / noise_scale / lr / batch size) の ckpt メタデータと runbook への記録 (M6 再 baseline の参照点)

### 含まないもの (Out of Scope)

- benchmark harness 本体 (AI-12 / M5)、 `tools/benchmark/models.yaml` への entry 追加 (AI-12)、 UTMOS v2 wrapper (`proxy_mos.py`) の新規実装 (AI-12) — 本チケットは AI-12 完成版を**先行利用**するのみで、 wrapper の正式リリースは M5 で扱う
- 7 ランタイム smoke + pairwise SNR 検証 (AI-13 / M5) — 本チケットは Python forward smoke のみ
- `audio-parity-contract.toml [istftnet2_mb_1d2d]` section 追加 (AI-14 / M5)
- MS-Wavehax との dual vocoder 統合学習 (AI-10 / M4) — 本チケット ckpt の acoustic 利用は AI-08 / AI-10 で行う
- PR #537 merge 後の bf16-mixed + pytest 9 再 benchmark (AI-16 / M6)
- PR #222 merge 後の FiLM rank-aware 化 + ONNX I/O 同期 (AI-17 / M6)
- mobile EP (iOS CoreML MLProgram / Android NNAPI) smoke (R7、 PoC 範囲外)

## テスト項目

### Unit Tests

本チケットは学習運用工程のため新規 unit test は書かない。 ただし以下を既存テスト経由で確認する。

- `src/python/tests/test_istftnet2_generator.py::test_forward_1d2d_output_shape` (AI-04 で追加済み)
  - assert: `output.shape == (1, 1, T)` かつ `T == phoneme_count * 256` (4×4×16 = 256x upsampling)
- `src/python/tests/test_istftnet2_generator.py::test_params_count_within_budget` (AI-04 で追加済み)
  - assert: `0.78e6 <= total_params <= 0.88e6` (0.83M ± 0.05M)
- `src/python/tests/test_istftnet2_generator.py::test_default_decoder_type_is_mb_istft_1d` (AI-04 で追加済み、 G-1.9 後方互換 gate)
  - assert: `MBiSTFTGenerator(**kwargs).decoder_type == 'mb_istft_1d'` (引数省略時の default)
- 既存 `src/python/tests/test_mb_istft_generator.py` は **touch しない** (G-1.9 後方互換 gate)。 本チケット起動前に CI で全 green を確認する。

### E2E Tests

- **warm start smoke (Day 0 必須):** 起動コマンド + `--max_epochs 1` で 1 epoch 学習を回し、 (a) state_dict key mismatch なし、 (b) train_loss が初期値で `mb_istft_1d` baseline 同等オーダー (NaN/Inf 回避)、 (c) WandB val audio が再生可能であることを確認。 失敗時は `--from-scratch` fall back に切替。
- **50 epoch 学習完走 (本チケット中核):** 起動コマンドで nohup 実行、 GPU OOM / NCCL hang / loss NaN なく完走。 中間 ckpt 5 個 + best.ckpt + last.ckpt が生成される。
- **ONNX export round trip:** `uv run python -m piper_train.export_onnx /data/piper/output-css10-ja-istftnet2-mb-poc/last.ckpt /data/piper/output-css10-ja-istftnet2-mb-poc/istftnet2-mb-1d2d-50epoch.onnx --simplify` でエラーなし、 `onnxruntime` で同入力に対する PyTorch forward と ONNX forward の出力 SNR ≥ 40 dB (FP16 export なら ≥ 30 dB)。
- **CPU p50 単発計測:** Xeon E5-2650 v4 / 25 phoneme 英文で warmup 5 + 30 runs、 p50 を WandB summary に記録 (詳細は AI-12 に委譲、 本チケットは Exit gate 判定値のみ確保)。
- **WandB audio log 視聴:** 5/10/25/40/50 epoch の val 音声を ML Researcher が聴感レビューし、 baseline と同等以上の自然性を保っていることを記述付きで report。
- **計画 §4.6 数値目標との照合:** UTMOS proxy MOS が baseline ± 0.1 / params 0.83M ± 0.05M / CPU p50 < 20ms / 出力 `[B,1,T]` float32 を Exit Criteria として全件確認。

### 受入基準 (Acceptance Criteria)

計画 §4.6 Benchmarks 目標値 + M2 Exit Criteria より以下を満たす。

- UTMOS proxy MOS (CSS10 JA 200 test utt): baseline (AI-02 で取得済み 1D baseline) ± 0.1 以内
- CPU RTF (Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs): p50 < 20ms (target 18ms に +2ms 安全幅、 計画 §5 Milestone 2 Exit と一致)
- params: 0.83M ± 0.05M (AI-04 unit test で確認済みだが 50 epoch ckpt でも再計測)
- 出力 shape `[B,1,T]` float32 を Python forward smoke で assert
- 6lang base ckpt からの warm start ロードが state_dict key mismatch なしで成功
- 既存 `decoder_type='mb_istft_1d'` (default) 経路の 1 epoch sanity が同期間中に regression なく回ること (G-1.9 gate)
- WandB run id と `/data/piper/output-css10-ja-istftnet2-mb-poc/` 配下のファイル一覧を runbook に記録

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

- **R2 (6lang base ckpt resume の warm start 喪失)**: PR #222 merge 前に PoC を完走させる必要があり、 PR #222 が予想外に早く merge された場合は warm start が機能しなくなる。 本チケット起動前に PR #222 状態を `/watch-pr 222` で確認し、 ready 化していたら起動を 24h 待機して状態安定を確認する。 さらに `--from-scratch` fall back を Day 0 から準備し、 warm start smoke で state_dict mismatch が出たら即時切替。
- **R3 (Q13 zero prior art による 50 epoch 投資失敗)**: 50 epoch 完走が 40 時間 GPU を消費するため、 中盤で失敗が判明すると投資ロスが大きい。 mitigation として Day 4 (25 epoch 相当) に中間 ckpt で proxy MOS と forward p50 を計測し、 「proxy MOS が baseline -0.2 未満かつ p50 が baseline 比 +10% 以上」なら学習打ち切りを判断 (親 M2 文書のリスク章と整合)。 打ち切り判断は ML Researcher + Training Operator の 2 名合意で行う。
- **R8 (1 GPU 直列スケジュール衝突)**: 本チケットは 1 GPU を約 40 時間占有する。 他チケット (AI-02 baseline / AI-07 FLY-TTS) の学習と GPU 競合する可能性があり、 起動前に GPU 占有状況を `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` で確認。 競合時は CSS10 JA 14h を 7h subset に絞り epoch 数 2 倍で代替する選択肢を維持。
- **数値ドリフトの落とし穴**: `--precision 32-true` を必ず指定。 ckpt メタデータに `precision='32-true'` を記録し、 M6 (AI-16) で PR #537 merge 後 bf16-mixed 再 benchmark する際の参照点を明示する。
- **warm start 部分 load の落とし穴**: `_forward_1d2d` の新規 2D Block × 4 は random init される一方、 `conv_pre` / `subband_conv_post` / `iSTFT` / `PQMF` は 1D ckpt と key 一致で load される。 PyTorch Lightning の `strict=False` 動作が AI-03 実装で正しく `missing_keys` のみ許可 (`unexpected_keys` は fail) になっていることを smoke で確認する必要がある。
- **ONNX export の op coverage**: `_forward_1d2d` 経由の export で `Conv2d / Reshape / Transpose` 以外の op (例: pixel-shuffle が `DepthToSpace` に展開される / unsupported `Einsum` 等) が紛れ込んでいないかを `onnx.checker` + 目視で確認。 R7 (mobile EP CPU fallback) は本チケット範囲外だが op audit は本チケットで初手として行う。

### レビュー項目 (チェックリスト)

- [ ] default decoder_type 不変 (G-1.9 後方互換、 本チケット起動が `mb_istft_1d` default を変更していないこと)
- [ ] [mb_istft_1d] audio parity 不変 (G-1.2 baseline 編集禁止、 並行して 1D 1 epoch sanity が regression なし)
- [ ] ONNX I/O 不変 (PR #222 二重同期回避、 export 時の input/output 名と shape が baseline と byte-for-byte 一致)
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響を audio-parity-contract tolerance に反映済み (本チケットは現行 dev で実施、 `precision='32-true'` を ckpt メタに記録し M6 AI-16 で再 baseline を行う旨を runbook に明記)
- [ ] warm start で `unexpected_keys` が空、 `missing_keys` が `_forward_1d2d` 2D Block 部分のみ
- [ ] WandB run id と ckpt 一式パスが runbook に記録され、 AI-08 / AI-12 から参照可能
- [ ] 中間 ckpt (25 epoch 相当) の proxy MOS / forward p50 計測値が Day 4 時点で取得済み
- [ ] PR #222 / #537 の最新状態を起動前 / 完走後の 2 ポイントで `/watch-pr` で確認
- [ ] ONNX export 時の op set audit で `Conv2d / Reshape / Transpose` 以外の想定外 op が含まれていない

## 一から作り直すとしたら (Ticket-level rethinking)

このチケットを一から設計するとしたら最初に再考すべきは「50 epoch 完走を Exit gate に置く」判断である。 親 M2 文書の rethinking 章でも触れたとおり、 Q13 zero prior art への投資判断は 50 epoch まで走らせなくても 5-10 epoch の sanity + 中間 RTF 計測で 8 割方の見通しが立つ。 本チケットを「AI-05a: 5 epoch sanity + RTF 中間計測 (0.5d)」と「AI-05b: 30-50 epoch 本学習 (1d)」に分割し、 AI-05a の Exit が green なら AI-05b に進む段階的 gate 構造が代替案として有力である。 これなら R3 (50 epoch 投資失敗) のリスクを最大 0.5d の損失に抑えられる。 現案が単一チケット 1.5d としているのは「M2 Exit gate を一つにまとめる」運用上の簡潔さと、 1 GPU 直列で stop-start を繰り返すオーバーヘッド回避が動機だが、 トレードオフとして「失敗時の sunk cost が大きい」点は受け入れている。

次に再考すべきは「warm start 経路の検証を本チケットで行うか別チケットに切るか」である。 現案は warm start smoke を Day 0 の本チケット内で済ませる前提だが、 これは AI-03 (実装) と AI-05 (学習) の境界が曖昧になる原因でもある。 別案として「AI-03 完成条件に `state_dict_load_smoke.py` を含めて 1D ckpt → 2D 経路の load 成功までを AI-03 のスコープにし、 AI-05 は load 後の純粋な学習運用に専念する」設計があり得る。 これなら本チケット (AI-05) は 50 epoch 学習の運用のみに責務が絞られ、 warm start 失敗時の `--from-scratch` 判断も AI-03 段階で完結する。 採用案 (本チケットで Day 0 smoke 担当) を選んだのは load smoke は実学習起動の文脈でしか発覚しない問題 (lr scheduler / EMA / DataLoader 互換) を含むためで、 AI-03 単体の unit test では拾えない範囲を本チケットでカバーする実用上の判断である。

3 点目の代替案として、 学習データセットを CSS10 JA 14h 単体ではなく「つくよみちゃん 100 utt smoke + CSS10 JA 14h 本学習の二段構成」にする選択肢を再評価できる。 つくよみちゃん 100 utt は親 M2 文書でも触れたとおり 30 分以内で 5 epoch 回せる ため、 本チケットの Day 0 smoke を CSS10 JA でなく つくよみちゃん で先行させれば warm start + forward path の異常を 10 倍速く検出できる。 採用案 (CSS10 JA 単体) を選んだのは benchmark との同条件 (200 test utt が CSS10 JA 由来) を維持する利点と、 二段構成での dataset 切替バグ混入リスクの回避が動機だが、 R3 早期検出には つくよみちゃん 並走の方が情報価値が高い余地は残る。 M2 全体で 1 度だけ採用判断する設計レビューを開く価値がある。

## 後続タスクへの連絡事項

- **AI-12 (benchmark harness、 M5) への引き渡し**:
  - ckpt 絶対パス: `/data/piper/output-css10-ja-istftnet2-mb-poc/last.ckpt` および `best.ckpt` (val_loss minimum)
  - ONNX 絶対パス: `/data/piper/output-css10-ja-istftnet2-mb-poc/istftnet2-mb-1d2d-50epoch.onnx` (FP16 export、 `--simplify` 適用済み)
  - `tools/benchmark/models.yaml` に追加すべき entry 名: `css10-ja-istftnet2-mb` (M2 M5 命名規約と整合)
  - 暫定 RTF 計測値: 本チケット Day 終了時点で Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs の p50 を runbook に記録、 AI-12 の `expected_p50_ms` gate の参照点
  - WandB run id を runbook と AI-12 の models.yaml comment に転記
- **AI-08 (MS-Wavehax vocoder 実装、 M4) への引き渡し**:
  - A-1 baseline ckpt (本チケット成果) を acoustic model として freeze、 vocoder-only FT の起点として `best.ckpt` を参照する
  - 引き渡し時の `subband_conv_post` 出力の中間 tensor shape: `[B, num_subbands=4, T_subband]` (T_subband = phoneme_count * 64)、 wavehax 入力契約として AI-10 着手前に確定
  - 「`decoder_type='istftnet2_mb_1d2d'` で訓練された ckpt」であることを `hparams.yaml` で明示し、 AI-10 の `--freeze-acoustic` 起動時に decoder_type 識別が機能することを smoke で確認
- **暫定 decoder_type default**: 本チケット完了時点でも default は `mb_istft_1d` のまま (リリース時に切替判断は M6 AI-18 採否判定で行う)。 本チケット起動で `--decoder-type istftnet2_mb_1d2d` を明示することで default 不変を保つ。
- **PR #222 rebase 時に注意すべき箇所** (M6 AI-17 引き渡し):
  - `MBiSTFTGenerator._apply_film` が `_forward_1d2d` の 4D `[B,C,F,T]` に対しても channel-axis split (dim=1) で動作するよう rank-aware 化する必要あり (本チケットは 1D-2D 経路で FiLM 未統合のまま完走するため M6 で初対面)
  - ONNX export の I/O 名 `sid → speaker_embedding[192]` 変更を本チケットで生成した ONNX export スクリプト経路にも反映する必要あり
- **PR #537 merge 後の再 baseline** (M6 AI-16 引き渡し):
  - 本チケットの ckpt は `precision='32-true'` で訓練されているため、 PR #537 merge 後の bf16-mixed default 学習結果と直接比較する場合は `audio-parity-contract.toml` の tolerance 拡張が必要
  - 本チケットの WandB run id を AI-16 の比較対照群として転記する
- **runbook 配置**: `docs/runbooks/ai-05-istftnet2-mb-training.md` に Day-by-Day Exit 判定 / warm start smoke 手順 / `--from-scratch` fall back コマンド / 中間 ckpt 評価コマンドを記録し、 AI-08 / AI-12 / AI-16 / AI-17 から参照可能にする

## 関連ドキュメント

- 親マイルストーン: [../milestones/M2-istftnet2-mb-backbone.md](../milestones/M2-istftnet2-mb-backbone.md)
- 親計画 §6 AI-05 / §4 PoC 設計 / §4.4 Training Plan / §4.6 Benchmarks: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査統合 §A-1: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Decoder Upgrade deep-dive §2.5 Phase 4 Risk 評価: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 学習テンプレート (CLAUDE.md Template B): [../../../CLAUDE.md](../../../CLAUDE.md)
- 既存 spec (M5 で `[istftnet2_mb_1d2d]` section 追加予定): [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml)
- 論文: [iSTFTNet2 (arXiv 2308.07117)](https://arxiv.org/pdf/2308.07117) Kaneko et al., Interspeech 2023, NTT
- 影響 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — M6 AI-17 で rebase 統合判定
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — M6 AI-16 で再 baseline
