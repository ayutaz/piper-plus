"""Tests for the tri-state decoder-arch classifier and SynthesizerTrn factory.

Stage 0 of the WaveNeXt decoder ablation
(docs/design/wavenext-decoder-ablation/03-ablation-plan.md):

- ``_detect_decoder_arch_from_state_dict`` classifies checkpoints as
  ``mb_istft`` / ``wavenext`` / ``hifigan``, or ``None`` for partial
  checkpoints without decoder keys (partial-transfer protection).
- ``_detect_decoder_arch`` prefers the ``hyper_parameters.decoder_arch`` tag
  over state_dict markers (warning on mismatch).
- ``_is_legacy_hifigan_checkpoint`` stays a bool-compatible wrapper so the
  existing rejection tests keep passing unchanged.
- ``SynthesizerTrn(decoder_arch=...)`` dispatches to MBiSTFTGenerator and
  raises NotImplementedError for the not-yet-implemented WaveNeXt archs.
"""

import argparse
import logging
from types import SimpleNamespace

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.__main__ import (  # noqa: E402
    _LEGACY_HIFIGAN_MESSAGE,
    _WRONG_DECODER_ARCH_MESSAGE,
    _detect_decoder_arch,
    _detect_decoder_arch_from_state_dict,
    _is_legacy_hifigan_checkpoint,
    _validate_checkpoint_decoder_arch,
)


# Mock state_dict keys as Stage 1 will produce them (module naming pinned to
# wetdog/BSC-LT: embed / norm / convnext / final_layer_norm / head).
_WAVENEXT_STATE_DICT = {
    "model_g.enc_p.emb.weight": None,
    "model_g.dec.embed.weight": None,
    "model_g.dec.norm.weight": None,
    "model_g.dec.convnext.0.dwconv.weight": None,
    "model_g.dec.convnext.7.gamma": None,
    "model_g.dec.final_layer_norm.weight": None,
    "model_g.dec.head.linear_1.weight": None,
    "model_g.dp.flows.0.pre.weight": None,
}

_MB_ISTFT_STATE_DICT = {
    "model_g.enc_p.emb.weight": None,
    "model_g.dec.conv_pre.weight": None,
    "model_g.dec.ups.0.weight": None,
    "model_g.dec.subband_conv_post.0.weight": None,
    "model_g.dec.pqmf.h_proto": None,
    "model_g.dp.flows.0.pre.weight": None,
}

_HIFIGAN_STATE_DICT = {
    "model_g.enc_p.emb.weight": None,
    "model_g.dec.conv_pre.weight": None,
    "model_g.dec.ups.0.bias": None,
    "model_g.dec.resblocks.0.convs1.0.bias": None,
    "model_g.dec.conv_post.weight": None,
    "model_g.dp.flows.0.pre.weight": None,
}


def _fake_model(decoder_arch="mb_istft"):
    """model.hparams.get(...) だけを提供する軽量スタブ。"""
    return SimpleNamespace(hparams={"decoder_arch": decoder_arch})


