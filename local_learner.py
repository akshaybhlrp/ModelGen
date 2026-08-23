#!/usr/bin/env python3
"""
ModelGen Local Directory Ingestion & Learning Engine
Scans any local project directory, extracts Python functions and test suites via AST,
runs them through the sandbox, mutation tester, and decontamination filter,
stores them in the skill library, and updates the neural weights on-the-fly.
"""
import os
import sys
from pathlib import Path
from kernel import init_db, store
from harvester import extract_ast
from mutation_tester import evaluate_mutation_score
from decontaminate import DecontaminationGate
from learned_router import train_learned_router

def ingest_local_directory(dir_path: str, conn=None, retrain_neural_weights: bool = True) -> dict:
    target = Path(dir_path).resolve()
    if not target.exists() or not target.is_dir():
        return {"status": "error", "message": f"Directory not found: {dir_path}", "learned_count": 0}

    if conn is None:
        conn = init_db()

    decontam = DecontaminationGate()
    discovered_files = list(target.rglob("*.py"))
    
    total_found = 0
    total_stored = 0
    modules_stored = []

    print(f"\n[+] Scanning Local Directory: {target} ({len(discovered_files)} Python files)")

    for py_file in discovered_files:
        # Ignore hidden / venv directories
        if any(part.startswith(".") or part in {"venv", "__pycache__", "node_modules", "build", "dist"} for part in py_file.parts):
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if len(content) < 30:
                continue

            extracted = extract_ast(content)
            for fn_name, fn_code, test_code in extracted:
                total_found += 1
                
                # Split-policy decontamination check
                is_contam, _ = decontam.is_contaminated(fn_code, test_code, source_url=f"local:{py_file}")
                if is_contam:
                    continue

                # Mutation test quality check
                mut_score, killed, total = evaluate_mutation_score(fn_code, test_code, max_mutants=5)
                if mut_score < 0.40:
                    continue

                mid = store(conn, fn_name, fn_code, test_code, "Local", f"local:{py_file}")
                if mid:
                    total_stored += 1
                    modules_stored.append(fn_name)
                    print(f"  [VERIFIED & LEARNED] #{mid} '{fn_name}' from {py_file.name} (Mutation Kill-Rate: {mut_score:.1%})")
        except Exception as e:
            continue

    # On-the-fly neural router weight retraining
    if total_stored > 0 and retrain_neural_weights:
        print(f"\n[+] Adapting Neural Router Weights for {total_stored} newly learned local modules...")
        train_learned_router(conn, epochs=10)

    return {
        "status": "success",
        "scanned_files": len(discovered_files),
        "candidates_found": total_found,
        "learned_count": total_stored,
        "modules": modules_stored
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 local_learner.py <path_to_directory>")
        sys.exit(1)

    path = sys.argv[1]
    res = ingest_local_directory(path)
    print(f"\n[+] Local Ingestion Complete. Learned {res['learned_count']} modules from {res['scanned_files']} files.")
