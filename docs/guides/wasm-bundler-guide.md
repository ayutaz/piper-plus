# WASM バンドラー設定ガイド

piper-plus の npm パッケージをバンドラーと組み合わせて使う方法を説明します。

---

## 前提条件

```bash
npm install piper-plus onnxruntime-web
```

## Vite

### vite.config.js

```js
import { defineConfig } from "vite";

export default defineConfig({
  optimizeDeps: {
    exclude: ["onnxruntime-web"],
  },
  build: {
    target: "esnext",
  },
});
```

### WASM ファイルの配置

onnxruntime-web の WASM ファイルを public/ にコピーします:

```bash
cp node_modules/onnxruntime-web/dist/*.wasm public/
```

### 使用例

```js
import { PiperPlus } from "piper-plus";

const piper = await PiperPlus.initialize("tsukuyomi");
const audio = await piper.synthesize("こんにちは");
audio.play();
```

## webpack

### webpack.config.js

```js
const CopyPlugin = require("copy-webpack-plugin");

module.exports = {
  experiments: {
    asyncWebAssembly: true,
  },
  plugins: [
    new CopyPlugin({
      patterns: [
        {
          from: "node_modules/onnxruntime-web/dist/*.wasm",
          to: "[name][ext]",
        },
      ],
    }),
  ],
};
```

## Next.js

```js
// next.config.js
const nextConfig = {
  webpack: (config) => {
    config.experiments = { ...config.experiments, asyncWebAssembly: true };
    return config;
  },
};
module.exports = nextConfig;
```

WASM ファイルは `public/` ディレクトリにコピーしてください。

## トラブルシューティング

### WASM ファイルが見つからない

ONNX Runtime Web の `.wasm` ファイルがサーバーから配信可能な場所にあることを確認してください。
バンドラーによっては WASM ファイルを自動的にコピーしません。

### CORS エラー

ローカル開発時は `file://` プロトコルではなく、ローカルサーバー (`vite dev`, `webpack serve`) を使用してください。

### SharedArrayBuffer エラー

ONNX Runtime Web のマルチスレッド版は `SharedArrayBuffer` が必要です。以下のヘッダーをサーバーに設定してください:

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Vite では `vite-plugin-cross-origin-isolation` プラグインが利用できます。
