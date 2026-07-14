"""Tests for the WaveNeXt Stage 1 transfer/loss CLI flags and the
--resume-encoder-only state_dict filter in piper_train.__main__.

Covers:

1. flag registration and defaults (--wavenext-init / --resume-encoder-only /
   --c-mrd / --c-mrstft / --pretrain-mel-steps)
2. ``_filter_encoder_only_state_dict`` drops decoder + discriminator weights
   and keeps the encoder half (v7 partial transfer, 03 doc smoke recipe)
3. the filtered checkpoint passes ``_validate_checkpoint_decoder_arch``
   against a wavenext model (partial-ckpt → None → no raise)
4. an unfiltered mb_istft checkpoint against a wavenext model raises the
   _WRONG_DECODER_ARCH_MESSAGE RuntimeError (validation added to the live
   --resume-from-multispeaker-checkpoint path — regression pin)
"""

from types import SimpleNamespace

import pytest


pytest.importorskip("torch", reason="torch required for piper_train.__main__")

from piper_train.__main__ import (  # noqa: E402
    _detect_decoder_arch_from_state_dict,
    _filter_encoder_only_state_dict,
    _validate_checkpoint_decoder_arch,
    create_parser,
)


_BASE_ARGS = ["--dataset-dir", "/tmp/test", "--batch-size", "4"]


# ---------------------------------------------------------------------------
# CLI flags
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCliFlags:
    def test_defaults(self):
        parser = create_parser()
        args = parser.parse_args(_BASE_ARGS)
        assert args.wavenext_init is None
        assert args.resume_encoder_only is False
        assert args.c_mrd == 0.1
        assert args.c_mrstft == 0.0
        assert args.pretrain_mel_steps == 0

    def test_explicit_values_accepted(self):
        parser = create_parser()
        args = parser.parse_args(
            [
                *_BASE_ARGS,
                "--decoder-arch",
                "wavenext",
                "--wavenext-init",
                "/data/piper/models/wavenext-mel-bsclt.pt",
                "--resume-encoder-only",
                "--c-mrd",
                "0.2",
                "--c-mrstft",
                "1.0",
                "--pretrain-mel-steps",
                "5000",
            ]
        )
        assert args.wavenext_init == "/data/piper/models/wavenext-mel-bsclt.pt"
        assert args.resume_encoder_only is True
        assert args.c_mrd == 0.2
        assert args.c_mrstft == 1.0
        assert args.pretrain_mel_steps == 5000


# ---------------------------------------------------------------------------
# _filter_encoder_only_state_dict
# ---------------------------------------------------------------------------

# mb_istft-like checkpoint keys: encoder half + decoder + discriminators
_MB_ISTFT_LIKE_STATE_DICT = {
    # keep: encoder half (v7 partial transfer targets)
    "model_g.enc_p.emb.weight": None,
    "model_g.enc_q.pre.weight": None,
    "model_g.flow.flows.0.pre.weight": None,
    "model_g.dp.flows.0.pre.weight": None,
    "model_g.spk_proj.0.weight": None,
    "spk_proj_teacher.0.weight": None,
    "dino_center": None,
    # drop: decoder (arch-specific, zero tensor-name overlap with wavenext)
    "model_g.dec.conv_pre.weight": None,
    "model_g.dec.subband_conv_post.0.weight": None,
    "model_g.dec.pqmf.h_proto": None,
    "model_g.dec.istft.inverse_basis": None,
    # drop: discriminators (Stage 1 MPD/MRD must start from scratch)
    "model_d.discriminators.0.convs.0.weight": None,
    "model_d_wavlm.head.weight": None,
}

_KEPT_KEYS = {
    "model_g.enc_p.emb.weight",
    "model_g.enc_q.pre.weight",
    "model_g.flow.flows.0.pre.weight",
    "model_g.dp.flows.0.pre.weight",
    "model_g.spk_proj.0.weight",
    "spk_proj_teacher.0.weight",
    "dino_center",
}


def _wavenext_model_stub():
    """model.hparams.get(...) だけを提供する軽量スタブ。"""
    return SimpleNamespace(hparams={"decoder_arch": "wavenext"})


@pytest.mark.unit
class TestFilterEncoderOnlyStateDict:
    def test_drops_decoder_and_discriminators_keeps_encoder_half(self):
        filtered = _filter_encoder_only_state_dict(_MB_ISTFT_LIKE_STATE_DICT)
        assert set(filtered) == _KEPT_KEYS

    def test_filtered_state_dict_is_partial_checkpoint(self):
        """After filtering there are no decoder keys → tri-state returns None."""
        filtered = _filter_encoder_only_state_dict(_MB_ISTFT_LIKE_STATE_DICT)
        assert _detect_decoder_arch_from_state_dict(filtered) is None

    def test_filtered_checkpoint_passes_wavenext_validation(self):
        """Filtered mb_istft ckpt + cleared hparams tag validates for wavenext.

        --resume-encoder-only の live path 相当: state_dict filter +
        hyper_parameters クリアの組で cross-arch encoder 転移が検証を通る。
        """
        filtered = _filter_encoder_only_state_dict(_MB_ISTFT_LIKE_STATE_DICT)
        checkpoint = {"state_dict": filtered, "hyper_parameters": {}}
        # Must not raise
        _validate_checkpoint_decoder_arch(
            checkpoint, _wavenext_model_stub(), "/fake/mb_istft.ckpt"
        )

    def test_unfiltered_mb_istft_checkpoint_raises_for_wavenext_model(self):
        """Without --resume-encoder-only the arch mismatch must raise.

        Stage 0 実装ギャップ修正の回帰 pin: live な
        --resume-from-multispeaker-checkpoint path に追加された
        _validate_checkpoint_decoder_arch が silent re-init を防ぐ。
        """
        checkpoint = {
            "state_dict": dict(_MB_ISTFT_LIKE_STATE_DICT),
            "hyper_parameters": {},
        }
        with pytest.raises(RuntimeError, match="decoder_arch='mb_istft'") as excinfo:
            _validate_checkpoint_decoder_arch(
                checkpoint, _wavenext_model_stub(), "/fake/mb_istft.ckpt"
            )
        assert "decoder_arch='wavenext'" in str(excinfo.value)
        assert "partial-transfer" in str(excinfo.value)
