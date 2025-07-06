#!/usr/bin/env python3
"""
Prepare CSS10 Japanese dataset for Piper TTS training.
This script processes CSS10 Japanese data and creates the necessary files for training.
"""

import os
import json
import csv
import argparse
from pathlib import Path
from typing import List, Dict, Tuple
import subprocess
import concurrent.futures
from tqdm import tqdm

from openjtalk_phonemizer import phonemize_openjtalk, phonemes_to_ids
from jp_phoneme_map import get_phoneme_id_map, create_model_config

def download_css10_japanese(output_dir: Path):
    """
    Download CSS10 Japanese dataset.
    CSS10: A Collection of Single Speaker Speech Datasets for 10 Languages
    """
    css10_url = "https://github.com/Kyubyong/css10/archive/master.zip"
    print(f"Downloading CSS10 dataset from {css10_url}")
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Download command
    download_cmd = [
        "wget", "-O", str(output_dir / "css10.zip"), css10_url
    ]
    
    try:
        subprocess.run(download_cmd, check=True)
        print("Download complete. Extracting...")
        
        # Extract
        extract_cmd = ["unzip", str(output_dir / "css10.zip"), "-d", str(output_dir)]
        subprocess.run(extract_cmd, check=True)
        
        # Move Japanese data
        japanese_dir = output_dir / "css10-master" / "japanese"
        if japanese_dir.exists():
            target_dir = output_dir / "japanese"
            if target_dir.exists():
                import shutil
                shutil.rmtree(target_dir)
            japanese_dir.rename(target_dir)
        
        # Cleanup
        os.remove(output_dir / "css10.zip")
        if (output_dir / "css10-master").exists():
            import shutil
            shutil.rmtree(output_dir / "css10-master")
        
        print(f"CSS10 Japanese data ready at: {output_dir / 'japanese'}")
        return output_dir / "japanese"
        
    except subprocess.CalledProcessError as e:
        print(f"Error downloading CSS10: {e}")
        return None

def process_transcript_line(line: str) -> Tuple[str, str]:
    """
    Process a line from CSS10 transcript.
    Format: filename|transcript
    """
    parts = line.strip().split('|')
    if len(parts) >= 2:
        filename = parts[0]
        transcript = parts[1]
        return filename, transcript
    return None, None

def phonemize_text(text: str, preserve_unvoiced: bool = True) -> List[str]:
    """
    Phonemize text and return flattened list of phonemes.
    """
    try:
        sentences = phonemize_openjtalk(text, preserve_unvoiced=preserve_unvoiced)
        # Flatten sentences and add sentence boundaries
        phonemes = []
        for i, sentence in enumerate(sentences):
            if i > 0:
                phonemes.append("^")  # Sentence boundary
            phonemes.extend(sentence)
        return phonemes
    except Exception as e:
        print(f"Error phonemizing text '{text}': {e}")
        return []

