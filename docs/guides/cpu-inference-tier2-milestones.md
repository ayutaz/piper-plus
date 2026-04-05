# CPU 推論 Tier 2 Quick Wins — マイルストーン

> **最終更新**: 2026-04-05 (全マイルストーン完了)
> **ブランチ**: `feat/cpu-inference-tier2-quick-wins`
> **設計書**: [cpu-inference-tier2-design.md](cpu-inference-tier2-design.md)
> **チケット一覧**: [docs/tickets/tier2/README.md](../tickets/tier2/README.md)

---

## M1: Python Warmup 実装


`ort_utils.py` に共有 warmup 関数を追加し、全 Python 推論エントリポイントから呼び出す。

### M1.1: `warmup_onnx_session()` コア実装

- [x] `ort_utils.py` に `warmup_onnx_session(session, runs=2, phoneme_length=100)` を追加
- [x] `session.get_inputs()` でオプション入力 (sid, lid, prosody_features) を動的検出
- [x] ダミー入力構築: `[BOS(1), dummy(8)×98, EOS(2)]`, scales=`[0.667, 1.0, 0.8]`
- [x] 全例外キャッチ → `_logger.warning()` → 非致命的に続行
- [x] `PIPER_DISABLE_WARMUP` 環境変数チェック (`1`/`true`/`yes` で無効化)
- [x] 実行時間ログ: `_logger.info("Warmup completed (%d runs in %.0fms)", ...)`

### M1.2: Python 推論スクリプトへの統合

- [x] `infer_onnx.py`: session 作成直後に `warmup_onnx_session(model)` 呼び出し
- [x] `infer_onnx_streaming.py`: `SpeechStreamer.__init__` 内で encoder session に対して呼び出し
- [x] `voice.py` (python_run): `PiperVoice.load()` 内で呼び出し (インライン実装、import 不可のため)
- [x] `docker/python-inference/inference.py`: `PiperInferenceEngine.__init__` 内で呼び出し
- [x] `docker/webui/app.py`: `_get_session()` 内、キャッシュロック内で呼び出し

### M1.3: Python Warmup テスト

- [x] `test_ort_utils.py` に `TestWarmup` クラス追加
  - [x] モック session で warmup 正常完了を検証
  - [x] `session.run` が例外 → warning ログのみで非致命的
  - [x] `PIPER_DISABLE_WARMUP=1` で `session.run` 未呼出
  - [x] `runs=0` で即 return
  - [x] オプション入力の動的検出 (sid あり/なし、lid あり/なし、prosody あり/なし)

### M1.4: 完了基準

- [x] `uv run pytest tests/test_ort_utils.py` 全 PASS
- [x] `uv run ruff check && uv run ruff format --check` PASS

---

## M2: C++ Warmup 実装


### M2.1: `warmupModel()` 関数追加

- [x] `piper.cpp` に `void warmupModel(ModelSession&, int runs=2)` 追加
- [x] 既存の `synthesize()` と同じテンソル構築パターンを使用
- [x] ダミー入力: BOS(1) + dummy(8)×98 + EOS(2), scales=[0.667, 1.0, 0.8]
- [x] `session.hasMultiSpeaker` / `hasLidInput` / `hasProsodyInput` でオプション入力を動的構築
- [x] 例外キャッチ → `spdlog::warn()` → 非致命的
- [x] 実行時間ログ: `spdlog::info("Warmup completed ({} runs in {}ms)", ...)`

### M2.2: `piper.hpp` にシグネチャ追加

- [x] `warmupModel()` のプロトタイプ宣言

### M2.3: CLI 統合

- [x] `main.cpp` の `RunConfig` に `bool noWarmup = false` 追加
- [x] `parseArgs()` に `--no-warmup` フラグ解析追加
- [x] `printUsage()` に `--no-warmup` の説明追加
- [x] `loadVoice()` 完了後、`!runConfig.noWarmup` なら `warmupModel()` 呼び出し

### M2.4: C++ テスト

- [x] 既存の C++ テストスイートでビルド・リンク成功を確認
- [x] `--no-warmup` フラグが正しく解析されることを確認

### M2.5: 完了基準

- [x] 3 OS (Windows/Linux/macOS) で C++ ビルド成功
- [x] `--no-warmup` フラグの動作確認

---

## M3: Python 最適化モデルキャッシュ


### M3.1: `create_session_with_cache()` コア実装

- [x] `ort_utils.py` に `create_session_with_cache(model_path, *, device, ...)` 追加
- [x] デバイスラベル生成: `"cpu"` or `"cuda0"` (providers から判定)
- [x] キャッシュパス生成: `model.{device}.opt.onnx`
- [x] センチネルパス生成: `model.{device}.opt.onnx.ok`
- [x] キャッシュ有効判定: `.opt.onnx` + `.ok` 両方存在 → `ORT_DISABLE_ALL` でロード
- [x] 不完全キャッシュ検出: `.opt.onnx` のみ存在 → 削除して再最適化
- [x] 初回: `optimized_model_filepath` 設定 → session 作成 → `.ok` 書込
- [x] 書込失敗 (PermissionError/OSError) → warning ログ → キャッシュなしで続行

