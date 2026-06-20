"""Tests for _select_ort_providers (SCL CAM++ inference provider selection).

学習時 SCL は毎 step で CAM++ ONNX を呼ぶため、CPU 固定だとボトルネックになる
(V100×4 環境で 14 sec/step、SCL 部分が大半)。GPU 化で 5-10× 改善するよう
``_select_ort_providers`` を導入した。

本ファイルは provider 選択ロジックを検証する。
"""

from __future__ import annotations

import os
from unittest import mock

import pytest


pytest.importorskip("torch", reason="torch required for piper_train.vits.lightning")


@pytest.mark.unit
class TestSelectOrtProviders:
    """SCL 用 ORT providers の選択ロジック"""

    def test_cuda_preferred_when_available(self, monkeypatch):
        """CUDA が available_providers にあれば最優先"""
        from piper_train.vits import lightning

        monkeypatch.delenv("PIPER_FORCE_CPU_ORT", raising=False)

        with mock.patch(
            "onnxruntime.get_available_providers",
            return_value=[
                "TensorrtExecutionProvider",
                "CUDAExecutionProvider",
                "CPUExecutionProvider",
            ],
        ):
            providers = lightning._select_ort_providers()

        assert providers[0] == "CUDAExecutionProvider"
        assert "CPUExecutionProvider" in providers

    def test_cpu_only_when_cuda_unavailable(self, monkeypatch):
        """CUDA 不在環境では CPU のみ"""
        from piper_train.vits import lightning

        monkeypatch.delenv("PIPER_FORCE_CPU_ORT", raising=False)

        with mock.patch(
            "onnxruntime.get_available_providers",
            return_value=["CPUExecutionProvider"],
        ):
            providers = lightning._select_ort_providers()

        assert providers == ["CPUExecutionProvider"]

    def test_force_cpu_via_env(self, monkeypatch):
        """環境変数 PIPER_FORCE_CPU_ORT=1 で CUDA 利用可能でも CPU 固定"""
        from piper_train.vits import lightning

        monkeypatch.setenv("PIPER_FORCE_CPU_ORT", "1")

        # CUDA available でも CPU only を返すべき
        with mock.patch(
            "onnxruntime.get_available_providers",
            return_value=["CUDAExecutionProvider", "CPUExecutionProvider"],
        ):
            providers = lightning._select_ort_providers()

        assert providers == ["CPUExecutionProvider"]

    def test_force_cpu_disabled_with_zero(self, monkeypatch):
        """PIPER_FORCE_CPU_ORT=0 では通常選択ロジックが働く"""
        from piper_train.vits import lightning

        monkeypatch.setenv("PIPER_FORCE_CPU_ORT", "0")

        with mock.patch(
            "onnxruntime.get_available_providers",
            return_value=["CUDAExecutionProvider", "CPUExecutionProvider"],
        ):
            providers = lightning._select_ort_providers()

        assert providers[0] == "CUDAExecutionProvider"

    def test_returns_list_type(self, monkeypatch):
        """戻り値は list (ort.InferenceSession の providers 引数互換)"""
        from piper_train.vits import lightning

        monkeypatch.delenv("PIPER_FORCE_CPU_ORT", raising=False)
        with mock.patch(
            "onnxruntime.get_available_providers",
            return_value=["CPUExecutionProvider"],
        ):
            providers = lightning._select_ort_providers()
        assert isinstance(providers, list)
        assert all(isinstance(p, str) for p in providers)
