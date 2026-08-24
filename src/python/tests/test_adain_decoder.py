"""v11 P3: decoder per-resblock AdaIN (--use-adain-decoder) の TDD。

docs/design/zero-shot-v11-conditioning-design.md §5.1 (a-2) / §10.5:
Phase 0 診断で decoder 描画段が SECS 損失の主座 (~78%) と確定し、P3
(per-resblock AdaIN、StyleTTS 2 系譜) が最優先アームに繰り上がった。

固定する契約:

* **default off = v10b bit 互換** (state_dict キー・forward とも不変)。
* **zero-init 恒等**: y = x + γ̂(g)·IN(x) + β(g) の残差形なので γ̂=β=0 で
  恒等 = on 直後の出力が off と bit 一致 (StyleTTS 原形 (1+γ)·IN(x)+β は
  γ̂=0 でも IN(x)≠x となり退避保証を満たせないための設計 deviation)。
* **s1 重心レイアウト** (LOO: s1 ≫ s2 > 入口): s1 全 resblock + 後段は
  floor 半分 + 入口なし。medium 実構成で +0.46M params (doc §5.1 見積 +0.45M)。
* **帯域 gate**: γ/β は発話あたり 1 回計算の時間 broadcast — 時間格子に同期
  した変調機構を持たないため、ランダム初期化 decoder で comb 指標が悪化しない
  (on < off + 0.5dB、片側 gate — 実測は on 側が系統的に低いため両側 |diff| は
  改善で fail する。IN の位相副作用リスクの pin、doc §7.3-6)。
* **勾配経路**: FiLM をゼロ化しても AdaIN 経由で g → spk_proj に勾配が届く。
* **ONNX**: 単一 graph / speaker_embedding [1,192] 契約不変 / torch-ORT parity。
"""

from __future__ import annotations

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.mb_istft import AdaIN1d, MBiSTFTGenerator  # noqa: E402


SR = 22050
# 白色 latent 96 frame → fullband 24576 サンプル (1.11 秒) で comb_metrics の
# 下限 0.5 秒を満たす (test_decoder_upsample_mode.py と同一手法)。
N_LATENT_FRAMES = 96


def _make_generator(seed: int = 0, **overrides) -> MBiSTFTGenerator:
    """本走同等の decoder 構成 (medium: 256→128/64ch、resblock 3 本/段)。"""
    torch.manual_seed(seed)
    kwargs = {
        "initial_channel": 192,
        "resblock": "2",
        "resblock_kernel_sizes": (3, 5, 7),
        "resblock_dilation_sizes": ((1, 2), (2, 6), (3, 12)),
        "upsample_rates": (4, 4),
        "upsample_initial_channel": 256,
        "upsample_kernel_sizes": (16, 16),
        "gin_channels": 512,
    }
    kwargs.update(overrides)
    return MBiSTFTGenerator(**kwargs)


def _paired_generators(seed: int = 0, adain_std: float = 0.0):
    """同一重みの (off, on) ペア。adain_std > 0 で AdaIN fc を乱数化する。"""
    gen_off = _make_generator(seed)
    gen_on = _make_generator(seed, use_adain_decoder=True)
    missing, unexpected = gen_on.load_state_dict(gen_off.state_dict(), strict=False)
    assert not unexpected
    assert all(k.startswith("adain_layers.") for k in missing), missing
    if adain_std > 0:
        rng = torch.Generator().manual_seed(seed + 100)
        with torch.no_grad():
            for m in gen_on.adain_layers.values():
                m.fc.weight.copy_(
                    torch.randn(m.fc.weight.shape, generator=rng) * adain_std
                )
                m.fc.bias.copy_(torch.randn(m.fc.bias.shape, generator=rng) * adain_std)
    gen_off.eval()
    gen_on.eval()
    return gen_off, gen_on


def _inputs(seed: int = 0, frames: int = 16):
    g = torch.Generator().manual_seed(seed + 7)
    x = torch.randn(1, 192, frames, generator=g)
    spk = torch.randn(1, 512, 1, generator=g)
    return x, spk


