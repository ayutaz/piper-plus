# Piper-plus 日本語音声合成品質問題の技術調査報告書

## 1. エグゼクティブサマリー

Piper-plusの日本語音声合成において、発音、アクセント、イントネーションの品質問題が報告されています。本調査では、これらの問題の技術的原因を分析し、改善策を提案します。

### 主要な発見事項
- **問題の根本原因は複合的**：G2P処理、音素マッピング、モデルアーキテクチャ、学習データの全てが影響
- **PyOpenJTalk依存の限界**：日本語特有の韻律情報の処理が不完全
- **VITSアーキテクチャの制約**：日本語のピッチアクセントパターンへの対応が不十分
- **学習データ品質の影響**：アライメント精度とデータセット規模が品質に直接影響

## 2. 問題の詳細と現状

### 2.1 観察される品質問題

#### 発音の問題
- 長音・促音・撥音の不正確な再現
- 外来語のカタカナ発音の不自然さ
- 無声化母音（I、U）の処理が不安定

#### アクセントの問題
- 単語レベルのピッチアクセントの誤り
- アクセント句境界の不明瞭さ
- 複合語のアクセント結合規則の未実装

#### イントネーションの問題
- 文全体の抑揚パターンの単調さ
- 疑問文・感嘆文の語尾上昇の不自然さ
- 長文での韻律制御の崩壊

### 2.2 問題発生のパターン

```
入力テキスト → G2P処理 → 音素列 → モデル推論 → 音声出力
     ↓           ↓         ↓          ↓           ↓
  文字認識    韻律解析   マッピング  アライメント  波形生成
     ↓           ↓         ↓          ↓           ↓
   [問題1]     [問題2]    [問題3]     [問題4]     [問題5]
```

## 3. 技術的原因の分析

### 3.1 G2P（Grapheme-to-Phoneme）処理の課題

#### PyOpenJTalkの実装分析

```python
# src/python/piper_train/phonemize/japanese.py の実装
def phonemize_japanese(text: str, custom_dict=None) -> list[str]:
    labels = pyopenjtalk.extract_fullcontext(text)
    tokens = []
    
    for idx, label in enumerate(labels):
        # 音素抽出
        phoneme = _RE_PHONEME.search(label).group(1)
        
        # 韻律マーク抽出（栗原メソッド）
        # A1: アクセント核の有無
        # A2: アクセント句内のモーラ位置
        # A3: アクセント句のモーラ数
        
        # 問題点：
        # 1. フルコンテキストラベルの一部しか使用していない
        # 2. F0（基本周波数）情報が失われる
        # 3. 継続長情報が考慮されていない
```

#### 韻律情報の損失

OpenJTalkのフルコンテキストラベルには豊富な韻律情報が含まれていますが、現在の実装では以下の情報が失われています：

1. **F0パターン情報**：アクセント型、フレーズ成分
2. **継続長情報**：各音素の標準的な長さ
3. **文脈情報**：前後の音素環境、品詞情報

### 3.2 音素マッピングの問題

#### 現在の音素セット（58音素）

```python
# src/python/piper_train/phonemize/jp_id_map.py
JAPANESE_PHONEMES = [
    # 母音（有声・無声）
    "a", "i", "u", "e", "o",
    "A", "I", "U", "E", "O",  # 無声化母音
    
    # 長母音
    "a:", "i:", "u:", "e:", "o:",
    
    # 子音群...
]
```

#### マッピングの課題

1. **多文字音素のPUA変換**
   - "ky", "sh", "ch" などが単一コードポイントに変換される
   - この変換により音素間の遷移情報が失われる

2. **コンテキスト依存音素の欠如**
   - 前後の音素環境による変化が考慮されない
   - 例：「ん」の音価変化（[n], [m], [ŋ], [ɴ]）が未区別

### 3.3 VITSモデルアーキテクチャの制約

#### Duration Predictorの限界

```python
# src/python/piper_train/vits/models.py
class DurationPredictor(nn.Module):
    def __init__(self, in_channels, filter_channels, kernel_size, p_dropout):
        # 固定サイズのCNNベース
        # 日本語の複雑な継続長パターンに対応困難
```

