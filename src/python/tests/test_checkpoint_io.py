"""Linux training metadata must load on Windows CPU without patching pathlib."""

import pathlib

import pytest


torch = pytest.importorskip(
    "torch",
    reason="Checkpoint preparation needs the train extra; lightweight Windows CI omits it.",
)


class SavedPosixPath:
    def __reduce__(self):
        return pathlib.PosixPath, ("/training/dataset",)


class SavedWindowsPath:
    def __reduce__(self):
        return pathlib.WindowsPath, ("C:/training/dataset",)


@pytest.mark.parametrize("metadata_path", [SavedPosixPath(), SavedWindowsPath()])
def test_loads_foreign_paths_without_global_pathlib_changes(tmp_path, metadata_path):
    from piper_train.checkpoint_io import load_checkpoint

    original_posix = pathlib.PosixPath
    original_windows = pathlib.WindowsPath
    checkpoint = tmp_path / "model.ckpt"
    torch.save(
        {
            "hyper_parameters": {"dataset": metadata_path},
            "state_dict": {"x": torch.ones(2)},
        },
        checkpoint,
    )
    loaded = load_checkpoint(checkpoint)
    assert isinstance(loaded["hyper_parameters"]["dataset"], pathlib.Path)
    assert torch.equal(loaded["state_dict"]["x"], torch.ones(2))
    assert pathlib.PosixPath is original_posix
    assert pathlib.WindowsPath is original_windows


# ---------------------------------------------------------------------------
# load_state_with_allowed_missing (reference-fusion plan §8 Task 6R)
#
# 旧 ("none") checkpoint を参照条件付きモデルへ weights-only で読む移行。
# 許可 prefix 配下の新設モジュールだけが欠落してよく、それ以外の欠落・
# checkpoint 側の余剰 key・shape 差はすべて明示エラーにする。
# ---------------------------------------------------------------------------

REFERENCE_PREFIXES = ("reference_encoder.", "capacity_control.")


def _legacy_generator():
    """参照モジュールを持たない生成器の stand-in (実 nn.Module)。"""
    torch.manual_seed(0)
    model = torch.nn.Module()
    model.spk_proj = torch.nn.Linear(3, 4)
    model.dec = torch.nn.Linear(4, 2)
    model.dec.register_buffer("marker", torch.arange(3.0))
    return model


def _reference_generator(name="reference_encoder"):
    """legacy と同じ既存モジュール + zero-init の新設モジュール。"""
    model = _legacy_generator()
    head = torch.nn.Linear(4, 4)
    torch.nn.init.zeros_(head.weight)
    torch.nn.init.zeros_(head.bias)
    setattr(model, name, head)
    return model


def _wrapped(inner):
    """VitsModel と同じ ``model_g.`` 入れ子 (key は ``model_g.<...>``)。"""
    outer = torch.nn.Module()
    outer.model_g = inner
    return outer


def _snapshot(model):
    return {k: v.detach().clone() for k, v in model.state_dict().items()}


def _assert_unchanged(model, before):
    after = model.state_dict()
    assert list(after) == list(before)
    for key, value in before.items():
        assert torch.equal(after[key], value), key


def _source_state(model, seed=7):
    """target と区別できる値の state_dict (読み込まれたことを値で確かめる)。"""
    gen = torch.Generator().manual_seed(seed)
    return {
        k: torch.randn(v.shape, generator=gen) for k, v in model.state_dict().items()
    }


@pytest.mark.parametrize("name", ["reference_encoder", "capacity_control"])
def test_allowed_missing_accepts_only_reference_keys(name):
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    legacy_state = _source_state(_legacy_generator())
    target = _reference_generator(name)
    result = load_state_with_allowed_missing(target, legacy_state, REFERENCE_PREFIXES)

    assert result == {
        "missing": [f"{name}.weight", f"{name}.bias"],
        "unexpected": [],
    }
    for key, value in legacy_state.items():
        assert torch.equal(target.state_dict()[key], value), key
    # 欠落した新設モジュールは zero-init のまま (旧モデルと出力 bit 一致の前提)
    head = getattr(target, name)
    assert torch.count_nonzero(head.weight) == 0
    assert torch.count_nonzero(head.bias) == 0


