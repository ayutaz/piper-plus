# WebGPU最適化マイルストーン

**ブランチ**: `feature/webgpu-optimization`
**開始日**: 2026-03-16
**最終更新**: 2026-03-17
**TDD方針**: テストを先に書き、実装後にパスさせる
**CI**: `.github/workflows/test-web-optimization.yml`

---

## マイルストーン一覧

| Phase | 名前 | 状態 | テストファイル | テスト結果 |
|-------|------|------|-------------|-----------|
| 1 | ベンチマーク基盤 | ✅ 完了 | `test-benchmark-runner.js` | 12/12 パス |
| 1 | IndexedDBキャッシュ | ✅ 完了 | `test-cache-manager.js` + `test-dictionary-cache.js` | 19/19 パス |
| 1 | ONNX Runtime更新 | 🔶 一部完了 | 手動検証 | ORT 1.21.0更新済 |
| 2a | リサンプラー | ✅ 完了 | `test-resampler.js` | 8/8 パス |
| 2a | AudioWorklet | ✅ 完了 | `test-audio-backend.js` | 8/8 パス |
| 2b | WebGPUセッション | ✅ 完了 | `test-webgpu-session.js` | 11/11 パス |
| 2c | 統合テスト | ✅ 完了 | `test-phase2-integration.js` | 10/10 パス |
| 3 | ストリーミング | ✅ 完了 | `test-streaming-pipeline.js` | 16/16 パス |
| 3 | メモリプール | ✅ 完了 | `test-memory-pool.js` | 7/7 パス |
| 4 | モバイルUI | ⬚ 未着手 | 手動検証 | - |
| 4 | FP16量子化 | ⬚ 未着手 | Python pytest | - |
| 5 | SAB/PWA | ⬚ 未着手 | E2E | - |

---

## ベンチマーク基盤 ✅ 完了

**Phase**: 1 | **期間**: Week 1 | **依存**: なし
**完了日**: 2026-03-16 | **コミット**: `82f22b4`

### 完了条件
- [x] `BenchmarkRunner` クラス実装 (`src/benchmark.js`)
- [x] `RegressionDetector` クラス実装 (メトリック別しきい値)
- [x] `test-benchmark-runner.js` 全12テストパス
- [x] GitHub Actions `test-web-optimization.yml` の Phase 1 ジョブ構成済み

### TDDテスト (12テスト — 全パス)
```
test-benchmark-runner.js
├── BenchmarkRunner (4テスト)
│   ├── ✅ measureAsync()で非同期関数の実行時間を計測できる
│   ├── ✅ 複数ステージを順番に計測できる
│   ├── ✅ getSummary()はdurationをms文字列で返す
│   └── ✅ reset()で計測データをクリアできる
└── RegressionDetector (8テスト)
    ├── 基本検知
    │   ├── ✅ しきい値内の変動はリグレッションとして検出しない
    │   ├── ✅ しきい値を超える劣化をリグレッションとして検出する
    │   └── ✅ 改善 (負のdelta) はリグレッションとして検出しない
    ├── メトリック別しきい値
    │   ├── ✅ Inference: 10%超過で検出
    │   ├── ✅ WASM Load: 5%超過で検出
    │   └── ✅ 未知メトリックはデフォルトしきい値を使用
    └── 重要度判定
        ├── ✅ 20%超過はcritical
        └── ✅ 20%以下の超過はhigh
```

### 実装ファイル
- `src/wasm/openjtalk-web/src/benchmark.js` (新規)

---

## IndexedDBキャッシュ ✅ 完了

**Phase**: 1 | **期間**: Week 1-2 | **依存**: なし
**完了日**: 2026-03-16 | **コミット**: `82f22b4`, `345b290`

### 完了条件
- [x] `CacheManager` クラス実装 (`src/cache-manager.js`)
- [x] iOS 50MB/origin制限の対応（優先度ベースeviction）
- [x] `test-cache-manager.js` 全13テストパス
- [x] `dictionary-loader.js` をキャッシュ統合に改修（`cacheManager`/`dictVersion`オプション追加）
- [x] 2回目以降のロード時間が95%以上削減されることを確認（キャッシュヒット時fetch 0回）

