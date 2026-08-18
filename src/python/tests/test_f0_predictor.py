"""S-2p: frame prior F0/V-UV predictor と GT 回帰 loss の TDD テスト。

docs/design/zero-shot-v10b-s2-f0-design.md §4 (predictor 設計) / §5 (契約適合)。

固定する契約:

* **padding 安全**: 予測は有効フレーム長の外側の内容に依存しない。バッチ内の
  padding が変わるだけで予測が動くと、学習 (バッチ) と推論 (単発) で別の値が
  出る = 再現不能になる。
* **話者条件の勾配経路**: default は ``g.detach()`` + 専用ヘッド ``spk_proj_f0``
  で spk_proj 本体を保護 (v10 M3 の ``spk_proj_dp`` と同じ流儀)。
  ``f0_spk_grad=True`` でのみ本体へ流す。
* **loss は GT frame-level F0 の per-frame 回帰**であり、生成音声の F0 統計を
  一切参照しない (zs-eval-contract §2 禁止事項 4 の例外条項に乗る形)。
  → 構造ガードは ``test_f0_contract_guard.py`` が別途固定する。
* **teacher forcing アニール**の scheduling は純関数で決まる。
"""

from __future__ import annotations

import math

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.vits.losses import (  # noqa: E402
    f0_prediction_loss,
    f0_teacher_forcing_prob,
)
from piper_train.vits.models import F0Predictor  # noqa: E402


def _mask(lengths, max_len):
    ar = torch.arange(max_len).unsqueeze(0)
    return (ar < torch.tensor(lengths).unsqueeze(1)).unsqueeze(1).float()


# --------------------------------------------------------------------------
# F0Predictor
# --------------------------------------------------------------------------


def test_predictor_output_shapes_and_masking():
    pred = F0Predictor(in_channels=192, hidden_channels=96, gin_channels=512)
    pred.eval()
    x = torch.randn(2, 192, 20)
    mask = _mask([20, 12], 20)
    g = torch.randn(2, 512, 1)

    with torch.no_grad():
        logf0, vuv_logit = pred(x, mask, g=g)

    assert logf0.shape == (2, 1, 20)
    assert vuv_logit.shape == (2, 1, 20)
    # padding 区間は 0 でマスクされている
    assert torch.all(logf0[1, :, 12:] == 0.0)
    assert torch.all(vuv_logit[1, :, 12:] == 0.0)


def test_predictor_is_padding_safe():
    """有効区間の予測が padding の長さ・中身に依存しない。

    GroupNorm を素朴に使うと padding が正規化統計に混ざり、この不変条件が
    壊れる (バッチ構成で予測が動く = train/infer 不一致)。
    """
    pred = F0Predictor(in_channels=192, hidden_channels=64, gin_channels=0)
    pred.eval()
    torch.manual_seed(0)
    core = torch.randn(1, 192, 10)

    short = core
    long = torch.cat([core, torch.randn(1, 192, 14)], dim=-1)

    with torch.no_grad():
        a, _ = pred(short, _mask([10], 10))
        b, _ = pred(long, _mask([10], 24))

    # conv の受容野 (k=5, 2 層 → 片側 4 frame) の内側だけ比較する
    torch.testing.assert_close(a[..., :6], b[..., :6], atol=1e-5, rtol=1e-4)


def test_predictor_uses_speaker_conditioning():
    pred = F0Predictor(in_channels=192, hidden_channels=64, gin_channels=512)
    pred.eval()
    x = torch.randn(1, 192, 8)
    mask = _mask([8], 8)
    with torch.no_grad():
        a, _ = pred(x, mask, g=torch.randn(1, 512, 1))
        b, _ = pred(x, mask, g=torch.randn(1, 512, 1))
    assert not torch.allclose(a, b), "speaker conditioning has no effect"


def test_predictor_f0_head_starts_in_a_plausible_range():
    """log F0 ヘッドの bias を log(200Hz) 付近に置き、exp 爆発を避ける。"""
    pred = F0Predictor(in_channels=192, hidden_channels=64, gin_channels=0)
    assert float(pred.proj_f0.bias.detach()) == pytest.approx(
        math.log(200.0), abs=1e-5
    )


# --------------------------------------------------------------------------
# loss
# --------------------------------------------------------------------------


def test_f0_loss_is_zero_for_a_perfect_prediction():
    f0_gt = torch.tensor([[[0.0, 200.0, 220.0, 0.0]]])
    vuv_gt = (f0_gt > 0).float()
    logf0_pred = torch.log(f0_gt.clamp(min=1.0))
    vuv_logit = torch.where(vuv_gt > 0, torch.tensor(20.0), torch.tensor(-20.0))
    mask = torch.ones(1, 1, 4)

    loss_f0, loss_vuv = f0_prediction_loss(
        logf0_pred, vuv_logit, f0_gt, vuv_gt, mask
    )
    assert float(loss_f0) == pytest.approx(0.0, abs=1e-6)
    assert float(loss_vuv) == pytest.approx(0.0, abs=1e-6)


def test_f0_loss_only_counts_voiced_frames():
    """無声フレームの log f0 誤差は L1 に入らない (f0 が未定義のため)。"""
    f0_gt = torch.tensor([[[0.0, 200.0]]])
    vuv_gt = (f0_gt > 0).float()
    mask = torch.ones(1, 1, 2)
    vuv_logit = torch.zeros(1, 1, 2)

    good = torch.tensor([[[0.0, math.log(200.0)]]])
    # 無声フレームだけ大きく外す → loss は変わらないはず
    bad_unvoiced = torch.tensor([[[9.0, math.log(200.0)]]])

    a, _ = f0_prediction_loss(good, vuv_logit, f0_gt, vuv_gt, mask)
    b, _ = f0_prediction_loss(bad_unvoiced, vuv_logit, f0_gt, vuv_gt, mask)
    assert float(a) == pytest.approx(float(b))


