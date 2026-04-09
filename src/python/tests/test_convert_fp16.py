"""Tests for FP16 conversion tool."""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


onnx = pytest.importorskip("onnx")


def _onnx_inference(onnx_path, phoneme_ids, prosody_features, noise_scale=0.667):
    """Run ONNX inference and return audio output.

    phoneme_ids/prosody_features を指定した場合はそれを使用し、
    それ以外の入力 (sid, lid 等) は本番 _create_dummy_inputs() に委譲する。
    """
    import onnxruntime

    from piper_train.tools.convert_fp16 import _create_dummy_inputs

    session = onnxruntime.InferenceSession(
        str(onnx_path), providers=["CPUExecutionProvider"]
    )

    # 本番関数でベースとなるダミー入力を生成
    inputs = _create_dummy_inputs(session)
    if inputs is None:
        raise RuntimeError("Failed to create dummy inputs for ONNX model")

    # テスト固有の phoneme_ids で上書き
    text = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
    inputs["input"] = text
    inputs["input_lengths"] = np.array([text.shape[1]], dtype=np.int64)
    inputs["scales"] = np.array([noise_scale, 1.0, 0.8], dtype=np.float32)

    # prosody_features の上書き
    input_names = [inp.name for inp in session.get_inputs()]
    if "prosody_features" in input_names:
        pf = []
        for feat in prosody_features:
            if feat is None:
                pf.append([0, 0, 0])
            else:
                pf.append([feat["a1"], feat["a2"], feat["a3"]])
        inputs["prosody_features"] = np.expand_dims(
            np.array(pf, dtype=np.int64), 0
        )

    outputs = session.run(None, inputs)
    return outputs[0].squeeze()


def _count_initializers_by_dtype(onnx_path):
    """Count initializers by data type."""
    model = onnx.load(str(onnx_path))
    counts = {}
    for init in model.graph.initializer:
        dtype = init.data_type
        counts[dtype] = counts.get(dtype, 0) + 1
    return counts


@pytest.mark.unit
class TestFP16Conversion:
    """Basic FP16 conversion tests."""

    def test_converts_model_to_fp16(self, temp_onnx_model, tmp_path):
        """FP16 model is generated successfully."""
        from piper_train.tools.convert_fp16 import main

        fp16_path = tmp_path / "model_fp16.onnx"
        main(["--model", str(temp_onnx_model), "--output", str(fp16_path)])

        assert fp16_path.exists(), "FP16 model file was not created"

        model = onnx.load(str(fp16_path))
        onnx.checker.check_model(model, full_check=False)

    def test_output_file_is_smaller(self, temp_onnx_model, tmp_path):
        """Output file is smaller than the original (roughly 50%)."""
        from piper_train.tools.convert_fp16 import main

        fp16_path = tmp_path / "model_fp16.onnx"
        main(["--model", str(temp_onnx_model), "--output", str(fp16_path)])

        original_size = Path(temp_onnx_model).stat().st_size
        fp16_size = fp16_path.stat().st_size

        assert fp16_size < original_size, (
            f"FP16 model ({fp16_size} bytes) should be smaller than "
            f"FP32 model ({original_size} bytes)"
        )

        reduction = 1.0 - (fp16_size / original_size)
        assert reduction > 0.2, (
            f"Size reduction {reduction:.1%} is less than expected 20% minimum"
        )

    def test_fp16_model_produces_valid_audio(
        self, temp_onnx_model, sample_phoneme_ids, sample_prosody_features, tmp_path
    ):
        """FP16 model produces valid audio (no NaN/Inf)."""
        from piper_train.tools.convert_fp16 import main

        fp16_path = tmp_path / "model_fp16.onnx"
        main(["--model", str(temp_onnx_model), "--output", str(fp16_path)])

        audio = _onnx_inference(fp16_path, sample_phoneme_ids, sample_prosody_features)

        assert audio.ndim == 1, f"Expected 1D audio, got {audio.ndim}D"
        assert audio.shape[0] > 0, "Audio output is empty"
        assert np.isfinite(audio).all(), "Audio contains NaN or Inf values"

    def test_fp16_output_close_to_fp32(
        self, temp_onnx_model, sample_phoneme_ids, sample_prosody_features, tmp_path
    ):
        """FP16 and FP32 outputs are close (relative error < 5%)."""
        from piper_train.tools.convert_fp16 import main

        fp16_path = tmp_path / "model_fp16.onnx"
        main(["--model", str(temp_onnx_model), "--output", str(fp16_path)])

        audio_fp32 = _onnx_inference(
            temp_onnx_model, sample_phoneme_ids, sample_prosody_features
        )
        audio_fp16 = _onnx_inference(
            fp16_path, sample_phoneme_ids, sample_prosody_features
        )

        assert audio_fp32.shape == audio_fp16.shape, (
            f"Shape mismatch: FP32={audio_fp32.shape}, FP16={audio_fp16.shape}"
        )

        np.testing.assert_allclose(
            audio_fp16,
            audio_fp32,
            rtol=0.05,
            atol=0.01,
            err_msg="FP16 output diverges too much from FP32",
        )


