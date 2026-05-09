# Hardware Execution Provider 自動選択 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全5ネイティブランタイム（Python/Rust/C#/C++/Go）で `PIPER_EXECUTION_PROVIDER` 環境変数と自動検出ロジックを統一し、CoreML・DirectML・OpenVINO を含むハードウェア EP を品質変更なしで活用できるようにする。

**Architecture:** `PIPER_EXECUTION_PROVIDER` 環境変数が最優先。未設定時は CUDA→CoreML→DirectML→CPU の順に自動検出（TensorRT は auto-detect 対象外、明示指定のみ）。各ランタイムは ORT セッション初期化時に EP を選択し、EP 別キャッシュファイル（`model.{ep_label}.opt.onnx`）を使用する。

**Tech Stack:** Python 3.12 + onnxruntime ≥1.17, Rust/ort 2.0.0-rc.12, C#/.NET 10 + Microsoft.ML.OnnxRuntime, Go + onnxruntime_go, C++ + ORT 1.17 C-API

**Spec:** `docs/superpowers/specs/2026-05-04-hardware-ep-design.md`

---

## ファイル一覧

| 操作 | ファイル | 変更内容 |
|---|---|---|
| Modify | `docs/spec/ort-session-contract.toml` | EP 優先度・キャッシュラベル追記 |
| Modify | `src/python/piper_train/ort_utils.py` | `get_providers()` + `_get_device_label()` 拡張 |
| Modify | `src/python/tests/test_ort_utils.py` | EP テスト追加 |
| Modify | `src/python_run/piper/voice.py` | `device: str` パラメータ追加、インライン EP 拡張 |
| Modify | `src/rust/piper-core/src/gpu.rs` | `resolve_device_string()` 追加（env var 対応） |
| Modify | `src/rust/piper-core/src/engine.rs` | `resolve_device_string()` に切り替え |
| Modify | `src/go/piperplus/device.go` | `PIPER_EXECUTION_PROVIDER` env var 対応 |
| Modify | `src/go/piperplus/device_test.go` | env var テスト追加 |
| Modify | `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs` | CoreML + auto-detect + env var 追加 |
| Modify | `src/cpp/piper.cpp` | "auto" モード追加 |
| Modify | `src/cpp/main.cpp` | `PIPER_EXECUTION_PROVIDER` env var 追加 |

---

## Task 1: ort-session-contract.toml — EP 仕様追記

**Files:**
- Modify: `docs/spec/ort-session-contract.toml`

- [ ] **Step 1: TOML に追記**

`docs/spec/ort-session-contract.toml` のファイル末尾に以下を追記する（既存の `[cache]` セクションには手を加えない）：

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

- [ ] **Step 2: Commit**

```bash
git add docs/spec/ort-session-contract.toml
git commit -m "docs(contract): EP 選択仕様と追加 device_label を ort-session-contract.toml に追記 (#382)"
```

---

## Task 2: Python — ort_utils.py の EP 拡張

**Files:**
- Modify: `src/python/piper_train/ort_utils.py`
- Modify: `src/python/tests/test_ort_utils.py`

- [ ] **Step 1: テストを追記（失敗することを確認するため）**

`src/python/tests/test_ort_utils.py` の末尾に以下のクラスを追加する：

