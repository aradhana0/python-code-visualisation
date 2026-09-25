"""Tiny stdlib-only web server for the Python code visualiser.

    python server.py [--port 8000]

Serves the frontend from ./static and exposes ``POST /api/trace`` which runs
the submitted code in a separate, time- and memory-limited Python process.

NOTE: the submitted code is real Python running on this machine.  The limits
stop runaway programs, not malicious ones - run this locally, not on the
public internet.
"""

import argparse
import json
import os
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(HERE, "static")
TRACER = os.path.join(HERE, "tracer.py")
TIMEOUT_SECONDS = 10
MAX_CODE_BYTES = 50_000


def run_trace(code, stdin=""):
    payload = json.dumps({"code": code, "stdin": stdin})
    try:
        proc = subprocess.run(
            [sys.executable, "-I", TRACER],
            input=payload,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"steps": [], "error": {"type": "Timeout", "message":
                "Program took longer than %d seconds." % TIMEOUT_SECONDS, "line": None}}
    if proc.returncode != 0 or not proc.stdout:
        detail = (proc.stderr or "").strip().splitlines()
        return {"steps": [], "error": {"type": "TracerError", "message":
                detail[-1] if detail else "Tracer crashed (memory or CPU limit?)", "line": None}}
    return json.loads(proc.stdout)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_POST(self):
        if self.path != "/api/trace":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_CODE_BYTES * 2:
            self.send_error(413, "Code too large")
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            code = str(body.get("code", ""))
            stdin = str(body.get("stdin", ""))
        except (ValueError, AttributeError):
            self.send_error(400, "Expected a JSON body")
            return
        if len(code.encode()) > MAX_CODE_BYTES:
            self.send_error(413, "Code too large")
            return

        data = json.dumps(run_trace(code, stdin)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("Python visualiser running at http://%s:%d" % (args.host, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
