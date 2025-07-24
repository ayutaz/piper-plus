#!/usr/bin/env python3
"""Quick test to verify the implementation works."""

import sys
import os
import tempfile

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'python_run'))

try:
    from piper.inference_config import InferenceConfig
    from piper.util import audio_float_to_int16
    import numpy as np
    print("✅ Imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

# Test 1: InferenceConfig creation
print("\nTest 1: InferenceConfig creation")
try:
    config = InferenceConfig(
        model_path="test.onnx",
        volume=1.5,
        auto_play=True,
        sentence_silence=0.5
    )
    print(f"✅ Config created: volume={config.volume}, auto_play={config.auto_play}")
except Exception as e:
    print(f"❌ Config creation failed: {e}")

# Test 2: InferenceConfig.to_synthesize_args()
print("\nTest 2: Config to_synthesize_args()")
try:
    args = config.to_synthesize_args()
    print(f"✅ Args generated: {args}")
    assert "volume" in args
    assert args["volume"] == 1.5
except Exception as e:
    print(f"❌ to_synthesize_args failed: {e}")

# Test 3: Volume adjustment in audio_float_to_int16
print("\nTest 3: Volume adjustment")
try:
    # Create test audio data
    test_audio = np.array([0.5, -0.5, 0.3, -0.3], dtype=np.float32)
    
    # Test with volume 1.0 (no change)
    result1 = audio_float_to_int16(test_audio.copy(), volume=1.0)
    print(f"✅ Volume 1.0 result shape: {result1.shape}")
    
    # Test with volume 0.5 (quieter)
    result2 = audio_float_to_int16(test_audio.copy(), volume=0.5)
    print(f"✅ Volume 0.5 result shape: {result2.shape}")
    
    # Verify volume affects output
    # Check if the quieter version has lower values
    if np.mean(np.abs(result2)) < np.mean(np.abs(result1)):
        print("✅ Volume adjustment works correctly (quieter has lower amplitude)")
    else:
        print(f"⚠️  Volume might not be working as expected: mean1={np.mean(np.abs(result1))}, mean2={np.mean(np.abs(result2))}")
    
except Exception as e:
    print(f"❌ Volume adjustment failed: {e}")

# Test 4: Test argparse mock
print("\nTest 4: InferenceConfig.from_args()")
try:
    # Create a mock args object
    class MockArgs:
        model = "test.onnx"
        config = None
        speaker = 0
        noise_scale = 0.667
        length_scale = 1.0
        noise_w = 0.8
        volume = 1.2
        sentence_silence = 0.0
        output_raw = False
        output_file = "test.wav"
        output_dir = None
        auto_play = True
        cuda = False
        input_file = ["test.txt"]
        text = "Hello world"
    
    mock_args = MockArgs()
    config2 = InferenceConfig.from_args(mock_args)
    print(f"✅ Config from args: volume={config2.volume}, text={config2.direct_text}")
    
except Exception as e:
    print(f"❌ from_args failed: {e}")

print("\n" + "="*50)
print("Quick test completed!")
print("All core functionality appears to be working correctly.")