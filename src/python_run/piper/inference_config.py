"""Inference configuration for Piper TTS."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class InferenceConfig:
    """Configuration for TTS inference."""

    # Model configuration
    model_path: str | Path
    config_path: str | Path | None = None

    # Voice parameters
    speaker_id: int | None = None

    # Synthesis parameters
    noise_scale: float = 0.667
    length_scale: float = 1.0
    noise_w: float = 0.8

    # Audio parameters
    volume: float = 1.0
    sentence_silence: float = 0.0
    sample_rate: int | None = None  # Auto-detected from model

    # Output configuration
    output_format: str = "wav"  # wav, raw
    output_file: str | Path | None = None
    output_dir: str | Path | None = None

    # Playback
    auto_play: bool = False

    # Hardware acceleration
    use_cuda: bool = False

    # Input configuration
    input_files: list[str | Path] = field(default_factory=list)
    direct_text: str | None = None

    def to_synthesize_args(self) -> dict:
        """Convert to arguments for synthesize methods."""
        return {
            "speaker_id": self.speaker_id,
            "length_scale": self.length_scale,
            "noise_scale": self.noise_scale,
            "noise_w": self.noise_w,
            "sentence_silence": self.sentence_silence,
            "volume": self.volume,
        }

    @classmethod
    def from_args(cls, args) -> "InferenceConfig":
        """Create from argparse arguments."""
        return cls(
            model_path=args.model,
            config_path=args.config,
            speaker_id=args.speaker,
            noise_scale=args.noise_scale or 0.667,
            length_scale=args.length_scale or 1.0,
            noise_w=args.noise_w or 0.8,
            volume=args.volume,
            sentence_silence=args.sentence_silence,
            output_format="raw" if args.output_raw else "wav",
            output_file=args.output_file,
            output_dir=args.output_dir,
            auto_play=args.auto_play,
            use_cuda=args.cuda,
            input_files=args.input_file or [],
            direct_text=args.text,
        )
