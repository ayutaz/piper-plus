# M4-5: int16/float32 二重変換の解消

> **Phase:** 4 -- 拡張 (将来)
> **利用者視点の優先度:** 低 -- 利用者フィードバック待ちでも可 (精度差は聴覚上無視可能、パフォーマンス改善も限定的)
> **見積り:** 中
> **依存:** Phase 3 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m4-5-int16float32-二重変換の解消)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

ONNX モデルの `float32` 出力から C API の `float32` 出力に至るデータフローで発生している `float32 -> int16 -> float32` の二重変換を解消し、精度向上と CPU コスト削減を実現する。

**現状のデータフロー:**

```
ONNX output (float32)
  |
  v  piper.cpp L776-789: clamp + scale -> int16_t
  |  audioBuffer.push_back(intAudioValue)
  v
std::vector<int16_t> audioBuffer
  |
  v  piper_plus_c_api.cpp: int16 -> float32 変換
  |  for (i) out[i] = audioBuffer[i] / 32768.0f
  v
float* out_samples (C API 出力)
```

この `float32 -> int16 -> float32` パスには 2 つの問題がある:

1. **精度劣化:** `int16` への量子化で 16-bit 精度に丸められ、元の `float32` に戻しても情報は失われている。量子化ノイズが加算される。
2. **CPU コスト:** 全サンプルに対して 2 回の型変換 + clamp 演算が走る。長い音声 (22050 Hz x 10 秒 = 220,500 サンプル) では無視できないオーバーヘッド。

**ゴール:** `piper::synthesize()` に `float32` 出力バリアントを追加し、C API がモデル出力を直接 `float32` のまま返せるようにする。既存の `int16` パス (CLI / WAV ファイル出力) は維持する。

---

## 2. 実装する内容の詳細

### 2.1 `piper.hpp` に float 出力バリアント追加

```cpp
namespace piper {

// Synthesize audio from phoneme IDs - float32 output variant.
// Output is normalized PCM float32 [-1.0, 1.0].
// Skips int16 quantization for direct float consumers (C API, streaming).
void synthesize(std::vector<PhonemeId> &phonemeIds,
                SynthesisConfig &synthesisConfig,
                ModelSession &session,
                std::vector<float> &audioBuffer,  // float32 output
                SynthesisResult &result,
                const std::vector<int64_t> *prosodyFeatures = nullptr,
                Voice *voice = nullptr);

} // namespace piper
```

### 2.2 `piper.cpp` のリファクタリング

現在の `synthesize()` (L649-836) を 2 段階に分割:

**Step 1: ONNX 推論の共通部分 (内部ヘルパー):**

```cpp
// 内部構造体: ONNX 推論の生出力を保持
struct SynthesisRawOutput {
    const float *audio;     // ONNX output tensor のポインタ
    int64_t audioCount;     // サンプル数
    float maxAudioValue;    // 正規化用の最大値
    // timing 関連 (duration output)
    std::vector<float> durations;
    bool hasDurations;
};

static SynthesisRawOutput runInference(
    std::vector<PhonemeId> &phonemeIds,
    SynthesisConfig &synthesisConfig,
    ModelSession &session,
    const std::vector<int64_t> *prosodyFeatures,
    Voice *voice);
```

**Step 2-A: int16 出力 (既存):**

```cpp
// 既存の synthesize() - int16 出力
void synthesize(std::vector<PhonemeId> &phonemeIds,
                SynthesisConfig &synthesisConfig,
                ModelSession &session,
                std::vector<int16_t> &audioBuffer,
                SynthesisResult &result,
                const std::vector<int64_t> *prosodyFeatures,
                Voice *voice)
{
    auto raw = runInference(phonemeIds, synthesisConfig, session,
                            prosodyFeatures, voice);
    // 既存の L776-789: float -> int16 変換
    float audioScale = MAX_WAV_VALUE / std::max(0.01f, raw.maxAudioValue);
    audioBuffer.reserve(raw.audioCount);
    for (int64_t i = 0; i < raw.audioCount; i++) {
        int16_t v = static_cast<int16_t>(
            std::clamp(raw.audio[i] * audioScale,
                       static_cast<float>(std::numeric_limits<int16_t>::min()),
                       static_cast<float>(std::numeric_limits<int16_t>::max())));
        audioBuffer.push_back(v);
    }
    // timing 抽出...
}
```

**Step 2-B: float32 出力 (新規):**

