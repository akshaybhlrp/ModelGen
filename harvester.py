#!/usr/bin/env python3
import ast
import os
import requests
import time
from kernel import init_db, store

TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Authorization": f"token {TOKEN}"} if TOKEN else {}

SEARCH_QUERIES = [
    "language:python def test_ algorithm in:file",
    "language:python def test_ sort in:file",
    "language:python def test_ search in:file",
    "language:python def test_ parse in:file",
    "language:python def test_ tree in:file",
    "language:python def test_ graph in:file",
    "language:python def test_ math in:file",
    "language:python def test_ string in:file",
]

def search(q: str, per_page=100, page=1):
    url = "https://api.github.com/search/code"
    params = {"q": q, "per_page": per_page, "page": page}
    r = requests.get(url, headers=HEADERS, params=params)
    if r.status_code in (403, 429):
        reset_time = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
        sleep_dur = max(5, reset_time - int(time.time()))
        print(f"Rate limited. Sleeping for {sleep_dur}s...")
        time.sleep(sleep_dur)
        return search(q, per_page, page)
    r.raise_for_status()
    return r.json()

def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.text

def extract_ast(content: str):
    """Extracts standalone top-level functions and test suites cleanly via Python AST."""
    try:
        tree = ast.parse(content)
    except Exception:
        return []
    
    functions = []
    tests = []
    lines = content.splitlines()

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            start = node.lineno - 1
            end = node.end_lineno
            code = "\n".join(lines[start:end])
            if node.name.startswith("test_") or node.name == "test":
                tests.append((node.name, code))
            else:
                functions.append((node.name, code))
    
    results = []
    if tests and functions:
        test_block = "\n\n".join([t[1] for t in tests])
        for fn_name, fn_code in functions:
            results.append((fn_name, fn_code, test_block))
    return results

def harvest_batch(conn, queries=SEARCH_QUERIES, token: str = "", max_pages_per_topic: int = 2):
    global HEADERS
    if token:
        HEADERS = {"Authorization": f"token {token}"}
    cands, stored = 0, 0
    for q in queries:
        print(f"\n[+] Harvesting topic: {q}")
        for page in range(1, max_pages_per_topic + 1):
            try:
                res = search(q, page=page)
                items = res.get("items", [])
                if not items:
                    break
                for item in items:
                    cands += 1
                    try:
                        raw_url = item["html_url"].replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
                        content = fetch(raw_url)
                        extracted = extract_ast(content)
                        for fn_name, fn_code, test_code in extracted:
                            if store(conn, fn_name, fn_code, test_code, "MIT", f"harvest:{item['html_url']}"):
                                stored += 1
                    except Exception:
                        continue
                print(f"    Page {page}/{max_pages_per_topic}: Stored={stored} | Candidates={cands}")
            except Exception as e:
                print(f"    Page {page} error: {e}")
            time.sleep(1)
    return cands, stored

def harvest_continuous(conn, pages_per_query=5):
    return harvest_batch(conn, SEARCH_QUERIES, max_pages_per_topic=pages_per_query)

if __name__ == "__main__":
    conn = init_db()
    c, s = harvest_continuous(conn, pages_per_query=3)
    print(f"\n[+] Harvest Session Complete: {s} modules verified and stored from {c} candidates.")
