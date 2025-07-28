import argparse
import logging
import os
import platform
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

from . import PiperVoice
from .download import ensure_voice_exists, find_voice, get_voices
from .inference_config import InferenceConfig


_FILE = Path(__file__)
_DIR = _FILE.parent
_LOGGER = logging.getLogger(_FILE.stem)


def play_audio_file(file_path: str, sample_rate: int = 22050) -> None:
    """Play audio file using platform-specific command."""
    system = platform.system()

    try:
        if system == "Linux":
            # Try multiple Linux audio players
            for cmd in [
                ["aplay", file_path],
                ["play", file_path],
                ["ffplay", "-nodisp", "-autoexit", file_path],
            ]:
                try:
                    subprocess.run(cmd, check=True, capture_output=True)
                    return
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue
            _LOGGER.warning(
                "No audio player found on Linux. Install aplay, sox, or ffmpeg."
            )

        elif system == "Darwin":  # macOS
            subprocess.run(["afplay", file_path], check=True)

        elif system == "Windows":
            # Use Windows Media Player
            subprocess.run(
                [
                    "powershell",
                    "-c",
                    f"(New-Object Media.SoundPlayer '{file_path}').PlaySync()",
                ],
                check=True,
                shell=True,
            )
        else:
            _LOGGER.warning("Unsupported platform for audio playback: %s", system)

    except Exception as e:
        _LOGGER.error("Failed to play audio: %s", e)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "text",
        nargs="?",
        help="Text to synthesize (optional, otherwise reads from stdin or file)",
    )
    parser.add_argument("-m", "--model", required=True, help="Path to Onnx model file")
    parser.add_argument("-c", "--config", help="Path to model config file")
    parser.add_argument(
        "-f",
        "--output-file",
        "--output_file",
        help="Path to output WAV file (default: stdout)",
    )
    parser.add_argument(
        "-d",
        "--output-dir",
        "--output_dir",
        help="Path to output directory (default: cwd)",
    )
    parser.add_argument(
        "--output-raw",
        "--output_raw",
        action="store_true",
        help="Stream raw audio to stdout",
    )
    parser.add_argument("-s", "--speaker", type=int, help="Id of speaker (default: 0)")
    parser.add_argument(
        "--length-scale", "--length_scale", type=float, help="Phoneme length"
    )
    parser.add_argument(
        "--noise-scale", "--noise_scale", type=float, help="Generator noise"
    )
    parser.add_argument(
        "--noise-w", "--noise_w", type=float, help="Phoneme width noise"
    )
    parser.add_argument("--cuda", action="store_true", help="Use GPU")
    parser.add_argument(
        "--sentence-silence",
        "--sentence_silence",
        type=float,
        default=0.0,
        help="Seconds of silence after each sentence",
    )
    parser.add_argument(
        "--data-dir",
        "--data_dir",
        action="append",
        default=[str(Path.cwd())],
        help="Data directory to check for downloaded models (default: current directory)",
    )
    parser.add_argument(
        "--download-dir",
        "--download_dir",
        help="Directory to download voices into (default: first data dir)",
    )
    parser.add_argument(
        "--update-voices",
        action="store_true",
        help="Download latest voices.json during startup",
    )
    parser.add_argument(
        "--volume",
        type=float,
        default=1.0,
        help="Volume multiplier (0.1-2.0, default: 1.0)",
    )
    parser.add_argument(
        "--auto-play",
        action="store_true",
        help="Automatically play audio after generation",
    )
    parser.add_argument(
        "--input-file",
        action="append",
        help="Text file(s) to read (can be used multiple times)",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to console"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    if not args.download_dir:
        # Download to first data directory by default
        args.download_dir = args.data_dir[0]

    # Download voice if file doesn't exist
    model_path = Path(args.model)
    if not model_path.exists():
        # Load voice info
        voices_info = get_voices(args.download_dir, update_voices=args.update_voices)

        # Resolve aliases for backwards compatibility with old voice names
        aliases_info: dict[str, Any] = {}
        for voice_info in voices_info.values():
            for voice_alias in voice_info.get("aliases", []):
                aliases_info[voice_alias] = {"_is_alias": True, **voice_info}

        voices_info.update(aliases_info)
        ensure_voice_exists(args.model, args.data_dir, args.download_dir, voices_info)
        args.model, args.config = find_voice(args.model, args.data_dir)

    # Create inference config
    config = InferenceConfig.from_args(args)

    # Load voice
    voice = PiperVoice.load(
        config.model_path, config_path=config.config_path, use_cuda=config.use_cuda
    )

    # Validate volume range
    if config.volume < 0.1 or config.volume > 2.0:
        _LOGGER.warning(
            "Volume should be between 0.1 and 2.0. Using: %s", config.volume
        )

    synthesize_args = config.to_synthesize_args()

    # Determine input source
    def read_input_lines():
        """Generator that yields input lines from files or stdin."""
        if config.direct_text:
            # Direct text input
            yield config.direct_text
        elif config.input_files:
            # Read from files
            for file_path in config.input_files:
                try:
                    with open(file_path, encoding="utf-8") as f:
                        for line in f:
                            yield line.strip()
                except Exception as e:
                    _LOGGER.error("Failed to read file %s: %s", file_path, e)
        else:
            # Read from stdin
            for line in sys.stdin:
                yield line.strip()

    if config.output_format == "raw":
        # Read line-by-line
        for line in read_input_lines():
            if not line:
                continue

            # Write raw audio to stdout as its produced
            audio_stream = voice.synthesize_stream_raw(line, **synthesize_args)
            for audio_bytes in audio_stream:
                sys.stdout.buffer.write(audio_bytes)
                sys.stdout.buffer.flush()
    elif config.output_dir:
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Read line-by-line
        for line in read_input_lines():
            if not line:
                continue

            wav_path = output_dir / f"{time.monotonic_ns()}.wav"
            with wave.open(str(wav_path), "wb") as wav_file:
                voice.synthesize(line, wav_file, **synthesize_args)

            _LOGGER.info("Wrote %s", wav_path)
    else:
        # Read entire input
        if config.direct_text:
            # Direct text input
            text = config.direct_text
        elif config.input_files:
            # Read all files
            text_parts = []
            for file_path in config.input_files:
                try:
                    with open(file_path, encoding="utf-8") as f:
                        text_parts.append(f.read())
                except Exception as e:
                    _LOGGER.error("Failed to read file %s: %s", file_path, e)
            text = "\n".join(text_parts)
        else:
            # Read from stdin
            text = sys.stdin.read()

        if (not config.output_file) or (config.output_file == "-"):
            # Write to stdout or auto-play
            if config.auto_play:
                # Create temporary file for auto-play
                with tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False
                ) as temp_file:
                    temp_path = temp_file.name

                with wave.open(temp_path, "wb") as wav_file:
                    voice.synthesize(text, wav_file, **synthesize_args)

                _LOGGER.info("Playing audio...")
                play_audio_file(temp_path, voice.config.sample_rate)

                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
            else:
                # Write to stdout
                with wave.open(sys.stdout.buffer, "wb") as wav_file:
                    voice.synthesize(text, wav_file, **synthesize_args)
        else:
            # Write to file
            with wave.open(str(config.output_file), "wb") as wav_file:
                voice.synthesize(text, wav_file, **synthesize_args)

            # Auto-play if requested
            if config.auto_play:
                _LOGGER.info("Playing audio file: %s", config.output_file)
                play_audio_file(str(config.output_file), voice.config.sample_rate)


if __name__ == "__main__":
    main()
