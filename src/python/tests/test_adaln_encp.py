"""v11 P2: enc_p AdaLN-Zero (--use-adaln-encp) の TDD。

docs/design/zero-shot-v11-conditioning-design.md §5.1 (a-1) / §10.5:
Phase 0 D-3 LOO で enc_p は dec と並ぶ実効キャリア (Δtop-1 −0.217) かつ
D-4 で dec と相補・超加法的と確定 → P2 は P3 (dec AdaIN) と同時投入。

固定する契約:

* **default off = v10b bit 互換** (state_dict キー・forward とも不変)。
* **zero-init 恒等**: per-norm head が zero-init (γ̂=β̂=0) なので
  ``x·(1+γ̂)+β̂ = x`` — on 直後の出力が off と bit 一致。
* **P0-4 (lang/spk 干渉分離)**: AdaLN trunk への入力は **g_spk のみ**。
  g_lang は含めない (Phase 0 実測 cos(g_spk, g_lang) = −0.56 —
  lang を含めると AdaLN が言語変調に容量を割いて干渉を再生産する)。
* **M2 (--speaker-cond-layer) と独立共存** (重複の要否は smoke A/B)。
* **パラメータ予算**: 共有 128-d trunk + 12 zero-init head で +0.66M
  (doc §5.1 a-1 の +0.66M ≈ +1.3MB fp16 見積と一致)。
* **ONNX**: speaker_embedding [1,192] 契約不変 / torch-ORT parity。
"""

from __future__ import annotations

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits import attentions  # noqa: E402
from piper_train.vits.models import TextEncoder  # noqa: E402


# ---------------------------------------------------------------------------
# attentions.Encoder 単体
# ---------------------------------------------------------------------------


def _make_encoder(seed: int = 0, **overrides) -> attentions.Encoder:
    torch.manual_seed(seed)
    kwargs = {
        "hidden_channels": 16,
        "filter_channels": 32,
        "n_heads": 2,
        "n_layers": 2,
        "kernel_size": 3,
        "p_dropout": 0.0,
    }
    kwargs.update(overrides)
    return attentions.Encoder(**kwargs)


def _enc_inputs(seed: int = 0, b: int = 2, h: int = 16, t: int = 12):
    g = torch.Generator().manual_seed(seed + 5)
    x = torch.randn(b, h, t, generator=g)
    mask = torch.ones(b, 1, t)
    mask[1, :, t - 3 :] = 0.0
    return x, mask


