# Piper アーキテクチャドキュメント

## 概要

Piperは高速で軽量な音声合成システムで、日本語を含む多言語に対応しています。このドキュメントでは、Piperのアーキテクチャと日本語音素変換メカニズムについて説明します。

## システムアーキテクチャ

### コンポーネント構成

```
┌─────────────────────────────────────────────────────────────┐
│                         Application Layer                      │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  CLI (C++)  │  │ Python API   │  │  Web Interface    │  │
│  └─────────────┘  └──────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                          Core Layer                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   Piper Core (C++)                    │    │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │    │
│  │  │ Phonemizer  │  │ VITS Engine  │  │ Audio I/O  │  │    │
│  │  └─────────────┘  └──────────────┘  └────────────┘  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    External Dependencies                      │
│  ┌──────────────┐  ┌─────────────────┐  ┌──────────────┐   │
│  │  OpenJTalk   │  │  ONNX Runtime   │  │  espeak-ng   │   │
│  │  (Japanese)  │  │  (Inference)    │  │  (Other)     │   │
│  └──────────────┘  └─────────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### データフロー

```
入力テキスト
    ↓
言語検出/前処理
    ↓
音素変換（Phonemization）
    ├── 日本語 → OpenJTalk
    ├── 英語 → espeak-ng
    └── その他 → 各言語固有エンジン
    ↓
音素マッピング（PUA変換）
    ↓
VITS音響モデル（ONNX）
    ↓
音声波形生成
    ↓
音声出力（WAV/RAW）
```

## 日本語音素変換メカニズム

### 1. OpenJTalk統合

日本語テキストの音素変換にはOpenJTalkを使用しています。

#### 処理フロー

1. **テキスト正規化**
   - UTF-8エンコーディングの確認
   - 特殊文字の処理
   - 改行・空白の正規化

2. **形態素解析**
   - MeCabベースの形態素解析
   - 品詞情報の抽出
   - 読み仮名の生成

3. **音素変換**
   - フルコンテキストラベルの生成
   - 音素列への変換
   - アクセント情報の付与

#### 実装詳細

```cpp
// src/cpp/openjtalk_wrapper.cpp の処理概要
class OpenJTalkWrapper {
    OpenJTalk* oj;
    
    HTS_Label* extractFullContext(const char* text) {
        // 1. テキストをOpenJTalkに渡す
        // 2. 形態素解析と音素変換を実行
        // 3. フルコンテキストラベルを返す
    }
};
```

### 2. 音素マッピング（PUA使用）

複数文字の音素を単一のUnicode文字にマッピングするため、Private Use Area (PUA)を使用しています。

#### マッピングテーブル

| 音素 | PUA コード | 用途 |
|------|-----------|------|
| ch   | U+E00E    | ちゃ、ちゅ、ちょ等 |
| ts   | U+E00F    | つぁ、つぃ等 |
| ky   | U+E006    | きゃ、きゅ、きょ |
| sh   | U+E010    | しゃ、しゅ、しょ |
| ny   | U+E011    | にゃ、にゅ、にょ |
| hy   | U+E012    | ひゃ、ひゅ、ひょ |
| ry   | U+E013    | りゃ、りゅ、りょ |
| gy   | U+E007    | ぎゃ、ぎゅ、ぎょ |
| jy   | U+E008    | じゃ、じゅ、じょ |
| by   | U+E009    | びゃ、びゅ、びょ |
| py   | U+E00A    | ぴゃ、ぴゅ、ぴょ |

#### 実装

```python
# src/python/piper_train/phonemize/token_mapper.py
TOKEN2CHAR = {
    "ch": "\ue00e",
    "ts": "\ue00f",
    "ky": "\ue006",
    # ... 他のマッピング
}

def map_sequence(phonemes: List[str]) -> List[str]:
    """音素列をPUA文字にマッピング"""
    mapped = []
    for phoneme in phonemes:
        if phoneme in TOKEN2CHAR:
            mapped.append(TOKEN2CHAR[phoneme])
        else:
            mapped.append(phoneme)
    return mapped