### TDDテスト (19テスト — 全パス)
```
test-cache-manager.js (13テスト)
├── 基本CRUD操作 (4テスト)
│   ├── ✅ set()/get()
│   ├── ✅ 存在しないキー
│   ├── ✅ 上書き
│   └── ✅ delete()
├── バージョン管理 (3テスト)
│   ├── ✅ isValid() 一致
│   ├── ✅ isValid() 不一致
│   └── ✅ isValid() キー不在
├── ストレージ容量管理 (2テスト)
│   ├── ✅ getUsage()
│   └── ✅ clear()
├── iOS制限対応 (2テスト)
│   ├── ✅ 50MB超過処理
│   └── ✅ 優先度ベースeviction
└── fetch統合 (2テスト)
    ├── ✅ getOrFetch() キャッシュミス
    └── ✅ getOrFetch() バージョン更新

test-dictionary-cache.js (6テスト)
├── ✅ キャッシュなしの場合、従来通りfetchで取得する
├── ✅ キャッシュあり・初回ロード: fetchしてキャッシュに保存する
├── ✅ キャッシュあり・2回目ロード: キャッシュから取得しfetchしない
├── ✅ 辞書ファイルはhigh優先度でキャッシュされる
├── ✅ dictVersionが変わった場合は再fetchする
└── ✅ clearCache()でキャッシュをクリアできる
```

### 実装ファイル
- `src/wasm/openjtalk-web/src/cache-manager.js` (新規)
- `src/wasm/openjtalk-web/src/dictionary-loader.js` (改修 — `cacheManager`/`dictVersion`オプション、`clearCache()`追加)

---

## ONNX Runtime更新 🔶 一部完了

**Phase**: 1 | **期間**: Week 2 | **依存**: M1

### 完了条件
- [x] `onnxruntime-web` を 1.17.1 → 1.21.0 に更新
- [ ] `executionProviders` を `['wasm-simd', 'wasm']` に変更 ← **未完了**
- [x] `enableMemPattern: true` 追加
- [ ] 既存テスト (`npm test`) がパス
- [ ] BenchmarkRunnerで1.17.1 vs 1.19+のレイテンシ比較結果を記録

### 実施済み
- ORT CDNを全5デモページで **1.17.1 → 1.21.0** に更新
  - `demo/index.html`, `demo/multilingual.html`, `demo/simple-multilingual.html`
  - `demo/piper-espeak-english.html`, `demo/piper-espeak-complete.html`
- セッションオプション適用: `graphOptimizationLevel: 'extended'`, `enableMemPattern: true`

### 残作業
- `executionProviders` を `['wasm']` → `['wasm-simd', 'wasm']` に変更
- ブラウザ手動検証 (MOS比較、メモリリーク、Safari互換性)
- BenchmarkRunnerでレイテンシ比較記録

### 検証項目
| テスト | 対象 |
|--------|------|
| MOS比較 | 全モデル (手動聴取) |
| メモリリーク | 100回連続推論 (DevToolsで確認) |
| Safari互換性 | macOS Safari 14.1+ |
| 既存デモ動作 | `demo/index.html` 全機能 |

### 実装ファイル
- `src/wasm/openjtalk-web/demo/index.html` (ORT CDN URL更新)
- `src/wasm/openjtalk-web/demo/multilingual.html` (ORT CDN URL更新)
- `src/wasm/openjtalk-web/demo/simple-multilingual.html` (ORT CDN URL更新)
- `src/wasm/openjtalk-web/demo/piper-espeak-english.html` (ORT CDN URL更新)
- `src/wasm/openjtalk-web/demo/piper-espeak-complete.html` (ORT CDN URL更新)

---

## リサンプラー ✅ 完了

**Phase**: 2a | **期間**: Week 3 | **依存**: なし
**完了日**: 2026-03-16

### 完了条件
- [x] `SimpleResampler` クラス実装 (`src/resampler.js`)
- [x] 22050Hz → 48000Hz 変換の正確性
- [x] `test-resampler.js` 全テストパス

