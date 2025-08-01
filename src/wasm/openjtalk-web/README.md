# OpenJTalk WebAssembly

OpenJTalkをWebAssemblyで動作させるための実装です。ブラウザ上で日本語テキストから音素ラベルを生成できます。

## 特徴

- ブラウザで動作する完全なOpenJTalk実装
- UTF-8エンコーディング対応
- 軽量なファイルサイズ（WASM: 376KB、JS: 33KB）
- ES6モジュール形式でのエクスポート

## プロジェクト構造

```
openjtalk-web/
├── build/          # ビルドスクリプト
├── src/            # C++ソースコード
├── dist/           # ビルド成果物（JS、WASM）
├── assets/         # 辞書・音声ファイル
│   ├── dict/       # MeCab辞書ファイル
│   └── voice/      # HTSVoiceファイル
└── test/           # テストファイル
```

## ビルド

### 必要なもの

- Emscripten 3.1.x以降
- CMake 3.10以降
- Make

### ビルド手順

```bash
# 依存関係のビルド（初回のみ）
./build/build-dependencies.sh

# OpenJTalkライブラリのビルド  
./build/build-with-wasm-openjtalk.sh

# デバッグビルド（コンソールログ付き）
./build/build-safe.sh

# プロダクションビルド（最適化済み）
./build/build-production.sh
```

## 使用方法

```javascript
// モジュールのインポート
import OpenJTalkModule from './dist/openjtalk.js';

// 初期化
const Module = await OpenJTalkModule({
    locateFile: (path) => {
        if (path.endsWith('.wasm')) {
            return './dist/openjtalk.wasm';
        }
        return path;
    }
});

// ファイルシステムの準備
Module.FS.mkdir('/dict');
Module.FS.mkdir('/voice');

// 辞書ファイルの読み込み
const dictFiles = ['char.bin', 'matrix.bin', 'sys.dic', 'unk.dic', 
                   'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def'];
for (const file of dictFiles) {
    const response = await fetch(`./assets/dict/${file}`);
    const data = await response.arrayBuffer();
    Module.FS.writeFile(`/dict/${file}`, new Uint8Array(data));
}

// 音声ファイルの読み込み
const voiceResponse = await fetch('./assets/voice/mei_normal.htsvoice');
const voiceData = await voiceResponse.arrayBuffer();
Module.FS.writeFile('/voice/mei_normal.htsvoice', new Uint8Array(voiceData));

// OpenJTalkの初期化
const dictPtr = Module.allocateUTF8('/dict');
const voicePtr = Module.allocateUTF8('/voice/mei_normal.htsvoice');
const result = Module._openjtalk_initialize(dictPtr, voicePtr);
Module._free(dictPtr);
Module._free(voicePtr);

// テキストから音素ラベルへの変換
const text = "こんにちは";
const textPtr = Module.allocateUTF8(text);
const labelsPtr = Module._openjtalk_synthesis_labels(textPtr);
const labels = Module.UTF8ToString(labelsPtr);
Module._openjtalk_free_string(labelsPtr);
Module._free(textPtr);

// 音素の抽出
const lines = labels.split('\n').filter(line => line.trim());
const phonemes = [];
for (const line of lines) {
    const match = line.match(/\-([^+]+)\+/);
    if (match && match[1] !== 'sil') {
        phonemes.push(match[1]);
    }
}
console.log(phonemes); // ['k', 'o', 'N', 'n', 'i', 'ch', 'i', 'w', 'a']
```

## API

### 関数

- `openjtalk_initialize(dic_dir, voice_path)` - OpenJTalkを初期化
- `openjtalk_synthesis_labels(text)` - テキストから音素ラベルを生成
- `openjtalk_clear()` - リソースを解放
- `openjtalk_free_string(str)` - 文字列メモリを解放
- `get_version()` - バージョン情報を取得
- `test_function(a, b)` - テスト関数（a + bを返す）

## 開発状況

- [x] Phase 1: 基本実装
  - [x] プロジェクトセットアップ
  - [x] wasm_open_jtalkソース分析
  - [x] ビルド環境構築
  - [x] ブラウザ対応ビルド
  
- [x] Phase 2: 最適化
  - [x] メモリ最適化（Open_JTalk構造体使用）
  - [x] プロダクションビルド（376KB WASM）
  - [x] デバッグログの削除

- [ ] Phase 3: 統合
  - [ ] Piper ONNX Runtime統合
  - [ ] ストリーミングサポート
  - [ ] 本番デプロイ

## テスト

```bash
# テストサーバーの起動
python3 -m http.server 8081

# ブラウザでアクセス
# http://localhost:8081/test/debug-test.html
```

## ライセンス

このプロジェクトはOpenJTalkおよびpiper-plusのライセンス条項に従います。