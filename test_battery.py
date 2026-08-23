import pytest
import sqlite3
from kernel import init_db, store, retrieve, verify, compute_simhash, normalize
from compose import compose
from tuner import tune_and_search
from pruner import prune_redundant_modules, ast_fingerprint

@pytest.fixture
def db():
    return init_db()

def test_kernel_store_and_verify(db):
    src = "def add_two(x: int) -> int:\n    return x + 2"
    tests = "def test_add():\n    assert add_two(3) == 5\n"
    mid = store(db, "add_two", src, tests, "MIT", "test_url", "int", "int")
    assert mid > 0

    # Retrieve by query
    results = retrieve(db, "add two numbers", k=5)
    assert len(results) > 0
    assert any(m[0] == mid for m in results)

def test_simhash_distance():
    s1 = "def sort_list(lst): return sorted(lst)"
    s2 = "def sort_items(items): return sorted(items)"
    s3 = "def reverse_string(s): return s[::-1]"
    
    sh1 = compute_simhash(s1)
    sh2 = compute_simhash(s2)
    sh3 = compute_simhash(s3)
    
    dist_12 = bin((sh1 ^ sh2) & 0xFFFFFFFFFFFFFFFF).count('1')
    dist_13 = bin((sh1 ^ sh3) & 0xFFFFFFFFFFFFFFFF).count('1')
    assert dist_12 < dist_13

def test_linear_composition(db):
    test_code = "def test():\n    assert pipeline('HELLO WORLD') == 3\n"
    res = compose(db, "str", "int", test_code)
    assert res is not None
    assert res["type"] in ("direct", "composition")

def test_parameter_tuner(db):
    test_code = "def test():\n    assert sort_len(['a', 'ccc', 'bb']) == ['ccc', 'bb', 'a']\n"
    res = tune_and_search(db, "template_sort", "sort_len", test_code)
    assert res is not None
    assert res["params"]["reverse"] is True