# ---------------------------------------------------------------------------
# AdaIN1d 単体
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAdaIN1dModule:
    def test_zero_init_is_exact_identity(self):
        """γ̂=β=0 (zero-init) で y == x が bit 一致 (退避保証の要)。"""
        adain = AdaIN1d(gin_channels=8, channels=4)
        x = torch.randn(2, 4, 32)
        g = torch.randn(2, 8, 1)
        y = adain(x, g)
        assert torch.equal(y, x)

    def test_residual_form_uses_instance_normalized_branch(self):
        """γ̂=1, β=0 なら y = x + IN(x) (変調枝は正規化座標で書かれる)。"""
        adain = AdaIN1d(gin_channels=8, channels=4)
        with torch.no_grad():
            adain.fc.weight.zero_()
            # bias 前半 (γ̂) = 1、後半 (β) = 0
            adain.fc.bias.copy_(torch.cat([torch.ones(4), torch.zeros(4)]))
        x = torch.randn(2, 4, 64)
        g = torch.zeros(2, 8, 1)
        branch = adain(x, g) - x
        # IN: 各 (sample, channel) の時間統計が除去されている
        assert float(branch.mean(dim=-1).abs().max()) < 1e-5
        assert torch.allclose(
            branch.std(dim=-1, unbiased=False),
            torch.ones(2, 4),
            atol=1e-3,
        )

    def test_beta_shifts_the_output_per_channel(self):
        adain = AdaIN1d(gin_channels=8, channels=4)
        with torch.no_grad():
            adain.fc.weight.zero_()
            adain.fc.bias.copy_(
                torch.cat([torch.zeros(4), torch.tensor([1.0, -2.0, 0.5, 0.0])])
            )
        x = torch.randn(1, 4, 16)
        y = adain(x, torch.zeros(1, 8, 1))
        torch.testing.assert_close(
            y - x, torch.tensor([1.0, -2.0, 0.5, 0.0]).reshape(1, 4, 1).expand(1, 4, 16)
        )

    def test_affine_depends_on_g(self):
        """γ/β が実際に g の関数である (broadcast 定数ではない)。"""
        torch.manual_seed(3)
        adain = AdaIN1d(gin_channels=8, channels=4)
        with torch.no_grad():
            adain.fc.weight.normal_(0.0, 0.5)
        x = torch.randn(1, 4, 16)
        y1 = adain(x, torch.randn(1, 8, 1))
        y2 = adain(x, torch.randn(1, 8, 1))
        assert float((y1 - y2).abs().mean()) > 1e-4


# ---------------------------------------------------------------------------
# Generator: default off の bit 互換 / state_dict 後方互換
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGeneratorOffCompat:
    def test_default_is_off_and_adds_no_modules(self):
        gen = _make_generator()
        assert gen.use_adain_decoder is False
        assert not hasattr(gen, "adain_layers")
        assert not any("adain" in k for k in gen.state_dict())

    def test_off_state_dict_loads_into_off_model(self):
        """off 同士は strict load 可能 (既存 ckpt の後方互換)。"""
        gen_a = _make_generator(seed=0)
        gen_b = _make_generator(seed=1)
        gen_b.load_state_dict(gen_a.state_dict())  # strict=True default

    def test_on_model_reports_only_adain_keys_missing_from_off_ckpt(self):
        """v10b ckpt → on モデルへの load で欠けるのは adain_layers.* のみ。"""
        gen_off = _make_generator(seed=0)
        gen_on = _make_generator(seed=0, use_adain_decoder=True)
        missing, unexpected = gen_on.load_state_dict(gen_off.state_dict(), strict=False)
        assert not unexpected
        assert missing and all(k.startswith("adain_layers.") for k in missing)

    def test_requires_speaker_conditioning(self):
        with pytest.raises(ValueError, match="gin_channels"):
            _make_generator(gin_channels=0, use_adain_decoder=True)


