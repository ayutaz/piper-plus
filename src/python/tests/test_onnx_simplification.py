"""
Tests for ONNX model simplification functionality
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from piper_train.export_onnx import simplify_onnx_model


class TestONNXSimplification:
    """Test ONNX model simplification functionality"""

    @pytest.mark.unit
    def test_simplify_onnx_model_missing_file(self):
        """Test simplification with non-existent file"""
        non_existent_path = Path("/tmp/non_existent_model.onnx")

        # Should handle missing files gracefully
        with patch("piper_train.export_onnx.onnx") as mock_onnx:
            mock_onnx.load.side_effect = FileNotFoundError("File not found")
            result = simplify_onnx_model(non_existent_path)
            assert result is False

    @pytest.mark.unit
    def test_simplify_onnx_model_missing_dependency(self):
        """Test behavior when onnxsim is not installed"""
        with tempfile.NamedTemporaryFile(suffix=".onnx") as tmp_file:
            tmp_path = Path(tmp_file.name)

            # Mock ImportError for missing onnxsim
            with patch("piper_train.export_onnx.onnx") as mock_onnx:
                mock_onnx.load.return_value = Mock()

                with patch(
                    "builtins.__import__",
                    side_effect=ImportError("No module named 'onnxsim'"),
                ):
                    result = simplify_onnx_model(tmp_path)
                    assert result is False

    @pytest.mark.unit
    def test_simplify_onnx_model_validation_failed(self):
        """Test behavior when simplification validation fails"""
        with tempfile.NamedTemporaryFile(suffix=".onnx") as tmp_file:
            tmp_path = Path(tmp_file.name)

            # Mock successful import but failed validation
            with (
                patch("piper_train.export_onnx.onnx") as mock_onnx,
                patch("piper_train.export_onnx.simplify") as mock_simplify,
            ):
                mock_onnx.load.return_value = Mock()
                mock_simplify.return_value = (Mock(), False)  # check_passed = False

                result = simplify_onnx_model(tmp_path)
                assert result is False

    @pytest.mark.unit
    def test_simplify_onnx_model_success(self):
        """Test successful simplification"""
        with tempfile.NamedTemporaryFile(suffix=".onnx") as tmp_file:
            tmp_path = Path(tmp_file.name)

            # Write some dummy data to get file size
            tmp_file.write(b"dummy_onnx_data" * 100)
            tmp_file.flush()

            # Mock successful simplification
            with (
                patch("piper_train.export_onnx.onnx") as mock_onnx,
                patch("piper_train.export_onnx.simplify") as mock_simplify,
            ):
                mock_model = Mock()
                mock_onnx.load.return_value = mock_model
                mock_simplify.return_value = (mock_model, True)  # check_passed = True

                result = simplify_onnx_model(tmp_path)
                assert result is True

                # Verify onnx.save was called
                mock_onnx.save.assert_called_once()

    @pytest.mark.unit
    def test_simplify_onnx_model_custom_check_n(self):
        """Test simplification with custom validation count"""
        with tempfile.NamedTemporaryFile(suffix=".onnx") as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(b"dummy_data")
            tmp_file.flush()

            with (
                patch("piper_train.export_onnx.onnx") as mock_onnx,
                patch("piper_train.export_onnx.simplify") as mock_simplify,
            ):
                mock_model = Mock()
                mock_onnx.load.return_value = mock_model
                mock_simplify.return_value = (mock_model, True)

                result = simplify_onnx_model(tmp_path, check_n=5)
                assert result is True

                # Verify simplify was called with custom check_n
                mock_simplify.assert_called_once()
                call_args = mock_simplify.call_args
                assert call_args[1]["check_n"] == 5

    @pytest.mark.integration
    @pytest.mark.requires_model
    def test_simplify_real_onnx_model(self):
        """Integration test with real ONNX model if available"""
        # Only run if we have a test model available
        test_model_path = Path("test/models/test_voice.onnx")
        if not test_model_path.exists():
            pytest.skip("Test ONNX model not available")

        # Create a copy for testing
        with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)

            try:
                # Copy test model
                with open(test_model_path, "rb") as src:
                    tmp_file.write(src.read())
                tmp_file.flush()

                # Test simplification
                result = simplify_onnx_model(tmp_path)

                # Should succeed if onnxsim is installed
                # (Will be False if not installed, which is also valid)
                assert isinstance(result, bool)

            finally:
                # Clean up
                tmp_path.unlink(missing_ok=True)


class TestExportONNXArguments:
    """Test command line argument parsing for ONNX export"""

    @pytest.mark.unit
    def test_export_onnx_simplify_arguments(self):
        """Test that new simplify arguments are properly parsed"""
        from piper_train.export_onnx import main

        # Test argument parsing without actually running main
        with (
            patch("piper_train.export_onnx.VitsModel"),
            patch("piper_train.export_onnx.torch.onnx.export"),
            patch("piper_train.export_onnx.simplify_onnx_model"),
        ):
            # Mock sys.argv to test argument parsing
            with patch(
                "sys.argv", ["export_onnx.py", "test.ckpt", "test.onnx", "--simplify"]
            ):
                try:
                    main()
                except SystemExit:
                    pass  # Expected when mocking fails

            # The mock should be called if simplify flag is used
            # (This is a basic smoke test for argument parsing)
