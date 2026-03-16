# ブラウザ互換性マトリックス

WebGPU最適化機能のブラウザ互換性リファレンス。
詳細な最適化設計については [webgpu-optimization-plan.md](./webgpu-optimization-plan.md) を参照。

---

## 機能別サポート状況

| 機能 | Chrome 130+ | Firefox 141+ | Safari 18+ | iOS Safari 18+ | Edge 130+ |
|------|------------|-------------|-----------|----------------|-----------|
| WebGPU | ✅ | ⚠️ (flag) | ❌ | ❌ | ✅ |
| WASM SIMD | ✅ | ✅ | ✅ | ✅ | ✅ |
| AudioWorklet | ✅ | ✅ | ✅ | ⚠️ (制限あり) | ✅ |
| IndexedDB | ✅ | ✅ | ✅ | ⚠️ (50MB制限) | ✅ |
| SharedArrayBuffer | ✅ (COOP/COEP) | ✅ (COOP/COEP) | ✅ | ⚠️ | ✅ |
| Service Worker | ✅ | ✅ | ✅ | ✅ | ✅ |
| DecompressionStream | ✅ | ✅ | ✅ | ✅ | ✅ |

### 補足

- **WebGPU (Chrome/Edge)**: D3D12 (Windows), Metal (macOS), Vulkan (Linux) バックエンドに対応。Android版も Qualcomm/ARM GPU で利用可能。
- **WebGPU (Firefox)**: Vulkan バックエンド、`dom.webgpu.enabled` フラグで有効化が必要。実験的段階。
- **WebGPU (Safari)**: Apple は Safari 18+ (macOS Sequoia以降) で段階的展開中だが、プロダクション利用には不十分。
- **AudioWorklet (iOS Safari)**: 2026-Q1時点で未対応。将来対応予定（時期未定）。
- **SharedArrayBuffer**: `Cross-Origin-Opener-Policy` / `Cross-Origin-Embedder-Policy` ヘッダーの設定が必須。iOS Safari は全バージョンで未対応。

---

## フォールバック戦略

### 推論バックエンド

| 優先度 | プロバイダー | 対応ブラウザ | 期待速度 |
|--------|------------|------------|---------|
| 1 | WebGPU | Chrome/Edge 130+ | 2-4x baseline |
| 2 | WASM-SIMD | 全モダンブラウザ | 1x baseline |
| 3 | WASM | レガシー | 0.5x baseline |

**推論時間の目安** (日本語 61MB モデル):

| プロバイダー | 推論時間 |
|------------|---------|
| WebGPU | 400-800ms |
| WASM-SIMD | 1200-1800ms |
| WASM | 1500-2500ms |

> WebGL EP は ONNX Runtime Web 1.18+ で非推奨のため、フォールバック対象外。
> フォールバックは自動で行われ、WebGPU が利用不可の場合は WASM-SIMD、それも不可なら WASM へ切り替わる。

### 音声再生

| 優先度 | バックエンド | 対応ブラウザ | レイテンシ |
|--------|------------|------------|----------|
| 1 | AudioWorklet | Chrome/Firefox/Safari/Edge | < 10ms |
| 2 | ScriptProcessor | 全ブラウザ (deprecated) | ~185ms |
| 3 | HTMLAudioElement | iOS Safari fallback | 再生開始まで遅延 |

**レイテンシ詳細**:

| メトリック | ScriptProcessor (22kHz) | AudioWorklet (48kHz) | 改善度 |
|----------|------------------------|---------------------|--------|
| bufferSize | 4096 samples | 128 samples | 32倍 |
| レイテンシ | ~185ms | ~2.7ms | 68倍 |
| ジッター | ±20ms | ±1ms | 20倍 |

> AudioWorklet はブラウザのネイティブサンプルレート (通常48kHz) で動作するため、
> 推論出力 (22kHz) からのリサンプリング処理が必要。リサンプリングコストは別途 +10-30ms を見込む。

### キャッシュ

| プラットフォーム | IndexedDB容量 | 注意事項 |
|----------------|-------------|---------|
| Chrome/Edge | 60%+ of disk | 制限なし (実質) |
| Firefox | ~2GB | - |
| Safari | ~1GB | - |
| iOS Safari | **50MB/origin** | 優先度ベースeviction必須 |

