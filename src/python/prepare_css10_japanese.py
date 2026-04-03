#!/usr/bin/env python3
"""
Prepare CSS10 Japanese dataset for piper-plus training with unvoiced vowel support.
"""

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

from tqdm import tqdm


sys.path.append(str(Path(__file__).parent))

from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
from piper_plus_g2p.encode.pua import map_token
from piper_plus_g2p.japanese import JapanesePhonemizer


def get_japanese_id_map():
    return get_phoneme_id_map("ja")


def phonemize_japanese(text):
    p = JapanesePhonemizer()
    tokens = p.phonemize(text)
    return [map_token(t) for t in ["^"] + tokens + ["$"]]


def download_css10_japanese(output_dir: Path):
    """Download CSS10 Japanese dataset."""
    css10_url = "https://github.com/Kyubyong/css10/archive/master.zip"
    print(f"Downloading CSS10 dataset from {css10_url}")

    output_dir.mkdir(parents=True, exist_ok=True)

    download_cmd = ["wget", "-O", str(output_dir / "css10.zip"), css10_url]

    try:
        subprocess.run(download_cmd, check=True)
        print("Download complete. Extracting...")

        extract_cmd = ["unzip", str(output_dir / "css10.zip"), "-d", str(output_dir)]
        subprocess.run(extract_cmd, check=True)

        japanese_dir = output_dir / "css10-master" / "japanese"
        if japanese_dir.exists():
            target_dir = output_dir / "japanese"
            if target_dir.exists():
                import shutil

                shutil.rmtree(target_dir)
            japanese_dir.rename(target_dir)

        os.remove(output_dir / "css10.zip")
        if (output_dir / "css10-master").exists():
            import shutil

            shutil.rmtree(output_dir / "css10-master")

        print(f"CSS10 Japanese data ready at: {output_dir / 'japanese'}")
        return output_dir / "japanese"

    except subprocess.CalledProcessError as e:
        print(f"Error downloading CSS10: {e}")
        return None


def process_transcript_line(line: str) -> tuple[str, str]:
    """Process a line from CSS10 transcript."""
    parts = line.strip().split("|")
    if len(parts) >= 2:
        filename = parts[0]
        transcript = parts[1]
        return filename, transcript
    return None, None


def prepare_dataset(css10_dir: Path, output_dir: Path):
    """
    Prepare CSS10 Japanese dataset for Piper training.
    Always preserves unvoiced vowels for better accuracy.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "wav").mkdir(exist_ok=True)

    transcript_file = css10_dir / "transcript.txt"
    if not transcript_file.exists():
        print(f"Error: Transcript file not found at {transcript_file}")
        return

    dataset = []
    phoneme_stats = {}

    print("Processing transcripts...")

    with open(transcript_file, encoding="utf-8") as f:
        lines = f.readlines()

    # Get phoneme ID mapping
    id_map = get_japanese_id_map()

    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = []
        entries = []

        for line in lines:
            filename, text = process_transcript_line(line)
            if filename and text:
                wav_path = css10_dir / "wav" / f"{filename}.wav"
                if wav_path.exists():
                    entries.append((filename, text, wav_path))
                    future = executor.submit(phonemize_japanese, text)
                    futures.append(future)

        for (filename, text, wav_path), future in tqdm(
            zip(entries, futures, strict=False), total=len(entries)
        ):
            phonemes = future.result()

            if phonemes:
                # Copy wav file
                target_wav = output_dir / "wav" / f"{filename}.wav"
                if not target_wav.exists():
                    import shutil

                    shutil.copy2(wav_path, target_wav)

                # Count phoneme statistics (original phonemes before PUA conversion)
                for p in phonemes:
                    # For PUA characters, find original phoneme
                    if len(p) == 1 and ord(p) >= 0xE000:
                        # This is handled by the mapping
                        pass
                    phoneme_stats[p] = phoneme_stats.get(p, 0) + 1

                # Convert phonemes to IDs
                phoneme_ids = []
                for p in phonemes:
                    if p in id_map:
                        phoneme_ids.extend(id_map[p])
                    else:
                        print(f"Warning: Unknown phoneme '{p}'")
                        phoneme_ids.extend(
                            id_map.get("_", [0])
                        )  # Use pause as fallback

                dataset.append(
                    {
                        "audio_path": f"wav/{filename}.wav",
                        "text": text,
                        "phonemes": phonemes,
                        "phoneme_ids": phoneme_ids,
                    }
                )

    print(f"Processed {len(dataset)} utterances")

    # Write dataset JSON
    dataset_file = output_dir / "dataset.json"
    with open(dataset_file, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    # Write training filelist
    train_file = output_dir / "train.txt"
    val_file = output_dir / "val.txt"

    split_idx = int(len(dataset) * 0.95)

    with open(train_file, "w", encoding="utf-8") as f:
        for entry in dataset[:split_idx]:
            phoneme_str = " ".join(entry["phonemes"])
            f.write(f"{entry['audio_path']}|{phoneme_str}\n")

    with open(val_file, "w", encoding="utf-8") as f:
        for entry in dataset[split_idx:]:
            phoneme_str = " ".join(entry["phonemes"])
            f.write(f"{entry['audio_path']}|{phoneme_str}\n")

    print(f"\nDataset prepared at: {output_dir}")
    print(f"  - Total utterances: {len(dataset)}")
    print(f"  - Training: {split_idx}")
    print(f"  - Validation: {len(dataset) - split_idx}")
    print(f"  - Unique symbols: {len(id_map)}")

    # Show unvoiced vowel statistics
    unvoiced_counts = {}
    voiced_counts = {}

    for p, count in phoneme_stats.items():
        if p in "AIUEO":
            unvoiced_counts[p] = count
        elif p in "aiueo":
            voiced_counts[p] = count

    if unvoiced_counts:
        print("\nUnvoiced vowel statistics:")
        for vowel in sorted(unvoiced_counts.keys()):
            unvoiced = unvoiced_counts.get(vowel, 0)
            voiced = voiced_counts.get(vowel.lower(), 0)
            total = unvoiced + voiced
            percentage = (unvoiced / total * 100) if total > 0 else 0
            print(
                f"  {vowel}: {unvoiced:,} occurrences ({percentage:.1f}% of all '{vowel.lower()}' sounds)"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Prepare CSS10 Japanese dataset for Piper training"
    )
    parser.add_argument(
        "--download", action="store_true", help="Download CSS10 dataset"
    )
    parser.add_argument(
        "--css10-dir", type=Path, help="Path to CSS10 Japanese directory"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("css10_prepared"),
        help="Output directory for processed data",
    )

    args = parser.parse_args()

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

    prepare_dataset(css10_dir, args.output_dir)


if __name__ == "__main__":
    main()
