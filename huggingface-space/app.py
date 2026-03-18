#!/usr/bin/env python3
"""
piper-plus Gradio Demo for Hugging Face Spaces
Supports multilingual text-to-speech using a single ONNX model
"""

import json
import logging
import threading

import gradio as gr
import nltk
import numpy as np
import onnxruntime


# Download NLTK data required by g2p-en (English phonemizer).
# This must run before importing modules that transitively load g2p-en.
nltk.download("averaged_perceptron_tagger_eng", quiet=True)
nltk.download("cmudict", quiet=True)

# Download models if not present
from download_models import download_models  # noqa: E402

from piper_train.infer_onnx import text_to_phoneme_ids_and_prosody  # noqa: E402


# Ensure models are downloaded
download_models()


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model configurations
# A single multilingual model handles all languages; the "language" field
# controls which phonemizer is used for text input.
MODELS = {
    "Multilingual (Japanese)": {
        "path": "models/multilingual-test-medium.onnx",
        "config": "models/multilingual-test-medium.onnx.json",
        "language": "ja",
    },
    "Multilingual (English)": {
        "path": "models/multilingual-test-medium.onnx",
        "config": "models/multilingual-test-medium.onnx.json",
        "language": "en",
    },
    "Multilingual (Chinese)": {
        "path": "models/multilingual-test-medium.onnx",
        "config": "models/multilingual-test-medium.onnx.json",
        "language": "zh",
    },
    "Multilingual (Spanish)": {
        "path": "models/multilingual-test-medium.onnx",
        "config": "models/multilingual-test-medium.onnx.json",
        "language": "es",
    },
    "Multilingual (French)": {
        "path": "models/multilingual-test-medium.onnx",
        "config": "models/multilingual-test-medium.onnx.json",
        "language": "fr",
    },
    "Multilingual (Portuguese)": {
        "path": "models/multilingual-test-medium.onnx",
        "config": "models/multilingual-test-medium.onnx.json",
        "language": "pt",
    },
}

# Sample texts shown when the user switches language/model
SAMPLE_TEXTS = {
    "ja": "こんにちは、今日はとても良い天気ですね。散歩に出かけましょう。",
    "en": "Hello, how are you today? The weather is beautiful, let's go for a walk.",
    "zh": "你好，今天天气非常好。我们一起去散步吧。",
    "es": "Hola, ¿cómo estás hoy? El clima es hermoso, vamos a dar un paseo.",
    "fr": "Bonjour, comment allez-vous aujourd'hui? Il fait beau, allons nous promener.",
    "pt": "Olá, como você está hoje? O tempo está lindo, vamos dar um passeio.",
}

_session_cache: dict[str, onnxruntime.InferenceSession] = {}
_session_lock = threading.Lock()


def _get_session(model_path: str) -> onnxruntime.InferenceSession:
    """Return a cached InferenceSession, creating one if needed."""
    with _session_lock:
        if model_path not in _session_cache:
            sess_options = onnxruntime.SessionOptions()
            sess_options.inter_op_num_threads = 1
            sess_options.intra_op_num_threads = 1
            _session_cache[model_path] = onnxruntime.InferenceSession(
                model_path,
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )
        return _session_cache[model_path]


def load_model_config(config_path: str) -> dict:
    """Load model configuration from JSON file"""
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def synthesize_speech(
    text: str,
    model_name: str,
    speaker_id: int = 0,
    length_scale: float = 1.0,
    noise_scale: float = 0.667,
    noise_w: float = 0.8,
) -> tuple[int, np.ndarray]:
    """Generate speech from text using selected model"""

    if not text.strip():
        raise gr.Error("Please enter some text")

    if model_name not in MODELS:
        raise gr.Error("Invalid model selected")

    model_info = MODELS[model_name]
    language = model_info["language"]
    config = load_model_config(model_info["config"])

    # Convert text to phoneme IDs and prosody features
    phoneme_id_map = config.get("phoneme_id_map", {})
    language_id_map = config.get("language_id_map", {})
    phoneme_ids, prosody_features_data = text_to_phoneme_ids_and_prosody(
        text, phoneme_id_map, language=language, language_id_map=language_id_map
    )

    if not phoneme_ids:
        raise gr.Error("Failed to convert text to phonemes")

    # Get cached ONNX session
    try:
        model = _get_session(model_info["path"])
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise gr.Error(f"Failed to load model: {str(e)}") from e

    # Prepare inputs
    text_array = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
    text_lengths = np.array([text_array.shape[1]], dtype=np.int64)
    scales = np.array([noise_scale, length_scale, noise_w], dtype=np.float32)

    # Handle speaker ID for multi-speaker models
    sid = None
    if config.get("num_speakers", 1) > 1:
        sid = np.array([speaker_id], dtype=np.int64)

    # Run inference
    try:
        inputs = {
            "input": text_array,
            "input_lengths": text_lengths,
            "scales": scales,
        }

        if sid is not None:
            inputs["sid"] = sid

        # Add language ID (lid) if the model supports multilingual conditioning
        input_names_set = {inp.name for inp in model.get_inputs()}
        if "lid" in input_names_set:
            lid_value = language_id_map.get(language, 0)
            inputs["lid"] = np.array([lid_value], dtype=np.int64)

        # Add prosody_features if the model requires them
        if "prosody_features" in input_names_set:
            if prosody_features_data:
                prosody_array = []
                for pf in prosody_features_data:
                    if pf is None:
                        prosody_array.append([0, 0, 0])
                    else:
                        prosody_array.append([pf["a1"], pf["a2"], pf["a3"]])
                inputs["prosody_features"] = np.expand_dims(
                    np.array(prosody_array, dtype=np.int64), 0
                )
            else:
                # Fallback: zero-filled prosody
                num_phonemes = text_array.shape[1]
                inputs["prosody_features"] = np.zeros(
                    (1, num_phonemes, 3), dtype=np.int64
                )

        audio = model.run(None, inputs)[0]

        # Remove batch and channel dimensions
        audio = audio.squeeze()

        # Convert to int16
        audio = np.clip(audio * 32767, -32768, 32767).astype(np.int16)

        sample_rate = config.get("audio", {}).get("sample_rate", 22050)

        return sample_rate, audio

    except Exception as e:
        logger.error(f"Inference failed: {e}")
        raise gr.Error(f"Failed to generate speech: {str(e)}") from e


