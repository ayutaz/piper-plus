# Issue #109: 音素タイミング情報出力機能 - 実装計画

## 1. 技術調査結果

### 1.1 現在のアーキテクチャ
- **音声合成モデル**: VITS (Variational Inference with adversarial learning for end-to-end TTS)
- **推論フロー**: テキスト → 音素 → 音素ID → ONNX モデル → 音声
- **サンプルレート**: デフォルト 22050 Hz

### 1.2 タイミング情報の取得可能性
VITSモデルの`infer`メソッドは以下を返す：
1. **音声データ** (`o`)
2. **アテンション行列** (`attn`) - 音素と音声フレームの対応関係
3. **マスク** (`y_mask`)
4. **潜在変数** (`z, z_p, m_p, logs_p`)

**アテンション行列**が音素タイミング抽出の鍵となる：
- 形状: `[batch_size, 1, audio_frames, phoneme_length]`
- 各音素がどの音声フレームに対応するかを示す

### 1.3 現在の制限事項
1. **ONNXエクスポート**: 音声データのみ出力 (`output_names = ["output"]`)
2. **C++推論**: アテンション行列を取得していない
3. **メモリ使用量**: アテンション行列の保存により増加

## 2. 実装方針

### 2.1 アプローチ1: ONNXモデルの拡張（推奨）
**メリット**:
- 最も正確なタイミング情報
- 追加の処理が不要
- リアルタイムで取得可能

**デメリット**:
- 既存モデルとの互換性問題
- モデルサイズの増加

### 2.2 アプローチ2: 後処理による推定
**メリット**:
- 既存モデルを変更不要
- 実装が簡単

**デメリット**:
- 精度が低い
- 追加の計算時間

## 3. 実装計画（アプローチ1を採用）

### Phase 1: Python側の修正（モデルエクスポート）
1. `export_onnx.py`の修正
   ```python
   def infer_forward(text, text_lengths, scales, sid=None):
       audio, attn, _, _ = model_g.infer(...)
       return audio, attn  # アテンション行列も返す
   ```

2. ONNXエクスポート時の出力名を追加
   ```python
   output_names = ["output", "attention"]
   ```

3. 既存モデルとの互換性のため、フラグで制御
   ```python
   parser.add_argument("--with-attention", action="store_true", 
                       help="Include attention matrix in ONNX output")
   ```

### Phase 2: C++側の修正（推論とタイミング抽出）

1. **piper.hpp**: 新しい構造体の追加
   ```cpp
   struct PhonemeInfo {
       std::string phoneme;
       float start_time;
       float end_time;
   };
   
   struct SynthesisResult {
       std::vector<int16_t> audioBuffer;
       std::vector<PhonemeInfo> phonemeTimings;  // 新規追加
       double inferSeconds;
       double audioSeconds;
       double realTimeFactor;
   };
   ```

2. **piper.cpp**: アテンション行列からタイミング抽出
   ```cpp
   // ONNXから2つの出力を取得
   std::array<const char *, 2> outputNames = {"output", "attention"};
   
   // アテンション行列を処理
   auto attention = outputTensors[1].GetTensorData<float>();
   std::vector<PhonemeInfo> extractPhonemeTimings(
       const float* attention, 
       const std::vector<std::string>& phonemes,
       int audioFrames, 
       int sampleRate
   );
   ```

3. **main.cpp**: CLIオプションの追加
   ```cpp
   --output-timing <file>  // タイミング情報をJSONで出力
   --timing-format <json|tsv>  // 出力形式の選択
   ```

### Phase 3: タイミング抽出アルゴリズム

```cpp
// アテンション行列から各音素の開始・終了フレームを検出
for (int p = 0; p < phonemeCount; ++p) {
    int startFrame = -1, endFrame = -1;
    
    // 各音声フレームでの音素の重みを確認
    for (int f = 0; f < audioFrames; ++f) {
        float weight = attention[f * phonemeCount + p];
        
        if (weight > threshold && startFrame == -1) {
            startFrame = f;
        }
        if (weight > threshold) {
            endFrame = f;
        }
    }
    
    // フレームを時間に変換
    float startTime = startFrame / (float)sampleRate;
    float endTime = (endFrame + 1) / (float)sampleRate;
}
```

### Phase 4: 多言語対応

1. **Piperの音素化システム**:
   - **eSpeak-ng**: 大部分の言語（英語、ドイツ語、フランス語など）
   - **OpenJTalk**: 日本語専用
   - **Text/Codepoints**: フォールバック用の直接UTF-8マッピング