@pytest.mark.unit
class TestKeepFP32Ops:
    """Tests for --keep-fp32-ops functionality."""

    def test_default_keep_fp32_ops(self, temp_onnx_model, tmp_path):
        """Default FP32-kept operators are applied and FP16 initializers exist."""
        from piper_train.tools.convert_fp16 import main

        fp16_path = tmp_path / "model_fp16.onnx"
        main(["--model", str(temp_onnx_model), "--output", str(fp16_path)])

        dtype_counts = _count_initializers_by_dtype(fp16_path)
        fp16_count = dtype_counts.get(onnx.TensorProto.FLOAT16, 0)
        assert fp16_count > 0, "No FP16 initializers found - conversion may have failed"

    def test_custom_keep_fp32_ops(self, temp_onnx_model, tmp_path):
        """Custom --keep-fp32-ops operators are preserved in FP32."""
        from piper_train.tools.convert_fp16 import main

        fp16_path = tmp_path / "model_fp16_custom.onnx"
        main(
            [
                "--model",
                str(temp_onnx_model),
                "--output",
                str(fp16_path),
                "--keep-fp32-ops",
                "Conv,MatMul",
            ]
        )

        assert fp16_path.exists(), (
            "FP16 model with custom keep-fp32-ops was not created"
        )

        model = onnx.load(str(fp16_path))
        onnx.checker.check_model(model, full_check=False)


@pytest.mark.unit
class TestValidation:
    """Tests for --validate functionality."""

    def test_validate_passes_for_valid_conversion(
        self, temp_onnx_model, sample_phoneme_ids, sample_prosody_features, tmp_path
    ):
        """Validation passes for a correctly converted model."""
        from piper_train.tools.convert_fp16 import main

        fp16_path = tmp_path / "model_fp16.onnx"
        main(
            ["--model", str(temp_onnx_model), "--output", str(fp16_path), "--validate"]
        )

        assert fp16_path.exists(), "FP16 model was not created with --validate"

        audio = _onnx_inference(fp16_path, sample_phoneme_ids, sample_prosody_features)
        assert np.isfinite(audio).all(), "Validated model produces NaN/Inf audio"


@pytest.mark.unit
class TestCLI:
    """Tests for CLI interface."""

    def test_cli_basic(self, temp_onnx_model, tmp_path):
        """Basic CLI invocation succeeds."""
        fp16_path = tmp_path / "model_fp16_cli.onnx"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "piper_train.tools.convert_fp16",
                "--model",
                str(temp_onnx_model),
                "--output",
                str(fp16_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, (
            f"CLI failed with returncode {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert fp16_path.exists(), "CLI did not produce output file"

    def test_cli_with_validate(self, temp_onnx_model, tmp_path):
        """CLI with --validate flag succeeds."""
        fp16_path = tmp_path / "model_fp16_cli_validate.onnx"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "piper_train.tools.convert_fp16",
                "--model",
                str(temp_onnx_model),
                "--output",
                str(fp16_path),
                "--validate",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, (
            f"CLI with --validate failed with returncode {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert fp16_path.exists(), "CLI with --validate did not produce output file"
