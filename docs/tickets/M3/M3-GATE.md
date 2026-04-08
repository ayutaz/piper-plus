# [M3-GATE] Go/No-Go 判定: Speaker Encoder 品質検証

**マイルストーン**: M3a (v2.0.0)
**カテゴリ**: 判定
**工数**: 2d
**依存**: M3-1
**ステータス**: 未着手

---

## 1. 目的とゴール

M3-1 で構築した Speaker Encoder (ECAPA-TDNN) が、Voice Cloning パイプラインの基盤として十分な話者弁別性能を持つかを定量的に検証し、M3-2 以降に進むか否かを判定する。不合格時の代替プランを明確にし、プロジェクト全体のリスクを早期に軽減する。

**ゴール:**
- 話者類似度メトリクスによる定量評価の実施
- Go/No-Go 判定基準に基づく明確な結論
- 不合格時の代替プラン (A/B) の選択とスケジュール影響の評価

## 2. 実装内容の詳細

### 2.1 評価データセット

| データセット | 話者数 | 発話数 | 用途 |
|------------|--------|--------|------|
| VoxCeleb1-O (テスト) | 40 | ~4,700ペア | EER 計測 (英語) |
| MOE-Speech テストセット | 5 | 各10発話 | 日本語話者での類似度検証 |
| AISHELL-3 テストセット | 10 | 各5発話 | 中国語話者での類似度検証 |

### 2.2 評価メトリクスと合格基準

| メトリクス | 合格基準 | 不合格基準 | 根拠 |
|-----------|---------|-----------|------|
| 同一話者 cosine similarity | > 0.85 | < 0.75 | ZSE-VITS 論文の推奨値 |
| 異話者 cosine similarity | < 0.40 | > 0.55 | 話者弁別の最低ライン |
| EER (VoxCeleb1-O) | < 3.0% | > 5.0% | SpeechBrain 公式 0.8% の3倍を許容 |
| 日本語話者 cosine similarity | > 0.80 | < 0.70 | 英語事前学習のドメインシフトを考慮 |
| ONNX vs PyTorch 出力差 | L2 < 1e-4 | L2 > 1e-2 | 量子化誤差の許容範囲 |

### 2.3 グレーゾーン判定

合格と不合格の中間値が出た場合:
- cosine similarity 0.75-0.85 → 条件付きGo (M3-2 で線形射影層を追加して補正)
- EER 3.0-5.0% → FP32 モデルで再評価、合格なら FP16 を諦めて FP32 で進行

### 2.4 評価スクリプト

```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.speaker_encoder.evaluate \
  --encoder-model speaker_encoder.onnx \
  --voxceleb-pairs /data/voxceleb1/veri_test2.txt \
  --moe-speech-dir /data/piper/moe-speech-test/ \
  --aishell-dir /data/piper/aishell3-test/ \
  --output-report docs/reports/speaker-encoder-evaluation.json
```

### 2.5 判定フロー

```
M3-1 完了
  │
  ├─ 評価メトリクス全て合格 → Go → M3-2 に進行
  │
  ├─ グレーゾーン → 条件付きGo (M3-2 で補正層追加)
  │
  └─ 不合格 → No-Go
       │
       ├─ 選択肢A: F5-TTS 方式に切り替え
       │   - Flow Matching DiT ベース
       │   - Speaker Encoder 不要 (参照音声を直接入力)
       │   - 工数: +30d (アーキテクチャ全面刷新)
       │   - v2.0.0 スケジュール: 2-3ヶ月遅延
       │
       └─ 選択肢B: Voice Cloning を v2.1.0 に延期
           - v2.0.0 は VITS2 + SSML + ZH増量のみ
           - Voice Cloning は v2.1.0 で再検討
           - 工数影響: M3-2,3,4 (25d) を削減
           - v2.0.0 スケジュール: 変更なし
```

### 2.6 判定レポート

`docs/reports/speaker-encoder-gate-decision.md` に以下を記録:
- 評価日時
- 各メトリクスの数値結果
- Go/No-Go 判定と理由
- (No-Go の場合) 選択された代替プランとスケジュール影響

## 3. エージェントチームの構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 評価リード | 1 | 評価スクリプト実行、メトリクス集計、判定レポート作成 |
| プロジェクトリード | 1 | Go/No-Go 判定、代替プラン選択、スケジュール調整 |

## 4. テスト計画

### 提供範囲（スコープ）
- IN: Speaker Encoder ONNX モデルの話者弁別性能評価、Go/No-Go 判定、判定レポート
- OUT: Speaker Encoder の改善 (不合格時は M3-1 に差し戻し)、VITS 統合 (M3-2)

### ユニットテスト

