# Piper WebAssembly 実装

ブラウザ上で動作する日本語テキスト音声合成（TTS）システムの WebAssembly 実装です。

## 🌐 デモサイト

https://ayutaz.github.io/piper-plus/

## 📋 目次

- [概要](#概要)
- [機能](#機能)
- [ブラウザ対応](#ブラウザ対応)
- [セットアップ](#セットアップ)
- [使用方法](#使用方法)
- [パフォーマンス最適化](#パフォーマンス最適化)
- [開発](#開発)
- [トラブルシューティング](#トラブルシューティング)

## 概要

Piper WebAssembly は、以下のコンポーネントで構成されています：

1. **MeCab WebAssembly** - 日本語形態素解析
2. **OpenJTalk WebAssembly** - 日本語音素変換
3. **ONNX Runtime Web** - ニューラルネットワーク推論
4. **ストリーミング合成** - リアルタイム音声生成

## 機能

### ✅ 実装済み機能

- 日本語テキストから音声への変換
- ブラウザ内での完全な処理（サーバー不要）
- ストリーミング音声合成
- WebGL/WebGPU アクセラレーション
- SIMD 最適化
- 複数話者対応
- リアルタイムファクター < 1.0

### 🚧 開発中機能

- Web Workers による並列処理
- プログレッシブ Web アプリ（PWA）対応
- 音声パラメータのリアルタイム調整

## ブラウザ対応

### 推奨ブラウザ

| ブラウザ | バージョン | 状態 |
|---------|-----------|------|
| Chrome | 91+ | ✅ 完全対応 |
| Edge | 91+ | ✅ 完全対応 |
| Firefox | 89+ | ✅ 対応（WebGPU除く） |
| Safari | 15.4+ | ⚠️ 部分対応 |

詳細は[ブラウザ互換性ガイド](browser-compatibility.md)を参照してください。

## セットアップ

### 前提条件

- Node.js 18+
- Emscripten 3.1.61+
- CMake 3.15+
- Python 3.8+

### ビルド手順

```bash
# リポジトリのクローン
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus/src/wasm

# 依存関係のインストール
cd mecab && npm ci && cd ..
cd openjtalk && npm ci && cd ..
cd onnx && npm ci && cd ..

# WebAssembly モジュールのビルド
cd mecab && npm run build:wasm && npm run build && cd ..
cd openjtalk && ./build.sh && npm run build && cd ..
cd onnx && npm run build && cd ..

# テストサーバーの起動
python3 test/server.py
```

ブラウザで http://localhost:8000/test/ にアクセスしてデモを確認できます。

## 使用方法

### 基本的な使い方

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Piper WebAssembly TTS</title>
</head>
<body>
    <textarea id="text">こんにちは世界</textarea>
    <button id="synthesize">音声合成</button>
    <audio id="audio" controls></audio>

    <script type="module">
        import { PiperWebTTS } from './dist/piper-web-tts.js';
        
        const tts = new PiperWebTTS();
        await tts.initialize({
            modelPath: '/models/ja_JP-test-medium.onnx',
            preferredBackend: 'webgl' // 'wasm', 'webgl', 'webgpu'
        });
        
        document.getElementById('synthesize').onclick = async () => {
            const text = document.getElementById('text').value;
            const audio = await tts.synthesize(text);
            
            document.getElementById('audio').src = audio.url;
        };
    </script>
</body>
</html>
```

### ストリーミング合成

```javascript
// ストリーミング音声合成
const stream = await tts.streamingSynthesize(text, {
    chunkSize: 50,
    onChunk: (audioChunk) => {
        // リアルタイムで音声チャンクを処理
        player.appendBuffer(audioChunk);
    }
});
```

### 高度な設定

```javascript
const tts = new PiperWebTTS({
    // パフォーマンス設定
    preferredBackend: 'webgpu',
    enableSIMD: true,
    numThreads: 4,
    
    // メモリ設定
    initialMemory: 64 * 1024 * 1024, // 64MB
    maximumMemory: 512 * 1024 * 1024, // 512MB
    
    // 音声設定
    speakerId: 0,
    lengthScale: 1.0,
    noiseScale: 0.667,
    noiseW: 0.8
});
```

## パフォーマンス最適化

### ベンチマークツール

パフォーマンスを測定するには：

```bash
# ベンチマークページを開く
open http://localhost:8000/test/benchmark.html
```

### 最適化のヒント

1. **SIMD を有効化**（Chrome 91+, Firefox 89+）
2. **WebGL バックエンドを使用**（GPU アクセラレーション）
3. **ストリーミング処理**でメモリ使用量を削減
4. **Service Worker** でリソースをキャッシュ

詳細は[パフォーマンス最適化ガイド](performance-optimization.md)を参照してください。

## 開発

### ディレクトリ構造

```
src/wasm/
├── mecab/          # MeCab WebAssembly モジュール
├── openjtalk/      # OpenJTalk WebAssembly モジュール
├── onnx/           # ONNX Runtime 統合
├── test/           # テストとデモ
├── CMakeLists.txt  # ビルド設定
└── build.sh        # ビルドスクリプト
```

### テストの実行

```bash
# 単体テスト
cd onnx && npm test

# 統合テスト
cd test/integration && npm test

# ブラウザ互換性テスト
cd test/browser-compat && npm test
```

### デバッグ

Chrome DevTools を使用：

1. Sources タブで WebAssembly コードを確認
2. Performance タブでプロファイリング
3. Memory タブでメモリ使用量を監視

## トラブルシューティング

### よくある問題

**Q: SharedArrayBuffer が使えない**
A: 以下のヘッダーを設定してください：
```
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Opener-Policy: same-origin
```

**Q: 音声が再生されない（Safari）**
A: Safari ではユーザー操作後に AudioContext を再開する必要があります。

**Q: メモリ不足エラー**
A: ストリーミング処理を使用するか、チャンクサイズを小さくしてください。

**Q: WebGL が使えない**
A: ブラウザの設定で WebGL が有効になっているか確認してください。

## パフォーマンス指標

典型的な処理時間（100文字の日本語テキスト）：

| 処理段階 | 時間 (ms) | 備考 |
|---------|-----------|------|
| MeCab | 10-30 | 形態素解析 |
| OpenJTalk | 20-50 | 音素変換 |
| ONNX推論 | 100-300 | モデル依存 |
| 音声生成 | 10-30 | 後処理 |
| **合計** | **140-410** | RTF < 0.5 |

## 貢献

プルリクエストを歓迎します！

1. このリポジトリをフォーク
2. 機能ブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. プルリクエストを作成

## ライセンス

このプロジェクトは MIT ライセンスの下で公開されています。

## 謝辞

- [Piper](https://github.com/rhasspy/piper) - オリジナルの TTS エンジン
- [MeCab](https://taku910.github.io/mecab/) - 日本語形態素解析
- [OpenJTalk](http://open-jtalk.sourceforge.net/) - 日本語音声合成
- [ONNX Runtime](https://onnxruntime.ai/) - 機械学習推論