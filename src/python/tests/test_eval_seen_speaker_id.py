"""Tests for piper_train.tools.eval_seen_speaker_id (seen 話者 N 択識別).

背景 (docs/design/zero-shot-v11-conditioning-design.md §6 / §8 oracle):
SECS の絶対値は (a) 話者同一性の誤差 と (b) 合成音 vs 実音声のドメイン差の
両方で下がる。raw top-1 と centered top-1 (両クラウドの平均を除去) を分離
することで「条件付け経路は話者情報を運べているか」を診断する。
本指標は**診断専用** (go/no-go 不使用、学習 loss 流用は恒久禁止)。
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from piper_train.tools import eval_seen_speaker_id
from piper_train.tools.eval_seen_speaker_id import (
    identification_report,
    load_reference_embeddings,
)


N_SPK = 8


def _basis_refs(n: int = N_SPK, dim: int = N_SPK) -> np.ndarray:
    return np.eye(n, dim, dtype=np.float64)


@pytest.mark.unit
class TestIdentificationReport:
    def test_perfect_embeddings_top1_is_1(self):
        """参照とほぼ一致する合成 embedding → raw top-1 = 1.0。"""
        refs = _basis_refs()
        rng = np.random.default_rng(0)
        synth = np.concatenate([refs, refs])  # 2 発話/話者
        synth = synth + 0.01 * rng.standard_normal(synth.shape)
        labels = np.tile(np.arange(N_SPK), 2)
        rep = identification_report(synth, labels, refs)
        assert rep["raw"]["top1_acc"] == 1.0
        assert rep["raw"]["top3_acc"] == 1.0
        assert rep["raw"]["mean_rank"] == 1.0
        assert rep["raw"]["chance_top1"] == pytest.approx(1.0 / N_SPK)
        assert rep["n_speakers"] == N_SPK
        assert rep["n_synth"] == 2 * N_SPK

    def test_centered_recovers_from_domain_offset(self):
        """全合成音に共通の「合成っぽさ」オフセットが乗ると raw は崩れるが、
        centered (両クラウド平均の除去) は話者同一性を復元する — oracle 診断
        (v10a-r2: raw 43% / centered 73%) の分離ロジックの本体。
        """
        refs = _basis_refs()
        offset = 3.0 * refs[0]  # 話者 0 方向への強い共通オフセット
        synth = np.array([r + offset for r in refs])
        labels = np.arange(N_SPK)
        rep = identification_report(synth, labels, refs)
        # raw: 全合成音が話者 0 に吸われる → 正解は話者 0 のみ
        assert rep["raw"]["top1_acc"] == pytest.approx(1.0 / N_SPK)
        # centered: オフセットが除去され全話者正解
        assert rep["centered"]["top1_acc"] == 1.0
        assert rep["centered"]["top1_acc"] > rep["raw"]["top1_acc"]
        # 分離度も centered で回復する
        assert rep["separation_centered"] > rep["separation_raw"]

    def test_shared_component_block(self):
        refs = _basis_refs()
        synth = refs.copy()
        rep = identification_report(refs, np.arange(N_SPK), refs)
        shared = rep["shared_component"]
        for key in (
            "norm_of_synth_cloud_mean",
            "norm_of_real_cloud_mean",
            "cos_synth_mean_vs_real_mean",
        ):
            assert key in shared
        assert synth.shape == refs.shape  # 入力は破壊されない

    def test_rank_metrics_hand_computed(self):
        """2 話者・1 合成で rank が手計算と一致する。"""
        refs = np.array([[1.0, 0.0], [0.0, 1.0]])
        synth = np.array([[0.6, 0.8]])  # 話者 1 (正解) に近い
        rep = identification_report(synth, np.array([1]), refs)
        assert rep["raw"]["top1_acc"] == 1.0
        assert rep["raw"]["mean_rank"] == 1.0
        assert rep["raw"]["mean_cos_correct"] == pytest.approx(0.8)
        assert rep["raw"]["mean_cos_wrong"] == pytest.approx(0.6)


@pytest.mark.unit
class TestLoadReferenceEmbeddings:
    def test_load_1d_and_2d_npy(self, tmp_path):
        """<speaker>.npy は [D] (centroid) と [N, D] (発話群 → 平均) の両対応。"""
        d = tmp_path / "refs"
        d.mkdir()
        np.save(d / "spk_a.npy", np.array([2.0, 0.0, 0.0]))  # 未正規化 [D]
        np.save(
            d / "spk_b.npy",
            np.array([[0.0, 3.0, 0.0], [0.0, 0.0, 3.0]]),  # [N, D]
        )
        speakers, refs = load_reference_embeddings(d)
        assert speakers == ["spk_a", "spk_b"]
        assert refs.shape == (2, 3)
        # 全行 L2 正規化済み
        np.testing.assert_allclose(np.linalg.norm(refs, axis=1), 1.0, atol=1e-6)
        np.testing.assert_allclose(refs[0], [1.0, 0.0, 0.0], atol=1e-6)
        # [N, D] は行ごとに正規化してから平均 → 再正規化
        expected_b = np.array([0.0, 1.0, 1.0]) / np.sqrt(2.0)
        np.testing.assert_allclose(refs[1], expected_b, atol=1e-6)

    def test_empty_dir_fails(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(SystemExit):
            load_reference_embeddings(d)


@pytest.mark.unit
class TestDiagnosticOnlyContract:
    def test_docstring_declares_diagnostic_only(self):
        doc = eval_seen_speaker_id.__doc__
        assert "EVAL-ONLY" in doc
        assert "診断専用" in doc
        assert "go/no-go" in doc

    def test_report_json_carries_diagnostic_flag(self):
        """JSON 出力に diagnostic_only が常在する (下流での go/no-go 誤用防止)。"""
        refs = _basis_refs(3, 4)
        rep = identification_report(refs, np.arange(3), refs)
        assert rep["diagnostic_only"] is True
        # JSON serializable であること
        json.dumps(rep)
