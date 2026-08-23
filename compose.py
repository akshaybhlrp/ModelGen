#!/usr/bin/env python3
import sqlite3
from kernel import init_db, verify

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

def compose(conn, in_type: str, out_type: str, tests: str):
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
        left = conn.execute("SELECT id, name, source_code FROM modules WHERE input_schema = ? AND output_schema = ?", (in_type, bridge)).fetchall()
        right = conn.execute("SELECT id, name, source_code FROM modules WHERE input_schema = ? AND output_schema = ?", (bridge, out_type)).fetchall()
        for l_id, l_name, l_src in left:
            for r_id, r_name, r_src in right:
                composed_src = f"{l_src}\n\n{r_src}\n\ndef pipeline(x):\n    return {r_name}({l_name}(x))\n"
                if verify(composed_src, tests):
                    return {
                        "type": "composition",
                        "pipeline": [l_name, r_name],
                        "code": composed_src
                    }
    return None

if __name__ == "__main__":
    conn = init_db()
    print("Composition engine ready.")
