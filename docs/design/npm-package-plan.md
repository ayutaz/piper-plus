# npm パッケージ公開計画

## 概要

既存の WASM 実装 (`src/wasm/openjtalk-web/`) を `piper-plus` として npm に公開する。ブラウザ内で完全オフラインの多言語 TTS を `npm install` で利用可能にする。

**ブランチ**: `feature/npm-package`

---

## 現在の状態

**ブランチ**: `feature/npm-package` (PR #285)
**完了日**: 2026-03-27
**テスト**: 282件 (全件合格)

| Phase | 状態 | 完了タスク |
|-------|------|-----------|
| Phase 1: パッケージ基盤 | 完了 | 4/4 |
| Phase 2: 高レベル API | 完了 | 3/3 |
| Phase 3: テスト・CI | ほぼ完了 | 3/4 (npm publish 未実施) |

---

## 背景と動機

piper-plus はブラウザ内 TTS のデモ (https://ayutaz.github.io/piper-plus/) が動作済みだが、npm に公開されていないため外部開発者が利用しづらい。sherpa-onnx エコシステム等の比較記事でも候補に入らない原因の一つとなっている。

npm パッケージとして公開することで:
- `npm install piper-plus` で即座に利用可能
- 他プロジェクトへの組み込みが容易に
- npm エコシステムでの発見可能性が向上

---

## 設計方針

### パッケージ構成

```
piper-plus (npm, MIT)
├── src/
│   ├── index.js                    # エントリーポイント
│   ├── simple_unified_api.js       # メイン音素化 API
│   ├── webgpu-session-manager.js   # ONNX セッション管理
│   ├── streaming-pipeline.js       # ストリーミング TTS
│   ├── audio-backend-factory.js    # オーディオ出力
│   ├── audio-worklet-processor.js  # AudioWorklet
│   ├── cache-manager.js            # IndexedDB キャッシュ
│   ├── custom_dictionary.js        # カスタム辞書
│   ├── japanese_phoneme_extract.js # 日本語音素抽出
│   ├── simple_english_phonemizer.js # 英語音素化 (独自実装)
│   ├── memory-pool.js              # メモリプール
│   ├── resampler.js                # リサンプラー
│   └── dictionary-loader.js        # 辞書ローダー
├── dist/
│   ├── openjtalk.wasm              # OpenJTalk WASM (564KB)
│   ├── openjtalk.js                # Emscripten JS (100KB)
│   └── load-dictionary.js          # 辞書ロードヘルパー
├── types/
│   └── index.d.ts                  # TypeScript 型定義
├── package.json
├── LICENSE.md
└── README.md
```

### npm パッケージに含めないもの

| 除外対象 | サイズ | 理由 |
|---------|--------|------|
| `dist/espeak-ng/` | 2.8MB | 推論パイプラインで不使用、GPL ライセンスリスク回避 |
| `assets/dict/` | 109MB | 初回実行時に動的ダウンロード |
| `assets/dict.tar.gz` | 23MB | 同上 |
| `models/` | 38MB | HuggingFace から動的ダウンロード |
| `assets/voice/` | 4.1MB | HuggingFace から動的ダウンロード |
| `test/` | - | 開発用 |
| `demo/` | - | 開発用 |
| `build/` | - | ビルドスクリプト |
| `dist/*.bak` | 956KB | バックアップファイル |

### アセット配信戦略

| アセット | 配信元 | サイズ | タイミング |
|---------|--------|--------|----------|
| WASM バイナリ | npm パッケージ内 | ~700KB | install 時 |
| OpenJTalk 辞書 | CDN / HuggingFace | 23MB (圧縮) | 初回実行時に DL、IndexedDB キャッシュ |
| ONNX モデル | HuggingFace | 38-75MB | ユーザーが指定、IndexedDB キャッシュ |
| HTS Voice | HuggingFace | ~842KB | 初回実行時に DL |

HuggingFace の `https://huggingface.co/ayousanz/piper-plus-*/resolve/main/` は CORS 対応済みで、ブラウザから直接フェッチ可能。

---

## 想定 API

### 基本的な使い方

```javascript
import { PiperPlus } from "piper-plus";

// 初期化 (モデル・辞書の自動DL + キャッシュ)
const tts = await PiperPlus.initialize({
  model: "ayousanz/piper-plus-tsukuyomi-chan",
});

// テキストから音声生成
const audio = await tts.synthesize("こんにちは、今日は良い天気ですね。", {
  language: "ja",
});

// 再生
audio.play();

// または WAV Blob として取得
const blob = audio.toBlob();
```

### ストリーミング

```javascript
const tts = await PiperPlus.initialize({
  model: "ayousanz/piper-plus-tsukuyomi-chan",
});

// 文ごとに逐次合成・再生
await tts.synthesizeStreaming("長い文章をここに入力...", {
  language: "ja",
  onChunk: (audioChunk) => {
    // 各チャンクを受け取る
  },
});
```

### 音素化のみ

```javascript
import { SimpleUnifiedPhonemizer } from "piper-plus";

const phonemizer = new SimpleUnifiedPhonemizer();
await phonemizer.initialize({ /* ... */ });

const phonemes = await phonemizer.textToPhonemes("こんにちは", "ja");
```

---

## 各言語の音素化方式

npm パッケージでは eSpeak-ng を使用せず、すべて独自実装で音素化する。

| 言語 | 音素化エンジン | 依存 | eSpeak-ng |
|------|-------------|------|-----------|
| ja | OpenJTalk WASM | openjtalk.wasm | 不使用 |
| en | SimpleEnglishPhonemizer | 辞書+規則ベース (JS) | 不使用 |
| zh | キャラクタベースマッピング | JS のみ | 不使用 |
| es | キャラクタベースマッピング | JS のみ | 不使用 |
| fr | キャラクタベースマッピング | JS のみ | 不使用 |
| pt | キャラクタベースマッピング | JS のみ | 不使用 |

---

## ライセンス

### npm パッケージのライセンス: MIT

| コンポーネント | ライセンス | npm に含む | 問題 |
|-------------|-----------|----------|------|
| piper-plus 本体 | MIT | はい | なし |
| OpenJTalk WASM | BSD-3-Clause | はい | なし |
| HTS Engine API | BSD-3-Clause | はい | なし |
| MeCab 辞書 (NAIST) | BSD-3-Clause | いいえ (動的DL) | なし |
| onnxruntime-web | MIT | いいえ (peerDep) | なし |
| eSpeak-ng | GPL-3.0 | **いいえ (除外)** | 除外で回避 |

### 学習データセット (ONNX モデル内)

モデルは npm パッケージに含めず HuggingFace からの動的 DL とするため、npm パッケージのライセンスには直接影響しない。

| データセット | ライセンス |
|------------|-----------|
| LibriTTS-R | CC-BY-4.0 |
| AISHELL-3 | Apache-2.0 |
| CML-TTS (es/fr/pt) | CC-BY-4.0 |
| MOE-Speech | 要確認 |

---

## 実装タスク

### Phase 1: パッケージ基盤

- [x] **1-1**: package.json の整備
  - `name`: "piper-plus"
  - `exports`, `main`, `module`, `types` フィールド
  - `peerDependencies`: `onnxruntime-web: "^1.21.0"`
  - `files` フィールドでパッケージ内容を制限
  - `keywords`, `repository`, `homepage` 等のメタデータ

- [x] **1-2**: エントリーポイント (`src/index.js`) 作成
  - `PiperPlus` クラス (高レベル API)
  - 既存モジュールの re-export

- [x] **1-3**: TypeScript 型定義 (`types/index.d.ts`) 作成

- [x] **1-4**: .npmignore 作成
  - `dist/espeak-ng/`, `test/`, `demo/`, `build/`, `assets/`, `models/` 等を除外

### Phase 2: 高レベル API

- [x] **2-1**: `PiperPlus` クラスの実装
  - `PiperPlus.initialize(options)` — モデル・辞書の自動 DL + キャッシュ + セッション作成
  - `tts.synthesize(text, options)` — テキスト → 音声生成
  - `tts.synthesizeStreaming(text, options)` — ストリーミング合成
  - `tts.dispose()` — リソース解放

- [x] **2-2**: モデル自動ダウンロード機能
  - HuggingFace URL からモデル + config.json を取得
  - IndexedDB キャッシュ統合

- [x] **2-3**: 辞書自動ダウンロード機能
  - OpenJTalk 辞書 (dict.tar.gz) の動的 DL + 解凍
  - IndexedDB キャッシュ統合

### Phase 3: テスト・ドキュメント・CI

- [x] **3-1**: npm パッケージ用テスト追加 (282テスト)
  - API の基本動作テスト
  - 型定義の整合性テスト

- [x] **3-2**: README.md (npm 向け) -- README.npm.md として作成済み
  - インストール方法
  - 基本的な使い方
  - API リファレンス
  - ライセンス情報

- [x] **3-3**: GitHub Actions ワークフロー -- npm-publish.yml + ci.yml に統合済み
  - npm publish 自動化 (タグトリガー)
  - パッケージサイズの検証

- [ ] **3-4**: npm パッケージ名の確保 -- 未実施 (npm login + 初回 publish)
  - `npm login` + 初回 publish

---

## package.json (案)

```json
{
  "name": "piper-plus",
  "version": "0.1.0",
  "description": "Browser-based multilingual neural TTS with VITS. Supports Japanese, English, Chinese, Spanish, French, and Portuguese.",
  "type": "module",
  "main": "src/index.js",
  "module": "src/index.js",
  "types": "types/index.d.ts",
  "exports": {
    ".": {
      "types": "./types/index.d.ts",
      "import": "./src/index.js"
    },
    "./phonemizer": {
      "import": "./src/simple_unified_api.js"
    },
    "./streaming": {
      "import": "./src/streaming-pipeline.js"
    }
  },
  "files": [
    "src/**/*.js",
    "dist/openjtalk.wasm",
    "dist/openjtalk.js",
    "dist/load-dictionary.js",
    "types/",
    "LICENSE.md",
    "README.md"
  ],
  "peerDependencies": {
    "onnxruntime-web": "^1.21.0"
  },
  "keywords": [
    "tts",
    "text-to-speech",
    "speech-synthesis",
    "japanese",
    "multilingual",
    "vits",
    "onnx",
    "webassembly",
    "wasm",
    "piper",
    "openjtalk"
  ],
  "repository": {
    "type": "git",
    "url": "https://github.com/ayutaz/piper-plus"
  },
  "homepage": "https://ayutaz.github.io/piper-plus/",
  "author": "ayutaz",
  "license": "MIT",
  "engines": {
    "node": ">=18.0.0"
  }
}
```

---

## リスクと対策

### 解決済み

| リスク | 状態 | 対策 |
|-------|------|------|
| eSpeak-ng GPL | 解決 | 推論パイプラインで不使用のため npm パッケージから除外 |

### 残存リスク

| リスク | 重大度 | 対策 |
|-------|--------|------|
| **パッケージサイズ** | 🟡 | WASM + JS のみ (~4-5MB) に限定、辞書・モデルは動的 DL |
| **ブラウザ専用** | 🟡 | README に明記。Node.js 対応は将来の Phase で検討 |
| **SimpleEnglishPhonemizer の精度** | 🟡 | 辞書ベースのため未知語の精度が限定的。eSpeak-ng 版を別パッケージで提供する選択肢あり |
| **zh/es/fr/pt の音素化精度** | 🟡 | キャラクタベースフォールバックのため品質は限定的 |
| **辞書 DL の初回遅延** | 🟢 | IndexedDB キャッシュで2回目以降は高速。進捗コールバック提供 |
| **HuggingFace の可用性** | 🟢 | CDN ミラー設定可能な設計にする |
| **npm パッケージ名の先取り** | 🟢 | "piper-plus" は現在未登録、早期に確保する |

---

## 参考: 既存の類似 npm パッケージ

| パッケージ | 特徴 | piper-plus との差異 |
|-----------|------|-------------------|
| kokoro-js | Kokoro-82M ONNX、Transformers.js 依存 | piper-plus は独自 WASM 音素化、より軽量 |
| sherpa-onnx | C++ ネイティブ + WASM、モデルズー | piper-plus はブラウザ特化、日本語に強い |
| @mintplex-labs/piper-tts-web | オリジナル Piper のブラウザフォーク | piper-plus は多言語+韻律対応 |
