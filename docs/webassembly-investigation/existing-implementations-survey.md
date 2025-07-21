# 既存WebAssembly実装調査レポート

作成日: 2025-07-21

## 調査概要

piper-plusのWebAssembly実装に向けて、既存のMeCabおよびOpenJTalkのWebAssembly/Emscripten実装を調査しました。

## MeCab WebAssembly実装

### 1. mecab-web-worker (leyhline)
- **GitHub**: https://github.com/leyhline/mecab-web-worker
- **最新**: 現在も活発にメンテナンス
- **技術スタック**:
  - TypeScript
  - Module Workers
  - Compression Streams API
  - Emscripten

**特徴**:
- Web Worker内で動作（メインスレッドをブロックしない）
- 辞書はZIPファイルとして配布
- CacheStorageで辞書キャッシュ
- fugashi (Python)風のAPI設計

**使用例**:
```javascript
const worker = await MecabWorker.create("/unidic-mecab-2.1.2_bin.zip");
const result = await worker.parse("和布蕪は、ワカメの付着器の上にある");
```

**制限事項**:
- Module WorkersとCompression Streams APIが必要（全ブラウザ未対応）
- Chrome最新版では動作確認済み

### 2. mecab-emscripten (fasiha)
- **GitHub**: https://github.com/fasiha/mecab-emscripten
- **公開年**: 2014年頃
- **技術詳細**:
  - C++からLLVM IRを経由してJavaScriptに変換
  - Emscriptenを使用

**ビルドプロセス**:
1. MeCabネイティブビルド
2. IPADICディクショナリの準備
3. Emscriptenでのコンパイル:
   ```bash
   EMCONFIGURE_JS=1 emconfigure ./configure --with-charset=utf8
   em++ -O1 mecab.bc libmecab.so -o mecab.js
   ```

**修正内容**:
- `tagger.cpp`と`mecab.h`の修正
- `mecab_do2`関数の追加（JavaScript引数処理用）

### 3. deprecated-mecab-wasm (Birch-san)
- **GitHub**: https://github.com/Birch-san/deprecated-mecab-wasm
- **状態**: 非推奨（作者は別のリポジトリを推奨）
- 初期のWebAssembly移植実験

## OpenJTalk WebAssembly実装

### 1. wasm_open_jtalk (hrhr49)
- **GitHub**: https://github.com/hrhr49/wasm_open_jtalk
- **npm**: https://www.npmjs.com/package/wasm_open_jtalk
- **公開**: 4年前（v0.0.1）
- **現状**: Node.js CLIツールとして動作

**技術仕様**:
- Emscripten 2.0.14使用
- Ubuntu 20.04でビルド
- wasm32-unknown-emscripten ターゲット

**ビルドプロセス**:
1. Emscripten SDKインストール
2. HTS Engine APIインストール
3. Open JTalkコンパイル
4. `open_jtalk.js`と`open_jtalk.wasm`生成

**使用方法**:
```bash
npm -g install wasm_open_jtalk
open_jtalk.js --help
```

**制限事項**:
- ブラウザ対応は未実装
- Node.js環境専用
- 追加パッケージの調査が必要（TODO）

### 2. SharpOpenJTalk (.NET統合)
- Blazor WebAssembly対応
- openjtalk.aをEmscripten 2.0.23でビルド
- .NETアプリケーション向け

## 技術的洞察

### 成功要因
1. **MeCab**:
   - Emscriptenでの移植実績多数
   - 辞書データの扱いが確立（ZIP圧縮、動的ロード）
   - Web Worker活用でパフォーマンス向上

2. **OpenJTalk**:
   - Node.js環境では動作確認済み
   - HTS Engine APIとの統合も可能
   - 基本的なビルドプロセスは確立

### 技術的課題
1. **辞書サイズ**:
   - MeCab: unidic-mecab-2.1.2_bin.zip（圧縮済み）
   - OpenJTalk: 103MB（未圧縮）→要最適化

2. **ブラウザ互換性**:
   - Module Workers（Chrome限定）
   - SharedArrayBuffer（セキュリティ制限）
   - 大容量メモリ使用

3. **音声合成部分**:
   - OpenJTalkはテキスト→音素化まで
   - HTS Engine（音声合成）の移植も必要
   - またはONNX Runtimeへの置き換え

## 推奨アプローチ

### Phase 1: MeCab統合
- **ベース実装**: mecab-web-worker
- **改良点**:
  - Chrome限定で最適化
  - 辞書サイズ削減（頻度ベース）
  - TypeScript/モダンJS活用

### Phase 2: OpenJTalk移植
- **ベース実装**: wasm_open_jtalk
- **改良点**:
  - ブラウザ対応追加
  - 辞書最適化（2-3MB目標）
  - MeCabとの統合

### Phase 3: 音声合成
- **方針**: ONNX Runtime Web使用
- HTS Engineの代わりにVITSモデル
- WebGPU/WebGL活用

## 結論

既存実装の調査により、以下が判明しました：

1. **MeCab**: 成熟した実装が存在、すぐに活用可能
2. **OpenJTalk**: Node.js実装は存在、ブラウザ対応は要開発
3. **統合**: 両者を組み合わせた実装は未存在

これらの既存実装を参考に、piper-plus向けに最適化したWebAssembly実装を進めることが可能です。特にChrome限定とすることで、最新のWeb技術を活用した高性能な実装が期待できます。