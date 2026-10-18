"""Manual-optimization regression tests with the real Lightning step wrapper.

Use tiny Linear G/D modules, the production training_step/training_step_d and
the production WavLM G gate/loss expression. No pretrained weights or GPU.
"""

from __future__ import annotations

import ast
import inspect
import json
import math
import os
import subprocess
import sys
import textwrap
from contextlib import nullcontext
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


torch = pytest.importorskip("torch", reason="manual optimizer tests require torch")
pl = pytest.importorskip("pytorch_lightning", reason="real Lightning optimizer steps")
from pytorch_lightning.plugins.precision import Precision  # noqa: E402
from torch import nn  # noqa: E402
from torch.utils.data import DataLoader, TensorDataset  # noqa: E402

from piper_train.__main__ import load_weights_only_checkpoint  # noqa: E402
from piper_train.vits.ema import EMACallback  # noqa: E402
from piper_train.vits.lightning import VitsModel  # noqa: E402
from piper_train.vits.losses import feature_loss, generator_loss  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.training]


def _g_expression(target):
    tree = ast.parse(textwrap.dedent(inspect.getsource(VitsModel.training_step_g)))
    for node in ast.walk(tree):
        if target == "gate" and isinstance(node, ast.If):
            if "self.model_d_wavlm" in ast.unparse(node.test):
                return compile(ast.Expression(node.test), "<WavLM G gate>", "eval")
        if isinstance(node, ast.Assign) and any(
            isinstance(item, ast.Name) and item.id == target for item in node.targets
        ):
            return compile(ast.Expression(node.value), "<WavLM G loss>", "eval")
    raise AssertionError(f"Production WavLM expression missing: {target}")


class _TinyGenerator(nn.Module):
    def __init__(self):
        super().__init__()
        self.dec = nn.Linear(1, 1)
        # Checkpoint compatibility requires an MB-iSTFT marker. This buffer
        # stands in for its subband head, without affecting numerical forward.
        self.dec.register_buffer("subband_conv_post_marker", torch.zeros(1))

    def forward(self, x):
        return self.dec(x)


class _TinyDiscriminator(nn.Module):
    def __init__(self):
        super().__init__()
        self.head = nn.Linear(1, 1)

    def forward(self, real, fake):
        r, f = self.head(real), self.head(fake)
        return [r], [f], [[r]], [[f]]


class _CountingSGD(torch.optim.SGD):
    def __init__(self, parameters):
        super().__init__(parameters, lr=0.01)
        self.step_calls = 0

    def step(self, closure=None):
        result = super().step(closure)
        self.step_calls += 1
        return result


class _ScheduleModel(VitsModel):
    """Replace numerical G forward only, preserving production optimizer logic."""

    def __init__(self, d_interval=1, wavlm_interval=2, g_nan=(), d_nan=(), lf=()):
        pl.LightningModule.__init__(self)
        self.automatic_optimization = False
        self.save_hyperparameters(
            {
                "d_update_interval": d_interval,
                "wavlm_every_n_steps": wavlm_interval,
                "c_wavlm": 0.5,
                "grad_clip": None,
            }
        )
        self.model_g = _TinyGenerator()
        self.model_d = _TinyDiscriminator()
        self.model_d_wavlm = _TinyDiscriminator()
        self.model_d_mrd = self.model_c_spk = None
        self._grad_probe_losses = None
        self._lf_step_active = False
        self._kl_cap_consecutive = 0
        self._kl_cap_abort_steps = 300
        self.training_batches_seen = 0
        self._training_batch_index = 0
        self.generator_updates = 0
        self.discriminator_updates = 0
        self.generator_updated_this_batch = False
        self.g_nan, self.d_nan, self.lf = set(g_nan), set(d_nan), set(lf)
        self.events = []
        self.g_wavlm_batches = []
        self.d_wavlm_batches = []
        self._g_gate = _g_expression("gate")
        self._g_loss = _g_expression("loss_wavlm")

    def configure_optimizers(self):
        self.g_optimizer = _CountingSGD(self.model_g.parameters())
        self.d_optimizer = _CountingSGD(
            list(self.model_d.parameters()) + list(self.model_d_wavlm.parameters())
        )
        return [self.g_optimizer, self.d_optimizer]

    def training_step_g(self, batch):
        self.batch_id = int(batch[0][0, 0])
        self._y = torch.ones_like(batch[0])
        self._y_hat = self.model_g(self._y)
        self._lf_step_active = self.batch_id in self.lf
        loss = self._y_hat.square().mean()
        if not self._lf_step_active and eval(self._g_gate, {"self": self}):  # noqa: S307
            self.g_wavlm_batches.append(self.batch_id)
            _, scores, real, fake = self.model_d_wavlm(self._y, self._y_hat)
            gen, _ = generator_loss(scores)
            loss += eval(  # noqa: S307
                self._g_loss,
                {
                    "self": self,
                    "loss_gen_wavlm": gen,
                    "loss_fm_wavlm": feature_loss(real, fake),
                },
            )
        if self.batch_id in self.g_nan:
            loss *= float("nan")
        return loss

    def training_step_d(self, batch):
        loss = super().training_step_d(batch)
        return loss * float("nan") if self.batch_id in self.d_nan else loss

    def _disc_autocast_ctx(self):
        return nullcontext()

    def on_train_epoch_end(self):
        # The tiny fixture has no LR schedulers (production has two).
        pass

    def _log_with_batch_info(self, key, *_args, **_kwargs):
        self.events.append(key)
        if key == "loss_disc_wavlm":
            self.d_wavlm_batches.append(self.batch_id)


