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


class TestSpeakerInfoNCECrossUtt:
    """positive_mode='cross_utt' (v10 roadmap B-1) の回帰テスト。

    Phase 0 Arm B で実証された Goodhart 経路 (same-utt 正例は発話一致だけで
    下がる) を塞ぐ再配線。対角 (same-utt) は負例化ではなく分母から除外する
    footgun 仕様をここで固定する。
    """

    def _embs(self, b=4, d=192, seed=0):
        g = torch.Generator().manual_seed(seed)
        return torch.nn.functional.normalize(
            torch.randn(b, d, generator=g), dim=-1
        )

    def test_requires_speaker_ids(self):
        ref = self._embs()
        with pytest.raises(ValueError, match="speaker_ids"):
            speaker_infonce_loss(ref, ref, positive_mode="cross_utt")

    def test_unknown_positive_mode_rejected(self):
        ref = self._embs()
        with pytest.raises(ValueError, match="positive_mode"):
            speaker_infonce_loss(ref, ref, positive_mode="both")

    def test_diagonal_is_neutral_not_negative(self):
        """対角 (same-utt) は分母から除外される (footgun 固定)。

        b=2 の同一話者ペアでは判別対象が正例 1 つだけになるため、対角が
        正しく除外されていれば loss は埋め込みの中身によらず厳密に 0。
        対角が negative として分母に残る誤実装では gen·ref 対角類似度に
        応じて loss > 0 になる。
        """
        ref = self._embs(b=2)
        same_pair = torch.tensor([7, 7])
        # gen を自分の参照 (対角) そっくりにしても loss は 0 のまま
        gen = ref.clone()
        loss = speaker_infonce_loss(
            gen, ref, speaker_ids=same_pair, positive_mode="cross_utt"
        )
        assert float(loss) == pytest.approx(0.0, abs=1e-6)

    def test_matches_bruteforce_supcon_reference(self):
        """SupCon 式のループ実装 (第一原理) と一致する。"""
        torch.manual_seed(1)
        b, tau = 5, 0.07
        ref = self._embs(b=b, seed=1)
        gen = self._embs(b=b, seed=2)
        speaker_ids = torch.tensor([7, 7, 8, 8, 9])
        expected_rows = []
        sims = (gen @ ref.t()) / tau
        for i in range(b):
            pos = [
                j
                for j in range(b)
                if j != i and speaker_ids[j] == speaker_ids[i]
            ]
            if not pos:
                continue  # 正例なしの行は除外 (speaker 9)
            denom_idx = [j for j in range(b) if j != i]  # 対角のみ除外
            log_denom = torch.logsumexp(sims[i, denom_idx], dim=0)
            expected_rows.append(
                log_denom - sims[i, pos].sum() / len(pos)
            )
        expected = torch.stack(expected_rows).mean()
        actual = speaker_infonce_loss(
            gen, ref, speaker_ids=speaker_ids, positive_mode="cross_utt"
        )
        assert float(actual) == pytest.approx(float(expected), abs=1e-5)

    def test_rewards_speaker_transfer_not_same_utt_match(self):
        """cross_utt では「同一話者の別発話に一致」が「自分の参照に一致」
        より低い loss になる (same_utt とは順序が逆転する)。"""
        ref = self._embs(b=4, seed=3)
        speaker_ids = torch.tensor([7, 7, 8, 8])
        swap = [1, 0, 3, 2]  # 各行が同一話者の別発話を指す
        loss_same_utt_match = speaker_infonce_loss(
            ref, ref, speaker_ids=speaker_ids, positive_mode="cross_utt"
        )
        loss_transfer = speaker_infonce_loss(
            ref[swap], ref, speaker_ids=speaker_ids, positive_mode="cross_utt"
        )
        assert float(loss_transfer) < float(loss_same_utt_match)
        # 従来モードでは逆 (対角一致が最小)
        legacy_match = speaker_infonce_loss(
            ref, ref, speaker_ids=speaker_ids, positive_mode="same_utt"
        )
        legacy_transfer = speaker_infonce_loss(
            ref[swap], ref, speaker_ids=speaker_ids, positive_mode="same_utt"
        )
        assert float(legacy_match) < float(legacy_transfer)

    def test_rows_without_positive_are_dropped(self):
        """batch 内に同一話者別発話を持たない行は損失に寄与しない
        (gen 側の摂動に不変)。"""
        ref = self._embs(b=4, seed=4)
        speaker_ids = torch.tensor([7, 7, 8, 9])
        gen = self._embs(b=4, seed=5)
        loss_a = speaker_infonce_loss(
            gen, ref, speaker_ids=speaker_ids, positive_mode="cross_utt"
        )
        gen2 = gen.clone()
        gen2[2] = torch.nn.functional.normalize(torch.randn(192), dim=-1)
        gen2[3] = torch.nn.functional.normalize(torch.randn(192), dim=-1)
        loss_b = speaker_infonce_loss(
            gen2, ref, speaker_ids=speaker_ids, positive_mode="cross_utt"
        )
        assert float(loss_a) == pytest.approx(float(loss_b), abs=1e-6)

    def test_all_singletons_falls_back_to_same_utt(self):
        """全行が正例なし (samples_per_speaker=1 相当) は same_utt 挙動に
        フォールバックし学習信号を失わない。"""
        ref = self._embs(b=4, seed=6)
        gen = self._embs(b=4, seed=7)
        singletons = torch.tensor([1, 2, 3, 4])
        loss_cross = speaker_infonce_loss(
            gen, ref, speaker_ids=singletons, positive_mode="cross_utt"
        )
        loss_same = speaker_infonce_loss(
            gen, ref, speaker_ids=singletons, positive_mode="same_utt"
        )
        assert float(loss_cross) == pytest.approx(float(loss_same), abs=1e-6)

    def test_gradient_flows(self):
        ref = self._embs(b=4, seed=8)
        gen = self._embs(b=4, seed=9).requires_grad_(True)
        speaker_ids = torch.tensor([7, 7, 8, 8])
        loss = speaker_infonce_loss(
            gen, ref, speaker_ids=speaker_ids, positive_mode="cross_utt"
        )
        loss.backward()
        assert gen.grad is not None
        assert float(gen.grad.abs().sum()) > 0

    def test_nan_guard_returns_zero(self):
        ref = self._embs(b=4, seed=10)
        gen = ref.clone()
        gen[0, 0] = float("nan")
        loss = speaker_infonce_loss(
            gen, ref, speaker_ids=torch.tensor([7, 7, 8, 8]),
            positive_mode="cross_utt",
        )
        assert float(loss) == 0.0


