#!/usr/bin/env python3
"""
Piper TTS Gradio Demo for Hugging Face Spaces
Supports Japanese and English text-to-speech using ONNX models
"""

import json
import logging
from pathlib import Path

import gradio as gr
import numpy as np
import onnxruntime


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model configurations
MODELS = {
    "Japanese (Medium)": {
        "path": "models/ja_JP-test-medium.onnx",
        "config": "models/ja_JP-test-medium.onnx.json",
        "language": "ja",
    },
    "English (Test)": {
        "path": "models/test_voice.onnx", 
        "config": "models/test_voice.onnx.json",
        "language": "en",
    },
}


def load_model_config(config_path: str) -> dict:
    """Load model configuration from JSON file"""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def text_to_phonemes(text: str, language: str) -> list[int]:
    """Convert text to phoneme IDs based on language"""
    
    if language == "ja":
        try:
            import pyopenjtalk
            
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
            
        except ImportError:
            logger.warning("pyopenjtalk not available, using fallback")
            # Simple fallback - just use dummy phonemes
            phonemes = ["^"] + list("aiueo") * 5 + ["$"]
            
    else:  # English
        try:
            from espeak_phonemizer import Phonemizer
            
            phonemizer = Phonemizer("en-us")
            phoneme_str = phonemizer.phonemize(text)
            # Convert phoneme string to list
            phonemes = ["^"] + list(phoneme_str.replace(" ", "")) + ["$"]
            
        except ImportError:
            logger.warning("espeak_phonemizer not available, using character fallback")
            # Character-based fallback
            phonemes = ["^"] + list(text.lower()) + ["$"]
    
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
    
    # Load ONNX model
    sess_options = onnxruntime.SessionOptions()
    sess_options.inter_op_num_threads = 1
    sess_options.intra_op_num_threads = 1
    
    try:
        model = onnxruntime.InferenceSession(
            model_info["path"], 
            sess_options=sess_options,
            providers=["CPUExecutionProvider"]
        )
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise gr.Error(f"Failed to load model: {str(e)}")
    
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
        raise gr.Error(f"Failed to generate speech: {str(e)}")


def create_interface():
    """Create Gradio interface"""
    
    with gr.Blocks(title="Piper TTS Demo") as interface:
        gr.Markdown("""
        # 🎙️ Piper TTS Demo
        
        High-quality text-to-speech synthesis supporting Japanese and English.
        
        This demo uses ONNX models for fast CPU inference.
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
                
                with gr.Accordion("Advanced Settings", open=False):
                    speaker_id = gr.Number(
                        label="Speaker ID", 
                        value=0, 
                        precision=0,
                        minimum=0,
                        maximum=10,
                        info="For multi-speaker models only"
                    )
                    
                    length_scale = gr.Slider(
                        label="Speed",
                        minimum=0.5,
                        maximum=2.0,
                        value=1.0,
                        step=0.1,
                        info="Lower = faster speech"
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
                
            with gr.Column(scale=1):
                audio_output = gr.Audio(
                    label="Generated Speech",
                    type="numpy",
                    autoplay=True,
                )
                
                gr.Markdown("""
                ### Tips:
                - Japanese model expects hiragana/kanji text
                - English model works with standard text
                - Adjust speed for faster/slower speech
                - Higher expressiveness = more natural variation
                """)
        
        # Examples
        gr.Examples(
            examples=[
                ["こんにちは、世界！今日はいい天気ですね。", "Japanese (Medium)"],
                ["おはようございます。本日の会議は午後3時から始まります。", "Japanese (Medium)"],
                ["Hello world! This is a text to speech demo.", "English (Test)"],
                ["Welcome to Piper TTS. Enjoy high quality speech synthesis.", "English (Test)"],
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


# Create and launch the app
interface = create_interface()

if __name__ == "__main__":
    interface.launch()