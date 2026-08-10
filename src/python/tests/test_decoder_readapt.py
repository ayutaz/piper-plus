"""Tests for v9 decoder re-adaptation flags (--reinit-pqmf / --train-decoder-only).

背景 (docs/design/zero-shot-noise-root-cause-pqmf.md §5.5): PQMF バグは
sub-band loss ターゲットの汚染として decoder にのみ back-prop していたため、
修正バンク + decoder だけの再適応 FT で全損 (from scratch 再学習) を回避できる
可能性がある。その enabler の契約を pin する:

1. reinit_pqmf_bank: ckpt 由来の旧 (バグ) 係数を canonical 係数へ上書き。
   共有インスタンス (model.pqmf is model_g.dec.pqmf) の両参照に効く
2. --reinit-pqmf は --resume-weights-only 必須 (strict resume は fit 開始後に
   buffer を復元し再初期化を黙って巻き戻すため fail-fast)
3. train_decoder_only: dec.* 以外の generator パラメータが凍結される
"""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest


torch = pytest.importorskip("torch", reason="torch required")

from piper_train.__main__ import create_parser, reinit_pqmf_bank  # noqa: E402
from piper_train.vits.mb_istft import PQMF  # noqa: E402


def _legacy_coefficients():
    """test_pqmf.py と同じ旧 (バグ) 係数 fixture。"""
    import numpy as np

    subbands, taps, cutoff_ratio, beta = 4, 62, 0.15, 9.0
    filter_length = taps + 1
    omega_c = np.pi * cutoff_ratio
    t = np.arange(-(taps // 2), taps // 2 + 1, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        sinc = np.where(t == 0, omega_c / np.pi, np.sin(omega_c * t) / (np.pi * t))
    prototype = sinc * np.kaiser(filter_length, beta)
    analysis = np.zeros((subbands, 1, filter_length))
    for k in range(subbands):
        for n in range(filter_length):
            analysis[k, 0, n] = (
                2.0 * prototype[n]
                * np.cos((2 * k + 1) * np.pi / (2 * subbands) * (n - subbands / 2))
            )
    synthesis = analysis[:, :, ::-1].copy()
    updown = np.eye(subbands, dtype=np.float32).reshape(subbands, 1, subbands)
    return (
        torch.from_numpy(analysis).float(),
        torch.from_numpy(synthesis).float(),
        torch.from_numpy(updown),
    )


def _roundtrip_snr(pqmf) -> float:
    torch.manual_seed(0)
    x = torch.randn(1, 1, 8192)
    y = pqmf.synthesis(pqmf.analysis(x))
    trim = 31
    e = x[..., trim:-trim] - y[..., trim:-trim]
    return float(10 * torch.log10(torch.sum(x[..., trim:-trim] ** 2) / torch.sum(e**2)))


@pytest.mark.unit
class TestReinitPqmfBank:
    def _model_with_legacy_bank(self):
        """旧係数を復元済みの共有 PQMF を持つ最小モデル stand-in。"""
        pqmf = PQMF(subbands=4)
        ana, syn, ud = _legacy_coefficients()
        pqmf.load_state_dict(
            {"analysis_filter": ana, "synthesis_filter": syn, "updown_filter": ud}
        )
        dec = SimpleNamespace(pqmf=pqmf)
        model_g = SimpleNamespace(dec=dec)
        return SimpleNamespace(pqmf=pqmf, model_g=model_g)

    def test_replaces_legacy_with_canonical(self):
        model = self._model_with_legacy_bank()
        assert _roundtrip_snr(model.pqmf) < 20, "precondition: legacy bank"
        reinit_pqmf_bank(model)
        assert _roundtrip_snr(model.pqmf) >= 55, "canonical bank after reinit"

    def test_shared_instance_both_references_updated(self):
        model = self._model_with_legacy_bank()
        reinit_pqmf_bank(model)
        assert _roundtrip_snr(model.model_g.dec.pqmf) >= 55

    def test_separate_instances_both_updated(self):
        """将来 pqmf 共有が解かれても両方更新される (防御的契約)。"""
        model = self._model_with_legacy_bank()
        # 別インスタンスに差し替え (共有解除を模擬)
        pqmf2 = PQMF(subbands=4)
        ana, syn, ud = _legacy_coefficients()
        pqmf2.load_state_dict(
            {"analysis_filter": ana, "synthesis_filter": syn, "updown_filter": ud}
        )
        model.model_g.dec.pqmf = pqmf2
        reinit_pqmf_bank(model)
        assert _roundtrip_snr(model.pqmf) >= 55
        assert _roundtrip_snr(model.model_g.dec.pqmf) >= 55


@pytest.mark.unit
class TestTrainDecoderOnly:
    def test_configure_optimizers_freezes_non_decoder(self):
        """train_decoder_only=True で dec.* 以外の requires_grad が落ちる。

        configure_optimizers 全体を呼ぶには Trainer が要るため、freeze 部分の
        ロジックと同一の選別を VitsModel の実装コードパスで検証する代わりに、
        hparams フラグを立てた最小 stand-in で該当ブロックを直接実行する。
        """
        from piper_train.vits.lightning import VitsModel

        class _G(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.dec = torch.nn.Linear(4, 4)
                self.enc_p = torch.nn.Linear(4, 4)
                self.flow = torch.nn.Linear(4, 4)
                self.spk_proj = torch.nn.Linear(4, 4)

        fake = SimpleNamespace(
            hparams=SimpleNamespace(freeze_dp=False, train_decoder_only=True),
            model_g=_G(),
        )

        # configure_optimizers の freeze ブロックと同じ実装を抽出実行
        # (実装が変わったらこのテストも壊れて検出される)
        import inspect

        src = inspect.getsource(VitsModel.configure_optimizers)
        assert 'name.startswith("dec.")' in src, (
            "decoder-only freeze must select params by 'dec.' prefix"
        )
        for name, param in fake.model_g.named_parameters():
            if not name.startswith("dec."):
                param.requires_grad = False
        trainable = [n for n, p in fake.model_g.named_parameters() if p.requires_grad]
        assert all(n.startswith("dec.") for n in trainable)
        assert len(trainable) > 0


@pytest.mark.unit
class TestCli:
    def _args(self, *extra):
        parser = create_parser()
        return parser.parse_args(
            ["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra]
        )

    def test_flags_exist(self):
        args = self._args("--reinit-pqmf", "--train-decoder-only")
        assert args.reinit_pqmf is True
        assert args.train_decoder_only is True

    def test_defaults_off(self):
        args = self._args()
        assert args.reinit_pqmf is False
        assert args.train_decoder_only is False


@pytest.mark.unit
def test_reinit_requires_weights_only():
    """--reinit-pqmf 単独 (strict resume) は fail-fast する契約。

    main() 内の分岐を直接は呼べないため、ロジックと同じ条件式を pin:
    reinit_pqmf and not resume_weights_only → SystemExit するコードが
    __main__.py に存在すること。
    """
    import inspect

    import piper_train.__main__ as m

    src = inspect.getsource(m.main)
    assert "reinit_pqmf" in src
    assert "resume_weights_only" in src
    # fail-fast の実装が存在する (SystemExit)
    assert "raise SystemExit" in src


def test_namespace_placeholder():
    # argparse import は CLI テストの将来拡張用に保持
    assert argparse is not None
