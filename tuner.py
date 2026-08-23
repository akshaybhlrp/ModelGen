#!/usr/bin/env python3
import json
from kernel import init_db, verify, store

TEMPLATES = [
    {
        "name": "template_sort",
        "code_template": """def {fn_name}(lst: list) -> list:
    return sorted(lst, key={key_fn}, reverse={reverse})""",
        "params": {
            "key_fn": ["None", "abs", "len", "lambda x: x[0]", "lambda x: x[-1]"],
            "reverse": [False, True]
        }
    },
    {
        "name": "template_filter",
        "code_template": """def {fn_name}(lst: list) -> list:
    return [x for x in lst if {predicate}]""",
        "params": {
            "predicate": [
                "x > 0",
                "x % 2 == 0",
                "x % 2 != 0",
                "len(x) > 3",
                "isinstance(x, int)"
            ]
        }
    }
]

def tune_and_search(conn, template_name: str, fn_name: str, tests: str):
    """Enumerates parameter domains for a template and verifies variants against tests."""
    template = next((t for t in TEMPLATES if t["name"] == template_name), None)
    if not template:
        return None

    import itertools
    keys, values = zip(*template["params"].items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]

    for combo in combinations:
        combo_formatted = combo.copy()
        combo_formatted["fn_name"] = fn_name
        candidate_code = template["code_template"].format(**combo_formatted)
        
        if verify(candidate_code, tests):
            mid = store(conn, fn_name, candidate_code, tests, f"tuned:{template_name}", "local_tuner", "list", "list")
            return {
                "fn_name": fn_name,
                "template": template_name,
                "params": combo,
                "code": candidate_code,
                "stored_id": mid
            }
    return None

def test_mvo4_tuner_battery(conn):
    print("\n" + "=" * 50)
    print("        MVO-4 BOUNDED PARAMETER TUNER BATTERY     ")
    print("=" * 50)
    
    tuning_problems = [
        {
            "desc": "sort strings by their length descending",
            "template": "template_sort",
            "fn_name": "sort_by_len_desc",
            "tests": "def test():\n    assert sort_by_len_desc(['a', 'ccc', 'bb']) == ['ccc', 'bb', 'a']\n"
        },
        {
            "desc": "filter only even integers from list",
            "template": "template_filter",
            "fn_name": "filter_evens",
            "tests": "def test():\n    assert filter_evens([1, 2, 3, 4, 5, 6]) == [2, 4, 6]\n"
        }
    ]
    
    solved = 0
    for p in tuning_problems:
        res = tune_and_search(conn, p["template"], p["fn_name"], p["tests"])
        if res:
            solved += 1
            print(f"[+] Solved via Parameter Tuning: {p['desc']}")
            print(f"    Parameters: {res['params']}")
            print(f"    Code:\n{res['code']}\n")
        else:
            print(f"[-] Failed to tune: {p['desc']}")
            
    print("-" * 50)
    print(f"MVO-4 Gate Status: {'PASS (Tuning Unlocks Novel Solutions)' if solved >= 1 else 'FAIL'}")
    print("=" * 50)
    return solved

if __name__ == "__main__":
    conn = init_db()
    test_mvo4_tuner_battery(conn)
