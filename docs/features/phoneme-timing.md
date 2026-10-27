# Phoneme Timing Output

VITS Duration Predictor から音素ごとの開始時刻・終了時刻・継続時間を抽出し、JSON/TSV/SRT 形式で出力する機能。リップシンク、字幕生成、カラオケアプリケーションで使用可能。

## 対応ランタイム

| ランタイム | 計算 | JSON | TSV | SRT | 利用 API / CLI | HTTP API |
|----------|------|------|-----|-----|----------|----------|
| Python | ✅ | ✅ | ✅ | ✅ | `PiperVoice.synthesize_with_timing()` | ✅ `/api/phoneme-timing` |
| Rust | ✅ | ✅ | ✅ | ✅ | `--timing FORMAT` (stderr 出力) | - |
| Go | ✅ | ✅ | ✅ | ✅ | `--output-timing` `--timing-format` | - |
| C++ | ✅ | ✅ | ✅ | ✅ | `--output-timing` `--timing-format` | - |
| C# | ✅ | ✅ | ✅ | ✅ | `--output-timing` `--timing-format` | - |
| WASM/JS | ✅ | ✅ | ✅ | ✅ | (`AudioResult.timing`) | N/A (browser) |

JSON/TSV/SRT 欄はライブラリ formatter を含みます。Python HTTP は JSON/TSV、C# CLI は JSON/TSV/SRT を公開し、Python CLI に timing flag はありません。WASM の
streaming/SSML 経路は timing を返しません。各 API/CLI の公開範囲を確認してください。

duration 出力を持つ同じ ONNX model と同じ入力を使った実装は、契約で定めた
timing schema と数値規則に従います。WAV の浮動小数点演算や、duration 出力を
持たない legacy model の fallback は runtime/model ごとに差があり、全モデルで
byte-for-byte の timing file を保証するものではありません。C++ は duration 出力が
ない model では timing file を生成せず警告します。

## 計算ロジック

```text
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

```text
start_ms	end_ms	duration_ms	phoneme
0.000	58.000	58.000	^
58.000	150.800	92.800	k
150.800	290.000	139.200	o
```

タブ・改行は phoneme 文字列内で `\t` / `\n` にエスケープされます。

### SRT (字幕)

```text
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
from piper_plus import PiperVoice
from piper_plus.timing import timing_to_json, timing_to_srt

voice = PiperVoice.load("model.onnx", config_path="config.json")
wav_bytes, timing = voice.synthesize_with_timing("こんにちは")

if timing:
    print(timing_to_json(timing))
    with open("subtitles.srt", "w") as f:
        f.write(timing_to_srt(timing))
```

### JavaScript / WASM

tsukuyomi is a legacy compatibility alias; the npm model resolver (including
published `piper-plus` 0.8.1 and 0.8.2) maps it to the legacy root model, not to
the zs-v1 fine-tune. For a reproducible release example, provide the pinned
releases/zs-v1/tsukuyomi.onnx and matching config.json URLs (or local files).
The alias below is retained only to document the legacy API.

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
piper-plus-cli -m model.onnx --text "Hello" -f speech.wav --timing json
```

The Rust CLI writes timing JSON to stderr; redirect or capture stderr when
persisting it. The timing option is --timing FORMAT, not --output-timing or
--timing-format.

### Go CLI

```bash
piper-plus --model model.onnx --text "Hello" \
  --output-timing timing.json --timing-format json
```

### C++ CLI

```bash
echo "Hello" | piper-plus --model model.onnx -f speech.wav \
  --output-timing timing.json --timing-format json
```

### HTTP API (Python `piper_plus.http_server`)

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
- Rust: [`src/rust/piper-core/src/timing.rs`](../../src/rust/piper-core/src/timing.rs)
- Go: [`src/go/README.md`](../../src/go/README.md)

## 関連仕様

- 計算式: `frame_time_ms = (hop_length / sample_rate) * 1000`
- フィールド名: snake_case (`start_ms`, `end_ms`, `duration_ms`, `total_duration_ms`, `sample_rate`)
- ID → 音素文字列の逆引き: PUA 文字 (U+E000–U+F8FF) は `U+XXXX` 形式へフォールバック
- 短文 padding 適用時: original phoneme IDs を保持し timing 計算に使用

## 複数発話と分割合成

このブランチの C# stdin と Go batch／JSONL は `--output-timing timing.json` に対し `timing_001.json`, `timing_002.json` のように発話別に保存します。duration を持たないモデルで明示的に timing を要求すると C#/Go CLI は失敗します。

Rust/Go の SSML 分割合成と Rust の phoneme-silence 分割合成は WAV を連結しますが、単一の aligned duration tensor は返しません。Rust は timing 不在を警告し、Go は timing を要求した場合に失敗します。C# は `--streaming` と `--output-timing` の同時指定を拒否します。
