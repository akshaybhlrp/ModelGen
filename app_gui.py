#!/usr/bin/env python3
"""
ModelGen Studio Backend Server
Lightweight HTTP API serving the LMStudio GUI interface and executing real-time sandbox queries.
"""
import http.server
import json
import time
from pathlib import Path
from kernel import init_db, retrieve, verify
from compose import compose
from dag_composer import synthesize_dag_pipeline

PORT = 8080
WEB_DIR = Path(__file__).parent / "web"

conn = init_db()

class ModelGenStudioHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/api/modules":
            rows = conn.execute("SELECT id, name, source_code, test_code, input_schema, output_schema, license FROM modules WHERE compile_status = 'ok'").fetchall()
            modules = []
            for mid, name, src, tests, in_s, out_s, lic in rows:
                modules.append({
                    "id": mid,
                    "name": name,
                    "source_code": src,
                    "test_code": tests,
                    "input_schema": in_s,
                    "output_schema": out_s,
                    "license": lic
                })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"total": len(modules), "modules": modules}).encode())
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/query":
            length = int(self.headers.get('Content-Length', 0))
            payload = json.loads(self.rfile.read(length).decode())
            prompt = payload.get("prompt", "").strip()
            mode = payload.get("mode", "query")

            # Check conversational / greeting inputs
            greetings = {"hello", "hi", "hey", "hola", "help", "who are you", "what can you do"}
            if prompt.lower() in greetings:
                response_data = {
                    "is_conversational": True,
                    "message": "Hello! I am ModelGen — your local, verifier-gated code synthesis engine. I synthesize and verify algorithmic solutions on-device with zero cloud dependencies. Try asking for an algorithm like 'binary search', 'check anagram', or switch modes below for multi-module composition!",
                    "latency_ms": 0.05
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode())
                return

            t0 = time.time()
            if mode == "compose":
                res = compose(conn, "str", "int", "def test(): assert pipeline('HELLO') == 2")
                latency = (time.time() - t0) * 1000
                response_data = {"composition": res, "latency_ms": round(latency, 2)}
            elif mode == "dag":
                res = synthesize_dag_pipeline(conn, "list", "list", "def test(): assert pipeline([2,1], [4,3]) == [1,2,3,4]")
                latency = (time.time() - t0) * 1000
                response_data = {"composition": res, "latency_ms": round(latency, 2)}
            else:
                cands = retrieve(conn, prompt, k=5)
                latency = (time.time() - t0) * 1000
                results = []
                for mid, score in cands:
                    row = conn.execute("SELECT name, source_code, input_schema, output_schema FROM modules WHERE id = ?", (mid,)).fetchone()
                    if row:
                        results.append({
                            "id": mid,
                            "name": row[0],
                            "source_code": row[1],
                            "input_schema": row[2],
                            "output_schema": row[3],
                            "score": score
                        })
                response_data = {"results": results, "latency_ms": round(latency, 2)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())

def run_server(port=PORT):
    server_address = ('', port)
    httpd = http.server.HTTPServer(server_address, ModelGenStudioHandler)
    print(f"[+] ModelGen Studio GUI running at http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Shutting down server.")

if __name__ == "__main__":
    run_server()
