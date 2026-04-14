# Ticket: Python ランタイム Phoneme Timing 対応

**ブランチ**: `feat/phoneme-timing-python-wasm`
**優先度**: High
**関連**: C++/Rust/C#/Go では実装済み、Python/WASM が未対応

---

## 概要

Python ランタイム (`src/python_run/piper/`) に phoneme timing 機能を追加する。ONNX モデルは既に `durations` テンソルを出力しているが、`voice.py` の `session.run(...)[0]` で audio のみ取得し durations を破棄している。他の4ランタイムと同等の JSON/TSV 出力を実現する。

## 現状分析

### durations データフロー (現在)

```
ONNX モデル → [audio, durations] → voice.py:515 → [0] で audio のみ取得 → durations 破棄
```

### 破棄箇所

**`src/python_run/piper/voice.py` L515-518:**
```python
audio = self.session.run(
    None,
    args,
)[0].squeeze(0)  # ← [0] で第1出力のみ、durations (第2出力) は破棄
```

### 他ランタイムでの実装状況

| ランタイム | 計算関数 | 構造体 | 出力形式 |
|-----------|---------|--------|---------|
| Rust | `durations_to_timing()` in `timing.rs` | `PhonemeTimingInfo` / `TimingResult` | JSON, TSV, SRT |
| C++ | `extractTimingsFromDurations()` in `piper.cpp` | `PhonemeInfo` | JSON, TSV |
| C# | `TimingWriter.CalculateTiming()` | `PhonemeTimingEntry` | JSON, TSV |
| Go | `DurationsToTiming()` in `timing.go` | `PhonemeTimingInfo` / `TimingResult` | JSON, TSV |

### 共通計算ロジック (全ランタイム共通)

```
frame_time_ms = hop_length(256) / sample_rate(22050) * 1000  ≈ 11.61 ms/frame

cursor_ms = 0.0
for each (duration_frames, phoneme_token):
    duration_ms = max(duration_frames, 0.0) * frame_time_ms
    start_ms = cursor_ms
    end_ms = cursor_ms + duration_ms
    → PhonemeTimingInfo { phoneme, start_ms, end_ms, duration_ms }
    cursor_ms = end_ms
```

---

## 実装計画

### Step 1: timing モジュール新規作成

**ファイル**: `src/python_run/piper/timing.py` (新規)

```python
@dataclass
class PhonemeTimingInfo:
    phoneme: str
    start_ms: float
    end_ms: float
    duration_ms: float

@dataclass
class TimingResult:
    phonemes: list[PhonemeTimingInfo]
    total_duration_ms: float
    sample_rate: int

DEFAULT_HOP_LENGTH = 256

def durations_to_timing(
    durations: list[float],
    phoneme_tokens: list[str],
    sample_rate: int,
    hop_length: int = DEFAULT_HOP_LENGTH,
) -> TimingResult:
    ...

def timing_to_json(result: TimingResult) -> str:
    ...

def timing_to_tsv(result: TimingResult) -> str:
    ...
```

- Rust/Go と同じ計算ロジック
- hop_length=256 をデフォルト (他ランタイムと統一)
- sample_rate は config から取得
- JSON/TSV の2形式 (SRT はオプション)

### Step 2: voice.py の synthesize_ids_to_raw() 拡張

**ファイル**: `src/python_run/piper/voice.py`

**変更箇所**: L515-525

```python
# Before (現在)
audio = self.session.run(None, args)[0].squeeze(0)

# After (修正後)
outputs = self.session.run(None, args)
audio = outputs[0].squeeze(0)
durations = outputs[1].squeeze(0) if len(outputs) > 1 else None
```

**戻り値の拡張**:
- `synthesize_ids_to_raw()` の戻り値を `bytes` から `tuple[bytes, Optional[list[float]]]` に変更
- または新メソッド `synthesize_ids_to_raw_with_timing()` を追加して後方互換性を維持

**後方互換性の考慮**:
- `synthesize_ids_to_raw()` は既存の呼び出し元 (`synthesize()`, `synthesize_stream_raw()`) が使用
- 推奨: 既存メソッドはそのまま維持し、新メソッドを追加

### Step 3: PiperVoice に timing 対応メソッド追加

**ファイル**: `src/python_run/piper/voice.py`

```python
def synthesize_with_timing(
    self,
    text: str,
    wav_file: wave.Wave_write,
    *,
    speaker_id: Optional[int] = None,
    length_scale: Optional[float] = None,
    noise_scale: Optional[float] = None,
    noise_w: Optional[float] = None,
) -> TimingResult:
    """音声合成 + phoneme timing を返す"""
    ...
```

### Step 4: phoneme_id_map の逆引き

**config.json の phoneme_id_map 構造:**
```json
{
  "phoneme_id_map": {
    "_": [0], "^": [1], "$": [2],
    "a": [10], "k": [12], ...
  }
}
```

- phoneme_id → phoneme 文字列の逆引きマップを構築
- Rust CLI は `ph_0`, `ph_1` ... のインデックス形式を使用 (逆引き不要)
- Python では逆引きを実装してリッチな出力を提供 (C++/C# と同様)

### Step 5: テスト

**ファイル**: `src/python_run/tests/test_phoneme_timing.py` (新規)

テストケース (Rust test_timing.rs を参考):
1. `test_basic_durations` - 3音素の基本タイミング計算
2. `test_zero_duration` - ゼロ長音素
3. `test_negative_duration_clamped` - 負値は0にクランプ
4. `test_length_mismatch_error` - 配列長不一致エラー
5. `test_invalid_sample_rate` - 無効なサンプルレート
6. `test_to_json_format` - JSON 出力形式
7. `test_to_tsv_format` - TSV 出力形式
8. `test_timing_continuity` - end[i] == start[i+1] の連続性
9. `test_first_starts_at_zero` - 最初の音素は0開始
10. `test_total_equals_sum` - 総長 == 個別合計

### Step 6 (オプション): HTTP サーバー拡張

**ファイル**: `src/python_run/piper/http_server.py`

新エンドポイント: `POST /v1/audio/speech/timing`
- リクエスト: `{ "text": "...", "format": "json" | "tsv" }`
- レスポンス: TimingResult JSON

---

## 影響範囲

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `src/python_run/piper/timing.py` | 新規 | timing 計算 + フォーマッター |
| `src/python_run/piper/voice.py` | 修正 | durations 取得、timing メソッド追加 |
| `src/python_run/tests/test_phoneme_timing.py` | 新規 | ユニットテスト |
| `src/python_run/piper/http_server.py` | 修正 (オプション) | timing エンドポイント |

## テスト実行

```bash
cd src/python_run
uv run pytest tests/test_phoneme_timing.py -v
```

## CI

既存の `.github/workflows/python-tests.yml` で自動実行される (src/python_run/** トリガー)。

## 受け入れ基準

- [ ] `durations_to_timing()` が Rust/Go と同一の計算結果を返す
- [ ] JSON 出力が Rust の `TimingResult.to_json()` と同等の構造
- [ ] TSV 出力が Rust の `TimingResult.to_tsv()` と同等の構造
- [ ] `PiperVoice.synthesize_with_timing()` が TimingResult を返す
- [ ] 既存の `synthesize()` / `synthesize_stream_raw()` に影響なし (後方互換)
- [ ] テスト 10+ ケースが全 PASS
- [ ] CI (python-tests.yml) が PASS