# ---------------------------------------------------------------------------
# レイアウト: s1 重心 (doc §10.5「中解像度 s1 重心・入口は縮小可」)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAdaINLayout:
    def test_s1_all_resblocks_s2_floor_half_no_entrance(self):
        """medium 構成: s1 (128ch) は resblock 3 本全部、s2 (64ch) は
        floor(3/2)=1 本、入口 (conv_pre 段 256ch) にはなし。"""
        gen = _make_generator(use_adain_decoder=True)
        assert set(gen.adain_layers.keys()) == {"0", "1", "2", "3"}
        for key in ("0", "1", "2"):  # stage 0 (s1)
            assert gen.adain_layers[key].channels == 128
        assert gen.adain_layers["3"].channels == 64  # stage 1 (s2) 先頭のみ
        # 入口段 (256ch) の AdaIN は存在しない
        assert not any(m.channels == 256 for m in gen.adain_layers.values())

    def test_parameter_budget_matches_the_design_estimate(self):
        """+0.46M params ≈ +0.92MB fp16 (doc §5.1 a-2 の +0.45M/+0.9MB 見積、
        FP16 40MB gate の残り ~1.2MB 内)。"""
        gen = _make_generator(use_adain_decoder=True)
        n = sum(p.numel() for p in gen.adain_layers.parameters())
        # 3×(512·256+256) + 1×(512·128+128) = 525,312 - 65,664 = 459,648
        assert n == 3 * (512 * 256 + 256) + (512 * 128 + 128)
        assert n * 2 / 1e6 < 1.0, "fp16 バイト数が +1MB を超えている"

    def test_single_kernel_config_gets_no_s2_site(self):
        """num_kernels=1 では floor(1/2)=0 → s2 サイトなし (境界)。"""
        gen = _make_generator(
            resblock_kernel_sizes=(3,),
            resblock_dilation_sizes=((1, 2),),
            use_adain_decoder=True,
        )
        assert set(gen.adain_layers.keys()) == {"0"}


# ---------------------------------------------------------------------------
# zero-init 恒等 / flag が forward に効く / 勾配経路
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestForwardBehaviour:
    def test_zero_init_on_is_bit_identical_to_off(self):
        gen_off, gen_on = _paired_generators(seed=0, adain_std=0.0)
        x, g = _inputs(0)
        with torch.no_grad():
            fb_off, sub_off = gen_off(x, g)
            fb_on, sub_on = gen_on(x, g)
        assert torch.equal(fb_on, fb_off)
        assert torch.equal(sub_on, sub_off)

    def test_on_differs_once_adain_weights_are_nonzero(self):
        gen_off, gen_on = _paired_generators(seed=0, adain_std=0.1)
        x, g = _inputs(0)
        with torch.no_grad():
            fb_off, _ = gen_off(x, g)
            fb_on, _ = gen_on(x, g)
        assert float((fb_on - fb_off).abs().mean()) > 1e-6, (
            "AdaIN 重みが非ゼロでも出力が変わらない (forward に配線されていない)"
        )

    def test_g_none_skips_adain(self):
        """g=None (無条件 forward) では AdaIN を踏まない (FiLM guard と同じ)。"""
        _, gen_on = _paired_generators(seed=0, adain_std=0.5)
        x, _ = _inputs(0)
        with torch.no_grad():
            gen_on(x, g=None)  # should not raise

    def test_gradient_reaches_g_through_adain_alone(self):
        """FiLM を全ゼロ化しても AdaIN 経由で g に勾配が届く。"""
        _, gen_on = _paired_generators(seed=0, adain_std=0.1)
        gen_on.train()
        with torch.no_grad():
            gen_on.cond.weight.zero_()
            gen_on.cond.bias.zero_()
            for layer in gen_on.cond_layers:
                layer.weight.zero_()
                layer.bias.zero_()
        x, g = _inputs(0)
        g = g.requires_grad_(True)
        fb, _ = gen_on(x, g)
        fb.mean().backward()
        assert g.grad is not None
        assert float(g.grad.abs().sum()) > 0.0

    def test_zero_init_adain_weights_still_receive_gradient(self):
        """zero-init でも fc 重み自身には非ゼロ勾配 (学習が bootstrap する)。"""
        _, gen_on = _paired_generators(seed=0, adain_std=0.0)
        gen_on.train()
        x, g = _inputs(0)
        fb, _ = gen_on(x, g)
        fb.mean().backward()
        for key, m in gen_on.adain_layers.items():
            assert m.fc.weight.grad is not None, f"adain_layers[{key}] に勾配なし"
            assert float(m.fc.weight.grad.abs().sum()) > 0.0, (
                f"adain_layers[{key}].fc.weight の勾配が全ゼロ"
            )