```python
@pytest.mark.unit
class TestGetProviders:
    """get_providers() の実行プロバイダー選択テスト."""

    def test_cpu_returns_cpu_ep(self):
        result = get_providers("cpu")
        assert result == ["CPUExecutionProvider"]

    def test_auto_with_no_gpu_returns_cpu(self):
        with patch("onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"]):
            result = get_providers("auto")
        assert result == ["CPUExecutionProvider"]

    def test_auto_detects_cuda(self):
        available = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("auto")
        assert result[0] == "CUDAExecutionProvider"
        assert "CPUExecutionProvider" in result

    def test_auto_detects_coreml_when_no_cuda(self):
        available = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("auto")
        assert result[0] == "CoreMLExecutionProvider"

    def test_auto_detects_directml_when_no_cuda_coreml(self):
        available = ["DmlExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("auto")
        assert result[0] == "DmlExecutionProvider"

    def test_explicit_cuda_returns_cuda_ep(self):
        available = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("cuda")
        assert any(
            ep == "CUDAExecutionProvider" or
            (isinstance(ep, tuple) and ep[0] == "CUDAExecutionProvider")
            for ep in result
        )

    def test_explicit_coreml_returns_coreml_ep(self):
        available = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("coreml")
        assert "CoreMLExecutionProvider" in result

    def test_explicit_directml_returns_dml_ep(self):
        available = ["DmlExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("directml")
        assert any(
            ep == "DmlExecutionProvider" or
            (isinstance(ep, tuple) and ep[0] == "DmlExecutionProvider")
            for ep in result
        )

    def test_unavailable_ep_falls_back_to_cpu(self):
        with patch("onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"]):
            result = get_providers("cuda")
        assert result == ["CPUExecutionProvider"]

    def test_env_var_overrides_device_param(self, monkeypatch):
        monkeypatch.setenv("PIPER_EXECUTION_PROVIDER", "cpu")
        available = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("auto")
        assert result == ["CPUExecutionProvider"]

    def test_env_var_selects_coreml(self, monkeypatch):
        monkeypatch.setenv("PIPER_EXECUTION_PROVIDER", "coreml")
        available = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("auto")
        assert "CoreMLExecutionProvider" in result

    def test_tensorrt_excluded_from_auto(self):
        available = ["TensorrtExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = get_providers("auto")
        assert result == ["CPUExecutionProvider"]

    def test_unknown_device_falls_back_to_cpu(self):
        result = get_providers("vulkan")
        assert result == ["CPUExecutionProvider"]


@pytest.mark.unit
class TestGetDeviceLabel:
    """_get_device_label() のキャッシュラベルテスト."""

    def test_cpu_returns_cpu(self):
        result = _get_device_label("cpu")
        assert result == "cpu"

    def test_auto_no_gpu_returns_cpu(self):
        with patch("onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"]):
            result = _get_device_label("auto")
        assert result == "cpu"

    def test_auto_with_cuda_returns_cuda0(self):
        available = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        with patch("onnxruntime.get_available_providers", return_value=available):
            result = _get_device_label("auto")
        assert result == "cuda0"

    def test_explicit_cuda_returns_cuda0(self):
        result = _get_device_label("cuda")
        assert result == "cuda0"

    def test_explicit_cuda1_returns_cuda1(self):
        result = _get_device_label("cuda:1")
        assert result == "cuda1"

    def test_explicit_coreml_returns_coreml(self):
        result = _get_device_label("coreml")
        assert result == "coreml"

    def test_explicit_directml_returns_directml0(self):
        result = _get_device_label("directml")
        assert result == "directml0"

    def test_explicit_directml1_returns_directml1(self):
        result = _get_device_label("directml:1")
        assert result == "directml1"

    def test_explicit_openvino_returns_openvino(self):
        result = _get_device_label("openvino")
        assert result == "openvino"

    def test_explicit_tensorrt_returns_tensorrt0(self):
        result = _get_device_label("tensorrt")
        assert result == "tensorrt0"

    def test_env_var_overrides_device_label(self, monkeypatch):
        monkeypatch.setenv("PIPER_EXECUTION_PROVIDER", "coreml")
        result = _get_device_label("auto")
        assert result == "coreml"
```

- [ ] **Step 2: テストを実行して失敗することを確認**

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus
uv run pytest src/python/tests/test_ort_utils.py::TestGetProviders src/python/tests/test_ort_utils.py::TestGetDeviceLabel -v 2>&1 | tail -20
```

Expected: 複数テストが `AssertionError` や `TypeError` で失敗する。

- [ ] **Step 3: `ort_utils.py` の `get_providers()` と `_get_device_label()` を実装**

`src/python/piper_train/ort_utils.py` の `get_providers()` 関数（104行目付近）を以下で置き換える：

```python
# TensorRT は auto-detect 対象外（明示指定のみ）
_EP_AUTO_PRIORITY = [
    "CUDAExecutionProvider",
    "CoreMLExecutionProvider",
    "DmlExecutionProvider",
    "OpenVINOExecutionProvider",
]

_EP_KEY_TO_ORT_NAME: dict[str, str] = {
    "cuda": "CUDAExecutionProvider",
    "coreml": "CoreMLExecutionProvider",
    "directml": "DmlExecutionProvider",
    "openvino": "OpenVINOExecutionProvider",
    "tensorrt": "TensorrtExecutionProvider",
}