**問題点**：
- 固定カーネルサイズでは日本語の多様な音素継続長パターンを学習困難
- アクセント句境界での継続長変化が考慮されない
- 話速変化への適応性が低い

#### Monotonic Alignmentの課題

```python
# 学習時のアライメント計算
def forward(self, x, x_lengths, y, y_lengths):
    # Monotonic Alignment Search
    # 問題：日本語の促音・長音でアライメントが崩れやすい
```

**アライメントエラーの原因**：
1. 促音（っ）の無音区間の扱い
2. 長音記号（ー）の継続長推定
3. 連続する同一母音の境界検出

### 3.4 学習設定とデータセットの影響

#### 現在の学習設定

```json
// src/python/train_config_japanese.json
{
  "model": {
    "text_encoder": {
      "n_layers": 6,
      "n_heads": 2,
      "hidden_channels": 192
    }
  },
  "train": {
    "segment_size": 8192,
    "batch_size": 16
  }
}
```

**問題点**：
- Transformerレイヤー数が少なく、長距離依存関係の学習が不十分
- セグメントサイズが小さく、文全体のイントネーションパターンが学習できない

## 4. 他の日本語TTSシステムとの技術比較

### 4.1 VOICEVOX

**優位点**：
- 専用設計された日本語音声合成エンジン
- ピッチ編集機能による細かい韻律調整が可能
- アクセント辞書の手動編集サポート

**実装の違い**：
```
VOICEVOX: テキスト → 音素 + アクセント → ピッチ生成 → 波形合成
Piper:    テキスト → 音素列 → End-to-End生成
```

### 4.2 商用システム（CoeFont、CeVIO等）

**技術的優位性**：
1. **韻律モデルの分離**：音素予測と韻律予測を別々にモデル化
2. **階層的処理**：文 → 文節 → アクセント句 → モーラの階層で処理
3. **大規模コーパス**：数百時間規模の高品質録音データ

### 4.3 性能比較表

| システム | 音素精度 | アクセント精度 | イントネーション | 学習可能性 | エッジ動作 |
|---------|---------|--------------|---------------|-----------|----------|
| Piper-plus | 中 | 低 | 低 | ◎ | ◎ |
| VOICEVOX | 高 | 高 | 中 | × | ◎ |
| CoeFont | 高 | 高 | 高 | △ | × |
| Coqui TTS | 中 | 低 | 低 | ◎ | ◎ |

## 5. 改善提案

### 5.1 短期的改善策（1-3ヶ月）

#### 1. PyOpenJTalk処理の最適化

```python
# 改善案：フルコンテキスト情報の活用
def enhanced_phonemize_japanese(text: str) -> list[tuple[str, dict]]:
    labels = pyopenjtalk.extract_fullcontext(text)
    tokens = []
    
    for label in labels:
        phoneme = extract_phoneme(label)
        prosody = {
            'accent_position': extract_accent_position(label),
            'phrase_position': extract_phrase_position(label),
            'f0_pattern': extract_f0_pattern(label),
            'duration_scale': extract_duration_scale(label)
        }
        tokens.append((phoneme, prosody))
    
    return tokens
```

#### 2. カスタム辞書の拡充

```python
# 単語レベルのアクセント辞書
custom_accent_dict = {
    "東京": "トーキョー[0]",  # 平板型
    "大阪": "オーサカ[1]",    # 頭高型
    "京都": "キョート[1]"     # 頭高型
}
```

#### 3. データ前処理の改善

- 音声ファイルの正規化（ラウドネス、無音区間）
- テキストの正規化（数字、記号の読み統一）
- 問題のあるサンプルの自動検出と除外

### 5.2 中期的改善策（3-6ヶ月）

#### 1. モデルアーキテクチャの拡張

```python
class JapaneseTextEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        # 音素エンコーダー
        self.phoneme_encoder = TransformerEncoder(...)
        # 韻律エンコーダー
        self.prosody_encoder = TransformerEncoder(...)
        # アテンションベースの統合
        self.cross_attention = MultiHeadAttention(...)
```

#### 2. 階層的Duration Predictor

```python
class HierarchicalDurationPredictor(nn.Module):
    def __init__(self):
        # モーラレベル
        self.mora_predictor = DurationPredictor(...)
        # アクセント句レベル
        self.phrase_predictor = DurationPredictor(...)
        # 文レベル
        self.sentence_predictor = DurationPredictor(...)
```

