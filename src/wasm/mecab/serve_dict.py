#!/usr/bin/env python3
"""
NAIST-JDIC Dictionary Server for MeCab WebAssembly
Serves dictionary files with proper CORS headers and compression support
"""

import http.server
import socketserver
import os
import gzip
from pathlib import Path

PORT = 8082
DICT_PATH = "dict/naist-jdic"

class DictionaryHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        
        # Cache headers for dictionary files
        if self.path.endswith(('.dic', '.bin', '.def')):
            self.send_header('Cache-Control', 'public, max-age=31536000')  # 1 year
        
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()
    
    def do_GET(self):
        # Check if gzipped version exists
        if self.path.endswith('.dic') or self.path.endswith('.bin'):
            gz_path = self.path + '.gz'
            full_gz_path = self.translate_path(gz_path)
            
            if os.path.exists(full_gz_path):
                # Serve gzipped version if client accepts it
                accept_encoding = self.headers.get('Accept-Encoding', '')
                if 'gzip' in accept_encoding:
                    self.path = gz_path
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Encoding', 'gzip')
                    self.end_headers()
                    
                    with open(full_gz_path, 'rb') as f:
                        self.wfile.write(f.read())
                    return
        
        # Fall back to normal serving
        super().do_GET()

def compress_dictionary_files():
    """Compress dictionary files if not already compressed"""
    dict_dir = Path(DICT_PATH)
    if not dict_dir.exists():
        print(f"Dictionary directory {DICT_PATH} not found!")
        return
    
    files_to_compress = ['sys.dic', 'matrix.bin', 'char.bin']
    
    for filename in files_to_compress:
        filepath = dict_dir / filename
        gz_filepath = dict_dir / f"{filename}.gz"
        
        if filepath.exists() and not gz_filepath.exists():
            print(f"Compressing {filename}...")
            with open(filepath, 'rb') as f_in:
                with gzip.open(gz_filepath, 'wb', compresslevel=9) as f_out:
                    f_out.write(f_in.read())
            
            original_size = filepath.stat().st_size
            compressed_size = gz_filepath.stat().st_size
            ratio = (1 - compressed_size / original_size) * 100
            print(f"  Compressed {filename}: {original_size:,} → {compressed_size:,} bytes ({ratio:.1f}% reduction)")

if __name__ == "__main__":
    # Compress files first
    compress_dictionary_files()
    
    # Start server
    with socketserver.TCPServer(("", PORT), DictionaryHTTPRequestHandler) as httpd:
        print(f"Serving dictionary files at http://localhost:{PORT}")
        print(f"Dictionary path: {os.path.abspath(DICT_PATH)}")
        print("Press Ctrl+C to stop")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")