def prepare_dataset(css10_dir: Path, output_dir: Path, preserve_unvoiced: bool = True):
    """
    Prepare CSS10 Japanese dataset for Piper training.
    
    Args:
        css10_dir: Path to CSS10 Japanese directory
        output_dir: Output directory for processed data
        preserve_unvoiced: Whether to preserve unvoiced vowels (uppercase)
    """
    # Create output directories
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "wav").mkdir(exist_ok=True)
    
    # Read transcript
    transcript_file = css10_dir / "transcript.txt"
    if not transcript_file.exists():
        print(f"Error: Transcript file not found at {transcript_file}")
        return
    
    # Process all entries
    dataset = []
    phoneme_stats = {}
    
    print("Processing transcripts...")
    
    with open(transcript_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Use multiprocessing for phonemization
    with concurrent.futures.ProcessPoolExecutor() as executor:
        # Submit all phonemization tasks
        futures = []
        entries = []
        
        for line in lines:
            filename, text = process_transcript_line(line)
            if filename and text:
                wav_path = css10_dir / "wav" / f"{filename}.wav"
                if wav_path.exists():
                    entries.append((filename, text, wav_path))
                    future = executor.submit(phonemize_text, text, preserve_unvoiced)
                    futures.append(future)
        
        # Collect results
        for (filename, text, wav_path), future in tqdm(zip(entries, futures), total=len(entries)):
            phonemes = future.result()
            
            if phonemes:
                # Copy wav file
                target_wav = output_dir / "wav" / f"{filename}.wav"
                if not target_wav.exists():
                    import shutil
                    shutil.copy2(wav_path, target_wav)
                
                # Count phoneme statistics
                for p in phonemes:
                    phoneme_stats[p] = phoneme_stats.get(p, 0) + 1
                
                # Add to dataset
                dataset.append({
                    "audio_path": f"wav/{filename}.wav",
                    "text": text,
                    "phonemes": phonemes,
                    "phoneme_ids": phonemes_to_ids(phonemes)
                })
    
    print(f"Processed {len(dataset)} utterances")
    
    # Write dataset JSON
    dataset_file = output_dir / "dataset.json"
    with open(dataset_file, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    
    # Write phoneme statistics
    stats_file = output_dir / "phoneme_stats.json"
    phoneme_stats_sorted = dict(sorted(phoneme_stats.items(), key=lambda x: x[1], reverse=True))
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(phoneme_stats_sorted, f, ensure_ascii=False, indent=2)
    
    # Create model config
    config = create_model_config("ja_JP-css10-openjtalk")
    config["dataset"] = "css10_japanese"
    config["audio"]["quality"] = "high"
    
    config_file = output_dir / "config.json"
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    # Write training filelist
    train_file = output_dir / "train.txt"
    val_file = output_dir / "val.txt"
    
    # Split 95% train, 5% validation
    split_idx = int(len(dataset) * 0.95)
    
    with open(train_file, 'w', encoding='utf-8') as f:
        for entry in dataset[:split_idx]:
            f.write(f"{entry['audio_path']}|{' '.join(entry['phonemes'])}\n")
    
    with open(val_file, 'w', encoding='utf-8') as f:
        for entry in dataset[split_idx:]:
            f.write(f"{entry['audio_path']}|{' '.join(entry['phonemes'])}\n")
    
    print(f"\nDataset prepared at: {output_dir}")
    print(f"  - Total utterances: {len(dataset)}")
    print(f"  - Training: {split_idx}")
    print(f"  - Validation: {len(dataset) - split_idx}")
    print(f"  - Unique phonemes: {len(phoneme_stats)}")
    
    # Show unvoiced vowel statistics
    unvoiced_stats = {p: count for p, count in phoneme_stats.items() if p in 'AIUEO'}
    if unvoiced_stats:
        print("\nUnvoiced vowel statistics:")
        for vowel, count in sorted(unvoiced_stats.items()):
            total_vowel = phoneme_stats.get(vowel.lower(), 0) + count
            percentage = (count / total_vowel * 100) if total_vowel > 0 else 0
            print(f"  {vowel}: {count:,} occurrences ({percentage:.1f}% of all '{vowel.lower()}' sounds)")

def main():
    parser = argparse.ArgumentParser(description="Prepare CSS10 Japanese dataset for Piper training")
    parser.add_argument("--download", action="store_true", help="Download CSS10 dataset")
    parser.add_argument("--css10-dir", type=Path, help="Path to CSS10 Japanese directory")
    parser.add_argument("--output-dir", type=Path, default=Path("css10_prepared"), 
                       help="Output directory for processed data")
    parser.add_argument("--no-preserve-unvoiced", action="store_true",
                       help="Convert unvoiced vowels to lowercase")
    
    args = parser.parse_args()
    
    # Download if requested
    if args.download:
        css10_dir = download_css10_japanese(Path("css10_data"))
        if not css10_dir:
            print("Failed to download CSS10 dataset")
            return
    else:
        css10_dir = args.css10_dir
        if not css10_dir or not css10_dir.exists():
            print("Please specify --css10-dir or use --download")
            return
    
    # Prepare dataset
    prepare_dataset(
        css10_dir,
        args.output_dir,
        preserve_unvoiced=not args.no_preserve_unvoiced
    )

if __name__ == "__main__":
    main()