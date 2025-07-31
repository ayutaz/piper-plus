#!/usr/bin/env python3
"""Gradio WebUI for Piper TTS"""

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import gradio as gr
import numpy as np

try:
    from piper import PiperVoice
except ImportError:
    # For testing UI without piper installed
    PiperVoice = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Template definitions for different languages
TEMPLATES = {
    "en_US": {
        "greeting": "Hello! Welcome to our service. How may I assist you today?",
        "news": "In today's news, researchers have made a breakthrough discovery in artificial intelligence, advancing the field of speech synthesis.",
        "story": "Once upon a time, in a small village nestled between mountains, there lived a curious young inventor.",
        "product": "Introducing our latest innovation - a revolutionary device that will transform your daily routine.",
        "assistant": "I understand your request. Let me help you with that information.",
    },
    "ja_JP": {
        "greeting": "こんにちは。本日はどのようなご用件でしょうか。お気軽にお申し付けください。",
        "news": "本日のニュースです。人工知能の分野で画期的な発見があり、音声合成技術が大きく進歩しました。",
        "story": "昔々、山に囲まれた小さな村に、好奇心旺盛な若い発明家が住んでいました。",
        "product": "新製品のご紹介です。この革新的なデバイスは、あなたの日常を劇的に変えることでしょう。",
        "assistant": "承知いたしました。そちらの情報についてお手伝いさせていただきます。",
    },
    "de_DE": {
        "greeting": "Guten Tag! Willkommen bei unserem Service. Wie kann ich Ihnen heute helfen?",
        "news": "In den heutigen Nachrichten haben Forscher einen bahnbrechenden Fortschritt in der künstlichen Intelligenz erzielt.",
        "story": "Es war einmal in einem kleinen Dorf, das zwischen Bergen lag, ein neugieriger junger Erfinder.",
        "product": "Wir präsentieren unsere neueste Innovation - ein revolutionäres Gerät, das Ihren Alltag verändern wird.",
        "assistant": "Ich verstehe Ihre Anfrage. Lassen Sie mich Ihnen bei diesen Informationen helfen.",
    },
    "fr_FR": {
        "greeting": "Bonjour! Bienvenue dans notre service. Comment puis-je vous aider aujourd'hui?",
        "news": "Dans l'actualité d'aujourd'hui, des chercheurs ont fait une découverte révolutionnaire en intelligence artificielle.",
        "story": "Il était une fois, dans un petit village niché entre les montagnes, un jeune inventeur curieux.",
        "product": "Nous vous présentons notre dernière innovation - un appareil révolutionnaire qui transformera votre quotidien.",
        "assistant": "Je comprends votre demande. Permettez-moi de vous aider avec ces informations.",
    },
}

# Template descriptions for UI
TEMPLATE_DESCRIPTIONS = {
    "greeting": "Greeting",
    "news": "News Reading", 
    "story": "Story Telling",
    "product": "Product Description",
    "assistant": "Voice Assistant",
}


def get_available_models(data_dir: Path) -> List[Tuple[str, str]]:
    """Scan directory for available ONNX models"""
    models = []
    
    if not data_dir.exists():
        logger.warning(f"Data directory {data_dir} does not exist")
        return [("No models found", "")]
    
    for onnx_file in data_dir.rglob("*.onnx"):
        # Skip .onnx.json files
        if onnx_file.suffix == ".json":
            continue
            
        config_file = onnx_file.with_suffix(".onnx.json")
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                language = config.get("language", {})
                if isinstance(language, dict):
                    lang_code = language.get("code", "unknown")
                else:
                    lang_code = str(language)
                display_name = f"{lang_code} - {onnx_file.stem}"
                models.append((display_name, str(onnx_file)))
            except Exception as e:
                logger.error(f"Error reading config for {onnx_file}: {e}")
                models.append((onnx_file.stem, str(onnx_file)))
        else:
            models.append((onnx_file.stem, str(onnx_file)))
    
    return models if models else [("No models found", "")]


