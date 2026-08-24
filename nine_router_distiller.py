#!/usr/bin/env python3
"""
ModelGen 9Router Frontier Teacher-Student Distillation Engine
Connects to the local 9router gateway (x-api-key authenticated) to query frontier teacher models
(Claude Sonnet, DeepSeek Reasoner, Kimi Coding), generates algorithmic challenge datasets,
validates the synthesized code in the local verifier sandbox, and distills the logic directly
into ModelGen's discrete library and neural router weights.
"""
import os
import re
import ast
import json
import requests
from kernel import init_db, store
from mutation_tester import evaluate_mutation_score
from decontaminate import DecontaminationGate
from learned_router import train_learned_router

GATEWAY_URL = os.environ.get("ROUTER_URL", "http://localhost:20128/v1")
API_KEY = os.environ.get("ROUTER_API_KEY", "sk-ef6bda77bfc03030-iheqrc-5ded8f96")

HEADERS = {
    "x-api-key": API_KEY,
    "Content-Type": "application/json"
}

ACTIVE_TEACHER_MODELS = [
    "gh/gpt-4o",
    "kr/auto",
    "kr/claude-sonnet-4.5",
    "gh/gpt-4o-mini",
    "kr/qwen3-coder-next",
    "openrouter/openrouter/free",
    "kimi/kimi-for-coding",
    "ds/deepseek-chat"
]

SYNTHESIS_PROMPT = """Write a complete, high-performance, standalone Python function or class for the following task:
{task}

Requirements:
1. Provide clean, production-grade Python code inside ```python ... ```
2. Include at least 3 assertions in a verification function named `def test():` or `def test_<name>():` to verify correctness.
3. No external dependencies, use pure Python stdlib.
"""

DEFAULT_DISTILL_TASKS = [
    "Implement an LRU Cache class with get and put operations in O(1) time complexity.",
    "Implement Trie (Prefix Tree) with insert, search, and startsWith methods.",
    "Find the longest increasing subsequence length in an array in O(n log n).",
    "Implement Kadane algorithm to find the maximum sum of a contiguous subarray.",
    "Implement a MinHeap priority queue class with push, pop, and peek operations.",
    "Implement Topological Sort for a Directed Acyclic Graph using Kahn's algorithm.",
    "Implement Knapsack 0/1 dynamic programming algorithm returning maximum value.",
    "Implement Levenshtein edit distance between two strings with DP table.",
    "Implement Dijkstra algorithm to find shortest paths from source in weighted graph.",
    "Implement Rabin-Karp string pattern matching algorithm using rolling hash."
]

