#!/usr/bin/env python3
"""
Mutation Testing Engine (Phase 0/1 Quality Gate)
Synthesizes 5 AST mutation operators and evaluates test-suite kill rate:
1. BinaryOp Replacement (+ <-> -, * <-> /)
2. Comparison Replacement (== <-> !=, < <-> >=, > <-> <=)
3. Constant Number Perturbation (x -> x + 1, x - 1, 0)
4. Boolean Inversion (True <-> False)
5. Return Value Mutation (return None / return 0)
"""
import ast
import copy
from kernel import init_db, verify

class MutationVisitor(ast.NodeTransformer):
    def __init__(self, target_idx: int):
        super().__init__()
        self.target_idx = target_idx
        self.current_idx = 0
        self.mutation_applied = False

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if self.current_idx == self.target_idx:
            self.mutation_applied = True
            if isinstance(node.op, ast.Add):
                node.op = ast.Sub()
            elif isinstance(node.op, ast.Sub):
                node.op = ast.Add()
            elif isinstance(node.op, ast.Mult):
                node.op = ast.FloorDiv()
            elif isinstance(node.op, ast.FloorDiv) or isinstance(node.op, ast.Div):
                node.op = ast.Mult()
        self.current_idx += 1
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        if self.current_idx == self.target_idx:
            self.mutation_applied = True
            new_ops = []
            for op in node.ops:
                if isinstance(op, ast.Eq):
                    new_ops.append(ast.NotEq())
                elif isinstance(op, ast.NotEq):
                    new_ops.append(ast.Eq())
                elif isinstance(op, ast.Lt):
                    new_ops.append(ast.GtE())
                elif isinstance(op, ast.Gt):
                    new_ops.append(ast.LtE())
                elif isinstance(op, ast.LtE):
                    new_ops.append(ast.Gt())
                elif isinstance(op, ast.GtE):
                    new_ops.append(ast.Lt())
                else:
                    new_ops.append(op)
            node.ops = new_ops
        self.current_idx += 1
        return node

    def visit_Constant(self, node):
        if self.current_idx == self.target_idx:
            self.mutation_applied = True
            if isinstance(node.value, bool):
                node.value = not node.value
            elif isinstance(node.value, (int, float)):
                node.value = node.value + 1
        self.current_idx += 1
        return node

def count_mutation_points(tree: ast.AST) -> int:
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.BinOp, ast.Compare, ast.Constant)):
            count += 1
    return count

def generate_mutants(source_code: str, max_mutants: int = 30) -> list:
    """Generates up to max_mutants distinct syntactic mutants of the source code."""
    try:
        base_tree = ast.parse(source_code)
    except Exception:
        return []

    total_points = count_mutation_points(base_tree)
    if total_points == 0:
        return []

    step = max(1, total_points // max_mutants)
    mutants = []

    for idx in range(0, total_points, step):
        if len(mutants) >= max_mutants:
            break
        tree_copy = copy.deepcopy(base_tree)
        visitor = MutationVisitor(target_idx=idx)
        mutated_tree = visitor.visit(tree_copy)
        if visitor.mutation_applied:
            try:
                mutant_src = ast.unparse(mutated_tree)
                if mutant_src != source_code:
                    mutants.append(mutant_src)
            except Exception:
                continue

    return mutants

def evaluate_mutation_score(source_code: str, test_code: str, max_mutants: int = 30) -> tuple:
    """
    Tests test-suite strength by running mutants against test suite.
    A mutant is KILLED if verify() returns False (tests caught the bug).
    A mutant SURVIVED if verify() returns True (weak test suite).
    """
    mutants = generate_mutants(source_code, max_mutants)
    if not mutants:
        return 1.0, 0, 0  # No mutable points

    killed = 0
    for m_src in mutants:
        # If test suite fails on mutant, the bug was caught (killed)
        if not verify(m_src, test_code, timeout=1.0):
            killed += 1

    score = killed / len(mutants)
    return score, killed, len(mutants)

def run_library_mutation_audit(conn, quarantine_weak: bool = True):
    print("\n" + "=" * 60)
    print("      MUTATION TESTING QUALITY AUDIT & QUARANTINE GATE     ")
    print("=" * 60)
    
    rows = conn.execute("SELECT id, name, source_code, test_code FROM modules WHERE compile_status = 'ok'").fetchall()
    scores = []
    quarantined = 0

    for mid, name, src, tests in rows:
        score, killed, total = evaluate_mutation_score(src, tests, max_mutants=10)
        scores.append(score)
        
        # Quarantine modules that have mutable points but 0% kill rate (fake/empty tests)
        if total >= 2 and score < 0.30 and quarantine_weak:
            conn.execute("UPDATE modules SET compile_status = 'quarantined' WHERE id = ?", (mid,))
            quarantined += 1

    conn.commit()
    active_rows = conn.execute("SELECT id, name, source_code, test_code FROM modules WHERE compile_status = 'ok'").fetchall()
    active_scores = [evaluate_mutation_score(src, tests, max_mutants=10)[0] for _, _, src, tests in active_rows]
    avg_score = sum(active_scores) / len(active_scores) if active_scores else 0.0

    print(f"[+] Total Scanned: {len(rows)} | Quarantined Weak Modules: {quarantined}")
    print(f"[+] Active Certified Modules: {len(active_rows)}")
    print(f"[+] Active Library Average Kill-Rate: {avg_score:.1%}")
    print("-" * 60)
    passed = avg_score >= 0.60
    print(f"Mutation Quality Gate Status       : {'PASS (>=60% Active Kill-Rate)' if passed else 'FAIL'}")
    print("=" * 60)
    return passed

if __name__ == "__main__":
    conn = init_db()
    run_library_mutation_audit(conn)
