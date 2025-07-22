# WebAssembly パフォーマンス最適化ガイド

## 概要

Piper WebAssembly版のパフォーマンスを最大化するための最適化手法とベストプラクティスを説明します。

## 1. SIMD (Single Instruction, Multiple Data) 最適化

### 有効化方法

SIMDは既にビルド時に有効化されています（`-msimd128`フラグ）。

```javascript
// SIMD サポートの確認
async function checkSIMDSupport() {
  try {
    const simdTest = new Uint8Array([
      0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
      0x01, 0x05, 0x01, 0x60, 0x00, 0x01, 0x7b, 0x03,
      0x02, 0x01, 0x00, 0x0a, 0x0a, 0x01, 0x08, 0x00,
      0x41, 0x00, 0xfd, 0x0f, 0x0b
    ]);
    await WebAssembly.instantiate(simdTest);
    return true;
  } catch (e) {
    return false;
  }
}
```

### パフォーマンス向上

- ベクトル演算により音声処理が最大**4倍高速化**
- 特に効果的な処理：
  - 音声波形の正規化
  - FFT/IFFT演算
  - 行列積計算

### ブラウザサポート

| ブラウザ | 最小バージョン | 備考 |
|---------|--------------|------|
| Chrome | 91+ | 完全サポート |
| Firefox | 89+ | 完全サポート |
| Safari | 16.4+ | 部分サポート |
| Edge | 91+ | 完全サポート |

## 2. WebGL/WebGPU バックエンド最適化

### WebGL バックエンドの使用

```javascript
import { PiperONNXRuntime } from './onnx/dist/index.js';

// WebGL優先で初期化
const runtime = new PiperONNXRuntime({
  preferredBackend: 'webgl',
  powerPreference: 'high-performance'
});

await runtime.initialize('/models/ja_JP-test-medium.onnx');
```

### WebGPU バックエンド（実験的）

```javascript
// WebGPU優先（Chrome 113+）
const runtime = new PiperONNXRuntime({
  preferredBackend: 'webgpu',
  enableProfiling: true
});
```

### バックエンド選択の推奨事項

1. **デスクトップ（高性能）**: WebGPU > WebGL > WASM+SIMD
2. **モバイル（省電力）**: WASM+SIMD > WebGL
3. **互換性重視**: WASM（全ブラウザ対応）

## 3. メモリ最適化

### 初期メモリ設定

```cmake
# CMakeLists.txt での設定
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s INITIAL_MEMORY=64MB")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s MAXIMUM_MEMORY=512MB")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s ALLOW_MEMORY_GROWTH=1")
```

### JavaScript側のメモリ管理

```javascript
// メモリ使用量の監視
function monitorMemory() {
  if (performance.memory) {
    const used = performance.memory.usedJSHeapSize / 1024 / 1024;
    const total = performance.memory.totalJSHeapSize / 1024 / 1024;
    console.log(`Memory: ${used.toFixed(2)}MB / ${total.toFixed(2)}MB`);
  }
}

// 不要なリソースの解放
runtime.dispose();
```

### ストリーミング処理でのメモリ効率化

```javascript
// チャンク単位で処理してメモリ使用量を抑制
const result = await runtime.streamSynthesize(phonemeIds, {
  chunkSize: 50,        // 小さいチャンクサイズ
  bufferAhead: 2,       // バッファリング数を制限
  enableMemoryPool: true // メモリプール使用
});
```

## 4. 並列処理とワーカー

### Web Workers の活用

```javascript
// worker.js
importScripts('/mecab/build/mecab_wasm.js');

let mecabModule = null;

self.onmessage = async (e) => {
  if (!mecabModule) {
    mecabModule = await MeCabModule();
  }
  
  const result = mecabModule.tokenize(e.data.text);
  self.postMessage({ result });
};

// main.js
const worker = new Worker('worker.js');
worker.postMessage({ text: 'こんにちは世界' });
```

### SharedArrayBuffer の使用（要COOP/COEP）

```javascript
// サーバー設定が必要
// Cross-Origin-Embedder-Policy: require-corp
// Cross-Origin-Opener-Policy: same-origin

if (typeof SharedArrayBuffer !== 'undefined') {
  const sab = new SharedArrayBuffer(1024 * 1024); // 1MB
  // 複数ワーカー間でメモリ共有
}
```

## 5. ロード時間の最適化

### 分割ロード

```javascript
// 必要なモジュールのみを遅延ロード
async function loadModules() {
  // 基本モジュール
  const mecab = await import('./mecab/build/mecab_wasm.js');
  
  // 必要に応じてロード
  if (needsOpenJTalk) {
    const openjtalk = await import('./openjtalk/build/openjtalk.js');
  }
}
```

### キャッシュ戦略

```javascript
// Service Worker でのキャッシュ
self.addEventListener('fetch', (event) => {
  if (event.request.url.includes('.wasm') || 
      event.request.url.includes('.onnx')) {
    event.respondWith(
      caches.match(event.request).then(response => {
        return response || fetch(event.request).then(response => {
          return caches.open('piper-v1').then(cache => {
            cache.put(event.request, response.clone());
            return response;
          });
        });
      })
    );
  }
});
```

## 6. ベンチマークツールの使用

```bash
# ローカルサーバーを起動
cd src/wasm
python3 test/server.py

# ブラウザで開く
open http://localhost:8000/test/benchmark.html
```

### ベンチマーク設定

- **反復回数**: 10-20回（統計的に有意）
- **テキスト長**: 短文、中文、長文で比較
- **バックエンド**: CPU vs WebGL vs WebGPU

### パフォーマンス指標

1. **総合処理時間**: エンドツーエンドの時間
2. **RTF (Real-Time Factor)**: 1.0以下が理想
3. **メモリ使用量**: ピーク使用量を監視
4. **各段階の処理時間**:
   - MeCab: 10-50ms
   - OpenJTalk: 20-100ms
   - ONNX推論: 100-500ms
   - 音声生成: 10-50ms

## 7. 最適化チェックリスト

- [ ] SIMD が有効になっているか確認
- [ ] 適切なバックエンドを選択
- [ ] メモリ使用量を監視
- [ ] 不要なリソースを解放
- [ ] キャッシュを活用
- [ ] ストリーミング処理を検討
- [ ] Web Workers で並列化
- [ ] ベンチマークで効果を測定

## 8. トラブルシューティング

### パフォーマンスが悪い場合

1. **Chrome DevTools** でプロファイリング
2. `performance.measure()` で各処理を計測
3. メモリリークをチェック
4. ネットワークタブでロード時間確認

### メモリ不足エラー

1. チャンクサイズを小さくする
2. 同時処理数を制限
3. `MAXIMUM_MEMORY` を増やす（再ビルド必要）

### SIMD が使えない場合

1. ブラウザバージョンを確認
2. フォールバック実装を用意
3. ユーザーに通知

## 9. 将来の最適化

- **WebNN API**: ネイティブML推論（開発中）
- **WebCodecs**: 音声エンコード最適化
- **Wasm Threads**: 真の並列処理
- **Memory64**: 4GB以上のメモリサポート