2. **言語別の音素化フロー**:
   ```
   # 日本語
   テキスト → OpenJTalk → 音素 → PUAマッピング → 音素ID → 合成
   
   # その他の言語
   テキスト → eSpeak-ng → IPA音素 → 音素ID → 合成
   ```

3. **タイミング抽出の統一性**:
   - **共通点**: VITSモデルのアテンション行列は言語に関係なく同じ形式
   - **音素IDベース**: 全ての言語で音素は数値IDに変換される
   - **タイミング抽出**: アテンション行列から音素IDの位置を特定

4. **言語別の考慮事項**:
   - **日本語（OpenJTalk）**:
     - 多文字音素（ky, sh, ch等）はPUAコードポイントに事前マッピング
     - 促音（っ）、長音（ー）の特別処理
     - 韻律マーカー（^, $, ?, #等）の除外
   
   - **eSpeak言語**:
     - IPA記号の直接使用
     - パディング文字（_）の処理
     - 言語固有の音素セット

5. **実装方法**:
   ```cpp
   // 音素文字列から実際の音素を抽出
   std::vector<std::string> extractPhonemes(
       const std::vector<Phoneme>& phonemeIds,
       const PhonemeIdMap& idMap,
       PhonemeType phonemeType
   ) {
       std::vector<std::string> phonemes;
       
       for (auto id : phonemeIds) {
           // IDから元の音素文字列を逆引き
           std::string phoneme = getPhonemeFromId(id, idMap);
           
           if (phonemeType == OpenJTalkPhonemes) {
               // PUAから元の多文字音素に戻す
               phoneme = unmapPUAToPhoneme(phoneme);
           }
           
           // 特殊記号（BOS, EOS等）を除外
           if (!isSpecialToken(phoneme)) {
               phonemes.push_back(phoneme);
           }
       }
       
       return phonemes;
   }
   
   // 言語別の後処理
   void postProcessTimings(
       std::vector<PhonemeInfo>& timings,
       PhonemeType phonemeType
   ) {
       if (phonemeType == OpenJTalkPhonemes) {
           // 日本語特有の処理
           adjustJapaneseTimings(timings);
       }
   }
   ```

6. **音素マッピングの管理**:
   - モデルの`phoneme_id_map`から音素とIDの対応を取得
   - 日本語のPUAマッピングテーブルの逆引き
   - 言語に依存しない統一的なタイミング抽出

### Phase 5: 出力形式

1. **JSON形式**:
   ```json
   {
     "phonemes": [
       {"phoneme": "k", "start": 0.000, "end": 0.045},
       {"phoneme": "o", "start": 0.045, "end": 0.120}
     ],
     "total_duration": 0.555,
     "language": "ja",
     "sample_rate": 22050
   }
   ```

2. **TSV形式**:
   ```
   phoneme\tstart\tend
   k\t0.000\t0.045
   o\t0.045\t0.120
   ```

### Phase 6: テストとベンチマーク

1. **単体テスト**:
   - アテンション行列の処理
   - タイミング抽出の精度
   - 出力形式の検証

2. **統合テスト**:
   - 各言語でのテスト
   - ストリーミングモードでの動作
   - 既存モデルとの互換性

3. **ベンチマーク**:
   - メモリ使用量の増加
   - 推論速度への影響
   - タイミング精度の評価

## 4. リスクと対策

### 4.1 互換性の問題
- **リスク**: 既存のONNXモデルが動作しない
- **対策**: アテンション出力をオプション化、デフォルトは無効

### 4.2 パフォーマンスへの影響
- **リスク**: メモリ使用量と処理時間の増加
- **対策**: 必要な場合のみアテンション行列を保持

### 4.3 精度の問題
- **リスク**: 音素境界の検出精度が低い
- **対策**: 閾値の調整、言語別の最適化

## 5. 実装スケジュール

1. **Week 1**: Python側の修正とモデルエクスポート
2. **Week 2**: C++側の基本実装
3. **Week 3**: タイミング抽出アルゴリズムの実装
4. **Week 4**: 多言語対応とテスト
5. **Week 5**: 最適化とドキュメント作成

## 6. 成功基準

1. **機能要件**:
   - JSON/TSV形式でのタイミング出力
   - 日本語を含む多言語対応
   - ストリーミングモードでの動作

2. **性能要件**:
   - 推論速度の低下 < 10%
   - メモリ使用量の増加 < 20%
   - タイミング精度 ±20ms以内

3. **互換性要件**:
   - 既存モデルの動作を妨げない
   - オプトイン方式での機能提供