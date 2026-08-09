"""Tests for --resume-weights-only (warm restart) in __main__.py.

v8.1 継続学習の要: 学習済み ckpt (WavLM なし) に対して WavLM discriminator を
後から有効化すると、strict Trainer resume は missing keys / optimizer param 数
不一致で成立しない。--resume-weights-only は weights のみ strict=False で読み、
epoch 0 + 新しい optimizer / LR schedule で学習を開始する。

Covers:
1. 一致キーはロードされ、ckpt に無いキー (model_d_wavlm 相当) は fresh-init のまま
2. ckpt にしか無いキーは捨てられる
3. legacy HiFi-GAN ckpt は明示エラー
4. 他の resume 系フラグとの併用は fail-fast
5. CLI surface: フラグが argparse に存在する
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest


torch = pytest.importorskip("torch")

from piper_train.__main__ import (  # noqa: E402
    check_resume_flags_exclusive,
    create_parser,
    load_weights_only_checkpoint,
)


class _TinyBase(torch.nn.Module):
    """ckpt 保存側: WavLM discriminator を持たないモデルの stand-in。"""

    def __init__(self):
        super().__init__()
        self.model_g = torch.nn.Linear(4, 4)
        self.model_d = torch.nn.Linear(4, 4)


class _TinyWithWavlm(_TinyBase):
    """継続学習側: WavLM discriminator が追加されたモデルの stand-in。"""

    def __init__(self):
        super().__init__()
        self.model_d_wavlm = torch.nn.Linear(4, 4)


def _save_ckpt(tmp_path: Path, model: torch.nn.Module) -> str:
    p = tmp_path / "base.ckpt"
    torch.save({"state_dict": model.state_dict()}, p)
    return str(p)


@pytest.mark.unit
class TestLoadWeightsOnly:
    def test_matching_keys_loaded(self, tmp_path):
        src = _TinyBase()
        ckpt = _save_ckpt(tmp_path, src)
        dst = _TinyBase()
        missing, unexpected = load_weights_only_checkpoint(ckpt, dst)
        assert missing == []
        assert unexpected == []
        assert torch.equal(dst.model_g.weight, src.model_g.weight)

    def test_new_wavlm_params_stay_fresh_init(self, tmp_path):
        """ckpt に無い model_d_wavlm.* は missing 扱いで fresh-init のまま残る。"""
        src = _TinyBase()
        ckpt = _save_ckpt(tmp_path, src)
        dst = _TinyWithWavlm()
        before = dst.model_d_wavlm.weight.clone()
        missing, unexpected = load_weights_only_checkpoint(ckpt, dst)
        assert any(k.startswith("model_d_wavlm.") for k in missing)
        assert unexpected == []
        # 共有部分はロードされ、wavlm は初期値のまま
        assert torch.equal(dst.model_g.weight, src.model_g.weight)
        assert torch.equal(dst.model_d_wavlm.weight, before)

    def test_extra_ckpt_keys_dropped(self, tmp_path):
        """ckpt にしか無いキーは unexpected として捨てられる (crash しない)。"""
        src = _TinyWithWavlm()
        ckpt = _save_ckpt(tmp_path, src)
        dst = _TinyBase()
        missing, unexpected = load_weights_only_checkpoint(ckpt, dst)
        assert missing == []
        assert any(k.startswith("model_d_wavlm.") for k in unexpected)

    def test_legacy_hifigan_ckpt_rejected(self, tmp_path):
        """HiFi-GAN 系 ckpt (dec あり・MB-iSTFT マーカーなし) は明示エラー。"""

        class _LegacyLike(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.layer = torch.nn.Linear(2, 2)

            def state_dict(self, *a, **kw):  # noqa: ARG002
                return {"model_g.dec.ups.0.weight": torch.zeros(1)}

        p = tmp_path / "legacy.ckpt"
        torch.save({"state_dict": _LegacyLike().state_dict()}, p)
        with pytest.raises(RuntimeError, match="HiFi-GAN|MB-iSTFT|v1.12"):
            load_weights_only_checkpoint(str(p), _TinyBase())


@pytest.mark.unit
class TestResumeFlagExclusivity:
    @staticmethod
    def _args(**kw):
        base = {
            "resume_weights_only": None,
            "resume_from_checkpoint": None,
            "resume_from_multispeaker_checkpoint": None,
            "resume_from_single_speaker_checkpoint": None,
        }
        base.update(kw)
        return argparse.Namespace(**base)

    def test_alone_is_ok(self):
        check_resume_flags_exclusive(self._args(resume_weights_only="a.ckpt"))

    def test_absent_is_ok_with_other_flags(self):
        check_resume_flags_exclusive(self._args(resume_from_checkpoint="a.ckpt"))

    @pytest.mark.parametrize(
        "other",
        [
            "resume_from_checkpoint",
            "resume_from_multispeaker_checkpoint",
            "resume_from_single_speaker_checkpoint",
        ],
    )
    def test_combination_rejected(self, other):
        args = self._args(resume_weights_only="a.ckpt", **{other: "b.ckpt"})
        with pytest.raises(SystemExit, match="resume-weights-only"):
            check_resume_flags_exclusive(args)


@pytest.mark.unit
def test_cli_advertises_flag():
    parser = create_parser()
    args = parser.parse_args(
        [
            "--dataset-dir", "/tmp/x",
            "--batch-size", "1",
            "--resume-weights-only", "/tmp/base.ckpt",
        ]
    )
    assert args.resume_weights_only == "/tmp/base.ckpt"