def _tiny_synthesizer():
    """B-3 検証用の最小 SynthesizerTrn (test_grad_probe と同構成)。"""
    try:
        from piper_train.vits.models import SynthesizerTrn
    except ImportError as e:  # pragma: no cover - env without training deps
        pytest.skip(f"Training dependencies not available: {e}")

    return SynthesizerTrn(
        n_vocab=50,
        spec_channels=513,
        segment_size=32,
        inter_channels=64,
        hidden_channels=64,
        filter_channels=128,
        n_heads=2,
        n_layers=1,
        kernel_size=3,
        p_dropout=0.0,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=64,
        upsample_kernel_sizes=(16, 16),
        n_speakers=4,
        gin_channels=64,
        use_sdp=True,
        prosody_dim=16,
    )


class TestSclWaveformDetachedZ:
    """scl_waveform_detached_z (v10 roadmap B-3) の勾配隔離を実モデルで固定。"""

    def _run_forward(self, model):
        torch.manual_seed(0)
        b, t_text, t_frames = 2, 20, 48
        x = torch.randint(1, 50, (b, t_text))
        x_lengths = torch.tensor([t_text, t_text])
        y = torch.randn(b, 513, t_frames)
        y_lengths = torch.tensor([t_frames, t_frames])
        emb = torch.nn.functional.normalize(torch.randn(b, 192), dim=-1)
        out = model(x, x_lengths, y, y_lengths, speaker_embeddings=emb)
        return out, emb

    def test_same_shape_as_forward_waveform(self):
        model = _tiny_synthesizer()
        out, emb = self._run_forward(model)
        o_scl = model.scl_waveform_detached_z(
            out.latents[0], out.ids_slice, speaker_embeddings=emb
        )
        assert o_scl.shape == out.waveform.shape

    def test_gradient_reaches_spk_proj_and_dec_but_not_enc_q(self):
        """SCL 勾配は spk_proj / dec のみ、enc_q (posterior) には流れない。"""
        model = _tiny_synthesizer()
        out, emb = self._run_forward(model)
        o_scl = model.scl_waveform_detached_z(
            out.latents[0], out.ids_slice, speaker_embeddings=emb
        )
        loss = o_scl.pow(2).mean()
        loss.backward()

        def grad_sum(module):
            return sum(
                float(p.grad.abs().sum())
                for p in module.parameters()
                if p.grad is not None
            )

        assert grad_sum(model.spk_proj) > 0, "spk_proj に SCL 勾配が届いていない"
        assert grad_sum(model.dec) > 0, "decoder に SCL 勾配が届いていない"
        assert grad_sum(model.enc_q) == 0, (
            "enc_q (posterior) に勾配が漏れている — z の detach が壊れている"
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


@pytest.mark.unit
def test_cli_spk_loss_positives_and_scl_detach_z():
    from piper_train.__main__ import create_parser

    parser = create_parser()
    # defaults: 従来挙動 (same_utt / detach なし)
    args = parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1"])
    assert args.spk_loss_positives == "same_utt"
    assert args.scl_detach_z is False
    # Phase 1 B-1 + B-3 構成
    args = parser.parse_args(
        [
            "--dataset-dir", "/tmp/x",
            "--batch-size", "1",
            "--spk-loss-positives", "cross_utt",
            "--scl-detach-z",
        ]
    )
    assert args.spk_loss_positives == "cross_utt"
    assert args.scl_detach_z is True


@pytest.mark.unit
def test_cli_spk_loss_positives_rejects_unknown():
    from piper_train.__main__ import create_parser

    parser = create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--dataset-dir", "/tmp/x",
                "--batch-size", "1",
                "--spk-loss-positives", "both",
            ]
        )