```

### 3. 無声化母音のサポート

日本語の無声化母音（A,I,U,E,O）をサポートしています。

```python
# 無声化母音のマッピング
UNVOICED_VOWELS = {
    "A": "a",  # 無声化された「あ」
    "I": "i",  # 無声化された「い」
    "U": "u",  # 無声化された「う」
    "E": "e",  # 無声化された「え」
    "O": "o",  # 無声化された「お」
}
```

## 拡張方法

### 新しい言語の追加

1. **音素変換エンジンの統合**
   ```cpp
   class NewLanguagePhonemizer : public Phonemizer {
       std::vector<std::string> phonemize(const std::string& text) override;
   };
   ```

2. **音素マッピングの定義**
   ```python
   # 新しい言語用のPUAマッピング
   NEW_LANG_TOKEN2CHAR = {
       "xxx": "\ue020",
       # ...
   }
   ```

3. **モデル設定の更新**
   ```json
   {
       "language": {"code": "xx"},
       "phoneme_type": "new_language",
       "phoneme_id_map": {
           "_": 0,
           "\ue020": 30
       }
   }
   ```

### カスタム音素セットの実装

1. **音素定義ファイルの作成**
   ```yaml
   phonemes:
     - symbol: "a"
       ipa: "a"
       description: "開前舌非円唇母音"
     - symbol: "k"
       ipa: "k"
       description: "無声軟口蓋破裂音"
   ```

2. **変換ルールの実装**
   ```python
   def custom_phoneme_rules(text: str) -> List[str]:
       # カスタムルールの実装
       pass
   ```

## パフォーマンス最適化

### 1. バッチ処理

複数のテキストを効率的に処理：

```cpp
class BatchPhonemizer {
    std::vector<std::vector<std::string>> phonemize_batch(
        const std::vector<std::string>& texts
    ) {
        // 並列処理の実装
        #pragma omp parallel for
        for (int i = 0; i < texts.size(); i++) {
            results[i] = phonemize(texts[i]);
        }
    }
};
```

### 2. キャッシング

頻繁に使用されるテキストの音素変換結果をキャッシュ：

```cpp
class PhonemeCache {
    std::unordered_map<std::string, std::vector<std::string>> cache;
    
    std::vector<std::string> get_or_compute(const std::string& text) {
        if (cache.find(text) != cache.end()) {
            return cache[text];
        }
        auto result = phonemize(text);
        cache[text] = result;
        return result;
    }
};
```

### 3. メモリ管理

効率的なメモリ使用：

```cpp
// 文字列プールを使用したメモリ最適化
class StringPool {
    std::unordered_set<std::string> pool;
    
    const std::string& intern(const std::string& str) {
        auto it = pool.insert(str);
        return *it.first;
    }
};
```

## セキュリティ考慮事項

### 入力検証

```cpp
bool validate_input(const std::string& text) {
    // 最大長チェック
    if (text.length() > MAX_INPUT_LENGTH) {
        return false;
    }
    
    // 制御文字チェック
    for (char c : text) {
        if (std::iscntrl(c) && c != '\n' && c != '\t') {
            return false;
        }
    }
    
    return true;
}
```

### 一時ファイルの安全な管理

```cpp
class SecureTempFile {
    std::string create_temp_file() {
        // ランダムなファイル名生成
        std::string filename = generate_random_filename();
        
        // 適切な権限設定
        int fd = open(filename.c_str(), O_CREAT | O_EXCL | O_WRONLY, 0600);
        
        // 使用後は必ず削除
        register_cleanup(filename);
        
        return filename;
    }
};
```

## デバッグとトラブルシューティング

### ログレベル

```cpp
enum LogLevel {
    ERROR = 0,
    WARNING = 1,
    INFO = 2,
    DEBUG = 3,
    TRACE = 4
};

// 環境変数でログレベルを制御
// PIPER_LOG_LEVEL=DEBUG
```

### 音素変換のデバッグ

```bash
# 音素変換の詳細ログを有効化
export PIPER_DEBUG_PHONEMES=1

# OpenJTalkの内部ログ
export OPENJTALK_DEBUG=1
```

### パフォーマンスプロファイリング

```cpp
class PerformanceProfiler {
    void profile_phonemization() {
        auto start = std::chrono::high_resolution_clock::now();
        
        // 処理実行
        phonemize(text);
        
        auto end = std::chrono::high_resolution_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
        
        log_performance("phonemization", duration.count());
    }
};
```

## 今後の拡張計画

1. **ストリーミング音素変換**
   - リアルタイム処理のサポート
   - 低レイテンシ実装

2. **高度な韻律制御**
   - SSML (Speech Synthesis Markup Language) サポート
   - 感情表現の追加

3. **マルチスレッド対応**
   - スレッドセーフな実装
   - 並列処理の最適化

4. **プラグインアーキテクチャ**
   - カスタム音素変換エンジンのプラグイン化
   - 動的ロード機能