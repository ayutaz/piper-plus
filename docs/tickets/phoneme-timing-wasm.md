# Ticket: JavaScript/WASM ランタイム Phoneme Timing 対応

**ブランチ**: `feat/phoneme-timing-python-wasm`
**優先度**: High
**関連**: C++/Rust/C#/Go では実装済み、Python/WASM が未対応

---

## 概要

JavaScript/WASM ランタイム (`src/wasm/openjtalk-web/`) に phoneme timing 機能を追加する。ONNX モデルは既に `durations` テンソルを出力しているが、`index.js` の `_infer()` で audio テンソルのみ取得し durations を無視している。ブラウザ内でリップシンク・カラオケ等のユースケースを実現する。

## 現状分析

### durations データフロー (現在)

```
ONNX モデル → { output: audio, durations: ... } → index.js:683 → results.output のみ取得 → durations 無視
```

### 無視箇所

**`src/wasm/openjtalk-web/src/index.js` L662, L683:**
```javascript
// L662: session.run
results = await this._session.run(feeds);

// L683: audio のみ取得、results.durations を無視
const audioTensor = results.output || results[Object.keys(results)[0]];
return new Float32Array(audioTensor.data);
```

### 現在の AudioResult クラス

**`src/wasm/openjtalk-web/src/audio-result.js` L108-117:**
```javascript
constructor(samples, sampleRate = 22050) {
  // samples: Float32Array, sampleRate: number のみ
  // timing 情報なし
}

// ゲッター: samples, sampleRate, duration (全体秒数のみ)
```

### 現在の TypeScript 型定義

**`src/wasm/openjtalk-web/types/index.d.ts`:**
- `SynthesizeOptions`: language, noiseScale, lengthScale, noiseW のみ
- `AudioResult`: samples, sampleRate, duration のみ
- timing 関連の型定義は一切なし

---

## 実装計画

### Step 1: _infer() から durations を返す

**ファイル**: `src/wasm/openjtalk-web/src/index.js`

**変更箇所**: L662-685 (`_infer()` メソッド)

```javascript
// Before (現在)
const audioTensor = results.output || results[Object.keys(results)[0]];
return new Float32Array(audioTensor.data);

// After (修正後)
const audioTensor = results.output || results[Object.keys(results)[0]];
const audio = new Float32Array(audioTensor.data);

let durations = null;
if (results.durations) {
  durations = new Float32Array(results.durations.data);
}

return { audio, durations };
```

**影響**: `_infer()` の戻り値が `Float32Array` → `{ audio: Float32Array, durations: Float32Array | null }` に変更。呼び出し元の `synthesize()`, `synthesizeWithVoiceCloning()`, `synthesizeStreaming()` を更新。

### Step 2: timing 計算ユーティリティ

**ファイル**: `src/wasm/openjtalk-web/src/timing.js` (新規)

```javascript
/**
 * @typedef {Object} PhonemeTimingInfo
 * @property {string} phoneme
 * @property {number} start_ms
 * @property {number} end_ms
 * @property {number} duration_ms
 */

/**
 * @typedef {Object} TimingResult
 * @property {PhonemeTimingInfo[]} phonemes
 * @property {number} total_duration_ms
 * @property {number} sample_rate
 */

const DEFAULT_HOP_LENGTH = 256;

/**
 * Duration フレーム配列からタイミング情報を計算する
 * @param {Float32Array} durations - フレーム単位の duration
 * @param {number} sampleRate - サンプルレート (e.g., 22050)
 * @param {number} [hopLength=256] - STFT hop length
 * @returns {TimingResult}
 */
export function durationsToTiming(durations, sampleRate, hopLength = DEFAULT_HOP_LENGTH) {
  const frameTimeMs = (hopLength / sampleRate) * 1000;
  let cursorMs = 0;
  const phonemes = [];

  for (let i = 0; i < durations.length; i++) {
    const frames = Math.max(durations[i], 0);
    const durationMs = frames * frameTimeMs;
    const startMs = cursorMs;
    const endMs = cursorMs + durationMs;

    phonemes.push({
      phoneme: `ph_${i}`,
      start_ms: startMs,
      end_ms: endMs,
      duration_ms: durationMs,
    });

    cursorMs = endMs;
  }

  return {
    phonemes,
    total_duration_ms: cursorMs,
    sample_rate: sampleRate,
  };
}

/**
 * TimingResult を JSON 文字列に変換
 * @param {TimingResult} result
 * @returns {string}
 */
export function timingToJson(result) {
  return JSON.stringify(result, null, 2);
}

/**
 * TimingResult を TSV 文字列に変換
 * @param {TimingResult} result
 * @returns {string}
 */
export function timingToTsv(result) {
  const header = 'start_ms\tend_ms\tduration_ms\tphoneme';
  const rows = result.phonemes.map(p =>
    `${p.start_ms.toFixed(3)}\t${p.end_ms.toFixed(3)}\t${p.duration_ms.toFixed(3)}\t${p.phoneme}`
  );
  return [header, ...rows].join('\n');
}
```

