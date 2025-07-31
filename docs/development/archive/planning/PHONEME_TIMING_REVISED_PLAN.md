# Issue #109: 音素タイミング情報出力機能 - 修正版実装計画

## 1. 概要

批判的レビューの結果を踏まえ、**Duration Predictor**の出力を活用したアプローチに変更します。これにより、既存モデルとの互換性を保ちながら、最小限の変更で音素タイミング情報を抽出できます。

## 2. 技術的アプローチ

### 2.1 VITSのDuration Predictorの仕組み

VITSモデルは音素の継続時間を予測する**Duration Predictor (DP)**を内蔵しています：

```python
# models.py内のinferメソッド
logw = self.dp(x, x_mask, g=g)  # log-domain duration
w = torch.exp(logw) * x_mask * length_scale  # 実際の継続時間（フレーム数）
```

この`w`は各音素が何フレーム継続するかを示します。

### 2.2 タイミング計算の原理

```
音素:     [k]  [o]  [n]  [n]  [i]  [ch] [i]  [w]  [a]
Duration:  4    6    5    4    6    5    6    4    6   (フレーム数)
累積:      0    4    10   15   19   25   30   36   40  46

時間 = フレーム数 × hop_size / sample_rate
例: 4フレーム × 256 / 22050 = 0.046秒
```

## 3. 実装計画

### Phase 1: Duration情報の取得（3日）

#### 1.1 Python側の修正（最小限）

**export_onnx.py**の修正：
```python
def infer_forward_with_durations(text, text_lengths, scales, sid=None):
    """音声とduration情報を返すフォワード関数"""
    # 既存のinfer処理
    with torch.no_grad():
        # Duration predictorの出力を取得
        x, m_p, logs_p, x_mask = model_g.enc_p(text, text_lengths)
        
        if model_g.n_speakers > 1 and sid is not None:
            g = model_g.emb_g(sid).unsqueeze(-1)
        else:
            g = None
            
        # Duration予測
        if model_g.use_sdp:
            logw = model_g.dp(x, x_mask, g=g, reverse=True, 
                            noise_scale=scales[2])
        else:
            logw = model_g.dp(x, x_mask, g=g)
        
        w = torch.exp(logw) * x_mask * scales[1]  # length_scale適用
        
        # 通常のinfer処理を続行
        audio = model_g.infer(text, text_lengths, 
                            noise_scale=scales[0],
                            length_scale=scales[1], 
                            noise_scale_w=scales[2],
                            sid=sid)[0].unsqueeze(1)
    
    # 音声とdurationを返す
    return audio, w

# エクスポートオプション
parser.add_argument("--with-durations", action="store_true",
                   help="Include duration information in ONNX output")
```

#### 1.2 モデル互換性の維持

- デフォルト: 従来通り音声のみ出力
- `--with-durations`フラグ: 音声とduration情報を出力
- 既存モデルは変更不要

### Phase 2: C++側の実装（4日）

#### 2.1 データ構造の定義

**piper.hpp**:
```cpp
struct PhonemeInfo {
    std::string phoneme;     // 音素文字列
    float start_time;        // 開始時刻（秒）
    float end_time;          // 終了時刻（秒）
    int start_frame;         // 開始フレーム
    int end_frame;           // 終了フレーム
};

struct SynthesisResult {
    std::vector<int16_t> audioBuffer;
    std::vector<PhonemeInfo> phonemeTimings;  // 追加
    double inferSeconds;
    double audioSeconds;
    double realTimeFactor;
    bool hasTimingInfo = false;  // タイミング情報の有無
};
```

#### 2.2 Duration情報からタイミング抽出

**piper.cpp**に追加:
```cpp
std::vector<PhonemeInfo> extractTimingsFromDurations(
    const std::vector<float>& durations,
    const std::vector<Phoneme>& phonemeIds,
    const PhonemeIdMap& idMap,
    int hopSize,
    int sampleRate,
    PhonemeType phonemeType
) {
    std::vector<PhonemeInfo> timings;
    
    // 音素IDから文字列への逆引きマップを構築
    std::unordered_map<PhonemeId, std::string> idToPhoneme;
    for (const auto& [phoneme, ids] : idMap) {
        if (!ids.empty()) {
            idToPhoneme[ids[0]] = phoneme;
        }
    }
    
    float frameLength = static_cast<float>(hopSize) / sampleRate;
    float currentTime = 0.0f;
    int currentFrame = 0;
    
    for (size_t i = 0; i < phonemeIds.size() && i < durations.size(); ++i) {
        PhonemeId id = phonemeIds[i];
        float duration = durations[i];  // フレーム数
        
        // 特殊トークンをスキップ
        if (id == 0 || id == 1 || id == 2) {  // PAD, BOS, EOS
            currentFrame += static_cast<int>(duration);
            currentTime += duration * frameLength;
            continue;
        }
        
        // 音素文字列を取得
        std::string phonemeStr = "?";
        auto it = idToPhoneme.find(id);
        if (it != idToPhoneme.end()) {
            phonemeStr = it->second;
            
            // 日本語の場合、PUAマッピングを逆変換
            if (phonemeType == OpenJTalkPhonemes) {
                phonemeStr = unmapPUAToPhoneme(phonemeStr);
            }
        }
        
        PhonemeInfo info;
        info.phoneme = phonemeStr;
        info.start_time = currentTime;
        info.start_frame = currentFrame;
        
        currentFrame += static_cast<int>(duration);
        currentTime += duration * frameLength;
        
        info.end_time = currentTime;
        info.end_frame = currentFrame;
        
        timings.push_back(info);
    }
    
    return timings;
}
```

#### 2.3 推論処理の修正

