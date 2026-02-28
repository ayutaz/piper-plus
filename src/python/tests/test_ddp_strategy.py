"""Tests for DDP strategy configuration.

Verifies that static_graph is never set (GAN training has unused params each step),
and that find_unused_parameters + gradient_as_bucket_view are always configured.
"""

import pytest


@pytest.mark.unit
def test_ddp_strategy_with_no_wavlm_has_no_static_graph():
    """GAN training has unused params each step; static_graph must NOT be set."""
    pytest.importorskip("pytorch_lightning")
    from pytorch_lightning.strategies import DDPStrategy

    from piper_train.__main__ import configure_ddp_strategy

    strategy = configure_ddp_strategy(num_gpus=4, no_wavlm=True)

    assert isinstance(strategy, DDPStrategy)
    assert "static_graph" not in strategy._ddp_kwargs


@pytest.mark.unit
def test_ddp_strategy_single_gpu_returns_none():
    """Single GPU should return None (no DDP strategy needed)."""
    pytest.importorskip("pytorch_lightning")
    from piper_train.__main__ import configure_ddp_strategy

    strategy = configure_ddp_strategy(num_gpus=1, no_wavlm=True)
    assert strategy is None

    strategy = configure_ddp_strategy(num_gpus=1, no_wavlm=False)
    assert strategy is None


@pytest.mark.unit
def test_ddp_strategy_user_override():
    """User-specified strategy should take precedence."""
    pytest.importorskip("pytorch_lightning")
    from piper_train.__main__ import configure_ddp_strategy

    strategy = configure_ddp_strategy(num_gpus=4, user_strategy="ddp", no_wavlm=True)
    assert strategy == "ddp"


@pytest.mark.unit
def test_ddp_strategy_always_has_find_unused_and_bucket_view():
    """DDP strategy should always have find_unused_parameters=True and gradient_as_bucket_view=True."""
    pytest.importorskip("pytorch_lightning")
    from pytorch_lightning.strategies import DDPStrategy

    from piper_train.__main__ import configure_ddp_strategy

    for no_wavlm in (True, False):
        strategy = configure_ddp_strategy(num_gpus=2, no_wavlm=no_wavlm)
        assert isinstance(strategy, DDPStrategy)
        assert strategy._ddp_kwargs.get("find_unused_parameters") is True
        assert strategy._ddp_kwargs.get("gradient_as_bucket_view") is True