@pytest.mark.unit
class TestGradientReachesSpkProj:
    def test_spk_proj_receives_gradient_via_adain(self):
        """SynthesizerTrn: dec FiLM をゼロ化しても AdaIN 経由で spk_proj に
        勾配が流れる (P3 の狙い = decoder 描画段が話者勾配の主搬送路になる)。"""
        from piper_train.vits.models import SynthesizerTrn

        torch.manual_seed(0)
        model = SynthesizerTrn(
            n_vocab=40,
            spec_channels=513,
            segment_size=32,
            inter_channels=192,
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
            upsample_initial_channel=256,
            upsample_kernel_sizes=(16, 16),
            n_speakers=4,
            n_languages=1,
            gin_channels=512,
            use_sdp=False,
            prosody_dim=0,
            use_adain_decoder=True,
        )
        with torch.no_grad():
            model.dec.cond.weight.zero_()
            model.dec.cond.bias.zero_()
            for layer in model.dec.cond_layers:
                layer.weight.zero_()
                layer.bias.zero_()
            for m in model.dec.adain_layers.values():
                m.fc.weight.normal_(0.0, 0.1)
        emb = torch.nn.functional.normalize(torch.randn(1, 192), dim=-1)
        g = model._get_speaker_condition(emb)
        z = torch.randn(1, 192, 16)
        fb, _ = model.dec(z, g=g)
        fb.mean().backward()
        grads = [
            p.grad.abs().sum()
            for p in model.spk_proj.parameters()
            if p.grad is not None
        ]
        assert grads and float(sum(grads)) > 0.0, (
            "spk_proj に勾配が届いていない (AdaIN の g 経路が切れている)"
        )


# ---------------------------------------------------------------------------
# 帯域 gate: comb 指標の on/off 非悪化 (IN の位相副作用リスクの pin)
# ---------------------------------------------------------------------------


def _comb_excess_of(wav: torch.Tensor) -> float:
    """E-4 と同一定義のコム物理量 (tests/ は isolation gate の scope 外)。"""
    from piper_train.tools.measure_comb_artifacts import comb_metrics

    y = wav.detach().reshape(-1).to(torch.float64).numpy()
    y = y / (np.sqrt((y**2).mean()) + 1e-9)
    m = comb_metrics(y, SR)
    assert m is not None
    return float(m["comb_excess_db"])