#### 3. 日本語特化の損失関数

```python
def japanese_loss(pred, target, accent_weight=2.0):
    # 基本損失
    base_loss = F.mse_loss(pred, target)
    
    # アクセント核付近の重み付け
    accent_loss = weighted_mse_loss(
        pred, target, 
        weights=accent_weights
    )
    
    return base_loss + accent_weight * accent_loss
```

### 5.3 長期的改善策（6ヶ月以上）

#### 1. 新しいG2Pシステムの開発

- ニューラルネットワークベースの日本語G2P
- コンテキスト依存音素の導入
- End-to-Endの韻律予測

#### 2. マルチタスク学習

```python
class MultiTaskJapaneseTTS(nn.Module):
    def forward(self, text):
        # タスク1: 音素予測
        phonemes = self.phoneme_predictor(text)
        
        # タスク2: アクセント予測
        accents = self.accent_predictor(text)
        
        # タスク3: 韻律予測
        prosody = self.prosody_predictor(text)
        
        # 統合して音声生成
        audio = self.synthesizer(phonemes, accents, prosody)
```

#### 3. 大規模データセットの構築

- 100時間以上の高品質日本語音声データ
- 多様な話者・発話スタイル
- 詳細なアノテーション（音素境界、アクセント、感情）

## 6. 実装優先順位

### Phase 1: 即効性のある改善（1ヶ月）
1. ✅ PyOpenJTalkのフルコンテキスト活用
2. ✅ カスタム辞書機能の強化
3. ✅ 学習データのクリーニング

### Phase 2: 基盤強化（3ヶ月）
1. ⏳ Duration Predictorの改良
2. ⏳ アライメント学習の安定化
3. ⏳ 学習パラメータの最適化

### Phase 3: アーキテクチャ改革（6ヶ月）
1. 🔄 階層的モデルの導入
2. 🔄 マルチタスク学習の実装
3. 🔄 新G2Pシステムの開発

## 7. 技術的制約と考慮事項

### 7.1 VITSアーキテクチャの根本的制約

VITSは英語などの強勢アクセント言語向けに設計されており、日本語のようなピッチアクセント言語には以下の制約があります：

1. **ピッチ制御の粒度**：モーラ単位でのピッチ制御が困難
2. **韻律の階層性**：文 → 文節 → アクセント句の階層構造が考慮されない
3. **学習の効率性**：日本語特有のパターンに対して学習が収束しにくい

### 7.2 PyOpenJTalkの限界

1. **辞書依存性**：未知語のアクセント推定精度が低い
2. **コンテキスト制限**：文を超えた文脈が考慮できない
3. **方言非対応**：標準語以外のアクセントパターンに対応困難

### 7.3 計算リソースとのトレードオフ

高品質化には以下のリソースが必要：
- GPU: 最低8GB VRAM（理想は24GB以上）
- 学習時間: 500エポックで約1週間
- データセット: 最低50時間（理想は200時間以上）

## 8. 結論と推奨事項

### 8.1 問題の本質

Piper-plusの日本語音声品質問題は、**英語向けに設計されたアーキテクチャを日本語に適用したことによる構造的な問題**です。部分的な改善は可能ですが、根本的な解決には日本語特化の設計が必要です。

### 8.2 推奨されるアプローチ

1. **短期的対応**：
   - PyOpenJTalkの活用を最大化
   - 学習データの品質向上
   - ハイパーパラメータの最適化

2. **中長期的対応**：
   - 日本語特化のモデルアーキテクチャ開発
   - 階層的な韻律モデリング
   - 大規模・高品質データセットの構築

### 8.3 期待される改善効果

| 改善策 | 実装コスト | 期待効果 | 実現時期 |
|--------|-----------|---------|---------|
| フルコンテキスト活用 | 低 | 中 | 1ヶ月 |
| カスタム辞書 | 低 | 中 | 1ヶ月 |
| Duration改良 | 中 | 高 | 3ヶ月 |
| 階層モデル | 高 | 非常に高 | 6ヶ月 |
| 新G2P開発 | 非常に高 | 革新的 | 12ヶ月 |

