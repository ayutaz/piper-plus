#!/usr/bin/env python3
"""
Organize and prepare audio artifacts for GitHub Actions upload.
This script organizes generated audio files into a structured format
and creates metadata for easier browsing.
"""

import argparse
import json
import os
import shutil
import wave
from pathlib import Path
from typing import Dict, List, Tuple


def get_audio_info(wav_path: Path) -> Dict[str, any]:
    """Extract information from a WAV file."""
    try:
        with wave.open(str(wav_path), 'rb') as wav:
            return {
                "duration_seconds": wav.getnframes() / wav.getframerate(),
                "sample_rate": wav.getframerate(),
                "channels": wav.getnchannels(),
                "file_size_kb": wav_path.stat().st_size / 1024
            }
    except Exception as e:
        return {"error": str(e)}


def categorize_audio_files(audio_files: List[Path]) -> Dict[str, List[Path]]:
    """Categorize audio files by type and language."""
    categories = {
        "japanese_basic": [],
        "japanese_comprehensive": [],
        "multilingual": [],
        "performance_tests": [],
        "special_tests": [],
        "other": []
    }
    
    for audio_file in audio_files:
        name = audio_file.name.lower()
        
        if "basic_" in name and any(jp in name for jp in ["hiragana", "katakana", "kanji", "mixed"]):
            categories["japanese_basic"].append(audio_file)
        elif "comprehensive_" in name:
            categories["japanese_comprehensive"].append(audio_file)
        elif "_basic.wav" in name and len(name.split("_")[0]) == 2:  # Language code pattern
            categories["multilingual"].append(audio_file)
        elif "performance" in name or "test_performance" in name:
            categories["performance_tests"].append(audio_file)
        elif "special" in name or "test_special" in name:
            categories["special_tests"].append(audio_file)
        else:
            categories["other"].append(audio_file)
    
    # Remove empty categories
    return {k: v for k, v in categories.items() if v}


def create_artifact_structure(results_dir: Path, output_dir: Path) -> Dict[str, any]:
    """Create organized structure for audio artifacts."""
    # Find all audio files
    audio_files = list(results_dir.glob("*.wav"))
    
    if not audio_files:
        return {"status": "no_audio_files", "count": 0}
    
    # Categorize files
    categories = categorize_audio_files(audio_files)
    
    # Create output structure
    output_dir.mkdir(parents=True, exist_ok=True)
    
    metadata = {
        "total_files": len(audio_files),
        "categories": {},
        "samples": {}
    }
    
    # Copy files to organized structure
    for category, files in categories.items():
        if not files:
            continue
            
        category_dir = output_dir / category
        category_dir.mkdir(exist_ok=True)
        
        metadata["categories"][category] = {
            "count": len(files),
            "files": []
        }
        
        for audio_file in files:
            # Copy file
            dest_path = category_dir / audio_file.name
            shutil.copy2(audio_file, dest_path)
            
            # Get audio info
            info = get_audio_info(audio_file)
            
            file_metadata = {
                "filename": audio_file.name,
                "category": category,
                "size_kb": round(info.get("file_size_kb", 0), 1),
                "duration_seconds": round(info.get("duration_seconds", 0), 2)
            }
            
            metadata["categories"][category]["files"].append(file_metadata)
            
            # Select representative samples (first file from each major category)
            if category not in metadata["samples"] and info.get("duration_seconds", 0) > 0:
                metadata["samples"][category] = file_metadata
    
    # Create index.json
    index_path = output_dir / "index.json"
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    # Create README for artifact browsing
    create_artifact_readme(output_dir, metadata)
    
    return metadata


