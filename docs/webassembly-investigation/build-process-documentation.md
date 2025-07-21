# WebAssemblyビルドプロセス ドキュメント

作成日: 2025-07-21

## 概要

既存実装の調査に基づき、MeCabとOpenJTalkをWebAssemblyにビルドするプロセスをまとめました。

## 共通準備

### Emscripten環境
```bash
# Emscripten SDKのインストール
git clone https://github.com/emscripten-core/emsdk.git
cd emsdk
./emsdk install latest
./emsdk activate latest
source ./emsdk_env.sh

# バージョン確認
emcc --version
```

### 推奨バージョン
- Emscripten: 3.1.61以上（最新版推奨）
- Node.js: 18以上
- CMake: 3.15以上

## MeCabビルドプロセス

### 1. ソースコード準備
```bash
# MeCabソースコード取得
wget https://github.com/taku910/mecab/archive/master.zip
unzip master.zip
cd mecab-master/mecab
```

### 2. Emscripten向け設定
```bash
# configure実行
EMCONFIGURE_JS=1 emconfigure ./configure \
  --with-charset=utf8 \
  --enable-utf8-only \
  --disable-shared \
  --host=wasm32-unknown-emscripten
```

### 3. コンパイルオプション
```javascript
// CMakeLists.txt または Makefile.am での設定
const EMSCRIPTEN_FLAGS = [
  "-O3",                          // 最適化レベル
  "-s WASM=1",                    // WebAssembly出力
  "-s MODULARIZE=1",              // モジュール化
  "-s EXPORT_ES6=1",              // ES6モジュール
  "-s ALLOW_MEMORY_GROWTH=1",     // 動的メモリ
  "-s INITIAL_MEMORY=32MB",       // 初期メモリ
  "-s MAXIMUM_MEMORY=256MB",      // 最大メモリ
  "-s EXPORTED_FUNCTIONS=['_mecab_new','_mecab_sparse_tostr','_mecab_destroy']",
  "-s EXPORTED_RUNTIME_METHODS=['ccall','cwrap','UTF8ToString','stringToUTF8']",
  "--bind"                        // Embind使用
];
```

### 4. 辞書データの処理
```bash
# 辞書のバイナリ化
# IPADICの場合
tar xzf mecab-ipadic-2.7.0-20070801.tar.gz
cd mecab-ipadic-2.7.0-20070801
./configure --with-charset=utf8
make

# 辞書データの圧縮
zip -r ipadic.zip *.dic *.def
```

### 5. JavaScript バインディング
```cpp
// mecab_wrapper.cpp
#include <emscripten/bind.h>
#include <mecab.h>

class MecabWrapper {
public:
    MecabWrapper(const std::string& dictPath) {
        tagger = MeCab::createTagger(("-d " + dictPath).c_str());
    }
    
    std::string parse(const std::string& text) {
        return tagger->parse(text.c_str());
    }
    
    ~MecabWrapper() {
        delete tagger;
    }
    
private:
    MeCab::Tagger* tagger;
};

EMSCRIPTEN_BINDINGS(mecab_module) {
    emscripten::class_<MecabWrapper>("MecabWrapper")
        .constructor<std::string>()
        .function("parse", &MecabWrapper::parse);
}
```

## OpenJTalkビルドプロセス

### 1. 依存関係の準備
```bash
# HTS Engine APIのビルド
wget https://sourceforge.net/projects/hts-engine/files/hts_engine%20API/hts_engine_API-1.10/hts_engine_API-1.10.tar.gz
tar xzf hts_engine_API-1.10.tar.gz
cd hts_engine_API-1.10

emconfigure ./configure \
  --host=wasm32-unknown-emscripten \
  --disable-shared
emmake make
```

### 2. OpenJTalkのビルド
```bash
# OpenJTalkソース取得
wget https://sourceforge.net/projects/open-jtalk/files/Open%20JTalk/open_jtalk-1.11/open_jtalk-1.11.tar.gz
tar xzf open_jtalk-1.11.tar.gz
cd open_jtalk-1.11

# configureとビルド
emconfigure ./configure \
  --with-hts-engine-header-path=../hts_engine_API-1.10/include \
  --with-hts-engine-library-path=../hts_engine_API-1.10/lib \
  --with-charset=UTF-8 \
  --host=wasm32-unknown-emscripten

emmake make
```

### 3. 辞書データの最適化
```python
# dictionary_optimizer.py
import struct
import zlib

def optimize_dictionary(input_file, output_file):
    """辞書データを最適化して圧縮"""
    with open(input_file, 'rb') as f:
        data = f.read()
    
    # 頻度の低い単語を除外
    # TODO: 実装
    
    # Brotli圧縮
    compressed = zlib.compress(data, level=9)
    
    with open(output_file, 'wb') as f:
        f.write(compressed)
```

## 統合ビルドスクリプト

### build_wasm.sh
```bash
#!/bin/bash
set -e

echo "Building MeCab..."
cd mecab
emconfigure ./configure --with-charset=utf8
emmake make
cd ..

echo "Building OpenJTalk..."
cd openjtalk
emconfigure ./configure \
  --with-hts-engine-header-path=../hts_engine_API/include \
  --with-hts-engine-library-path=../hts_engine_API/lib
emmake make
cd ..

echo "Creating final WASM module..."
em++ -O3 \
  mecab/src/.libs/libmecab.a \
  openjtalk/src/.libs/libopen_jtalk.a \
  -o piper_phonemizer.js \
  -s WASM=1 \
  -s MODULARIZE=1 \
  -s EXPORT_ES6=1 \
  -s ALLOW_MEMORY_GROWTH=1 \
  -s INITIAL_MEMORY=64MB \
  -s MAXIMUM_MEMORY=256MB \
  --bind

echo "Build complete!"
```

## トラブルシューティング

### よくある問題

1. **configure失敗**
   ```bash
   # autotoolsの再生成
   autoreconf -fi
   ```

2. **メモリ不足エラー**
   ```javascript
   // 初期メモリを増やす
   -s INITIAL_MEMORY=128MB
   ```

3. **文字コード問題**
   ```bash
   # UTF-8を強制
   export LANG=C.UTF-8
   ```

4. **リンクエラー**
   ```bash
   # 静的ライブラリのみ使用
   --disable-shared --enable-static
   ```

## パフォーマンス最適化

### コンパイラフラグ
```bash
# リリースビルド用
-O3                    # 最大最適化
-flto                  # Link Time Optimization
-s ASSERTIONS=0        # アサーション無効化
-s DISABLE_EXCEPTION_CATCHING=1  # 例外処理無効化
```

### メモリ最適化
```javascript
// メモリプールの実装
Module.preRun.push(function() {
    // 辞書データをプリロード
    FS.createPreloadedFile('/', 'dict.dat', 'dict.dat', true, false);
});
```

### Chrome専用最適化
```javascript
// WebAssembly SIMD有効化
-msimd128

// WebGPU対応（将来）
-s USE_WEBGPU=1
```

## ビルド成果物

### 期待される出力
- `piper_phonemizer.js` - JavaScriptグルーコード
- `piper_phonemizer.wasm` - WebAssemblyバイナリ
- `piper_phonemizer.d.ts` - TypeScript定義（オプション）

### ファイルサイズ目標
- JavaScript: < 200KB
- WASM: < 2MB
- 辞書（圧縮済み）: < 3MB

## 次のステップ

1. このビルドプロセスに従って実際のビルドを実行
2. 生成されたWASMモジュールのテスト
3. ブラウザ環境での動作確認
4. パフォーマンス測定と最適化