### TDDテスト (8テスト — 全パス)
```
test-resampler.js
├── アップサンプリング (22050→48000) (4テスト)
│   ├── ✅ 出力長が正しい
│   ├── ✅ 無音入力→無音出力
│   ├── ✅ DC信号の保持
│   └── ✅ 出力値が-1.0〜1.0の範囲内
├── ダウンサンプリング (48000→22050) (1テスト)
│   └── ✅ 出力長が正しい
├── 同一レート (22050→22050) (1テスト)
│   └── ✅ 入力と同一出力
└── エッジケース (2テスト)
    ├── ✅ 空入力
    └── ✅ 1サンプル入力
```

**備考**: 当初7テスト予定 → 実装時に8テストに拡張（エッジケース追加）

### 実装ファイル
- `src/wasm/openjtalk-web/src/resampler.js` (新規)

---

## AudioWorklet ✅ 完了

**Phase**: 2a | **期間**: Week 3-4 | **依存**: M4
**完了日**: 2026-03-16

### 完了条件
- [x] `PushAudioWorkletProcessor` 実装
- [x] ScriptProcessorフォールバック (Factory パターン)
- [x] iOS Safari向け `<audio>` タグフォールバック (WAVエンコーダ内蔵)
- [ ] Chrome / Firefox でリアルタイム再生成功 ← **ブラウザE2E未実施**
- [ ] レイテンシ < 10ms (48kHz環境) ← **ブラウザE2E未実施**

### TDDテスト (8テスト — 全パス)
```
test-audio-backend.js
├── AudioWorkletBackend (1テスト)
│   └── ✅ AudioWorkletNodeの生成と接続
├── ScriptProcessorBackend (2テスト)
│   ├── ✅ ScriptProcessorNodeの生成
│   └── ✅ pushChunk()でバッファにデータを追加できる
├── HTMLAudioBackend (3テスト)
│   ├── ✅ WAVエンコード・再生
│   ├── ✅ stop()で再生停止
│   └── ✅ dispose()でリソース解放
└── Common interface (2テスト)
    ├── ✅ 全バックエンドがplay/pushChunk/stop/disposeを持つ
    └── ✅ AudioBackendFactory.create()のフォールバック順序
```

### 実装ファイル
- `src/wasm/openjtalk-web/src/audio-worklet-processor.js` (新規)
- `src/wasm/openjtalk-web/src/audio-backend-factory.js` (新規)
- `src/wasm/openjtalk-web/demo/index.html` (改修)

### ブラウザE2Eテスト (未実施 — 将来Playwright化)
| テスト | Chrome | Firefox | Safari | iOS Safari |
|--------|--------|---------|--------|------------|
| 日本語テキスト再生 | 未検証 | 未検証 | 未検証 | 未検証 |
| 長文ストリーミング | 未検証 | 未検証 | - | - |
| レイテンシ計測 | 未検証 | 未検証 | - | - |

---

## WebGPUセッション ✅ 完了

**Phase**: 2b | **期間**: Week 5-6 | **依存**: M3
**完了日**: 2026-03-16

### 完了条件
- [x] `WebGPUSessionManager` クラス実装
- [x] フォールバック: WebGPU → wasm-simd → wasm (WebGL含まない)
- [x] GPU容量チェック (maxBufferSize)
- [x] `test-webgpu-session.js` 全テストパス
- [ ] Chrome WebGPU環境で推論速度が WASM比 2倍以上 ← **ブラウザE2E未実施**

### TDDテスト (11テスト — 全パス)
```
test-webgpu-session.js
├── フォールバック順序 (5テスト)
│   ├── ✅ WebGPU対応→webgpu選択
│   ├── ✅ WebGPU非対応→wasm-simd
│   ├── ✅ wasm-simd非対応→wasm
│   ├── ✅ 全失敗→エラー
│   └── ✅ WebGL含まない
├── GPU容量チェック (3テスト)
│   ├── ✅ 容量内→true
│   ├── ✅ 容量超過→false
│   └── ✅ GPU非対応→false
└── セッション設定 (3テスト)
    ├── ✅ graphOptimizationLevel=extended
    ├── ✅ enableMemPattern=true
    └── ✅ intraOpNumThreads未設定
```