```cpp
// 新規 synthesize() - float32 出力
void synthesize(std::vector<PhonemeId> &phonemeIds,
                SynthesisConfig &synthesisConfig,
                ModelSession &session,
                std::vector<float> &audioBuffer,
                SynthesisResult &result,
                const std::vector<int64_t> *prosodyFeatures,
                Voice *voice)
{
    auto raw = runInference(phonemeIds, synthesisConfig, session,
                            prosodyFeatures, voice);
    // float32 正規化: [-1.0, 1.0] に正規化
    float audioScale = 1.0f / std::max(0.01f, raw.maxAudioValue);
    audioBuffer.reserve(raw.audioCount);
    for (int64_t i = 0; i < raw.audioCount; i++) {
        audioBuffer.push_back(
            std::clamp(raw.audio[i] * audioScale, -1.0f, 1.0f));
    }
    // timing 抽出 (int16 版と同一ロジック)
}
```

**ARM64 NEON 対応:**

`audio_neon.cpp` にも float32 出力用の NEON 最適化関数を追加:

```cpp
// 既存: int16 変換 + NEON
void scaleAndConvertAudioNEON(const float *input, int16_t *output,
                               int64_t count, float scale);

// 新規: float32 正規化 + NEON
void normalizeAudioNEON(const float *input, float *output,
                         int64_t count, float scale);
```

### 2.3 `textToAudio` の float32 対応

`textToAudio()` も float32 版を追加:

```cpp
void textToAudio(PiperConfig &config, Voice &voice, std::string text,
                 std::vector<float> &audioBuffer, SynthesisResult &result,
                 const std::function<void()> &audioCallback,
                 const std::vector<ProsodyFeature> *externalProsody = nullptr);
```

内部は既存の `textToAudio()` と同一の音素化ロジックを使い、`synthesize()` の float32 オーバーロードを呼び出す。

### 2.4 C API の内部変更

`piper_plus_c_api.cpp` の `piper_plus_synthesize` 内部で、int16 経由の変換ループを削除:

```cpp
// 変更前 (Phase 1):
std::vector<int16_t> audioBuffer;
piper::textToAudio(engine->config, engine->voice, text, audioBuffer, result, ...);
// int16 -> float32 変換
float *samples = (float *)malloc(audioBuffer.size() * sizeof(float));
for (size_t i = 0; i < audioBuffer.size(); i++) {
    samples[i] = audioBuffer[i] / 32768.0f;
}

// 変更後 (M4-5):
std::vector<float> audioBuffer;
piper::textToAudio(engine->config, engine->voice, text, audioBuffer, result, ...);
// 直接コピー (変換不要)
float *samples = (float *)malloc(audioBuffer.size() * sizeof(float));
std::memcpy(samples, audioBuffer.data(), audioBuffer.size() * sizeof(float));
```

### 2.5 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper.hpp` | `synthesize()` / `textToAudio()` の float32 オーバーロード宣言 |
| `src/cpp/piper.cpp` | `runInference()` 内部ヘルパー抽出、float32 版 `synthesize()` / `textToAudio()` 実装 |
| `src/cpp/audio_neon.hpp` | `normalizeAudioNEON()` 宣言 |
| `src/cpp/audio_neon.cpp` | `normalizeAudioNEON()` NEON 実装 |
| `src/cpp/piper_plus_c_api.cpp` | int16 経由の変換を float32 直接パスに置換 |
| `src/cpp/tests/test_c_api.cpp` | 出力精度検証テスト追加 |

**変更不要:** `main.cpp` (CLI は WAV 出力で int16 を使い続ける), `wavfile.hpp` (WAV は int16 フォーマット)

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | `synthesize()` リファクタリング + float32 バリアント + C API 統合 |
| テストエージェント | 1 | 精度比較テスト + パフォーマンスベンチマーク |

合計 2 名。`synthesize()` の内部リファクタリングは `textToAudio` / `textToAudioStreaming` / `phonemesToAudio` 等の全呼び出し元に影響するため、回帰テストが重要。

---

## 4. 提供範囲とテスト項目

### スコープ

- `synthesize()` の内部リファクタリング (`runInference` 抽出)
- float32 出力バリアントの追加
- C API の int16 経由変換を float32 直接パスに置換
- ARM64 NEON の float32 正規化関数
- 既存の int16 パスの維持 (CLI / WAV 出力)

