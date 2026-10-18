"""resume 系 3 経路で checkpoint の参照 hparam と今回の値を照合する (Ruling R16)。

参照融合計画 §8 の最終レビュー I3。``reference_spec_frontend`` /
``generator_reference`` / ``reference_max_frames`` は参照条件付きモデルの契約
(export・評価がこの宣言に従う) なので、resume で黙って変えると epoch によって
宣言の違う checkpoint ができ、評価の比較が成り立たなくなる。

固定する契約:

* strict resume (``--resume_from_checkpoint``、``VitsModel.on_load_checkpoint``
  で fit 中だけ): どの key の食い違いも ``SystemExit``。key 名・両方の値・
  続け方を書く。重みは読み込まない。
* weights-only (``--resume-weights-only``) と multispeaker FT
  (``--resume-from-multispeaker-checkpoint``): ``reference_spec_frontend`` の
  食い違いは ``SystemExit`` (参照 spec の分布が変わる)。``generator_reference`` /
  ``reference_max_frames`` は key 名と両方の値を WARNING に出して続ける。
* ``reference_spec_frontend`` / ``reference_max_frames`` を比べるのは
  checkpoint と今回の両方が同じ参照条件付き (none 以外) のときだけ。
  ``generator_reference`` は none を含むすべての mode で比べる (Ruling R16a:
  C0 = none + cross_utt は S5 の主な比較群)。どの key も checkpoint に key が
  ない、または値が None (宣言なし) なら黙って受け入れる (旧 none ckpt は従来
  どおり)。
* ``reference_conditioning`` 自体の食い違いは state_dict の key 差で止まる
  (strict は ``SystemExit``)。この照合では扱わない。
"""

from __future__ import annotations

import logging
import shlex
import shutil

import pytest


torch = pytest.importorskip(
    "torch", reason="resume contract needs the train extra (torch)."
)
pl = pytest.importorskip(
    "pytorch_lightning", reason="strict resume runs a real Lightning restore."
)

from torch.utils.data import DataLoader, TensorDataset  # noqa: E402


pytestmark = pytest.mark.unit

MQ = "no-vad;soxr-mq"
HQ = "no-vad;soxr-hq"

_TINY = {
    "num_symbols": 40,
    "num_speakers": 2,
    "num_languages": 1,
    "dataset": None,
    "upsample_rates": (4, 4),
    "upsample_initial_channel": 32,
    "upsample_kernel_sizes": (16, 16),
    "hidden_channels": 32,
    "inter_channels": 32,
    "filter_channels": 64,
    "n_layers": 1,
    "prosody_dim": 0,
    "gin_channels": 32,
    "use_wavlm_discriminator": False,
}

# checkpoint 側の ref_spec の宣言 (CLI で作れる組み合わせ)
SAVED_REF = {
    "reference_conditioning": "ref_spec",
    "generator_reference": "cross_utt",
    "reference_spec_frontend": MQ,
    "reference_max_frames": 512,
}
# 各 key について、checkpoint と食い違う今回の値
CHANGED = {
    "reference_spec_frontend": HQ,
    "generator_reference": "self",
    "reference_max_frames": 256,
}
CLI_FLAG = {
    "reference_spec_frontend": "--reference-spec-frontend",
    "generator_reference": "--generator-reference",
    "reference_max_frames": "--reference-max-frames",
}
WARN_KEYS = ["generator_reference", "reference_max_frames"]


def _model(seed=0, **overrides):
    from piper_train.vits.lightning import VitsModel

    torch.manual_seed(seed)
    return VitsModel(**{**_TINY, **overrides})


def _trainer(root):
    # limit_train_batches=0: restore (on_load_checkpoint → load_state_dict →
    # optimizer) までは本番どおり走り、training_step は呼ばれない
    return pl.Trainer(
        accelerator="cpu",
        devices=1,
        max_epochs=1,
        limit_train_batches=0,
        limit_val_batches=0,
        num_sanity_val_steps=0,
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
        enable_model_summary=False,
        default_root_dir=root,
    )


def _loader():
    return DataLoader(TensorDataset(torch.zeros(1, 1)), batch_size=1)


