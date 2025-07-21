# 技術的制約事項分析

作成日: 2025-07-21

## 概要

WebAssembly実装における技術的制約と解決策をまとめます。

## 主要な技術的制約

### 1. メモリ制約

#### 問題点
- **ブラウザメモリ制限**: 
  - Chrome: 最大4GB（実質2GB程度）
  - Safari: より厳しい制限
  - Unity WebGL: 256MB〜512MB

- **辞書データサイズ**:
  - MeCab IPADIC: 約50MB
  - OpenJTalk辞書: 103MB（sys.dic: 99MB）
  - 合計: 150MB以上

#### 解決策
- 辞書の段階的ロード
- 頻度ベースの語彙選定
- 圧縮（Brotli/gzip）
- メモリプール実装

### 2. スレッド制約

#### 問題点
- **SharedArrayBuffer制限**:
  - Cross-Origin Isolation必須
  - 一部ブラウザで無効化
  - Unity WebGLはシングルスレッド

#### 解決策
- Web Worker活用（メインスレッド分離）
- 非同期処理の徹底
- AudioWorkletで音声処理

### 3. ファイルシステム制約

#### 問題点
- **仮想ファイルシステム**:
  - Emscripten FSは同期的
  - 大容量ファイルの扱いが困難
  - 永続化なし

#### 解決策
```javascript
// IndexedDBでの永続化
async function cacheDictionary(data) {
    const db = await openDB('piper-cache', 1);
    await db.put('dictionaries', data, 'openjtalk');
}

// 動的ロード
Module.preRun.push(() => {
    FS.mkdir('/dict');
    FS.mount(IDBFS, {}, '/dict');
    FS.syncfs(true, (err) => {
        if (!err) console.log('Dictionary loaded from cache');
    });
});
```

### 4. パフォーマンス制約

#### 問題点
- **初期化時間**:
  - 辞書ロード: 数秒
  - WASM初期化: 1-2秒
  - 合計: 5秒以上の可能性

#### 解決策
- プログレッシブ初期化
- Service Workerでキャッシュ
- WebAssembly.instantiateStreaming使用

### 5. API制約

#### 問題点
- **C++ API → JavaScript**:
  - 文字列の受け渡しが非効率
  - ポインタ管理が複雑
  - メモリリーク risk

#### 解決策
```cpp
// Embindで安全なバインディング
EMSCRIPTEN_BINDINGS(piper_module) {
    emscripten::class_<PiperTTS>("PiperTTS")
        .constructor<>()
        .function("initialize", &PiperTTS::initialize)
        .function("synthesize", &PiperTTS::synthesize,
            emscripten::return_value_policy::take_ownership());
}
```

## ブラウザ別制約

### Chrome (PC版)
- ✅ SharedArrayBuffer対応
- ✅ WebGPU対応
- ✅ 大容量メモリ
- ⚠️ CORS/COOP/COEP必須

### Safari
- ❌ WebGPU未対応
- ⚠️ SharedArrayBuffer制限
- ⚠️ メモリ制限厳しい
- ⚠️ WASM最適化が弱い

### Firefox
- ✅ SharedArrayBuffer対応
- ❌ WebGPU未対応
- ⚠️ パフォーマンスばらつき

## Unity WebGL固有の制約

### メモリ管理
```csharp
// Unity側の制約
WebGLMemoryStats.GetTotalMemorySize(); // 256MB default
```

### JavaScript Bridge制限
- 文字列は最大1MB
- 配列は分割送信必要
- 同期呼び出し不可

### 解決策
```javascript
// .jslib での分割処理
PiperWebGL_SynthesizeLarge: function(textPtr, chunkSize) {
    var text = UTF8ToString(textPtr);
    var chunks = [];
    
    // 分割処理
    for (var i = 0; i < text.length; i += chunkSize) {
        chunks.push(text.slice(i, i + chunkSize));
    }
    
    // 各チャンクを処理
    return processChunks(chunks);
}
```

## セキュリティ制約

### Cross-Origin Isolation
```html
<!-- 必須ヘッダー -->
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Opener-Policy: same-origin
```

### Content Security Policy
```html
<!-- WASMとWorker許可 -->
<meta http-equiv="Content-Security-Policy" 
      content="script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'">
```

## 回避策まとめ

### 1. Chrome PC限定で開発
- 最新機能フル活用
- 制約最小限
- 最高パフォーマンス

### 2. 段階的実装
1. 最小辞書で動作確認
2. 機能を徐々に追加
3. 最適化は最後

### 3. フォールバック戦略
```javascript
// 機能検出
const features = {
    webgpu: 'gpu' in navigator,
    sharedArrayBuffer: typeof SharedArrayBuffer !== 'undefined',
    webWorker: typeof Worker !== 'undefined',
    audioWorklet: 'audioWorklet' in AudioContext.prototype
};

// 最適な実装を選択
if (features.webgpu) {
    return new WebGPUBackend();
} else if (features.sharedArrayBuffer) {
    return new WASMBackend();
} else {
    return new FallbackBackend();
}
```

## リスク評価

| 制約 | 影響度 | Chrome対応 | 回避策 |
|-----|--------|-----------|--------|
| メモリ制限 | 高 | ✅ 余裕 | 辞書圧縮 |
| SharedArrayBuffer | 中 | ✅ 対応 | Worker分離 |
| WebGPU | 低 | ✅ 対応 | WASM fallback |
| 初期化時間 | 中 | - | プログレッシブ |
| Unity統合 | 高 | - | メモリ最適化 |

## 結論

Chrome PC限定とすることで、ほとんどの技術的制約を回避可能です。主な課題は：

1. **辞書サイズ**: 圧縮と選定で対応
2. **Unity WebGLメモリ**: 段階的ロードで対応
3. **初期化時間**: キャッシュとプログレッシブロードで対応

これらの制約を考慮した実装により、実用的なWebAssembly版piper-plusの実現が可能です。