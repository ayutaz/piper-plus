# T-03: Python voice.py のインライン EP 拡張

**Milestone:** feat: Hardware EP 自動選択 (#382) — Milestone #16
**依存タスク:** T-02（`ort_utils.py` の EP 拡張）
**後続タスク:** T-04 以降（Rust/Go/C#/C++ ランタイムへの EP 対応）

---

## 1. タスク目的とゴール

### 目的

`src/python_run/piper/voice.py` は `piper_train` パッケージに依存しないスタンドアロン動作を保証するため、`ort_utils.py` の EP ロジックをインライン複製して保持している。このインライン実装（`_load_session_inline()` と `device_label` 計算）を T-02 で拡張した `ort_utils.py` と同水準の全 EP 対応に引き上げる。また、公開 API である `PiperVoice.load()` に `device: str = "auto"` パラメータを追加し、既存の `use_cuda: bool` との後方互換を維持する。

### なぜ必要か

- `voice.py` は PyPI パッケージ `piper-plus` の中核モジュールであり、エンドユーザーが直接呼び出す。`use_cuda: bool` の True/False 二択では CoreML / DirectML / OpenVINO を利用するユーザーが環境変数（`PIPER_EXECUTION_PROVIDER`）しか手段を持たない。
- `_load_session_inline()` の `device_label = "cuda0" if use_cuda else "cpu"` は硬直した2択であり、CoreML EP で生成されたモデルが `model.cpu.opt.onnx` という名前で保存されてしまう（EP をまたぐキャッシュ再利用不可の問題）。
- `_HAS_SHARED_ORT_UTILS` が True でも CUDA 以外の EP を使う場合、T-02 完了後の `_shared_create_session_with_cache(model_path, device=device)` を正しく呼び出せるよう `device` 引数を渡す必要がある。

### 完了の定義（Done 基準）

- `PiperVoice.load(model_path, device="coreml")` で CoreML EP によるセッションが生成される（macOS のみ）。
- `PiperVoice.load(model_path, use_cuda=True)` が従来と同じ動作（`device="cuda"` として扱われる）。
- `PiperVoice.load(model_path)` がデフォルトで `device="auto"` として動作し、利用可能な最良 EP を選択する。
- `PIPER_EXECUTION_PROVIDER` 環境変数が `device` 引数を上書きする。
- `_inline_get_providers()` と `_inline_get_device_label()` が `ort_utils.py` の関数と同じ出力を返す（実装計画の定義に従う）。
- `_load_session_inline()` が `device: str` パラメータを受け付け、`use_cuda: bool` は後方互換のために残存する。
- 既存テスト（`src/python_run/tests/`）が全件 PASS のまま。

---

## 2. 実装する内容の詳細

### 2.1 インライン EP ヘルパー関数の追加

**変更箇所:** `src/python_run/piper/voice.py`、`_load_session_inline()` の上（おおよそ 115 行目付近）に以下のコードを追加する。

```python
# TensorRT は auto-detect 対象外（明示指定のみ）。
# ort_utils.py の _EP_AUTO_PRIORITY / _EP_KEY_TO_ORT_NAME と同期を保つこと。
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
    """Inline variant of ort_utils.get_providers() for standalone voice.py.

    Keep in sync with piper_train.ort_utils.get_providers().
    """
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
    """Inline variant of ort_utils._get_device_label() for standalone voice.py.

    Keep in sync with piper_train.ort_utils._get_device_label().
    """
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

### 2.2 `_load_session_inline()` の修正

**変更箇所:** `src/python_run/piper/voice.py` の `_load_session_inline()` 関数（115行目〜227行目）

現行の `use_cuda: bool = False` のみのシグネチャに `device: str = "auto"` を追加し、内部の `providers` 計算と `device_label` 計算を新関数に委譲する。

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
    # ... (以下、SessionOptions 生成のコードは現行のまま) ...

    device_label = _inline_get_device_label(device)  # ← 旧: "cuda0" if use_cuda else "cpu"
    cache_path = model_p.with_suffix(f".{device_label}.opt.onnx")
```

**変更箇所の概要（差分イメージ）:**

```diff
 def _load_session_inline(
     model_path: str | Path,
     *,
     use_cuda: bool = False,
+    device: str = "auto",
 ) -> onnxruntime.InferenceSession:
+    # Backward compat: use_cuda=True + device="auto" → device="cuda"
+    if use_cuda and device == "auto":
+        device = "cuda"
-    providers: list[str | tuple[str, dict[str, Any]]]
-    if use_cuda:
-        providers = [
-            (
-                "CUDAExecutionProvider",
-                {"cudnn_conv_algo_search": "HEURISTIC"},
-            )
-        ]
-    else:
-        providers = ["CPUExecutionProvider"]
+    providers = _inline_get_providers(device)
     # ... SessionOptions 生成 (変更なし) ...
-    device_label = "cuda0" if use_cuda else "cpu"
+    device_label = _inline_get_device_label(device)
     cache_path = model_p.with_suffix(f".{device_label}.opt.onnx")
```

### 2.3 `PiperVoice.load()` の修正

**変更箇所:** `src/python_run/piper/voice.py` の `PiperVoice.load()` スタティックメソッド（389行目〜418行目）

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

    if config_path is None:
        candidate = Path(f"{model_path}.json")
        if candidate.exists():
            config_path = candidate
        else:
            config_path = Path(model_path).parent / "config.json"

    with open(config_path, encoding="utf-8") as config_file:
        config_dict = json.load(config_file)

    if _HAS_SHARED_ORT_UTILS:
        session = _shared_create_session_with_cache(model_path, device=device)
        _shared_warmup(session)
    else:
        session = _load_session_inline(model_path, device=device)
        _warmup_session(session)

    return PiperVoice(
        config=PiperConfig.from_dict(config_dict),
        session=session,
    )
```

**変更のポイント:**

- 現行の `if _HAS_SHARED_ORT_UTILS and not use_cuda:` という条件分岐を撤廃し、`_HAS_SHARED_ORT_UTILS` があれば常に共有実装を使う形に変更する。`device` 引数を `_shared_create_session_with_cache()` に渡すことで、CUDA/CoreML 等の全 EP が共有実装経由で動作する。
- `_load_session_inline()` には `use_cuda=` ではなく `device=device` を渡す。`use_cuda` の backward compat 変換は `load()` の先頭で処理済みのため、インライン関数には変換後の `device` を渡せばよい。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|---|---|---|
| Implementation Agent | 1 | `_inline_get_providers()` / `_inline_get_device_label()` の追加、`_load_session_inline()` の修正、`PiperVoice.load()` のシグネチャ変更 |
| Review Agent | 1 | T-02 の `ort_utils.py` との同期確認（定数テーブル・ロジックの一致）、後方互換確認（`use_cuda=True` の動作）、型ヒント確認 |
| QA Agent | 1 | 既存テスト（`src/python_run/tests/`）全件実行、`TestVoiceCacheParity` の命名規則同期テスト確認 |

---

## 4. 提供範囲とテスト項目

### 提供範囲（スコープ）

| ファイル | 変更内容 |
|---|---|
| `src/python_run/piper/voice.py` | `_INLINE_EP_AUTO_PRIORITY`, `_INLINE_EP_KEY_MAP` 定数追加 / `_inline_get_providers()` 追加 / `_inline_get_device_label()` 追加 / `_load_session_inline()` のシグネチャ変更（`device: str` 追加）と内部実装変更 / `PiperVoice.load()` のシグネチャ変更（`device: str` 追加）と内部実装変更 |

### Unit テスト

既存テストファイル `src/python_run/tests/` で以下の回帰テストが通ること：

**後方互換テスト（既存テストのうち、動作変更の影響範囲）:**
- `PiperVoice.load(model_path, use_cuda=False)` が CPU EP でセッションを生成すること
- `PiperVoice.load(model_path, use_cuda=True)` が CUDA EP でセッションを生成すること（`device="cuda"` として扱われる）
- `PiperVoice.load(model_path)` がデフォルトで `device="auto"` として動作し、利用可能な最良 EP を選択すること

**インライン関数テスト（新規追加推奨）:**
- `_inline_get_providers("cpu")` → `["CPUExecutionProvider"]`
- `_inline_get_providers("auto")` が CUDA 利用可能時に CUDA を返すこと
- `_inline_get_providers("coreml")` が CoreML 利用可能時に CoreML を返すこと
- `_inline_get_device_label("coreml")` → `"coreml"`
- `_inline_get_device_label("cuda:1")` → `"cuda1"`
- `PIPER_EXECUTION_PROVIDER` env var が `_inline_get_providers()` / `_inline_get_device_label()` を上書きすること

**`TestVoiceCacheParity` テスト（既存）:**
- `test_cache_path_naming_cpu` / `test_cache_path_naming_cuda` が引き続き通ること
- 新 EP 用の命名テストを追加することが望ましい（例: `test_cache_path_naming_coreml`）

### E2E テスト

- `PIPER_EXECUTION_PROVIDER=cpu` でキャッシュファイル名が `model.cpu.opt.onnx` になること
- macOS + `device="coreml"` でキャッシュファイル名が `model.coreml.opt.onnx` になること（CI: macos-14 ランナー）
- HTTP サーバー（`http_server.py`）経由での合成リクエストが、EP 変更後も正常に応答すること

---

## 5. 実装に関する懸念事項とレビュー項目

### 懸念事項

1. **`_HAS_SHARED_ORT_UTILS` 分岐の撤廃リスク**: 現行コードでは `_HAS_SHARED_ORT_UTILS and not use_cuda` の条件分岐があり、CUDA 使用時はインライン実装を優先していた。これは `cudnn_conv_algo_search=HEURISTIC` オプションを確実に渡すためだった。T-02 で共有実装が CUDA のオプションを適切に設定するようになるため、T-02 完了を前提として分岐を撤廃する。ただし T-02 の実装を確認してから変更すること。

2. **`Any` 型インポート**: `_inline_get_providers()` の戻り値型で `Any` を使用する。`voice.py` の先頭で `from typing import Any` が既にインポートされているか確認すること（未インポートの場合は追加）。

3. **インライン実装の同期コスト**: `voice.py` は `ort_utils.py` の機能を複製する「インライン実装」を持つ設計上の負債を内包している。T-02 で `ort_utils.py` を変更した後、T-03 で `voice.py` にも同等の変更を加える必要があるが、このダブルメンテナンスは将来的なバグの温床になり得る。`# NOTE: voice.py (python_run) にインライン複製あり。変更時は両方更新すること`（`ort_utils.py` 141行目）のコメントが引き継ぎ者に確実に認識されるよう、T-03 完了時に同コメントの内容を更新すること。

4. **`_shared_create_session_with_cache` のインターフェース変化**: T-02 完了後の `create_session_with_cache(model_path, device=device)` シグネチャを確認してから T-03 の変更を行うこと。T-02 でデフォルト値が変更されている可能性がある。

5. **`http_server.py` への影響**: `voice.py` の `PiperVoice.load()` シグネチャ変更が HTTP サーバーの呼び出し箇所（`docker/python-inference/inference.py` 等）に影響しないか確認すること。既存の `use_cuda` 引数を使っているコードはそのまま動作するが、新しい `device` 引数を活用するためのサーバー側変更はスコープ外。

6. **`@staticmethod` と `@classmethod` の混在**: 現行 `PiperVoice.load()` は `@staticmethod` として定義されている（390行目付近）。`@classmethod` のほうがサブクラス化に対応できるが、変更するとAPIが変わる（`cls` 引数の有無）。本タスクでは変更しない。

### レビューチェックリスト

- [ ] `_INLINE_EP_AUTO_PRIORITY` と `ort_utils._EP_AUTO_PRIORITY` が同一のリストであること
- [ ] `_INLINE_EP_KEY_MAP` と `ort_utils._EP_KEY_TO_ORT_NAME` が同一のマッピングであること
- [ ] `_inline_get_device_label()` の `label_map` と `ort_utils._EP_ORT_TO_LABEL` が一致していること
- [ ] `_load_session_inline()` 内の `device_label` 計算が `_inline_get_device_label(device)` を呼ぶよう変更されていること
- [ ] `PiperVoice.load()` で `use_cuda=True` かつ `device="auto"` の場合に `device="cuda"` として扱われること（backward compat）
- [ ] `_HAS_SHARED_ORT_UTILS` 分岐変更後、CUDA EP で `cudnn_conv_algo_search=HEURISTIC` が確実に設定されること
- [ ] `from typing import Any` が `voice.py` の先頭でインポートされていること
- [ ] `ort_utils.py` の既存コメント（141行目の `NOTE:`）が T-03 の変更を反映して更新されていること
- [ ] 既存テスト（`TestVoiceCacheParity`）の命名規則テストが引き続き通ること

---

## 6. 一から作り直すとしたら（Green Field Design）

### 設計思想

「スタンドアロン動作のためにコードを複製しない」という原則を採用する。`voice.py` がインライン実装を持つのは `piper_train` を必須依存にしたくないという設計意図があるが、これは「コード複製」によるダブルメンテナンスというコストを生んでいる。理想的には、EP 選択ロジックを `piper-plus` の軽量コアとして `piper_run_core` パッケージに分離し、`piper_train` も `piper_run` も同パッケージに依存する形に変える。

### アーキテクチャ

```
packages/
  piper-plus-core/          # 軽量コア（numpy + onnxruntime のみ依存）
    setup.py                # 最小依存
    piper_core/
      ep_resolver.py        # EP 選択（T-02 の EPResolver クラス相当）
      session_builder.py    # SessionOptions + キャッシュ + Warmup
      voice_base.py         # PiperVoice の基底クラス

  piper-plus-train/         # 学習側（piper_train）
    # piper-plus-core を依存に追加
    piper_train/
      ort_utils.py          # piper_core.session_builder を wrap

  piper-plus/               # 推論ランタイム側
    # piper-plus-core を依存に追加
    piper/
      voice.py              # piper_core.voice_base.PiperVoiceBase を継承
```

**現行の問題点:**
- `ort_utils.py` (学習側) と `voice.py` (推論側) の2箇所に EP ロジックが存在し、どちらが正とも言えない状態
- `_HAS_SHARED_ORT_UTILS` フラグによる実行時の条件分岐は、ロジックが分岐していることの副作用であり、根本的な解決ではない

### 実装アプローチ

**短期（本 Issue の範囲）:** T-03 では現行のインライン複製アプローチを維持しつつ、同期が取れていることをテストで保証する。新規テスト `test_inline_ort_parity.py` を追加し、`_inline_get_providers()` が `ort_utils.get_providers()` と同じ出力を返すことをパラメトリックテストで検証する。

**中期（将来 Issue）:** `piper-plus-core` パッケージへの分離。`ort_utils.py` コメント（141行目の `NOTE:`）に技術的負債を明記し、将来の担当者が把握できるようにする。

### 現行実装との主な差異

| 観点 | 現行 | 理想 |
|---|---|---|
| コード共有 | インライン複製 | 共通パッケージに切り出し |
| パッケージ構成 | `piper_train` / `piper_run` の2階層 | `piper_core` を底辺とする3階層 |
| `PiperVoice.load()` のデフォルト EP | CPU（暗黙） | `auto`（明示） |
| `use_cuda` 引数 | メイン API | 非推奨（Deprecated）として docstring に明記、major version up 時に削除 |
| 同期の保証 | コメントのみ | パリティテストで自動保証 |
| EP 拡張コスト | `voice.py` と `ort_utils.py` の2箇所を変更 | `piper_core.ep_resolver` の1箇所を変更 |

---

## 7. 後続タスクへの引き継ぎ事項

### T-04 以降（Rust/Go/C#/C++ ランタイム）への引き継ぎ

1. **Python 実装の確定版**: T-03 完了時点での `_INLINE_EP_AUTO_PRIORITY`（`["CUDAExecutionProvider", "CoreMLExecutionProvider", "DmlExecutionProvider", "OpenVINOExecutionProvider"]`）が全ランタイムの自動検出優先度の正とする。

2. **環境変数仕様の確定**: `PIPER_EXECUTION_PROVIDER` の受け入れ値（`"cpu"`, `"cuda"`, `"cuda:N"`, `"coreml"`, `"directml"`, `"directml:N"`, `"openvino"`, `"tensorrt"`, `"tensorrt:N"`）が Python 側で確定する。Rust/Go/C#/C++ も同じ値をサポートすること。

3. **キャッシュラベル命名規則の確定**: T-03 完了時点のキャッシュラベル（`"cpu"`, `"cuda0"`, `"coreml"`, `"directml0"`, `"openvino"`, `"tensorrt0"`）が全ランタイムの命名規則の正とする。`ort-session-contract.toml`（T-01 で更新済み）も同内容を反映していることを確認すること。

4. **OpenVINO の Python 専用スコープ**: `_INLINE_EP_AUTO_PRIORITY` に `"OpenVINOExecutionProvider"` が含まれているが、これは Python ランタイム専用のスコープ（設計仕様書 §4）。Rust/Go/C#/C++ の `EP_AUTO_PRIORITY` には含めないこと。

5. **`use_cuda` deprecation 告知**: T-03 完了後、`PiperVoice.load()` の `use_cuda` パラメータに `DeprecationWarning` を追加するかどうかは T-03 実施者が判断する。明示的な deprecation を入れる場合は CHANGELOG に記載し、後続ランタイムの担当者に共有すること。
