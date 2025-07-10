# 音素変換メカニズム詳細ドキュメント

## 概要

このドキュメントでは、Piperにおける音素変換の詳細なメカニズムと実装について説明します。

## 音素変換プロセス

### 1. テキスト前処理

#### 文字正規化
```python
def normalize_text(text: str) -> str:
    """テキストの正規化処理"""
    # NFKCで正規化（全角→半角変換など）
    text = unicodedata.normalize('NFKC', text)
    
    # 改行を統一
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # 連続する空白を単一に
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()
```

#### 特殊文字処理
```python
SPECIAL_CHARS = {
    '～': 'ー',  # 波ダッシュを長音記号に
    '〜': 'ー',  # 波ダッシュを長音記号に
    '−': 'ー',  # マイナス記号を長音記号に
    '‐': 'ー',  # ハイフンを長音記号に
}

def process_special_chars(text: str) -> str:
    for old, new in SPECIAL_CHARS.items():
        text = text.replace(old, new)
    return text
```

### 2. 日本語音素変換の詳細

#### OpenJTalkによる解析プロセス

1. **形態素解析**
   ```
   入力: "こんにちは世界"
   ↓
   形態素: こんにちは/感動詞 + 世界/名詞
   ```

2. **読み仮名生成**
   ```
   形態素: こんにちは → コンニチワ
   形態素: 世界 → セカイ
   ```

3. **音素列生成**
   ```
   コンニチワ → k o N n i ch i w a
   セカイ → s e k a i
   ```

#### フルコンテキストラベル

OpenJTalkが生成するフルコンテキストラベルの例：

```
xx^xx-sil+k=o/A:xx+xx+xx/B:xx-xx_xx/C:xx_xx+xx/D:xx+xx_xx/E:xx_xx!xx_xx-xx/F:xx_xx#xx_xx@xx_xx|xx_xx/G:xx_xx%xx_xx_xx/H:xx_xx/I:xx-xx@xx+xx&xx-xx|xx+xx/J:xx_xx/K:xx+xx-xx
```

各セクションの意味：
- A: 音素レベルの情報
- B: モーラレベルの情報
- C: 単語レベルの情報
- D: アクセント句レベルの情報
- E: 呼気段落レベルの情報
- F-K: その他の韻律情報

### 3. 音素体系

#### 日本語音素一覧

##### 母音
| 音素 | IPA | 説明 |
|------|-----|------|
| a | [a] | あ |
| i | [i] | い |
| u | [ɯ] | う |
| e | [e] | え |
| o | [o] | お |
| A | [ḁ] | 無声化あ |
| I | [i̥] | 無声化い |
| U | [ɯ̥] | 無声化う |
| E | [e̥] | 無声化え |
| O | [o̥] | 無声化お |

##### 子音
| 音素 | IPA | 説明 |
|------|-----|------|
| k | [k] | か行 |
| g | [g] | が行 |
| s | [s] | さ行 |
| z | [z] | ざ行 |
| t | [t] | た行 |
| d | [d] | だ行 |
| n | [n] | な行 |
| h | [h] | は行 |
| b | [b] | ば行 |
| p | [p] | ぱ行 |
| m | [m] | ま行 |
| y | [j] | や行 |
| r | [ɾ] | ら行 |
| w | [w] | わ行 |

##### 特殊音素
| 音素 | IPA | 説明 |
|------|-----|------|
| N | [ɴ] | ん（撥音） |
| q | [ʔ] | っ（促音） |
| cl | - | 閉鎖音の前の無音区間 |

##### 拗音（複合音素）
| 音素 | IPA | 説明 |
|------|-----|------|
| ky | [kʲ] | きゃ、きゅ、きょ |
| gy | [gʲ] | ぎゃ、ぎゅ、ぎょ |
| sh | [ɕ] | しゃ、しゅ、しょ |
| ch | [tɕ] | ちゃ、ちゅ、ちょ |
| ny | [ɲ] | にゃ、にゅ、にょ |
| hy | [ç] | ひゃ、ひゅ、ひょ |
| by | [bʲ] | びゃ、びゅ、びょ |
| py | [pʲ] | ぴゃ、ぴゅ、ぴょ |
| my | [mʲ] | みゃ、みゅ、みょ |
| ry | [ɾʲ] | りゃ、りゅ、りょ |

### 4. 音素変換ルール

#### 長音処理
```python
def process_long_vowels(kana: str, phonemes: List[str]) -> List[str]:
    """長音記号の処理"""
    result = []
    for i, char in enumerate(kana):
        if char == 'ー':
            # 直前の母音を繰り返す
            if i > 0 and result:
                last_vowel = get_last_vowel(result)
                if last_vowel:
                    result.append(last_vowel)
        else:
            result.extend(kana_to_phonemes(char))
    return result
```

#### 促音処理
```python
def process_sokuon(kana: str) -> List[str]:
    """促音（っ）の処理"""
    result = []
    i = 0
    while i < len(kana):
        if kana[i] in 'っッ':
            # 次の子音の種類に応じて処理
            if i + 1 < len(kana):
                next_consonant = get_consonant(kana[i + 1])
                if next_consonant in ['k', 'g', 't', 'd', 'p', 'b']:
                    result.append('cl')  # 閉鎖音の前
                result.append('q')
        else:
            result.extend(kana_to_phonemes(kana[i]))
        i += 1
    return result
```

