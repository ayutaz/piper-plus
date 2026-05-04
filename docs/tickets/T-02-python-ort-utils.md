# T-02: Python ort_utils.py の EP 拡張

**Milestone:** feat: Hardware EP 自動選択 (#382) — Milestone #16
**依存タスク:** T-01（`docs/spec/ort-session-contract.toml` への EP 仕様追記）
**後続タスク:** T-03（`voice.py` のインライン EP 拡張）

---

## 1. タスク目的とゴール

### 目的

`src/python/piper_train/ort_utils.py` の EP 選択ロジックを現行の「CPU/CUDA のみ」から「CUDA・CoreML・DirectML・OpenVINO・TensorRT を含む全 EP」に拡張する。これにより、macOS Apple Silicon 上での CoreML（3〜10x 高速化）、Windows 上での DirectML（2〜5x）、Intel CPU 上での OpenVINO（1.5〜3x）が利用可能になる。

### なぜ必要か

- 現行 `get_providers(device: str = "cpu")` は `"cpu"`, `"gpu"`, `"auto"` の3値しか受け付けず、CUDA 以外のハードウェアアクセラレーターに対応していない。
- `_get_device_label()` も `"cuda0"` と `"cpu"` の2択しかなく、CoreML・DirectML 等の EP 別キャッシュファイル命名に対応していない。
- T-01 で策定した `ort-session-contract.toml` の仕様（`EP_AUTO_PRIORITY`、`device_label_*` キー、`PIPER_EXECUTION_PROVIDER` env var）に Python ランタイムが準拠する必要がある。

### 完了の定義（Done 基準）

- `get_providers("cpu")` が `["CPUExecutionProvider"]` を返す。
- `get_providers("coreml")` が CoreML EP を返す（利用可能時）。
- `get_providers("auto")` が `EP_AUTO_PRIORITY` 順（CUDA→CoreML→DirectML→OpenVINO→CPU）に自動選択する。TensorRT を auto 対象に含まない。
- `PIPER_EXECUTION_PROVIDER` 環境変数が `device` 引数より優先される。
- 存在しない EP を指定した場合に警告ログを出して CPU にフォールバックする。
- `_get_device_label()` が全 EP に対して `ort-session-contract.toml` 準拠のラベル（`"coreml"`, `"directml0"`, `"openvino"`, `"tensorrt0"` 等）を返す。
- 新規テスト（`TestGetProviders` + `TestGetDeviceLabel` クラス）が全件 PASS。
- 既存テスト（`TestCreateSessionOptions`, `TestModelCache` 等）が全件 PASS のまま。

---

## 2. 実装する内容の詳細

### 2.1 `get_providers()` の置き換え

**変更箇所:** `src/python/piper_train/ort_utils.py` の `get_providers()` 関数（104行目付近）

現行の関数シグネチャ `get_providers(device: str = "cpu")` を以下で置き換える。

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
        _LOGGER.warning("Unknown provider %r, falling back to CPU", provider_key)
        return ["CPUExecutionProvider"]

    if ep_name not in available:
        _LOGGER.warning("EP %s not available, falling back to CPU", ep_name)
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

**注意事項:**
- 既存の `TestGetProviders.test_gpu_provider_with_cuda` は `get_providers("gpu")` を呼んでいる。新実装では `"gpu"` は `_EP_KEY_TO_ORT_NAME` に未登録のため `"Unknown provider"` 警告＋CPU フォールバックになる。既存テストが壊れないようテストの `"gpu"` を `"cuda"` に書き換えるか、後方互換のため `"gpu"` を `"cuda"` の別名として `_EP_KEY_TO_ORT_NAME` に登録する方針を選択すること（実装者判断）。
- デフォルト値を `"cpu"` から `"auto"` に変更する。これにより `create_session_with_cache()` の呼び出し側に影響が出る可能性があるため、`create_session_with_cache()` 内部の `device="cpu"` デフォルトは変更しない。

### 2.2 `_get_device_label()` の置き換え

**変更箇所:** `src/python/piper_train/ort_utils.py` の `_get_device_label()` 関数（124行目付近）

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

**注意事項:**
- 既存テスト `TestModelCacheHelpers.test_device_label_gpu_with_cuda` は `_get_device_label("gpu")` を呼んでいる。新実装では `"gpu"` は `_EP_KEY_TO_LABEL_FORMAT` に未登録のため `"cpu"` を返す（テストが壊れる）。`"gpu"` の後方互換処理か、テスト修正が必要。

### 2.3 テストの追加

**変更箇所:** `src/python/tests/test_ort_utils.py` の末尾

実装計画の Task 2 Step 1 に記載されたテストクラス (`TestGetProviders`, `TestGetDeviceLabel`) を全件追加する。既存の `TestGetProviders` クラス名と衝突する場合は既存クラスを新実装対応に書き換えること。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|---|---|---|
| Implementation Agent | 1 | `ort_utils.py` の `get_providers()` / `_get_device_label()` 置き換え、テスト追加 |
| Review Agent | 1 | コントラクト仕様（T-01 で更新された `ort-session-contract.toml`）との整合性確認、後方互換確認 |
| QA Agent | 1 | 全テスト実行（新規 + 既存）、`create_session_with_cache()` への影響検証 |

---

## 4. 提供範囲とテスト項目

### 提供範囲（スコープ）

| ファイル | 変更内容 |
|---|---|
| `src/python/piper_train/ort_utils.py` | `get_providers()` 置き換え（全 EP 対応）、`_get_device_label()` 置き換え（全 EP ラベル対応）、定数テーブル（`_EP_AUTO_PRIORITY`, `_EP_KEY_TO_ORT_NAME`, `_EP_KEY_TO_LABEL_FORMAT`, `_EP_ORT_TO_LABEL`）追加 |
| `src/python/tests/test_ort_utils.py` | `TestGetProviders` クラス（13テスト）と `TestGetDeviceLabel` クラス（11テスト）の追加 |

### Unit テスト

実装計画に記載された以下のテストを追加・更新する：

**`TestGetProviders` クラス（13件）:**
- `test_cpu_returns_cpu_ep`: `get_providers("cpu")` → `["CPUExecutionProvider"]`
- `test_auto_with_no_gpu_returns_cpu`: CPU のみ利用可能時の auto → CPU
- `test_auto_detects_cuda`: CUDA 利用可能時の auto → CUDA
- `test_auto_detects_coreml_when_no_cuda`: CoreML 利用可能（CUDA なし）時の auto → CoreML
- `test_auto_detects_directml_when_no_cuda_coreml`: DirectML のみ利用可能時の auto → DML
- `test_explicit_cuda_returns_cuda_ep`: `"cuda"` 明示指定
- `test_explicit_coreml_returns_coreml_ep`: `"coreml"` 明示指定
- `test_explicit_directml_returns_dml_ep`: `"directml"` 明示指定
- `test_unavailable_ep_falls_back_to_cpu`: 利用不可能な EP 指定 → CPU フォールバック
- `test_env_var_overrides_device_param`: `PIPER_EXECUTION_PROVIDER=cpu` が device 引数を上書き
- `test_env_var_selects_coreml`: `PIPER_EXECUTION_PROVIDER=coreml` の動作
- `test_tensorrt_excluded_from_auto`: TensorRT が auto 検出に含まれないこと
- `test_unknown_device_falls_back_to_cpu`: 未知の device 文字列 → CPU フォールバック

**`TestGetDeviceLabel` クラス（11件）:**
- `test_cpu_returns_cpu`: `"cpu"` → `"cpu"`
- `test_auto_no_gpu_returns_cpu`: GPU なし環境の auto → `"cpu"`
- `test_auto_with_cuda_returns_cuda0`: CUDA 利用可能時の auto → `"cuda0"`
- `test_explicit_cuda_returns_cuda0`: `"cuda"` → `"cuda0"`
- `test_explicit_cuda1_returns_cuda1`: `"cuda:1"` → `"cuda1"`
- `test_explicit_coreml_returns_coreml`: `"coreml"` → `"coreml"`
- `test_explicit_directml_returns_directml0`: `"directml"` → `"directml0"`
- `test_explicit_directml1_returns_directml1`: `"directml:1"` → `"directml1"`
- `test_explicit_openvino_returns_openvino`: `"openvino"` → `"openvino"`
- `test_explicit_tensorrt_returns_tensorrt0`: `"tensorrt"` → `"tensorrt0"`
- `test_env_var_overrides_device_label`: `PIPER_EXECUTION_PROVIDER=coreml` が device ラベルを上書き

### E2E テスト

- `PIPER_EXECUTION_PROVIDER=cpu` 環境変数を設定した状態で `create_session_with_cache()` を呼び出し、`model.cpu.opt.onnx` ファイルが生成されること
- `PIPER_EXECUTION_PROVIDER=coreml`（macOS のみ）環境変数設定下で `model.coreml.opt.onnx` ファイルが生成されること（CI: macos-14 ランナー）
- 設定なし（auto）でのセッション生成が正常完了すること（既存 smoke test の範囲）

---

## 5. 実装に関する懸念事項とレビュー項目

### 懸念事項

1. **後方互換問題（`"gpu"` 文字列）**: 既存テスト `test_gpu_provider_with_cuda` と `test_device_label_gpu_with_cuda` は `"gpu"` を device 値として使用している。新実装では `"gpu"` がサポート外になるため、テストが壊れる。対処方針として以下を検討すること:
   - `_EP_KEY_TO_ORT_NAME["gpu"] = "CUDAExecutionProvider"` として別名を登録する（推奨: 移行期の互換維持）
   - または既存テストを `"cuda"` に書き換える（テストの意図が明確になる）

2. **`get_providers()` デフォルト値変更**: 現行 `device: str = "cpu"` → 新実装 `device: str = "auto"` への変更。`create_session_with_cache()` のデフォルト `device="cpu"` は変更しないため呼び出し側への影響は最小限だが、`get_providers()` を直接呼ぶコードがあれば挙動が変わる。影響範囲の調査が必要。

3. **CoreML の初回セッション初期化遅延**: 設計仕様書 §3 に記載の通り、CoreML EP 利用時はANE コンパイルにより初回セッション初期化が数秒かかる場合がある。warmup でカバーされるが、ユーザーの体感で「起動が遅い」という印象を与える可能性がある。ログ出力で通知することを推奨。

4. **`get_providers()` の戻り値型変化**: `list[str]` から `list[str | tuple[str, dict]]` に変わる。型ヒントの更新を忘れないこと。

5. **ORT EP 初期化失敗のハンドリング**: `create_session_with_cache()` 内で ORT セッション初期化時に `onnxruntime.OrtException` が発生した場合（EP は利用可能だが初期化失敗）の CPU フォールバック処理。設計仕様書 §5.1 には `load_onnx_model` 内の try-except で対処するとあるが、`ort_utils.py` では `create_session_with_cache()` 内に try-except を追加する必要がある。

### レビューチェックリスト

- [ ] `_EP_AUTO_PRIORITY` に TensorRT が含まれていないこと（設計仕様書 §2.1 に準拠）
- [ ] `PIPER_EXECUTION_PROVIDER` 環境変数が `device` 引数より優先されること（設計仕様書 §2.2）
- [ ] `"cuda:1"` 形式のデバイス番号指定が正しく解析されること
- [ ] `"gpu"` の後方互換が考慮されていること（既存テストが壊れないこと）
- [ ] `_get_device_label()` のキャッシュラベルが `ort-session-contract.toml` の `device_label_*` キーと一致していること
- [ ] `get_providers()` 戻り値型が型ヒントに正しく反映されていること
- [ ] 不明な provider 文字列に対して警告ログが出力されること（`_LOGGER.warning` 使用）
- [ ] ロガー変数名が `_LOGGER`（既存コードと統一）であること
- [ ] `create_session_with_cache()` のデフォルト引数 `device="cpu"` が変更されていないこと

---

## 6. 一から作り直すとしたら（Green Field Design）

### 設計思想

「EP 選択ロジックは単一責任のプロバイダーファクトリとして独立させる」という原則で設計する。現行の `ort_utils.py` は Session 設定・EP 選択・キャッシュ・Warmup を1ファイルに同居させており、EP 拡張のたびにファイル全体の理解が必要になる。EP 選択ロジックを独立モジュールとして分離することで、テスト容易性と保守性が向上する。

### アーキテクチャ

```
piper_train/
  ort_utils/
    __init__.py          # 公開 API（後方互換）
    ep_resolver.py       # EP 選択ロジック（単一責任）
    session_factory.py   # SessionOptions 生成
    model_cache.py       # .opt.onnx キャッシュ管理
    warmup.py            # セッション Warmup
```

**`ep_resolver.py` の理想設計:**

```python
from dataclasses import dataclass
from enum import Enum, auto

class ExecutionProvider(Enum):
    CPU = auto()
    CUDA = auto()
    COREML = auto()
    DIRECTML = auto()
    OPENVINO = auto()
    TENSORRT = auto()

@dataclass(frozen=True)
class ResolvedEP:
    provider: ExecutionProvider
    device_id: int
    ort_name: str
    cache_label: str
    ort_options: dict

class EPResolver:
    AUTO_PRIORITY = [
        ExecutionProvider.CUDA,
        ExecutionProvider.COREML,
        ExecutionProvider.DIRECTML,
        ExecutionProvider.OPENVINO,
    ]

    def resolve(self, device: str = "auto") -> ResolvedEP:
        """環境変数 > device 引数 > 自動検出の優先順位で EP を解決する。"""
        ...
    
    def get_ort_providers(self, resolved: ResolvedEP) -> list:
        """ORT InferenceSession 生成用のプロバイダーリストを返す。"""
        ...
```

**利点:**
- `ExecutionProvider` Enum により文字列ミスが型エラーで検出される
- `ResolvedEP` データクラスで EP 情報（ORT 名、キャッシュラベル、オプション）を1オブジェクトに集約し、`get_providers()` と `_get_device_label()` が同じ解決結果から派生する（現行は2関数が独立して環境変数を読む重複あり）
- `EPResolver.resolve()` のユニットテストが環境変数なしのモック不要な純粋関数的テストで書ける

### 実装アプローチ

現行実装との主な差異：

1. **`get_providers()` と `_get_device_label()` の重複**: 両関数が独立して `os.environ.get("PIPER_EXECUTION_PROVIDER")` を呼んでいる。理想的には1回の `resolve()` 呼び出しで EP を決定し、その結果から ORT プロバイダーリストとキャッシュラベルを両方導出する。
2. **文字列リテラルの散在**: `"CUDAExecutionProvider"`, `"DmlExecutionProvider"` 等のORT EP 名が複数箇所に散在。Enum 化で一元管理できる。
3. **`"gpu"` 別名**: 後方互換のために `"gpu"` を受け付ける必要があるが、内部的には `"cuda"` に変換するアダプター層として扱うと設計が明確になる。

### 現行実装との主な差異

| 観点 | 現行 | 理想 |
|---|---|---|
| モジュール構成 | 単一ファイル | モジュール分割 |
| EP 表現 | 文字列 | Enum |
| 環境変数読み取り | `get_providers()` と `_get_device_label()` で個別に | `resolve()` で一元化 |
| 後方互換 | `"gpu"` が非対応（要対処） | Adapter パターンで明示的に分離 |
| エラーハンドリング | EP 利用不可時は警告＋CPU | ORT Session 初期化失敗時のフォールバックが不十分 |

---

## 7. 後続タスクへの引き継ぎ事項

### T-03（`voice.py` インライン EP 拡張）への引き継ぎ

T-02 完了後、以下の情報を T-03 担当に伝えること：

1. **定数テーブルのコピー**: `voice.py` はスタンドアロン動作のためインライン実装が必要。T-02 で定義した `_EP_AUTO_PRIORITY`, `_EP_KEY_TO_ORT_NAME`, `_EP_KEY_TO_LABEL_FORMAT`, `_EP_ORT_TO_LABEL` と同一ロジックを `_INLINE_EP_AUTO_PRIORITY`, `_INLINE_EP_KEY_MAP` 等のプレフィックスで複製する（`voice.py` の慣例に合わせる）。

2. **`"gpu"` 後方互換の決定事項**: T-02 で `"gpu"` を `"cuda"` 別名として扱うか廃止するかを決定した場合、T-03 でも同じ方針を採用すること。

3. **`create_session_with_cache()` のインターフェース**: T-02 完了後の関数シグネチャ（デフォルト値の変更有無）を T-03 に伝え、`voice.py` の `_HAS_SHARED_ORT_UTILS` パスの呼び出しコードが整合していることを確認すること。

4. **既存テストの変更内容**: `test_ort_utils.py` で `"gpu"` → `"cuda"` への書き換えを行った場合、`test_voice*.py` に同様の変更が必要かを T-03 担当が確認すること。

5. **コメント更新**: `ort_utils.py` のコメント（141行目）`# NOTE: voice.py (python_run) にインライン複製あり。変更時は両方更新すること` が T-03 完了後も有効であることを確認すること。
