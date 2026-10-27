#!/usr/bin/env python3
"""Integration tests for Piper WebUI"""

import ast
import inspect
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import gradio as gr
    from piper_plus.sample_texts import SAMPLE_TEXTS, get_sample_by_category
    from piper_plus.training_manager import CHECKPOINT_FLAGS
    from piper_plus.webui import (
        TEMPLATES,
        apply_template,
        check_start_options,
        create_interface,
        find_checkpoints,
        get_available_models,
        get_language_from_model,
        start_training,
        synthesize_speech,
        update_start_mode,
        update_templates,
        validate_dataset,
    )

    WEBUI_AVAILABLE = True
except ImportError:
    WEBUI_AVAILABLE = False


TRAINER_MAIN = (
    Path(__file__).resolve().parents[3] / "src" / "python" / "piper_train" / "__main__.py"
)


def _trainer_quality_choices() -> tuple[str, ...]:
    """Read the ``--quality`` choices from piper_train's argparse setup.

    Parsed with ``ast`` so the test does not import piper_train (torch).
    """
    tree = ast.parse(TRAINER_MAIN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "--quality"
        ):
            continue
        for keyword in node.keywords:
            if keyword.arg == "choices":
                return tuple(ast.literal_eval(keyword.value))
    raise AssertionError(f"--quality choices not found in {TRAINER_MAIN}")


@pytest.mark.skipif(not WEBUI_AVAILABLE, reason="WebUI dependencies not installed")
class TestWebUI:
    """Test WebUI functionality"""

    def test_model_detection(self):
        """Test model detection from directory"""
        test_models_dir = Path("test/models")
        if test_models_dir.exists():
            models = get_available_models(test_models_dir)
            assert len(models) > 0
            assert all(isinstance(m, tuple) and len(m) == 2 for m in models)

            # Check for specific model types
            model_names = [m[0] for m in models]
            has_english = any("English" in name for name in model_names)
            has_japanese = any("Japanese" in name for name in model_names)
            assert has_english or has_japanese

    def test_language_detection(self):
        """Test language detection from model path"""
        # Test Japanese model (no config file → filename fallback to ja_JP)
        ja_lang = get_language_from_model("test/models/japanese-voice.onnx")
        assert ja_lang == "ja_JP"

        # Test multilingual model (config language.code="multilingual" → en_US fallback)
        en_lang = get_language_from_model("test/models/multilingual-test-medium.onnx")
        assert en_lang == "en_US"

        # Test fallback
        unknown_lang = get_language_from_model("test/models/unknown.onnx")
        assert unknown_lang == "en_US"  # Default fallback

    def test_template_system(self):
        """Test template functionality"""
        # Check template languages
        assert "en_US" in TEMPLATES
        assert "ja_JP" in TEMPLATES

        # Check template categories
        for lang in ["en_US", "ja_JP"]:
            assert "greeting" in TEMPLATES[lang]
            assert "news" in TEMPLATES[lang]
            assert "story" in TEMPLATES[lang]

        # Check Japanese-specific templates
        assert "announcement" in TEMPLATES["ja_JP"]
        assert "navigation" in TEMPLATES["ja_JP"]

    def test_template_updates(self):
        """Test template dropdown updates based on model"""
        # Test with Japanese model
        ja_dropdown = update_templates("test/models/multilingual-test-medium.onnx")
        assert hasattr(ja_dropdown, "choices")

        # Test with multilingual model
        en_dropdown = update_templates("test/models/multilingual-test-medium.onnx")
        assert hasattr(en_dropdown, "choices")

    def test_template_application(self):
        """Test applying templates to text input"""
        # Test custom text
        custom_text = apply_template(
            "Custom Text", "test/models/multilingual-test-medium.onnx"
        )
        assert custom_text == ""

        # Test Japanese greeting (no config file → filename fallback to ja_JP)
        ja_greeting = apply_template(
            "Greeting (greeting)", "test/models/japanese-voice.onnx"
        )
        assert "こんにちは" in ja_greeting

        # Test English greeting (multilingual model falls back to en_US)
        en_greeting = apply_template(
            "Greeting (greeting)", "test/models/multilingual-test-medium.onnx"
        )
        assert "Hello" in en_greeting

    def test_sample_texts(self):
        """Test sample text functionality"""
        # Check available languages
        assert "en_US" in SAMPLE_TEXTS
        assert "ja_JP" in SAMPLE_TEXTS

        # Check categories
        for lang in ["en_US", "ja_JP"]:
            assert "short" in SAMPLE_TEXTS[lang]
            assert "conversational" in SAMPLE_TEXTS[lang]
            assert "professional" in SAMPLE_TEXTS[lang]

        # Test sample retrieval
        ja_greeting = get_sample_by_category("ja_JP", "short", 0)
        assert ja_greeting == "こんにちは！"

        en_greeting = get_sample_by_category("en_US", "short", 0)
        assert en_greeting == "Hello world!"

    def test_interface_creation(self):
        """Test Gradio interface creation"""
        test_models_dir = Path("test/models")
        if test_models_dir.exists():
            interface = create_interface(test_models_dir)
            assert isinstance(interface, gr.Blocks)
            assert interface.title == "piper-plus"

            # Check that interface has components
            assert len(interface.blocks) > 0

    def test_training_quality_choices_match_trainer(self, tmp_path):
        """The Training tab offers only --quality values piper_train accepts.

        The tab offered "low", which piper_train rejects (its choices are
        x-low / medium / high), so a training run started with it exited at
        argument parsing.
        """
        interface = create_interface(tmp_path)
        radios = [
            block
            for block in interface.blocks.values()
            if isinstance(block, gr.Radio) and block.label == "Model Quality"
        ]
        assert len(radios) == 1
        ui_values = [
            choice[1] if isinstance(choice, tuple) else choice
            for choice in radios[0].choices
        ]
        assert ui_values == list(_trainer_quality_choices())
        assert radios[0].value in ui_values

    def test_training_start_modes_match_training_manager(self, tmp_path):
        """Every non-new start mode maps to a piper_train checkpoint flag."""
        interface = create_interface(tmp_path)
        radios = [
            block
            for block in interface.blocks.values()
            if isinstance(block, gr.Radio) and block.label == "Start"
        ]
        assert len(radios) == 1
        values = [
            choice[1] if isinstance(choice, tuple) else choice
            for choice in radios[0].choices
        ]
        assert values == ["new", *CHECKPOINT_FLAGS]
        assert radios[0].value == "new"
        # The ONNX voice list is no longer offered as something to train from.
        assert not [
            block
            for block in interface.blocks.values()
            if getattr(block, "label", None) in ("Base Model", "Number of Speakers")
        ]

    def test_synthesis_function_signature(self):
        """Test that synthesis function has correct signature"""
        # Get function signature
        sig = inspect.signature(synthesize_speech)
        params = list(sig.parameters.keys())

        # Check required parameters
        expected_params = [
            "text",
            "model_path",
            "speaker_id",
            "length_scale",
            "noise_scale",
            "noise_w",
            "language_code",
        ]
        assert params == expected_params

        # Check return type annotation
        return_annotation = sig.return_annotation
        assert return_annotation != inspect.Signature.empty


