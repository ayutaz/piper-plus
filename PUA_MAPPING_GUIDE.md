# PUA音素マッピングガイド

## 概要

PiperのOpenJTalk実装では、複数文字音素を単一のUnicode Private Use Area (PUA)文字にマッピングすることで、音素情報を保持しながら互換性を維持しています。

## なぜPUAマッピングが必要か

OpenJTalkは「ち」を"ch"、「つ」を"ts"のような複数文字音素として出力しますが、Piperのモデルは単一文字の音素を期待しています。単純に分割すると音素情報が失われるため、PUA文字（U+E000-U+E015）を使用して1対1のマッピングを実現しています。

## 既存モデルの更新方法（再学習不要）

### 方法1：自動更新スクリプト

```bash
# モデルのconfig.jsonを更新
python update_model_config.py path/to/your/model.onnx.json

# 例
python update_model_config.py ja_JP-kokoro-medium.onnx.json
```

これにより：
- 既存の音素IDマップにPUA文字のマッピングが追加されます
- "ch" → U+E00E、"ts" → U+E00F などがマッピングされます
- バックアップファイルが自動生成されます

### 方法2：手動で対応表を追加

既存の`config.json`の`phoneme_id_map`に以下を追加：

```json
{
  "phoneme_id_map": {
    // 既存のマッピング...
    
    // PUA文字を既存の音素IDにマッピング
    "\ue00e": [8, 11],  // "ch" → "c"のID + "h"のID
    "\ue00f": [19, 18], // "ts" → "t"のID + "s"のID
    "\ue010": [18, 11], // "sh" → "s"のID + "h"のID
    // ... 他のPUAマッピング
  }
}
```

## 新規モデルの学習

### Python側の前処理

```python
from token_mapper import map_phonemes
import pyopenjtalk

# テキストから音素を取得
text = "こんにちは"
phonemes = pyopenjtalk.g2p(text, kana=False).split()
# ['k', 'o', 'N', 'n', 'i', 'ch', 'i', 'w', 'a']

# PUAマッピングを適用
mapped_phonemes = map_phonemes(phonemes)
# ['k', 'o', 'N', 'n', 'i', '\ue00e', 'i', 'w', 'a']

# この mapped_phonemes を学習に使用
```

### config.json の生成

```python
from token_mapper import get_phoneme_id_map

# 音素IDマップを生成
phoneme_id_map = get_phoneme_id_map()

# モデル設定に含める
config = {
    "phoneme_type": "openjtalk",
    "phoneme_id_map": phoneme_id_map,
    # ... 他の設定
}
```

## 効果

1. **音質向上**: 複数文字音素の情報が保持される
2. **互換性維持**: 既存のモデル構造を変更する必要がない
3. **簡単な移行**: config.jsonの更新のみで対応可能

## PUAマッピング一覧

| 音素 | 説明 | PUA文字 | Unicode |
|------|------|---------|---------|
| a: | 長音あ | ‎ | U+E000 |
| i: | 長音い | ‎ | U+E001 |
| u: | 長音う | ‎ | U+E002 |
| e: | 長音え | ‎ | U+E003 |
| o: | 長音お | ‎ | U+E004 |
| cl | 促音 | ‎ | U+E005 |
| ch | ち | ‎ | U+E00E |
| ts | つ | ‎ | U+E00F |
| sh | し | ‎ | U+E010 |
| ky | きゃ | ‎ | U+E006 |
| gy | ぎゃ | ‎ | U+E008 |
| ny | にゃ | ‎ | U+E013 |
| hy | ひゃ | ‎ | U+E012 |
| my | みゃ | ‎ | U+E014 |
| ry | りゃ | ‎ | U+E015 |
| py | ぴゃ | ‎ | U+E00C |
| by | びゃ | ‎ | U+E00D |

## トラブルシューティング

### 警告が消えない場合

```
[warning] Missing "c" (\u0063): 1 time(s)
```

このような警告が出る場合は、config.jsonのPUAマッピングが不完全です。`update_model_config.py`を実行してください。

### 音質が改善しない場合

- モデルが元々単一文字で学習されている可能性があります
- その場合でも、PUAマッピングにより今後の改善が期待できます