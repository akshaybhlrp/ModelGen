#!/usr/bin/env python3
import ast
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

DB_PATH = Path("frontier.db")

def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS modules (
            id INTEGER PRIMARY KEY,
            content_hash BLOB UNIQUE,
            name TEXT,
            source_code TEXT,
            test_code TEXT,
            input_schema TEXT DEFAULT 'Any',
            output_schema TEXT DEFAULT 'Any',
            is_template BOOLEAN DEFAULT 0,
            parameters TEXT,
            license TEXT,
            source_url TEXT,
            compile_status TEXT DEFAULT 'pending',
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS routing_counters (
            input_hash BLOB,
            module_id INTEGER,
            counter INTEGER DEFAULT 0,
            PRIMARY KEY (input_hash, module_id)
        );
        CREATE TABLE IF NOT EXISTS simhash_index (
            module_id INTEGER PRIMARY KEY,
            simhash INTEGER
        );
    ''')
    conn.commit()
    return conn

def content_hash(data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=32).digest()

def normalize(text: str) -> str:
    return ' '.join(text.lower().split())

def input_hash(text: str) -> bytes:
    return hashlib.sha256(normalize(text).encode()).digest()

def compute_simhash(text: str) -> int:
    tokens = normalize(text).split()
    if not tokens:
        return 0
    v = [0] * 64
    for t in tokens:
        h = int(hashlib.md5(t.encode()).hexdigest()[:16], 16)
        for i in range(64):
            v[i] += 1 if (h & (1 << i)) else -1
    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= (1 << i)
    # Convert to signed 64-bit int for SQLite compatibility
    if fingerprint >= (1 << 63):
        fingerprint -= (1 << 64)
    return fingerprint

def verify(source: str, tests: str, timeout: float = 2.0) -> bool:
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "test_run.py"
        test_wrapper = (
            source + "\n\n" + tests + 
            "\n\nif __name__ == '__main__':\n"
            "    for k, v in list(globals().items()):\n"
            "        if (k.startswith('test_') or k == 'test') and callable(v):\n"
            "            v()\n"
        )
        p.write_text(test_wrapper)
        try:
            r = subprocess.run([sys.executable, str(p)],
                               capture_output=True, timeout=timeout, text=True)
            return r.returncode == 0
        except Exception:
            return False

def store(conn, name: str, source: str, tests: str, license_type: str, url: str, input_schema: str = "Any", output_schema: str = "Any") -> int:
    h = content_hash(source.encode())
    if not verify(source, tests):
        return 0
    try:
        cur = conn.execute(
            """INSERT OR IGNORE INTO modules 
               (content_hash, name, source_code, test_code, input_schema, output_schema, license, source_url, compile_status) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ok')""",
            (h, name, source, tests, input_schema, output_schema, license_type, url))
        mid = cur.lastrowid
        if mid:
            sh = compute_simhash(source)
            conn.execute("INSERT OR REPLACE INTO simhash_index (module_id, simhash) VALUES (?, ?)", (mid, sh))
            conn.commit()
            return mid
    except sqlite3.Error:
        pass
    return 0

def retrieve(conn, query: str, k: int = 10):
    qh = input_hash(query)
    # Tier 1: Exact counter routing
    rows = conn.execute(
        "SELECT module_id, counter FROM routing_counters WHERE input_hash = ? ORDER BY counter DESC LIMIT ?",
        (qh, k)).fetchall()
    if rows:
        return rows
    # Tier 2: SimHash LSH nearest neighbor
    q_sh = compute_simhash(query)
    all_mods = conn.execute("SELECT module_id, simhash FROM simhash_index").fetchall()
    scored = []
    for mid, sh in all_mods:
        dist = bin(q_sh ^ sh).count('1')
        scored.append((mid, max(0, 64 - dist)))
    scored.sort(key=lambda x: x[1], reverse=True)
    if scored and scored[0][1] > 0:
        return scored[:k]
    # Tier 3: Recent compiled modules fallback
    return conn.execute("SELECT id, 0 FROM modules WHERE compile_status = 'ok' ORDER BY fetched_at DESC LIMIT ?", (k,)).fetchall()

def update_counter(conn, ih: bytes, mid: int, success: bool):
    d = 1 if success else -1
    conn.execute(
        """INSERT INTO routing_counters (input_hash, module_id, counter) VALUES (?, ?, ?) 
           ON CONFLICT(input_hash, module_id) DO UPDATE SET counter = max(0, counter + ?)""",
        (ih, mid, max(0, d), d))
    conn.commit()

if __name__ == "__main__":
    conn = init_db()
    print("Database initialized at", DB_PATH)
