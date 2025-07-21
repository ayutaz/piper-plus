#!/usr/bin/env python3
import http.server
import socketserver
import os
from pathlib import Path

PORT = 8080

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers for WebAssembly
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        # Proper MIME types
        if self.path.endswith('.wasm'):
            self.send_header('Content-Type', 'application/wasm')
        elif self.path.endswith('.js'):
            self.send_header('Content-Type', 'application/javascript')
        super().end_headers()

# Change to the mecab directory
mecab_dir = Path(__file__).parent.parent
os.chdir(mecab_dir)

print(f"Serving MeCab WebAssembly demo from: {mecab_dir}")
print(f"Server running at http://localhost:{PORT}/test/")
print(f"Open http://localhost:{PORT}/test/index.html in Chrome")

with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
    httpd.serve_forever()