"""Tests for v1.12.0 breaking change: HiFi-GAN ckpt rejection.

v1.12.0 unified the decoder to MB-iSTFT-VITS2. Resuming/fine-tuning from
a v1.11.x HiFi-GAN checkpoint is no longer possible — the loader must
detect such checkpoints and emit a clear migration error.

These tests pin the detection logic in
``piper_train.__main__._is_legacy_hifigan_checkpoint`` so we don't:
  - accidentally accept a HiFi-GAN ckpt (silent corruption), or
  - reject a valid MB-iSTFT ckpt (false positive).
"""

import pytest

from piper_train.__main__ import (
    _LEGACY_HIFIGAN_MESSAGE,
    _is_legacy_hifigan_checkpoint,
)


@pytest.mark.unit
class TestIsLegacyHifiganCheckpoint:
    def test_empty_state_dict_returns_false(self):
        assert _is_legacy_hifigan_checkpoint({}) is False

    def test_no_decoder_keys_returns_false(self):
        state_dict = {
            "model_g.enc_p.emb.weight": None,
            "model_g.flow.flows.0.pre.weight": None,
        }
        assert _is_legacy_hifigan_checkpoint(state_dict) is False

    def test_pqmf_marker_recognised_as_mbistft(self):
        state_dict = {
            "model_g.dec.conv_pre.weight": None,
            "model_g.dec.pqmf.h_proto": None,
        }
        assert _is_legacy_hifigan_checkpoint(state_dict) is False

    def test_subband_conv_post_marker_recognised_as_mbistft(self):
        state_dict = {
            "model_g.dec.conv_pre.weight": None,
            "model_g.dec.subband_conv_post.0.weight": None,
        }
        assert _is_legacy_hifigan_checkpoint(state_dict) is False

    def test_decoder_keys_without_mbistft_marker_returns_true(self):
        state_dict = {
            "model_g.dec.conv_pre.weight": None,
            "model_g.dec.ups.0.weight": None,
            "model_g.dec.resblocks.0.convs1.0.weight": None,
            "model_g.dec.conv_post.weight": None,
        }
        assert _is_legacy_hifigan_checkpoint(state_dict) is True

    def test_realistic_hifigan_state_dict_detected(self):
        state_dict = {
            "model_g.enc_p.emb.weight": None,
            "model_g.dec.conv_pre.weight": None,
            "model_g.dec.ups.0.bias": None,
            "model_g.dec.ups.1.weight": None,
            "model_g.dec.resblocks.0.convs1.0.bias": None,
            "model_g.dec.conv_post.weight": None,
            "model_g.dp.flows.0.pre.weight": None,
        }
        assert _is_legacy_hifigan_checkpoint(state_dict) is True

    def test_realistic_mbistft_state_dict_not_detected(self):
        state_dict = {
            "model_g.enc_p.emb.weight": None,
            "model_g.dec.conv_pre.weight": None,
            "model_g.dec.ups.0.weight": None,
            "model_g.dec.subband_conv_post.0.weight": None,
            "model_g.dec.pqmf.h_proto": None,
            "model_g.dec.pqmf.synthesis_filter": None,
            "model_g.dp.flows.0.pre.weight": None,
        }
        assert _is_legacy_hifigan_checkpoint(state_dict) is False

    def test_only_pqmf_no_other_decoder_keys_still_classified_as_mbistft(self):
        state_dict = {"model_g.dec.pqmf.h_proto": None}
        assert _is_legacy_hifigan_checkpoint(state_dict) is False


@pytest.mark.unit
class TestLegacyHifiganMessage:
    def test_path_is_substituted(self):
        msg = _LEGACY_HIFIGAN_MESSAGE.format(path="/foo/bar.ckpt")
        assert "/foo/bar.ckpt" in msg

    def test_mentions_v1_12(self):
        msg = _LEGACY_HIFIGAN_MESSAGE.format(path="x")
        assert "v1.12.0" in msg

    def test_mentions_mb_istft_replacement(self):
        msg = _LEGACY_HIFIGAN_MESSAGE.format(path="x")
        assert "MB-iSTFT" in msg

    def test_links_migration_resources(self):
        msg = _LEGACY_HIFIGAN_MESSAGE.format(path="x")
        assert "huggingface.co/ayousanz/piper-plus-base" in msg
        assert "docs/migration/v1.11-to-v1.12.md" in msg
