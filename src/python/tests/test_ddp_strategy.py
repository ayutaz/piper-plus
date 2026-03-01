"""Tests for DDP strategy configuration.

Verifies that static_graph is never set (GAN training has unused params each step),
and that find_unused_parameters + gradient_as_bucket_view are always configured.
"""

import pytest


def _import_ddp_deps():
    """Import DDP test dependencies, skipping if training stack unavailable."""
    pytest.importorskip("pytorch_lightning")
    try:
        from pytorch_lightning.strategies import DDPStrategy

        from piper_train.__main__ import configure_ddp_strategy
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")
    return DDPStrategy, configure_ddp_strategy


@pytest.mark.unit
def test_ddp_strategy_with_no_wavlm_has_no_static_graph():
    """GAN training has unused params each step; static_graph must NOT be set."""
    DDPStrategy, configure_ddp_strategy = _import_ddp_deps()

    strategy = configure_ddp_strategy(num_gpus=4, no_wavlm=True)

    assert isinstance(strategy, DDPStrategy)
    assert "static_graph" not in strategy._ddp_kwargs


@pytest.mark.unit
def test_ddp_strategy_single_gpu_returns_none():
    """Single GPU should return None (no DDP strategy needed)."""
    _, configure_ddp_strategy = _import_ddp_deps()

    strategy = configure_ddp_strategy(num_gpus=1, no_wavlm=True)
    assert strategy is None

    strategy = configure_ddp_strategy(num_gpus=1, no_wavlm=False)
    assert strategy is None


@pytest.mark.unit
def test_ddp_strategy_user_override():
    """User-specified strategy should take precedence."""
    _, configure_ddp_strategy = _import_ddp_deps()

    strategy = configure_ddp_strategy(num_gpus=4, user_strategy="ddp", no_wavlm=True)
    assert strategy == "ddp"


@pytest.mark.unit
def test_ddp_strategy_always_has_find_unused_and_bucket_view():
    """DDP strategy should always have find_unused_parameters=True and gradient_as_bucket_view=True."""
    DDPStrategy, configure_ddp_strategy = _import_ddp_deps()

    for no_wavlm in (True, False):
        strategy = configure_ddp_strategy(num_gpus=2, no_wavlm=no_wavlm)
        assert isinstance(strategy, DDPStrategy)
        assert strategy._ddp_kwargs.get("find_unused_parameters") is True
        assert strategy._ddp_kwargs.get("gradient_as_bucket_view") is True