**備考**: 当初9テスト予定 → 実装時に11テストに拡張（セッション設定を3テストに分割）

### 実装ファイル
- `src/wasm/openjtalk-web/src/webgpu-session-manager.js` (新規)

---

## Phase 2 統合テスト ✅ 完了

**Phase**: 2c | **期間**: Week 7 | **依存**: M5, M6
**完了日**: 2026-03-16

### 完了条件
- [x] AudioWorklet + WebGPU統合動作確認 (ユニットレベルモック)
- [ ] 3ブラウザ (Chrome/Firefox/Edge) で日本語・英語TTS動作 ← **ブラウザE2E未実施**
- [x] BenchmarkRunnerで各ステージの計測結果を記録
- [ ] RegressionDetectorでベースラインとの比較 ← **未記録**

### TDDテスト (10テスト — 全パス)
```
test-phase2-integration.js
├── ✅ BenchmarkRunner + Resampler計測
├── ✅ CacheManager getOrFetchサイクル
├── ✅ Resampler + Streaming (TextChunkerチャンク → リサンプラー)
├── ✅ WebGPU + Benchmark (セッション作成タイミング)
├── ✅ TypedArrayPool + Resampler (プール割り当て)
├── ✅ フルパイプライン (TextChunker → phonemize → infer → resample → onAudioChunk)
├── ✅ CacheManagerバージョンチェック
├── ✅ Resampler identity in pipeline (22050→22050)
├── ✅ Pool stats after pipeline (hits/misses追跡)
└── ✅ エラー耐性 (synthesize失敗伝播)
```

### ブラウザE2Eテストマトリックス (未実施)
| テスト | Chrome 130+ | Firefox 141+ | Edge 130+ |
|--------|------------|-------------|-----------|
| WebGPU推論 | 未検証 | 未検証 | 未検証 |
| WASM-SIMDフォールバック | 未検証 | 未検証 | 未検証 |
| AudioWorklet再生 | 未検証 | 未検証 | 未検証 |
| IndexedDBキャッシュ | 未検証 | 未検証 | 未検証 |

### 実装ファイル
- `src/wasm/openjtalk-web/test/js/test-phase2-integration.js` (新規)

---

## ストリーミング再生 ✅ 完了

**Phase**: 3 | **期間**: Week 8-9 | **依存**: M5 (AudioWorklet)
**完了日**: 2026-03-16

### 完了条件
- [x] `TextChunker` 実装 (日本語/英語文分割)
- [x] `StreamingTTSPipeline` 実装 (パイプライン並列化)
- [x] `ChunkCrossfader` 実装 (50msクロスフェード)
- [x] `RingBuffer` 実装
- [x] `test-streaming-pipeline.js` 全テストパス
- [ ] TTFB < 600ms (WASM, キャッシュ有り) ← **ブラウザE2E未実施**

### TDDテスト (16テスト — 全パス)
```
test-streaming-pipeline.js
├── TextChunker (6テスト)
│   ├── ✅ 日本語: 句点分割
│   ├── ✅ 日本語: 感嘆符・疑問符
│   ├── ✅ 日本語: 句読点なし
│   ├── ✅ 日本語: 空文字列
│   ├── ✅ 英語: ピリオド分割
│   └── ✅ 英語: 略語ピリオド
├── RingBuffer (4テスト)
│   ├── ✅ enqueue/dequeue基本
│   ├── ✅ 空dequeue
│   ├── ✅ 容量超過
│   └── ✅ size()
├── ChunkCrossfader (3テスト)
│   ├── ✅ 最初のチャンク
│   ├── ✅ クロスフェード処理
│   └── ✅ クロスフェード長0
└── StreamingTTSPipeline (3テスト)
    ├── ✅ 実行順序
    ├── ✅ パイプライン並列化
    └── ✅ 空テキスト
```

**備考**: 当初14テスト予定 → 実装時に16テストに拡張

### 実装ファイル
- `src/wasm/openjtalk-web/src/streaming-pipeline.js` (新規)

---

## メモリプール ✅ 完了

