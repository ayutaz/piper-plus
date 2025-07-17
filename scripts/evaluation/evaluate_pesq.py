#!/usr/bin/env python3
"""
PESQ (Perceptual Evaluation of Speech Quality) evaluation tool for TTS
Compares synthesized speech with reference speech using ITU-T P.862 standard
"""

import argparse
import numpy as np
from pathlib import Path
import json
from typing import Optional
import logging
from pesq import pesq
import librosa
import soundfile as sf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def evaluate_pesq(ref_path: str, synth_path: str, mode: str = 'wb') -> dict:
    """
    Evaluate PESQ between reference and synthesized audio
    
    Args:
        ref_path: Path to reference audio
        synth_path: Path to synthesized audio
        mode: 'wb' for wideband (16kHz) or 'nb' for narrowband (8kHz)
    
    Returns:
        Dictionary with PESQ score and metadata
    """
    try:
        # Set sample rate based on mode
        if mode == 'wb':
            target_sr = 16000
        else:  # nb
            target_sr = 8000
        
        # Load reference audio
        ref_audio, ref_sr = librosa.load(ref_path, sr=None)
        if ref_sr != target_sr:
            ref_audio = librosa.resample(ref_audio, orig_sr=ref_sr, target_sr=target_sr)
        
        # Load synthesized audio
        synth_audio, synth_sr = librosa.load(synth_path, sr=None)
        if synth_sr != target_sr:
            synth_audio = librosa.resample(synth_audio, orig_sr=synth_sr, target_sr=target_sr)
        
        # Ensure same length
        min_len = min(len(ref_audio), len(synth_audio))
        ref_audio = ref_audio[:min_len]
        synth_audio = synth_audio[:min_len]
        
        # Calculate PESQ
        pesq_score = pesq(target_sr, ref_audio, synth_audio, mode)
        
        return {
            "reference": ref_path,
            "synthesized": synth_path,
            "pesq_score": float(pesq_score),
            "mode": mode,
            "sample_rate": target_sr,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"Error processing {ref_path} and {synth_path}: {e}")
        return {
            "reference": ref_path,
            "synthesized": synth_path,
            "pesq_score": None,
            "status": "error",
            "error": str(e)
        }


def evaluate_directory(ref_dir: str, synth_dir: str, 
                      output_file: Optional[str] = None,
                      mode: str = 'wb') -> dict:
    """Evaluate PESQ for all matching files in directories"""
    ref_path = Path(ref_dir)
    synth_path = Path(synth_dir)
    
    # Find all audio files
    ref_files = sorted(list(ref_path.glob("*.wav")) + list(ref_path.glob("*.mp3")))
    
    results = []
    pesq_scores = []
    
    for ref_file in ref_files:
        # Find corresponding synthesized file
        synth_file = synth_path / ref_file.name
        
        if not synth_file.exists():
            logger.warning(f"No synthesized file found for {ref_file.name}")
            continue
        
        # Evaluate
        result = evaluate_pesq(str(ref_file), str(synth_file), mode=mode)
        results.append(result)
        
        if result["status"] == "success":
            pesq_scores.append(result["pesq_score"])
            logger.info(f"{ref_file.name}: PESQ = {result['pesq_score']:.3f}")
    
    # Calculate statistics
    if pesq_scores:
        stats = {
            "mean_pesq": float(np.mean(pesq_scores)),
            "std_pesq": float(np.std(pesq_scores)),
            "min_pesq": float(np.min(pesq_scores)),
            "max_pesq": float(np.max(pesq_scores)),
            "median_pesq": float(np.median(pesq_scores)),
            "num_samples": len(pesq_scores),
            "mode": mode
        }
    else:
        stats = {
            "mean_pesq": None,
            "num_samples": 0,
            "mode": mode
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
    parser = argparse.ArgumentParser(description="Calculate PESQ between reference and synthesized speech")
    
    # Single file evaluation
    parser.add_argument("--reference", type=str, help="Reference audio file")
    parser.add_argument("--synthesized", type=str, help="Synthesized audio file")
    
    # Directory evaluation
    parser.add_argument("--reference_dir", type=str, help="Directory containing reference audio files")
    parser.add_argument("--synthesized_dir", type=str, help="Directory containing synthesized audio files")
    
    # Output
    parser.add_argument("--output", type=str, help="Output JSON file for results")
    
    # Parameters
    parser.add_argument("--mode", type=str, default="wb", choices=["wb", "nb"],
                        help="PESQ mode: 'wb' for wideband (16kHz), 'nb' for narrowband (8kHz)")
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.reference and args.synthesized:
        # Single file evaluation
        result = evaluate_pesq(args.reference, args.synthesized, mode=args.mode)
        
        if result["status"] == "success":
            print(f"PESQ Score: {result['pesq_score']:.3f} ({args.mode})")
            print(f"Scale: 1.0 (bad) to 4.5 (excellent)")
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
            mode=args.mode
        )
        
        if results["statistics"]["num_samples"] > 0:
            print(f"\nOverall PESQ Statistics ({args.mode}):")
            print(f"Mean PESQ: {results['statistics']['mean_pesq']:.3f}")
            print(f"Std PESQ: {results['statistics']['std_pesq']:.3f}")
            print(f"Min PESQ: {results['statistics']['min_pesq']:.3f}")
            print(f"Max PESQ: {results['statistics']['max_pesq']:.3f}")
            print(f"Median PESQ: {results['statistics']['median_pesq']:.3f}")
            print(f"Samples: {results['statistics']['num_samples']}")
            print(f"\nScale: 1.0 (bad) to 4.5 (excellent)")
        else:
            print("No valid samples found for evaluation")
    
    else:
        parser.error("Please provide either --reference and --synthesized for single file evaluation, "
                    "or --reference_dir and --synthesized_dir for directory evaluation")


if __name__ == "__main__":
    main()