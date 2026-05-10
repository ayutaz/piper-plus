#!/usr/bin/env python3
"""piper-plus WebUI - Gradio-based interface for text-to-speech synthesis."""

import argparse
import json
import threading
from pathlib import Path

import gradio as gr
import numpy as np
import onnxruntime

from piper_train.infer_onnx import text_to_phoneme_ids_and_prosody
from piper_train.ort_utils import create_session_with_cache, warmup_onnx_session


SAMPLE_TEXTS = {
    "ja": "こんにちは、今日はとても良い天気ですね。散歩に出かけましょう。",
    "en": "Hello, how are you today? The weather is beautiful, let's go for a walk.",
    "zh": "你好，今天天气非常好。我们一起去散步吧。",
    "es": "Hola, ¿cómo estás hoy? El clima es hermoso, vamos a dar un paseo.",
    "fr": "Bonjour, comment allez-vous aujourd'hui? Il fait beau, allons nous promener.",
    "pt": "Olá, como você está hoje? O tempo está lindo, vamos dar um passeio.",
    "sv": "Hej, hur mår du idag?",
}


def on_language_change(language: str) -> str:
    """Return sample text for the selected language."""
    return SAMPLE_TEXTS.get(language, "")


_session_cache: dict[str, onnxruntime.InferenceSession] = {}
_config_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def _get_session(model_path: str) -> onnxruntime.InferenceSession:
    """Return a cached InferenceSession, creating one if needed."""
    with _cache_lock:
        if model_path not in _session_cache:
            session = create_session_with_cache(
                model_path, device="cpu", intra_op_threads=1
            )
            warmup_onnx_session(session)
            _session_cache[model_path] = session
        return _session_cache[model_path]


def _get_config(model_path: str) -> dict | None:
    """Return a cached config dict, loading from disk if needed."""
    with _cache_lock:
        if model_path not in _config_cache:
            config = load_config(model_path)
            if config is None:
                return None
            _config_cache[model_path] = config
        return _config_cache[model_path]


def audio_float_to_int16(
    audio: np.ndarray, max_wav_value: float = 32767.0
) -> np.ndarray:
    """Normalize audio and convert to int16 range."""
    audio_norm = audio * (max_wav_value / max(0.01, np.max(np.abs(audio))))
    audio_norm = np.clip(audio_norm, -max_wav_value, max_wav_value)
    audio_norm = audio_norm.astype("int16")
    return audio_norm


def find_models(model_dir: str) -> list[str]:
    """Find all ONNX models in the given directory."""
    model_dir_path = Path(model_dir)
    models = sorted(model_dir_path.glob("**/*.onnx"))
    return [str(m) for m in models]


def load_config(model_path: str) -> dict | None:
    """Load config.json associated with a model."""
    model_p = Path(model_path)
    for config_path in [
        model_p.with_suffix(".onnx.json"),
        model_p.parent / "config.json",
    ]:
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                return json.load(f)
    return None


_SHORT_TEXT_THRESHOLD = 10


def _is_short_text(text: str, threshold: int = _SHORT_TEXT_THRESHOLD) -> bool:
    """Check if text is short (excluding whitespace)."""
    if text.lstrip().startswith(("<speak>", "<speak ")):
        return False
    return sum(1 for c in text if not c.isspace()) <= threshold