```cpp
// synthesize関数内
if (session.hasDurationOutput) {
    // 2つの出力を取得
    std::array<const char*, 2> outputNames = {"output", "durations"};
    auto outputTensors = session.onnx.Run(...);
    
    // Duration情報を取得
    auto durationTensor = outputTensors[1];
    auto durations = durationTensor.GetTensorData<float>();
    size_t durationCount = durationTensor.GetTensorTypeAndShapeInfo()
                                       .GetElementCount();
    
    // タイミング情報を抽出
    std::vector<float> durationVec(durations, durations + durationCount);
    result.phonemeTimings = extractTimingsFromDurations(
        durationVec, phonemeIds, 
        voice.phonemizeConfig.phonemeIdMap,
        256,  // hop_size (from model config)
        voice.synthesisConfig.sampleRate,
        voice.phonemizeConfig.phonemeType
    );
    result.hasTimingInfo = true;
}
```

### Phase 3: 出力形式の実装（2日）

#### 3.1 JSON出力

```cpp
void outputTimingsAsJSON(
    const std::vector<PhonemeInfo>& timings,
    const std::string& filename,
    const std::string& text,
    int sampleRate
) {
    json output;
    json phonemesArray = json::array();
    
    for (const auto& info : timings) {
        phonemesArray.push_back({
            {"phoneme", info.phoneme},
            {"start", info.start_time},
            {"end", info.end_time},
            {"start_frame", info.start_frame},
            {"end_frame", info.end_frame}
        });
    }
    
    output["text"] = text;
    output["phonemes"] = phonemesArray;
    output["total_duration"] = timings.empty() ? 0.0 : 
                              timings.back().end_time;
    output["sample_rate"] = sampleRate;
    output["frame_shift_ms"] = 256.0 / sampleRate * 1000;  // hop_size
    
    std::ofstream file(filename);
    file << output.dump(2);
}
```

#### 3.2 TSV出力

```cpp
void outputTimingsAsTSV(
    const std::vector<PhonemeInfo>& timings,
    const std::string& filename
) {
    std::ofstream file(filename);
    file << "phoneme\tstart\tend\tstart_frame\tend_frame\n";
    
    for (const auto& info : timings) {
        file << info.phoneme << "\t"
             << info.start_time << "\t" 
             << info.end_time << "\t"
             << info.start_frame << "\t"
             << info.end_frame << "\n";
    }
}
```

### Phase 4: 多言語対応とテスト（3日）

#### 4.1 言語別の後処理

```cpp
void adjustTimingsForLanguage(
    std::vector<PhonemeInfo>& timings,
    PhonemeType phonemeType
) {
    if (phonemeType == OpenJTalkPhonemes) {
        // 日本語: 促音の長さ調整
        for (size_t i = 0; i < timings.size(); ++i) {
            if (timings[i].phoneme == "cl" && i > 0) {
                // 促音は前の音素に一部含める
                float overlap = (timings[i].end_time - 
                               timings[i].start_time) * 0.3f;
                timings[i-1].end_time += overlap;
                timings[i].start_time += overlap;
            }
        }
    }
    // 他の言語の調整...
}
```

#### 4.2 CLIオプション

```cpp
// main.cpp
runConfig.outputTimingPath = "";
runConfig.timingFormat = "json";  // or "tsv"

// オプション追加
{"output-timing", required_argument, nullptr, 'T'},
{"timing-format", required_argument, nullptr, 'F'},
```

### Phase 5: 既存モデルのサポート（2日）

既存モデル（durationなし）に対するフォールバック:

```cpp
std::vector<PhonemeInfo> estimateTimingsFromAudio(
    const std::vector<int16_t>& audio,
    const std::vector<Phoneme>& phonemes,
    int sampleRate
) {
    // シンプルな均等分割
    float totalDuration = audio.size() / static_cast<float>(sampleRate);
    float phonemeDuration = totalDuration / phonemes.size();
    
    std::vector<PhonemeInfo> timings;
    float currentTime = 0.0f;
    
    for (const auto& phoneme : phonemes) {
        PhonemeInfo info;
        info.phoneme = phonemeToString(phoneme);
        info.start_time = currentTime;
        info.end_time = currentTime + phonemeDuration;
        timings.push_back(info);
        currentTime += phonemeDuration;
    }
    
    return timings;
}
```

## 4. 利点とリスク

### 利点
1. **既存モデルとの互換性維持**
2. **最小限のメモリオーバーヘッド**（duration配列のみ）
3. **実装の簡潔性**
4. **高速な処理**（追加の計算がほぼ不要）

### リスク
1. **フレームレベルの精度**（約11.6ms @22050Hz）
2. **Duration Predictorの精度に依存**
3. **細かい音素境界の曖昧さ**

### 対策
1. **オプション機能として実装**（デフォルトOFF）
2. **将来的な精度向上の余地を残す**
3. **ユーザーに精度の限界を明示**

## 5. スケジュール

| フェーズ | 期間 | 内容 |
|---------|------|------|
| Phase 1 | 3日 | Python側のduration出力対応 |
| Phase 2 | 4日 | C++実装とタイミング抽出 |
| Phase 3 | 2日 | 出力形式（JSON/TSV） |
| Phase 4 | 3日 | 多言語対応とテスト |
| Phase 5 | 2日 | 既存モデルサポート |
| **合計** | **14日** | **2週間** |

## 6. 成功基準

1. **機能要件**
   - Duration情報からの音素タイミング抽出
   - JSON/TSV形式での出力
   - 既存モデルとの互換性

2. **性能要件**
   - 推論速度の低下 < 5%
   - メモリ増加 < 5%
   - タイミング精度 ±50ms以内

3. **品質要件**
   - 全言語でのテストカバレッジ
   - ドキュメントの完備
   - サンプルコードの提供