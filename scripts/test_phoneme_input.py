#!/usr/bin/env python3
"""Test script for phoneme input functionality"""

import os
import subprocess
import sys
import tempfile


def test_phoneme_input(piper_binary, model_path):
    """Test various phoneme input scenarios"""
    tests = [
        {
            "name": "Plain text",
            "input": "Hello world",
            "description": "Regular text without phoneme notation",
        },
        {
            "name": "Single phoneme notation",
            "input": "[[ h ə l oʊ ]]",
            "description": "Direct phoneme input only",
        },
        {
            "name": "Mixed text and phonemes",
            "input": "Hello [[ h ə l oʊ ]] world",
            "description": "Text with embedded phoneme notation",
        },
        {
            "name": "Multiple phoneme notations",
            "input": "Say [[ h ə l oʊ ]] and [[ w ɝ l d ]]",
            "description": "Multiple phoneme segments",
        },
        {
            "name": "Japanese phonemes",
            "input": "こんにちは [[ k o N n i ch i w a ]] です",
            "description": "Japanese text with phoneme notation",
        },
        {
            "name": "Japanese multi-char phonemes",
            "input": "[[ ky a sh a ]]",
            "description": "Japanese multi-character phonemes",
        },
    ]

    results = []
    for test in tests:
        print(f"\nRunning test: {test['name']}")
        print(f"Input: {test['input']}")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            output_path = tmp_file.name
        try:
            # Run piper
            process = subprocess.Popen(
                [piper_binary, "--model", model_path, "--output_file", output_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            stdout, stderr = process.communicate(input=test["input"])
            # Check if audio file was created
            success = os.path.exists(output_path) and os.path.getsize(output_path) > 0
            result = {
                "test": test["name"],
                "success": success,
                "output_size": os.path.getsize(output_path) if success else 0,
                "return_code": process.returncode,
                "stderr": stderr.strip() if stderr else None,
            }
            if success:
                print(f"✓ Success: Generated {result['output_size']} bytes")
            else:
                print(f"✗ Failed: {result['stderr']}")

            results.append(result)
        finally:
            # Clean up
            if os.path.exists(output_path):
                os.unlink(output_path)

    return results


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <piper_binary> <model_path>")
        sys.exit(1)

    piper_binary = sys.argv[1]
    model_path = sys.argv[2]
    if not os.path.exists(piper_binary):
        print(f"Error: Piper binary not found: {piper_binary}")
        sys.exit(1)

    if not os.path.exists(model_path):
        print(f"Error: Model file not found: {model_path}")
        sys.exit(1)

    print("Testing phoneme input with:")
    print(f"  Binary: {piper_binary}")
    print(f"  Model: {model_path}")

    results = test_phoneme_input(piper_binary, model_path)
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)

    passed = sum(1 for r in results if r["success"])
    total = len(results)
    for result in results:
        status = "PASS" if result["success"] else "FAIL"
        print(f"{status}: {result['test']}")
        if not result["success"] and result["stderr"]:
            print(f"     Error: {result['stderr']}")

    print(f"\nTotal: {passed}/{total} tests passed")
    # Exit with error if any test failed
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