def _trainer(tmp_path, *, epochs=1, callbacks=(), plugins=()):
    return pl.Trainer(
        accelerator="cpu",
        devices=1,
        max_epochs=epochs,
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
        enable_model_summary=False,
        default_root_dir=tmp_path,
        callbacks=list(callbacks),
        plugins=list(plugins),
        num_sanity_val_steps=0,
        limit_val_batches=0,
    )


def _loader(n=8):
    return DataLoader(
        TensorDataset(torch.arange(n, dtype=torch.float32).reshape(n, 1)), batch_size=1
    )


@pytest.mark.parametrize("d_interval", [1, 2, 3])
def test_real_lightning_update_ratio_and_wavlm(tmp_path, d_interval):
    torch.manual_seed(1234)
    model = _ScheduleModel(d_interval=d_interval)
    before = [p.detach().clone() for p in model.model_d_wavlm.parameters()]
    _trainer(tmp_path).fit(model, _loader())
    assert model.g_optimizer.step_calls == math.ceil(8 / d_interval)
    assert model.d_optimizer.step_calls == 8
    assert model.g_wavlm_batches == [
        i for i in range(8) if i % d_interval == 0 and i % 2 == 0
    ]
    assert model.d_wavlm_batches == [0, 2, 4, 6]
    assert any(
        not torch.equal(a, b)
        for a, b in zip(before, model.model_d_wavlm.parameters(), strict=True)
    )
    assert model.training_batches_seen == 8
    assert model.generator_updates == model.g_optimizer.step_calls
    assert model.discriminator_updates == model.d_optimizer.step_calls


@pytest.mark.parametrize("d_interval,expected", [(1, 1.0), (2, 0.5), (3, 1.0)])
def test_wavlm_g_compensation_uses_frequency_among_g_updates(d_interval, expected):
    model = _ScheduleModel(d_interval=d_interval)
    weighted = eval(  # noqa: S307
        model._g_loss,
        {
            "self": model,
            "loss_gen_wavlm": torch.tensor(1.0),
            "loss_fm_wavlm": torch.tensor(0.0),
        },
    )
    assert weighted.item() == pytest.approx(expected)


def test_batch_clock_advances_on_g_nan_d_nan_and_latent_filling(tmp_path):
    model = _ScheduleModel(d_interval=2, g_nan=(0,), d_nan=(3,), lf=(4,))
    _trainer(tmp_path).fit(model, _loader())
    assert model.training_batches_seen == 8
    assert model.generator_updates == model.g_optimizer.step_calls == 3
    assert model.discriminator_updates == model.d_optimizer.step_calls == 5
    assert "lf_step" in model.events
    assert "non_finite_skip" in model.events
    assert model._y_hat is None


def test_checkpoint_restores_batch_phase_and_update_counts(tmp_path):
    model = _ScheduleModel(d_interval=2)
    trainer = _trainer(tmp_path)
    trainer.fit(model, _loader(3))
    model._kl_cap_consecutive = 2
    checkpoint = tmp_path / "phase.ckpt"
    trainer.save_checkpoint(checkpoint)
    saved = torch.load(checkpoint, weights_only=False)
    assert saved["training_schedule_state"]["batches_seen"] == 3
    assert saved["training_schedule_state"]["kl_cap_consecutive"] == 2
    restored = _ScheduleModel(d_interval=2)
    _trainer(tmp_path, epochs=2).fit(restored, _loader(3), ckpt_path=checkpoint)
    assert restored.training_batches_seen == 6
    assert restored.generator_updates == 3
    assert restored.discriminator_updates == 6
    assert restored._kl_cap_consecutive == 2
    assert restored.g_optimizer.step_calls == 1  # resumed batch phase 3,4,5
    assert restored.d_wavlm_batches == [1]  # phase 4, not reset to phase 0


