# Phase 2: ONNX エクスポート + 6 ランタイム対応

**マイルストーン**: [#12](https://github.com/ayutaz/peav-style-conditioning-research-style-conditioning-research/milestone/12) ([ayutaz/piper-plus#12](https://github.com/ayutaz/piper-plus/milestone/12))
**期日**: 2026-05-04
**Claude Code 工数目安**: 2〜3 日 (Agent 並列起動活用)
**前提**: Phase 1 全タスク完了 (`style_vector` conditioning 学習側統合)
**関連ドキュメント**: [`../../phase-2.md`](../../phase-2.md) / [`../../README.md`](../../README.md)

---

## 1. 概要

Phase 1 で `VitsModel.generator` に追加された `style_vector` conditioning を、推論用 ONNX グラフの入力として表面化し、6 ランタイム (Python / C++ / Rust / C# / Go / WASM) で利用可能にする。本 Phase は Phase 5 (fine-tune 実験 + ランタイム横断評価) の前提。

本家 `speaker_embedding` / `speaker_embedding_mask` で確立された mask パターン (Optional 入力、zeros fallback) をそのまま style_vector に適用することで、実装の対称性・レビュー容易性・後方互換性を担保する。

---

## 2. チケット一覧

| ID | タイトル | 対象 | 工数 | 依存 |
|----|--------|-----|------|------|
| [P2-T01](P2-T01.md) | ONNX エクスポート拡張 (`--style-vector-dim`, mask パターン) | `src/python/piper_train/export_onnx.py` | 4〜6h | Phase 1 完了 |
| [P2-T02](P2-T02.md) | Python ランタイム統合 (`PiperVoice.synthesize`) | `src/python_run/piper/voice.py`, `infer_onnx.py`, `http_server.py` | 2〜4h | T01 |
| [P2-T03](P2-T03.md) | C++ ランタイム統合 (`libpiper_plus` + C API + CLI) | `src/cpp/piper_plus.h`, `piper_plus_c_api.cpp`, `piper.cpp`, `main.cpp` | 6〜8h | T01 |
| [P2-T04](P2-T04.md) | Rust ランタイム統合 (`piper-core` + CLI + PyO3) | `src/rust/piper-core/src/engine.rs`, `piper-cli/src/main.rs`, `piper-python/src/lib.rs` | 4〜6h | T01 |
| [P2-T05](P2-T05.md) | C# ランタイム統合 (`PiperPlus.Core` + CLI) | `src/csharp/PiperPlus.Core/Inference/*.cs`, `PiperPlus.Cli/Program.cs` | 4〜6h | T01 |
| [P2-T06](P2-T06.md) | Go ランタイム統合 (`piperplus` + `phonemize` + CLI) | `src/go/piperplus/*.go`, `cmd/piper-plus/main.go` | 4〜6h | T01 |
| [P2-T07](P2-T07.md) | WASM/JS ランタイム統合 (npm: `piper-plus` + `piper-wasm`) | `src/wasm/openjtalk-web/src/index.js`, `src/rust/piper-wasm/src/lib.rs`, `types/index.d.ts` | 4〜6h | T01, T04 |
| [P2-T08](P2-T08.md) | クロスランタイム互換性テスト (byte-for-byte 一致検証) | `tests/cross_runtime/test_style_vector_compat.py` | 3〜4h | T01〜T07 |

**Claude Code 合計**:
- 逐次実施: 約 31〜46 時間 (約 4〜6 日)
- 並列 Agent 実施: 約 **2〜3 日** (T02〜T07 を 6 Agent 並列、T08 最終統合)

---

## 3. 依存関係図

```
                  Phase 1 完了 (style_vector 学習側統合)
                           │
                           ▼
                ┌────────────────────┐
                │ P2-T01             │
                │ ONNX export 拡張   │
                └──────────┬─────────┘
                           │
            ┌──────────────┼──────────────┬──────────────┐
            ▼              ▼              ▼              ▼
       ┌────────┐     ┌────────┐     ┌────────┐     ┌────────┐
       │ P2-T02 │     │ P2-T03 │     │ P2-T04 │     │ P2-T05 │
       │ Python │     │ C++    │     │ Rust   │     │ C#     │
       └────┬───┘     └────┬───┘     └────┬───┘     └────┬───┘
            │              │              │              │
            │              │              ▼              │
            │              │         ┌────────┐          │
            │              │         │ P2-T07 │          │
            │              │         │ WASM   │◄─────────┤ (Rust workspace 依存)
            │              │         └────┬───┘          │
            │              │              │              │
            │         ┌────────┐          │              │
            │         │ P2-T06 │          │              │
            │         │ Go     │          │              │
            │         └────┬───┘          │              │
            │              │              │              │
            └──────────────┴──────────────┴──────────────┘
                           │
                           ▼
                ┌────────────────────┐
                │ P2-T08             │
                │ Cross-runtime test │
                └──────────┬─────────┘
                           │
                           ▼
                   Phase 5 (fine-tune 実験)
```

**並列実行のポイント**:
- T02〜T06 は T01 完了後、Agent 6 つで **完全並列可能**
- T07 (WASM) は Rust workspace の `SynthesisRequestData` 更新を含むため、T04 と workspace 単位で相互干渉する可能性あり。workspace レベルのブランチ共有 or T04 先行マージが推奨
- T08 は T01〜T07 全完了後の最終統合テスト

---

## 4. PR 分割案 (phase-2.md §2.7 と整合)

| PR | タイトル | チケット | 工数 | 並列可 |
|----|--------|---------|-----|-------|
| PR-C | `feat(export): style_vector を ONNX 入力に追加 (mask パターン)` | T01 | 1.5 日 | 先行必須 |
| PR-D-Py | `feat(infer): Python ONNX 推論で style_vector サポート` | T02 | 1 日 | ✅ |
| PR-D-Cpp | `feat(runtime): C++ API に style_vector サポート追加` | T03 | 2 日 | ✅ |
| PR-D-Rust | `feat(rust): piper-core と CLI に style_vector 追加` | T04 | 1.5 日 | ✅ (先行推奨) |
| PR-D-CSharp | `feat(csharp): PiperPlus.Core と CLI に style_vector 追加` | T05 | 1.5 日 | ✅ |
| PR-D-Go | `feat(go): Go エンジンに style_vector サポート追加` | T06 | 1.5 日 | ✅ |
| PR-D-Wasm | `feat(wasm): JS/WASM API で style_vector エクスポート` | T07 | 1.5 日 | T04 先行推奨 |
| PR-D-Test | `test(cross-runtime): style_vector byte 互換性検証` | T08 | 0.5 日 | 最終統合 |

**マージ順**: PR-C → (PR-D-Py / PR-D-Cpp / PR-D-Rust / PR-D-CSharp / PR-D-Go 並列) → PR-D-Wasm → PR-D-Test

---

## 5. 成功基準

以下をすべて満たせば Phase 2 完了:

- [ ] 6 ランタイム全てで `style_vector_dim=0` の既存モデルが従来通り動作 (後方互換性)
- [ ] 6 ランタイム全てで `style_vector_dim=256` の新モデルが synthesize 成功
- [ ] 同じ `style_vector.npy` 入力で 5 ランタイム (Python / C++ / Rust / C# / Go) の wav が **byte-for-byte 一致** (FP32 CPU provider)
- [ ] WASM は Python との wav sample 誤差が `ε=1e-3` 以内
- [ ] CLI の `--style-vector PATH` オプション名が 6 ランタイム共通
- [ ] ONNX metadata キー名 `style_vector_dim`, `style_condition_mode` が 6 ランタイム共通
- [ ] 既存 CI (`rust-tests.yml`, `csharp-ci.yml`, `go-ci.yml`, `wasm-build.yml` 等) の全 OS matrix で緑
- [ ] cross-runtime test (T08) が PR / weekly で自動実行

---

## 6. 一から考えたら (代替設計の議論)

Phase 2 実装にあたり、「もし現在の本家 `speaker_embedding` mask パターン資産がなかったら」「Claude Code の Agent 並列起動を最大活用する前提で設計するなら」の観点で、別アーキテクチャを検討した記録。

### 6.1 mask パターン vs ONNX Optional input

**現状採用**: `speaker_embedding` と同じく、`style_vector` / `style_vector_mask` を**常にグラフに入れ、mask=0 で無効化**する方式。

**代替案**: ONNX opset 15+ の `Optional` 型を使い、input として `null` を渡す。

| 項目 | mask パターン (現状) | ONNX Optional |
|-----|-----|-----|
| 実装コスト | 6 ランタイムに zeros tensor 生成ロジック必須 | ランタイム側は `null` 渡せばよい |
| ONNX Runtime サポート | 全言語・全バージョンで安定 | Python OK、Rust/Go/C++/C# binding 未成熟 |
| グラフ検証 | input 数 = 一定 (静的) | input 数 = 実行時可変 |
| 本プロジェクト適合性 | ✅ (既存パターンと対称) | ✗ (多言語対応の足枷) |

**結論**: mask パターン採用が合理的。将来 onnxruntime-web や ort Go binding が Optional を完全サポートした段階で移行検討。

### 6.2 style_vector を speaker_embedding に concatenate して 1 入力にまとめる

**代替案**: ONNX 入力を増やさず、`[speaker_embedding | style_vector]` を連結して `conditioning_vector` 1 本で受ける。

| 利点 | 欠点 |
|-----|-----|
| 入力数削減 (2 → 0) | 学習側での concatenation 順序・次元の厳密管理が必要 |
| ABI / API 変更最小 | speaker_id との排他制御設計が style と混ざる |
| モデルサイズ変化なし | `style_condition_mode=per_frame` への拡張時に shape mismatch |

**結論**: speaker_embedding と style_vector は **独立した conditioning 軸**。独立入力のまま維持が正しい設計。学習側の loss 分離・ablation study にも有利。

### 6.3 CLI 引数を共通 spec (TOML) で定義して差異削減

**現状方針**: 各ランタイム (Python/Rust/Go/C#/Go/WASM) で手作業で `--style-vector` オプションを追加。

**代替案**: `docs/spec/cli-options.toml` に 6 ランタイム共通の CLI 引数仕様を定義、各言語の CLI boilerplate (clap / System.CommandLine / flag / commander.js) を codegen で自動生成。

| 利点 | 欠点 |
|-----|-----|
| 引数名・型の差分根絶 | codegen パイプライン構築コスト (初期 1 週間+) |
| 新オプション追加が spec 編集のみで全ランタイム波及 | codegen 出力が各言語 idiomatic でない場合あり |
| Documentation の単一真実ソース | 既存 CLI (例: Go の `flag`) に後付けするのが困難 |

**結論**: Phase 2 の工数 (2〜3 日) では codegen 投資が過大。Phase 6 以降で検討。現状は T08 の `style-vector-contract.toml` に入力 spec を集約し、人間レビューで整合性担保する運用。

### 6.4 WASM でメモリ共有 (SharedArrayBuffer) を使って Float32Array コピー削減

**現状方針**: `Float32Array` を JS → wasm-bindgen → Rust に渡す際、`Array.from(vec)` 相当のコピーが発生。

**代替案**: `SharedArrayBuffer` で JS と WASM メモリを共有、コピーなしで style_vector 渡し。

| 利点 | 欠点 |
|-----|-----|
| 大規模 vector (per_frame mode 等) でメモリ効率向上 | COOP/COEP HTTP headers が必須 (`Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`) |
| マルチスレッド WASM との親和性 | GitHub Pages / Netlify の無料枠では headers 設定不可 |
| postMessage のオーバーヘッドも同時に解消 | 開発環境構築の複雑度上昇 |

**結論**: 256〜512 次元 float32 (1〜2KB) はコピーコスト無視可能。per_frame mode (数千要素) が採用されたら再検討。

### 6.5 自動生成 (OpenAPI-like spec → 各言語 API を codegen)

**代替案**: `style_vector` API の全 6 ランタイム実装を、仕様ドキュメント (例: AsyncAPI / OpenAPI 拡張) から codegen で生成。

| 利点 | 欠点 |
|-----|-----|
| 仕様と実装の乖離ゼロ | codegen template 記述・保守コスト |
| 新機能追加が全ランタイムで同時進行 | 各言語 idiomatic でない API になりがち |
| クロスランタイム互換性が設計時点で保証 | 既存コードスタイルとの親和性低下 |

**結論**: 現状の本プロジェクト (各言語の慣習を尊重する方針) には不適合。共通 spec TOML (§6.3) で緩やかな整合性担保が現実解。

### 6.6 Phase 2 を「ランタイム」別ではなく「機能」別に分割

**代替案**: T02〜T07 を「ランタイム毎の統合」ではなく、「CLI 追加」「ONNX 入力検出」「テンソル構築」「Tests」で横断的に分割。

| 利点 | 欠点 |
|-----|-----|
| 1 Agent が複数言語を横断するので仕様理解の一貫性 | 言語固有の知識が薄い Agent で品質低下 |
| コードレビューが機能単位で完結 | PR 分割が複雑化、CI 並列化が困難 |

**結論**: 言語固有のビルド/テスト/CI を Agent 毎に持たせた方が Claude Code の Agent 並列起動を最大活用できる。現状方針維持。

---

## 7. 参考リンク

### 前提資料
- [`../../phase-2.md`](../../phase-2.md) Phase 2 実装計画 (詳細)
- [`../../phase-0-1.md`](../../phase-0-1.md) Phase 0/1 (前提)
- [`../../README.md`](../../README.md) 全体 README

### 本家先例 (speaker_embedding)
- `src/python/piper_train/export_onnx.py:495-514` ONNX export 側
- `src/cpp/piper_plus.h:102-103` C API struct 定義
- `src/rust/piper-core/src/engine.rs:75-80, 612-638` Rust core
- `src/csharp/PiperPlus.Core/Inference/PiperSession.cs:31-46, 305-` C# record
- `src/go/piperplus/engine.go:23, 241-270` Go engine
- `src/wasm/openjtalk-web/src/index.js:344-375, 682-730` WASM/JS

### cross-runtime 互換性先例 (Phoneme Timing)
- Phoneme Timing の `(hop_length / sample_rate) * 1000` 計算が 4 ランタイム (Rust/Go/C++/C#) で byte-for-byte 互換: CLAUDE.md「Phoneme Timing 出力」節参照
- テスト: `tests/test_phoneme_timing.py`, `tests/test_voice_timing.py`

### 外部仕様
- ONNX Runtime custom metadata: https://onnxruntime.ai/docs/api/python/api_summary.html#modelmetadata
- numpy .npy format: https://numpy.org/doc/stable/reference/generated/numpy.lib.format.html
- wasm-bindgen guide: https://rustwasm.github.io/wasm-bindgen/
- ONNX opset Optional type (将来検討): https://github.com/onnx/onnx/blob/main/docs/Operators.md#optional
