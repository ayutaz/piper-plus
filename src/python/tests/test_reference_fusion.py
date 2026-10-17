"""Task 6R: 参照条件付けモジュールの LR 倍率・LR 慣らし・重み移行。

docs/design/zero-shot-reference-fusion-plan-2026-10-17.md §8 (Task 6R):

* ``reference_encoder`` / ``capacity_control`` (SynthesizerTrn の属性) を
  生成器 optimizer の**別 param group** に入れ、lr = base_lr ×
  ``--reference-lr-scale`` とする。``requires_grad`` は変えない (凍結で
  慣らすと EMA shadow と optimizer から外れるため、plan §8 表)。
* ``--reference-warmup-steps W`` は参照 group の実効 lr に係数
  ``f(k) = min(1, k / W)`` を掛ける。``k`` は**その step より前に成功した
  生成器更新の回数** (``generator_updates``、D のみの batch・非有限 skip・
  precision plugin の skip では進まない)。``W = 0`` は係数 1 (慣らしなし)。
  係数は optimizer.step() の間だけ掛け、終わったら scheduler の値へ戻す。
  scheduler (ExponentialLR / cosine) は group の lr を連鎖的に更新するので、
  慣らし係数が scheduler の状態に混ざらないことを確かめる。
* 既定 (``reference_conditioning="none"``) の optimizer / scheduler は変更前と
  同一。D optimizer は参照条件付けに関係なく不変。
* weights-only / multispeaker 移行: 参照モジュールが関わるときだけ
  ``load_state_with_allowed_missing`` で厳格に読む。none の ckpt → 参照付き
  モデルは参照 key の欠落だけを許し、参照付き ckpt → none モデルはエラー。
"""

from __future__ import annotations

from contextlib import nullcontext

import pytest


torch = pytest.importorskip("torch", reason="torch required")
pl = pytest.importorskip("pytorch_lightning", reason="real Lightning optimizer steps")

from torch import nn  # noqa: E402
from torch.utils.data import DataLoader, TensorDataset  # noqa: E402


pytestmark = pytest.mark.unit

