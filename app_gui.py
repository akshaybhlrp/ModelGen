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

from conversational_bridge import ConversationalBridge

PORT = 8080
WEB_DIR = Path(__file__).parent / "web"

conn = init_db()
bridge = ConversationalBridge(conn)

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
                conv_res = bridge.process_message(prompt)
                latency = (time.time() - t0) * 1000
                if conv_res["type"] == "chat":
                    response_data = {
                        "is_conversational": True,
                        "message": conv_res["message"],
                        "latency_ms": round(latency, 2)
                    }
                else:
                    response_data = {
                        "is_conversational": True,
                        "message": conv_res["message"],
                        "results": [{
                            "name": conv_res.get("name", "Verified Solution"),
                            "source_code": conv_res["code"],
                            "score": 100
                        }],
                        "latency_ms": round(latency, 2)
                    }

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
