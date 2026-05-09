# T-09: ort-versions.md ドキュメント更新

**Milestone:** feat: Hardware EP 自動選択 (#382) — Milestone #16
**依存タスク:** なし（T-01 とほぼ並行実施可能。T-02〜T-07 の完了は不要）
**後続タスク:** なし（独立したドキュメント変更）

---

## 1. タスク目的とゴール

`docs/spec/ort-versions.md` は各ランタイムが使用する ONNX Runtime のバージョンを記録したドキュメントである。現時点では EP の対応状況に関する情報が記載されておらず、どのランタイムでどの EP が利用可能かを確認する場所がない。

このタスクの目的は、ランタイムごとの EP サポートマトリクスを `ort-versions.md` の末尾に追加し、ユーザーおよびコントリビューターが「自分の環境・ランタイムで CoreML/DirectML/OpenVINO が使えるか」を一目で確認できるようにすることである。

**完了の定義（Done 基準）:**
- `docs/spec/ort-versions.md` の末尾に `## Execution Provider Support Matrix` セクションが追加されている
- Python/Rust/C#/Go/C++/JS-WASM の 6 ランタイムについて CUDA/CoreML/DirectML/OpenVINO/TensorRT の対応状況が表形式で記載されている
- auto-detect の順序と TensorRT/OpenVINO の制約がテキストで補足されている
- 既存の表とテキストが変更されていない

---

## 2. 実装する内容の詳細

### 変更ファイル

`docs/spec/ort-versions.md` の末尾（現在の `## Updating` セクションの後）に以下を追記する。

```markdown
## Execution Provider Support Matrix

| Runtime  | CUDA | CoreML | DirectML | OpenVINO | TensorRT |
|----------|------|--------|----------|----------|----------|
| Python   | ✓ (`onnxruntime-gpu`) | ✓ (`onnxruntime`, macOS) | ✓ (`onnxruntime-directml`) | ✓ (`onnxruntime-openvino`) | ✓ (`onnxruntime-gpu`) |
| Rust     | ✓ (feature `cuda`) | ✓ (feature `coreml`) | ✓ (feature `directml`) | — | ✓ (feature `tensorrt`) |
| C#       | ✓ (`OnnxRuntime.Gpu`) | ✓ (`OnnxRuntime`, macOS) | ✓ (`OnnxRuntime.DirectML`) | — | ✓ (`OnnxRuntime.Gpu`) |
| Go       | ✓ | ✓ | ✓ | — | ✓ |
| C++      | ✓ | ✓ (macOS) | ✓ (Windows) | — | — |
| JS/WASM  | — (sandbox) | — | — | — | — |

Auto-detect order: CUDA → CoreML → DirectML → OpenVINO → CPU  
TensorRT: explicit only (`PIPER_EXECUTION_PROVIDER=tensorrt`)  
OpenVINO: Python only
```

### 追記内容の根拠

各セルの内容は設計仕様書 Section 4「ORT パッケージ要件とランタイムスコープ」および実装計画 Task 1/Task 9 に基づく。

| ランタイム | 根拠 |
|---|---|
| Python | 設計仕様書 Section 4: `onnxruntime`/`onnxruntime-gpu`/`onnxruntime-directml`/`onnxruntime-openvino` の 4 パッケージ体制 |
| Rust | 設計仕様書 Section 4: `ort` crate の features (`cuda`, `coreml`, `directml`)。TensorRT は `features = ["tensorrt"]` で明示指定のみ。OpenVINO はスコープ外 |
| C# | 設計仕様書 Section 4: `Microsoft.ML.OnnxRuntime`/`.Gpu`/`.DirectML`。OpenVINO は NuGet なし |
| Go | 設計仕様書 Section 4: `onnxruntime_go` の CUDA/CoreML/DirectML/TensorRT 対応。OpenVINO は共有ライブラリ差し替えが必要でスコープ外 |
| C++ | 設計仕様書 Section 4: CUDA 既存、CoreML は `__APPLE__` 条件コンパイル、DirectML は `<dml_provider_factory.h>` 存在時。OpenVINO はデフォルト OFF。TensorRT は auto-detect 対象外かつ C++ の明示サポートなし |
| JS/WASM | 設計仕様書 Section 1: ブラウザのサンドボックス制限により全 EP 対象外（SIMD 最適化は利用済み） |

### 現在のファイル末尾からの続き

現在の `ort-versions.md` は以下のように終わっている:

```markdown
## Updating

When bumping the ONNX Runtime version for a specific runtime:

1. Update the package reference in the relevant build file.
2. Update this table.
3. For iOS/Android release builds, change the top-level `env.ONNXRUNTIME_VERSION` in `release-shared-lib.yml`.
```

この `## Updating` セクションの後に `## Execution Provider Support Matrix` セクションを追加する。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|---|---|---|
| Implementation Agent | 1 | Markdown テーブルと補足テキストの追記 |
| Review Agent | 1 | 設計仕様書との正確性確認、ランタイム対応状況の正確性チェック |
| QA Agent | 0 | Markdown のリンク切れチェックは不要（新規リンクなし）。実装 Agent が目視確認で十分 |

変更量は Markdown テーブル追記のみ。1 エージェントで完結する。

---

## 4. 提供範囲とテスト項目

### 提供範囲（スコープ）

- `docs/spec/ort-versions.md` への Markdown テーブル追記のみ
- 既存の ORT バージョン表、CI Workflow References 表、Updating セクションは変更しない

### Unit テスト

Markdown ファイルの変更は自動テスト対象外だが、以下を確認する:

1. Markdown のレンダリングがテーブル崩れなく表示されること（GitHub の Preview 機能や `markdownlint` で確認）
2. 追記箇所が既存セクションの後に正しく配置されていること
3. セルの `—` （em dash）が統一されていること（ハイフン `-` ではなく `—`）

### E2E テスト

このタスク単体では実行可能な E2E テストはない。T-02〜T-07 の実装完了後に `PIPER_EXECUTION_PROVIDER` を各値に設定して動作確認することが最終的な E2E 検証となる。

---

## 5. 実装に関する懸念事項とレビュー項目

### 懸念事項

1. **C++ の TensorRT 対応状況**: 設計仕様書では C++ の TensorRT について「auto-detect 対象外」と明記されているが、明示指定の実装（`PIPER_EXECUTION_PROVIDER=tensorrt` を受け付けるか）は Task 7 の scope に含まれていない。現時点では C++ の TensorRT を `—` としているが、Task 7 完了後に実際の実装状況に合わせてセルを更新する必要がある可能性がある。

2. **Go の TensorRT 対応**: `device.go` の既存 `autoSelectEP` 実装には TensorRT が含まれている（設計仕様書 Section 1 の現状欄）。しかし auto-detect 対象外の方針により、Go の TensorRT は「明示指定のみ可能」かつ「auto-detect 非対象」という状態になる。テーブルの `✓` は「使用可能」を示しており、`PIPER_EXECUTION_PROVIDER=tensorrt` で明示指定すれば Go でも TensorRT は使えるため `✓` は正しい。

3. **C++ の OpenVINO**: 設計仕様書ではコンパイル時フラグ `PIPER_USE_OPENVINO` を追加するが、デフォルト OFF で本 Issue では検証しないとある。テーブルでは `—` としているが、将来コンパイル時フラグで有効化される可能性があることをコメントで補足すべきか検討する。

4. **テーブルの列幅**: Python 列のセル内容が長い（パッケージ名が複数入る）ため、テーブルが横に広くなる。Markdown のレンダリング環境によっては読みにくくなる可能性がある。

### レビューチェックリスト

- [ ] Python 行: 全 5 EP のパッケージ名が正確か（`onnxruntime-gpu`, `onnxruntime-directml`, `onnxruntime-openvino`）
- [ ] Rust 行: feature 名が正確か（`cuda`, `coreml`, `directml`, `tensorrt`）。OpenVINO が `—` であるか
- [ ] C# 行: NuGet パッケージ名が正確か（`OnnxRuntime.Gpu`, `OnnxRuntime.DirectML`）。OpenVINO が `—` であるか
- [ ] Go 行: OpenVINO が `—` であるか
- [ ] C++ 行: CoreML が `(macOS)` 条件付きであるか。TensorRT と OpenVINO が `—` であるか
- [ ] JS/WASM 行: 全 EP が `—` で、`(sandbox)` 注記があるか
- [ ] `Auto-detect order:` の順序が `ort-session-contract.toml` の `auto_priority` と一致しているか
- [ ] TensorRT の明示指定コマンド例が `PIPER_EXECUTION_PROVIDER=tensorrt` であるか
- [ ] `## Updating` セクションの後に追記されており、既存セクションが変更されていないか

---

## 6. 一から作り直すとしたら（Green Field Design）

### 設計思想

ランタイムの EP サポート状況は「静的なドキュメント」ではなく「CI が検証する動的な仕様」であるべき。どのランタイムで何が動くかは実装の変更に追随して自動更新されるのが理想。Green Field では `ort-versions.md` のテーブルを手書きせず、CI が各ランタイムの EP テストの合否から自動生成する仕組みにする。

### アーキテクチャ

理想的なアーキテクチャ:

1. 各ランタイムの CI に EP smoke test を追加（CUDA/CoreML/DirectML/OpenVINO 環境でそれぞれ実行）
2. smoke test の結果を JSON で出力（`{"runtime": "python", "ep": "cuda", "status": "pass"}`）
3. 全ランタイムの結果を集約してテーブルを自動生成する GitHub Actions ワークフロー
4. 生成されたテーブルを `docs/spec/ort-versions.md` に PR として自動提出

この仕組みにより、実装の変更と同時にドキュメントが更新され、手動更新の漏れがなくなる。

### 実装アプローチ

```yaml
# .github/workflows/ep-support-matrix.yml
# 各ランタイムの EP テストを self-hosted ランナーで実行
# 結果を JSON 集約 → Python スクリプトでテーブル生成 → PR 作成
```

ドキュメント生成スクリプト:

```python
# tools/generate_ep_matrix.py
# CI 結果の JSON を読み込み、Markdown テーブルを生成
# 手動で作成したテーブルより常に最新の状態を保持
```

### 現行実装との主な差異

| 観点 | 現行 | 理想形 |
|---|---|---|
| 更新方法 | 手動追記 | CI による自動生成 |
| 正確性保証 | レビュアーの目視確認のみ | CI テストの合否を直接反映 |
| 粒度 | ランタイム × EP の○/✕ | バージョン・OS 別の詳細マトリクス |
| 警告・注記 | 手動でコメント | 失敗時の詳細ログへのリンク |

---

## 7. 後続タスクへの引き継ぎ事項

**完了した変更:**
- `docs/spec/ort-versions.md` の末尾に `## Execution Provider Support Matrix` セクションが追加された

**後続タスク担当者への注意点:**

1. **T-09 は独立したタスク**: Python/Rust/Go/C#/C++ の実装タスク（T-02〜T-07）とは独立しており、順序依存がない。ドキュメントは先に追加しておいて問題ない。

2. **テーブルの更新タイミング**: T-02〜T-07 の実装中に EP の対応状況が変わった場合（例: C++ で TensorRT の明示指定が実装された場合）、`ort-versions.md` のテーブルも合わせて更新すること。

3. **T-08 との連携**: `ort-versions.md` の Python 行に `onnxruntime-directml` と `onnxruntime-openvino` のパッケージ名が記載されており、T-08 で `extras_require` に追加するグループ名（`directml`, `openvino`）と対応する。T-08 完了後にインストールコマンドの例（`pip install piper-plus[directml]`）を README や別ドキュメントに追加する際は T-09 のテーブルを参照すること。

4. **JS/WASM の将来対応**: 設計仕様書 Section 9（スコープ外）に「WASM: onnxruntime-web の WebGPU EP 対応」が将来 Issue として挙げられている。WebGPU EP が実装された際は JS/WASM 行を更新すること。
