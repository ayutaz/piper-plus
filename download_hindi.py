#!/usr/bin/env python3
"""
download_hindi.py

Downloads and optionally extracts the Hindi subset of IndicVoices-R from Hugging Face:
ai4bharat/indicvoices_r (CC-BY-4.0).

Note: IndicVoices-R is a gated dataset on Hugging Face.
Please visit https://huggingface.co/datasets/ai4bharat/indicvoices_r
to request access, then run `huggingface-cli login` or set HF_TOKEN before running this script.
"""

import argparse
import hashlib
import os
from pathlib import Path
import sys

from huggingface_hub import get_token, snapshot_download


def check_hf_access():
    token = get_token()
    if not token:
        print(
            "WARNING: No Hugging Face token found!\n"
            "IndicVoices-R is a gated dataset. If download fails with a 401/403 error:\n"
            "1. Request access at: https://huggingface.co/datasets/ai4bharat/indicvoices_r\n"
            "2. Run: huggingface-cli login (or set export HF_TOKEN=...)\n",
            file=sys.stderr,
            flush=True,
        )


def extract_parquet_shards(download_dir: Path, output_dir: Path, max_utts: int | None = None):
    try:
        import pyarrow.parquet as pq
    except ImportError:
        print("pyarrow is required to extract parquet shards. Install via pip install pyarrow", file=sys.stderr)
        return

    parquet_files = sorted(download_dir.rglob("*.parquet"))
    if not parquet_files:
        print(f"No .parquet files found in {download_dir}", flush=True)
        return

    wav_dir = output_dir / "wavs"
    wav_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "metadata.tsv"

    print(f"Extracting {len(parquet_files)} parquet shards to {output_dir}...", flush=True)
    extracted_count = 0

    with open(manifest_path, "w", encoding="utf-8") as out_f:
        out_f.write("audio_filepath\ttext\tspeaker_id\n")
        for p_file in parquet_files:
            pf = pq.ParquetFile(p_file)
            schema_names = pf.schema_arrow.names
            text_candidates = ["text", "normalized", "normalized_text", "transcription", "sentence"]
            spk_candidates = ["speaker_id", "speaker", "client_id"]
            audio_candidates = ["audio", "wav", "audio_filepath"]

            text_col = next((c for c in text_candidates if c in schema_names), None)
            spk_col = next((c for c in spk_candidates if c in schema_names), None)
            audio_col = next((c for c in audio_candidates if c in schema_names), None)

            if not text_col or not audio_col:
                continue

            needed_cols = [c for c in [text_col, spk_col, audio_col] if c]
            table = pf.read(columns=needed_cols)
            df = table.to_pydict()

            num_rows = len(df[text_col])
            for i in range(num_rows):
                text = str(df[text_col][i] or "").strip()
                spk = str(df[spk_col][i] if spk_col else "ivr_spk").strip()
                audio_entry = df[audio_col][i]

                if isinstance(audio_entry, dict) and "bytes" in audio_entry:
                    audio_bytes = audio_entry["bytes"]
                    audio_hash = hashlib.md5(f"{p_file.name}_{i}_{text}".encode()).hexdigest()
                    wav_name = f"{audio_hash}.wav"
                    wav_dest = wav_dir / wav_name
                    if not wav_dest.exists():
                        with open(wav_dest, "wb") as wf:
                            wf.write(audio_bytes)
                    out_f.write(f"wavs/{wav_name}\t{text}\t{spk}\n")
                    extracted_count += 1
                elif isinstance(audio_entry, str):
                    out_f.write(f"{audio_entry}\t{text}\t{spk}\n")
                    extracted_count += 1

                if max_utts and extracted_count >= max_utts:
                    break
            if max_utts and extracted_count >= max_utts:
                break

    print(f"Extraction complete! {extracted_count} utterances written to {manifest_path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Download IndicVoices-R Hindi subset.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw-hi-en/indicvoices_r_hi"),
        help="Local target directory",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract audio and transcripts from downloaded Parquet files",
    )
    parser.add_argument(
        "--max-extract",
        type=int,
        default=None,
        help="Max utterances to extract (optional)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=os.environ.get("HF_TOKEN"),
        help="Hugging Face User Access Token (or set HF_TOKEN env var)",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.token:
        check_hf_access()

    print(f"Target directory: {args.output_dir.absolute()}", flush=True)
    print("Downloading Hindi subset from ai4bharat/indicvoices_r...", flush=True)

    downloaded_dir = None
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Download attempt {attempt}/{max_retries}...", flush=True)
            downloaded_dir = snapshot_download(
                repo_id="ai4bharat/indicvoices_r",
                repo_type="dataset",
                allow_patterns=[
                    "Hindi/**",
                    "*Hindi*/**",
                    "*hindi*/**",
                    "README.md",
                ],
                token=args.token,
                local_dir=str(args.output_dir),
            )
            print(f"\nDownload finished successfully! Stored at: {downloaded_dir}", flush=True)
            break
        except Exception as e:
            print(f"\nAttempt {attempt} encountered network error: {e}", file=sys.stderr)
            if attempt < max_retries:
                import time
                wait_s = 5 * attempt
                print(f"Retrying in {wait_s}s (previously downloaded files will be resumed, not re-downloaded)...", flush=True)
                time.sleep(wait_s)
            else:
                print(f"\nAll {max_retries} download attempts failed. Please check internet connection.", file=sys.stderr)
                return

    if downloaded_dir and args.extract:
        extract_parquet_shards(Path(downloaded_dir), Path(downloaded_dir), args.max_extract)


if __name__ == "__main__":
    main()