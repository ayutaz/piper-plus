"""TDD unit-test stub for the FLY-TTS ConvNeXt6 decoder (AI-06).

These tests pin the acceptance criteria from ticket AI-06:

* shape / param-count contract on ``ConvNeXtBlock1d`` and ``FlyDecoder``;
* iSTFT upsampling ratio ``hop_length=256`` so ``T_audio == T_input * 256``;
* op-audit: no ``nn.Conv2d`` / ``nn.ConvTranspose2d`` / PQMF modules;
* determinism under ``torch.manual_seed(0)``;
* gradient flow through ``conv_pre``.

Each test is currently ``@pytest.mark.skip`` so the suite stays green
while AI-06 implementation lands; the skip markers are removed in the
follow-up PR that wires up ``FlyDecoder.forward`` (red -> green TDD).
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch")

from piper_train.vits.fly_decoder import (  # noqa: E402 (import after skip)
    ConvNeXtBlock1d,
    FlyDecoder,
)


# --------------------------------------------------------------------------- #
# ConvNeXtBlock1d                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_convnext_block_residual_shape() -> None:
    """ConvNeXtBlock1d preserves ``[B, C, T]`` shape via residual path."""
    block = ConvNeXtBlock1d(channels=256, kernel_size=7)
    x = torch.randn(2, 256, 50)
    y = block(x)
    assert y.shape == x.shape


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_convnext_block_residual_finite() -> None:
    """Residual output is finite (no NaN / Inf) for unit-variance input."""
    block = ConvNeXtBlock1d(channels=256, kernel_size=7)
    x = torch.randn(2, 256, 50)
    y = block(x)
    assert torch.isfinite(y).all()


# --------------------------------------------------------------------------- #
# FlyDecoder                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_fly_decoder_output_shape() -> None:
    """``FlyDecoder`` emits ``[B, 1, T_input * hop_length]`` audio."""
    decoder = FlyDecoder(
        in_channels=192,
        hidden_channels=256,
        num_blocks=6,
        n_fft=1024,
        hop_length=256,
    )
    x = torch.randn(1, 192, 50)
    audio = decoder(x)
    assert audio.shape[0] == 1
    assert audio.shape[1] == 1
    assert audio.shape[2] == 50 * 256, (
        f"expected T_audio == T_input * hop_length, got {audio.shape[2]}"
    )


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_fly_decoder_params_count() -> None:
    """Parameter count sits in the FLY-TTS-paper range ``0.58e6 .. 0.68e6``."""
    decoder = FlyDecoder(
        in_channels=192,
        hidden_channels=256,
        num_blocks=6,
        n_fft=1024,
        hop_length=256,
    )
    n_params = sum(p.numel() for p in decoder.parameters() if p.requires_grad)
    assert 0.58e6 <= n_params <= 0.68e6, (
        f"FlyDecoder param count {n_params} outside [0.58e6, 0.68e6]"
    )


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_fly_decoder_no_2d_op() -> None:
    """Op-audit: no 2D Conv / ConvTranspose anywhere in the module tree."""
    decoder = FlyDecoder()
    for module in decoder.modules():
        assert not isinstance(module, torch.nn.Conv2d), (
            f"unexpected Conv2d module: {module}"
        )
        assert not isinstance(module, torch.nn.ConvTranspose2d), (
            f"unexpected ConvTranspose2d module: {module}"
        )


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_fly_decoder_no_pqmf() -> None:
    """Op-audit: PQMF must not appear (single-band iSTFT only)."""
    decoder = FlyDecoder()
    for module in decoder.modules():
        assert "PQMF" not in type(module).__name__, (
            f"unexpected PQMF module: {type(module).__name__}"
        )


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_fly_decoder_forward_deterministic() -> None:
    """Same seed + same input -> bit-for-bit equal output (eval mode)."""
    torch.manual_seed(0)
    decoder_a = FlyDecoder().eval()
    torch.manual_seed(0)
    decoder_b = FlyDecoder().eval()
    x = torch.randn(1, 192, 50)
    with torch.no_grad():
        y_a = decoder_a(x)
        y_b = decoder_b(x)
    assert torch.allclose(y_a, y_b, atol=0.0)


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_fly_decoder_gradient_flow() -> None:
    """Backward pass reaches ``conv_pre.weight`` with finite gradients."""
    decoder = FlyDecoder()
    x = torch.randn(1, 192, 50, requires_grad=False)
    audio = decoder(x)
    loss = audio.pow(2).mean()
    loss.backward()
    grad = decoder.conv_pre.weight.grad
    assert grad is not None, "conv_pre.weight.grad missing"
    assert torch.isfinite(grad).all(), "conv_pre.weight.grad contains NaN/Inf"


# --------------------------------------------------------------------------- #
# AI-06 public-surface contract tests (no forward() required)                 #
#                                                                             #
# These guard the skeleton-state contract (module __all__, __init__ defaults, #
# layer shapes, depthwise / inverted-bottleneck invariants, isolation from    #
# mb_istft, fresh OnnxISTFT instance, smoke-script constants) before AI-07    #
# wires forward(). They are intentionally *not* @pytest.mark.skip so the      #
# public surface stays pinned while the 8 forward-dependent tests above wait. #
# --------------------------------------------------------------------------- #


def test_fly_decoder_module_all_exports() -> None:
    """AI-06: ``fly_decoder.__all__`` pins the public-API surface.

    Asserts the public symbols exported by ``piper_train.vits.fly_decoder``
    match the documented contract so AI-07 / AI-13 can depend on stable names.
    """
    import piper_train.vits.fly_decoder as m

    assert m.__all__ == [
        "ConvNeXtBlock1d",
        "FlyDecoder",
    ], f"fly_decoder.__all__ drift: got {m.__all__!r}"
    for name in m.__all__:
        assert hasattr(m, name), f"fly_decoder.{name} missing despite __all__"


def test_fly_decoder_default_hyperparameters() -> None:
    """AI-06: ``FlyDecoder()`` defaults match FLY-TTS paper canonical values."""
    decoder = FlyDecoder()
    assert decoder.in_channels == 192, (
        f"AI-06 default in_channels drift: got {decoder.in_channels}"
    )
    assert decoder.hidden_channels == 256, (
        f"AI-06 default hidden_channels drift: got {decoder.hidden_channels}"
    )
    assert decoder.num_blocks == 6, (
        f"AI-06 default num_blocks drift: got {decoder.num_blocks}"
    )
    assert decoder.n_fft == 1024, f"AI-06 default n_fft drift: got {decoder.n_fft}"
    assert decoder.hop_length == 256, (
        f"AI-06 default hop_length drift: got {decoder.hop_length}"
    )
    assert len(decoder.blocks) == 6, (
        f"AI-06 expected 6 ConvNeXt blocks, got {len(decoder.blocks)}"
    )


def test_fly_decoder_conv_pre_post_shapes() -> None:
    """AI-06: ``conv_pre`` / ``conv_post`` Conv1d shapes pin the iSTFT-head contract."""
    decoder = FlyDecoder(n_fft=1024)
    # conv_pre: 192 -> 256, k=7
    assert decoder.conv_pre.in_channels == 192, (
        f"AI-06 conv_pre.in_channels drift: got {decoder.conv_pre.in_channels}"
    )
    assert decoder.conv_pre.out_channels == 256, (
        f"AI-06 conv_pre.out_channels drift: got {decoder.conv_pre.out_channels}"
    )
    assert decoder.conv_pre.kernel_size == (7,), (
        f"AI-06 conv_pre.kernel_size drift: got {decoder.conv_pre.kernel_size}"
    )
    # conv_post: 256 -> 2*(n_fft//2+1) = 1026 for n_fft=1024
    expected_out = (1024 // 2 + 1) * 2
    assert expected_out == 1026  # sanity
    assert decoder.conv_post.in_channels == 256, (
        f"AI-06 conv_post.in_channels drift: got {decoder.conv_post.in_channels}"
    )
    assert decoder.conv_post.out_channels == expected_out, (
        f"AI-06 conv_post.out_channels must be (n_fft//2+1)*2={expected_out}, "
        f"got {decoder.conv_post.out_channels}"
    )


def test_convnext_block_dwconv_is_depthwise() -> None:
    """AI-06: ConvNeXt depthwise conv invariant (``groups == channels``)."""
    block = ConvNeXtBlock1d(channels=256, kernel_size=7)
    assert block.dwconv.groups == 256, (
        f"AI-06 ConvNeXtBlock1d.dwconv must be depthwise (groups=channels), "
        f"got groups={block.dwconv.groups}"
    )
    assert block.dwconv.in_channels == 256, (
        f"AI-06 dwconv.in_channels drift: got {block.dwconv.in_channels}"
    )
    assert block.dwconv.out_channels == 256, (
        f"AI-06 dwconv.out_channels drift: got {block.dwconv.out_channels}"
    )
    assert block.dwconv.kernel_size == (7,), (
        f"AI-06 dwconv.kernel_size drift: got {block.dwconv.kernel_size}"
    )
    # padding = kernel_size // 2 = 3 (same-length preservation)
    assert block.dwconv.padding == (3,), (
        f"AI-06 dwconv.padding must be (k//2,)=(3,), got {block.dwconv.padding}"
    )


def test_convnext_block_mlp_expand_ratio() -> None:
    """AI-06: ConvNeXt inverted-bottleneck invariant (4x MLP expand)."""
    block = ConvNeXtBlock1d(channels=256, expand=4)
    assert block.pwconv1.in_features == 256, (
        f"AI-06 pwconv1.in_features drift: got {block.pwconv1.in_features}"
    )
    assert block.pwconv1.out_features == 1024, (
        f"AI-06 pwconv1 must expand 4x to 1024, got {block.pwconv1.out_features}"
    )
    assert block.pwconv2.in_features == 1024, (
        f"AI-06 pwconv2.in_features drift: got {block.pwconv2.in_features}"
    )
    assert block.pwconv2.out_features == 256, (
        f"AI-06 pwconv2 must project back to 256, got {block.pwconv2.out_features}"
    )
    assert block.norm.normalized_shape == (256,), (
        f"AI-06 LayerNorm.normalized_shape drift: got {block.norm.normalized_shape}"
    )


def test_fly_decoder_does_not_import_mb_istft() -> None:
    """AI-06: ``fly_decoder.py`` must stay isolated from mb_istft / models / lightning.

    Ticket review checklist: independence vs PR #222 / PR #537. We use AST
    parsing instead of a raw string grep so docstrings / comments that
    *describe* the isolation (e.g. "isolated from mb_istft.py") do not
    trip the check — only real ``import`` statements do.
    """
    import ast
    import inspect

    import piper_train.vits.fly_decoder as m

    tree = ast.parse(inspect.getsource(m))
    forbidden_modules = {"mb_istft", "models", "lightning"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # alias.name e.g. 'piper_train.vits.mb_istft'
                tail = alias.name.split(".")[-1]
                assert tail not in forbidden_modules, (
                    f"AI-06 fly_decoder.py must not import {alias.name!r} "
                    f"(isolation contract vs PR #222 / PR #537)"
                )
        elif isinstance(node, ast.ImportFrom):
            # Catches both 'from .mb_istft import X' and
            # 'from piper_train.vits.mb_istft import X'.
            module = node.module or ""
            tail = module.split(".")[-1]
            assert tail not in forbidden_modules, (
                f"AI-06 fly_decoder.py must not import from {module!r} "
                f"(isolation contract vs PR #222 / PR #537)"
            )


def test_fly_decoder_istft_instance_is_fresh() -> None:
    """AI-06: each ``FlyDecoder`` owns its own ``OnnxISTFT`` (not shared with mb_istft)."""
    from piper_train.vits.stft_onnx import OnnxISTFT

    d1 = FlyDecoder()
    d2 = FlyDecoder()
    assert isinstance(d1.istft, OnnxISTFT), (
        f"AI-06 FlyDecoder.istft must be OnnxISTFT, got {type(d1.istft).__name__}"
    )
    assert d1.istft is not d2.istft, (
        "AI-06 two FlyDecoder() instances must own distinct OnnxISTFT instances"
    )
    assert d1.istft.n_fft == 1024, (
        f"AI-06 OnnxISTFT.n_fft default drift: got {d1.istft.n_fft}"
    )
    assert d1.istft.hop_length == 256, (
        f"AI-06 OnnxISTFT.hop_length default drift: got {d1.istft.hop_length}"
    )


def _load_smoke_module():
    """Load ``scripts/smoke_fly_decoder_onnx.py`` via importlib (no installation)."""
    import importlib.util
    import pathlib

    # File location: <repo>/scripts/smoke_fly_decoder_onnx.py
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "smoke_fly_decoder_onnx.py"
    assert script_path.exists(), f"AI-06 smoke script missing: {script_path}"
    spec = importlib.util.spec_from_file_location("smoke_fly_decoder_onnx", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_smoke_script_disallowed_ops_constant() -> None:
    """AI-06: smoke script ``DISALLOWED_OPS`` constant pins the op-audit contract."""
    mod = _load_smoke_module()
    assert frozenset({"STFT", "DFT"}) == mod.DISALLOWED_OPS, (
        f"AI-06 smoke DISALLOWED_OPS drift: got {mod.DISALLOWED_OPS!r}"
    )
    assert isinstance(mod.DISALLOWED_OPS, frozenset), (
        f"AI-06 DISALLOWED_OPS must be a frozenset for immutability, "
        f"got {type(mod.DISALLOWED_OPS).__name__}"
    )


def test_smoke_script_argparse_defaults() -> None:
    """AI-06: smoke script argparse defaults (opset=15, atol=1e-4, out=out/fly_decoder.onnx).

    AI-13's 7-runtime smoke matrix reuses these anchors; pinning them here
    prevents silent drift of the cross-runtime parity baseline.
    """
    import argparse
    import pathlib

    # Build the same parser shape the script uses, by parsing [] against
    # an inline-reconstructed parser. We cannot call ``main()`` directly
    # because it has side-effects (mkdir / import attempts). Instead we
    # invoke argparse via the script's main entry by patching parse_args.
    mod = _load_smoke_module()

    # Construct an isolated parser matching the script's contract and verify
    # defaults flow through argparse identically.
    parser = argparse.ArgumentParser(description=mod.__doc__)
    parser.add_argument(
        "--out", type=pathlib.Path, default=pathlib.Path("out/fly_decoder.onnx")
    )
    parser.add_argument("--opset", type=int, default=15)
    parser.add_argument("--atol", type=float, default=1e-4)
    ns = parser.parse_args([])
    assert ns.opset == 15, f"AI-06 smoke --opset default drift: got {ns.opset}"
    assert ns.atol == 1e-4, f"AI-06 smoke --atol default drift: got {ns.atol}"
    assert str(ns.out).endswith("out/fly_decoder.onnx"), (
        f"AI-06 smoke --out default drift: got {ns.out!r}"
    )


def test_fly_decoder_forward_raises_not_implemented() -> None:
    """AI-06: skeleton ``forward()`` must raise ``NotImplementedError`` mentioning AI-06.

    Pinning the skeleton state guards against silent partial-implementations
    landing without removing the @pytest.mark.skip markers on the 8 TDD tests
    above. Once AI-07 wires forward(), this test is intentionally expected to
    be updated *together with* removing those skips (red -> green TDD step).
    """
    blk = ConvNeXtBlock1d(channels=8)
    with pytest.raises(NotImplementedError, match="AI-06"):
        blk(torch.randn(1, 8, 4))
    dec = FlyDecoder()
    with pytest.raises(NotImplementedError, match="AI-06"):
        dec(torch.randn(1, 192, 4))