@pytest.mark.unit
class TestEncoderAdaLN:
    def test_default_has_no_adaln_modules_or_keys(self):
        enc = _make_encoder()
        assert enc.adaln_heads is None
        assert not any("adaln" in k for k in enc.state_dict())

    def test_off_ckpt_loads_into_on_encoder_with_only_adaln_missing(self):
        enc_off = _make_encoder(seed=0)
        enc_on = _make_encoder(seed=0, adaln_gin_channels=8)
        missing, unexpected = enc_on.load_state_dict(enc_off.state_dict(), strict=False)
        assert not unexpected
        assert missing and all(k.startswith("adaln_") for k in missing)

    def test_zero_init_on_is_bit_identical_to_off(self):
        """zero-init head → g_adaln を渡しても素の LN と bit 一致。"""
        enc_off = _make_encoder(seed=0)
        enc_on = _make_encoder(seed=0, adaln_gin_channels=8)
        enc_on.load_state_dict(enc_off.state_dict(), strict=False)
        enc_off.eval()
        enc_on.eval()
        x, mask = _enc_inputs(0)
        g_adaln = torch.randn(2, 8, 1)
        with torch.no_grad():
            y_off = enc_off(x, mask)
            y_on = enc_on(x, mask, g_adaln=g_adaln)
        assert torch.equal(y_on, y_off)

    def test_g_adaln_none_skips_modulation(self):
        """AdaLN 構築済みでも g_adaln=None なら素の LN (単一話者経路)。"""
        enc_off = _make_encoder(seed=0)
        enc_on = _make_encoder(seed=0, adaln_gin_channels=8)
        enc_on.load_state_dict(enc_off.state_dict(), strict=False)
        with torch.no_grad():
            for head in enc_on.adaln_heads:
                head.weight.normal_(0.0, 0.5)
        enc_off.eval()
        enc_on.eval()
        x, mask = _enc_inputs(0)
        with torch.no_grad():
            y_off = enc_off(x, mask)
            y_on = enc_on(x, mask, g_adaln=None)
        assert torch.equal(y_on, y_off)

    def test_output_depends_on_g_adaln_once_heads_are_nonzero(self):
        enc = _make_encoder(seed=1, adaln_gin_channels=8)
        with torch.no_grad():
            for head in enc.adaln_heads:
                head.weight.normal_(0.0, 0.5)
        enc.eval()
        x, mask = _enc_inputs(1)
        with torch.no_grad():
            y1 = enc(x, mask, g_adaln=torch.randn(2, 8, 1))
            y2 = enc(x, mask, g_adaln=torch.randn(2, 8, 1))
        assert float((y1 - y2).abs().mean()) > 1e-6

    def test_gradient_reaches_g_adaln(self):
        """head が非ゼロなら AdaLN 経由で g に勾配が届く (zero-init 直後は
        head 側の勾配 bootstrap — 次テスト — が非ゼロ化を担う)。"""
        enc = _make_encoder(seed=2, adaln_gin_channels=8)
        with torch.no_grad():
            for head in enc.adaln_heads:
                head.weight.normal_(0.0, 0.1)
        enc.train()
        x, mask = _enc_inputs(2)
        g_adaln = torch.randn(2, 8, 1, requires_grad=True)
        y = enc(x, mask, g_adaln=g_adaln)
        y.mean().backward()
        assert g_adaln.grad is not None
        assert float(g_adaln.grad.abs().sum()) > 0.0

    def test_zero_init_heads_still_receive_gradient(self):
        enc = _make_encoder(seed=3, adaln_gin_channels=8)
        enc.train()
        x, mask = _enc_inputs(3)
        y = enc(x, mask, g_adaln=torch.randn(2, 8, 1))
        y.mean().backward()
        for i, head in enumerate(enc.adaln_heads):
            assert head.weight.grad is not None, f"head[{i}] に勾配なし"
            assert float(head.weight.grad.abs().sum()) > 0.0, (
                f"head[{i}].weight の勾配が全ゼロ"
            )

    def test_adaln_coexists_with_m2_cond_injection(self):
        """M2 (cond_layer_idx) と AdaLN は独立に同時適用できる。"""
        enc = _make_encoder(seed=4, adaln_gin_channels=8)
        with torch.no_grad():
            for head in enc.adaln_heads:
                head.weight.normal_(0.0, 0.5)
        enc.eval()
        x, mask = _enc_inputs(4)
        cond = torch.randn(2, 16, 1)
        g_adaln = torch.randn(2, 8, 1)
        with torch.no_grad():
            y_both = enc(x, mask, cond=cond, cond_layer_idx=1, g_adaln=g_adaln)
            y_m2 = enc(x, mask, cond=cond, cond_layer_idx=1)
            y_adaln = enc(x, mask, g_adaln=g_adaln)
        assert float((y_both - y_m2).abs().mean()) > 1e-6
        assert float((y_both - y_adaln).abs().mean()) > 1e-6


# ---------------------------------------------------------------------------
# TextEncoder 配線 (P0-4 の g_spk 限定を含む)
# ---------------------------------------------------------------------------


def _make_text_encoder(seed: int = 0, **overrides) -> TextEncoder:
    torch.manual_seed(seed)
    kwargs = {
        "n_vocab": 40,
        "out_channels": 8,
        "hidden_channels": 16,
        "filter_channels": 32,
        "n_heads": 2,
        "n_layers": 2,
        "kernel_size": 3,
        "p_dropout": 0.0,
        "gin_channels": 8,
    }
    kwargs.update(overrides)
    return TextEncoder(**kwargs)


