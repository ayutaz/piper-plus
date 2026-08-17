"""v10b Phase B (H-1 / H-2b) の CLI + 配線テスト。

新フラグ 3 本を CLI から decoder まで通す経路の固定:

    --upsample-mode {transposed,resize}   (H-1)
    --pqmf-taps INT                       (H-2b)
    --trainable-pqmf-synthesis            (H-2b)

**最重要の配線点**: ``lightning.py`` は GT analysis 用に自前で ``PQMF`` を作り
``self.model_g.dec.pqmf = self.pqmf`` で decoder のバンクを **上書きする**
(sub-band STFT loss の target と decoder synthesis を同一バンクに保つため)。
従って ``MBiSTFTGenerator(pqmf_taps=...)`` だけを配線すると
**VitsModel 経由の学習では taps 指定が黙って捨てられる**。
``test_lightning_shared_pqmf_honours_taps_and_trainable`` がこの穴を塞ぐ
(M1 の logdet→KL 配線漏れと同型の「default では何も壊れないので他のテストが
全部生き残る」種類のリスク)。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")


def _parse_train_args(extra=()):
    from piper_train.__main__ import create_parser

    parser = create_parser()
    return parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra])


@pytest.mark.unit
class TestV10bDecoderCli:
    def test_defaults_preserve_v10a_behaviour(self):
        args = _parse_train_args()
        assert args.upsample_mode == "transposed"
        assert args.pqmf_taps == 62
        assert args.trainable_pqmf_synthesis is False

    def test_opt_in_flags_parse(self):
        args = _parse_train_args(
            ("--upsample-mode", "resize", "--pqmf-taps", "126", "--trainable-pqmf-synthesis")
        )
        assert args.upsample_mode == "resize"
        assert args.pqmf_taps == 126
        assert args.trainable_pqmf_synthesis is True

    def test_invalid_upsample_mode_rejected_by_argparse(self):
        with pytest.raises(SystemExit):
            _parse_train_args(("--upsample-mode", "transposed-conv"))

    def test_pqmf_taps_choices_are_the_codesigned_presets(self):
        """co-design されていない taps は CLI で弾く (PQMF_DESIGN と同期)。"""
        from piper_train.vits.mb_istft import PQMF_DESIGN

        for taps in PQMF_DESIGN:
            assert _parse_train_args(("--pqmf-taps", str(taps))).pqmf_taps == taps
        with pytest.raises(SystemExit):
            _parse_train_args(("--pqmf-taps", "94"))


def _synthesizer(**overrides):
    try:
        from piper_train.vits.models import SynthesizerTrn
    except ImportError as e:  # pragma: no cover
        pytest.skip(f"Training dependencies not available: {e}")
    kwargs = dict(
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
    kwargs.update(overrides)
    torch.manual_seed(0)
    return SynthesizerTrn(**kwargs)


@pytest.mark.unit
class TestSynthesizerPlumbing:
    def test_defaults_are_v10a_compatible(self):
        model = _synthesizer()
        assert model.dec.upsample_mode == "transposed"
        assert model.dec.pqmf.taps == 62
        assert model.dec.pqmf.trainable_synthesis is False

    def test_synthesizer_forwards_all_three_options(self):
        model = _synthesizer(
            upsample_mode="resize", pqmf_taps=126, trainable_pqmf_synthesis=True
        )
        assert model.dec.upsample_mode == "resize"
        assert model.dec.pqmf.taps == 126
        assert model.dec.pqmf.trainable_synthesis is True

    def test_resize_synthesizer_forward_runs(self):
        model = _synthesizer(upsample_mode="resize")
        torch.manual_seed(1)
        b, t_text, t_frames = 2, 20, 48
        x = torch.randint(1, 50, (b, t_text))
        x_lengths = torch.tensor([t_text, t_text])
        y = torch.randn(b, 513, t_frames)
        y_lengths = torch.tensor([t_frames, t_frames])
        emb = torch.nn.functional.normalize(torch.randn(b, 192), dim=-1)
        out = model(x, x_lengths, y, y_lengths, speaker_embeddings=emb)
        assert torch.isfinite(out.waveform).all()


def _vits_model(**overrides):
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:  # pragma: no cover
        pytest.skip(f"Training dependencies not available: {e}")
    # tests/test_channels_last.py::_make_model と同型 (dataset=None で
    # datamodule 経路に入らない最小構成)。
    kwargs = dict(
        num_symbols=97,
        num_speakers=2,
        num_languages=2,
        dataset=None,
        batch_size=4,
        learning_rate=2e-5,
        use_wavlm_discriminator=False,
        upsample_rates=(4, 4),
        upsample_kernel_sizes=(16, 16),
    )
    kwargs.update(overrides)
    torch.manual_seed(0)
    return VitsModel(**kwargs)


@pytest.mark.unit
class TestLightningPlumbing:
    def test_defaults_are_v10a_compatible(self):
        model = _vits_model()
        assert model.model_g.dec.upsample_mode == "transposed"
        assert model.pqmf.taps == 62
        assert model.pqmf.trainable_synthesis is False

    def test_upsample_mode_reaches_the_decoder(self):
        model = _vits_model(upsample_mode="resize")
        assert model.model_g.dec.upsample_mode == "resize"

    def test_lightning_shared_pqmf_honours_taps_and_trainable(self):
        """lightning が作る共有 PQMF に taps / trainable が伝わっていること。

        ``VitsModel.__init__`` は ``self.pqmf = PQMF(...)`` を作って
        ``self.model_g.dec.pqmf`` を上書きするため、この 1 行に引数を渡し
        忘れると decoder 側の指定が黙って消える。default では何も壊れない
        ので、この統合点を見るテストだけが検出できる。
        """
        model = _vits_model(pqmf_taps=126, trainable_pqmf_synthesis=True)
        assert model.pqmf.taps == 126, "共有 PQMF に --pqmf-taps が渡っていない"
        assert model.pqmf.trainable_synthesis is True
        # decoder と GT analysis は同一インスタンスを共有し続ける
        assert model.model_g.dec.pqmf is model.pqmf
        assert model.model_g.dec.pqmf.taps == 126

    def test_trainable_synthesis_filter_is_in_generator_parameters(self):
        """学習可能合成フィルタが optimizer の対象 (model_g.parameters()) に入る。"""
        model = _vits_model(trainable_pqmf_synthesis=True)
        names = [n for n, _ in model.model_g.named_parameters()]
        assert any("pqmf.synthesis_filter" in n for n in names), names[:5]