**キャッシュ対象の総サイズ**:

| 資産 | サイズ |
|------|--------|
| OpenJTalk辞書 (8ファイル) | ~23MB |
| ONNXモデル (日本語) | 61MB |
| ONNXモデル (英語) | 26MB |
| **合計** | **~110MB** |

---

## iOS Safari 固有の制限と対策

| # | 制限 | 対策 |
|---|------|------|
| 1 | IndexedDB 50MB/origin | CacheManager の優先度eviction (辞書23MB + 使用中モデル1つのみキャッシュ) |
| 2 | AudioWorklet 未対応 (2026-Q1) | ScriptProcessor または HTMLAudioElement fallback |
| 3 | WebGPU 非対応 | WASM-SIMD fallback |
| 4 | ユーザージェスチャー必須 | 初回タップで `AudioContext.resume()` |
| 5 | SharedArrayBuffer 非対応 | `postMessage` + `Transferable` フォールバック |
| 6 | WASMメモリ ~1GB | モデル + 辞書合計を300MB以下に制限 |
| 7 | バックグラウンド停止 | `<audio>` タグ使用で再生継続 |

### iOS IndexedDB キャッシュ優先順位

50MB制限下での推奨キャッシュ戦略:

| 優先度 | 対象 | サイズ | 理由 |
|--------|------|--------|------|
| 1 (必須) | OpenJTalk辞書 | ~23MB | 言語切替で共用 |
| 2 (推奨) | 使用中のモデル (1言語) | 26-61MB | 頻繁に利用 |
| 3 (対象外) | 他言語モデル | - | オンデマンド fetch |

> 辞書 (23MB) + 英語モデル (26MB) = 49MB で50MB制限内に収まる。
> 日本語モデル (61MB) を単独でキャッシュする場合は辞書との合計が84MBとなり超過するため、
> 辞書のみキャッシュし、モデルはオンデマンド fetch とする選択肢もある。

---

## デスクトップブラウザ詳細

### Chrome / Edge 130+

最も完全なサポート。WebGPU + AudioWorklet + IndexedDB の全機能が利用可能。

| 機能 | 状況 | 備考 |
|------|------|------|
| WebGPU | ✅ 完全対応 | D3D12/Metal/Vulkan |
| WASM-SIMD | ✅ | ORT 1.19+ で最適化強化 |
| AudioWorklet | ✅ (Chrome 66+) | - |
| IndexedDB | ✅ | 端末容量の60%+を使用可能 |
| SharedArrayBuffer | ✅ | COOP/COEP 設定時 |

### Firefox 141+

WebGPU は実験的段階。WASM-SIMD による推論は安定。

| 機能 | 状況 | 備考 |
|------|------|------|
| WebGPU | ⚠️ フラグ有効時のみ | `dom.webgpu.enabled` Vulkan バックエンド |
| WASM-SIMD | ✅ | - |
| AudioWorklet | ✅ (Firefox 76+) | - |
| IndexedDB | ✅ | ~2GB |
| SharedArrayBuffer | ✅ | COOP/COEP 設定時 |

### Safari 18+

WebGPU は限定的。AudioWorklet は macOS で対応。

| 機能 | 状況 | 備考 |
|------|------|------|
| WebGPU | ⚠️ 部分的 | Metal (macOS Sequoia以降、段階的展開中) |
| WASM-SIMD | ✅ | - |
| AudioWorklet | ✅ (Safari 14.1+) | 部分的な制限あり |
| IndexedDB | ✅ | ~1GB |
| SharedArrayBuffer | ✅ | COOP/COEP 設定時 |

---

## モバイルブラウザ詳細

### Android Chrome

デスクトップ Chrome とほぼ同等の機能。WebGPU は Qualcomm/ARM GPU で利用可能。

| 機能 | 状況 | 備考 |
|------|------|------|
| WebGPU | ✅ (Chrome 130+) | GPU容量チェック推奨 |
| WASM-SIMD | ✅ | - |
| AudioWorklet | ✅ (Chrome 66+) | - |
| IndexedDB | ✅ | 端末容量の60% |

**GPUメモリの注意点**:

| デバイス分類 | VRAM | 26MBモデル | 61MBモデル |
|------------|------|----------|----------|
| ハイエンド (Snapdragon 8 Gen) | 512MB+ | ✅ | ⚠️ |
| ミッドレンジ | 256-512MB | ⚠️ | ❌ (WASM fallback) |

### iOS Safari 18+

最も制限が多い環境。WASM-SIMD fallback が主要な推論パス。

| 機能 | 状況 | 備考 |
|------|------|------|
| WebGPU | ❌ | WASM-SIMD にフォールバック |
| WASM-SIMD | ✅ | - |
| AudioWorklet | ❌ (2026-Q1) | ScriptProcessor / HTMLAudioElement fallback |
| IndexedDB | ⚠️ 50MB/origin | 優先度ベースキャッシュ必須 |
| SharedArrayBuffer | ❌ | postMessage + Transferable fallback |

---

## テスト環境

| ブラウザ | テスト方法 | 自動化 | 備考 |
|---------|----------|--------|------|
| Chrome | Playwright | ✅ (将来) | WebGPU テストは `--enable-features=Vulkan` フラグ付きで実行 |
| Firefox | Playwright | ✅ (将来) | WebGPU フラグ有効化が必要 |
| Safari | WebDriver | ⚠️ (macOS CI必要) | AudioWorklet の部分的制限に注意 |
| iOS Safari | 手動 | ❌ | 実機テスト推奨。50MB IndexedDB 制限の検証必須 |
| Android Chrome | 手動 / Playwright | ⚠️ | WebGPU は実機テスト推奨 |

### E2Eテストマトリックス (Phase 2完了時目標)

| テスト項目 | Chrome 130+ | Firefox 141+ | Safari 18+ | Edge 130+ |
|-----------|-------------|-------------|------------|-----------|
| 日本語テキスト → 音声出力 | ✅ | ✅ | ✅ | ✅ |
| 英語テキスト → 音声出力 | ✅ | ✅ | ✅ | ✅ |
| AudioWorklet 再生 | ✅ | ✅ | ⚠️ | ✅ |
| WebGPU 推論 | ✅ | ⚠️ | ⚠️ | ✅ |
| ScriptProcessor フォールバック | ✅ | ✅ | ✅ | ✅ |
| IndexedDB キャッシュ | ✅ | ✅ | ✅ | ✅ |

### モバイル E2Eテスト (Phase 4完了時目標)

| テスト項目 | iOS Safari | Android Chrome |
|-----------|-----------|---------------|
| タッチUI操作 | ✅ | ✅ |
| メモリ使用量 (<300MB) | ✅ | ✅ |
| IndexedDB キャッシュ (<50MB) | ✅ | - |
| バックグラウンド再生 | ⚠️ | ✅ |

---

## GitHub Pages デプロイ時の注意

### COOP/COEP ヘッダー

GitHub Pages ではカスタム HTTP ヘッダーを設定できないため、SharedArrayBuffer がデフォルトで無効。
[coi-serviceworker](https://github.com/nicbarker/coi-serviceworker) を使用して回避可能。

```
必要なヘッダー:
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Embedder-Policy: require-corp
```

### SharedArrayBuffer 有効化

| デプロイ先 | SAB対応 | 方法 |
|-----------|---------|------|
| GitHub Pages | ❌ (デフォルト) → ✅ | coi-serviceworker で回避 |
| Netlify / Vercel | ✅ | カスタムヘッダー設定 |
| 自前サーバー | ✅ | nginx/Apache でヘッダー設定 |

### COEP 有効時の CDN リソース

COEP: `require-corp` 設定時にクロスオリジンリソース (例: `cdn.jsdelivr.net` からの ONNX Runtime) がブロックされる可能性がある。

**対策**:
- ONNX Runtime をローカルバンドル化
- または CDN の CORS ヘッダー対応を確認

### WASM ファイルの MIME type

サーバーが `.wasm` ファイルに対して正しい MIME type を返すことを確認:

```
Content-Type: application/wasm
```

> GitHub Pages は `.wasm` ファイルに `application/wasm` を自動設定するため追加設定は不要。
> カスタムサーバーの場合は明示的な設定が必要。
