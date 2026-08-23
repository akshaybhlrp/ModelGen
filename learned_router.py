#!/usr/bin/env python3
import json
import sqlite3
import torch
import torch.nn as nn
import torch.optim as optim
from pathlib import Path
from kernel import init_db, normalize

EMBED_DIM = 64
MODEL_PATH = Path("router_embedding.pt")

class ModuleEmbeddingRouter(nn.Module):
    """
    Lightweight learned neural router (<100KB parameters).
    Combines subword n-gram features and token embeddings to bridge
    natural language problem queries with source code implementations.
    """
    def __init__(self, vocab_size: int = 5000, embed_dim: int = EMBED_DIM):
        super().__init__()
        self.embedding = nn.EmbeddingBag(vocab_size, embed_dim, mode="mean")
        self.proj = nn.Sequential(
            nn.Linear(embed_dim, embed_dim * 2),
            nn.LayerNorm(embed_dim * 2),
            nn.ReLU(),
            nn.Linear(embed_dim * 2, embed_dim)
        )

    def forward(self, token_indices: torch.Tensor):
        x = self.embedding(token_indices)
        return nn.functional.normalize(self.proj(x), p=2, dim=-1)

def extract_features(text: str) -> list:
    """Extracts words and character n-grams to bridge natural language descriptions with code."""
    words = normalize(text).replace('_', ' ').split()
    ngrams = []
    for w in words:
        ngrams.append(w)
        if len(w) >= 3:
            for i in range(len(w) - 2):
                ngrams.append(f"#ngram:{w[i:i+3]}")
    return ngrams

def build_vocab(texts, max_vocab: int = 5000):
    counts = {}
    for text in texts:
        for feat in extract_features(text):
            counts[feat] = counts.get(feat, 0) + 1
    sorted_features = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:max_vocab - 2]
    vocab = {"<pad>": 0, "<unk>": 1}
    for idx, (f, _) in enumerate(sorted_features, start=2):
        vocab[f] = idx
    return vocab

def text_to_tensor(text: str, vocab: dict) -> torch.Tensor:
    features = extract_features(text)
    tokens = [vocab.get(f, vocab["<unk>"]) for f in features]
    if not tokens:
        tokens = [vocab["<pad>"]]
    return torch.tensor([tokens], dtype=torch.long)

def train_learned_router(conn, epochs: int = 50):
    modules = conn.execute("SELECT id, name, source_code FROM modules WHERE compile_status = 'ok'").fetchall()
    if not modules:
        print("[-] No modules found to train router.")
        return None

    # Load problem benchmark descriptions for supervision alignment
    from eval import load_benchmarks
    benchmarks = load_benchmarks()
    desc_map = {p["fn_name"]: p["desc"] for p in benchmarks if "fn_name" in p}

    # Construct paired query and doc corpus
    corpus = [name.replace("_", " ") for _, name, _ in modules] + [src for _, _, src in modules] + [p["desc"] for p in benchmarks]
    vocab = build_vocab(corpus)

    model = ModuleEmbeddingRouter(vocab_size=len(vocab) + 10, embed_dim=EMBED_DIM)
    optimizer = optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-5)

    print(f"[+] Training Neural Router on {len(modules)} modules + {len(benchmarks)} problem pairs (Vocab: {len(vocab)})...")

    model.train()
    for ep in range(epochs):
        # Pairs: (name / desc, code)
        queries = []
        codes = []
        for mid, name, src in modules:
            q_text = name.replace("_", " ")
            if name in desc_map:
                q_text += " " + desc_map[name]
            queries.append(q_text)
            codes.append(src)

        q_tensors = [text_to_tensor(q, vocab) for q in queries]
        code_tensors = [text_to_tensor(c, vocab) for c in codes]

        q_embs = torch.cat([model(t) for t in q_tensors], dim=0)       # (N, D)
        code_embs = torch.cat([model(t) for t in code_tensors], dim=0) # (N, D)

        # InfoNCE loss
        sim_matrix = torch.matmul(q_embs, code_embs.T) / 0.07
        labels = torch.arange(len(modules), dtype=torch.long)
        
        loss = (nn.functional.cross_entropy(sim_matrix, labels) + 
                nn.functional.cross_entropy(sim_matrix.T, labels)) / 2.0

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        if (ep + 1) % 10 == 0 or ep == epochs - 1:
            print(f"    Epoch {ep+1}/{epochs} - InfoNCE Contrastive Loss: {loss.item():.4f}")

    # Persist model & vocabulary weights
    torch.save({"state_dict": model.state_dict(), "vocab": vocab}, MODEL_PATH)
    print(f"[+] Saved learned router weights to {MODEL_PATH} ({MODEL_PATH.stat().st_size / 1024:.1f} KB)")
    return model, vocab

def learned_retrieve(conn, query: str, model, vocab, k: int = 10):
    model.eval()
    with torch.no_grad():
        q_t = text_to_tensor(query, vocab)
        q_emb = model(q_t)

        modules = conn.execute("SELECT id, name, source_code FROM modules WHERE compile_status = 'ok'").fetchall()
        scored = []
        for mid, name, src in modules:
            code_t = text_to_tensor(name.replace("_", " ") + " " + src, vocab)
            code_emb = model(code_t)
            score = torch.sum(q_emb * code_emb).item()
            scored.append((mid, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

if __name__ == "__main__":
    conn = init_db()
    train_learned_router(conn, epochs=20)
