#!/bin/bash
# MeCab Server Startup Script

echo "MeCab Server セットアップ"
echo "========================"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python3 is not installed"
    exit 1
fi

# Install dependencies if needed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
fi

# Check if MeCab is installed
if ! python3 -c "import MeCab" 2>/dev/null; then
    echo "MeCab Python binding not found. Installing..."
    pip3 install mecab-python3 unidic-lite
fi

# Start server
echo "Starting MeCab server on port 5000..."
python3 mecab_server.py