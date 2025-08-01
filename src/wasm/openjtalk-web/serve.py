#!/usr/bin/env python3
"""Simple HTTP server for testing WebAssembly modules"""

import http.server
import os
import socketserver


class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

        # Add proper MIME types
        if self.path.endswith(".wasm"):
            self.send_header("Content-Type", "application/wasm")
        elif self.path.endswith(".js"):
            self.send_header("Content-Type", "application/javascript")

        super().end_headers()


if __name__ == "__main__":
    PORT = 8080

    # Change to the dist directory
    os.chdir("dist")

    with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
        print(f"Server running at http://localhost:{PORT}/")
        print(f"Test page: http://localhost:{PORT}/test.html")
        print("Press Ctrl+C to stop...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
