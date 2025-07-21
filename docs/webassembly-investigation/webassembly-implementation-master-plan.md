# Piper WebAssembly統合実装計画

最終更新: 2025-07-21

## 概要

このドキュメントは、piper-plusのWebAssembly対応における統合実装計画です。日本語TTSを最優先とし、Unity WebGLでの動作を前提としています。

## アーキテクチャ

### システム構成
```
┌─────────────────────────────────────────────────────────────┐
│                  ブラウザ / Unity WebGL                        │
├─────────────────────────────────────────────────────────────┤
│                  JavaScript/TypeScript API                     │
│                     (@piper-tts/wasm)                         │
├──────────────────┬────────────────┬──────────────────────────┤
│  音素化          │   音声合成      │     音声出力              │
│  ┌─────────────┐│ ┌─────────────┐│ ┌──────────────────┐  │
│  │   MeCab     ││ │ONNX Runtime ││ │  AudioWorklet    │  │
│  │  OpenJTalk  ││ │    Web      ││ │   Web Audio API  │  │
│  └─────────────┘│ └─────────────┘│ └──────────────────┘  │
├──────────────────┴────────────────┴──────────────────────────┤
│                    WebAssembly Runtime                         │
└─────────────────────────────────────────────────────────────┘
```

### ディレクトリ構造
```
piper-wasm/
├── src/
│   ├── cpp/              # C++実装
│   │   ├── mecab/        # MeCab WebAssembly移植
│   │   ├── openjtalk/    # OpenJTalk WebAssembly移植
│   │   └── bindings/     # JavaScript バインディング
│   ├── js/               # JavaScript/TypeScript API
│   │   ├── src/
│   │   │   ├── PiperTTS.ts
│   │   │   ├── phonemizer/
│   │   │   └── workers/
│   │   └── dist/         # ビルド成果物
│   └── unity/            # Unity WebGL統合
│       ├── PiperWebGL.jslib
│       └── PiperWebGLBridge.cs
├── dict/                 # 辞書データ
│   ├── minimal/          # 2-3MB
│   ├── standard/         # 5MB
│   └── full/             # 10MB
└── models/               # ONNXモデル
```

## 実装フェーズ

### Phase 0: 技術検証（1週間）

#### 目標
- OpenJTalk WebAssembly移植の実現性確認
- 最小辞書での動作検証
- Unity WebGLメモリ制限の確認

#### 成果物
- 技術検証レポート
- プロトタイプ実装（1000語辞書）
- メモリ使用量測定結果

### Phase 1: 日本語音素化基盤（3-4週間）

#### 1.1 MeCab WebAssembly移植
```bash
# ビルド設定
emcc -O3 \
  -s WASM=1 \
  -s MODULARIZE=1 \
  -s EXPORT_ES6=1 \
  -s EXPORTED_FUNCTIONS="['_mecab_new', '_mecab_sparse_tostr', '_mecab_destroy']" \
  -s INITIAL_MEMORY=32MB \
  -s ALLOW_MEMORY_GROWTH=1 \
  mecab_src.cpp -o mecab.js
```

#### 1.2 OpenJTalk統合
```c++
// openjtalk_wrapper.cpp
extern "C" {
    EMSCRIPTEN_KEEPALIVE
    char* text_to_phonemes(const char* text) {
        OpenJTalk* oj = openjtalk_initialize();
        openjtalk_load_dictionary(oj, "/dict/minimal");
        
        char* phonemes = openjtalk_synthesize_phonemes(oj, text);
        openjtalk_clear(oj);
        
        return phonemes;
    }
}
```

#### 1.3 PUAマッピング実装
```typescript
// 多文字音素を単一文字にマッピング
const PUA_MAPPING: Record<string, string> = {
    'ky': '\ue000', 'sy': '\ue001', 'ty': '\ue002',
    'ny': '\ue003', 'hy': '\ue004', 'ry': '\ue005',
    'gy': '\ue006', 'zy': '\ue007', 'by': '\ue008',
    'py': '\ue009', 'my': '\ue00a', 'dy': '\ue00b',
    'ch': '\ue00e', 'ts': '\ue00f', 'sh': '\ue010'
};
```

### Phase 2: ONNX Runtime統合（2週間）

#### 2.1 音声合成実装
```typescript
export class VoiceSynthesizer {
    private session: ort.InferenceSession;
    
    async initialize(modelPath: string) {
        const options: ort.InferenceSession.SessionOptions = {
            executionProviders: ['webgpu', 'wasm'],
            graphOptimizationLevel: 'all'
        };
        
        this.session = await ort.InferenceSession.create(modelPath, options);
    }
    
    async synthesize(phonemeIds: number[]): Promise<Float32Array> {
        const inputTensor = new ort.Tensor(
            'int64', 
            phonemeIds, 
            [1, phonemeIds.length]
        );
        
        const results = await this.session.run({ 'input': inputTensor });
        return results.audio.data as Float32Array;
    }
}
```

### Phase 3: 最適化とブラウザ統合（2週間）

