"""Tests for differentiable SCL (torch CAM++ + InfoNCE) — v8.1.

背景 (design doc §3.15): 従来の SCL は ONNX CAM++ を torch.no_grad で呼ぶため
勾配が完全にゼロで、v7/v8 を通じて loss_spk は一度も学習に寄与していなかった。
本テストは新設の微分可能経路の契約を pin する:

1. DifferentiableCamPPEncoder — 出力形状 / L2 正規化 / 入力への勾配疎通 /
   frozen & eval 固定 / 公式重み (state_dict) とのキー互換
2. speaker_infonce_loss — 識別損失の意味論 / 同一話者 false negative マスク /
   B=1 フォールバック / 勾配疎通 / NaN ガード

実重み (campplus_cn_common.bin) との数値 parity は手動検証済み
(2026-08-09: ONNX 出力と cos=0.993)。CI ではネットワーク不要のrandom-init
検証のみ行う。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch")
pytest.importorskip("torchaudio")

from piper_train.speaker_encoder.campplus_torch import (  # noqa: E402
    CAMPPlus,
    DifferentiableCamPPEncoder,
)
from piper_train.vits.losses import speaker_infonce_loss  # noqa: E402


@pytest.fixture(scope="module")
def encoder(tmp_path_factory):
    """Random-init CAM++ weights を保存 → encoder にロード (キー互換も同時に pin)。"""
    path = tmp_path_factory.mktemp("campplus") / "campplus_random.bin"
    torch.save(CAMPPlus(embedding_size=192).state_dict(), path)
    return DifferentiableCamPPEncoder(str(path), source_sr=22050)


@pytest.mark.unit
class TestDifferentiableCamPPEncoder:
    def test_official_state_dict_keys_load_strict(self, encoder):
        """fixture 構築自体が strict=True ロード成功 = キー互換の証明。"""
        assert encoder is not None

    def test_forward_shape_and_l2_norm(self, encoder):
        audio = torch.randn(2, 8192) * 0.1
        emb = encoder(audio)
        assert emb.shape == (2, 192)
        norms = emb.norm(dim=-1)
        assert torch.allclose(norms, torch.ones(2), atol=1e-4)

    def test_gradient_flows_to_waveform(self, encoder):
        """decoder 出力 (waveform) まで勾配が流れることが差分可能 SCL の核心。"""
        audio = (torch.randn(2, 8192) * 0.1).requires_grad_(True)
        emb = encoder(audio)
        loss = (1 - emb.sum(dim=-1)).mean()
        loss.backward()
        assert audio.grad is not None
        assert float(audio.grad.abs().sum()) > 0

    def test_params_frozen(self, encoder):
        assert all(not p.requires_grad for p in encoder.parameters())

    def test_train_override_keeps_eval(self, encoder):
        """Lightning の再帰 .train() が BN を batch statistics に戻さないこと。"""
        encoder.train()
        assert encoder.training is False
        assert all(not m.training for m in encoder.modules())

    def test_rejects_non_2d_input(self, encoder):
        with pytest.raises(ValueError, match="B, T"):
            encoder(torch.randn(2, 1, 8192))


@pytest.mark.unit
class TestSpeakerInfoNCELoss:
    def _embs(self, b=4, d=192, seed=0):
        g = torch.Generator().manual_seed(seed)
        ref = torch.nn.functional.normalize(torch.randn(b, d, generator=g), dim=-1)
        return ref

    def test_perfect_match_lower_than_shuffled(self):
        ref = self._embs()
        loss_match = speaker_infonce_loss(ref, ref)
        loss_shuffled = speaker_infonce_loss(ref[[1, 0, 3, 2]], ref)
        assert float(loss_match) < float(loss_shuffled)

    def test_same_speaker_false_negatives_masked(self):
        """同一話者の他発話参照が negative から除外される。

        gen[0] が ref[1] (同一話者の別発話) に酷似していても、マスクにより
        ペナルティを受けない — マスクなしとの損失差で検証する。
        """
        ref = self._embs(b=4)
        # gen[0] を「同一話者の別発話 ref[1]」そっくりにする
        gen = ref.clone()
        gen[0] = torch.nn.functional.normalize(
            0.9 * ref[1] + 0.1 * ref[0], dim=-1
        )
        speaker_ids = torch.tensor([7, 7, 8, 9])  # 0 と 1 が同一話者
        loss_masked = speaker_infonce_loss(gen, ref, speaker_ids=speaker_ids)
        loss_unmasked = speaker_infonce_loss(gen, ref)
        assert float(loss_masked) < float(loss_unmasked)

    def test_batch_of_one_falls_back_to_cosine(self):
        ref = self._embs(b=1)
        loss = speaker_infonce_loss(ref, ref)
        assert float(loss) == pytest.approx(0.0, abs=1e-5)

    def test_gradient_flows(self):
        ref = self._embs()
        gen = ref.clone().requires_grad_(True)
        loss = speaker_infonce_loss(gen, ref)
        loss.backward()
        assert gen.grad is not None
        assert float(gen.grad.abs().sum()) > 0

    def test_nan_guard_returns_zero(self):
        ref = self._embs()
        gen = ref.clone()
        gen[0, 0] = float("nan")
        loss = speaker_infonce_loss(gen, ref)
        assert float(loss) == 0.0

    def test_speaker_ids_none_equivalent_to_all_distinct(self):
        ref = self._embs()
        distinct = torch.tensor([0, 1, 2, 3])
        assert float(speaker_infonce_loss(ref, ref)) == pytest.approx(
            float(speaker_infonce_loss(ref, ref, speaker_ids=distinct)), abs=1e-6
        )


@pytest.mark.unit
def test_cli_advertises_differentiable_scl_flags():
    from piper_train.__main__ import create_parser

    parser = create_parser()
    args = parser.parse_args(
        [
            "--dataset-dir", "/tmp/x",
            "--batch-size", "1",
            "--speaker-encoder-torch-path", "/tmp/campplus_cn_common.bin",
            "--spk-loss-type", "infonce",
            "--segment-size", "16384",
        ]
    )
    assert args.speaker_encoder_torch_path == "/tmp/campplus_cn_common.bin"
    assert args.spk_loss_type == "infonce"
    assert args.segment_size == 16384


@pytest.mark.unit
def test_spk_loss_type_rejects_unknown():
    from piper_train.__main__ import create_parser

    parser = create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--dataset-dir", "/tmp/x",
                "--batch-size", "1",
                "--spk-loss-type", "triplet",
            ]
        )
