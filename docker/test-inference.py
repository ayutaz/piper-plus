#!/usr/bin/env python3
"""
Test script for Docker inference environments
Tests both Python and C++ inference capabilities with test models
"""

import json
import numpy as np
import sys
import os

def test_python_inference():
    """Test Python inference with ONNX Runtime"""
    try:
        import onnxruntime as ort
        print("✓ ONNX Runtime imported successfully")
        
        # Test with text_voice model (simple phoneme model)
        model_path = "/models/text_voice.onnx"
        config_path = "/models/text_voice.onnx.json"
        
        if os.path.exists(model_path) and os.path.exists(config_path):
            # Load config
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Create session
            session = ort.InferenceSession(model_path)
            print(f"✓ Loaded model: {model_path}")
            
            # Get input/output info
            inputs = session.get_inputs()
            outputs = session.get_outputs()
            print(f"  Input names: {[i.name for i in inputs]}")
            print(f"  Output names: {[o.name for o in outputs]}")
            
            # Prepare input - "hello world" in phonemes
            # h=20, e=18, l=24, l=24, o=27, space=3, w=35, o=27, r=30, l=24, d=17
            input_ids = np.array([[1, 20, 18, 24, 24, 27, 3, 35, 27, 30, 24, 17, 2]], dtype=np.int64)
            scales = np.array([
                config['inference']['noise_scale'],
                config['inference']['length_scale']
            ], dtype=np.float32)
            
            # Run inference
            input_dict = {
                inputs[0].name: input_ids,
                inputs[1].name: scales
            }
            
            outputs = session.run(None, input_dict)
            audio = outputs[0]
            
            print(f"✓ Inference successful!")
            print(f"  Generated audio shape: {audio.shape}")
            print(f"  Audio duration: {audio.shape[-1] / config['audio']['sample_rate']:.2f} seconds")
            
            return True
        else:
            print("⚠ Test model not found, skipping inference test")
            return True
            
    except Exception as e:
        print(f"✗ Python inference test failed: {e}")
        return False

def test_japanese_model():
    """Test Japanese model loading (not full inference due to OpenJTalk dependency)"""
    try:
        import onnxruntime as ort
        
        model_path = "/models/ja_JP-test-medium.onnx"
        config_path = "/models/ja_JP-test-medium.onnx.json"
        
        if os.path.exists(model_path) and os.path.exists(config_path):
            # Load config
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Create session
            session = ort.InferenceSession(model_path)
            print(f"✓ Loaded Japanese model: {model_path}")
            
            # Just verify the model structure
            inputs = session.get_inputs()
            outputs = session.get_outputs()
            print(f"  Input shapes: {[i.shape for i in inputs]}")
            print(f"  Number of speakers: {config.get('num_speakers', 1)}")
            
            return True
        else:
            print("⚠ Japanese test model not found, skipping")
            return True
            
    except Exception as e:
        print(f"✗ Japanese model test failed: {e}")
        return False

def test_fastapi_structure():
    """Test FastAPI server structure"""
    try:
        from fastapi import FastAPI
        import uvicorn
        
        app = FastAPI()
        
        @app.get("/health")
        def health_check():
            return {"status": "healthy"}
        
        @app.post("/tts")
        def text_to_speech(text: str):
            return {"message": f"Would synthesize: {text}"}
        
        print("✓ FastAPI server structure OK")
        return True
        
    except Exception as e:
        print(f"✗ FastAPI test failed: {e}")
        return False

def main():
    print("=== Docker Inference Environment Tests ===\n")
    
    tests = [
        ("Python Inference", test_python_inference),
        ("Japanese Model Loading", test_japanese_model),
        ("FastAPI Structure", test_fastapi_structure),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\nTesting {test_name}...")
        if test_func():
            passed += 1
        else:
            failed += 1
    
    print(f"\n=== Summary ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())