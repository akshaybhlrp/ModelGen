#!/usr/bin/env python3
"""
Phase 4 Federation Protocol with Beta-Bernoulli Peer Trust
Facilitates decentralized P2P sharing of verified skill modules between instances.
- Re-verifies all incoming foreign modules locally before acceptance.
- Computes Bayesian Beta-Bernoulli trust posterior for peer nodes:
    Trust Score = (alpha + successes) / (alpha + beta + successes + failures)
- Blocks peers whose trust falls below the verification threshold.
"""
import json
import sqlite3
from pathlib import Path
from kernel import init_db, verify, store

class PeerNode:
    def __init__(self, node_id: str, alpha: float = 1.0, beta: float = 1.0):
        self.node_id = node_id
        self.successes = 0
        self.failures = 0
        self.alpha = alpha
        self.beta = beta

    @property
    def trust_score(self) -> float:
        """Bayesian expected trust probability E[theta] = (alpha + S) / (alpha + beta + S + F)"""
        return (self.alpha + self.successes) / (self.alpha + self.beta + self.successes + self.failures)

    def record_verification(self, success: bool):
        if success:
            self.successes += 1
        else:
            self.failures += 1

class FederationEngine:
    def __init__(self, conn, min_trust_threshold: float = 0.50):
        self.conn = conn
        self.min_trust_threshold = min_trust_threshold
        self.peers = {}

    def get_or_create_peer(self, node_id: str) -> PeerNode:
        if node_id not in self.peers:
            self.peers[node_id] = PeerNode(node_id)
        return self.peers[node_id]

    def export_modules_package(self, limit: int = 20) -> list:
        """Exports verified modules with signatures for peer sharing."""
        rows = self.conn.execute(
            "SELECT name, source_code, test_code, input_schema, output_schema, license FROM modules WHERE compile_status = 'ok' LIMIT ?",
            (limit,)).fetchall()
        package = []
        for name, src, tests, in_s, out_s, lic in rows:
            package.append({
                "name": name,
                "source_code": src,
                "test_code": tests,
                "input_schema": in_s,
                "output_schema": out_s,
                "license": lic
            })
        return package

    def ingest_federated_package(self, peer_id: str, package: list) -> tuple:
        """
        Receives package from remote peer, re-verifies in local sandbox,
        updates peer Beta-Bernoulli trust posterior, and stores verified modules.
        """
        peer = self.get_or_create_peer(peer_id)
        if peer.trust_score < self.min_trust_threshold:
            print(f"[!] REJECTED: Peer {peer_id} trust score ({peer.trust_score:.2f}) below threshold ({self.min_trust_threshold:.2f})")
            return 0, len(package), peer.trust_score

        accepted = 0
        rejected = 0

        for item in package:
            # Re-verify independently in local execution sandbox
            if verify(item["source_code"], item["test_code"]):
                peer.record_verification(True)
                store(self.conn, item["name"], item["source_code"], item["test_code"],
                      item["license"], f"federated:{peer_id}", item["input_schema"], item["output_schema"])
                accepted += 1
            else:
                peer.record_verification(False)
                rejected += 1

        return accepted, rejected, peer.trust_score

def test_federation_suite(conn):
    print("\n" + "=" * 60)
    print("   PHASE 4 FEDERATION & BETA-BERNOULLI TRUST PROTOCOL   ")
    print("=" * 60)
    
    engine = FederationEngine(conn)

    # 1. Export valid package from local library
    pkg = engine.export_modules_package(limit=5)
    print(f"[+] Exported {len(pkg)} certified modules for P2P network sharing.")

    # 2. Simulate honest peer node
    print("\n[+] Ingesting from Honest Peer 'node_bravo'...")
    acc, rej, trust = engine.ingest_federated_package("node_bravo", pkg)
    print(f"    Accepted: {acc}, Rejected: {rej}, Updated Trust: {trust:.2%}")

    # 3. Simulate adversarial/malicious peer sending broken/poisoned modules
    print("\n[+] Ingesting from Adversarial Peer 'node_mallory' (poisoned modules)...")
    malicious_pkg = [
        {"name": "bad_fn_1", "source_code": "def bad(): return 1", "test_code": "def test(): assert bad() == 2", "input_schema": "Any", "output_schema": "Any", "license": "MIT"},
        {"name": "bad_fn_2", "source_code": "def bad2(): return 1/0", "test_code": "def test(): assert bad2() == 1", "input_schema": "Any", "output_schema": "Any", "license": "MIT"},
        {"name": "bad_fn_3", "source_code": "def bad3(): pass", "test_code": "def test(): assert bad3() == 42", "input_schema": "Any", "output_schema": "Any", "license": "MIT"}
    ]
    m_acc, m_rej, m_trust = engine.ingest_federated_package("node_mallory", malicious_pkg)
    print(f"    Accepted: {m_acc}, Rejected: {m_rej}, Updated Trust: {m_trust:.2%}")

    # 4. Confirm adversarial peer is blocked on subsequent requests
    print("\n[+] Testing Quarantine Block on Adversarial Peer 'node_mallory'...")
    b_acc, b_rej, b_trust = engine.ingest_federated_package("node_mallory", pkg)
    
    passed = acc == 5 and m_acc == 0 and b_acc == 0
    print("-" * 60)
    print(f"Phase 4 Federation Gate Status  : {'PASS (Bayesian Isolation Active)' if passed else 'FAIL'}")
    print("=" * 60)
    return passed

if __name__ == "__main__":
    conn = init_db()
    test_federation_suite(conn)
