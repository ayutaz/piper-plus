# CPU 推論 Tier 2 Quick Wins — 技術設計書

> **作成日**: 2026-04-05
> **ブランチ**: `feat/cpu-inference-tier2-quick-wins`
> **前提**: PR #315 (ort_utils), PR #317 (dynamic_block_base + メモリアリーナ) 完了済み

---

## 概要

Tier 1 (PR #315, #317) の完了を受け、追加のコード変更のみで実装可能な 3 施策を実装する。

| # | 施策 | 期待効果 | 対象 |
|---|------|---------|------|
| 7 | Python/C++ Warmup 追加 | 初回推論 500-800ms 安定化、RTF stdev ~30% 低減 | Python (5箇所) + C++ |
| 6 | Python 最適化モデルキャッシュ (.opt.onnx) | 2回目以降の起動 500-800ms 短縮 | Python |
| 4 | 日本語音素化キャッシュ | 繰り返し音素化 10-50x 高速化 (50-150ms → 1-5ms) | Python |

**見送り**: ストリーミング TTFA 改善 (現状 RTF ~0.19 で十分高速、Encoder の全文一括処理が根本制約)

---

## 施策 #7: ONNX Runtime Warmup

### 背景

ONNX Runtime は初回 `session.run()` 時に JIT コンパイル・メモリアロケーション最適化を実行するため、500-800ms の遅延が発生する。Rust/C# は既にダミー推論で warmup を実装済みだが、Python/C++ は未対応。

### 設計方針

#### 共有関数: `ort_utils.warmup_onnx_session()`

```
場所: src/python/piper_train/ort_utils.py
```

- `session.get_inputs()` でモデルのオプション入力を動的検出
- ダミー入力 100 phonemes: `[BOS(1), dummy(8)×98, EOS(2)]`
- scales: `[0.667, 1.0, 0.8]` (Rust/C# と同一)
- オプション入力 (sid, lid, prosody_features) はモデルが要求する場合のみゼロ値で追加
- デフォルト 2 回実行
- 全例外キャッチ → warning ログ → 非致命的に続行
- `PIPER_DISABLE_WARMUP=1` 環境変数で無効化可能

#### 呼び出し箇所 (Python)

| ファイル | 呼び出し位置 | 備考 |
|----------|-------------|------|
| `infer_onnx.py` | session 作成直後 (推論ループ前) | CLI 推論 |
| `infer_onnx_streaming.py` | `SpeechStreamer.__init__` 内、encoder session 作成後 | ストリーミング推論 |
| `voice.py` (python_run) | `PiperVoice.load()` 内、session 作成後 | ランタイムパッケージ |
| `docker/python-inference/inference.py` | `PiperInferenceEngine.__init__` 内 | Docker 推論サーバー |
| `docker/webui/app.py` | `_get_session()` 内、キャッシュロック内で session 作成後 | WebUI (1モデル1回のみ) |

#### C++ 実装

```
場所: src/cpp/piper.cpp + src/cpp/main.cpp
```

- `piper.cpp` に `warmupModel(ModelSession&, int runs=2)` 関数追加
- 既存の `synthesize()` を呼び出す (テンソル構築ロジックの重複回避)
- ダミー入力: Rust と同一 (100 phonemes, BOS/EOS/dummy)
- `session.hasMultiSpeaker` / `hasLidInput` / `hasProsodyInput` に基づきオプション入力を動的構築
- 例外キャッチ → spdlog::warn → 非致命的
- `main.cpp` に `--no-warmup` フラグ追加
- `printUsage()` に説明追加

#### テスト

| テスト | 場所 | 内容 |
|--------|------|------|
| Python warmup 成功 | `tests/test_ort_utils.py` | モック session で warmup 完了を検証 |
| Python warmup 失敗 (非致命的) | `tests/test_ort_utils.py` | session.run が例外 → warning ログ出力のみ |
| Python PIPER_DISABLE_WARMUP | `tests/test_ort_utils.py` | 環境変数 `1` で session.run 未呼出を検証 |
| C++ warmup CLI | C++ テストスイート | `--no-warmup` フラグ解析テスト |

### リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| warmup 失敗でアプリ停止 | 高 | try/except で全例外をキャッチ、warning ログのみ |
| GPU OOM | 中 | 本番と同じ形状 (100 phonemes) を使用 — 本番が動くなら warmup も動く |
| WebUI で毎リクエスト warmup | 低 | `_get_session()` のキャッシュロック内で 1 モデル 1 回のみ |
| 組込み環境で起動遅延 | 低 | `PIPER_DISABLE_WARMUP=1` または `--no-warmup` で無効化 |

---

## 施策 #6: Python 最適化モデルキャッシュ

### 背景

ONNX Runtime はセッション作成時にグラフ最適化 (定数畳み込み、演算子融合等) を実行する。`optimized_model_filepath` を設定すると最適化済みモデルをディスクに保存し、2回目以降は最適化をスキップして 500-800ms の起動時間を削減できる。Rust/C# は実装済み。

### 設計方針

#### キャッシュパス生成

```
元モデル: /path/to/model.onnx
CPU キャッシュ: /path/to/model.cpu.opt.onnx
CUDA キャッシュ: /path/to/model.cuda0.opt.onnx
センチネル: /path/to/model.cpu.opt.onnx.ok
```

- Rust/C# と同一のパス命名規則
- デバイスラベル: `get_providers()` の結果から決定 ("cpu" or "cuda0")

#### センチネルファイル (.ok)

プロセス中断時に不完全な `.opt.onnx` が残る問題を防止:

1. `.opt.onnx` と `.ok` の両方が存在 → キャッシュ有効 (最適化スキップ)
2. `.opt.onnx` のみ存在 → 不完全 → 削除して再最適化
3. どちらも存在しない → 初回最適化

#### API 設計

`ort_utils.py` に以下を追加:

```python
def create_session_with_cache(
    model_path: str | Path,
    *,
    device: str = "cpu",
    intra_op_threads: int | None = None,
    inter_op_threads: int = 1,
) -> onnxruntime.InferenceSession:
    """最適化モデルキャッシュ付きで InferenceSession を作成する。

    1. キャッシュ有効チェック (.opt.onnx + .ok)
    2. キャッシュ有効 → 最適化無効でキャッシュから読込
    3. キャッシュ無効 → 最適化実行 + .opt.onnx 保存 + .ok 書込
    4. 書込失敗 → warning ログのみ (通常の最適化で続行)
    """
```

- `create_session_options()` は変更なし (後方互換)
- 新関数 `create_session_with_cache()` がキャッシュロジックを内包
- 既存の呼び出し元は段階的に移行可能

#### 呼び出し箇所

| ファイル | 変更内容 |
|----------|---------|
| `infer_onnx.py` | `InferenceSession()` → `create_session_with_cache()` |
| `voice.py` (python_run) | `InferenceSession()` → インラインキャッシュロジック (import 不可のため) |
| `docker/python-inference/inference.py` | `InferenceSession()` → `create_session_with_cache()` |
| `docker/webui/app.py` | `_get_session()` 内で `create_session_with_cache()` 使用 |

### リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| 読み取り専用 FS (Docker `ro` マウント) | 中 | `PermissionError` / `OSError` を try/except でキャッチ → キャッシュなしで続行 |
| ORT バージョン変更でキャッシュ非互換 | 低 | ORT 内部でデシリアライズ失敗時にエラー → キャッシュ削除して再最適化 |
| 複数プロセス同時書込の race condition | 低 | 最悪でも再最適化が走るだけ (データ破損なし、センチネルで保護) |
| モデル更新後の古いキャッシュ | 低 | ユーザーに `.opt.onnx` + `.ok` 手動削除を案内。将来的にモデルハッシュ検証を検討 |

### テスト

| テスト | 内容 |
|--------|------|
| キャッシュ作成 | 初回ロード → `.opt.onnx` + `.ok` が生成される |
| キャッシュヒット | 2回目ロード → `GraphOptimizationLevel.ORT_DISABLE_ALL` で読込 |
| 不完全キャッシュ削除 | `.opt.onnx` のみ存在 → 削除して再最適化 |
| 読み取り専用 FS | `PermissionError` → warning ログのみ、正常に推論可能 |
| デバイス別パス | CPU と CUDA で異なるキャッシュファイル |

---

## 施策 #4: 日本語音素化キャッシュ

### 背景

日本語音素化の主要ボトルネックは `pyopenjtalk.extract_fullcontext()` (MeCab 形態素解析 + フルコンテキストラベル生成) で、1回あたり 50-150ms かかる。WebUI やサーバー環境で同一テキストの繰り返し処理時に無駄な再計算が発生する。

### 設計方針

#### コンテキスト依存性の回避

A1/A2/A3 prosody 値はテキスト中の位置によって変化する:

```python
# 同じ「こんにちは」でも前後の文脈で A2/A3 が異なる
pyopenjtalk.extract_fullcontext("こんにちは")        # 単独: A2=X
pyopenjtalk.extract_fullcontext("私はこんにちは")    # 文中: A2=Y (異なる可能性)
```

**対策**: 既存の `_split_long_text()` で**文単位に分割した後**にキャッシュする。文単位であればコンテキストは固定されるため安全。

#### キャッシュ戦略

```python
# src/python/piper_train/phonemize/japanese.py

from functools import lru_cache

@lru_cache(maxsize=2000)
def _phonemize_sentence_cached(sentence: str, prosody: bool) -> tuple:
    """単一文の音素化結果をキャッシュする。"""
    return _phonemize_core(sentence, prosody=prosody)
```

- **キャッシュキー**: `(文テキスト, prosody有無)` のタプル
- **maxsize**: 2000 文 (メモリ ~1-2MB)
- **スレッド安全性**: `functools.lru_cache` は Python 3.2+ でスレッドセーフ
- **無効化**: カスタム辞書変更時に `_phonemize_sentence_cached.cache_clear()` を呼出

#### 対象範囲

| 実装 | 対応 | 理由 |
|------|------|------|
| **Python (piper_train)** | ✅ 今回実装 | WebUI/サーバーで最も効果大 |
| **Python (python_run)** | ✅ 今回実装 | ランタイムパッケージ |
| Rust | 見送り | `lru` クレート追加が必要、Phase 2 |
| C# | 見送り | `MemoryCache` 統合が必要、Phase 2 |

#### キャッシュ適用フロー

```
phonemize_japanese(text, prosody=True)
  │
  ├── _split_long_text(text) → [sentence1, sentence2, ...]
  │
  ├── for each sentence:
  │     ├── cache hit? → 即返却 (< 0.01ms)
  │     └── cache miss? → _phonemize_core(sentence) → キャッシュ保存 (50-150ms)
  │
  └── 結合 + BOS/EOS 付与
```

### リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| コンテキスト依存で prosody が不正確 | 中 | 文単位キャッシュで回避 (文内は安定) |
| カスタム辞書変更後に古い結果が返る | 中 | 辞書変更時に `cache_clear()` を呼出 |
| 長時間稼働でメモリ増加 | 低 | LRU maxsize=2000 で上限あり (~1-2MB) |
| キャッシュキーの衝突 | 極低 | Python dict のハッシュ衝突は実用上無視できる |

### テスト

| テスト | 内容 |
|--------|------|
| キャッシュヒット | 同一文を 2 回呼出 → 2 回目は高速 (< 1ms) |
| キャッシュミス | 異なる文 → 通常処理 |
| prosody フラグ別 | `prosody=True` と `prosody=False` で別キャッシュ |
| cache_clear | 辞書変更後にキャッシュクリア → 再計算確認 |
| スレッド安全性 | 並行呼出でデッドロック/クラッシュなし |

---

## 実装順序

```
#7 Warmup (Python 5箇所 + C++)
  ↓
#6 モデルキャッシュ (Python)
  ↓
#4 日本語音素化キャッシュ (Python)
  ↓
テスト・CI 確認
  ↓
コミット・PR
```

---

## 参考: 既存実装の対応表

| 機能 | Rust | C# | C++ | Python |
|------|------|-----|-----|--------|
| Warmup | `engine.rs:420-434` | `SessionFactory.cs:220-317` | **今回追加** | **今回追加** |
| モデルキャッシュ | `engine.rs:116-195` | `SessionFactory.cs:130-193` | N/A | **今回追加** |
| 音素化キャッシュ | `english.rs` (bincode) | なし | なし | **今回追加** (JA) |
