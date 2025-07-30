# CSS10日本語TTSモデル学習引き継ぎ書

## 1. 現在の状況

### 学習状態
- **開始時刻**: 2024-07-30 13:02 JST
- **ステータス**: 新規学習実行中（エポック0進行中）
- **出力ディレクトリ**: `/data/piper/output-css10-ja-accuracy-v1-fixed-init/`
- **予想完了時間**: 約10-12日後

### 実行中のコマンド
```bash
python -m piper_train \
    --dataset-dir /data/piper/dataset-css10-ja-accuracy-v1/ \
    --accelerator gpu \
    --devices 4 \
    --strategy ddp_find_unused_parameters_true \
    --batch-size 32 \
    --num-workers 16 \
    --disable_auto_lr_scaling \
    --base_lr 1e-4 \
    --max_epochs 15000 \
    --checkpoint-epochs 100 \
    --save-top-k -1 \
    --ema-decay 0.9999 \
    --default_root_dir /data/piper/output-css10-ja-accuracy-v1-fixed-init/
```

## 2. 過去の失敗からの教訓

### 失敗した学習
- **ディレクトリ**: `/data/piper/output-css10-ja-accuracy-v1/`
- **結果**: 10,000エポック学習後も意味不明な音声
- **原因**: 
  1. F0 Predictorの初期化が不適切（std=1.0は大きすぎた）
  2. 学習率が高すぎた（0.0032）
  3. version_5からの継続学習による影響

### 実施した修正
1. **コード修正**: `src/python/piper_train/vits/f0_predictor.py`に`_init_weights()`メソッド追加
2. **前処理修正**: `src/python/piper_train/preprocess.py`に日本語用prosody情報の自動追加
3. **学習設定の最適化**: 学習率とバッチサイズの調整

## 3. 監視すべきポイント

### TensorBoard監視
```bash
# TensorBoard起動
tensorboard --logdir /data/piper/output-css10-ja-accuracy-v1-fixed-init/lightning_logs/
```

### 重要な指標
1. **loss_gen_all**
   - 初期値: 40-60程度（正常）
   - 目標: 10-20以下
   - 異常: 100以上または減少しない

2. **loss_disc_all**
   - 正常範囲: 0.5-2.0
   - 安定していることを確認

3. **学習速度**
   - 現在: 約0.44it/s
   - 1エポック: 約2分（49バッチ）

## 4. チェックポイントでの確認作業

### 100エポックごとの作業

1. **チェックポイントの確認**
```bash
ls -la /data/piper/output-css10-ja-accuracy-v1-fixed-init/lightning_logs/version_0/checkpoints/
```

2. **ONNXエクスポート**
```bash
# CPUモードでエクスポート（CUDAエラー回避）
CUDA_VISIBLE_DEVICES="" python -m piper_train.export_onnx \
    /data/piper/output-css10-ja-accuracy-v1-fixed-init/lightning_logs/version_0/checkpoints/epoch=99-step=XXX.ckpt \
    /data/piper/piper_MODELS_EXPORTED/test_epoch100.onnx
```

3. **config.jsonの準備**
```bash
cp /data/piper/dataset-css10-ja-accuracy-v1/config.json \
   /data/piper/piper_MODELS_EXPORTED/test_epoch100.onnx.json
```

4. **音声生成テスト**
```bash
echo "こんにちは、今日は良い天気ですね。" | \
python -m piper --model /data/piper/piper_MODELS_EXPORTED/test_epoch100.onnx \
--output_file /home/jovyan/test_epoch100.wav
```

## 5. トラブルシューティング

### 問題1: 損失が減少しない
- **確認**: TensorBoardでloss_gen_allが停滞
- **対処**: 
  1. 学習を停止（Ctrl+C）
  2. 学習率をさらに下げて再開（5e-5など）

### 問題2: CUDAメモリ不足
- **確認**: "CUDA out of memory"エラー
- **対処**: バッチサイズを削減（32→16）

### 問題3: 音声が改善しない
- **確認**: 1000エポック後も発音が不明瞭
- **対処**: 
  1. データセットの品質確認
  2. 別のデータセットでのテスト検討

## 6. 完了後の作業

### 最終モデルのエクスポート
```bash
# 最終チェックポイントをONNXに変換
CUDA_VISIBLE_DEVICES="" python -m piper_train.export_onnx \
    /data/piper/output-css10-ja-accuracy-v1-fixed-init/lightning_logs/version_0/checkpoints/last.ckpt \
    /data/piper/piper_MODELS_EXPORTED/ja_JP-css10-v1-fixed-final.onnx

# config.jsonをコピー
cp /data/piper/dataset-css10-ja-accuracy-v1/config.json \
   /data/piper/piper_MODELS_EXPORTED/ja_JP-css10-v1-fixed-final.onnx.json
```

### 品質評価
```bash
# 複数の文章でテスト
echo "おはようございます。" | python -m piper --model final.onnx --output_file test1.wav
echo "今日は素晴らしい一日になりそうです。" | python -m piper --model final.onnx --output_file test2.wav
echo "日本語の音声合成が正常に動作しています。" | python -m piper --model final.onnx --output_file test3.wav
```

## 7. 関連ファイル

### 重要なファイル
- 調査報告書: `/data/piper/docs/CSS10-JA-TRAINING-INVESTIGATION-REPORT.md`
- 修正したコード: 
  - `/data/piper/src/python/piper_train/vits/f0_predictor.py`
  - `/data/piper/src/python/piper_train/preprocess.py`
- 前処理済みデータ: `/data/piper/dataset-css10-ja-accuracy-v1/`

### 過去の学習ログ
- 失敗した学習: `/data/piper/output-css10-ja-accuracy-v1/`
- TensorBoardログ: `events.out.tfevents.*`ファイル

## 8. 連絡事項

### 注意点
1. 学習は中断しないこと（10-12日かかる）
2. GPU使用率を定期的に確認（nvidia-smi）
3. ディスク容量に注意（チェックポイントが蓄積）

### 推奨事項
1. 100エポックごとに音声品質を確認
2. 異常な損失値の変化に注意
3. 問題があれば早期に対処

---
作成日: 2024-07-30
次回確認予定: エポック100到達時（約3.5時間後）