"""Tests for the zero-shot tab handler of the HF Space app."""

import app
import gradio as gr
import numpy as np
import pytest
import zero_shot


REFERENCE = (16000, np.ones(16000, dtype=np.int16))


class RaisingEngine:
    def __init__(self, error):
        self.error = error

    def synthesize(self, *_args, **_kwargs):
        raise self.error


class RecordingEngine:
    def __init__(self):
        self.calls = []

    def synthesize(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return 22050, np.zeros(10, dtype=np.int16)


def test_ui_requires_reference():
    with pytest.raises(gr.Error, match="reference"):
        app.synthesize_zero_shot_ui("こんにちは", "ja", None, 1.0, 0.667, 0.8)


def test_ui_rejects_empty_text():
    with pytest.raises(gr.Error):
        app.synthesize_zero_shot_ui("  ", "ja", REFERENCE, 1.0, 0.667, 0.8)


def test_ui_maps_input_errors_to_gr_error(monkeypatch):
    engine = RaisingEngine(zero_shot.ZeroShotInputError("too short"))
    monkeypatch.setattr(zero_shot, "get_engine", lambda: engine)
    with pytest.raises(gr.Error, match="too short"):
        app.synthesize_zero_shot_ui("こんにちは", "ja", REFERENCE, 1.0, 0.667, 0.8)


def test_ui_maps_download_failure_to_gr_error(monkeypatch):
    monkeypatch.setattr(zero_shot, "get_engine", lambda: RaisingEngine(OSError("hub")))
    with pytest.raises(gr.Error, match="failed"):
        app.synthesize_zero_shot_ui("こんにちは", "ja", REFERENCE, 1.0, 0.667, 0.8)


def test_ui_passes_settings_to_engine(monkeypatch):
    engine = RecordingEngine()
    monkeypatch.setattr(zero_shot, "get_engine", lambda: engine)
    result = app.synthesize_zero_shot_ui("Hello", "en", REFERENCE, 1.2, 0.5, 0.6)
    assert result[0] == 22050
    (args, kwargs) = engine.calls[0]
    assert args[:2] == ("Hello", "en")
    assert args[2] is REFERENCE
    assert kwargs == {"length_scale": 1.2, "noise_scale": 0.5, "noise_w": 0.6}


def test_interface_builds_with_zero_shot_tab():
    assert len(app.MODELS) == 6
    assert app.create_interface() is not None
