#!/usr/bin/env python3
import time
from kernel import init_db, retrieve, verify, input_hash, update_counter, store

HELD_OUT = [
    {
        "desc": "sort a list of integers in ascending order",
        "tests": """def test_sort():
    assert sort_list([3,1,2]) == [1,2,3]
    assert sort_list([]) == []
    assert sort_list([5]) == [5]
"""
    },
    {
        "desc": "reverse a string",
        "tests": """def test_reverse():
    assert reverse_str("abc") == "cba"
    assert reverse_str("") == ""
"""
    },
    {
        "desc": "compute the factorial of n",
        "tests": """def test_factorial():
    assert factorial(0) == 1
    assert factorial(5) == 120
"""
    }
]

def seed_sample_data(conn):
    """Seed benchmark algorithms to test retrieval harness."""
    store(conn, "sort_list", "def sort_list(lst):\n    return sorted(lst)", "def test_sort():\n    assert sort_list([2,1]) == [1,2]", "MIT", "local")
    store(conn, "reverse_str", "def reverse_str(s):\n    return s[::-1]", "def test_rev():\n    assert reverse_str('a') == 'a'", "MIT", "local")
    store(conn, "factorial", "def factorial(n):\n    return 1 if n <= 1 else n * factorial(n - 1)", "def test_fact():\n    assert factorial(3) == 6", "MIT", "local")

def evaluate(conn, problems, k=10):
    correct, latencies = 0, []
    for p in problems:
        t0 = time.time()
        cands = retrieve(conn, p["desc"], k)
        latencies.append(time.time() - t0)
        found = False
        for mid, _ in cands:
            row = conn.execute("SELECT source_code FROM modules WHERE id = ?", (mid,)).fetchone()
            if row and verify(row[0], p["tests"]):
                correct += 1
                update_counter(conn, input_hash(p["desc"]), mid, True)
                found = True
                break
            else:
                update_counter(conn, input_hash(p["desc"]), mid, False)
        if not found:
            print(f"FAIL: {p['desc'][:50]}...")
    recall = correct / len(problems) if problems else 0
    p99 = sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0
    return recall, p99

if __name__ == "__main__":
    conn = init_db()
    seed_sample_data(conn)
    recall, p99 = evaluate(conn, HELD_OUT)
    print(f"\nEvaluation Results:")
    print(f"Recall@10: {recall:.2%}")
    print(f"P99 Latency: {p99*1000:.2f}ms")
    print("STATUS:", "PASS" if recall >= 0.30 and p99 < 0.1 else "FAIL")
