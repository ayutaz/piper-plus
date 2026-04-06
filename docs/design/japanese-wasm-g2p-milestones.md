# Japanese WASM G2P Integration — マイルストーン

> 参照: [技術調査・対応方針](./japanese-wasm-g2p-integration.md)

---

## チケット一覧・進捗

| チケット | タイトル | マイルストーン | 状態 | 依存 |
|---------|---------|--------------|------|------|
| [M1-1](tickets/M1-1-wasm-loader.md) | `_init()` に Rust WASM ローダー追加 | M1 | TODO | なし |
| [M1-2](tickets/M1-2-text-to-phoneme-ids.md) | `_textToPhonemeIds()` に日本語分岐追加 | M1 | TODO | M1-1 |
| [M1-3](tickets/M1-3-language-detection.md) | 言語検出の統合 | M1 | TODO | M1-1 |
| [M1-4](tickets/M1-4-dispose.md) | `dispose()` でのリソース解放 | M1 | TODO | M1-1 |
| [M2-1](tickets/M2-1-wasm-loader-tests.md) | WASM ローダーのユニットテスト | M2 | TODO | M1-1 |
| [M2-2](tickets/M2-2-phonemize-branch-tests.md) | phonemize 分岐・言語検出・dispose テスト | M2 | TODO | M1-2, M1-3, M1-4 |
| [M2-3](tickets/M2-3-ci-integration.md) | CI にテスト追加 | M2 | TODO | M2-1, M2-2 |
| [M3-1](tickets/M3-1-demo-ja-verification.md) | デモページ日本語動作確認 | M3 | TODO | M2-3 |
| [M3-2](tickets/M3-2-regression-other-langs.md) | 他言語回帰テスト | M3 | TODO | M2-3 |

---

## M1: PiperPlus に Rust WASM phonemizer を統合

**目標**: `PiperPlus._init()` で Rust WASM (`WasmPhonemizer`) を自動ロードし、日本語 G2P として使用する。他言語は既存の JS G2P (`@piper-plus/g2p`) をそのまま使う。

**チケット**: [M1-1](tickets/M1-1-wasm-loader.md) → [M1-2](tickets/M1-2-text-to-phoneme-ids.md) → [M1-3](tickets/M1-3-language-detection.md) → [M1-4](tickets/M1-4-dispose.md)

### 一から設計するとしたら

現在の設計は「PiperPlus が内部で Rust WASM をロードし、日本語だけ特別扱いする」方式。一からやり直すなら以下を検討する:

1. **Rust WASM を全言語の G2P バックエンドにする**: `@piper-plus/g2p` の JS 実装を廃止し、Rust WASM の `WasmPhonemizer` を唯一の G2P とする。メリットは単一パスによる簡潔さ。デメリットは WASM バイナリ (19MB gzip) が全ユーザーに必須になること、ルールベース言語で JS の方が軽量であること。

2. **DI (Dependency Injection) パターンの統一**: `PiperPlus.initialize({ phonemizer })` で外部から phonemizer を注入し、PiperPlus は G2P の実装詳細を知らない設計。現在は openjtalkModule / wasmPhonemizer / G2P.create と3つの注入パスが混在しており複雑。理想は 1 つの PhonemizerInterface を定義し、Rust WASM / JS G2P / 将来の実装が同じインターフェースを実装する形。

3. **段階的ロード**: WASM バイナリのロードを初期化時ではなく、日本語テキストが初めて入力された時点で行う遅延ロード。初期化時間を短縮できるが、初回日本語合成のレイテンシが増加するトレードオフ。

**今回の方式の妥協点**: 日本語だけ特別パスを通す条件分岐が `_init()`, `_textToPhonemeIds()`, `synthesize()`, `dispose()` の4箇所に散らばる。しかし、既存の JS G2P エコシステム (npm パッケージ、テスト、CI) を壊さずに日本語を動かす最短経路でもある。

---

## M2: テスト

**目標**: M1 の全変更をテストでカバーし、CI で事前検知できるようにする。

**チケット**: [M2-1](tickets/M2-1-wasm-loader-tests.md) → [M2-2](tickets/M2-2-phonemize-branch-tests.md) → [M2-3](tickets/M2-3-ci-integration.md)

### 一から設計するとしたら

現在のテスト戦略は「外部依存 (WASM, fetch, ort, IndexedDB) をモックして Node.js で実行」。一からやり直すなら:

1. **ブラウザ E2E テストを第一級市民にする**: Playwright で実際の GitHub Pages デモを叩くテストを CI に組み込む。WASM ロード、ONNX 推論、音声出力まで通しで検証できる。Node.js ユニットテストはモック前提のため統合バグを見逃しやすい（今回の一連のバグがその証拠）。

2. **WASM ビルド成果物をテスト artifact として共有**: `wasm-build.yml` が WASM をビルドし、`test-webassembly.yml` がそれをダウンロードして使うパイプライン。現在は WASM テストが全てモックベースで、実際のバイナリとの互換性を検証できない。

3. **テストヘルパーの `_init()` バイパスを廃止**: `createInitializedInstance()` が private フィールドを直接代入するパターンを段階的に廃止し、`PiperPlus.initialize()` をモック付き環境で実際に呼ぶパターンに移行する。今回のスタブ監査で発覚した問題の根本原因。

---

## M3: デモページの動作確認

**目標**: GitHub Pages のデモページで日本語テキスト → 音声合成が動作する。

**チケット**: [M3-1](tickets/M3-1-demo-ja-verification.md) → [M3-2](tickets/M3-2-regression-other-langs.md)

### 一から設計するとしたら

手動ブラウザテストは再現性が低く属人的。一からやり直すなら:

1. **Playwright による自動 E2E**: デモページへのアクセス → テキスト入力 → 合成ボタン → 音声再生確認をスクリプト化。GitHub Actions で Chromium headless 実行。音声出力は Web Audio API のサンプル数やゼロでないことで検証。

2. **Audio regression テスト**: 既知の入力テキストに対する音声出力の統計的特徴 (長さ、RMS、スペクトラム) をスナップショットとして保存し、デプロイ前に比較。完全一致ではなく、しきい値ベースの比較で意図しない音質劣化を検知。

3. **多言語合成のスモークテスト**: 全6言語の短いテキストを合成し、音声長がゼロでないことを自動チェック。言語ごとに期待される最小音声長を設定。

---

## 依存関係図

```
M1-1 (WASM ローダー) ──────────────┐
  │                                 │
  ├─→ M1-2 (_textToPhonemeIds)     │
  │                                 │
  ├─→ M1-3 (言語検出)              │
  │                                 │
  └─→ M1-4 (dispose)               │
                                    │
       M2-1 (ローダーテスト) ←──────┘
         │
       M2-2 (分岐テスト) ←── M1-2, M1-3, M1-4
         │
       M2-3 (CI 統合) ←── M2-1, M2-2
         │
       ┌─┴─┐
  M3-1    M3-2
  (JA)    (回帰)
```

## 見積もり

| マイルストーン | チケット数 | 規模 |
|--------------|-----------|------|
| M1 (実装) | 4 | `index.js` 1ファイルの変更 (~50行追加) |
| M2 (テスト) | 3 | テスト1ファイル新規 + CI 更新 |
| M3 (確認) | 2 | デプロイ + ブラウザ確認 |
