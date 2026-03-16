# WebGPU & ブラウザTTS最適化計画

**ブランチ**: `feature/webgpu-optimization`
**作成日**: 2026-03-16
**最終更新**: 2026-03-16 (レビュー反映)
**調査方法**: 10名の専門エージェントによる並列調査 + 5名のレビューエージェントによる検証

---

## 目次

1. [エグゼクティブサマリー](#1-エグゼクティブサマリー)
2. [AudioWorklet移行](#2-audioworklet移行)
3. [ストリーミング再生](#3-ストリーミング再生)
4. [メモリプール戦略](#4-メモリプール戦略)
5. [WebGPUバックエンド](#5-webgpuバックエンド)
6. [SharedArrayBuffer](#6-sharedarraybuffer)
7. [IndexedDBキャッシュ](#7-indexeddbキャッシュ)
8. [モバイルブラウザ最適化](#8-モバイルブラウザ最適化)
9. [ONNX Runtime Web最適化](#9-onnx-runtime-web最適化)
10. [パイプライン全体設計](#10-パイプライン全体設計)
11. [ベンチマーク基盤](#11-ベンチマーク基盤)
12. [実装ロードマップ](#12-実装ロードマップ)
13. [テスト計画](#13-テスト計画)

---

## 1. エグゼクティブサマリー

### 現状

piper-plusのブラウザTTS実装（`src/wasm/openjtalk-web/`）は以下の構成:

- **音素化**: OpenJTalk WASM (日本語) + eSpeak-ng Worker (英語)
- **推論**: ONNX Runtime Web 1.17.1, `executionProviders: ['wasm']`
- **再生**: HTML5 `<audio>` + ScriptProcessor (非推奨)
- **キャッシュ**: なし（毎回fetchでダウンロード）

### 期待される改善効果

| 最適化項目 | 改善度 | 優先度 |
|-----------|--------|--------|
| WebGPUバックエンド | 推論速度 2-4倍 | P1 |
| AudioWorklet移行 | レイテンシ 30倍改善 | P1 |
| IndexedDBキャッシュ | 2回目以降ロード 95%+削減 | P1 |
| ストリーミング再生 | TTFB 3-10倍改善 | P2 |
| メモリプール | GC圧力 50-65%削減 | P2 |
| ONNX Runtime更新 | 全体 15-25%高速化 | P2 |
| SharedArrayBuffer | Worker転送 50-80%削減 | P3 |
| モバイル最適化 | UX大幅改善 | P2 |

---

## 2. AudioWorklet移行

### 現状の問題

**ファイル**: `dist/demo.js` (L20-125)

```javascript
// 非推奨API
this.scriptNode = context.createScriptProcessor(4096, 1, 1);
```

| 問題 | 影響 |
|------|------|
| レイテンシ: bufferSize=4096で~185ms (22kHz時) | ユーザー体験低下 |
| ScriptProcessorは廃止予定 | 将来互換性なし |
| メインスレッド実行 | UIブロック |

> **計算根拠**: 4096 / 22050Hz = 185.8ms

### 移行設計

**AudioWorkletProcessor** (音声処理スレッドで実行):

```javascript
class PushAudioWorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._shouldKeepProcessing = true;  // 標準APIとの競合回避
    this.samplesQueue = [];
    this.port.onmessage = (e) => this.handleMessage(e.data);
  }

  handleMessage(data) {
    if (data.type === 'audio') {
      this.samplesQueue.push(data.samples);
    } else if (data.type === 'stop') {
      this._shouldKeepProcessing = false;
    }
  }

  process(inputs, outputs, parameters) {
    const output = outputs[0][0];
    let offset = 0;
    while (this.samplesQueue.length && offset < output.length) {
      const chunk = this.samplesQueue[0];
      const toCopy = Math.min(chunk.length, output.length - offset);
      output.set(chunk.subarray(0, toCopy), offset);
      offset += toCopy;
      if (toCopy === chunk.length) this.samplesQueue.shift();
      else this.samplesQueue[0] = chunk.subarray(toCopy);
    }
    if (offset < output.length) output.fill(0, offset);
    return this._shouldKeepProcessing || this.samplesQueue.length > 0;
  }
}
registerProcessor('push-audio-worklet-processor', PushAudioWorkletProcessor);
```

> **注意**: `this.closed` は AudioWorkletProcessor の標準APIに存在しないため、
> `_shouldKeepProcessing` のようなプライベートフラグを使用する。

**メインスレッド側**: Factoryパターンでフォールバック

```javascript
function selectAudioBackend() {
  if (typeof AudioWorkletNode !== 'undefined') return 'audioworklet';  // 推奨
  if (ctx.createScriptProcessor) return 'scriptprocessor';            // レガシー
  // iOS Safari メディア制約対応
  if (/iPhone|iPad|iPod/.test(navigator.userAgent)) return 'native-audio';
  return 'none';
}
```

### サンプルレート不一致への対応

推論モデルは22kHz出力だが、AudioWorkletはブラウザのネイティブサンプルレート（通常48kHz）を使用する。
**リサンプリング処理が必須**:

```javascript
class SimpleResampler {
  constructor(fromRate, toRate) {
    this.ratio = toRate / fromRate;  // 48000/22050 ≈ 2.18
  }

  resample(input) {
    const outputLength = Math.ceil(input.length * this.ratio);
    const output = new Float32Array(outputLength);
    for (let i = 0; i < outputLength; i++) {
      const srcIndex = i / this.ratio;
      const srcFloor = Math.floor(srcIndex);
      const srcCeil = Math.min(srcFloor + 1, input.length - 1);
      const frac = srcIndex - srcFloor;
      output[i] = input[srcFloor] * (1 - frac) + input[srcCeil] * frac;
    }
    return output;
  }
}
```

### 性能比較

| メトリック | ScriptProcessor (22kHz) | AudioWorklet (48kHz) | 改善度 |
|----------|------------------------|---------------------|--------|
| bufferSize | 4096 samples | 128 samples | 32倍 |
| レイテンシ | ~185ms | ~2.7ms | **68倍** |
| ジッター | ±20ms | ±1ms | 20倍 |

> **注意**: AudioWorkletレイテンシはブラウザのネイティブサンプルレートに依存。
> リサンプリングコスト（22kHz→48kHz）は別途 +10-30ms を見込む。

### ブラウザ対応

| ブラウザ | AudioWorklet | フォールバック |
|---------|-------------|--------------|
| Chrome 66+ | ✅ | - |
| Firefox 76+ | ✅ | - |
| Safari 14.1+ | ⚠️ 部分的 | ScriptProcessor |
| iOS Safari | ❌ (2026-Q1時点) | ScriptProcessor / native `<audio>` |
| Android Chrome 66+ | ✅ | - |

> **iOS Safari**: 2026年時点でAudioWorklet未対応。将来対応予定（時期未定）。
> iOS環境では `<audio>` タグによるWAVファイル再生にフォールバックする。

---

## 3. ストリーミング再生

### 現状の問題

全音声をバッファしてからWAV形式に変換 → 再生。長文テキストでTTFBが2-5秒。

### チャンク単位パイプライン設計

VITSモデルはサブ音素ストリーミング不可だが、**文単位チャンキング**は可能:

```
テキスト分割 → [Chunk1, Chunk2, Chunk3]
     ↓ パイプライン並列処理
Chunk1: [音素化] → [推論] → [再生開始]  ← TTFB ~300-600ms
Chunk2:    [音素化] → [推論] → [キュー待機]
Chunk3:       [音素化] → [推論] → [キュー待機]
```

### コア設計

```javascript
class StreamingTTSPipeline {
  constructor(options = {}) {
    // リングバッファサイズの根拠:
    // - デコード遅延の吸収: 最大3世代分
    // - 推論突風 +200ms → 4チャンク × 500ms/chunk で吸収
    // - メモリ: 4チャンク × ~10KB = ~40KB（許容範囲）
    // デスクトップ: 4-6、モバイル: 2-3 推奨
    this.ringBufferSize = options.bufferSize || 4;
    this.crossfadeMs = options.crossfadeMs || 50;
    this.sampleRate = options.sampleRate || 22050;
  }

  async synthesizeAndPlay(longText, language) {
    const chunks = this.splitSentences(longText, language);
    const ringBuffer = new RingBuffer(this.ringBufferSize);
    const crossfader = new ChunkCrossfader(this.crossfadeMs, this.sampleRate);

    // 音素化キャッシュ（並列パイプライン用）
    const phonemeCache = new Array(chunks.length);

    // パイプライン1: 音素化（先行処理）
    const phonemizeTask = (async () => {
      for (let i = 0; i < chunks.length; i++) {
        phonemeCache[i] = await this.phonemize(chunks[i], language);
      }
    })();

    // パイプライン2: 推論 + 再生（音素化完了を待って逐次実行）
    const synthesizeTask = (async () => {
      for (let i = 0; i < chunks.length; i++) {
        while (phonemeCache[i] === undefined) {
          await new Promise(r => setTimeout(r, 10));
        }
        const audio = await this.synthesize(phonemeCache[i]);
        const processed = crossfader.addChunk(this.trimSilence(audio));
        ringBuffer.enqueue(processed);
      }
    })();

    await Promise.all([phonemizeTask, synthesizeTask]);
  }
}
```

### チャンク間クロスフェード

文単位分割ではチャンク接合部で音が途切れる可能性がある。
50msのクロスフェードで自然な接続を実現:

```javascript
class ChunkCrossfader {
  constructor(crossfadeMs = 50, sampleRate = 22050) {
    this.crossfadeLength = Math.ceil(sampleRate * crossfadeMs / 1000);
    this.lastChunk = null;
  }

  addChunk(audio) {
    if (!this.lastChunk) {
      this.lastChunk = audio;
      return audio;
    }
    const faded = new Float32Array(audio.length);
    const fadeLen = Math.min(this.crossfadeLength, audio.length);
    for (let i = 0; i < fadeLen; i++) {
      const ratio = i / fadeLen;
      const prevIdx = Math.max(0, this.lastChunk.length - fadeLen + i);
      faded[i] = this.lastChunk[prevIdx] * (1 - ratio) + audio[i] * ratio;
    }
    for (let i = fadeLen; i < audio.length; i++) faded[i] = audio[i];
    this.lastChunk = audio;
    return faded;
  }
}
```

### 文分割ルール

| 言語 | 分割パターン | 目標チャンク長 |
|------|------------|--------------|
| 日本語 | `。！？` | 15-30文字 (1-3秒) |
| 英語 | `.!?` | 30-60文字 (1-3秒) |

### プロソディ維持に関する注意

VITSはテキスト全体の文脈でプロソディを学習しているため、文単位分割では:

- 文末のイントネーション低下パターンに変化が生じる可能性
- Duration Predictorが短文モードで長めの発音を生成する傾向
- エンコーダ状態がチャンク間で引き継がれない

**緩和策**: 文脈ウィンドウの拡大（現在の文 + 次の文を入力し、現在の文のみ再生）

> **要検証**: 文単位分割 vs 文脈ウィンドウ方式のMOS比較テストが必要

### 性能比較

| メトリック | 現在 (バッファ方式) | ストリーミング | 改善度 |
|----------|------------------|-------------|--------|
| TTFB (長文) | 2-5秒 | 300-600ms | **3-10倍** |
| TTFB (短文/キャッシュ) | 1-2秒 | 200-350ms | **3-7倍** |
| メモリ使用 | 20-100MB | 5-10MB (4バッファ) | 2-20倍 |

### TTFB詳細分析

| 環境 | 音素化 | ONNX推論 | リサンプリング | WAV生成 | 合計 |
|------|--------|----------|-------------|--------|------|
| Desktop (WebGPU + キャッシュ) | 50ms | 150ms | 50ms | 10ms | **260ms** |
| Desktop (WASM + キャッシュ) | 50ms | 400ms | 50ms | 10ms | **510ms** |
| モバイル (WASM + キャッシュなし) | 100ms | 800ms | 100ms | 20ms | **1020ms** |

---

## 4. メモリプール戦略

### 現状の問題

推論1回あたり10-20個のTypedArray新規作成 → GC圧力大

**主要アロケーション箇所** (`demo/index.html`):

| 行番号 | 型 | サイズ | 頻度 |
|--------|-----|--------|------|
| 718-720 | BigInt64Array (phonemeIds) | 可変 | 推論毎 |
| 723-725 | BigInt64Array (lengths) | 8B | 推論毎 |
| 728-734 | Float32Array (scales) | 12B | 推論毎 |
| 758 | Float32Array (audio) | 110-220KB | 推論毎 |
| 788-822 | ArrayBuffer (WAV) | 110-220KB | 推論毎 |

### プール設計

```javascript
class TypedArrayPool {
  static MAX_POOL_SIZE = 50;        // メモリリーク防止: 上限
  static MAX_POOL_AGE_MS = 60000;   // 1分で自動清掃

  constructor() {
    this.pools = new Map();   // key: "type:size" → array[]
    this.poolAges = new Map();
    this.stats = { hits: 0, misses: 0, evictions: 0 };
  }

  getArray(type, size) {
    const key = `${type}:${size}`;
    const pool = this.pools.get(key) || [];
    if (pool.length > 0) {
      this.stats.hits++;
      return pool.pop();
    }
    this.stats.misses++;
    return new (type === 'float32' ? Float32Array : BigInt64Array)(size);
  }

  returnArray(type, size, arr) {
    const key = `${type}:${size}`;
    let pool = this.pools.get(key);
    if (!pool) { pool = []; this.pools.set(key, pool); }

    // メモリリーク防止: 上限超過時は破棄
    if (pool.length >= TypedArrayPool.MAX_POOL_SIZE) {
      this.stats.evictions++;
      return;  // GC対象になる
    }

    arr.fill(0);  // セキュリティ: 前回データをクリア
    pool.push(arr);
    this.poolAges.set(key, Date.now());
  }

  // 定期クリーンアップ（推論完了後に呼び出し）
  cleanup() {
    const now = Date.now();
    for (const [key, timestamp] of this.poolAges.entries()) {
      if (now - timestamp > TypedArrayPool.MAX_POOL_AGE_MS) {
        this.pools.delete(key);
        this.poolAges.delete(key);
      }
    }
  }
}
```

### 期待効果

| 項目 | 現在 | 最適化後 | 改善率 | 根拠 |
|------|------|---------|--------|------|
| TypedArray作成/推論 | 10-20回 | 1-2回 | **95%** | プール化で削減 |
| GCオブジェクト/推論 | 10-15個 | 5-8個 | **50-65%** | ORT内部の中間テンソル生成は制御外 |
| 1推論メモリピーク | 600-700KB | 300-400KB | **50%** | プール化+再利用 |
| GC待機時間 (10推論) | 6-30ms | 3-10ms | **50%** | ブラウザ実測が必要 |

> **注意**: GC削減率はブラウザのGCアルゴリズムに依存し直接計測が困難。
> ONNX Runtime内部のテンソル割当は制御外のため、85%削減は過大評価。

---

## 5. WebGPUバックエンド

### VITSモデルのWebGPU対応率: ~95%

VITSモデルのONNXエクスポート時に、PyTorchの高レベルオペレータは基本演算に分解される:

| ONNXオペレータ | 用途 | WebGPU対応 | 備考 |
|---------------|------|----------|------|
| Conv | 特徴抽出 (Conv1d→Conv) | ✅ | VITSの主要演算 |
| ConvTranspose | デコーダ・アップサンプリング | ✅ | VITSの主要演算 |
| MatMul | 線形変換 | ✅ | |
| ReduceMean/Pow/Sqrt | LayerNorm構成要素 | ✅ | ONNX化時に分解 |
| Softmax | 注意機構 | ✅ | |
| Sigmoid/Tanh/Relu | 活性化 | ✅ | |
| Pad/Reshape/Concat | 形状操作 | ✅ | |

> **注意**: PyTorchの `LayerNorm` はONNXエクスポート時に `ReduceMean → Sub → Pow → ReduceMean → Add → Sqrt → Div` に分解される。
> VITSモデルでは Attention/GRU は使用されていない（Duration PredictorはConvベース）。

### フォールバック設計

```javascript
class WebGPUSessionManager {
  async createSession(modelPath) {
    // WebGL EPはORT 1.18+で非推奨のため、wasm-simd にフォールバック
    const providers = [
      { name: 'webgpu',    options: { graphOptimizationLevel: 'extended' } },
      { name: 'wasm-simd', options: { graphOptimizationLevel: 'extended' } },
      { name: 'wasm',      options: { graphOptimizationLevel: 'extended' } }
    ];

    for (const provider of providers) {
      try {
        if (provider.name === 'webgpu' && !await this.isWebGPUSupported()) continue;
        const session = await ort.InferenceSession.create(modelPath, {
          executionProviders: [provider]
        });
        this.currentProvider = provider.name;
        return session;
      } catch (e) {
        console.warn(`${provider.name} failed:`, e.message);
      }
    }
    throw new Error('All execution providers failed');
  }

  async isWebGPUSupported() {
    try { return !!(await navigator.gpu?.requestAdapter()); }
    catch { return false; }
  }
}
```

### ブラウザ対応状況 (2026年3月)

| ブラウザ | デスクトップ | モバイル | 備考 |
|---------|------------|---------|------|
| Chrome 130+ | ✅ D3D12/Metal/Vulkan | ✅ Android (Qualcomm/ARM) | 完全対応 |
| Edge 130+ | ✅ | ✅ Android | Chrome同等 |
| Firefox 141+ | ⚠️ Vulkan (フラグ有効時) | ❌ | 実験的段階 |
| Safari 18+ | ⚠️ Metal (部分対応) | ⚠️ iOS 18+ (限定的) | 実装初期段階 |

> **Safari**: Apple はメジャーOSリリースに準じたバージョニング。
> WebGPU は Safari 18+ (macOS Sequoia以降) で段階的展開中。
> プロダクションでは Chrome/Edge デスクトップを主対象に。

### 性能比較見積もり

| モデル | WASM | WASM-SIMD | WebGPU | 高速化 (vs WASM) |
|--------|------|-----------|--------|-----------------|
| 英語 (26MB) | 1000-1500ms | 800-1200ms | 300-600ms | **2-4倍** |
| 日本語 (61MB) | 1500-2500ms | 1200-1800ms | 400-800ms | **2-4倍** |
| ベースラインv2 (74MB) | 2000-3000ms | 1500-2200ms | 500-1000ms | **2-4倍** |

> **注意**: WebGPUにはGPU dispatch オーバーヘッド (~50-100ms) が含まれる。
> WASM-SIMDでも既に25-35%高速化されるため、WebGPUの相対的改善は2-4倍が現実的。

### GPUメモリ管理

| デバイス | VRAM | 26MB模型 | 61MB模型 |
|---------|------|---------|---------|
| デスクトップGPU | 4-12GB | ✅ | ✅ |
| タブレットGPU | 512MB-2GB | ✅ | ⚠️ |
| スマートフォンGPU | 256-512MB | ⚠️ | ❌ |

```javascript
// モバイルGPU容量チェック
async function checkGPUCapacity(modelSize) {
  const adapter = await navigator.gpu?.requestAdapter();
  if (!adapter) return false;
  const device = await adapter.requestDevice();
  const maxBufferSize = device.limits.maxBufferSize;
  const maxStorageSize = device.limits.maxStorageBufferBindingSize;
  const required = modelSize + 100 * 1024 * 1024; // +100MB buffer
  // 両方の制約でチェック
  return required <= maxBufferSize && modelSize <= maxStorageSize;
}
```

---

## 6. SharedArrayBuffer

### 現状

eSpeak-ng Worker はpostMessage()によるコピー転送。
ただし単文処理では転送サイズが1-30KB程度のため、**ボトルネック化は低確率**。
ストリーミング推論（長文・複数chunk）では10-30msの遅延が顕著になる。

### SAB設計

| 領域 | サイズ | 用途 |
|------|--------|------|
| 入力バッファ | 8KB | テキスト・音素データ |
| 出力バッファ | 65KB | 音素ID列 |
| 音声バッファ | 1MB | PCMデータ (22kHz × 10秒 = 880KB) |
| **合計** | **~1.1MB** | |

> **注意**: 20秒超の発話では1MBを超過するため、動的リサイズまたはストリーミング分割が必要。

### デプロイ制約 (COOP/COEP)

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

**COEP有効時のCDNリソース影響**:
現在のindex.html (L412) では `cdn.jsdelivr.net` からONNX Runtimeをロードしている。
COEP: require-corp ヘッダー設定時にはクロスオリジンリソースがブロックされる可能性がある。
→ ローカルバンドル化またはCORS確認が必要。

| プラットフォーム | SAB対応 | 備考 |
|---------------|---------|------|
| Chrome / Edge | ✅ COOP/COEP設定時 | |
| Firefox | ✅ COOP/COEP設定時 | |
| Safari (iOS) | ❌ 全バージョン未対応 | |
| GitHub Pages | ❌ ヘッダーカスタマイズ不可 | coi-serviceworker で回避可能 |
| Netlify / Vercel | ✅ ヘッダー設定可能 | |

### GitHub Pages 回避策

GitHub Pagesではカスタムヘッダーを設定できないが、
[coi-serviceworker](https://github.com/nicbarker/coi-serviceworker) を使用することで
SABを有効化できる:

```javascript
async function enableCrossOriginIsolation() {
  if (window.crossOriginIsolated) return true;
  const isGitHubPages = window.location.hostname.includes('github.io');
  if (!isGitHubPages) return false;

  try {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/coi-serviceworker@3.0.0/coi-amd.js';
    script.defer = true;
    return new Promise((resolve) => {
      script.onload = () => setTimeout(() => resolve(window.crossOriginIsolated), 100);
      script.onerror = () => resolve(false);
      document.head.appendChild(script);
    });
  } catch { return false; }
}
```

### フォールバック戦略

```
段階1: SAB + Atomics (Chrome/Firefox, COOP/COEP設定時)
段階2: postMessage + Transferable (Safari, 非COEP環境) — 8-12倍高速化
段階3: メインスレッド実行 (レガシーブラウザ)
```

> **実用的推奨**: 単文処理ではpostMessage + Transferableで十分。
> SABの導入はストリーミング対応後にROIを評価して判断する。

---

## 7. IndexedDBキャッシュ

### 現状のダウンロード規模

| 資産 | サイズ | 頻度 |
|------|--------|------|
| OpenJTalk辞書 (8ファイル) | ~23MB | 毎回 |
| ONNXモデル (日本語) | 61MB | 毎回 |
| ONNXモデル (英語) | 26MB | 毎回 |
| **合計** | **~110MB** | |

### ネットワーク環境別ロード時間

計算式: `サイズ(MB) × 8(bits) / 速度(Mbps) = 秒`

| 環境 | 速度 | 時間 |
|------|------|------|
| WiFi (50Mbps) | 50Mbps | **~18秒** |
| 4G LTE (20Mbps) | 20Mbps | **~44秒** |
| 3G (1Mbps) | 1Mbps | **~15分** |

### キャッシュ設計

```javascript
class CacheManager {
  static DB_NAME = 'piper-tts-cache';
  static DB_VERSION = 1;

  async openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(CacheManager.DB_NAME, CacheManager.DB_VERSION);
      req.onupgradeneeded = (e) => {
        e.target.result.createObjectStore('assets', { keyPath: 'key' });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async get(key) {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('assets', 'readonly');
      const req = tx.objectStore('assets').get(key);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async set(key, data, metadata) {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('assets', 'readwrite');
      const req = tx.objectStore('assets').put({
        key, data, metadata,
        version: metadata.version,
        timestamp: Date.now()
      });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
      tx.onerror = () => reject(tx.error);
    });
  }

  async isValid(key, expectedVersion) {
    const cached = await this.get(key);
    return cached && cached.version === expectedVersion;
  }
}
```

### Cache API vs IndexedDB

| 特性 | Cache API | IndexedDB |
|------|-----------|-----------|
| 用途 | HTTP レスポンス | 任意のバイナリ |
| Service Worker連携 | ✅ ネイティブ | 別途実装 |
| 構造化データ | ❌ | ✅ |
| **推奨用途** | WASM/JS/HTML | **モデル/辞書** |

### モバイルストレージ制限

| OS | 制限 | Eviction | 備考 |
|----|------|----------|------|
| iOS Safari | **~50MB/origin** | LRU | 110MB全体のキャッシュは不可 |
| Android Chrome | 端末の60% | LRU | 通常十分な容量 |

> **重要**: iOS Safari のオリジンあたりの制限は ~50MB であり、110MB全体をIndexedDBに保存できない。
> iOS向けには**優先度ベースのキャッシュ戦略**が必要:
> 1. 辞書ファイル (~23MB): 必ずキャッシュ（言語切替で共用）
> 2. 使用中のモデル: キャッシュ（1言語のみ、26-61MB）
> 3. 他言語モデル: キャッシュ対象外（オンデマンドfetch）
>
> Android Chromeでは端末容量の60%を使用可能なため、全資産キャッシュが可能。

### Service Worker設計

```javascript
// service-worker.js
const CACHE_NAME = 'piper-v1';
const STATIC_ASSETS = [
  '/index.html',
  '/src/simple_unified_api.js',
  '/dist/openjtalk.js',
  '/dist/openjtalk.wasm'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  // 静的アセット: Cache API
  if (url.pathname.includes('/dist/') || url.pathname.includes('/src/')) {
    event.respondWith(
      caches.match(event.request).then(r => r || fetch(event.request))
    );
  }
  // モデル/辞書: IndexedDB（メインスレッドで処理）
});
```

---

## 8. モバイルブラウザ最適化

### 現在のUI問題

- メディアクエリなし（レスポンシブ未対応）
- ボタンサイズ不足（タッチターゲット 48px未満）
- `textarea` フォントサイズ < 16px（iOS自動ズーム発生）
- タッチフィードバックなし

### iOS Safari 固有の制約

| 制約 | 対策 |
|------|------|
| AudioContext autoplay | ユーザータップ内で `context.resume()` |
| WASMメモリ ~1GB | モデル + 辞書合計を300MB以下に |
| バックグラウンド停止 | `<audio>` タグ使用で継続可能 |
| SharedArrayBuffer非対応 | postMessage + Transferable フォールバック |
| IndexedDB ~50MB/origin | 優先度ベースキャッシュ（辞書+1モデルのみ） |

### モデル量子化戦略

| 方式 | サイズ削減 | 速度向上 | 品質影響 | 優先度 | 検証状況 |
|------|---------|---------|---------|--------|---------|
| **FP16** | 50% | +10-20% | ±0.05-0.15 MOS | **P1** | **要検証** |
| INT8 | 75% | +20-30% | ±0.3-0.5 MOS | P3 | 未検証 |

> **注意**: MOS影響は一般的なTTSモデルの文献値。Piper-plus VITSモデルでの実測はまだ行われていない。
> WavLM Discriminator学習モデルではFP16で数値不安定性（音割れ）の可能性があり、慎重な検証が必要。
> FP16量子化はPython側 (`export_onnx.py`) に `--fp16` フラグ追加が必要（Web側だけでは完結しない）。

### PWA対応

```json
{
  "name": "Piper TTS",
  "short_name": "Piper TTS",
  "display": "standalone",
  "start_url": "./",
  "icons": [
    { "src": "./icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "./icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

> **変更**: `start_url` を相対パス `"./"` に変更（GitHub Pages以外のデプロイにも対応）。

### レスポンシブCSS

```css
/* 小型スマートフォン (iPhone SE, Pixel 5) */
@media (max-width: 360px) {
  .container { padding: 6px; }
  button { min-height: 44px; width: 100%; font-size: 14px; }
  textarea { font-size: 16px; }  /* iOS自動ズーム防止 */
  .button-group { flex-direction: column; gap: 6px; }
}

/* スマートフォン (iPhone 12, Galaxy S) */
@media (min-width: 361px) and (max-width: 480px) {
  .container { padding: 8px; }
  button { min-height: 44px; width: 100%; }
  textarea { font-size: 16px; }
  .button-group { flex-direction: column; gap: 8px; }
}

/* タブレット (iPad) */
@media (min-width: 481px) and (max-width: 768px) {
  .container { padding: 16px; }
  button { min-height: 44px; }
  .button-group { flex-direction: row; gap: 10px; }
}

/* デスクトップ */
@media (min-width: 769px) {
  .container { max-width: 900px; margin: 0 auto; padding: 30px; }
  .button-group { flex-direction: row; gap: 10px; }
}
```

---

## 9. ONNX Runtime Web最適化

### バージョン更新: 1.17.1 → 1.19+

| 機能 | 1.17.1 | 1.19+ | 効果 | Web対応 |
|------|--------|-------|------|---------|
| WASM SIMD | 基本対応 | 最適化強化 | +25-35% | ✅ |
| マルチスレッド | ❌ | 実験的 | +2-3倍 | ⚠️ 限定的 |
| enableMemPattern | 限定的 | ✅ | +8-12% | ✅ |
| ~~IOBinding~~ | - | - | - | ❌ **Node.js専用** |
| ~~intraOpNumThreads~~ | - | - | - | ❌ **WASM非対応** |

> **重要**: `IOBinding` は Node.js C++ API のみ（Web版ではAPIが存在しない）。
> `intraOpNumThreads` は WASM 環境ではシングルスレッド実行のため効果なし。
> これらをWeb版で設定するとエラーまたは無視される。

### 推奨セッション設定

```javascript
// 現在 (1.17.1)
onnxSession = await ort.InferenceSession.create(modelPath, {
  executionProviders: ['wasm'],
  graphOptimizationLevel: 'all'
});

// 推奨 (1.19+)
onnxSession = await ort.InferenceSession.create(modelPath, {
  executionProviders: ['wasm-simd', 'wasm'],  // SIMD優先、自動フォールバック
  graphOptimizationLevel: 'extended',         // 拡張最適化
  enableMemPattern: true                      // メモリパターン再利用
  // intraOpNumThreads, IOBinding はWeb版では使用不可
});
```

### 互換性テスト要件

ORT 1.17.1→1.19+ の更新前に以下を検証:

| テスト項目 | 対象 | 備考 |
|-----------|------|------|
| MOS/レイテンシ比較 | 全モデル | 劣化がないことを確認 |
| メモリリーク | 長時間連続推論 (100回+) | DevToolsで計測 |
| Safari 14.1+互換性 | macOS/iOS | マルチスレッド機能のdisable確認 |
| 既存デモ動作確認 | demo/index.html | CDN URL更新後の全機能テスト |

### VITSモデル固有の最適化

| レイヤー | SIMD効果 | 全体寄与 |
|---------|---------|---------|
| Conv (8層) | +25-35% | +5-10% |
| ConvTranspose (Decoder) | +20-30% | +5-8% |
| ReduceMean/Pow/Sqrt (LayerNorm) | +15-25% | +3-5% |
| **全体** | | **+15-25%** |

---

## 10. パイプライン全体設計

### 現在のシリアルパイプライン (実測値ベース)

```
テキスト入力 → 前処理 → 音素化 → ID変換 → ONNX推論 → WAV生成 → 再生
               [100ms]  [200ms]  [50ms]   [1000-2000ms] [50ms]
                                                  合計: ~1400-2400ms (WASM, 初回)
```

> **注意**: 以前の見積もり (ONNX推論150ms, 合計550ms) はWebGPU最適化後の目標値であり、
> 現在のWASMバックエンドでの実測値は1000-2000ms。

### 最適化後の並列パイプライン

```
┌─────────────────────────────────────────────────────────────┐
│ UI レイヤー                                                  │
│ テキスト入力 │ 言語選択 │ 話者選択 │ 再生コントロール          │
└──────┬──────────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────────────────┐
│ メインスレッド (音素化)  ← キャッシュ確認 → IndexedDB         │
│ OpenJTalk WASM (日本語) / eSpeak-ng Worker (英語)            │
└──────┬──────────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────────────────┐
│ ONNX推論 (WebGPU → WASM-SIMD → WASM フォールバック)          │
│ + メモリプール                                               │
└──────┬──────────────────────────────────────────────────────┘
       ↓
┌──────────────────────────────────────────────────────────────┐
│ AudioWorklet (リアルタイム再生)                               │
│ リサンプラー (22kHz→48kHz) → リングバッファ → スピーカー       │
└──────────────────────────────────────────────────────────────┘
```

> **変更点**:
> - WebGLフォールバック削除（ORT 1.18+で非推奨）→ WASM-SIMDに変更
> - IOBinding削除（Web版非対応）
> - OpenJTalk WASMは現時点ではメインスレッド実行（Worker移行は段階的に実施）
> - リサンプラー追加（22kHz→48kHz変換）

### 実装優先順位 (ROI)

| 優先度 | 施策 | 効果 | 実装時間 |
|--------|------|------|---------|
| P1 | キャッシング (IndexedDB) | 2回目以降95%+高速化 | 2-3日 |
| P1 | WebGPUフォールバック | 推論2-4倍 | 1-2週 |
| P1 | AudioWorklet移行 | レイテンシ30倍+ | 2-3週 |
| P2 | ONNX Runtime更新 + SIMD | 全体15-25% | 1-2日 |
| P2 | ストリーミング再生 | TTFB 3-10倍 | 2-3週 |
| P2 | メモリプール | GC 50-65%削減 | 1-2週 |
| P2 | モバイルUI | UX大幅改善 | 1週 |
| P3 | SharedArrayBuffer | 転送50-80%削減 | 2-3週 |
| P3 | FP16量子化 (Python+Web) | サイズ50%削減 | 1-2週 |
| P3 | PWA対応 | オフライン利用可 | 1週 |

---

## 11. ベンチマーク基盤

### 計測ポイント

初回ロード（キャッシュなし）とキャッシュ有りを分離して目標設定:

| ステージ | メトリクス | 初回目標 | キャッシュ有り目標 |
|---------|-----------|---------|------------------|
| CDN/ネットワーク遅延 | Network | ~200-500ms | 0ms |
| WASM初期化 | WASM Load | <200ms | <200ms |
| 辞書ロード | Dict Load | <2000ms | <200ms (IndexedDB) |
| ONNXモデルロード | Model Load | <1500ms | <300ms (IndexedDB) |
| 音素化 | Phonemization | <100ms | <100ms |
| ONNX推論 (WASM) | Inference | <1500ms | <1500ms |
| ONNX推論 (WebGPU) | Inference | <500ms | <500ms |
| **初回TTFB** | **Time To First Audio** | **<5000ms** | - |
| **2回目以降TTFB** | (キャッシュ有) | - | **<800ms (WebGPU)** |

### BenchmarkRunner設計

```javascript
class BenchmarkRunner {
  async measureAsync(stageName, fn) {
    performance.mark(`${stageName}-start`);
    const result = await fn();
    performance.mark(`${stageName}-end`);
    performance.measure(stageName, `${stageName}-start`, `${stageName}-end`);
    return result;
  }

  getSummary() {
    return performance.getEntriesByType('measure').map(m => ({
      name: m.name,
      duration: m.duration.toFixed(2) + 'ms'
    }));
  }
}
```

### リグレッション検知

```javascript
class RegressionDetector {
  // メトリック別のしきい値設定
  static THRESHOLDS = {
    'Inference':      { percent: 0.10, absolute: 30 },   // 10% or 30ms
    'Phonemization':  { percent: 0.10, absolute: 20 },   // 10% or 20ms
    'WASM Load':      { percent: 0.05, absolute: 50 },   // 5% or 50ms
    'Dict Load':      { percent: 0.05, absolute: 100 },  // 5% or 100ms
    'Model Load':     { percent: 0.05, absolute: 150 },  // 5% or 150ms
  };
  static DEFAULT_THRESHOLD = { percent: 0.05, absolute: 50 };

  detect(baseline, current) {
    const regressions = [];
    for (const [metric, base] of Object.entries(baseline)) {
      const delta = current[metric] - base;
      const config = RegressionDetector.THRESHOLDS[metric]
        || RegressionDetector.DEFAULT_THRESHOLD;
      const threshold = Math.max(base * config.percent, config.absolute);
      if (delta > threshold) {
        regressions.push({
          metric, delta, base, threshold,
          severity: delta / base > 0.2 ? 'critical' : 'high'
        });
      }
    }
    return regressions;
  }
}
```

---

## 12. 実装ロードマップ

### Phase間の依存関係

```
Phase 1: 基盤構築 (独立)
    │
    ├──→ Phase 2a: AudioWorklet (Phase 1 のORT更新確認後)
    │       │
    │       └──→ Phase 3: ストリーミング (AudioWorkletの再生ロジックに依存)
    │
    ├──→ Phase 2b: WebGPU (Phase 1 のORT更新確認後)
    │
    ├──→ Phase 4: モバイル最適化 (PWAはPhase 1のIndexedDBに依存、UIは独立)
    │       │
    │       └── FP16量子化: Python側export_onnx.py修正が必要 (Web側だけでは不可)
    │
    └──→ Phase 5: 高度な最適化 (Phase 2の安定性確認後)
```

### チーム体制別スケジュール

**シナリオA: 1人チーム**

| Phase | 期間 | 内容 |
|-------|------|------|
| Phase 1 | Week 1-2 | 基盤構築 |
| Phase 2a | Week 3-4 | AudioWorklet |
| Phase 2b | Week 5-6 | WebGPU |
| Phase 2c | Week 7 | 統合テスト |
| Phase 3 | Week 8-10 | ストリーミング & メモリ |
| Phase 4 | Week 11-13 | モバイル最適化 |
| Phase 5 | Week 14-16 | 高度な最適化 |
| **合計** | **16週** | |

**シナリオB: 2人チーム**

| Phase | 期間 | Frontend担当 | Backend担当 |
|-------|------|-------------|-------------|
| Phase 1 | Week 1-2 | ORT更新+BenchmarkRunner | IndexedDBキャッシュ |
| Phase 2 | Week 3-6 | AudioWorklet+WebGPU | モバイルUI+レスポンシブ |
| Phase 3 | Week 7-9 | ストリーミング | FP16量子化 (Python) |
| Phase 4-5 | Week 10-12 | 統合+高度な最適化 | PWA+Service Worker |
| **合計** | **12週** | | |

### Phase 1: 基盤構築 (Week 1-2)

- [ ] ONNX Runtime Web 1.19+ へ更新
- [ ] 1.17.1→1.19+ 互換性テスト（MOS/レイテンシ/メモリリーク）
- [ ] `executionProviders` をSIMD優先に変更
- [ ] IndexedDB キャッシュマネージャー実装（iOS 50MB制限対応）
- [ ] BenchmarkRunner 基盤実装

### Phase 2a: AudioWorklet (Week 3-4)

- [ ] AudioWorkletProcessor / AudioWorkletNode 実装
- [ ] SimpleResampler (22kHz→48kHz) 実装
- [ ] Factoryパターンでバックエンド自動選択 (AudioWorklet / ScriptProcessor / native audio)
- [ ] デスクトップブラウザテスト (Chrome/Firefox/Safari)

### Phase 2b: WebGPU (Week 5-6)

- [ ] WebGPUSessionManager 実装 (WebGPU → WASM-SIMD → WASM フォールバック)
- [ ] GPU容量チェック (maxBufferSize / maxStorageBufferBindingSize)
- [ ] モバイルGPUフォールバック自動判定

### Phase 2c: 統合テスト (Week 7)

- [ ] AudioWorklet + WebGPU 統合テスト
- [ ] クロスブラウザテストマトリックス実行

### Phase 3: ストリーミング & メモリ (Week 8-10)

- [ ] TextChunker (文分割エンジン) 実装
- [ ] StreamingTTSPipeline (並列パイプライン) 実装
- [ ] ChunkCrossfader (50msクロスフェード) 実装
- [ ] RingBuffer + TypedArrayPool (上限/TTL付き) 実装

### Phase 4: モバイル最適化 (Week 11-13)

- [ ] レスポンシブCSS (360px / 480px / 768px ブレークポイント)
- [ ] タッチUI最適化 (44pxタップターゲット)
- [ ] Python側: export_onnx.py に `--fp16` フラグ追加
- [ ] FP16モデル音質検証 (MOS測定、WavLMモデルとの相互作用確認)
- [ ] PWA対応 (manifest.json + Service Worker)
- [ ] iOS Safari / Android Chrome テスト

### Phase 5: 高度な最適化 (Week 14-16)

- [ ] SharedArrayBuffer + Atomics (COOP/COEP対応環境)
- [ ] coi-serviceworker によるGitHub Pages SAB対応
- [ ] マルチスピーカーUI
- [ ] パフォーマンスダッシュボード
- [ ] CI リグレッション検知

---

## 13. テスト計画

### ユニットテスト

| テスト対象 | 検証項目 |
|-----------|---------|
| AudioWorkletProcessor | チャンク処理、バッファアンダーラン、停止制御 |
| WebGPUSessionManager | フォールバック動作、GPU非対応時の挙動 |
| TypedArrayPool | 再利用率、上限超過時の破棄、TTLクリーンアップ |
| CacheManager | IndexedDB読み書き、バージョン管理、トランザクション完了 |
| SimpleResampler | 22kHz→48kHz変換精度、エッジケース |
| StreamingTTSPipeline | 並列実行、クロスフェード、リングバッファ |
| RegressionDetector | しきい値判定、メトリック別設定 |

### E2Eテスト (Playwright推奨)

**Phase 2完了時:**

| テスト項目 | Chrome 130+ | Firefox 141+ | Safari 18+ | Edge 130+ |
|-----------|-------------|-------------|------------|-----------|
| 日本語テキスト→音声出力 | ✅ | ✅ | ✅ | ✅ |
| 英語テキスト→音声出力 | ✅ | ✅ | ✅ | ✅ |
| AudioWorklet再生 | ✅ | ✅ | ⚠️ | ✅ |
| WebGPU推論 | ✅ | ⚠️ | ⚠️ | ✅ |
| ScriptProcessorフォールバック | ✅ | ✅ | ✅ | ✅ |

**Phase 4完了時 (モバイル):**

| テスト項目 | iOS Safari | Android Chrome |
|-----------|-----------|---------------|
| タッチUI操作 | ✅ | ✅ |
| メモリ使用量 (<300MB) | ✅ | ✅ |
| IndexedDBキャッシュ (<50MB) | ✅ | - |
| バックグラウンド再生 | ⚠️ | ✅ |

### パフォーマンスベースライン

```javascript
// Phase 1完了時の基準値
const baseline = {
  'WASM Load': 350,
  'Dict Load': 800,
  'Model Load': 600,
  'Phonemization': 85,
  'Inference': 1200     // WASM
};

// Phase 2完了時の目標値
const targets = {
  'Inference': 400,     // WebGPU
  'TTFB_cached': 700,   // キャッシュ有
};
```

---

## 付録: 関連ファイル

| 用途 | パス |
|------|------|
| メインデモ | `src/wasm/openjtalk-web/demo/index.html` |
| 統合API | `src/wasm/openjtalk-web/src/simple_unified_api.js` |
| 辞書ローダー | `src/wasm/openjtalk-web/src/dictionary-loader.js` |
| eSpeak Worker | `src/wasm/openjtalk-web/dist/espeak-ng/espeakng.worker.js` |
| 音声再生 (非推奨) | `src/wasm/openjtalk-web/dist/demo.js` |
| Emscriptenビルド | `src/wasm/openjtalk-web/build/build-production.sh` |
| Python推論 | `src/python/piper_train/infer_onnx.py` |
| ONNXエクスポート | `src/python/piper_train/export_onnx.py` |
| Docker WebUI | `docker/webui/app.py` |
