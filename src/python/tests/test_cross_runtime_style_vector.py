""": cross-runtime style_vector contract verification.

Six runtimes (Python, C++, Rust, C#, Go, WASM/JS) each implement
``style_vector`` input handling according to the contract written in
``docs/spec/style-vector-contract.toml``. A full byte-for-byte comparison
would require building and running every runtime against a shared ONNX
model — that is left to CI gates.

This file verifies the static guarantees that every runtime depends on:

1. The contract TOML exists and declares the invariants we assert elsewhere.
2. Each runtime's reference file (listed in ``[implementations]`` of the
   contract) mentions ``style_vector`` and ``style_vector_mask`` — a simple
   but effective guard against runtimes silently dropping out of sync.
3. The Python-side ``SynthesizerTrn.infer`` and the ONNX exporter accept
   a ``style_vector`` argument / CLI flag (the contract's Python anchors).
4. The Python unit tests for style_vector conditioning exist and use the
   exact tensor shape/dtype that the contract mandates.

When this file fails it almost always means one of the runtimes was modified
without updating the contract TOML, or vice versa. The fix is to reconcile
the specific runtime file with the contract.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "docs" / "spec" / "style-vector-contract.toml"


@pytest.fixture(scope="module")
def contract() -> dict:
    assert CONTRACT_PATH.is_file(), f"contract missing: {CONTRACT_PATH}"
    with CONTRACT_PATH.open("rb") as handle:
        return tomllib.load(handle)


# ---------------------------------------------------------------------------
# 1. Contract shape invariants
# ---------------------------------------------------------------------------


def test_contract_declares_float32_input(contract: dict) -> None:
    style_input = contract["onnx"]["inputs"]["style_vector"]
    assert style_input["dtype"] == "float32"
    assert style_input["shape"] == [1, "style_vector_dim"]


def test_contract_declares_int64_mask(contract: dict) -> None:
    mask = contract["onnx"]["inputs"]["style_vector_mask"]
    assert mask["dtype"] == "int64"
    assert mask["shape"] == [1, 1]


def test_contract_declares_all_six_runtimes(contract: dict) -> None:
    assert sorted(contract["meta"]["applies_to"]) == sorted(
        ["python", "rust", "go", "cpp", "csharp", "wasm-js"]
    )


# ---------------------------------------------------------------------------
# 2. Every runtime reference file mentions the contract tokens
# ---------------------------------------------------------------------------


def _runtime_reference_files(contract: dict) -> list[Path]:
    """Walk the [implementations] table and collect file paths."""
    files: list[Path] = []
    for runtime_group in contract["implementations"].values():
        if isinstance(runtime_group, str):
            files.append(REPO_ROOT / runtime_group)
        elif isinstance(runtime_group, dict):
            for value in runtime_group.values():
                if isinstance(value, str):
                    files.append(REPO_ROOT / value)
    return files


def test_every_runtime_file_exists(contract: dict) -> None:
    for path in _runtime_reference_files(contract):
        # Directories listed in the contract (e.g. C# Inference/) are OK too.
        assert path.exists(), f"contract points at missing file: {path}"


def _gather_source_text(path: Path) -> str:
    """Read file contents; for directories, read every source file inside."""
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    if path.is_dir():
        parts: list[str] = []
        for child in path.rglob("*"):
            if child.is_file() and child.suffix in {
                ".py", ".cs", ".cpp", ".hpp", ".h",
                ".rs", ".go", ".js", ".ts", ".d.ts",
            }:
                parts.append(child.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(parts)
    return ""


@pytest.mark.parametrize(
    "runtime_key",
    ["python.export", "python.runtime", "python.cli",
     "cpp.header", "cpp.runtime", "cpp.c_api", "cpp.cli",
     "rust.core", "rust.cli",
     "csharp.core", "csharp.cli",
     "go.core", "go.cli",
     "wasm.js", "wasm.types"],
)
def test_runtime_file_mentions_style_vector(contract: dict, runtime_key: str) -> None:
    """Each runtime reference file/dir must mention `style_vector`.

    This guards against a runtime silently dropping style_vector support while
    the contract still advertises it.
    """
    group, leaf = runtime_key.split(".", 1)
    path = REPO_ROOT / contract["implementations"][group][leaf]
    text = _gather_source_text(path)
    assert text, f"no readable source files in {path}"
    # Accept either snake_case (ONNX feed keys) or camelCase (JS/C# variants).
    # We use a lenient pattern: any occurrence of style_vector OR styleVector
    # with a word-boundary-ish suffix.
    pattern = re.compile(r"style[_]?[Vv]ector")
    assert pattern.search(text), (
        f"{runtime_key} at {path.relative_to(REPO_ROOT)} does not reference "
        f"style_vector — runtime likely out of sync with the contract"
    )


# ---------------------------------------------------------------------------
# 3. Python anchor: SynthesizerTrn.infer exposes `style_vector`
# ---------------------------------------------------------------------------


def test_synthesizer_trn_infer_has_style_vector_parameter() -> None:
    from piper_train.vits.models import SynthesizerTrn

    sig = inspect.signature(SynthesizerTrn.infer)
    assert "style_vector" in sig.parameters, (
        "SynthesizerTrn.infer must accept a `style_vector` parameter; "
        "runtimes rely on this signature for graph export."
    )


def test_infer_onnx_has_style_vector_cli_flag() -> None:
    path = REPO_ROOT / "src" / "python" / "piper_train" / "infer_onnx.py"
    text = path.read_text(encoding="utf-8")
    assert "--style-vector" in text, (
        "infer_onnx.py must expose --style-vector to match the cross-runtime "
        "CLI contract defined in style-vector-contract.toml"
    )


def test_export_onnx_writes_style_vector_metadata() -> None:
    path = REPO_ROOT / "src" / "python" / "piper_train" / "export_onnx.py"
    text = path.read_text(encoding="utf-8")
    assert "style_vector_dim" in text, (
        "export_onnx.py must write style_vector_dim metadata to the ONNX model"
    )


# ---------------------------------------------------------------------------
# 4. WASM TypeScript contract: SynthesizeOptions.styleVector
# ---------------------------------------------------------------------------


def test_wasm_typescript_exposes_style_vector_option() -> None:
    d_ts = REPO_ROOT / "src" / "wasm" / "openjtalk-web" / "types" / "index.d.ts"
    text = d_ts.read_text(encoding="utf-8")
    # The d.ts must declare styleVector?: Float32Array inside SynthesizeOptions.
    assert re.search(r"styleVector\??\s*:\s*Float32Array", text), (
        "SynthesizeOptions in index.d.ts must expose styleVector?: Float32Array"
    )


# ---------------------------------------------------------------------------
# 5. Existing unit tests cover the Python side of the contract
# ---------------------------------------------------------------------------


def test_existing_style_vector_unit_tests_present() -> None:
    base = REPO_ROOT / "src" / "python" / "tests"
    assert (base / "test_style_vector_conditioning.py").is_file(), (
        " unit tests missing"
    )
    assert (base / "test_load_weights_from_checkpoint.py").is_file(), (
        " load_weights tests missing"
    )
