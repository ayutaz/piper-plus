"""学習 hparam ``reference_spec_frontend`` (参照融合計画 §8 Task 11R、Ruling R14)。

固定する契約:

* ``--reference-spec-frontend`` の選択肢は ``reference_spec_contract`` の閉じた
  集合そのもの (既定値なし)。
* ``--reference-conditioning ref_spec`` では必須 (無ければ ``SystemExit``、S2 の
  data audit と選択肢を名指しする)。``none`` / ``capacity`` で指定したら
  ``SystemExit`` (黙って無視しない)。dataset を読む前に止める。
* VitsModel の hparam として checkpoint に保存される。直接構築でも閉じた集合の
  外の名前や、ref_spec 以外での指定は ``ValueError``。
* key を持たない旧 checkpoint (none / capacity) は従来どおり読める。
"""

from __future__ import annotations

import sys

import pytest


torch = pytest.importorskip(
    "torch",
    reason="VitsModel hparams need the train extra (torch).",
)

from piper_train.reference_spec_contract import REFERENCE_SPEC_FRONTENDS  # noqa: E402


pytestmark = pytest.mark.unit

NO_VAD_MQ = "no-vad;soxr-mq"

_TINY = {
    "num_symbols": 40,
    "num_speakers": 2,
    "num_languages": 1,
    "dataset": None,
    "upsample_rates": (4, 4),
    "upsample_initial_channel": 32,
    "upsample_kernel_sizes": (16, 16),
    "hidden_channels": 32,
    "inter_channels": 32,
    "filter_channels": 64,
    "n_layers": 1,
    "prosody_dim": 0,
    "gin_channels": 32,
    "use_wavlm_discriminator": False,
}


def _model(**overrides):
    from piper_train.vits.lightning import VitsModel

    torch.manual_seed(0)
    return VitsModel(**{**_TINY, **overrides})


def _parse(extra=()):
    from piper_train.__main__ import create_parser

    return create_parser().parse_args(
        ["--dataset-dir", "/nonexistent-dataset-dir", "--batch-size", "1", *extra]
    )


def _check(args):
    from piper_train.zero_shot_requirements import validate_reference_spec_frontend_args

    validate_reference_spec_frontend_args(
        reference_conditioning=args.reference_conditioning,
        reference_spec_frontend=args.reference_spec_frontend,
    )


_REF_SPEC = [
    "--reference-conditioning",
    "ref_spec",
    "--generator-reference",
    "cross_utt",
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCli:
    def test_parser_default_is_none(self):
        assert _parse().reference_spec_frontend is None

    def test_parser_choices_are_the_contract_closed_set(self):
        from piper_train.__main__ import create_parser

        action = next(
            a
            for a in create_parser()._actions
            if "--reference-spec-frontend" in a.option_strings
        )
        assert sorted(action.choices) == sorted(REFERENCE_SPEC_FRONTENDS)

    @pytest.mark.parametrize("frontend", sorted(REFERENCE_SPEC_FRONTENDS))
    def test_parser_accepts_each_contract_frontend(self, frontend):
        assert (
            _parse(
                [*_REF_SPEC, "--reference-spec-frontend", frontend]
            ).reference_spec_frontend
            == frontend
        )

    def test_parser_rejects_unknown_frontend(self):
        with pytest.raises(SystemExit):
            _parse([*_REF_SPEC, "--reference-spec-frontend", "silero-vad;torchaudio"])

    def test_ref_spec_without_frontend_exits(self):
        with pytest.raises(SystemExit, match="--reference-spec-frontend"):
            _check(_parse(_REF_SPEC))

    def test_ref_spec_without_frontend_message_names_s2_audit(self):
        with pytest.raises(SystemExit, match="S2"):
            _check(_parse(_REF_SPEC))

    def test_ref_spec_without_frontend_message_lists_choices(self):
        with pytest.raises(SystemExit) as excinfo:
            _check(_parse(_REF_SPEC))
        assert all(name in str(excinfo.value) for name in REFERENCE_SPEC_FRONTENDS)

    def test_ref_spec_with_frontend_passes(self):
        _check(_parse([*_REF_SPEC, "--reference-spec-frontend", NO_VAD_MQ]))

    @pytest.mark.parametrize("mode", ["none", "capacity"])
    def test_frontend_with_other_mode_exits(self, mode):
        extra = ["--reference-conditioning", mode]
        if mode != "none":
            extra += ["--generator-reference", "cross_utt"]
        with pytest.raises(SystemExit, match="ref_spec"):
            _check(_parse([*extra, "--reference-spec-frontend", NO_VAD_MQ]))

    @pytest.mark.parametrize("mode", ["none", "capacity"])
    def test_other_mode_without_frontend_passes(self, mode):
        _check(_parse(["--reference-conditioning", mode]))

    def test_main_rejects_missing_frontend_before_reading_the_dataset(
        self, monkeypatch
    ):
        from piper_train import __main__ as cli

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "piper_train",
                "--dataset-dir",
                "/nonexistent-dataset-dir",
                "--batch-size",
                "1",
                *_REF_SPEC,
            ],
        )
        with pytest.raises(SystemExit, match="--reference-spec-frontend"):
            cli.main()


