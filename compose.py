#!/usr/bin/env python3
import sqlite3
from kernel import init_db, verify, store

def find_bridge_types(conn, in_type: str, out_type: str):
    """Finds intermediate types T_mid connecting T_in -> T_mid -> T_out."""
    q = """
    SELECT m1.output_schema 
    FROM modules m1 
    JOIN modules m2 ON m1.output_schema = m2.input_schema 
    WHERE m1.input_schema = ? AND m2.output_schema = ? AND m1.compile_status = 'ok' AND m2.compile_status = 'ok'
    GROUP BY m1.output_schema
    """
    rows = conn.execute(q, (in_type, out_type)).fetchall()
    return [r[0] for r in rows]

def compose(conn, in_type: str, out_type: str, tests: str, store_on_success: bool = True):
    """Attempts direct single-module retrieval first, then linear A -> B composition."""
    # 1. Direct retrieval
    direct = conn.execute(
        "SELECT id, name, source_code FROM modules WHERE input_schema = ? AND output_schema = ? AND compile_status = 'ok'",
        (in_type, out_type)).fetchall()
    for mid, name, src in direct:
        if verify(src, tests):
            return {"type": "direct", "module_id": mid, "code": src}

    # 2. Linear Composition A -> B
    bridges = find_bridge_types(conn, in_type, out_type)
    for bridge in bridges:
        left = conn.execute("SELECT id, name, source_code FROM modules WHERE input_schema = ? AND output_schema = ? AND compile_status = 'ok'", (in_type, bridge)).fetchall()
        right = conn.execute("SELECT id, name, source_code FROM modules WHERE input_schema = ? AND output_schema = ? AND compile_status = 'ok'", (bridge, out_type)).fetchall()
        for l_id, l_name, l_src in left:
            for r_id, r_name, r_src in right:
                composed_src = f"{l_src}\n\n{r_src}\n\ndef pipeline(x):\n    return {r_name}({l_name}(x))\n"
                if verify(composed_src, tests):
                    comp_name = f"pipeline_{l_name}_{r_name}"
                    if store_on_success:
                        store(conn, comp_name, composed_src, tests, f"composed:{l_name}:{r_name}", "local_composition", in_type, out_type)
                    return {
                        "type": "composition",
                        "pipeline": [l_name, r_name],
                        "name": comp_name,
                        "code": composed_src
                    }
    return None

def test_mvo1_composite_battery(conn):
    """Evaluates multi-module composition across held-out composite benchmarks."""
    composite_problems = [
        {
            "name": "lowercase_and_count_vowels",
            "in_type": "str",
            "out_type": "int",
            "tests": "def test():\n    assert pipeline('HELLO WORLD') == 3\n    assert pipeline('XYZ') == 0\n"
        },
        {
            "name": "reverse_and_count_vowels",
            "in_type": "str",
            "out_type": "int",
            "tests": "def test():\n    assert pipeline('hello world') == 3\n    assert pipeline('radar') == 2\n"
        }
    ]
    
    passed = 0
    print("\n" + "=" * 50)
    print("           MVO-1 COMPOSITION BATTERY              ")
    print("=" * 50)
    for prob in composite_problems:
        # Test composition specifically (excluding previously stored compound pipelines)
        bridges = find_bridge_types(conn, prob["in_type"], prob["out_type"])
        found = False
        for bridge in bridges:
            left = conn.execute("SELECT id, name, source_code FROM modules WHERE input_schema = ? AND output_schema = ? AND license != 'composed' AND compile_status = 'ok'", (prob["in_type"], bridge)).fetchall()
            right = conn.execute("SELECT id, name, source_code FROM modules WHERE input_schema = ? AND output_schema = ? AND license != 'composed' AND compile_status = 'ok'", (bridge, prob["out_type"])).fetchall()
            for l_id, l_name, l_src in left:
                for r_id, r_name, r_src in right:
                    composed_src = f"{l_src}\n\n{r_src}\n\ndef pipeline(x):\n    return {r_name}({l_name}(x))\n"
                    if verify(composed_src, prob["tests"]):
                        passed += 1
                        found = True
                        print(f"[+] Solved via Multi-Module Composition: {prob['name']} (Chain: {l_name} -> {r_name})")
                        break
                if found:
                    break
            if found:
                break
        if not found:
            print(f"[-] No composition chain found: {prob['name']}")
    
    print("-" * 50)
    print(f"MVO-1 Gate Status: {'PASS (>=1 Composition Verified)' if passed >= 1 else 'FAIL'}")
    print("=" * 50)
    return passed

if __name__ == "__main__":
    conn = init_db()
    test_mvo1_composite_battery(conn)