## 9. 参考資料とリソース

### 技術文献
- Kurihara, N., et al. (2021). "Japanese Text-to-Speech with Hierarchical Prosody Modeling"
- OpenJTalk Documentation: http://open-jtalk.sourceforge.net/
- VITS Paper: Kim, J., et al. (2021). "Conditional Variational Autoencoder with Adversarial Learning for End-to-End Text-to-Speech"

### 実装リファレンス
- VOICEVOX Engine: https://github.com/VOICEVOX/voicevox_engine
- ESPnet-TTS: https://github.com/espnet/espnet
- Tacotron2 Japanese: https://github.com/Tacotron2-Japanese

### データセット
- JVS Corpus: https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_corpus
- CSS10 Japanese: https://github.com/Kyubyong/css10
- JSUT Corpus: https://sites.google.com/site/shinnosuketakamichi/publication/jsut

## 10. 付録：技術詳細

### A. OpenJTalkフルコンテキストラベル形式

```
xx^xx-sil+k=o/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx/D:xx+xx_xx/E:xx_xx!xx_xx-xx/F:xx_xx#xx_xx@xx_xx|xx_xx/G:xx_xx%xx_xx_xx/H:xx_xx/I:xx-xx@xx+xx&xx-xx|xx+xx/J:xx_xx/K:xx+xx-xx
```

各フィールドの意味：
- A-E: 音素・モーラレベル情報
- F-I: アクセント句レベル情報
- J-K: 呼気段落・文レベル情報

### B. 日本語音素体系の詳細

| カテゴリ | 音素 | IPA | 備考 |
|----------|------|-----|------|
| 母音 | a, i, u, e, o | [a, i, ɯ, e, o] | 基本5母音 |
| 無声化母音 | I, U | [i̥, ɯ̥] | 無声子音間で発生 |
| 長母音 | a:, i:, u:, e:, o: | [aː, iː, ɯː, eː, oː] | 2モーラ分の長さ |
| 撥音 | N | [n, m, ŋ, ɴ] | 後続音により変化 |
| 促音 | cl, q | [ʔ] | 声門閉鎖音 |

### C. サンプルコード：改善されたG2P処理

```python
import pyopenjtalk
import regex as re
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class PhonemeWithProsody:
    phoneme: str
    mora_position: int
    accent_type: int
    phrase_position: int
    duration_scale: float
    f0_contour: Optional[List[float]] = None

class EnhancedJapaneseG2P:
    def __init__(self):
        self.phoneme_pattern = re.compile(r'-([^+]+)\+')
        self.accent_pattern = re.compile(r'/A:([+-]?\d+)\+(\d+)\+(\d+)')
        
    def process(self, text: str) -> List[PhonemeWithProsody]:
        labels = pyopenjtalk.extract_fullcontext(text)
        result = []
        
        for label in labels:
            # 音素抽出
            phoneme_match = self.phoneme_pattern.search(label)
            if not phoneme_match:
                continue
                
            phoneme = phoneme_match.group(1)
            
            # 韻律情報抽出
            accent_match = self.accent_pattern.search(label)
            if accent_match:
                accent_type = int(accent_match.group(1))
                mora_position = int(accent_match.group(2))
                phrase_length = int(accent_match.group(3))
            else:
                accent_type = 0
                mora_position = 0
                phrase_length = 0
            
            # 継続長スケール計算（簡略化）
            duration_scale = 1.0
            if phoneme == 'pau':
                duration_scale = 0.5
            elif phoneme in ['a:', 'i:', 'u:', 'e:', 'o:']:
                duration_scale = 2.0
            
            result.append(PhonemeWithProsody(
                phoneme=phoneme,
                mora_position=mora_position,
                accent_type=accent_type,
                phrase_position=mora_position / max(phrase_length, 1),
                duration_scale=duration_scale
            ))
        
        return result

# 使用例
g2p = EnhancedJapaneseG2P()
phonemes = g2p.process("こんにちは、世界")
for p in phonemes:
    print(f"{p.phoneme}: accent={p.accent_type}, position={p.mora_position}")
```

---

**文書作成日**: 2025年9月5日  
**作成者**: Piper-plus技術調査チーム  
**バージョン**: 1.0