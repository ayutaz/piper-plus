# ブラウザ互換性ガイド

## 対応ブラウザ一覧

### 完全対応（推奨）

| ブラウザ | 最小バージョン | 備考 |
|---------|---------------|------|
| Google Chrome | 91+ | SIMD, WebGL, WebGPU対応 |
| Microsoft Edge | 91+ | Chromiumベース |
| Brave | 1.36+ | Chromiumベース |

### 部分対応

| ブラウザ | 最小バージョン | 制限事項 |
|---------|---------------|----------|
| Firefox | 89+ | WebGPU未対応、SAB要設定 |
| Safari | 15.4+ | WebGPU未対応、音声要ユーザー操作 |
| Opera | 77+ | Chromiumベース |

### 非対応

- Internet Explorer（全バージョン）
- 古いバージョンのブラウザ
- 一部のモバイルブラウザ

## 機能別サポート状況

### WebAssembly機能

| 機能 | Chrome | Firefox | Safari | Edge |
|------|--------|---------|--------|------|
| 基本WASM | ✅ | ✅ | ✅ | ✅ |
| SIMD | ✅ 91+ | ✅ 89+ | ⚠️ 16.4+ | ✅ 91+ |
| Threads | ✅* | ✅* | ❌ | ✅* |
| Memory64 | 🚧 | 🚧 | ❌ | 🚧 |

*要COOP/COEPヘッダー

### Web API サポート

| API | Chrome | Firefox | Safari | Edge |
|-----|--------|---------|--------|------|
| Web Audio | ✅ | ✅ | ✅** | ✅ |
| WebGL 2.0 | ✅ | ✅ | ✅ | ✅ |
| WebGPU | ✅ 113+ | ❌ | ❌ | ✅ 113+ |
| SharedArrayBuffer | ✅* | ✅* | ✅* | ✅* |

**Safari は音声再生にユーザー操作が必要

## ブラウザ別設定ガイド

### Chrome/Edge

最適なパフォーマンスを得るための設定：

```javascript
// 推奨設定
const runtime = new PiperONNXRuntime({
  preferredBackend: 'webgpu', // または 'webgl'
  enableProfiling: false,
  powerPreference: 'high-performance'
});
```

起動フラグ（開発時）：
```bash
# Chrome
google-chrome --enable-features=SharedArrayBuffer \
              --enable-unsafe-webgpu \
              --disable-web-security

# Edge
msedge --enable-features=SharedArrayBuffer
```

### Firefox

必要な設定とフラグ：

```javascript
// Firefox用設定
const runtime = new PiperONNXRuntime({
  preferredBackend: 'wasm', // WebGLも可
  numThreads: 1 // SAB無効時
});
```

about:config 設定：
- `dom.postMessage.sharedArrayBuffer.bypassCOOP_COEP.insecure.enabled`: true
- `javascript.options.wasm_simd`: true
- `webgl.enable-webgl2`: true

### Safari

Safari特有の対応：

```javascript
// Safari用初期化
async function initForSafari() {
  // オーディオコンテキストの準備
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  let audioCtx = new AudioContext();
  
  // ユーザー操作後に再開
  document.addEventListener('click', async () => {
    if (audioCtx.state === 'suspended') {
      await audioCtx.resume();
    }
  }, { once: true });
  
  // 基本設定のみ使用
  const runtime = new PiperONNXRuntime({
    preferredBackend: 'wasm',
    enableProfiling: false
  });
  
  return runtime;
}
```

## セキュリティヘッダー設定

### 必須ヘッダー（SharedArrayBuffer使用時）

```nginx
# Nginx設定
add_header Cross-Origin-Embedder-Policy "require-corp";
add_header Cross-Origin-Opener-Policy "same-origin";
```

```javascript
// Express.js
app.use((req, res, next) => {
  res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
  res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  next();
});
```

### 開発サーバー設定

```python
# Python HTTPサーバー
class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        super().end_headers()
```