def _text_inputs(seed: int = 0, b: int = 2, t: int = 10):
    g = torch.Generator().manual_seed(seed + 11)
    x = torch.randint(1, 40, (b, t), generator=g)
    lengths = torch.LongTensor([t, t - 3])
    return x, lengths


@pytest.mark.unit
class TestTextEncoderWiring:
    def test_requires_speaker_conditioning(self):
        with pytest.raises(ValueError, match="gin_channels"):
            _make_text_encoder(gin_channels=0, use_adaln=True)

    def test_default_off_forward_accepts_and_ignores_g_spk(self):
        """off では g_spk を渡しても従来経路と bit 一致 (後方互換)。"""
        enc = _make_text_encoder(seed=0)
        enc.eval()
        x, lengths = _text_inputs(0)
        g = torch.randn(2, 8, 1)
        with torch.no_grad():
            ref = enc(x, lengths, g=g)
            out = enc(x, lengths, g=g, g_spk=torch.randn(2, 8, 1))
        for a, b in zip(ref, out, strict=True):
            assert torch.equal(a, b)

    def test_zero_init_on_matches_off(self):
        enc_off = _make_text_encoder(seed=0)
        enc_on = _make_text_encoder(seed=0, use_adaln=True)
        missing, unexpected = enc_on.load_state_dict(enc_off.state_dict(), strict=False)
        assert not unexpected
        assert missing and all("adaln_" in k for k in missing)
        enc_off.eval()
        enc_on.eval()
        x, lengths = _text_inputs(0)
        g = torch.randn(2, 8, 1)
        g_spk = torch.randn(2, 8, 1)
        with torch.no_grad():
            ref = enc_off(x, lengths, g=g)
            out = enc_on(x, lengths, g=g, g_spk=g_spk)
        for a, b in zip(ref, out, strict=True):
            assert torch.equal(a, b)

    def test_p0_4_adaln_uses_g_spk_only_not_g(self):
        """[P0-4] cond_layer をゼロ化すると出力は g_spk のみに依存する
        (g = g_spk + g_lang を変えても不変) — lang が AdaLN に入らない証拠。"""
        enc = _make_text_encoder(seed=5, use_adaln=True)
        with torch.no_grad():
            enc.cond_layer.weight.zero_()
            enc.cond_layer.bias.zero_()
            for head in enc.encoder.adaln_heads:
                head.weight.normal_(0.0, 0.5)
        enc.eval()
        x, lengths = _text_inputs(5)
        g_spk = torch.randn(2, 8, 1)
        with torch.no_grad():
            out1 = enc(x, lengths, g=torch.randn(2, 8, 1), g_spk=g_spk)
            out2 = enc(x, lengths, g=torch.randn(2, 8, 1), g_spk=g_spk)
            out3 = enc(x, lengths, g=torch.randn(2, 8, 1), g_spk=torch.randn(2, 8, 1))
        assert torch.equal(out1[0], out2[0]), "g (lang 込み) が AdaLN に漏れている"
        assert float((out1[0] - out3[0]).abs().mean()) > 1e-6, (
            "g_spk が AdaLN に届いていない"
        )

    def test_parameter_budget_matches_the_design_estimate(self):
        """本走構成 (gin=512, hidden=192, 6 層): trunk 512·128+128 +
        12 head × (128·384+384) = 660,096 ≈ +0.66M (doc §5.1 a-1)。"""
        enc = _make_text_encoder(
            n_vocab=100,
            out_channels=192,
            hidden_channels=192,
            filter_channels=768,
            n_heads=2,
            n_layers=6,
            gin_channels=512,
            use_adaln=True,
        )
        n = sum(p.numel() for name, p in enc.named_parameters() if "adaln_" in name)
        assert n == (512 * 128 + 128) + 12 * (128 * 384 + 384)
        assert n * 2 / 1e6 < 1.4, "fp16 バイト数が +1.4MB を超えている"


# ---------------------------------------------------------------------------
# SynthesizerTrn / 勾配経路
# ---------------------------------------------------------------------------


