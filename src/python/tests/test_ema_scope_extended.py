"""v10b Phase B — S-5: EMA 対象を flow / enc_p (+ spk_proj_dp) に拡張。

背景 (docs/design/zero-shot-v10-design.md §10 所見 5):
現行 EMA は ``dec`` + ``spk_proj`` のみを対象にしており、flow / enc_p / dp は
対象外だった。v10a の崩壊時に「EMA でも救われない」ことが実測されたが、そもそも
崩壊した経路 (flow の SNAC スケール成長) が EMA の対象外だったという整備不足が
背景にある。SNAC flow (M1) 導入後は必須整備。

契約:
- ``--ema-scope legacy`` (default) は現行と bit 互換 (追加 shadow なし)
- ``--ema-scope extended`` で flow / enc_p / spk_proj_dp (存在する場合) を追加
- **export 側も追随**: ckpt に scope 情報を保存し、export が自動判別して
  正しいサブモジュールに shadow を適用する (学習側だけ拡張して export が
  dec しか見ないと、拡張 EMA は「学習ログ上は存在するが成果物に乗らない」
  という静かな取りこぼしになる)
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch")
pytest.importorskip("pytorch_lightning")

from torch import nn  # noqa: E402

from piper_train.vits.ema import EMACallback  # noqa: E402


pytestmark = pytest.mark.unit


class _Block(nn.Module):
    def __init__(self, fill: float):
        super().__init__()
        self.linear = nn.Linear(4, 4)
        with torch.no_grad():
            self.linear.weight.fill_(fill)
            self.linear.bias.zero_()


class _DummyGenerator(nn.Module):
    """model_g の EMA 対象サブモジュール構成を模したもの。"""

    def __init__(self, with_dp_head: bool = False):
        super().__init__()
        self.dec = _Block(1.0)
        self.spk_proj = _Block(2.0)
        self.flow = _Block(3.0)
        self.enc_p = _Block(4.0)
        if with_dp_head:
            self.spk_proj_dp = _Block(5.0)


class _DummyLightningModule(nn.Module):
    """nn.Module 派生: resume 後の device sync が ``model.parameters()`` を呼ぶ。"""

    def __init__(self, with_dp_head: bool = False):
        super().__init__()
        self.model_g = _DummyGenerator(with_dp_head=with_dp_head)


class _DummyTrainer:
    def __init__(self, global_step: int = 0):
        self.global_step = global_step


def _extended_names():
    from piper_train.vits import ema

    names = getattr(ema, "EXTENDED_EMA_MODULES", None)
    if names is None:
        pytest.fail(
            "piper_train.vits.ema.EXTENDED_EMA_MODULES が未実装 "
            "(S-5: 拡張 scope の対象サブモジュール表)"
        )
    return names


# ===========================================================================
# 1. 学習側 — scope の作用
# ===========================================================================


class TestEmaScopeTraining:
    def test_extended_module_list(self):
        assert tuple(_extended_names()) == ("flow", "enc_p", "spk_proj_dp")

    def test_legacy_scope_tracks_only_dec_and_spk_proj(self):
        cb = EMACallback(decay=0.5)
        model = _DummyLightningModule()
        cb.on_fit_start(_DummyTrainer(), model)
        assert cb.ema_generator is not None
        assert cb.ema_spk_proj is not None
        assert cb.ema_extended == {}, "legacy default で拡張 EMA が生えている"

    def test_extended_scope_tracks_flow_and_enc_p(self):
        cb = EMACallback(decay=0.5, scope="extended")
        model = _DummyLightningModule()
        cb.on_fit_start(_DummyTrainer(), model)
        assert set(cb.ema_extended) == {"flow", "enc_p"}, (
            "spk_proj_dp を持たないモデルでは 2 つだけ (存在するものだけ対象)"
        )

    def test_extended_scope_includes_dp_head_when_present(self):
        cb = EMACallback(decay=0.5, scope="extended")
        model = _DummyLightningModule(with_dp_head=True)
        cb.on_fit_start(_DummyTrainer(), model)
        assert set(cb.ema_extended) == {"flow", "enc_p", "spk_proj_dp"}

    def test_invalid_scope_rejected(self):
        with pytest.raises(ValueError, match="scope"):
            EMACallback(decay=0.5, scope="everything")

    def test_extended_shadows_are_updated_on_train_batch_end(self):
        cb = EMACallback(decay=0.5, scope="extended")
        model = _DummyLightningModule()
        cb.on_fit_start(_DummyTrainer(), model)
        with torch.no_grad():
            model.model_g.flow.linear.weight.fill_(30.0)
            model.model_g.enc_p.linear.weight.fill_(40.0)
        cb.on_train_batch_end(_DummyTrainer(global_step=0), model, None, None, 0)
        for name, start in (("flow", 3.0), ("enc_p", 4.0)):
            shadow = cb.ema_extended[name].shadow_params["linear.weight"][0, 0].item()
            assert shadow != pytest.approx(start), f"{name} の shadow が更新されない"
            assert cb.ema_extended[name].num_updates == 1

    def test_extended_shadows_apply_and_restore_around_validation(self):
        cb = EMACallback(decay=0.5, scope="extended")
        model = _DummyLightningModule()
        cb.on_fit_start(_DummyTrainer(), model)
        with torch.no_grad():
            cb.ema_extended["flow"].shadow_params["linear.weight"].fill_(9.0)
        snapshot = model.model_g.flow.linear.weight.clone()

        cb.on_validation_epoch_start(_DummyTrainer(), model)
        assert torch.allclose(
            model.model_g.flow.linear.weight,
            torch.full_like(model.model_g.flow.linear.weight, 9.0),
        )
        cb.on_validation_epoch_end(_DummyTrainer(), model)
        assert torch.equal(model.model_g.flow.linear.weight, snapshot)
        assert cb.ema_extended["flow"].backup_params == {}


# ===========================================================================
# 2. checkpoint の往復 + 後方互換
# ===========================================================================


class TestEmaScopeCheckpoint:
    def _saved(self, scope: str, with_dp_head: bool = False) -> dict:
        cb = EMACallback(decay=0.9, scope=scope)
        model = _DummyLightningModule(with_dp_head=with_dp_head)
        cb.on_fit_start(_DummyTrainer(), model)
        cb.on_train_batch_end(_DummyTrainer(global_step=0), model, None, None, 0)
        ckpt: dict = {}
        cb.on_save_checkpoint(_DummyTrainer(), model, ckpt)
        return ckpt

    def test_scope_is_recorded_in_checkpoint(self):
        assert self._saved("legacy")["ema_scope"] == "legacy"
        assert self._saved("extended")["ema_scope"] == "extended"

    def test_legacy_checkpoint_has_no_extended_payload(self):
        ckpt = self._saved("legacy")
        assert ckpt["ema_extended_state"] in (None, {})
        assert "ema_generator_state" in ckpt

    def test_extended_checkpoint_carries_module_shadows(self):
        ckpt = self._saved("extended")
        payload = ckpt["ema_extended_state"]
        assert set(payload) == {"flow", "enc_p"}
        assert "linear.weight" in payload["flow"]["shadow_params"]

    def test_load_restores_extended_state_and_scope(self):
        ckpt = self._saved("extended")
        cb = EMACallback(decay=0.9)  # legacy で起動 (resume 時の取り違え)
        model = _DummyLightningModule()
        cb.on_load_checkpoint(_DummyTrainer(), model, ckpt)
        assert set(cb.ema_extended) == {"flow", "enc_p"}
        assert cb.scope == "extended", (
            "拡張 shadow を積んだ ckpt から legacy で resume すると shadow が "
            "更新されず陳腐化する — ckpt の scope を採用する"
        )
        # resume 後も更新が続く
        cb.on_train_batch_end(_DummyTrainer(global_step=1), model, None, None, 0)
        assert cb.ema_extended["flow"].num_updates >= 1

    def test_load_legacy_checkpoint_is_backward_compatible(self):
        """拡張キーを持たない旧 ckpt でも例外なく読める。"""
        cb_old = EMACallback(decay=0.9)
        model = _DummyLightningModule()
        cb_old.on_fit_start(_DummyTrainer(), model)
        cb_old.on_train_batch_end(_DummyTrainer(global_step=0), model, None, None, 0)
        ckpt: dict = {}
        cb_old.on_save_checkpoint(_DummyTrainer(), model, ckpt)
        del ckpt["ema_scope"]
        del ckpt["ema_extended_state"]

        cb = EMACallback(decay=0.9, scope="extended")
        cb.on_load_checkpoint(_DummyTrainer(), _DummyLightningModule(), ckpt)
        assert cb.ema_generator is not None
        assert cb.ema_extended == {}
        assert cb.scope == "extended"


# ===========================================================================
# 3. export 側 (自動判別)
# ===========================================================================


class TestExportAppliesExtendedShadows:
    def _fn(self):
        from piper_train import export_onnx

        fn = getattr(export_onnx, "apply_ema_scope_from_checkpoint", None)
        if fn is None:
            pytest.fail(
                "piper_train.export_onnx.apply_ema_scope_from_checkpoint が未実装 "
                "(S-5 の export 側)"
            )
        return fn

    def _shadow(self, module, value: float) -> dict:
        return {
            name: torch.full_like(p.data, value)
            for name, p in module.named_parameters()
        }

    def test_legacy_checkpoint_applies_dec_and_spk_proj_only(self):
        model_g = _DummyGenerator()
        ckpt = {
            "ema_generator_state": {"shadow_params": self._shadow(model_g.dec, 7.0)},
            "ema_spk_proj_state": {
                "shadow_params": self._shadow(model_g.spk_proj, 8.0)
            },
        }
        report = self._fn()(model_g, ckpt)
        assert report["dec"][0] > 0 and report["spk_proj"][0] > 0
        assert "flow" not in report
        assert torch.allclose(
            model_g.dec.linear.weight,
            torch.full_like(model_g.dec.linear.weight, 7.0),
        )
        # flow / enc_p は触られない
        assert torch.allclose(
            model_g.flow.linear.weight,
            torch.full_like(model_g.flow.linear.weight, 3.0),
        )

    def test_extended_checkpoint_applies_to_the_right_modules(self):
        model_g = _DummyGenerator(with_dp_head=True)
        ckpt = {
            "ema_scope": "extended",
            "ema_generator_state": {"shadow_params": self._shadow(model_g.dec, 7.0)},
            "ema_extended_state": {
                "flow": {"shadow_params": self._shadow(model_g.flow, 11.0)},
                "enc_p": {"shadow_params": self._shadow(model_g.enc_p, 12.0)},
                "spk_proj_dp": {
                    "shadow_params": self._shadow(model_g.spk_proj_dp, 13.0)
                },
            },
        }
        report = self._fn()(model_g, ckpt)
        assert {"dec", "flow", "enc_p", "spk_proj_dp"} <= set(report)
        for name, value in (("flow", 11.0), ("enc_p", 12.0), ("spk_proj_dp", 13.0)):
            weight = getattr(model_g, name).linear.weight
            assert torch.allclose(weight, torch.full_like(weight, value)), (
                f"{name} に別モジュールの shadow が乗っている / 適用されていない"
            )

    def test_missing_module_is_reported_not_crashed(self):
        """ckpt に spk_proj_dp の shadow があるがモデルに無い場合は skip。"""
        model_g = _DummyGenerator()  # spk_proj_dp なし
        ckpt = {
            "ema_scope": "extended",
            "ema_extended_state": {
                "spk_proj_dp": {"shadow_params": {"linear.weight": torch.zeros(4, 4)}}
            },
        }
        report = self._fn()(model_g, ckpt)
        assert report.get("spk_proj_dp") == (0, 1)

    def test_no_ema_state_is_a_noop(self):
        model_g = _DummyGenerator()
        before = model_g.dec.linear.weight.clone()
        report = self._fn()(model_g, {})
        assert report == {}
        assert torch.equal(model_g.dec.linear.weight, before)


# ===========================================================================
# 4. CLI
# ===========================================================================


class TestEmaScopeCli:
    def _parse(self, extra=()):
        from piper_train.__main__ import create_parser

        return create_parser().parse_args(
            ["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra]
        )

    def test_default_is_legacy(self):
        assert self._parse().ema_scope == "legacy"

    def test_extended_parses(self):
        assert self._parse(("--ema-scope", "extended")).ema_scope == "extended"

    def test_invalid_scope_rejected(self):
        with pytest.raises(SystemExit):
            self._parse(("--ema-scope", "all"))

    def test_scope_reaches_the_callback(self):
        from piper_train.__main__ import create_parser
        from piper_train.vits.ema import EMACallback

        args = create_parser().parse_args(
            [
                "--dataset-dir",
                "/tmp/x",
                "--batch-size",
                "1",
                "--ema-scope",
                "extended",
                "--default_root_dir",
                "/tmp/out",
            ]
        )
        # _build_trainer は Trainer を作ってしまうため、callback 構築のみを検証
        cb = EMACallback(decay=args.ema_decay, scope=args.ema_scope)
        assert cb.scope == "extended"
