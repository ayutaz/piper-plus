#!/bin/bash

echo "=== CI Environment Debug Script ==="
echo "Date: $(date)"
echo "PWD: $(pwd)"
echo "Runner OS: ${RUNNER_OS:-local}"
echo ""

echo "=== Directory Structure ==="
echo "Looking for espeak-ng-data directories:"
find . -type d -name "espeak-ng-data" 2>/dev/null | while read dir; do
    echo "  Found: $dir"
    echo "  Size: $(du -sh "$dir" 2>/dev/null | cut -f1)"
    echo "  Files: $(find "$dir" -type f | wc -l)"
done
echo ""

echo "=== Build directory structure ==="
if [ -d "build" ]; then
    echo "build/"
    ls -la build/ | head -20
    
    if [ -d "build/pi" ]; then
        echo ""
        echo "build/pi/"
        ls -la build/pi/
        
        if [ -d "build/pi/share" ]; then
            echo ""
            echo "build/pi/share/"
            ls -la build/pi/share/
        fi
    fi
    
    if [ -d "build/ei" ]; then
        echo ""
        echo "build/ei/"
        ls -la build/ei/
        
        if [ -d "build/ei/share" ]; then
            echo ""
            echo "build/ei/share/"
            ls -la build/ei/share/
        fi
    fi
else
    echo "No build directory found"
fi
echo ""

echo "=== Piper binary check ==="
for piper_path in "piper/bin/piper" "build/piper" "build/Release/piper.exe" "build/piper.exe"; do
    if [ -f "$piper_path" ]; then
        echo "Found piper at: $piper_path"
        ls -la "$piper_path"
        
        # Check if it can run
        if [[ "$piper_path" == *.exe ]]; then
            echo "  Windows executable (cannot test on non-Windows)"
        else
            if "$piper_path" --version 2>&1; then
                echo "  Version check passed"
            else
                echo "  Version check failed: $?"
            fi
        fi
    fi
done
echo ""

echo "=== Environment Variables ==="
echo "ESPEAK_DATA_PATH: ${ESPEAK_DATA_PATH:-not set}"
echo "LD_LIBRARY_PATH: ${LD_LIBRARY_PATH:-not set}"
echo "DYLD_LIBRARY_PATH: ${DYLD_LIBRARY_PATH:-not set}"
echo "PATH: ${PATH}"
echo ""

echo "=== Test Model Check ==="
if [ -d "test/models" ]; then
    echo "Models in test/models:"
    ls -la test/models/ | head -10
else
    echo "No test/models directory found"
fi
echo ""

echo "=== Library Dependencies ==="
if [ "$(uname)" = "Linux" ]; then
    echo "Checking shared library dependencies:"
    for lib in "libespeak-ng" "libpiper_phonemize" "libonnxruntime"; do
        echo "  Looking for $lib:"
        find . -name "${lib}*.so*" -type f 2>/dev/null | head -5
    done
elif [ "$(uname)" = "Darwin" ]; then
    echo "Checking dynamic library dependencies:"
    for lib in "libespeak-ng" "libpiper_phonemize" "libonnxruntime"; do
        echo "  Looking for $lib:"
        find . -name "${lib}*.dylib" -type f 2>/dev/null | head -5
    done
fi
echo ""

echo "=== Debug Complete ==="