def _build_synthesizer(**overrides):
    from piper_train.vits.models import SynthesizerTrn

    torch.manual_seed(1234)
    kwargs: dict = {
        "n_vocab": 60,
        "spec_channels": 513,
        "segment_size": 32,
        "inter_channels": 192,
        "hidden_channels": 192,
        "filter_channels": 256,
        "n_heads": 2,
        "n_layers": 2,
        "kernel_size": 3,
        "p_dropout": 0.0,
        "resblock": "2",
        "resblock_kernel_sizes": (3, 5, 7),
        "resblock_dilation_sizes": ((1, 2), (2, 6), (3, 12)),
        "upsample_rates": (4, 4),
        "upsample_initial_channel": 256,
        "upsample_kernel_sizes": (16, 16),
        "n_speakers": 4,
        "n_languages": 1,
        "gin_channels": 512,
        "use_sdp": True,
        "prosody_dim": 0,
    }
    kwargs.update(overrides)
    return SynthesizerTrn(**kwargs)


@pytest.mark.unit
class TestSynthesizerGradient:
    def test_spk_proj_receives_gradient_via_encp_adaln_alone(self):
        """enc_p の cond_layer をゼロ化 + detach しても AdaLN 経由で
        spk_proj に勾配が流れる (P2 の狙い = prior 彫刻への話者勾配)。"""
        model = _build_synthesizer(use_adaln_encp=True, n_layers=1)
        with torch.no_grad():
            model.enc_p.cond_layer.weight.zero_()
            model.enc_p.cond_layer.bias.zero_()
            for head in model.enc_p.encoder.adaln_heads:
                head.weight.normal_(0.0, 0.1)
        emb = torch.nn.functional.normalize(torch.randn(1, 192), dim=-1)
        g_spk = model._get_speaker_condition(emb)
        x = torch.randint(1, 60, (1, 8))
        lengths = torch.LongTensor([8])
        # g は cond_layer ゼロ化済みなので detach して AdaLN 経路だけを残す
        _x, m_p, _logs_p, _mask = model.enc_p(x, lengths, g=g_spk.detach(), g_spk=g_spk)
        m_p.mean().backward()
        grads = [
            p.grad.abs().sum()
            for p in model.spk_proj.parameters()
            if p.grad is not None
        ]
        assert grads and float(sum(grads)) > 0.0, (
            "spk_proj に勾配が届いていない (AdaLN の g_spk 経路が切れている)"
        )

    def test_infer_runs_with_adaln_enabled(self):
        model = _build_synthesizer(use_adaln_encp=True)
        model.eval()
        with torch.no_grad():
            for head in model.enc_p.encoder.adaln_heads:
                head.weight.normal_(0.0, 0.1)
        emb = torch.nn.functional.normalize(torch.randn(1, 192), dim=-1)
        x = torch.randint(1, 60, (1, 12))
        lengths = torch.LongTensor([12])
        with torch.no_grad():
            out = model.infer(x, lengths, speaker_embeddings=emb)
        assert out.audio.shape[0] == 1 and out.audio.shape[1] == 1
        assert torch.isfinite(out.audio).all()


# ---------------------------------------------------------------------------
# ONNX export: 契約不変 + torch-ORT parity
# ---------------------------------------------------------------------------


N_VOCAB = 60


def _onnx_inputs(n_phonemes: int = 12):
    torch.manual_seed(7)
    text = torch.randint(1, N_VOCAB, (1, n_phonemes), dtype=torch.long)
    lengths = torch.LongTensor([n_phonemes])
    scales = torch.FloatTensor([0.4, 1.0, 0.5])
    emb = torch.nn.functional.normalize(torch.randn(1, 192), dim=-1)
    return text, lengths, scales, emb


