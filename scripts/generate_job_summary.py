#!/usr/bin/env python3
"""
Generate GitHub Actions Job Summary from performance metrics.
This script reads performance metrics JSON files and generates a markdown summary
with tables and visualizations for the GitHub Actions job summary.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Import platform utilities
from platform_utils import PLATFORM_ICONS


def load_metrics_files(results_dir: Path) -> list[dict[str, Any]]:
    """Load all performance metrics JSON files from the results directory."""
    metrics_files = []

    # Look for performance summary files
    summary_files = list(results_dir.glob("performance_summary.json"))

    # Also look in performance subdirectory
    perf_dir = results_dir / "performance"
    if perf_dir.exists():
        summary_files.extend(perf_dir.glob("*_metrics_*.json"))

    # Load each file
    for file_path in summary_files:
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                data["source_file"] = file_path.name
                metrics_files.append(data)
        except Exception as e:
            print(f"Warning: Failed to load {file_path}: {e}", file=sys.stderr)

    return metrics_files


def generate_japanese_tts_summary(metrics: dict[str, Any]) -> str:
    """Generate summary for Japanese TTS test results."""
    summary_lines = []

    summary_lines.append("### 🇯🇵 日本語 TTS パフォーマンス")
    summary_lines.append("")

    # Overall statistics
    if "summary" in metrics:
        stats = metrics["summary"]
        summary_lines.append("**統計サマリー:**")
        summary_lines.append(
            f"- 平均 RTF: **{stats.get('avg_rtf', 'N/A')}** (低いほど良い)"
        )
        summary_lines.append(
            f"- 平均速度: **{stats.get('avg_chars_per_second', 'N/A'):.1f}** 文字/秒"
        )
        summary_lines.append(f"- 総テスト数: **{stats.get('total_tests', 0)}**")
        summary_lines.append("")

    # Detailed results table
    if "test_results" in metrics and metrics["test_results"]:
        summary_lines.append("<details>")
        summary_lines.append("<summary>詳細なテスト結果</summary>")
        summary_lines.append("")
        summary_lines.append(
            "| テスト名 | 音声ファイル名 | テストテキスト | 文字数 | 生成時間 | 音声時間 | RTF | 速度 (文字/秒) |"
        )
        summary_lines.append(
            "|----------|----------------|----------------|--------|----------|----------|-----|----------------|"
        )

        for result in metrics["test_results"]:
            test_name = result.get("test_name", "Unknown")
            audio_file = result.get("audio_file", "N/A")
            text_preview = (
                result.get("text_preview", result.get("text", ""))[:40] + "..."
            )
            chars = result.get("char_count", 0)
            gen_time = result.get("generation_time_ms", 0)
            audio_dur = result.get("audio_duration_ms", 0)
            rtf = result.get("rtf", 0)
            speed = result.get("chars_per_second", 0)

            summary_lines.append(
                f"| {test_name} | `{audio_file}` | {text_preview} | {chars} | {gen_time:.0f}ms | {audio_dur:.0f}ms | {rtf:.3f} | {speed:.1f} |"
            )

        summary_lines.append("")
        summary_lines.append("</details>")

    summary_lines.append("")
    return "\n".join(summary_lines)


def generate_multilingual_tts_summary(metrics: dict[str, Any]) -> str:
    """Generate summary for multilingual TTS test results."""
    summary_lines = []

    summary_lines.append("### 🌍 多言語 TTS パフォーマンス")
    summary_lines.append("")

    # Overall statistics
    if "summary" in metrics:
        stats = metrics["summary"]
        summary_lines.append("**統計サマリー:**")
        summary_lines.append(f"- テスト言語数: **{stats.get('total_languages', 0)}**")
        summary_lines.append(f"- 平均 RTF: **{stats.get('avg_rtf', 'N/A')}**")
        summary_lines.append(
            f"- 平均速度: **{stats.get('avg_speed_chars_per_second', 'N/A'):.1f}** 文字/秒"
        )
        summary_lines.append("")

    # Language comparison table
    if "languages" in metrics and metrics["languages"]:
        summary_lines.append(
            "| 言語 | モデル | 音声ファイル名 | テストテキスト | RTF | 速度 (文字/秒) | 生成時間 | 音声時間 |"
        )
        summary_lines.append(
            "|------|--------|----------------|----------------|-----|----------------|----------|----------|"
        )

        for lang, data in sorted(metrics["languages"].items()):
            model = data.get("model", "Unknown")
            perf = data.get("performance", {})
            rtf = perf.get("rtf", 0)
            speed = perf.get("chars_per_second", 0)
            gen_time = perf.get("generation_time_ms", 0)
            audio_dur = perf.get("audio_duration_ms", 0)
            audio_file = perf.get("audio_file", "N/A")
            test_text = perf.get("test_text", "")[:30] + "..."

            # Add flag emoji for languages
            lang_flags = {
                "en_US": "🇺🇸",
                "en_GB": "🇬🇧",
                "de_DE": "🇩🇪",
                "fr_FR": "🇫🇷",
                "es_ES": "🇪🇸",
                "it_IT": "🇮🇹",
                "pt_BR": "🇧🇷",
                "ru_RU": "🇷🇺",
                "zh_CN": "🇨🇳",
                "ja_JP": "🇯🇵",
                "ko_KR": "🇰🇷",
                "ar_JO": "🇯🇴",
                "nl_NL": "🇳🇱",
                "pl_PL": "🇵🇱",
                "sv_SE": "🇸🇪",
                "tr_TR": "🇹🇷",
            }
            flag = lang_flags.get(lang, "🌐")

            summary_lines.append(
                f"| {flag} {lang} | {model} | `{audio_file}` | {test_text} | {rtf:.3f} | {speed:.1f} | {gen_time:.0f}ms | {audio_dur:.0f}ms |"
            )

        summary_lines.append("")

    # Performance visualization using Mermaid
    if "languages" in metrics and len(metrics["languages"]) > 0:
        summary_lines.append("<details>")
        summary_lines.append("<summary>パフォーマンス可視化</summary>")
        summary_lines.append("")
        summary_lines.append("```mermaid")
        summary_lines.append("graph LR")
        summary_lines.append("    subgraph RTF パフォーマンス")

        # Sort languages by RTF for better visualization
        sorted_langs = sorted(
            [
                (lang, data.get("performance", {}).get("rtf", 0))
                for lang, data in metrics["languages"].items()
            ],
            key=lambda x: x[1],
        )

        for lang, rtf in sorted_langs[:10]:  # Show top 10
            # Color code based on RTF
            if rtf < 0.5:
                pass
            elif rtf < 1.0:
                pass
            else:
                pass

            summary_lines.append(f"        {lang}[{lang}<br/>RTF: {rtf:.2f}]")

        summary_lines.append("    end")
        summary_lines.append("```")
        summary_lines.append("")
        summary_lines.append("</details>")

    summary_lines.append("")
    return "\n".join(summary_lines)


def generate_combined_platform_summary(all_metrics: list[dict[str, Any]]) -> str:
    """Generate combined summary with all platforms and test types."""
    # Separate Japanese and multilingual metrics
    japanese_metrics = []
    multilingual_metrics = []

    for metrics in all_metrics:
        if "language" in metrics and metrics["language"] == "ja_JP":
            japanese_metrics.append(metrics)
        elif "languages" in metrics:
            multilingual_metrics.append(metrics)

    summary_lines = []

    # Combined Japanese TTS summary across platforms
    if japanese_metrics:
        summary_lines.append("### 🇯🇵 日本語 TTS パフォーマンス (全プラットフォーム)")
        summary_lines.append("")

        # Combine all test results
        all_test_results = []
        platform_summaries = {}

        for metrics in japanese_metrics:
            platform = metrics.get("platform", "unknown")
            if "test_results" in metrics:
                for result in metrics["test_results"]:
                    result["platform"] = platform
                    all_test_results.append(result)

            if "summary" in metrics:
                platform_summaries[platform] = metrics["summary"]

        # Overall statistics
        if platform_summaries:
            total_tests = sum(
                s.get("total_tests", 0) for s in platform_summaries.values()
            )
            all_rtf = []
            all_speeds = []

            for summary in platform_summaries.values():
                if summary.get("avg_rtf", 0) > 0:
                    all_rtf.append(summary["avg_rtf"])
                if summary.get("avg_chars_per_second", 0) > 0:
                    all_speeds.append(summary["avg_chars_per_second"])

            summary_lines.append("**統計サマリー (全プラットフォーム):**")
            summary_lines.append(f"- 総テスト数: **{total_tests}**")
            if all_rtf:
                summary_lines.append(
                    f"- 全体平均 RTF: **{sum(all_rtf) / len(all_rtf):.4f}** (低いほど良い)"
                )
            if all_speeds:
                summary_lines.append(
                    f"- 全体平均速度: **{sum(all_speeds) / len(all_speeds):.1f}** 文字/秒"
                )
            summary_lines.append("")

            # Platform comparison
            summary_lines.append("**プラットフォーム別パフォーマンス:**")
            summary_lines.append(
                "| プラットフォーム | 平均 RTF | 平均速度 (文字/秒) | テスト数 |"
            )
            summary_lines.append(
                "|------------------|----------|-------------------|----------|"
            )

            for platform, summary in sorted(platform_summaries.items()):
                platform_icon = PLATFORM_ICONS.get(platform, "💻")

                avg_rtf = summary.get("avg_rtf", "N/A")
                avg_speed = summary.get("avg_chars_per_second", "N/A")
                test_count = summary.get("total_tests", 0)

                summary_lines.append(
                    f"| {platform_icon} {platform} | {avg_rtf} | {avg_speed:.1f} | {test_count} |"
                )

            summary_lines.append("")

            # Detailed test results table
            if all_test_results:
                summary_lines.append("**詳細なテスト結果:**")
                summary_lines.append("")
                summary_lines.append("<details>")
                summary_lines.append(
                    "<summary>テスト結果の詳細（クリックして展開）</summary>"
                )
                summary_lines.append("")
                summary_lines.append(
                    "| プラットフォーム | テスト名 | 音声ファイル名 | テストテキスト | 文字数 | 生成時間 | RTF | 速度 (文字/秒) |"
                )
                summary_lines.append(
                    "|------------------|----------|----------------|----------------|--------|----------|-----|----------------|"
                )

                for result in sorted(
                    all_test_results,
                    key=lambda x: (x.get("platform", ""), x.get("test_name", "")),
                ):
                    platform = result.get("platform", "unknown")
                    platform_icon = PLATFORM_ICONS.get(platform, "💻")

                    test_name = result.get("test_name", "Unknown")
                    audio_file = result.get("audio_file", "N/A")
                    text_preview = (
                        result.get("text_preview", result.get("text", ""))[:30] + "..."
                    )
                    chars = result.get("char_count", 0)
                    gen_time = result.get("generation_time_ms", 0)
                    rtf = result.get("rtf", 0)
                    speed = result.get("chars_per_second", 0)

                    summary_lines.append(
                        f"| {platform_icon} {platform} | {test_name} | `{audio_file}` | {text_preview} | {chars} | {gen_time:.0f}ms | {rtf:.3f} | {speed:.1f} |"
                    )

                summary_lines.append("")
                summary_lines.append("</details>")
                summary_lines.append("")

    # Combined multilingual TTS summary across platforms
    if multilingual_metrics:
        summary_lines.append("### 🌍 多言語 TTS パフォーマンス (全プラットフォーム)")
        summary_lines.append("")

        # Combine language results across platforms
        language_by_platform = {}

        for metrics in multilingual_metrics:
            platform = metrics.get("platform", "unknown")
            if "languages" in metrics:
                for lang, data in metrics["languages"].items():
                    if lang not in language_by_platform:
                        language_by_platform[lang] = {}
                    language_by_platform[lang][platform] = data

        # Overall statistics
        all_languages = set()
        platform_stats = {}

        for metrics in multilingual_metrics:
            platform = metrics.get("platform", "unknown")
            if "summary" in metrics:
                platform_stats[platform] = metrics["summary"]
            if "languages" in metrics:
                all_languages.update(metrics["languages"].keys())

        summary_lines.append("**統計サマリー (全プラットフォーム):**")
        summary_lines.append(f"- テスト言語数: **{len(all_languages)}**")

        if platform_stats:
            all_rtf = []
            all_speeds = []

            for stats in platform_stats.values():
                if stats.get("avg_rtf", 0) > 0:
                    all_rtf.append(stats["avg_rtf"])
                if stats.get("avg_speed_chars_per_second", 0) > 0:
                    all_speeds.append(stats["avg_speed_chars_per_second"])

            if all_rtf:
                summary_lines.append(
                    f"- 全体平均 RTF: **{sum(all_rtf) / len(all_rtf):.4f}**"
                )
            if all_speeds:
                summary_lines.append(
                    f"- 全体平均速度: **{sum(all_speeds) / len(all_speeds):.1f}** 文字/秒"
                )

        summary_lines.append("")

        # Language performance across platforms
        if language_by_platform:
            summary_lines.append("**言語別クロスプラットフォーム比較:**")
            summary_lines.append(
                "| 言語 | プラットフォーム | モデル | 音声ファイル名 | RTF | 速度 (文字/秒) |"
            )
            summary_lines.append(
                "|------|------------------|--------|----------------|-----|----------------|"
            )

            # Language flags
            lang_flags = {
                "en_US": "🇺🇸",
                "en_GB": "🇬🇧",
                "de_DE": "🇩🇪",
                "fr_FR": "🇫🇷",
                "es_ES": "🇪🇸",
                "it_IT": "🇮🇹",
                "pt_BR": "🇧🇷",
                "ru_RU": "🇷🇺",
                "zh_CN": "🇨🇳",
                "ja_JP": "🇯🇵",
                "ko_KR": "🇰🇷",
                "ar_JO": "🇯🇴",
                "nl_NL": "🇳🇱",
                "pl_PL": "🇵🇱",
                "sv_SE": "🇸🇪",
                "tr_TR": "🇹🇷",
            }

            for lang in sorted(language_by_platform.keys()):
                flag = lang_flags.get(lang, "🌐")
                platforms_data = language_by_platform[lang]

                for platform, data in sorted(platforms_data.items()):
                    platform_icon = PLATFORM_ICONS.get(platform, "💻")

                    model = data.get("model", "Unknown")
                    perf = data.get("performance", {})
                    rtf = perf.get("rtf", "N/A")
                    speed = perf.get("chars_per_second", "N/A")
                    audio_file = perf.get("audio_file", "N/A")

                    if isinstance(rtf, int | float):
                        rtf = f"{rtf:.3f}"
                    if isinstance(speed, int | float):
                        speed = f"{speed:.1f}"

                    summary_lines.append(
                        f"| {flag} {lang} | {platform_icon} {platform} | {model} | `{audio_file}` | {rtf} | {speed} |"
                    )

            summary_lines.append("")

    return "\n".join(summary_lines)


def generate_audio_artifacts_section(results_dir: Path) -> str:
    """Generate section about audio artifacts."""
    wav_files = list(results_dir.glob("*.wav"))

    if not wav_files:
        return ""

    summary_lines = []
    summary_lines.append("### 🎵 生成された音声サンプル")
    summary_lines.append("")
    summary_lines.append(
        f"テスト中に **{len(wav_files)}** 個の音声ファイルを生成しました。"
    )
    summary_lines.append("")

    # Group files by language and platform
    file_groups = {}
    for wav_file in wav_files:
        # Parse filename pattern: language_platform_model.wav or ja_JP_platform_type_name.wav
        parts = wav_file.name.split("_")
        if len(parts) >= 3:
            if parts[0] == "ja" and parts[1] == "JP":
                lang = "ja_JP"
                platform = parts[2]
                desc = "_".join(parts[3:]).replace(".wav", "")
            else:
                lang = f"{parts[0]}_{parts[1]}" if parts[1].isupper() else parts[0]
                platform = parts[2] if len(parts) > 2 else "unknown"
                desc = (
                    "_".join(parts[3:]).replace(".wav", "")
                    if len(parts) > 3
                    else parts[-1].replace(".wav", "")
                )

            key = (lang, platform)
            if key not in file_groups:
                file_groups[key] = []
            file_groups[key].append((wav_file.name, desc))

    # Display organized file list
    if file_groups:
        summary_lines.append("**言語・プラットフォーム別の音声ファイル:**")
        summary_lines.append("")
        summary_lines.append("<details>")
        summary_lines.append("<summary>ファイル一覧（クリックして展開）</summary>")
        summary_lines.append("")

        # Language names
        lang_names = {
            "ja_JP": "🇯🇵 日本語",
            "en_US": "🇺🇸 英語（米国）",
            "en_GB": "🇬🇧 英語（英国）",
            "de_DE": "🇩🇪 ドイツ語",
            "fr_FR": "🇫🇷 フランス語",
            "es_ES": "🇪🇸 スペイン語",
            "it_IT": "🇮🇹 イタリア語",
            "pt_BR": "🇧🇷 ポルトガル語",
            "zh_CN": "🇨🇳 中国語",
            "ru_RU": "🇷🇺 ロシア語",
            "nl_NL": "🇳🇱 オランダ語",
            "ko_KR": "🇰🇷 韓国語",
        }

        platform_names = {"ubuntu": "Ubuntu", "macos": "macOS", "windows": "Windows"}

        for (lang, platform), files in sorted(file_groups.items()):
            lang_display = lang_names.get(lang, f"🌐 {lang}")
            platform_display = platform_names.get(platform, platform)

            summary_lines.append(f"#### {lang_display} - {platform_display}")
            summary_lines.append("")

            for filename, _desc in sorted(files):
                summary_lines.append(f"- `{filename}`")

            summary_lines.append("")

        summary_lines.append("</details>")
        summary_lines.append("")

    # Example naming pattern
    summary_lines.append("**ファイル名の形式:**")
    summary_lines.append("- 多言語: `言語コード_プラットフォーム_モデル名.wav`")
    summary_lines.append("  - 例: `en_US_ubuntu_en_US-lessac-medium.wav`")
    summary_lines.append("- 日本語: `ja_JP_プラットフォーム_テストタイプ_テスト名.wav`")
    summary_lines.append("  - 例: `ja_JP_windows_basic_hiragana.wav`")
    summary_lines.append("")
    summary_lines.append(
        "音声ファイルはアーティファクトからダウンロードして聴くことができます。"
    )
    summary_lines.append("")

    return "\n".join(summary_lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate GitHub Actions job summary from performance metrics"
    )
    parser.add_argument(
        "--results-dir",
        default="test_results",
        help="Directory containing test results and metrics",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file (default: write to GITHUB_STEP_SUMMARY)",
    )

    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        print(f"Error: Results directory {results_dir} does not exist")
        sys.exit(1)

    # Load all metrics files
    all_metrics = load_metrics_files(results_dir)

    if not all_metrics:
        print("Warning: No metrics files found")
        summary = "## 📊 TTS パフォーマンスレポート\n\nこのテスト実行ではパフォーマンスメトリクスが収集されませんでした。\n"
    else:
        # Generate summary sections
        summary_parts = []
        summary_parts.append("## 📊 TTS パフォーマンスレポート")
        summary_parts.append("")

        # Generate combined platform summary
        combined_summary = generate_combined_platform_summary(all_metrics)
        if combined_summary:
            summary_parts.append(combined_summary)

        # If no combined summary, fall back to individual summaries
        if not combined_summary:
            for metrics in all_metrics:
                if "language" in metrics and metrics["language"] == "ja_JP":
                    summary_parts.append(generate_japanese_tts_summary(metrics))
                elif "languages" in metrics:
                    summary_parts.append(generate_multilingual_tts_summary(metrics))

        # Add audio artifacts section
        audio_section = generate_audio_artifacts_section(results_dir)
        if audio_section:
            summary_parts.append(audio_section)

        # Add footer
        summary_parts.append("---")
        summary_parts.append("*piper-plus パフォーマンステストスイートによって生成*")

        summary = "\n".join(summary_parts)

    # Write output
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(summary)
        print(f"Summary written to {args.output}")
    else:
        # Write to GitHub Actions step summary
        github_step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if github_step_summary:
            with open(github_step_summary, "a", encoding="utf-8") as f:
                f.write(summary)
            print("Summary written to GITHUB_STEP_SUMMARY")
        else:
            # Fallback: print to stdout
            print(summary)


if __name__ == "__main__":
    main()