- `test_evaluation_script`: 評価スクリプトがダミーデータで正常に動作すること
- `test_report_schema`: 判定レポートの JSON スキーマ検証

### E2Eテスト

- 評価スクリプトを実際のテストデータで実行し、レポートが正しく生成されること
- メトリクス値が合理的な範囲内にあること (cosine similarity が -1 ~ 1 の範囲)

## 5. 懸念事項とレビュー項目

### 懸念事項

1. **評価データの偏り**: VoxCeleb は英語のみ。日本語/中国語でのドメインシフトにより性能が低下する可能性が高い。MOE-Speech/AISHELL-3 のテストセットでの追加評価が必須
2. **cosine similarity と実際の Voice Cloning 品質の乖離**: cosine similarity が高くても、VITS の `emb_g` 空間にマッピングした後の音声品質は別問題。本ゲートは Speaker Encoder 単体の評価であり、最終的な音声品質は M3-3 後に再評価が必要
3. **判定の主観性**: 数値基準は設けたが、グレーゾーンの判断はプロジェクトリードの裁量に依存する

### レビューチェックリスト

- [ ] 評価データセットが公開データのみで構成されている (ライセンス問題なし)
- [ ] 合格基準の数値が ZSE-VITS / YourTTS 等の先行研究と整合的
- [ ] No-Go 時の代替プラン (A/B) の工数見積が現実的
- [ ] 判定レポートのフォーマットが再現可能 (第三者が同じ手順で同じ結論に達する)
- [ ] グレーゾーン判定のエスカレーションパスが明確

## 6. 一から作り直すとしたら

**ゲート設計の根本的な再考:**

現在のゲートは Speaker Encoder の「単体性能」を評価しているが、真に検証すべきは「VITS の `emb_g` 空間に射影した後の音声品質」である。理想的には以下の2段階ゲートにすべき:

1. **Stage 1 (現 M3-GATE)**: Speaker Encoder 単体の話者弁別性能 → 足切り
2. **Stage 2 (M3-3 後)**: Voice Cloning モデルの MOS 評価 + 話者類似度 → 最終判定

しかし Stage 2 まで待つと M3-2, M3-3 の工数 (15d) が無駄になるリスクがある。そこで現在の設計では Stage 1 のみでゲートしている。

**ゼロから設計する場合の M3a 全体のゲート戦略:**

1. M3-1 を 3d のプロトタイプフェーズに縮小 (ONNX エクスポートのみ)
2. M3-2 の線形射影層を含めた「ミニ Voice Cloning パイプライン」を 5d で構築
3. 少数データ (10話者, 1000発話) で学習して Stage 2 相当の評価を実施
4. ここで Go/No-Go 判定 → 合格なら本格学習 (M3-3) に進む

この方法なら 8d で最終品質に近い判定ができ、15d の無駄を防げる。ただし、プロトタイプの品質が本番と乖離するリスクがある。

**Voice Cloning アーキテクチャの選択について:**

ECAPA-TDNN + VITS (`emb_g` 置換) はシンプルだが、以下の代替も検討に値する:

- **F5-TTS (Flow Matching DiT)**: Speaker Encoder 不要で参照音声を直接条件付け。品質は高いがモデルサイズが大きく (>500MB)、推論が遅い。ブラウザ/RPi には非現実的
- **XTTS (Coqui)**: GPT + VITS の2段階。品質は最高峰だが GPL ライセンス (piper-plus は Apache-2.0)
- **CosyVoice (Alibaba)**: Flow Matching ベース。品質は良いがコードが Apache-2.0 でもモデル重みのライセンスが不明

piper-plus のコンセプト (軽量、マルチプラットフォーム、Apache-2.0) を考えると、ECAPA-TDNN + VITS が最も現実的な選択。F5-TTS は v3.0.0 以降のロードマップとして検討すべき。

## 7. 後続タスクへの連絡事項

- **Go の場合**: M3-2 に進行。Speaker Encoder の出力次元 (256) と VITS `gin_channels` の一致を確認した上で着手
- **条件付き Go の場合**: M3-2 のスコープに線形射影層 (256 -> gin_channels) の追加を含める。工数 +1d
- **No-Go (選択肢A) の場合**: M3-2,3,4 を全て破棄し、F5-TTS アーキテクチャの調査チケットを新規作成。M3-5,6,7,8 は影響なし
- **No-Go (選択肢B) の場合**: M3-2,3,4 を v2.1.0 に移動。v2.0.0 のスコープは M3-5,6,7,8 のみ。リリースノートに Voice Cloning 延期を記載
- 判定レポートは `docs/reports/speaker-encoder-gate-decision.md` に保存し、PR で共有