def _save_real_checkpoint(root, model):
    """Lightning の save_checkpoint で本物の checkpoint を作る。"""
    trainer = _trainer(root)
    trainer.fit(model, _loader())
    path = root / "saved.ckpt"
    trainer.save_checkpoint(path)
    return path


@pytest.fixture(scope="module")
def saved_ckpts(tmp_path_factory):
    """seed 1 で作った ref_spec / none / C0 の checkpoint (各 test は複製して使う)。

    C0 = none + ``generator_reference="cross_utt"`` (参照モジュールなし)。
    """
    root = tmp_path_factory.mktemp("saved")
    ref = _model(seed=1, **SAVED_REF)
    for kind in ("ref", "none", "c0"):
        (root / kind).mkdir()
    return {
        "ref": (_save_real_checkpoint(root / "ref", ref), ref.state_dict()),
        "none": (
            _save_real_checkpoint(root / "none", _model(seed=1)),
            _model(seed=1).state_dict(),
        ),
        "c0": (
            _save_real_checkpoint(
                root / "c0", _model(seed=1, generator_reference="cross_utt")
            ),
            _model(seed=1, generator_reference="cross_utt").state_dict(),
        ),
    }


def _ckpt(tmp_path, saved_ckpts, kind="ref", *, pop=(), **hparam_changes):
    """保存済み checkpoint を複製し、hyper_parameters を書き換える。"""
    src, _ = saved_ckpts[kind]
    dst = tmp_path / f"{kind}.ckpt"
    shutil.copyfile(src, dst)
    if pop or hparam_changes:
        checkpoint = torch.load(dst, map_location="cpu", weights_only=False)
        for key in pop:
            checkpoint["hyper_parameters"].pop(key)
        checkpoint["hyper_parameters"].update(hparam_changes)
        torch.save(checkpoint, dst)
    return str(dst)


def _current(**changes):
    return _model(seed=2, **{**SAVED_REF, **changes})


def _ref_weights(model):
    return {
        k: v.detach().clone()
        for k, v in model.state_dict().items()
        if k.startswith("model_g.reference_encoder.")
    }


def _same(a, b):
    return a.keys() == b.keys() and all(torch.equal(a[k], b[k]) for k in a)


def _saved_ref_weights(saved_ckpts):
    _, state = saved_ckpts["ref"]
    return {
        k: v for k, v in state.items() if k.startswith("model_g.reference_encoder.")
    }


def _hparam_warnings(caplog):
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.WARNING and "hparam" in r.getMessage()
    ]


def _strict(tmp_path, model, ckpt):
    from piper_train.__main__ import run_strict_resume

    run_strict_resume(_trainer(tmp_path / "resume"), model, ckpt)


def _weights_only(model, ckpt):
    from piper_train.__main__ import load_weights_only_checkpoint

    return load_weights_only_checkpoint(ckpt, model)


def _finetune(model, ckpt):
    from piper_train.__main__ import load_multispeaker_checkpoint

    load_multispeaker_checkpoint(ckpt, model)


# ---------------------------------------------------------------------------
# strict resume (trainer.fit(ckpt_path) → VitsModel.on_load_checkpoint)
# ---------------------------------------------------------------------------