def test_allowed_missing_with_no_missing_keys_loads_everything():
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    source = _source_state(_reference_generator())
    target = _reference_generator()
    result = load_state_with_allowed_missing(target, source, REFERENCE_PREFIXES)
    assert result == {"missing": [], "unexpected": []}
    for key, value in source.items():
        assert torch.equal(target.state_dict()[key], value), key


def test_allowed_missing_matches_prefix_below_wrapper_module():
    """VitsModel の key は ``model_g.reference_encoder.*`` になる。"""
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    legacy_state = _source_state(_wrapped(_legacy_generator()))
    target = _wrapped(_reference_generator())
    result = load_state_with_allowed_missing(target, legacy_state, REFERENCE_PREFIXES)
    assert result["missing"] == [
        "model_g.reference_encoder.weight",
        "model_g.reference_encoder.bias",
    ]


def test_allowed_missing_matches_prefix_below_torch_compile_wrapper():
    """``torch.compile`` 後の ``model_g._orig_mod.reference_encoder.*`` も許可。"""
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    inner = torch.nn.Module()
    inner._orig_mod = _reference_generator()
    target = _wrapped(inner)
    legacy_inner = torch.nn.Module()
    legacy_inner._orig_mod = _legacy_generator()
    legacy_state = _source_state(_wrapped(legacy_inner))
    result = load_state_with_allowed_missing(target, legacy_state, REFERENCE_PREFIXES)
    assert result["missing"] == [
        "model_g._orig_mod.reference_encoder.weight",
        "model_g._orig_mod.reference_encoder.bias",
    ]


def test_allowed_missing_prefix_matches_only_at_module_boundary():
    """``my_reference_encoder.*`` は ``reference_encoder.`` の許可に入らない。"""
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    legacy_state = _source_state(_legacy_generator())
    target = _reference_generator("my_reference_encoder")
    before = _snapshot(target)
    with pytest.raises(ValueError, match=r"my_reference_encoder\.weight"):
        load_state_with_allowed_missing(target, legacy_state, REFERENCE_PREFIXES)
    _assert_unchanged(target, before)


def test_allowed_missing_rejects_other_missing_key():
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    legacy_state = _source_state(_legacy_generator())
    del legacy_state["dec.weight"]
    target = _reference_generator()
    before = _snapshot(target)
    with pytest.raises(ValueError, match=r"missing.*dec\.weight"):
        load_state_with_allowed_missing(target, legacy_state, REFERENCE_PREFIXES)
    _assert_unchanged(target, before)


def test_allowed_missing_rejects_missing_buffer():
    """persistent buffer の欠落も重みの欠落と同じく拒否する。"""
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    legacy_state = _source_state(_legacy_generator())
    del legacy_state["dec.marker"]
    with pytest.raises(ValueError, match=r"dec\.marker"):
        load_state_with_allowed_missing(
            _reference_generator(), legacy_state, REFERENCE_PREFIXES
        )


def test_allowed_missing_rejects_unexpected_key():
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    legacy_state = _source_state(_legacy_generator())
    legacy_state["emb_g.weight"] = torch.zeros(2, 4)
    target = _reference_generator()
    before = _snapshot(target)
    with pytest.raises(ValueError, match=r"unexpected.*emb_g\.weight"):
        load_state_with_allowed_missing(target, legacy_state, REFERENCE_PREFIXES)
    _assert_unchanged(target, before)


def test_reference_checkpoint_into_legacy_model_raises():
    """参照付き checkpoint を none モデルへ読むと捨てずにエラー (unexpected)。

    許可 prefix は「欠落してよい」だけで、余剰の参照重みを捨てる許可ではない。
    """
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    reference_state = _source_state(_reference_generator())
    target = _legacy_generator()
    before = _snapshot(target)
    with pytest.raises(ValueError, match=r"unexpected.*reference_encoder\.weight"):
        load_state_with_allowed_missing(target, reference_state, REFERENCE_PREFIXES)
    _assert_unchanged(target, before)


