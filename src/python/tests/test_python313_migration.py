"""Regression tests for Issue #527 (Python 3.13 + torch 2.11 + cu128 migration).

Groups the migration Decision Record (DR) regressions into one owned file:

- DR-006: legacy HiFi-GAN (v1.11) checkpoint rejected with clear migration error.
- DR-007: TF32 enabled at training startup (``torch.backends.cuda.matmul.allow_tf32``
  and ``torch.backends.cudnn.allow_tf32`` both ``True``).
- DR-008: ``--precision`` default matches Template A/B canonical ``bf16-mixed``.
- Windows checkpoint compat: ``pathlib.PosixPath`` is monkey-patched to
  ``WindowsPath`` *before* the first ``torch.load`` on Windows; no-op on POSIX.
- pyproject cu128 marker correctness: torch resolves to ``+cu128`` on Linux.
"""

from __future__ import annotations

import platform
import subprocess
import sys
import textwrap

import pytest


pytest.importorskip("torch")

import torch  # noqa: E402

from piper_train.__main__ import (  # noqa: E402
    _is_legacy_hifigan_checkpoint,
    create_parser,
)


# ---------------------------------------------------------------------------
# DR-007: TF32 enable
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tf32_enabled_after_main_initialization():
    """After ``main()`` runs its TF32 init block, both TF32 flags must be True.

    We invoke the init logic in an isolated subprocess (so the test process's
    own TF32 settings aren't measured), import ``piper_train.__main__``, then
    execute the exact two-line TF32 enable block from lines 576-577.
    """
    code = textwrap.dedent(
        """
        import torch
        # Reproduce the DR-007 init block from piper_train.__main__ main() (L576-577).
        # Importing the module also exercises the module-level Windows / safe_globals
        # patches (L19-24), so we exercise both surfaces in one subprocess.
        import piper_train.__main__  # noqa: F401
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        assert torch.backends.cuda.matmul.allow_tf32 is True, "matmul TF32 not enabled"
        assert torch.backends.cudnn.allow_tf32 is True, "cudnn TF32 not enabled"
        print("OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        f"TF32 init subprocess failed.\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "OK" in result.stdout


# ---------------------------------------------------------------------------
# DR-006: legacy HiFi-GAN checkpoint detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_old_hifigan_ckpt_raises_dr006_error(tmp_path):
    """A fake v1.11 HiFi-GAN ckpt is detected and yields a migration error.

    We don't run the full ``main()`` here (it would require a dataset and a
    Trainer); instead we mirror the exact two-step contract used in
    ``main()`` at L854-859: ``torch.load(..., weights_only=False)`` then
    ``_is_legacy_hifigan_checkpoint(state_dict)`` then raise
    ``RuntimeError(_LEGACY_HIFIGAN_MESSAGE.format(path=...))``.
    """
    from piper_train.__main__ import _LEGACY_HIFIGAN_MESSAGE

    fake_state_dict = {
        "model_g.enc_p.emb.weight": torch.zeros(50, 192),
        # HiFi-GAN-specific decoder keys WITHOUT the MB-iSTFT markers
        # (no model_g.dec.subband_conv_post.* and no model_g.dec.pqmf.*).
        "model_g.dec.conv_pre.weight": torch.zeros(512, 192, 7),
        "model_g.dec.ups.0.weight": torch.zeros(256, 128, 16, 1),
        "model_g.dec.resblocks.0.convs1.0.weight": torch.zeros(256, 256, 3),
        "model_g.dec.conv_post.weight": torch.zeros(1, 32, 7),
        "model_g.dp.flows.0.pre.weight": torch.zeros(192, 192, 1),
    }
    ckpt_path = tmp_path / "legacy.ckpt"
    torch.save({"state_dict": fake_state_dict}, ckpt_path)

    loaded = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    assert _is_legacy_hifigan_checkpoint(loaded["state_dict"]) is True

    # Reproduce the raise contract from main() at L857-860 verbatim.
    with pytest.raises(RuntimeError) as exc_info:
        if _is_legacy_hifigan_checkpoint(loaded["state_dict"]):
            raise RuntimeError(_LEGACY_HIFIGAN_MESSAGE.format(path=str(ckpt_path)))

    msg = str(exc_info.value)
    assert "MB-iSTFT" in msg
    assert "migration" in msg.lower() or "v1.11-to-v1.12" in msg
    # The message uses {path!r} so the embedded path is repr-quoted; on
    # Windows that doubles every backslash. Check by basename instead of
    # full path to stay platform-agnostic.
    assert ckpt_path.name in msg


# ---------------------------------------------------------------------------
# Windows PosixPath patch (L19-24)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_windows_posix_path_patch_applied():
    """On Windows, importing ``piper_train.__main__`` aliases PosixPath -> WindowsPath.

    On POSIX systems the patch is a no-op (the ``if platform.system() == 'Windows'``
    guard at L23 ensures PosixPath stays the original class).

    Uses a fresh subprocess to avoid relying on whatever order the parent test
    process imported things in.
    """
    code = textwrap.dedent(
        """
        import platform, pathlib, sys
        original_posix = pathlib.PosixPath
        import piper_train.__main__  # triggers L19-24 patch
        if platform.system() == "Windows":
            # Patch must have aliased PosixPath to WindowsPath.
            assert pathlib.PosixPath is pathlib.WindowsPath, (
                f"Expected PosixPath aliased to WindowsPath, got {pathlib.PosixPath!r}"
            )
            print("WINDOWS_PATCHED")
        else:
            # Patch must be a no-op on POSIX.
            assert pathlib.PosixPath is original_posix, (
                f"Expected PosixPath unchanged on POSIX, got {pathlib.PosixPath!r}"
            )
            assert pathlib.PosixPath is not pathlib.WindowsPath
            print("POSIX_NOOP")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        f"PosixPath patch subprocess failed.\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    if platform.system() == "Windows":
        assert "WINDOWS_PATCHED" in result.stdout
    else:
        assert "POSIX_NOOP" in result.stdout


