#!/usr/bin/env python3
"""
Organize and prepare audio artifacts for GitHub Actions upload.
This script organizes generated audio files into a structured format
and creates metadata for easier browsing.
"""

import argparse
import json
import shutil
import sys
import wave
from pathlib import Path
from typing import Any

from test_text_constants import MULTILINGUAL_TEST_TEXTS, get_test_text_description


def get_audio_info(wav_path: Path) -> dict[str, Any]:
    """Extract information from a WAV file."""
    try:
        with wave.open(str(wav_path), "rb") as wav:
            return {
                "duration_seconds": wav.getnframes() / wav.getframerate(),
                "sample_rate": wav.getframerate(),
                "channels": wav.getnchannels(),
                "file_size_kb": wav_path.stat().st_size / 1024,
            }
    except Exception as e:
        return {"error": str(e)}


def categorize_audio_files(audio_files: list[Path]) -> dict[str, list[Path]]:
    """Categorize audio files by type and language."""
    categories = {
        "japanese": {},  # Organized by platform
        "multilingual": {},  # Organized by language and platform
        "other": [],
    }

    for audio_file in audio_files:
        name = audio_file.name
        parts = name.split("_")

        # New naming pattern: language_platform_model.wav or ja_JP_platform_type_name.wav
        if len(parts) >= 3:
            if parts[0] == "ja" and parts[1] == "JP":
                # Japanese file
                platform = parts[2]
                if platform not in categories["japanese"]:
                    categories["japanese"][platform] = []
                categories["japanese"][platform].append(audio_file)
            elif len(parts[0]) == 2 and (len(parts[1]) == 2 and parts[1].isupper()):
                # Multilingual file (e.g., en_US, de_DE)
                lang = f"{parts[0]}_{parts[1]}"
                if lang not in categories["multilingual"]:
                    categories["multilingual"][lang] = {}
                platform = parts[2] if len(parts) > 2 else "unknown"
                if platform not in categories["multilingual"][lang]:
                    categories["multilingual"][lang][platform] = []
                categories["multilingual"][lang][platform].append(audio_file)
            else:
                categories["other"].append(audio_file)
        else:
            categories["other"].append(audio_file)

    # Remove empty categories
    if not categories["other"]:
        del categories["other"]
    if not categories["japanese"]:
        del categories["japanese"]
    if not categories["multilingual"]:
        del categories["multilingual"]

    return categories


