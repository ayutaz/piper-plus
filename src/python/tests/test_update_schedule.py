"""G/D/WavLM update periods count batches, not optimizer steps.

Under manual optimization Lightning advances ``global_step`` once per
optimizer step, i.e. twice per batch when both G and D step. Periods derived
from ``global_step`` therefore did not mean "every N batches":
``--d-update-interval 2`` still updated G on every batch, and with
``--wavlm-every-n-steps 2`` the D-side WavLM check (taken after the G step, at
an odd ``global_step``) never fired.
"""

from types import SimpleNamespace
from unittest import mock

import pytest

torch = pytest.importorskip("torch")
pl = pytest.importorskip("pytorch_lightning")

from piper_train.vits.lightning import VitsModel, _schedule_batch_index  # noqa: E402

pytestmark = pytest.mark.unit


class _CountingOpt:
    """Optimizer stand-in that advances the fake ``global_step`` like Lightning."""

    def __init__(self, owner):
        self.owner = owner
        self.step_calls = 0

    def zero_grad(self, set_to_none: bool = False):
        pass

    def step(self):
        self.step_calls += 1
        self.owner.global_step += 1


def _fake_model(d_update_interval: int):
    fake = mock.MagicMock()
    fake.hparams = SimpleNamespace(d_update_interval=d_update_interval, grad_clip=None)
    fake.global_step = 0
    opt_g, opt_d = _CountingOpt(fake), _CountingOpt(fake)
    fake.optimizers = mock.MagicMock(return_value=(opt_g, opt_d))
    fake._ddp_synced_is_finite = VitsModel._ddp_synced_is_finite

    def step_g(batch):
        fake._y = torch.zeros(1, 1, 8)
        fake._y_hat = torch.zeros(1, 1, 8)
        return torch.tensor(1.0)

    fake.training_step_g = step_g
    fake.training_step_d = lambda batch: torch.tensor(0.5)
    batch = SimpleNamespace(
        phoneme_ids=torch.zeros(2, 4, dtype=torch.long),
        phoneme_lengths=torch.tensor([4, 4]),
        audio_lengths=torch.tensor([100, 100]),
        spectrogram_lengths=torch.tensor([20, 20]),
    )
    return fake, opt_g, opt_d, batch


@pytest.mark.parametrize(("interval", "g_steps"), [(1, 6), (2, 3), (3, 2)])
def test_generator_updates_every_d_update_interval_batches(interval, g_steps):
    fake, opt_g, opt_d, batch = _fake_model(interval)
    for batch_idx in range(6):
        VitsModel.training_step(fake, batch, batch_idx=batch_idx)
    assert opt_g.step_calls == g_steps
    assert opt_d.step_calls == 6


def _wavlm_host(d: int, w: int, idx: int, training: bool = True):
    return SimpleNamespace(
        hparams=SimpleNamespace(d_update_interval=d, wavlm_every_n_steps=w),
        training=training,
        _schedule_batch_idx=idx,
    )


def _due(d: int, w: int, generator: bool, batches: int = 12) -> list[int]:
    return [
        i
        for i in range(batches)
        if VitsModel._wavlm_due(_wavlm_host(d, w, i), generator=generator)
    ]


def test_wavlm_discriminator_runs_every_w_batches():
    # D updates on every batch, so its WavLM term runs every w batches.
    assert _due(1, 2, generator=False) == [0, 2, 4, 6, 8, 10]
    assert _due(2, 3, generator=False) == [0, 3, 6, 9]


def test_wavlm_generator_term_only_on_generator_update_batches():
    assert _due(1, 2, generator=True) == [0, 2, 4, 6, 8, 10]
    assert _due(2, 2, generator=True) == [0, 2, 4, 6, 8, 10]
    assert _due(2, 3, generator=True) == [0, 6]


def test_wavlm_validation_does_not_require_generator_update():
    host = _wavlm_host(2, 1, 1, training=False)
    assert VitsModel._wavlm_due(host, generator=True)


@pytest.mark.parametrize(
    ("d", "w", "scale"), [(1, 1, 1), (1, 2, 2), (2, 2, 1), (2, 3, 3), (2, 4, 2)]
)
def test_wavlm_generator_loss_scale_counts_generator_updates(d, w, scale):
    assert VitsModel._wavlm_g_loss_scale(_wavlm_host(d, w, 0)) == scale


def test_default_periods_run_everything_every_batch():
    # d=1, w=1 (CLI defaults): behaviour unchanged.
    assert _due(1, 1, generator=False) == list(range(12))
    assert _due(1, 1, generator=True) == list(range(12))
    assert VitsModel._wavlm_g_loss_scale(_wavlm_host(1, 1, 0)) == 1


def test_schedule_index_without_trainer_uses_batch_idx():
    assert _schedule_batch_index(SimpleNamespace(), 5) == 5


class _ManualTwoOptimizers(pl.LightningModule):
    """Two optimizer steps per batch, like VitsModel's G and D."""

    def __init__(self):
        super().__init__()
        self.automatic_optimization = False
        self.a = torch.nn.Linear(1, 1)
        self.b = torch.nn.Linear(1, 1)
        self.seen = []

    def training_step(self, batch, batch_idx):
        self.seen.append((_schedule_batch_index(self, batch_idx), self.global_step))
        opt_a, opt_b = self.optimizers()
        for opt, layer in ((opt_a, self.a), (opt_b, self.b)):
            opt.zero_grad()
            self.manual_backward(layer(batch[0]).sum())
            opt.step()

    def configure_optimizers(self):
        return (
            torch.optim.SGD(self.a.parameters(), lr=0.0),
            torch.optim.SGD(self.b.parameters(), lr=0.0),
        )

    def train_dataloader(self):
        data = torch.utils.data.TensorDataset(torch.ones(3, 1))
        return torch.utils.data.DataLoader(data, batch_size=1)


def test_schedule_index_counts_batches_across_epochs_with_real_trainer(tmp_path):
    module = _ManualTwoOptimizers()
    trainer = pl.Trainer(
        max_epochs=2,
        accelerator="cpu",
        devices=1,
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
        enable_model_summary=False,
        default_root_dir=tmp_path,
    )
    trainer.fit(module)
    indices = [idx for idx, _ in module.seen]
    steps = [step for _, step in module.seen]
    assert indices == [0, 1, 2, 3, 4, 5]
    # global_step advances per optimizer step: it cannot be used as a batch clock.
    assert steps == [0, 2, 4, 6, 8, 10]