def create_artifact_readme(output_dir: Path, metadata: Dict[str, any]):
    """Create README.md for easier artifact browsing."""
    readme_lines = []
    
    readme_lines.append("# TTS Audio Test Artifacts")
    readme_lines.append("")
    readme_lines.append(f"Total audio files: **{metadata['total_files']}**")
    readme_lines.append("")
    
    # Category descriptions
    category_descriptions = {
        "japanese_basic": "Basic Japanese TTS tests (hiragana, katakana, kanji)",
        "japanese_comprehensive": "Comprehensive Japanese tests (long text, punctuation, etc.)",
        "multilingual": "Multilingual TTS tests across different languages",
        "performance_tests": "Performance and stress test outputs",
        "special_tests": "Special character and edge case tests",
        "other": "Other test outputs"
    }
    
    # List categories
    readme_lines.append("## Categories")
    readme_lines.append("")
    
    for category, data in metadata["categories"].items():
        desc = category_descriptions.get(category, category.replace("_", " ").title())
        readme_lines.append(f"### {desc}")
        readme_lines.append(f"- Files: {data['count']}")
        
        # Add sample duration info
        total_duration = sum(f.get("duration_seconds", 0) for f in data["files"])
        if total_duration > 0:
            readme_lines.append(f"- Total duration: {total_duration:.1f} seconds")
        
        readme_lines.append("")
        
        # List files in this category
        readme_lines.append("<details>")
        readme_lines.append("<summary>Files in this category</summary>")
        readme_lines.append("")
        readme_lines.append("| File | Duration | Size |")
        readme_lines.append("|------|----------|------|")
        
        for file_info in sorted(data["files"], key=lambda x: x["filename"]):
            name = file_info["filename"]
            duration = file_info.get("duration_seconds", 0)
            size = file_info.get("size_kb", 0)
            readme_lines.append(f"| {name} | {duration:.1f}s | {size:.1f}KB |")
        
        readme_lines.append("")
        readme_lines.append("</details>")
        readme_lines.append("")
    
    # Representative samples
    if metadata.get("samples"):
        readme_lines.append("## Representative Samples")
        readme_lines.append("")
        readme_lines.append("One sample from each category for quick testing:")
        readme_lines.append("")
        
        for category, sample in metadata["samples"].items():
            desc = category_descriptions.get(category, category.replace("_", " ").title())
            readme_lines.append(f"- **{desc}**: `{sample['filename']}` ({sample['duration_seconds']:.1f}s)")
        
        readme_lines.append("")
    
    # Usage instructions
    readme_lines.append("## Usage")
    readme_lines.append("")
    readme_lines.append("1. Download the artifact archive from GitHub Actions")
    readme_lines.append("2. Extract the archive")
    readme_lines.append("3. Navigate to the category folder of interest")
    readme_lines.append("4. Play the WAV files with any audio player")
    readme_lines.append("")
    
    # Write README
    readme_path = output_dir / "README.md"
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(readme_lines))


def create_sample_subset(output_dir: Path, metadata: Dict[str, any], max_files: int = 10):
    """Create a subset of representative samples for quick download."""
    samples_dir = output_dir / "samples"
    samples_dir.mkdir(exist_ok=True)
    
    selected_files = []
    
    # Select files from each category
    for category, data in metadata["categories"].items():
        # Take up to 2 files from each category
        category_files = data["files"][:2]
        for file_info in category_files:
            if len(selected_files) >= max_files:
                break
            
            src_path = output_dir / category / file_info["filename"]
            if src_path.exists():
                dest_path = samples_dir / file_info["filename"]
                shutil.copy2(src_path, dest_path)
                selected_files.append(file_info)
    
    # Create samples metadata
    samples_metadata = {
        "description": "Representative samples from each test category",
        "total_files": len(selected_files),
        "files": selected_files
    }
    
    with open(samples_dir / "samples.json", 'w', encoding='utf-8') as f:
        json.dump(samples_metadata, f, indent=2)
    
    return len(selected_files)


def main():
    parser = argparse.ArgumentParser(description="Organize audio artifacts for GitHub Actions")
    parser.add_argument("--results-dir", default="test_results",
                       help="Directory containing test results")
    parser.add_argument("--output-dir", default="audio_artifacts",
                       help="Output directory for organized artifacts")
    parser.add_argument("--create-samples", action="store_true",
                       help="Create a subset of sample files")
    parser.add_argument("--max-samples", type=int, default=10,
                       help="Maximum number of sample files to include")
    
    args = parser.parse_args()
    
    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)
    
    if not results_dir.exists():
        print(f"Error: Results directory {results_dir} does not exist")
        return 1
    
    # Clean output directory
    if output_dir.exists():
        shutil.rmtree(output_dir)
    
    # Create artifact structure
    print(f"Organizing audio files from {results_dir}...")
    metadata = create_artifact_structure(results_dir, output_dir)
    
    if metadata.get("status") == "no_audio_files":
        print("No audio files found to organize")
        return 0
    
    print(f"Organized {metadata['total_files']} audio files into {len(metadata['categories'])} categories")
    
    # Create sample subset if requested
    if args.create_samples:
        sample_count = create_sample_subset(output_dir, metadata, args.max_samples)
        print(f"Created sample subset with {sample_count} files")
    
    # Print summary
    print("\nCategory summary:")
    for category, data in metadata["categories"].items():
        print(f"  - {category}: {data['count']} files")
    
    print(f"\nArtifacts organized in: {output_dir.absolute()}")
    
    return 0


if __name__ == "__main__":
    exit(main())