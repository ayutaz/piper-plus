#!/usr/bin/env python3
"""Integration tests for training functionality"""

import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.integration
class TestTrainingIntegration:
    """Integration tests for training functionality"""

    @pytest.fixture
    def create_test_dataset(self, tmp_path):
        """Create a minimal test dataset"""
        dataset_dir = tmp_path / "test_dataset"
        dataset_dir.mkdir()

        # Create metadata.csv
        metadata_file = dataset_dir / "metadata.csv"
        with open(metadata_file, "w") as f:
            f.write("speaker|audio_001|Hello world, this is a test.\n")
            f.write("speaker|audio_002|Another test sentence here.\n")
            f.write("speaker|audio_003|Testing the training system.\n")

        # Create wavs directory
        wavs_dir = dataset_dir / "wavs"
        wavs_dir.mkdir()

        # Create dummy audio files (just empty files for testing)
        for i in range(1, 4):
            audio_file = wavs_dir / f"audio_{i:03d}.wav"
            audio_file.touch()

        return dataset_dir

    def test_training_manager_lifecycle(self, create_test_dataset, tmp_path):
        """Test complete training lifecycle"""
        from piper.training_manager import TrainingManager

        manager = TrainingManager()
        output_dir = tmp_path / "output"

        # Register a callback to track status updates
        status_updates = []
        manager.register_callback(
            "test", lambda status: status_updates.append(status.to_dict())
        )

        # Mock subprocess to simulate training
        with patch("subprocess.Popen") as mock_popen:
            # Create mock process
            mock_process = Mock()
            mock_process.poll.side_effect = [
                None,
                None,
                None,
                0,
            ]  # Running 3 times, then done
            mock_process.returncode = 0
            mock_process.stdout.readline.side_effect = [
                "Initializing training...\n",
                "Epoch 1/3\n",
                "train_loss: 1.5, val_loss: 1.6\n",
                "Epoch 2/3\n",
                "train_loss: 0.8, val_loss: 0.9\n",
                "Epoch 3/3\n",
                "train_loss: 0.3, val_loss: 0.4\n",
                "Training completed!\n",
                "",  # End of output
            ]
            mock_process.wait.return_value = None
            mock_popen.return_value = mock_process

            # Start training
            success = manager.start_training(
                dataset_path=str(create_test_dataset),
                output_dir=str(output_dir),
                quality="x-low",
                batch_size=2,
                learning_rate=1e-4,
                num_epochs=3,
                checkpoint_interval=1,
                validation_split=0.3,
            )

            assert success
            assert manager.is_running()

            # Wait for process to complete
            time.sleep(0.5)

            # Check final status
            final_status = manager.get_status()
            assert not final_status.is_running
            assert final_status.error is None
            assert final_status.best_loss == 0.3

            # Check logs
            logs = manager.get_logs()
            assert any("Training completed!" in log for log in logs)
            assert any("Epoch 3/3" in log for log in logs)

            # Check callbacks were triggered
            assert len(status_updates) > 0

    def test_training_error_handling(self, create_test_dataset, tmp_path):
        """Test handling of training errors"""
        from piper.training_manager import TrainingManager

        manager = TrainingManager()

        with patch("subprocess.Popen") as mock_popen:
            # Simulate process that fails immediately
            mock_process = Mock()
            mock_process.poll.return_value = 1  # Non-zero exit code
            mock_process.returncode = 1
            mock_process.stdout.readline.side_effect = [
                "Error: Missing required module\n",
                "",
            ]
            mock_process.wait.return_value = None
            mock_popen.return_value = mock_process

            success = manager.start_training(
                dataset_path=str(create_test_dataset),
                output_dir=str(tmp_path / "output"),
                quality="medium",
                batch_size=16,
                learning_rate=1e-4,
                num_epochs=100,
                checkpoint_interval=10,
                validation_split=0.1,
            )

            assert success  # Start succeeds even if process fails later

            # Wait for monitoring to detect failure
            time.sleep(0.2)

            status = manager.get_status()
            assert not status.is_running
            assert "exit code" in (status.error or "")

    def test_webui_training_flow(self, create_test_dataset, tmp_path):
        """Test complete WebUI training flow"""
        from piper.webui import (
            get_training_status,
            start_training,
            stop_training,
            training_manager,
        )

        # Reset training manager
        training_manager.process = None
        training_manager.status.is_running = False

        # Check dependencies (mocked)
        with patch("piper.webui.check_training_dependencies") as mock_check:
            mock_check.return_value = []  # No missing dependencies

            with patch("piper.training_manager.subprocess.Popen") as mock_popen:
                # Mock successful process
                mock_process = Mock()
                mock_process.poll.return_value = None
                mock_process.stdout.readline.return_value = ""
                mock_popen.return_value = mock_process

                # Start training via WebUI
                result = start_training(
                    dataset_path=str(create_test_dataset),
                    base_model="New Model",
                    num_speakers=1,
                    quality="x-low",
                    batch_size=1,
                    learning_rate=1e-4,
                    num_epochs=5,
                    checkpoint_interval=1,
                    validation_split=0.1,
                    output_dir=str(tmp_path / "output"),
                )

                assert "✅" in result
                assert "successfully" in result

                # Get status
                status = get_training_status()
                assert status["is_running"]

                # Stop training
                stop_result = stop_training()
                assert "✅" in stop_result

                # Verify process was terminated
                mock_process.terminate.assert_called()

    def test_concurrent_training_prevention(self, create_test_dataset, tmp_path):
        """Test that concurrent training is prevented"""
        from piper.webui import start_training

        with patch("piper.training_manager.subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.poll.return_value = None  # Process is running
            mock_process.stdout.readline.return_value = ""
            mock_popen.return_value = mock_process

            # Mock dependencies check
            with patch("piper.webui.check_training_dependencies") as mock_check:
                mock_check.return_value = []

                # Start first training
                result1 = start_training(
                    dataset_path=str(create_test_dataset),
                    base_model="New Model",
                    num_speakers=1,
                    quality="x-low",
                    batch_size=1,
                    learning_rate=1e-4,
                    num_epochs=1,
                    checkpoint_interval=1,
                    validation_split=0.1,
                    output_dir=str(tmp_path / "output1"),
                )

                assert "✅" in result1

                # Try to start second training
                result2 = start_training(
                    dataset_path=str(create_test_dataset),
                    base_model="New Model",
                    num_speakers=1,
                    quality="x-low",
                    batch_size=1,
                    learning_rate=1e-4,
                    num_epochs=1,
                    checkpoint_interval=1,
                    validation_split=0.1,
                    output_dir=str(tmp_path / "output2"),
                )

                assert "⚠️" in result2
                assert "already running" in result2

    @pytest.mark.skipif(
        not Path(
            "/Users/s19447/Desktop/total-piper/piper/src/python/piper_train"
        ).exists(),
        reason="piper_train not available",
    )
    def test_real_piper_train_invocation(self, create_test_dataset, tmp_path):
        """Test with real piper_train (if available)"""
        from piper.training_manager import TrainingManager

        manager = TrainingManager()

        # Start training with minimal settings
        success = manager.start_training(
            dataset_path=str(create_test_dataset),
            output_dir=str(tmp_path / "output"),
            quality="x-low",
            batch_size=1,
            learning_rate=1e-4,
            num_epochs=1,
            checkpoint_interval=1,
            validation_split=0.5,
            accelerator="cpu",  # Force CPU for testing
            devices=1,
        )

        assert success

        # Let it run for a bit
        time.sleep(2)

        # Stop it
        manager.stop_training()

        # Check that some output was generated
        logs = manager.get_logs()
        assert len(logs) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
