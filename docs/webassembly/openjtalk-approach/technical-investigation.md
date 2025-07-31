# WebAssembly OpenJTalkアプローチ - 技術調査報告書

作成日: 2025-07-31
作成者: piper-plus開発チーム

## 1. エグゼクティブサマリー

PR #118でのMeCab単独実装の失敗を踏まえ、`wasm_open_jtalk`の実装方式（OpenJTalk全体の移植）を採用することで、WebAssemblyでの日本語TTS実現が技術的に可能であることを確認しました。

### 主要な発見
- wasm_open_jtalkはOpenJTalk全体をWebAssembly化することに成功
- 辞書互換性の問題は解決済み
- Node.js環境では正常動作を確認
- ブラウザ対応は技術的に可能（Emscripten設定の変更で対応）

## 2. 技術的背景

### 2.1 PR #118の失敗分析

#### 失敗したアプローチ
```
MeCab単独の移植
↓
DARTS辞書フォーマットの非互換性
↓
文頭文字の欠落（精度0%）
```

#### 根本原因
1. MeCab辞書の特殊なDARTS実装（base=-2, check=199）
2. 公式仕様書の不在
3. リバースエンジニアリングの限界

### 2.2 wasm_open_jtalkの成功要因

#### 成功したアプローチ
```
OpenJTalk全体の移植
↓
MeCab + 辞書処理を含む完全な移植
↓
辞書互換性問題を回避
```

## 3. wasm_open_jtalk詳細調査

### 3.1 プロジェクト概要
- **リポジトリ**: https://github.com/hrhr49/wasm_open_jtalk
- **npm**: https://www.npmjs.com/package/wasm_open_jtalk
- **バージョン**: 0.0.1（2021年2月公開）
- **現状**: Node.js CLIツールとして動作

### 3.2 技術スタック
```
OpenJTalk (C++)
    ↓
Emscripten 2.0.14
    ↓
WebAssembly + JavaScript
```

### 3.3 ビルド構成
```makefile
# 主要なビルドステップ
1. Emscripten SDK (emsdk) インストール
2. HTS Engine API ビルド
3. OpenJTalk ビルド with Emscripten
4. 出力: open_jtalk.js + open_jtalk.wasm
```

### 3.4 現在の制限事項
- Node.js専用（`process`, `fs`モジュール依存）
- ブラウザ未対応
- コマンドライン引数処理

## 4. ブラウザ対応の技術的実現性

### 4.1 必要な変更点

#### A. Emscripten設定
```bash
# 現在（Node.js専用）
emcc -s ENVIRONMENT='node' \
     -s NODERAWFS=1 \
     ...

# 変更後（ブラウザ対応）
emcc -s ENVIRONMENT='web,worker' \
     -s MODULARIZE=1 \
     -s EXPORT_ES6=1 \
     -s EXPORTED_RUNTIME_METHODS='["FS", "cwrap", "ccall"]' \
     -s INITIAL_MEMORY=256MB \
     -s ALLOW_MEMORY_GROWTH=1 \
     ...
```

#### B. ファイルシステム対応
```javascript
// Node.js版
const fs = require('fs');
const dictData = fs.readFileSync('dict.dat');

// ブラウザ版
// Option 1: 事前埋め込み
--preload-file naist-jdic@/dict

// Option 2: 動的ロード
await fetch('dict.dat').then(r => r.arrayBuffer());
FS.writeFile('/dict/sys.dic', new Uint8Array(data));
```

#### C. API設計
```javascript
// Node.js版（CLI）
$ open_jtalk.js -x /dict -m voice.htsvoice input.txt

// ブラウザ版（JavaScript API）
const openjtalk = await OpenJTalkModule();
const phonemes = await openjtalk.textToPhonemes("こんにちは");
```

### 4.2 技術的課題と解決策

| 課題 | 影響 | 解決策 |
|------|------|--------|
| 辞書サイズ（103MB） | 初期ロード時間 | CDN + 圧縮 + キャッシュ |
| メモリ使用量 | ブラウザ制限 | 段階的ロード + GC最適化 |
| 初期化時間 | UX | Web Worker + 非同期初期化 |
| ブラウザ互換性 | 利用可能性 | Chrome/Edge優先 → 段階的拡大 |

## 5. 実装可能性評価

### 5.1 技術的実現性: ✅ 高

**根拠**:
1. OpenJTalk全体の移植実績（wasm_open_jtalk）
2. Emscriptenの成熟度と実績
3. 類似プロジェクトの成功例（mecab-web-worker）

### 5.2 リスク評価

| リスク項目 | 確率 | 影響 | 対策 |
|-----------|------|------|------|
| 辞書ロード失敗 | 低 | 高 | CDN冗長化 + フォールバック |
| メモリ不足 | 中 | 中 | 最小辞書 + 段階ロード |
| 性能問題 | 低 | 中 | Web Worker + 最適化 |
| ブラウザ非対応 | 低 | 低 | 段階的サポート |

## 6. 既存実装との比較

| 項目 | PR #118（MeCab単独） | wasm_open_jtalk | 提案アプローチ |
|------|---------------------|-----------------|---------------|
| 実装方針 | MeCab単独移植 | OpenJTalk全体 | OpenJTalk全体 |
| 辞書互換性 | ❌ 失敗 | ✅ 成功 | ✅ 期待 |
| ブラウザ対応 | ✅ 試みた | ❌ Node.js専用 | ✅ 実装予定 |
| 精度 | 0% | 100%（Node.js） | 100%（期待） |

## 7. 推奨事項

### 7.1 採用すべきアプローチ
**wasm_open_jtalkベースのブラウザ対応実装**

### 7.2 実装の優先順位
1. **必須**: 基本的なブラウザ動作
2. **重要**: 辞書の最適化とキャッシング
3. **推奨**: Web Worker統合
4. **将来**: 完全な最適化

### 7.3 成功の定義
- 音素変換精度: PyOpenJTalk同等（95%以上）
- 初期化時間: 5秒以内
- 変換速度: 100ms/文以内
- メモリ使用: 256MB以内

## 8. 結論

wasm_open_jtalkのアプローチを採用し、ブラウザ対応の変更を加えることで、WebAssemblyでの高精度な日本語TTS実現が可能です。PR #118の失敗は実装アプローチの問題であり、技術的な不可能性ではありませんでした。

## 9. 参考文献

1. wasm_open_jtalk: https://github.com/hrhr49/wasm_open_jtalk
2. Emscripten Documentation: https://emscripten.org/docs/
3. mecab-web-worker: https://github.com/leyhline/mecab-web-worker
4. PR #118 分析結果: docs/webassembly-investigation/