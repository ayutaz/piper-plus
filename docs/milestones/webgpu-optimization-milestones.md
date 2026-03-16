# WebGPU最適化マイルストーン

**ブランチ**: `feature/webgpu-optimization`
**開始日**: 2026-03-16
**TDD方針**: テストを先に書き、実装後にパスさせる
**CI**: `.github/workflows/test-web-optimization.yml`

---

## マイルストーン一覧

| MS | Phase | 名前 | 期間 | テストファイル | 完了条件 |
|----|-------|------|------|-------------|---------|
| M1 | 1 | ベンチマーク基盤 | Week 1 | `test-benchmark-runner.js` | 全テストパス |
| M2 | 1 | IndexedDBキャッシュ | Week 1-2 | `test-cache-manager.js` | 全テストパス |
| M3 | 1 | ONNX Runtime更新 | Week 2 | 手動検証 | 1.19+で既存テスト通過 |
| M4 | 2a | リサンプラー | Week 3 | `test-resampler.js` | 全テストパス |
| M5 | 2a | AudioWorklet | Week 3-4 | ブラウザE2E | Chrome/Firefoxで再生成功 |
| M6 | 2b | WebGPUセッション | Week 5-6 | `test-webgpu-session.js` | 全テストパス |
| M7 | 2c | 統合テスト | Week 7 | E2E | 3ブラウザで動作 |
| M8 | 3 | ストリーミング | Week 8-9 | `test-streaming-pipeline.js` | 全テストパス |
| M9 | 3 | メモリプール | Week 9-10 | `test-memory-pool.js` | 全テストパス |
| M10 | 4 | モバイルUI | Week 11 | 手動検証 | iOS/Android表示確認 |
| M11 | 4 | FP16量子化 | Week 12-13 | Python pytest | MOS差 < 0.15 |
| M12 | 5 | SAB/PWA | Week 14-16 | E2E | オフライン動作 |

---

## M1: ベンチマーク基盤

**Phase**: 1 | **期間**: Week 1 | **依存**: なし

### 完了条件
- [ ] `BenchmarkRunner` クラス実装 (`src/benchmark.js`)
- [ ] `RegressionDetector` クラス実装 (メトリック別しきい値)
- [ ] `test-benchmark-runner.js` 全テストパス
- [ ] GitHub Actions `test-web-optimization.yml` の Phase 1 ジョブがグリーン

### TDDテスト (7テスト)
```
test-benchmark-runner.js
├── BenchmarkRunner
│   ├── measureAsync()で非同期関数の実行時間を計測できる
│   ├── 複数ステージを順番に計測できる
│   ├── getSummary()はdurationをms文字列で返す
│   └── reset()で計測データをクリアできる
└── RegressionDetector
    ├── しきい値内の変動はリグレッションとして検出しない
    ├── Inference: 10%超過で検出
    ├── WASM Load: 5%超過で検出
    ├── 未知メトリックはデフォルトしきい値を使用
    ├── 20%超過はcritical
    └── 20%以下の超過はhigh
```

### 実装ファイル
- `src/wasm/openjtalk-web/src/benchmark.js` (新規)

---

## M2: IndexedDBキャッシュ

**Phase**: 1 | **期間**: Week 1-2 | **依存**: なし

### 完了条件
- [ ] `CacheManager` クラス実装 (`src/cache-manager.js`)
- [ ] iOS 50MB/origin制限の対応（優先度ベースeviction）
- [ ] `test-cache-manager.js` 全テストパス
- [ ] `dictionary-loader.js` をキャッシュ統合に改修
- [ ] 2回目以降のロード時間が95%以上削減されることを確認

### TDDテスト (12テスト)
```
test-cache-manager.js
├── 基本CRUD操作 (4テスト)
│   ├── set()/get()
│   ├── 存在しないキー
│   ├── 上書き
│   └── delete()
├── バージョン管理 (3テスト)
│   ├── isValid() 一致
│   ├── isValid() 不一致
│   └── isValid() キー不在
├── ストレージ容量管理 (2テスト)
│   ├── getUsage()
│   └── clear()
├── iOS制限対応 (2テスト)
│   ├── 50MB超過処理
│   └── 優先度ベースeviction
└── fetch統合 (2テスト)
    ├── getOrFetch() キャッシュミス
    └── getOrFetch() バージョン更新
```

