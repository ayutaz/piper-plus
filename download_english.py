#!/usr/bin/env python3
"""
download_english.py

Downloads and extracts the train-clean-100 subset of LibriTTS-R from OpenSLR 141
(CC-BY-4.0 license, restored speech, ~54 hours, clean multi-speaker English).

URL: https://www.openslr.org/resources/141/train_clean_100.tar.gz (~8.1 GB)
"""

import argparse
import concurrent.futures
import os
from pathlib import Path
import sys
import tarfile
import time
import urllib.request
import urllib.error

OPENSLR_URL = "https://www.openslr.org/resources/141/train_clean_100.tar.gz"


def get_remote_file_size(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return int(resp.headers.get("Content-Length", 0))


def download_chunk(url: str, start: int, end: int, part_path: Path, max_retries: int = 5):
    """Downloads a byte range [start, end] into part_path with retries."""
    for attempt in range(1, max_retries + 1):
        try:
            cur_size = part_path.stat().st_size if part_path.exists() else 0
            chunk_start = start + cur_size
            if chunk_start > end:
                return  # already complete

            req = urllib.request.Request(
                url,
                headers={"Range": f"bytes={chunk_start}-{end}"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp, open(part_path, "ab") as f:
                while True:
                    buf = resp.read(1024 * 1024)  # 1MB
                    if not buf:
                        break
                    f.write(buf)
            return
        except Exception as e:
            if attempt == max_retries:
                raise RuntimeError(f"Failed to download chunk {start}-{end} after {max_retries} attempts: {e}")
            time.sleep(2 * attempt)


def download_file_parallel(url: str, dest_path: Path, num_connections: int = 4):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    total_size = get_remote_file_size(url)
    if not total_size:
        raise RuntimeError("Could not determine remote file size from OpenSLR.")

    print(f"File size: {total_size / (1024**3):.2f} GB ({total_size} bytes)", flush=True)

    if dest_path.exists() and dest_path.stat().st_size == total_size:
        print(f"Archive already downloaded and complete at {dest_path}", flush=True)
        return

    chunk_size = total_size // num_connections
    chunks = []
    part_files = []

    for i in range(num_connections):
        start = i * chunk_size
        end = (start + chunk_size - 1) if i < num_connections - 1 else total_size - 1
        part_file = dest_path.with_name(f"{dest_path.name}.part{i}")
        chunks.append((start, end, part_file))
        part_files.append(part_file)

    print(f"Downloading in {num_connections} parallel streams to maximize throughput...", flush=True)
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_connections) as executor:
        futures = {
            executor.submit(download_chunk, url, start, end, part_file): i
            for i, (start, end, part_file) in enumerate(chunks)
        }

        while any(not f.done() for f in futures):
            downloaded = sum(p.stat().st_size for p in part_files if p.exists())
            elapsed = time.time() - start_time
            speed = (downloaded / (1024 * 1024)) / max(elapsed, 0.1)
            pct = (downloaded / total_size) * 100.0
            print(
                f"\rProgress: {downloaded / (1024**3):.2f}/{total_size / (1024**3):.2f} GB ({pct:.1f}%) "
                f"| Speed: {speed:.1f} MB/s",
                end="",
                flush=True,
            )
            time.sleep(1)

        # Ensure all finished without error
        for f in concurrent.futures.as_completed(futures):
            f.result()

    print(f"\nDownload streams finished. Assembling into {dest_path.name}...", flush=True)
    with open(dest_path, "wb") as out_f:
        for part_file in part_files:
            with open(part_file, "rb") as in_f:
                while True:
                    buf = in_f.read(16 * 1024 * 1024)
                    if not buf:
                        break
                    out_f.write(buf)
            part_file.unlink()

    print(f"Assembly complete! Verified size: {dest_path.stat().st_size} bytes.", flush=True)


def extract_tar_gz(archive_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Extracting {archive_path.name} to {output_dir}...", flush=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(path=output_dir)
    print(f"Extraction finished successfully! Stored at {output_dir}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Download and extract LibriTTS-R English train-clean-100 subset.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw-hi-en/libritts_r_en"),
        help="Target directory for extracted dataset",
    )
    parser.add_argument(
        "--connections",
        type=int,
        default=4,
        help="Number of parallel download connections (default: 4)",
    )
    parser.add_argument(
        "--keep-archive",
        action="store_true",
        help="Keep the downloaded .tar.gz archive after extraction",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = args.output_dir / "train_clean_100.tar.gz"

    print(f"Target directory: {args.output_dir.resolve()}", flush=True)
    print("Downloading LibriTTS-R train-clean-100 (OpenSLR 141, CC-BY-4.0)...", flush=True)
    download_file_parallel(OPENSLR_URL, archive_path, num_connections=args.connections)

    extract_tar_gz(archive_path, args.output_dir)

    if not args.keep_archive and archive_path.exists():
        print(f"Removing archive {archive_path.name} to save disk space...", flush=True)
        archive_path.unlink()

    # Count extracted samples
    num_txts = len(list(args.output_dir.rglob("*.normalized.txt")))
    print(f"\nVerification: Found {num_txts} *.normalized.txt files ready for preprocessing.", flush=True)


if __name__ == "__main__":
    main()
