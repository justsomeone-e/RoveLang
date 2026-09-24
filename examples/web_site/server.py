#!/usr/bin/env python3
"""Lightweight local development HTTP server for Rove WebAssembly website."""

import http.server
import mimetypes
import os
import socketserver
import sys
import webbrowser

# Ensure WebAssembly and modern JS MIME types are recognized
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/plain", ".wat")


class RoveWasmHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS and isolation headers for WebAssembly / SharedArrayBuffer if needed
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()

    def guess_type(self, path):
        if path.endswith(".wasm"):
            return "application/wasm"
        if path.endswith(".mjs"):
            return "application/javascript"
        if path.endswith(".wat"):
            return "text/plain"
        return super().guess_type(path)


def run_server(port=8080, open_browser=True):
    site_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(site_dir)

    # Try ports starting from requested port
    actual_port = port
    server = None
    while actual_port < port + 20:
        try:
            server = socketserver.TCPServer(("", actual_port), RoveWasmHandler)
            break
        except OSError:
            actual_port += 1

    if server is None:
        print(f"[!] Could not find an open port between {port} and {port + 20}")
        sys.exit(1)

    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    url = f"http://localhost:{actual_port}/index.html"
    print("=" * 68)
    print("[*] ROVE WEBASSEMBLY INTERACTIVE PORTAL")
    print("=" * 68)
    print(f"[*] Serving site directory: {site_dir}")
    print(f"[*] URL: {url}")
    print("[*] Press Ctrl+C to stop the server.")
    print("=" * 68)

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server stopped.")
        server.server_close()


if __name__ == "__main__":
    no_browser = "--no-browser" in sys.argv
    port_arg = 8080
    for arg in sys.argv[1:]:
        if arg.isdigit():
            port_arg = int(arg)
    run_server(port=port_arg, open_browser=not no_browser)
