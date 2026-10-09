"""Inference contexts shared by monitoring and offline audio generation.

This module generates audio only. Evaluation scores stay in offline tools.
"""

import random
from contextlib import contextmanager

import numpy as np
import torch


@contextmanager
def isolated_inference(module: torch.nn.Module, seed: int | None = None):
    """Temporarily use eval/no_grad, restoring mixed modes and every used RNG."""
    modes = [(child, child.training) for child in module.modules()]
    numpy_state = np.random.get_state()
    python_state = random.getstate()
    devices = sorted(
        {
            tensor.device.index
            for tensor in (*module.parameters(), *module.buffers())
            if tensor.device.type == "cuda"
        }
    )
    try:
        with torch.random.fork_rng(devices=devices), torch.no_grad():
            if seed is not None:
                torch.random.default_generator.manual_seed(seed)
                for device in devices:
                    with torch.cuda.device(device):
                        torch.cuda.manual_seed(seed)
                np.random.seed(seed % (2**32))
                random.seed(seed)
            module.eval()
            yield
    finally:
        # Calling .train() on parents would overwrite deliberately mixed modes.
        for child, training in modes:
            child.training = training
        np.random.set_state(numpy_state)
        random.setstate(python_state)
