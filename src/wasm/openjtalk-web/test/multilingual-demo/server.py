#!/usr/bin/env python3
"""
Simple HTTP server for testing OpenJTalk WebAssembly demo
Serves with proper CORS and MIME types for WASM
"""

import http.server
import os
import socketserver
from pathlib import Path


PORT = 8080


class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # Required for SharedArrayBuffer if needed in future
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def guess_type(self, path):
        mimetype = super().guess_type(path)
        # Set proper MIME type for WebAssembly
        if path.endswith(".wasm"):
            return "application/wasm"
        return mimetype


def main():
    # Change to demo directory
    demo_dir = Path(__file__).parent
    os.chdir(demo_dir)

    with socketserver.TCPServer(("", PORT), CORSRequestHandler) as httpd:
        print("OpenJTalk WebAssembly Demo Server")
        print(f"Serving at: http://localhost:{PORT}")
        print("Demo page: http://localhost:{PORT}/index.html")
        print("")
        print("Press Ctrl+C to stop the server")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")


if __name__ == "__main__":
    main()
