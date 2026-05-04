# T-01: ort-session-contract.toml の EP 仕様追記

**Milestone:** feat: Hardware EP 自動選択 (#382) — Milestone #16
**依存タスク:** なし（このタスクが最初に実施される）
**後続タスク:** T-02 (Python ort_utils.py 拡張), T-03 (voice.py 拡張), T-04 (Rust gpu.rs), T-05 (Go device.go), T-06 (C# SessionFactory.cs), T-07 (C++ piper.cpp)

---

## 1. タスク目的とゴール

`docs/spec/ort-session-contract.toml` は全ランタイム（Python/Rust/C#/C++/Go）が実装の基準とするクロスランゲージ仕様書である。現時点では CPU と CUDA の EP しか定義されておらず、CoreML・DirectML・OpenVINO・TensorRT のキャッシュラベルや環境変数のルールが記載されていない。

このタスクの目的は、EP 自動選択機能の全実装が開始される前に、以下の仕様を TOML ファイルに追記してコントラクトを確立することである。

- EP 自動検出の優先順位（CUDA → CoreML → DirectML → OpenVINO → CPU）
- `PIPER_EXECUTION_PROVIDER` 環境変数の仕様と有効な値
- TensorRT が auto-detect 対象外で明示指定のみ可能であること
- OpenVINO が Python ランタイムのみ対応であること
- 新規 EP のキャッシュファイル device_label（`coreml`, `directml{device_id}`, `openvino`, `tensorrt{device_id}`）

**完了の定義（Done 基準）:**
- `docs/spec/ort-session-contract.toml` に `[execution_provider]` セクションと `[execution_provider.env]` セクションが追記されている
- 新規 EP の device_label が `[cache.extra_device_labels]` サブテーブルとして定義されている
- 各ランタイムの EP 対応状況がコメントとして明記されている
- TOML ファイルの既存セクションが破壊されていない（`toml` パーサーで構文エラーなし）

---

## 2. 実装する内容の詳細

### 変更ファイル

`docs/spec/ort-session-contract.toml` のファイル末尾に以下を追記する。既存の `[cache]` セクションや `[env_vars]` セクションには手を加えない。

```toml
# --- Execution Provider ---

[execution_provider]
# 自動検出の優先度順（TensorRT は auto-detect 対象外 — 明示指定のみ）
# OpenVINO は Python ランタイムのみ対応。
auto_priority = ["CUDA", "CoreML", "DirectML", "OpenVINO", "CPU"]

[execution_provider.env]
override_var = "PIPER_EXECUTION_PROVIDER"
# 値: "cpu" | "cuda" | "cuda:N" | "coreml" | "directml" | "directml:N"
#     | "openvino" | "tensorrt" | "tensorrt:N"
# TensorRT は auto-detect 対象外だが明示指定は可能。
# env var は device パラメータより優先される。

# --- [cache] セクションへの追記 ---
# 既存キー device_label_cpu / device_label_cuda_format に加えて追加:

[cache.extra_device_labels]
device_label_coreml          = "coreml"
device_label_directml_format = "directml{device_id}"
device_label_openvino        = "openvino"
device_label_tensorrt_format = "tensorrt{device_id}"

# --- [env_vars.implementation_status] への追記 ---
# PIPER_EXECUTION_PROVIDER の実装状況
#                        Rust    C#     C++    Python   Go
# ep env var             ✓       ✓      ✓      ✓        ✓
# openvino ep            -       -      -      ✓        -
```

### 追記後の `[cache]` セクションとの関係

既存の `[cache]` セクション（`device_label_cpu = "cpu"`, `device_label_cuda_format = "cuda{device_id}"`）はそのまま保持する。新規 EP の device_label は `[cache.extra_device_labels]` サブテーブルとして追加することで、既存キーとの衝突を避ける。

### TOML 構文検証

追記後に以下のコマンドで構文エラーがないことを確認する:

```bash
python3 -c "import tomllib; tomllib.load(open('docs/spec/ort-session-contract.toml', 'rb'))"
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|---|---|---|
| Implementation Agent | 1 | TOML ファイルへの追記、構文検証 |
| Review Agent | 1 | 設計仕様書との整合性確認、後続タスクの実装者が迷わないか確認 |
| QA Agent | 0 | TOML 構文チェックは Implementation Agent が実施するため不要 |

このタスクは単一ファイルへの追記であり、コードの実行は不要。Implementation Agent 1 名と Review Agent 1 名で十分。

---

## 4. 提供範囲とテスト項目

### 提供範囲（スコープ）

- `docs/spec/ort-session-contract.toml` への追記のみ
- 既存セクション（`[session]`, `[warmup]`, `[cache]`, `[env_vars]`, `[phonemize_cache]`）は変更しない

### Unit テスト

TOML ファイルの変更は自動テスト対象外だが、以下を手動で確認する:

1. Python 3.11 以上の `tomllib` でパースエラーが発生しないこと
   ```bash
   python3 -c "import tomllib; data = tomllib.load(open('docs/spec/ort-session-contract.toml', 'rb')); print('OK:', list(data.keys()))"
   ```
2. `auto_priority` が `["CUDA", "CoreML", "DirectML", "OpenVINO", "CPU"]` であること
3. `[execution_provider.env]` の `override_var` が `"PIPER_EXECUTION_PROVIDER"` であること
4. `[cache.extra_device_labels]` に 4 つのキーがすべて存在すること

### E2E テスト

このタスク単体では実行可能な E2E テストはない。T-02〜T-07 の実装完了後に全ランタイムのテストが `ort-session-contract.toml` の値を参照して合格することが最終的な E2E 検証となる。

---

## 5. 実装に関する懸念事項とレビュー項目

### 懸念事項

1. **TOML サブテーブル命名の一貫性**: 既存の `[cache]` セクションには `device_label_cpu` と `device_label_cuda_format` が flat key として定義されている。新規 EP の device_label を `[cache.extra_device_labels]` という別サブテーブルに追加することで既存との非対称が生じる。将来的に既存キーも `[cache.extra_device_labels]` に統合すべきか、または全て flat key に揃えるかを後続 Issue で検討する価値がある。

2. **`[execution_provider]` と `[execution_provider.env]` の分離**: 設計仕様書（Section 6）ではこのネスト構造を採用しているが、他のセクション（`[env_vars]` など）とは構造が異なる。将来的に `[env_vars]` に `PIPER_EXECUTION_PROVIDER` を統合する議論が起こりうる。本チケットでは仕様書に従い `[execution_provider.env]` を使用する。

3. **OpenVINO の Python 限定スコープ**: `auto_priority` に `"OpenVINO"` を含めているが、Python 以外では実装しない。コメントに明記するが、将来 Go/C#/C++ に OpenVINO を追加する際に `auto_priority` の変更は不要（実装側で利用可能かチェックする）。

### レビューチェックリスト

- [ ] `auto_priority` の順序が設計仕様書 Section 2.1 と一致しているか（CUDA → CoreML → DirectML → OpenVINO → CPU）
- [ ] TensorRT が `auto_priority` に含まれていないか（auto-detect 対象外）
- [ ] `override_var` の値が `"PIPER_EXECUTION_PROVIDER"` であるか
- [ ] `device_label_directml_format` と `device_label_tensorrt_format` に `{device_id}` プレースホルダーが含まれているか
- [ ] Python 3.11+ の `tomllib` でパースエラーが発生しないか
- [ ] 既存の `[cache]` セクションの `device_label_cpu` / `device_label_cuda_format` が変更されていないか
- [ ] 実装状況コメントの `Rust/C#/C++/Python/Go` の列が正確か（openvino は Python のみ）

---

## 6. 一から作り直すとしたら（Green Field Design）

### 設計思想

TOML コントラクトファイルは「人間が読める、機械が検証できる」仕様書であるべき。現行の `ort-session-contract.toml` はコメントが多く人間可読性は高いが、実装との整合性を自動検証する仕組みがない。Green Field では「コントラクトが唯一の真実（Single Source of Truth）」となり、テストコードが自動生成される設計にする。

### アーキテクチャ

理想的には JSON Schema または TOML の型システムを活用した機械検証可能な仕様書にする:

```toml
[execution_provider]
# 型付き enum として定義
auto_priority = ["CUDA", "CoreML", "DirectML", "OpenVINO", "CPU"]
# machine-readable なランタイム対応状況
[execution_provider.supported_by]
CUDA     = ["python", "rust", "csharp", "cpp", "go"]
CoreML   = ["python", "rust", "csharp", "cpp", "go"]
DirectML = ["python", "rust", "csharp", "cpp", "go"]
OpenVINO = ["python"]
TensorRT = ["python", "rust", "csharp", "cpp", "go"]  # explicit-only
```

各ランタイムのテストが `ort-session-contract.toml` を直接読み込んで `auto_priority` の順序やラベル形式を検証するコントラクトテストを持つことで、仕様と実装のズレを自動検出できる。

### 実装アプローチ

1. TOML パーサーライブラリ（各言語）でコントラクトファイルを読み込む共通ユーティリティを用意
2. 各ランタイムのビルド時に `contract_check` テストを実行し、実装値がコントラクト値と一致することを CI で担保
3. コントラクトファイルの変更が即座に全ランタイムの CI テスト失敗として現れる設計

### 現行実装との主な差異

| 観点 | 現行 | 理想形 |
|---|---|---|
| 機械検証 | なし（コメントベース） | 全ランタイムのコントラクトテストで自動検証 |
| 対応状況の記述 | コメントで手書き | `supported_by` テーブルとして機械可読 |
| キャッシュラベル定義 | 一部が flat key、一部がサブテーブル | 統一されたサブテーブル構造 |
| バージョン管理 | なし | `spec_version = "2"` で仕様バージョンを管理 |

---

## 7. 後続タスクへの引き継ぎ事項

**完了した変更:**
- `docs/spec/ort-session-contract.toml` に `[execution_provider]`, `[execution_provider.env]`, `[cache.extra_device_labels]` セクションが追記された

**後続タスク担当者（T-02〜T-07）への注意点:**

1. **EP 自動検出の優先順序は `auto_priority` に従うこと**: `["CUDA", "CoreML", "DirectML", "OpenVINO", "CPU"]`。TensorRT はこのリストに含まれないため auto-detect の対象外。

2. **環境変数名は `PIPER_EXECUTION_PROVIDER`**: 大文字小文字の正規化（小文字に統一）は各実装側で行う。値の例: `"cpu"`, `"cuda"`, `"cuda:1"`, `"coreml"`, `"directml"`, `"directml:0"`, `"openvino"`, `"tensorrt"`, `"tensorrt:0"`。

3. **キャッシュファイルの device_label:**
   - `coreml` → `"coreml"`
   - `directml` (device 0) → `"directml0"`
   - `directml:1` (device 1) → `"directml1"`
   - `openvino` → `"openvino"`
   - `tensorrt` (device 0) → `"tensorrt0"`
   - 既存: `cpu` → `"cpu"`, `cuda` (device 0) → `"cuda0"`

4. **OpenVINO は Python のみ実装**: Rust/C#/C++/Go では `PIPER_EXECUTION_PROVIDER=openvino` と設定されても `OpenVINOExecutionProvider` は利用不可として CPU にフォールバックすること。

5. **`PIPER_GPU_DEVICE_ID` との互換性**: C# と C++ では既存の `PIPER_GPU_DEVICE_ID` 環境変数が存在する。`PIPER_EXECUTION_PROVIDER` が設定されている場合はそちらを優先し、`PIPER_GPU_DEVICE_ID` は互換のため残す（設計仕様書 Section 2.3 参照）。