@pytest.mark.unit
class TestDetectDecoderArchFromStateDict:
    def test_mb_istft_detected(self):
        assert _detect_decoder_arch_from_state_dict(_MB_ISTFT_STATE_DICT) == "mb_istft"

    @pytest.mark.parametrize(
        "marker_key",
        [
            "model_g.dec.subband_conv_post.0.weight",
            "model_g.dec.pqmf.h_proto",
            "model_g.dec.istft.inverse_basis",
        ],
    )
    def test_each_mb_istft_marker_is_sufficient(self, marker_key):
        assert _detect_decoder_arch_from_state_dict({marker_key: None}) == "mb_istft"

    def test_wavenext_detected(self):
        assert _detect_decoder_arch_from_state_dict(_WAVENEXT_STATE_DICT) == "wavenext"

    def test_hifigan_detected(self):
        assert _detect_decoder_arch_from_state_dict(_HIFIGAN_STATE_DICT) == "hifigan"

    def test_empty_state_dict_returns_none(self):
        assert _detect_decoder_arch_from_state_dict({}) is None

    def test_partial_ckpt_without_decoder_keys_returns_none(self):
        # spk_proj-only partial checkpoints must not raise (v8 partial transfer)
        state_dict = {
            "model_g.spk_proj.0.weight": None,
            "model_g.flow.flows.0.pre.weight": None,
        }
        assert _detect_decoder_arch_from_state_dict(state_dict) is None

    def test_conv_post_is_not_confused_with_subband_conv_post(self):
        # "conv_post" is a substring of "subband_conv_post"; substring matching
        # would classify HiFi-GAN as mb_istft. Pin the startswith behaviour.
        state_dict = {"model_g.dec.conv_post.weight": None}
        assert _detect_decoder_arch_from_state_dict(state_dict) == "hifigan"

    def test_pqmf_contamination_wins_over_wavenext(self):
        # Correctness requirement for Stage 1: lightning.py's unconditional
        # `self.model_g.dec.pqmf = self.pqmf` injection must be gated by
        # decoder arch. If a WaveNeXt checkpoint were contaminated with pqmf
        # buffers, the mb_istft markers (evaluated first) would win and the
        # checkpoint would be misclassified.
        contaminated = dict(_WAVENEXT_STATE_DICT)
        contaminated["model_g.dec.pqmf.h_proto"] = None
        assert _detect_decoder_arch_from_state_dict(contaminated) == "mb_istft"

    def test_wavenext_mock_state_dict_has_no_pqmf_keys(self):
        # Pin the Stage 1 expectation itself: a proper WaveNeXt checkpoint
        # contains no model_g.dec.pqmf.* keys (re-verified against a real
        # checkpoint in Stage 1).
        assert not any(
            k.startswith("model_g.dec.pqmf.") for k in _WAVENEXT_STATE_DICT
        )


@pytest.mark.unit
class TestDetectDecoderArchTagPriority:
    def test_tag_wins_over_marker_with_warning(self, caplog):
        checkpoint = {
            "state_dict": _MB_ISTFT_STATE_DICT,
            "hyper_parameters": {"decoder_arch": "wavenext"},
        }
        with caplog.at_level(logging.WARNING):
            assert _detect_decoder_arch(checkpoint) == "wavenext"
        assert "decoder_arch mismatch" in caplog.text

    def test_tag_matching_marker_no_warning(self, caplog):
        checkpoint = {
            "state_dict": _MB_ISTFT_STATE_DICT,
            "hyper_parameters": {"decoder_arch": "mb_istft"},
        }
        with caplog.at_level(logging.WARNING):
            assert _detect_decoder_arch(checkpoint) == "mb_istft"
        assert "decoder_arch mismatch" not in caplog.text

    def test_no_tag_falls_back_to_marker(self):
        checkpoint = {"state_dict": _HIFIGAN_STATE_DICT, "hyper_parameters": {}}
        assert _detect_decoder_arch(checkpoint) == "hifigan"

    def test_missing_hyper_parameters_falls_back_to_marker(self):
        checkpoint = {"state_dict": _WAVENEXT_STATE_DICT}
        assert _detect_decoder_arch(checkpoint) == "wavenext"


@pytest.mark.unit
class TestBoolWrapperCompat:
    """_is_legacy_hifigan_checkpoint == (arch == 'hifigan') を pin する。"""

    def test_hifigan_is_true(self):
        assert _is_legacy_hifigan_checkpoint(_HIFIGAN_STATE_DICT) is True

    def test_mb_istft_is_false(self):
        assert _is_legacy_hifigan_checkpoint(_MB_ISTFT_STATE_DICT) is False

    def test_wavenext_is_false(self):
        assert _is_legacy_hifigan_checkpoint(_WAVENEXT_STATE_DICT) is False

    def test_partial_ckpt_is_false(self):
        assert _is_legacy_hifigan_checkpoint({"model_g.spk_proj.0.weight": None}) is False


