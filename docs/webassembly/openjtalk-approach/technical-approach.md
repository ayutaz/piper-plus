# WebAssembly OpenJTalk技術アプローチ

## 1. アーキテクチャ概要

### 1.1 全体構成
```
┌─────────────────────────────────────────┐
│         ブラウザ (Chrome/Edge)           │
├─────────────────────────────────────────┤
│          Web Application                │
│  ┌─────────────┐  ┌─────────────────┐  │
│  │   UI層      │  │  Web Worker     │  │
│  │  (React/Vue)│  │  (並列処理)     │  │
│  └──────┬──────┘  └────────┬────────┘  │
│         │                   │           │
│  ┌──────┴───────────────────┴────────┐  │
│  │        JavaScript API層           │  │
│  │  ┌─────────┐  ┌───────────────┐  │  │
│  │  │OpenJTalk │  │Piper ONNX     │  │  │
│  │  │Web API  │  │Runtime API    │  │  │
│  └──┴─────┬───┴──┴───────┬───────┴──┘  │
│           │              │             │
│  ┌────────┴──────┐  ┌───┴──────────┐  │
│  │OpenJTalk WASM │  │ONNX Runtime  │  │
│  │  (音素変換)   │  │Web (音声合成) │  │
│  └───────────────┘  └──────────────┘  │
└─────────────────────────────────────────┘
```

### 1.2 データフロー
```
[テキスト入力]
    ↓
[OpenJTalk WebAssembly]
    ├→ 形態素解析（MeCab）
    ├→ 読み推定
    └→ 音素変換
    ↓
[音素列]
    ↓
[Piper ONNX Runtime]
    ├→ 音響特徴生成
    └→ 波形生成（VITS）
    ↓
[音声データ (PCM)]
    ↓
[Web Audio API]
    └→ 音声再生
```

## 2. 技術スタック

### 2.1 コア技術
| レイヤー | 技術 | 役割 |
|---------|------|------|
| 音素変換 | OpenJTalk (C++) | 日本語解析・音素化 |
| WebAssembly化 | Emscripten 3.x | C++ → WASM変換 |
| 音声合成 | ONNX Runtime Web | VITSモデル実行 |
| 音声再生 | Web Audio API | PCM → 音声出力 |
| 並列処理 | Web Workers | UIブロッキング回避 |

### 2.2 補助技術
- **圧縮**: Brotli/Gzip（辞書圧縮）
- **キャッシュ**: IndexedDB（辞書保存）
- **CDN**: CloudFlare（アセット配信）
- **ビルド**: Docker（再現性確保）

## 3. 実装アプローチ詳細

### 3.1 OpenJTalk WebAssembly化

#### A. Emscripten設定
```javascript
// emcc コンパイルフラグ
const EMCC_FLAGS = [
  '-s', 'ENVIRONMENT=web,worker',
  '-s', 'MODULARIZE=1',
  '-s', 'EXPORT_ES6=1',
  '-s', 'EXPORTED_RUNTIME_METHODS=["FS","cwrap","ccall","setValue","getValue"]',
  '-s', 'EXPORTED_FUNCTIONS=["_malloc","_free","_openjtalk_initialize","_openjtalk_synthesis"]',
  '-s', 'INITIAL_MEMORY=256MB',
  '-s', 'ALLOW_MEMORY_GROWTH=1',
  '-s', 'MAXIMUM_MEMORY=512MB',
  '-s', 'FILESYSTEM=1',
  '-O3',
  '--closure', '1'
].join(' ');
```

#### B. C++ラッパー実装
```cpp
// openjtalk_wrapper.cpp
extern "C" {
  EMSCRIPTEN_KEEPALIVE
  int openjtalk_initialize(const char* dict_path, const char* voice_path) {
    // OpenJTalk初期化
    return initialize_openjtalk(dict_path, voice_path);
  }
  
  EMSCRIPTEN_KEEPALIVE
  char* openjtalk_text_to_phonemes(const char* text) {
    // テキスト→音素変換
    std::string phonemes = convert_to_phonemes(text);
    return strdup(phonemes.c_str());
  }
  
  EMSCRIPTEN_KEEPALIVE
  void openjtalk_free_string(char* str) {
    free(str);
  }
}
```

