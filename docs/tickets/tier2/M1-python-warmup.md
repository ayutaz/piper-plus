# M1: Python Warmup 実装

> **マイルストーン**: [M1](../../guides/cpu-inference-tier2-milestones.md#m1-python-warmup-実装)
> **設計書**: [cpu-inference-tier2-design.md](../../guides/cpu-inference-tier2-design.md#施策-7-onnx-runtime-warmup)
> **ステータス**: 未着手
> **依存**: なし (独立して実装可能)
> **後続**: [M2](M2-cpp-warmup.md), [M3](M3-python-model-cache.md)

---

## 1. タスク目的とゴール

### 背景

ONNX Runtime は初回 `session.run()` 呼び出し時に JIT コンパイルとメモリアロケーション最適化を実行するため、500-800ms の初回遅延が発生する。この遅延はユーザーの最初のリクエストに影響を与え、RTF (Real-Time Factor) の標準偏差を増大させる。Rust (`engine.rs:420-434`) と C# (`SessionFactory.cs:220-317`) では既にダミー推論による warmup が実装済みだが、Python の全推論エントリポイント (5箇所) では未対応。

### ゴール

1. `ort_utils.py` に共有 warmup 関数を追加し、全 Python 推論パスで初回遅延を解消する
2. 初回推論のレイテンシを 500-800ms 安定化させる (warmup で JIT コストを吸収)
3. RTF の標準偏差を約 30% 低減する
4. warmup 失敗がアプリケーション動作に影響しないことを保証する (非致命的設計)

### 成功基準

- [ ] 全 5 箇所の Python 推論エントリポイントで warmup が呼び出される
- [ ] Rust/C# と同一のダミー入力パラメータ (100 phonemes, scales=[0.667, 1.0, 0.8])
- [ ] warmup 例外がアプリケーションをクラッシュさせない
- [ ] `PIPER_DISABLE_WARMUP=1` で無効化可能
- [ ] 既存テスト全 PASS + 新規テスト 5件以上 PASS

---

## 2. 実装内容の詳細

### M1.1: `warmup_onnx_session()` コア実装

**ファイル**: `src/python/piper_train/ort_utils.py`

既存の `create_session_options()` と `get_providers()` の後に追加する。

**注意**: `ort_utils.py` の既存ロガー変数は `_logger` (小文字) だが、プロジェクト内の他ファイル (`infer_onnx.py`, `infer_onnx_streaming.py`, `voice.py`, `inference.py`) は全て `_LOGGER` (大文字) を使用している。一貫性のため、`ort_utils.py` のロガー変数名を `_logger` → `_LOGGER` にリネームすること (`_logger = logging.getLogger(__name__)` → `_LOGGER = logging.getLogger(__name__)` + 既存参照箇所の更新)。

```python
import time
import numpy as np

# --- 定数 (Rust/C# と統一) ---
WARMUP_PHONEME_LENGTH = 100
"""warmup 用ダミー phoneme 入力長。本番入力 (50-200) と同程度の形状で
ORT メモリアロケーションを温める。Rust/C# と同一値。"""

DEFAULT_WARMUP_RUNS = 2
"""ORT JIT キャッシュは 1-2 回で安定。2 回で安全マージン確保。"""


def warmup_onnx_session(
    session: onnxruntime.InferenceSession,
    *,
    runs: int = DEFAULT_WARMUP_RUNS,
    phoneme_length: int = WARMUP_PHONEME_LENGTH,
) -> None:
    """ONNX Runtime セッションを warmup する。

    ダミー phoneme ID でモデルを ``runs`` 回実行し、ORT の JIT コンパイルと
    メモリプール初期化を事前に完了させる。全例外をキャッチし warning ログに
    留めるため、呼び出し元の動作には影響しない。

    Rust ``PiperEngine::warmup()`` (engine.rs:420-434) および
    C# ``SessionFactory.Warmup()`` (SessionFactory.cs:210-306) と
    同一のダミー入力パラメータを使用する。

    Args:
        session: 推論セッション
        runs: warmup 実行回数 (デフォルト: 2)
        phoneme_length: ダミー phoneme 入力長 (デフォルト: 100)

    Environment Variables:
        PIPER_DISABLE_WARMUP: ``1``, ``true``, ``yes`` のいずれかで warmup を無効化
    """
```

**実装詳細**:

1. **環境変数チェック**: `os.environ.get("PIPER_DISABLE_WARMUP", "")` を `("1", "true", "yes")` と照合。一致すれば `_LOGGER.info("Warmup disabled via PIPER_DISABLE_WARMUP")` で即 return
2. **runs ガード**: `runs <= 0` なら即 return
3. **ダミー入力構築**:
   - `phoneme_ids`: `np.array` shape `(1, phoneme_length)`, dtype `int64`
     - `[0] = 1` (BOS), `[1:-1] = 8` (dummy phoneme), `[-1] = 2` (EOS)
   - `input_lengths`: `np.array([phoneme_length])`, dtype `int64`
   - `scales`: `np.array([0.667, 1.0, 0.8])`, dtype `float32` (Rust/C# と同一)
4. **オプション入力の動的検出**: `session.get_inputs()` で入力名リストを取得し、以下を条件付きで追加:
   - `"sid"` が存在 → `np.array([0], dtype=np.int64)`
   - `"lid"` が存在 → `np.array([0], dtype=np.int64)`
   - `"prosody_features"` が存在 → `np.zeros((1, phoneme_length, 3), dtype=np.int64)`
5. **出力名**: `session.get_outputs()` から名前リストを取得して `session.run()` に渡す (モデルが `"durations"` 出力を持つ場合にも対応)
6. **実行ループ**: `for i in range(runs): session.run(output_names, inputs)`
7. **タイミングログ**: `time.perf_counter()` で計測し `_LOGGER.info("Warmup completed (%d runs in %.0fms)", runs, elapsed_ms)` を出力
8. **例外処理**: 外側の `try/except Exception` で全例外をキャッチし `_LOGGER.warning("Warmup failed (non-fatal): %s", e)` で続行

**Rust/C# との対応表**:

| パラメータ | Rust (`engine.rs`) | C# (`SessionFactory.cs`) | Python (今回) |
|-----------|-------------------|--------------------------|--------------|
| phoneme_length | `WARMUP_PHONEME_LENGTH = 100` | `WarmupPhonemeLength = 100` | `WARMUP_PHONEME_LENGTH = 100` |
| default_runs | 2 (呼び出し元で指定) | `DefaultWarmupRuns = 2` | `DEFAULT_WARMUP_RUNS = 2` |
| BOS token | 1 | 1 | 1 |
| EOS token | 2 | 2 | 2 |
| dummy phoneme | 8 | 8 | 8 |
| scales | `[0.667, 1.0, 0.8]` | `[0.667f, 1.0f, 0.8f]` | `[0.667, 1.0, 0.8]` |
| sid (optional) | `SynthesisRequest::default()` | `metadata.ContainsKey("sid")` | `"sid" in input_names` |
| lid (optional) | (同上) | `metadata.ContainsKey("lid")` | `"lid" in input_names` |
| prosody (optional) | (同上) | `metadata.ContainsKey("prosody_features")` | `"prosody_features" in input_names` |
| 例外処理 | `Result<(), PiperError>` (呼び出し元で処理) | `catch (Exception)` → `LogWarning` | `except Exception` → `_LOGGER.warning` |

### M1.2: Python 推論スクリプトへの統合

各ファイルで session 作成直後に `warmup_onnx_session()` を 1 行追加する。

#### M1.2.1: `infer_onnx.py`

**ファイル**: `src/python/piper_train/infer_onnx.py`

**変更箇所**: `main()` 関数内、L292-297 の session 作成直後 (L297 の `_LOGGER.info("Loaded model ...")` の後)

```python
# 既存コード (L289-297)
sess_options = create_session_options()
providers = get_providers(args.device)
_LOGGER.debug("Loading model from %s", args.model)
model = onnxruntime.InferenceSession(
    str(args.model), sess_options=sess_options, providers=providers
)
_LOGGER.info("Loaded model from %s (providers: %s)", args.model, model.get_providers())

# ↓ 追加
from .ort_utils import warmup_onnx_session  # import は先頭に移動
warmup_onnx_session(model)
```

**import 変更**: ファイル先頭の `from .ort_utils import create_session_options, get_providers` に `warmup_onnx_session` を追加。

#### M1.2.2: `infer_onnx_streaming.py`

**ファイル**: `src/python/piper_train/infer_onnx_streaming.py`

**変更箇所**: `SpeechStreamer.__init__()` 内、encoder session 作成後 (L46 の後)

```python
# 既存コード (L42-50)
sess_options = create_session_options()
_LOGGER.debug("Loading encoder model from %s", encoder_path)
self.encoder = onnxruntime.InferenceSession(
    encoder_path, sess_options=sess_options
)
_LOGGER.debug("Loading decoder model from %s", decoder_path)
self.decoder = onnxruntime.InferenceSession(
    decoder_path, sess_options=sess_options
)

# ↓ encoder のみ warmup (decoder は encoder 出力を入力とするため warmup 不可)
warmup_onnx_session(self.encoder)
```

**注意**: ストリーミングモデルの encoder は通常の VITS モデルと同一の入力シグネチャ (`input`, `input_lengths`, `scales` + オプション) を持つため、同じ warmup 関数が使える。decoder は `z`, `y_mask` 等の encoder 出力を入力とするため、独立して warmup できない。encoder の warmup だけで ORT の JIT キャッシュは十分に温まる。

**import 変更**: 既存の import 行 `from .ort_utils import create_session_options` (L15) を以下に変更:

```python
from .ort_utils import create_session_options, warmup_onnx_session
```

#### M1.2.3: `voice.py` (python_run)

**ファイル**: `src/python_run/piper/voice.py`

**変更箇所**: `PiperVoice.load()` 静的メソッド内、session 作成後 (L95-102 の `return PiperVoice(...)` の前)

`python_run` パッケージは `piper_train` を import できないため、warmup ロジックをインラインで実装する。

```python
@staticmethod
def load(model_path, config_path=None, use_cuda=False):
    # ... 既存の session 作成コード (L59-100) ...

    session = onnxruntime.InferenceSession(
        str(model_path), sess_options=sess_options, providers=providers,
    )

    # ↓ インライン warmup 追加
    _warmup_session(session)

    return PiperVoice(
        config=PiperConfig.from_dict(config_dict),
        session=session,
    )
```

モジュールレベルに以下のヘルパー関数を追加:

```python
def _warmup_session(
    session: onnxruntime.InferenceSession,
    runs: int = 2,
    phoneme_length: int = 100,
) -> None:
    """Inline warmup (piper_train.ort_utils が import 不可のため)."""
    if os.environ.get("PIPER_DISABLE_WARMUP", "").lower() in ("1", "true", "yes"):
        return
    if runs <= 0:
        return
    try:
        import numpy as np  # voice.py は既に numpy を import 済み

        phoneme_ids = np.full((1, phoneme_length), 8, dtype=np.int64)
        phoneme_ids[0, 0] = 1   # BOS
        phoneme_ids[0, -1] = 2  # EOS
        input_lengths = np.array([phoneme_length], dtype=np.int64)
        scales = np.array([0.667, 1.0, 0.8], dtype=np.float32)

        input_names = {inp.name for inp in session.get_inputs()}
        inputs = {
            "input": phoneme_ids,
            "input_lengths": input_lengths,
            "scales": scales,
        }
        if "sid" in input_names:
            inputs["sid"] = np.array([0], dtype=np.int64)
        if "lid" in input_names:
            inputs["lid"] = np.array([0], dtype=np.int64)
        if "prosody_features" in input_names:
            inputs["prosody_features"] = np.zeros(
                (1, phoneme_length, 3), dtype=np.int64
            )

        output_names = [o.name for o in session.get_outputs()]
        for _ in range(runs):
            session.run(output_names, inputs)

        _LOGGER.info("Warmup completed (%d runs)", runs)
    except Exception as e:
        _LOGGER.warning("Warmup failed (non-fatal): %s", e)
```

#### M1.2.4: `docker/python-inference/inference.py`

**ファイル**: `docker/python-inference/inference.py`

**変更箇所**: `PiperInferenceEngine.__init__()` 内、session 作成後 (L102-104 の後)

```python
# 既存コード (L100-104)
sess_options = create_session_options()
providers = get_providers(device)
self.model = onnxruntime.InferenceSession(
    model_path, sess_options=sess_options, providers=providers
)

# ↓ 追加
warmup_onnx_session(self.model)
```

**import 変更**: `from piper_train.ort_utils import create_session_options, get_providers` に `warmup_onnx_session` を追加。

#### M1.2.5: `docker/webui/app.py`

**ファイル**: `docker/webui/app.py`

**変更箇所**: `_get_session()` 関数内、キャッシュロック内で session 作成直後

```python
def _get_session(model_path: str) -> onnxruntime.InferenceSession:
    """Return a cached InferenceSession, creating one if needed."""
    with _cache_lock:
        if model_path not in _session_cache:
            sess_options = create_session_options(intra_op_threads=1)
            session = onnxruntime.InferenceSession(
                model_path,
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )
            warmup_onnx_session(session)  # キャッシュロック内 → 1モデル1回のみ
            _session_cache[model_path] = session
        return _session_cache[model_path]
```

**import 変更**: `from piper_train.ort_utils import create_session_options` に `warmup_onnx_session` を追加。

**注意 (logger 追加)**: `docker/webui/app.py` には現在モジュールレベルのロガーが定義されていない。`warmup_onnx_session()` 内部のログ出力は `ort_utils.py` 側のロガー (`_LOGGER`) を使用するため `app.py` 側にロガーは不要だが、将来的な保守性のためにファイル先頭の import 群の後に以下を追加することを推奨する:

```python
import logging

_LOGGER = logging.getLogger(__name__)
```

`docker/python-inference/inference.py` は既に `_LOGGER = logging.getLogger(__name__)` を持つため追加不要。

**重要**: warmup はキャッシュロック (`_cache_lock`) 内で実行される。これにより同一モデルに対して warmup が 1 回だけ実行されることが保証される。warmup 所要時間 (~1-2秒) はロック保持時間に加算されるが、WebUI の起動時にのみ発生するため実用上問題ない。

### M1.3: Python Warmup テスト

**ファイル**: `src/python/tests/test_ort_utils.py` (既存ファイルに追加)

既存の `TestCreateSessionOptions`, `TestGetProviders` 等のクラスの後に `TestWarmup` クラスを追加する。

```python
from unittest.mock import MagicMock, patch, call
import logging

@pytest.mark.unit
class TestWarmup:
    """warmup_onnx_session() のテスト."""

    def _make_mock_session(self, *, has_sid=False, has_lid=False, has_prosody=False):
        """オプション入力を制御可能なモック session を作成.

        注意: MagicMock(name=...) の name= はモックの repr 名であり、
        .name 属性ではない。warmup_onnx_session() は inp.name で入力名を
        取得するため、.name を明示的に設定する必要がある。
        """
        session = MagicMock()
        inputs = [
            MagicMock(),  # input
            MagicMock(),  # input_lengths
            MagicMock(),  # scales
        ]
        inputs[0].name = "input"
        inputs[1].name = "input_lengths"
        inputs[2].name = "scales"
        if has_sid:
            sid_input = MagicMock()
            sid_input.name = "sid"
            inputs.append(sid_input)
        if has_lid:
            lid_input = MagicMock()
            lid_input.name = "lid"
            inputs.append(lid_input)
        if has_prosody:
            prosody_input = MagicMock()
            prosody_input.name = "prosody_features"
            inputs.append(prosody_input)

        session.get_inputs.return_value = inputs

        output = MagicMock()
        output.name = "output"
        session.get_outputs.return_value = [output]
        session.run.return_value = [np.zeros((1, 1, 22050))]
        return session

    def test_warmup_completes_successfully(self):
        """正常系: session.run が runs 回呼ばれる."""
        session = self._make_mock_session()
        warmup_onnx_session(session, runs=2)
        assert session.run.call_count == 2

    def test_warmup_failure_is_non_fatal(self, caplog):
        """session.run が例外 → warning ログのみで非致命的."""
        session = self._make_mock_session()
        session.run.side_effect = RuntimeError("ORT internal error")
        with caplog.at_level(logging.WARNING):
            warmup_onnx_session(session)  # 例外で落ちないことを確認
        assert "Warmup failed" in caplog.text

    @patch.dict("os.environ", {"PIPER_DISABLE_WARMUP": "1"})
    def test_disable_warmup_env_1(self):
        """PIPER_DISABLE_WARMUP=1 → session.run 未呼出."""
        session = self._make_mock_session()
        warmup_onnx_session(session)
        session.run.assert_not_called()

    @patch.dict("os.environ", {"PIPER_DISABLE_WARMUP": "true"})
    def test_disable_warmup_env_true(self):
        """PIPER_DISABLE_WARMUP=true → session.run 未呼出."""
        session = self._make_mock_session()
        warmup_onnx_session(session)
        session.run.assert_not_called()

    @patch.dict("os.environ", {"PIPER_DISABLE_WARMUP": "yes"})
    def test_disable_warmup_env_yes(self):
        """PIPER_DISABLE_WARMUP=yes → session.run 未呼出."""
        session = self._make_mock_session()
        warmup_onnx_session(session)
        session.run.assert_not_called()

    def test_runs_zero_returns_immediately(self):
        """runs=0 → session.run 未呼出."""
        session = self._make_mock_session()
        warmup_onnx_session(session, runs=0)
        session.run.assert_not_called()

    def test_optional_inputs_sid_only(self):
        """sid ありモデル → 入力に sid が含まれる."""
        session = self._make_mock_session(has_sid=True)
        warmup_onnx_session(session, runs=1)
        call_args = session.run.call_args
        inputs_dict = call_args[0][1]  # 第2引数が入力 dict
        assert "sid" in inputs_dict
        assert "lid" not in inputs_dict
        assert "prosody_features" not in inputs_dict

    def test_optional_inputs_all(self):
        """sid + lid + prosody ありモデル → 全オプション入力が含まれる."""
        session = self._make_mock_session(
            has_sid=True, has_lid=True, has_prosody=True
        )
        warmup_onnx_session(session, runs=1)
        call_args = session.run.call_args
        inputs_dict = call_args[0][1]
        assert "sid" in inputs_dict
        assert "lid" in inputs_dict
        assert "prosody_features" in inputs_dict

    def test_optional_inputs_none(self):
        """オプション入力なしモデル → 必須入力のみ."""
        session = self._make_mock_session()
        warmup_onnx_session(session, runs=1)
        call_args = session.run.call_args
        inputs_dict = call_args[0][1]
        assert "input" in inputs_dict
        assert "input_lengths" in inputs_dict
        assert "scales" in inputs_dict
        assert "sid" not in inputs_dict
        assert "lid" not in inputs_dict
        assert "prosody_features" not in inputs_dict

    def test_dummy_input_shape_and_values(self):
        """ダミー入力の形状と BOS/EOS/dummy 値が正しい."""
        session = self._make_mock_session()
        warmup_onnx_session(session, runs=1, phoneme_length=100)
        call_args = session.run.call_args
        inputs_dict = call_args[0][1]
        phoneme_ids = inputs_dict["input"]
        assert phoneme_ids.shape == (1, 100)
        assert phoneme_ids[0, 0] == 1    # BOS
        assert phoneme_ids[0, -1] == 2   # EOS
        assert phoneme_ids[0, 1] == 8    # dummy phoneme
        assert phoneme_ids[0, 50] == 8   # middle = dummy
        scales = inputs_dict["scales"]
        np.testing.assert_array_almost_equal(scales, [0.667, 1.0, 0.8])

    def test_prosody_features_shape(self):
        """prosody_features の形状が (1, phoneme_length, 3) である."""
        session = self._make_mock_session(has_prosody=True)
        warmup_onnx_session(session, runs=1, phoneme_length=100)
        call_args = session.run.call_args
        inputs_dict = call_args[0][1]
        prosody = inputs_dict["prosody_features"]
        assert prosody.shape == (1, 100, 3)
        assert prosody.dtype == np.int64
```

### M1.4: 完了基準

- [ ] `uv run pytest src/python/tests/test_ort_utils.py -v` 全 PASS (既存テスト + 新規 TestWarmup)
- [ ] `uv run ruff check src/python/piper_train/ort_utils.py` PASS
- [ ] `uv run ruff format --check src/python/piper_train/ort_utils.py` PASS
- [ ] 全変更ファイルに対して `ruff check` / `ruff format --check` PASS

---

## 3. エージェントチームの構成

本タスクは小規模 (コア関数 1 つ + 統合 5 箇所 + テスト 1 ファイル) のため、2 エージェント体制で実施する。

### Agent A: 実装担当 (implementer)

**担当範囲**:
- M1.1: `ort_utils.py` に `warmup_onnx_session()` を実装
- M1.2: 5 箇所の推論エントリポイントへの統合
- M1.4: ruff check / ruff format の確認

**作業順序**:
1. `ort_utils.py` にコア関数を実装
2. `infer_onnx.py` に統合 (最もシンプル、動作確認の基準)
3. `infer_onnx_streaming.py` に統合
4. `docker/python-inference/inference.py` に統合
5. `docker/webui/app.py` に統合
6. `voice.py` にインライン実装 (import 不可のため最後)
7. ruff check / format 確認

### Agent B: テスト担当 (test-writer)

**担当範囲**:
- M1.3: `test_ort_utils.py` に `TestWarmup` クラスを追加
- Agent A の実装完了後にテスト実行・結果確認

**作業順序**:
1. Agent A が M1.1 を完了した時点でテスト作成を開始
2. モック session のヘルパーメソッドを実装
3. 正常系・異常系・環境変数・オプション入力の各テストケースを実装
4. `uv run pytest src/python/tests/test_ort_utils.py -v` で全テスト PASS を確認

### レビュー

Agent A と Agent B の実装完了後、以下を確認:
- Rust/C# との定数一致 (BOS=1, EOS=2, dummy=8, length=100, scales=[0.667, 1.0, 0.8])
- 例外処理の一貫性 (全箇所で非致命的)
- `voice.py` のインライン実装が `ort_utils.py` のロジックと同一であること

---

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**スコープ内**:

| 項目 | 詳細 |
|------|------|
| コア関数 | `ort_utils.warmup_onnx_session()` |
| 定数 | `WARMUP_PHONEME_LENGTH`, `DEFAULT_WARMUP_RUNS` |
| 統合 (5箇所) | `infer_onnx.py`, `infer_onnx_streaming.py`, `voice.py`, `inference.py`, `app.py` |
| テスト | `test_ort_utils.py::TestWarmup` (10件以上) |
| 環境変数 | `PIPER_DISABLE_WARMUP` |

**スコープ外**:

| 項目 | 理由 |
|------|------|
| C++ warmup | M2 で実装 |
| モデルキャッシュ (.opt.onnx) | M3 で実装 |
| 日本語音素化キャッシュ | M4 で実装 |
| benchmarking / パフォーマンス計測 | 手動確認のみ (CI ではレイテンシが不安定) |
| `voice.py` での `piper_train.ort_utils` import | `python_run` は独立パッケージのため import 不可。インライン実装で対応 |
| ストリーミングモデルの decoder warmup | decoder は encoder 出力を入力とするため独立 warmup 不可能 |

### 4.2 ユニットテスト

**ファイル**: `src/python/tests/test_ort_utils.py`

| # | テスト名 | 入力 | 期待結果 |
|---|---------|------|---------|
| 1 | `test_warmup_completes_successfully` | モック session, runs=2 | `session.run` が 2 回呼ばれる |
| 2 | `test_warmup_failure_is_non_fatal` | `session.run` が `RuntimeError` | warning ログ出力、例外なし |
| 3 | `test_disable_warmup_env_1` | `PIPER_DISABLE_WARMUP=1` | `session.run` 未呼出 |
| 4 | `test_disable_warmup_env_true` | `PIPER_DISABLE_WARMUP=true` | `session.run` 未呼出 |
| 5 | `test_disable_warmup_env_yes` | `PIPER_DISABLE_WARMUP=yes` | `session.run` 未呼出 |
| 6 | `test_runs_zero_returns_immediately` | runs=0 | `session.run` 未呼出 |
| 7 | `test_optional_inputs_sid_only` | モデルに sid 入力あり | 入力 dict に `"sid"` が含まれる |
| 8 | `test_optional_inputs_all` | sid + lid + prosody あり | 全オプション入力が含まれる |
| 9 | `test_optional_inputs_none` | オプション入力なし | 必須入力 (input, input_lengths, scales) のみ |
| 10 | `test_dummy_input_shape_and_values` | phoneme_length=100 | shape=(1,100), BOS=1, EOS=2, dummy=8, scales=[0.667,1.0,0.8] |
| 11 | `test_prosody_features_shape` | prosody あり, phoneme_length=100 | shape=(1,100,3), dtype=int64 |

### 4.3 E2E テスト

E2E テストは手動実行で確認する (CI で ONNX モデルをロードするのは重量級のため)。

| # | シナリオ | 確認方法 | 期待結果 |
|---|---------|---------|---------|
| 1 | CLI 推論 (`infer_onnx.py --text`) | `CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx --model <model> --text "テスト"` でログ確認 | `Warmup completed (2 runs in XXXms)` がログに出力される |
| 2 | CLI 推論 warmup 無効化 | `PIPER_DISABLE_WARMUP=1` を付けて同上 | `Warmup disabled` がログに出力される |
| 3 | Docker 推論サーバー | `docker run` で起動後、初回リクエストの RTF を確認 | warmup なしの場合と比較して初回 RTF が安定 |
| 4 | WebUI | WebUI 起動後、最初の合成リクエストの応答時間を確認 | warmup 済みのため初回も低レイテンシ |
| 5 | ストリーミング推論 | `infer_onnx_streaming.py` で JSONL 入力 | `Warmup completed` ログ出力後に通常のストリーミング動作 |

---

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| # | 懸念 | 影響度 | 対策 |
|---|------|--------|------|
| 1 | **warmup 失敗でアプリ停止** | 高 | 全例外を `try/except Exception` でキャッチ。warmup は完全にオプショナルな最適化であり、失敗しても推論は正常に動作する |
| 2 | **GPU OOM** | 中 | ダミー入力は本番入力と同程度の形状 (100 phonemes) を使用。本番推論が動作するメモリ環境であれば warmup も動作する |
| 3 | **WebUI で毎リクエスト warmup** | 低 | `_get_session()` のキャッシュロック内で session 作成時に 1 回だけ実行。キャッシュヒット時は warmup をスキップ |
| 4 | **組込み環境での起動遅延追加** | 低 | `PIPER_DISABLE_WARMUP=1` 環境変数で完全無効化可能 |
| 5 | **voice.py のインライン実装の乖離** | 中 | `ort_utils.py` の実装と同一のロジック・定数・パラメータを使用。将来的にリファクタリングで統一を検討。コードコメントに「Keep in sync with ort_utils.warmup_onnx_session()」を記載 |
| 6 | **ストリーミングモデルの warmup 不完全** | 低 | encoder のみ warmup する。decoder は encoder 出力が必要なため独立 warmup 不可。encoder warmup で ORT の JIT キャッシュは十分温まり、decoder の初回遅延は小さい |
| 7 | **numpy import のオーバーヘッド** | 極低 | `ort_utils.py` は既に `onnxruntime` を import しており、`numpy` は `onnxruntime` の依存。追加 import コストは無視できる |

### 5.2 レビューチェックリスト

- [ ] **定数一致**: `WARMUP_PHONEME_LENGTH=100`, `DEFAULT_WARMUP_RUNS=2`, BOS=1, EOS=2, dummy=8, scales=[0.667, 1.0, 0.8] が Rust/C# と一致
- [ ] **例外処理**: 全呼び出し箇所で例外がアプリケーションをクラッシュさせないこと
- [ ] **ログレベル**: 成功時 `info`、失敗時 `warning`、無効化時 `info`
- [ ] **環境変数**: `PIPER_DISABLE_WARMUP` の値チェックが大文字小文字非依存 (`.lower()`)
- [ ] **voice.py 同期**: インライン実装が `ort_utils.py` と同一のロジック
- [ ] **import 整理**: 新規 import が ruff の import order ルールに準拠
- [ ] **テスト網羅性**: 正常系 / 異常系 / 環境変数 / runs=0 / オプション入力パターン全て
- [ ] **WebUI ロック**: warmup がキャッシュロック内で実行され、1 モデル 1 回のみ
- [ ] **streaming**: encoder のみ warmup、decoder は未対応の旨がコメントに記載
- [ ] **既存テスト非破壊**: `uv run pytest src/python/tests/ --override-ini="addopts="` で既存テスト全 PASS

---

## 6. 一から作り直すとしたら

### 検討した代替案

#### 案 A: 各エントリポイントに個別インライン実装 (採用しない)

各推論スクリプトにそれぞれ warmup ロジックを直接書く方式。

**不採用理由**: 5 箇所で同一ロジックの重複が発生し、定数変更時に全箇所の同期が必要。Rust/C# との一貫性も維持しにくい。

#### 案 B: warmup を session ラッパークラスに内包 (将来検討)

`ort_utils.py` に `PiperSession` ラッパークラスを作り、session 作成 + warmup + キャッシュを一元管理する方式。

```python
class PiperSession:
    def __init__(self, model_path, device="cpu"):
        self.session = create_session_with_cache(model_path, device=device)
        warmup_onnx_session(self.session)
```

**不採用理由**: M1 のスコープを超える。M3 (モデルキャッシュ) との統合時に検討する価値はあるが、現時点では過剰設計。既存コードへの変更が最小限の関数ベースアプローチを優先。

#### 案 C: warmup を別スレッドで非同期実行 (採用しない)

session 作成後に別スレッドで warmup を実行し、初回リクエストまでに完了を目指す方式。

**不採用理由**: ONNX Runtime session はスレッドセーフだが、warmup 完了前に推論リクエストが来た場合の排他制御が複雑。warmup 自体は 1-2 秒で完了するため、同期実行で十分。

### 現在のアプローチを選択した理由

1. **最小変更**: 既存コードへの影響が最小。各エントリポイントに 1-2 行追加するだけ
2. **Rust/C# 整合性**: 同一のダミー入力パラメータ、同一の例外処理戦略
3. **テスト容易性**: モック session で完全にユニットテスト可能。実モデル不要
4. **段階的移行**: M3 (モデルキャッシュ) で `create_session_with_cache()` を導入する際に、warmup 呼び出しも統合できる

### もし最初からやり直すなら

`ort_utils.py` をセッション管理のファサードとして設計し、`create_session()` 一つで「SessionOptions 設定 + キャッシュ + warmup」を全て行う統一 API を提供する。`voice.py` の `python_run` パッケージも `piper_train.ort_utils` に依存できるようにパッケージ構成を見直す。ただし、既存の後方互換性と段階的な実装計画を考慮すると、現在の関数ベースのアプローチが最も現実的。

---

## 7. 後続タスクへの連絡事項

### M2 (C++ Warmup) への連絡

- Python の `warmup_onnx_session()` と同一の定数を使用すること: `WARMUP_PHONEME_LENGTH=100`, BOS=1, EOS=2, dummy=8, scales=[0.667, 1.0, 0.8], runs=2
- C++ では `--no-warmup` CLI フラグで無効化 (Python の `PIPER_DISABLE_WARMUP` 環境変数に相当)
- 例外処理: `spdlog::warn()` で非致命的に続行 (Python の `_LOGGER.warning()` に相当)

### M3 (Python モデルキャッシュ) への連絡

- `ort_utils.py` に `warmup_onnx_session()` が追加済み。`create_session_with_cache()` 実装時に、キャッシュからのセッション作成後にも warmup を呼び出すこと
- **統合ポイント**: `create_session_with_cache()` の末尾で `warmup_onnx_session(session)` を呼び出すのが理想的。これにより各エントリポイントでの個別 warmup 呼び出しを 1 箇所に統合できる
- `voice.py` のインライン warmup は M3 でも維持が必要 (`piper_train` を import 不可のため)
- `PIPER_DISABLE_WARMUP` 環境変数は warmup のみに影響し、モデルキャッシュには影響しない

### M4 (日本語音素化キャッシュ) への連絡

- M1 は ONNX Runtime レイヤーの最適化であり、音素化レイヤーとは独立。M4 の実装に影響なし
- warmup で使用するダミー phoneme ID (8) は実際の日本語音素とは無関係。音素化キャッシュのキーにはならない