### ユニットテスト

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestFloat32Normalization` | float32 出力が [-1.0, 1.0] 範囲 | 全サンプルが範囲内 |
| `TestInt16Unchanged` | int16 出力が変更前と同一 | ビット単位で一致 |
| `TestNoDoubleConversion` | C API 出力と ONNX 生出力の比較 | int16 経由より精度が高い |

### E2E テスト (モデル必要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestFloat32VsInt16` | 同一テキストで float32 / int16 パスの出力比較 | float32 の方が ONNX 生出力に近い (SNR > 90dB) |
| `TestFloat32Synthesis` | C API でワンショット合成 -> float32 出力 | サンプル数 > 0、有効な音声波形 |
| `TestFloat32Streaming` | Iterator / コールバック合成 -> float32 出力 | 各チャンクが正規化された float32 |
| `TestCLIWavUnchanged` | CLI の WAV 出力が変更前と同一 | バイナリ一致 |
| `TestPerformance` | 10 秒音声の合成時間比較 | float32 パスが int16+変換パスより高速 (目標: 5-10% 削減) |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| `synthesize()` リファクタリングの回帰 | 高 | `textToAudio`, `textToAudioStreaming`, `phonemesToAudio`, `phonemesToAudioStreaming` の全呼び出しパスが影響を受ける。int16 版の出力がビット単位で変わらないことを検証する回帰テスト必須 |
| ONNX output tensor のライフタイム | 高 | `runInference()` が `Ort::Value` の参照 (`const float*`) を返す場合、テンソルのライフタイムを超えてポインタが無効になる。内部ヘルパーで `std::vector<float>` にコピーするか、`Ort::Value` を保持する設計が必要 |
| float32 正規化の定義 | 中 | ONNX モデル出力は [-1, 1] に近いが保証されない。現在の int16 パスは `maxAudioValue` でスケーリングしている。float32 パスでも同じスケーリングを適用し、`[-1.0, 1.0]` に正規化する |
| NEON 実装の分岐 | 低 | ARM64 でのみ NEON パスを使う。`#ifdef USE_ARM64_NEON` の条件分岐が正しく動作すること |
| ABI 互換性 | 低 | C API の公開インターフェースは変更なし (float* 出力は Phase 1 から)。内部変更のみ |

### レビュー時の確認項目

1. `runInference()` の ONNX tensor ライフタイム管理が安全であること
2. int16 版 `synthesize()` の出力が変更前とビット単位で一致すること
3. float32 版の正規化が `[-1.0, 1.0]` 範囲を保証すること
4. `textToAudioStreaming` の内部チャンク処理が float32 に対応していること
5. ARM64 NEON の float32 版が正しく動作すること
6. CLI (`main.cpp`) の WAV 出力パスが影響を受けないこと

---

## 6. 一から作り直すとしたら

**Phase 1 で float32 パスを標準にすべきだった:** C API は最初から `float*` を返す設計。Phase 1 の時点で `synthesize()` に float32 出力を追加していれば、int16 経由の変換コードは最初から不要だった。ただし、Phase 1 の優先事項は「既存コードの最小変更で動くこと」であり、内部リファクタリングを避けたのは妥当な判断。

**`synthesize()` のテンプレート化:** int16 / float32 のコードが大部分重複するため、テンプレートまたはラムダで出力変換を抽象化する設計が理想的:

```cpp
template<typename T, typename ConvertFn>
void synthesizeImpl(/* common args */, std::vector<T> &audioBuffer,
                    ConvertFn convert) {
    auto raw = runInference(...);
    audioBuffer.reserve(raw.audioCount);
    for (int64_t i = 0; i < raw.audioCount; i++) {
        audioBuffer.push_back(convert(raw.audio[i], audioScale));
    }
}
```

ただし、テンプレートは `piper.cpp` のコンパイル時間を増加させ、ヘッダーへの移動が必要になるため、Phase 4 ではオーバーロード (2 つの関数) が実用的。

---

## 7. 後続タスクへの連絡事項

- **Phase 1 / Phase 2:** Phase 1 の `piper_plus_synthesize` は当初 int16->float32 変換で実装される。M4-5 でこの変換を除去する。Phase 2 の Iterator / streaming も同様に float32 直接パスに移行する。
- **M4-2 (Phoneme timing):** timing 抽出ロジックは `synthesize()` 内にある。`runInference()` への分離時に timing 抽出も共通化すること。
- **ARM64 NEON:** `audio_neon.cpp` の `normalizeAudioNEON` は M4-4 (Android NDK) と組み合わせてモバイルでのパフォーマンス向上に寄与する。
- **WAV 出力:** CLI の WAV ファイル出力は int16 フォーマット (PCM16) のため、int16 版 `synthesize()` は引き続き必要。削除しないこと。
