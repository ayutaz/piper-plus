"""Check an installed provider distribution and run actual CPU fallback inference."""

import argparse
import importlib.metadata
from pathlib import Path

import numpy as np
import onnxruntime as ort


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", choices=["cpu", "gpu"], required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    installed = {
        distribution.metadata["Name"].lower()
        for distribution in importlib.metadata.distributions()
    }
    expected = "onnxruntime-gpu" if args.expected == "gpu" else "onnxruntime"
    forbidden = "onnxruntime" if args.expected == "gpu" else "onnxruntime-gpu"
    if expected not in installed or forbidden in installed:
        raise RuntimeError(
            f"Expected only {expected}, found {installed & {'onnxruntime', 'onnxruntime-gpu'}}"
        )
    if (
        args.expected == "gpu"
        and "CUDAExecutionProvider" not in ort.get_available_providers()
    ):
        raise RuntimeError("GPU wheel does not expose CUDAExecutionProvider")
    session = ort.InferenceSession(str(args.model), providers=["CPUExecutionProvider"])
    outputs = session.run(
        None,
        {
            "input": np.array([[1, 10, 11, 2]], dtype=np.int64),
            "input_lengths": np.array([4], dtype=np.int64),
            "scales": np.array([0, 1, 0], dtype=np.float32),
        },
    )
    if not outputs[0].size or not np.isfinite(outputs[0]).all():
        raise RuntimeError("CPU fallback produced empty/nonfinite audio")
    print(
        f"{expected} {ort.__version__}: isolated distribution and CPU fallback passed; providers={ort.get_available_providers()}"
    )


if __name__ == "__main__":
    main()
