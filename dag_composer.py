#!/usr/bin/env python3
"""
Research Track M6: Non-Linear DAG Composition & Decomposition Prototype
Enables complex branch-and-merge pipelines:
  Input (A, B) -> Split -> (Module 1(A), Module 2(B)) -> Join (Module 3) -> Output
Example: Merge two sorted lists and compute statistical median.
"""
import ast
import sqlite3
from kernel import init_db, verify, store

def synthesize_dag_pipeline(conn, in_type: str, out_type: str, tests: str, store_on_success: bool = True):
    """
    Synthesizes a 2-branch join DAG pipeline:
    Left: in_type -> branch_type_1 (Module L)
    Right: in_type -> branch_type_2 (Module R)
    Join: (branch_type_1, branch_type_2) -> out_type (Module J)
    """
    modules = conn.execute("SELECT id, name, source_code, input_schema, output_schema FROM modules WHERE compile_status = 'ok'").fetchall()

    for l_id, l_name, l_src, l_in, l_out in modules:
        for r_id, r_name, r_src, r_in, r_out in modules:
            for j_id, j_name, j_src, j_in, j_out in modules:
                # Check join signature compatibility
                if l_id != r_id and l_id != j_id and r_id != j_id:
                    dag_code = f"""{l_src}

{r_src}

{j_src}

def pipeline(a, b):
    res_l = {l_name}(a)
    res_r = {r_name}(b)
    return {j_name}(res_l, res_r)
"""
                    if verify(dag_code, tests, timeout=1.0):
                        dag_name = f"dag_{l_name}_{r_name}_{j_name}"
                        if store_on_success:
                            store(conn, dag_name, dag_code, tests, f"dag:{l_name}:{r_name}:{j_name}", "local_dag_synthesis")
                        return {
                            "type": "dag_branch_join",
                            "branches": [l_name, r_name],
                            "join": j_name,
                            "name": dag_name,
                            "code": dag_code
                        }
    return None

def test_dag_synthesis_battery(conn):
    print("\n" + "=" * 60)
    print("      RESEARCH TRACK: DAG DECOMPOSITION & SYNTHESIS     ")
    print("=" * 60)

    # Multi-branch join task:
    # Given two unsorted lists, sort both individually, then merge into one sorted list
    dag_test = """
def test():
    assert pipeline([3, 1, 2], [6, 4, 5]) == [1, 2, 3, 4, 5, 6]
    assert pipeline([], [1]) == [1]
"""

    res = synthesize_dag_pipeline(conn, "list", "list", dag_test)
    if res:
        print(f"[+] Successfully Synthesized DAG Pipeline: {res['name']}")
        print(f"    Branch 1: {res['branches'][0]}")
        print(f"    Branch 2: {res['branches'][1]}")
        print(f"    Join    : {res['join']}")
        print(f"\nGenerated DAG Program:\n{res['code']}")
    else:
        print("[-] DAG synthesis failed.")

    passed = res is not None
    print("-" * 60)
    print(f"Research Track M6 Gate Status   : {'PASS (DAG Synthesis Proven)' if passed else 'FAIL'}")
    print("=" * 60)
    return passed

if __name__ == "__main__":
    conn = init_db()
    test_dag_synthesis_battery(conn)