@pytest.mark.unit
class TestCombBandGate:
    _SEEDS = (0, 1, 2)

    @pytest.mark.parametrize("mode", ["resize", "transposed"])
    @pytest.mark.parametrize("adain_std", [0.1, 0.5])
    def test_active_adain_does_not_worsen_comb_excess(self, mode, adain_std):
        """[帯域 gate、conditioning doc §7.3-6] AdaIN 有効 (非ゼロ重み) の
        ランダム初期化 decoder で comb_excess が悪化しない (on < off + 0.5dB)。

        γ/β は発話あたり 1 回計算の時間 broadcast なので、時間格子に同期した
        変調 (= コムの機序) を作る自由度が構造的にない — これをシードごとに pin。

        gate は片側 (非悪化): 実測では AdaIN は on 側が系統的に**低い**
        (std=0.1 resize で −0.3〜−1.0dB / transposed で −0.7〜−3.9dB、
        std=0.5 では −2.1〜−9.5dB — IN が変調枝の channel 平均を除去し、
        乱数 γ/β が upsample 格子と channel 平均の整列を崩すため)。悪化方向
        のみを 0.5dB で塞ぐのが「comb 非悪化」の意図に忠実な形
        (両側 |diff|<0.5 だと改善で fail する)。
        """
        for seed in self._SEEDS:
            gen_off = _make_generator(seed, upsample_mode=mode)
            gen_on = _make_generator(seed, upsample_mode=mode, use_adain_decoder=True)
            gen_on.load_state_dict(gen_off.state_dict(), strict=False)
            rng = torch.Generator().manual_seed(seed + 100)
            with torch.no_grad():
                for m in gen_on.adain_layers.values():
                    m.fc.weight.copy_(
                        torch.randn(m.fc.weight.shape, generator=rng) * adain_std
                    )
                    m.fc.bias.copy_(
                        torch.randn(m.fc.bias.shape, generator=rng) * adain_std
                    )
            for gen in (gen_off, gen_on):
                gen.eval()
                gen.onnx_export_mode = True
            x, g = _inputs(seed, frames=N_LATENT_FRAMES)
            with torch.no_grad():
                comb_off = _comb_excess_of(gen_off(x, g))
                comb_on = _comb_excess_of(gen_on(x, g))
            assert comb_on < comb_off + 0.5, (
                f"mode={mode} std={adain_std} seed={seed}: comb_excess "
                f"on={comb_on:.3f} dB > off={comb_off:.3f} dB + 0.5 — "
                f"AdaIN (IN の位相副作用) がコムを悪化させている"
            )


# ---------------------------------------------------------------------------
# ONNX export: 契約不変 + torch-ORT parity
# ---------------------------------------------------------------------------


N_VOCAB = 60


def _build_synthesizer(**overrides):
    from piper_train.vits.models import SynthesizerTrn

    torch.manual_seed(1234)
    model = SynthesizerTrn(
        n_vocab=N_VOCAB,
        spec_channels=513,
        segment_size=32,
        inter_channels=192,
        hidden_channels=192,
        filter_channels=256,
        n_heads=2,
        n_layers=2,
        kernel_size=3,
        p_dropout=0.0,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
        n_speakers=4,
        n_languages=1,
        gin_channels=512,
        use_sdp=True,
        prosody_dim=0,
        **overrides,
    )
    return model


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

        model = _build_synthesizer(use_adain_decoder=True)
        # 学習済みらしい挙動にするため AdaIN の zero-init を外す (恒等のままの
        # graph を export しても parity テストが AdaIN 経路を検証しない)
        with torch.no_grad():
            for m in model.dec.adain_layers.values():
                m.fc.weight.normal_(0.0, 0.1)
        model.eval()
        with torch.no_grad():
            model.dec.remove_weight_norm()
        set_export_mode(model, True)
        model.forward = build_infer_forward(model, stochastic=False)

        path = tmp_path_factory.mktemp("adain_onnx") / "adain.onnx"
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

    def test_graph_contains_the_adain_instance_norm(self, exported):
        import onnx

        _model, path = exported
        proto = onnx.load(str(path))
        adain_ops = {
            node.op_type for node in proto.graph.node if "adain_layers" in node.name
        }
        assert "InstanceNormalization" in adain_ops, (
            "AdaIN の InstanceNormalization が graph に出ていない"
        )

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
        assert _parse_train_args().use_adain_decoder is False

    def test_cli_opt_in_parses(self):
        assert _parse_train_args(("--use-adain-decoder",)).use_adain_decoder is True

    def test_lightning_default_keeps_decoder_plain(self):
        model = _vits_model()
        assert model.hparams.use_adain_decoder is False
        assert model.model_g.dec.use_adain_decoder is False
        assert not hasattr(model.model_g.dec, "adain_layers")

    def test_lightning_flag_reaches_the_decoder(self):
        """hparam → SynthesizerTrn → decoder の統合点 pin (ckpt resume /
        ONNX export は hparams 経由で VitsModel を再構築するため)。"""
        model = _vits_model(use_adain_decoder=True)
        assert model.hparams.use_adain_decoder is True
        assert model.model_g.dec.use_adain_decoder is True
        assert len(model.model_g.dec.adain_layers) > 0
