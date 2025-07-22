# Piper WebAssembly TTS 本番実装計画

## 概要

本ドキュメントは、Piper TTSをWebAssemblyで実装し、ブラウザ上で日本語音声合成を実現するための詳細な実装計画です。

## 目標

- ブラウザ上で完全に動作する日本語TTS
- インストール不要、サーバー不要
- リアルタイム音声合成（RTF > 10x）
- 高品質な音声出力

## アーキテクチャ

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│   テキスト   │ --> │    MeCab     │ --> │  OpenJTalk  │ --> │ ONNX Runtime │
│   入力      │     │  (形態素解析) │     │ (音素変換)  │     │  (音声合成)  │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘
                           ↓                      ↓                    ↓
                      WebAssembly            WebAssembly         WebAssembly
                        Module                 Module            + WebGL/GPU
```

## フェーズ1: 基盤モジュールのビルド

### 1.1 MeCab WebAssemblyモジュール

#### 目的
日本語テキストの形態素解析をブラウザ上で実行

#### 技術要件
- MeCab 0.996
- IPA辞書（NAIST Japanese Dictionary）
- Emscripten 3.1.61+

#### 実装タスク

1. **ソースコード準備**
   ```bash
   # MeCabソースの取得
   wget https://github.com/taku910/mecab/archive/refs/tags/v0.996.tar.gz
   tar -xzf v0.996.tar.gz
   ```

2. **Emscriptenビルド設定**
   ```cmake
   # CMakeLists.txt
   set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -O3 -s WASM=1")
   set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s ALLOW_MEMORY_GROWTH=1")
   set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s EXPORTED_FUNCTIONS=['_mecab_new','_mecab_parse']")
   set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -s EXPORTED_RUNTIME_METHODS=['ccall','cwrap']")
   ```

3. **辞書データの埋め込み**
   - 辞書データをバイナリ形式に変換
   - Emscriptenの仮想ファイルシステムに組み込み
   - 初期化時の自動ロード実装

4. **JavaScript APIラッパー**
   ```javascript
   class MeCabWrapper {
     async initialize(dictPath) {
       this.module = await MeCabModule();
       this.mecab = this.module._mecab_new();
       return this.loadDictionary(dictPath);
     }
     
     parse(text) {
       const ptr = this.module.allocateUTF8(text);
       const result = this.module._mecab_parse(this.mecab, ptr);
       this.module._free(ptr);
       return this.module.UTF8ToString(result);
     }
   }
   ```

#### 成果物
- `mecab.wasm` (約2MB)
- `mecab.js` (グルーコード)
- `mecab-dict.dat` (辞書データ、約15MB)

### 1.2 OpenJTalk WebAssemblyモジュール

#### 目的
形態素解析結果から音素列への変換

#### 技術要件
- OpenJTalk 1.11
- HTS Engine 1.10
- 日本語音声合成用音響モデル

#### 実装タスク

1. **依存関係の解決**
   - MeCabとの連携インターフェース
   - HTSエンジンの組み込み
   - 音響モデルの軽量化

2. **音素出力フォーマット**
   ```javascript
   {
     "phonemes": ["k", "o", "N", "n", "i", "ch", "i", "w", "a"],
     "durations": [0.1, 0.08, 0.12, 0.09, 0.1, 0.11, 0.1, 0.09, 0.11],
     "accents": [0, 0, 0, 1, 1, 0, 0, 0, 0]
   }
   ```

3. **メモリ最適化**
   - 不要な音声合成機能の削除
   - 音素変換のみに特化

#### 成果物
- `openjtalk.wasm` (約1MB)
- `openjtalk.js` (グルーコード)
- `hts_voice.dat` (音響モデル、約5MB)

## フェーズ2: 音声合成エンジン統合

### 2.1 ONNX Runtime Web統合

#### 目的
Piperのニューラルネットワークモデルを実行

#### 技術要件
- ONNX Runtime Web 1.16.3
- WebGL/WebGPUバックエンド
- SIMD対応（オプション）

#### 実装タスク

1. **ランタイム設定**
   ```javascript
   const session = await ort.InferenceSession.create(modelPath, {
     executionProviders: [
       {
         name: 'webgl',
         deviceType: 'gpu',
         powerPreference: 'high-performance'
       },
       'wasm'
     ],
     graphOptimizationLevel: 'all'
   });
   ```

2. **メモリプール実装**
   - テンソルの再利用
   - ガベージコレクション最適化

3. **バッチ処理対応**
   - 複数文の並列処理
   - ストリーミング出力

### 2.2 Piper TTSモデルの準備

#### 必要なモデル
- 日本語VITS/JETS モデル
- 22.05kHz サンプリングレート
- 単一話者または多話者対応

#### モデル最適化

1. **量子化**
   ```python
   # INT8量子化でサイズを1/4に
   import onnx
   from onnxruntime.quantization import quantize_dynamic
   
   quantize_dynamic(
     model_input='model.onnx',
     model_output='model_quantized.onnx',
     weight_type=QuantType.QInt8
   )
   ```

2. **プルーニング**
   - 重要度の低い重みを削除
   - モデルサイズ50%削減目標

#### 成果物
- `ja_JP-kokoro-medium.onnx` (約20MB、量子化後)
- `phoneme_map.json` (音素マッピング)

## フェーズ3: パイプライン実装

### 3.1 音素変換パイプライン

#### データフロー
```
テキスト → 正規化 → MeCab → OpenJTalk → 音素列 → 前処理
```

#### 実装詳細

1. **テキスト正規化**
   ```javascript
   function normalizeText(text) {
     // 数字の読み変換
     text = text.replace(/(\d+)/g, (match) => convertNumberToKana(match));
     // 英語の処理
     text = text.replace(/([a-zA-Z]+)/g, (match) => convertEnglishToKana(match));
     return text;
   }
   ```

2. **音素エンコーディング**
   ```javascript
   function encodePhonemes(phonemes) {
     const encoded = phonemes.map(p => PHONEME_TO_ID[p] || 0);
     return new Int32Array(encoded);
   }
   ```

### 3.2 音声合成パイプライン

#### ストリーミング実装

```javascript
class StreamingSynthesizer {
  constructor(session) {
    this.session = session;
    this.chunkSize = 1024; // サンプル数
  }
  