@pytest.mark.unit
class TestOnnxExport:
    @pytest.fixture(scope="class")
    def exported(self, tmp_path_factory):
        pytest.importorskip("onnx", reason="onnx required")
        pytest.importorskip("onnxruntime", reason="onnxruntime required")
        pytest.importorskip("onnxscript", reason="onnxscript required for export")
        from piper_train.export_onnx import build_infer_forward, set_export_mode

        model = _build_synthesizer(use_adaln_encp=True)
        # zero-init のままだと graph 上 AdaLN が恒等になり parity テストが
        # 経路を検証しないため、学習済みらしい非ゼロ重みにする
        with torch.no_grad():
            for head in model.enc_p.encoder.adaln_heads:
                head.weight.normal_(0.0, 0.1)
        model.eval()
        with torch.no_grad():
            model.dec.remove_weight_norm()
        set_export_mode(model, True)
        model.forward = build_infer_forward(model, stochastic=False)

        path = tmp_path_factory.mktemp("adaln_onnx") / "adaln.onnx"
        text, lengths, scales, emb = _onnx_inputs()
        torch.onnx.export(
            model=model,
            args=(text, lengths, scales, emb),
            f=str(path),
            opset_version=15,
            input_names=["input", "input_lengths", "scales", "speaker_embedding"],
            output_names=["output", "durations"],
            dynamic_axes={
                "input": {0: "batch_size", 1: "phonemes"},
                "input_lengths": {0: "batch_size"},
                "speaker_embedding": {0: "batch_size"},
                "output": {0: "batch_size", 2: "time"},
                "durations": {0: "batch_size", 1: "phonemes"},
            },
            dynamo=False,
        )
        return model, path

    def test_export_succeeds_and_keeps_the_input_contract(self, exported):
        import onnx

        _model, path = exported
        proto = onnx.load(str(path))
        onnx.checker.check_model(proto, full_check=False)
        names = [i.name for i in proto.graph.input]
        assert names == ["input", "input_lengths", "scales", "speaker_embedding"]
        spk = next(i for i in proto.graph.input if i.name == "speaker_embedding")
        dims = spk.type.tensor_type.shape.dim
        assert len(dims) == 2 and dims[1].dim_value == 192

    def test_onnx_matches_torch(self, exported):
        import onnxruntime

        model, path = exported
        text, lengths, scales, emb = _onnx_inputs()
        with torch.no_grad():
            torch_out, _ = model(text, lengths, scales, emb)
        sess = onnxruntime.InferenceSession(
            str(path), providers=["CPUExecutionProvider"]
        )
        ort_out = sess.run(
            None,
            {
                "input": text.numpy(),
                "input_lengths": lengths.numpy(),
                "scales": scales.numpy(),
                "speaker_embedding": emb.numpy(),
            },
        )[0]
        assert ort_out.shape == tuple(torch_out.shape)
        np.testing.assert_allclose(ort_out, torch_out.numpy(), atol=2e-4, rtol=0)


# ---------------------------------------------------------------------------
# CLI / lightning 配線
# ---------------------------------------------------------------------------


def _parse_train_args(extra=()):
    from piper_train.__main__ import create_parser

    parser = create_parser()
    return parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra])


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
        "learning_rate": 2e-5,
        "use_wavlm_discriminator": False,
        "upsample_rates": (4, 4),
        "upsample_kernel_sizes": (16, 16),
    }
    kwargs.update(overrides)
    torch.manual_seed(0)
    return VitsModel(**kwargs)


@pytest.mark.unit
class TestCliAndLightningWiring:
    def test_cli_default_is_off(self):
        assert _parse_train_args().use_adaln_encp is False

    def test_cli_opt_in_parses(self):
        assert _parse_train_args(("--use-adaln-encp",)).use_adaln_encp is True

    def test_lightning_default_keeps_encoder_plain(self):
        model = _vits_model()
        assert model.hparams.use_adaln_encp is False
        assert model.model_g.enc_p.use_adaln is False
        assert model.model_g.enc_p.encoder.adaln_heads is None

    def test_lightning_flag_reaches_the_text_encoder(self):
        """hparam → SynthesizerTrn → enc_p の統合点 pin (resume / export は
        hparams 経由で VitsModel を再構築するため)。"""
        model = _vits_model(use_adaln_encp=True)
        assert model.hparams.use_adaln_encp is True
        assert model.model_g.enc_p.use_adaln is True
        n_layers = int(model.hparams.n_layers)
        assert len(model.model_g.enc_p.encoder.adaln_heads) == 2 * n_layers