def get_language_from_model(model_path: str) -> str:
    """Extract language code from model path or config"""
    if not model_path or model_path == "":
        return "en_US"
    
    try:
        config_path = Path(model_path).with_suffix(".onnx.json")
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            language = config.get("language", {})
            if isinstance(language, dict):
                return language.get("code", "en_US")
            return str(language)
    except Exception as e:
        logger.error(f"Error getting language from model: {e}")
    
    # Try to extract from filename
    model_name = Path(model_path).stem
    for lang_code in TEMPLATES.keys():
        if lang_code.lower() in model_name.lower():
            return lang_code
    
    return "en_US"


def update_templates(model_path: str) -> gr.Dropdown:
    """Update template choices based on selected model"""
    language = get_language_from_model(model_path)
    
    options = ["Custom Text"]
    if language in TEMPLATES:
        options.extend([
            f"{TEMPLATE_DESCRIPTIONS[key]} ({key})"
            for key in TEMPLATES[language].keys()
        ])
    
    return gr.Dropdown(choices=options, value="Custom Text")


def apply_template(template_choice: str, model_path: str) -> str:
    """Apply selected template to text input"""
    if template_choice == "Custom Text":
        return ""
    
    language = get_language_from_model(model_path)
    
    # Extract template key from choice
    template_key = None
    for key in TEMPLATE_DESCRIPTIONS:
        if f"({key})" in template_choice:
            template_key = key
            break
    
    if template_key and language in TEMPLATES:
        return TEMPLATES[language].get(template_key, "")
    
    return ""


def synthesize_speech(
    text: str,
    model_path: str,
    speaker_id: int,
    length_scale: float,
    noise_scale: float,
    noise_w: float,
) -> Tuple[int, np.ndarray]:
    """Generate speech from text"""
    if not text.strip():
        raise gr.Error("Please enter some text")
    
    if not model_path or model_path == "" or not Path(model_path).exists():
        raise gr.Error("Please select a valid model")
    
    if PiperVoice is None:
        # Return dummy audio for UI testing
        logger.warning("PiperVoice not available, returning dummy audio")
        sample_rate = 22050
        duration = 2.0  # seconds
        t = np.linspace(0, duration, int(sample_rate * duration))
        audio = np.sin(2 * np.pi * 440 * t) * 0.3  # 440 Hz sine wave
        return sample_rate, (audio * 32767).astype(np.int16)
    
    try:
        # Load voice and generate audio
        voice = PiperVoice.load(model_path)
        audio_generator = voice.synthesize(
            text,
            speaker_id=speaker_id,
            length_scale=length_scale,
            noise_scale=noise_scale,
            noise_w=noise_w,
        )
        
        # Convert generator to numpy array
        audio = np.array(list(audio_generator), dtype=np.int16)
        
        return voice.config.sample_rate, audio
    except Exception as e:
        logger.error(f"Synthesis error: {e}")
        raise gr.Error(f"Synthesis failed: {str(e)}")


def validate_dataset(dataset_path: str) -> Dict:
    """Validate dataset structure and return statistics"""
    if not dataset_path:
        return {"error": "Please specify a dataset path"}
    
    dataset_dir = Path(dataset_path)
    if not dataset_dir.exists():
        return {"error": f"Directory {dataset_path} does not exist"}
    
    if not dataset_dir.is_dir():
        return {"error": f"{dataset_path} is not a directory"}
    
    # Check for metadata.csv
    metadata_file = dataset_dir / "metadata.csv"
    if not metadata_file.exists():
        return {"error": "metadata.csv not found in dataset directory"}
    
    # Analyze dataset
    stats = {
        "path": dataset_path,
        "status": "Valid",
        "files": 0,
        "total_duration": "Unknown",
        "speakers": [],
        "sample_rate": "Unknown",
    }
    
    # Count audio files
    audio_extensions = {".wav", ".mp3", ".flac", ".ogg"}
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(dataset_dir.rglob(f"*{ext}"))
    stats["files"] = len(audio_files)
    
    # Try to read metadata.csv for speaker info
    try:
        import csv
        speakers = set()
        with open(metadata_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="|")
            for row in reader:
                if len(row) >= 3:  # speaker|filename|text format
                    speakers.add(row[0])
        stats["speakers"] = list(speakers)
    except Exception as e:
        logger.error(f"Error reading metadata.csv: {e}")
    
    return stats