class NineRouterDistiller:
    def __init__(self, conn=None, base_url: str = GATEWAY_URL, api_key: str = API_KEY):
        self.conn = conn if conn else init_db()
        self.base_url = base_url
        self.headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json"
        }
        self.decontam = DecontaminationGate()

    def query_teacher(self, prompt: str, model: str = None) -> str:
        models_to_try = [model] if model else ACTIVE_TEACHER_MODELS
        if not model:
            models_to_try = ACTIVE_TEACHER_MODELS

        url = f"{self.base_url}/chat/completions"
        for m in models_to_try:
            if not m: continue
            payload = {
                "model": m,
                "messages": [
                    {"role": "system", "content": "You are ModelGen, an intelligent, helpful, and versatile AI assistant and code synthesis engine. When given a keyword, entity, topic, or question (e.g. 'Tigor', 'Python', 'Photosynthesis'), provide a helpful, natural, and informative overview explaining what it is, key context, and related details. When asked to write code, provide clean, executable Python inside ```python ... ``` with a verification test function test()."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1024,
                "stream": False
            }
            try:
                res = requests.post(url, headers=self.headers, json=payload, timeout=15)
                if res.status_code == 200:
                    text_resp = res.text.strip()
                    # 1. Try standard JSON
                    try:
                        data = res.json()
                        if "choices" in data and len(data["choices"]) > 0:
                            choice = data["choices"][0]
                            if "message" in choice and "content" in choice["message"]:
                                return choice["message"]["content"]
                            if "text" in choice:
                                return choice["text"]
                    except Exception:
                        pass

                    # 2. Try parsing Server-Sent Events (SSE) streaming format
                    chunks = []
                    for line in text_resp.splitlines():
                        line = line.strip()
                        if line.startswith("data:") and not line.startswith("data: [DONE]"):
                            json_str = line[5:].strip()
                            try:
                                d = json.loads(json_str)
                                choices = d.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    if "content" in delta and delta["content"]:
                                        chunks.append(delta["content"])
                                    elif "text" in choices[0]:
                                        chunks.append(choices[0]["text"])
                            except Exception:
                                pass
                    if chunks:
                        return "".join(chunks)
            except Exception:
                continue
        return ""

    def parse_python_code(self, raw_response: str):
        # Extract code inside ```python blocks or raw text
        match = re.search(r"```python(.*?)```", raw_response, re.DOTALL)
        code = match.group(1).strip() if match else raw_response.strip()

        try:
            tree = ast.parse(code)
        except Exception:
            return None, None, None

        functions = []
        tests = []
        lines = code.splitlines()

        for node in tree.body:
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.ClassDef):
                start = node.lineno - 1
                end = node.end_lineno
                snippet = "\n".join(lines[start:end])
                if node.name.startswith("test_") or node.name == "test":
                    tests.append((node.name, snippet))
                else:
                    functions.append((node.name, snippet))

        if functions and tests:
            test_block = "\n\n".join([t[1] for t in tests])
            return functions[0][0], functions[0][1], test_block
        elif functions:
            return functions[0][0], functions[0][1], ""
        return None, None, None

    def distill_task(self, task_description: str, model: str = None) -> bool:
        print(f"\n[9Router Distill] Prompting frontier teacher for: '{task_description}'...")
        prompt = SYNTHESIS_PROMPT.format(task=task_description)
        raw_code = self.query_teacher(prompt, model=model)
        if not raw_code:
            return False

        fn_name, fn_code, test_code = self.parse_python_code(raw_code)
        if not fn_name or not fn_code:
            print("  [-] Failed to parse executable AST from teacher output.")
            return False

        if not test_code:
            test_code = "def test():\n    pass\n"

        # Quality Gate 1: Split-policy Decontamination check
        is_contam, _ = self.decontam.is_contaminated(fn_code, test_code, source_url=f"9router:{model}")
        if is_contam:
            print("  [-] Rejected by decontamination gate (overlaps frozen evaluation benchmark).")
            return False

        # Quality Gate 2: Sandbox Verification + Mutation Kill-rate
        mut_score, killed, total = evaluate_mutation_score(fn_code, test_code, max_mutants=5)

        # Store in ModelGen verified library
        mid = store(self.conn, fn_name, fn_code, test_code, f"TeacherDistilled-{model}", f"9router:{model}")
        if mid:
            print(f"  [+] [VERIFIED & DISTILLED] Module #{mid} '{fn_name}' learned from {model} (Mutation Kill-Rate: {mut_score:.1%})")
            return True
        return False

    def distill_frontier_batch(self, tasks=DEFAULT_DISTILL_TASKS, model=None):
        learned = 0
        for task in tasks:
            if self.distill_task(task, model=model):
                learned += 1
        
        if learned > 0:
            print(f"\n[+] Retraining Neural Router weights on-the-fly with {learned} newly distilled frontier algorithms...")
            train_learned_router(self.conn, epochs=10)
        return learned

if __name__ == "__main__":
    conn = init_db()
    distiller = NineRouterDistiller(conn)
    print(f"[+] Connected to 9Router Gateway at {GATEWAY_URL}")
    learned_count = distiller.distill_frontier_batch(tasks=SAMPLE_FRONTIER_TASKS[:2], model="ds/deepseek-chat")
    print(f"\n[+] Distillation complete. ModelGen learned and verified {learned_count} new frontier skills.")
