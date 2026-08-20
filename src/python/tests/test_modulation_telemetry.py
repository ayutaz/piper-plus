"""v11 D-2: 変調統計テレメトリ常設 (--telemetry-every) の TDD。

docs/design/zero-shot-v11-conditioning-design.md §3 D-2 / §10.6-4 / §10.3-1:
「変調の総量 (ノルム・分散量) だけでは SNAC 型の死荷重を検知できない」教訓の
制度化。各注入点 (FiLM/AdaIN/AdaLN/M2/SNAC/DP) の**話者依存分散比**
(batch 内の話者間分散 / 総分散) を学習中 N step ごとに log する。

固定する契約:

* **定義どおりの値** (合成 batch で手計算一致): channel ごとの biased
  variance で between = Σ_s (n_s/B)(μ_s−μ)²、total = mean_b (v−μ)²、
  ratio = mean_c(between)/mean_c(total)。
* 全話者ユニーク → 1.0 / 単一話者 or 定数変調 → 0.0 / B<2 → None。
* 注入点キーは **存在する flag 構成でのみ** 出る (P5 で SNAC 統計を
  除去した構成では flow_snac キー自体が消える)。
* lightning: ``--telemetry-every`` default 500、0 で無効、eval 中は発火
  しない。log キーは ``telemetry/...``。
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.telemetry import (  # noqa: E402
    collect_modulation_telemetry,
    speaker_variance_ratio,
)


# ---------------------------------------------------------------------------
# speaker_variance_ratio: 定義の手計算一致
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSpeakerVarianceRatio:
    def test_matches_hand_computed_value(self):
        """V = [[0,0],[2,2],[10,10],[12,12]]、spk = [0,0,1,1]:
        μ=6、群平均 {1, 11} → between = (2/4)·25 + (2/4)·25 = 25、
        total = (36+16+16+36)/4 = 26 → ratio = 25/26。"""
        values = torch.tensor([[0.0, 0.0], [2.0, 2.0], [10.0, 10.0], [12.0, 12.0]])
        sids = torch.tensor([0, 0, 1, 1])
        ratio = speaker_variance_ratio(values, sids)
        assert ratio == pytest.approx(25.0 / 26.0, abs=1e-6)

    def test_unbalanced_groups_hand_computed(self):
        """群サイズ非均等の重み (n_s/B) も定義どおり:
        V = [[0],[0],[6]]、spk = [0,0,1]: μ=2、μ_0=0 (n=2)、μ_1=6 (n=1)
        → between = (2/3)·4 + (1/3)·16 = 8、total = (4+4+16)/3 = 8 → 1.0
        (この配置は群内分散ゼロなので話者だけが分散を説明する)。"""
        values = torch.tensor([[0.0], [0.0], [6.0]])
        sids = torch.tensor([0, 0, 1])
        assert speaker_variance_ratio(values, sids) == pytest.approx(1.0, abs=1e-6)

    def test_within_speaker_variance_lowers_the_ratio(self):
        """V = [[0],[2],[6],[6]]、spk = [0,0,1,1]: μ=3.5、μ_0=1、μ_1=6 →
        between = 0.5·6.25 + 0.5·6.25 = 6.25、
        total = (12.25+2.25+6.25+6.25)/4 = 6.75 → 25/27。"""
        values = torch.tensor([[0.0], [2.0], [6.0], [6.0]])
        sids = torch.tensor([0, 0, 1, 1])
        assert speaker_variance_ratio(values, sids) == pytest.approx(
            6.25 / 6.75, abs=1e-6
        )

    def test_all_unique_speakers_is_one(self):
        values = torch.randn(5, 7)
        sids = torch.arange(5)
        assert speaker_variance_ratio(values, sids) == pytest.approx(1.0, abs=1e-5)

    def test_single_speaker_is_zero(self):
        values = torch.randn(4, 3)
        sids = torch.zeros(4, dtype=torch.long)
        assert speaker_variance_ratio(values, sids) == pytest.approx(0.0, abs=1e-6)

    def test_constant_modulation_is_zero(self):
        """総分散 ≈ 0 (話者共通の固定変換) は 0-division せず 0.0。"""
        values = torch.ones(4, 3) * 2.5
        sids = torch.tensor([0, 0, 1, 1])
        assert speaker_variance_ratio(values, sids) == 0.0

    def test_batch_of_one_is_undefined(self):
        assert speaker_variance_ratio(torch.randn(1, 3), torch.tensor([0])) is None


# ---------------------------------------------------------------------------
# collect_modulation_telemetry: 注入点キーと値
# ---------------------------------------------------------------------------


def _build_synthesizer(**overrides):
    from piper_train.vits.models import SynthesizerTrn

    torch.manual_seed(1234)
    kwargs: dict = {
        "n_vocab": 60,
        "spec_channels": 513,
        "segment_size": 32,
        "inter_channels": 192,
        "hidden_channels": 96,
        "filter_channels": 128,
        "n_heads": 2,
        "n_layers": 1,
        "kernel_size": 3,
        "p_dropout": 0.0,
        "resblock": "2",
        "resblock_kernel_sizes": (3,),
        "resblock_dilation_sizes": ((1, 2),),
        "upsample_rates": (4, 4),
        "upsample_initial_channel": 64,
        "upsample_kernel_sizes": (16, 16),
        "n_speakers": 4,
        "n_languages": 2,
        "gin_channels": 512,
        "use_sdp": False,
        "prosody_dim": 0,
    }
    kwargs.update(overrides)
    return SynthesizerTrn(**kwargs)


def _batch_inputs(b: int = 4, seed: int = 0):
    g = torch.Generator().manual_seed(seed)
    emb = torch.nn.functional.normalize(torch.randn(b, 192, generator=g), dim=-1)
    lid = torch.tensor([0, 1, 0, 1][:b])
    sids = torch.tensor([0, 0, 1, 1][:b])
    return emb, lid, sids


@pytest.mark.unit
class TestCollectTelemetry:
    def test_baseline_config_reports_film_and_encp_points(self):
        model = _build_synthesizer()
        emb, lid, sids = _batch_inputs()
        metrics = collect_modulation_telemetry(model, emb, lid=lid, speaker_ids=sids)
        for point in ("dec_film_input", "dec_film_s1", "dec_film_s2", "encp_cond"):
            assert f"telemetry/mod_std/{point}" in metrics
            assert f"telemetry/spk_var_ratio/{point}" in metrics
        assert "telemetry/g_spk_norm" in metrics
        assert "telemetry/g_lang_spk_norm_ratio" in metrics
        assert "telemetry/g_spk_lang_cos" in metrics
        assert all(np.isfinite(v) for v in metrics.values())
        # 話者依存分散比は比なので [0, 1] (数値誤差マージン付き)
        for k, v in metrics.items():
            if "spk_var_ratio" in k:
                assert -1e-6 <= v <= 1.0 + 1e-6, f"{k}={v}"

    def test_ratio_matches_direct_computation_for_dec_film_input(self):
        """collect の値が「実際に conditioning に使う変調ベクトル」に対する
        定義どおりの値である (dec.cond(g) を手動再現して一致)。"""
        model = _build_synthesizer()
        with torch.no_grad():
            model.dec.cond.weight.normal_(0.0, 0.1)
        emb, lid, sids = _batch_inputs()
        metrics = collect_modulation_telemetry(model, emb, lid=lid, speaker_ids=sids)
        with torch.no_grad():
            g = model._get_global_conditioning(None, lid, speaker_embeddings=emb)
            vals = model.dec.cond(g).squeeze(-1)
        expected_ratio = speaker_variance_ratio(vals, sids)
        expected_std = float(vals.float().std(dim=0, unbiased=False).mean())
        assert metrics["telemetry/spk_var_ratio/dec_film_input"] == pytest.approx(
            expected_ratio, abs=1e-6
        )
        assert metrics["telemetry/mod_std/dec_film_input"] == pytest.approx(
            expected_std, abs=1e-6
        )

    def test_g_spk_lang_cos_matches_direct_computation(self):
        model = _build_synthesizer()
        emb, lid, sids = _batch_inputs()
        metrics = collect_modulation_telemetry(model, emb, lid=lid, speaker_ids=sids)
        with torch.no_grad():
            _g, g_spk, g_lang = model._get_global_conditioning(
                None, lid, speaker_embeddings=emb, return_components=True
            )
            cos = torch.nn.functional.cosine_similarity(
                g_spk.squeeze(-1), g_lang.squeeze(-1), dim=-1
            ).mean()
        assert metrics["telemetry/g_spk_lang_cos"] == pytest.approx(
            float(cos), abs=1e-6
        )

    def test_optional_points_appear_only_with_their_flags(self):
        """AdaIN / AdaLN / SNAC / DP head のキーは flag 構成に追随する。"""
        base = _build_synthesizer()
        emb, lid, sids = _batch_inputs()
        m_base = collect_modulation_telemetry(base, emb, lid=lid, speaker_ids=sids)
        for point in ("dec_adain", "encp_adaln", "flow_snac", "dp_head"):
            assert f"telemetry/mod_std/{point}" not in m_base

        full = _build_synthesizer(
            use_adain_decoder=True,
            use_adaln_encp=True,
            use_snac_flow=True,
            dp_spk_head=True,
        )
        m_full = collect_modulation_telemetry(full, emb, lid=lid, speaker_ids=sids)
        for point in ("dec_adain", "encp_adaln", "flow_snac", "dp_head"):
            assert f"telemetry/mod_std/{point}" in m_full
            assert f"telemetry/spk_var_ratio/{point}" in m_full
        assert "telemetry/dp_delta_norm" in m_full

    def test_p5_no_snac_stats_removes_the_flow_snac_point(self):
        """P5 で統計注入を除去した構成では flow_snac キー自体が消える
        (死荷重の測定対象が存在しない)。"""
        model = _build_synthesizer(use_snac_flow=True, snac_stats=False)
        emb, lid, sids = _batch_inputs()
        metrics = collect_modulation_telemetry(model, emb, lid=lid, speaker_ids=sids)
        assert "telemetry/mod_std/flow_snac" not in metrics

    def test_without_speaker_ids_ratio_keys_are_omitted(self):
        model = _build_synthesizer()
        emb, lid, _sids = _batch_inputs()
        metrics = collect_modulation_telemetry(model, emb, lid=lid, speaker_ids=None)
        assert "telemetry/mod_std/dec_film_input" in metrics
        assert not any("spk_var_ratio" in k for k in metrics)

    def test_no_grad_and_no_graph_leak(self):
        """テレメトリは autograd graph を作らない (学習を汚さない)。"""
        model = _build_synthesizer()
        emb, lid, sids = _batch_inputs()
        emb = emb.requires_grad_(True)
        metrics = collect_modulation_telemetry(model, emb, lid=lid, speaker_ids=sids)
        assert metrics  # 値は生値の float (tensor ではない)
        assert all(isinstance(v, float) for v in metrics.values())


# ---------------------------------------------------------------------------
# lightning 配線: スケジュール + log キー
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
class TestLightningWiring:
    def test_cli_default_is_500(self):
        assert _parse_train_args().telemetry_every == 500

    def test_cli_accepts_override_and_disable(self):
        assert _parse_train_args(("--telemetry-every", "100")).telemetry_every == 100
        assert _parse_train_args(("--telemetry-every", "0")).telemetry_every == 0

    def test_hparam_default_is_500(self):
        model = _vits_model()
        assert model.hparams.telemetry_every == 500

    def test_due_schedule(self):
        model = _vits_model()
        model.train()
        # trainer なし → global_step=0 → 0 % 500 == 0 → due
        assert model._telemetry_due() is True
        model.eval()
        assert model._telemetry_due() is False

    def test_zero_disables(self):
        model = _vits_model(telemetry_every=0)
        model.train()
        assert model._telemetry_due() is False

    def test_log_modulation_telemetry_emits_telemetry_keys(self):
        model = _vits_model()
        logged: dict[str, float] = {}
        model.log = lambda key, value, **kw: logged.__setitem__(key, value)
        emb = torch.nn.functional.normalize(torch.randn(4, 192), dim=-1)
        lid = torch.tensor([0, 1, 0, 1])
        batch = SimpleNamespace(
            phoneme_ids=torch.zeros(4, 5, dtype=torch.long),
            speaker_ids=torch.tensor([0, 0, 1, 1]),
        )
        model._log_modulation_telemetry(batch, emb, lid)
        assert logged
        assert all(k.startswith("telemetry/") for k in logged)
        assert "telemetry/spk_var_ratio/dec_film_input" in logged