def create_artifact_structure(results_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Create organized structure for audio artifacts."""
    # Find all audio files
    audio_files = list(results_dir.glob("*.wav"))

    if not audio_files:
        return {"status": "no_audio_files", "count": 0}

    # Categorize files
    categories = categorize_audio_files(audio_files)

    # Create output structure
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = {"total_files": len(audio_files), "categories": {}, "samples": {}}

    # Copy files to organized structure
    if "japanese" in categories:
        japan_dir = output_dir / "japanese"
        japan_dir.mkdir(exist_ok=True)
        metadata["categories"]["japanese"] = {"platforms": {}}

        for platform, files in categories["japanese"].items():
            platform_dir = japan_dir / platform
            platform_dir.mkdir(exist_ok=True)

            metadata["categories"]["japanese"]["platforms"][platform] = {
                "count": len(files),
                "files": [],
            }

            for audio_file in files:
                dest_path = platform_dir / audio_file.name
                shutil.copy2(audio_file, dest_path)

                info = get_audio_info(audio_file)
                file_metadata = {
                    "filename": audio_file.name,
                    "platform": platform,
                    "size_kb": round(info.get("file_size_kb", 0), 1),
                    "duration_seconds": round(info.get("duration_seconds", 0), 2),
                }
                metadata["categories"]["japanese"]["platforms"][platform][
                    "files"
                ].append(file_metadata)

    if "multilingual" in categories:
        multi_dir = output_dir / "multilingual"
        multi_dir.mkdir(exist_ok=True)
        metadata["categories"]["multilingual"] = {"languages": {}}

        for lang, platforms in categories["multilingual"].items():
            lang_dir = multi_dir / lang
            lang_dir.mkdir(exist_ok=True)
            metadata["categories"]["multilingual"]["languages"][lang] = {
                "platforms": {}
            }

            for platform, files in platforms.items():
                platform_dir = lang_dir / platform
                platform_dir.mkdir(exist_ok=True)

                metadata["categories"]["multilingual"]["languages"][lang]["platforms"][
                    platform
                ] = {"count": len(files), "files": []}

                for audio_file in files:
                    dest_path = platform_dir / audio_file.name
                    shutil.copy2(audio_file, dest_path)

                    info = get_audio_info(audio_file)
                    file_metadata = {
                        "filename": audio_file.name,
                        "language": lang,
                        "platform": platform,
                        "size_kb": round(info.get("file_size_kb", 0), 1),
                        "duration_seconds": round(info.get("duration_seconds", 0), 2),
                    }
                    metadata["categories"]["multilingual"]["languages"][lang][
                        "platforms"
                    ][platform]["files"].append(file_metadata)

    if "other" in categories:
        other_dir = output_dir / "other"
        other_dir.mkdir(exist_ok=True)
        metadata["categories"]["other"] = {
            "count": len(categories["other"]),
            "files": [],
        }

        for audio_file in categories["other"]:
            dest_path = other_dir / audio_file.name
            shutil.copy2(audio_file, dest_path)

            info = get_audio_info(audio_file)
            file_metadata = {
                "filename": audio_file.name,
                "size_kb": round(info.get("file_size_kb", 0), 1),
                "duration_seconds": round(info.get("duration_seconds", 0), 2),
            }
            metadata["categories"]["other"]["files"].append(file_metadata)

    # Create index.json
    index_path = output_dir / "index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # Create README for artifact browsing
    create_artifact_readme(output_dir, metadata)

    return metadata


def create_artifact_readme(output_dir: Path, metadata: dict[str, Any]):
    """Create README.md for easier artifact browsing."""
    readme_lines = []

    readme_lines.append("# TTS 音声テストアーティファクト")
    readme_lines.append("")
    readme_lines.append(f"総音声ファイル数: **{metadata['total_files']}**")
    readme_lines.append("")

    # Add test text information
    readme_lines.append("## テストで使用されたテキスト")
    readme_lines.append("")

    # Japanese test texts
    if "japanese" in metadata:
        readme_lines.append(get_test_text_description("ja_JP"))
        readme_lines.append("")

    # Multilingual test texts
    if "multilingual" in metadata:
        readme_lines.append("### 多言語テストテキスト")
        readme_lines.append("")
        readme_lines.append("| 言語 | テストテキスト |")
        readme_lines.append("|------|----------------|")

        languages_in_test = set()
        for lang_data in metadata.get("multilingual", {}).values():
            if isinstance(lang_data, dict):
                for lang in lang_data.keys():
                    languages_in_test.add(lang)

        for lang in sorted(languages_in_test):
            if lang in MULTILINGUAL_TEST_TEXTS:
                text = MULTILINGUAL_TEST_TEXTS[lang]
                # Truncate long texts
                if len(text) > 60:
                    text = text[:57] + "..."
                readme_lines.append(f"| {lang} | {text} |")

        readme_lines.append("")

    readme_lines.append("---")
    readme_lines.append("")
    readme_lines.append("## ファイル命名規則")
    readme_lines.append("")
    readme_lines.append("### 多言語音声ファイル")
    readme_lines.append("- 形式: `言語コード_プラットフォーム_モデル名.wav`")
    readme_lines.append("- 例: `en_US_ubuntu_en_US-lessac-medium.wav`")
    readme_lines.append("  - `en_US`: 言語コード（英語・米国）")
    readme_lines.append("  - `ubuntu`: プラットフォーム")
    readme_lines.append("  - `en_US-lessac-medium`: 使用モデル")
    readme_lines.append("")
    readme_lines.append("### 日本語音声ファイル")
    readme_lines.append("- 形式: `ja_JP_プラットフォーム_テストタイプ_テスト名.wav`")
    readme_lines.append("- 例: `ja_JP_windows_basic_hiragana.wav`")
    readme_lines.append("  - `ja_JP`: 言語コード（日本語）")
    readme_lines.append("  - `windows`: プラットフォーム")
    readme_lines.append("  - `basic`: テストタイプ")
    readme_lines.append("  - `hiragana`: テスト名")
    readme_lines.append("")

    # List categories
    readme_lines.append("## ディレクトリ構造")
    readme_lines.append("")
    readme_lines.append("```")
    readme_lines.append("audio_artifacts/")
    readme_lines.append("├── japanese/           # 日本語音声ファイル")
    readme_lines.append("│   ├── ubuntu/")
    readme_lines.append("│   ├── macos/")
    readme_lines.append("│   └── windows/")
    readme_lines.append("├── multilingual/       # 多言語音声ファイル")
    readme_lines.append("│   ├── en_US/         # 英語（米国）")
    readme_lines.append("│   │   ├── ubuntu/")
    readme_lines.append("│   │   ├── macos/")
    readme_lines.append("│   │   └── windows/")
    readme_lines.append("│   ├── zh_CN/         # 中国語")
    readme_lines.append("│   │   └── .../")
    readme_lines.append("│   └── .../           # その他の言語")
    readme_lines.append("└── README.md")
    readme_lines.append("```")
    readme_lines.append("")

    # Japanese files
    if "japanese" in metadata["categories"]:
        readme_lines.append("## 日本語音声ファイル")
        readme_lines.append("")
        for platform, data in metadata["categories"]["japanese"]["platforms"].items():
            platform_display = {
                "ubuntu": "Ubuntu",
                "macos": "macOS",
                "windows": "Windows",
            }.get(platform, platform)

            readme_lines.append(f"### {platform_display}")
            readme_lines.append(f"- ファイル数: {data['count']}")

            total_duration = sum(f.get("duration_seconds", 0) for f in data["files"])
            if total_duration > 0:
                readme_lines.append(f"- 合計時間: {total_duration:.1f} 秒")

            readme_lines.append("")
            readme_lines.append("<details>")
            readme_lines.append("<summary>ファイル一覧</summary>")
            readme_lines.append("")
            readme_lines.append("| ファイル | 時間 | サイズ |")
            readme_lines.append("|----------|------|--------|")

            for file_info in sorted(data["files"], key=lambda x: x["filename"]):
                name = file_info["filename"]
                duration = file_info.get("duration_seconds", 0)
                size = file_info.get("size_kb", 0)
                readme_lines.append(f"| {name} | {duration:.1f}秒 | {size:.1f}KB |")

            readme_lines.append("")
            readme_lines.append("</details>")
            readme_lines.append("")

    # Multilingual files
    if "multilingual" in metadata["categories"]:
        readme_lines.append("## 多言語音声ファイル")
        readme_lines.append("")

        lang_names = {
            "en_US": "英語（米国）",
            "en_GB": "英語（英国）",
            "de_DE": "ドイツ語",
            "fr_FR": "フランス語",
            "es_ES": "スペイン語",
            "zh_CN": "中国語",
            "it_IT": "イタリア語",
            "pt_BR": "ポルトガル語",
            "ru_RU": "ロシア語",
        }

        for lang, lang_data in sorted(
            metadata["categories"]["multilingual"]["languages"].items()
        ):
            lang_display = lang_names.get(lang, lang)
            readme_lines.append(f"### {lang_display} ({lang})")
            readme_lines.append("")

            for platform, data in lang_data["platforms"].items():
                platform_display = {
                    "ubuntu": "Ubuntu",
                    "macos": "macOS",
                    "windows": "Windows",
                }.get(platform, platform)

                readme_lines.append(f"#### {platform_display}")
                readme_lines.append(f"- ファイル数: {data['count']}")

                for file_info in data["files"]:
                    readme_lines.append(
                        f"- `{file_info['filename']}` ({file_info.get('duration_seconds', 0):.1f}秒, {file_info.get('size_kb', 0):.1f}KB)"
                    )

                readme_lines.append("")

    # Usage instructions
    readme_lines.append("## 使用方法")
    readme_lines.append("")
    readme_lines.append(
        "1. GitHub Actions からアーティファクトアーカイブをダウンロード"
    )
    readme_lines.append("2. アーカイブを解凍")
    readme_lines.append("3. 目的の言語・プラットフォームフォルダに移動")
    readme_lines.append("4. WAVファイルを任意の音声プレイヤーで再生")
    readme_lines.append("")
    readme_lines.append("## プラットフォーム間の比較")
    readme_lines.append("")
    readme_lines.append(
        "同じテキストを異なるプラットフォームで生成した音声を比較できます："
    )
    readme_lines.append("- 例: `en_US_ubuntu_*.wav` vs `en_US_windows_*.wav`")
    readme_lines.append("- 音質、発音、生成速度の違いを確認できます")
    readme_lines.append("")

    # Write README
    readme_path = output_dir / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("\n".join(readme_lines))


def create_sample_subset(
    output_dir: Path, metadata: dict[str, Any], max_files: int = 10
):
    """Create a subset of representative samples for quick download."""
    samples_dir = output_dir / "samples"
    samples_dir.mkdir(exist_ok=True)

    selected_files = []

    # Select files from each category
    for category, data in metadata["categories"].items():
        if category == "japanese" and "platforms" in data:
            # Japanese files are organized by platform
            for platform, platform_data in data["platforms"].items():
                if len(selected_files) >= max_files:
                    break
                # Take 1 file from each platform
                for file_info in platform_data["files"][:1]:
                    if len(selected_files) >= max_files:
                        break
                    src_path = (
                        output_dir / "japanese" / platform / file_info["filename"]
                    )
                    if src_path.exists():
                        dest_path = samples_dir / file_info["filename"]
                        shutil.copy2(src_path, dest_path)
                        selected_files.append(file_info)

        elif category == "multilingual" and "languages" in data:
            # Multilingual files are organized by language and platform
            for lang, lang_data in data["languages"].items():
                if len(selected_files) >= max_files:
                    break
                for platform, platform_data in lang_data["platforms"].items():
                    if len(selected_files) >= max_files:
                        break
                    # Take 1 file from each language/platform combination
                    for file_info in platform_data["files"][:1]:
                        if len(selected_files) >= max_files:
                            break
                        src_path = (
                            output_dir
                            / "multilingual"
                            / lang
                            / platform
                            / file_info["filename"]
                        )
                        if src_path.exists():
                            dest_path = samples_dir / file_info["filename"]
                            shutil.copy2(src_path, dest_path)
                            selected_files.append(file_info)

        elif "files" in data:
            # Other category with direct files
            for file_info in data["files"][:2]:
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
        "files": selected_files,
    }

    with open(samples_dir / "samples.json", "w", encoding="utf-8") as f:
        json.dump(samples_metadata, f, indent=2)

    return len(selected_files)


def main():
    parser = argparse.ArgumentParser(
        description="Organize audio artifacts for GitHub Actions"
    )
    parser.add_argument(
        "--results-dir",
        default="test_results",
        help="Directory containing test results",
    )
    parser.add_argument(
        "--output-dir",
        default="audio_artifacts",
        help="Output directory for organized artifacts",
    )
    parser.add_argument(
        "--create-samples", action="store_true", help="Create a subset of sample files"
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=10,
        help="Maximum number of sample files to include",
    )

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

    print(
        f"Organized {metadata['total_files']} audio files into {len(metadata['categories'])} categories"
    )

    # Create sample subset if requested
    if args.create_samples:
        sample_count = create_sample_subset(output_dir, metadata, args.max_samples)
        print(f"Created sample subset with {sample_count} files")

    # Print summary
    print("\nCategory summary:")
    for category, data in metadata["categories"].items():
        if category == "japanese" and "platforms" in data:
            total_count = sum(
                platform_data["count"] for platform_data in data["platforms"].values()
            )
            print(f"  - {category}: {total_count} files")
        elif category == "multilingual" and "languages" in data:
            total_count = sum(
                platform_data["count"]
                for lang_data in data["languages"].values()
                for platform_data in lang_data["platforms"].values()
            )
            print(f"  - {category}: {total_count} files")
        elif "count" in data:
            print(f"  - {category}: {data['count']} files")
        else:
            print(f"  - {category}: unknown structure")

    print(f"\nArtifacts organized in: {output_dir.absolute()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
