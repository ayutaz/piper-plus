# M5: 最終統合・CI・PR

> **マイルストーン**: [M5](../../guides/cpu-inference-tier2-milestones.md#m5-最終統合cipr)
> **設計書**: [cpu-inference-tier2-design.md](../../guides/cpu-inference-tier2-design.md)
> **ステータス**: 未着手
> **依存**: [M1](M1-python-warmup.md), [M2](M2-cpp-warmup.md), [M3](M3-python-model-cache.md), [M4](M4-japanese-phonemize-cache.md) (全完了後)
> **後続**: なし (最終タスク)

---

## 1. タスク目的とゴール

**目的:** M1-M4 で個別に実装した 4 施策 (Python Warmup, C++ Warmup, Python モデルキャッシュ, 日本語音素化キャッシュ) を統合し、lint/フォーマット修正、全 CI ジョブの通過を確認した上で PR を作成・マージする。

**ゴール:**

- M1-M4 の全変更が `feat/cpu-inference-tier2-quick-wins` ブランチ上で矛盾なく共存すること
- Python (`ruff check` / `ruff format`), Rust (`cargo fmt` / `cargo clippy`), C# (`dotnet format`) のフォーマット/lint が全て PASS すること
- 全 CI ジョブ (Python, C++, Rust, C#, npm, HF Space, lint) が PASS すること
- `docs/guides/cpu-inference-optimization.md` のステータステーブルが更新されていること
- Copilot レビュー指摘事項が対応済みであること
- PR が `dev` ブランチへマージ可能な状態であること

**非ゴール:**

- 新規機能の追加 (M1-M4 スコープ外の変更)
- パフォーマンスベンチマークの実施 (手動確認は M1-M4 内で完了済み)
- Rust/C# の音素化キャッシュ実装 (Phase 2 として見送り済み)

---

## 2. 実装内容の詳細

### 2.1 lint・フォーマット修正

| 対象 | コマンド | 変更対象ファイル (想定) |
|------|---------|----------------------|
| Python | `uv run ruff check --fix && uv run ruff format` | `ort_utils.py`, `infer_onnx.py`, `infer_onnx_streaming.py`, `phonemize/japanese.py`, `tests/test_ort_utils.py`, `tests/test_japanese_cache.py` |
| Rust | `cargo fmt --all` | **無条件実行** — M2 で直接の Rust 変更はないが、回帰確認として必ず実行 |
| C# | `dotnet format src/csharp/PiperPlus.sln --verify-no-changes` | **無条件実行** — M1-M4 で C# 変更はないが、回帰確認として必ず実行 |
| C++ | clang-format (手動確認) | `piper.cpp`, `piper.hpp`, `main.cpp` |

**注意:** `ruff` のバージョンは CI で `ruff==0.12.5` が指定されている (`ci.yml` lint ジョブ)。ローカルでも同一バージョンを使用すること。

### 2.2 全テスト実行

| テストスイート | コマンド | 備考 |
|---------------|---------|------|
| Python unit | `cd src/python && uv run pytest tests/ -v --tb=short -m "unit and not training and not benchmark and not inference" --override-ini="addopts="` | M1/M3 の `test_ort_utils.py`, M4 の日本語キャッシュテストを含む |
| Python 音素化 | `cd src/python && uv run pytest tests/ -v -k "phonemize or japanese"` | M4 の既存テスト回帰確認 |
| Rust | `cd src/rust && cargo test -p piper-plus --lib --no-fail-fast` | **無条件実行** — M1-M4 で Rust 変更なしでも回帰テストとして必ず実行 |
| C# | `dotnet test src/csharp/PiperPlus.Core.Tests -c Release` | **無条件実行** — M1-M4 で C# 変更なしでも回帰テストとして必ず実行 |
| C++ | `cd build && ctest --output-on-failure` (ビルド後) | M2 の warmup 関数追加による回帰確認 |

### 2.3 HF Space CI 対応

PR #315 で `ort_utils.py` のコピー漏れにより HF Space CI が失敗した前例がある。M1/M3 で `ort_utils.py` に `warmup_onnx_session()` と `create_session_with_cache()` を追加するが、以下の 2 つの CI ワークフローでは既に `ort_utils.py` がコピー対象に含まれているため、**関数追加のみであれば追加の CI 修正は不要**:

| ワークフロー | `ort_utils.py` コピー | 確認箇所 |
|-------------|---------------------|---------|
| `.github/workflows/test-hf-space.yml` | L45: `cp src/python/piper_train/ort_utils.py hf-space-deploy/piper_train/` | OK (ファイル全体をコピー) |
| `.github/workflows/deploy-huggingface.yml` | L77: `cp src/python/piper_train/ort_utils.py hf-space-deploy/piper_train/` | OK (ファイル全体をコピー) |

**ただし以下を確認すること:**

1. `ort_utils.py` の新関数が `onnxruntime` 以外の新規 import を追加していないこと (HF Space の `requirements.txt` に含まれない依存が増えると CI 失敗)
2. **MUST-DO (PR 前に必ず実施):** `test-hf-space.yml` と `deploy-huggingface.yml` の `paths:` トリガーに `src/python/piper_train/ort_utils.py` が含まれていない (**現在 `push` / `pull_request` 両方とも未登録**)。PR #315 で `ort_utils.py` を新設した際にコピー処理は追加されたがパストリガーは更新されなかった — 全く同じバグパターンの再発防止として、本 PR のコミット 6 で**必ず**追加すること。これを怠ると `ort_utils.py` 単体の変更で HF Space CI がスキップされ、デプロイ後に初めて壊れるサイレント障害になる
3. `infer_onnx.py` 内の変更 (M1 warmup 呼び出し追加、M3 の `create_session_with_cache()` 呼び出し) は `test-hf-space.yml` の `paths:` トリガー (`src/python/piper_train/infer_onnx.py`) に含まれるため、自動トリガーされる

**必須対応 (コミット 6 で実施):** `test-hf-space.yml` と `deploy-huggingface.yml` の `paths:` トリガーに `src/python/piper_train/ort_utils.py` を追加する。これにより `ort_utils.py` 単体の変更でも HF Space CI が走るようになる:

```yaml
# test-hf-space.yml (push + pull_request 両方)
paths:
  - 'src/python/piper_train/infer_onnx.py'
  - 'src/python/piper_train/ort_utils.py'    # 追加
```

```yaml
# deploy-huggingface.yml (push のみ)
paths:
  - 'src/python/piper_train/infer_onnx.py'
  - 'src/python/piper_train/ort_utils.py'    # 追加
```

### 2.4 ドキュメント更新

`docs/guides/cpu-inference-optimization.md` の「実装間の設定比較」テーブル (L178-192) を更新:

| 設定項目 | 更新前 | 更新後 |
|---------|--------|--------|
| 最適化モデルキャッシュ (.opt.onnx) — Python | **未実装** | OK |
| センチネルファイル (.ok) — Python | **未実装** | OK |
| Warmup 推論 (2回) — Python | **未実装** | OK |
| Warmup 推論 (2回) — C++ | **未実装** | OK |

また、Tier 2 テーブル (L152-160) に完了状態カラムを追加:

| # | 施策 | 状態 |
|---|------|------|
| 7 | Python/C++ Warmup 追加 | **完了** (本 PR) |
| 6 | Python 最適化モデルキャッシュ | **完了** (本 PR) |
| 4 | 日本語音素化キャッシュ | **完了** (本 PR) |
| 9 | 音素化キャッシュ (Rust/C#) | 見送り (Phase 2) |
| 10 | ストリーミング推論改善 | 見送り (RTF 十分高速) |

### 2.5 コミット・PR 作成

**コミット戦略:** 施策ごとに個別コミットを推奨 (レビューしやすさのため):

1. `perf(python): add ONNX Runtime warmup — M1`
2. `perf(cpp): add ONNX Runtime warmup — M2`
3. `perf(python): add optimized model cache (.opt.onnx) — M3`
4. `perf(python): add Japanese phonemize LRU cache — M4`
5. `docs: update cpu-inference-optimization.md — Tier 2 完了`
6. `ci: add ort_utils.py to HF Space path triggers`

**PR:**

- タイトル: `perf: CPU 推論 Tier 2 Quick Wins — warmup/cache/音素化キャッシュ (#XXX)`
- ベースブランチ: `dev`
- ラベル: `performance`, `python`, `cpp`, `japanese`

---

## 3. エージェントチームの構成

| 役割 | 人数 | 担当 |
|------|------|------|
| **統合エージェント** | 1 | lint/format 修正、テスト実行、CI 確認、ドキュメント更新、PR 作成 |

**合計: 1 エージェント** (ただし下記の並列化が可能)

M5 は新規実装を含まないため、単一エージェントで全作業を逐次実行する。lint 修正 → テスト → ドキュメント → コミット → PR → CI 確認 → Copilot レビュー対応の順序で進める。

> **並列化ノート:** M5 のタスクは依存関係が少ないため、2-3 エージェントに分散して並列実行できる:
> - **エージェント A**: lint/format 修正 (Python ruff, Rust cargo fmt, C# dotnet format, C++ clang-format)
> - **エージェント B**: テスト実行 (Python pytest, Rust cargo test, C# dotnet test, C++ ctest)
> - **エージェント C**: ドキュメント更新 + PR 作成 + CI パストリガー修正
>
> A と B は完全に独立して並列実行可能。C は A/B の結果を待ってからコミット・PR 作成を行う。

**前提条件:** M1-M4 の全コミットが `feat/cpu-inference-tier2-quick-wins` ブランチ上に存在すること。

---

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

| 含む | 含まない |
|------|---------|
| lint/format 修正 (Python, Rust, C#, C++) | 新規機能の追加 |
| 全テストスイートの実行・通過確認 | パフォーマンスベンチマーク |
| `cpu-inference-optimization.md` の更新 | 他のドキュメント (CLAUDE.md 等) の更新 |
| HF Space CI パストリガーの追加 | HF Space アプリ本体の変更 |
| PR 作成・Copilot レビュー対応 | dev ブランチへのマージ (レビュー承認後) |
| CI ワークフローの確認・修正 | 新規 CI ワークフローの作成 |

### 4.2 ユニットテスト

M5 自体では新規テストを追加しない。M1-M4 で追加されたテストが全て PASS することを確認する:

| テストファイル | 追加元 | テスト内容 |
|--------------|--------|-----------|
| `tests/test_ort_utils.py::TestWarmup` | M1 | warmup 正常完了、例外時非致命的、`PIPER_DISABLE_WARMUP` 環境変数、`runs=0`、オプション入力動的検出 |
| `tests/test_ort_utils.py::TestModelCache` | M3 | キャッシュ作成、キャッシュヒット、不完全キャッシュ削除、読み取り専用 FS、デバイス別パス |
| `tests/test_japanese_cache.py` | M4 | キャッシュヒット高速化、prosody フラグ別キャッシュ、`cache_clear()`、LRU maxsize |

**実行コマンド:**

```bash
# M1/M3 のテスト
cd src/python && uv run pytest tests/test_ort_utils.py -v --override-ini="addopts="

# M4 のテスト
cd src/python && uv run pytest tests/test_japanese_cache.py -v --override-ini="addopts="

# 全ユニットテスト (回帰確認)
cd src/python && uv run pytest tests/ -v --tb=short -m "unit and not training and not benchmark and not inference" --override-ini="addopts="
```

### 4.3 E2E テスト

| テスト | 確認方法 | 合格基準 |
|--------|---------|---------|
| CI: Python tests | `ci.yml` → `python-tests` ジョブ | 全テスト PASS (ubuntu-22.04) |
| CI: Python tests (3OS) | `python-tests.yml` | 全テスト PASS (ubuntu, windows, macos) |
| CI: C++ tests | `ci.yml` → `cpp-tests` ジョブ (`_build-test-cpp.yml`) | 3 OS x 2 Build Type = 6 ジョブ全 PASS |
| CI: Rust tests | `ci.yml` → `rust-tests` ジョブ | ubuntu + macos PASS |
| CI: C# tests | `ci.yml` → `csharp-tests` ジョブ | 3 OS 全 PASS |
| CI: lint | `ci.yml` → `lint` ジョブ | `ruff check` + `ruff format --check` PASS |
| CI: HF Space | `test-hf-space.yml` | Layer 1-5 全 PASS |
| CI: Rust fmt | `ci.yml` → `rust-tests` → `cargo fmt --all -- --check` | PASS |
| CI: C# format | `ci.yml` → `csharp-tests` → `dotnet format --verify-no-changes` | PASS |

---

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| 懸念 | リスク | 対策 | 根拠 |
|------|--------|------|------|
| HF Space CI で `ort_utils.py` の新関数が import エラー | 中 | `warmup_onnx_session()` と `create_session_with_cache()` は `onnxruntime` のみに依存。HF Space の `requirements.txt` に `onnxruntime` は含まれている。ファイル全体がコピーされるため関数追加は安全 | PR #315 で `ort_utils.py` コピー漏れが発生した前例。今回はコピー自体は既存だが、新依存の有無を確認する必要がある |
| Copilot レビューで rustfmt 指摘 | 中 | `cargo fmt --all` を PR 前に必ず実行。PR #317 で rustfmt 指摘があった前例 | PR #317 の教訓。CI の `cargo fmt --all -- --check` で自動検出される |
| C++ ビルドエラー (M2 の warmup 関数) | 中 | 3 OS x 2 Build Type の CI マトリクスで検証。`warmupModel()` は既存の `synthesize()` パターンを踏襲するため新しい依存なし | C++ のクロスプラットフォームビルドは過去に macOS で問題が出ることがある |
| `test-hf-space.yml` のパストリガー不足 | **高** | `ort_utils.py` をパストリガーに**必ず**追加する (MUST-DO)。PR #315 と全く同じバグパターン。追加しなくても `infer_onnx.py` の変更でトリガーされるが、将来 `ort_utils.py` 単体の変更時にサイレント障害になる | PR #315 の教訓。コミット 6 で対応 |
| M1-M4 間のコード競合 | 低 | M1/M3 は同一ファイル (`ort_utils.py`) を変更するが、追加のみで編集箇所が重ならない。M4 は `phonemize/japanese.py` で独立 | 設計書で実装順序が規定されている (M1→M3 は同ファイル、M4 は独立) |
| `python_run/voice.py` のインライン実装と `piper_train` 側の乖離 | 低 | `voice.py` は `piper_train` を import できないため、M1 の warmup と M3 のキャッシュをインラインで実装する。ロジックの重複が発生するが、設計書の方針に従う | 設計書 M1.2/M3.2 で明示的にインライン実装と記載 |

### 5.2 レビューチェックリスト

**コード品質:**

- [ ] `uv run ruff check` が警告ゼロ
- [ ] `uv run ruff format --check` が差分ゼロ
- [ ] `cargo fmt --all -- --check` が差分ゼロ (無条件実行 — 回帰確認)
- [ ] `dotnet format --verify-no-changes` が差分ゼロ (無条件実行 — 回帰確認)
- [ ] C++ コードが既存のコーディングスタイルに準拠

**テスト:**

- [ ] `tests/test_ort_utils.py` の全テスト PASS
- [ ] `tests/test_japanese_cache.py` の全テスト PASS (M4)
- [ ] 既存の日本語音素化テスト (`tests/test_japanese_phonemizer.py` 等) が回帰なし
- [ ] 既存の ORT 関連テスト (`tests/test_ort_utils.py` の既存テスト) が回帰なし

**CI:**

- [ ] `ci.yml` の全ジョブ PASS (cpp-tests, csharp-tests, python-tests, rust-tests, npm-package-tests, lint)
- [ ] `python-tests.yml` の 3 OS x Python 3.11 PASS
- [ ] `test-hf-space.yml` の Layer 1-5 PASS
- [ ] Copilot レビュー指摘事項の全対応

**ドキュメント:**

- [ ] `cpu-inference-optimization.md` の設定比較テーブルが最新
- [ ] Tier 2 テーブルの状態カラムが正確

**HF Space:**

- [ ] `ort_utils.py` の新関数が `onnxruntime` 以外の新規 import を含んでいないこと
- [ ] `test-hf-space.yml` / `deploy-huggingface.yml` のパストリガーに `ort_utils.py` が追加されていること
- [ ] HF Space デプロイディレクトリに必要なファイルが全てコピーされること

**PR:**

- [ ] コミットメッセージが施策ごとに分離されている
- [ ] PR 説明に M1-M4 の変更サマリー、期待効果、テスト結果を含む
- [ ] PR ラベルが適切 (`performance`, `python`, `cpp`, `japanese`)

---

## 6. 一から作り直すとしたら

### CI パストリガーの設計

**現在の問題:** `test-hf-space.yml` と `deploy-huggingface.yml` のパストリガーに `ort_utils.py` が含まれていない。PR #315 で `ort_utils.py` を新設した際にコピー処理は追加されたが、パストリガーは更新されなかった。

**もし一から設計するなら:**

1. **HF Space デプロイで使用する全 Python ファイルのリストを一箇所で管理する:**
   - `huggingface-space/deploy-files.txt` のようなマニフェストファイルを作成
   - CI ワークフローのコピー処理とパストリガーの両方がこのマニフェストを参照する
   - ファイル追加時にマニフェストだけ更新すれば、コピーもトリガーも自動で対応される

2. **パストリガーにワイルドカードを使用する:**
   ```yaml
   paths:
     - 'src/python/piper_train/*.py'  # 個別ファイル列挙の代わりに
   ```
   ただし、これだと学習専用ファイル (`__main__.py`, `vits/lightning.py` 等) の変更でも HF Space CI がトリガーされるため、過剰トリガーとのトレードオフがある。

3. **HF Space CI を常時実行にする (パストリガー撤廃):**
   - HF Space CI は軽量 (2-3 分) なので、毎 PR で実行しても負担は小さい
   - パストリガーの漏れによる CI スキップを完全に防止できる
   - **判断:** 現時点では個別ファイル列挙 + `ort_utils.py` 追加が最も低リスク

### コミット粒度

**もし一から設計するなら:**

- M1-M4 を 1 コミットずつではなく、「Python 全変更」と「C++ 変更」の 2 コミットに分ける選択肢もある
- ただし施策ごとのコミットの方が `git bisect` やレバート時に有利
- **判断:** 施策ごとのコミットを維持。レビューしやすさと将来のメンテナンス性を優先

### テスト戦略

**現在の懸念:** M1 (warmup) と M3 (model cache) のテストが同一ファイル (`test_ort_utils.py`) に配置される。ファイルが大きくなると見通しが悪くなる。

**もし一から設計するなら:**

- `test_ort_utils_warmup.py` と `test_ort_utils_cache.py` に分割する
- ただし既存の `test_ort_utils.py` に `TestSessionOptions` クラスが既にあるため、同一ファイルにクラスを追加する方が一貫性がある
- **判断:** 現在の設計 (同一ファイルにクラス追加) を維持

---

## 7. 後続タスクへの連絡事項

### Tier 2 完了後の状態

本 PR マージ後、CPU 推論の最適化状態は以下の通り:

| 機能 | Rust | C# | C++ | Python |
|------|------|-----|-----|--------|
| Warmup | OK | OK | **OK (本PR)** | **OK (本PR)** |
| モデルキャッシュ | OK | OK | N/A | **OK (本PR)** |
| 音素化キャッシュ | - | - | - | **OK (本PR, JA)** |

### 残存タスク (Phase 2 以降)

1. **Rust/C# 音素化キャッシュ:** Rust は `lru` クレート追加、C# は `MemoryCache` 統合が必要。本 PR の Python 実装をリファレンスとして使用可能
2. **`test-hf-space.yml` のパストリガー整備:** 本 PR で `ort_utils.py` を追加するが、将来的にはマニフェストファイル方式への移行を検討
3. **Tier 3 施策 (再学習必要):** MB-iSTFT-VITS (4-8x 高速化)、知識蒸留 (3-5x)、Vocos デコーダ (13x) は別ブランチ・別 PR で対応

### PR #315 / #317 の教訓の適用

| 教訓 | PR | 本 PR での対応 |
|------|-----|---------------|
| HF Space CI で `ort_utils.py` コピー漏れ | #315 | パストリガーに `ort_utils.py` を追加。コピー処理は既存で対応済み |
| `cargo fmt` 未実行で CI 失敗 | #317 | PR 前に `cargo fmt --all` を必ず実行。チェックリストに明記 |
| Copilot レビューでの指摘対応遅延 | #317 | lint/format を PR 前に完了させ、Copilot 指摘を最小化 |

### CLAUDE.md への反映

本 PR マージ後、`CLAUDE.md` の「実装済み機能」セクションに以下を追加することを検討:

- ONNX Runtime Warmup (Python/C++)
- Python 最適化モデルキャッシュ (.opt.onnx)
- 日本語音素化 LRU キャッシュ

ただし CLAUDE.md の更新は本 PR のスコープ外。別途対応すること。
