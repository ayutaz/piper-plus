"""
Tests for PiperVoice.load() config path fallback logic and related regressions.

Verifies the three-tier resolution:
  1. {model}.onnx.json  (auto-detected)
  2. config.json         (fallback in same directory)
  3. FileNotFoundError   (neither exists)

Also covers:
  #4  PhonemeType enum completeness
  #5  language_id propagation to lid tensor
  #6  MULTILINGUAL PhonemeType tries MultilingualPhonemizer
  #26 noise_scale=0.0 not overridden by defaults
"""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# Guard: skip entire module when onnxruntime is unavailable
ort = pytest.importorskip("onnxruntime", reason="onnxruntime is required")

from piper.config import PhonemeType, PiperConfig  # noqa: E402
from piper.inference_config import InferenceConfig  # noqa: E402
from piper.voice import PiperVoice  # noqa: E402


# Absolute path to the real test model shipped with the repo
_REPO_ROOT = Path(__file__).resolve().parents[3]  # src/python_run/tests -> repo root
_TEST_MODEL = _REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx"
_TEST_CONFIG = _REPO_ROOT / "test" / "models" / "multilingual-test-medium.onnx.json"


@pytest.fixture()
def config_dict():
    """Return the reference config dict from the test model."""
    with open(_TEST_CONFIG, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------
# Helper: copy the real .onnx into tmp_path so each test is isolated
# ------------------------------------------------------------------
def _copy_model(tmp_path: Path) -> Path:
    """Copy the real ONNX model into *tmp_path* and return its path."""
    dest = tmp_path / "model.onnx"
    shutil.copy2(_TEST_MODEL, dest)
    return dest


class TestSessionOptions:
    """PiperVoice.load() が作成する SessionOptions の設定値テスト."""

    @pytest.mark.unit
    def test_session_options(self, tmp_path, config_dict):
        """load() が InferenceSession に渡す sess_options の全設定を検証."""
        model_path = _copy_model(tmp_path)
        config_path = tmp_path / "model.onnx.json"
        config_path.write_text(json.dumps(config_dict), encoding="utf-8")

        # Mock InferenceSession to capture the sess_options argument
        with patch("piper.voice.onnxruntime.InferenceSession") as mock_cls:
            mock_cls.return_value = MagicMock()
            PiperVoice.load(model_path)

            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args
            opts = call_kwargs.kwargs.get("sess_options")
            assert opts is not None, "sess_options was not passed to InferenceSession"

            assert (
                opts.graph_optimization_level
                == ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
            assert opts.execution_mode == ort.ExecutionMode.ORT_SEQUENTIAL
            assert opts.enable_cpu_mem_arena is True
            assert opts.enable_mem_pattern is True
            assert opts.enable_mem_reuse is True
            assert opts.get_session_config_entry("session.dynamic_block_base") == "4"
            assert opts.intra_op_num_threads >= 1


class TestConfigFallback:
    """PiperVoice.load() config resolution."""

    @pytest.mark.unit
    def test_onnx_json_auto_detected(self, tmp_path, config_dict):
        """{model}.onnx.json is picked up when config_path is None."""
        model_path = _copy_model(tmp_path)
        config_path = tmp_path / "model.onnx.json"
        config_path.write_text(json.dumps(config_dict), encoding="utf-8")

        voice = PiperVoice.load(model_path)

        assert voice.config.sample_rate == config_dict["audio"]["sample_rate"]
        assert len(voice.config.phoneme_id_map) > 0

    @pytest.mark.unit
    def test_config_json_fallback(self, tmp_path, config_dict):
        """config.json in the same directory is used when .onnx.json is absent."""
        model_path = _copy_model(tmp_path)
        # Do NOT create model.onnx.json; place config.json instead
        fallback_path = tmp_path / "config.json"
        fallback_path.write_text(json.dumps(config_dict), encoding="utf-8")

        voice = PiperVoice.load(model_path)

        assert voice.config.sample_rate == config_dict["audio"]["sample_rate"]
        assert len(voice.config.phoneme_id_map) > 0

    @pytest.mark.unit
    def test_no_config_raises(self, tmp_path):
        """FileNotFoundError is raised when no config file exists at all."""
        model_path = _copy_model(tmp_path)
        # No config files in tmp_path

        with pytest.raises(FileNotFoundError):
            PiperVoice.load(model_path)


# ------------------------------------------------------------------
# #4: PhonemeType enum completeness
# ------------------------------------------------------------------
class TestPhonemeTypeEnum:
    """Ensure PhonemeType covers bilingual / multilingual / openjtalk values."""

    @pytest.mark.unit
    def test_phoneme_type_bilingual_exists(self):
        """PhonemeType('bilingual') resolves correctly."""
        assert PhonemeType("bilingual") == PhonemeType.BILINGUAL

    @pytest.mark.unit
    def test_phoneme_type_multilingual_exists(self):
        """PhonemeType('multilingual') resolves correctly."""
        assert PhonemeType("multilingual") == PhonemeType.MULTILINGUAL

    @pytest.mark.unit
    def test_phoneme_type_openjtalk_exists(self):
        """PhonemeType('openjtalk') resolves correctly."""
        assert PhonemeType("openjtalk") == PhonemeType.OPENJTALK

    @pytest.mark.unit
    def test_phoneme_type_invalid_raises(self):
        """An unknown phoneme type string raises ValueError."""
        with pytest.raises(ValueError):
            PhonemeType("nonexistent_type")


# ------------------------------------------------------------------
# #5: language_id propagated to lid tensor
# ------------------------------------------------------------------
class TestLanguageIdPropagation:
    """Verify that language_id flows through to the ONNX lid input."""

    @pytest.mark.unit
    def test_language_id_propagated_to_lid(self):
        """synthesize_ids_to_raw with language_id=2 produces lid=[2]."""
        # Build a mock ONNX session whose get_inputs advertises "lid"
        mock_input_lid = MagicMock()
        mock_input_lid.name = "lid"
        mock_input_main = MagicMock()
        mock_input_main.name = "input"
        mock_input_lengths = MagicMock()
        mock_input_lengths.name = "input_lengths"
        mock_input_scales = MagicMock()
        mock_input_scales.name = "scales"

        mock_session = MagicMock()
        mock_session.get_inputs.return_value = [
            mock_input_main,
            mock_input_lengths,
            mock_input_scales,
            mock_input_lid,
        ]
        # Return a dummy audio tensor from session.run
        mock_session.run.return_value = [np.zeros((1, 1, 8000), dtype=np.float32)]

        config = PiperConfig(
            num_symbols=100,
            num_speakers=1,
            sample_rate=22050,
            length_scale=1.0,
            noise_scale=0.667,
            noise_w=0.8,
            phoneme_id_map={"^": [1], "_": [0], "$": [2]},
            phoneme_type=PhonemeType.MULTILINGUAL,
        )

        voice = PiperVoice(session=mock_session, config=config)
        voice.synthesize_ids_to_raw([1, 0, 2], language_id=2)

        # Inspect the args dict passed to session.run
        call_args = mock_session.run.call_args
        fed_args = call_args[0][1]  # positional arg 1 is the feeds dict
        assert "lid" in fed_args
        np.testing.assert_array_equal(fed_args["lid"], np.array([2], dtype=np.int64))

    @pytest.mark.unit
    def test_language_id_defaults_to_zero(self):
        """When language_id is None, lid tensor defaults to [0]."""
        mock_input_lid = MagicMock()
        mock_input_lid.name = "lid"
        mock_input_main = MagicMock()
        mock_input_main.name = "input"
        mock_input_lengths = MagicMock()
        mock_input_lengths.name = "input_lengths"
        mock_input_scales = MagicMock()
        mock_input_scales.name = "scales"

        mock_session = MagicMock()
        mock_session.get_inputs.return_value = [
            mock_input_main,
            mock_input_lengths,
            mock_input_scales,
            mock_input_lid,
        ]
        mock_session.run.return_value = [np.zeros((1, 1, 8000), dtype=np.float32)]

        config = PiperConfig(
            num_symbols=100,
            num_speakers=1,
            sample_rate=22050,
            length_scale=1.0,
            noise_scale=0.667,
            noise_w=0.8,
            phoneme_id_map={"^": [1], "_": [0], "$": [2]},
            phoneme_type=PhonemeType.MULTILINGUAL,
        )

        voice = PiperVoice(session=mock_session, config=config)
        voice.synthesize_ids_to_raw([1, 0, 2])

        fed_args = mock_session.run.call_args[0][1]
        assert "lid" in fed_args
        np.testing.assert_array_equal(fed_args["lid"], np.array([0], dtype=np.int64))


# ------------------------------------------------------------------
# #26: noise_scale=0.0 not overridden by defaults
# ------------------------------------------------------------------
class TestZeroNoiseScale:
    """Ensure explicitly-set zero values are preserved, not replaced by defaults."""

    @pytest.mark.unit
    def test_zero_noise_scale_not_overridden(self):
        """--noise-scale 0.0 must not be replaced by the default 0.667."""
        args = SimpleNamespace(
            model="dummy.onnx",
            config=None,
            speaker=0,
            noise_scale=0.0,
            length_scale=0.0,
            noise_w=0.0,
            volume=1.0,
            sentence_silence=0.0,
            output_raw=False,
            output_file=None,
            output_dir=None,
            auto_play=False,
            cuda=False,
            input_file=None,
            text=None,
        )
        cfg = InferenceConfig.from_args(args)
        assert cfg.noise_scale == 0.0, (
            f"noise_scale should be 0.0, got {cfg.noise_scale}"
        )
        assert cfg.length_scale == 0.0, (
            f"length_scale should be 0.0, got {cfg.length_scale}"
        )
        assert cfg.noise_w == 0.0, f"noise_w should be 0.0, got {cfg.noise_w}"

    @pytest.mark.unit
    def test_none_noise_scale_uses_default(self):
        """When argparse provides None (flag omitted), defaults should apply."""
        args = SimpleNamespace(
            model="dummy.onnx",
            config=None,
            speaker=0,
            noise_scale=None,
            length_scale=None,
            noise_w=None,
            volume=1.0,
            sentence_silence=0.0,
            output_raw=False,
            output_file=None,
            output_dir=None,
            auto_play=False,
            cuda=False,
            input_file=None,
            text=None,
        )
        cfg = InferenceConfig.from_args(args)
        assert cfg.noise_scale == 0.667
        assert cfg.length_scale == 1.0
        assert cfg.noise_w == 0.8


# ------------------------------------------------------------------
# #6: MULTILINGUAL PhonemeType tries MultilingualPhonemizer
# ------------------------------------------------------------------
class TestMultilingualPhonemizerImport:
    """Verify that MULTILINGUAL phoneme_type triggers MultilingualPhonemizer.

    Regression test for #6: when config.phoneme_type is MULTILINGUAL,
    PiperVoice.phonemize() must attempt to import and use
    MultilingualPhonemizer from piper_train.phonemize.multilingual
    before falling back to the JA phonemizer + eSpeak path.
    """

    @pytest.mark.unit
    def test_multilingual_phoneme_type_tries_multilingual_phonemizer(self):
        """MULTILINGUAL type attempts to import MultilingualPhonemizer."""
        from unittest.mock import patch

        config = PiperConfig(
            num_symbols=173,
            num_speakers=1,
            sample_rate=22050,
            length_scale=1.0,
            noise_scale=0.667,
            noise_w=0.8,
            phoneme_id_map={"_": [0], "^": [1], "$": [2], "a": [10]},
            phoneme_type=PhonemeType.MULTILINGUAL,
        )

        mock_session = MagicMock()
        voice = PiperVoice(session=mock_session, config=config)

        # Patch the import inside voice.phonemize() to verify it is attempted.
        # We intercept the MultilingualPhonemizer class and verify it gets
        # instantiated with the expected language list.
        mock_mp_instance = MagicMock()
        mock_mp_instance.phonemize.return_value = ["a"]
        mock_mp_class = MagicMock(return_value=mock_mp_instance)

        with patch(
            "piper.voice.MultilingualPhonemizer",
            mock_mp_class,
            create=True,
        ), patch.dict(
            "sys.modules",
            {
                "piper.phonemize.multilingual": MagicMock(
                    MultilingualPhonemizer=mock_mp_class,
                )
            },
        ):
            result = voice.phonemize("test")

        # MultilingualPhonemizer should have been constructed
        mock_mp_class.assert_called_once()
        call_kwargs = mock_mp_class.call_args
        # The languages kwarg should be the 6-language list for MULTILINGUAL
        used_languages = call_kwargs[1].get(
            "languages", call_kwargs[0][0] if call_kwargs[0] else None
        )
        assert used_languages == ["ja", "en", "zh", "es", "fr", "pt"], (
            f"Expected 6-language list for MULTILINGUAL, got {used_languages}"
        )

        # phonemize should have been called on the instance
        mock_mp_instance.phonemize.assert_called_once_with("test")

        # Result should be wrapped in a list (sentence grouping)
        assert result == [["a"]]

    @pytest.mark.unit
    def test_bilingual_phoneme_type_tries_multilingual_phonemizer_with_ja_en(self):
        """BILINGUAL type attempts MultilingualPhonemizer with ['ja', 'en']."""
        from unittest.mock import patch

        config = PiperConfig(
            num_symbols=97,
            num_speakers=1,
            sample_rate=22050,
            length_scale=1.0,
            noise_scale=0.667,
            noise_w=0.8,
            phoneme_id_map={"_": [0], "^": [1], "$": [2], "a": [10]},
            phoneme_type=PhonemeType.BILINGUAL,
        )

        mock_session = MagicMock()
        voice = PiperVoice(session=mock_session, config=config)

        mock_mp_instance = MagicMock()
        mock_mp_instance.phonemize.return_value = ["a"]
        mock_mp_class = MagicMock(return_value=mock_mp_instance)

        with patch(
            "piper.voice.MultilingualPhonemizer",
            mock_mp_class,
            create=True,
        ), patch.dict(
            "sys.modules",
            {
                "piper.phonemize.multilingual": MagicMock(
                    MultilingualPhonemizer=mock_mp_class,
                )
            },
        ):
            result = voice.phonemize("test")

        mock_mp_class.assert_called_once()
        call_kwargs = mock_mp_class.call_args
        used_languages = call_kwargs[1].get(
            "languages", call_kwargs[0][0] if call_kwargs[0] else None
        )
        assert used_languages == ["ja", "en"], (
            f"Expected ['ja', 'en'] for BILINGUAL, got {used_languages}"
        )

    @pytest.mark.unit
    def test_multilingual_falls_back_when_import_fails(self):
        """When piper_train is unavailable, MULTILINGUAL falls back gracefully.

        The phonemize() method wraps the MultilingualPhonemizer import in
        try/except ImportError.  When the import fails, it must fall through
        to the JA phonemizer / eSpeak fallback rather than propagating
        the ImportError to the caller.
        """
        import sys
        from unittest.mock import patch

        config = PiperConfig(
            num_symbols=173,
            num_speakers=1,
            sample_rate=22050,
            length_scale=1.0,
            noise_scale=0.667,
            noise_w=0.8,
            phoneme_id_map={"_": [0], "^": [1], "$": [2], "a": [10]},
            phoneme_type=PhonemeType.MULTILINGUAL,
        )

        mock_session = MagicMock()
        voice = PiperVoice(session=mock_session, config=config)

        # Temporarily remove the piper_train module from sys.modules so
        # the import inside phonemize() fails with ImportError.
        removed_modules = {}
        keys_to_remove = [k for k in sys.modules if k.startswith("piper_train")]
        for k in keys_to_remove:
            removed_modules[k] = sys.modules.pop(k)

        try:
            # Block re-import by injecting a sentinel that raises ImportError
            with patch.dict(
                "sys.modules",
                {"piper.phonemize.multilingual": None},
            ):
                # The phonemize method should not raise ImportError --
                # it should fall back to JA phonemizer or eSpeak.
                try:
                    voice.phonemize("test")
                except ImportError:
                    pytest.fail(
                        "MULTILINGUAL phonemize() must not propagate ImportError "
                        "when piper_train is unavailable -- it should fall back"
                    )
                except Exception:
                    # Other exceptions (e.g., pyopenjtalk not installed) are
                    # acceptable fallback failures, not import propagation.
                    pass
        finally:
            # Restore original modules
            sys.modules.update(removed_modules)


# ------------------------------------------------------------------
# voice.py の _warmup_session() 直接テスト
# ------------------------------------------------------------------
class TestVoiceInlineWarmup:
    """voice.py の _warmup_session() 直接テスト."""

    def _make_mock_session(self, *, has_sid=False, has_lid=False, has_prosody=False):
        session = MagicMock()
        inputs = [MagicMock(), MagicMock(), MagicMock()]
        inputs[0].name = "input"
        inputs[1].name = "input_lengths"
        inputs[2].name = "scales"
        if has_sid:
            sid = MagicMock()
            sid.name = "sid"
            inputs.append(sid)
        if has_lid:
            lid = MagicMock()
            lid.name = "lid"
            inputs.append(lid)
        if has_prosody:
            p = MagicMock()
            p.name = "prosody_features"
            inputs.append(p)
        session.get_inputs.return_value = inputs
        output = MagicMock()
        output.name = "output"
        session.get_outputs.return_value = [output]
        session.run.return_value = [MagicMock()]
        return session

    @pytest.mark.unit
    def test_warmup_calls_session_run(self):
        from piper.voice import _warmup_session

        session = self._make_mock_session()
        _warmup_session(session)
        assert session.run.call_count == 2

    @pytest.mark.unit
    @patch.dict("os.environ", {"PIPER_DISABLE_WARMUP": "1"})
    def test_warmup_disabled(self):
        from piper.voice import _warmup_session

        session = self._make_mock_session()
        _warmup_session(session)
        session.run.assert_not_called()

    @pytest.mark.unit
    def test_warmup_failure_non_fatal(self):
        from piper.voice import _warmup_session

        session = self._make_mock_session()
        session.run.side_effect = RuntimeError("ORT error")
        _warmup_session(session)  # Should not raise

    @pytest.mark.unit
    def test_warmup_optional_inputs(self):
        from piper.voice import _warmup_session

        session = self._make_mock_session(has_sid=True, has_lid=True, has_prosody=True)
        _warmup_session(session, runs=1)
        call_args = session.run.call_args
        inputs_dict = call_args[0][1]
        assert "sid" in inputs_dict
        assert "lid" in inputs_dict
        assert "prosody_features" in inputs_dict


class TestPiperConfigHopSize:
    """Tests for the hop_size field added for phoneme timing support."""

    def _base_config_dict(self):
        """Minimal valid config dict for PiperConfig.from_dict()."""
        return {
            "num_symbols": 100,
            "num_speakers": 1,
            "audio": {"sample_rate": 22050},
            "inference": {
                "noise_scale": 0.667,
                "length_scale": 1.0,
                "noise_w": 0.8,
            },
            "phoneme_id_map": {"_": [0], "^": [1], "$": [2], "a": [10]},
            "phoneme_type": "multilingual",
        }

    def test_hop_size_default_when_missing(self):
        """hop_size defaults to 256 when not present in config.json."""
        from piper.config import PiperConfig

        config_dict = self._base_config_dict()
        # No audio.hop_size key
        config = PiperConfig.from_dict(config_dict)
        assert config.hop_size == 256

    def test_hop_size_explicit_value_from_config(self):
        """hop_size is read from config['audio']['hop_size'] when provided."""
        from piper.config import PiperConfig

        config_dict = self._base_config_dict()
        config_dict["audio"]["hop_size"] = 512
        config = PiperConfig.from_dict(config_dict)
        assert config.hop_size == 512

    def test_hop_size_zero_in_config(self):
        """hop_size of 0 in config is preserved (PiperConfig does not validate)."""
        from piper.config import PiperConfig

        config_dict = self._base_config_dict()
        config_dict["audio"]["hop_size"] = 0
        config = PiperConfig.from_dict(config_dict)
        assert config.hop_size == 0

    def test_hop_size_small_value(self):
        """hop_size can be set to small values like 128."""
        from piper.config import PiperConfig

        config_dict = self._base_config_dict()
        config_dict["audio"]["hop_size"] = 128
        config = PiperConfig.from_dict(config_dict)
        assert config.hop_size == 128

    def test_hop_size_attribute_accessible_from_instance(self):
        """PiperConfig instances expose hop_size as a regular attribute."""
        from piper.config import PiperConfig

        config_dict = self._base_config_dict()
        config_dict["audio"]["hop_size"] = 256
        config = PiperConfig.from_dict(config_dict)
        # Can be read like any dataclass field
        assert hasattr(config, "hop_size")
        assert config.hop_size == 256