PHONEMES = {"_": [0], "^": [1], "$": [2], "a": [3]}


def _preprocessed(directory: Path, num_speakers=1, phoneme_id_map=None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "config.json").write_text(
        json.dumps(
            {
                "audio": {"sample_rate": 22050},
                "language": {"code": "ja"},
                "num_symbols": 4,
                "num_speakers": num_speakers,
                "phoneme_id_map": phoneme_id_map or PHONEMES,
            }
        ),
        encoding="utf-8",
    )
    (directory / "dataset.jsonl").write_text(
        '{"phoneme_ids": [1, 3, 2]}\n{"phoneme_ids": [1, 3, 3, 2]}\n',
        encoding="utf-8",
    )
    return directory


@pytest.mark.skipif(not WEBUI_AVAILABLE, reason="WebUI dependencies not installed")
class TestTrainingStartOptions:
    """The Training tab checks a run before piper_train sees it."""

    def test_raw_dataset_asks_for_preprocessing(self, tmp_path):
        (tmp_path / "metadata.csv").write_text("a|hello\n", encoding="utf-8")

        result = validate_dataset(str(tmp_path))

        assert "config.json and dataset.jsonl not found" in result["error"]
        assert "piper_train.preprocess" in result["error"]

    def test_preprocessed_dataset_reports_its_config(self, tmp_path):
        result = validate_dataset(str(_preprocessed(tmp_path / "data")))

        assert result["status"] == "Valid"
        assert result["utterances"] == 2
        assert result["num_speakers"] == 1
        assert result["language"] == "ja"
        assert result["sample_rate"] == 22050

    def test_new_model_needs_no_checkpoint(self, tmp_path):
        assert check_start_options("new", None, str(tmp_path)) is None

    @pytest.mark.parametrize("start_mode", ["resume", "finetune"])
    def test_onnx_voice_is_not_a_checkpoint(self, tmp_path, start_mode):
        voice = tmp_path / "voice.onnx"
        voice.touch()

        error = check_start_options(start_mode, str(voice), str(tmp_path))

        assert "not a training checkpoint (.ckpt)" in error

    def test_missing_checkpoint(self, tmp_path):
        error = check_start_options("resume", str(tmp_path / "x.ckpt"), "")
        assert "does not exist" in error

    def test_resume_accepts_an_existing_ckpt(self, tmp_path):
        checkpoint = tmp_path / "last.ckpt"
        checkpoint.touch()
        assert check_start_options("resume", str(checkpoint), str(tmp_path)) is None

    def test_finetune_needs_a_single_speaker_dataset(self, tmp_path):
        dataset = _preprocessed(tmp_path / "data", num_speakers=3)
        checkpoint = tmp_path / "base" / "base.ckpt"
        checkpoint.parent.mkdir()
        checkpoint.touch()

        error = check_start_options("finetune", str(checkpoint), str(dataset))

        assert "has 3 speakers" in error

    def test_finetune_needs_the_base_phoneme_ids(self, tmp_path):
        """A released base ships config.json next to base.ckpt (releases/zs-v1)."""
        dataset = _preprocessed(tmp_path / "data")
        base = _preprocessed(
            tmp_path / "base", phoneme_id_map={**PHONEMES, "a": [4]}
        )
        checkpoint = base / "base.ckpt"
        checkpoint.touch()

        error = check_start_options("finetune", str(checkpoint), str(dataset))

        assert "prepare_single_speaker_finetune.py" in error

        aligned = _preprocessed(tmp_path / "aligned", phoneme_id_map={**PHONEMES, "a": [4]})
        assert check_start_options("finetune", str(checkpoint), str(aligned)) is None

    def test_find_checkpoints_lists_newest_first(self, tmp_path):
        old = tmp_path / "lightning_logs" / "version_0" / "checkpoints" / "a.ckpt"
        new = tmp_path / "lightning_logs" / "version_1" / "checkpoints" / "b.ckpt"
        for path in (old, new):
            path.parent.mkdir(parents=True)
            path.touch()
        os.utime(old, (1, 1))

        assert find_checkpoints(str(tmp_path)) == [str(new), str(old)]
        assert find_checkpoints(str(tmp_path / "missing")) == []

    def test_mode_change_sets_picker_and_learning_rate(self, tmp_path):
        checkpoint = tmp_path / "checkpoints" / "last.ckpt"
        checkpoint.parent.mkdir()
        checkpoint.touch()

        picker, learning_rate = update_start_mode("resume", str(tmp_path))
        assert picker["visible"] is True
        assert picker["value"] == str(checkpoint)
        # A resumed run restores its optimizer state; the field is left alone.
        assert "value" not in learning_rate

        picker, learning_rate = update_start_mode("finetune", str(tmp_path))
        assert picker["visible"] is True
        assert picker["value"] is None
        assert learning_rate["value"] == 2e-5

        picker, learning_rate = update_start_mode("new", str(tmp_path))
        assert picker["visible"] is False
        assert learning_rate["value"] == 1e-4

    def test_start_training_rejects_onnx_before_launching(self, tmp_path):
        dataset = _preprocessed(tmp_path / "data")
        voice = tmp_path / "voice.onnx"
        voice.touch()

        with patch("piper_plus.training_manager.subprocess.Popen") as popen:
            result = start_training(
                dataset_path=str(dataset),
                start_mode="resume",
                checkpoint_path=str(voice),
                quality="medium",
                batch_size=1,
                learning_rate=1e-4,
                num_epochs=1,
                checkpoint_interval=1,
                validation_split=0.1,
                output_dir=str(tmp_path / "out"),
            )

        assert "❌" in result
        assert ".ckpt" in result
        popen.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
