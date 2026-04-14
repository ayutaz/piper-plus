# Phoneme Timing Output

VITS Duration Predictor から音素ごとの開始時刻・終了時刻・継続時間を抽出し、JSON/TSV/SRT 形式で出力する機能。リップシンク、字幕生成、カラオケアプリケーションで使用可能。

## 対応ランタイム

| ランタイム | 計算 | JSON | TSV | SRT | CLI flag | HTTP API |
|----------|------|------|-----|-----|----------|----------|
| Python | ✅ | ✅ | ✅ | ✅ | (`piper.synthesize_with_timing()`) | ✅ `/api/phoneme-timing` |
| Rust | ✅ | ✅ | ✅ | ✅ | `--output-timing` `--timing-format` | - |
| Go | ✅ | ✅ | ✅ | ✅ | `--output-timing` `--timing-format` | ✅ |
| C++ | ✅ | ✅ | ✅ | ✅ | `--output-timing` `--timing-format` | - |
| C# | ✅ | ✅ | ✅ | ✅ | (`PhonemeTimingExtractor`) | - |
| WASM/JS | ✅ | ✅ | ✅ | ✅ | (`AudioResult.timing`) | N/A (browser) |

すべての実装は **byte-for-byte 互換**: 同じ入力に対して同じ出力を生成します。

## 計算ロジック

```
frame_time_ms = (hop_length / sample_rate) * 1000

cursor_ms = 0
for each (duration_frames, phoneme_token):
    duration_ms = max(duration_frames, 0) * frame_time_ms
    start_ms = cursor_ms
    end_ms = cursor_ms + duration_ms
    cursor_ms = end_ms
```

**デフォルト値:**
- `hop_length`: 256 (VITS medium quality)
- `sample_rate`: モデル設定 (`config.json` の `audio.sample_rate`、通常 22050)

22050Hz / 256 hop の場合、1 フレーム ≈ 11.61 ms。

## 出力形式

### JSON (pretty-printed)

```json
{
  "phonemes": [
    {"phoneme": "^", "start_ms": 0.0, "end_ms": 58.0, "duration_ms": 58.0},
    {"phoneme": "k", "start_ms": 58.0, "end_ms": 150.8, "duration_ms": 92.8},
    {"phoneme": "o", "start_ms": 150.8, "end_ms": 290.0, "duration_ms": 139.2}
  ],
  "total_duration_ms": 290.0,
  "sample_rate": 22050
}
```

### JSON (compact)
単一行の JSON。ネットワーク送信や log 出力向け。

### TSV
```
start_ms	end_ms	duration_ms	phoneme
0.000	58.000	58.000	^
58.000	150.800	92.800	k
150.800	290.000	139.200	o
```

タブ・改行は phoneme 文字列内で `\t` / `\n` にエスケープされます。

### SRT (字幕)
```
1
00:00:00,000 --> 00:00:00,058
^

2
00:00:00,058 --> 00:00:00,151
k
```

VLC など標準的な字幕プレイヤーで再生可能。

## 使用例

### Python
```python
from piper import PiperVoice
from piper.timing import timing_to_json, timing_to_srt

voice = PiperVoice.load("model.onnx", config_path="config.json")
wav_bytes, timing = voice.synthesize_with_timing("こんにちは")

if timing:
    print(timing_to_json(timing))
    with open("subtitles.srt", "w") as f:
        f.write(timing_to_srt(timing))
```

### JavaScript / WASM
```javascript
import { PiperPlus, timingToJson, timingToSrt } from 'piper-plus';

const piper = await PiperPlus.initialize({ model: 'tsukuyomi' });
const result = await piper.synthesize('こんにちは');

if (result.hasTimingInfo) {
  console.log(timingToJson(result.timing));

  // リップシンク用
  for (const p of result.timing.phonemes) {
    console.log(`${p.phoneme}: ${p.start_ms.toFixed(1)}ms`);
  }
}
```

### Rust CLI
```bash
piper-plus -m model.onnx --text "Hello" \
  --output-timing timing.json --timing-format json
```

### Go CLI
```bash
piper-plus --model model.onnx --text "Hello" \
  --output-timing timing.json --timing-format json
```

### C++ CLI
```bash
echo "Hello" | piper --model model.onnx -f speech.wav \
  --output-timing timing.json --timing-format json
```

### HTTP API (Python `piper.http_server`)
```bash
curl "http://localhost:5000/api/phoneme-timing?text=Hello&format=json"
curl "http://localhost:5000/api/phoneme-timing?text=Hello&format=tsv"
```

## ユースケース

### リップシンク
3D アバター (VRM, Live2D) や 2D キャラクターの口の形状を音素に同期させる:

```javascript
const PHONEME_TO_VISEME = {
  a: 'A', i: 'I', u: 'U', e: 'E', o: 'O',
  k: 'K', g: 'K',
  s: 'S', sh: 'S', z: 'S',
  // ...
};

result.timing.phonemes.forEach(p => {
  setTimeout(() => {
    setMouthShape(PHONEME_TO_VISEME[p.phoneme] || 'NEUTRAL');
  }, p.start_ms);
});
```

### カラオケ字幕
歌詞を音素単位でハイライト表示:

```python
for p in timing.phonemes:
    schedule_highlight(p.phoneme, p.start_ms, p.end_ms)
```

### 動画字幕生成
SRT を直接動画編集ソフト (DaVinci Resolve, Premiere) にインポート:

```python
srt = timing_to_srt(timing)
with open("output.srt", "w") as f:
    f.write(srt)
```

## API リファレンス

詳細は各ランタイムの README を参照:

- Python: [`src/python_run/README.md`](../../src/python_run/README.md)
- WASM: [`src/wasm/openjtalk-web/README.npm.md`](../../src/wasm/openjtalk-web/README.npm.md)
- Rust: [`src/rust/piper-cli/README.md`](../../src/rust/piper-cli/README.md)
- Go: [`src/go/README.md`](../../src/go/README.md)

## 関連仕様

- 計算式: `frame_time_ms = (hop_length / sample_rate) * 1000`
- フィールド名: snake_case (`start_ms`, `end_ms`, `duration_ms`, `total_duration_ms`, `sample_rate`)
- ID → 音素文字列の逆引き: PUA 文字 (U+E000–U+F8FF) は `U+XXXX` 形式へフォールバック
- 短文 padding 適用時: original phoneme IDs を保持し timing 計算に使用