def test_legacy_checkpoint_allows_weights_but_rejects_strict_resume(tmp_path):
    model = _ScheduleModel()
    trainer = _trainer(tmp_path)
    trainer.fit(model, _loader(2))
    checkpoint = tmp_path / "legacy.ckpt"
    trainer.save_checkpoint(checkpoint)
    saved = torch.load(checkpoint, weights_only=False)
    saved.pop("training_schedule_state", None)
    torch.save(saved, checkpoint)
    weights_model = _ScheduleModel()
    weights_model.on_load_checkpoint(saved)
    weights_model.load_state_dict(saved["state_dict"])
    assert weights_model.training_batches_seen == 0
    with pytest.raises(ValueError, match="resume-weights-only"):
        _trainer(tmp_path, epochs=2).fit(
            _ScheduleModel(), _loader(2), ckpt_path=checkpoint
        )


class _CountingEMA(EMACallback):
    def on_fit_start(self, trainer, model):
        super().on_fit_start(trainer, model)
        self.update_calls = 0
        original = self.ema_generator.update

        def count():
            self.update_calls += 1
            original()

        self.ema_generator.update = count


def test_ema_updates_only_after_successful_g_optimizer_step(tmp_path):
    callback = _CountingEMA()
    model = _ScheduleModel(d_interval=2, g_nan=(0,))
    _trainer(tmp_path, callbacks=(callback,)).fit(model, _loader())
    assert callback.update_calls == model.g_optimizer.step_calls == 3


@pytest.mark.parametrize("batch_index,due", [(2, False), (3, True), (6, True)])
def test_probes_use_batch_clock_instead_of_optimizer_global_step(batch_index, due):
    model = _ScheduleModel()
    model.hparams.grad_probe_every = model.hparams.telemetry_every = 3
    model._training_batch_index = batch_index
    assert model._grad_probe_due() is due
    assert model._telemetry_due() is due


class _SkipOptimizerPrecision(Precision):
    """CPU simulation of GradScaler bypassing a raw optimizer step."""

    def __init__(self, which):
        self.which = which

    def optimizer_step(self, optimizer, model, closure, **kwargs):
        skipped = model.g_optimizer if self.which == "g" else model.d_optimizer
        if optimizer is skipped:
            return closure()
        return super().optimizer_step(optimizer, model, closure, **kwargs)


@pytest.mark.parametrize("which,g_steps,d_steps", [("g", 0, 8), ("d", 8, 0)])
def test_precision_skipped_optimizer_is_not_counted_or_ema_updated(
    tmp_path, which, g_steps, d_steps
):
    model = _ScheduleModel()
    callback = _CountingEMA()
    _trainer(
        tmp_path, callbacks=(callback,), plugins=(_SkipOptimizerPrecision(which),)
    ).fit(model, _loader())
    assert model.g_optimizer.step_calls == model.generator_updates == g_steps
    assert model.d_optimizer.step_calls == model.discriminator_updates == d_steps
    assert callback.update_calls == g_steps


def test_weights_only_restarts_batch_schedule_and_kl_guard(tmp_path):
    model = _ScheduleModel()
    (
        model.training_batches_seen,
        model.generator_updates,
        model.discriminator_updates,
    ) = 5, 3, 5
    model._kl_cap_consecutive = 2
    checkpoint = tmp_path / "weights.ckpt"
    torch.save({"state_dict": model.state_dict()}, checkpoint)
    load_weights_only_checkpoint(str(checkpoint), model)
    assert (
        model.training_batches_seen
        == model.generator_updates
        == model.discriminator_updates
        == 0
    )
    assert model._kl_cap_consecutive == 0


class _MidEpochCheckpoint(pl.Callback):
    def __init__(self, path):
        self.path = path

    def on_train_batch_end(self, trainer, model, outputs, batch, batch_idx):
        if batch_idx == 2:
            trainer.save_checkpoint(self.path)


def test_mid_epoch_checkpoint_restores_next_batch_phase(tmp_path):
    path = tmp_path / "mid.ckpt"
    model = _ScheduleModel(d_interval=2)
    _trainer(tmp_path, callbacks=(_MidEpochCheckpoint(path),)).fit(model, _loader())
    state = torch.load(path, weights_only=False)["training_schedule_state"]
    assert state["batches_seen"] == 3
    assert state["generator_updates"] == 2
    restored = _ScheduleModel(d_interval=2)
    _trainer(tmp_path).fit(restored, _loader(), ckpt_path=path)
    assert restored.training_batches_seen == 8
    assert restored.generator_updates == 4
    assert restored.discriminator_updates == 8