  async *synthesizeStream(phonemes) {
    const chunks = this.splitIntoChunks(phonemes);
    
    for (const chunk of chunks) {
      const audio = await this.synthesizeChunk(chunk);
      yield audio;
    }
  }
}
```

## フェーズ4: 最適化

### 4.1 ロード時間の最適化

1. **遅延ロード**
   ```javascript
   // 必要なモジュールのみを段階的にロード
   async function lazyLoadModules() {
     // まずUIを表示
     showUI();
     
     // 並列でモジュールをロード
     const [mecab, openjtalk, onnx] = await Promise.all([
       import('./mecab.js'),
       import('./openjtalk.js'),
       import('./onnx-runtime.js')
     ]);
   }
   ```

2. **キャッシュ戦略**
   - Service Workerでモデルファイルをキャッシュ
   - IndexedDBで辞書データを保存

### 4.2 パフォーマンス最適化

1. **Web Workers活用**
   ```javascript
   // 音声合成を別スレッドで実行
   const worker = new Worker('synthesis-worker.js');
   worker.postMessage({ text, options });
   ```

2. **SIMD最適化**
   - `-msimd128`フラグでビルド
   - ベクトル演算の活用

## 実装スケジュール

### 第1週: MeCab WebAssemblyビルド
- [ ] ソースコード準備とビルド環境構築
- [ ] 基本的なWebAssemblyビルド
- [ ] 辞書データの組み込み
- [ ] JavaScriptラッパー実装

### 第2週: OpenJTalk統合
- [ ] OpenJTalkのWebAssemblyビルド
- [ ] MeCabとの連携実装
- [ ] 音素出力フォーマット定義
- [ ] テスト実装

### 第3週: ONNX Runtime統合
- [ ] ONNX Runtime Webのセットアップ
- [ ] Piperモデルの準備と変換
- [ ] 基本的な音声合成実装
- [ ] 音質評価

### 第4週: 統合とデプロイ
- [ ] 全体パイプラインの統合
- [ ] パフォーマンス最適化
- [ ] ブラウザ互換性テスト
- [ ] デモサイトの更新

## テスト計画

### 単体テスト
- MeCab形態素解析精度
- OpenJTalk音素変換精度
- ONNX推論速度

### 統合テスト
- エンドツーエンド音声合成
- メモリリーク検証
- ブラウザ互換性

### パフォーマンステスト
- 初期化時間: < 3秒
- 合成速度: RTF > 10x
- メモリ使用量: < 200MB

## リスクと対策

### 技術的リスク
1. **ファイルサイズ**
   - リスク: 総計50MB以上になる可能性
   - 対策: 段階的ロード、CDN活用

2. **ブラウザ互換性**
   - リスク: Safari/iOSでの制限
   - 対策: フォールバック実装

3. **パフォーマンス**
   - リスク: モバイルでの処理速度
   - 対策: 品質レベルの選択機能

## 参考資料

- [MeCab公式](https://taku910.github.io/mecab/)
- [OpenJTalk](http://open-jtalk.sourceforge.net/)
- [ONNX Runtime Web](https://onnxruntime.ai/docs/get-started/with-javascript.html)
- [Emscripten Documentation](https://emscripten.org/docs/)
- [Piper TTS](https://github.com/rhasspy/piper)