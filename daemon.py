#!/usr/bin/env python3
"""
ModelGen Continuous Ingestion Daemon
Continuously harvests, decontaminates, mutation-tests, and indexes verified Python algorithms.
"""
import os
import sys
import time
import sqlite3
from kernel import init_db
from harvester import harvest_batch
from mutation_tester import run_library_mutation_audit
from decontaminate import run_decontamination_audit
from pruner import prune_redundant_modules

TOPICS = [
    "language:python def test_ sort in:file",
    "language:python def test_ search in:file",
    "language:python def test_ graph in:file",
    "language:python def test_ tree in:file",
    "language:python def test_ string in:file",
    "language:python def test_ matrix in:file",
    "language:python def test_ dynamic in:file",
    "language:python def test_ math in:file"
]

def run_daemon_cycle(conn, token: str):
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting background harvesting cycle...")
    
    # 1. Harvesting pass
    harvest_batch(conn, TOPICS, token=token, max_pages_per_topic=2)
    
    # 2. Decontamination audit
    run_decontamination_audit(conn)
    
    # 3. Mutation testing & weak test quarantine
    run_library_mutation_audit(conn, quarantine_weak=True)
    
    # 4. AST deduplication & pruning
    prune_redundant_modules(conn)
    
    total = conn.execute("SELECT COUNT(*) FROM modules WHERE compile_status = 'ok'").fetchone()[0]
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Cycle complete. Total active verified modules: {total}")

if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN", "")
    conn = init_db()
    
    # Single execution cycle
    run_daemon_cycle(conn, token)
