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


# ---------------------------------------------------------------------------
# d_update_interval > 1 と NaN-skip の相互作用
# ---------------------------------------------------------------------------


class _FakeHparams:
    def __init__(self, d_update_interval: int):
        self.d_update_interval = d_update_interval
        self.grad_clip = None


class _FakeOpt:
    def __init__(self):
        self.zero_grad_calls = 0
        self.step_calls = 0

    def zero_grad(self, set_to_none: bool = False):
        self.zero_grad_calls += 1

    def step(self):
        self.step_calls += 1


class _FakeBatch:
    """Minimal Batch stand-in for training_step logging path."""

    def __init__(self):
        self.phoneme_ids = torch.zeros(2, 4, dtype=torch.long)
        self.phoneme_lengths = torch.tensor([4, 4])
        self.audio_lengths = torch.tensor([100, 100])
        self.spectrogram_lengths = torch.tensor([20, 20])


def _make_fake_model(
    d_update_interval: int,
    loss_g_sequence: list[float],
    loss_d_value: float = 0.5,
):
    """Build a fake-self for VitsModel.training_step.

    ``loss_g_sequence[i]`` is returned by ``training_step_g`` on call ``i``.
    A NaN entry simulates an unstable G forward.
    """
    fake = mock.MagicMock()
    fake.hparams = _FakeHparams(d_update_interval=d_update_interval)
    fake.global_step = 0
    fake._y = None
    fake._y_hat = None

    opt_g = _FakeOpt()
    opt_d = _FakeOpt()
    fake.optimizers = mock.MagicMock(return_value=(opt_g, opt_d))
    fake._opt_g = opt_g
    fake._opt_d = opt_d

    # Real DDP-sync helper (single-rank path → finite check is local).
    # _ddp_synced_is_finite is a @staticmethod, so bind as plain callable.
    fake._ddp_synced_is_finite = VitsModel._ddp_synced_is_finite

    g_calls = {"n": 0}

    def fake_training_step_g(batch):
        idx = g_calls["n"]
        g_calls["n"] += 1
        val = loss_g_sequence[idx] if idx < len(loss_g_sequence) else 1.0
        # Mimic production: set _y_hat fresh on every G forward.
        fake._y_hat = torch.zeros(1, 1, 8)
        fake._y = torch.zeros(1, 1, 8)
        return torch.tensor(val)

    def fake_training_step_d(batch):
        # Production reads self._y_hat; assert it's non-None at D entry.
        assert fake._y_hat is not None, (
            "D entered with stale-cleared _y_hat — would crash production"
        )
        return torch.tensor(loss_d_value)

    fake.training_step_g = fake_training_step_g
    fake.training_step_d = fake_training_step_d
    fake.manual_backward = mock.MagicMock()
    fake._log_with_batch_info = mock.MagicMock()
    fake.model_g = mock.MagicMock()
    fake.model_d = mock.MagicMock()
    fake.model_d_wavlm = None
    fake._g_call_counter = g_calls
    return fake


class TestDUpdateIntervalNaNSkip:
    """d_update_interval > 1 と NaN-skip の組み合わせで stale state が
    残らないことを検証。"""

    def test_nan_skip_with_d_update_interval_2(self):
        """step 1 で loss_g=NaN かつ d_update_interval=2 のとき、
        step 0 の ``_y_hat`` を stale 再利用して D forward を走らせては
        いけない。NaN-skip 経路では D を実行せず、``_y_hat`` を None に
        clear する。"""
        fake = _make_fake_model(
            d_update_interval=2,
            loss_g_sequence=[1.0, float("nan")],
        )
        batch = _FakeBatch()

        # Step 0: finite loss_g, update_generator=True, D 通常実行
        fake.global_step = 0
        VitsModel.training_step(fake, batch, batch_idx=0)
        assert fake._y_hat is None, "Step 0 終端で _y_hat は clear される"
        step0_d_steps = fake._opt_d.step_calls
        assert step0_d_steps == 1, "Step 0 で D step が 1 回"

        # Step 1: loss_g=NaN, update_generator=False (1 % 2 != 0)
        # → NaN-skip 経路に入り D は走らない (= D step 数増えない)
        fake.global_step = 1
        VitsModel.training_step(fake, batch, batch_idx=1)
        assert fake._y_hat is None, (
            "NaN skip 後 _y_hat は None にクリアされ stale 再利用が防がれる"
        )
        assert fake._opt_d.step_calls == step0_d_steps, (
            "NaN skip 経路では D backward+step は実行されない (stale _y_hat の "
            "再利用も発生しない)"
        )

    def test_nan_skip_consistency_across_d_intervals(self):
        """d_update_interval=1 と 2 で NaN-skip の判定回数が一致する。"""
        plan = [1.0, 1.0, float("nan"), 1.0]
        skip_counts = {}

        for interval in (1, 2):
            fake = _make_fake_model(
                d_update_interval=interval,
                loss_g_sequence=plan,
            )
            batch = _FakeBatch()
            for step in range(len(plan)):
                fake.global_step = step
                VitsModel.training_step(fake, batch, batch_idx=step)

            # Count skip events: production calls _log_with_batch_info(
            # "non_finite_skip", 1.0, batch) on G NaN skip.
            skip_count = sum(
                1
                for call in fake._log_with_batch_info.call_args_list
                if call.args and call.args[0] == "non_finite_skip"
            )
            skip_counts[interval] = skip_count

        assert skip_counts[1] == skip_counts[2], (
            f"NaN-skip 回数は d_update_interval に依存しないはず: "
            f"{skip_counts}"
        )
        assert skip_counts[1] == 1, (
            "step=2 の planted NaN がちょうど 1 回 skip として記録される"
        )
