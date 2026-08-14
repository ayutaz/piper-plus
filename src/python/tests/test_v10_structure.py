"""v10 構造介入 (M1/M2/M3/E1/E2) の TDD red テスト。

docs/design/zero-shot-v10-design.md §4 の構造介入の契約を実装に先行して固定する:

- M2 (``--speaker-cond-layer``, default 0): enc_p の speaker 注入位置。
  default 0 は現行の「transformer 全層通過後に cond_layer(g) を加算」と
  bit 互換。N>=1 で加算を attentions.Encoder の第 N 層入口に移動
  (後段加算は行わない)。v10 推奨値 3 (VITS2 同構成)。
- M3 (``--dp-spk-head``, default off): DP の話者勾配。default off は
  g detach 維持 (現行挙動の固定)。on で ``spk_proj_dp`` 残差ヘッド
  (weight init N(0, 1e-3)) に duration 勾配を集約し、spk_proj 本体 /
  enc_p は保護 (g_dp = g.detach() + spk_proj_dp(g.detach())、
  x = torch.detach(x) は常に維持)。
- M1 (``--use-snac-flow``, default off): ResidualCouplingLayer の snac
  モード。入口で SN(x; g_spk) = (x - m) * exp(-v)、inverse 出口で
  SDN(x; g_spk) = x * exp(v) + m。m, v = ``sn_linear``(g_spk)
  (= Conv1d(gin, 2 * half_channels, 1) を chunk、m が先)、init N(0, 1e-3)、
  v は clamp [-4, 4] (bf16 の exp overflow 対策)。
  logdet = Σ logs - Σ v (mask 内) を ResidualCouplingBlock で累積し、
  SynthesizerTrn.forward が SynthesizerOutput.flow_logdet
  (末尾 field、default None) で返す。off 時は logdet=0 かつ既存経路と
  bit 互換 (新規パラメータなし = v9 ckpt 互換)。
- E2: SN/SDN 統計は話者成分 (g_spk = spk_proj(emb) 由来) のみから予測。
  coupling 内 WN の gin 条件付けは lang 成分のみ (n_languages==1 なら None)。
  ``_get_global_conditioning(..., return_components=True)`` で
  (g_combined, g_spk, g_lang) を取得可能 (既存呼び出しの互換維持)。
- logdet→KL 配線: ``kl_loss(..., logdet=...)`` で loss_kl が
  ``- logdet.sum() / z_mask.sum()`` だけ変化する (符号の根拠:
  log p(z) = log N(flow(z); m_p, logs_p) + logdet なので KL では負号)。
  lightning.training_step_g は SynthesizerOutput.flow_logdet をここに渡す。
- E1 (``--film-init-std``, default 0.0): dec FiLM (cond_layers) の
  zero-init を N(0, std) に置換する opt-in。新設ヘッド sn_linear /
  spk_proj_dp は本フラグと無関係に無条件で N(0, 1e-3)。
- F7: ``--spk-emb-noise-sigma`` の default を 0.05 → 0.0 に変更
  (破壊的 noise を default から除去。v9 スクリプトは明示指定なので不変)。

実装が存在しない段階では新挙動のテストは fail する (TDD red)。
現行挙動の pin (default 経路) は実装前後で常に green であること。
tiny モデルは tests/test_grad_probe.py の ``_tiny_synthesizer`` と
tests/test_scl_differentiable.py の ``TestSclWaveformDetachedZ`` を踏襲。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits import modules  # noqa: E402
from piper_train.vits.losses import kl_loss  # noqa: E402


def _import_models():
    """models.py は mb_istft / monotonic_align 依存のため guard 付き import。"""
    try:
        from piper_train.vits import models
    except ImportError as e:  # pragma: no cover - env without training deps
        pytest.skip(f"Training dependencies not available: {e}")
    return models


def _tiny_synthesizer(**overrides):
    """probe 対象構造 (spk_proj / dec / enc_p / flow) を持つ最小モデル。"""
    models = _import_models()
    kwargs = {
        "n_vocab": 50,
        "spec_channels": 513,
        "segment_size": 32,
        "inter_channels": 64,
        "hidden_channels": 64,
        "filter_channels": 128,
        "n_heads": 2,
        "n_layers": 1,
        "kernel_size": 3,
        "p_dropout": 0.0,
        "resblock": "2",
        "resblock_kernel_sizes": (3, 5, 7),
        "resblock_dilation_sizes": ((1, 2), (2, 6), (3, 12)),
        "upsample_rates": (4, 4),
        "upsample_initial_channel": 64,
        "upsample_kernel_sizes": (16, 16),
        "n_speakers": 4,
        "gin_channels": 64,
        "use_sdp": True,
        "prosody_dim": 16,
    }
    kwargs.update(overrides)
    return models.SynthesizerTrn(**kwargs)


def _run_forward(model, lid=None, seed=0):
    """tiny モデルの training forward を 1 回流す (TestSclWaveformDetachedZ 踏襲)。"""
    torch.manual_seed(seed)
    b, t_text, t_frames = 2, 20, 48
    x = torch.randint(1, 50, (b, t_text))
    x_lengths = torch.tensor([t_text, t_text])
    y = torch.randn(b, 513, t_frames)
    y_lengths = torch.tensor([t_frames, t_frames])
    emb = torch.nn.functional.normalize(torch.randn(b, 192), dim=-1)
    out = model(x, x_lengths, y, y_lengths, lid=lid, speaker_embeddings=emb)
    return out, emb


def _randomize_(module, std=0.2, seed=0):
    """zero-init (post 等) を含む全パラメータを決定的に randomize する。"""
    gen = torch.Generator().manual_seed(seed)
    with torch.no_grad():
        for p in module.parameters():
            p.copy_(torch.randn(p.shape, generator=gen) * std)


# TextEncoder 共通 kwargs (M2 は第 3 層入口注入を試すため n_layers=3)
_ENC_KW = {
    "n_vocab": 40,
    "out_channels": 8,
    "hidden_channels": 32,
    "filter_channels": 64,
    "n_heads": 2,
    "n_layers": 3,
    "kernel_size": 3,
    "p_dropout": 0.0,
    "gin_channels": 16,
}


def _enc_inputs(seed=100):
    gen = torch.Generator().manual_seed(seed)
    x = torch.randint(1, 40, (2, 11), generator=gen)
    x_lengths = torch.tensor([11, 7])
    g1 = torch.randn(2, 16, 1, generator=gen)
    g2 = torch.randn(2, 16, 1, generator=gen)
    return x, x_lengths, g1, g2


# ---------------------------------------------------------------------------
# M2: enc_p の g 注入位置 (--speaker-cond-layer)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestM2SpeakerCondLayer:
    def test_default_g_added_after_encoder(self):
        """現行挙動の pin: default では g は transformer 通過後の一括加算。

        out(g1) - out(g2) が (cond_layer(g1) - cond_layer(g2)) * mask に
        厳密一致する = attention は g を一度も見ていない (F3 の固定)。
        """
        models = _import_models()
        torch.manual_seed(20)
        enc = models.TextEncoder(**_ENC_KW)
        enc.eval()
        x, x_lengths, g1, g2 = _enc_inputs()

        out1, _, _, mask = enc(x, x_lengths, g=g1)
        out2, _, _, _ = enc(x, x_lengths, g=g2)

        expected = (enc.cond_layer(g1) - enc.cond_layer(g2)) * mask
        assert torch.allclose(out1 - out2, expected, atol=1e-6)

    def test_explicit_zero_is_bit_identical_to_default(self):
        """speaker_cond_layer=0 は default 構築と bit 互換 (新規パラメータなし)。"""
        models = _import_models()
        torch.manual_seed(21)
        enc_default = models.TextEncoder(**_ENC_KW)
        enc_zero = models.TextEncoder(**_ENC_KW, speaker_cond_layer=0)
        # v9 ckpt 互換: strict load が通る = パラメータ集合が不変
        enc_zero.load_state_dict(enc_default.state_dict())
        enc_default.eval()
        enc_zero.eval()
        x, x_lengths, g1, _ = _enc_inputs()

        out_d = enc_default(x, x_lengths, g=g1)
        out_z = enc_zero(x, x_lengths, g=g1)
        for a, b in zip(out_d, out_z, strict=True):
            assert torch.equal(a, b)

    def test_layer3_injection_reaches_attention(self):
        """speaker_cond_layer=3 では g が第 3 層入口に注入され attention を通る。

        出力差分が「後段一括加算の定数差分」ではなくなることで、注入位置の
        移動 (単なる複製追加ではない) を観測する。
        """
        models = _import_models()
        torch.manual_seed(22)
        enc3 = models.TextEncoder(**_ENC_KW, speaker_cond_layer=3)
        enc3.eval()
        x, x_lengths, g1, g2 = _enc_inputs()

        out1, _, _, mask = enc3(x, x_lengths, g=g1)
        out2, _, _, _ = enc3(x, x_lengths, g=g2)
        diff = (out1 - out2).detach()
        const_diff = (enc3.cond_layer(g1) - enc3.cond_layer(g2)).detach() * mask

        assert float(diff.abs().sum()) > 0.0, "g が出力に影響していない"
        assert not torch.allclose(diff, const_diff, atol=1e-5), (
            "差分が後段一括加算と同型 — 注入が層内に移動していない"
        )

    def test_layer3_gradient_flows_to_g(self):
        """speaker_cond_layer=3 で autograd.grad(out, g) が非ゼロ。"""
        models = _import_models()
        torch.manual_seed(23)
        enc3 = models.TextEncoder(**_ENC_KW, speaker_cond_layer=3)
        enc3.eval()
        x, x_lengths, g1, _ = _enc_inputs()
        g = g1.clone().requires_grad_(True)

        out, _, _, _ = enc3(x, x_lengths, g=g)
        (grad,) = torch.autograd.grad(out.sum(), g)
        assert float(grad.abs().sum()) > 0.0

    def test_synthesizer_accepts_speaker_cond_layer(self):
        """SynthesizerTrn が speaker_cond_layer を受理し forward が通る。"""
        model = _tiny_synthesizer(speaker_cond_layer=1)  # tiny は n_layers=1
        out, _ = _run_forward(model)
        assert torch.isfinite(out.waveform).all()


# ---------------------------------------------------------------------------
# M3: DP の話者勾配 (--dp-spk-head)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestM3DpSpkHead:
    def test_default_dur_loss_isolated_from_speaker_path(self):
        """現行挙動の pin: off では dur loss から spk_proj への勾配ゼロ (F4)。

        併せて default 構築に spk_proj_dp が存在しないこと (v9 ckpt 互換) を
        固定する。

        NOTE: SDP の ConvFlow.proj は zero-init のため、randomize しないと
        g への勾配は detach の有無に関係なく厳密に 0 になり pin が空になる
        (ConvFlow の spline パラメータが定数 → dL/dh = W_proj^T grad = 0)。
        dp のみ randomize して detach による遮断を実質的に検証する。
        """
        model = _tiny_synthesizer()
        assert not any("spk_proj_dp" in n for n, _ in model.named_parameters()), (
            "default で新規パラメータが増えている (ckpt 互換破壊)"
        )
        _randomize_(model.dp, std=0.2, seed=60)

        out, _ = _run_forward(model)
        dur = out.duration_loss.sum()
        grads = torch.autograd.grad(
            dur, list(model.spk_proj.parameters()), allow_unused=True
        )
        assert all(g is None or float(g.abs().sum()) == 0.0 for g in grads), (
            "dur loss の勾配が spk_proj に届いている — g detach が壊れている"
        )

    def test_head_receives_dur_gradient_and_spk_proj_is_protected(self):
        """on で spk_proj_dp に非ゼロ勾配、spk_proj 本体 / enc_p はゼロ勾配。

        dp を randomize するのは default pin と同じ理由 (SDP の ConvFlow.proj
        zero-init のままでは g への勾配が構造と無関係に 0 になるため)。
        """
        model = _tiny_synthesizer(dp_spk_head=True)
        _randomize_(model.dp, std=0.2, seed=61)
        out, _ = _run_forward(model)
        dur = out.duration_loss.sum()

        head_params = list(model.spk_proj_dp.parameters())
        spk_params = list(model.spk_proj.parameters())
        enc_p_params = list(model.enc_p.parameters())
        grads = torch.autograd.grad(
            dur, head_params + spk_params + enc_p_params, allow_unused=True
        )
        head_grads = grads[: len(head_params)]
        rest_grads = grads[len(head_params) :]

        assert any(g is not None and float(g.abs().sum()) > 0.0 for g in head_grads), (
            "dur loss の勾配が spk_proj_dp に届いていない"
        )
        assert all(g is None or float(g.abs().sum()) == 0.0 for g in rest_grads), (
            "spk_proj 本体 / enc_p に勾配が漏れている (保護違反)"
        )

    def test_head_structure_and_small_gaussian_init(self):
        """spk_proj_dp は Linear(gin, gin//4) → GELU → Linear(gin//4, gin)、
        weight init は N(0, 1e-3) (無条件、--film-init-std とは独立)。"""
        model = _tiny_synthesizer(dp_spk_head=True)  # gin=64
        weights = [
            p for n, p in model.spk_proj_dp.named_parameters() if n.endswith("weight")
        ]
        assert sorted(tuple(w.shape) for w in weights) == sorted([(16, 64), (64, 16)])
        for w in (w.detach() for w in weights):
            assert float(w.abs().sum()) > 0.0
            assert 2e-4 < float(w.std()) < 5e-3

    def test_sdp_default_detaches_g(self):
        """現行挙動の pin: StochasticDurationPredictor は g を detach する。

        randomize は ConvFlow.proj zero-init による勾配の trivially-zero を
        避け、detach による遮断そのものを pin するため (上記 NOTE 参照)。
        """
        models = _import_models()
        torch.manual_seed(30)
        sdp = models.StochasticDurationPredictor(64, 192, 3, 0.5, 4, gin_channels=16)
        _randomize_(sdp, std=0.2, seed=30)
        sdp.eval()
        x = torch.randn(1, 64, 8)
        mask = torch.ones(1, 1, 8)
        w = torch.ones(1, 1, 8)
        g = torch.randn(1, 16, 1, requires_grad=True)

        torch.manual_seed(31)
        nll = sdp(x, mask, w=w, g=g)
        (grad,) = torch.autograd.grad(nll.sum(), g, allow_unused=True)
        assert grad is None or float(grad.abs().sum()) == 0.0

    def test_sdp_detach_g_false_allows_gradient(self):
        """detach_g=False で SDP NLL から g へ勾配が通る。

        randomize は ConvFlow.proj zero-init による勾配の trivially-zero を
        避けるため (上記 NOTE 参照)。
        """
        models = _import_models()
        torch.manual_seed(32)
        sdp = models.StochasticDurationPredictor(
            64, 192, 3, 0.5, 4, gin_channels=16, detach_g=False
        )
        _randomize_(sdp, std=0.2, seed=32)
        sdp.eval()
        x = torch.randn(1, 64, 8)
        mask = torch.ones(1, 1, 8)
        w = torch.ones(1, 1, 8)
        g = torch.randn(1, 16, 1, requires_grad=True)

        torch.manual_seed(33)
        nll = sdp(x, mask, w=w, g=g)
        (grad,) = torch.autograd.grad(nll.sum(), g)
        assert float(grad.abs().sum()) > 0.0

    def test_dp_detach_g_false_allows_gradient(self):
        """非 SDP の DurationPredictor も detach_g=False で g へ勾配が通る。"""
        models = _import_models()
        torch.manual_seed(34)
        dp = models.DurationPredictor(64, 256, 3, 0.5, gin_channels=16, detach_g=False)
        dp.eval()
        x = torch.randn(1, 64, 8)
        mask = torch.ones(1, 1, 8)
        g = torch.randn(1, 16, 1, requires_grad=True)

        logw = dp(x, mask, g=g)
        (grad,) = torch.autograd.grad(logw.sum(), g)
        assert float(grad.abs().sum()) > 0.0


# ---------------------------------------------------------------------------
# M1 + E2: SNAC flow (--use-snac-flow) — module レベル
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestM1SnacCouplingModules:
    def test_default_layer_reference_math_and_zero_logdet(self):
        """現行挙動の pin: default 構築の coupling は既存 math と一致し、
        mean_only=True では logdet が常に 0 (Σ logs = 0)。"""
        torch.manual_seed(11)
        layer = modules.ResidualCouplingLayer(
            4, 8, 3, 1, 2, gin_channels=8, mean_only=True
        )
        _randomize_(layer, std=0.2, seed=11)
        layer.eval()
        x = torch.randn(2, 4, 6)
        mask = torch.ones(2, 1, 6)
        g = torch.randn(2, 8, 1)

        y, logdet = layer(x, mask, g=g)

        x0, x1 = torch.split(x, [2, 2], 1)
        h = layer.pre(x0) * mask
        h = layer.enc(h, mask, g=g)
        m = layer.post(h) * mask
        ref = torch.cat([x0, m + x1 * mask], 1)
        assert torch.allclose(y, ref, atol=1e-7)
        assert torch.equal(logdet, torch.zeros(2))

    def test_snac_off_flag_is_bit_identical_and_adds_no_params(self):
        """use_snac=False は default 構築と bit 互換 (v9 ckpt 互換)。"""
        torch.manual_seed(12)
        layer = modules.ResidualCouplingLayer(
            4, 8, 3, 1, 2, gin_channels=8, mean_only=True
        )
        _randomize_(layer, std=0.2, seed=12)
        layer_off = modules.ResidualCouplingLayer(
            4, 8, 3, 1, 2, gin_channels=8, mean_only=True, use_snac=False
        )
        # strict load が通る = use_snac=False で新規パラメータなし
        layer_off.load_state_dict(layer.state_dict())

        x = torch.randn(2, 4, 6)
        mask = torch.ones(2, 1, 6)
        g = torch.randn(2, 8, 1)
        y, logdet = layer(x, mask, g=g)
        y_off, logdet_off = layer_off(x, mask, g=g)
        assert torch.equal(y_off, y)
        assert torch.equal(logdet_off, logdet)

    def test_snac_layer_invertible(self):
        """snac on: reverse(forward(x)) ≈ x (g_spk あり、WN g 条件付きあり)。"""
        torch.manual_seed(2)
        layer = modules.ResidualCouplingLayer(
            4, 8, 3, 1, 2, gin_channels=8, mean_only=True, use_snac=True
        )
        _randomize_(layer, std=0.2, seed=2)
        x = torch.randn(2, 4, 6)
        mask = torch.ones(2, 1, 6)
        g = torch.randn(2, 8, 1)
        g_spk = torch.randn(2, 8, 1)

        y, logdet = layer(x, mask, g=g, g_spk=g_spk)
        assert y.shape == x.shape
        assert logdet.shape == (2,)
        x_rec = layer(y, mask, g=g, g_spk=g_spk, reverse=True)
        assert torch.allclose(x_rec, x, atol=1e-4, rtol=1e-4)

    def test_snac_block_logdet_matches_autograd_slogdet(self):
        """block 累積 logdet が autograd jacobian の slogdet と厳密一致。

        小次元 [1, 4, 3] で全 12x12 jacobian を構築して比較する
        (M1 の「logdet を漏らすと KL が静かに壊れる」の直接ガード)。
        """
        models = _import_models()
        torch.manual_seed(3)
        block = models.ResidualCouplingBlock(
            4, 8, 3, 1, 1, n_flows=2, gin_channels=8, use_snac=True
        ).double()
        _randomize_(block, std=0.2, seed=3)
        b, c, t = 1, 4, 3
        mask = torch.ones(b, 1, t, dtype=torch.float64)
        g = torch.randn(b, 8, 1, dtype=torch.float64)
        g_spk = torch.randn(b, 8, 1, dtype=torch.float64)
        x = torch.randn(b, c, t, dtype=torch.float64)

        y, logdet = block(x, mask, g=g, g_spk=g_spk)
        x_rec = block(y, mask, g=g, g_spk=g_spk, reverse=True)
        assert torch.allclose(x_rec, x, atol=1e-8)

        def f(flat):
            out, _ = block(flat.reshape(b, c, t), mask, g=g, g_spk=g_spk)
            return out.flatten()

        jac = torch.autograd.functional.jacobian(f, x.flatten())
        sign, logabsdet = torch.linalg.slogdet(jac)
        assert float(sign) == pytest.approx(1.0)
        assert float(logdet.detach()[0]) == pytest.approx(float(logabsdet), abs=1e-6)

    def test_snac_v_clamp_bounds_scale_and_logdet(self):
        """sn の v は clamp [-4, 4]: 巨大 v でも overflow せず、
        logdet = Σ logs - Σ clamp(v) が mask 内でのみ数えられる。"""
        torch.manual_seed(4)
        layer = modules.ResidualCouplingLayer(
            4, 8, 3, 1, 2, gin_channels=8, mean_only=True, use_snac=True
        )
        # post は zero-init のまま (coupling identity)。sn_linear を細工:
        # weight=0, bias 前半 (m)=0, 後半 (v)=+100 → clamp で v=4 に固定
        with torch.no_grad():
            layer.sn_linear.weight.zero_()
            layer.sn_linear.bias.zero_()
            layer.sn_linear.bias[2:] = 100.0  # 2*half=4 chunk の後半が v

        x = torch.randn(1, 4, 5)
        mask = torch.tensor([[[1.0, 1.0, 1.0, 0.0, 0.0]]])
        g_spk = torch.randn(1, 8, 1)

        y, logdet = layer(x, mask, g_spk=g_spk)
        assert torch.isfinite(y).all()
        assert torch.isfinite(logdet).all()
        # half_channels=2, 有効 frame=3, v=4 → logdet = -4 * 2 * 3 = -24
        assert float(logdet.detach()[0]) == pytest.approx(-24.0, abs=1e-3)

        # reverse は exp(+v): clamp がなければ exp(100) → inf
        x_rec = layer(y, mask, g_spk=g_spk, reverse=True)
        assert torch.isfinite(x_rec).all()
        assert torch.allclose(x_rec[..., :3], x[..., :3], atol=1e-4)

    def test_e2_sn_stats_insensitive_to_wn_conditioning(self):
        """E2: SN 統計は g_spk のみに依存し、WN 側の g (lang) に不感応。

        post は zero-init のまま (coupling identity) → 出力は SN 変換そのもの。
        g を変えても出力不変 / g_spk を変えると出力が変わる、を対で固定。
        WN の lang 条件付け自体は post を有効化すると生きていることも確認。
        """
        torch.manual_seed(5)
        layer = modules.ResidualCouplingLayer(
            4, 8, 3, 1, 2, gin_channels=8, mean_only=True, use_snac=True
        )
        with torch.no_grad():
            layer.sn_linear.weight.normal_(0, 0.5)
            layer.sn_linear.bias.normal_(0, 0.5)
        x = torch.randn(2, 4, 6)
        mask = torch.ones(2, 1, 6)
        g_spk = torch.randn(2, 8, 1)
        g_lang_a = torch.randn(2, 8, 1)
        g_lang_b = torch.randn(2, 8, 1)

        y_a, ld_a = layer(x, mask, g=g_lang_a, g_spk=g_spk)
        y_b, ld_b = layer(x, mask, g=g_lang_b, g_spk=g_spk)
        assert torch.allclose(y_a, y_b, atol=1e-6), (
            "SN 統計が lang 成分 (WN g) に依存している — E2 違反"
        )
        assert torch.allclose(ld_a, ld_b, atol=1e-6)

        # 対照 1: g_spk を変えると SN 出力は変わる (テストが空でない証明)
        y_c, _ = layer(x, mask, g=g_lang_a, g_spk=torch.randn(2, 8, 1))
        assert not torch.allclose(y_a, y_c, atol=1e-4)

        # 対照 2: post を有効化すると WN (lang) 条件付けは生きている
        with torch.no_grad():
            layer.post.weight.normal_(0, 0.5)
        y_a2, _ = layer(x, mask, g=g_lang_a, g_spk=g_spk)
        y_b2, _ = layer(x, mask, g=g_lang_b, g_spk=g_spk)
        assert not torch.allclose(y_a2, y_b2, atol=1e-4), (
            "lang 成分が WN 条件付けから消えている — E2 は分離であって削除ではない"
        )


# ---------------------------------------------------------------------------
# M1 + E2: SynthesizerTrn 統合
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestM1SynthesizerIntegration:
    def test_default_has_no_snac_params(self):
        """現行挙動の pin: default 構築に sn_linear は存在しない (ckpt 互換)。"""
        model = _tiny_synthesizer()
        assert not any("sn_linear" in n for n, _ in model.named_parameters())

    def test_default_flow_logdet_is_none_or_zero(self):
        """snac off の forward は flow_logdet = None (または全ゼロ)。"""
        model = _tiny_synthesizer()
        out, _ = _run_forward(model)
        assert out.flow_logdet is None or float(out.flow_logdet.abs().sum()) == 0.0

    def test_synthesizer_output_tail_field_defaults_none(self):
        """SynthesizerOutput の新 field は末尾 default None (既存の
        positional 構築 8 引数を壊さない)。"""
        models = _import_models()
        t = torch.zeros(1)
        out = models.SynthesizerOutput(t, t, t, t, t, t, (), None)
        assert out.flow_logdet is None

    def test_snac_forward_returns_flow_logdet(self):
        """use_snac_flow=True の forward は per-sample logdet [b] を返す。"""
        model = _tiny_synthesizer(use_snac_flow=True)
        out, _ = _run_forward(model)
        assert out.flow_logdet is not None
        assert out.flow_logdet.shape == (2,)
        assert torch.isfinite(out.flow_logdet).all()

    def test_sn_linear_unconditional_small_gaussian_init(self):
        """sn_linear は --film-init-std と無関係に無条件 N(0, 1e-3) init。"""
        model = _tiny_synthesizer(use_snac_flow=True)
        sn_weights = [
            p
            for n, p in model.named_parameters()
            if "sn_linear" in n and n.endswith("weight")
        ]
        assert sn_weights, "snac flow に sn_linear が存在しない"
        for w in (w.detach() for w in sn_weights):
            assert float(w.abs().sum()) > 0.0
            assert 2e-4 < float(w.std()) < 5e-3

    def test_get_global_conditioning_components(self):
        """_get_global_conditioning(return_components=True) は
        (g_combined, g_spk, g_lang) を返し、既存呼び出しは単一 tensor のまま。"""
        model = _tiny_synthesizer(n_languages=2)
        torch.manual_seed(40)
        emb = torch.nn.functional.normalize(torch.randn(2, 192), dim=-1)
        lid = torch.tensor([0, 1])

        g = model._get_global_conditioning(lid=lid, speaker_embeddings=emb)
        g_c, g_spk, g_lang = model._get_global_conditioning(
            lid=lid, speaker_embeddings=emb, return_components=True
        )
        assert torch.allclose(g_c, g, atol=1e-6)
        assert torch.allclose(g_c, g_spk + g_lang, atol=1e-6)

        # g_spk は lid 不感応 / g_lang は emb 不感応
        _, g_spk2, g_lang2 = model._get_global_conditioning(
            lid=torch.tensor([1, 0]),
            speaker_embeddings=emb,
            return_components=True,
        )
        assert torch.allclose(g_spk, g_spk2, atol=1e-6)
        assert not torch.allclose(g_lang, g_lang2, atol=1e-4)
        emb2 = torch.nn.functional.normalize(torch.randn(2, 192), dim=-1)
        _, g_spk3, g_lang3 = model._get_global_conditioning(
            lid=lid, speaker_embeddings=emb2, return_components=True
        )
        assert not torch.allclose(g_spk, g_spk3, atol=1e-4)
        assert torch.allclose(g_lang, g_lang3, atol=1e-6)

        # n_languages == 1 では g_lang は None
        model1 = _tiny_synthesizer()
        g_c1, g_spk1, g_lang1 = model1._get_global_conditioning(
            speaker_embeddings=emb, return_components=True
        )
        assert g_lang1 is None
        assert torch.allclose(g_c1, g_spk1, atol=1e-6)

    def _spy_flow(self, model):
        captured = {}
        orig_forward = model.flow.forward

        def spy(x, x_mask, g=None, reverse=False, g_spk=None):
            captured["g"] = g
            captured["g_spk"] = g_spk
            return orig_forward(x, x_mask, g=g, reverse=reverse, g_spk=g_spk)

        model.flow.forward = spy
        return captured

    def test_e2_flow_receives_spk_only_and_lang_only(self):
        """E2 配線: snac forward で flow の WN g には lang 成分のみ、
        SN 統計用 g_spk には話者成分のみが渡される。"""
        model = _tiny_synthesizer(n_languages=2, use_snac_flow=True)
        captured = self._spy_flow(model)
        lid = torch.tensor([0, 1])
        _out, emb = _run_forward(model, lid=lid)

        _, g_spk, g_lang = model._get_global_conditioning(
            lid=lid, speaker_embeddings=emb, return_components=True
        )
        assert captured["g_spk"] is not None
        assert torch.allclose(captured["g_spk"], g_spk, atol=1e-6)
        assert captured["g"] is not None
        assert torch.allclose(captured["g"], g_lang, atol=1e-6), (
            "flow の WN に lang 以外 (spk 込み) の g が渡っている — E2 違反"
        )

    def test_e2_single_language_wn_receives_none(self):
        """n_languages==1 の snac では flow の WN g は None。"""
        model = _tiny_synthesizer(use_snac_flow=True)
        captured = self._spy_flow(model)
        _out, emb = _run_forward(model)

        _, g_spk, g_lang = model._get_global_conditioning(
            speaker_embeddings=emb, return_components=True
        )
        assert g_lang is None
        assert captured["g"] is None
        assert torch.allclose(captured["g_spk"], g_spk, atol=1e-6)


# ---------------------------------------------------------------------------
# logdet → KL 配線
# ---------------------------------------------------------------------------


def _kl_inputs():
    gen = torch.Generator().manual_seed(50)
    b, h, t = 2, 6, 10
    z_p = torch.randn(b, h, t, generator=gen)
    logs_q = torch.randn(b, h, t, generator=gen) * 0.1
    m_p = torch.randn(b, h, t, generator=gen)
    logs_p = torch.randn(b, h, t, generator=gen) * 0.1
    z_mask = torch.ones(b, 1, t)
    z_mask[1, :, 7:] = 0.0
    return z_p, logs_q, m_p, logs_p, z_mask


@pytest.mark.unit
class TestKlLogdetWiring:
    def test_logdet_none_keeps_legacy_value(self):
        """logdet=None (default) は従来の kl_loss と厳密一致。"""
        args = _kl_inputs()
        base = kl_loss(*args)
        same = kl_loss(*args, logdet=None)
        assert torch.equal(same, base)

    def test_logdet_shifts_kl_with_negative_sign(self):
        """loss_kl = kl_loss(...) - Σ logdet / Σ z_mask (符号込み)。

        log p(z) = log N(flow(z); m_p, logs_p) + logdet なので、logdet が
        正に増えるほど KL は下がる (符号を逆にすると flow が発散方向に
        報酬を受け KL が静かに壊れる — v10 design §4 M1 リスク)。
        """
        args = _kl_inputs()
        z_mask = args[4]
        base = kl_loss(*args)
        logdet = torch.tensor([3.0, 1.5])

        shifted = kl_loss(*args, logdet=logdet)
        expected = float(base) - float(logdet.sum() / z_mask.sum())
        assert float(shifted) == pytest.approx(expected, abs=1e-6)
        assert float(shifted) < float(base)

    def test_lightning_wires_flow_logdet_into_kl_loss(self):
        """lightning.training_step_g の kl_loss 呼び出しに
        ``logdet=g_output.flow_logdet`` が配線されていること (source 検査 pin)。

        M1 の最重要リスク (design doc §4/§7「logdet→KL 配線漏れ → KL が
        静かに壊れ学習全損」) の統合点ガード。この kwarg を外す mutation は
        snac off (default) では挙動を一切変えないため、kl_loss 単体の数学
        pin (上の 2 テスト) や module レベルの logdet テストを全て生存する
        — 検出できるのは統合点そのものを見るこの pin だけ
        (test_temperature_wired_into_speaker_infonce_call と同型)。
        """
        import inspect
        import re

        from piper_train.vits import lightning as lightning_mod

        src = inspect.getsource(lightning_mod)
        call_windows = [
            src[m.end() : m.end() + 200] for m in re.finditer(r"kl_loss\(", src)
        ]
        assert call_windows, "lightning に kl_loss の呼び出しが存在しない"
        assert all("logdet" in w and "flow_logdet" in w for w in call_windows), (
            "kl_loss 呼び出しに logdet=g_output.flow_logdet が配線されていない "
            "(M1: logdet 破棄 → snac on の学習だけが静かに壊れる)"
        )


# ---------------------------------------------------------------------------
# E1: --film-init-std
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestE1FilmInitStd:
    def test_default_film_zero_init(self):
        """現行挙動の pin: default では dec FiLM (cond_layers) は zero-init。"""
        model = _tiny_synthesizer()
        for layer in model.dec.cond_layers:
            assert float(layer.weight.detach().abs().sum()) == 0.0
            assert float(layer.bias.detach().abs().sum()) == 0.0

    def test_film_init_std_replaces_zero_init(self):
        """film_init_std=1e-3 で cond_layers の weight が N(0, 1e-3) 相当、
        0.0 (明示) では zero-init 維持。"""
        model = _tiny_synthesizer(film_init_std=1e-3)
        for layer in model.dec.cond_layers:
            w = layer.weight.detach()
            assert float(w.abs().sum()) > 0.0
            assert 2e-4 < float(w.std()) < 5e-3

        model0 = _tiny_synthesizer(film_init_std=0.0)
        for layer in model0.dec.cond_layers:
            assert float(layer.weight.detach().abs().sum()) == 0.0


# ---------------------------------------------------------------------------
# CLI (create_parser)
# ---------------------------------------------------------------------------


def _parse_train_args(extra=()):
    from piper_train.__main__ import create_parser

    parser = create_parser()
    return parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra])


@pytest.mark.unit
class TestV10StructureCli:
    def test_defaults_preserve_v9_behaviour(self):
        """新フラグの default は全て off / 0 (v9 と bit 互換)。"""
        args = _parse_train_args()
        assert args.speaker_cond_layer == 0
        assert args.dp_spk_head is False
        assert args.use_snac_flow is False
        assert args.film_init_std == 0.0

    def test_opt_in_flags_parse(self):
        args = _parse_train_args(
            (
                "--speaker-cond-layer",
                "3",
                "--dp-spk-head",
                "--use-snac-flow",
                "--film-init-std",
                "0.001",
            )
        )
        assert args.speaker_cond_layer == 3
        assert args.dp_spk_head is True
        assert args.use_snac_flow is True
        assert args.film_init_std == pytest.approx(1e-3)

    def test_spk_emb_noise_sigma_default_now_zero(self):
        """F7: 破壊的 noise (σ=0.05) を default から除去 (0.05 → 0.0)。

        v9 再現スクリプトは --spk-emb-noise-sigma 0.05 を明示指定して
        いるため、default 変更で v9 の再現性は壊れない (design doc §3.3)。
        """
        args = _parse_train_args()
        assert args.spk_emb_noise_sigma == 0.0


class TestStreamingExportGuards:
    """streaming export が v10 opt-in 構造を silent に落とした graph を
    出力しないこと (レビュー指摘: ガードの対称性)。"""

    @staticmethod
    def _fake_model(**attrs):
        class _M:
            use_snac_flow = False
            spk_proj_dp = None

        m = _M()
        for k, v in attrs.items():
            setattr(m, k, v)
        return m

    def test_plain_model_passes(self):
        from piper_train.export_onnx_streaming import (
            check_streaming_export_supported,
        )

        check_streaming_export_supported(self._fake_model())

    def test_snac_flow_rejected(self):
        from piper_train.export_onnx_streaming import (
            check_streaming_export_supported,
        )

        with pytest.raises(NotImplementedError, match="use_snac_flow"):
            check_streaming_export_supported(self._fake_model(use_snac_flow=True))

    def test_dp_spk_head_rejected(self):
        from piper_train.export_onnx_streaming import (
            check_streaming_export_supported,
        )

        with pytest.raises(NotImplementedError, match="dp_spk_head"):
            check_streaming_export_supported(
                self._fake_model(spk_proj_dp=object())
            )
