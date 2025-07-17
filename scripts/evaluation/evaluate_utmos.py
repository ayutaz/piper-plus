#!/usr/bin/env python3
"""
UTMOS (Unified Text-to-Speech Mean Opinion Score) evaluation tool
Uses a pre-trained model to predict MOS scores automatically
"""

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import torch
import torchaudio
from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# UTMOS model from Hugging Face
UTMOS_MODEL = "sarulab-speech/UTMOS-22k"


class UTMOSEvaluator:
    def __init__(self, device: str | None = None):
        """Initialize UTMOS evaluator with pre-trained model"""
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        logger.info(f"Loading UTMOS model on {self.device}")

        # Load model and feature extractor
        self.model = AutoModelForAudioClassification.from_pretrained(UTMOS_MODEL)
        self.model.to(self.device)
        self.model.eval()

        self.feature_extractor = AutoFeatureExtractor.from_pretrained(UTMOS_MODEL)
        self.target_sr = self.feature_extractor.sampling_rate

    def evaluate_audio(self, audio_path: str) -> dict:
        """Evaluate a single audio file and return MOS score"""
        try:
            # Load audio
            waveform, sample_rate = torchaudio.load(audio_path)

            # Resample if necessary
            if sample_rate != self.target_sr:
                resampler = torchaudio.transforms.Resample(sample_rate, self.target_sr)
                waveform = resampler(waveform)

            # Convert to mono if stereo
            if waveform.shape[0] > 1:
                waveform = torch.mean(waveform, dim=0, keepdim=True)

            # Prepare input
            inputs = self.feature_extractor(
                waveform.squeeze().numpy(),
                sampling_rate=self.target_sr,
                return_tensors="pt",
            )

            # Move to device
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Predict MOS
            with torch.no_grad():
                outputs = self.model(**inputs)
                mos_score = outputs.logits.squeeze().cpu().item()

            return {
                "audio_file": audio_path,
                "mos_score": float(mos_score),
                "status": "success",
            }

        except Exception as e:
            logger.error(f"Error processing {audio_path}: {e}")
            return {
                "audio_file": audio_path,
                "mos_score": None,
                "status": "error",
                "error": str(e),
            }


def evaluate_directory(
    audio_dir: str, output_file: str | None = None, device: str | None = None
) -> dict:
    """Evaluate all audio files in a directory"""
    audio_path = Path(audio_dir)

    # Find all audio files
    audio_files = sorted(
        list(audio_path.glob("*.wav"))
        + list(audio_path.glob("*.mp3"))
        + list(audio_path.glob("*.flac"))
    )

    if not audio_files:
        logger.error(f"No audio files found in {audio_dir}")
        return {"statistics": {"num_samples": 0}, "results": []}

    # Initialize evaluator
    evaluator = UTMOSEvaluator(device=device)

    results = []
    mos_scores = []

    for audio_file in audio_files:
        logger.info(f"Evaluating {audio_file.name}")
        result = evaluator.evaluate_audio(str(audio_file))
        results.append(result)

        if result["status"] == "success":
            mos_scores.append(result["mos_score"])
            logger.info(f"{audio_file.name}: MOS = {result['mos_score']:.3f}")

    # Calculate statistics
    if mos_scores:
        stats = {
            "mean_mos": float(np.mean(mos_scores)),
            "std_mos": float(np.std(mos_scores)),
            "min_mos": float(np.min(mos_scores)),
            "max_mos": float(np.max(mos_scores)),
            "median_mos": float(np.median(mos_scores)),
            "num_samples": len(mos_scores),
        }
    else:
        stats = {"mean_mos": None, "num_samples": 0}

    output = {"statistics": stats, "results": results}

    # Save results
    if output_file:
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)
        logger.info(f"Results saved to {output_file}")

    return output


def compare_models(
    baseline_dir: str,
    test_dir: str,
    output_file: str | None = None,
    device: str | None = None,
) -> dict:
    """Compare MOS scores between baseline and test models"""
    logger.info("Evaluating baseline model outputs...")
    baseline_results = evaluate_directory(baseline_dir, device=device)

    logger.info("Evaluating test model outputs...")
    test_results = evaluate_directory(test_dir, device=device)

    comparison = {
        "baseline": baseline_results["statistics"],
        "test": test_results["statistics"],
    }

    # Calculate improvement
    if (
        baseline_results["statistics"]["mean_mos"] is not None
        and test_results["statistics"]["mean_mos"] is not None
    ):
        improvement = (
            test_results["statistics"]["mean_mos"]
            - baseline_results["statistics"]["mean_mos"]
        )

        comparison["improvement"] = {
            "absolute": float(improvement),
            "percentage": float(
                (improvement / baseline_results["statistics"]["mean_mos"]) * 100
            ),
        }

    if output_file:
        with open(output_file, "w") as f:
            json.dump(comparison, f, indent=2)

    return comparison


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate TTS quality using UTMOS (automatic MOS prediction)"
    )

    # Single directory evaluation
    parser.add_argument(
        "--audio_dir", type=str, help="Directory containing audio files to evaluate"
    )

    # Model comparison
    parser.add_argument(
        "--baseline_dir", type=str, help="Directory with baseline model outputs"
    )
    parser.add_argument(
        "--test_dir", type=str, help="Directory with test model outputs"
    )

    # Output
    parser.add_argument("--output", type=str, help="Output JSON file for results")

    # Device
    parser.add_argument(
        "--device",
        type=str,
        choices=["cuda", "cpu"],
        help="Device to use for evaluation (default: auto)",
    )

    args = parser.parse_args()

    if args.audio_dir:
        # Single directory evaluation
        results = evaluate_directory(args.audio_dir, args.output, device=args.device)

        if results["statistics"]["num_samples"] > 0:
            print("\nUTMOS Evaluation Results:")
            print(f"Mean MOS: {results['statistics']['mean_mos']:.3f}")
            print(f"Std MOS: {results['statistics']['std_mos']:.3f}")
            print(f"Min MOS: {results['statistics']['min_mos']:.3f}")
            print(f"Max MOS: {results['statistics']['max_mos']:.3f}")
            print(f"Median MOS: {results['statistics']['median_mos']:.3f}")
            print(f"Samples: {results['statistics']['num_samples']}")
            print("\nScale: 1.0 (bad) to 5.0 (excellent)")

    elif args.baseline_dir and args.test_dir:
        # Model comparison
        comparison = compare_models(
            args.baseline_dir, args.test_dir, args.output, device=args.device
        )

        print("\nModel Comparison Results:")
        print("\nBaseline Model:")
        if comparison["baseline"]["mean_mos"] is not None:
            print(f"  Mean MOS: {comparison['baseline']['mean_mos']:.3f}")
            print(f"  Samples: {comparison['baseline']['num_samples']}")
        else:
            print("  No valid samples")

        print("\nTest Model:")
        if comparison["test"]["mean_mos"] is not None:
            print(f"  Mean MOS: {comparison['test']['mean_mos']:.3f}")
            print(f"  Samples: {comparison['test']['num_samples']}")
        else:
            print("  No valid samples")

        if "improvement" in comparison:
            print("\nImprovement:")
            print(f"  Absolute: {comparison['improvement']['absolute']:+.3f}")
            print(f"  Percentage: {comparison['improvement']['percentage']:+.1f}%")

    else:
        parser.error(
            "Please provide either --audio_dir for single evaluation, "
            "or --baseline_dir and --test_dir for model comparison"
        )


if __name__ == "__main__":
    main()
