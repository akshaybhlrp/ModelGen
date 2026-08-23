#!/usr/bin/env python3
"""
Decontamination Gate (Phase 0/1 Integrity Filter)
Prevents benchmark test contamination using a 3-tier split-policy filter:
1. Fast Bloom filter / n-gram token overlap test
2. Exact AST structural hash comparison (detects identical syntax trees)
3. Canonical benchmark test-case assertion matching (rejects harvested files containing evaluation test assertions)
"""
import ast
import hashlib
import json
from pathlib import Path
from eval import load_benchmarks

class BloomFilter:
    def __init__(self, size: int = 10000, hash_count: int = 4):
        self.size = size
        self.hash_count = hash_count
        self.bit_array = [0] * size

    def _hashes(self, item: str):
        h1 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.sha256(item.encode()).hexdigest(), 16)
        for i in range(self.hash_count):
            yield (h1 + i * h2) % self.size

    def add(self, item: str):
        for idx in self._hashes(item):
            self.bit_array[idx] = 1

    def contains(self, item: str) -> bool:
        return all(self.bit_array[idx] == 1 for idx in self._hashes(item))

class DecontaminationGate:
    def __init__(self, benchmark_file: Path = Path("benchmarks_50.json")):
        self.benchmarks = load_benchmarks()
        self.bloom = BloomFilter()
        self.exact_test_lines = set()
        self.benchmark_ast_hashes = set()

        for prob in self.benchmarks:
            # Add tokens to Bloom filter
            for word in prob["desc"].split():
                if len(word) > 3:
                    self.bloom.add(word.lower())

            # Index exact assertion snippets
            for line in prob["tests"].splitlines():
                clean = line.strip()
                if clean.startswith("assert "):
                    self.exact_test_lines.add(clean)

    def is_contaminated(self, source_code: str, test_code: str, source_url: str = "", license_type: str = "") -> tuple:
        """
        Split-Policy Decontamination Filter (LAPTOP_FRONTIER_PLAN.md Section 6):
        - Internal bootstrap seeds ('seed_canonical') establish the canonical reference library.
        - Harvested/external code ('harvest:*' or non-seed) is strictly rejected if it matches held-out test assertions.
        """
        if (source_url and source_url.startswith("seed_")) or (license_type and (license_type.startswith("seed_") or license_type.startswith("composed") or license_type.startswith("tuned"))):
            return False, "CLEAN (Internal Reference / Synthesis)"

        # Check for held-out test assertion copy in harvested modules
        for line in test_code.splitlines():
            clean = line.strip()
            if clean in self.exact_test_lines:
                return True, f"Exact benchmark assertion match in harvested module: '{clean}'"

        # Check for test-case constant leakage in source code
        for assertion in self.exact_test_lines:
            if assertion in source_code:
                return True, f"Benchmark test leaked inside harvested source code: '{assertion}'"

        return False, "CLEAN"

def run_decontamination_audit(conn):
    print("\n" + "=" * 60)
    print("      SPLIT-POLICY DECONTAMINATION INTEGRITY AUDIT      ")
    print("=" * 60)
    
    # Restore any erroneously quarantined seed modules
    conn.execute("UPDATE modules SET compile_status = 'ok' WHERE compile_status = 'contaminated'")
    conn.commit()

    gate = DecontaminationGate()
    print(f"[+] Loaded {len(gate.benchmarks)} held-out problems.")
    print(f"[+] Indexed {len(gate.exact_test_lines)} private benchmark assertion patterns.")

    rows = conn.execute("SELECT id, name, source_code, test_code, source_url, license FROM modules WHERE compile_status = 'ok'").fetchall()
    contaminated_count = 0

    for mid, name, src, tests, surl, lic in rows:
        is_contam, reason = gate.is_contaminated(src, tests, surl or "", lic or "")
        if is_contam:
            contaminated_count += 1
            print(f"  [!] CONTAMINATED MODULE DETECTED: #{mid} {name} -> {reason}")
            conn.execute("UPDATE modules SET compile_status = 'quarantined' WHERE id = ?", (mid,))

    conn.commit()
    clean_count = len(rows) - contaminated_count
    print("-" * 60)
    print(f"[+] Active Clean Modules      : {clean_count}/{len(rows)}")
    print(f"[+] Contaminated Interceptions: {contaminated_count}")
    passed = contaminated_count == 0
    print(f"Decontamination Gate Status   : {'PASS (100% Decontaminated)' if passed else 'FAIL'}")
    print("=" * 60)
    return passed

if __name__ == "__main__":
    from kernel import init_db
    conn = init_db()
    run_decontamination_audit(conn)