### 実装ファイル
- `src/wasm/openjtalk-web/src/cache-manager.js` (新規)
- `src/wasm/openjtalk-web/src/dictionary-loader.js` (改修)

---

## M3: ONNX Runtime更新

**Phase**: 1 | **期間**: Week 2 | **依存**: M1

### 完了条件
- [ ] `onnxruntime-web` を 1.17.1 → 1.19+ に更新
- [ ] `executionProviders` を `['wasm-simd', 'wasm']` に変更
- [ ] `enableMemPattern: true` 追加
- [ ] 既存テスト (`npm test`) がパス
- [ ] BenchmarkRunnerで1.17.1 vs 1.19+のレイテンシ比較結果を記録

### 検証項目
| テスト | 対象 |
|--------|------|
| MOS比較 | 全モデル (手動聴取) |
| メモリリーク | 100回連続推論 (DevToolsで確認) |
| Safari互換性 | macOS Safari 14.1+ |
| 既存デモ動作 | `demo/index.html` 全機能 |

### 実装ファイル
- `src/wasm/openjtalk-web/demo/index.html` (ORT CDN URL更新)

---

## M4: リサンプラー

**Phase**: 2a | **期間**: Week 3 | **依存**: なし

### 完了条件
- [ ] `SimpleResampler` クラス実装 (`src/resampler.js`)
- [ ] 22050Hz → 48000Hz 変換の正確性
- [ ] `test-resampler.js` 全テストパス

### TDDテスト (7テスト)
```
test-resampler.js
├── アップサンプリング (22050→48000)
│   ├── 出力長が正しい
│   ├── 無音入力→無音出力
│   ├── DC信号の保持
│   └── 出力値が-1.0〜1.0の範囲内
├── ダウンサンプリング (48000→22050)
│   └── 出力長が正しい
├── 同一レート (22050→22050)
│   └── 入力と同一出力
└── エッジケース
    ├── 空入力
    └── 1サンプル入力
```

### 実装ファイル
- `src/wasm/openjtalk-web/src/resampler.js` (新規)

---

## M5: AudioWorklet

**Phase**: 2a | **期間**: Week 3-4 | **依存**: M4

### 完了条件
- [ ] `PushAudioWorkletProcessor` 実装
- [ ] ScriptProcessorフォールバック (Factory パターン)
- [ ] iOS Safari向け `<audio>` タグフォールバック
- [ ] Chrome / Firefox でリアルタイム再生成功
- [ ] レイテンシ < 10ms (48kHz環境)

### 実装ファイル
- `src/wasm/openjtalk-web/src/audio-worklet-processor.js` (新規)
- `src/wasm/openjtalk-web/src/audio-backend-factory.js` (新規)
- `src/wasm/openjtalk-web/demo/index.html` (改修)

### ブラウザE2Eテスト (手動 → 将来Playwright化)
| テスト | Chrome | Firefox | Safari | iOS Safari |
|--------|--------|---------|--------|------------|
| 日本語テキスト再生 | ✅ | ✅ | ✅ | ✅ (fallback) |
| 長文ストリーミング | ✅ | ✅ | - | - |
| レイテンシ計測 | < 10ms | < 10ms | - | - |

---

## M6: WebGPUセッション

**Phase**: 2b | **期間**: Week 5-6 | **依存**: M3

### 完了条件
- [ ] `WebGPUSessionManager` クラス実装
- [ ] フォールバック: WebGPU → wasm-simd → wasm
- [ ] GPU容量チェック (maxBufferSize / maxStorageBufferBindingSize)
- [ ] `test-webgpu-session.js` 全テストパス
- [ ] Chrome WebGPU環境で推論速度が WASM比 2倍以上

### TDDテスト (9テスト)
```
test-webgpu-session.js
├── フォールバック順序 (5テスト)
│   ├── WebGPU対応→webgpu選択
│   ├── WebGPU非対応→wasm-simd
│   ├── wasm-simd非対応→wasm
│   ├── 全失敗→エラー
│   └── WebGL含まない
├── GPU容量チェック (3テスト)
│   ├── 容量内→true
│   ├── 容量超過→false
│   └── GPU非対応→false
└── セッション設定 (3テスト)
    ├── graphOptimizationLevel=extended
    ├── enableMemPattern=true
    └── intraOpNumThreads未設定
```