class TestStrictResume:
    def test_matching_hparams_resume_and_restore_weights(self, tmp_path, saved_ckpts):
        model = _current()
        _strict(tmp_path, model, _ckpt(tmp_path, saved_ckpts))
        assert _same(_ref_weights(model), _saved_ref_weights(saved_ckpts))

    @pytest.mark.parametrize("key", sorted(CHANGED))
    def test_mismatch_exits(self, tmp_path, saved_ckpts, key):
        with pytest.raises(SystemExit):
            _strict(
                tmp_path, _current(**{key: CHANGED[key]}), _ckpt(tmp_path, saved_ckpts)
            )

    @pytest.mark.parametrize("key", sorted(CHANGED))
    def test_mismatch_message_names_key_and_both_values(
        self, tmp_path, saved_ckpts, key
    ):
        with pytest.raises(SystemExit) as excinfo:
            _strict(
                tmp_path, _current(**{key: CHANGED[key]}), _ckpt(tmp_path, saved_ckpts)
            )
        message = str(excinfo.value)
        assert key in message
        assert repr(SAVED_REF[key]) in message
        assert repr(CHANGED[key]) in message

    @pytest.mark.parametrize("key", sorted(CHANGED))
    def test_mismatch_message_says_how_to_continue(self, tmp_path, saved_ckpts, key):
        """今回の flag を checkpoint の値に戻す方法を書く。"""
        with pytest.raises(SystemExit) as excinfo:
            _strict(
                tmp_path, _current(**{key: CHANGED[key]}), _ckpt(tmp_path, saved_ckpts)
            )
        # shell にそのまま貼れるよう値は quote する (frontend 名は ';' を含む)
        expected = f"{CLI_FLAG[key]} {shlex.quote(str(SAVED_REF[key]))}"
        assert expected in str(excinfo.value)

    @pytest.mark.parametrize("key", WARN_KEYS)
    def test_warm_start_changeable_key_points_to_weights_only(
        self, tmp_path, saved_ckpts, key
    ):
        with pytest.raises(SystemExit) as excinfo:
            _strict(
                tmp_path, _current(**{key: CHANGED[key]}), _ckpt(tmp_path, saved_ckpts)
            )
        assert "--resume-weights-only" in str(excinfo.value)

    def test_frontend_mismatch_points_to_new_run_not_weights_only(
        self, tmp_path, saved_ckpts
    ):
        """frontend は weights-only でも変えられないので新しい run を案内する。"""
        with pytest.raises(SystemExit) as excinfo:
            _strict(
                tmp_path,
                _current(reference_spec_frontend=HQ),
                _ckpt(tmp_path, saved_ckpts),
            )
        message = str(excinfo.value)
        assert "new run" in message
        assert "--resume-weights-only" not in message

    def test_mismatch_does_not_load_weights(self, tmp_path, saved_ckpts):
        model = _current(reference_max_frames=256)
        before = _ref_weights(model)
        with pytest.raises(SystemExit):
            _strict(tmp_path, model, _ckpt(tmp_path, saved_ckpts))
        assert _same(_ref_weights(model), before)
        assert not _same(before, _saved_ref_weights(saved_ckpts))

    def test_all_mismatches_are_reported_together(self, tmp_path, saved_ckpts):
        with pytest.raises(SystemExit) as excinfo:
            _strict(tmp_path, _current(**CHANGED), _ckpt(tmp_path, saved_ckpts))
        assert all(key in str(excinfo.value) for key in CHANGED)

    @pytest.mark.parametrize("key", sorted(CHANGED))
    def test_legacy_checkpoint_without_key_resumes(self, tmp_path, saved_ckpts, key):
        model = _current(**{key: CHANGED[key]})
        _strict(tmp_path, model, _ckpt(tmp_path, saved_ckpts, pop=(key,)))
        assert _same(_ref_weights(model), _saved_ref_weights(saved_ckpts))

    def test_undeclared_frontend_checkpoint_resumes(self, tmp_path, saved_ckpts):
        """値が None (宣言なし) の checkpoint は key なしと同じく受け入れる。"""
        model = _current()
        _strict(
            tmp_path, model, _ckpt(tmp_path, saved_ckpts, reference_spec_frontend=None)
        )
        assert _same(_ref_weights(model), _saved_ref_weights(saved_ckpts))

    def test_none_mode_max_frames_is_not_compared(self, tmp_path, saved_ckpts):
        """none では reference_max_frames を照合しない (参照 spec を使わない)。"""
        model = _model(seed=2, reference_max_frames=256)
        _strict(tmp_path, model, _ckpt(tmp_path, saved_ckpts, "none"))
        _, state = saved_ckpts["none"]
        assert torch.equal(
            model.state_dict()["model_g.spk_proj.0.weight"],
            state["model_g.spk_proj.0.weight"],
        )

    def test_conditioning_mismatch_is_stopped_by_state_dict(
        self, tmp_path, saved_ckpts
    ):
        """reference_conditioning の食い違いは state_dict の key 差で止まる。"""
        model = _model(
            seed=2, reference_conditioning="capacity", generator_reference="cross_utt"
        )
        with pytest.raises(SystemExit, match="strict resume"):
            _strict(tmp_path, model, _ckpt(tmp_path, saved_ckpts))

    def test_load_from_checkpoint_with_override_is_not_checked(
        self, tmp_path, saved_ckpts
    ):
        """fit 以外 (export・評価の load_from_checkpoint) では照合しない。"""
        from piper_train.vits.lightning import VitsModel

        loaded = VitsModel.load_from_checkpoint(
            _ckpt(tmp_path, saved_ckpts), dataset=None, reference_max_frames=256
        )
        assert loaded.hparams.reference_max_frames == 256


