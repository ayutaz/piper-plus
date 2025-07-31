# Piper-WASM 日本語TTS最小実装計画

## 既存実装の調査結果

### 利用可能な実装
1. **wasm_open_jtalk** (hrhr49) - 2021年、基本的な実装
2. **openjtalk-wasm** - TypeScript対応、ブラウザ向け
3. **node-openjtalk-binding** - 2024年6月更新、最新のC API

### 技術的発見
- Emscripten 2.0.14でビルド可能
- Node.js環境での動作確認済み
- 辞書データはファイルシステムエミュレーション使用

## Phase 1: 最小限の日本語音素化実装（2週間）

### Week 1: 環境構築とOpenJTalk移植

**Day 1-2: ビルド環境セットアップ**
```bash
# Emscripten最新版インストール
git clone https://github.com/emscripten-core/emsdk.git
cd emsdk
./emsdk install latest
./emsdk activate latest
source ./emsdk_env.sh

# piper-plusリポジトリ準備
cd /data/piper
mkdir -p src/wasm
cd src/wasm
```

**Day 3-5: OpenJTalk/MeCabコア移植**
```bash
# 最小構成でのビルド
git clone https://github.com/r9y9/open_jtalk.git
cd open_jtalk

# Emscripten用パッチ適用
emconfigure ./configure \
  --with-charset=utf-8 \
  --enable-utf8-only \
  --disable-shared \
  --prefix=$PWD/install

# ビルドフラグ最適化
export CFLAGS="-Os -s USE_ZLIB=1"
export CXXFLAGS="-Os -s USE_ZLIB=1"
emmake make
```

**Day 6-7: 辞書データ最小化**
```javascript
// 最小辞書セット（5-10MB目標）
const minimalDictFiles = [
  'char.bin',      // 文字定義
  'matrix.bin',    // 連接コスト（圧縮）
  'sys.dic',       // システム辞書（基本語彙のみ）
  'unk.dic'        // 未知語処理
];
```

### Week 2: Piper統合とAPI実装

**Day 8-10: C++バインディング**
```cpp
// src/wasm/openjtalk_wasm.cpp
#include <emscripten/bind.h>
#include "openjtalk.h"

class OpenJTalkWASM {
private:
    OpenJTalk* jtalk;
    
public:
    OpenJTalkWASM() {
        jtalk = new OpenJTalk();
        // 最小辞書ロード
        jtalk->load("/assets/dict-minimal");
    }
    
    std::string textToPhonemes(const std::string& text) {
        return jtalk->extractPhonemes(text);
    }
};

EMSCRIPTEN_BINDINGS(openjtalk_module) {
    emscripten::class_<OpenJTalkWASM>("OpenJTalkWASM")
        .constructor()
        .function("textToPhonemes", &OpenJTalkWASM::textToPhonemes);
}
```

**Day 11-12: JavaScript API**
```javascript
// src/wasm/piper-openjtalk.js
export class PiperOpenJTalk {
    constructor() {
        this.ready = false;
        this.module = null;
    }
    
    async initialize() {
        // 辞書の非同期ロード
        this.module = await import('./openjtalk_wasm.js');
        await this.module.ready;
        this.instance = new this.module.OpenJTalkWASM();
        this.ready = true;
    }
    
    textToPhonemes(text) {
        if (!this.ready) throw new Error('Not initialized');
        return this.instance.textToPhonemes(text);
    }
}
```

**Day 13-14: Piper統合テスト**
```javascript
// 統合テスト
import { PiperOpenJTalk } from './piper-openjtalk.js';
import { PiperTTS } from 'piper-wasm';

const openjtalk = new PiperOpenJTalk();
await openjtalk.initialize();

const piper = new PiperTTS();
await piper.loadModel('ja-model.onnx');

// 日本語テキスト→音素→音声
const phonemes = openjtalk.textToPhonemes('こんにちは');
const audio = await piper.synthesizePhonemes(phonemes);
```

## Phase 2: 音声合成統合（2週間）

### Week 3: ONNX Runtime Web統合

**Day 15-17: 音素→音声変換**
```javascript
// PUA音素マッピング対応
const puaMapping = {
    'a:': '\uE000', 'i:': '\uE001', 'u:': '\uE002',
    'cl': '\uE005', 'ch': '\uE00E', 'ts': '\uE00F'
    // ... 完全なマッピング
};

function mapPhonemesToPUA(phonemes) {
    return phonemes.replace(/([a-z]+:?)/g, (match) => {
        return puaMapping[match] || match;
    });
}
```

**Day 18-21: パフォーマンス最適化**
```javascript
// Web Worker実装
// worker.js
self.importScripts('openjtalk_wasm.js', 'piper_wasm.js');

let openjtalk, piper;

self.onmessage = async (e) => {
    if (e.data.cmd === 'init') {
        openjtalk = new OpenJTalkWASM();
        piper = new PiperTTS();
        await piper.loadModel(e.data.model);
        self.postMessage({ ready: true });
    } else if (e.data.cmd === 'synthesize') {
        const phonemes = openjtalk.textToPhonemes(e.data.text);
        const audio = await piper.synthesizePhonemes(phonemes);
        self.postMessage({ audio: audio.buffer }, [audio.buffer]);
    }
};
```

### Week 4: Unity WebGL対応準備

**Day 22-24: Unity Native Plugin化**
```c
// Unity WebGL用エクスポート
#ifdef __EMSCRIPTEN__
#include <emscripten.h>

EMSCRIPTEN_KEEPALIVE
const char* piper_wasm_text_to_phonemes(const char* text) {
    static std::string result;
    result = g_openjtalk->textToPhonemes(text);
    return result.c_str();
}

EMSCRIPTEN_KEEPALIVE
int piper_wasm_synthesize(const char* text, float** audio_buffer) {
    // 音声合成処理
    return audio_length;
}
#endif
```

**Day 25-28: 最終テストとドキュメント**
- ブラウザ互換性テスト
- メモリ使用量測定
- API ドキュメント作成

## ビルドコマンド

```bash
# 最適化ビルド
emcc -Os \
  -s WASM=1 \
  -s MODULARIZE=1 \
  -s EXPORT_ES6=1 \
  -s EXPORTED_RUNTIME_METHODS='["cwrap", "ccall"]' \
  -s ALLOW_MEMORY_GROWTH=1 \
  -s INITIAL_MEMORY=64MB \
  -s MAXIMUM_MEMORY=256MB \
  -s FILESYSTEM=1 \
  -s FORCE_FILESYSTEM=1 \
  --preload-file dict-minimal@/assets/dict-minimal \
  -o piper-openjtalk.js \
  openjtalk_wasm.cpp
```

## 成果物

1. **piper-openjtalk.js** - メインJavaScriptモジュール
2. **piper-openjtalk.wasm** - WebAssemblyバイナリ
3. **dict-minimal.data** - 最小辞書データ（5-10MB）
4. **デモページ** - ブラウザでの動作確認

## リスクと対策

| リスク | 対策 |
|--------|------|
| 辞書サイズが大きい | 段階的ロード、圧縮、キャッシュ |
| 初期化時間が長い | Web Worker、非同期初期化 |
| メモリ不足 | 動的メモリ管理、ストリーミング処理 |
| ブラウザ互換性 | Polyfill、フォールバック実装 |

## 次のステップ

1. **辞書最適化** - 専用の圧縮フォーマット開発
2. **ストリーミング対応** - リアルタイム音声合成
3. **ブラウザ統合** - Web Audio API活用
4. **性能向上** - SIMD、WebGPU活用