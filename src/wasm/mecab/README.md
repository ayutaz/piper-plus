# MeCab WebAssembly Prototype

MeCab（日本語形態素解析エンジン）のWebAssembly実装プロトタイプです。

## 概要

このプロトタイプは、MeCabの基本機能をWebAssemblyで実装し、ブラウザ上で日本語テキストの形態素解析を可能にします。

## 機能

- 形態素解析（品詞情報付き）
- 分かち書き
- 読み仮名取得
- 構造化データ出力

## ビルド方法

### 前提条件
- Emscripten SDK 3.1.61以上
- CMake 3.15以上
- Python 3（テストサーバー用）

### ビルド手順
```bash
# 1. Emscripten環境の設定
source ../setup_env.sh

# 2. ビルド実行
./build.sh

# 3. クリーンビルド（必要な場合）
./build.sh --clean
```

## 使用方法

### JavaScriptからの使用
```javascript
import MeCabWrapper from './mecab-wrapper.js';

// 初期化
const mecab = new MeCabWrapper();
await mecab.initialize('./dist/mecab_wasm.wasm');

// 形態素解析
const result = mecab.parse('こんにちは世界');
console.log(result);

// 分かち書き
const wakati = mecab.wakati('今日は良い天気ですね');
console.log(wakati); // "今日 は 良い 天気 です ね"

// 読み仮名
const reading = mecab.getReading('世界');
console.log(reading); // "セカイ"
```

### テストページ
```bash
cd test
python3 server.py
# ブラウザで http://localhost:8080/test/index.html を開く
```

## ファイル構成

```
mecab/
├── CMakeLists.txt      # ビルド設定
├── build.sh            # ビルドスクリプト
├── src/                # C++ソースコード
│   └── mecab.cpp       # SimpleMeCab実装
├── dict/               # 辞書データ
│   └── minimal/        # 最小辞書
├── dist/               # ビルド成果物
│   ├── mecab_wasm.js
│   ├── mecab_wasm.wasm
│   └── mecab_wasm.data
├── test/               # テスト用ファイル
│   ├── index.html      # テストページ
│   └── server.py       # 開発サーバー
└── mecab-wrapper.js    # JavaScript API

```

## 技術仕様

- **WebAssembly**: Emscriptenでコンパイル
- **メモリ**: 初期32MB、最大128MB
- **API**: Embindによるバインディング
- **辞書**: プロトタイプ用最小辞書（8単語）

## 制限事項

- 辞書は限定的（実装例として8単語のみ）
- 未知語の処理は簡易的
- 本番利用には実際のMeCab辞書が必要

## ライセンス

このプロトタイプはMeCabのライセンスに従います。