# ---------------------------------------------------------------------------
# weights-only (--resume-weights-only) / multispeaker FT
# ---------------------------------------------------------------------------

WARM_STARTS = {"weights_only": _weights_only, "finetune": _finetune}
WARM_FLAGS = {
    "weights_only": "--resume-weights-only",
    "finetune": "--resume-from-multispeaker-checkpoint",
}


@pytest.mark.parametrize("path", sorted(WARM_STARTS))
class TestWarmStart:
    def test_matching_hparams_load_without_warning(
        self, tmp_path, saved_ckpts, caplog, path
    ):
        model = _current()
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            WARM_STARTS[path](model, _ckpt(tmp_path, saved_ckpts))
        assert _hparam_warnings(caplog) == []
        assert _same(_ref_weights(model), _saved_ref_weights(saved_ckpts))

    def test_frontend_mismatch_exits(self, tmp_path, saved_ckpts, path):
        with pytest.raises(SystemExit):
            WARM_STARTS[path](
                _current(reference_spec_frontend=HQ), _ckpt(tmp_path, saved_ckpts)
            )

    def test_frontend_mismatch_message(self, tmp_path, saved_ckpts, path):
        with pytest.raises(SystemExit) as excinfo:
            WARM_STARTS[path](
                _current(reference_spec_frontend=HQ), _ckpt(tmp_path, saved_ckpts)
            )
        message = str(excinfo.value)
        assert "reference_spec_frontend" in message
        assert repr(MQ) in message and repr(HQ) in message
        assert f"--reference-spec-frontend {shlex.quote(MQ)}" in message
        assert WARM_FLAGS[path] in message

    def test_frontend_mismatch_does_not_mutate_weights(
        self, tmp_path, saved_ckpts, path
    ):
        model = _current(reference_spec_frontend=HQ)
        before = {k: v.detach().clone() for k, v in model.state_dict().items()}
        with pytest.raises(SystemExit):
            WARM_STARTS[path](model, _ckpt(tmp_path, saved_ckpts))
        assert _same(model.state_dict(), before)

    @pytest.mark.parametrize("key", WARN_KEYS)
    def test_changeable_key_mismatch_warns_once(
        self, tmp_path, saved_ckpts, caplog, path, key
    ):
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            WARM_STARTS[path](
                _current(**{key: CHANGED[key]}), _ckpt(tmp_path, saved_ckpts)
            )
        assert len(_hparam_warnings(caplog)) == 1

    @pytest.mark.parametrize("key", WARN_KEYS)
    def test_changeable_key_warning_names_key_values_and_path(
        self, tmp_path, saved_ckpts, caplog, path, key
    ):
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            WARM_STARTS[path](
                _current(**{key: CHANGED[key]}), _ckpt(tmp_path, saved_ckpts)
            )
        (message,) = _hparam_warnings(caplog)
        assert key in message
        assert repr(SAVED_REF[key]) in message
        assert repr(CHANGED[key]) in message
        assert WARM_FLAGS[path] in message

    @pytest.mark.parametrize("key", WARN_KEYS)
    def test_changeable_key_mismatch_still_loads_weights(
        self, tmp_path, saved_ckpts, path, key
    ):
        model = _current(**{key: CHANGED[key]})
        WARM_STARTS[path](model, _ckpt(tmp_path, saved_ckpts))
        assert _same(_ref_weights(model), _saved_ref_weights(saved_ckpts))
        assert model.hparams[key] == CHANGED[key]

    @pytest.mark.parametrize("key", sorted(CHANGED))
    def test_legacy_checkpoint_without_key_loads_silently(
        self, tmp_path, saved_ckpts, caplog, path, key
    ):
        model = _current(**{key: CHANGED[key]})
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            WARM_STARTS[path](model, _ckpt(tmp_path, saved_ckpts, pop=(key,)))
        assert _hparam_warnings(caplog) == []
        assert _same(_ref_weights(model), _saved_ref_weights(saved_ckpts))

    def test_undeclared_frontend_checkpoint_loads_silently(
        self, tmp_path, saved_ckpts, caplog, path
    ):
        model = _current()
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            WARM_STARTS[path](
                model, _ckpt(tmp_path, saved_ckpts, reference_spec_frontend=None)
            )
        assert _hparam_warnings(caplog) == []

    def test_checkpoint_without_hyper_parameters_loads(
        self, tmp_path, saved_ckpts, caplog, path
    ):
        """hyper_parameters 自体のない checkpoint (手で作った ckpt 等)。"""
        src = _ckpt(tmp_path, saved_ckpts)
        checkpoint = torch.load(src, map_location="cpu", weights_only=False)
        del checkpoint["hyper_parameters"]
        torch.save(checkpoint, src)
        model = _current(reference_spec_frontend=HQ)
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            WARM_STARTS[path](model, src)
        assert _hparam_warnings(caplog) == []
        assert _same(_ref_weights(model), _saved_ref_weights(saved_ckpts))