### M3.2: Python 推論スクリプトへの統合

- [x] `infer_onnx.py`: `InferenceSession()` → `create_session_with_cache()` に置換
- [x] `docker/python-inference/inference.py`: 同上
- [x] `docker/webui/app.py`: `_get_session()` 内で `create_session_with_cache()` 使用
- [x] `voice.py` (python_run): インラインでキャッシュロジック実装 (import 不可)

### M3.3: HF Space CI 対応

- [x] `.github/workflows/test-hf-space.yml` に新関数の影響がないか確認
- [x] `.github/workflows/deploy-huggingface.yml` 同上

### M3.4: テスト

- [x] `test_ort_utils.py` に `TestModelCache` クラス追加
  - [x] 初回ロード → `.opt.onnx` + `.ok` が生成される
  - [x] 2回目ロード → `ORT_DISABLE_ALL` でロード (最適化スキップ)
  - [x] 不完全キャッシュ → `.opt.onnx` 削除 → 再最適化
  - [x] 読み取り専用ディレクトリ → warning ログのみ、正常動作
  - [x] デバイス別パス (`cpu` vs `cuda0`)

### M3.5: 完了基準

- [x] `uv run pytest tests/test_ort_utils.py` 全 PASS
- [x] `uv run ruff check && uv run ruff format --check` PASS

---

## M4: 日本語音素化キャッシュ


### M4.1: piper_train 側 (学習/推論パッケージ)

- [x] `phonemize/japanese.py` の `phonemize_japanese()` にキャッシュ導入
- [x] `_split_long_text()` で文分割 → 文単位で `@lru_cache(maxsize=2000)` 適用
- [x] キャッシュキー: `(sentence_text, prosody_flag)` タプル
- [x] `clear_phonemize_cache()` 関数を公開 (カスタム辞書変更時用)

### M4.2: python_run 側 (ランタイムパッケージ)

- [x] `piper/voice.py` の `phonemize()` メソッド内で同等のキャッシュ適用
- [x] `piper_train.phonemize.japanese` を import できる場合はそちらに委譲
- [x] import 不可の場合はインラインで lru_cache 適用

### M4.3: テスト

- [x] `tests/test_japanese_cache.py` 新規作成 (または既存テストに追加)
  - [x] 同一文 2 回呼出 → 2 回目は高速 (< 5ms)
  - [x] `prosody=True` と `prosody=False` で別キャッシュエントリ
  - [x] `cache_clear()` 後に再計算確認
  - [x] LRU maxsize 到達時に古いエントリが退去
- [x] 既存の日本語音素化テストが引き続き PASS

### M4.4: 完了基準

- [x] 日本語音素化テスト全 PASS
- [x] `uv run ruff check && uv run ruff format --check` PASS
- [x] キャッシュヒット時のレイテンシ < 5ms (手動確認)

---

## M5: 最終統合・CI・PR


### M5.1: lint・フォーマット

- [x] `uv run ruff check --fix && uv run ruff format` (Python)
- [x] `cargo fmt --all` (Rust — 無条件実行、回帰確認)
- [x] `dotnet format src/csharp/PiperPlus.sln` (C# — 無条件実行、回帰確認)

### M5.2: 全テスト実行

- [x] `uv run pytest src/python/tests/ --override-ini="addopts="` 全 PASS
- [x] `cargo test -p piper-plus --lib` 全 PASS (無条件実行 — 回帰テスト)
- [x] `dotnet test src/csharp/PiperPlus.Core.Tests` 全 PASS (無条件実行 — 回帰テスト)

### M5.3: ドキュメント更新 + CI 修正

- [x] `docs/guides/cpu-inference-optimization.md` の Tier 2 テーブルを完了状態に更新
- [x] 実装間設定比較テーブルに warmup/cache の行を更新
- [x] **(MUST-DO)** `test-hf-space.yml` と `deploy-huggingface.yml` の `paths:` トリガーに `src/python/piper_train/ort_utils.py` を追加 (PR #315 と同じバグパターンの再発防止)

### M5.4: コミット・PR

- [x] 施策ごとに個別コミット (`git bisect` / レビュー容易性のため):
  1. `perf(python): add ONNX Runtime warmup — M1`
  2. `perf(cpp): add ONNX Runtime warmup — M2`
  3. `perf(python): add optimized model cache (.opt.onnx) — M3`
  4. `perf(python): add Japanese phonemize LRU cache — M4`
  5. `docs: update cpu-inference-optimization.md — Tier 2 完了`
  6. `ci: add ort_utils.py to HF Space path triggers` **(MUST-DO — PR #315 と同じバグの再発防止)**
- [x] `git push` → PR 作成 (ラベル: `performance`, `python`, `cpp`, `japanese`)
- [x] CI 全ジョブ PASS 確認
- [x] Copilot レビュー対応

> **並列化ノート:** M5 タスクは 2-3 エージェントに分散可能: (A) lint/format, (B) テスト実行, (C) ドキュメント/PR/CI修正。A と B は並列実行可能、C は A/B 完了後にコミット・PR 作成。