#### C. JavaScript API
```javascript
class OpenJTalkWeb {
  constructor() {
    this.module = null;
    this.initialized = false;
  }
  
  async initialize(config = {}) {
    // WebAssemblyモジュールのロード
    this.module = await OpenJTalkModule({
      locateFile: (path) => config.wasmPath || path
    });
    
    // 辞書ファイルのロード
    await this.loadDictionary(config.dictUrl);
    await this.loadVoice(config.voiceUrl);
    
    // OpenJTalk初期化
    const result = this.module.ccall(
      'openjtalk_initialize',
      'number',
      ['string', 'string'],
      ['/dict', '/voice.htsvoice']
    );
    
    this.initialized = (result === 0);
    return this.initialized;
  }
  
  async textToPhonemes(text) {
    if (!this.initialized) {
      throw new Error('OpenJTalk not initialized');
    }
    
    const ptr = this.module.ccall(
      'openjtalk_text_to_phonemes',
      'number',
      ['string'],
      [text]
    );
    
    const phonemes = this.module.UTF8ToString(ptr);
    this.module.ccall('openjtalk_free_string', null, ['number'], [ptr]);
    
    return phonemes;
  }
  
  async loadDictionary(url) {
    const response = await fetch(url);
    const data = await response.arrayBuffer();
    
    // Emscripten FSに書き込み
    this.module.FS.mkdir('/dict');
    const files = ['sys.dic', 'unk.dic', 'matrix.bin', 'char.bin'];
    // ... 辞書ファイルの展開と書き込み
  }
}
```

### 3.2 辞書最適化戦略

#### Phase 1: 基本圧縮（103MB → 50MB）
```javascript
// 1. 不要なデータの削除
- 使用頻度の低い品詞情報
- デバッグ情報
- 冗長なインデックス

// 2. バイナリ最適化
- 32bit → 16bit整数（可能な箇所）
- 文字列の共通部分抽出
```

#### Phase 2: 頻度ベース圧縮（50MB → 10MB）
```javascript
// 頻出5000語に限定
const frequentWords = analyzeCorpus(corpus)
  .sort((a, b) => b.frequency - a.frequency)
  .slice(0, 5000);

// カスタム辞書生成
generateCustomDictionary(frequentWords);
```

#### Phase 3: 配信最適化
```javascript
// Brotli圧縮 + チャンク分割
const chunks = splitDictionary(dictionary, CHUNK_SIZE);
const compressed = chunks.map(chunk => brotli.compress(chunk));

// Progressive Loading
async function loadDictionary() {
  // 基本辞書を最初にロード
  await loadChunk(0); // 最頻出1000語
  
  // 残りは非同期でロード
  Promise.all(chunks.slice(1).map(loadChunk));
}
```

### 3.3 メモリ管理

#### A. メモリプール実装
```javascript
class MemoryPool {
  constructor(size) {
    this.buffer = new ArrayBuffer(size);
    this.view = new DataView(this.buffer);
    this.offset = 0;
  }
  
  allocate(size) {
    if (this.offset + size > this.buffer.byteLength) {
      throw new Error('Out of memory');
    }
    const ptr = this.offset;
    this.offset += size;
    return ptr;
  }
  
  reset() {
    this.offset = 0;
  }
}
```

#### B. ガベージコレクション最適化
```javascript
// 明示的なメモリ解放
class ManagedOpenJTalk extends OpenJTalkWeb {
  async textToPhonemes(text) {
    const phonemes = await super.textToPhonemes(text);
    
    // 定期的にGCを促す
    if (++this.callCount % 100 === 0) {
      if (global.gc) global.gc();
    }
    
    return phonemes;
  }
}
```

### 3.4 Web Worker統合

#### A. Worker実装
```javascript
// openjtalk.worker.js
let openjtalk = null;

self.addEventListener('message', async (e) => {
  const { type, data, id } = e.data;
  
  try {
    switch (type) {
      case 'initialize':
        openjtalk = new OpenJTalkWeb();
        await openjtalk.initialize(data);
        self.postMessage({ type: 'initialized', id });
        break;
        
      case 'textToPhonemes':
        const phonemes = await openjtalk.textToPhonemes(data.text);
        self.postMessage({ type: 'phonemes', data: phonemes, id });
        break;
    }
  } catch (error) {
    self.postMessage({ type: 'error', error: error.message, id });
  }
});
```

