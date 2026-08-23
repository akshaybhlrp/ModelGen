import pytest
import sqlite3
import tempfile
from pathlib import Path
from kernel import init_db, store, retrieve, verify, compute_simhash, normalize, update_counter, input_hash
from compose import compose, find_bridge_types
from tuner import tune_and_search
from pruner import prune_redundant_modules, ast_fingerprint, verify_zero_forgetting
from eval import run_evaluation, load_benchmarks
from baseline_grep import grep_baseline_retrieve, compare_router_vs_grep

@pytest.fixture
def test_conn(tmp_path):
    """Creates a temporary test database instance."""
    db_file = tmp_path / "test_frontier.db"
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA journal_mode=WAL")
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

# 1. Verification Sandbox Tests
def test_verify_valid_function():
    src = "def add(a, b):\n    return a + b"
    test = "def test():\n    assert add(2, 3) == 5"
    assert verify(src, test) is True

def test_verify_failing_assertion():
    src = "def add(a, b):\n    return a - b"
    test = "def test():\n    assert add(2, 3) == 5"
    assert verify(src, test) is False

def test_verify_syntax_error():
    src = "def bad_syntax(:"
    test = "def test():\n    assert True"
    assert verify(src, test) is False

def test_verify_timeout():
    src = "def inf_loop():\n    while True:\n        pass"
    test = "def test():\n    inf_loop()"
    assert verify(src, test, timeout=0.5) is False

# 2. Storage & SimHash Tests
def test_store_and_simhash(test_conn):
    src = "def multiply(x, y):\n    return x * y"
    test = "def test():\n    assert multiply(3, 4) == 12"
    mid = store(test_conn, "multiply", src, test, "MIT", "test://local", "int, int", "int")
    assert mid > 0

    # Ensure SimHash is indexed
    sh = test_conn.execute("SELECT simhash FROM simhash_index WHERE module_id = ?", (mid,)).fetchone()
    assert sh is not None
    assert isinstance(sh[0], int)

def test_store_duplicate_prevention(test_conn):
    src = "def square(x):\n    return x * x"
    test = "def test():\n    assert square(3) == 9"
    mid1 = store(test_conn, "square", src, test, "MIT", "test://local", "int", "int")
    mid2 = store(test_conn, "square", src, test, "MIT", "test://local", "int", "int")
    assert mid1 > 0
    assert mid2 == 0  # Duplicate should be ignored

# 3. Router Ranking & Counter Updates
def test_router_retrieval_and_counters(test_conn):
    src1 = "def sort_ints(lst):\n    return sorted(lst)"
    test1 = "def test():\n    assert sort_ints([2, 1]) == [1, 2]"
    mid1 = store(test_conn, "sort_ints", src1, test1, "MIT", "test://local", "list", "list")

    src2 = "def rev_ints(lst):\n    return lst[::-1]"
    test2 = "def test():\n    assert rev_ints([1, 2]) == [2, 1]"
    mid2 = store(test_conn, "rev_ints", src2, test2, "MIT", "test://local", "list", "list")

    # Exact query matching
    results = retrieve(test_conn, "sort ints", k=2)
    assert len(results) >= 1
    assert results[0][0] == mid1

    # Counter feedback update
    q_hash = input_hash("sort ints")
    update_counter(test_conn, q_hash, mid1, True)
    
    counter_val = test_conn.execute("SELECT counter FROM routing_counters WHERE input_hash = ? AND module_id = ?", (q_hash, mid1)).fetchone()[0]
    assert counter_val == 1

# 4. Composition Engine Tests
def test_linear_composition_pipeline(test_conn):
    # Step 1: int -> str
    store(test_conn, "int_to_str", "def int_to_str(x: int) -> str:\n    return str(x)", "def test():\n    assert int_to_str(5) == '5'", "MIT", "local", "int", "str")
    
    # Step 2: str -> list
    store(test_conn, "repeat_str", "def repeat_str(s: str) -> list:\n    return [s, s]", "def test():\n    assert repeat_str('a') == ['a', 'a']", "MIT", "local", "str", "list")

    # Target test: int -> list
    target_test = "def test():\n    assert pipeline(42) == ['42', '42']"
    res = compose(test_conn, "int", "list", target_test, store_on_success=True)
    assert res is not None
    assert res["type"] == "composition"
    assert res["pipeline"] == ["int_to_str", "repeat_str"]

# 5. Parameter Tuner Tests
def test_tuner_sort_template(test_conn):
    test_code = "def test():\n    assert sort_desc([1, 4, 2]) == [4, 2, 1]"
    res = tune_and_search(test_conn, "template_sort", "sort_desc", test_code)
    assert res is not None
    assert res["params"]["reverse"] is True

def test_tuner_filter_template(test_conn):
    test_code = "def test():\n    assert filter_odds([1, 2, 3, 4, 5]) == [1, 3, 5]"
    res = tune_and_search(test_conn, "template_filter", "filter_odds", test_code)
    assert res is not None
    assert res["params"]["predicate"] == "x % 2 != 0"

# 6. AST Fingerprinting & Pruning Tests
def test_ast_fingerprint_equivalence():
    code1 = """def foo(x):\n    # comment\n    return x + 1"""
    code2 = """def foo(  x  ):\n\n    return x + 1\n"""
    assert ast_fingerprint(code1) == ast_fingerprint(code2)

def test_prune_duplicates(test_conn):
    code1 = "def helper1(x):\n    return x * 10"
    test1 = "def test():\n    assert helper1(2) == 20"
    code2 = "def helper2(x):\n    # identical AST\n    return x * 10"
    test2 = "def test():\n    assert helper2(2) == 20"
    
    m1 = store(test_conn, "helper1", code1, test1, "MIT", "local")
    # Manually insert second module with different content_hash but identical AST
    test_conn.execute("INSERT INTO modules (content_hash, name, source_code, test_code, compile_status) VALUES (?, ?, ?, ?, 'ok')", (b"hash2", "helper2", code2, test2))
    test_conn.commit()

    pruned = prune_redundant_modules(test_conn)
    assert pruned == 1
