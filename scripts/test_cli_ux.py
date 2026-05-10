#!/usr/bin/env python3
"""
Integration tests for piper-plus C++ CLI UX improvements.

Tests:
1. --text option: Direct text input without stdin pipe
2. --list-models: Model catalog listing
3. --download-model: Model download functionality
4. --help: Updated help text includes new options
5. Environment variables: PIPER_DEFAULT_MODEL, PIPER_MODEL_DIR

Usage:
    python scripts/test_cli_ux.py [--piper-exe PATH]

    If --piper-exe is not provided, searches common build locations.
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


def find_piper_exe() -> Optional[Path]:
    """Find piper executable in common build locations."""
    search_paths = [
        Path("build/Release/piper.exe"),
        Path("build/Release/piper"),
        Path("build/piper"),
        Path("build/Debug/piper.exe"),
        Path("install/bin/piper.exe"),
        Path("install/bin/piper"),
    ]

    for p in search_paths:
        if p.exists():
            return p.resolve()

    return None


def run_piper(piper_exe: Path, args: list, stdin_text: str = None,
              timeout: int = 30, env: dict = None) -> subprocess.CompletedProcess:
    """Run piper with given arguments."""
    cmd = [str(piper_exe)] + args

    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    return subprocess.run(
        cmd,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=run_env,
    )


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.message = ""

    def ok(self, msg: str = ""):
        self.passed = True
        self.message = msg

    def fail(self, msg: str):
        self.passed = False
        self.message = msg


def test_help_includes_new_options(piper_exe: Path) -> TestResult:
    """Test that --help output includes new CLI options."""
    result = TestResult("--help includes new options")

    proc = run_piper(piper_exe, ["--help"])
    help_text = proc.stderr + proc.stdout

    missing = []
    for option in ["--text", "--list-models", "--download-model", "--model-dir"]:
        if option not in help_text:
            missing.append(option)

    if missing:
        result.fail(f"Missing options in help text: {', '.join(missing)}")
    else:
        result.ok()

    return result


def test_list_models(piper_exe: Path) -> TestResult:
    """Test --list-models output."""
    result = TestResult("--list-models")

    proc = run_piper(piper_exe, ["--list-models"])

    if proc.returncode != 0:
        result.fail(f"Exit code {proc.returncode}: {proc.stderr}")
        return result

    output = proc.stderr + proc.stdout

    # Should contain at least piper-plus models
    if "tsukuyomi" not in output.lower():
        result.fail("Output doesn't contain tsukuyomi model")
        return result

    result.ok()
    return result


def test_list_models_language_filter(piper_exe: Path) -> TestResult:
    """Test --list-models with language filter."""
    result = TestResult("--list-models ja (language filter)")

    proc = run_piper(piper_exe, ["--list-models", "ja"])

    if proc.returncode != 0:
        result.fail(f"Exit code {proc.returncode}: {proc.stderr}")
        return result

    output = proc.stderr + proc.stdout

    # Should contain Japanese models
    if "japanese" not in output.lower() and "日本語" not in output:
        result.fail("Output doesn't contain Japanese models")
        return result

    result.ok()
    return result


def test_text_option_no_model(piper_exe: Path) -> TestResult:
    """Test --text without model (should fail gracefully)."""
    result = TestResult("--text without --model (graceful error)")

    proc = run_piper(piper_exe, ["--text", "test"])

    # Should fail with a clear error, not crash
    if proc.returncode == 0:
        result.fail("Expected non-zero exit code when no model specified")
        return result

    # Should not be a segfault (return code -11 or 139)
    if proc.returncode in (-11, 139, -6, 134):
        result.fail(f"Crashed with signal {proc.returncode}")
        return result

    result.ok(f"Exit code: {proc.returncode}")
    return result


def test_text_option_with_test_mode(piper_exe: Path) -> TestResult:
    """Test --text with --test-mode (no ONNX required)."""
    result = TestResult("--text with --test-mode")

    # Create a minimal test config
    with tempfile.NamedTemporaryFile(mode='w', suffix='.onnx', delete=False) as f:
        model_path = f.name
        f.write("dummy")

    config = {
        "audio": {"sample_rate": 22050},
        "espeak": {"voice": "en-us"},
        "inference": {"noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8},
        "phoneme_type": "espeak",
        "phoneme_id_map": {"_": [0], "^": [1], "$": [2], " ": [3], "a": [4]},
        "num_speakers": 1
    }

    config_path = model_path + ".json"
    with open(config_path, 'w') as f:
        json.dump(config, f)

    try:
        proc = run_piper(piper_exe, [
            "--model", model_path,
            "--text", "test",
            "--test-mode",
        ])

        # In test mode, it should accept --text without crashing
        if proc.returncode in (-11, 139, -6, 134):
            result.fail(f"Crashed with signal {proc.returncode}")
        else:
            result.ok(f"Exit code: {proc.returncode}")
    finally:
        os.unlink(model_path)
        if os.path.exists(config_path):
            os.unlink(config_path)

    return result


def test_download_model_help(piper_exe: Path) -> TestResult:
    """Test --download-model with non-existent model (should fail gracefully)."""
    result = TestResult("--download-model non-existent (graceful error)")

    with tempfile.TemporaryDirectory() as tmpdir:
        proc = run_piper(piper_exe, [
            "--download-model", "non-existent-model-xyz",
            "--model-dir", tmpdir,
        ])

        # Should fail with non-zero exit
        if proc.returncode == 0:
            result.fail("Expected non-zero exit code for non-existent model")
            return result

        # Should not crash
        if proc.returncode in (-11, 139, -6, 134):
            result.fail(f"Crashed with signal {proc.returncode}")
            return result

        output = proc.stderr + proc.stdout
        if "not found" not in output.lower() and "error" not in output.lower():
            result.fail(f"No error message in output: {output[:200]}")
            return result

    result.ok()
    return result


def test_version_still_works(piper_exe: Path) -> TestResult:
    """Test that --version still works after changes."""
    result = TestResult("--version")

    proc = run_piper(piper_exe, ["--version"])

    if proc.returncode != 0:
        result.fail(f"Exit code {proc.returncode}")
        return result

    version = (proc.stdout + proc.stderr).strip()
    if not version:
        result.fail("No version output")
        return result

    result.ok(f"Version: {version}")
    return result


def test_model_dir_env_var(piper_exe: Path) -> TestResult:
    """Test PIPER_MODEL_DIR environment variable."""
    result = TestResult("PIPER_MODEL_DIR env var")

    with tempfile.TemporaryDirectory() as tmpdir:
        proc = run_piper(
            piper_exe,
            ["--list-models"],
            env={"PIPER_MODEL_DIR": tmpdir}
        )

        # Should not crash
        if proc.returncode in (-11, 139, -6, 134):
            result.fail(f"Crashed with signal {proc.returncode}")
            return result

    result.ok()
    return result


def main():
    parser = argparse.ArgumentParser(description="Test piper-plus CLI UX improvements")
    parser.add_argument("--piper-exe", type=Path, help="Path to piper executable")
    args = parser.parse_args()

    piper_exe = args.piper_exe or find_piper_exe()

    if not piper_exe:
        print("ERROR: piper executable not found. Use --piper-exe to specify path.")
        sys.exit(1)

    if not piper_exe.exists():
        print(f"ERROR: {piper_exe} does not exist")
        sys.exit(1)

    print(f"Testing piper at: {piper_exe}")
    print(f"Platform: {platform.system()} {platform.machine()}")
    print()

    tests = [
        test_version_still_works,
        test_help_includes_new_options,
        test_list_models,
        test_list_models_language_filter,
        test_text_option_no_model,
        test_text_option_with_test_mode,
        test_download_model_help,
        test_model_dir_env_var,
    ]

    results = []
    for test_fn in tests:
        try:
            result = test_fn(piper_exe)
        except Exception as e:
            result = TestResult(test_fn.__name__)
            result.fail(f"Exception: {e}")
        results.append(result)

        status = "PASS" if result.passed else "FAIL"
        msg = f" ({result.message})" if result.message else ""
        print(f"  [{status}] {result.name}{msg}")

    print()
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"Results: {passed}/{total} passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
