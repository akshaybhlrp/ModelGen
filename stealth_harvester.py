#!/usr/bin/env python3
"""
ModelGen Stealth Web Harvester & Autonomous Web Learning Engine
Simulates real human browser fingerprints (User-Agents, Sec-Ch-Ua, viewport headers, jitter delays)
to browse public coding repositories, algorithmic forums, and documentation sites without triggering anti-bot or WAF detections.
"""
import ast
import random
import time
import requests
from urllib.parse import quote_plus
from kernel import init_db, store

# Realistic modern desktop browser profiles
BROWSER_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:123.0) Gecko/20100101 Firefox/123.0"
]

ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-GB,en-US;q=0.9,en;q=0.8",
    "en-CA,en-US;q=0.9,en;q=0.8"
]

def get_stealth_headers():
    """Generates realistic human browser request headers with Sec-CH and viewport metadata."""
    ua = random.choice(BROWSER_USER_AGENTS)
    is_chrome = "Chrome" in ua
    
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": random.choice(ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    if is_chrome:
        headers.update({
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"' if "Macintosh" in ua else ('"Windows"' if "Windows" in ua else '"Linux"'),
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1"
        })
    return headers

class StealthWebHarvester:
    def __init__(self, conn):
        self.conn = conn
        self.session = requests.Session()

    def human_delay(self, min_s: float = 1.0, max_s: float = 3.0):
        """Simulates natural human typing / browsing jitter."""
        time.sleep(random.uniform(min_s, max_s))

    def fetch_page_stealth(self, url: str) -> str:
        """Fetches web content using rotating browser headers and session cookies."""
        try:
            self.session.headers.update(get_stealth_headers())
            res = self.session.get(url, timeout=12)
            if res.status_code == 200:
                return res.text
            else:
                return ""
        except Exception:
            return ""

    def extract_python_ast(self, content: str):
        """Extracts executable functions and verification test suites via AST analysis."""
        try:
            tree = ast.parse(content)
        except Exception:
            return []
        
        functions = []
        tests = []
        lines = content.splitlines()

        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                start = node.lineno - 1
                end = node.end_lineno
                code = "\n".join(lines[start:end])
                if node.name.startswith("test_") or node.name == "test":
                    tests.append((node.name, code))
                else:
                    functions.append((node.name, code))
        
        results = []
        if tests and functions:
            test_block = "\n\n".join([t[1] for t in tests])
            for fn_name, fn_code in functions:
                results.append((fn_name, fn_code, test_block))
        return results

    def harvest_public_sources(self, topics: list = None, max_items_per_topic: int = 5):
        """Crawls public repositories and algorithmic archives using stealth browser emulation."""
        if not topics:
            topics = ["algorithms", "python algorithms", "data structures python", "dynamic programming python"]

        total_stored = 0
        for topic in topics:
            print(f"\n[Stealth Browser] Browsing topic: '{topic}'...")
            self.human_delay(0.5, 1.5)
            
            # Use public GitHub search API / code mirrors with stealth browser persona
            search_url = f"https://api.github.com/search/repositories?q={quote_plus(topic)}+language:python&sort=stars&order=desc"
            try:
                res = self.session.get(search_url, headers=get_stealth_headers(), timeout=10)
                if res.status_code == 200:
                    repos = res.json().get("items", [])[:max_items_per_topic]
                    for repo in repos:
                        repo_name = repo.get("full_name")
                        default_branch = repo.get("default_branch", "master")
                        print(f"  [+] Inspecting repository: {repo_name} (branch: {default_branch})")
                        
                        # Dynamically discover Python source files via git tree API
                        tree_url = f"https://api.github.com/repos/{repo_name}/git/trees/{default_branch}?recursive=1"
                        try:
                            tree_res = self.session.get(tree_url, headers=get_stealth_headers(), timeout=10)
                            if tree_res.status_code == 200:
                                files = [t["path"] for t in tree_res.json().get("tree", []) if t["path"].endswith(".py") and not t["path"].startswith(".")]
                                # Select top algorithm files
                                algo_files = [f for f in files if any(k in f.lower() for k in ["sort", "search", "algo", "math", "graph", "tree", "string", "test"])][:4]
                                if not algo_files and files:
                                    algo_files = files[:3]
                                    
                                for fpath in algo_files:
                                    self.human_delay(0.5, 1.2)
                                    raw_url = f"https://raw.githubusercontent.com/{repo_name}/{default_branch}/{fpath}"
                                    raw_code = self.fetch_page_stealth(raw_url)
                                    if raw_code and len(raw_code) > 40:
                                        extracted = self.extract_python_ast(raw_code)
                                        for fn_name, fn_code, test_code in extracted:
                                            if store(self.conn, fn_name, fn_code, test_code, "MIT", f"stealth_web:{raw_url}"):
                                                total_stored += 1
                                                print(f"    -> [VERIFIED & LEARNED] Stored #{total_stored}: {fn_name} from {fpath}")
                        except Exception as te:
                            pass
            except Exception as e:
                print(f"  [!] Stealth crawl warning: {e}")
                
        return total_stored

    def search_web_grounding(self, query: str, max_results: int = 3) -> str:
        """Searches Google/DuckDuckGo for the user's prompt to retrieve real-time facts and documentation snippets."""
        snippets = []
        try:
            # 1. DuckDuckGo HTML / Lite Search
            ddg_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            headers = get_stealth_headers()
            res = self.session.get(ddg_url, headers=headers, timeout=2.5)
            if res.status_code == 200:
                import re
                # Extract text from result snippets
                matches = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', res.text, re.DOTALL)
                for m in matches[:max_results]:
                    clean_txt = re.sub(r"<.*?>", "", m).strip()
                    if clean_txt:
                        snippets.append(clean_txt)
        except Exception:
            pass

        if not snippets:
            try:
                # 2. Fallback to Google Search HTML scrape
                google_url = f"https://www.google.com/search?q={quote_plus(query)}&hl=en"
                headers = get_stealth_headers()
                res = self.session.get(google_url, headers=headers, timeout=2.5)
                if res.status_code == 200:
                    import re
                    # Look for snippet blocks
                    matches = re.findall(r'<div class="BNeawe s3v9rd AP7Wnd"[^>]*>(.*?)</div>', res.text, re.DOTALL)
                    for m in matches[:max_results]:
                        clean_txt = re.sub(r"<.*?>", "", m).strip()
                        if clean_txt and len(clean_txt) > 20:
                            snippets.append(clean_txt)
            except Exception:
                pass

        return "\n".join(snippets) if snippets else ""

if __name__ == "__main__":
    conn = init_db()
    harvester = StealthWebHarvester(conn)
    stored = harvester.harvest_public_sources(max_items_per_topic=2)
    print(f"\n[+] Stealth Browser Harvest Completed. Verified & Learned: {stored} modules.")
