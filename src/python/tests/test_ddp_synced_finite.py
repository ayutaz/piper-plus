"""Tests for VitsModel._ddp_synced_is_finite (NaN skip with DDP sync).

DDP では loss skip を rank ごとにバラつかせると all_reduce が mismatch して
NCCL collective timeout (30 分タイムアウト → CUDA illegal access に偽装される)
を引き起こす。本ファイルは ``_ddp_synced_is_finite`` ヘルパーが、

- 単一 rank (DDP 未初期化) では Local finite check として動作
- DDP 初期化済みでは ``ReduceOp.MIN`` で全 rank 同期して、1 rank でも
  非有限なら全 rank で False を返す

ことを検証する。
"""

from __future__ import annotations

from unittest import mock

import pytest


pytest.importorskip("torch", reason="torch required for VitsModel")

import torch  # noqa: E402

from piper_train.vits.lightning import VitsModel  # noqa: E402


# ---------------------------------------------------------------------------
# Single-rank (DDP 未初期化) 挙動
# ---------------------------------------------------------------------------


class TestSingleRank:
    """torch.distributed が初期化されていない環境での挙動"""

    def test_finite_returns_true(self):
        result = VitsModel._ddp_synced_is_finite(torch.tensor(1.5))
        assert result is True

    def test_finite_zero(self):
        result = VitsModel._ddp_synced_is_finite(torch.tensor(0.0))
        assert result is True

    def test_finite_negative(self):
        result = VitsModel._ddp_synced_is_finite(torch.tensor(-3.14))
        assert result is True

    def test_nan_returns_false(self):
        result = VitsModel._ddp_synced_is_finite(torch.tensor(float("nan")))
        assert result is False

    def test_positive_inf_returns_false(self):
        result = VitsModel._ddp_synced_is_finite(torch.tensor(float("inf")))
        assert result is False

    def test_negative_inf_returns_false(self):
        result = VitsModel._ddp_synced_is_finite(torch.tensor(float("-inf")))
        assert result is False


# ---------------------------------------------------------------------------
# DDP 初期化済み環境での挙動 (mock)
# ---------------------------------------------------------------------------


class TestDDPSync:
    """DDP all_reduce が呼ばれることを mock で検証"""

    def test_all_reduce_invoked_when_ddp_active(self, monkeypatch):
        """DDP 初期化済みなら all_reduce が呼ばれる"""
        all_reduce_calls = []

        def fake_all_reduce(tensor, op=None):
            all_reduce_calls.append((tensor.item(), op))
            # mock: 全 rank finite (=1) と仮定して何もしない

        monkeypatch.setattr(torch.distributed, "is_available", lambda: True)
        monkeypatch.setattr(torch.distributed, "is_initialized", lambda: True)
        monkeypatch.setattr(torch.distributed, "all_reduce", fake_all_reduce)

        result = VitsModel._ddp_synced_is_finite(torch.tensor(1.5))
        assert result is True
        assert len(all_reduce_calls) == 1
        assert all_reduce_calls[0][1] == torch.distributed.ReduceOp.MIN

    def test_one_rank_nan_propagates_to_all(self, monkeypatch):
        """1 rank でも NaN だと all_reduce(MIN) で is_finite=0 になり、全 rank False"""

        def fake_all_reduce(tensor, op=None):
            # 別 rank が NaN だったと模擬: tensor を 0 に書き換え
            tensor.zero_()

        monkeypatch.setattr(torch.distributed, "is_available", lambda: True)
        monkeypatch.setattr(torch.distributed, "is_initialized", lambda: True)
        monkeypatch.setattr(torch.distributed, "all_reduce", fake_all_reduce)

        # 自 rank では loss は finite だが、他 rank が NaN
        result = VitsModel._ddp_synced_is_finite(torch.tensor(1.5))
        assert result is False, (
            "1 rank でも NaN なら all_reduce(MIN) 後に全 rank で False を返すべき"
        )

    def test_all_ranks_finite_returns_true(self, monkeypatch):
        """全 rank finite なら all_reduce(MIN) は変更なし → True"""

        def fake_all_reduce(tensor, op=None):
            # 何も変更しない (全 rank で 1)
            pass

        monkeypatch.setattr(torch.distributed, "is_available", lambda: True)
        monkeypatch.setattr(torch.distributed, "is_initialized", lambda: True)
        monkeypatch.setattr(torch.distributed, "all_reduce", fake_all_reduce)

        result = VitsModel._ddp_synced_is_finite(torch.tensor(1.5))
        assert result is True

    def test_local_nan_remains_false_after_sync(self, monkeypatch):
        """自 rank が NaN の場合、all_reduce(MIN) でも 0 のまま → False"""

        def fake_all_reduce(tensor, op=None):
            # 他 rank も全て 0 と模擬 (差はない)
            pass

        monkeypatch.setattr(torch.distributed, "is_available", lambda: True)
        monkeypatch.setattr(torch.distributed, "is_initialized", lambda: True)
        monkeypatch.setattr(torch.distributed, "all_reduce", fake_all_reduce)

        result = VitsModel._ddp_synced_is_finite(torch.tensor(float("nan")))
        assert result is False

    def test_skip_all_reduce_when_not_initialized(self, monkeypatch):
        """is_initialized=False なら all_reduce を呼ばない"""
        all_reduce_calls = []

        def fake_all_reduce(tensor, op=None):
            all_reduce_calls.append(tensor)

        monkeypatch.setattr(torch.distributed, "is_available", lambda: True)
        monkeypatch.setattr(torch.distributed, "is_initialized", lambda: False)
        monkeypatch.setattr(torch.distributed, "all_reduce", fake_all_reduce)

        VitsModel._ddp_synced_is_finite(torch.tensor(1.5))
        assert len(all_reduce_calls) == 0