def test_allowed_missing_rejects_shape_mismatch():
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    legacy_state = _source_state(_legacy_generator())
    legacy_state["dec.weight"] = torch.zeros(3, 4)  # model は [2, 4]
    target = _reference_generator()
    before = _snapshot(target)
    with pytest.raises(ValueError, match=r"shape.*dec\.weight.*\(3, 4\).*\(2, 4\)"):
        load_state_with_allowed_missing(target, legacy_state, REFERENCE_PREFIXES)
    _assert_unchanged(target, before)


def test_allowed_missing_rejects_shape_mismatch_inside_allowed_prefix():
    """許可 prefix は欠落だけを許す。存在する参照重みの shape 差は拒否。"""
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    source = _source_state(_reference_generator())
    source["reference_encoder.weight"] = torch.zeros(4, 5)
    with pytest.raises(ValueError, match=r"reference_encoder\.weight"):
        load_state_with_allowed_missing(
            _reference_generator(), source, REFERENCE_PREFIXES
        )


@pytest.mark.parametrize("dtype", [torch.float16, torch.bfloat16, torch.float64])
def test_allowed_missing_rejects_dtype_mismatch(dtype):
    """``load_state_dict`` は dtype 差を黙って cast するので先に拒否する。"""
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    legacy_state = _source_state(_legacy_generator())
    legacy_state["dec.weight"] = legacy_state["dec.weight"].to(dtype)
    target = _reference_generator()
    before = _snapshot(target)
    with pytest.raises(ValueError, match=r"dtype.*dec\.weight"):
        load_state_with_allowed_missing(target, legacy_state, REFERENCE_PREFIXES)
    _assert_unchanged(target, before)


def test_allowed_missing_rejects_non_tensor_value():
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    legacy_state = _source_state(_legacy_generator())
    legacy_state["dec.weight"] = [[0.0] * 4] * 2
    with pytest.raises(ValueError, match=r"dec\.weight"):
        load_state_with_allowed_missing(
            _reference_generator(), legacy_state, REFERENCE_PREFIXES
        )


def test_allowed_missing_reports_every_problem_at_once():
    """欠落・余剰・shape 差を 1 回のエラーにまとめる (修正の往復を減らす)。"""
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    legacy_state = _source_state(_legacy_generator())
    del legacy_state["spk_proj.bias"]
    legacy_state["extra.weight"] = torch.zeros(1)
    legacy_state["dec.weight"] = torch.zeros(3, 4)
    with pytest.raises(ValueError) as excinfo:
        load_state_with_allowed_missing(
            _reference_generator(), legacy_state, REFERENCE_PREFIXES
        )
    message = str(excinfo.value)
    for key in ("spk_proj.bias", "extra.weight", "dec.weight"):
        assert key in message


def test_empty_allowed_prefixes_is_strict():
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    legacy_state = _source_state(_legacy_generator())
    with pytest.raises(ValueError, match=r"reference_encoder\.weight"):
        load_state_with_allowed_missing(_reference_generator(), legacy_state, ())


@pytest.mark.parametrize(
    "prefixes",
    [
        "reference_encoder.",  # tuple ではなく文字列 (1 文字ずつの prefix になる)
        ("reference_encoder",),  # module 境界の "." がない
        ("",),  # 全 key を許可してしまう
        (None,),
    ],
)
def test_allowed_prefixes_must_be_dotted_module_prefixes(prefixes):
    from piper_train.checkpoint_io import load_state_with_allowed_missing

    with pytest.raises((TypeError, ValueError), match="allowed_prefixes"):
        load_state_with_allowed_missing(
            _reference_generator(), _source_state(_legacy_generator()), prefixes
        )