@pytest.mark.parametrize(
    "key,value",
    [
        ("batches_seen", -1),
        ("generator_updates", 9),
        ("discriminator_updates", True),
        ("version", 2),
    ],
)
def test_invalid_schedule_checkpoint_fails_explicitly(key, value):
    state = {
        "version": 1,
        "batches_seen": 8,
        "generator_updates": 4,
        "discriminator_updates": 8,
        "kl_cap_consecutive": 0,
    }
    state[key] = value
    with pytest.raises(ValueError):
        _ScheduleModel().on_load_checkpoint({"training_schedule_state": state})


def _rank_clock_worker(rank, store_path, output_dir):
    """Exercise real finite all_reduce; full DDP gradient smoke is separate."""
    torch.set_num_threads(1)
    torch.manual_seed(1234)
    dist = torch.distributed
    dist.init_process_group(
        "gloo",
        store=dist.FileStore(store_path, 2),
        rank=rank,
        world_size=2,
        timeout=timedelta(seconds=30),
    )
    try:
        model = _ScheduleModel(
            d_interval=2,
            g_nan=(0,) if rank else (),
            d_nan=(3,) if rank else (),
            lf=(4,),
        )
        optimizers = model.configure_optimizers()
        model.optimizers = lambda: optimizers
        model.manual_backward = lambda loss: loss.backward()
        # Deliberately unequal optimizer counters must not affect batch gates.
        model._trainer = SimpleNamespace(global_step=rank + 100)
        rows = []
        for index, batch in enumerate(_loader()):
            model.training_step(batch, index)
            rows.append(
                (
                    model.training_batches_seen,
                    model.generator_updates,
                    model.discriminator_updates,
                )
            )
        gathered = [None, None]
        dist.all_gather_object(gathered, rows)
        assert gathered[0] == gathered[1]
        assert rows[-1] == (8, 3, 5)
        (Path(output_dir) / f"rank-{rank}.json").write_text(
            json.dumps(rows), encoding="utf-8"
        )
    finally:
        dist.destroy_process_group()


@pytest.mark.skipif(
    not torch.distributed.is_gloo_available(), reason="CPU Gloo backend unavailable"
)
def test_two_ranks_agree_on_batch_schedule_and_remote_nonfinite_skip(tmp_path):
    # Run native Gloo initialization in an isolated, single-thread CPU
    # environment. Windows access violations were observed both in a broad
    # pytest process and with isolation alone; preserve fault-handler output
    # if they recur instead of retrying or suppressing a failed worker.
    code = """
import sys
import torch
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
import test_training_batch_schedule as schedule
if __name__ == '__main__':
    torch.multiprocessing.spawn(schedule._rank_clock_worker,
        args=(sys.argv[3], sys.argv[4]), nprocs=2, join=True)
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(Path(__file__).parents[1]),
            str(Path(__file__).parent),
            str(tmp_path / "store"),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        env={
            **os.environ,
            "PYTHONFAULTHANDLER": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    results = [
        json.loads((tmp_path / f"rank-{rank}.json").read_text()) for rank in range(2)
    ]
    assert results[0] == results[1]
    assert results[0][-1] == [8, 3, 5]


class _ValidationScheduleModel(_ScheduleModel):
    def __init__(self):
        super().__init__()
        self._kl_cap_consecutive = 2
        self._kl_cap_abort_steps = 3
        self.validation_states = []

    def training_step_g(self, batch):
        self._update_kl_cap_guard(1.0 if self.training else 20000.0)
        return super().training_step_g(batch)

    def val_dataloader(self):
        return _loader(2)

    def on_validation_epoch_start(self):
        self.before_validation = (
            self.training_batches_seen,
            self._training_batch_index,
            self._kl_cap_consecutive,
        )

    def on_validation_epoch_end(self):
        after = (
            self.training_batches_seen,
            self._training_batch_index,
            self._kl_cap_consecutive,
        )
        self.validation_states.append((self.before_validation, after))


def test_real_sanity_and_validation_leave_training_schedule_and_kl_unchanged(tmp_path):
    model = _ValidationScheduleModel()
    trainer = pl.Trainer(
        accelerator="cpu",
        devices=1,
        max_epochs=1,
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
        enable_model_summary=False,
        default_root_dir=tmp_path,
        num_sanity_val_steps=2,
    )
    trainer.fit(model, _loader(4))
    assert len(model.validation_states) == 2  # sanity and end-of-epoch validation
    assert all(before == after for before, after in model.validation_states)
    assert model.validation_states[0][0] == (0, 0, 2)
    assert model.training_batches_seen == 4
