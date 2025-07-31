#!/usr/bin/env python3
"""Training process manager for WebUI"""

import logging
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)


@dataclass
class TrainingStatus:
    """Training process status"""

    is_running: bool = False
    current_epoch: int = 0
    total_epochs: int = 0
    current_loss: float = 0.0
    best_loss: float = float("inf")
    start_time: datetime | None = None
    last_update: datetime | None = None
    error: str | None = None
    log_messages: list[str] = None

    def __post_init__(self):
        if self.log_messages is None:
            self.log_messages = []

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "is_running": self.is_running,
            "current_epoch": self.current_epoch,
            "total_epochs": self.total_epochs,
            "current_loss": self.current_loss,
            "best_loss": self.best_loss,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "error": self.error,
            "log_messages": self.log_messages[-100:],  # Keep last 100 messages
        }


class TrainingManager:
    """Manages training processes for WebUI"""

    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.status = TrainingStatus()
        self.log_queue = queue.Queue()
        self.callbacks: dict[str, Callable] = {}
        self._stop_event = threading.Event()
        self._monitor_thread: threading.Thread | None = None

    def start_training(
        self,
        dataset_path: str,
        output_dir: str,
        base_model: str | None = None,
        num_speakers: int = 1,
        quality: str = "medium",
        batch_size: int = 16,
        learning_rate: float = 1e-4,
        num_epochs: int = 100,
        checkpoint_interval: int = 10,
        validation_split: float = 0.1,
        num_workers: int | None = None,
        accelerator: str = "auto",
        devices: int = 1,
    ) -> bool:
        """Start training process"""
        if self.is_running():
            logger.warning("Training is already running")
            return False

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Find the correct Python path for piper_train
        piper_python_path = Path(__file__).parent.parent.parent / "python"

        # Build command
        cmd = [
            sys.executable,
            "-m",
            "piper_train",
            "--dataset-dir",
            dataset_path,
            "--quality",
            quality,
            "--batch-size",
            str(batch_size),
            "--learning-rate",
            str(learning_rate),
            "--epochs",
            str(num_epochs),
            "--validation-split",
            str(validation_split),
            "--checkpoint-epochs",
            str(checkpoint_interval),
            "--accelerator",
            accelerator,
            "--devices",
            str(devices),
        ]

        # Add environment variables to find piper_train
        env = os.environ.copy()
        if piper_python_path.exists():
            env["PYTHONPATH"] = str(piper_python_path) + ":" + env.get("PYTHONPATH", "")

        if num_workers is not None:
            cmd.extend(["--num-workers", str(num_workers)])

        if base_model and base_model != "New Model":
            cmd.extend(["--checkpoint-path", base_model])

        if num_speakers > 1:
            cmd.extend(["--num-speakers", str(num_speakers)])

        # Reset status
        self.status = TrainingStatus(
            is_running=True, total_epochs=num_epochs, start_time=datetime.now()
        )
        self._stop_event.clear()

        try:
            # Start process
            logger.info(f"Starting training with command: {' '.join(cmd)}")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=env,
                cwd=piper_python_path if piper_python_path.exists() else None,
            )

            # Start monitoring thread
            self._monitor_thread = threading.Thread(target=self._monitor_process)
            self._monitor_thread.start()

            # Add initial log message
            self._add_log(f"Training started at {self.status.start_time}")
            self._add_log(f"Dataset: {dataset_path}")
            self._add_log(f"Output: {output_dir}")
            self._add_log(f"Quality: {quality}, Batch size: {batch_size}")
            self._add_log(f"Epochs: {num_epochs}, LR: {learning_rate}")

            return True

        except Exception as e:
            logger.error(f"Failed to start training: {e}")
            self.status.is_running = False
            self.status.error = str(e)
            return False

    def stop_training(self) -> bool:
        """Stop training process"""
        if not self.is_running():
            return False

        logger.info("Stopping training process...")
        self._stop_event.set()

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Process didn't terminate, forcing kill")
                self.process.kill()
                self.process.wait()

        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

        self.status.is_running = False
        self._add_log("Training stopped by user")
        return True

    def is_running(self) -> bool:
        """Check if training is running"""
        return (
            self.status.is_running
            and self.process is not None
            and self.process.poll() is None
        )

    def get_status(self) -> TrainingStatus:
        """Get current training status"""
        return self.status

    def get_logs(self, last_n: int = 100) -> list[str]:
        """Get recent log messages"""
        return self.status.log_messages[-last_n:]

    def register_callback(self, name: str, callback: Callable):
        """Register a callback for status updates"""
        self.callbacks[name] = callback

    def _monitor_process(self):
        """Monitor training process output"""
        if not self.process:
            return

        try:
            for line in iter(self.process.stdout.readline, ""):
                if self._stop_event.is_set():
                    break

                if line:
                    line = line.strip()
                    self._add_log(line)
                    self._parse_output(line)

            # Process finished
            self.process.wait()
            exit_code = self.process.returncode

            if exit_code == 0:
                self._add_log("Training completed successfully!")
            else:
                self._add_log(f"Training failed with exit code: {exit_code}")
                self.status.error = f"Process exited with code {exit_code}"

        except Exception as e:
            logger.error(f"Error monitoring process: {e}")
            self.status.error = str(e)

        finally:
            self.status.is_running = False
            self._trigger_callbacks()

    def _parse_output(self, line: str):
        """Parse training output for progress information"""
        try:
            # Parse epoch information
            if "Epoch" in line and "/" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "Epoch" and i + 1 < len(parts):
                        epoch_info = parts[i + 1]
                        if "/" in epoch_info:
                            current, total = epoch_info.split("/")
                            self.status.current_epoch = int(current)
                            self.status.total_epochs = int(total)

            # Parse loss information
            if "loss:" in line.lower():
                parts = line.split()
                for i, part in enumerate(parts):
                    if "loss:" in part.lower() and i + 1 < len(parts):
                        try:
                            loss_value = float(parts[i + 1].rstrip(","))
                            self.status.current_loss = loss_value
                            self.status.best_loss = min(
                                self.status.best_loss, loss_value
                            )
                        except ValueError:
                            pass

            self.status.last_update = datetime.now()
            self._trigger_callbacks()

        except Exception as e:
            logger.debug(f"Error parsing output line '{line}': {e}")

    def _add_log(self, message: str):
        """Add log message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.status.log_messages.append(log_entry)
        self.log_queue.put(log_entry)
        logger.info(message)

    def _trigger_callbacks(self):
        """Trigger registered callbacks"""
        for callback in self.callbacks.values():
            try:
                callback(self.status)
            except Exception as e:
                logger.error(f"Error in callback: {e}")


# Global training manager instance
training_manager = TrainingManager()