def synthesize(
    text: str,
    model_path: str,
    speaker_id: int,
    language: str,
    noise_scale: float,
    length_scale: float,
    noise_scale_w: float,
) -> tuple[int, np.ndarray] | None:
    """Synthesize text to speech."""
    if not text.strip() or not model_path:
        return None

    if _is_short_text(text):
        gr.Warning(
            "Short text may produce degraded audio quality. "
            "Consider using a longer sentence.\n"
            "短いテキストは音声品質が低下する可能性があります。"
            "より長い文章をお試しください。"
        )

    config = _get_config(model_path)
    if config is None:
        raise gr.Error("config.json not found for selected model")

    phoneme_id_map = config.get("phoneme_id_map")
    if not phoneme_id_map:
        raise gr.Error("phoneme_id_map not found in config.json")

    sample_rate = config.get("audio", {}).get("sample_rate", 22050)

    language_id_map = config.get("language_id_map", {})

    phoneme_ids, prosody_features_data = text_to_phoneme_ids_and_prosody(
        text, phoneme_id_map, language=language, language_id_map=language_id_map
    )

    session = _get_session(model_path)
    input_names = [inp.name for inp in session.get_inputs()]
    has_prosody = "prosody_features" in input_names
    has_sid = "sid" in input_names
    has_lid = "lid" in input_names

    text_array = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
    text_lengths = np.array([text_array.shape[1]], dtype=np.int64)
    scales = np.array([noise_scale, length_scale, noise_scale_w], dtype=np.float32)

    inputs = {
        "input": text_array,
        "input_lengths": text_lengths,
        "scales": scales,
    }

    if has_sid:
        inputs["sid"] = np.array([int(speaker_id)], dtype=np.int64)

    if has_lid:
        language_id = language_id_map.get(language, 0)
        inputs["lid"] = np.array([language_id], dtype=np.int64)

    if has_prosody and prosody_features_data:
        prosody_array = []
        for pf in prosody_features_data:
            if pf is None:
                prosody_array.append([0, 0, 0])
            else:
                prosody_array.append([pf["a1"], pf["a2"], pf["a3"]])
        inputs["prosody_features"] = np.expand_dims(
            np.array(prosody_array, dtype=np.int64), 0
        )

    outputs = session.run(None, inputs)
    audio = outputs[0].squeeze(0)
    audio = audio_float_to_int16(audio.squeeze())

    return (sample_rate, audio)


def create_ui(model_dir: str, output_dir: str):
    """Create the Gradio UI."""
    models = find_models(model_dir)
    model_choices = models if models else ["No models found"]

    with gr.Blocks(title="piper-plus") as demo:
        gr.Markdown("# piper-plus")

        with gr.Row():
            with gr.Column():
                text_input = gr.Textbox(
                    label="Text",
                    placeholder="Enter text to synthesize...",
                    info=(
                        "Tip: Very short text (10 chars or less) may produce "
                        "degraded audio. Use longer sentences for best quality. "
                        "/ 短いテキスト(10文字以下)は音声品質が低下する場合があります。"
                    ),
                    lines=3,
                    value=SAMPLE_TEXTS["ja"],
                )
                model_dropdown = gr.Dropdown(
                    choices=model_choices,
                    label="Model",
                    value=model_choices[0] if models else None,
                )
                language = gr.Radio(
                    choices=["ja", "en", "zh", "es", "fr", "pt", "sv"],
                    label="Language",
                    value="ja",
                )
                speaker_id = gr.Number(label="Speaker ID", value=0, precision=0)

                with gr.Accordion("Advanced", open=False):
                    noise_scale = gr.Slider(0.0, 1.0, value=0.667, label="Noise Scale")
                    length_scale = gr.Slider(0.1, 3.0, value=1.0, label="Length Scale")
                    noise_scale_w = gr.Slider(
                        0.0, 1.0, value=0.8, label="Noise Scale W"
                    )

                btn = gr.Button("Synthesize", variant="primary")

            with gr.Column():
                audio_output = gr.Audio(label="Output", type="numpy")

        language.change(
            fn=on_language_change,
            inputs=[language],
            outputs=[text_input],
        )

        btn.click(
            fn=synthesize,
            inputs=[
                text_input,
                model_dropdown,
                speaker_id,
                language,
                noise_scale,
                length_scale,
                noise_scale_w,
            ],
            outputs=audio_output,
        )

    return demo


def main():
    parser = argparse.ArgumentParser(description="piper-plus WebUI")
    parser.add_argument(
        "--model-dir", default="/models", help="Directory containing ONNX models"
    )
    parser.add_argument(
        "--output-dir", default="/output", help="Directory for output files"
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()

    demo = create_ui(args.model_dir, args.output_dir)
    demo.launch(server_name=args.host, server_port=args.port)


if __name__ == "__main__":
    main()
