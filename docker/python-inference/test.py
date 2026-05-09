#!/usr/bin/env python3
"""
Test script for python-inference container.
Verifies that inference functionality works correctly.
"""

import sys
import tempfile


def test_imports():
    """Test that all required packages can be imported."""
    print("Testing package imports...")

    required_packages = [
        "numpy",
        "onnxruntime",
        "soundfile",
        "piper_train",
        "piper_train.infer_onnx",
        "piper_plus_g2p.registry",
    ]

    failed = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"  OK {package}")
        except ImportError as e:
            print(f"  FAIL {package}: {e}")
            failed.append(package)

    return len(failed) == 0


def test_onnx_runtime():
    """Test ONNX Runtime functionality."""
    print("\nTesting ONNX Runtime...")
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        print(f"  Available providers: {providers}")
        print("  OK ONNX Runtime")
        return True
    except Exception as e:
        print(f"  FAIL ONNX Runtime: {e}")
        return False


def test_phonemizer():
    """Test phonemizer registry."""
    print("\nTesting phonemizer registry...")
    try:
        from piper_plus_g2p.registry import available_languages, get_phonemizer

        langs = available_languages()
        print(f"  Available languages: {langs}")

        if "ja" in langs:
            p = get_phonemizer("ja")
            print(f"  OK Japanese phonemizer: {type(p).__name__}")

        if "en" in langs:
            p = get_phonemizer("en")
            print(f"  OK English phonemizer: {type(p).__name__}")

        return True
    except Exception as e:
        print(f"  FAIL phonemizer: {e}")
        return False


def test_inference_script():
    """Test the inference.py script can be imported."""
    print("\nTesting inference.py script...")
    try:
        import inference

        assert hasattr(inference, "PiperInferenceEngine")
        print("  OK PiperInferenceEngine class available")

        assert hasattr(inference, "main")
        print("  OK main function available")

        return True
    except Exception as e:
        print(f"  FAIL inference.py: {e}")
        return False


def test_soundfile():
    """Test soundfile read/write."""
    print("\nTesting soundfile...")
    try:
        import numpy as np
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            sample_rate = 22050
            samples = int(sample_rate * 0.1)
            audio = np.random.uniform(-0.5, 0.5, samples).astype(np.float32)

            sf.write(tmp.name, audio, sample_rate)
            data, sr = sf.read(tmp.name)

            assert sr == sample_rate
            assert len(data) == samples
            print("  OK soundfile read/write")
            return True
    except Exception as e:
        print(f"  FAIL soundfile: {e}")
        return False


def main():
    print("=== Python Inference Container Test ===\n")

    tests = [
        ("Package imports", test_imports),
        ("ONNX Runtime", test_onnx_runtime),
        ("Phonemizer", test_phonemizer),
        ("Inference script", test_inference_script),
        ("Soundfile I/O", test_soundfile),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"--- {test_name} ---")
        results.append(test_func())

    passed = sum(results)
    total = len(results)

    print(f"\n=== Summary: {passed}/{total} passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
