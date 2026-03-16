#!/usr/bin/env python3
"""
piper-plus Gradio Demo for Hugging Face Spaces
Supports multilingual text-to-speech using a single ONNX model
"""

import json
import logging
import threading

import gradio as gr
import numpy as np
import onnxruntime
from app_imports import ESPEAK_AVAILABLE, PYOPENJTALK_AVAILABLE

# Download models if not present
from download_models import download_models


# Ensure models are downloaded
download_models()


# Import optional dependencies
if PYOPENJTALK_AVAILABLE:
    import pyopenjtalk
if ESPEAK_AVAILABLE:
    from espeak_phonemizer import Phonemizer


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
}

# Basic English word to IPA mapping for common words
# This is a simplified fallback when espeak-ng is not available
ENGLISH_IPA_MAP = {
    "hello": "hɛloʊ",
    "world": "wɜrld",
    "this": "ðɪs",
    "is": "ɪz",
    "a": "ə",
    "test": "tɛst",
    "text": "tɛkst",
    "to": "tu",
    "speech": "spitʃ",
    "demo": "dɛmoʊ",
    "welcome": "wɛlkəm",
    "piper": "paɪpər",
    "tts": "titiɛs",
    "enjoy": "ɛndʒɔɪ",
    "high": "haɪ",
    "quality": "kwɑləti",
    "synthesis": "sɪnθəsɪs",
    "the": "ðə",
    "and": "ænd",
    "for": "fɔr",
    "with": "wɪð",
    "you": "ju",
    "can": "kæn",
    "it": "ɪt",
    "that": "ðæt",
    "have": "hæv",
    "from": "frʌm",
    "or": "ɔr",
    "which": "wɪtʃ",
    "one": "wʌn",
    "would": "wʊd",
    "all": "ɔl",
    "will": "wɪl",
    "there": "ðɛr",
    "say": "seɪ",
    "who": "hu",
    "make": "meɪk",
    "when": "wɛn",
    "time": "taɪm",
    "if": "ɪf",
    "no": "noʊ",
    "way": "weɪ",
    "has": "hæz",
    "yes": "jɛs",
    "good": "gʊd",
    "very": "vɛri",
}

# Japanese multi-character phoneme to Unicode PUA mapping
# This mapping must match the C++ implementation and training data
PHONEME_TO_PUA = {
    # Long vowels
    "a:": "\ue000",
    "i:": "\ue001",
    "u:": "\ue002",
    "e:": "\ue003",
    "o:": "\ue004",
    # Special consonants
    "cl": "\ue005",  # Geminate/glottal stop
    # Palatalized consonants
    "ky": "\ue006",
    "kw": "\ue007",
    "gy": "\ue008",
    "gw": "\ue009",
    "ty": "\ue00a",
    "dy": "\ue00b",
    "py": "\ue00c",
    "by": "\ue00d",
    # Affricates and special sounds
    "ch": "\ue00e",
    "ts": "\ue00f",
    "sh": "\ue010",
    "zy": "\ue011",
    "hy": "\ue012",
    # Palatalized nasals/liquids
    "ny": "\ue013",
    "my": "\ue014",
    "ry": "\ue015",
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


def map_phonemes(phonemes: list[str]) -> list[str]:
    """Map multi-character phonemes to Unicode PUA characters"""
    result = []
    for phoneme in phonemes:
        if phoneme in PHONEME_TO_PUA:
            result.append(PHONEME_TO_PUA[phoneme])
        else:
            result.append(phoneme)
    return result


def text_to_phonemes(text: str, language: str) -> list[str]:
    """Convert text to phoneme strings based on language"""

    if language == "ja":
        if PYOPENJTALK_AVAILABLE:
            # Get phonemes from OpenJTalk
            labels = pyopenjtalk.extract_fullcontext(text)
            phonemes = []

            for label in labels:
                # Extract phoneme from label
                if "-" in label and "+" in label:
                    phoneme = label.split("-")[1].split("+")[0]
                    if phoneme not in ["sil", "pau"]:
                        phonemes.append(phoneme)

            # Add sentence markers
            phonemes = ["^"] + phonemes + ["$"]

            # Convert multi-character phonemes to Unicode PUA
            phonemes = map_phonemes(phonemes)
        else:
            logger.warning("pyopenjtalk not available, using fallback")
            # Simple fallback - just use dummy phonemes
            phonemes = ["^"] + list("aiueo") * 5 + ["$"]

    elif ESPEAK_AVAILABLE:  # English
        phonemizer = Phonemizer("en-us")
        phoneme_str = phonemizer.phonemize(text)
        # Convert phoneme string to list
        phonemes = ["^"] + list(phoneme_str.replace(" ", "")) + ["$"]
    else:
        logger.warning("espeak_phonemizer not available, using IPA fallback")
        # IPA-based fallback for better English pronunciation
        words = text.lower().split()
        phonemes = ["^"]

        for i, word in enumerate(words):
            # Add space between words
            if i > 0:
                phonemes.append(" ")

            # Remove punctuation from word
            clean_word = "".join(c for c in word if c.isalpha())

            if clean_word in ENGLISH_IPA_MAP:
                # Use IPA mapping if available
                ipa = ENGLISH_IPA_MAP[clean_word]
                phonemes.extend(list(ipa))
            else:
                # Fall back to character-by-character for unknown words
                phonemes.extend(list(clean_word))

        phonemes.append("$")

    return phonemes


def phonemes_to_ids(phonemes: list[str], config: dict) -> list[int]:
    """Convert phonemes to model input IDs"""
    phoneme_id_map = config.get("phoneme_id_map", {})

    ids = []
    for phoneme in phonemes:
        if phoneme in phoneme_id_map:
            ids.extend(phoneme_id_map[phoneme])
        else:
            # Use pad token for unknown phonemes
            ids.append(0)

    return ids


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
    config = load_model_config(model_info["config"])

    # Convert text to phoneme IDs
    phonemes = text_to_phonemes(text, model_info["language"])
    phoneme_ids = phonemes_to_ids(phonemes, config)

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


def create_interface():
    """Create Gradio interface"""
    with gr.Blocks(title="piper-plus Demo") as interface:
        gr.Markdown("""
            # piper-plus Demo

            High-quality multilingual text-to-speech synthesis supporting Japanese and English.

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
                - Select Japanese mode for hiragana/kanji text
                - Select English mode for standard English text
                - Both modes use the same multilingual model
                - Adjust speed for faster/slower speech
                - Higher expressiveness = more natural variation
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
            ],
            inputs=[text_input, model_dropdown],
        )

        # Event handlers
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
