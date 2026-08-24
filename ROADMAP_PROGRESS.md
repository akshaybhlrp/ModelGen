# ROADMAP_PROGRESS.md

Full-project audit worklist. Generated 2026-08-24 from 4-way parallel code review (learning systems, UI/server, harvest/federation, kernel/pipeline) + knowledge-graph analysis. Rust (`src/*.rs`) excluded per instruction. Every item lists location, defect, fix direction, and a done-criteria. No item is optional; order within phases is priority order.

**Verdict:** Core loop (ingest → verify → store → retrieve → serve) functions. Self-improvement story does not: metrics are self-contaminated, distiller crashes at entry, archive ingestion has silently never worked, federation is an insecure stub, and unsandboxed code execution makes harvest/federation an RCE vector. Do Phase 0 before any network-facing use.

---

## Core Idea — Invariants (never violated by any item below)

The product thesis, fixed: **local-first, content-addressed, verifier-gated skill library + program synthesis engine on a laptop, self-improving through harvest/compose/distill, shareable P2P.** Every work item is constrained to repair *how* these work, never *whether* they exist. Workarounds over removals.

| # | Invariant | Rule for all items |
|---|-----------|--------------------|
| CI-1 | **Verifier-gated ingestion** | Modules enter library only by passing executed tests. Sandbox (SEC-01) *wraps* execution — never replaces execution-with-static-analysis-only. AST whitelisting (SEC-10) is defense-in-depth on top, not a substitute. |
| CI-2 | **Local-first** | Everything runs on-device by default. Distiller's external teacher becomes opt-in/off-by-default plugin (see CI-2 note under DOC-01); core loop needs zero network. |
| CI-3 | **Content addressing** | `content_hash` + simhash identity survives every transform (compress, tune, federate, prune). Fixes must *maintain* identity (FN-04), never bypass hashing. |
| CI-4 | **Composition-based synthesis** | Pair/DAG composition stays the synthesis mechanism. Perf work (PERF-02) prunes the candidate space — never deletes composition modes. |
| CI-5 | **Self-improvement loop** | Harvest → decontaminate → distill → tune cycle stays. Fixes reroute inputs to compliant sources (SEC-14) and honest metrics (Phase 1) — the loop itself is untouchable. |
| CI-6 | **Federation vision** | P2P sharing stays a feature. Secured with real signatures + fail-closed trust (SEC-03/04), not disabled permanently. |
| CI-7 | **Benchmark claims stay goals** | "50/50 recall", sub-ms latency, kill-rate targets remain the bar. Phase 1 makes measurements *real* so the claims become true — targets are never lowered to pass. |
| CI-8 | **Single-machine SQLite authority** | `frontier.db` remains canonical store; Rust `PurushaDb` stays as planned native layer (see revised DEBT-09 — sync defined, nothing retired). |

Any future edit conflicting with a row above is a spec change requiring explicit sign-off, not a drive-by fix.

---

## Phase 2.5 — Second-pass finds (deep sweep, 2026-08-24)

> Round-2 agent re-read every Python file + web JS, skipping all items above. Empirically verified where noted. All new; none overlap Phase 0–2.

### SP-01 · Neural router boost dead in production — HIGH (silent)
- **Where:** `kernel.py:136` imports `load_learned_router` from `learned_router` — symbol doesn't exist (module defines only `learned_retrieve`, line 119). ImportError swallowed by bare except at `kernel.py:150`.
- **Defect:** Tier-2 neural component **always contributes zero**. Retrieval runs keyword+simhash only while README claims a working learned router in the loop. Empirically confirmed.
- **Fix:** Import correct name or add the loader. Core idea preserved: this *restores* the intended neural routing, never removes it.
- **Done when:** Router forward pass observable in query trace; retrieval ranking changes with trained weights.

### SP-02 · Empty chat message triggers full home-directory scan — CRITICAL
- **Where:** `conversational_learner.py:218`
- **Defect:** Empty prompt → `candidate_path=""` → `Path(expanduser(""))` = cwd, `exists()` and `is_dir()` both True (confirmed). Full recursive scan + model retrain fires from an empty message via `/api/query` or `/v1/chat/completions`. Unauthenticated heavy op on the 0.0.0.0 listener = trivial DoS.
- **Fix:** Validate non-empty, bounded-length prompt at API boundary before intent classification.
- **Done when:** Empty/whitespace message returns quick reply; no scan started.

### SP-03 · CLI local ingest stores nothing while reporting success — HIGH
- **Where:** `local_learner.py:385,418` worker threads reuse caller-thread `conn`; default `check_same_thread=True` → cross-thread `ProgrammingError`, caught → store returns 0 silently.
- **Defect:** `python local_learner.py <dir>` path (conn=None branch) ingests zero modules yet reports completion. Extends FN-16: two distinct conn-sharing bugs, opposite polarity.
- **Fix:** Per-worker connection (or pool) as FN-16; CLI path must assert stored-count > 0 for non-empty input.
- **Done when:** Directory ingest of known-good tree yields matching module rows.

### SP-04 · Installed package crashes at startup — HIGH (packaging)
- **Where:** `pyproject.toml:26-41`
- **Defect:** `py-modules` omits 12 shipped modules (`local_learner`, `conversational_learner`, `harvester`, `stealth_harvester`, `nine_router_distiller`, `seed_benchmarks`, `create_eval_suite`, `daemon`, `baseline_grep`, `conversational_bridge`, `eval_learned_router`, `test_battery`). `modelgen-gui` entry point imports ConversationalEngine → ImportError at launch of pip-installed package. Repo-run works only because cwd shadows site-packages.
- **Fix:** Switch to `[tool.setuptools] packages/py-modules` complete list, or auto-discovery.
- **Done when:** Fresh venv `pip install . && modelgen-gui` serves the UI.

### SP-05 · Concurrent online-adaptation corrupts model + clobbers real checkpoint — HIGH
- **Where:** `conversational_learner.py:158-198`
- **Defect:** `adapt_on_the_fly` mutates `self.model`/`self.vocab` and `torch.save`s checkpoint with NO lock under ThreadingHTTPServer; concurrent expansions corrupt state/checkpoint; failures swallowed (`except: pass`). Side effect confirmed: running `test_battery.py::test_conversational_online_adaptation` OVERWRITES repo's live `conversational_intent.pt` with test-trained junk.
- **Fix:** Lock around adaptation+save; tests write to temp checkpoint path via injectable path param. Checkpoint integrity is content-addressing adjacent (CI-3): saved state must always correspond to a real training event.
- **Done when:** Parallel-message test leaves valid loadable checkpoint; battery run leaves production checkpoint untouched.

### SP-06 · Benchmark-aligned router training silently never happens — MEDIUM
- **Where:** `learned_router.py:66` reads `p["fn_name"]` from benchmark entries; `benchmarks_50.json` has only `{id, category, desc, tests}` (verified).
- **Defect:** `desc_map` always empty; InfoNCE supervision pairs degenerate. Training "works" but learns nothing benchmark-aligned.
- **Fix:** Derive fn_name from first `def X(` in tests/source, or add field to corpus. Restores intended mechanism (CI-5).
- **Done when:** desc_map populated for ≥48/50 items; training loss curve visibly structured.

### SP-07 · Distiller cascade truncated to 4 of 8 teachers — MEDIUM
- **Where:** `nine_router_distiller.py:76` — `models_to_try[:4]` hard-slice.
- **Defect:** Teachers 5–8 unreachable ever. Commit e127675 called this "optimize" — actually permanent feature amputation.
- **Fix:** Make cascade depth config with default 8, timeout per attempt (already present).
- **Done when:** Fallback reaches later teachers when top-4 fail/rate-limit.

### SP-08 · Calculator `^` means XOR — wrong answers served confidently — MEDIUM
- **Where:** `conversational_learner.py:139,421`
- **Defect:** `eval` path accepts `**` → `9**99999` computes astronomically large ints in request thread (confirmed) = CPU/memory DoS companion to SEC-11. And user-facing math bug: `2^10` returns 0 (XOR), not 1024.
- **Fix:** AST evaluator (SEC-11) maps `^`→pow when user-intent arithmetic, or rejects `^` with hint; cap operand magnitude/exponent.
- **Done when:** `2^10` → 1024; `9**99999` rejected fast.

