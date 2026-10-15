"""
Verify ONNX export contract compliance.

Reads docs/spec/onnx-export-contract.toml and confirms:
  1. main TTS model uses opset_version = 15 (in export_onnx.py)
  2. speaker encoder uses opset_version = 17 (in export_encoder.py)
  3. Both scripts call onnx.checker.check_model after export
  4. Both scripts call onnx.shape_inference.infer_shapes

Exit code:
  0 = compliant
  1 = drift detected
"""

import ast
import sys
from pathlib import Path

from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPORT_ONNX = REPO_ROOT / "src" / "python" / "piper_train" / "export_onnx.py"
EXPORT_ENCODER = (
    REPO_ROOT
    / "src"
    / "python"
    / "piper_train"
    / "speaker_encoder"
    / "export_encoder.py"
)
CONTRACT = REPO_ROOT / "docs" / "spec" / "onnx-export-contract.toml"

EXPECTED_TTS_OPSET = 15
EXPECTED_ENCODER_OPSET = 17


def check_opset(file_path: Path, expected: int, label: str) -> list[str]:
    errors = []
    if not file_path.exists():
        return [f"[{label}] file missing: {file_path}"]
    text = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [f"[{label}] invalid Python: {exc}"]
    assignments = [
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "OPSET_VERSION"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
    ]
    if not assignments:
        errors.append(f"[{label}] OPSET_VERSION not found in {file_path}")
    else:
        actual = assignments[0]
        if actual != expected:
            errors.append(
                f"[{label}] OPSET_VERSION drift: expected {expected}, found {actual} in {file_path}"
            )
    calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
    if not any(
        isinstance(call, ast.Attribute)
        and call.attr == "check_model"
        and isinstance(call.value, ast.Attribute)
        and call.value.attr == "checker"
        for call in calls
    ):
        errors.append(
            f"[{label}] missing onnx.checker.check_model() call in {file_path}"
        )
    if not any(
        isinstance(call, ast.Attribute)
        and call.attr == "infer_shapes"
        and isinstance(call.value, ast.Attribute)
        and call.value.attr == "shape_inference"
        for call in calls
    ):
        errors.append(
            f"[{label}] missing onnx.shape_inference.infer_shapes() call in {file_path}"
        )
    return errors


def main() -> int:
    if not CONTRACT.exists():
        print(f"ERROR: contract file missing: {CONTRACT}", file=sys.stderr)
        return 1

    errors: list[str] = []
    errors.extend(check_opset(EXPORT_ONNX, EXPECTED_TTS_OPSET, "main TTS"))
    errors.extend(
        check_opset(EXPORT_ENCODER, EXPECTED_ENCODER_OPSET, "speaker encoder")
    )

    if errors:
        print("ONNX export contract drift detected:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("✓ ONNX export contract compliant")
    print(f"  - main TTS opset = {EXPECTED_TTS_OPSET}")
    print(f"  - speaker encoder opset = {EXPECTED_ENCODER_OPSET}")
    print(
        "  - both scripts call onnx.checker.check_model + shape_inference.infer_shapes"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
