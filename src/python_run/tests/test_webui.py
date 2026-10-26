#!/usr/bin/env python3
"""Integration tests for Piper WebUI"""

import ast
import inspect
import os
import sys
from pathlib import Path

import pytest


# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import gradio as gr
    from piper_plus.sample_texts import SAMPLE_TEXTS, get_sample_by_category
    from piper_plus.webui import (
        TEMPLATES,
        apply_template,
        create_interface,
        get_available_models,
        get_language_from_model,
        synthesize_speech,
        update_templates,
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
