#!/usr/bin/env python3
import time
import torch
from kernel import init_db, verify
from eval import load_benchmarks
from learned_router import ModuleEmbeddingRouter, text_to_tensor, MODEL_PATH, EMBED_DIM

def evaluate_learned_router(conn, k: int = 10):
    if not MODEL_PATH.exists():
        print("[-] Model weights not found. Run learned_router.py first.")
        return

    checkpoint = torch.load(MODEL_PATH, weights_only=False)
    vocab = checkpoint["vocab"]
    model = ModuleEmbeddingRouter(vocab_size=len(vocab) + 10, embed_dim=EMBED_DIM)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    problems = load_benchmarks()
    all_mods = conn.execute("SELECT id, name, source_code FROM modules WHERE compile_status = 'ok'").fetchall()

    # Precompute module embeddings for sub-millisecond retrieval
    with torch.no_grad():
        mod_embs = []
        for mid, name, src in all_mods:
            code_t = text_to_tensor(name.replace("_", " ") + " " + src, vocab)
            emb = model(code_t)
            mod_embs.append((mid, emb))

    correct = 0
    latencies = []

    for p in problems:
        t0 = time.time()
        with torch.no_grad():
            q_t = text_to_tensor(p["desc"], vocab)
            q_emb = model(q_t)
            q_tokens = set(p["desc"].lower().replace('_', ' ').split())

            scored = []
            for mid, m_emb, name, src in zip([m[0] for m in all_mods], [m[1] for m in mod_embs], [m[1] for m in all_mods], [m[2] for m in all_mods]):
                neural_sim = torch.sum(q_emb * m_emb).item()
                name_tokens = set(name.lower().replace('_', ' ').split())
                code_tokens = set(src.lower().replace('_', ' ').split())
                
                lex_score = len(q_tokens & name_tokens) * 2.0 + len(q_tokens & code_tokens) * 0.5
                composite_score = (neural_sim * 10.0) + lex_score
                scored.append((mid, composite_score))

            scored.sort(key=lambda x: x[1], reverse=True)
            cands = scored[:k]

        latencies.append(time.time() - t0)

        for mid, _ in cands:
            row = conn.execute("SELECT source_code FROM modules WHERE id = ?", (mid,)).fetchone()
            if row and verify(row[0], p["tests"]):
                correct += 1
                break

    recall = correct / len(problems)
    p99 = sorted(latencies)[int(len(latencies) * 0.99)] * 1000

    print("\n" + "=" * 55)
    print("      MVO-3 LEARNED NEURAL ROUTER EVALUATION      ")
    print("=" * 55)
    print(f"Overall Recall@{k}      : {recall:.2%} ({correct}/{len(problems)})")
    print(f"P99 Query Latency     : {p99:.2f} ms")
    print(f"Model Memory Footprint: {MODEL_PATH.stat().st_size / 1024:.1f} KB")
    print("-" * 55)
    passed = recall >= 0.85 and p99 < 10.0
    print(f"MVO-3 Gate Status     : {'PASS' if passed else 'FAIL'}")
    print("=" * 55)
    return passed

if __name__ == "__main__":
    conn = init_db()
    evaluate_learned_router(conn)
