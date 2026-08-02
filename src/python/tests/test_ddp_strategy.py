"""Tests for DDP strategy configuration.

Verifies that find_unused_parameters=True and gradient_as_bucket_view=True
are always configured for multi-GPU runs, and that static_graph is NOT set.

static_graph=True (Plan A) は 4x A100 DDP の v8 smoke (2026-08-02) で
iteration 2 に「unused parameters ...」RuntimeError を起こすことが実測で
確定し撤回された。VITS の GAN 交互最適化は G step / D step で unused-param
集合が交互に変わるため、static graph の「毎 iteration 同一」前提を
満たさない。
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
def test_ddp_strategy_does_not_set_static_graph():
    """static_graph は設定しない (GAN 交互最適化と非互換、2026-08-02 実測)。

    G step / D step で unused set が交互に変わるため、static_graph=True は
    4x DDP 実走の iteration 2 で RuntimeError になる。再導入する場合は
    必ず multi-GPU 実走 smoke で検証すること。
    """
    DDPStrategy, configure_ddp_strategy = _import_ddp_deps()

    for no_wavlm in (True, False):
        strategy = configure_ddp_strategy(num_gpus=4, no_wavlm=no_wavlm)
        assert isinstance(strategy, DDPStrategy)
        assert not strategy._ddp_kwargs.get("static_graph"), (
            "static_graph must not be enabled: incompatible with GAN "
            "alternating optimization (proven on 4x A100 DDP, 2026-08-02)"
        )


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


@pytest.mark.unit
def test_train_dataloader_has_shuffle():
    """非balanced パスの DataLoader に shuffle=True が設定されている.

    Regression test: VitsModel.train_dataloader() の non-balanced (single-speaker
    or samples_per_speaker=0) コードパスで DataLoader に shuffle=True が渡されて
    いること。shuffle=False だとエポックごとに同一順序で学習してしまい、
    過学習や学習品質劣化の原因になる。
    """
    torch = pytest.importorskip("torch")
    pytest.importorskip("pytorch_lightning")

    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    # single-speaker, samples_per_speaker=0 -> non-balanced path
    model = VitsModel(
        num_symbols=97,
        num_speakers=1,
        num_languages=1,
        dataset=None,
        batch_size=4,
        learning_rate=2e-4,
        use_wavlm_discriminator=False,
    )

    # Inject a minimal fake train dataset so train_dataloader() can run
    from torch.utils.data import TensorDataset

    fake_dataset = TensorDataset(torch.zeros(10))
    model._train_dataset = fake_dataset
    model.hparams["samples_per_speaker"] = 0

    loader = model.train_dataloader()

    # DataLoader stores the shuffle sampler internally. When shuffle=True and
    # no custom sampler is given, PyTorch wraps it in a RandomSampler.
    from torch.utils.data import RandomSampler

    assert isinstance(loader.sampler, RandomSampler), (
        f"Non-balanced DataLoader must use RandomSampler (shuffle=True), "
        f"got {type(loader.sampler).__name__}"
    )
