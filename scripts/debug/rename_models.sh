#!/bin/bash
# Rename model files for CI testing

cd /Users/s19447/Desktop/piper

# Rename the model files
mv test/models/css10_ja_epoch2099.onnx test/models/ja_JP-test-medium.onnx
mv test/models/css10_ja_epoch2099.onnx.json test/models/ja_JP-test-medium.onnx.json

echo "Model files renamed successfully"
ls -la test/models/ja_JP-test-medium.*