# P5-T02: Fine-tune Stage 5a 実行 (CREMA-D ベース 6lang)

| 項目 | 値 |
|------|-----|
| Phase | 5 |
| マイルストーン | [#15](https://github.com/ayutaz/piper-plus/milestone/15) |
| ステータス | 未着手 |
| 優先度 | 最高 (T03/T04/T05 の前提) |
| Claude Code 工数 | 1h (実装・起動・監視) + GPU 2 日 (バックグラウンド学習) |
| 依存チケット | P5-T01 (dataset 準備), Phase 1 全タスク (CLI/models/dataset), Phase 4 全タスク (PE-A loss、Stage 5b 時のみ必須、Stage 5a は style conditioning のみ) |
| 後続チケット | P5-T03, P5-T04 |
| 関連 PR | PR-G |
| 期日 | 2026-05-08 |

## 1. タスク目的とゴール

### 1.1 目的

P5-T01 で準備した `/data/piper/dataset-crema-d-emotion/` を用い、6lang ベース (`/data/piper/output-multilingual-6lang/lightning_logs/version_0/checkpoints/epoch=74-step=504712.ckpt`) から style vector conditioning 付き fine-tune を実施する。Stage 5a は **PE-A loss なし** の style conditioning のみで、Phase 1 の最小機能セットで感情合成が実現できるかを検証する。

PE-A loss を加えた Stage 5b は Phase 4 完了後に同じ dataset + 前段 fine-tune 結果 (best.ckpt) から継続学習する形で走らせる。本チケットは Stage 5a のみを対象とするが、コマンドテンプレートとして Stage 5b も §2.3 に併記し、P5-T03 評価結果次第で起動判断する。

GPU 学習時間は V100 1GPU で 20〜24h を想定 (200 epoch)。本タスクの Claude Code 稼働部分 (起動・ログ監視) は 1h 程度で、残りはバックグラウンド処理。`nohup ... > log 2>&1 &` パターンで学習完了を別セッションで待つ。

### 1.2 ゴール (Definition of Done)

- [ ] Stage 5a 学習が `/data/piper/output-emotion-fine-tune-v1/` 下で起動され、`training_emotion_v1.log` が生成されている
- [ ] 最初の 10 step 内で loss 値が有効 (NaN / Inf でない) に出力されていることをログで確認
- [ ] WandB run が `piper-plus-emotion-finetune` プロジェクト下に `Phase 5a: Style conditioning only, CREMA-D, 200 epochs` note 付きで作成されている
- [ ] 20 epoch ごとにチェックポイントが `output-emotion-fine-tune-v1/lightning_logs/version_X/checkpoints/` に保存される (10 個目安)
- [ ] 200 epoch 完了 or 早期停止 (validation loss 50 epoch 連続非改善 / 良好 ckpt 3 個溜まり次第手動停止) で学習終了
- [ ] 最終 epoch の validation loss が baseline (6lang style_vector_dim=0 の直近 val loss) に対し +0.5 以内 (catastrophic forgetting の閾値)
- [ ] style_vector dropout 効果の smoke test: `style_vector=None` (zeros) で `style_vector=happy_centroid` と異なる音声が出ることを 1 サンプルで確認
- [ ] `config.json` の書き込みが正しく、`style_vector_dim`, `style_condition_mode`, `style_condition_dropout` が反映されている

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `/data/piper/output-emotion-fine-tune-v1/` (新規、学習出力)
- `/data/piper/training_emotion_v1.log` (新規、nohup ログ)
- `scripts/run_stage_5a_finetune.sh` (新規 or 既存の学習起動シェル、ラッパーとして便利)

### 2.2 実装手順

1. **前提チェック**: P5-T01 完了 (`/data/piper/dataset-crema-d-emotion/dataset.jsonl` 存在確認)、Phase 1 の CLI オプション (`--style-vector-dim`, `--style-condition-mode`, `--style-condition-dropout`) がマージ済みであること
2. **GPU 状況確認**: `nvidia-smi` でメモリ空き確認、ゾンビプロセスがあれば kill
3. **WandB 設定**: `.env` から `WANDB_API_KEY` を export、`WANDB_PROJECT` / `WANDB_NOTES` を設定
4. **学習起動**: §2.3 のコマンドを `nohup ... &` で起動
5. **起動確認** (15 分以内):
    - `tail -f /data/piper/training_emotion_v1.log` で最初の 10 step の loss が出ることを確認
    - WandB ダッシュボードで run が作成されていることを確認
    - NaN / Inf / RuntimeError が出ていないことを確認
6. **バックグラウンド待機** (20〜24h):
    - 別セッションで `tail -f /data/piper/training_emotion_v1.log | grep -E "epoch|val_loss|nan|error"` を継続監視
    - 早期停止条件: validation loss が 50 epoch 連続で改善しない or 良好 ckpt 3 個以上
7. **学習完了確認**:
    - 最終 epoch 数
    - 最終 val_loss
    - 保存された ckpt 一覧
    - WandB でサンプル音声 (audio-log-epochs 20 で 10 回ログされるはず) の確認

### 2.3 Stage 5a 学習コマンド (phase-5.md §5.4.1 完全形)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
export WANDB_PROJECT="piper-plus-emotion-finetune" && \
export WANDB_NOTES="Phase 5a: Style conditioning only, CREMA-D, 200 epochs" && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-crema-d-emotion \
  --prosody-dim 16 \
  --style-vector-dim 256 \
  --style-condition-mode global \
  --style-condition-dropout 0.1 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 200 --batch-size 4 --samples-per-speaker 2 \
  --checkpoint-epochs 20 --quality medium \
  --base_lr 2e-5 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm --freeze-dp \
  --val-every-n-epochs 20 \
  --audio-log-epochs 20 \
  --load_weights_from_checkpoint \
    /data/piper/output-multilingual-6lang/lightning_logs/version_0/checkpoints/epoch=74-step=504712.ckpt \
  --default_root_dir /data/piper/output-emotion-fine-tune-v1 \
  > /data/piper/training_emotion_v1.log 2>&1 &
```

### 2.4 Stage 5b 学習コマンド (参考、P5-T03 評価後に起動判断)

Phase 4 完了 & `style_bank_crema_d.npz` 生成済みの場合:

```bash
export WANDB_NOTES="Phase 5b: Style + PE-A loss, warmup 2k steps" && \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-crema-d-emotion \
  --prosody-dim 16 \
  --style-vector-dim 256 \
  --style-condition-mode global \
  --style-condition-dropout 0.1 \
  --pea-emotion-style-bank /data/piper/style_bank_crema_d.npz \
  --pea-emotion-loss-weight 0.1 \
  --pea-emotion-centroid-weight 0.1 \
  --pea-emotion-margin-weight 0.05 \
  --pea-emotion-loss-every-n-steps 4 \
  --pea-emotion-warmup-steps 2000 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 200 --batch-size 4 --samples-per-speaker 2 \
  --checkpoint-epochs 20 --quality medium \
  --base_lr 2e-5 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --no-wavlm --freeze-dp \
  --val-every-n-epochs 20 \
  --audio-log-epochs 20 \
  --load_weights_from_checkpoint \
    /data/piper/output-emotion-fine-tune-v1/lightning_logs/version_X/checkpoints/best.ckpt \
  --default_root_dir /data/piper/output-emotion-fine-tune-v2 \
  > /data/piper/training_emotion_v2.log 2>&1 &
```

### 2.5 パラメータ根拠 (phase-5.md §5.4.1 抜粋)

| パラメータ | 値 | 根拠 |
|-----------|-----|-----|
| `--style-vector-dim 256` | 256 | Phase 0 で確定の PE-A embedding 次元、Phase 3 の style bank 次元と整合 |
| `--style-condition-mode global` | global | text mode より学習安定、g (話者 embedding) に加算する最もシンプルなパス |
| `--style-condition-dropout 0.1` | 0.1 | 10% の確率で style なし生成も学習し、推論時の style なし縮退を防止 |
| `--base_lr 2e-5` | 2e-5 | ベース事前学習の 1/10。catastrophic forgetting 防止 (CLAUDE.md 既存 template B と整合) |
| `--freeze-dp` | 有効 | Duration Predictor 凍結。既存話長特性 (6lang の発話リズム) を保持 |
| `--ema-decay 0.9995` | 0.9995 | CLAUDE.md 既存 template と整合 |
| `--batch-size 4` | 4 | CREMA-D 7,442 ÷ 4 ≒ 1,860 batches/epoch。V100 16GB 内で安全 |
| `--samples-per-speaker 2` | 2 | 91 話者 × 2 = 182 samples/epoch の話者均等 |
| `--max_epochs 200` | 200 | 1,860 × 200 = 372,000 step。v3 バイリンガル (~202K step) より多く、感情制御の収束に十分 |
| `--checkpoint-epochs 20` | 20 | 200 / 20 = 10 個のチェックポイント |
| `--no-wavlm` | 有効 | V100 では WavLM discriminator で ~0.03 it/s まで低下、速度優先 |
| `--load_weights_from_checkpoint` | 6lang ckpt | `--resume-from-multispeaker-checkpoint` ではなく部分 weight load (91 話者の emb_g は再初期化、6 言語の emb_lang は保持) |
| `--audio-log-epochs 20` | 20 | validation 20 epoch ごとの合成サンプルを WandB 送信 |

### 2.6 想定学習時間

- V100 1GPU で ~120 ms/step
- 1,860 step × 200 epoch × 120 ms = 44,640,000 ms ≒ 12.4h (ベース)
- overhead (validation, checkpoint, audio log) で +30〜50% → 実測 20〜24h 見込み

## 3. エージェントチーム構成

| 役割 | 人数 | 主な責務 |
|------|------|---------|
| Infra Operator | 1 | GPU 状況確認 (`nvidia-smi`、ゾンビプロセス kill)、学習コマンドの nohup 起動、WandB 設定確認 |
| Monitor | 1 | 最初の 10 step の loss 値確認、NaN/Inf 検知、起動から 1h の経過監視 |
| Scheduler | 1 | バックグラウンド 20〜24h の経過を別セッションで追跡、完了 or 早期停止条件に応じて手動停止判断 |

## 4. 提供範囲 (Deliverables)

- [ ] `/data/piper/output-emotion-fine-tune-v1/` の学習成果物一式
    - [ ] `lightning_logs/version_X/checkpoints/epoch=NN-step=MMMMMM.ckpt` (10 個目安)
    - [ ] `lightning_logs/version_X/hparams.yaml`
    - [ ] `lightning_logs/version_X/events.out.tfevents.*` (TensorBoard ログ)
- [ ] `/data/piper/training_emotion_v1.log` (完全な学習ログ)
- [ ] WandB run URL (dashboard で参照可能)
- [ ] 最終 validation loss (数値)
- [ ] best ckpt のパスと対応する epoch 数

**提供範囲外**:
- モデル評価 (P5-T03)
- ONNX エクスポート (P5-T04)
- Stage 5b 学習 (P5-T03 の評価結果で Go/No-go 判断)

## 5. テスト項目

### 5.1 Unit テスト

- 本タスクは学習実行のため unit テストは作成しない (Phase 1/2/4 で CLI・models・loss のテストは既に存在)
- 学習起動時の起動時エラー (例: `--style-vector-dim` argparse エラー、`--load_weights_from_checkpoint` の shape mismatch) はログで即検知可能

### 5.2 E2E テスト

- **起動後 5 分以内**: `grep -E "epoch 0" /data/piper/training_emotion_v1.log` で 1 epoch 目のログが出現
- **起動後 1h 以内**: `grep -E "val_loss" /data/piper/training_emotion_v1.log` で validation ログが出現 (20 epoch 目安)
- **学習完了時**: `ls /data/piper/output-emotion-fine-tune-v1/lightning_logs/version_X/checkpoints/` で 10 個前後の ckpt 生成確認
- **WandB**: dashboard で `train_loss_*`, `val_loss_*`, `audio_examples` の 3 種類が 10 回以上プロットされている

### 5.3 人間評価 (optional)

- WandB の audio_examples タブで 20 epoch ごとの合成サンプル (テキスト: CREMA-D 12 固定文のうち 2 文) を聴取
- 感情差 (例: `angry` vs `happy` の発話) が認識可能か主観評価
- MOS 形式の定量評価は P5-T03 で実施

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **Catastrophic forgetting (6lang 言語品質低下)**: `--freeze-dp` + `--base_lr 2e-5` で対策するが、CREMA-D は英語のみなので日本語・中国語等の他言語品質が低下する可能性。P5-T03 で 6 言語 spot check 必須
- **CREMA-D 英語のみ → 多言語感情表現力不足**: fine-tune は英語のみデータ、推論時に日本語で `style_vector=happy` を与えても感情が伝わらない可能性。シナリオ B (つくよみちゃん 100 発話を emotion="neutral" で混入) or C (ESD 中国語追加) で緩和検討
- **GPU 2 日の学習でインフラ問題 (OOM, 電源断)**: バックグラウンド学習中にマシンリブート・ネットワーク断が発生すると ckpt ロスト。対策: `--checkpoint-epochs 20` で定期保存、`--load_weights_from_checkpoint` でリスタート可能にしておく。tmux/screen 使用
- **SER 精度が期待値に届かない場合のネクストアクション**: 英語 SER 65% 未満の場合、P5-T03 で原因分析 → シナリオ B (データ増強) or C (ベース再学習スコープ切り出し)
- **`--load_weights_from_checkpoint` vs `--resume-from-multispeaker-checkpoint`**: 後者は emb_g 除去 + emb_lang 補正 + freeze-dp 自動有効化を行うが、CREMA-D は 91 話者の新規マルチスピーカー fine-tune なので emb_g を保持せず再初期化する必要あり。前者 (部分 weight load) を採用。ただし emb_lang は保持したい → hparams.yaml で確認
- **batch-size 4 の収束速度**: 大 dataset (CREMA-D 7,442) に対し batch 4 は小さく学習が遅い。GPU メモリに余裕があれば batch 8 に増やせるか検討 (ただし V100 16GB では A-posteriori)

### 6.2 レビュー項目

- [ ] `--style-vector-dim 256` が argparse で受理され、`VitsModel.__init__` に伝播している
- [ ] `--style-condition-mode global`, `--style-condition-dropout 0.1` が同様に伝播している
- [ ] `--load_weights_from_checkpoint` で shape mismatch (emb_g が 571 → 91 話者) が適切にハンドリングされている (strict=False or 部分 load ロジック)
- [ ] `--freeze-dp` により Duration Predictor の gradient が流れていない (optimizer の param groups 確認)
- [ ] WandB run にサンプル音声 (20 epoch ごと) がログされている
- [ ] ckpt サイズが妥当 (~500MB 前後、既存 6lang ckpt と同等)
- [ ] 学習ログに `style_vector_dim=256, style_condition_mode=global` の初期化ログが出力されている

## 7. 一から作り直すとしたら

### 7.1 代替案の検討

- **代替案 A: Fine-tune ではなく from-scratch 学習**
    - 利点: 6lang の制約を受けずに CREMA-D 向けに最適化された model が得られる、感情表現力が高くなる可能性
    - 欠点: 学習時間が 10 倍以上 (75 epoch × 4GPU → 500+ epoch × 1GPU)、既存多言語品質を失う
- **代替案 B: Stage 5a を skip して直接 Stage 5b を実行**
    - 利点: PE-A loss の効果を最大化、全体で 1 段階の学習で済む
    - 欠点: PE-A loss の NaN リスクが高まる、Stage 5a の baseline 比較ができない
- **代替案 C: シナリオ A/B/C を並列実行して最良を選ぶ**
    - 利点: 経験的に最良のデータセット構成が見つかる
    - 欠点: GPU 資源 3 倍、期日内に全完了困難
- **代替案 D: Multi-speaker fine-tune ではなく single-speaker × emotion (話者固定・感情切替のみ)**
    - 利点: emb_g 問題を回避、話者ごとの品質安定
    - 欠点: CREMA-D の 91 話者多様性を活かせない、speaker × emotion の直積制御ができない

### 7.2 現在の実装を選んだ理由

- phase-5.md §5.3.4 の「段階的 A → B → C」方針に準拠、まずリスク最小の Stage 5a で style conditioning 単独の効果を検証
- 6lang ベースを保持することで既存 6 言語品質を維持、英語のみの PE-A でも speaker_embedding 的な global conditioning として機能する想定
- GPU 2 日という期日内で Claude Code が監視可能な粒度に収まる

### 7.3 リファクタ機会 (将来)

- 学習起動を `scripts/run_stage_5a_finetune.sh` にラップし、`--resume` モードや `--dry-run` を追加
- ckpt ローテーション (最新 3 個のみ保持、古いものは自動削除) を PyTorch Lightning callback で実装、ディスク圧迫防止
- 自動早期停止を `EarlyStopping` callback (patience=50) で実装、手動停止の判断負荷を減らす
- WandB alert で NaN / Inf 発生時に即通知、学習失敗を 20h 待たずに検知

## 8. 後続タスクへの連絡事項

- **P5-T03 へ**: best ckpt のパスを連絡。評価対象は `epoch=NN-step=MMMMMM.ckpt` (val_loss 最小) + 最終 epoch の 2 つ。CREMA-D validation split の 18 話者 (話者ベース split) で SER 評価
- **P5-T04 へ**: best ckpt を ONNX エクスポートの入力として使用。`--style-vector-dim 256` を export_onnx に伝播させる必要あり (Phase 2 完了前提)
- **Stage 5b 判断**: P5-T03 で Stage 5a の SER >= 65% を満たした場合、Stage 5b (PE-A loss 追加) を本チケット §2.4 のコマンドで起動。満たさない場合はシナリオ B/C への切り替え検討
- **P5-T05 へ**: 学習ログから主要メトリクス (epoch 数、val_loss 推移、GPU 時間) を抽出し、最終レポートに反映

## 9. 参考リンク

- `phase-5.md §5.3` Fine-tune シナリオ
- `phase-5.md §5.4.1` Stage 5a 学習コマンド完全形
- `phase-5.md §5.4.2` Stage 5b 学習コマンド
- CLAUDE.md 「ファインチューニング テンプレート > Template B」
- CLAUDE.md 「つくよみちゃん 6langベースファインチューニング」
- 6lang ベース ckpt: `/data/piper/output-multilingual-6lang/lightning_logs/version_0/checkpoints/epoch=74-step=504712.ckpt`
- P5-T01 データセット: `/data/piper/dataset-crema-d-emotion/`
