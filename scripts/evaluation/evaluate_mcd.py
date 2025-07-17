#!/usr/bin/env python3
"""
Mel-Cepstral Distortion (MCD) evaluation tool for TTS
Compares synthesized speech with reference speech
"""

import argparse
import json
import logging
from pathlib import Path

import librosa
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_mfcc(audio_path: str, sr: int = 22050, n_mfcc: int = 13) -> np.ndarray:
    """Extract MFCC features from audio file"""
    # Load audio
    y, orig_sr = librosa.load(audio_path, sr=None)

    # Resample if necessary
    if orig_sr != sr:
        y = librosa.resample(y, orig_sr=orig_sr, target_sr=sr)

    # Extract MFCC
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)

    return mfcc.T  # Transpose to (time, features)


def align_features(feat1: np.ndarray, feat2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Align two feature sequences using DTW"""
    from dtw import dtw
    from scipy.spatial.distance import cdist

    # Calculate distance matrix
    dist_matrix = cdist(feat1, feat2, metric='euclidean')

    # Perform DTW
    alignment = dtw(dist_matrix)

    # Get aligned indices
    path = np.array(alignment.path)

    # Return aligned features
    aligned_feat1 = feat1[path[:, 0]]
    aligned_feat2 = feat2[path[:, 1]]

    return aligned_feat1, aligned_feat2


def calculate_mcd(ref_features: np.ndarray, synth_features: np.ndarray) -> float:
    """Calculate MCD between reference and synthesized features"""
    # Align features
    ref_aligned, synth_aligned = align_features(ref_features, synth_features)

    # Calculate MCD
    diff = ref_aligned - synth_aligned
    squared_diff = diff ** 2
    sum_squared_diff = np.sum(squared_diff, axis=1)

    # MCD formula: (10 / ln(10)) * sqrt(2 * sum(squared_differences))
    mcd = (10.0 / np.log(10.0)) * np.sqrt(2.0 * np.mean(sum_squared_diff))

    return mcd


def evaluate_file_pair(ref_path: str, synth_path: str,
                      sr: int = 22050, n_mfcc: int = 13) -> dict:
    """Evaluate MCD between a reference and synthesized audio file"""
    try:
        # Extract features
        ref_mfcc = extract_mfcc(ref_path, sr=sr, n_mfcc=n_mfcc)
        synth_mfcc = extract_mfcc(synth_path, sr=sr, n_mfcc=n_mfcc)

        # Calculate MCD
        mcd = calculate_mcd(ref_mfcc, synth_mfcc)

        return {
            "reference": ref_path,
            "synthesized": synth_path,
            "mcd": float(mcd),
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Error processing {ref_path} and {synth_path}: {e}")
        return {
            "reference": ref_path,
            "synthesized": synth_path,
            "mcd": None,
            "status": "error",
            "error": str(e)
        }


def evaluate_directory(ref_dir: str, synth_dir: str,
                      output_file: str | None = None,
                      sr: int = 22050, n_mfcc: int = 13) -> dict:
    """Evaluate MCD for all matching files in directories"""
    ref_path = Path(ref_dir)
    synth_path = Path(synth_dir)

    # Find all audio files
    ref_files = sorted(list(ref_path.glob("*.wav")) + list(ref_path.glob("*.mp3")))

    results = []
    mcd_values = []

    for ref_file in ref_files:
        # Find corresponding synthesized file
        synth_file = synth_path / ref_file.name

        if not synth_file.exists():
            logger.warning(f"No synthesized file found for {ref_file.name}")
            continue

        # Evaluate
        result = evaluate_file_pair(
            str(ref_file),
            str(synth_file),
            sr=sr,
            n_mfcc=n_mfcc
        )

        results.append(result)

        if result["status"] == "success":
            mcd_values.append(result["mcd"])
            logger.info(f"{ref_file.name}: MCD = {result['mcd']:.2f}")

    # Calculate statistics
    if mcd_values:
        stats = {
            "mean_mcd": float(np.mean(mcd_values)),
            "std_mcd": float(np.std(mcd_values)),
            "min_mcd": float(np.min(mcd_values)),
            "max_mcd": float(np.max(mcd_values)),
            "median_mcd": float(np.median(mcd_values)),
            "num_samples": len(mcd_values)
        }
    else:
        stats = {
            "mean_mcd": None,
            "num_samples": 0
        }

    output = {
        "statistics": stats,
        "results": results
    }

    # Save results
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        logger.info(f"Results saved to {output_file}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Calculate MCD between reference and synthesized speech")

    # Single file evaluation
    parser.add_argument("--reference", type=str, help="Reference audio file")
    parser.add_argument("--synthesized", type=str, help="Synthesized audio file")

    # Directory evaluation
    parser.add_argument("--reference_dir", type=str, help="Directory containing reference audio files")
    parser.add_argument("--synthesized_dir", type=str, help="Directory containing synthesized audio files")

    # Output
    parser.add_argument("--output", type=str, help="Output JSON file for results")

    # Parameters
    parser.add_argument("--sample_rate", type=int, default=22050, help="Sample rate for audio (default: 22050)")
    parser.add_argument("--n_mfcc", type=int, default=13, help="Number of MFCC coefficients (default: 13)")

    args = parser.parse_args()

    # Validate arguments
    if args.reference and args.synthesized:
        # Single file evaluation
        result = evaluate_file_pair(
            args.reference,
            args.synthesized,
            sr=args.sample_rate,
            n_mfcc=args.n_mfcc
        )

        if result["status"] == "success":
            print(f"MCD: {result['mcd']:.2f}")
        else:
            print(f"Error: {result['error']}")

        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)

    elif args.reference_dir and args.synthesized_dir:
        # Directory evaluation
        results = evaluate_directory(
            args.reference_dir,
            args.synthesized_dir,
            output_file=args.output,
            sr=args.sample_rate,
            n_mfcc=args.n_mfcc
        )

        if results["statistics"]["num_samples"] > 0:
            print("\nOverall Statistics:")
            print(f"Mean MCD: {results['statistics']['mean_mcd']:.2f}")
            print(f"Std MCD: {results['statistics']['std_mcd']:.2f}")
            print(f"Min MCD: {results['statistics']['min_mcd']:.2f}")
            print(f"Max MCD: {results['statistics']['max_mcd']:.2f}")
            print(f"Median MCD: {results['statistics']['median_mcd']:.2f}")
            print(f"Samples: {results['statistics']['num_samples']}")
        else:
            print("No valid samples found for evaluation")

    else:
        parser.error("Please provide either --reference and --synthesized for single file evaluation, "
                    "or --reference_dir and --synthesized_dir for directory evaluation")


if __name__ == "__main__":
    main()

