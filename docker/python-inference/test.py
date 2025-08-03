#!/usr/bin/env python3
"""
Test script for python-inference container
Verifies that inference functionality works correctly
"""

import sys
import tempfile

def test_imports():
    """Test that all required packages can be imported"""
    print("Testing package imports...")
    
    required_packages = [
        "numpy",
        "onnxruntime",
        "soundfile",
        "piper",
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

def test_onnx_runtime():
    """Test ONNX Runtime functionality"""
    print("\nTesting ONNX Runtime...")
    try:
        import onnxruntime as ort
        
        # Check available providers
        providers = ort.get_available_providers()
        print(f"Available providers: {providers}")
        
        # Check CUDA availability
        if 'CUDAExecutionProvider' in providers:
            print("✓ CUDA provider available")
        else:
            print("ℹ CUDA provider not available (using CPU)")
        
        print("✓ ONNX Runtime test passed")
        return True
    except Exception as e:
        print(f"✗ ONNX Runtime test failed: {e}")
        return False

def test_piper_basic():
    """Test basic piper functionality"""
    print("\nTesting piper library...")
    try:
        import piper
        
        # Test that we can access PiperVoice class
        assert hasattr(piper, 'PiperVoice')
        print("✓ PiperVoice class available")
        
        # Test synthesis method exists
        print("✓ piper library test passed")
        return True
    except Exception as e:
        print(f"✗ piper library test failed: {e}")
        return False

def test_inference_script():
    """Test the inference.py script"""
    print("\nTesting inference.py script...")
    try:
        # Import the inference module
        import inference
        
        # Check required functions exist
        assert hasattr(inference, 'synthesize_text')
        print("✓ synthesize_text function available")
        
        assert hasattr(inference, 'main')
        print("✓ main function available")
        
        print("✓ inference.py test passed")
        return True
    except Exception as e:
        print(f"✗ inference.py test failed: {e}")
        return False

def test_soundfile():
    """Test soundfile functionality"""
    print("\nTesting soundfile...")
    try:
        import soundfile as sf
        import numpy as np
        
        # Create temporary test file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=True) as tmp:
            # Generate test audio
            sample_rate = 22050
            duration = 0.1  # 100ms
            samples = int(sample_rate * duration)
            audio = np.random.uniform(-0.5, 0.5, samples).astype(np.float32)
            
            # Write and read back
            sf.write(tmp.name, audio, sample_rate)
            data, sr = sf.read(tmp.name)
            
            assert sr == sample_rate
            assert len(data) == samples
            print("✓ soundfile test passed")
            return True
    except Exception as e:
        print(f"✗ soundfile test failed: {e}")
        return False

def main():
    print("=== Python Inference Container Test ===\n")
    
    tests = [
        ("Package imports", test_imports),
        ("ONNX Runtime", test_onnx_runtime),
        ("Piper library", test_piper_basic),
        ("Inference script", test_inference_script),
        ("Soundfile I/O", test_soundfile),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        results.append(test_func())
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n=== Summary ===")
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())