## 一般的な問題と解決策

### 1. SharedArrayBuffer が使えない

**症状**: `SharedArrayBuffer is not defined`

**解決策**:
- 必須ヘッダーを設定
- HTTPSを使用（localhost除く）
- ブラウザ設定を確認

### 2. WebAssembly.instantiateStreaming エラー

**症状**: `Failed to execute 'instantiateStreaming'`

**解決策**:
```javascript
// フォールバック実装
async function loadWasm(url) {
  try {
    return await WebAssembly.instantiateStreaming(fetch(url));
  } catch (e) {
    // フォールバック
    const response = await fetch(url);
    const buffer = await response.arrayBuffer();
    return await WebAssembly.instantiate(buffer);
  }
}
```

### 3. Safari で音声が再生されない

**症状**: AudioContext が 'suspended' 状態

**解決策**:
```javascript
// ユーザー操作をトリガーに
button.addEventListener('click', async () => {
  if (audioContext.state === 'suspended') {
    await audioContext.resume();
  }
  // 音声合成処理
});
```

### 4. メモリ不足エラー

**症状**: `Out of memory` または `RangeError`

**解決策**:
- ストリーミング処理を使用
- チャンクサイズを削減
- 不要なリソースを解放

## テスト方法

### 自動テストの実行

```bash
cd src/wasm/test/browser-compat
npm install
npm run install # Playwright ブラウザインストール
npm test        # 全ブラウザテスト
```

### 手動テスト

1. ローカルサーバー起動
   ```bash
   cd src/wasm
   python3 test/server.py
   ```

2. 各ブラウザでアクセス
   - http://localhost:8000/test/mecab-test.html
   - http://localhost:8000/test/full-tts-demo.html
   - http://localhost:8000/test/benchmark.html

### 互換性チェックリスト

- [ ] WebAssembly基本機能
- [ ] SIMD サポート
- [ ] Web Audio API
- [ ] 音声再生
- [ ] メモリ管理
- [ ] エラーハンドリング
- [ ] パフォーマンス

## ブラウザ検出とフォールバック

```javascript
function detectBrowserCapabilities() {
  const ua = navigator.userAgent;
  const capabilities = {
    browser: 'unknown',
    version: 0,
    features: {}
  };
  
  // ブラウザ検出
  if (ua.includes('Chrome')) {
    capabilities.browser = 'chrome';
    capabilities.version = parseInt(ua.match(/Chrome\/(\d+)/)?.[1] || '0');
  } else if (ua.includes('Firefox')) {
    capabilities.browser = 'firefox';
    capabilities.version = parseInt(ua.match(/Firefox\/(\d+)/)?.[1] || '0');
  } else if (ua.includes('Safari') && !ua.includes('Chrome')) {
    capabilities.browser = 'safari';
    capabilities.version = parseInt(ua.match(/Version\/(\d+)/)?.[1] || '0');
  }
  
  // 機能検出
  capabilities.features = {
    wasm: typeof WebAssembly !== 'undefined',
    simd: checkSIMDSupport(),
    sharedArrayBuffer: typeof SharedArrayBuffer !== 'undefined',
    webgl2: !!document.createElement('canvas').getContext('webgl2'),
    webgpu: 'gpu' in navigator
  };
  
  return capabilities;
}

// 最適な設定を選択
function getOptimalConfig(capabilities) {
  if (capabilities.browser === 'chrome' && capabilities.version >= 113) {
    return { preferredBackend: 'webgpu' };
  } else if (capabilities.features.webgl2) {
    return { preferredBackend: 'webgl' };
  } else {
    return { preferredBackend: 'wasm' };
  }
}
```

## まとめ

1. **Chrome/Edge 91+** が最適（全機能対応）
2. **Firefox 89+** は十分な性能（WebGPU以外）
3. **Safari 15.4+** は基本機能のみ（制限あり）
4. 適切なフォールバックを実装
5. ブラウザ固有の問題に対応
6. 定期的にテストを実行