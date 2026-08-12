"""Tests for piper_train.tools.diagnose_zs_ckpt (v10 roadmap A-1b).

実 ckpt の代わりに、models.py / mb_istft.py の実キー名・実形状に合わせた
小型乱数テンソルの合成 state_dict を保存して CLI / diagnose() を検証する。

Covers:
1. CLI が JSON レポートを出力し、構造 (4 セクション) が揃っている
2. spk_proj の手動再構成が nn.Sequential (models.py と同構成) と一致する
3. zero-init FiLM (未学習) では delta_norm / rel_l2 感度が 0
4. 同一 embedding 同士では FiLM 感度 (rel_l2) が 0、cosine は 1
5. emb_lang ノルムと lang/spk ratio の妥当性
6. spk_proj キーが無い ckpt は ValueError
7. EMA teacher (model_g. prefix なし) や ema_generator_state は無視される
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


torch = pytest.importorskip("torch")

from piper_train.tools.diagnose_zs_ckpt import (  # noqa: E402
    _extract_model_g_state,
    _spk_proj_forward,
    diagnose,
    main,
)


EMB_DIM = 192
GIN = 16
N_LANG = 3
UPSAMPLE_INITIAL = 32
NUM_UPSAMPLES = 2


def _make_state_dict(
    *, zero_film: bool = False, seed: int = 0
) -> dict[str, torch.Tensor]:
    """models.py / mb_istft.py の実キー名・実形状に合わせた合成 state_dict。"""
    gen = torch.Generator().manual_seed(seed)

    def rnd(*shape: int) -> torch.Tensor:
        return torch.randn(*shape, generator=gen) * 0.1

    sd = {
        # spk_proj: Linear(192, gin) -> LayerNorm(gin) -> GELU -> Linear(gin, gin)
        "model_g.spk_proj.0.weight": rnd(GIN, EMB_DIM),
        "model_g.spk_proj.0.bias": rnd(GIN),
        "model_g.spk_proj.1.weight": torch.ones(GIN) + rnd(GIN),
        "model_g.spk_proj.1.bias": rnd(GIN),
        "model_g.spk_proj.3.weight": rnd(GIN, GIN),
        "model_g.spk_proj.3.bias": rnd(GIN),
        "model_g.emb_lang.weight": rnd(N_LANG, GIN),
        # dec input-stage FiLM: Conv1d(gin, upsample_initial*2, 1)
        "model_g.dec.cond.weight": rnd(UPSAMPLE_INITIAL * 2, GIN, 1),
        "model_g.dec.cond.bias": rnd(UPSAMPLE_INITIAL * 2),
    }
    # dec per-upsample FiLM: Conv1d(gin, ch_stage*2, 1), zero-init
    for i in range(NUM_UPSAMPLES):
        ch = UPSAMPLE_INITIAL // (2 ** (i + 1))
        if zero_film:
            w, b = torch.zeros(ch * 2, GIN, 1), torch.zeros(ch * 2)
        else:
            w, b = rnd(ch * 2, GIN, 1), rnd(ch * 2)
        sd[f"model_g.dec.cond_layers.{i}.weight"] = w
        sd[f"model_g.dec.cond_layers.{i}.bias"] = b
    return sd


def _save_ckpt(tmp_path: Path, sd: dict, name: str = "test.ckpt") -> str:
    """Lightning ckpt 相当の構造 (EMA state 込み) で保存する。"""
    ckpt = {
        "state_dict": {
            **sd,
            # model_g. prefix を持たない DINO teacher — 無視されるべき
            "spk_proj_teacher.0.weight": torch.zeros(GIN, EMB_DIM),
        },
        # EMA state — 読まれないべき
        "ema_generator_state": {"shadow_params": {}},
        "epoch": 49,
    }
    p = tmp_path / name
    torch.save(ckpt, p)
    return str(p)


@pytest.mark.unit
class TestExtraction:
    def test_model_g_prefix_stripped_and_others_ignored(self, tmp_path):
        sd = _make_state_dict()
        path = _save_ckpt(tmp_path, sd)
        ckpt = torch.load(path, map_location="cpu", weights_only=True)
        extracted = _extract_model_g_state(ckpt)
        assert "spk_proj.0.weight" in extracted
        assert "dec.cond_layers.1.weight" in extracted
        # teacher (prefix なし) は落ちる
        assert not any("teacher" in k for k in extracted)

    def test_orig_mod_prefix_stripped(self):
        sd = {"model_g.dec._orig_mod.conv_pre.weight": torch.zeros(1)}
        extracted = _extract_model_g_state({"state_dict": sd})
        assert "dec.conv_pre.weight" in extracted

    def test_missing_spk_proj_raises(self, tmp_path):
        sd = {"model_g.emb_lang.weight": torch.zeros(N_LANG, GIN)}
        path = _save_ckpt(tmp_path, sd)
        with pytest.raises(ValueError, match="spk_proj"):
            diagnose(path)


@pytest.mark.unit
class TestSpkProjReconstruction:
    def test_manual_forward_matches_nn_sequential(self):
        """手動再構成が models.py の nn.Sequential 定義と数値一致する。"""
        module = torch.nn.Sequential(
            torch.nn.Linear(EMB_DIM, GIN),
            torch.nn.LayerNorm(GIN),
            torch.nn.GELU(),
            torch.nn.Linear(GIN, GIN),
        )
        sd = {
            f"spk_proj.{k}": v.detach().float() for k, v in module.state_dict().items()
        }
        emb = torch.randn(4, EMB_DIM, generator=torch.Generator().manual_seed(7))
        with torch.no_grad():
            expected = module(emb)
        actual = _spk_proj_forward(sd, emb)
        assert torch.allclose(actual, expected, atol=1e-6)


@pytest.mark.unit
class TestDiagnoseReport:
    def test_json_structure(self, tmp_path):
        path = _save_ckpt(tmp_path, _make_state_dict())
        json_out = tmp_path / "report.json"
        main([path, "--json-out", str(json_out)])
        result = json.loads(json_out.read_text(encoding="utf-8"))

        assert result["emb_dim"] == EMB_DIM
        assert result["gin_channels"] == GIN
        assert result["n_languages"] == N_LANG
        assert result["num_random_embeddings"] == 8
        assert result["num_real_embeddings"] == 0

        lv = result["lang_vs_speaker"]
        assert len(lv["spk_out_norms"]) == 8
        assert len(lv["lang_norms"]) == N_LANG
        assert lv["spk_out_norm_mean"] > 0
        assert lv["lang_norm_mean"] > 0
        # ratio は互いに逆数
        assert lv["lang_over_spk"] * lv["spk_over_lang"] == pytest.approx(1.0)

        # FiLM 層は input-stage + upsample 2 段
        expected_layers = ["dec.cond", "dec.cond_layers.0", "dec.cond_layers.1"]
        assert list(result["film_wakeup"]) == expected_layers
        assert list(result["film_sensitivity"]) == expected_layers
        assert result["film_wakeup"]["dec.cond"]["zero_init"] is False
        assert result["film_wakeup"]["dec.cond_layers.0"]["zero_init"] is True
        for stats in result["film_wakeup"].values():
            assert stats["weight_norm"] >= 0
            assert stats["scale_weight_norm"] <= stats["weight_norm"] + 1e-6

        # 乱数 (非ゼロ) FiLM は話者感度を持つ
        sens = result["film_sensitivity"]["dec.cond"]
        assert sens["num_pairs"] == 8 * 7 // 2
        assert sens["rel_l2_mean"] > 0
        assert sens["delta_norm_mean"] > 0

        assert set(result["spk_proj_layers"]) == {
            "spk_proj.0",
            "spk_proj.1",
            "spk_proj.3",
        }
        for stats in result["spk_proj_layers"].values():
            assert stats["weight_norm"] > 0

    def test_zero_init_film_has_zero_sensitivity(self, tmp_path):
        """未学習 (zero-init) FiLM は delta も感度も 0 — 「起きていない」判定。"""
        path = _save_ckpt(tmp_path, _make_state_dict(zero_film=True))
        result = diagnose(path)
        for i in range(NUM_UPSAMPLES):
            wakeup = result["film_wakeup"][f"dec.cond_layers.{i}"]
            assert wakeup["weight_norm"] == 0.0
            assert wakeup["bias_norm"] == 0.0
            sens = result["film_sensitivity"][f"dec.cond_layers.{i}"]
            assert sens["delta_norm_mean"] == pytest.approx(0.0, abs=1e-7)
            assert sens["rel_l2_mean"] == pytest.approx(0.0, abs=1e-7)
            assert sens["cosine_mean"] is None  # ゼロベクトル同士は未定義

    def test_identical_embeddings_zero_sensitivity(self, tmp_path):
        """同一 embedding なら FiLM 変調も同一 → rel_l2 = 0, cosine = 1。"""
        path = _save_ckpt(tmp_path, _make_state_dict())
        emb = np.random.default_rng(3).normal(size=EMB_DIM).astype(np.float32)
        npy = tmp_path / "emb.npy"
        np.save(npy, emb)
        result = diagnose(path, emb_npy=[npy, npy], num_random=2)
        assert result["num_real_embeddings"] == 2
        real = result["film_sensitivity_real"]
        assert real is not None
        for stats in real.values():
            assert stats["num_pairs"] == 1
            assert stats["rel_l2_mean"] == pytest.approx(0.0, abs=1e-7)
            # 非ゼロ層では cosine が定義され 1 になる
            if stats["delta_norm_mean"] > 1e-7:
                assert stats["cosine_mean"] == pytest.approx(1.0, abs=1e-6)

    def test_deterministic_across_runs(self, tmp_path):
        """固定 seed のランダム embedding により結果は再現可能。"""
        path = _save_ckpt(tmp_path, _make_state_dict())
        r1 = diagnose(path)
        r2 = diagnose(path)
        assert r1["lang_vs_speaker"] == r2["lang_vs_speaker"]
        assert r1["film_sensitivity"] == r2["film_sensitivity"]

    def test_emb_npy_batch_and_dim_validation(self, tmp_path):
        path = _save_ckpt(tmp_path, _make_state_dict())
        good = tmp_path / "batch.npy"
        np.save(good, np.random.default_rng(0).normal(size=(3, EMB_DIM)))
        result = diagnose(path, emb_npy=[good])
        assert result["num_real_embeddings"] == 3

        bad = tmp_path / "bad.npy"
        np.save(bad, np.zeros((2, EMB_DIM + 1), dtype=np.float32))
        with pytest.raises(ValueError, match="expected shape"):
            diagnose(path, emb_npy=[bad])
