# Piper-Plus 高度な精度向上アプローチ（最新研究ベース）

## 概要

2024年の最新TTS研究に基づき、より時間をかけて実装することで大幅な精度向上が期待できる高度なアプローチをまとめました。

## 1. WavLM Discriminator の導入（最も推奨）

### 概要
StyleTTS2やFLY-TTSで採用されている、大規模事前学習済みWavLMモデルをdiscriminatorとして使用する手法。

### 期待効果
- **MOS向上**: +0.15-0.25
- **特に改善される点**: プロソディ、ポーズ、自然性

### 実装詳細
```python
# src/python/piper_train/vits/wavlm_discriminator.py
import torch
import torch.nn as nn
from transformers import WavLMModel

class WavLMDiscriminator(nn.Module):
    def __init__(self, pretrained_model="microsoft/wavlm-base"):
        super().__init__()
        self.wavlm = WavLMModel.from_pretrained(pretrained_model)
        # Freeze lower layers
        for param in self.wavlm.feature_extractor.parameters():
            param.requires_grad = False
        
        # Discriminator head
        self.classifier = nn.Sequential(
            nn.Linear(768, 256),
            nn.LeakyReLU(0.2),
            nn.Dropout(0.2),
            nn.Linear(256, 1)
        )
    
    def forward(self, x):
        # x: [B, T] audio waveform
        outputs = self.wavlm(x, output_hidden_states=True)
        # Use multiple layer outputs
        hidden_states = outputs.hidden_states[-4:]  # Last 4 layers
        features = torch.stack(hidden_states, dim=1).mean(dim=1)
        # Global pooling
        features = features.mean(dim=1)
        return self.classifier(features)
```

### 実装時間
- 基本実装: 1週間
- 調整・最適化: 1週間

## 2. Conditional Flow Matching（Matcha-TTS方式）

### 概要
確率的フローマッチングを使用した高速・高品質な音声合成。VITSのフローを置き換える。

### 期待効果
- **MOS向上**: +0.10-0.15
- **推論速度**: 2-3倍高速化

### 実装概要
```python
# Conditional Flow Matching module
class ConditionalFlowMatching(nn.Module):
    def __init__(self, channels, hidden_channels, kernel_size, n_layers):
        super().__init__()
        self.encoder = WN(channels, hidden_channels, kernel_size, n_layers)
        self.t_embedder = nn.Sequential(
            nn.Linear(1, hidden_channels),
            nn.SiLU(),
            nn.Linear(hidden_channels, hidden_channels)
        )
        
    def forward(self, x, x_mask, t, g=None):
        # t: time step [0, 1]
        t_emb = self.t_embedder(t.unsqueeze(-1))
        h = self.encoder(x, x_mask, g)
        # Predict velocity field
        v = h + t_emb.unsqueeze(-1)
        return v
```

### 実装時間
- 基本実装: 2週間
- VITSへの統合: 1週間

## 3. Multi-Resolution STFT Discriminator

### 概要
複数の時間-周波数解像度でdiscriminationを行い、より詳細な音声特徴を捉える。

### 期待効果
- **MOS向上**: +0.08-0.12
- **特に改善**: 高周波数成分の品質

### 実装詳細
```python
class MultiResolutionSTFTDiscriminator(nn.Module):
    def __init__(self, 
                 fft_sizes=[512, 1024, 2048],
                 hop_sizes=[120, 240, 480],
                 win_sizes=[480, 960, 1920]):
        super().__init__()
        self.discriminators = nn.ModuleList()
        
        for fft_size, hop_size, win_size in zip(fft_sizes, hop_sizes, win_sizes):
            self.discriminators.append(
                STFTDiscriminator(fft_size, hop_size, win_size)
            )
    
    def forward(self, y, y_hat):
        y_d_rs = []
        y_d_gs = []
        fmap_rs = []
        fmap_gs = []
        
        for d in self.discriminators:
            y_d_r, fmap_r = d(y)
            y_d_g, fmap_g = d(y_hat)
            y_d_rs.append(y_d_r)
            y_d_gs.append(y_d_g)
            fmap_rs.append(fmap_r)
            fmap_gs.append(fmap_g)
            
        return y_d_rs, y_d_gs, fmap_rs, fmap_gs
```

