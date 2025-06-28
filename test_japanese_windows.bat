@echo off
REM Test script for Japanese TTS on Windows

echo Testing Japanese TTS on Windows...
echo.

REM Test with Japanese text
echo 日本語のテストです | piper\bin\piper.exe --model test\models\ja_JP-test-medium.onnx --output_file test_japanese.wav

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Japanese TTS test failed
    echo Note: This is expected on Windows as OpenJTalk support is limited
    exit /b 1
) else (
    echo Japanese TTS test completed
    if exist test_japanese.wav (
        echo Output file created: test_japanese.wav
    ) else (
        echo WARNING: No output file created
    )
)