class TestWarmStartNoneMode:
    def test_none_checkpoint_into_reference_model_is_not_compared(
        self, tmp_path, saved_ckpts, caplog
    ):
        """C0 の ckpt (cross_utt / 512 / None) から ref_spec を warm start する。

        frontend・max_frames は none の ckpt と比べない (generator_reference は
        一致させて、この性質だけを見る)。
        """
        model = _current(reference_spec_frontend=HQ, reference_max_frames=256)
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            _weights_only(model, _ckpt(tmp_path, saved_ckpts, "c0"))
        assert _hparam_warnings(caplog) == []

    def test_none_to_none_weights_only_max_frames_is_not_compared(
        self, tmp_path, saved_ckpts, caplog
    ):
        model = _model(seed=2, reference_max_frames=256)
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            _weights_only(model, _ckpt(tmp_path, saved_ckpts, "none"))
        assert _hparam_warnings(caplog) == []

    def test_reference_checkpoint_into_single_speaker_finetune_is_not_compared(
        self, tmp_path, saved_ckpts, caplog
    ):
        """single-speaker の FT 先 (none) は参照 weights を捨てる従来の経路 (R9)。

        frontend・max_frames は none の FT 先と比べない (generator_reference は
        一致させて、この性質だけを見る)。
        """
        model = _model(seed=2, num_speakers=1, generator_reference="cross_utt")
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            _finetune(model, _ckpt(tmp_path, saved_ckpts))
        assert _hparam_warnings(caplog) == []
        assert any(
            "reference-conditioning weights" in r.getMessage() for r in caplog.records
        )


# ---------------------------------------------------------------------------
# generator_reference は none を含むすべての mode で比べる (Ruling R16a)
# ---------------------------------------------------------------------------


def _shared_weight(model, saved_ckpts, kind):
    """single-speaker FT 先とも共有する text encoder の重みが ckpt と同じか。"""
    _, state = saved_ckpts[kind]
    key = "model_g.enc_p.emb.weight"
    return torch.equal(model.state_dict()[key], state[key])


def _warm_target(path, **overrides):
    # FT 先は single-speaker (CLI の --resume-from-multispeaker-checkpoint と同じ)
    speakers = {"num_speakers": 1} if path == "finetune" else {}
    return _model(seed=2, **speakers, **overrides)


