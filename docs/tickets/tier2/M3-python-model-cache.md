# M3: Python 最適化モデルキャッシュ

> **マイルストーン**: [M3](../../guides/cpu-inference-tier2-milestones.md#m3-python-最適化モデルキャッシュ)
> **設計書**: [cpu-inference-tier2-design.md](../../guides/cpu-inference-tier2-design.md#施策-6-python-最適化モデルキャッシュ)
> **ステータス**: 完了
> **依存**: [M1](M1-python-warmup.md) (warmup は cache 後に呼ばれる)
> **後続**: [M4](M4-japanese-phonemize-cache.md), [M5](M5-integration.md)

---

## 1. タスク目的とゴール

**背景:** ONNX Runtime はセッション作成時にグラフ最適化 (定数畳み込み、演算子融合、レイアウト最適化) を毎回実行する。この最適化には 500-800ms のオーバーヘッドがかかり、推論エンドポイントの起動やモデル切り替え時のレイテンシの主要因となっている。Rust (`engine.rs:116-195`) と C# (`SessionFactory.cs:119-179`) は既に最適化済みモデルをディスクにキャッシュする仕組みを実装済みだが、Python 推論パスには未実装。

**目的:** ONNX Runtime の `optimized_model_filepath` 機能を活用し、最適化済みモデルを `.opt.onnx` としてディスクに保存する。2回目以降のセッション作成では最適化をスキップし、起動時間を 500-800ms 短縮する。

**ゴール:**

- `ort_utils.py` に `create_session_with_cache()` 関数を追加し、全 Python 推論パスで利用可能にする
- 初回起動で `model.{device}.opt.onnx` + `model.{device}.opt.onnx.ok` (センチネル) を生成
- 2回目以降は `GraphOptimizationLevel.ORT_DISABLE_ALL` でキャッシュからロード
- 不完全キャッシュ (`.opt.onnx` のみ、`.ok` なし) を検出・削除して再最適化
- 書き込み権限がない環境 (Docker `ro` マウント等) では warning ログのみで通常起動
- Rust/C# と同一のパス命名規則・センチネルパターンを踏襲

**非ゴール:**

- モデルファイルのハッシュ検証 (将来検討。現時点はユーザーに `.opt.onnx` + `.ok` 手動削除を案内)
- ORT バージョン間のキャッシュ互換性保証 (ORT 内部でデシリアライズ失敗時はキャッシュ削除で対処)
- `python_run/piper/voice.py` 以外の Python パッケージ (python_run は `piper_train` を import できないためインライン実装)

---

## 2. 実装内容の詳細

### 2.1 `create_session_with_cache()` コア実装 (`ort_utils.py`)

**ファイル:** `src/python/piper_train/ort_utils.py`

```python
# NOTE: voice.py (python_run) にインライン複製あり。変更時は両方更新すること
def create_session_with_cache(
    model_path: str | Path,
    *,
    device: str = "cpu",
    intra_op_threads: int | None = None,
    inter_op_threads: int = 1,
) -> onnxruntime.InferenceSession:
```

**処理フロー:**

```
create_session_with_cache(model_path, device="cpu")
  |
  +-- PIPER_DISABLE_CACHE チェック → 有効なら通常ロードで即 return
  |
  +-- デバイスラベル生成 ("cpu" or "cuda0")
  +-- キャッシュパス生成: model.{device}.opt.onnx
  +-- センチネルパス生成: model.{device}.opt.onnx.ok
  |
  +-- .opt.onnx + .ok 両方存在?
  |     YES --> ORT_DISABLE_ALL でキャッシュからロード
  |     NO  --> .opt.onnx のみ存在? (不完全)
  |               YES --> 削除して再最適化
  |               NO  --> 初回最適化
  |
  +-- 初回パス:
  |     +-- create_session_options() でベースオプション取得
  |     +-- opts.optimized_model_filepath = cache_path (try/except)
  |     +-- InferenceSession(model_path, opts, providers) 作成
  |     +-- .opt.onnx が存在確認 --> .ok 書き込み (try/except)
  |
  +-- キャッシュヒットパス:
  |     +-- create_session_options() でベースオプション取得
  |     +-- opts.graph_optimization_level = ORT_DISABLE_ALL
  |     +-- InferenceSession(cache_path, opts, providers) 作成
  |
  +-- session を返却
```

**キャッシュパス命名規則** (Rust/C# と統一):

| 元モデル | CPU キャッシュ | CUDA キャッシュ | センチネル |
|----------|---------------|----------------|-----------|
| `/path/to/model.onnx` | `/path/to/model.cpu.opt.onnx` | `/path/to/model.cuda0.opt.onnx` | `/path/to/model.cpu.opt.onnx.ok` |

**デバイスラベル生成ロジック:**

```python
def _get_device_label(device: str) -> str:
    """providers リストから実効デバイスラベルを生成する。"""
    if device in ("gpu", "auto"):
        available = onnxruntime.get_available_providers()
        if "CUDAExecutionProvider" in available:
            return "cuda0"
    return "cpu"
```

> **Note (Rust との差異):** Rust は `device_type.to_string().replace(':', ".")` で `DeviceType` enum からラベルを生成するが、Python の `ort_utils.py` は `DeviceType` enum を持たないため `get_available_providers()` で実効プロバイダを検出する方式を採用している。生成されるラベル文字列 (`"cpu"`, `"cuda0"`) は Rust/C# と同一であり、この差異は意図的な設計判断。

**`PIPER_DISABLE_CACHE` 環境変数:**

デバッグ・テスト用にキャッシュを完全無効化する環境変数を提供する (`PIPER_DISABLE_WARMUP` と同パターン)。

```python
def create_session_with_cache(...) -> onnxruntime.InferenceSession:
    # キャッシュ無効化チェック (PIPER_DISABLE_WARMUP と同パターン)
    if os.environ.get("PIPER_DISABLE_CACHE", "").lower() in ("1", "true", "yes"):
        _logger.info("Model cache disabled via PIPER_DISABLE_CACHE")
        opts = create_session_options(intra_op_threads=intra_op_threads, inter_op_threads=inter_op_threads)
        providers = get_providers(device)
        return onnxruntime.InferenceSession(str(model_path), opts, providers=providers)
    # ... 以降通常のキャッシュロジック
```

用途: CI 環境でキャッシュ副作用を排除したい場合、読み取り専用環境で warning ログを抑制したい場合など。

**例外ハンドリング方針** (Rust/C# と同一):

| 例外シナリオ | 対処 |
|-------------|------|
| `optimized_model_filepath` 設定時の `PermissionError` / `OSError` | warning ログ → キャッシュなしで通常ロード |
| センチネル `.ok` 書き込み失敗 | warning ログ → セッション自体は正常 (次回再最適化されるだけ) |
| 不完全キャッシュ `.opt.onnx` 削除失敗 | warning ログ → 元モデルから通常ロード |
| キャッシュ `.opt.onnx` からのロード失敗 (ORT バージョン非互換等) | キャッシュ + センチネル削除 → 元モデルから再最適化 |

**Rust 参照実装 (`engine.rs:116-201`):**

- `device_label` = `device_type.to_string().replace(':', ".")`
- `optimized_path` = `model_path.with_extension("{device_label}.opt.onnx")`
- `sentinel_path` = `optimized_path + ".ok"`
- キャッシュ有効 = `.opt.onnx` && `.ok` 両方存在
- 不完全キャッシュ = `.opt.onnx` のみ → `remove_file` (ベストエフォート)
- 初回: `with_optimized_model_path()` で ORT に保存指示、成功後 `write(&sentinel_path, b"ok")`
- キャッシュヒット: `GraphOptimizationLevel::Disable` で直接ロード

**C# 参照実装 (`SessionFactory.cs:119-179`):**

- `deviceLabel` = `useCuda ? $"cuda{resolvedDeviceId}" : "cpu"`
- `optimizedPath` = `Path.ChangeExtension(modelPath, $".{deviceLabel}.opt.onnx")`
- `sentinelPath` = `optimizedPath + ".ok"`
- 同一のキャッシュ有効判定 + 不完全キャッシュ削除 + センチネル書き込みパターン

### 2.2 既存 `create_session_options()` との関係

`create_session_options()` は**変更なし**。`create_session_with_cache()` が内部で `create_session_options()` を呼び出してベースオプションを取得し、その上にキャッシュロジックを追加する。既存の呼び出し元は段階的に移行可能。

```
create_session_with_cache()
  |
  +-- opts = create_session_options(intra_op_threads=..., inter_op_threads=...)
  +-- providers = get_providers(device)
  +-- [キャッシュロジック: opts を修正]
  +-- InferenceSession(path, opts, providers)
```

### 2.3 推論スクリプトへの統合

#### 2.3.1 `infer_onnx.py` (`src/python/piper_train/infer_onnx.py`)

**変更箇所 (L289-294):**

```python
# Before:
sess_options = create_session_options()
providers = get_providers(args.device)
model = onnxruntime.InferenceSession(
    str(args.model), sess_options=sess_options, providers=providers
)

# After:
from .ort_utils import create_session_with_cache
model = create_session_with_cache(args.model, device=args.device)
# M1 warmup: キャッシュロード後にダミー推論で JIT コストを吸収 (M1 実装後に追加)
# warmup_onnx_session(model)
```

import 文の `create_session_options, get_providers` はまだ他で使われていないため削除可能。ただし `get_providers` は残す (`create_session_with_cache` 内部で使用するため外部 import は不要になる)。

> **M1 連携:** `create_session_with_cache()` の直後が warmup の呼び出し位置。初期化フロー全体: **cache load (M3)** → **warmup (M1)** → リクエスト受付。M1 が先に実装されている場合はコメントアウトを解除する。

#### 2.3.2 `docker/python-inference/inference.py`

**変更箇所 (`PiperInferenceEngine.__init__`, L99-104):**

```python
# Before:
sess_options = create_session_options()
providers = get_providers(device)
self.model = onnxruntime.InferenceSession(
    model_path, sess_options=sess_options, providers=providers
)

# After:
from piper_train.ort_utils import create_session_with_cache
self.model = create_session_with_cache(model_path, device=device)
# M1 warmup: cache load 後にダミー推論 (M1 実装後に追加)
# warmup_onnx_session(self.model)
```

#### 2.3.3 `docker/webui/app.py`

**変更箇所 (`_get_session()`, L38-50):**

```python
# Before:
def _get_session(model_path: str) -> onnxruntime.InferenceSession:
    with _cache_lock:
        if model_path not in _session_cache:
            sess_options = create_session_options(intra_op_threads=1)
            _session_cache[model_path] = onnxruntime.InferenceSession(
                model_path,
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )
        return _session_cache[model_path]

# After:
from piper_train.ort_utils import create_session_with_cache

def _get_session(model_path: str) -> onnxruntime.InferenceSession:
    with _cache_lock:
        if model_path not in _session_cache:
            session = create_session_with_cache(
                model_path, device="cpu", intra_op_threads=1
            )
            # M1 warmup: cache load 後にダミー推論 (M1 実装後に追加)
            # warmup_onnx_session(session)
            _session_cache[model_path] = session
        return _session_cache[model_path]
```

WebUI のインメモリキャッシュ (`_session_cache`) とディスクキャッシュ (`.opt.onnx`) は異なるレイヤーで共存する。インメモリキャッシュはプロセス内でのセッション再利用、ディスクキャッシュはプロセス再起動時の最適化スキップを担当。

#### 2.3.4 `src/python_run/piper/voice.py`

**制約:** `piper_train` パッケージを import できない独立配布パッケージのため、インラインでキャッシュロジックを実装する。

**コード同期戦略:**

`voice.py` のインライン実装と `ort_utils.py` のコア実装の乖離を防止するため、以下を全て実施する:

1. **明示的な同期コメント:** `voice.py` のキャッシュロジック冒頭に `# === Model cache logic: Keep in sync with piper_train.ort_utils.create_session_with_cache() ===` コメントを追加。`ort_utils.py` 側にも `# NOTE: voice.py (python_run) にインライン複製あり。変更時は両方更新すること` を追加。

2. **自動パリティテスト:** `tests/test_ort_utils.py` に `TestVoiceCacheParity` クラスを追加し、両実装が同一のキャッシュパス生成・センチネル判定を行うことを検証する:

```python
class TestVoiceCacheParity:
    """voice.py インライン実装と ort_utils.py の同期を検証."""

    def test_cache_path_naming_parity(self, tmp_path):
        """両実装が同一のキャッシュパス命名規則を使用すること."""
        model = tmp_path / "model.onnx"
        # ort_utils: _build_cache_paths() のロジック
        from piper_train.ort_utils import _build_cache_paths
        ort_cache, ort_sentinel = _build_cache_paths(model, "cpu")
        # voice.py: インラインロジック再現
        voice_cache = model.with_suffix(".cpu.opt.onnx")
        voice_sentinel = Path(str(voice_cache) + ".ok")
        assert ort_cache == voice_cache
        assert ort_sentinel == voice_sentinel

    def test_cache_path_naming_parity_cuda(self, tmp_path):
        """CUDA パスも同一であること."""
        model = tmp_path / "model.onnx"
        from piper_train.ort_utils import _build_cache_paths
        ort_cache, ort_sentinel = _build_cache_paths(model, "cuda0")
        voice_cache = model.with_suffix(".cuda0.opt.onnx")
        voice_sentinel = Path(str(voice_cache) + ".ok")
        assert ort_cache == voice_cache
        assert ort_sentinel == voice_sentinel
```

3. **レビューチェックリスト項目:** セクション 5.2 に `voice.py` 同期確認項目を追加 (下記参照)。

**変更箇所 (`PiperVoice.load()`, L59-102):**

`sess_options` 構築後、`InferenceSession` 作成前にキャッシュロジックを挿入:

```python
# === Model cache logic: Keep in sync with piper_train.ort_utils.create_session_with_cache() ===
# PIPER_DISABLE_CACHE 環境変数チェック
_disable_cache = os.environ.get("PIPER_DISABLE_CACHE", "").lower() in ("1", "true", "yes")

# キャッシュパス生成
model_p = Path(model_path)
device_label = "cuda0" if use_cuda else "cpu"
cache_path = model_p.with_suffix(f".{device_label}.opt.onnx")
sentinel_path = Path(str(cache_path) + ".ok")
use_cached = (not _disable_cache) and cache_path.exists() and sentinel_path.exists()

if _disable_cache:
    _LOGGER.info("Model cache disabled via PIPER_DISABLE_CACHE")
    effective_model_path = str(model_path)
elif use_cached:
    _LOGGER.info("Loading pre-optimized model from %s", cache_path)
    sess_options.graph_optimization_level = (
        onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL
    )
    effective_model_path = str(cache_path)
else:
    # 不完全キャッシュ削除
    if cache_path.exists() and not sentinel_path.exists():
        _LOGGER.warning("Removing incomplete cache %s (missing sentinel)", cache_path)
        try:
            cache_path.unlink()
        except OSError:
            pass
    # optimized_model_filepath 設定 (書込権限がなければスキップ)
    try:
        sess_options.optimized_model_filepath = str(cache_path)
    except Exception as exc:
        _LOGGER.warning(
            "Could not set optimized model path %s: %s (continuing without cache)",
            cache_path, exc,
        )
    effective_model_path = str(model_path)

session = onnxruntime.InferenceSession(
    effective_model_path, sess_options=sess_options, providers=providers,
)

# センチネル書き込み (キャッシュ無効化時はスキップ)
if not _disable_cache and not use_cached and cache_path.exists():
    try:
        sentinel_path.write_text("ok")
        _LOGGER.info("Cache sentinel written: %s", sentinel_path)
    except OSError as exc:
        _LOGGER.warning("Failed to write sentinel %s: %s", sentinel_path, exc)
```

### 2.4 HF Space CI への影響確認

`.github/workflows/test-hf-space.yml` と `.github/workflows/deploy-huggingface.yml` を確認し、新関数の追加がテスト/デプロイに影響しないことを検証する。HF Space 環境ではモデルディレクトリが読み取り専用の場合があるため、`PermissionError` のフォールバックが正しく機能することが重要。

---

## 3. エージェントチームの構成

| エージェント | 担当 | 主要ファイル |
|-------------|------|------------|
| **Agent A (コア実装)** | `create_session_with_cache()` + ヘルパー関数 | `src/python/piper_train/ort_utils.py` |
| **Agent B (統合)** | 推論スクリプト 4 箇所への統合 | `infer_onnx.py`, `voice.py`, `inference.py`, `app.py` |
| **Agent C (テスト)** | ユニットテスト + E2E テスト | `tests/test_ort_utils.py` |

**実行順序:**

1. Agent A がコア関数を実装
2. Agent B が統合 (Agent A 完了後)、Agent C がユニットテスト (Agent A と並行可能)
3. Agent C が E2E テスト (Agent B 完了後)

**推定工数:** 各エージェント 15-25 分、合計 45-75 分。

---

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**変更ファイル:**

| ファイル | 変更内容 |
|----------|---------|
| `src/python/piper_train/ort_utils.py` | `create_session_with_cache()`, `_get_device_label()`, `_build_cache_paths()` 追加 |
| `src/python/piper_train/infer_onnx.py` | `InferenceSession()` 直接構築 → `create_session_with_cache()` に置換 |
| `docker/python-inference/inference.py` | 同上 |
| `docker/webui/app.py` | `_get_session()` 内で `create_session_with_cache()` 使用 |
| `src/python_run/piper/voice.py` | インラインキャッシュロジック追加 (import 制約) |
| `tests/test_ort_utils.py` | `TestModelCache` + `TestVoiceCacheParity` クラス追加 |

**変更しないファイル:**

| ファイル | 理由 |
|----------|------|
| `create_session_options()` | 後方互換維持。新関数が内部で呼び出す |
| `get_providers()` | 変更不要 |
| Rust/C# 実装 | 参照のみ、変更なし |

### 4.2 ユニットテスト

**ファイル:** `tests/test_ort_utils.py` に `TestModelCache` クラス追加

| テスト名 | 内容 | 検証ポイント |
|---------|------|------------|
| `test_cache_creation` | 初回ロード | `.opt.onnx` と `.ok` が生成されること |
| `test_cache_hit` | 2回目ロード | `GraphOptimizationLevel.ORT_DISABLE_ALL` で読み込まれること (モック検証) |
| `test_incomplete_cache_deleted` | `.opt.onnx` のみ存在 (`.ok` なし) | 不完全キャッシュが削除されて再最適化が実行されること |
| `test_readonly_filesystem` | `PermissionError` 発生環境 | warning ログが出力され、通常の最適化で推論が正常に動作すること |
| `test_device_label_cpu` | `device="cpu"` | パスに `.cpu.opt.onnx` が含まれること |
| `test_device_label_cuda` | `device="gpu"` + CUDA 利用可能 | パスに `.cuda0.opt.onnx` が含まれること |
| `test_sentinel_write_failure` | センチネル書き込み失敗 | warning ログのみ、セッションは正常に返却されること |
| `test_cache_load_failure_fallback` | キャッシュからのロード失敗 (ORT 非互換) | キャッシュ + センチネル削除 → 元モデルから再最適化 |
| `test_disable_cache_env` | `PIPER_DISABLE_CACHE=1` | キャッシュ生成せず通常ロード |

**モック戦略:**

`onnxruntime.InferenceSession` をモックし、実際の ONNX モデルファイルなしでテスト可能にする。`tmp_path` でファイルシステム操作を実環境で検証する。

```python
from unittest.mock import MagicMock, patch
from pathlib import Path
import onnxruntime

@pytest.fixture
def mock_session():
    """onnxruntime.InferenceSession のモック."""
    session = MagicMock(spec=onnxruntime.InferenceSession)
    session.get_providers.return_value = ["CPUExecutionProvider"]
    session.get_inputs.return_value = []
    return session

class TestModelCache:
    def test_cache_hit_uses_disable_all(self, tmp_path, mock_session):
        """キャッシュヒット時に ORT_DISABLE_ALL が設定されること."""
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")
        cache = tmp_path / "model.cpu.opt.onnx"
        cache.write_bytes(b"optimized")
        sentinel = tmp_path / "model.cpu.opt.onnx.ok"
        sentinel.write_text("ok")

        captured_opts = {}

        def capture_session(path, sess_options=None, providers=None):
            captured_opts["level"] = sess_options.graph_optimization_level
            captured_opts["path"] = path
            return mock_session

        with patch("onnxruntime.InferenceSession", side_effect=capture_session):
            from piper_train.ort_utils import create_session_with_cache
            create_session_with_cache(model, device="cpu")

        # キャッシュヒット: ORT_DISABLE_ALL + キャッシュパスからロード
        assert captured_opts["level"] == onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL
        assert captured_opts["path"] == str(cache)

    def test_cache_miss_sets_optimized_filepath(self, tmp_path, mock_session):
        """キャッシュミス時に optimized_model_filepath が設定されること."""
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")

        captured_opts = {}

        def capture_session(path, sess_options=None, providers=None):
            captured_opts["optimized"] = sess_options.optimized_model_filepath
            captured_opts["path"] = path
            # ORT がキャッシュファイルを生成することをシミュレート
            cache = tmp_path / "model.cpu.opt.onnx"
            cache.write_bytes(b"optimized")
            return mock_session

        with patch("onnxruntime.InferenceSession", side_effect=capture_session):
            from piper_train.ort_utils import create_session_with_cache
            create_session_with_cache(model, device="cpu")

        # キャッシュミス: 元モデルパスからロード + optimized_model_filepath 設定
        expected_cache = str(tmp_path / "model.cpu.opt.onnx")
        assert captured_opts["optimized"] == expected_cache
        assert captured_opts["path"] == str(model)
        # センチネル生成確認
        assert (tmp_path / "model.cpu.opt.onnx.ok").exists()

    @patch.dict("os.environ", {"PIPER_DISABLE_CACHE": "1"})
    def test_disable_cache_env(self, tmp_path, mock_session):
        """PIPER_DISABLE_CACHE=1 → キャッシュ生成なし."""
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")

        with patch("onnxruntime.InferenceSession", return_value=mock_session):
            from piper_train.ort_utils import create_session_with_cache
            create_session_with_cache(model, device="cpu")

        assert not (tmp_path / "model.cpu.opt.onnx").exists()
        assert not (tmp_path / "model.cpu.opt.onnx.ok").exists()
```

**モック方針まとめ:**

| 検証対象 | モック手法 |
|---------|-----------|
| `InferenceSession` | `unittest.mock.patch` で差し替え。`side_effect` で `sess_options` の属性をキャプチャ |
| ファイルシステム | `tmp_path` (pytest) で実ファイル操作。モデルファイルは `b"dummy"` の最小バイト列 |
| 環境変数 | `@patch.dict("os.environ", ...)` で `PIPER_DISABLE_CACHE` 等を注入 |
| 読み取り専用FS | `tmp_path` 内ディレクトリの `os.chmod(0o444)` または `Path.write_text` の `patch` で `PermissionError` を発生させる |

### 4.3 E2E テスト

| テスト | 内容 | 実行方法 |
|--------|------|---------|
| テストモデルでのキャッシュ往復 | `test/models/` 配下のテストモデルでキャッシュ作成 → 削除 → 再作成 | `uv run pytest` (テストモデルが利用可能な場合) |
| `infer_onnx.py` E2E | `--text` モードでキャッシュファイルが生成されることを確認 | 手動実行 (CI ではテストモデル依存) |
| WebUI セッションキャッシュ | `_get_session()` 呼び出し後にディスクキャッシュが存在することを確認 | 手動実行 |

**完了基準:**

- [x] `uv run pytest tests/test_ort_utils.py -k TestModelCache` 全 PASS
- [x] `uv run pytest tests/test_ort_utils.py -k TestVoiceCacheParity` 全 PASS
- [x] `uv run ruff check && uv run ruff format --check` PASS
- [x] 既存の `test_ort_utils.py` テストに退行なし

---

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| # | 懸念 | 影響度 | 対策 |
|---|------|--------|------|
| 1 | **読み取り専用ファイルシステム** (Docker `ro` マウント、HF Space) | 中 | `PermissionError` / `OSError` を try/except でキャッチ → warning ログ → キャッシュなしで通常起動。Rust/C# と同一パターン |
| 2 | **ORT バージョン変更でキャッシュ非互換** | 低 | ORT 内部でデシリアライズ失敗 → 例外キャッチ → キャッシュ + センチネル削除 → 再最適化。ユーザー操作不要 |
| 3 | **複数プロセス同時書き込みの race condition** | 低 | 最悪でも再最適化が走るだけ (データ破損なし)。センチネルパターンにより不完全ファイルは次回検出・削除される |
| 4 | **モデル更新後の古いキャッシュ** | 低 | 現時点はユーザーに `.opt.onnx` + `.ok` 手動削除を案内。将来的にモデルファイルの mtime またはハッシュによる自動無効化を検討 |
| 5 | **`voice.py` のインライン実装がコア実装と乖離するリスク** | 中 | 3層防御: (a) 両ファイルに `# Keep in sync with ...` コメント、(b) `TestVoiceCacheParity` でパス命名の自動パリティテスト、(c) レビューチェックリストに同期確認項目 (下記 #9) |
| 6 | **WebUI のインメモリキャッシュとの二重キャッシュ** | 極低 | 異なるレイヤー (プロセス内 vs ディスク) のため問題なし。インメモリキャッシュは一度ロードしたセッションの再利用、ディスクキャッシュはプロセス再起動時の最適化スキップ |

### 5.2 レビューチェックリスト

- [x] **パス命名規則**: `.{device}.opt.onnx` + `.{device}.opt.onnx.ok` が Rust (`engine.rs:120-126`) / C# (`SessionFactory.cs:122-124`) と完全一致すること
- [x] **センチネルパターン**: (1) `.opt.onnx` + `.ok` 両方存在 → キャッシュヒット、(2) `.opt.onnx` のみ → 削除 + 再最適化、(3) どちらもなし → 初回最適化。3 パターン全てが Rust/C# と同一であること
- [x] **例外ハンドリング**: `optimized_model_filepath` 設定失敗、センチネル書き込み失敗、不完全キャッシュ削除失敗 — 全てが warning ログのみで非致命的に続行すること
- [x] **`ORT_DISABLE_ALL`**: キャッシュヒット時に `graph_optimization_level = ORT_DISABLE_ALL` が設定されていること (再最適化の二重実行を防止)
- [x] **`create_session_options()` 非破壊**: 既存関数のシグネチャ・動作に変更がないこと
- [x] **`voice.py` インライン実装**: `ort_utils.py` のコア実装と同一のロジック (パス生成、キャッシュ判定、センチネル、フォールバック) であること
- [x] **ログメッセージ**: Rust (`tracing::info!`) / C# (`logger.LogInformation`) と同等のメッセージを `_logger.info()` / `_logger.warning()` で出力すること
- [x] **テスト網羅性**: 正常系 (作成 + ヒット) + 異常系 (不完全キャッシュ、権限エラー、ロード失敗) が全てカバーされていること
- [x] **`voice.py` 同期コメント**: `voice.py` に `# === Model cache logic: Keep in sync with piper_train.ort_utils.create_session_with_cache() ===` が存在し、`ort_utils.py` に `# NOTE: voice.py (python_run) にインライン複製あり。変更時は両方更新すること` が存在すること
- [x] **`TestVoiceCacheParity`**: `tests/test_ort_utils.py` にパリティテストが存在し、CPU/CUDA 両方のパス命名が検証されていること
- [x] **`PIPER_DISABLE_CACHE`**: `ort_utils.py` と `voice.py` の両方で `PIPER_DISABLE_CACHE` 環境変数に対応していること
- [x] **Warmup 統合コメント**: 各統合箇所 (`infer_onnx.py`, `inference.py`, `app.py`) に `# M1 warmup: ...` コメントが記載されていること

---

## 6. 一から作り直すとしたら

1. **モデルハッシュによる自動無効化**: 現在のセンチネルファイルには「ok」の 2 バイトしか書かれない。元モデルの SHA256 ハッシュ (または mtime + size) をセンチネルに記録し、モデル更新時にキャッシュを自動無効化すれば、ユーザーが手動で `.opt.onnx` を削除する必要がなくなる。Rust/C# にもこの改善を横展開できる。

2. **`voice.py` のコード共有**: `piper_train` を import できない制約のためインライン実装が必要だが、キャッシュロジックを `ort_cache.py` のような独立した小さなモジュールに切り出し、`voice.py` と `ort_utils.py` の両方からインポートできるようにすれば、コード重複を排除できる。ただし `python_run` パッケージの依存関係を増やすトレードオフがある。

3. **キャッシュディレクトリの設定可能化**: 現在はモデルと同じディレクトリにキャッシュを書き込む。`PIPER_CACHE_DIR` 環境変数で書き込み先を変更できるようにすれば、読み取り専用マウントの問題を根本的に解決できる (例: `/tmp/piper-cache/`)。

4. **統一 API でのセッション作成**: 将来的に warmup (M1) + cache (M3) を統合した `create_optimized_session()` 高レベル API を提供し、呼び出し元は 1 関数で最適化されたセッションを取得できるようにする。現在は `create_session_with_cache()` → `warmup_onnx_session()` の 2 ステップ。

---

## 7. 後続タスクへの連絡事項

### M1 (Python Warmup) への注意

- `warmup_onnx_session()` は `create_session_with_cache()` が返したセッションに対して呼び出される
- M1 と M3 が統合される場合、呼び出し順は: **キャッシュロード → warmup** (キャッシュヒット時でも warmup は必要。ORT の JIT 最適化はセッション作成とは別のレイヤー)
- `infer_onnx.py` 等の統合箇所では `model = create_session_with_cache(...)` の直後に `warmup_onnx_session(model)` を呼ぶ

### M4 (日本語音素化キャッシュ) への注意

- M3 は推論セッションのキャッシュ、M4 は音素化結果のキャッシュ — 完全に独立したレイヤー
- 両方が有効な場合の起動シーケンス: `create_session_with_cache()` → `warmup_onnx_session()` → (リクエスト受信) → `lru_cache` 付き音素化 → `session.run()`

### M5 (最終統合) への注意

- M3 で `ort_utils.py` に追加される関数のシグネチャが確定してから、M5 のドキュメント更新 (`docs/guides/cpu-inference-optimization.md`) を行うこと
- 実装間設定比較テーブルに「モデルキャッシュ」の行を追加し、Python/Rust/C# の対応状況を記載すること
- CI ワークフロー (`test-hf-space.yml`, `deploy-huggingface.yml`) でキャッシュ関連のテストが通過することを確認すること
