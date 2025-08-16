# カスタム辞書更新時のワークフロー

## 概要
Piper-plusでカスタム辞書を更新した際の推奨ワークフローです。辞書更新の規模に応じて、適切な対応方法を選択してください。

## 辞書更新レベルと対応方法

### レベル1: 軽微な修正（1-10語程度）
**例**: 固有名詞の追加、少数の誤読修正

**対応方法**: 再学習不要
```bash
# 1. 辞書を更新
vim data/dictionaries/user_custom_dict.json

# 2. 推論テスト
python test_dictionary_phonemization.py --compare

# 3. そのまま使用可能
echo "テストテキスト" | uv run python -m piper --model model.onnx --output_file output.wav
```

### レベル2: 中規模な変更（10-100語程度）
**例**: 「音声→おんせい」のような頻出語の修正

**対応方法**: Text Encoderのみ再学習（推奨）
```bash
# 1. 辞書を更新
vim data/dictionaries/user_custom_dict.json

# 2. データセットを再前処理（カスタム辞書適用）
python -m piper_train.preprocess \
  --language ja \
  --input-dir /path/to/audio \
  --output-dir dataset-with-new-dict \
  --dataset-format ljspeech

# 3. Text Encoderのみ再学習（10-20k steps、2-4時間）
python retrain_text_encoder.py \
  --checkpoint output/model.ckpt \
  --dataset-dir dataset-with-new-dict \
  --output-dir output-text-encoder-retrain \
  --max-steps 20000 \
  --batch-size 32 \
  --learning-rate 1e-4 \
  --reinit  # Text Encoderを再初期化

# 4. ONNXエクスポート
python -m piper_train.export_onnx \
  output-text-encoder-retrain/final_text_encoder.ckpt \
  model-updated.onnx
```

### レベル3: 大規模な変更（100語以上）
**例**: 新しい分野の専門用語辞書を追加

**対応方法**: 完全な再学習
```bash
# 1. 辞書を更新
vim data/dictionaries/user_custom_dict.json

# 2. データセットを再前処理
python -m piper_train.preprocess \
  --language ja \
  --input-dir /path/to/audio \
  --output-dir dataset-with-new-dict \
  --dataset-format ljspeech

# 3. 最初から学習（1-3日）
python -m piper_train \
  --dataset-dir dataset-with-new-dict \
  --accelerator gpu \
  --devices 4 \
  --batch-size 48 \
  --max_epochs 2500 \
  --default_root_dir output-new
```

## Text Encoder再学習の詳細

### なぜText Encoderだけで良いのか？

VITSアーキテクチャでは：
- **Text Encoder (enc_p)**: テキスト/音素列を特徴ベクトルに変換
- **Duration Predictor**: 音素の長さを予測
- **Decoder**: 特徴ベクトルから音声を生成

辞書更新は主に音素列に影響するため、Text Encoderのみの再学習で対応可能です。

### 再学習時のパラメータ

```python
# 推奨設定
--max-steps 20000        # 日本語では10-20kで収束
--batch-size 32          # GPUメモリに応じて調整
--learning-rate 1e-4     # 元の学習率の1/2程度
--reinit                 # 大きな変更時は再初期化推奨
```

### 学習の監視

```bash
# TensorBoardで監視
tensorboard --logdir output-text-encoder-retrain

# 確認ポイント：
# - loss/g_total が減少していること
# - 10k steps程度で収束傾向
```

## 辞書テストツール

### 1. 音素化の確認
```bash
# 辞書適用前後の比較
python test_dictionary_phonemization.py --compare
```

### 2. 実際の音声生成テスト
```bash
# テストテキストで音声生成
echo "音声合成のテストです" | uv run python -m piper \
  --model model.onnx \
  --output_file test.wav
```

## ベストプラクティス

### 1. 辞書更新前の準備
- 現在の辞書をバックアップ
- 現在のモデルチェックポイントをバックアップ
- テストセットを準備

### 2. 段階的な更新
- 一度に大量の変更を避ける
- 重要な語句から優先的に修正
- 各更新後にテストを実施

### 3. 評価指標
- 音素化の正確性（test_dictionary_phonemization.py）
- 生成音声の自然性（主観評価）
- MOS（Mean Opinion Score）評価（可能であれば）

## トラブルシューティング

### Q: Text Encoder再学習が収束しない
A: 学習率を下げる（5e-5など）、またはreinitオプションを外す

### Q: 再学習後、音質が劣化した
A: 
- チェックポイントを10k, 15k, 20kなど複数試す
- 元のモデルとブレンドする（研究中）

### Q: どのレベルの対応が必要か分からない
A: まずレベル1（再学習なし）を試し、品質が不十分ならレベル2へ

## 今後の改善予定

1. **自動判定機能**: 辞書変更の影響度を自動評価
2. **増分学習**: 変更された語句のみを効率的に学習
3. **辞書のバージョン管理**: Git統合による辞書履歴管理

## 参考情報

- VITSの論文: [Conditional Variational Autoencoder with Adversarial Learning for End-to-End Text-to-Speech](https://arxiv.org/abs/2106.06103)
- Style-Bert-VITS2の辞書機能: VOICEVOXエンジンベース
- GPT-SoVITSの音素化: pyopenjtalk使用