BASE_LR = 2e-5
REFERENCE_MODULES = {"ref_spec": "reference_encoder", "capacity": "capacity_control"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _vits_model(**overrides):
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:  # pragma: no cover
        pytest.skip(f"Training dependencies not available: {e}")
    kwargs = {
        "num_symbols": 97,
        "num_speakers": 2,
        "num_languages": 2,
        "dataset": None,
        "batch_size": 4,
        "learning_rate": BASE_LR,
        "use_wavlm_discriminator": False,
        "upsample_rates": (4, 4),
        "upsample_kernel_sizes": (16, 16),
    }
    kwargs.update(overrides)
    torch.manual_seed(0)
    return VitsModel(**kwargs)


def _parse_train_args(extra=()):
    from piper_train.__main__ import create_parser

    return create_parser().parse_args(
        ["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra]
    )


def _legacy_configure_optimizers(model):
    """変更前 (HEAD b7b1aed4) の ``configure_optimizers`` の写し (golden)。

    既定経路が変更前と同一であることを、旧実装の出力と直接比べて確かめる。
    freeze_dp / train_decoder_only は既定 (off) の経路だけを写す。
    """
    from torch.optim.lr_scheduler import CosineAnnealingLR, LinearLR, SequentialLR

    hp = model.hparams
    g_params = [p for p in model.model_g.parameters() if p.requires_grad]
    d_params = list(model.model_d.parameters())
    optimizers = [
        torch.optim.AdamW(
            g_params,
            lr=hp.learning_rate,
            betas=hp.betas,
            eps=hp.eps,
            fused=torch.cuda.is_available(),
        ),
        torch.optim.AdamW(
            d_params,
            lr=hp.learning_rate,
            betas=hp.betas,
            eps=hp.eps,
            fused=torch.cuda.is_available(),
        ),
    ]
    max_epochs = hp.get("max_epochs", 200)
    warmup_epochs = getattr(hp, "lr_warmup_epochs", None)
    if warmup_epochs is None:
        warmup_epochs = getattr(hp, "warmup_epochs", 5)
    eta_min = getattr(hp, "lr_min", 1e-5)
    schedulers = []
    if getattr(hp, "lr_scheduler", "cosine") == "exponential":
        for opt in optimizers:
            schedulers.append(
                torch.optim.lr_scheduler.ExponentialLR(
                    opt, gamma=getattr(hp, "lr_decay", 0.999875)
                )
            )
    else:
        for opt in optimizers:
            if warmup_epochs > 0 and warmup_epochs < max_epochs:
                warmup = LinearLR(opt, start_factor=0.01, total_iters=warmup_epochs)
                cosine = CosineAnnealingLR(
                    opt, T_max=max_epochs - warmup_epochs, eta_min=eta_min
                )
                scheduler = SequentialLR(
                    opt, schedulers=[warmup, cosine], milestones=[warmup_epochs]
                )
            else:
                scheduler = CosineAnnealingLR(opt, T_max=max_epochs, eta_min=eta_min)
            schedulers.append(scheduler)
    return optimizers, schedulers


def _groups_without_params(optimizer):
    """param_groups の hyperparameter と param の並び (index) を比較用に取り出す。"""
    return optimizer.state_dict()["param_groups"]


def _lr_trajectory(optimizers, schedulers, epochs):
    rows = []
    for _ in range(epochs):
        rows.append([[g["lr"] for g in opt.param_groups] for opt in optimizers])
        for sch in schedulers:
            sch.step()
    return rows


# ---------------------------------------------------------------------------
# 既定経路の不変性
# ---------------------------------------------------------------------------


class TestDefaultOptimizerUnchanged:
    @pytest.mark.parametrize(
        "scheduler_kwargs",
        [
            {},  # cosine + 既定 warmup 5 epoch
            {"lr_scheduler": "cosine", "lr_warmup_epochs": 0},
            {"lr_scheduler": "exponential", "lr_decay": 0.9},
        ],
        ids=["cosine-warmup", "cosine", "exponential"],
    )
    def test_default_optimizer_groups_unchanged(self, scheduler_kwargs):
        model = _vits_model(max_epochs=12, **scheduler_kwargs)
        optimizers, schedulers = model.configure_optimizers()
        golden_opts, golden_schs = _legacy_configure_optimizers(
            _vits_model(max_epochs=12, **scheduler_kwargs)
        )
        assert len(optimizers) == len(golden_opts) == 2
        for opt, golden in zip(optimizers, golden_opts, strict=True):
            assert _groups_without_params(opt) == _groups_without_params(golden)
        assert [type(s) for s in schedulers] == [type(s) for s in golden_schs]
        assert _lr_trajectory(optimizers, schedulers, 12) == _lr_trajectory(
            golden_opts, golden_schs, 12
        )

    def test_default_generator_optimizer_holds_same_parameters_in_order(self):
        model = _vits_model()
        (opt_g, _), _ = model.configure_optimizers()
        expected = [p for p in model.model_g.parameters() if p.requires_grad]
        assert len(opt_g.param_groups) == 1
        got = opt_g.param_groups[0]["params"]
        assert len(got) == len(expected)
        assert all(a is b for a, b in zip(got, expected, strict=True))

    def test_default_hparams_carry_neutral_reference_flags(self):
        model = _vits_model()
        assert model.hparams.reference_lr_scale == 1.0
        assert model.hparams.reference_warmup_steps == 0

    def test_old_hparams_without_reference_lr_keys_rebuild(self):
        """旧 ckpt の hparams (キーなし) からも既定値で再構築できる。"""
        model = _vits_model()
        old = {
            k: v
            for k, v in model.hparams.items()
            if k not in ("reference_lr_scale", "reference_warmup_steps")
        }
        for key in ("num_symbols", "num_speakers", "num_languages"):
            old.pop(key)
        rebuilt = _vits_model(**old)
        assert rebuilt.hparams.reference_lr_scale == 1.0
        assert rebuilt.hparams.reference_warmup_steps == 0


# ---------------------------------------------------------------------------
# param group と LR 倍率
# ---------------------------------------------------------------------------


def _reference_param_group(optimizer):
    from piper_train.vits.lightning import REFERENCE_PARAM_GROUP

    groups = [
        g for g in optimizer.param_groups if g.get("name") == REFERENCE_PARAM_GROUP
    ]
    assert len(groups) == 1, [g.get("name") for g in optimizer.param_groups]
    return groups[0]


class TestReferenceParamGroup:
    @pytest.mark.parametrize("mode", ["ref_spec", "capacity"])
    @pytest.mark.parametrize("scale", [0.5, 1.0, 3.0])
    def test_reference_param_group_lr_scale(self, mode, scale):
        model = _vits_model(reference_conditioning=mode, reference_lr_scale=scale)
        (opt_g, _), _ = model.configure_optimizers()
        assert len(opt_g.param_groups) == 2
        main, reference = opt_g.param_groups
        assert reference is _reference_param_group(opt_g)
        # 既定 cosine は LinearLR warmup (start_factor 0.01) が構築時に group の
        # lr を書き換えるので、group の基準 lr は scheduler の initial_lr で見る
        assert main["initial_lr"] == BASE_LR
        assert reference["initial_lr"] == BASE_LR * scale
        # 乗算の順序が違うだけ ((base·s)·0.01 と (base·0.01)·s) なので丸め
        # 1 ulp 程度の差しか出ない
        assert reference["lr"] == pytest.approx(main["lr"] * scale, rel=1e-12)

    @pytest.mark.parametrize("mode", ["ref_spec", "capacity"])
    def test_reference_group_holds_exactly_the_reference_parameters(self, mode):
        model = _vits_model(reference_conditioning=mode)
        (opt_g, _), _ = model.configure_optimizers()
        main, reference = opt_g.param_groups
        module = getattr(model.model_g, REFERENCE_MODULES[mode])
        expected_ref = list(module.parameters())
        assert len(reference["params"]) == len(expected_ref)
        assert all(
            a is b for a, b in zip(reference["params"], expected_ref, strict=True)
        )
        ref_ids = {id(p) for p in expected_ref}
        expected_main = [
            p
            for p in model.model_g.parameters()
            if p.requires_grad and id(p) not in ref_ids
        ]
        assert len(main["params"]) == len(expected_main)
        assert all(a is b for a, b in zip(main["params"], expected_main, strict=True))

    @pytest.mark.parametrize("mode", ["ref_spec", "capacity"])
    def test_requires_grad_is_not_changed(self, mode):
        model = _vits_model(reference_conditioning=mode, reference_warmup_steps=100)
        before = {n: p.requires_grad for n, p in model.named_parameters()}
        model.configure_optimizers()
        after = {n: p.requires_grad for n, p in model.named_parameters()}
        assert after == before
        module = getattr(model.model_g, REFERENCE_MODULES[mode])
        assert all(p.requires_grad for p in module.parameters())

    def test_discriminator_optimizer_is_unaffected(self):
        legacy = _vits_model()
        reference = _vits_model(
            reference_conditioning="ref_spec",
            reference_lr_scale=4.0,
            reference_warmup_steps=10,
        )
        (_, legacy_d), _ = legacy.configure_optimizers()
        (_, reference_d), _ = reference.configure_optimizers()
        assert _groups_without_params(reference_d) == _groups_without_params(legacy_d)

    def test_generator_named_params_mirror_optimizer_order(self):
        """pre-FiLM optimizer state の移行が使う並びと optimizer の並びが一致。"""
        model = _vits_model(reference_conditioning="ref_spec")
        (opt_g, _), _ = model.configure_optimizers()
        flat = [p for g in opt_g.param_groups for p in g["params"]]
        named = model._generator_named_params()
        assert len(flat) == len(named)
        assert all(a is b for a, (_, b) in zip(flat, named, strict=True))

    def test_frozen_reference_parameters_leave_no_empty_group(self):
        """--train-decoder-only は参照モジュールも凍結する。空の group は作らない。"""
        model = _vits_model(reference_conditioning="ref_spec", train_decoder_only=True)
        (opt_g, _), _ = model.configure_optimizers()
        assert len(opt_g.param_groups) == 1
        assert all(len(g["params"]) > 0 for g in opt_g.param_groups)

    @pytest.mark.parametrize(
        ("scheduler_kwargs", "scale", "ok"),
        [
            # cosine は全 group を同じ絶対値 eta_min へ寄せる (torch の仕様)。
            # base×scale が eta_min 未満だと参照 group の lr が学習中に増える。
            ({"lr_scheduler": "cosine", "lr_min": 1e-5}, 0.25, False),
            ({"lr_scheduler": "cosine", "lr_min": 1e-5}, 0.5, True),  # = eta_min
            ({"lr_scheduler": "exponential"}, 0.25, True),
        ],
    )
    def test_cosine_reference_lr_below_eta_min_raises(
        self, scheduler_kwargs, scale, ok
    ):
        model = _vits_model(
            reference_conditioning="ref_spec",
            reference_lr_scale=scale,
            **scheduler_kwargs,
        )
        if ok:
            model.configure_optimizers()
        else:
            with pytest.raises(ValueError, match="reference-lr-scale"):
                model.configure_optimizers()


# ---------------------------------------------------------------------------
# 入力検査
# ---------------------------------------------------------------------------


class TestReferenceLrValidation:
    @pytest.mark.parametrize(
        "scale", [0.0, -1.0, float("nan"), float("inf"), True, "1.0", None]
    )
    def test_invalid_lr_scale_raises(self, scale):
        with pytest.raises((TypeError, ValueError), match="reference_lr_scale"):
            _vits_model(reference_conditioning="ref_spec", reference_lr_scale=scale)

    @pytest.mark.parametrize("steps", [-1, 1.5, True, "10", None])
    def test_invalid_warmup_steps_raises(self, steps):
        with pytest.raises((TypeError, ValueError), match="reference_warmup_steps"):
            _vits_model(reference_conditioning="ref_spec", reference_warmup_steps=steps)

    @pytest.mark.parametrize(
        "flags",
        [{"reference_lr_scale": 0.5}, {"reference_warmup_steps": 10}],
    )
    def test_flags_without_reference_module_raise(self, flags):
        """none で指定すると黙って無効になるため、明示エラーにする。"""
        with pytest.raises(ValueError, match="reference-conditioning"):
            _vits_model(**flags)

    def test_integer_scale_is_accepted(self):
        model = _vits_model(reference_conditioning="ref_spec", reference_lr_scale=2)
        (opt_g, _), _ = model.configure_optimizers()
        assert _reference_param_group(opt_g)["initial_lr"] == BASE_LR * 2


# ---------------------------------------------------------------------------
# 慣らし係数
# ---------------------------------------------------------------------------


class TestWarmupFactor:
    @pytest.mark.parametrize(
        ("warmup", "updates", "expected"),
        [
            (0, 0, 1.0),  # 慣らしなし
            (0, 7, 1.0),
            (1, 0, 0.0),
            (1, 1, 1.0),
            (4, 0, 0.0),  # 最初の更新は lr 0
            (4, 1, 0.25),
            (4, 2, 0.5),  # 中間
            (4, 3, 0.75),
            (4, 4, 1.0),  # 終端
            (4, 1000, 1.0),  # 以後
        ],
    )
    def test_factor_schedule(self, warmup, updates, expected):
        model = _vits_model(
            reference_conditioning="capacity", reference_warmup_steps=warmup
        )
        model.generator_updates = updates
        assert model._reference_lr_factor() == expected


class _TinyGenerator(nn.Module):
    """``dec`` と ``reference_encoder`` を持つ最小の生成器 (実 Linear)。"""

    def __init__(self, with_reference: bool):
        super().__init__()
        self.dec = nn.Linear(1, 1)
        self.dec.register_buffer("subband_conv_post_marker", torch.zeros(1))
        if with_reference:
            self.reference_encoder = nn.Linear(1, 1)

    def forward(self, x):
        y = self.dec(x)
        if hasattr(self, "reference_encoder"):
            y = y + self.reference_encoder(x)
        return y


class _TinyDiscriminator(nn.Module):
    def __init__(self):
        super().__init__()
        self.head = nn.Linear(1, 1)

    def forward(self, real, fake):
        r, f = self.head(real), self.head(fake)
        return [r], [f], [[r]], [[f]]


def _tiny_model_class():
    from piper_train.vits.lightning import VitsModel

    class _WarmupModel(VitsModel):
        """数値 forward だけ差し替え、optimizer / scheduler / training_step /
        on_train_epoch_end / checkpoint hook は本番実装をそのまま使う。"""

        def __init__(self, *, warmup, scale, scheduler, d_interval=1):
            pl.LightningModule.__init__(self)
            self.automatic_optimization = False
            hp = {
                "learning_rate": 1e-3,
                "betas": (0.8, 0.99),
                "eps": 1e-9,
                "d_update_interval": d_interval,
                "wavlm_every_n_steps": 1,
                "grad_clip": None,
                "reference_conditioning": "ref_spec",
                "reference_lr_scale": scale,
                "reference_warmup_steps": warmup,
                "max_epochs": 3,
                "lr_min": 1e-5,
            }
            hp.update(scheduler)
            self.save_hyperparameters(hp)
            self.model_g = _TinyGenerator(with_reference=True)
            self.model_d = _TinyDiscriminator()
            self.model_d_wavlm = self.model_d_mrd = self.model_c_spk = None
            self._grad_probe_losses = None
            self._lf_step_active = False
            self._kl_cap_abort_steps = 300
            self._reset_training_progress()
            self.effective = []  # G step 時の [main lr, reference lr]
            self.scheduled = []  # 各 batch 後の [main lr, reference lr]

        def configure_optimizers(self):
            optimizers, schedulers = super().configure_optimizers()
            opt_g = optimizers[0]

            def record(optimizer, *_args):
                self.effective.append(
                    (self.generator_updates, [g["lr"] for g in optimizer.param_groups])
                )

            opt_g.register_step_pre_hook(record)
            self.opt_g = opt_g
            return optimizers, schedulers

        def training_step_g(self, batch):
            self._y = torch.ones_like(batch[0])
            self._y_hat = self.model_g(self._y)
            return self._y_hat.square().mean()

        def _disc_autocast_ctx(self):
            return nullcontext()

        def _log_with_batch_info(self, *_args, **_kwargs):
            pass

        def on_train_batch_end(self, outputs, batch, batch_idx):
            self.scheduled.append([g["lr"] for g in self.opt_g.param_groups])

    return _WarmupModel


def _trainer(tmp_path, epochs, callbacks=()):
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
        num_sanity_val_steps=0,
        limit_val_batches=0,
    )


def _loader(n=4):
    return DataLoader(
        TensorDataset(torch.arange(n, dtype=torch.float32).reshape(n, 1)), batch_size=1
    )


# 実効 lr は「scheduler の lr × 係数」の 1 回の乗算。期待値も同じ演算順で
# 作るので一致は厳密だが、Python float の乗算 1 回分 (≤ 1 ulp ≈ 1.1e-16) の
# 丸め差を許して rel=1e-12 とする (係数の取り違えは 1/6 以上の差になる)。
LR_REL = 1e-12


class TestWarmupInTraining:
    def test_reference_warmup_ramps_lr(self, tmp_path):
        """ExponentialLR (epoch 単位) と慣らし (G 更新単位) の積が実効 lr。"""
        warmup, scale, gamma = 6, 0.25, 0.5
        model = _tiny_model_class()(
            warmup=warmup,
            scale=scale,
            scheduler={"lr_scheduler": "exponential", "lr_decay": gamma},
        )
        _trainer(tmp_path, epochs=2).fit(model, _loader(4))

        assert [k for k, _ in model.effective] == list(range(8))
        for k, (main_lr, ref_lr) in model.effective:
            epoch = k // 4
            scheduled = 1e-3 * gamma**epoch
            assert main_lr == pytest.approx(scheduled, rel=LR_REL)
            assert ref_lr == pytest.approx(
                scheduled * scale * min(1.0, k / warmup), rel=LR_REL
            )
        # 期待値の具体値: 開始 0、中間 (k=3) 0.5、終端 (k=6) 以降 1
        factors = [
            ref / (1e-3 * gamma ** (k // 4) * scale) for k, (_, ref) in model.effective
        ]
        assert factors == pytest.approx(
            [0.0, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6, 1.0, 1.0], rel=LR_REL
        )

    def test_group_lr_is_restored_to_scheduler_value_after_step(self, tmp_path):
        model = _tiny_model_class()(
            warmup=6,
            scale=0.25,
            scheduler={"lr_scheduler": "exponential", "lr_decay": 0.5},
        )
        _trainer(tmp_path, epochs=2).fit(model, _loader(4))
        for index, (main_lr, ref_lr) in enumerate(model.scheduled):
            scheduled = 1e-3 * 0.5 ** (index // 4)
            assert main_lr == scheduled
            assert ref_lr == scheduled * 0.25

    @pytest.mark.parametrize(
        "scheduler",
        [
            {"lr_scheduler": "exponential", "lr_decay": 0.7},
            {"lr_scheduler": "cosine", "lr_warmup_epochs": 0},
            {"lr_scheduler": "cosine", "lr_warmup_epochs": 1},
        ],
        ids=["exponential", "cosine", "cosine-warmup"],
    )
    def test_warmup_does_not_perturb_scheduler_trajectory(self, tmp_path, scheduler):
        """慣らしの有無で scheduler の lr 列 (step 間の group lr) が同一。"""
        runs = {}
        for warmup in (0, 5):
            model = _tiny_model_class()(warmup=warmup, scale=0.5, scheduler=scheduler)
            _trainer(tmp_path / str(warmup), epochs=3).fit(model, _loader(4))
            runs[warmup] = model
        assert len(runs[5].scheduled) == 12
        assert runs[5].scheduled == runs[0].scheduled
        # W=0 の実効 lr は scheduler の lr そのもの。W=5 はその参照 group だけ
        # min(1, k/5) 倍で、主 group は同一。
        assert [k for k, _ in runs[5].effective] == list(range(12))
        for (k, slow), (_, plain) in zip(
            runs[5].effective, runs[0].effective, strict=True
        ):
            assert slow[0] == plain[0]
            assert slow[1] == pytest.approx(plain[1] * min(1.0, k / 5), rel=LR_REL)

    def test_warmup_clock_counts_generator_updates_not_batches(self, tmp_path):
        """d_update_interval=2 では G 更新は 2 batch に 1 回。係数は G 更新数で進む。"""
        model = _tiny_model_class()(
            warmup=4,
            scale=1.0,
            scheduler={"lr_scheduler": "exponential", "lr_decay": 1.0},
            d_interval=2,
        )
        _trainer(tmp_path, epochs=1).fit(model, _loader(8))
        assert [k for k, _ in model.effective] == [0, 1, 2, 3]
        assert [ref for _, (_, ref) in model.effective] == pytest.approx(
            [0.0, 2.5e-4, 5e-4, 7.5e-4], rel=LR_REL
        )

    def test_precision_skipped_step_keeps_clock_and_restores_lr(self, tmp_path):
        """GradScaler 相当の skip では G 更新数も係数も進まず、group lr は
        scheduler の値へ戻る (skip 中に係数が残留しない)。"""
        from pytorch_lightning.plugins.precision import Precision

        class _SkipGenerator(Precision):
            def optimizer_step(self, optimizer, model, closure, **kwargs):
                if optimizer is model.opt_g:
                    return closure()
                return super().optimizer_step(optimizer, model, closure, **kwargs)

        model = _tiny_model_class()(
            warmup=4,
            scale=0.5,
            scheduler={"lr_scheduler": "exponential", "lr_decay": 1.0},
        )
        trainer = pl.Trainer(
            accelerator="cpu",
            devices=1,
            max_epochs=1,
            logger=False,
            enable_checkpointing=False,
            enable_progress_bar=False,
            enable_model_summary=False,
            default_root_dir=tmp_path,
            plugins=[_SkipGenerator()],
            num_sanity_val_steps=0,
            limit_val_batches=0,
        )
        trainer.fit(model, _loader(3))
        assert model.generator_updates == 0
        assert model.effective == []
        assert model.scheduled == [[1e-3, 5e-4]] * 3

    def test_strict_resume_continues_warmup(self, tmp_path):
        """strict resume 後も係数は保存された generator_updates から続く。"""
        scheduler = {"lr_scheduler": "exponential", "lr_decay": 0.5}
        cls = _tiny_model_class()
        full = cls(warmup=6, scale=0.25, scheduler=scheduler)
        _trainer(tmp_path / "full", epochs=2).fit(full, _loader(4))

        first = cls(warmup=6, scale=0.25, scheduler=scheduler)
        trainer = _trainer(tmp_path / "first", epochs=1)
        trainer.fit(first, _loader(4))
        ckpt = tmp_path / "epoch0.ckpt"
        trainer.save_checkpoint(ckpt)

        resumed = cls(warmup=6, scale=0.25, scheduler=scheduler)
        _trainer(tmp_path / "resumed", epochs=2).fit(
            resumed, _loader(4), ckpt_path=str(ckpt)
        )
        assert first.effective + resumed.effective == full.effective

    def test_reference_parameters_do_not_move_on_first_update(self, tmp_path):
        """k=0 の係数は 0。AdamW (decoupled weight decay も lr 倍) で重みは不変。"""
        model = _tiny_model_class()(
            warmup=3,
            scale=1.0,
            scheduler={"lr_scheduler": "exponential", "lr_decay": 1.0},
        )
        before = model.model_g.reference_encoder.weight.detach().clone()
        dec_before = model.model_g.dec.weight.detach().clone()
        _trainer(tmp_path, epochs=1).fit(model, _loader(1))
        assert torch.equal(model.model_g.reference_encoder.weight, before)
        assert not torch.equal(model.model_g.dec.weight, dec_before)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestReferenceLrCli:
    def test_defaults(self):
        args = _parse_train_args()
        assert args.reference_lr_scale == 1.0
        assert args.reference_warmup_steps == 0

    def test_values_parse(self):
        args = _parse_train_args(
            ("--reference-lr-scale", "0.3", "--reference-warmup-steps", "2000")
        )
        assert args.reference_lr_scale == 0.3
        assert args.reference_warmup_steps == 2000

    @pytest.mark.parametrize(
        "extra",
        [
            ("--reference-lr-scale", "abc"),
            ("--reference-warmup-steps", "1.5"),
        ],
    )
    def test_malformed_values_rejected(self, extra):
        with pytest.raises(SystemExit):
            _parse_train_args(extra)

    def test_cli_args_reach_model(self):
        """CLI → ``vars(args)`` → ``VitsModel(**dict_args)`` (main と同じ受け渡し)。"""
        from piper_train.vits.lightning import VitsModel

        args = _parse_train_args(
            (
                "--no-wavlm",
                "--reference-conditioning",
                "ref_spec",
                "--reference-lr-scale",
                "2.0",
                "--reference-warmup-steps",
                "7",
            )
        )
        dict_args = vars(args)
        dict_args["use_wavlm_discriminator"] = False
        dict_args["upsample_rates"] = (4, 4)
        dict_args["upsample_kernel_sizes"] = (16, 16)
        dict_args["learning_rate"] = BASE_LR
        model = VitsModel(
            num_symbols=97,
            num_speakers=2,
            num_languages=2,
            sample_rate=22050,
            dataset=None,
            **dict_args,
        )
        assert model.hparams.reference_lr_scale == 2.0
        assert model.hparams.reference_warmup_steps == 7


# ---------------------------------------------------------------------------
# 重み移行 (--resume-weights-only / --resume-from-multispeaker-checkpoint)
# ---------------------------------------------------------------------------


def _save(tmp_path, model, name):
    path = tmp_path / name
    torch.save({"state_dict": model.state_dict()}, path)
    return str(path)


@pytest.fixture(scope="module")
def legacy_checkpoint(tmp_path_factory):
    model = _vits_model()
    with torch.no_grad():
        for p in model.parameters():
            p.add_(0.01)  # 新規初期化と区別できる値にする
    path = _save(tmp_path_factory.mktemp("legacy"), model, "none.ckpt")
    return path, {k: v.clone() for k, v in model.state_dict().items()}


class TestWeightsOnlyMigration:
    @pytest.mark.parametrize("mode", ["ref_spec", "capacity"])
    def test_none_checkpoint_into_reference_model(self, legacy_checkpoint, mode):
        from piper_train.__main__ import load_weights_only_checkpoint

        path, saved = legacy_checkpoint
        model = _vits_model(reference_conditioning=mode)
        module_name = REFERENCE_MODULES[mode]
        missing, unexpected = load_weights_only_checkpoint(path, model)

        prefix = f"model_g.{module_name}."
        assert unexpected == []
        assert missing, "参照モジュールの key が missing として報告されない"
        assert all(k.startswith(prefix) for k in missing), missing
        assert set(missing) == {k for k in model.state_dict() if k.startswith(prefix)}
        state = model.state_dict()
        for key, value in saved.items():
            assert torch.equal(state[key], value), key
        out = getattr(model.model_g, module_name).out
        assert torch.count_nonzero(out.weight) == 0
        assert torch.count_nonzero(out.bias) == 0

    def test_reference_checkpoint_into_legacy_model_raises(self, tmp_path):
        from piper_train.__main__ import load_weights_only_checkpoint

        path = _save(tmp_path, _vits_model(reference_conditioning="ref_spec"), "r.ckpt")
        model = _vits_model()
        before = {k: v.clone() for k, v in model.state_dict().items()}
        with pytest.raises(ValueError, match="reference_encoder"):
            load_weights_only_checkpoint(path, model)
        for key, value in before.items():
            assert torch.equal(model.state_dict()[key], value), key

    def test_ref_spec_checkpoint_into_capacity_model_raises(self, tmp_path):
        from piper_train.__main__ import load_weights_only_checkpoint

        path = _save(tmp_path, _vits_model(reference_conditioning="ref_spec"), "r.ckpt")
        with pytest.raises(ValueError, match="unexpected"):
            load_weights_only_checkpoint(
                path, _vits_model(reference_conditioning="capacity")
            )

    def test_other_missing_key_raises_for_reference_model(self, tmp_path):
        from piper_train.__main__ import load_weights_only_checkpoint

        state = _vits_model().state_dict()
        key = "model_g.spk_proj.0.weight"
        del state[key]
        path = tmp_path / "partial.ckpt"
        torch.save({"state_dict": state}, path)
        with pytest.raises(ValueError, match=r"spk_proj\.0\.weight"):
            load_weights_only_checkpoint(
                str(path), _vits_model(reference_conditioning="ref_spec")
            )

    def test_extra_key_raises_for_reference_model(self, tmp_path):
        from piper_train.__main__ import load_weights_only_checkpoint

        state = _vits_model().state_dict()
        state["model_d_wavlm.extra.weight"] = torch.zeros(1)
        path = tmp_path / "extra.ckpt"
        torch.save({"state_dict": state}, path)
        with pytest.raises(ValueError, match="model_d_wavlm"):
            load_weights_only_checkpoint(
                str(path), _vits_model(reference_conditioning="ref_spec")
            )

    def test_legacy_to_legacy_keeps_lenient_behaviour(self, tmp_path):
        """参照モジュールが関わらない移行は従来どおり strict=False (余剰を捨てる)。"""
        from piper_train.__main__ import load_weights_only_checkpoint

        state = _vits_model().state_dict()
        state["model_d_wavlm.extra.weight"] = torch.zeros(1)
        path = tmp_path / "extra.ckpt"
        torch.save({"state_dict": state}, path)
        missing, unexpected = load_weights_only_checkpoint(str(path), _vits_model())
        assert missing == []
        assert unexpected == ["model_d_wavlm.extra.weight"]


class TestMultispeakerMigration:
    def test_reference_checkpoint_into_single_speaker_model_raises(self, tmp_path):
        """single-speaker FT 先は参照モジュールを持てない。参照重みを黙って
        捨てずにエラーにする。"""
        from piper_train.__main__ import load_multispeaker_checkpoint

        path = _save(
            tmp_path, _vits_model(reference_conditioning="capacity"), "cap.ckpt"
        )
        target = _vits_model(num_speakers=1)
        with pytest.raises(ValueError, match="capacity_control"):
            load_multispeaker_checkpoint(path, target)

    def test_none_checkpoint_into_single_speaker_model_still_loads(
        self, legacy_checkpoint
    ):
        from piper_train.__main__ import load_multispeaker_checkpoint

        path, saved = legacy_checkpoint
        target = _vits_model(num_speakers=1)
        load_multispeaker_checkpoint(path, target)
        assert torch.equal(
            target.state_dict()["model_g.dec.conv_pre.bias"],
            saved["model_g.dec.conv_pre.bias"],
        )


def test_reference_module_names_are_shared():
    """EMA・optimizer・移行が同じ属性名表を使う (片方だけ更新される事故の防止)。"""
    from piper_train.vits import ema, lightning
    from piper_train.vits.reference_encoder import REFERENCE_MODULE_NAMES

    assert REFERENCE_MODULE_NAMES == ("reference_encoder", "capacity_control")
    assert ema.REFERENCE_EMA_MODULES is REFERENCE_MODULE_NAMES
    expected_prefixes = tuple(f"{name}." for name in REFERENCE_MODULE_NAMES)
    assert expected_prefixes == lightning.REFERENCE_PARAM_PREFIXES