def start_training(
    dataset_path: str,
    base_model: str,
    num_speakers: int,
    quality: str,
    batch_size: int,
    learning_rate: float,
    num_epochs: int,
    checkpoint_interval: int,
    validation_split: float,
) -> str:
    """Start training process (mock implementation for UI)"""
    # This is a placeholder - actual implementation would start a background process
    return "Training started! (This is a UI demo - actual training not implemented)"


def create_interface(data_dir: Path) -> gr.Blocks:
    """Create Gradio interface with tabs for inference and training"""
    available_models = get_available_models(data_dir)
    
    with gr.Blocks(title="Piper TTS WebUI") as interface:
        gr.Markdown("# Piper TTS WebUI")
        gr.Markdown("Generate high-quality speech from text using Piper TTS models.")
        
        with gr.Tabs():
            # Inference Tab
            with gr.TabItem("Inference"):
                with gr.Row():
                    with gr.Column(scale=2):
                        model_dropdown = gr.Dropdown(
                            choices=available_models,
                            label="Select Model",
                            value=available_models[0][1] if available_models else None,
                        )
                        
                        with gr.Row():
                            template_dropdown = gr.Dropdown(
                                choices=["Custom Text"],
                                label="Template",
                                value="Custom Text",
                            )
                            reset_btn = gr.Button("Reset", size="sm")
                        
                        text_input = gr.Textbox(
                            label="Text to synthesize",
                            placeholder="Enter your text here...",
                            lines=5,
                        )
                        
                        with gr.Accordion("Advanced Settings", open=False):
                            speaker_id = gr.Number(
                                label="Speaker ID",
                                value=0,
                                precision=0,
                                minimum=0,
                                maximum=99,
                            )
                            
                            length_scale = gr.Slider(
                                label="Speed (Length Scale)",
                                minimum=0.5,
                                maximum=2.0,
                                value=1.0,
                                step=0.1,
                                info="Lower = faster speech",
                            )
                            
                            noise_scale = gr.Slider(
                                label="Noise Scale",
                                minimum=0.0,
                                maximum=1.0,
                                value=0.667,
                                step=0.01,
                                info="Higher = more expressive",
                            )
                            
                            noise_w = gr.Slider(
                                label="Noise Width",
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
                        )
                        
                        gr.Markdown("""
                        ### Tips:
                        - Lower speed values = faster speech
                        - Higher noise scale = more expressive
                        - Speaker ID only works with multi-speaker models
                        """)
                
                # Examples
                gr.Examples(
                    examples=[
                        ["Hello, welcome to Piper text to speech system.", available_models[0][1] if available_models else "", 0, 1.0, 0.667, 0.8],
                        ["The quick brown fox jumps over the lazy dog.", available_models[0][1] if available_models else "", 0, 0.8, 0.5, 0.8],
                    ],
                    inputs=[text_input, model_dropdown, speaker_id, length_scale, noise_scale, noise_w],
                )
            
            # Training Tab
            with gr.TabItem("Training"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("## Dataset Configuration")
                        
                        dataset_path = gr.Textbox(
                            label="Dataset Directory Path",
                            placeholder="/path/to/your/dataset",
                            info="Folder containing audio files and metadata.csv",
                        )
                        
                        validate_btn = gr.Button("Validate Dataset")
                        
                        dataset_info = gr.JSON(
                            label="Dataset Information",
                            visible=False,
                        )
                        
                        gr.Markdown("""
                        ### Expected folder structure:
                        ```
                        dataset/
                        ├── metadata.csv (speaker|filename|text)
                        ├── wavs/
                        │   ├── audio_001.wav
                        │   ├── audio_002.wav
                        │   └── ...
                        └── speaker_info.json (optional)
                        ```
                        """)
                    
                    with gr.Column():
                        gr.Markdown("## Training Configuration")
                        
                        base_model_dropdown = gr.Dropdown(
                            choices=["New Model"] + [m[0] for m in available_models],
                            label="Base Model",
                            value="New Model",
                            info="Start from scratch or fine-tune existing model",
                        )
                        
                        num_speakers = gr.Number(
                            label="Number of Speakers",
                            value=1,
                            precision=0,
                            minimum=1,
                            maximum=100,
                        )
                        
                        quality = gr.Radio(
                            choices=["low", "medium", "high"],
                            label="Model Quality",
                            value="medium",
                            info="Higher quality = longer training time",
                        )
                        
                        with gr.Accordion("Training Parameters", open=False):
                            batch_size = gr.Number(
                                label="Batch Size",
                                value=16,
                                precision=0,
                                minimum=1,
                                maximum=64,
                            )
                            
                            learning_rate = gr.Number(
                                label="Learning Rate",
                                value=1e-4,
                                info="Default: 1e-4",
                            )
                            
                            num_epochs = gr.Number(
                                label="Number of Epochs",
                                value=100,
                                precision=0,
                                minimum=1,
                                maximum=1000,
                            )
                            
                            checkpoint_interval = gr.Number(
                                label="Checkpoint Interval (epochs)",
                                value=10,
                                precision=0,
                                minimum=1,
                            )
                            
                            validation_split = gr.Slider(
                                label="Validation Split",
                                minimum=0.05,
                                maximum=0.3,
                                value=0.1,
                                step=0.05,
                            )
                
                with gr.Row():
                    start_training_btn = gr.Button("Start Training", variant="primary")
                    stop_training_btn = gr.Button("Stop Training", variant="stop")
                
                with gr.Row():
                    training_progress = gr.Progress()
                    training_status = gr.Textbox(
                        label="Training Status",
                        value="Not started",
                        interactive=False,
                    )
                
                with gr.Row():
                    loss_plot = gr.LinePlot(
                        label="Training Loss",
                        x="epoch",
                        y="loss",
                        visible=False,
                    )
                    
                    validation_audio = gr.Audio(
                        label="Validation Sample",
                        visible=False,
                    )
        
        # Event handlers
        model_dropdown.change(
            fn=update_templates,
            inputs=[model_dropdown],
            outputs=[template_dropdown],
        )
        
        template_dropdown.change(
            fn=apply_template,
            inputs=[template_dropdown, model_dropdown],
            outputs=[text_input],
        )
        
        reset_btn.click(
            fn=apply_template,
            inputs=[template_dropdown, model_dropdown],
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
        
        validate_btn.click(
            fn=validate_dataset,
            inputs=[dataset_path],
            outputs=[dataset_info],
        ).then(
            lambda: gr.update(visible=True),
            outputs=[dataset_info],
        )
        
        start_training_btn.click(
            fn=start_training,
            inputs=[
                dataset_path,
                base_model_dropdown,
                num_speakers,
                quality,
                batch_size,
                learning_rate,
                num_epochs,
                checkpoint_interval,
                validation_split,
            ],
            outputs=[training_status],
        )
    
    return interface


def main():
    parser = argparse.ArgumentParser(description="Piper TTS WebUI")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("models"),
        help="Directory containing ONNX models",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to run the server on",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Port to run the server on",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Create a public shareable link",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create data directory if it doesn't exist
    args.data_dir.mkdir(parents=True, exist_ok=True)
    
    # Create and launch interface
    interface = create_interface(args.data_dir)
    interface.launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
    )


if __name__ == "__main__":
    main()