def on_model_change(model_name: str) -> str:
    """Return sample text for the selected model's language."""
    model_info = MODELS.get(model_name, {})
    language = model_info.get("language", "ja")
    return SAMPLE_TEXTS.get(language, "")


def create_interface():
    """Create Gradio interface"""
    with gr.Blocks(title="piper-plus Demo") as interface:
        gr.Markdown("""
            # piper-plus Demo

            High-quality multilingual text-to-speech synthesis supporting Japanese, English,
            Chinese, Spanish, French, and Portuguese.

            This demo uses a single multilingual ONNX model for fast CPU inference.
            """)

        with gr.Row():
            with gr.Column(scale=2):
                model_dropdown = gr.Dropdown(
                    choices=list(MODELS.keys()),
                    label="Select Model",
                    value=list(MODELS.keys())[0],
                )

                text_input = gr.Textbox(
                    label="Text to synthesize",
                    placeholder="Enter text here...",
                    value=SAMPLE_TEXTS["ja"],
                    lines=3,
                )

                # Advanced Settings without Accordion (flattened)
                gr.Markdown("### Advanced Settings")

                speaker_id = gr.Number(
                    label="Speaker ID (for multi-speaker models)",
                    value=0,
                    precision=0,
                    minimum=0,
                    maximum=10,
                )

                length_scale = gr.Slider(
                    label="Speed (Lower = faster speech)",
                    minimum=0.5,
                    maximum=2.0,
                    value=1.0,
                    step=0.1,
                )

                noise_scale = gr.Slider(
                    label="Expressiveness",
                    minimum=0.0,
                    maximum=1.0,
                    value=0.667,
                    step=0.01,
                )

                noise_w = gr.Slider(
                    label="Phoneme Duration Variance",
                    minimum=0.0,
                    maximum=1.0,
                    value=0.8,
                    step=0.01,
                )

            synthesize_btn = gr.Button("Generate Speech", variant="primary")

        with gr.Column(scale=2):
            audio_output = gr.Audio(
                label="Generated Speech",
                type="numpy",
                autoplay=True,
            )

            gr.Markdown("""
                ### Tips:
                - Select the language matching your input text
                - All modes use the same multilingual ONNX model
                - Adjust speed for faster/slower speech
                - Higher expressiveness = more natural variation
                - Chinese, Spanish, French, Portuguese require piper_train installed
                """)

        # Examples
        gr.Examples(
            examples=[
                ["こんにちは、世界！今日はいい天気ですね。", "Multilingual (Japanese)"],
                [
                    "おはようございます。本日の会議は午後3時から始まります。",
                    "Multilingual (Japanese)",
                ],
                [
                    "Hello world! This is a text to speech demo.",
                    "Multilingual (English)",
                ],
                [
                    "Welcome to piper-plus. Enjoy high quality speech synthesis.",
                    "Multilingual (English)",
                ],
                ["你好，世界！今天天气很好。", "Multilingual (Chinese)"],
                ["¡Hola, mundo! Bienvenido a piper-plus.", "Multilingual (Spanish)"],
                [
                    "Bonjour le monde! Bienvenue sur piper-plus.",
                    "Multilingual (French)",
                ],
                ["Olá, mundo! Bem-vindo ao piper-plus.", "Multilingual (Portuguese)"],
            ],
            inputs=[text_input, model_dropdown],
        )

        # Event handlers
        model_dropdown.change(
            fn=on_model_change,
            inputs=[model_dropdown],
            outputs=[text_input],
        )

        synthesize_btn.click(
            fn=synthesize_speech,
            inputs=[
                text_input,
                model_dropdown,
                speaker_id,
                length_scale,
                noise_scale,
                noise_w,
            ],
            outputs=audio_output,
        )

    return interface


def create_minimal_interface():
    """Create a minimal fallback interface if main interface fails"""
    with gr.Blocks(title="piper-plus Demo") as interface:
        gr.Markdown("# piper-plus Demo")

        text_input = gr.Textbox(
            label="Text to synthesize",
            placeholder="Enter text here...",
            lines=3,
        )

        model_dropdown = gr.Dropdown(
            choices=list(MODELS.keys()),
            label="Select Model",
            value=list(MODELS.keys())[0],
        )

        synthesize_btn = gr.Button("Generate Speech", variant="primary")

        audio_output = gr.Audio(
            label="Generated Speech",
            type="numpy",
        )

        synthesize_btn.click(
            fn=lambda text, model: synthesize_speech(text, model, 0, 1.0, 0.667, 0.8),
            inputs=[text_input, model_dropdown],
            outputs=audio_output,
        )

    return interface


# Create and launch the app
# Move interface creation inside main block to avoid context issues
interface = None

if __name__ == "__main__":
    # Create and launch interface
    interface = create_interface()
    # Launch with minimal configuration for Hugging Face Spaces
    interface.launch()