#### B. メインスレッド側
```javascript
class OpenJTalkWorkerClient {
  constructor() {
    this.worker = new Worker('openjtalk.worker.js');
    this.promises = new Map();
    this.nextId = 0;
    
    this.worker.addEventListener('message', (e) => {
      const { id, type, data, error } = e.data;
      const promise = this.promises.get(id);
      
      if (promise) {
        if (error) {
          promise.reject(new Error(error));
        } else {
          promise.resolve(data);
        }
        this.promises.delete(id);
      }
    });
  }
  
  async textToPhonemes(text) {
    const id = this.nextId++;
    
    return new Promise((resolve, reject) => {
      this.promises.set(id, { resolve, reject });
      this.worker.postMessage({
        type: 'textToPhonemes',
        data: { text },
        id
      });
    });
  }
}
```

## 4. パフォーマンス最適化

### 4.1 WebAssembly Streaming
```javascript
async function loadWasmStreaming(url) {
  if (WebAssembly.instantiateStreaming) {
    const response = await fetch(url);
    return WebAssembly.instantiateStreaming(response);
  }
  // フォールバック
  const response = await fetch(url);
  const buffer = await response.arrayBuffer();
  return WebAssembly.instantiate(buffer);
}
```

### 4.2 SIMD活用
```javascript
// Emscriptenフラグ
'-msimd128',
'-s', 'SIMD=1'

// 実行時チェック
if (WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,5,1,96,0,1,123,3,2,1,0,7,8,1,4,116,101,115,116,0,0,10,15,1,13,0,65,0,253,15,253,98,11]))) {
  console.log('SIMD supported');
}
```

### 4.3 キャッシング戦略
```javascript
class CachedOpenJTalk extends OpenJTalkWeb {
  constructor() {
    super();
    this.cache = new Map();
    this.maxCacheSize = 1000;
  }
  
  async textToPhonemes(text) {
    // キャッシュチェック
    if (this.cache.has(text)) {
      return this.cache.get(text);
    }
    
    const phonemes = await super.textToPhonemes(text);
    
    // LRUキャッシュ
    if (this.cache.size >= this.maxCacheSize) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
    
    this.cache.set(text, phonemes);
    return phonemes;
  }
}
```

## 5. エラーハンドリング

### 5.1 初期化エラー
```javascript
class RobustOpenJTalk extends OpenJTalkWeb {
  async initialize(config) {
    try {
      await super.initialize(config);
    } catch (error) {
      // フォールバック辞書を試す
      if (error.message.includes('dictionary')) {
        console.warn('Failed to load full dictionary, trying minimal...');
        config.dictUrl = config.minimalDictUrl;
        await super.initialize(config);
      } else {
        throw error;
      }
    }
  }
}
```

### 5.2 メモリエラー
```javascript
// メモリ不足検知
if (performance.memory) {
  const usage = performance.memory.usedJSHeapSize / performance.memory.jsHeapSizeLimit;
  if (usage > 0.9) {
    console.warn('Memory usage high:', (usage * 100).toFixed(1) + '%');
    // キャッシュクリアなどの対策
  }
}
```

## 6. 統合例

### 完全な実装例
```javascript
// piper-web-tts.js
class PiperWebTTS {
  constructor() {
    this.openjtalk = null;
    this.onnxRuntime = null;
    this.audioContext = new AudioContext();
  }
  
  async initialize() {
    // OpenJTalk初期化
    this.openjtalk = new OpenJTalkWorkerClient();
    await this.openjtalk.initialize({
      dictUrl: 'https://cdn.example.com/dict.br',
      wasmUrl: 'https://cdn.example.com/openjtalk.wasm'
    });
    
    // ONNX Runtime初期化
    this.onnxRuntime = new PiperONNXRuntime();
    await this.onnxRuntime.loadModel('https://cdn.example.com/ja_speaker.onnx');
  }
  
  async synthesize(text) {
    // テキスト→音素
    const phonemes = await this.openjtalk.textToPhonemes(text);
    
    // 音素→音声
    const audioData = await this.onnxRuntime.synthesize(phonemes);
    
    // 音声再生
    const audioBuffer = await this.audioContext.decodeAudioData(audioData);
    const source = this.audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.audioContext.destination);
    source.start();
    
    return audioBuffer;
  }
}

// 使用例
const tts = new PiperWebTTS();
await tts.initialize();
await tts.synthesize('こんにちは、世界！');
```

---

最終更新: 2025-07-31