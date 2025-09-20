#!/bin/bash
# Fallback build script for ARMv7
# This script is used when Docker build fails

set -e

echo "Starting ARMv7 fallback build..."

# Update package list
apt-get update

# Install build dependencies (same as Dockerfile)
apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    wget \
    curl \
    ca-certificates \
    libsndfile1-dev

# Create build directory
mkdir -p build
cd build

# Configure with CMake
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTS=OFF

# Build with limited parallelism for ARM
make -j2

# Go back to workspace
cd ..

# Create distribution structure
mkdir -p dist/piper/bin dist/piper/lib dist/piper/share

# Copy binary
if [ -f "build/piper" ]; then
    cp build/piper dist/piper/bin/
    echo "Piper binary copied successfully"
else
    echo "ERROR: piper binary not found at build/piper"
    exit 1
fi

# Copy shared libraries
find build -name '*.so*' -type f -exec cp {} dist/piper/lib/ \; 2>/dev/null || true

# Download and install OpenJTalk dictionary
echo "Downloading OpenJTalk dictionary..."
curl -L -o open_jtalk_dic.tar.gz \
    "https://sourceforge.net/projects/open-jtalk/files/Dictionary/open_jtalk_dic-1.11/open_jtalk_dic_utf_8-1.11.tar.gz/download"

if [ -f "open_jtalk_dic.tar.gz" ]; then
    tar -xzf open_jtalk_dic.tar.gz
    mkdir -p dist/piper/share/open_jtalk
    mv open_jtalk_dic_utf_8-1.11 dist/piper/share/open_jtalk/dic
    rm -f open_jtalk_dic.tar.gz
    echo "OpenJTalk dictionary installed"
else
    echo "Warning: Failed to download OpenJTalk dictionary"
fi

# Download espeak-ng-data
echo "Downloading espeak-ng-data..."
wget -q -O espeak-ng-data.tar.gz \
    "https://github.com/rhasspy/espeak-ng/releases/download/2023.9.7-4/espeak-ng-data.tar.gz" || true

if [ -f "espeak-ng-data.tar.gz" ]; then
    tar -xzf espeak-ng-data.tar.gz
    mkdir -p dist/piper/share
    mv espeak-ng-data dist/piper/share/
    rm -f espeak-ng-data.tar.gz
    echo "espeak-ng-data installed"
else
    echo "Warning: Failed to download espeak-ng-data"
fi

# Create tarball
cd dist
tar czf piper-linux-armv7.tar.gz piper/
echo "Created piper-linux-armv7.tar.gz successfully"
ls -la piper-linux-armv7.tar.gz