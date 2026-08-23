#!/usr/bin/env python3
import json
import time
from pathlib import Path
from kernel import init_db, retrieve, verify, input_hash, update_counter

BENCHMARK_FILE = Path("benchmarks_50.json")

def load_benchmarks():
    with open(BENCHMARK_FILE) as f:
        return json.load(f)

def run_evaluation(conn, k=10):
    problems = load_benchmarks()
    print(f"[+] Loaded {len(problems)} held-out problems from {BENCHMARK_FILE}")
    
    total_stored = conn.execute("SELECT COUNT(*) FROM modules WHERE compile_status = 'ok'").fetchone()[0]
    print(f"[+] Currently verified modules in library: {total_stored}")

    correct = 0
    latencies = []
    category_scores = {}

    for p in problems:
        cat = p.get("category", "general")
        if cat not in category_scores:
            category_scores[cat] = {"total": 0, "correct": 0}
        category_scores[cat]["total"] += 1

        t0 = time.time()
        cands = retrieve(conn, p["desc"], k)
        latencies.append(time.time() - t0)

        found = False
        for mid, _ in cands:
            row = conn.execute("SELECT source_code FROM modules WHERE id = ?", (mid,)).fetchone()
            if row and verify(row[0], p["tests"]):
                correct += 1
                category_scores[cat]["correct"] += 1
                update_counter(conn, input_hash(p["desc"]), mid, True)
                found = True
                break
            else:
                update_counter(conn, input_hash(p["desc"]), mid, False)

    recall = correct / len(problems) if problems else 0
    p99 = sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0

    print("\n" + "=" * 50)
    print("           MVO-0 EVALUATION REPORT                ")
    print("=" * 50)
    print(f"Verified Library Size : {total_stored} modules")
    print(f"Overall Recall@{k}      : {recall:.2%} ({correct}/{len(problems)})")
    print(f"P99 Query Latency     : {p99 * 1000:.2f} ms")
    print("-" * 50)
    print("Category Breakdown:")
    for cat, sc in category_scores.items():
        pct = sc["correct"] / sc["total"] if sc["total"] else 0
        print(f"  - {cat:<18}: {sc['correct']}/{sc['total']} ({pct:.1%})")
    print("-" * 50)
    status = "PASS" if (recall >= 0.30 and p99 < 0.1) else "IN PROGRESS (Needs more harvesting)"
    print(f"MVO-0 Gate Status     : {status}")
    print("=" * 50)
    return recall, p99

if __name__ == "__main__":
    conn = init_db()
    run_evaluation(conn, k=10)