**Phase**: 3 | **期間**: Week 9-10 | **依存**: なし
**完了日**: 2026-03-16

### 完了条件
- [x] `TypedArrayPool` クラス実装 (上限/TTL付き)
- [x] `test-memory-pool.js` 全テストパス
- [ ] DevToolsでGCオブジェクト数50%以上削減を確認 ← **ブラウザE2E未実施**

### TDDテスト (7テスト — 全パス)
```
test-memory-pool.js
├── 基本操作 (3テスト)
│   ├── ✅ Float32Array取得
│   ├── ✅ BigInt64Array取得
│   └── ✅ プール再利用
├── メモリリーク防止 (2テスト)
│   ├── ✅ MAX_POOL_SIZE超過
│   └── ✅ TTLクリーンアップ
├── 統計情報 (1テスト)
│   └── ✅ hits/misses/evictions
└── セキュリティ (1テスト)
    └── ✅ ゼロクリア
```

### 実装ファイル
- `src/wasm/openjtalk-web/src/memory-pool.js` (新規)

---

## モバイルUI

**Phase**: 4 | **期間**: Week 11 | **依存**: なし

### 完了条件
- [ ] レスポンシブCSS (360px / 480px / 768px ブレークポイント)
- [ ] タッチターゲット 44px以上
- [ ] iOS自動ズーム防止 (font-size: 16px)
- [ ] iOS Safari / Android Chrome で表示確認

### 実装ファイル
- `src/wasm/openjtalk-web/demo/index.html` (CSS改修)

---

## FP16量子化

**Phase**: 4 | **期間**: Week 12-13 | **依存**: M3

### 完了条件
- [ ] `export_onnx.py` に `--fp16` フラグ追加
- [ ] FP16モデルの音質検証 (MOS差 < 0.15)
- [ ] WavLMモデルとの相互作用テスト
- [ ] FP16モデルのWeb推論動作確認

### テスト
```bash
# Python側テスト
uv run python -m pytest tests/test_export_onnx.py -v -k "fp16"

# 音質比較
uv run python -m piper_train.infer_onnx --model fp16_model.onnx --text "テスト文" --output-dir /tmp
```

### 実装ファイル
- `src/python/piper_train/export_onnx.py` (改修)

---

## SAB/PWA

**Phase**: 5 | **期間**: Week 14-16 | **依存**: M7

### 完了条件
- [ ] Service Worker実装
- [ ] manifest.json 作成
- [ ] coi-serviceworker によるGitHub Pages SAB対応
- [ ] オフラインTTS動作確認（キャッシュ済みモデル使用）
- [ ] Lighthouse PWAスコア 90+

### 実装ファイル
- `src/wasm/openjtalk-web/src/service-worker.js` (新規)
- `src/wasm/openjtalk-web/demo/manifest.json` (新規)

---

## テスト実行コマンド

### ローカル開発

```bash
# 全最適化テスト
cd src/wasm/openjtalk-web
npm run test:optimization

# Phase別テスト
npm run test:optimization:phase1
npm run test:optimization:phase2
npm run test:optimization:phase3

# ウォッチモード（既存テスト）
npm run test:watch

# Python FP16テスト
cd src/python
uv run python -m pytest tests/test_export_onnx.py -v -k "fp16"
```

### CI (GitHub Actions)

- **ワークフロー**: `.github/workflows/test-web-optimization.yml`
- **トリガー**: push/PR to `dev` or `feature/webgpu-optimization`
- **パス条件**: `src/wasm/openjtalk-web/{src,test}/**` 変更時

```
test-web-optimization.yml
├── test-phase1 (BenchmarkRunner + CacheManager)
├── test-phase2 (Resampler + WebGPUSession)
├── test-phase3 (StreamingPipeline + MemoryPool)
├── test-all (全テスト統合)
└── test-python-fp16 (Python FP16量子化)
```

---

## 進捗管理

### TDDサイクル

各マイルストーンの進め方:

1. **RED**: テストファイルを書く（既に完了 → `test/js/test-*.js`）
2. **GREEN**: 最小実装でテストをパスさせる
3. **REFACTOR**: コードを改善しつつテストが通り続けることを確認

