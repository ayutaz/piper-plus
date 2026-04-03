#!/usr/bin/env python3
"""
Simple HTTP server for testing multilingual TTS demo
"""

import http.server
import os
import socketserver
import sys


PORT = 8080
DIRECTORY = os.path.dirname(os.path.abspath(__file__))


class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        # Add CORS headers for testing
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # Add headers for WebAssembly
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()


def main():
    os.chdir(DIRECTORY)

    with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
        print(f"Server started at http://localhost:{PORT}")
        print(f"Serving directory: {DIRECTORY}")
        print("\nTest URLs:")
        print(
            f"  - Simple Multilingual Demo: http://localhost:{PORT}/demo/simple-multilingual.html"
        )
        print(f"  - Japanese Demo: http://localhost:{PORT}/demo/index.html")
        print("\nPress Ctrl+C to stop")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped")
            sys.exit(0)


if __name__ == "__main__":
    main()
