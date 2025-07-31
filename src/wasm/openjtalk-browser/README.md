# OpenJTalk Browser Implementation

## 概要

wasm_open_jtalkをベースにしたブラウザ対応実装の実験ディレクトリ。

## 実装方針

### 1. wasm_open_jtalkの問題点
- Node.js専用（`process`、`fs`モジュールに依存）
- ブラウザでのファイルシステムアクセス未対応
- コマンドライン引数処理

### 2. ブラウザ対応の方針

#### A. Emscripten設定の変更
```bash
# Node.js専用から
emcc -s ENVIRONMENT='node' ...

# ブラウザ対応へ
emcc -s ENVIRONMENT='web,worker' \
     -s MODULARIZE=1 \
     -s EXPORT_ES6=1 \
     -s EXPORTED_RUNTIME_METHODS='["FS", "cwrap", "ccall"]' \
     ...
```

#### B. 辞書ファイルの埋め込み
```bash
# 辞書を事前に埋め込む
emcc ... --preload-file naist-jdic@/dict
```

#### C. JavaScript APIラッパー
```javascript
class OpenJTalkBrowser {
  async initialize() {
    // WebAssemblyモジュールの初期化
    this.module = await OpenJTalkModule();
    
    // 辞書の準備
    await this.loadDictionary();
  }
  
  async textToPhonemes(text) {
    // OpenJTalkを使用してテキストを音素列に変換
    return this.module.ccall('openjtalk_text2phonemes', 
      'string', ['string'], [text]);
  }
}
```

## 実装ステップ

### Step 1: 基本的なビルド設定
1. wasm_open_jtalkのソースコードを取得
2. Emscripten設定をブラウザ対応に変更
3. 最小限のテストページで動作確認

### Step 2: 辞書の最適化
1. 辞書サイズの削減（頻出語のみ）
2. 圧縮形式での配信
3. IndexedDBでのキャッシュ

### Step 3: APIの設計
1. Promise-basedのJavaScript API
2. Web Worker対応
3. ストリーミング対応

## 技術的課題

### 1. メモリ使用量
- フル辞書: 103MB
- 目標: 50MB以下

### 2. 初期化時間
- 現状: 数秒
- 目標: 1秒以下

### 3. ブラウザ互換性
- 優先: Chrome/Edge（Chromium系）
- 将来: Firefox、Safari

## 参考リソース
- [wasm_open_jtalk](https://github.com/hrhr49/wasm_open_jtalk)
- [Emscripten File System API](https://emscripten.org/docs/api_reference/Filesystem-API.html)
- [mecab-web-worker](https://github.com/leyhline/mecab-web-worker)