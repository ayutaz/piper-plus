#!/usr/bin/env python3
"""Tests for training manager functionality"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest


# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from piper.training_manager import TrainingManager, TrainingStatus


class TestTrainingStatus:
    """Test TrainingStatus dataclass"""

    def test_initialization(self):
        """Test TrainingStatus initialization"""
        status = TrainingStatus()
        assert not status.is_running
        assert status.current_epoch == 0
        assert status.total_epochs == 0
        assert status.current_loss == 0.0
        assert status.best_loss == float("inf")
        assert status.start_time is None
        assert status.last_update is None
        assert status.error is None
        assert status.log_messages == []

    def test_to_dict(self):
        """Test conversion to dictionary"""
        from datetime import datetime

        status = TrainingStatus(
            is_running=True,
            current_epoch=5,
            total_epochs=10,
            current_loss=0.5,
            best_loss=0.3,
            start_time=datetime.now(),
            last_update=datetime.now(),
            error=None,
            log_messages=["test1", "test2"],
        )

        result = status.to_dict()
        assert result["is_running"] is True
        assert result["current_epoch"] == 5
        assert result["total_epochs"] == 10
        assert result["current_loss"] == 0.5
        assert result["best_loss"] == 0.3
        assert result["start_time"] is not None
        assert result["last_update"] is not None
        assert result["error"] is None
        assert result["log_messages"] == ["test1", "test2"]


class TestTrainingManager:
    """Test TrainingManager functionality"""

    @pytest.fixture
    def manager(self):
        """Create a TrainingManager instance"""
        return TrainingManager()

    @pytest.fixture
    def test_dataset(self, tmp_path):
        """Create a test dataset"""
        dataset_dir = tmp_path / "test_dataset"
        dataset_dir.mkdir()

        # Create metadata.csv
        metadata_file = dataset_dir / "metadata.csv"
        metadata_file.write_text(
            "speaker|audio_001|Hello world\nspeaker|audio_002|Test"
        )

        # Create wavs directory
        wavs_dir = dataset_dir / "wavs"
        wavs_dir.mkdir()

        return dataset_dir

    def test_initialization(self, manager):
        """Test TrainingManager initialization"""
        assert manager.process is None
        assert isinstance(manager.status, TrainingStatus)
        assert not manager.status.is_running
        assert manager.callbacks == {}

    def test_is_running_when_not_started(self, manager):
        """Test is_running returns False when not started"""
        assert not manager.is_running()

    def test_stop_training_when_not_running(self, manager):
        """Test stopping when no training is running"""
        assert not manager.stop_training()

    def test_register_callback(self, manager):
        """Test callback registration"""
        callback = Mock()
        manager.register_callback("test", callback)
        assert "test" in manager.callbacks
        assert manager.callbacks["test"] == callback

    @patch("subprocess.Popen")
    def test_start_training_success(self, mock_popen, manager, test_dataset, tmp_path):
        """Test successful training start"""
        # Mock the process
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_process.stdout.readline.return_value = ""
        mock_popen.return_value = mock_process

        output_dir = tmp_path / "output"

        success = manager.start_training(
            dataset_path=str(test_dataset),
            output_dir=str(output_dir),
            quality="x-low",
            batch_size=1,
            learning_rate=1e-4,
            num_epochs=2,
            checkpoint_interval=1,
            validation_split=0.1,
        )

        assert success
        assert manager.status.is_running
        assert manager.status.total_epochs == 2
        assert manager.status.start_time is not None
        assert output_dir.exists()

        # Check command construction
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert "-m" in cmd
        assert "piper_train" in cmd
        assert "--dataset-dir" in cmd
        assert str(test_dataset) in cmd

    def test_start_training_invalid_dataset(self, manager, tmp_path):
        """Test starting training with invalid dataset path"""
        success = manager.start_training(
            dataset_path="/non/existent/path",
            output_dir=str(tmp_path / "output"),
            quality="medium",
            batch_size=16,
            learning_rate=1e-4,
            num_epochs=100,
            checkpoint_interval=10,
            validation_split=0.1,
        )

        # Should still return True as path validation is done elsewhere
        assert success

    def test_start_training_while_running(self, manager, test_dataset, tmp_path):
        """Test starting training while already running"""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_process.stdout.readline.return_value = ""
            mock_popen.return_value = mock_process

            # Start first training
            manager.start_training(
                dataset_path=str(test_dataset),
                output_dir=str(tmp_path / "output1"),
                quality="x-low",
                batch_size=1,
                learning_rate=1e-4,
                num_epochs=1,
                checkpoint_interval=1,
                validation_split=0.1,
            )

            # Try to start second training
            success = manager.start_training(
                dataset_path=str(test_dataset),
                output_dir=str(tmp_path / "output2"),
                quality="x-low",
                batch_size=1,
                learning_rate=1e-4,
                num_epochs=1,
                checkpoint_interval=1,
                validation_split=0.1,
            )

            assert not success

    def test_parse_output_epoch_info(self, manager):
        """Test parsing epoch information from output"""
        manager._parse_output("Epoch 5/100")
        assert manager.status.current_epoch == 5
        assert manager.status.total_epochs == 100

    def test_parse_output_loss_info(self, manager):
        """Test parsing loss information from output"""
        manager._parse_output("train_loss: 0.1234, val_loss: 0.2345")
        assert manager.status.current_loss == 0.1234
        assert manager.status.best_loss == 0.1234

        # Test lower loss updates best
        manager._parse_output("train_loss: 0.1000")
        assert manager.status.current_loss == 0.1000
        assert manager.status.best_loss == 0.1000

        # Test higher loss doesn't update best
        manager._parse_output("train_loss: 0.2000")
        assert manager.status.current_loss == 0.2000
        assert manager.status.best_loss == 0.1000

    def test_add_log(self, manager):
        """Test adding log messages"""
        manager._add_log("Test message 1")
        manager._add_log("Test message 2")

        assert len(manager.status.log_messages) == 2
        assert "Test message 1" in manager.status.log_messages[0]
        assert "Test message 2" in manager.status.log_messages[1]

        # Check timestamp is added
        assert "[" in manager.status.log_messages[0]
        assert "]" in manager.status.log_messages[0]

    def test_get_logs(self, manager):
        """Test getting recent logs"""
        # Add many logs
        for i in range(150):
            manager._add_log(f"Log message {i}")

        # Get last 10
        recent = manager.get_logs(last_n=10)
        assert len(recent) == 10
        assert "Log message 149" in recent[-1]
        assert "Log message 140" in recent[0]

    def test_trigger_callbacks(self, manager):
        """Test callback triggering"""
        callback1 = Mock()
        callback2 = Mock()

        manager.register_callback("cb1", callback1)
        manager.register_callback("cb2", callback2)

        manager._trigger_callbacks()

        callback1.assert_called_once_with(manager.status)
        callback2.assert_called_once_with(manager.status)

    def test_trigger_callbacks_with_error(self, manager):
        """Test callback error handling"""
        good_callback = Mock()
        bad_callback = Mock(side_effect=Exception("Callback error"))

        manager.register_callback("good", good_callback)
        manager.register_callback("bad", bad_callback)

        # Should not raise exception
        manager._trigger_callbacks()

        good_callback.assert_called_once()
        bad_callback.assert_called_once()

    @patch("subprocess.Popen")
    def test_monitor_process_success(self, mock_popen, manager, test_dataset, tmp_path):
        """Test monitoring a successful process"""
        # Mock process that outputs some lines then exits successfully
        mock_process = MagicMock()
        mock_process.poll.side_effect = [None, None, 0]  # Running, running, then done
        mock_process.returncode = 0
        mock_process.stdout.readline.side_effect = [
            "Starting training...\n",
            "Epoch 1/10\n",
            "train_loss: 0.5\n",
            "",  # Empty line signals end
        ]
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process

        manager.start_training(
            dataset_path=str(test_dataset),
            output_dir=str(tmp_path / "output"),
            quality="x-low",
            batch_size=1,
            learning_rate=1e-4,
            num_epochs=10,
            checkpoint_interval=1,
            validation_split=0.1,
        )

        # Wait for monitoring to process
        time.sleep(0.1)

        # Check logs were added
        logs = manager.get_logs()
        assert any("Starting training" in log for log in logs)
        assert any("Epoch 1/10" in log for log in logs)

    @patch("subprocess.Popen")
    def test_stop_training_success(self, mock_popen, manager, test_dataset, tmp_path):
        """Test stopping training successfully"""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Running
        mock_process.stdout.readline.return_value = ""
        mock_popen.return_value = mock_process

        # Start training
        manager.start_training(
            dataset_path=str(test_dataset),
            output_dir=str(tmp_path / "output"),
            quality="x-low",
            batch_size=1,
            learning_rate=1e-4,
            num_epochs=1,
            checkpoint_interval=1,
            validation_split=0.1,
        )

        # Stop training
        success = manager.stop_training()
        assert success

        # Check process was terminated
        mock_process.terminate.assert_called_once()


class TestTrainingWebUIIntegration:
    """Test WebUI integration with training"""

    def test_check_training_dependencies(self):
        """Test dependency checking function"""
        from piper.webui import check_training_dependencies

        # Test with mocked imports
        with patch.dict(sys.modules, {"pytorch_lightning": None, "torch": None}):
            deps = check_training_dependencies()
            assert "pytorch-lightning" in deps
            assert "torch" in deps

    def test_start_training_webui_invalid_dataset(self):
        """Test WebUI start_training with invalid dataset"""
        from piper.webui import start_training

        result = start_training(
            dataset_path="/non/existent/path",
            base_model="New Model",
            num_speakers=1,
            quality="medium",
            batch_size=16,
            learning_rate=1e-4,
            num_epochs=100,
            checkpoint_interval=10,
            validation_split=0.1,
            output_dir="output",
        )

        assert "❌" in result
        assert "does not exist" in result

    def test_get_training_status(self):
        """Test getting training status for WebUI"""
        from datetime import datetime

        from piper.webui import get_training_status, training_manager

        # Set up a mock status
        training_manager.status = TrainingStatus(
            is_running=True,
            current_epoch=5,
            total_epochs=10,
            current_loss=0.5,
            start_time=datetime.now(),
            last_update=datetime.now(),
            log_messages=["Log 1", "Log 2", "Log 3"],
        )

        status_dict = get_training_status()

        assert status_dict["is_running"] is True
        assert status_dict["progress"] == 0.5  # 5/10
        assert "Epoch 5/10" in status_dict["status_text"]
        assert "Loss: 0.5000" in status_dict["status_text"]
        assert "Log 3" in status_dict["logs"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