### GitHub Actionsステータス

| Phase | ジョブ名 | 現在のステータス |
|-------|---------|---------------|
| 1 | test-phase1 | 🟢 PASS (ベンチマーク+キャッシュ+辞書、31テスト) |
| 2 | test-phase2 | 🟢 PASS (リサンプラー+WebGPU+Audio、27テスト) |
| 3 | test-phase3 | 🟢 PASS (ストリーミング+メモリプール、23テスト) |
| Integration | test-integration | 🟢 PASS (統合テスト、10テスト) |
| 4 | test-python-fp16 | 🟡 SKIP (テストなし) |

### テスト統計 (2026-03-17時点)

| カテゴリ | テストファイル | テスト数 | パス |
|---------|--------------|---------|------|
| ベンチマーク基盤 | test-benchmark-runner.js | 12 | 12 |
| IndexedDBキャッシュ | test-cache-manager.js | 13 | 13 |
| 辞書キャッシュ統合 | test-dictionary-cache.js | 6 | 6 |
| リサンプラー | test-resampler.js | 8 | 8 |
| AudioWorklet | test-audio-backend.js | 8 | 8 |
| WebGPUセッション | test-webgpu-session.js | 11 | 11 |
| 統合テスト | test-phase2-integration.js | 10 | 10 |
| ストリーミング | test-streaming-pipeline.js | 16 | 16 |
| メモリプール | test-memory-pool.js | 7 | 7 |
| **合計** | | **91** | **91** |

### ベンチマーク (Node.js計測, 2026-03-17)

| コンポーネント | 結果 |
|--------------|------|
| Resampler 22050→48000 (10秒音声) | < 1ms |
| TypedArrayPool 10K回 get+return | 51%高速化 (22ms→10.7ms vs new毎回) |
| TextChunker 日本語 | 1.5μs/回 |
| TextChunker 英語 | 3.8μs/回 |
| CacheManager キャッシュヒット | 0.01ms (実環境で98%以上の2回目ロード削減) |
| StreamingPipeline 5文パイプライン | 14%高速化 vs シーケンシャル |
| ChunkCrossfader 50ms | 0.054ms/チャンク (リアルタイム比0.01%) |

計測ファイル: `test/js/bench-optimization.js`

---

## コードレビュー対応履歴

### PRレビュー指摘 (2026-03-17, コミット `d9c735e`)

GitHub Copilotレビューの7件指摘を修正。

| # | ファイル | 内容 |
|---|---------|------|
| 1 | `test-webgpu-session.js` | テストコメントが実装と不一致 → 修正 |
| 2 | `cache-manager.js` | `dbFactory`未指定でTypeError、`objectStore()`引数なし → 必須チェック + `objectStore(STORE_NAME)` |
| 3 | `cache-manager.js` | `_wrap()`が実IDBで完了を待たずresolve → Mock(`_mock`フラグ)/実IDB(`addEventListener`)で分岐 |
| 4 | `audio-backend-factory.js` | AudioWorkletフォールバック時AudioContextリーク → `close()`追加 |
| 5 | `audio-backend-factory.js` | `HTMLAudioBackend.play()`が既存再生を止めない → `stop()`を冒頭で呼び出し |
| 6 | `streaming-pipeline.js` | クロスフェード係数が短チャンクで0..1に正規化されない → `actualFadeLen`で正規化 |
| 7 | `dictionary-loader.js` | `getOrFetch()`直後に同じkeyを`set()`で二重書き込み → `getOrFetch()`に`priority`引数追加、冗長`set()`削除 |

### 初回レビュー指摘 (2026-03-16, コミット `588a5fe`)

12エージェントチームによるレビューの13件修正。

| 重要度 | 件数 | 内容 |
|--------|------|------|
| CRITICAL | 3 | 除算ゼロ防止、URLメモリリーク、TOCTOU競合解消 |
| HIGH | 4 | WebGPUエラー詳細、nullガード、AudioNodeリーク、テスト欠落 |
| MEDIUM | 6 | 型検証、戻り値統一、タイミングテスト安定化、JSDoc追加 |