#### 撥音処理
```python
def process_hatsuon(kana: str, next_sound: Optional[str]) -> str:
    """撥音（ん）の処理"""
    if next_sound is None:
        return 'N'  # 語末
    
    # 次の音に応じて調音位置が変わる
    if next_sound[0] in ['m', 'b', 'p']:
        return 'm'  # 両唇鼻音
    elif next_sound[0] in ['n', 't', 'd', 'r', 'z', 's']:
        return 'n'  # 歯茎鼻音
    elif next_sound[0] in ['k', 'g']:
        return 'ng'  # 軟口蓋鼻音
    else:
        return 'N'  # 口蓋垂鼻音
```

### 5. コンテキスト依存処理

#### 無声化
```python
def apply_devoicing(phonemes: List[str], context: Dict) -> List[str]:
    """母音の無声化処理"""
    result = []
    for i, phoneme in enumerate(phonemes):
        if phoneme in ['i', 'u']:
            # 無声子音に挟まれた場合
            if (i > 0 and i < len(phonemes) - 1 and
                is_voiceless(phonemes[i-1]) and
                is_voiceless(phonemes[i+1])):
                # 無声化母音に変換
                result.append(phoneme.upper())
            else:
                result.append(phoneme)
        else:
            result.append(phoneme)
    return result
```

#### 連濁
```python
def apply_rendaku(word1: str, word2: str) -> str:
    """連濁の適用"""
    # 複合語の後部要素の語頭が濁音化
    initial_sound = get_initial_sound(word2)
    
    if can_apply_rendaku(word1, word2):
        if initial_sound == 'k':
            return 'g' + word2[1:]
        elif initial_sound == 's':
            return 'z' + word2[1:]
        elif initial_sound == 't':
            return 'd' + word2[1:]
        elif initial_sound == 'h':
            return 'b' + word2[1:]
    
    return word2
```

### 6. 音素マッピングの実装詳細

#### PUAマッピングプロセス
```python
def map_phonemes_to_pua(phonemes: List[str]) -> List[str]:
    """音素列をPUA文字にマッピング"""
    result = []
    i = 0
    
    while i < len(phonemes):
        # 2文字の組み合わせをチェック
        if i + 1 < len(phonemes):
            digraph = phonemes[i] + phonemes[i + 1]
            if digraph in TOKEN2CHAR:
                result.append(TOKEN2CHAR[digraph])
                i += 2
                continue
        
        # 単一文字
        if phonemes[i] in TOKEN2CHAR:
            result.append(TOKEN2CHAR[phonemes[i]])
        else:
            result.append(phonemes[i])
        i += 1
    
    return result
```

### 7. エラー処理と検証

#### 音素検証
```python
VALID_PHONEMES = set(['a', 'i', 'u', 'e', 'o', 'k', 'g', 's', 'z', 't', 'd', 
                      'n', 'h', 'b', 'p', 'm', 'y', 'r', 'w', 'N', 'q', 'cl',
                      'A', 'I', 'U', 'E', 'O'])

def validate_phonemes(phonemes: List[str]) -> bool:
    """音素列の妥当性を検証"""
    for phoneme in phonemes:
        if phoneme not in VALID_PHONEMES and phoneme not in TOKEN2CHAR:
            logger.warning(f"Invalid phoneme: {phoneme}")
            return False
    return True
```

#### 音素修正
```python
def correct_phoneme_sequence(phonemes: List[str]) -> List[str]:
    """音素列の自動修正"""
    corrected = []
    
    for i, phoneme in enumerate(phonemes):
        # 連続する同一母音を長音に
        if (i > 0 and phoneme in VOWELS and 
            corrected and corrected[-1] == phoneme):
            # そのまま追加（長音として扱う）
            corrected.append(phoneme)
        
        # 不正な子音クラスタを修正
        elif is_invalid_cluster(corrected, phoneme):
            corrected.append('u')  # 母音を挿入
            corrected.append(phoneme)
        else:
            corrected.append(phoneme)
    
    return corrected
```

## 実装のベストプラクティス

### 1. パフォーマンス最適化

```python
# 音素変換結果のキャッシュ
@lru_cache(maxsize=10000)
def cached_phonemize(text: str) -> List[str]:
    return phonemize_japanese(text)
```

### 2. メモリ効率

```python
# ジェネレータを使用した大量テキスト処理
def phonemize_large_text(text: str, chunk_size: int = 1000):
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        yield phonemize_japanese(chunk)
```

### 3. エラーハンドリング

```python
def safe_phonemize(text: str) -> List[str]:
    try:
        return phonemize_japanese(text)
    except UnicodeDecodeError:
        # エンコーディングエラーの処理
        text = text.encode('utf-8', errors='ignore').decode('utf-8')
        return phonemize_japanese(text)
    except Exception as e:
        logger.error(f"Phonemization failed: {e}")
        # フォールバック処理
        return text_to_phonemes_fallback(text)
```

## トラブルシューティングガイド

### よくある問題と解決方法

1. **長音が正しく処理されない**
   - 原因：長音記号の種類が統一されていない
   - 解決：前処理で長音記号を統一する

2. **拗音が分離される**
   - 原因：音素マッピングが適用されていない
   - 解決：PUAマッピングを確認する

3. **アクセントが不自然**
   - 原因：アクセント情報が失われている
   - 解決：フルコンテキストラベルを使用する