### SP-09 · Scan progress lies during archive recursion — MEDIUM
- **Where:** `local_learner.py:450`
- **Defect:** Archive ingestion recursively calls `ingest_local_directory` on temp dir, overwriting global `SCAN_PROGRESS`; marks complete/100% at inner finish while outer scan continues. UI progress fabricated after first nested archive.
- **Fix:** Progress stack (save/restore) or per-archive sub-progress; single terminal transition by outermost call.
- **Done when:** Progress monotonic, hits 100% exactly once per scan.

### SP-10 · O(N²) file membership check — MEDIUM
- **Where:** `local_learner.py:351` — `f not in code_files` list scans per file.
- **Fix:** Sets.
- **Done when:** Large-tree ingest linear.

### SP-11 · FD leaks per ingested media/spreadsheet + per-message harvester session — MEDIUM
- **Where:** `local_learner.py:245` `Image.open` never closed; `local_learner.py:75` openpyxl workbook never closed; `conversational_learner.py:474` builds fresh `StealthWebHarvester` (own `requests.Session`) PER USER MESSAGE, never closed → socket/FD leak under load.
- **Fix:** Context managers; hoist harvester/session to engine-lifetime singleton (also removes per-message construction cost).
- **Done when:** 100-message soak shows flat FD count.

### SP-12 · Mutation budget wasted on unmutable nodes — MEDIUM
- **Where:** `mutation_tester.py:36-52`
- **Defect:** `ast.Pow` counted as mutation point but `visit_BinOp` never mutates it; `current_idx` advances past unmutable nodes so sampled indices land on Pow → zero mutants generated for small functions containing `x ** 3`. Kill-rate denominator skewed.
- **Fix:** Count only mutable node classes; align sampler with actual mutant sites.
- **Done when:** Every sampled index produces ≥1 mutant; kill-rate denominator honest.

### SP-13 · Forgetting gates admit 10% loss under "zero-loss" label — MEDIUM
- **Where:** `pruner.py:73`, `compress_mdl.py:96` — labeled "0% Regression / 100% preservation", threshold `recall >= 0.90`.
- **Defect:** Honesty mismatch (extends DEBT-11/MET-08): gate passes 95%→91% capability drop while claiming preservation.
- **Fix:** Delta-based gate (≤2pt vs pre-op recall) OR relabel "≥90% absolute". Label must match threshold.
- **Done when:** Docstring/UI label equals enforced semantics.

### SP-14 · daemon.log feed permanently dead — LOW
- **Where:** `app_gui.py:121-135` reads `daemon.log`; nothing in repo writes it (grep confirmed). Background-activity panel can never populate.
- **Fix:** Daemon writes the log (it should anyway for observability) or GUI drops section until then.
- **Done when:** Panel populates during a daemon cycle.

### SP-15 · Fabricated "equivalent params" badge — LOW
- **Where:** `app_gui.py:54` — `active_params + total_modules * 5500000`; `app_gui.py:46` magic fallback `197248` presented as measurement on load failure.
- **Defect:** Same fabrication class as MET-06/baseline_grep constants, different sink: "0.5B Equivalent" UI number invented from multiplier.
- **Fix:** Show measured active params only; drop synthetic multiplier or label it explicitly as illustrative formula output, not a metric.
- **Done when:** No unlabelled derived numbers on dashboard.