class TestGeneratorReferenceStrictResume:
    def test_c0_checkpoint_resumed_as_self_exits(self, tmp_path, saved_ckpts):
        with pytest.raises(SystemExit):
            _strict(tmp_path, _model(seed=2), _ckpt(tmp_path, saved_ckpts, "c0"))

    def test_c0_mismatch_message_names_key_values_and_weights_only(
        self, tmp_path, saved_ckpts
    ):
        with pytest.raises(SystemExit) as excinfo:
            _strict(tmp_path, _model(seed=2), _ckpt(tmp_path, saved_ckpts, "c0"))
        message = str(excinfo.value)
        assert "generator_reference" in message
        assert "'cross_utt'" in message and "'self'" in message
        assert "--generator-reference cross_utt" in message
        assert "--resume-weights-only" in message

    def test_c0_mismatch_does_not_load_weights(self, tmp_path, saved_ckpts):
        model = _model(seed=2)
        with pytest.raises(SystemExit):
            _strict(tmp_path, model, _ckpt(tmp_path, saved_ckpts, "c0"))
        assert not _shared_weight(model, saved_ckpts, "c0")

    def test_self_checkpoint_resumed_as_cross_utt_exits(self, tmp_path, saved_ckpts):
        model = _model(seed=2, generator_reference="cross_utt")
        with pytest.raises(SystemExit, match="generator_reference"):
            _strict(tmp_path, model, _ckpt(tmp_path, saved_ckpts, "none"))

    @pytest.mark.parametrize(("kind", "mode"), [("none", "self"), ("c0", "cross_utt")])
    def test_matching_none_mode_resumes(self, tmp_path, saved_ckpts, kind, mode):
        model = _model(seed=2, generator_reference=mode)
        _strict(tmp_path, model, _ckpt(tmp_path, saved_ckpts, kind))
        assert _shared_weight(model, saved_ckpts, kind)


@pytest.mark.parametrize("path", sorted(WARM_STARTS))
class TestGeneratorReferenceWarmStart:
    def test_none_mismatch_warns_once(self, tmp_path, saved_ckpts, caplog, path):
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            WARM_STARTS[path](_warm_target(path), _ckpt(tmp_path, saved_ckpts, "c0"))
        assert len(_hparam_warnings(caplog)) == 1

    def test_none_mismatch_warning_names_key_values_and_path(
        self, tmp_path, saved_ckpts, caplog, path
    ):
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            WARM_STARTS[path](_warm_target(path), _ckpt(tmp_path, saved_ckpts, "c0"))
        (message,) = _hparam_warnings(caplog)
        assert "generator_reference" in message
        assert "'cross_utt'" in message and "'self'" in message
        assert WARM_FLAGS[path] in message

    def test_none_mismatch_still_loads_weights(self, tmp_path, saved_ckpts, path):
        model = _warm_target(path)
        WARM_STARTS[path](model, _ckpt(tmp_path, saved_ckpts, "c0"))
        assert _shared_weight(model, saved_ckpts, "c0")

    def test_matching_none_mode_loads_without_warning(
        self, tmp_path, saved_ckpts, caplog, path
    ):
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            WARM_STARTS[path](_warm_target(path), _ckpt(tmp_path, saved_ckpts, "none"))
        assert _hparam_warnings(caplog) == []


class TestLegacyNoneCheckpointWithoutKey:
    """generator_reference を持たない旧 none ckpt は、どの経路でも黙って読む。"""

    def test_strict_resume(self, tmp_path, saved_ckpts):
        model = _model(seed=2, generator_reference="cross_utt")
        ckpt = _ckpt(tmp_path, saved_ckpts, "none", pop=("generator_reference",))
        _strict(tmp_path, model, ckpt)
        assert _shared_weight(model, saved_ckpts, "none")

    @pytest.mark.parametrize("path", sorted(WARM_STARTS))
    def test_warm_start(self, tmp_path, saved_ckpts, caplog, path):
        model = _warm_target(path, generator_reference="cross_utt")
        ckpt = _ckpt(tmp_path, saved_ckpts, "none", pop=("generator_reference",))
        with caplog.at_level(logging.WARNING, logger="piper_train"):
            WARM_STARTS[path](model, ckpt)
        assert _hparam_warnings(caplog) == []
        assert _shared_weight(model, saved_ckpts, "none")
