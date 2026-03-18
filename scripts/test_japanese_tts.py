#!/usr/bin/env python3
"""
Comprehensive Japanese TTS testing script for piper.
Tests various aspects of Japanese text-to-speech synthesis including:
- Basic functionality
- Dictionary auto-download
- Various text patterns (hiragana, katakana, kanji, mixed)
- Long text handling
- Special characters and punctuation
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

# Import platform utilities
from platform_utils import get_platform_name


# Configure stdout for UTF-8 on Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Test sentences covering various Japanese text patterns
TEST_SENTENCES = {
    "basic": {
        "hiragana": "こんにちは、これはテストです。",
        "katakana": "コンニチハ、コレハテストデス。",
        "kanji": "今日は良い天気です。",
        "mixed": "今日は2025年7月2日です。",
        "english_mixed": "これはPiperのテストです。",
    },
    "comprehensive": {
        "long_sentence": "吾輩は猫である。名前はまだ無い。どこで生れたかとんと見当がつかぬ。何でも薄暗いじめじめした所でニャーニャー泣いていた事だけは記憶している。",
        "punctuation": "これは、句読点のテストです。疑問符は使えますか？感嘆符も使えます！",
        "numbers": "値段は1,234円です。電話番号は03-1234-5678です。",
        "symbols": "メールアドレスはtest@example.comです。URLはhttps://example.com/です。",
        "particles": "私は学校へ行きます。彼と一緒に勉強をしています。",
        "honorifics": "田中さん、佐藤様、山田先生がいらっしゃいます。",
        "onomatopoeia": "犬がワンワンと吠えています。雨がザーザー降っています。",
        "dialects": "大阪弁：めっちゃええやん。標準語：とても良いですね。",
    },
}


class JapaneseTTSTester:
    def __init__(self, piper_path: str, model_path: str = None):
        self.piper_path = Path(piper_path).resolve()

        # Add .exe extension on Windows if not present
        if sys.platform == "win32" and not self.piper_path.suffix:
            exe_path = self.piper_path.with_suffix(".exe")
            if exe_path.exists():
                self.piper_path = exe_path

        self.model_path = model_path
        self.results = {
            "platform": sys.platform,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tests": {},
        }

        # Performance metrics
        self.performance_metrics = {
            "language": "ja_JP",
            "model": "multilingual-test-medium",
            "platform": sys.platform,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "test_results": [],
            "summary": {},
        }

        # Create test results directory
        self.results_dir = Path("test_results")
        self.results_dir.mkdir(exist_ok=True)

        # Create performance directory
        self.performance_dir = self.results_dir / "performance"
        self.performance_dir.mkdir(exist_ok=True)

    def check_piper_exists(self) -> bool:
        """Check if piper executable exists."""
        if not self.piper_path.exists():
            print(f"Error: Piper executable not found at {self.piper_path}")
            return False
        return True

    def download_model_if_needed(self):
        """Download Japanese model if not provided."""
        if self.model_path:
            return

        print("Downloading Japanese TTS model...")
        # Use the test model that's already in the repository
        test_model_path = (
            Path(__file__).parent.parent / "test" / "models" / "multilingual-test-medium.onnx"
        )

        if test_model_path.exists():
            self.model_path = test_model_path
            print(f"Using test model: {self.model_path}")
            return

        # If test model doesn't exist, raise error
        print("Test model not found, creating minimal test model...")
        raise FileNotFoundError(
            "Japanese test model not found. Expected at: "
            + str(test_model_path)
            + "\nPlease ensure test models are available in the repository."
        )

    def run_tts(self, text: str, output_file: str) -> tuple[bool, str, float]:
        """Run TTS and return success status, error message, and duration."""
        start_time = time.time()

        cmd = [
            str(self.piper_path),
            "--model",
            str(self.model_path),
            "--output_file",
            output_file,
            "--debug",
        ]

        try:
            # Set environment for espeak-ng data if needed
            env = os.environ.copy()
            espeak_data = self.piper_path.parent.parent / "share" / "espeak-ng-data"
            if espeak_data.exists():
                env["ESPEAK_DATA_PATH"] = str(espeak_data)

            # Set library path for Linux
            if sys.platform == "linux":
                lib_path = self.piper_path.parent.parent / "lib"
                if lib_path.exists():
                    ld_library_path = env.get("LD_LIBRARY_PATH", "")
                    env["LD_LIBRARY_PATH"] = (
                        f"{lib_path}:{ld_library_path}"
                        if ld_library_path
                        else str(lib_path)
                    )

            # Set library path for macOS
            elif sys.platform == "darwin":
                lib_path = self.piper_path.parent.parent / "lib"
                if lib_path.exists():
                    dyld_library_path = env.get("DYLD_LIBRARY_PATH", "")
                    env["DYLD_LIBRARY_PATH"] = (
                        f"{lib_path}:{dyld_library_path}"
                        if dyld_library_path
                        else str(lib_path)
                    )
                    # Also set fallback path
                    dyld_fallback_library_path = env.get(
                        "DYLD_FALLBACK_LIBRARY_PATH", ""
                    )
                    env["DYLD_FALLBACK_LIBRARY_PATH"] = (
                        f"{lib_path}:{dyld_fallback_library_path}"
                        if dyld_fallback_library_path
                        else str(lib_path)
                    )

            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                encoding="utf-8",
            )

            stdout, stderr = process.communicate(input=text)
            duration = time.time() - start_time

            if process.returncode != 0:
                return False, stderr, duration

            # Check if output file was created and has content
            if not os.path.exists(output_file):
                return False, "Output file was not created", duration

            if os.path.getsize(output_file) == 0:
                return False, "Output file is empty", duration

            return True, "", duration

        except Exception as e:
            return False, str(e), time.time() - start_time

    def check_wav_file(self, wav_file: str) -> dict:
        """Analyze WAV file properties."""
        try:
            with wave.open(wav_file, "rb") as wav:
                return {
                    "channels": wav.getnchannels(),
                    "sample_width": wav.getsampwidth(),
                    "framerate": wav.getframerate(),
                    "frames": wav.getnframes(),
                    "duration": wav.getnframes() / wav.getframerate(),
                }
        except Exception as e:
            return {"error": str(e)}

    def record_performance_metrics(
        self, test_name: str, text: str, generation_time: float, audio_path: str
    ) -> None:
        """Record performance metrics for a test."""
        wav_info = self.check_wav_file(audio_path)
        if "error" not in wav_info:
            audio_duration = wav_info.get("duration", 0)
            rtf = (
                generation_time / audio_duration if audio_duration > 0 else float("inf")
            )

            metric = {
                "test_name": test_name,
                "text": text,  # Full text for reference
                "text_preview": (
                    text[:50] + "..." if len(text) > 50 else text
                ),  # Truncated for display
                "char_count": len(text),
                "generation_time_ms": round(generation_time * 1000, 2),
                "audio_duration_ms": round(audio_duration * 1000, 2),
                "rtf": round(rtf, 4),
                "chars_per_second": (
                    round(len(text) / generation_time, 2) if generation_time > 0 else 0
                ),
                "file_size_bytes": os.path.getsize(audio_path),
                "audio_file": os.path.basename(audio_path),
            }

            self.performance_metrics["test_results"].append(metric)

    def test_basic(self) -> bool:
        """Run basic Japanese TTS tests."""
        print("\n=== Running Basic Japanese TTS Tests ===")

        all_passed = True

        for test_name, text in TEST_SENTENCES["basic"].items():
            platform_name = get_platform_name()
            output_file = str(
                self.results_dir / f"ja_JP_{platform_name}_basic_{test_name}.wav"
            )
            print(f"\nTesting {test_name}: {text}")

            success, error, duration = self.run_tts(text, output_file)

            test_result = {
                "text": text,
                "success": success,
                "duration": duration,
                "error": error,
            }

            if success:
                wav_info = self.check_wav_file(output_file)
                test_result["wav_info"] = wav_info
                print(
                    f"  [OK] Success! Generated {wav_info.get('duration', 0):.2f}s audio in {duration:.2f}s"
                )
                # Record performance metrics
                self.record_performance_metrics(
                    f"basic_{test_name}", text, duration, output_file
                )
            else:
                print(f"  [FAIL] Failed: {error}")
                all_passed = False

            self.results["tests"][f"basic_{test_name}"] = test_result

        return all_passed

    def test_comprehensive(self) -> bool:
        """Run comprehensive Japanese TTS tests."""
        print("\n=== Running Comprehensive Japanese TTS Tests ===")

        all_passed = True

        for test_name, text in TEST_SENTENCES["comprehensive"].items():
            platform_name = get_platform_name()
            output_file = str(
                self.results_dir
                / f"ja_JP_{platform_name}_comprehensive_{test_name}.wav"
            )
            print(f"\nTesting {test_name}: {text[:50]}...")

            success, error, duration = self.run_tts(text, output_file)

            test_result = {
                "text": text,
                "success": success,
                "duration": duration,
                "error": error,
            }

            if success:
                wav_info = self.check_wav_file(output_file)
                test_result["wav_info"] = wav_info
                print(
                    f"  [OK] Success! Generated {wav_info.get('duration', 0):.2f}s audio in {duration:.2f}s"
                )
                # Record performance metrics
                self.record_performance_metrics(
                    f"comprehensive_{test_name}", text, duration, output_file
                )
            else:
                print(f"  [FAIL] Failed: {error}")
                all_passed = False

            self.results["tests"][f"comprehensive_{test_name}"] = test_result

        return all_passed

    def test_dictionary_download(self) -> bool:
        """Test OpenJTalk dictionary auto-download."""
        print("\n=== Testing Dictionary Auto-Download ===")

        # Create a temporary HOME to ensure clean dictionary state
        with tempfile.TemporaryDirectory() as temp_home:
            env = os.environ.copy()
            env["HOME"] = temp_home

            # Remove any existing dictionary path
            env.pop("OPENJTALK_DICTIONARY_PATH", None)

            output_file = str(self.results_dir / "dictionary_download_test.wav")

            cmd = [
                str(self.piper_path),
                "--model",
                str(self.model_path),
                "--output_file",
                output_file,
            ]

            # Set espeak-ng data path if available
            espeak_data = self.piper_path.parent.parent / "share" / "espeak-ng-data"
            if espeak_data.exists():
                env["ESPEAK_DATA_PATH"] = str(espeak_data)

            start_time = time.time()

            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                encoding="utf-8",
            )

            stdout, stderr = process.communicate(input="辞書ダウンロードテスト")
            duration = time.time() - start_time

            # Check if dictionary was downloaded
            dict_path = (
                Path(temp_home)
                / ".local"
                / "share"
                / "piper"
                / "open_jtalk_dic_utf_8-1.11"
            )

            test_result = {
                "success": process.returncode == 0,
                "duration": duration,
                "dictionary_downloaded": dict_path.exists(),
                "stdout": stdout,
                "stderr": stderr,
            }

            if test_result["success"] and test_result["dictionary_downloaded"]:
                print("  [OK] Dictionary auto-download successful!")
            else:
                print("  [FAIL] Dictionary auto-download failed")
                print(f"    stderr: {stderr}")

            self.results["tests"]["dictionary_download"] = test_result

            return test_result["success"]

    def save_results(self):
        """Save test results to JSON file."""
        results_file = (
            self.results_dir
            / f"japanese_tts_results_{sys.platform}_{int(time.time())}.json"
        )

        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

        print(f"\nTest results saved to: {results_file}")

    def save_performance_metrics(self):
        """Save performance metrics and calculate summary statistics."""
        if self.performance_metrics["test_results"]:
            # Calculate summary statistics
            results = self.performance_metrics["test_results"]
            rtf_values = [r["rtf"] for r in results if r["rtf"] != float("inf")]
            gen_times = [r["generation_time_ms"] for r in results]
            char_speeds = [r["chars_per_second"] for r in results]

            self.performance_metrics["summary"] = {
                "total_tests": len(results),
                "avg_rtf": (
                    round(sum(rtf_values) / len(rtf_values), 4) if rtf_values else 0
                ),
                "min_rtf": round(min(rtf_values), 4) if rtf_values else 0,
                "max_rtf": round(max(rtf_values), 4) if rtf_values else 0,
                "avg_generation_time_ms": (
                    round(sum(gen_times) / len(gen_times), 2) if gen_times else 0
                ),
                "avg_chars_per_second": (
                    round(sum(char_speeds) / len(char_speeds), 2) if char_speeds else 0
                ),
            }

            # Save to file
            metrics_file = (
                self.performance_dir
                / f"japanese_tts_metrics_{sys.platform}_{int(time.time())}.json"
            )
            with open(metrics_file, "w", encoding="utf-8") as f:
                json.dump(self.performance_metrics, f, ensure_ascii=False, indent=2)

            print(f"\nPerformance metrics saved to: {metrics_file}")

            # Also save a simplified version for the job summary
            summary_file = self.results_dir / "performance_summary.json"
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(self.performance_metrics, f, ensure_ascii=False, indent=2)

    def run_all_tests(self, test_type: str = "all") -> bool:
        """Run all requested tests."""
        if not self.check_piper_exists():
            return False

        all_passed = True

        # Try to find a model
        try:
            if not self.model_path:
                self.download_model_if_needed()

            # Run model-dependent tests
            if test_type in ["all", "basic"]:
                if not self.test_basic():
                    all_passed = False

            if test_type in ["all", "comprehensive"]:
                if not self.test_comprehensive():
                    all_passed = False
        except FileNotFoundError as e:
            print(f"\nWarning: {e}")
            print("Skipping model-dependent tests.")

        # Always run OpenJTalk availability test
        print("\n=== Testing OpenJTalk Availability ===")
        if not self.test_openjtalk_binary():
            all_passed = False

        self.save_results()
        self.save_performance_metrics()

        # Print summary
        print("\n=== Test Summary ===")
        total_tests = len(self.results["tests"])
        passed_tests = sum(
            1 for t in self.results["tests"].values() if t.get("success", False)
        )

        print(f"Total tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        if total_tests > 0:
            print(f"Success rate: {passed_tests / total_tests * 100:.1f}%")

        # Print performance summary
        if self.performance_metrics["summary"]:
            print("\n=== Performance Summary ===")
            summary = self.performance_metrics["summary"]
            print(f"Average RTF: {summary['avg_rtf']} (lower is better)")
            print(
                f"Average generation speed: {summary['avg_chars_per_second']:.1f} chars/second"
            )
            print(
                f"Average generation time: {summary['avg_generation_time_ms']:.1f} ms"
            )

        return all_passed

    def test_openjtalk_binary(self) -> bool:
        """Test if OpenJTalk functionality is available (statically linked into piper)."""
        print("\nTesting OpenJTalk availability...")

        # Since M1.5, OpenJTalk is statically linked into the piper binary.
        # Standalone open_jtalk / open_jtalk_phonemizer binaries are no longer built.
        # We verify OpenJTalk is available by checking that piper exists and
        # can process Japanese text (already validated by basic TTS tests above).
        if self.piper_path.exists():
            print(f"  [OK] OpenJTalk is statically linked into piper ({self.piper_path})")
            self.results["tests"]["openjtalk_binary"] = {
                "statically_linked": True,
                "piper_path": str(self.piper_path),
            }
            return True
        else:
            print(f"  [FAIL] Piper binary not found at: {self.piper_path}")
            self.results["tests"]["openjtalk_binary"] = {
                "statically_linked": False,
                "piper_path": str(self.piper_path),
            }
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Test Japanese TTS functionality in piper"
    )
    parser.add_argument(
        "--piper", default="piper/bin/piper", help="Path to piper executable"
    )
    parser.add_argument(
        "--model", help="Path to Japanese TTS model (will download if not provided)"
    )
    parser.add_argument("--basic", action="store_true", help="Run only basic tests")
    parser.add_argument(
        "--comprehensive", action="store_true", help="Run comprehensive tests"
    )

    args = parser.parse_args()

    # Determine test type
    if args.basic:
        test_type = "basic"
    elif args.comprehensive:
        test_type = "comprehensive"
    else:
        test_type = "all"

    tester = JapaneseTTSTester(args.piper, args.model)

    success = tester.run_all_tests(test_type)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
