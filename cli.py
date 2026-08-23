#!/usr/bin/env python3
"""
ModelGen CLI — Query, Compose, and Tune Verified Code Modules locally.
"""
import argparse
import sys
from kernel import init_db, retrieve, verify, store
from compose import compose
from tuner import tune_and_search
from eval import run_evaluation

def query_cmd(args):
    conn = init_db()
    results = retrieve(conn, args.prompt, k=args.top_k)
    print(f"\n[+] Query: '{args.prompt}'")
    print(f"[+] Found {len(results)} candidate modules:\n")
    for rank, (mid, score) in enumerate(results, 1):
        row = conn.execute("SELECT name, input_schema, output_schema, source_code FROM modules WHERE id = ?", (mid,)).fetchone()
        if row:
            name, in_s, out_s, src = row
            print(f"--- #{rank}: {name} (Score: {score}) [Types: {in_s} -> {out_s}] ---")
            if args.verbose:
                print(src)
                print()

def compose_cmd(args):
    conn = init_db()
    print(f"\n[+] Searching for composition pipeline ({args.in_type} -> {args.out_type})...")
    res = compose(conn, args.in_type, args.out_type, args.test_code)
    if res:
        print(f"\n[+] COMPOSITION FOUND ({res['type']}):")
        if "pipeline" in res:
            print(f"    Chained modules: {res['pipeline']}")
        print("\n" + res["code"])
    else:
        print("[-] No valid composition pipeline passed verification.")

def eval_cmd(args):
    conn = init_db()
    run_evaluation(conn, k=args.top_k)

def main():
    parser = argparse.ArgumentParser(description="ModelGen — Local Verified Skill-Library & Code Synthesis CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # query
    q_parser = subparsers.add_parser("query", help="Retrieve modules matching natural language query")
    q_parser.add_argument("prompt", help="Natural language problem description")
    q_parser.add_argument("-k", "--top-k", type=int, default=5, help="Number of results to return")
    q_parser.add_argument("-v", "--verbose", action="store_true", help="Print full source code")
    q_parser.set_defaults(func=query_cmd)

    # compose
    c_parser = subparsers.add_parser("compose", help="Assemble multi-module linear composition pipeline")
    c_parser.add_argument("--in-type", required=True, help="Input type (e.g. str, list, int)")
    c_parser.add_argument("--out-type", required=True, help="Output type (e.g. int, list, str)")
    c_parser.add_argument("--test-code", required=True, help="Python test assertion snippet containing pipeline(x)")
    c_parser.set_defaults(func=compose_cmd)

    # eval
    e_parser = subparsers.add_parser("eval", help="Run 50-problem MVO evaluation suite")
    e_parser.add_argument("-k", "--top-k", type=int, default=10, help="Recall@k parameter")
    e_parser.set_defaults(func=eval_cmd)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