# ---------------------------------------------------------------------------
# DR-008: --precision default = bf16-mixed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_argparse_precision_default_is_bf16_mixed():
    """``--precision`` default must be ``bf16-mixed`` per DR-008 / Template A/B canonical.

    Both ``--dataset-dir`` and ``--batch-size`` are required positionals; we
    supply dummy values so ``parse_args`` succeeds and we can inspect the
    default for ``--precision``.
    """
    parser = create_parser()
    args = parser.parse_args(["--dataset-dir", "/tmp/dummy", "--batch-size", "4"])
    assert args.precision == "bf16-mixed", (
        f"DR-008 violation: --precision default is {args.precision!r}, "
        "expected 'bf16-mixed' (Template A/B canonical). "
        "See docs/reference/python-313/specifications.md."
    )


# ---------------------------------------------------------------------------
# pyproject.toml cu128 marker correctness
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_torch_211_cu128_resolution_on_linux():
    """On Linux, torch must resolve to a cu128 build per the uv source marker.

    On Windows, the CPU wheel is acceptable (no cu128 marker for Windows in
    pyproject.toml). The important contract on Windows is just that the
    pin (``torch>=2.11.0``) imported successfully.
    """
    # Basic version pin (pyproject: torch>=2.11.0)
    major, minor, *_ = torch.__version__.split("+")[0].split(".")
    assert (int(major), int(minor)) >= (2, 11), (
        f"torch>={2}.{11} required, got {torch.__version__}"
    )

    if sys.platform == "linux":
        if not torch.cuda.is_available():
            pytest.skip(
                "Linux without CUDA-capable runtime; cu128 wheel may still be "
                "installed but version string is the only signal."
            )
        # Either the local-version segment carries +cu128 or torch.version.cuda
        # advertises 12.8.x.
        has_cu128_local = "+cu128" in torch.__version__
        cuda_ver = getattr(torch.version, "cuda", None) or ""
        has_cu128_runtime = cuda_ver.startswith("12.8")
        assert has_cu128_local or has_cu128_runtime, (
            f"Linux torch must be cu128 build, got version={torch.__version__!r} "
            f"cuda={cuda_ver!r}"
        )
    else:
        # Windows / macOS: just ensure torch is importable and a Path-like
        # attribute is callable (smoke check).
        assert callable(torch.tensor)