### Step 3: AudioResult 拡張

**ファイル**: `src/wasm/openjtalk-web/src/audio-result.js`

```javascript
class AudioResult {
  #samples;
  #sampleRate;
  #timing;  // ← 追加

  constructor(samples, sampleRate = 22050, timing = null) {
    // ... 既存のバリデーション ...
    this.#timing = timing;  // TimingResult | null
  }

  /** @returns {TimingResult | null} */
  get timing() {
    return this.#timing;
  }

  /** @returns {boolean} */
  get hasTimingInfo() {
    return this.#timing !== null;
  }

  // ... 既存メソッドはそのまま ...
}
```

### Step 4: synthesize() でタイミングを計算

**ファイル**: `src/wasm/openjtalk-web/src/index.js`

**変更箇所**: `synthesize()` メソッド (L261-307)

```javascript
async synthesize(text, options = {}) {
  // ... 既存の音素化・パディング処理 ...

  const { audio, durations } = await this._infer(phonemeIds, ...);

  // timing 計算
  let timing = null;
  if (durations) {
    timing = durationsToTiming(durations, this._config.audio.sample_rate);
  }

  // ... サイレンストリム処理 ...

  return new AudioResult(trimmedAudio, this._config.audio.sample_rate, timing);
}
```

`synthesizeWithVoiceCloning()` も同様に修正。

### Step 5: SynthesizeOptions 拡張 (オプション)

timing 計算のオーバーヘッドは極小 (数百音素の配列ループのみ) のため、常に計算してよい。ただし明示的な opt-in を好む場合:

```typescript
export interface SynthesizeOptions {
  language?: Language;
  noiseScale?: number;
  lengthScale?: number;
  noiseW?: number;
  returnTiming?: boolean;  // デフォルト: true
}
```

### Step 6: TypeScript 型定義更新

**ファイル**: `src/wasm/openjtalk-web/types/index.d.ts`

```typescript
/** 単一音素のタイミング情報 */
export interface PhonemeTimingInfo {
  /** 音素インデックス (e.g., "ph_0") */
  phoneme: string;
  /** 開始時刻 (ミリ秒) */
  start_ms: number;
  /** 終了時刻 (ミリ秒) */
  end_ms: number;
  /** 持続時間 (ミリ秒) */
  duration_ms: number;
}

/** 全音素のタイミング結果 */
export interface TimingResult {
  phonemes: PhonemeTimingInfo[];
  total_duration_ms: number;
  sample_rate: number;
}

export class AudioResult {
  constructor(samples: Float32Array, sampleRate?: number, timing?: TimingResult | null);
  readonly samples: Float32Array;
  readonly sampleRate: number;
  readonly duration: number;
  /** Phoneme timing 情報 (モデルが durations 出力を持つ場合) */
  readonly timing: TimingResult | null;
  /** timing 情報が利用可能かどうか */
  readonly hasTimingInfo: boolean;
  play(): Promise<void>;
  toBlob(): Blob;
  toWav(): ArrayBuffer;
  download(filename?: string): void;
}

export function durationsToTiming(
  durations: Float32Array,
  sampleRate: number,
  hopLength?: number,
): TimingResult;

export function timingToJson(result: TimingResult): string;
export function timingToTsv(result: TimingResult): string;
```