def test_f0_loss_is_in_the_log_domain():
    """1 オクターブずれ = log 誤差 ln(2) — 話者間の音域差を乗法的に扱う。"""
    f0_gt = torch.full((1, 1, 4), 200.0)
    vuv_gt = torch.ones(1, 1, 4)
    mask = torch.ones(1, 1, 4)
    octave_up = torch.full((1, 1, 4), math.log(400.0))
    loss_f0, _ = f0_prediction_loss(
        octave_up, torch.zeros(1, 1, 4), f0_gt, vuv_gt, mask
    )
    assert float(loss_f0) == pytest.approx(math.log(2.0), abs=1e-5)


def test_f0_loss_ignores_padded_frames():
    f0_gt = torch.tensor([[[200.0, 200.0, 999.0]]])
    vuv_gt = torch.tensor([[[1.0, 1.0, 1.0]]])
    mask = torch.tensor([[[1.0, 1.0, 0.0]]])
    pred = torch.tensor([[[math.log(200.0), math.log(200.0), 0.0]]])
    loss_f0, _ = f0_prediction_loss(pred, torch.zeros(1, 1, 3), f0_gt, vuv_gt, mask)
    assert float(loss_f0) == pytest.approx(0.0, abs=1e-6)


def test_f0_loss_is_zero_and_finite_when_no_voiced_frames_exist():
    """完全無声バッチで 0/0 の NaN を出さない (non-finite skip を誘発しない)。"""
    f0_gt = torch.zeros(1, 1, 4)
    vuv_gt = torch.zeros(1, 1, 4)
    mask = torch.ones(1, 1, 4)
    loss_f0, loss_vuv = f0_prediction_loss(
        torch.zeros(1, 1, 4), torch.zeros(1, 1, 4), f0_gt, vuv_gt, mask
    )
    assert torch.isfinite(loss_f0) and torch.isfinite(loss_vuv)
    assert float(loss_f0) == 0.0


def test_f0_loss_aggregates_in_float32_under_bf16_inputs():
    """bf16 予測でも集計は fp32 (frame 数の丸めと累積誤差を避ける)。

    bf16 の仮数は 8 bit しかないので、有効フレーム数の総和が 256 を超えると
    正規化分母が丸まる (1000 → 1008)。長い発話ほど loss が系統的にずれる。
    """
    n_frames = 1000
    f0_gt = torch.full((1, 1, n_frames), 200.0)
    vuv_gt = torch.ones(1, 1, n_frames)
    mask = torch.ones(1, 1, n_frames)
    pred = torch.full((1, 1, n_frames), math.log(220.0), dtype=torch.bfloat16)

    loss_f0, loss_vuv = f0_prediction_loss(
        pred,
        torch.zeros(1, 1, n_frames, dtype=torch.bfloat16),
        f0_gt,
        vuv_gt,
        mask,
    )
    assert loss_f0.dtype == torch.float32
    assert loss_vuv.dtype == torch.float32

    # 期待値は「bf16 に丸まった予測値」から作る — 入力の量子化誤差 (log(220)
    # は bf16 で 5.40625) と、ここで検証したい **集計精度** を切り分けるため。
    # 全フレーム同値なので fp32 集計なら誤差ゼロで一致する。bf16 集計だと
    # 総和と分母 (1000 → 1008) の丸めで 0.4% 級ずれるので rel=1e-6 で弁別できる。
    quantised_pred = float(pred[0, 0, 0])
    assert float(loss_f0) == pytest.approx(
        abs(quantised_pred - math.log(200.0)), rel=1e-6
    )


def test_f0_loss_gradient_flows_to_the_predictor():
    pred_logf0 = torch.full((1, 1, 4), math.log(150.0), requires_grad=True)
    vuv_logit = torch.zeros(1, 1, 4, requires_grad=True)
    f0_gt = torch.full((1, 1, 4), 200.0)
    vuv_gt = torch.ones(1, 1, 4)
    loss_f0, loss_vuv = f0_prediction_loss(
        pred_logf0, vuv_logit, f0_gt, vuv_gt, torch.ones(1, 1, 4)
    )
    (loss_f0 + loss_vuv).backward()
    assert float(pred_logf0.grad.abs().sum()) > 0
    assert float(vuv_logit.grad.abs().sum()) > 0


# --------------------------------------------------------------------------
# teacher forcing anneal (§4.4)
# --------------------------------------------------------------------------


def test_teacher_forcing_prob_ramp():
    # K=10, R=10, p_max=0.5 (設計 doc の default)
    assert f0_teacher_forcing_prob(0, 10, 10, 0.5) == 0.0
    assert f0_teacher_forcing_prob(10, 10, 10, 0.5) == 0.0
    assert f0_teacher_forcing_prob(15, 10, 10, 0.5) == pytest.approx(0.25)
    assert f0_teacher_forcing_prob(20, 10, 10, 0.5) == pytest.approx(0.5)
    assert f0_teacher_forcing_prob(100, 10, 10, 0.5) == pytest.approx(0.5)


def test_teacher_forcing_prob_with_zero_ramp_switches_immediately():
    assert f0_teacher_forcing_prob(9, 10, 0, 0.5) == 0.0
    assert f0_teacher_forcing_prob(10, 10, 0, 0.5) == pytest.approx(0.5)


def test_teacher_forcing_prob_is_clamped_to_unit_interval():
    assert f0_teacher_forcing_prob(50, 0, 10, 3.0) == pytest.approx(1.0)
    assert f0_teacher_forcing_prob(5, 10, 10, -1.0) == 0.0
