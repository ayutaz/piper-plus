#!/usr/bin/env python3
"""Gradio WebUI for Piper TTS"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Python 3.11+ is required for this module
import gradio as gr
import numpy as np


try:
    from piper import PiperVoice
except ImportError:
    # For testing UI without piper installed
    PiperVoice = None

from .training_manager import training_manager


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
        "weather": "Today's weather forecast shows partly cloudy skies with a high of 72 degrees Fahrenheit. There's a 20% chance of afternoon showers.",
        "podcast": "Welcome to today's episode of Tech Talk, where we explore the latest innovations in artificial intelligence and machine learning.",
        "audiobook": "Chapter One. The morning sun cast long shadows across the cobblestone streets as Sarah made her way to the ancient library.",
        "commercial": "Experience the difference with our premium quality products. Visit our store today and save 20% on your first purchase.",
        "tutorial": "In this tutorial, we'll learn how to create beautiful presentations using simple design principles. Let's begin with the basics.",
    },
    "ja_JP": {
        "greeting": "こんにちは。本日はどのようなご用件でしょうか。お気軽にお申し付けください。",
        "news": "本日のニュースです。人工知能の分野で画期的な発見があり、音声合成技術が大きく進歩しました。",
        "story": "昔々、山に囲まれた小さな村に、好奇心旺盛な若い発明家が住んでいました。",
        "product": "新製品のご紹介です。この革新的なデバイスは、あなたの日常を劇的に変えることでしょう。",
        "assistant": "承知いたしました。そちらの情報についてお手伝いさせていただきます。",
        "weather": "本日の天気予報です。晴れ時々曇り、最高気温は22度、降水確率は20パーセントとなっております。",
        "podcast": "テクノロジートークへようこそ。今回は、最新のAI技術と、それが私たちの生活に与える影響について探っていきます。",
        "audiobook": "第一章。朝の光が石畳の道に長い影を落とす中、さくらは古い図書館へと足を向けていた。",
        "commercial": "品質にこだわった商品を、特別価格でご提供いたします。初回ご購入の方は20パーセント割引となります。",
        "tutorial": "このチュートリアルでは、シンプルなデザイン原則を使って、美しいプレゼンテーションを作成する方法を学びます。",
        "announcement": "お客様各位。本日は定期メンテナンスのため、午後3時から5時まで一部サービスを停止させていただきます。",
        "navigation": "次の交差点を右に曲がってください。目的地まであと500メートルです。到着予定時刻は午後2時30分です。",
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
    "weather": "Weather Report",
    "podcast": "Podcast Intro",
    "audiobook": "Audiobook Narration",
    "commercial": "Commercial",
    "tutorial": "Tutorial",
    "announcement": "Public Announcement",
    "navigation": "Navigation Guide",
}


def get_available_models(data_dir: Path) -> list[tuple[str, str]]:
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
                with open(config_file, encoding="utf-8") as f:
                    config = json.load(f)
                language = config.get("language", {})
                if isinstance(language, dict):
                    lang_code = language.get("code", "en")
                else:
                    lang_code = str(language) if language else "en"

                # Create user-friendly display names
                lang_names = {
                    "ja": "Japanese",
                    "en": "English",
                    "de": "German",
                    "fr": "French",
                    "es": "Spanish",
                    "zh": "Chinese",
                    "ko": "Korean",
                }
                lang_display = lang_names.get(lang_code, lang_code.upper())

                # Extract quality from filename if present
                quality = ""
                if "high" in onnx_file.stem.lower():
                    quality = " (High)"
                elif "medium" in onnx_file.stem.lower():
                    quality = " (Medium)"
                elif "low" in onnx_file.stem.lower():
                    quality = " (Low)"

                display_name = f"{lang_display}{quality} - {onnx_file.stem}"
                models.append((display_name, str(onnx_file)))
            except Exception as e:
                logger.error(f"Error reading config for {onnx_file}: {e}")
                models.append((onnx_file.stem, str(onnx_file)))
        else:
            # No config file, try to guess from filename
            model_name = onnx_file.stem
            if "ja" in model_name.lower():
                display_name = f"Japanese - {model_name}"
            elif "en" in model_name.lower():
                display_name = f"English - {model_name}"
            else:
                display_name = model_name
            models.append((display_name, str(onnx_file)))

    # Sort models by language name for better UX
    models.sort(key=lambda x: x[0])

    return models if models else [("No models found", "")]


def get_language_from_model(model_path: str) -> str:
    """Extract language code from model path or config"""
    if not model_path or model_path == "":
        return "en_US"

    lang_code = None

    # Try to get from config file
    try:
        config_path = Path(model_path).with_suffix(".onnx.json")
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            language = config.get("language", {})
            if isinstance(language, dict):
                lang_code = language.get("code", "en_US")
            else:
                lang_code = str(language)
    except Exception as e:
        logger.error(f"Error getting language from model: {e}")

    # If no lang_code from config, try filename
    if not lang_code:
        model_name = Path(model_path).stem.lower()
        filename_mapping = {
            ("ja", "japanese"): "ja",
            ("de", "german"): "de",
            ("fr", "french"): "fr",
            ("en", "english"): "en",
        }
        for keywords, code in filename_mapping.items():
            if any(kw in model_name for kw in keywords):
                lang_code = code
                break

    # Map language codes to template keys
    if lang_code:
        code_mapping = {
            "ja": "ja_JP",
            "en": "en_US",
            "de": "de_DE",
            "fr": "fr_FR",
        }

        # Direct mapping
        if lang_code in code_mapping:
            return code_mapping[lang_code]

        # Already a template key
        if lang_code in TEMPLATES:
            return lang_code

        # Try prefix matching
        for template_key in TEMPLATES.keys():
            if lang_code.startswith(template_key.split("_")[0]):
                return template_key

    return "en_US"


def update_templates(model_path: str) -> gr.Dropdown:
    """Update template choices based on selected model"""
    language = get_language_from_model(model_path)

    options = ["Custom Text"]
    if language in TEMPLATES:
        options.extend(
            [
                f"{TEMPLATE_DESCRIPTIONS[key]} ({key})"
                for key in TEMPLATES[language].keys()
            ]
        )

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
) -> tuple[int, np.ndarray]:
    """Generate speech from text"""
    if not text.strip():
        raise gr.Error("Please enter some text")

    if not model_path or model_path == "" or not Path(model_path).exists():
        raise gr.Error("Please select a valid model")

    if PiperVoice is None:
        # Return dummy audio for UI testing
        logger.warning("PiperVoice not available, returning dummy audio")
        raise gr.Warning(
            "PiperVoice is not available. Generating synthetic audio for testing purposes."
        )
        sample_rate = 22050
        duration = 2.0  # seconds
        t = np.linspace(0, duration, int(sample_rate * duration))
        audio = np.sin(2 * np.pi * 440 * t) * 0.3  # 440 Hz sine wave
        return sample_rate, (audio * 32767).astype(np.int16)

    try:
        import io
        import wave

        # Load voice
        voice = PiperVoice.load(model_path)

        # Create in-memory WAV file
        wav_buffer = io.BytesIO()

        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(voice.config.sample_rate)

            # Synthesize to WAV
            voice.synthesize(
                text,
                wav_file,
                speaker_id=speaker_id,
                length_scale=length_scale,
                noise_scale=noise_scale,
                noise_w=noise_w,
            )

        # Read audio data from buffer
        wav_buffer.seek(0)
        with wave.open(wav_buffer, "rb") as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16)

        return voice.config.sample_rate, audio
    except Exception as e:
        logger.error(f"Synthesis error: {e}")
        raise gr.Error(f"Synthesis failed: {str(e)}") from e


def validate_dataset(dataset_path: str) -> dict:
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
        with open(metadata_file, encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="|")
            for row in reader:
                if len(row) >= 3:  # speaker|filename|text format
                    speakers.add(row[0])
        stats["speakers"] = list(speakers)
    except Exception as e:
        logger.error(f"Error reading metadata.csv: {e}")

    return stats


def check_training_dependencies():
    """Check if training dependencies are installed"""
    missing_deps = []

    try:
        import importlib.util

        if importlib.util.find_spec("pytorch_lightning") is None:
            missing_deps.append("pytorch-lightning")
    except Exception:
        missing_deps.append("pytorch-lightning")

    try:
        import importlib.util

        if importlib.util.find_spec("torch") is None:
            missing_deps.append("torch")
    except Exception:
        missing_deps.append("torch")

    try:
        # Check if piper_train is accessible
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "piper_train", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and "No module named piper_train" in result.stderr:
            missing_deps.append("piper_train (not in Python path)")
    except Exception:
        missing_deps.append("piper_train (check failed)")

    return missing_deps


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
    output_dir: str = "models/training",
) -> str:
    """Start training process"""
    if not dataset_path or not Path(dataset_path).exists():
        return "❌ Error: Dataset path does not exist"

    # Check dependencies
    missing_deps = check_training_dependencies()
    if missing_deps:
        deps_list = "\n  - ".join(missing_deps)
        return f"❌ Missing training dependencies:\n  - {deps_list}\n\nPlease install them first:\n  cd src/python && pip install -r requirements_train.txt"

    if training_manager.is_running():
        return "⚠️ Training is already running. Please stop the current training first."

    # Start training
    success = training_manager.start_training(
        dataset_path=dataset_path,
        output_dir=output_dir,
        base_model=base_model if base_model != "New Model" else None,
        num_speakers=num_speakers,
        quality=quality,
        batch_size=batch_size,
        learning_rate=learning_rate,
        num_epochs=num_epochs,
        checkpoint_interval=checkpoint_interval,
        validation_split=validation_split,
    )

    if success:
        return "✅ Training started successfully! Check the progress below."
    else:
        error = training_manager.get_status().error
        return f"❌ Failed to start training: {error}"


def stop_training() -> str:
    """Stop current training process"""
    if not training_manager.is_running():
        return "ℹ️ No training is currently running."

    if training_manager.stop_training():
        return "✅ Training stopped successfully."
    else:
        return "❌ Failed to stop training."


def get_training_status() -> dict:
    """Get current training status"""
    status = training_manager.get_status()

    # Calculate progress
    progress = 0.0
    if status.total_epochs > 0:
        progress = status.current_epoch / status.total_epochs

    # Calculate ETA
    eta_text = "N/A"
    if status.is_running and status.start_time and status.current_epoch > 0:
        if status.last_update:
            elapsed = (status.last_update - status.start_time).total_seconds()
        else:
            elapsed = time.time() - status.start_time.timestamp()
        per_epoch = elapsed / status.current_epoch
        remaining_epochs = status.total_epochs - status.current_epoch
        eta_seconds = per_epoch * remaining_epochs
        eta_hours = int(eta_seconds // 3600)
        eta_minutes = int((eta_seconds % 3600) // 60)
        eta_text = f"{eta_hours}h {eta_minutes}m"

    return {
        "is_running": status.is_running,
        "progress": progress,
        "status_text": f"Epoch {status.current_epoch}/{status.total_epochs} | Loss: {status.current_loss:.4f} | ETA: {eta_text}",
        "logs": "\n".join(status.log_messages[-20:]),  # Last 20 log lines
        "error": status.error,
    }


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
                            value=available_models[0][1]
                            if available_models and available_models[0][1]
                            else None,
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

                # Prepare model paths for examples
                # Find English and Japanese models
                en_model_path = ""
                ja_model_path = ""
                for name, path in available_models:
                    if "English" in name and not en_model_path:
                        en_model_path = path
                    elif "Japanese" in name and not ja_model_path:
                        ja_model_path = path

                # Default to first model if specific language not found
                if not en_model_path and available_models:
                    en_model_path = available_models[0][1]
                if not ja_model_path and available_models:
                    ja_model_path = available_models[0][1]

                # Examples
                gr.Examples(
                    examples=[
                        # English examples with English model
                        [
                            "Hello, welcome to Piper text to speech system.",
                            en_model_path,
                            0,
                            1.0,
                            0.667,
                            0.8,
                        ],
                        [
                            "The quick brown fox jumps over the lazy dog.",
                            en_model_path,
                            0,
                            0.8,
                            0.5,
                            0.8,
                        ],
                        [
                            "Good morning! Today's weather is perfect for a walk in the park.",
                            en_model_path,
                            0,
                            1.0,
                            0.667,
                            0.8,
                        ],
                        [
                            "Artificial intelligence is transforming how we interact with technology.",
                            en_model_path,
                            0,
                            0.9,
                            0.7,
                            0.8,
                        ],
                        [
                            "Testing speech synthesis with numbers: 1, 2, 3, 4, 5.",
                            en_model_path,
                            0,
                            1.0,
                            0.667,
                            0.8,
                        ],
                        # Japanese examples with Japanese model
                        [
                            "こんにちは。今日はいい天気ですね。",
                            ja_model_path,
                            0,
                            1.0,
                            0.667,
                            0.8,
                        ],
                        [
                            "人工知能による音声合成のデモンストレーションです。",
                            ja_model_path,
                            0,
                            1.0,
                            0.667,
                            0.8,
                        ],
                        [
                            "明日の会議は午後3時から始まります。よろしくお願いします。",
                            ja_model_path,
                            0,
                            0.9,
                            0.667,
                            0.8,
                        ],
                        [
                            "春の桜は本当に美しいです。日本の四季は素晴らしいですね。",
                            ja_model_path,
                            0,
                            1.1,
                            0.7,
                            0.8,
                        ],
                        [
                            "2024年の技術トレンドについて説明します。",
                            ja_model_path,
                            0,
                            1.0,
                            0.667,
                            0.8,
                        ],
                    ],
                    inputs=[
                        text_input,
                        model_dropdown,
                        speaker_id,
                        length_scale,
                        noise_scale,
                        noise_w,
                    ],
                    label="Example Texts (English & Japanese)",
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

                # Output directory for trained models
                output_dir = gr.Textbox(
                    label="Output Directory",
                    value="models/training",
                    placeholder="Directory to save trained models",
                )

                with gr.Row():
                    start_training_btn = gr.Button("Start Training", variant="primary")
                    stop_training_btn = gr.Button("Stop Training", variant="stop")

                with gr.Row():
                    training_progress = gr.Slider(
                        label="Training Progress",
                        minimum=0,
                        maximum=1,
                        value=0,
                        interactive=False,
                    )
                    training_status = gr.Textbox(
                        label="Training Status",
                        value="Not started",
                        interactive=False,
                    )

                # Training logs
                training_logs = gr.Textbox(
                    label="Training Logs",
                    value="",
                    lines=15,
                    max_lines=20,
                    interactive=False,
                    autoscroll=True,
                )

                # Auto-refresh checkbox
                auto_refresh = gr.Checkbox(
                    label="Auto-refresh logs (every 2 seconds)",
                    value=True,
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

        # Training control handlers
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
                output_dir,
            ],
            outputs=[training_status],
        )

        stop_training_btn.click(
            fn=stop_training,
            outputs=[training_status],
        )

        # Auto-refresh training status
        def refresh_training_ui(should_refresh):
            """Refresh training UI components"""
            if not should_refresh:
                return gr.update(), gr.update(), gr.update()

            status_dict = get_training_status()

            # Update progress bar
            progress_update = gr.update(value=status_dict["progress"])

            # Update status text
            if status_dict["error"]:
                status_text = f"❌ Error: {status_dict['error']}"
            elif status_dict["is_running"]:
                status_text = f"🏃 Running: {status_dict['status_text']}"
            else:
                status_text = "⏹️ Not running"

            status_update = gr.update(value=status_text)

            # Update logs
            logs_update = gr.update(value=status_dict["logs"])

            return progress_update, status_update, logs_update

        # Set up periodic refresh
        # Note: Using a button click loop as Timer might not be available in all Gradio versions
        refresh_btn = gr.Button("Refresh Status", visible=False)
        refresh_btn.click(
            fn=refresh_training_ui,
            inputs=[auto_refresh],
            outputs=[training_progress, training_status, training_logs],
        )

        # Automatic refresh using JavaScript (if supported)
        interface.load(
            fn=None,
            js="""
            () => {
                setInterval(() => {
                    const refreshBtn = document.querySelector('button:contains("Refresh Status")');
                    if (refreshBtn && document.querySelector('input[type="checkbox"][aria-label*="Auto-refresh"]')?.checked) {
                        refreshBtn.click();
                    }
                }, 2000);
            }
            """,
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