### Step 7: テスト

**ファイル**: `src/wasm/openjtalk-web/test/js/test-phoneme-timing.js` (新規)

テストケース (Rust test_timing.rs を参考):

```javascript
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { durationsToTiming, timingToJson, timingToTsv } from '../../src/timing.js';
```

1. `test_basic_three_phonemes` - 3音素の基本タイミング計算
2. `test_zero_duration` - ゼロ長音素
3. `test_negative_duration_clamped` - 負値は0にクランプ
4. `test_empty_input` - 空入力
5. `test_timing_continuity` - end[i] == start[i+1]
6. `test_first_starts_at_zero` - 最初の音素は0開始
7. `test_total_equals_sum` - 総長 == 個別合計
8. `test_json_output_valid` - JSON パース可能
9. `test_json_contains_all_fields` - JSON フィールド検証
10. `test_tsv_header_and_rows` - TSV ヘッダとデータ行
11. `test_different_sample_rates` - サンプルレート依存性
12. `test_audio_result_timing_property` - AudioResult.timing ゲッター
13. `test_audio_result_has_timing_info` - hasTimingInfo フラグ

**モック更新** (`test-piper-plus.js` 等):
```javascript
// session.run() のモックに durations を追加
globalThis.ort = {
  InferenceSession: {
    create: async () => ({
      run: async () => ({
        output: { data: new Float32Array(22050), dims: [1, 1, 22050] },
        durations: { data: new Float32Array([5, 8, 12, 10, 7]), dims: [1, 5] },
      }),
    }),
  },
};
```

### Step 8: package.json エクスポート更新

**ファイル**: `src/wasm/openjtalk-web/package.json`

```json
{
  "exports": {
    ".": { "types": "./types/index.d.ts", "import": "./src/index.js" },
    "./timing": { "types": "./types/index.d.ts", "import": "./src/timing.js" }
  }
}
```

---

## 影響範囲

| ファイル | 変更種別 | 内容 |
|---------|---------|------|
| `src/wasm/openjtalk-web/src/timing.js` | 新規 | timing 計算 + フォーマッター |
| `src/wasm/openjtalk-web/src/index.js` | 修正 | `_infer()` durations 取得、`synthesize()` timing 計算 |
| `src/wasm/openjtalk-web/src/audio-result.js` | 修正 | timing プロパティ追加 |
| `src/wasm/openjtalk-web/types/index.d.ts` | 修正 | 型定義追加 |
| `src/wasm/openjtalk-web/test/js/test-phoneme-timing.js` | 新規 | ユニットテスト |
| `src/wasm/openjtalk-web/package.json` | 修正 | エクスポート追加 |

## テスト実行

```bash
cd src/wasm/openjtalk-web
node --test test/js/test-phoneme-timing.js
```

## CI

既存の `.github/workflows/wasm-build.yml` と `g2p-wasm-ci.yml` で自動実行される。

## 利用例 (ブラウザ)

```javascript
import { PiperPlus } from 'piper-plus';

const piper = await PiperPlus.initialize({ model: 'tsukuyomi' });
const result = await piper.synthesize('こんにちは');

// 音声再生
await result.play();

// phoneme timing 取得
if (result.hasTimingInfo) {
  for (const p of result.timing.phonemes) {
    console.log(`${p.phoneme}: ${p.start_ms.toFixed(1)} - ${p.end_ms.toFixed(1)} ms`);
  }
}
```

## 受け入れ基準

- [ ] `_infer()` が durations テンソルも返す
- [ ] `durationsToTiming()` が Rust/Go と同一の計算結果を返す
- [ ] `AudioResult.timing` で TimingResult にアクセス可能
- [ ] `AudioResult.hasTimingInfo` が正しく判定
- [ ] JSON 出力が Rust の `TimingResult.to_json()` と同等の構造
- [ ] TSV 出力が Rust の `TimingResult.to_tsv()` と同等の構造
- [ ] TypeScript 型定義が全パブリック API をカバー
- [ ] 既存の `synthesize()` が timing なしモデルでも正常動作 (後方互換)
- [ ] テスト 13+ ケースが全 PASS
- [ ] CI (wasm-build.yml) が PASS