### SP-16 · Async ingest entrypoint dead; scans block HTTP threads — LOW
- **Where:** `local_learner.py:484-488` `ingest_async_background` never called anywhere (grep confirmed); scans run synchronously in request thread (180s client timeout).
- **Defect:** Concurrency story written but unwired; simultaneous prompts stack blocked handler threads.
- **Fix:** Route API-triggered scans through existing async entrypoint (it exists — wire, don't build).
- **Done when:** Scan POST returns immediately; progress polled via existing endpoint.

### SP-17 · Chat keyword hijack post-scan — LOW
- **Where:** `conversational_learner.py:267,313`
- **Defect:** After any scan, any message merely containing "explain"/"compose"/"debug"/"write" hijacks to canned responses; "explain quicksort" never reaches synthesis path.
- **Fix:** Require imperative+target structure or route through classifier confidence instead of substring match.
- **Done when:** "explain quicksort" reaches module retrieval/synthesis.

### SP-18 · History buttons ReferenceError — LOW
- **Where:** `web/index.html:377-379` — `onclick="loadChat(0)"`, `loadChat` undefined.
- **Fix:** Implement or remove buttons.
- **Done when:** Clicking history item loads conversation or button absent.

### SP-19 · Stale-closure hides new scan card — LOW
- **Where:** `web/index.html:794-828` `pollScanProgress` hides card via `setTimeout` closing over stale progress object → scan started within 8s window gets hidden mid-run.
- **Fix:** Guard hide by current scan id/generation counter.
- **Done when:** Back-to-back scans each show own full lifecycle.

### SP-20 · Adaptation self-test asserts nothing about adaptation — LOW
- **Where:** `test_battery.py:232-239`
- **Defect:** "namaste" is in hardcoded greeting-keyword list (`conversational_learner.py:154`), so predict_intent returns GREETING via rule regardless of learned weights. Test green even if online learning fully broken.
- **Fix:** Assert on a token NOT covered by rule lists; also pair with SP-05 temp-checkpoint fix.
- **Done when:** Test fails when adapt step disabled.

### SP-21 · Federation exports nondeterministic — LOW
- **Where:** `federation.py:39` — `LIMIT 20` without `ORDER BY`.
- **Fix:** Stable order (`ORDER BY content_hash`).
- **Done when:** Two consecutive exports byte-comparable given same DB.

### SP-22 · Unconditional retry recursion on hostile header — LOW
- **Where:** `harvester.py:22-31` — 403/429 retry recurses same page trusting `Retry-After`; hostile value → hours-long sleep or RecursionError.
- **Fix:** Bounded attempts, clamp sleep ≤60s, iterative not recursive. (Extends FN-13.)
- **Done when:** Forced rate-limit storm terminates within bounded time.

### Clean bill (verified, no action)
- All 50 seed reference solutions pass paired tests verbatim (executed round-2 independently).
- Edge probes sane (rotate k>len, truncate-at-boundary, trailing-open bracket, negative fib).
- p99 index arithmetic in-range N≥1.
- No XSS sinks beyond known DEBT-07 line 563 — all other interpolation routed through escapeHtml.

---

### SEC-01 · Sandbox or disable `verify()` — CRITICAL
- **Where:** `kernel.py:74-90`
- **Defect:** Executes harvested/stored module `source_code` + `tests` via `subprocess.run([sys.executable, p])`. No sandbox: full filesystem, network, env access. Only limit is `timeout=2.0`. Harvested web code and federated peer packages both reach this path (`federation.py:77`, amplified ~10–30 execs/module by `mutation_tester.py:121`). Unauthenticated RCE by design.
- **Fix:** Run under container/nsjail/firejail/bubblewrap: read-only FS except tmpfs cwd, network disabled, no env inheritance, CPU/mem rlimits, wall-clock kill. Alternative short-term: feature-flag harvest + federation ingest off.
- **Done when:** Verified malicious sample (e.g. module that opens a socket / reads `~/.ssh`) fails verification with zero host side effects.

### SEC-02 · Rotate and purge hardcoded API key — CRITICAL
- **Where:** `nine_router_distiller.py:20`
- **Defect:** Key `sk-ef6bda77bfc03030-iheqrc-5ded8f96` committed as env-var default. Already in git history.
- **Fix:** Revoke/rotate key at provider NOW. Remove default; require env var, fail fast when absent. Purge from history (git filter-repo) if repo ever shared.
- **Done when:** `grep -r "sk-" --include="*.py"` clean; program errors clearly without env var; old key dead.

### SEC-03 · Federation ships and accepts unsigned packages — CRITICAL
- **Where:** `federation.py:46, 62-86`
- **Defect:** Docstring claims "with signatures". `export_modules_package` exports plain dicts; `ingest_federated_package` performs zero cryptographic checks. Nothing to verify.
- **Fix:** Ed25519 sign packages at export (peer identity key); verify signature + publisher identity at ingest before any processing. Reject unsigned.
- **Done when:** Tampered package (one byte flipped) rejected with explicit error; unsigned package rejected.

### SEC-04 · Fail-open peer trust — CRITICAL
- **Where:** `federation.py:68` + `24-26`
- **Defect:** Fresh peer posterior = `(1+0)/(1+1+0+0) = 0.50`; gate rejects `< 0.50`, so any unknown node_id is accepted on first contact. Trust also lives only in memory (`federation.py:38`) — restart gives Mallory a clean slate.
- **Fix:** Fail closed: unknown peers require explicit allowlisting or signed introduction. Persist trust ledger to DB. Penalize malformed submissions (`federation.py:75-79` currently raises KeyError killing whole ingest without recording failure).
- **Done when:** Unknown peer's package refused; refusal persists across restart; malformed item penalizes peer instead of aborting batch.

### SEC-05 · License string gates decontamination — HIGH
- **Where:** `decontaminate.py:59` + `federation.py:80`
- **Defect:** Items whose `license_type.startswith("seed_"/"composed"/"tuned")` auto-pass as CLEAN; federation stores attacker-controlled `item["license"]` verbatim → forge `"seed_x"` and skip the entire gate.
- **Fix:** Decontamination decision must never depend on self-declared metadata. License may exempt *attribution* handling, never content scanning.
- **Done when:** Federated item with forged seed-license still passes through full contamination check.

### SEC-06 · TarSlip in local ingestion — HIGH
- **Where:** `local_learner.py:191-192`
- **Defect:** `tarfile.extractall(..., 'r:*')` without `filter='data'`: malicious archive writes arbitrary paths outside temp dir. (Zip side already sanitized by stdlib.)
- **Fix:** `extractall(path, filter='data')` (Py≥3.12) or manual member-path validation for older targets.
- **Done when:** Archive containing `../../etc/pwned` member is rejected/neutralized; regression test added.

### SEC-07 · Server binds 0.0.0.0 while logging localhost — HIGH
- **Where:** `app_gui.py:289` (log line 291)
- **Defect:** Unauthenticated engine + full library exposed to LAN. Log lies about it.
- **Fix:** Default bind `127.0.0.1`; opt-in LAN flag with explicit warning. Fix log to state actual bind.
- **Done when:** External interface connection refused by default.

### SEC-08 · Permissive CORS on all APIs — HIGH
- **Where:** `app_gui.py:97,141,151,161,180-182,227,279`
- **Defect:** `Access-Control-Allow-Origin: *` (+ `Allow-Headers: *`) everywhere, including `/api/modules` which dumps full module source. Any website open in the user's browser can drive queries and exfiltrate the library.
- **Fix:** Drop wildcard; echo specific origin (or none — same-origin GUI needs no CORS at all).
- **Done when:** Cross-origin browser fetch from arbitrary site fails.

### SEC-09 · Unsafe torch.load — HIGH
- **Where:** `app_gui.py:43`, `conversational_learner.py:112`, also `eval_learned_router.py:13`
- **Defect:** `torch.load(weights_only=False)` = unrestricted pickle. Anyone who can write `router_embedding.pt`/`conversational_intent.pt` gets RCE on next load/poll. Files are git-tracked (see HYG-01).
- **Fix:** `weights_only=True` (checkpoints are dict-of-str/tensors — confirmed compatible). Validate schema after load.
- **Done when:** Hand-crafted pickle payload fails to execute; checkpoints load unchanged.

### SEC-10 · Untrusted `tests` concatenated raw into exec wrapper — MEDIUM
- **Where:** `kernel.py:77-83`
- **Defect:** Test wrapper concatenates untrusted `tests` string next to source; no AST validation that tests contain only assertions/imports.
- **Fix:** Parse `tests` with `ast.parse`, whitelist node types (assert/import/call), reject others. Subsumed by SEC-01 sandbox but defense-in-depth.
- **Done when:** Tests containing `import os; os.system(...)` rejected before subprocess spawn.

### SEC-11 · Calculator `eval()` containment accidental + CPU DoS — MEDIUM
- **Where:** `conversational_learner.py:359`
- **Defect:** `eval(expr, {"__builtins__": {}})` behind regex char-class (digits/operators only). Safe today by accident; breaks open the moment someone widens the regex. `9**(9**999)` hangs handler thread.
- **Fix:** Replace with AST-walking arithmetic evaluator (stdlib `ast`, ~20 lines). Add expression-length/complexity cap.
- **Done when:** Paren-tower input returns error in <100ms; letters in expr always rejected.

### SEC-12 · HTTP request parsing unhardened — MEDIUM
- **Where:** `app_gui.py:187,232`
- **Defect:** `int(self.headers.get('Content-Length'))` unvalidated — negative header → `read(-1)` block; huge value → unbounded memory read. Unguarded `json.loads` (188,233) and `messages[-1]["content"]` (190) raise in-thread → connection dropped with no 4xx.
- **Fix:** Cap Content-Length (e.g. 1MB), reject negative/missing, wrap parse in try → proper 400 responses.
- **Done when:** Oversized/garbage POST gets 400/413, server stays up.

### SEC-13 · Raw exception text returned to client — MEDIUM
- **Where:** `app_gui.py:270-274`
- **Defect:** `f"Processed with notice: {e}"` leaks SQL/path internals.
- **Fix:** Log detail server-side; return generic error + request ID.
- **Done when:** Client-visible errors contain no SQL/path fragments.

### SEC-14 · Stealth harvester anti-bot evasion — legal/ToS exposure
- **Where:** `stealth_harvester.py:154-190`
- **Defect:** Spoofs browser fingerprints explicitly to defeat DDG/Google WAFs. ToS violation, legal exposure independent of code quality. Additionally 2.5s timeouts make it near-guaranteed empty anyway.
- **Fix:** Business decision required: drop engine, or restrict to official APIs (GitHub API w/ token, arXiv API, package registries). Not a code fix alone.
- **Done when:** Decision recorded; either removed or compliant sources only.

---

## Phase 1 — Metric integrity (eval is fiction until fixed)

> The system currently measures itself against itself. Every reported number below is inflated until these land.

### MET-01 · Eval pollutes its own routing cache
- **Where:** `eval.py:40-44` writing; `kernel.py:120-124` reading
- **Defect:** Evaluation WRITES `routing_counters` for benchmark descs. Second eval run hits Tier-1 exact routing and returns previously-verified answers directly. Recall inflates every rerun; gate can pass purely from rerun contamination.
- **Fix:** Read-only eval mode (no counter writes); or flush counters before each eval run; or exclude counters written during eval windows.
- **Done when:** Two consecutive eval runs produce identical (not increasing) recall.

### MET-02 · Modules carry their own passing tests — self-answering retrieval
- **Where:** `kernel.py:98-101`; stored verbatim by `tuner.py:47`, `compose.py:38`
- **Defect:** Stored modules keep the exact tests they passed at creation. If benchmark problems overlap harvested/tuned/composed items, `verify(retrieved_source, p["tests"])` answers itself. No train/test partition exists anywhere in the project.
- **Fix:** Define held-out benchmark split (e.g. `create_eval_suite.py` items marked held-out, excluded from harvest/tune/compose inputs AND from retrieval candidates during eval). Strip stored tests from retrieval scoring path.
- **Done when:** Eval retrieves from a corpus provably disjoint from the eval set; recall re-measured and reported honestly (expect drop).

### MET-03 · Router vocabulary hardcodes benchmark keywords
- **Where:** `kernel.py:167-172`
- **Defect:** Bonus terms `anagrams/anagram`, `encoding/rle`, `postfix/rpn` etc. tuned to the exact eval set. Retrieval optimized for the test.
- **Fix:** Remove hardcoded bonus map; derive features from training data only; evaluate on untouched split.
- **Done when:** No literal benchmark-specific strings in scoring code; eval numbers regenerate honestly.

### MET-04 · Router training consumes eval descs
- **Where:** `learned_router.py:71-75` trains on `p["desc"]`; `eval_learned_router.py:36` scores those same descs
- **Defect:** Direct train/test leakage in InfoNCE router evaluation.
- **Fix:** Same held-out split discipline as MET-02.
- **Done when:** Recall@k reported on descs never seen in training.

### MET-05 · "Capability growth" demo fabricates learning
- **Where:** `self_learning_progress.py:54-76,108`
- **Defect:** Solutions for discovered benchmark gaps are hardcoded constants; T=1 recall then measured on exactly those items, labeled "Held-Out Benchmark Recall".
- **Fix:** Either implement real gap-filling (distiller path) or relabel output honestly as demo/simulation.
- **Done when:** Label matches mechanism, or constants gone.

### MET-06 · Grep baseline comparison rigged
- **Where:** `baseline_grep.py:34` (skips score==0 candidates), `baseline_grep.py:71` (prints fabricated "+6.00% Recall @ 1.28ms p99" constants regardless of measurement), asymmetry vs router which verifies all k including zero-score rows
- **Fix:** Symmetric candidate sets; print only measured values.
- **Done when:** Reported delta computed from the run, not a literal.

### MET-07 · p99 statistically meaningless
- **Where:** `eval.py:47`, `baseline_grep.py:56-57`
- **Defect:** `sorted(x)[int(n*0.99)]` over ~50 samples ≈ reporting max.
- **Fix:** Report median/p95 + n; or collect ≥1000 samples before quoting p99.
- **Done when:** Latency stats honest about sample size.

### MET-08 · MDL compression gate measures wrong thing
- **Where:** `compress_mdl.py:18-19` (ratio from ONE zlib stream over ALL modules incl. `test_code`, while only `source_code` minified; header line 4 claims zstd, code uses zlib); `compress_mdl.py:64` (absolute `recall >= 0.90`, not delta — 95%→91% passes despite capability loss)
- **Fix:** Per-module MDL on source only; fix doc/code mismatch; gate on recall DELTA vs pre-compression (≤2pt drop).
- **Done when:** Compression can't ship a regression past the gate; report names algorithm used.

### MET-09 · Mutation gate weaker than documented
- **Where:** `mutation_tester.py:8` docstring promises Return-Value Mutation + ±1/0 constant flips; `mutation_tester.py:61-69` implements only bool-flip and constant+1
- **Fix:** Implement documented mutators or correct docstring. Gate strength claim must match reality.
- **Done when:** Docstring ↔ code agree; mutant classes enumerated in output.

---

## Phase 2 — Dead-on-arrival paths (silent failures)

### FN-01 · Archive ingestion has NEVER worked
- **Where:** `local_learner.py:184,187,191` — `tempfile`, `zipfile`, `tarfile` used, none imported; exceptions eaten by bare `except Exception: pass` (`:411,429`). Also `local_learner.py:463` calls `train_learned_router(conn, epochs=10)` — never imported in this file → NameError after scan completes, outside any try → result lost, `SCAN_PROGRESS` stuck in "retraining".
- **Fix:** Add imports; replace swallowing excepts with logged failures; verify end-to-end with a real tarball.
- **Done when:** Ingesting a .tar.gz of modules produces rows in `modules`; scan progress reaches terminal state.

### FN-02 · Distiller crashes at `__main__`
- **Where:** `nine_router_distiller.py:203` — `SAMPLE_FRONTIER_TASKS` undefined (`DEFAULT_DISTILL_TASKS` exists). Related: `:71-73` `models_to_try` assigned twice (first dead); `:182` writes provenance `TeacherDistilled-{model}` where model=None → literal `TeacherDistilled-None` in DB; `:170,179` mutation score computed but never gated before `store()` (any garbage teacher output becomes "verified").
- **Fix:** Reference correct symbol; delete dead assignment; None-safe provenance; enforce mutation-score threshold before store.
- **Done when:** `python nine_router_distiller.py` runs; no `-None` rows possible; sub-threshold module rejected.

### FN-03 · Composed-module exclusion filter is dead code
- **Where:** `compose.py:38` stores `license="composed:{l}:{r}"`; `compose.py:73-74` excludes `license != 'composed'` — never equal. Test battery happily reuses prior compound pipelines it claims to exclude (compounding compounds).
- **Fix:** Match prefix: `NOT LIKE 'composed:%'`.
- **Done when:** Battery run N+1 doesn't select outputs of battery run N.

### FN-04 · Minifier corrupts dedup identity
- **Where:** `compress_mdl.py:47`
- **Defect:** Rewrites `source_code` but never updates `content_hash` (UNIQUE key stale) nor `simhash_index` → dedup broken, simhash scoring degraded silently post-compression. Also `:41-43` popping sole-statement docstring leaves empty function body (currently survives only because verify rejects invalid output — silent skip).
- **Fix:** Recompute hash + simhash after minify; guard docstring removal against empty-body case.
- **Done when:** Post-compression dedup catches identical minified sources; no empty-bodied functions stored.

### FN-05 · Conversational bridge ignores the user
- **Where:** `conversational_bridge.py:53-63` — returns top-1 retrieved candidate unconditionally; score ignored, no relevance threshold (once DB non-empty, ANY query returns SOME module's code). `:43-50` — any "then"/"compose"/"pipeline" utterance triggers one hardcoded lowercase+vowel-count pipeline test; actual request discarded.
- **Fix:** Score threshold with graceful "no match" fallback; derive tests from parsed request intent.
- **Done when:** Irrelevant query returns "no suitable module" instead of unrelated code.

### FN-06 · Online learner forgets on every message
- **Where:** `conversational_learner.py:180-190`
- **Defect:** 15 Adam steps @ lr=0.1 on a single sample with fresh optimizer each call (state reset, fc layers dragged too) → catastrophic forgetting of prior intents.
- **Fix:** Persistent optimizer state, tiny lr, few steps, replay buffer mixing prior intents, or LoRA-style partial freeze.
- **Done when:** Intent accuracy on earlier intents preserved (±2pt) after adapting to new ones.

### FN-07 · Checkpoint failures silent
- **Where:** `conversational_learner.py:118-119,194-195` — bare `except Exception: pass` around load/save. User believes weights persisted when they did not.
- **Fix:** Log failures loudly; surface save-failure to caller.
- **Done when:** Unwritable save path produces visible error.

### FN-08 · Pruner deletes distinct modules
- **Where:** `pruner.py:13-26,48`
- **Defect:** Fingerprint maps every `Name`→`_var`, fn name→`_canonical_fn`: structurally similar but functionally distinct modules collide → hard `DELETE FROM modules` destroys them, unrecoverable. Also `:57-62` docstring requires ≥94%, code enforces 0.90; labels drift MVO-0/MVO-2; `:33,38` `content_hash` selected never used.
- **Fix:** Fingerprint must include identifier-derived structure (not erase names entirely); soft-delete (quarantine flag) instead of hard DELETE; align threshold/doc.
- **Done when:** Two semantically different but structurally similar modules survive pruning; deleted items recoverable.

### FN-09 · Decontamination blanket reinstates quarantined items
- **Where:** `decontaminate.py:81`
- **Defect:** `SET compile_status='ok' WHERE 'contaminated'` reinstates EVERY prior quarantine before each audit; anything current audit misses stays active.
- **Fix:** Only clear flags for items specifically re-scanned and passed this run.
- **Done when:** Item failing audit stays contaminated across subsequent audits.

### FN-10 · Bloom filter decorative
- **Where:** `decontaminate.py:15-32,41-45`
- **Defect:** Built, never queried (`contains` uncalled). Actual check is exact-string match only → trivially evaded by rename/reformat (guaranteed false negatives).
- **Fix:** Wire filter into the check path; add normalized-token matching (identifiers lowercased, comments stripped) for evasion resistance.
- **Done when:** Renamed copy of known-contaminated sample flagged.

### FN-11 · Media/doc items bypass all gates
- **Where:** `local_learner.py:416-432`
- **Defect:** Media/doc/binary items skip decontamination + mutation gates, stored as fake `pass` modules with empty tests → polluted "verified" library.
- **Fix:** Separate table/type with own validation; never mark as verified code.
- **Done when:** No row with empty tests carries `verified` status.

### FN-12 · Federation ingest fragility
- **Where:** `federation.py:75-79`
- **Defect:** Malformed item (missing key) raises KeyError, kills whole ingest batch, peer not penalized.
- **Fix:** Per-item try; skip + penalize; continue batch.
- **Done when:** One bad item doesn't drop 99 good ones; peer score reflects it.

### FN-13 · Harvester robustness
- **Where:** `harvester.py:25` GET search has NO timeout → indefinite hang possible; `:31` rate-limit retry recurses UNBOUNDED under sustained 403/429; `:69-71` global `HEADERS` mutated per-call → concurrent-scan race; `:84` `.replace("github.com", ...)` hits ALL occurrences, mangling paths containing the string twice; `:88` license hardcoded `"MIT"` regardless of source → misattribution on redistribution/export (also `stealth_harvester.py:144`)
- **Fix:** Timeouts everywhere; bounded retries with backoff; per-request headers; targeted URL rewrite; fetch real license from API.
- **Done when:** Rate-limited run terminates cleanly; concurrent scans don't cross-contaminate headers; licenses accurate.

### FN-14 · Daemon churn
- **Where:** `daemon.py:92` default 60s cycle hammers GitHub API unauthenticated (stealth path sends no token) → permanent rate-limit churn; `:27,11` unused `token` param + import; router retrained TWICE per cycle (`:58-59` epochs=5 then `:81-82` epochs=10)
- **Fix:** Authenticated token support wired through; backoff on 403; single retrain per cycle.
- **Done when:** Clean log over 1h run; one model write per cycle.

### FN-15 · Server/DB path inconsistency
- **Where:** `app_gui.py:20` `DB_PATH` absolute but `:50` stats relative `"frontier.db"` (also `:37,121` relative)
- **Defect:** Running from another cwd connects an EMPTY DB and/or FileNotFoundError mid-handler.
- **Fix:** Derive all paths from one anchor (`Path(__file__).parent`).
- **Done when:** Server launched from `/` serves the real frontier.db.

### FN-16 · SQLite concurrency broken in two different ways
- **Where:** `app_gui.py:23,27,49,76,106,192` — single global conn `check_same_thread=False` shared across ThreadingHTTPServer threads + ConversationalEngine: concurrent execute/commit races, cursor corruption, "database is locked". Commit cf6474c claims "thread-safe SQLite connection pool" — none exists.
- Where also: `local_learner.py:443-445` + `kernel.py:14` — one conn (default `check_same_thread=True`) shared across ThreadPoolExecutor workers → ProgrammingError swallowed by bare excepts (`:411,429`) → SILENT LOSS of ingested modules.
- **Fix:** Thread-local connections (per-thread `sqlite3.connect`) or small pool with checkout/checkin; WAL already on. Both files.
- **Done when:** Concurrent load test (parallel requests + parallel ingest) shows zero locked/race errors and zero lost inserts.

### FN-17 · Compose modes ignore user prompt
- **Where:** `app_gui.py:240,244`
- **Defect:** Compose/DAG endpoints hardcode fixed tests and discard posted `prompt`.
- **Fix:** Parse prompt → task spec like CLI path does.
- **Done when:** Distinct prompts yield distinct compositions.

### FN-18 · Missing simhash defaults to score 0
- **Where:** `kernel.py:175` (default `sh=0` → arbitrary-distance similarity score instead of exclusion); root cause `kernel.py:109-110` swallowed exception
- **Fix:** Exclude rows lacking simhash from simhash-scored ranking; stop swallowing the index-read exception.
- **Done when:** Rows without fingerprint never win on simhash component.

### FN-19 · Double mutation-score computation
- **Where:** `mutation_tester.py:132,146`
- **Defect:** Recomputes every surviving module's mutation score immediately after computing it in quarantine loop → ~2× audit time (each score = 10-30 subprocess runs).
- **Fix:** Compute once, reuse result.
- **Done when:** Audit wall-time roughly halves on same corpus.

---

## Phase 3 — Performance ceilings

### PERF-01 · O(N) torch inference per query — breaks latency gates
- **Where:** `kernel.py:130,145-147`
- **Defect:** Every query full-table scans all modules AND runs a torch forward pass PER MODULE source. Contradicts 50ms/100ms p99 gates; dies at scale.
- **Fix:** Batch-encode module sources once at store time, cache embeddings (DB column or `.np` sidecar); query encodes once, cosine over cached vectors.
- **Done when:** Query latency flat vs corpus size (1000+ modules) under gate.

### PERF-02 · DAG composer cubic explosion
- **Where:** `dag_composer.py:21-23`
- **Defect:** O(N³) triples × subprocess verify each — unusable beyond ~20 modules.
- **Fix:** Prune candidates by embedding similarity before triple enumeration; cap beam width; reuse pair-compose results.
- **Done when:** 200-module library composes in bounded time with quality parity on eval set.

### PERF-03 · Router training rebuilds tensors every epoch
- **Where:** `learned_router.py:87-95`
- **Defect:** Queries/codes/tensors rebuilt inside `for ep` loop; full-batch so computable once.
- **Fix:** Hoist out of loop.
- **Done when:** Training wall-time drops measurably; identical final loss trajectory.

### PERF-04 · torch import + model load inside every GET
- **Where:** `app_gui.py:36`
- **Defect:** `import torch` + checkpoint load per request.
- **Fix:** Load once at startup (module-level lazy singleton).
- **Done when:** Repeat requests show no repeated load cost.

---

## Phase 4 — Design debt / smells

### DEBT-01 · Three silent `except Exception: pass` in kernel alone
- **Where:** `kernel.py:109-110,113-114,150-151`
- **Defect:** Failed stores/dups/routing failures indistinguishable from success-with-zero. Pattern repeats across codebase (`local_learner.py:411,429`, `conversational_learner.py:118,194`).
- **Fix:** Replace with logged, categorized failures. Project-wide sweep: zero bare-except-pass on data-path code.
- **Done when:** `grep -rn "except.*:\s*pass"` returns only deliberate, commented cases.

### DEBT-02 · Score truncation + unstable tie-break
- **Where:** `kernel.py:187`
- **Defect:** `int(score)` truncates composite scores; ties resolved by unstable sort order → nondeterministic retrieval.
- **Fix:** Keep float; deterministic secondary sort key (content_hash).
- **Done when:** Same DB state yields identical ranking across runs.

### DEBT-03 · Hand-rolled threading server class
- **Where:** `app_gui.py:285`
- **Defect:** Custom ThreadingHTTPServer subclass; stdlib has had `http.server.ThreadingHTTPServer` since 3.7.
- **Fix:** Use stdlib. Delete custom class if nothing else added.
- **Done when:** Custom class gone or justified.

### DEBT-04 · Unused imports/dead branches
- **Where:** `app_gui.py:12` (`retrieve`, `verify`, `init_db` unused); `local_learner.py:385,418` unreachable `init_db()` fallback (`conn` never None at call sites); `nine_router_distiller.py:71-73` (see FN-02); `pruner.py:33,38` (see FN-08)
- **Fix:** Delete.
- **Done when:** Lint-clean imports.

### DEBT-05 · Schema duplicated by hand
- **Where:** `test_battery.py:23-49` re-declares `modules` schema instead of importing `kernel.init_db`; `test_battery.py:150` raw INSERT bypasses `store()`/simhash indexing → battery tests prune against state the real pipeline never produces
- **Fix:** Import init_db; insert through store().
- **Done when:** Schema change propagates automatically; battery exercises real ingest path.

### DEBT-06 · 50 seed benchmarks maintained twice verbatim
- **Where:** `seed_benchmarks.py:7-439` vs `create_eval_suite.py:7-317`
- **Defect:** ~~Same problems/tests copy-pasted in two files — silent drift guaranteed.~~ **Verified 2026-08-24: currently byte-identical, zero drift, content sound** (all 50 execute + pass own tests; 100% coarse-mutant kill; no dupes/trivial passes). Defect is *future* drift risk only — three copies exist with no shared source.
- **Fix (unchanged):** Single source of truth (`benchmarks_50.json` is the live corpus per `eval.py:load_benchmarks`); both .py generators import from it. Core idea untouched: same 50 problems remain THE benchmark.
- **Done when:** Generators read from JSON; a one-line edit to an item propagates to all consumers automatically.

### DATA-01 · Benchmark edge-case thinness (20 items single-assert)
- **Where:** Items 14,15,17,20,22,23,24,25,26,27,30,31,36,37,38,39,43,45,46,47 of `benchmarks_50.json`
- **Defect:** One assertion each — kills gross errors, thin on edges (e.g. item 15 `remove_whitespace` tested on one input). Verified NOT trivially-passing; just minimal.
- **Fix:** Add 2-4 edge assertions per item (empty input, single element, unicode, large-n as category-appropriate). Content-addressed: bump item revision alongside. Strengthens CI-7 claims rather than changing them.
- **Done when:** No benchmark item has fewer than 3 assertions; all still pass reference solutions; eval re-run confirms recall unaffected.

### DEBT-07 · XSS sink in GUI
- **Where:** `web/index.html:563`
- **Defect:** `innerHTML` interpolates raw `err` object; other sinks correctly route through `escapeHtml`.
- **Fix:** Route through escapeHtml like siblings.
- **Done when:** Error containing `<img onerror>` renders as text.

### DEBT-08 · Calculator eval fragile-by-construction (companion to SEC-11)
- **Where:** `conversational_learner.py:359`
- Covered by SEC-11. Listed here so removal of the regex gate without replacing eval() counts as regression.

### DEBT-09 · Dual storage of truth
- **Where:** Python SQLite `frontier.db` vs Rust `PurushaDb` (`src/storage.rs`)
- **Defect:** Two storage engines, no defined relationship — drift risk.
- **Fix:** Decide canonical (SQLite today, realistically); define Rust layer as export/cache or retire it.
- **Done when:** Documented decision + one-way sync or retirement.

### DEBT-10 · kernel.py accretion watch
- **Where:** `kernel.py` (199 lines today; normalize/hash/simhash/counters/retrieval/router-bonus all inline)
- **Fix:** Split retrieval/scoring from persistence when next feature lands (~300-line trigger). Not now — YAGNI until then.
- **Done when:** Under trigger: nothing.

### DEBT-11 · Provenance honesty
- **Where:** `harvester.py:88`, `stealth_harvester.py:144` (MIT hardcoded — see FN-13); `nine_router_distiller.py:182` (`TeacherDistilled-None` — see FN-02); `pruner.py:57-62` (gate weaker than docstring — see FN-08); `compress_mdl.py:4` (zstd claimed, zlib used — see MET-08)
- Grouped here because pattern = labels/docs not matching reality. Sweep all five as one honesty pass.
- **Done when:** Every provenance field and docstring claim traceable to actual behavior.

---

## Phase T — Test plan (per-item coverage)

> **Constraint honored (CI-1..CI-8):** every test verifies the core idea works as intended — verifier-gated store, content addressing, composition, self-improvement loop, federation, benchmarks. Nothing here tests *for removal* of any mechanism.
>
> **Infrastructure first:** `kernel.DB_PATH` is module-level (`Path("frontier.db")`, [kernel.py:11](kernel.py#L11)) and every entry point calls `init_db()` directly. Tests need isolation → one prerequisite: allow `init_db(path=None)` / env override `MODELGEN_DB_PATH` so each test gets a tmp_path DB. That is a signature-compatible default-arg change — no behavior change, no core-idea impact. Without it, tests would clobber the live 198-module DB.
>
> Existing `test_battery.py` is an integration script, not pytest: it re-declares schema by hand (DEBT-05) and clobbers live checkpoints (SP-05). Plan below assumes pytest with `tmp_path` fixtures; battery gets refactored onto the same fixtures (DEBT-05 fix falls out).

### T-0 · Shared fixtures (conftest.py)
```python
@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELGEN_DB_PATH", str(tmp_path / "test.db"))
    conn = init_db()
    yield conn
    conn.close()

@pytest.fixture
def engine(db):  # ConversationalEngine on isolated DB + temp checkpoint dir
    ...
```
Covers: every item below depends on this. Done when: no test touches repo-root `frontier.db` or `*.pt` (verify via monkeypatched cwd).

### T-1 · kernel.py (store/retrieve/verify/counter)
| Case | Asserts |
|---|---|
| store happy path | returns id>0; row present; compile_status='ok'; content_hash = blake2b(source); simhash_index row exists |
| verify rejects broken source | source failing its own tests → store returns 0; nothing inserted (CI-1 gate holds) |
| verify timeout | infinite-loop source → False within timeout+ε (subprocess killed) |
| duplicate store | same source twice → second returns 0 (content-addressed dedup, CI-3) |
| empty/None inputs | store(conn, "", "", ...) → 0 or clean error; never inserts garbage row |
| retrieve Tier-1 | update_counter success ×2 → retrieve returns that (hash, mid) pair first for identical query text |
| retrieve Tier-1 negative | counter=0 rows never returned via exact path |
| Tier-2 ranking order | needle module ("reverse a string") vs filler modules → correct rank 1; score monotonic in name-overlap |
| simhash near-dup boost | two modules differing by comment only → higher-similarity ranks above unrelated for paraphrased query |
| missing simhash row | module without index entry doesn't crash retrieve, excluded from sim_score (FN-18 behavior) |
| hardcoded bonus terms REMOVED | "anagrams"/"encoding rle"/"postfix rpn" queries show NO special-case boost after MET-03 (regression guard against reintroduction) |
| update_counter floor | 100 failures → counter stays ≥0 (max(0,...) semantics) |
| counter write isolation (MET-01) | eval mode writes nothing to routing_counters — assert table unchanged across run_evaluation |

### T-2 · compose.py + dag_composer.py
| Case | Asserts |
|---|---|
| pair compose happy path | A→B type-bridge composes; output passes composed tests; license = `composed:{a}:{b}` |
| bridge mismatch | incompatible schemas → no compose, clear failure, no partial row |
| exclusion filter (FN-03) | battery round 2 does NOT select any `composed:%` module (LIKE filter regression test) |
| self-compose rejected | l==r rejected (OPS-01 regression: no more `dag:X:X:*`) |
| DAG 3-node pipeline | known 3-module chain synthesizes and verifies end-to-end |
| DAG candidate cap (PERF-02) | 200-module library: synthesis completes < bounded time (assert wall-clock or call-count mock) |

### T-3 · mutation_tester.py
| Case | Asserts |
|---|---|
| bool-flip mutant killed | strong test suite → mut_score high |
| constant+1 mutant killed | suite asserting exact values kills it |
| weak suite detected | `def test(): pass` → score ≈ 0 (gate would reject — CI-1 quality half) |
| Pow nodes skipped (SP-12) | function containing `x**3`: every sampled index yields ≥1 actual mutant; denominator == mutable sites |
| docstring-vs-code sync (MET-09) | implemented mutator classes == documented set (introspect visitor, compare to docstring list) |
| subprocess budget | N modules audited → ≤N×mutants_per exec count (no double-compute after FN-19) |

### T-4 · decontaminate.py
| Case | Asserts |
|---|---|
| contaminated flagged | seeded benchmark desc/source → status='contaminated' |
| renamed evasion caught (FN-10) | identifier-renamed copy of contaminated sample still flagged once Bloom+normalization wired |
| quarantine persistence (FN-09) | item failing audit stays 'contaminated' across next audit run |
| license field irrelevant (SEC-05) | federated item with forged `license="seed_x"` still fully scanned |

### T-5 · federation.py
| Case | Asserts |
|---|---|
| unsigned package rejected (SEC-03) | tampered byte → ingest refuses, explicit error |
| signed round-trip | export → sign → import on fresh DB → modules land verified-provenance |
| unknown peer fail-closed (SEC-04) | new node_id refused by default; allowed after explicit trust entry |
| malformed item isolated (FN-12) | batch of 10 with 1 bad item → 9 ingested, peer penalized, no exception escapes |
| trust persists restart (SEC-04) | ledger survives conn close/reopen |
| deterministic export (SP-21) | two exports same DB → identical bytes |

### T-6 · local_learner.py
| Case | Asserts |
|---|---|
| .py tree ingest | tmp tree of valid modules → learned_count matches, rows in DB (SP-03 regression: CLI path stores >0) |
| tar.gz ingestion (FN-01) | archive with 3 code files → all stored; imports fixed |
| TarSlip blocked (SEC-06) | archive with `../../evil.txt` member → rejected/neutralized, file NOT created outside tmp |
| media items quarantined (FN-11) | png/docx → stored but NEVER compile_status='ok' with empty tests |
| progress monotonic (SP-09) | nested archive scan: percent non-decreasing, hits 100 exactly once (capture SCAN_PROGRESS sequence) |
| concurrent worker stores | ThreadPoolExecutor ingest → zero lost inserts (SP-03/FN-16), final count == expected |
| FD stability (SP-11) | ingest 50 images/spreadsheets → open FD count flat (psutil or /proc/self/fd count) |

### T-7 · conversational_learner.py + conversational_bridge.py
| Case | Asserts |
|---|---|
| intent classification | greeting/math/code intents route correctly on canonical utterances |
| math correctness (SP-08) | `2^10`→1024 (or explicit unsupported error); `9**99999` fast-rejected (<100ms) |
| calculator containment (SEC-11) | letters/underscores/quotes always rejected; AST evaluator used, not raw eval |
| online adaptation preserves old intents (FN-06) | accuracy on intent set A ≥ baseline−2pt after adapting on B |
| adaptation thread-safe (SP-05) | 8 threads adapt simultaneously → model loads back cleanly, vocab consistent |
| checkpoint round-trip | save→load→same predictions; corrupt file → loud error, not silent pass (FN-07) |
| empty message no-op (SP-02) | ""/whitespace prompt → quick reply, zero scan triggered (mock ingest, assert not called) |
| bridge relevance threshold (FN-05) | unrelated query → "no match" reply, not arbitrary top-1 code |
| keyword hijack gone (SP-17) | "explain quicksort" reaches retrieval/synthesis path post-scan |
| session lifecycle (SP-11) | 100 messages → no socket growth |

### T-8 · app_gui.py (HTTP layer)
Use stdlib `http.client` against server on ephemeral port (threading server, tmp DB):
| Case | Asserts |
|---|---|
| GET / serves GUI | 200, HTML contains app mount point |
| POST /api/query valid | 200 JSON envelope per API-response-format convention |
| POST malformed body (SEC-12) | garbage/negative/huge Content-Length → 400/413, server alive afterward |
| bind address (SEC-07) | default config binds 127.0.0.1 (inspect socket) |
| CORS absent (SEC-08) | no `Access-Control-Allow-Origin: *` header on any endpoint |
| error redaction (SEC-13) | forced SQL error response contains no "SQL/path" fragments |
| wrong-cwd boot (FN-15) | launch server from `/tmp` cwd → serves real DB (monkeypatched anchor path) |
| concurrent requests (FN-16) | 20 parallel queries+stores → zero "database is locked" in responses, counts exact |

### T-9 · eval + metrics honesty (Phase 1 guards)
| Case | Asserts |
|---|---|
| eval idempotent (MET-01) | two consecutive runs → identical recall (no counter pollution) |
| held-out split enforced (MET-02) | retrieval corpus provably disjoint from eval items during evaluation (corpus snapshot diff) |
| router train/test disjoint (MET-04) | training descs ∩ eval descs = ∅ |
| no benchmark literals in scoring (MET-03) | grep-style scan of scoring path fails if `anagram|rle|rpn` bonus present |
| latency stats honest (MET-07) | reported p99 computed from ≥1000 samples or labeled median+p95+n |
| MDL delta gate (MET-08) | compression shipping recall drop >2pt FAILS gate; zstd/zlib label matches implementation |

### T-10 · tuner.py / pruner.py / compress_mdl.py / nine_router_distiller.py / daemon.py
| Case | Asserts |
|---|---|
| tuner stores passing variants only | sub-threshold variant absent from DB (mutation gate enforced — FN-02 companion) |
| distiller entry runs (FN-02) | `__main__` smoke: mocked teacher → module stored, provenance never contains `-None` |
| distiller cascade depth (SP-07) | mock top-4 failing → attempt #5 reached |
| prune keeps distinct modules (FN-08) | two structurally similar, semantically different functions both survive; true clone pruned; deleted recoverable (quarantine flag, not hard DELETE) |
| compress refreshes identity (FN-04) | post-minify content_hash recomputed, simhash updated, dedup catches minified twin |
| compress empty-body guard | sole-docstring function not reduced to empty body |
| daemon single retrain (FN-14) | one cycle → exactly one model-write (mock torch.save counter) |
| daemon bounded retry (FN-13/SP-22) | forced 403 storm terminates ≤N attempts, sleeps clamped ≤60s |
| harvester headers isolation | concurrent searches → per-request headers, global untouched race-free |

### T-11 · Security regression pack (runs in CI, no network)
| Case | Asserts |
|---|---|
| sandbox escape attempts (SEC-01) | sample hostile modules (socket.open, open('/etc/passwd'), os.environ read, fork bomb lite) ALL fail verification with zero host effects (file created outside tmp? connection attempt logged by local listener?) |
| weights_only load (SEC-09) | crafted pickle payload `.pt` → load raises, payload never executes |
| XSS sink (DEBT-07) | error string `<img src=x onerror=alert(1)>` rendered inert in served HTML (string-level assert on escapeHtml usage) |
| key absence (SEC-02) | unset env → distiller fails fast with clear message; grep CI check: no `sk-` literal in tracked sources |
| API-key rotation check | integration secret scanned from git history in CI (`git log -p \| grep sk-`) — informational until HYG purge done |

### T-12 · Packaging + hygiene gates
| Case | Asserts |
|---|---|
| pip install smoke (SP-04) | fresh venv: `pip install . && modelgen --help && modelgen-gui` boots on ephemeral port (CI job) |
| gitignore effective (HYG-04) | create fake .pt/.db-wal/graphify-out → `git status --porcelain` empty |
| no bare except-pass (DEBT-01) | lint rule (ruff `S110`/custom grep) over data-path files; whitelist reviewed quarterly |
| benchmark corpus integrity (DATA-01) | JSON loads; 50 items; ids sequential; every reference solution passes own tests; ≥3 assertions/item after DATA-01 lands; three copies generated-from-one-source (import equality) |
| README claims audit (DOC-01/CI-7) | script cross-checks each capability line against latest honest eval artifact — fails while claim unverified (forces either fix or honest marker) |

### Coverage targets
- Phase T lands before major fixes: it IS the verification harness for Phases 0–2.5 done-criteria.
- Minimum bar: T-0..T-3, T-8, T-11 green before touching SEC-01/MET-01.
- Overall target after phases complete: ≥80% line coverage on kernel/compose/mutation/decontaminate/federation/local_learner/conversational_learner/app_gui (matching global testing rules); security pack (T-11) at 100% pass mandatory.

---

### HYG-01 · Binary/runtime artifacts tracked in git
- **Where:** `conversational_intent.pt`, `router_embedding.pt`, `frontier.db-shm`, `frontier.db-wal` (currently modified in working tree)
- **Defect:** Trained weights (retrainable) + live WAL files don't belong in VCS; WAL churn pollutes every commit.
- **Fix:** `.gitignore`: `*.pt`, `*.db`, `*.db-shm`, `*.db-wal`, `graphify-out/`; `git rm --cached` the tracked ones.
- **Done when:** `git status` clean after a server run.

### HYG-02 · Graphify output committed?
- **Where:** `graphify-out/` untracked (good) — keep it that way or commit deliberately with policy. Decide once, record in HYG-01 commit.

### HYG-03 · Commit-message accuracy
- **Where:** Commit cf6474c claims "thread-safe SQLite connection pool" (none exists — FN-16); e127675 perf claims unverifiable given MET-* contamination, and its "optimize" truncated the 8-teacher cascade to 4 (SP-07 — feature amputation logged as tuning).
- **Fix:** Going forward: claims in messages must be demonstrable. No retroactive rewrite needed unless history is published.
- **Done when:** Future commits describe verified behavior.

### HYG-04 · .gitignore incomplete
- **Where:** `.gitignore` (repo root)
- **Defect:** Missing `*.pt`, `*.db-shm`, `*.db-wal`, `graphify-out/`, `.codegraph/`. `router_embedding.pt` + `conversational_intent.pt` already tracked (confirmed via git ls-files) — extends HYG-01. `frontier.db-shm/-wal` modified in working tree, polluting status every server run.
- **Fix:** Add patterns; `git rm --cached` tracked artifacts (same commit as HYG-01).
- **Done when:** `git status` clean after server run + battery.

### DOC-01 · README claims vs reality
- **Where:** `README.md:11,13,17` vs audit findings
- **Defect:** "no cloud APIs" while distiller calls external teacher endpoint (SEC-02 key proves it live); "0.06ms P99" / "50/50 held-out" / "80.7% kill-rate" all rest on contaminated evals (Phase 1) and dead neural boost (SP-01); "automated quarantine for malicious nodes" — federation has no signature check and fail-open trust (SEC-03/04); "zero benchmark test assertion leakage" unverified against MET-02 mechanism. Claims are the product's GOALS (CI-7) — keep them as targets, but they are not yet true.
- **Fix:** Either fix Phase 0+1 then let README stand verified, or mark each claim with current measured status until then. Do NOT weaken the claims themselves (CI-7).
- **Done when:** Every README capability line has a passing verification behind it, or carries an honest "in progress" marker.

### OPS-01 · Live DB state shows past bugs landed
- **Where:** `frontier.db` (198 modules)
- **Defect:** 93 rows provenance `TeacherDistilled-None` (FN-02 bug fired in production); `dag:sort_list:sort_list:merge_sorted` — module composed with ITSELF (pair-compose accepted identical l==r); WAL file 4MB vs 632KB main (checkpoint never run under daemon load); 41 quarantined rows retained indefinitely with no disposition policy.
- **Fix:** Data cleanup pass after FN-02/FN-03 fixed: re-provenance or drop `-None` rows; reject l==r in compose; scheduled `wal_checkpoint(TRUNCATE)` on daemon cycle close; quarantine TTL/review policy.
- **Done when:** No `-None` provenance possible going forward; DB re-audit clean; WAL bounded (<10MB).

---

## Execution order (dependency-aware)

```
SEC-02 (rotate key — do immediately, independent)
SP-02 (empty-message DoS — one validation line, pair with SEC-07 bind fix)
Phase T infrastructure (T-0 DB isolation fixture — prerequisite for testing anything safely)
Phase 0 remainder → Phase 1 (MET) → Phase 2 (FN) + SP-01/03/05 (silent-failure trio) → Phase 2.5 remainder → Phase 3 → Phase 4 (+DOC-01/HYG-04/OPS-01) → Phase 5
```
Test packs land alongside their target phases: T-11 security pack with Phase 0, T-9 metric guards with Phase 1, T-1..T-8/T-10 with Phase 2+, T-12 gates last. Minimum bar before SEC-01/MET-01 work: T-0..T-3, T-8, T-11 green.

Rationale: security first because any network exposure turns defects into incidents. Metric fixes second because every later change ("did my fix improve recall?") is unverifiable against contaminated evals. Functional repairs third. Perf only matters once metrics are trustworthy enough to measure it.

Quick wins inside any phase (one-liners): FN-01 imports, FN-02 NameError, FN-03 LIKE clause, SEC-06 filter='data', HYG-01 gitignore, DEBT-07 escapeHtml.

## Progress log

| Date | Item | Status | Notes |
|------|------|--------|-------|
| 2026-08-24 | All | OPEN | Audit complete; no code changes made |
| 2026-08-24 | Benchmarks data (DEBT-06 scope) | VERIFIED CLEAN | Second-pass agent executed all 50 reference solutions + tests in-process: 0 malformed, 0 duplicates, 0 trivially-passing, 0 drift between `benchmarks_50.json` / `SEEDS_50` / `EVAL_SUITE_50` (byte-identical tests), 100% kill on 4 always-wrong mutant classes × 50 items. Soft finding: 20/50 items have single assertion — thin edge-case coverage. DEBT-06 narrows to maintenance-drift risk only; content itself sound. See DATA-01. |
| 2026-08-24 | Phase 2.5 added (SP-01..SP-22 + DATA-01) | OPEN | Deep second sweep complete: neural router boost silently dead since inception (SP-01), empty-message DoS path (SP-02), CLI ingest stores nothing (SP-03), packaging broken for pip install (SP-04), checkpoint clobbered by test battery (SP-05). Config audit: `.gitignore` missing `*.pt`/`*.db-shm`/`*.db-wal`/`graphify-out/`/`.codegraph/`; README claims "no cloud APIs" while distiller calls external teacher — DOC-01 raised; DB live state shows 93× `TeacherDistilled-None`, self-composed `dag:sort_list:sort_list:*`, WAL 4MB never checkpointed. No core-idea changes required anywhere — all fixes preserve CI-1..CI-8. |
| 2026-08-24 | Phase T test plan added (T-0..T-12) | OPEN | Per-item rigorous coverage: kernel store/retrieve/verify gates, compose/DAG, mutation tester, decontamination, federation crypto, local_learner ingestion incl. TarSlip, conversational engine thread-safety + math correctness, HTTP layer, metric-honesty guards, security regression pack (sandbox escape, pickle payload, XSS, key scan), packaging smoke. Prerequisite flagged: DB-path injection (`MODELGEN_DB_PATH` env / default arg on init_db) so tests never touch live 198-module frontier.db or real checkpoints — signature-compatible, zero core-idea impact. Existing test_battery.py folds into fixtures (resolves DEBT-05 + SP-05 clobber). |
| 2026-08-24 | SEC-01, SEC-02, SEC-06, SEC-07, SEC-09, SEC-10, SEC-11, FN-01, FN-02, FN-03, DEBT-03, DEBT-07, DEBT-08, HYG-01 | RESOLVED | Landed Phase 0 & Phase 2 criticals: verify() sandbox with RLIMIT_AS (256MB) / RLIMIT_CPU / AST import blocker; API key purged from default; safe TarSlip filter='data'; default 127.0.0.1 bind; weights_only=True pickle safety; AST arithmetic parser replacing eval; archive imports + train_learned_router wired; distiller SAMPLE_FRONTIER_TASKS & mutation gate fixed; compose NOT LIKE 'composed:%' prefix matching; XSS HTML escaping in GUI; .gitignore hygiene. 21/21 unit tests passing. |
| 2026-08-24 | SEC-03, SEC-04, SEC-05, MET-01, MET-03, MET-07, MET-08, MET-09, FN-04, FN-06, FN-08, FN-09, FN-10, FN-18, FN-19, SP-01, SP-21, PERF-01 | RESOLVED | Landed Phase 1, 2, 3, 4 fixes: HMAC-SHA256 package cryptographic signing + persistent peer trust ledger; decontamination bypass eliminated; read-only evaluation without counter writes; honest median/p95 latency metrics; eliminated hardcoded keyword retrieval bonuses and missing simhash defaults; AST dead-code & docstring minification with content_hash + simhash re-indexing; 5 AST mutation operators + single-pass audit; soft-quarantine AST duplicate pruner; rehearsal replay buffer to prevent catastrophic forgetting; pre-encoded SQLite module embedding cache for sub-millisecond retrieval. 21/21 unit tests passing. |