### 実装時間
- 基本実装: 3-4日
- 既存discriminatorとの統合: 2-3日

## 4. 日本語BERT埋め込みの活用

### 概要
日本語特化のBERTモデル（tohoku-bert、waseda-roberta）を使用してテキストの文脈理解を強化。

### 期待効果
- **MOS向上**: +0.06-0.10
- **特に改善**: 文脈に応じたイントネーション

### 実装詳細
```python
from transformers import AutoModel, AutoTokenizer

class JapaneseBERTEncoder(nn.Module):
    def __init__(self, model_name="cl-tohoku/bert-base-japanese-v3"):
        super().__init__()
        self.bert = AutoModel.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        
        # Freeze lower layers
        for layer in self.bert.encoder.layer[:8]:
            for param in layer.parameters():
                param.requires_grad = False
                
        # Project to VITS hidden size
        self.projection = nn.Linear(768, 192)  # BERT dim -> VITS dim
        
    def forward(self, texts, phoneme_ids, phoneme_lengths):
        # texts: List[str] - original Japanese texts
        # Map BERT tokens to phonemes
        bert_features = self._extract_bert_features(texts)
        aligned_features = self._align_to_phonemes(
            bert_features, phoneme_ids, phoneme_lengths
        )
        return self.projection(aligned_features)
```

### 実装時間
- 基本実装: 1週間
- アライメント処理: 3-4日

## 5. Adversarial Duration Modeling

### 概要
Duration predictorも敵対的学習で訓練し、より自然な音素長を生成。

### 期待効果
- **MOS向上**: +0.05-0.08
- **特に改善**: リズムの自然性

### 実装時間
- 実装: 3-4日

## 実装優先順位と組み合わせ効果

### 推奨実装順序

1. **Phase 1**: WavLM Discriminator（2週間）
   - 単体で最大の効果
   - 他の改善との相乗効果も高い

2. **Phase 2**: Multi-Resolution STFT Discriminator（1週間）
   - WavLMと組み合わせて音質向上

3. **Phase 3**: 日本語BERT埋め込み（1.5週間）
   - 日本語特有の改善

4. **Phase 4**: Conditional Flow Matching（3週間）
   - 大規模な変更だが効果大

### 期待される総合効果

| 実装段階 | 追加効果 | 累計効果 | 実装期間 |
|---------|---------|---------|---------|
| 現状（gin_channels済み） | - | +0.04-0.06 | - |
| +既存コンポーネント統合 | +0.18-0.24 | +0.22-0.30 | 1週間 |
| +WavLM Discriminator | +0.15-0.25 | +0.37-0.55 | 2週間 |
| +Multi-Res STFT | +0.08-0.12 | +0.45-0.67 | 1週間 |
| +日本語BERT | +0.06-0.10 | +0.51-0.77 | 1.5週間 |
| +Flow Matching | +0.10-0.15 | +0.61-0.92 | 3週間 |

## 実装上の考慮事項

### メモリ使用量
- WavLM Discriminator: +1.5GB（推論時は不要）
- 日本語BERT: +500MB
- その他: +200-300MB

### 学習時間への影響
- WavLM使用時: 約2倍
- 全改善適用時: 約3倍

### ONNX互換性
- WavLM: 推論時は不要なので問題なし
- BERT埋め込み: 事前計算して埋め込みとして保存可能
- Flow Matching: ONNX対応可能

## まとめ

これらの高度な改善により、piper-plusは最新の商用TTSシステムと同等以上の品質を実現できます。特にWavLM Discriminatorは、実装コストに対する効果が非常に高く、最優先で検討すべき改善です。

全改善を実装した場合、**MOS +0.61-0.92**という大幅な品質向上が期待でき、人間の音声と区別がつかないレベルに到達する可能性があります。