#### 3.1 Web Worker実装
```typescript
// synthesis.worker.ts
class SynthesisWorker {
    private piper: PiperTTS;
    
    async onMessage(event: MessageEvent) {
        const { id, text, options } = event.data;
        
        try {
            const audio = await this.piper.synthesize(text, options);
            
            // Transferable objectsで効率的な転送
            self.postMessage({
                id,
                audio: audio.buffer
            }, [audio.buffer]);
        } catch (error) {
            self.postMessage({ id, error: error.message });
        }
    }
}
```

#### 3.2 メモリ最適化
```javascript
class MemoryOptimizer {
    private pool: ArrayBuffer[] = [];
    
    allocate(size: number): ArrayBuffer {
        // メモリプールから再利用
        const buffer = this.pool.find(b => b.byteLength >= size);
        if (buffer) {
            this.pool = this.pool.filter(b => b !== buffer);
            return buffer;
        }
        
        return new ArrayBuffer(size);
    }
    
    free(buffer: ArrayBuffer) {
        if (this.pool.length < 10) {
            this.pool.push(buffer);
        }
    }
}
```

### Phase 4: Unity WebGL統合（1-2週間）

#### 4.1 JavaScript Bridge (.jslib)
```javascript
var PiperWebGLPlugin = {
    PiperWebGL_Initialize: function(modelPathPtr, dictPathPtr, callbackPtr) {
        var modelPath = UTF8ToString(modelPathPtr);
        var dictPath = UTF8ToString(dictPathPtr);
        
        PiperWASM().then(function(module) {
            PiperState.module = module;
            module._initialize_openjtalk(dictPath);
            
            return initializeONNXRuntime(modelPath);
        }).then(function() {
            Module.dynCall_vi(callbackPtr, 1); // 成功
        });
    },
    
    PiperWebGL_Synthesize: function(textPtr, callbackPtr) {
        var text = UTF8ToString(textPtr);
        
        synthesizeJapanese(text).then(function(audioData) {
            var bufferPtr = _malloc(audioData.length * 4);
            HEAPF32.set(audioData, bufferPtr / 4);
            
            Module.dynCall_viii(callbackPtr, bufferPtr, audioData.length, 22050);
        });
    }
};

mergeInto(LibraryManager.library, PiperWebGLPlugin);
```

#### 4.2 C#インターフェース
```csharp
public class PiperWebGLInterface : IPiperTTS {
    #if UNITY_WEBGL && !UNITY_EDITOR
    [DllImport("__Internal")]
    private static extern void PiperWebGL_Initialize(
        string modelPath, string dictPath, Action<int> callback);
    
    [DllImport("__Internal")]
    private static extern void PiperWebGL_Synthesize(
        string text, Action<IntPtr, int, int> callback);
    #endif
    
    public async Task<AudioClip> GenerateAudioAsync(string text) {
        var tcs = new TaskCompletionSource<AudioClip>();
        
        PiperWebGL_Synthesize(text, OnAudioGenerated);
        
        void OnAudioGenerated(IntPtr dataPtr, int length, int sampleRate) {
            float[] audioData = new float[length];
            Marshal.Copy(dataPtr, audioData, 0, length);
            
            AudioClip clip = AudioClip.Create("TTS_Output", length, 1, sampleRate, false);
            clip.SetData(audioData, 0);
            tcs.SetResult(clip);
        }
        
        return await tcs.Task;
    }
}
```

### Phase 5: テストとドキュメント（2週間）

#### 5.1 自動テスト
- ユニットテスト（Jest）
- E2Eテスト（Playwright）
- パフォーマンステスト
- Unity WebGLフレームレートテスト

#### 5.2 デモアプリケーション
- Webデモページ
- Unity WebGLサンプル
- npmパッケージ公開準備

## 辞書最適化戦略（段階的アプローチ）

### Phase 1: 10MB辞書
- 基本語彙10,000語
- 教育漢字1,000字
- 圧縮率60%

### Phase 2: 5MB辞書
- 最頻出5,000語
- 必須漢字500字
- 圧縮率70%

### Phase 3: 2-3MB辞書
- コア語彙3,000語
- 最小漢字セット
- 圧縮率80%+

## パフォーマンス目標

| 指標 | Phase 1 | Phase 2 | Phase 3 |
|------|---------|---------|---------|
| 辞書サイズ | 10MB | 5MB | 2-3MB |
| 初期化時間 | < 5秒 | < 3秒 | < 2秒 |
| 音声生成遅延 | < 500ms | < 400ms | < 300ms |
| メモリ使用量 | < 200MB | < 150MB | < 100MB |
| フレームレート | 30fps+ | 45fps+ | 60fps |

## リスク管理

| リスク | 影響度 | 対策 |
|--------|--------|------|
| OpenJTalk移植の複雑さ | 高 | Phase 0で早期検証、既存実装の調査 |
| 辞書サイズ目標未達 | 中 | 段階的アプローチ、品質とのトレードオフ |
| Unity WebGLメモリ超過 | 高 | プロファイリング、積極的GC、キャッシング |
| ブラウザ互換性 | 中 | フォールバック実装、Progressive Enhancement |

## 成果物

1. **npmパッケージ**: `@piper-tts/wasm`
2. **Unity Package**: `com.piper-tts.webgl`
3. **ドキュメント**: API仕様、統合ガイド、トラブルシューティング
4. **デモ**: オンラインデモ、サンプルプロジェクト

---

このマスタープランは、以前の複数の実装計画を統合し、最新の改訂内容を反映しています。