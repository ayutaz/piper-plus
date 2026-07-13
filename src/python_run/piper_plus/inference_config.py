"""Inference configuration for piper-plus."""

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
    speaker_embedding: list[float] | None = None

    # Synthesis parameters
    noise_scale: float = 0.4
    length_scale: float = 1.0
    noise_w: float = 0.5

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
        import numpy as np

        args: dict = {
            "speaker_id": self.speaker_id,
            "length_scale": self.length_scale,
            "noise_scale": self.noise_scale,
            "noise_w": self.noise_w,
            "sentence_silence": self.sentence_silence,
            "volume": self.volume,
        }
        if self.speaker_embedding is not None:
            args["speaker_embedding"] = np.array(
                self.speaker_embedding, dtype=np.float32
            )
        return args

    @classmethod
    def from_args(cls, args) -> "InferenceConfig":
        """Create from argparse arguments."""
        # Load speaker embedding from file if --speaker-embedding was given
        speaker_embedding: list[float] | None = None
        speaker_embedding_path = getattr(args, "speaker_embedding", None)
        if speaker_embedding_path is not None:
            import numpy as np

            raw = np.load(speaker_embedding_path)
            speaker_embedding = raw.flatten().tolist()

        return cls(
            model_path=args.model,
            config_path=args.config,
            speaker_id=args.speaker,
            noise_scale=args.noise_scale if args.noise_scale is not None else 0.4,
            length_scale=args.length_scale if args.length_scale is not None else 1.0,
            noise_w=args.noise_w if args.noise_w is not None else 0.5,
            volume=args.volume,
            sentence_silence=args.sentence_silence,
            output_format="raw" if args.output_raw else "wav",
            output_file=args.output_file,
            output_dir=args.output_dir,
            auto_play=args.auto_play,
            use_cuda=args.cuda,
            input_files=args.input_file or [],
            direct_text=args.text,
            speaker_embedding=speaker_embedding,
        )
