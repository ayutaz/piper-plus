#!/usr/bin/env python3
"""
Test script for python-train container
Verifies that all required packages are installed and functional
"""

import sys


def test_imports():
    """Test that all required packages can be imported"""
    print("Testing package imports...")

    required_packages = [
        "torch",
        "torchaudio",
        "torchvision",
        "numpy",
        "scipy",
        "matplotlib",
        "tensorboard",
        "wandb",
        "piper_train",
    ]

    failed = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package}")
        except ImportError as e:
            print(f"✗ {package}: {e}")
            failed.append(package)

    return len(failed) == 0


def test_cuda():
    """Test CUDA availability"""
    print("\nTesting CUDA...")
    try:
        import torch  # noqa: PLC0415

        cuda_available = torch.cuda.is_available()
        device_count = torch.cuda.device_count()

        print(f"CUDA available: {cuda_available}")
        print(f"CUDA device count: {device_count}")

        if cuda_available and device_count > 0:
            print(f"CUDA device name: {torch.cuda.get_device_name(0)}")
            print("✓ CUDA test passed")
            return True
        else:
            print("✗ CUDA not available")
            return False
    except Exception as e:
        print(f"✗ CUDA test failed: {e}")
        return False


def test_piper_train():
    """Test piper_train installation"""
    print("\nTesting piper_train...")
    try:
        from piper_train import preprocess  # noqa: PLC0415, F401
        from piper_train.vits.models import SynthesizerTrn  # noqa: PLC0415, F401

        print("✓ piper_train modules accessible")
        return True
    except Exception as e:
        print(f"✗ piper_train test failed: {e}")
        return False


def main():
    print("=== Python Train Container Test ===\n")

    tests = [
        ("Package imports", test_imports),
        ("CUDA functionality", test_cuda),
        ("Piper train modules", test_piper_train),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        results.append(test_func())

    passed = sum(results)
    total = len(results)

    print("\n=== Summary ===")
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