def get_providers(device: str = "auto") -> list[str | tuple[str, dict]]:
    """Return ONNX Runtime execution providers for the given device.

    Args:
        device: "auto" | "cpu" | "cuda" | "cuda:N" | "coreml" |
                "directml" | "directml:N" | "openvino" | "tensorrt" | "tensorrt:N"

    PIPER_EXECUTION_PROVIDER env var overrides ``device`` when set.
    """
    env = os.environ.get("PIPER_EXECUTION_PROVIDER", "").lower().strip()
    target = env if env else device.lower().strip()

    if target in ("cpu", ""):
        return ["CPUExecutionProvider"]

    available = onnxruntime.get_available_providers()

    if target == "auto":
        for ep in _EP_AUTO_PRIORITY:
            if ep in available:
                _LOGGER.info("Auto-selected execution provider: %s", ep)
                return [ep, "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    parts = target.split(":", 1)
    provider_key = parts[0]
    device_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

    ep_name = _EP_KEY_TO_ORT_NAME.get(provider_key)
    if ep_name is None:
        _LOG.warning("Unknown provider %r, falling back to CPU", provider_key)
        return ["CPUExecutionProvider"]

    if ep_name not in available:
        _LOG.warning("EP %s not available, falling back to CPU", ep_name)
        return ["CPUExecutionProvider"]

    if provider_key == "cuda":
        return [
            (ep_name, {"device_id": str(device_id), "cudnn_conv_algo_search": "HEURISTIC"}),
            "CPUExecutionProvider",
        ]
    if provider_key in ("directml", "tensorrt"):
        return [(ep_name, {"device_id": str(device_id)}), "CPUExecutionProvider"]
    return [ep_name, "CPUExecutionProvider"]
```

また、`_get_device_label()` 関数（124行目付近）を以下で置き換える：

```python
_EP_KEY_TO_LABEL_FORMAT: dict[str, str] = {
    "cuda": "cuda{id}",
    "coreml": "coreml",
    "directml": "directml{id}",
    "openvino": "openvino",
    "tensorrt": "tensorrt{id}",
}

_EP_ORT_TO_LABEL: dict[str, str] = {
    "CUDAExecutionProvider": "cuda0",
    "CoreMLExecutionProvider": "coreml",
    "DmlExecutionProvider": "directml0",
    "OpenVINOExecutionProvider": "openvino",
}


def _get_device_label(device: str) -> str:
    """Return effective device label for cache path (e.g., 'cpu', 'cuda0', 'coreml')."""
    env = os.environ.get("PIPER_EXECUTION_PROVIDER", "").lower().strip()
    target = env if env else device.lower().strip()

    if target in ("cpu", ""):
        return "cpu"

    if target == "auto":
        available = onnxruntime.get_available_providers()
        for ep, label in _EP_ORT_TO_LABEL.items():
            if ep in available:
                return label
        return "cpu"

    parts = target.split(":", 1)
    provider_key = parts[0]
    device_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

    fmt = _EP_KEY_TO_LABEL_FORMAT.get(provider_key)
    if fmt is None:
        return "cpu"
    return fmt.format(id=device_id)
```

※ `_LOG` は既存の `logging.getLogger(__name__)` を使用。ファイル内の既存ロガー変数名を確認して合わせること。

- [ ] **Step 4: テストを実行して全件 PASS を確認**

```bash
uv run pytest src/python/tests/test_ort_utils.py::TestGetProviders src/python/tests/test_ort_utils.py::TestGetDeviceLabel -v 2>&1 | tail -30
```

Expected: 全テストが PASSED。

- [ ] **Step 5: 既存テストが壊れていないことを確認**

```bash
uv run pytest src/python/tests/test_ort_utils.py -v 2>&1 | tail -20
```

Expected: 既存の `TestCreateSessionOptions` / `TestGetProviders` / `TestGetDeviceLabel` が全て PASSED。

- [ ] **Step 6: Commit**

```bash
git add src/python/piper_train/ort_utils.py src/python/tests/test_ort_utils.py
git commit -m "feat(python): ort_utils.py の get_providers()/device_label を全 EP 対応に拡張 (#382)"
```

---

## Task 3: Python — voice.py のインライン EP 拡張

**Files:**
- Modify: `src/python_run/piper/voice.py`

- [ ] **Step 1: `_load_session_inline()` を `device: str` 対応に変更**

`src/python_run/piper/voice.py` の `_load_session_inline()` 関数を以下で置き換える（`use_cuda: bool` パラメータを残しつつ `device: str` を追加）：

```python
# TensorRT は auto-detect 対象外
_INLINE_EP_AUTO_PRIORITY = [
    "CUDAExecutionProvider",
    "CoreMLExecutionProvider",
    "DmlExecutionProvider",
    "OpenVINOExecutionProvider",
]

_INLINE_EP_KEY_MAP: dict[str, str] = {
    "cuda": "CUDAExecutionProvider",
    "coreml": "CoreMLExecutionProvider",
    "directml": "DmlExecutionProvider",
    "openvino": "OpenVINOExecutionProvider",
    "tensorrt": "TensorrtExecutionProvider",
}


def _inline_get_providers(device: str) -> list[str | tuple[str, dict[str, Any]]]:
    """Inline variant of ort_utils.get_providers() for standalone voice.py."""
    import onnxruntime as _ort

    env = os.environ.get("PIPER_EXECUTION_PROVIDER", "").lower().strip()
    target = env if env else device.lower().strip()

    if target in ("cpu", ""):
        return ["CPUExecutionProvider"]

    available = _ort.get_available_providers()

    if target == "auto":
        for ep in _INLINE_EP_AUTO_PRIORITY:
            if ep in available:
                return [ep, "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    parts = target.split(":", 1)
    key = parts[0]
    dev_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

    ep_name = _INLINE_EP_KEY_MAP.get(key)
    if ep_name is None or ep_name not in available:
        return ["CPUExecutionProvider"]

    if key == "cuda":
        return [(ep_name, {"device_id": str(dev_id), "cudnn_conv_algo_search": "HEURISTIC"}),
                "CPUExecutionProvider"]
    if key in ("directml", "tensorrt"):
        return [(ep_name, {"device_id": str(dev_id)}), "CPUExecutionProvider"]
    return [ep_name, "CPUExecutionProvider"]


def _inline_get_device_label(device: str) -> str:
    """Inline variant of ort_utils._get_device_label() for standalone voice.py."""
    import onnxruntime as _ort

    env = os.environ.get("PIPER_EXECUTION_PROVIDER", "").lower().strip()
    target = env if env else device.lower().strip()

    if target in ("cpu", ""):
        return "cpu"

    if target == "auto":
        available = _ort.get_available_providers()
        label_map = {
            "CUDAExecutionProvider": "cuda0",
            "CoreMLExecutionProvider": "coreml",
            "DmlExecutionProvider": "directml0",
            "OpenVINOExecutionProvider": "openvino",
        }
        for ep, label in label_map.items():
            if ep in available:
                return label
        return "cpu"

    parts = target.split(":", 1)
    key = parts[0]
    dev_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

    fmt_map = {
        "cuda": f"cuda{dev_id}",
        "coreml": "coreml",
        "directml": f"directml{dev_id}",
        "openvino": "openvino",
        "tensorrt": f"tensorrt{dev_id}",
    }
    return fmt_map.get(key, "cpu")
```

- [ ] **Step 2: `_load_session_inline()` 本体を修正**

`_load_session_inline()` の引数と内部実装を以下に変更する（`use_cuda: bool` は backward compat のため残す）：

```python
def _load_session_inline(
    model_path: str | Path,
    *,
    use_cuda: bool = False,  # deprecated: use device="cuda" instead
    device: str = "auto",
) -> onnxruntime.InferenceSession:
    """Create an InferenceSession using inline logic (no piper_train dependency).

    Keep in sync with piper_train.ort_utils.create_session_with_cache().
    """
    # Backward compat: use_cuda=True + device="auto" → device="cuda"
    if use_cuda and device == "auto":
        device = "cuda"

    providers = _inline_get_providers(device)
```

さらに、関数内の `device_label = "cuda0" if use_cuda else "cpu"` を以下で置き換える：

```python
    device_label = _inline_get_device_label(device)
```

- [ ] **Step 3: `PiperVoice.load()` に `device: str` パラメータを追加**

`PiperVoice.load()` のシグネチャ（392行目付近）を以下に変更する：

```python
    @staticmethod
    def load(
        model_path: str | Path,
        config_path: str | Path | None = None,
        use_cuda: bool = False,   # deprecated: use device="cuda" instead
        device: str = "auto",
    ) -> "PiperVoice":
        """Load an ONNX model and config."""
        # Backward compat: use_cuda=True + device="auto" → device="cuda"
        if use_cuda and device == "auto":
            device = "cuda"
```

`if _HAS_SHARED_ORT_UTILS and not use_cuda:` の条件を以下に変更する：

```python
        if _HAS_SHARED_ORT_UTILS:
            session = _shared_create_session_with_cache(model_path, device=device)
            _shared_warmup(session)
        else:
            session = _load_session_inline(model_path, device=device)
            _warmup_session(session)
```

- [ ] **Step 4: 既存テストを実行して回帰がないことを確認**

```bash
uv run pytest src/python_run/tests/ -v 2>&1 | tail -20
```

Expected: 全テストが PASSED（既存の short_text_mitigation テスト等）。

- [ ] **Step 5: Commit**

```bash
git add src/python_run/piper/voice.py
git commit -m "feat(python-run): voice.py に device 文字列パラメータ追加、全 EP インライン対応 (#382)"
```

---

## Task 4: Rust — gpu.rs に env var 対応を追加

**Files:**
- Modify: `src/rust/piper-core/src/gpu.rs`
- Modify: `src/rust/piper-core/src/engine.rs`

- [ ] **Step 1: `gpu.rs` のテスト追加**

`src/rust/piper-core/src/gpu.rs` のテストモジュール（`#[cfg(test)]` ブロック）の末尾に追加する：

```rust
    #[test]
    fn test_resolve_device_string_env_var_cpu() {
        // SAFETY: テスト内で環境変数を設定/解除する。並列実行に注意。
        std::env::set_var("PIPER_EXECUTION_PROVIDER", "cpu");
        let result = resolve_device_string("auto").unwrap();
        std::env::remove_var("PIPER_EXECUTION_PROVIDER");
        assert_eq!(result, DeviceType::Cpu);
    }

    #[test]
    fn test_resolve_device_string_env_var_cuda() {
        std::env::set_var("PIPER_EXECUTION_PROVIDER", "cuda");
        let result = resolve_device_string("cpu").unwrap();
        std::env::remove_var("PIPER_EXECUTION_PROVIDER");
        assert_eq!(result, DeviceType::Cuda { device_id: 0 });
    }

    #[test]
    fn test_resolve_device_string_env_var_coreml() {
        std::env::set_var("PIPER_EXECUTION_PROVIDER", "coreml");
        let result = resolve_device_string("cpu").unwrap();
        std::env::remove_var("PIPER_EXECUTION_PROVIDER");
        assert_eq!(result, DeviceType::CoreML);
    }

    #[test]
    fn test_resolve_device_string_no_env_var_uses_param() {
        std::env::remove_var("PIPER_EXECUTION_PROVIDER");
        let result = resolve_device_string("cpu").unwrap();
        assert_eq!(result, DeviceType::Cpu);
    }

    #[test]
    fn test_resolve_device_string_empty_env_var_uses_param() {
        std::env::set_var("PIPER_EXECUTION_PROVIDER", "");
        let result = resolve_device_string("cpu").unwrap();
        std::env::remove_var("PIPER_EXECUTION_PROVIDER");
        assert_eq!(result, DeviceType::Cpu);
    }

    #[test]
    fn test_resolve_device_string_auto_without_env() {
        std::env::remove_var("PIPER_EXECUTION_PROVIDER");
        // auto → always returns a valid DeviceType (at minimum CPU)
        let result = resolve_device_string("auto").unwrap();
        match result {
            DeviceType::Cpu
            | DeviceType::Cuda { .. }
            | DeviceType::CoreML
            | DeviceType::DirectML { .. }
            | DeviceType::TensorRT { .. } => {}
        }
    }
```

- [ ] **Step 2: テストを実行して失敗することを確認**

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus/src/rust
cargo test -p piper-core resolve_device_string 2>&1 | tail -15
```

Expected: `error[E0425]: cannot find function 'resolve_device_string'`

- [ ] **Step 3: `resolve_device_string()` を `gpu.rs` に実装**

`gpu.rs` の `parse_device_string()` 関数の直後（`AUTO_DEVICE_CACHE` の前）に追加する：

```rust
/// Resolve a device string, applying `PIPER_EXECUTION_PROVIDER` env var override.
///
/// Priority: `PIPER_EXECUTION_PROVIDER` env var > `device` argument > auto-detect.
///
/// Use this instead of `parse_device_string` in inference engines.
pub fn resolve_device_string(device: &str) -> Result<DeviceType, PiperError> {
    let env_ep = std::env::var("PIPER_EXECUTION_PROVIDER")
        .ok()
        .filter(|s| !s.is_empty());

    let effective = env_ep.as_deref().unwrap_or(device);

    if effective.eq_ignore_ascii_case("auto") || effective.is_empty() {
        return Ok(auto_detect_device());
    }

    parse_device_string(effective)
}
```

- [ ] **Step 4: `engine.rs` で `parse_device_string` を `resolve_device_string` に切り替え**

`src/rust/piper-core/src/engine.rs` の以下の行を変更する：

変更前（398行目付近）：
```rust
        let device_type = crate::gpu::parse_device_string(device)
            .map_err(|e| PiperError::ModelLoad(format!("invalid device '{}': {}", device, e)))?;
```

変更後：
```rust
        let device_type = crate::gpu::resolve_device_string(device)
            .map_err(|e| PiperError::ModelLoad(format!("invalid device '{}': {}", device, e)))?;
```

- [ ] **Step 5: テストを実行して全件 PASS を確認**

```bash
cargo test -p piper-core 2>&1 | tail -20
```

Expected: 全テストが `ok`。

- [ ] **Step 6: Commit**

```bash
git add src/rust/piper-core/src/gpu.rs src/rust/piper-core/src/engine.rs
git commit -m "feat(rust): gpu.rs に resolve_device_string() を追加し PIPER_EXECUTION_PROVIDER env var に対応 (#382)"
```

---

## Task 5: Go — device.go に env var 対応を追加

**Files:**
- Modify: `src/go/piperplus/device.go`
- Modify: `src/go/piperplus/device_test.go`

- [ ] **Step 1: テストを追記**

`src/go/piperplus/device_test.go` の末尾に追加する：

```go
func TestConfigureSessionOptionsEnvVar(t *testing.T) {
    // PIPER_EXECUTION_PROVIDER=cpu の場合は CPU が選択されること
    t.Setenv("PIPER_EXECUTION_PROVIDER", "cpu")
    // configureSessionOptions は実際の ORT セッションを作るため、
    // ここでは env var が device パラメータに反映されることをログ経由で確認するのが
    // 実際的。代わりに selectDeviceWithEnv のユニットテストで検証する。
    result := selectDeviceWithEnv("auto")
    if result != "cpu" {
        t.Errorf("selectDeviceWithEnv(auto) with PIPER_EXECUTION_PROVIDER=cpu = %q, want %q", result, "cpu")
    }
}

func TestSelectDeviceWithEnv(t *testing.T) {
    tests := []struct {
        envVal string
        device string
        want   string
    }{
        {envVal: "cpu", device: "auto", want: "cpu"},
        {envVal: "cuda", device: "auto", want: "cuda"},
        {envVal: "coreml", device: "cpu", want: "coreml"},
        {envVal: "", device: "cpu", want: "cpu"},
        {envVal: "", device: "cuda", want: "cuda"},
        {envVal: "", device: "auto", want: "auto"},
    }
    for _, tt := range tests {
        t.Run(tt.envVal+"_"+tt.device, func(t *testing.T) {
            if tt.envVal != "" {
                t.Setenv("PIPER_EXECUTION_PROVIDER", tt.envVal)
            } else {
                t.Setenv("PIPER_EXECUTION_PROVIDER", "")
            }
            got := selectDeviceWithEnv(tt.device)
            if got != tt.want {
                t.Errorf("selectDeviceWithEnv(%q) with env=%q = %q, want %q",
                    tt.device, tt.envVal, got, tt.want)
            }
        })
    }
}
```

- [ ] **Step 2: テストを実行して失敗することを確認**

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus/src/go
go test ./piperplus/ -run "TestSelectDeviceWithEnv|TestConfigureSessionOptionsEnvVar" -v 2>&1 | tail -15
```

Expected: `undefined: selectDeviceWithEnv`

- [ ] **Step 3: `selectDeviceWithEnv()` を `device.go` に追加し `configureSessionOptions` を修正**

`src/go/piperplus/device.go` の `ParseDevice` 関数の直前に追加する：

```go
// selectDeviceWithEnv returns the effective device string after applying the
// PIPER_EXECUTION_PROVIDER environment variable override.
// env var takes precedence over the device parameter.
func selectDeviceWithEnv(device string) string {
    if ep := os.Getenv("PIPER_EXECUTION_PROVIDER"); ep != "" {
        return strings.ToLower(strings.TrimSpace(ep))
    }
    return device
}
```

`configureSessionOptions()` の先頭（`ParseDevice` 呼び出しの前）に1行追加する：

```go
func configureSessionOptions(device string, logger *slog.Logger) (*ort.SessionOptions, error) {
    device = selectDeviceWithEnv(device)   // ← この1行を先頭に追加
    if logger == nil {
        logger = slog.Default()
    }
    // ... 残りは既存のまま
```

また、ファイル先頭の import に `"os"` が含まれていなければ追加する（既存の import ブロックを確認）。

- [ ] **Step 4: テストを実行して全件 PASS を確認**

```bash
go test ./piperplus/ -v 2>&1 | tail -20
```

Expected: 全テストが `PASS`。

- [ ] **Step 5: Commit**

```bash
git add src/go/piperplus/device.go src/go/piperplus/device_test.go
git commit -m "feat(go): device.go に PIPER_EXECUTION_PROVIDER env var 対応を追加 (#382)"
```

---

## Task 6: C# — SessionFactory に CoreML + auto-detect + env var を追加

**Files:**
- Modify: `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs`

- [ ] **Step 1: テストを追加**

C# のテストプロジェクト（`src/csharp/PiperPlus.Core.Tests/`）内の SessionFactory 関連テストファイルを探す：

```bash
find /Users/inamotoyuuta/Desktop/piper-plus/src/csharp -name "*SessionFactory*" -o -name "*session*factory*" 2>/dev/null | grep -i test
```

見つかったテストファイルの末尾に以下を追加する。ファイルが見つからない場合は `src/csharp/PiperPlus.Core.Tests/SessionFactoryTests.cs` を新規作成する：

```csharp
[Fact]
public void ResolveDevice_EnvVarCpu_ReturnsCpu()
{
    Environment.SetEnvironmentVariable("PIPER_EXECUTION_PROVIDER", "cpu");
    try
    {
        var result = SessionFactory.ResolveDevice("auto");
        Assert.Equal("cpu", result);
    }
    finally
    {
        Environment.SetEnvironmentVariable("PIPER_EXECUTION_PROVIDER", null);
    }
}

[Fact]
public void ResolveDevice_EnvVarCoreML_ReturnsCoreML()
{
    Environment.SetEnvironmentVariable("PIPER_EXECUTION_PROVIDER", "coreml");
    try
    {
        var result = SessionFactory.ResolveDevice("auto");
        Assert.Equal("coreml", result);
    }
    finally
    {
        Environment.SetEnvironmentVariable("PIPER_EXECUTION_PROVIDER", null);
    }
}

[Fact]
public void ResolveDevice_NoEnvVar_ReturnsParam()
{
    Environment.SetEnvironmentVariable("PIPER_EXECUTION_PROVIDER", null);
    var result = SessionFactory.ResolveDevice("cpu");
    Assert.Equal("cpu", result);
}

[Fact]
public void GetDeviceLabel_CoreML_ReturnsCoreML()
{
    var label = SessionFactory.GetDeviceLabel("coreml");
    Assert.Equal("coreml", label);
}

[Fact]
public void GetDeviceLabel_DirectML_ReturnsDirectML0()
{
    var label = SessionFactory.GetDeviceLabel("directml");
    Assert.Equal("directml0", label);
}

[Fact]
public void GetDeviceLabel_Cpu_ReturnsCpu()
{
    var label = SessionFactory.GetDeviceLabel("cpu");
    Assert.Equal("cpu", label);
}
```

- [ ] **Step 2: テストを実行して失敗することを確認**

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus/src/csharp
dotnet test PiperPlus.Core.Tests/ --filter "ResolveDevice|GetDeviceLabel" 2>&1 | tail -15
```

Expected: `error CS0117: 'SessionFactory' does not contain a definition for 'ResolveDevice'`

- [ ] **Step 3: `SessionFactory.cs` に `ResolveDevice()` / `GetDeviceLabel()` を追加**

`src/csharp/PiperPlus.Core/Inference/SessionFactory.cs` に以下の public static メソッドを追加する（既存クラス内）：

```csharp
/// <summary>
/// Resolves the effective device string, applying PIPER_EXECUTION_PROVIDER env var.
/// </summary>
public static string ResolveDevice(string device = "auto")
{
    var ep = Environment.GetEnvironmentVariable("PIPER_EXECUTION_PROVIDER");
    if (!string.IsNullOrWhiteSpace(ep))
        return ep.Trim().ToLowerInvariant();
    return device.ToLowerInvariant();
}

/// <summary>
/// Returns the cache file device label for the given device string.
/// e.g. "cuda:1" → "cuda1", "coreml" → "coreml"
/// </summary>
public static string GetDeviceLabel(string device)
{
    var resolved = ResolveDevice(device);
    if (resolved is "cpu" or "")
        return "cpu";

    var parts = resolved.Split(':', 2);
    var key = parts[0];
    var id = parts.Length > 1 && int.TryParse(parts[1], out var n) ? n : 0;

    return key switch
    {
        "cuda" => $"cuda{id}",
        "coreml" => "coreml",
        "directml" => $"directml{id}",
        "openvino" => "openvino",
        "tensorrt" => $"tensorrt{id}",
        _ => "cpu",
    };
}
```

- [ ] **Step 4: auto-detect と CoreML の SessionOptions 設定を追加**

`SessionFactory.cs` の既存 `Create()` メソッド内（`deviceLabel` / `optimizedPath` 計算の前）に `ResolveDevice()` を組み込む。

現在の `var deviceLabel = useCuda ? $"cuda{resolvedDeviceId}" : "cpu";` を以下で置き換える：

```csharp
// device パラメータに変換（backward compat: useCuda=true → "cuda"）
var deviceStr = useCuda ? $"cuda:{resolvedDeviceId}" : "cpu";
var deviceLabel = GetDeviceLabel(deviceStr);
```

auto-detect と CoreML を AppendExecutionProvider するメソッドを追加する：

```csharp
private static void TryAppendCoreML(SessionOptions options, ILogger logger)
{
    try
    {
        // CoreML EP は macOS/iOS で自動有効。uint flags: 0 = default
        options.AppendExecutionProviderCoreML(0);
        logger.LogInformation("CoreML execution provider enabled");
    }
    catch (Exception ex)
    {
        logger.LogWarning("CoreML execution provider unavailable, falling back to CPU: {Message}", ex.Message);
    }
}

private static string AutoDetectAndConfigureEP(SessionOptions options, ILogger logger)
{
    var available = OrtEnv.Instance.GetAvailableProviders();

    if (Array.IndexOf(available, "CUDAExecutionProvider") >= 0)
    {
        TryAppendCuda(options, 0, logger);
        return "cuda0";
    }
    if (Array.IndexOf(available, "CoreMLExecutionProvider") >= 0)
    {
        TryAppendCoreML(options, logger);
        return "coreml";
    }
    if (Array.IndexOf(available, "DmlExecutionProvider") >= 0)
    {
        TryAppendDirectML(options, 0, logger);
        return "directml0";
    }
    return "cpu";
}
```

※ `TryAppendCudaProvider` は既存メソッド。DirectML は既存コードに同等メソッドがあればそれを流用し、なければ `TryAppendDirectMLProvider` として同パターンで追加する。

- [ ] **Step 5: テストを実行して全件 PASS を確認**

```bash
dotnet test PiperPlus.Core.Tests/ 2>&1 | tail -15
```

Expected: 全テストが Passed。

- [ ] **Step 6: Commit**

```bash
git add src/csharp/PiperPlus.Core/Inference/SessionFactory.cs src/csharp/PiperPlus.Core.Tests/
git commit -m "feat(csharp): SessionFactory に CoreML + auto-detect + PIPER_EXECUTION_PROVIDER 対応を追加 (#382)"
```

---

## Task 7: C++ — piper.cpp に "auto" モード、main.cpp に env var 追加

**Files:**
- Modify: `src/cpp/piper.cpp`
- Modify: `src/cpp/main.cpp`

- [ ] **Step 1: `piper.cpp` の `loadModel()` に "auto" モードを追加**

`src/cpp/piper.cpp` の `loadModel()` 関数（438行目付近）に `provider == "auto"` のケースを追加する。既存の `} else if (!provider.empty() && provider != "cpu") {` の手前に挿入する：

```cpp
} else if (provider == "auto" || provider.empty()) {
    // Auto-detect: CUDA → CoreML → DirectML → CPU
    // ORT 1.17 C-API: GetAvailableProviders
    const OrtApi* ort_api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    char** available_eps = nullptr;
    int num_eps = 0;
    OrtStatus* status = ort_api->GetAvailableProviders(&available_eps, &num_eps);
    if (status == nullptr && available_eps != nullptr) {
        auto has_ep = [&](const std::string& name) {
            for (int i = 0; i < num_eps; ++i) {
                if (std::string(available_eps[i]) == name) return true;
            }
            return false;
        };
        bool configured = false;
        if (has_ep("CUDAExecutionProvider")) {
            try {
                OrtCUDAProviderOptions cuda_opts{};
                cuda_opts.device_id = gpuDeviceId;
                session.options.AppendExecutionProvider_CUDA(cuda_opts);
                spdlog::info("Auto-detected: using CUDA execution provider (device={})", gpuDeviceId);
                configured = true;
            } catch (const std::exception& e) {
                spdlog::warn("CUDA EP failed: {}, trying next", e.what());
            }
        }
#ifdef __APPLE__
        if (!configured && has_ep("CoreMLExecutionProvider")) {
            try {
                Ort::ThrowOnError(OrtSessionOptionsAppendExecutionProvider_CoreML(session.options, 0));
                spdlog::info("Auto-detected: using CoreML execution provider");
                configured = true;
            } catch (const std::exception& e) {
                spdlog::warn("CoreML EP failed: {}, trying next", e.what());
            }
        }
#endif
#if __has_include(<dml_provider_factory.h>)
        if (!configured && has_ep("DmlExecutionProvider")) {
            try {
                Ort::ThrowOnError(OrtSessionOptionsAppendExecutionProvider_DML(session.options, gpuDeviceId));
                spdlog::info("Auto-detected: using DirectML execution provider (device={})", gpuDeviceId);
                configured = true;
            } catch (const std::exception& e) {
                spdlog::warn("DirectML EP failed: {}, trying next", e.what());
            }
        }
#endif
        ort_api->ReleaseAvailableProviders(available_eps, num_eps);
        if (!configured) {
            spdlog::info("Auto-detect: no hardware EP available, using CPU");
        }
    }
```

- [ ] **Step 2: `main.cpp` に `PIPER_EXECUTION_PROVIDER` env var 読み取りを追加**

`src/cpp/main.cpp` の `PIPER_GPU_DEVICE_ID` を読む箇所（792行目付近）の**前**に追加する：

```cpp
  // PIPER_EXECUTION_PROVIDER は --provider CLI フラグより優先
  const char* epEnv = std::getenv("PIPER_EXECUTION_PROVIDER");
  if (epEnv != nullptr && strlen(epEnv) > 0) {
    provider = std::string(epEnv);
    spdlog::info("Execution provider set from PIPER_EXECUTION_PROVIDER: {}", provider);
  }
```

また、help テキスト（776行目付近）に1行追加する：

```cpp
  cerr << "   PIPER_EXECUTION_PROVIDER         Execution provider: auto|cpu|cuda|coreml|directml|tensorrt" << endl;
```

- [ ] **Step 3: ビルドして警告・エラーがないことを確認**

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus
cmake -B build/cpp -S src/cpp -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -5
cmake --build build/cpp --parallel 4 2>&1 | tail -15
```

Expected: `[100%] Built target piper` (または同等のメッセージ)、エラーなし。

- [ ] **Step 4: smoke test — "auto" モードで CPU フォールバックが動作することを確認**

```bash
build/cpp/piper --model test/models/multilingual-test-medium.onnx \
  --provider auto --output-raw - <<< "test" > /dev/null && echo "PASS"
```

Expected: `PASS`（音声ストリームが /dev/null に流れる）。

- [ ] **Step 5: Commit**

```bash
git add src/cpp/piper.cpp src/cpp/main.cpp
git commit -m "feat(cpp): piper.cpp に auto EP 自動検出、main.cpp に PIPER_EXECUTION_PROVIDER env var を追加 (#382)"
```

---

## Task 8: Python パッケージ — setup.py extras_require に EP グループを追加

**Files:**
- Modify: `src/python_run/setup.py`

- [ ] **Step 1: extras_require に DirectML / OpenVINO を追加**

`src/python_run/setup.py` の `extras_require` 辞書（`"gpu"` キーがある箇所）を以下で置き換える：

```python
    extras_require={
        "gpu": ["onnxruntime-gpu>=1.11.0,<2"],
        "directml": ["onnxruntime-directml"],
        "openvino": ["onnxruntime-openvino"],
        "http": [
            "fastapi>=0.110,<1",
            "uvicorn[standard]>=0.27,<1",
        ],
    },
```

※ CoreML は macOS 版 `onnxruntime` に含まれるため追加不要。

- [ ] **Step 2: Commit**

```bash
git add src/python_run/setup.py
git commit -m "feat(python-run): setup.py に directml / openvino extras_require グループを追加 (#382)"
```

---

## Task 9: ドキュメント更新

**Files:**
- Modify: `docs/spec/ort-versions.md`

- [ ] **Step 1: ort-versions.md に EP 対応状況を追記**

`docs/spec/ort-versions.md` の末尾に追加する：

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

- [ ] **Step 2: Commit**

```bash
git add docs/spec/ort-versions.md
git commit -m "docs: ort-versions.md に EP 対応状況マトリクスを追加 (#382)"
```

---

## Task 10: 全体回帰テスト

- [ ] **Step 1: Python 全テストを実行**

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus
uv run pytest src/python/tests/ src/python_run/tests/ -v --tb=short 2>&1 | tail -30
```

Expected: 全テストが PASSED、新規テストを含む。

- [ ] **Step 2: Rust 全テストを実行**

```bash
cd src/rust
cargo test --workspace 2>&1 | tail -20
```

Expected: `test result: ok. X passed; 0 failed`

- [ ] **Step 3: Go 全テストを実行**

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus/src/go
go test ./... 2>&1 | tail -10
```

Expected: `ok  github.com/ayutaz/piper-plus/src/go/...`

- [ ] **Step 4: C# 全テストを実行**

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus/src/csharp
dotnet test --logger "console;verbosity=minimal" 2>&1 | tail -10
```

Expected: 全テストが Passed。

- [ ] **Step 5: 最終コミット — PR 準備**

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus
git log --oneline feat/hardware-ep ^dev
```

全タスクのコミットが一覧されることを確認する。