# ---------------------------------------------------------------------------
# VitsModel hparam / checkpoint
# ---------------------------------------------------------------------------


class TestVitsModelHparam:
    def test_default_hparam_is_none(self):
        assert _model().hparams.reference_spec_frontend is None

    def test_ref_spec_model_records_frontend(self):
        model = _model(
            reference_conditioning="ref_spec", reference_spec_frontend=NO_VAD_MQ
        )
        assert model.hparams.reference_spec_frontend == NO_VAD_MQ

    def test_unknown_frontend_raises(self):
        with pytest.raises(ValueError, match="frontend"):
            _model(
                reference_conditioning="ref_spec",
                reference_spec_frontend="silero-vad;torchaudio",
            )

    @pytest.mark.parametrize("mode", ["none", "capacity"])
    def test_frontend_with_other_mode_raises(self, mode):
        with pytest.raises(ValueError, match="ref_spec"):
            _model(reference_conditioning=mode, reference_spec_frontend=NO_VAD_MQ)

    def test_frontend_is_saved_in_checkpoint(self, tmp_path):
        from piper_train.vits.lightning import VitsModel

        model = _model(
            reference_conditioning="ref_spec", reference_spec_frontend=NO_VAD_MQ
        )
        path = tmp_path / "ref.ckpt"
        torch.save(
            {
                "state_dict": model.state_dict(),
                "hyper_parameters": dict(model.hparams),
                "pytorch-lightning_version": "2.0.0",
            },
            path,
        )
        loaded = VitsModel.load_from_checkpoint(path, dataset=None)
        assert loaded.hparams.reference_spec_frontend == NO_VAD_MQ

    @pytest.mark.parametrize("mode", ["none", "capacity"])
    def test_old_checkpoint_without_key_loads(self, tmp_path, mode):
        """key の無い旧 checkpoint (none / capacity) は strict に読め、出力も同じ。"""
        from piper_train.vits.lightning import VitsModel

        model = _model(reference_conditioning=mode)
        hyper = dict(model.hparams)
        hyper.pop("reference_spec_frontend")
        path = tmp_path / "old.ckpt"
        torch.save(
            {
                "state_dict": model.state_dict(),
                "hyper_parameters": hyper,
                "pytorch-lightning_version": "2.0.0",
            },
            path,
        )
        loaded = VitsModel.load_from_checkpoint(path, dataset=None, strict=True)
        assert loaded.hparams.reference_spec_frontend is None
        text = torch.randint(1, 40, (1, 7))
        kwargs = {
            "speaker_embeddings": torch.nn.functional.normalize(
                torch.randn(1, 192), dim=-1
            ),
            "noise_scale": 0.0,
            "noise_scale_w": 0.0,
        }
        model.model_g.eval()
        loaded.model_g.eval()
        with torch.no_grad():
            expected = model.model_g.infer(text, torch.tensor([7]), **kwargs)[0]
            actual = loaded.model_g.infer(text, torch.tensor([7]), **kwargs)[0]
        assert torch.equal(actual, expected)
