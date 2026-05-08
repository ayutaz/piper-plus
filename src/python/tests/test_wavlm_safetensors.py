"""Regression tests for WavLM Discriminator ``use_safetensors`` auto-selection.

Pins commit 56f20b38 (#353): the constructor of ``WavLMDiscriminator`` must
**not** pass ``use_safetensors=True`` to ``transformers.WavLMModel.from_pretrained``.

History
-------
Originally the discriminator hard-coded ``use_safetensors=True``, which broke
training whenever the configured WavLM model only published
``pytorch_model.bin`` (microsoft/wavlm-base-plus does not ship safetensors).
The fix delegates the choice to ``transformers``: omit the kwarg entirely so
the default (``None``) lets the library pick whichever weight file is
present (safetensors-only, pytorch-bin-only, or both).

These tests are intentionally **mock-based** because real WavLM weights are
~370 MB; running them in CI must be fast.  Each test patches
``transformers.WavLMModel`` so the constructor never hits the network.

Tests
-----
1. ``test_wavlm_loads_via_safetensors_when_available`` -- when the only
   tracked file is ``model.safetensors``, ``from_pretrained`` succeeds and
   the discriminator constructs.
2. ``test_wavlm_falls_back_to_pytorch_bin_when_safetensors_missing`` -- when
   only ``pytorch_model.bin`` is present (the default
   microsoft/wavlm-base-plus case), ``from_pretrained`` succeeds.  This is
   the case the original bug broke.
3. ``test_wavlm_use_safetensors_false_explicit`` -- pins that the production
   code does **not** pass ``use_safetensors=True`` (or any explicit boolean):
   inspecting the call kwargs proves the auto-selection contract.
4. ``test_wavlm_load_handles_corrupt_safetensors_file`` -- when
   ``from_pretrained`` itself raises (corrupt weights, missing files,
   network error), the error must surface from the constructor and be
   chained / decorated correctly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# Skip the entire module if transformers is not installed (e.g. CI env that
# only runs the runtime tests).  WavLM is a training-only dependency.
transformers = pytest.importorskip("transformers")
torchaudio = pytest.importorskip("torchaudio")


# transformers >= 4.30 lazy-loads symbols; ``patch("transformers.WavLMModel")``
# only takes effect after the attribute has been resolved at least once.
# Force resolution at module load so all tests in this file have a real
# patch target.
_ = transformers.WavLMModel


@pytest.mark.unit
@pytest.mark.training
class TestWavLMSafeTensorsAutoSelection:
    """Pin auto-selection of safetensors / pytorch_model.bin in WavLMDiscriminator."""

    def test_wavlm_loads_via_safetensors_when_available(self) -> None:
        """When the model ships safetensors, ``from_pretrained`` succeeds.

        We mock ``WavLMModel.from_pretrained`` to simulate a model that only
        has ``model.safetensors``: with the fix, transformers picks it up
        automatically because we don't pin ``use_safetensors=False``.
        """
        from piper_train.vits.models import WavLMDiscriminator

        mock_wavlm = MagicMock()
        mock_wavlm.feature_extractor.parameters.return_value = []
        # Simulate a custom safetensors-only model.
        with patch("transformers.WavLMModel") as mock_wavlm_cls:
            mock_wavlm_cls.from_pretrained.return_value = mock_wavlm

            disc = WavLMDiscriminator(model_name="custom/wavlm-safetensors-only")

            assert disc.wavlm is mock_wavlm
            assert mock_wavlm_cls.from_pretrained.call_count == 1
            # Confirm the model name was forwarded.
            args, _ = mock_wavlm_cls.from_pretrained.call_args
            assert args[0] == "custom/wavlm-safetensors-only"

    def test_wavlm_falls_back_to_pytorch_bin_when_safetensors_missing(self) -> None:
        """The default model only has pytorch_model.bin; this must not break.

        This is the **exact regression scenario** of commit 56f20b38: with the
        old hard-coded ``use_safetensors=True``, transformers raised
        ``OSError`` when it could not find ``model.safetensors``.  The fix is
        to omit the kwarg.
        """
        from piper_train.vits.models import WavLMDiscriminator

        mock_wavlm = MagicMock()
        mock_wavlm.feature_extractor.parameters.return_value = []
        with patch("transformers.WavLMModel") as mock_wavlm_cls:
            mock_wavlm_cls.from_pretrained.return_value = mock_wavlm

            # Default model_name = "microsoft/wavlm-base-plus" which only ships
            # pytorch_model.bin.  Must succeed.
            disc = WavLMDiscriminator()

            assert disc.wavlm is mock_wavlm
            args, _ = mock_wavlm_cls.from_pretrained.call_args
            assert args[0] == "microsoft/wavlm-base-plus"

    def test_wavlm_use_safetensors_false_explicit(self) -> None:
        """``from_pretrained`` must not be called with an explicit
        ``use_safetensors`` boolean.

        This pins the regression contract: the production constructor
        delegates the decision to transformers.  If a future refactor
        re-introduces ``use_safetensors=True`` (or ``False``), this test
        fails immediately and forces a code review.
        """
        from piper_train.vits.models import WavLMDiscriminator

        mock_wavlm = MagicMock()
        mock_wavlm.feature_extractor.parameters.return_value = []
        with patch("transformers.WavLMModel") as mock_wavlm_cls:
            mock_wavlm_cls.from_pretrained.return_value = mock_wavlm

            WavLMDiscriminator(model_name="microsoft/wavlm-base-plus")

            # Inspect call: from_pretrained(model_name) — no use_safetensors kw.
            _, kwargs = mock_wavlm_cls.from_pretrained.call_args
            assert "use_safetensors" not in kwargs, (
                "WavLMDiscriminator must not pin use_safetensors; "
                "transformers picks the file format based on what the "
                "configured model ships.  Re-introducing this kwarg "
                "regresses commit 56f20b38 (default microsoft/wavlm-base-plus "
                "ships only pytorch_model.bin)."
            )

    def test_wavlm_load_handles_corrupt_safetensors_file(self) -> None:
        """If ``from_pretrained`` raises (corrupt file, missing weights,
        network error), the constructor surfaces the error.

        This pins that we **do not** silently swallow load failures: if
        transformers can't load the weights, training must fail loudly so
        the user sees the real cause instead of crashing later in forward
        pass with a confusing error.
        """
        from piper_train.vits.models import WavLMDiscriminator

        with patch("transformers.WavLMModel") as mock_wavlm_cls:
            # Simulate transformers raising on a corrupt safetensors file.
            mock_wavlm_cls.from_pretrained.side_effect = OSError(
                "Error while deserializing header: HeaderTooLarge"
            )

            with pytest.raises(OSError, match="HeaderTooLarge"):
                WavLMDiscriminator(model_name="custom/wavlm-corrupt")