### 実装ファイル
- `src/wasm/openjtalk-web/src/webgpu-session-manager.js` (新規)

---

## M7: Phase 2 統合テスト

**Phase**: 2c | **期間**: Week 7 | **依存**: M5, M6

### 完了条件
- [ ] AudioWorklet + WebGPU統合動作確認
- [ ] 3ブラウザ (Chrome/Firefox/Edge) で日本語・英語TTS動作
- [ ] BenchmarkRunnerで各ステージの計測結果を記録
- [ ] RegressionDetectorでベースラインとの比較

### テストマトリックス
| テスト | Chrome 130+ | Firefox 141+ | Edge 130+ |
|--------|------------|-------------|-----------|
| WebGPU推論 | ✅ | ⚠️ (flag) | ✅ |
| WASM-SIMDフォールバック | ✅ | ✅ | ✅ |
| AudioWorklet再生 | ✅ | ✅ | ✅ |
| IndexedDBキャッシュ | ✅ | ✅ | ✅ |

---

## M8: ストリーミング再生

**Phase**: 3 | **期間**: Week 8-9 | **依存**: M5 (AudioWorklet)

### 完了条件
- [ ] `TextChunker` 実装 (日本語/英語文分割)
- [ ] `StreamingTTSPipeline` 実装 (パイプライン並列化)
- [ ] `ChunkCrossfader` 実装 (50msクロスフェード)
- [ ] `RingBuffer` 実装
- [ ] `test-streaming-pipeline.js` 全テストパス
- [ ] TTFB < 600ms (WASM, キャッシュ有り)

### TDDテスト (14テスト)
```
test-streaming-pipeline.js
├── TextChunker (6テスト)
│   ├── 日本語: 句点分割
│   ├── 日本語: 感嘆符・疑問符
│   ├── 日本語: 句読点なし
│   ├── 日本語: 空文字列
│   ├── 英語: ピリオド分割
│   └── 英語: 略語ピリオド
├── RingBuffer (4テスト)
│   ├── enqueue/dequeue基本
│   ├── 空dequeue
│   ├── 容量超過
│   └── size()
├── ChunkCrossfader (3テスト)
│   ├── 最初のチャンク
│   ├── クロスフェード処理
│   └── クロスフェード長0
└── StreamingTTSPipeline (3テスト)
    ├── 実行順序
    ├── パイプライン並列化
    └── 空テキスト
```

### 実装ファイル
- `src/wasm/openjtalk-web/src/streaming-pipeline.js` (新規)

---

## M9: メモリプール

**Phase**: 3 | **期間**: Week 9-10 | **依存**: なし

### 完了条件
- [ ] `TypedArrayPool` クラス実装 (上限/TTL付き)
- [ ] `test-memory-pool.js` 全テストパス
- [ ] DevToolsでGCオブジェクト数50%以上削減を確認

### TDDテスト (7テスト)
```
test-memory-pool.js
├── 基本操作 (3テスト)
│   ├── Float32Array取得
│   ├── BigInt64Array取得
│   └── プール再利用
├── メモリリーク防止 (2テスト)
│   ├── MAX_POOL_SIZE超過
│   └── TTLクリーンアップ
├── 統計情報 (1テスト)
│   └── hits/misses/evictions
└── セキュリティ (1テスト)
    └── ゼロクリア
```

### 実装ファイル
- `src/wasm/openjtalk-web/src/memory-pool.js` (新規)

---

## M10: モバイルUI

**Phase**: 4 | **期間**: Week 11 | **依存**: なし

### 完了条件
- [ ] レスポンシブCSS (360px / 480px / 768px ブレークポイント)
- [ ] タッチターゲット 44px以上
- [ ] iOS自動ズーム防止 (font-size: 16px)
- [ ] iOS Safari / Android Chrome で表示確認

### 実装ファイル
- `src/wasm/openjtalk-web/demo/index.html` (CSS改修)

---

## M11: FP16量子化

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

## M12: SAB/PWA

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
| 1 | test-phase1 | 🔴 FAIL (未実装) |
| 2 | test-phase2 | 🔴 FAIL (未実装) |
| 3 | test-phase3 | 🔴 FAIL (未実装) |
| 4 | test-python-fp16 | 🟡 SKIP (テストなし) |

→ 実装が進むにつれて 🔴 → 🟢 に変わる