@pytest.mark.unit
class TestValidateCheckpointDecoderArch:
    def test_hifigan_raises_legacy_message(self):
        checkpoint = {"state_dict": _HIFIGAN_STATE_DICT}
        with pytest.raises(RuntimeError, match="v1.12.0"):
            _validate_checkpoint_decoder_arch(
                checkpoint, _fake_model("mb_istft"), "/foo/legacy.ckpt"
            )

    def test_arch_mismatch_raises_wrong_arch_message(self):
        checkpoint = {"state_dict": _WAVENEXT_STATE_DICT}
        with pytest.raises(RuntimeError, match="decoder_arch='wavenext'"):
            _validate_checkpoint_decoder_arch(
                checkpoint, _fake_model("mb_istft"), "/foo/wavenext.ckpt"
            )

    def test_matching_arch_passes(self):
        checkpoint = {"state_dict": _MB_ISTFT_STATE_DICT}
        _validate_checkpoint_decoder_arch(
            checkpoint, _fake_model("mb_istft"), "/foo/ok.ckpt"
        )

    def test_partial_ckpt_passes(self):
        checkpoint = {"state_dict": {"model_g.spk_proj.0.weight": None}}
        _validate_checkpoint_decoder_arch(
            checkpoint, _fake_model("mb_istft"), "/foo/partial.ckpt"
        )

    def test_model_without_decoder_arch_hparam_defaults_to_mb_istft(self):
        # Old VitsModel hparams (pre decoder_arch) must behave as mb_istft
        checkpoint = {"state_dict": _MB_ISTFT_STATE_DICT}
        model = SimpleNamespace(hparams={})
        _validate_checkpoint_decoder_arch(checkpoint, model, "/foo/old.ckpt")

    def test_wrong_arch_message_substitutes_all_fields(self):
        msg = _WRONG_DECODER_ARCH_MESSAGE.format(
            path="/foo/bar.ckpt", ckpt_arch="wavenext", model_arch="mb_istft"
        )
        assert "/foo/bar.ckpt" in msg
        assert "wavenext" in msg
        assert "mb_istft" in msg
        assert "docs/design/wavenext-decoder-ablation/03-ablation-plan.md" in msg

    def test_legacy_message_still_links_migration_resources(self):
        msg = _LEGACY_HIFIGAN_MESSAGE.format(path="x")
        assert "docs/migration/v1.11-to-v1.12.md" in msg


def _make_synthesizer(**overrides):
    from piper_train.vits.models import SynthesizerTrn

    kwargs = dict(
        n_vocab=97,
        spec_channels=513,
        segment_size=32,
        inter_channels=192,
        hidden_channels=192,
        filter_channels=768,
        n_heads=2,
        n_layers=6,
        kernel_size=3,
        p_dropout=0.1,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
        n_speakers=1,
        n_languages=1,
        gin_channels=0,
    )
    kwargs.update(overrides)
    return SynthesizerTrn(**kwargs)


@pytest.mark.unit
class TestSynthesizerTrnFactory:
    def test_default_is_mb_istft(self):
        from piper_train.vits.mb_istft import MBiSTFTGenerator

        model = _make_synthesizer()
        assert model.decoder_arch == "mb_istft"
        assert isinstance(model.dec, MBiSTFTGenerator)

    def test_explicit_mb_istft(self):
        from piper_train.vits.mb_istft import MBiSTFTGenerator

        model = _make_synthesizer(decoder_arch="mb_istft")
        assert isinstance(model.dec, MBiSTFTGenerator)

    @pytest.mark.parametrize("arch", ["wavenext", "wavenext2"])
    def test_wavenext_archs_raise_not_implemented(self, arch):
        with pytest.raises(NotImplementedError, match=arch):
            _make_synthesizer(decoder_arch=arch)

    def test_unknown_arch_raises_value_error(self):
        with pytest.raises(ValueError, match="bogus"):
            _make_synthesizer(decoder_arch="bogus")


@pytest.mark.unit
class TestCliFlag:
    def test_decoder_arch_flag_registered_with_default(self):
        from piper_train.vits.lightning import VitsModel

        parser = argparse.ArgumentParser()
        VitsModel.add_model_specific_args(parser)
        args = parser.parse_args(["--batch-size", "1"])
        assert args.decoder_arch == "mb_istft"

    def test_decoder_arch_flag_accepts_wavenext(self):
        from piper_train.vits.lightning import VitsModel

        parser = argparse.ArgumentParser()
        VitsModel.add_model_specific_args(parser)
        args = parser.parse_args(["--batch-size", "1", "--decoder-arch", "wavenext"])
        assert args.decoder_arch == "wavenext"

    def test_decoder_arch_flag_rejects_unknown(self):
        from piper_train.vits.lightning import VitsModel

        parser = argparse.ArgumentParser()
        VitsModel.add_model_specific_args(parser)
        with pytest.raises(SystemExit):
            parser.parse_args(["--batch-size", "1", "--decoder-arch", "bogus"])
