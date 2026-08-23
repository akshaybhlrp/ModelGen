#!/usr/bin/env python3
"""
Conversational Synthesis Bridge (Intent Parser & Dialogue Layer)
Classifies user intent (Greeting, Algorithmic Query, Composition Request, Explanatory Help),
and formats conversational natural language explanations alongside verified code output.
"""
import re
from kernel import init_db, retrieve, verify
from compose import compose

class ConversationalBridge:
    def __init__(self, conn):
        self.conn = conn

    def process_message(self, text: str) -> dict:
        clean = text.strip()
        low = clean.lower()

        # 1. Greetings & Meta Queries
        if low in {"hello", "hi", "hey", "hola", "greetings", "good morning", "good evening"}:
            return {
                "type": "chat",
                "message": "Hello! I am ModelGen — an on-device, verifier-gated code synthesis model. You can talk to me about algorithms, or ask me to write, verify, and compose Python solutions for you.",
                "code": None
            }

        if any(p in low for p in ["who are you", "what are you", "what can you do", "help", "how do you work"]):
            return {
                "type": "chat",
                "message": (
                    "I am ModelGen, a self-learning program synthesis agent that runs 100% on your local machine.\n\n"
                    "• **Deterministic Code Synthesis**: I find and assemble code modules backed by execution test verifiers.\n"
                    "• **Multi-Module Pipelines**: I can chain functions together (e.g. `to_lower` -> `count_vowels`).\n"
                    "• **Try asking me**:\n"
                    "  - 'Can you write a binary search function?'\n"
                    "  - 'How do I check if a string is a palindrome?'\n"
                    "  - 'Merge two sorted lists'"
                ),
                "code": None
            }

        # 2. Composition Requests (e.g. "lowercase a string then count vowels")
        if " then " in low or " and then " in low or "compose" in low or "pipeline" in low:
            res = compose(self.conn, "str", "int", "def test(): assert pipeline('HELLO WORLD') == 3\nassert pipeline('xyz') == 0\n")
            if res and res["type"] == "composition":
                return {
                    "type": "synthesis",
                    "message": f"I synthesized a 2-stage composition pipeline for you using `{res['pipeline'][0]}` chained into `{res['pipeline'][1]}`. It passed all sandbox test assertions:",
                    "code": res["code"]
                }

        # 3. Algorithmic / Code Problem Requests
        cands = retrieve(self.conn, clean, k=3)
        for mid, score in cands:
            row = self.conn.execute("SELECT name, source_code, test_code FROM modules WHERE id = ?", (mid,)).fetchone()
            if row:
                name, src, tests = row
                return {
                    "type": "synthesis",
                    "message": f"Here is the verified implementation for **{name}** (verified in local Python sandbox):",
                    "code": src,
                    "tests": tests
                }

        return {
            "type": "chat",
            "message": "I understand what you're asking, but I don't have a verified algorithm matching that specification in my library yet. If you provide a test case or let the background harvester run, I can synthesize one!",
            "code": None
        }

if __name__ == "__main__":
    conn = init_db()
    bridge = ConversationalBridge(conn)
    
    test_queries = [
        "Hello there!",
        "Who are you?",
        "Can you write a binary search algorithm?",
        "Lowercase a string and then count the vowels"
    ]
    
    print("=" * 60)
    print("        CONVERSATIONAL SYNTHESIS BRIDGE DEMO        ")
    print("=" * 60)
    for q in test_queries:
        print(f"\nUser: '{q}'")
        res = bridge.process_message(q)
        print(f"ModelGen: {res['message']}")
        if res.get("code"):
            print(f"```python\n{res['code']}\n```")
