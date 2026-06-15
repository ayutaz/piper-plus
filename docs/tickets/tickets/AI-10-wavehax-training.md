# AI-10: MS-Wavehax vocoder-only FT 学習 30 epoch

## メタ情報

- ID: AI-10
- 親マイルストーン: [M4](../milestones/M4-mswavehax-dual-vocoder.md)
- 工数見積: 1 日
- 依存チケット: AI-09 (configure_optimizers に `_collect_g_params` hook 追加)
- 後続チケット: AI-11 (voice.py streaming 閾値切替), AI-12 (3 variant benchmark + UTMOS proxy MOS)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items / §4.3 A-2 PoC 設計 / §4.4 Training Plan](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

本チケットは [親計画 §6 Milestone 4](../../research/implementation-plan-a1-a2-2026-06-16.md) の **AI-10** に対応する。 AI-08 で実装した sibling `self.dec_wavehax` (`wavehax.py`、 0.332M params、 spectral envelope + harmonic-aware shift + complex residual + `OnnxISTFT(n_fft=64, hop=16)`) と AI-09 で導入した `_collect_g_params` hook を前提として、 **CSS10 JA 単一話者** で **vocoder-only FT 30 epoch** を完走する。 acoustic model (text encoder / posterior encoder / flow / duration predictor) は **freeze** したまま vocoder 部のみを更新し、 短文 streaming 経路で MB-iSTFT 比 低 p50 chunk latency を達成できる軽量 vocoder ckpt を作る。

上流 AI-09 からは `_collect_g_params` hook 経由で `self.dec_wavehax.parameters()` が `opt_g` に集約される構造を受け取る。 `--freeze-acoustic` フラグを併用することで acoustic 側の trainable parameters を 0 に落とし、 勾配計算と GPU メモリを vocoder 部に局所化する。 これにより batch を 4 から 8 まで上げられる余地が生まれる (V100 想定、 CLAUDE.md Template B 拡張) ため、 30 epoch を ~12h で完走させる。

下流 AI-11 (streaming 閾値切替) へは ckpt パス `/data/piper/output-css10-ja-mswavehax-poc/last.ckpt` と export 済み companion ONNX `/data/piper/output-css10-ja-mswavehax-poc/wavehax.onnx` を引き渡し、 `PiperVoice(wavehax_model_path=..., streaming_threshold_phonemes=25)` の wiring に着手できる前提を作る。 AI-12 (benchmark) へは `models.yaml` 追加用の最終 ckpt + ONNX + WandB run URL を引き渡し、 Python 単独 chunk-level p50/p95 ベンチを開始できる状態にする。 本チケットは「**学習を回すだけのチケット**」 ではなく、 後続 2 チケットの blocking を 1 日で解除する **gating ticket** として位置づける。

## 実装内容の詳細

### 編集対象ファイル

- **`src/python/piper_train/__main__.py`** (関数: `main()` の `argparse` ブロック、 行範囲: 既存 `--enable-wavehax` / `--freeze-acoustic` フラグ追加点に隣接) — 学習 entry point。 AI-08 で追加した `--enable-wavehax` と本チケットで追加する `--wavehax-lr 2e-4` / `--freeze-acoustic` を最終確認し、 CLI 引数を `VitsModel.__init__` に流す
- **`src/python/piper_train/vits/lightning.py`** (関数: `VitsModel.__init__`, `VitsModel.configure_optimizers`, `VitsModel.training_step`) — AI-09 で導入済みの `_collect_g_params` hook が `self.net_g.dec_wavehax.parameters()` を `opt_g` に集約することを確認し、 `freeze_acoustic` flag 受領時に acoustic 側 (text_encoder / posterior_encoder / flow / dp) の `requires_grad = False` を `__init__` 末尾で適用する分岐を追加 (新規 ~15 LoC)
- **学習スクリプト (新規)** `scripts/train_mswavehax_poc.sh` (~30 LoC) — CLAUDE.md Template B (single-speaker FT) ベース、 後述の差分パラメータを反映した nohup 起動 wrapper。 commit 対象 (再現性確保のため)
- **学習ログ出力先** `/data/piper/output-css10-ja-mswavehax-poc/` — ckpt + WandB metadata + `training.log` を集約。 commit 対象外 (ckpt は HF Hub に別途 upload)
- **export 追加経路** `src/python/piper_train/export_onnx.py` — AI-08 で追加した `--decoder-branch wavehax` 引数を本チケットの最終 ckpt に対して走らせ、 companion ONNX を export。 本チケットでは export 経路のコード変更はしない (AI-08 で完了済み前提)、 実行のみ

### 新規ファイル

- `scripts/train_mswavehax_poc.sh` (~30 LoC) — 学習起動 wrapper

### 既存 default 値 / 互換維持の制約 (G-1.9 後方互換 gate)

- **`decoder_type` default 不変**: AI-08 / AI-09 を経て `enable_wavehax=False` がデフォルトであることを `VitsModel.__init__` の signature で再確認。 本チケットの学習は `--enable-wavehax` を明示指定して走らせるため、 既存 1D MB-iSTFT 経路は完全に保持される
- **`[mb_istft_1d]` baseline 編集禁止 (G-1.2)**: 本チケットは `audio-parity-contract.toml` を touch しない。 AI-14 (M5) で `[mswavehax]` section を追加する際の素材として ckpt + ONNX を残すのみ
- **EMA `shadow_params` 不変**: vocoder-only FT で `self.dec_wavehax` が EMA の追跡対象に正しく入ることを 1 epoch sanity で確認 (lightning.py の EMA update が `self.net_g.parameters()` 全体を見る前提に依存、 sibling 追加で自動的に追跡される設計)
- **`infer_forward model_g.dec(...)` 不変**: 本チケットの学習で `dec_wavehax` 経路を踏むのは training_step の forward のみ。 inference (TTS 経路) は `enable_wavehax=False` 既存挙動を維持

### PR #222 / PR #537 との conflict 回避策

親計画 §3 Conflict Map より:

- **PR #222 (Multi-scale FiLM 改造) との関係**: 本チケットは `mb_istft.py` を touch しない (AI-08 / AI-09 で sibling 構造に閉じ込め済み)。 学習結果の ckpt は `dec_wavehax` のみが update されており、 既存 `self.dec` (= MBiSTFTGenerator) の重みは freeze で不変。 PR #222 rebase 時に Multi-scale FiLM が `MBiSTFTGenerator.forward` を改造しても、 本チケットの ckpt は `dec_wavehax` 部のみが独立しているため衝突しない (companion ONNX 配布形態が同じ性質)
- **PR #222 (WavLM-D + DINO opt_d/opt_g 拡張) との関係**: AI-09 で導入した `_collect_g_params` hook が PR #222 rebase 時に `dec.spk_proj.parameters()` 追加の 1 行差分で取り込める構造になっていることを、 本チケットの 1 epoch sanity 時に `configure_optimizers` の return shape (`[opt_g, opt_d]`) が不変であることで再 verify する
- **PR #537 (TF32-on + bf16-mixed) との関係**: 本チケットは PR #537 merge **前** の現行 dev (torch 2.2 / py3.11 / CUDA 12.6 / `--precision 32-true`) で完走させる。 wavehax の `torch.fft` / wavelet ops が bf16-mixed で 1e-3 magnitude drift を起こすリスク (Risk R5) は PR #537 merge 後の M6 / AI-16 で torch 2.11 sandbox + 5 epoch sanity に切り出し、 本チケットでは blocking させない

### 設定 default 値 / 新規 CLI フラグ

| フラグ | 値 | 由来 |
|--------|-----|------|
| `--enable-wavehax` | 必須 (本チケットで明示指定) | AI-08 で追加 |
| `--freeze-acoustic` | 必須 (本チケットで明示指定) | 本チケットで CLI フラグの最終確認 |
| `--wavehax-lr` | `2e-4` | 親計画 §6 AI-10 行 208 から引用、 acoustic FT の `base_lr 2e-5` より 10x 大きい |
| `--max_epochs` | `30` | 親計画 §4.4 から、 vocoder-only FT 範囲 |
| `--batch-size` | `4` (V100 standard) / `8` (memory 余裕時) | 親計画 §4.4 base + acoustic freeze で勾配が局所化されるため上振れ余地 |
| `--samples-per-speaker` | `4` | 親計画 §4.4 |
| `--checkpoint-epochs` | `5` | 30 epoch 中 6 段階で sanity check |
| `--val-every-n-epochs` | `5` | WandB audio log と同期 |
| `--audio-log-epochs` | `5` | val と同期 |
| `--ema-decay` | `0.9995` | CLAUDE.md Template B |
| `--no-wavlm` | 有効 | V100 想定 + vocoder-only FT で WavLM-D は不要 |

### 起動コマンド (pseudo)

```bash
# scripts/train_mswavehax_poc.sh
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
    --dataset-dir /data/piper/dataset-css10-ja-poc \
    --prosody-dim 16 \
    --accelerator gpu --devices 1 --precision 32-true \
    --max_epochs 30 --batch-size 4 --samples-per-speaker 4 \
    --checkpoint-epochs 5 --quality medium \
    --base_lr 2e-5 --disable_auto_lr_scaling \
    --ema-decay 0.9995 --max-phoneme-ids 400 --no-wavlm \
    --val-every-n-epochs 5 --audio-log-epochs 5 \
    --enable-wavehax --freeze-acoustic --wavehax-lr 2e-4 \
    --resume-from-multispeaker-checkpoint /data/piper/output-css10-ja-poc-baseline/last.ckpt \
    --default_root_dir /data/piper/output-css10-ja-mswavehax-poc/ \
    > /data/piper/output-css10-ja-mswavehax-poc/training.log 2>&1 &
```

### 学習後の export

```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
    --decoder-branch wavehax \
    /data/piper/output-css10-ja-mswavehax-poc/last.ckpt \
    /data/piper/output-css10-ja-mswavehax-poc/wavehax.onnx
```

## エージェントチームの役割と人数

| 役割 | 人数 | 責任範囲 |
|------|-----|---------|
| ML Trainer | 1 | CLAUDE.md Template B 拡張、 nohup 起動、 WandB 監視 (epoch 5 / 10 / 20 / 30 で proxy MOS と vocoder loss を chart 確認)、 異常検知時の early termination 判断、 `--freeze-acoustic` 経路の正しさ確認 (acoustic params の `requires_grad=False` が trainable param count に反映されているか) |
| ONNX Engineer | 1 | 学習完了後の companion ONNX export (`--decoder-branch wavehax`)、 ONNX shape inference + I/O assert (`phoneme_ids` / `input_lengths` / `scales` / `sid|speaker_embedding` → `[B, 1, T]` float32 不変)、 ORT session 起動 sanity (CPU EP / opset 15+) |
| Test Engineer | 1 | `test_wavehax_vocoder.py` の 1 epoch sanity tier (forward-only smoke は AI-08 で完了済み、 本チケットは learning curve の monotonic decrease assert + EMA shadow_params 正常更新 assert を追加)、 `enable_wavehax=False` 既存経路の forward-only smoke が完全不変であることを CI で gate (G-1.9) |

必要スキル: PyTorch (DDP 不要、 single GPU)、 PyTorch Lightning (EMA / configure_optimizers / freeze 制御)、 ONNX Runtime CPU EP、 WandB chart 解釈、 audio quality 1 次判定 (UTMOS proxy 起動は AI-12 / M5 範囲だが trend を耳で確認)。

## 提供範囲 (Scope)

### 含むもの

- `--enable-wavehax --freeze-acoustic --wavehax-lr 2e-4` での 30 epoch vocoder-only FT 完走
- ckpt `/data/piper/output-css10-ja-mswavehax-poc/last.ckpt` の生成
- companion ONNX `/data/piper/output-css10-ja-mswavehax-poc/wavehax.onnx` の export と shape sanity
- WandB run の audio log (epoch 5/10/15/20/25/30 で 4 サンプル合成、 baseline と耳比較)
- `scripts/train_mswavehax_poc.sh` を再現性のため commit
- 学習中の異常 (NaN / loss explosion / acoustic params が誤って update された痕跡) の検知と report
- 1 epoch sanity 時に `_collect_g_params` hook が AI-09 の意図どおり `dec_wavehax.parameters()` を `opt_g` に集約していることを `print(len(list(opt_g.param_groups[0]['params'])))` ベースで verify

### 含まないもの (Out of Scope)

- **`PiperVoice` streaming 閾値切替** — AI-11 で実装、 本チケットでは API 設計に介入しない
- **3 variant benchmark + UTMOS proxy MOS** — AI-12 (M5 / blocked by 本チケット完了) で実施、 本チケットは Python 単独の audio log 耳判定にとどめる
- **7 ランタイム companion ONNX 動作確認** — AI-13 (M5)、 本チケットは Python ORT CPU EP の 1 推論 smoke のみ
- **`audio-parity-contract.toml` への `[mswavehax]` section 追加** — AI-14 (M5)、 本チケットは contract を一切 touch しない (G-1.2)
- **PR #222 rebase 後の FiLM rank-aware 化への対応** — AI-17 (M6)
- **PR #537 merge 後の bf16-mixed + TF32-on での再学習** — AI-16 (M6)

## テスト項目

### Unit Tests

- **`src/python/tests/test_wavehax_vocoder.py::test_freeze_acoustic_zero_grad`** (新規 ~30 LoC)
  - assert: `--freeze-acoustic` 有効時、 `VitsModel.training_step` 後に `model.net_g.enc_p.parameters()` / `enc_q.parameters()` / `flow.parameters()` / `dp.parameters()` の grad が `None` または 0-norm
  - assert: 一方で `model.net_g.dec_wavehax.parameters()` の grad は non-zero
- **`src/python/tests/test_wavehax_vocoder.py::test_collect_g_params_includes_wavehax`** (新規 ~20 LoC)
  - assert: `enable_wavehax=True` 時、 `model._collect_g_params()` が返す iterable に `model.net_g.dec_wavehax.weight` (代表 param) を含む
  - assert: `enable_wavehax=False` 時、 同 iterable に `dec_wavehax` 系 param を含まない (AI-09 hook の both-direction 検証)
- **`src/python/tests/test_wavehax_vocoder.py::test_ema_shadow_includes_wavehax`** (新規 ~20 LoC)
  - assert: 1 step optimizer.step 後、 `model.ema_state_dict()` のキーに `net_g.dec_wavehax.*` が含まれる
- **既存 `src/python/tests/test_mb_istft_generator.py` は touch しない** (G-1.9 後方互換 gate、 default 経路の baseline 不変)

### E2E Tests

- **30 epoch 学習完走 sanity**
  - `training.log` の最終 epoch で `vocoder_loss` (mel-loss + sub_stft_loss + adversarial_loss) が epoch 1 比で **monotonic decrease** (許容: 局所的な揺れは認めるが trend が下降)、 epoch 1 / epoch 30 の平均 loss 比較で >= 10% 減少
  - `acoustic_loss` (text_encoder / flow / dp 由来) が `freeze-acoustic` で 0 から動かない (= acoustic 側の gradient backward が完全に切れている proof)
  - WandB audio log の epoch 30 サンプルが baseline (epoch 0 = warm start 直後) と耳判定で大差なし (聞き取れる劣化なし)
- **ONNX export round trip**
  - `--decoder-branch wavehax` で export した `wavehax.onnx` を `onnx.checker.check_model(...)` で pass、 `onnx.shape_inference.infer_shapes(...)` で output shape が `[B, 1, T]` 確定
  - ORT CPU EP で `phoneme_ids` (random 25 tokens) + `input_lengths` + `scales` を流して `[1, 1, T]` float32 が返ることを smoke
  - companion ONNX の input/output 名・順序が既存 `tsukuyomi.onnx` と完全同一 (PR #222 二重同期回避前提を verify)
- **`audio-parity-contract.toml` [mb_istft_1d] baseline 不変 audit**
  - 既存 `tsukuyomi.onnx` (本チケット非更新) で `tools/benchmark/results/baseline.json` を再測定し、 Xeon E5-2650 v4 / 25 phoneme 英文で p50 27ms ± 1ms に収まる (regression guard)
- **WandB audio log 4 サンプル耳判定**
  - epoch 5 / 10 / 20 / 30 で `noise_scale=0.667` / `length_scale=1.0` の 4 文 (短/中/長/疑問) を synth、 baseline (epoch 0) と耳判定でメタリック歪み / 高域ハッシュノイズが発生していないことを `notes/AI-10-audio-log-review.md` に記録

### 受入基準 (Acceptance Criteria)

親計画 §4.6 / §5 / M4 Exit Criteria から:

- **UTMOS proxy MOS**: AI-12 (M5) で本格測定するが、 本チケットでは epoch 30 ckpt + companion ONNX が引き渡し可能な状態 (= AI-12 起動の blocking 解除) が達成基準
- **CPU RTF (Xeon E5-2650 v4 / 25 phoneme / warmup 5 + 30 runs)**: AI-12 で正式測定、 本チケットでは Python 単独の chunk-level p50 を `tools/benchmark/results/mswavehax-css10-ja.json` に記録 (Python ORT CPU EP / 30 runs / warmup 5 で `<` 既存 1D MB-iSTFT canonical 27ms)
- **params**: `wavehax.py` 実装が 0.332M params (AI-08 で assert 済み、 本チケットでは ckpt size と onnx weight size が想定範囲 ±10% 内であることを確認)
- **7 runtime smoke**: 本チケット範囲外 (AI-13 / M5)、 Python ORT CPU EP の 1 推論 smoke のみで blocking 解除
- **既存経路 forward-only smoke green**: `enable_wavehax=False` の default で `pytest src/python/tests/test_mb_istft_generator.py` が完全に green (CI gate)
- **`_collect_g_params` hook 健全性**: AI-09 の hook が return する param 数が `enable_wavehax=True` 時に既存 +α (`dec_wavehax` 分) であり、 `False` 時は既存と完全一致

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

- **R5 (PR #537 TF32-on + bf16-mixed の torch.fft 互換性) — MEDIUM**: 本チケットは PR #537 merge 前の現行 torch 2.2 / fp32 で完走するため、 直接 blocking は受けない。 ただし本チケットの ckpt は PR #537 merge 後に bf16-mixed で fine-tune を再開する場合に 1e-3 magnitude drift が増幅する潜在リスクがあり、 AI-16 (M6) で torch 2.11 sandbox + 5 epoch sanity の検証素材として残る (本チケットでは事前対応せず M6 に切り出す前提)
- **R8 (1 GPU 占有他作業との衝突) — MEDIUM**: vocoder-only FT 30 epoch は CLAUDE.md Template B 計算で ~12h を見積もるが、 acoustic freeze で勾配計算が局所化されるため batch を 8 に上げて ~8h に短縮できる余地あり (V100 メモリ実測で判断)。 他学習との競合時は CSS10 JA 14h を 7h subset (`/data/piper/dataset-css10-ja-poc-half/`) に絞り epoch 数 30 を維持する fallback を準備
- **チケット固有: warm start ckpt の整合性** — `--resume-from-multispeaker-checkpoint` で AI-02 baseline ckpt (50 epoch 完走) を読む際、 `dec_wavehax` 部の weight は random init になる (baseline ckpt には存在しない sibling のため)。 これが lightning の `strict=False` resume で正しく処理されるか 1 epoch sanity で確認 (`Missing key(s) in state_dict: net_g.dec_wavehax.*` の warning が出るのが正常)
- **チケット固有: `freeze-acoustic` の意図ずれ** — `freeze-acoustic` 適用範囲が text_encoder / posterior_encoder / flow / dp の 4 module だけか、 PQMF / iSTFT も含むかが曖昧だと vocoder backbone の一部が誤って freeze される。 本チケットでは「`self.net_g.dec` (= 既存 MBiSTFTGenerator) と `self.net_g.dec_wavehax` 以外は全て freeze」 と明確に定義し、 unit test `test_freeze_acoustic_zero_grad` で 4 module 全部の grad が 0 であることを assert
- **チケット固有: EMA shadow が wavehax を追跡し損ねる** — sibling 追加で `self.net_g.parameters()` 経由の EMA 自動追跡に乗る前提だが、 `lightning.py` で EMA を限定的に `self.net_g.dec.parameters()` だけ追跡する書き方になっていたら拾えない。 1 epoch sanity 時に `ema_state_dict()` のキーを print して確認

### レビュー項目 (チェックリスト)

- [ ] default `decoder_type` (= `mb_istft_1d`) と `enable_wavehax=False` が `VitsModel.__init__` の signature で不変 (G-1.9 後方互換)
- [ ] `[mb_istft_1d]` audio parity 不変 (G-1.2 baseline 編集禁止): 本チケットは `audio-parity-contract.toml` を一切 touch していない
- [ ] ONNX I/O 不変 (PR #222 二重同期回避): companion ONNX の入出力名・順序・shape が既存 `tsukuyomi.onnx` と完全一致
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響を `audio-parity-contract` tolerance に反映: 本チケットでは未対応、 AI-16 (M6) に handoff 明記
- [ ] `_collect_g_params` hook の構造が `[opt_g, opt_d]` return shape を変えていない (PR #222 rebase 1 行差分前提を維持)
- [ ] `--freeze-acoustic` の適用範囲が text_encoder / posterior_encoder / flow / dp の 4 module に閉じ、 `dec` / `dec_wavehax` / PQMF / iSTFT は trainable のまま
- [ ] EMA `shadow_params` が `net_g.dec_wavehax.*` キーを含む (1 epoch sanity で verify)
- [ ] WandB audio log の epoch 30 サンプルが baseline と耳判定で大差なし (メタリック歪み / 高域ハッシュノイズなし)
- [ ] `scripts/train_mswavehax_poc.sh` が再現性のため commit され、 dataset path / output path / フラグが PR body に明記される
- [ ] AI-11 / AI-12 へ引き渡す ckpt 絶対パス + ONNX 絶対パス + WandB run URL が PR body の 「後続タスクへの連絡事項」 に明示される

## 一から作り直すとしたら (Ticket-level rethinking)

本チケットの設計を一から考え直すなら、 まず **「vocoder-only FT を 30 epoch fixed で予算化する」 という前提を疑いたい**。 現行は親計画 §4.4 から 30 epoch を機械的に採用したが、 vocoder-only FT は acoustic 表現が固定されているため loss curve が比較的早期 (10-15 epoch) で plateau に到達する可能性が高い。 そこで「early stopping with patience=3 epoch on vocoder_loss」 を導入し、 loss が 3 epoch 連続で改善しなければ 15 epoch でも完了とする運用に切り替えれば、 GPU 時間を ~6h まで圧縮できる。 ただしこれは「30 epoch なら baseline ± 0.15 を満たす」 という Exit Criteria 設計と整合させる必要があり、 早期停止での MOS 確証は AI-12 の UTMOS proxy MOS で取るしかなく、 本チケット内で完結しない依存が増える。 結局「30 epoch 上限 + 早期停止下限なし」 の現行設計が運用シンプルさで勝ち、 早期停止は「異常時の手動 abort」 にとどめる現実解に戻る。

次に、 **`freeze-acoustic` を on/off で 2 段 FT に分ける案** を真剣に検討したい。 前半 15 epoch を `freeze-acoustic=True` で vocoder を独立に最適化し、 後半 15 epoch を `freeze-acoustic=False + base_lr=5e-6` (acoustic を 10x さらに小さい lr で微調整) に切り替えることで、 acoustic 側が vocoder の生成傾向に合わせて微補正される余地が生まれる。 MS-Wavehax 論文 (Yoneyama et al., Interspeech 2025) のテーブル 4 では joint FT が +0.05 MOS の gain を報告しており、 軽量 vocoder では joint FT の恩恵が大きい可能性がある。 ただしこれは PR #222 (emb_g 削除 + Flow dilation 1→2) merge 後の acoustic 構造変更と衝突するため、 後半段は PR #222 merge 後の M6 に切り出すのが安全であり、 本チケット内では「freeze 一貫」 を維持する判断が現実解として正しい。 別案の利点 (joint FT MOS gain) は M6 / AI-17 で再評価の余地として残す。

第三に、 **acoustic warm start を baseline ckpt ではなく iSTFTNet2-MB ckpt (M2 / AI-05) から行う案**。 AI-05 で完走する `decoder_type='istftnet2_mb_1d2d'` の ckpt は CSS10 JA で fine-tune 済みであり、 そこから wavehax 部のみを追加 FT すれば「短文 streaming 時は wavehax + 長文時は iSTFTNet2-MB」 の dual vocoder が「より整合した品質」 で出る可能性がある。 ただし AI-05 と本チケットを直列で走らせるとスケジュールが伸び、 また AI-05 ckpt の MBiSTFTGenerator は 1D-2D backbone なので EMA shadow が 2 backbone (iSTFTNet2-MB + wavehax) を同時に追跡することになり EMA state size が膨らむ。 設計上は綺麗だが運用が複雑で、 本チケットの「1 日完了 / blocking 解除最優先」 目標と相性が悪い。 採用案は「AI-02 baseline (= 1D MB-iSTFT 50 epoch) からの warm start + wavehax は random init で 30 epoch FT」 が、 ckpt 互換性 / EMA シンプルさ / 後続 AI-11 streaming 切替で「閾値超過分は MBiSTFTGenerator 経由」 という dual vocoder のシンプルな分岐構造とも整合し、 現実解として最良である。 別案 (iSTFTNet2-MB ckpt 起点) は将来 wavehax が prod ready になった段階で再 FT として実施する余地として残す。

## 後続タスクへの連絡事項

AI-11 (voice.py streaming 閾値切替) / AI-12 (3 variant benchmark) に引き渡す具体的成果物:

- **ckpt パス**: `/data/piper/output-css10-ja-mswavehax-poc/last.ckpt` を canonical とする。 AI-11 / AI-12 ともこの絶対パスを直接参照
- **last-epoch ckpt の epoch 数**: 30 (early stopping は本チケット範囲外、 30 完走前提)
- **companion ONNX パス**: `/data/piper/output-css10-ja-mswavehax-poc/wavehax.onnx` を canonical とする。 AI-11 では `wavehax_model_path` default を本パスに置く案もあるが、 配布形態が決まるまで AI-11 の default は `None` を維持し、 ベンチマーク用途のみ本パスを明示
- **暫定 default 値**: `streaming_threshold_phonemes=25` (親計画 §4.3 / M4 Exit Criteria より)、 本チケットでは voice.py に書き込まない (AI-11 で確定)。 値の根拠は CSS10 JA / Xeon E5-2650 v4 / 1D MB-iSTFT canonical 27ms 基準
- **WandB run URL**: 学習完了時に PR body と `notes/AI-10-handoff-to-AI-11-AI-12.md` (暫定 handoff doc) に記録、 AI-12 の `tools/benchmark/results/mswavehax-css10-ja.json` の出典として参照
- **`models.yaml` 追加用メタ情報** (AI-12 向け): variant name `mswavehax-css10-ja`、 ckpt path 上記、 onnx path 上記、 sample_rate 22050、 phoneme set "ja-en-zh-es-fr-pt" は使用せず単一 ja のみ、 noise_scale 0.667 固定
- **`_collect_g_params` hook の構造確認結果**: 本チケット 1 epoch sanity 時に `len(list(model._collect_g_params()))` を print して PR body に記録 (AI-09 hook 健全性の cross-ticket verify、 PR #222 / AI-17 rebase 計画の素材)
- **PR #222 rebase 注意事項** (M6 / AI-17 担当者向け): 本チケットの ckpt は `dec_wavehax` 部のみが update されており既存 `self.dec` の重みは freeze で不変。 PR #222 が `MBiSTFTGenerator` を Multi-scale FiLM 化する rebase で `dec_wavehax` 部は影響を受けない (sibling 構造で隔離済み)、 ただし `_collect_g_params` hook に PR #222 が `dec.spk_proj.parameters()` を追加する際に hook 内のループ順序 (`dec.parameters()` → `dec_wavehax.parameters()`) を変えないこと
- **PR #537 状況** (M6 / AI-16 担当者向け): 本チケット完走時点で PR #537 merge 状態を `gh pr view 537 --json mergeStateStatus` で確認、 もし CLEAN になっていれば本チケット ckpt を torch 2.11 sandbox + bf16-mixed で 5 epoch sanity 再学習する素材として直接使える状態にある (本チケットは fp32 完走前提のため drift 検証は M6 で実施)
- **`audio-parity-contract.toml` [mswavehax] section テンプレ**: 本チケットでは contract を touch しないが、 AI-14 (M5) 担当者へのテンプレ案として「expected_p50_ms 18ms (chunk-level)、 output_shape `[1,1,T]` float32、 pairwise_snr_db_min 30、 noise_scale 0.667」 を `notes/M4-handoff-to-M5.md` に記載 (M4 マイルストーン doc 既定の handoff doc に集約)

## 関連ドキュメント

- 親マイルストーン: [../milestones/M4-mswavehax-dual-vocoder.md](../milestones/M4-mswavehax-dual-vocoder.md)
- 親計画 §6: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- Deep-dive companion: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 改善調査統合: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- 既存仕様:
  - [`docs/spec/audio-parity-contract.toml`](../../spec/audio-parity-contract.toml) — **本チケット編集禁止** (G-1.2)、 AI-14 (M5) で `[mswavehax]` section 追加
  - [`docs/spec/text-splitter-contract.toml`](../../spec/text-splitter-contract.toml) — **編集禁止** (decoder-agnostic 維持)
  - [`docs/spec/ort-session-contract.toml`](../../spec/ort-session-contract.toml) — companion ONNX session 設定の参照元
- 学習テンプレ: CLAUDE.md Template B (single-speaker FT) を `--enable-wavehax --freeze-acoustic --wavehax-lr 2e-4` で拡張
- 影響 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — `_collect_g_params` hook (AI-09) で rebase 衝突回避、 本チケットは sibling ckpt 構造で隔離
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — merge 後 M6 / AI-16 で `torch.fft` + bf16-mixed の 5 epoch sanity 再学習に本チケット ckpt を流用
- 論文:
  - [arXiv 2506.03554](https://arxiv.org/html/2506.03554) MS-Wavehax (Yoneyama et al., Interspeech 2025) — vocoder-only FT で MOS gain を報告 (table 4)
