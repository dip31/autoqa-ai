"""
AutoQA AI — Autonomous QA Orchestrator v2
Full pipeline: Crawl → Analyze → Generate (25-50 TCs) → Execute → Heal → Report
"""
import os, json, time, re, requests
from playwright.sync_api import sync_playwright
from database.db import execute_query
from dotenv import load_dotenv

load_dotenv(override=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODELS  = ["gemini-flash-lite-latest", "gemini-flash-latest"]

MODE_CONFIG = {
    "Quick Scan":          {"count": 12, "execute_limit": 8},
    "Standard Run":        {"count": 25, "execute_limit": 18},
    "Deep Run":            {"count": 40, "execute_limit": 30},
    "Full Autonomous Run": {"count": 30, "execute_limit": 22},
}
DEFAULT_MODE = "Full Autonomous Run"


# ── Gemini helper ─────────────────────────────────────────────────────────────
def _call_gemini(prompt: str, is_json: bool = True):
    cfg = {"temperature": 0.35, "maxOutputTokens": 8192}
    if is_json:
        cfg["response_mime_type"] = "application/json"
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": cfg}
    last_err = None
    for model in GEMINI_MODELS:
        try:
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={GEMINI_API_KEY}")
            res = requests.post(url, json=payload, timeout=90)
            res.raise_for_status()
            raw = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip()) if is_json else raw.strip()
        except Exception as e:
            last_err = str(e)
    raise Exception(f"Gemini unavailable: {last_err}")


# ── Structured logger ─────────────────────────────────────────────────────────
def _log(run_id, action, detail, status="SUCCESS", tc_id=None, step_num=None, url=None):
    execute_query(
        "INSERT INTO autonomous_execution_logs "
        "(run_id, action_type, action_detail, status, test_case_id, step_number, current_url) "
        "VALUES (?,?,?,?,?,?,?)",
        (run_id, action, str(detail)[:500], status, tc_id, step_num, url)
    )


# ── 4-Stage Self-Healing Engine ───────────────────────────────────────────────
class SelfHealingEngine:
    """
    Stage 1 – Direct Attempt
    Stage 2 – Retry after 1.5s pause (timing / render issue)
    Stage 3 – Relaxed selector (partial ID / class / text)
    Stage 4 – DOM similarity search (token overlap scoring)
    """
    THRESHOLD = 0.48

    def __init__(self, page, run_id):
        self.page   = page
        self.run_id = run_id

    def execute(self, tc_id, tc_title, action, selector, value=None):
        """Run action. Returns {'success', 'healed', 'stage', 'new_selector', 'confidence', 'error'}"""
        last_error = "Interaction failed — no specific error captured"

        # ── Stage 1: Direct ──────────────────────────────────────────────────
        ok, err = self._try(action, selector, value)
        if ok:
            return self._ok("direct", selector)
        last_error = err or last_error

        _log(self.run_id, "HEALING",
             f"[{tc_id}] Direct attempt failed. Error: {last_error}. Starting recovery.",
             "WARNING", tc_id)

        # ── Stage 2: Retry (1.5 s wait) ──────────────────────────────────────
        time.sleep(1.5)
        ok, err = self._try(action, selector, value)
        if ok:
            _log(self.run_id, "HEALING",
                 f"[{tc_id}] Stage 2 (Retry) — success after timing delay.", "SUCCESS", tc_id)
            self._persist(tc_id, tc_title, selector, selector,
                          "Retry resolved transient timing issue", 0.90, "Auto-Healed")
            return self._ok("retry", selector, healed=True, conf=0.90)

        # ── Stage 3: Relaxed selector ─────────────────────────────────────────
        relaxed = self._relax(selector)
        if relaxed and relaxed != selector:
            ok, _ = self._try(action, relaxed, value)
            if ok:
                _log(self.run_id, "HEALING",
                     f"[{tc_id}] Stage 3 (Relax) — recovered with: {relaxed}", "SUCCESS", tc_id)
                self._persist(tc_id, tc_title, selector, relaxed,
                              last_error, 0.75, "Auto-Healed")
                return self._ok("relax", relaxed, healed=True, conf=0.75)

        # ── Stage 4: DOM similarity ───────────────────────────────────────────
        candidates = self._scan_dom()
        best       = self._find_best(selector, tc_title, candidates)
        if best and best["score"] >= self.THRESHOLD:
            ok, _ = self._try(action, best["sel"], value)
            if ok:
                _log(self.run_id, "HEALING",
                     f"[{tc_id}] Stage 4 (DOM Match) — recovered: {best['sel']} "
                     f"(confidence {best['score']})", "SUCCESS", tc_id)
                self._persist(tc_id, tc_title, selector, best["sel"],
                              last_error, best["score"], "Auto-Healed")
                return self._ok("dom_match", best["sel"], healed=True, conf=best["score"])

        # ── All stages failed ─────────────────────────────────────────────────
        _log(self.run_id, "HEALING",
             f"[{tc_id}] All 4 recovery stages exhausted. Failure is unresolved.", "FAIL", tc_id)
        self._persist(tc_id, tc_title, selector, None, last_error, 0.0, "Unresolved")
        return {"success": False, "healed": False, "stage": "failed",
                "new_selector": None, "confidence": 0, "error": last_error}

    @staticmethod
    def _ok(stage, selector, healed=False, conf=1.0):
        return {"success": True, "healed": healed, "stage": stage,
                "new_selector": selector, "confidence": conf, "error": None}

    def _try(self, action, selector, value):
        try:
            if action == "click":
                self.page.click(selector, timeout=6000)
            elif action == "fill":
                self.page.fill(selector, str(value or ""), timeout=5000)
            elif action in ("visible", "check_visible"):
                el = self.page.query_selector(selector)
                if not el or not el.is_visible():
                    raise Exception(f"Element not visible: {selector}")
            elif action == "navigate":
                self.page.goto(selector, timeout=20000, wait_until="domcontentloaded")
            elif action == "check_text":
                if value and str(value).lower() not in self.page.content().lower():
                    raise Exception(f"Expected text not found: '{value}'")
            elif action == "check_url":
                if value and str(value).lower() not in self.page.url.lower():
                    raise Exception(f"URL mismatch — expected '{value}' in '{self.page.url}'")
            elif action == "count":
                if len(self.page.query_selector_all(selector)) == 0:
                    raise Exception(f"No elements matched: {selector}")
            return True, None
        except Exception as e:
            return False, str(e)[:300]

    @staticmethod
    def _relax(selector: str):
        if not selector:
            return None
        if selector.startswith("#"):
            return f"[id*='{selector[1:]}']"
        if "[name=" in selector:
            parts = selector.split("'")
            return f"[name*='{parts[1]}']" if len(parts) > 1 else None
        if selector.startswith("."):
            cls = selector.split(".")[1].split(" ")[0].split(":")[0]
            return f"[class*='{cls}']"
        if "text=" in selector:
            txt = selector.replace("text=", "").strip("'\" ")
            return f"text={txt[:max(4, int(len(txt) * 0.7))]}" if len(txt) > 4 else None
        if ">>" in selector:
            return selector.split(">>")[0].strip()
        return None

    def _scan_dom(self):
        try:
            return self.page.evaluate("""() => {
                const q = 'button, input, a[href], select, textarea, '
                         +'[role="button"], [role="link"], label, [data-testid]';
                return Array.from(document.querySelectorAll(q)).slice(0, 120).map(el => ({
                    tag:  el.tagName.toLowerCase(),
                    text: (el.innerText || el.value || el.placeholder || '').trim().slice(0, 60),
                    id:   el.id || '',
                    name: el.getAttribute('name') || '',
                    type: el.getAttribute('type') || '',
                    role: el.getAttribute('role') || '',
                    aria: el.getAttribute('aria-label') || '',
                    ph:   el.getAttribute('placeholder') || '',
                    cls:  el.className || '',
                    href: (el.getAttribute('href') || '').slice(0, 100),
                    tid:  el.getAttribute('data-testid') || ''
                }));
            }""") or []
        except Exception:
            return []

    @staticmethod
    def _find_best(selector: str, context: str, candidates: list):
        def tok(s):
            return set(w.lower() for w in re.split(r'[#.\[\]=\'"()\s_\-/]', str(s)) if len(w) > 2)

        sel_tok = tok(selector)
        ctx_tok = tok(context)
        best    = None
        for c in candidates:
            blob  = f"{c['text']} {c['id']} {c['name']} {c['aria']} {c['ph']} {c['cls']} {c['href']} {c['tid']}"
            btok  = tok(blob)
            score = min(len(sel_tok & btok) * 0.30 + len(ctx_tok & btok) * 0.15, 1.0)
            if not best or score > best["score"]:
                if c["tid"]:   sel = f"[data-testid='{c['tid']}']"
                elif c["id"]:  sel = f"#{c['id']}"
                elif c["name"]: sel = f"[name='{c['name']}']"
                elif c["aria"]: sel = f"[aria-label*='{c['aria'][:30]}']"
                elif c["text"]: sel = f"text='{c['text'][:30]}'"
                else:           sel = c["tag"]
                best = {"sel": sel, "score": round(score, 2)}
        return best

    def _persist(self, tc_id, step, original, suggested, reason, score, status):
        execute_query(
            "INSERT INTO autonomous_healing_logs "
            "(run_id, test_case_id, step_detail, original_selector, suggested_selector, "
            "failure_reason, confidence_score, status) VALUES (?,?,?,?,?,?,?,?)",
            (self.run_id, tc_id, str(step)[:200], original, suggested,
             str(reason)[:300], score, status)
        )


# ── Page Crawler ──────────────────────────────────────────────────────────────
def _crawl_page(url: str) -> dict:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page    = browser.new_page(viewport={"width": 1280, "height": 720})
            try:
                page.goto(url, timeout=25000, wait_until="domcontentloaded")
                time.sleep(1.5)
                data = page.evaluate("""() => {
                    const t = s => (s || '').trim().slice(0, 80);
                    return {
                        title:     document.title,
                        url:       location.href,
                        h1:        t(document.querySelector('h1')?.innerText),
                        h2s:       Array.from(document.querySelectorAll('h2,h3')).slice(0,10).map(e=>t(e.innerText)),
                        nav_links: Array.from(document.querySelectorAll('nav a,header a,.menu a,.nav a')).slice(0,25)
                                    .map(a=>({text:t(a.innerText),href:(a.getAttribute('href')||'').slice(0,120)})),
                        forms:     Array.from(document.querySelectorAll('form')).slice(0,8).map(f=>({
                                     id: f.id||'', action:(f.getAttribute('action')||'').slice(0,100),
                                     method: f.getAttribute('method')||'get',
                                     inputs: Array.from(f.querySelectorAll('input,textarea,select')).map(i=>({
                                         type:i.type||'text', name:i.name||'',
                                         placeholder:(i.placeholder||'').slice(0,50), required:i.required
                                     }))
                                   })),
                        buttons:   Array.from(document.querySelectorAll('button,[role="button"]')).slice(0,25)
                                    .map(b=>t(b.innerText)).filter(Boolean),
                        inputs:    Array.from(document.querySelectorAll('input,textarea')).slice(0,20)
                                    .map(i=>({type:i.type,name:i.name,placeholder:(i.placeholder||'').slice(0,50)})),
                        links:     Array.from(document.querySelectorAll('a[href]')).slice(0,40)
                                    .map(a=>({text:t(a.innerText),href:(a.href||'').slice(0,120)})),
                        images:    document.querySelectorAll('img').length,
                        has_login: !!document.querySelector('input[type="password"]'),
                        has_search:!!document.querySelector('input[type="search"],input[placeholder*="search" i]'),
                        has_cart:  !!document.querySelector('[class*="cart" i],[id*="cart" i],[href*="cart"]'),
                        has_product: !!document.querySelector('[class*="product" i],[class*="item" i]'),
                        main_text: (document.querySelector('main,.main,#main,article')?.innerText
                                    ||document.body?.innerText||'').trim().slice(0,600)
                    };
                }""")
                flows = []
                if data.get("has_login"):    flows.append("Authentication/Login")
                if data.get("has_search"):   flows.append("Search Functionality")
                if data.get("has_cart"):     flows.append("Shopping Cart")
                if data.get("has_product"):  flows.append("Product Browsing")
                if data.get("forms"):        flows.append("Form Submission")
                if data.get("nav_links"):    flows.append("Navigation")
                data["detected_flows"] = flows
                return data
            finally:
                browser.close()
    except Exception as e:
        return {"title": "Unknown", "error": str(e), "detected_flows": [],
                "forms": [], "nav_links": [], "buttons": [], "inputs": [], "links": []}


# ── Requirement Analysis ──────────────────────────────────────────────────────
def _analyze_requirement(req_text: str, url: str, page_data: dict) -> dict:
    page_summary = {
        "title":          page_data.get("title", ""),
        "detected_flows": page_data.get("detected_flows", []),
        "forms_count":    len(page_data.get("forms", [])),
        "nav_links":      [l["text"] for l in page_data.get("nav_links", [])[:10]],
        "buttons_sample": page_data.get("buttons", [])[:12],
        "has_login":      page_data.get("has_login", False),
        "has_search":     page_data.get("has_search", False),
        "has_cart":       page_data.get("has_cart", False),
    }
    prompt = f"""Analyze this QA requirement and real website crawl data.
Requirement: {req_text}
URL: {url}
Website crawl: {json.dumps(page_summary)}

Return JSON:
{{
  "summary": "2-sentence feature summary",
  "items": ["specific testing area 1", ...],
  "assumptions": ["assumption 1", ...],
  "priority": "High/Medium/Low",
  "coverage_estimate": 0.80,
  "detected_module_type": "e-commerce/blog/SaaS/corporate/portfolio/...",
  "key_user_flows": ["Login and Registration", "Product Search and Filter", ...],
  "risk_areas": ["Checkout flow", "Form validation", ...]
}}"""
    try:
        return _call_gemini(prompt)
    except Exception:
        return {"summary": f"Testing {url}", "items": ["Functional testing"],
                "assumptions": [], "priority": "Medium", "coverage_estimate": 0.7,
                "detected_module_type": "web", "key_user_flows": ["Main navigation"],
                "risk_areas": []}


# ── Rich Test Case Generation ─────────────────────────────────────────────────
def _generate_rich_cases(scope: dict, page_data: dict, count: int) -> list:
    page_ctx = {
        "title":          page_data.get("title", ""),
        "nav_links":      [{"text": l.get("text", ""), "href": l.get("href", "")}
                           for l in page_data.get("nav_links", [])[:15]],
        "forms":          page_data.get("forms", [])[:6],
        "buttons":        page_data.get("buttons", [])[:15],
        "inputs":         page_data.get("inputs", [])[:12],
        "detected_flows": page_data.get("detected_flows", []),
        "has_login":      page_data.get("has_login", False),
        "has_search":     page_data.get("has_search", False),
        "has_cart":       page_data.get("has_cart", False),
    }
    dist = _category_distribution(count)

    prompt = f"""You are a Senior QA Engineer. Generate EXACTLY {count} professional test cases for this website.

SCOPE:
{json.dumps(scope, indent=2)}

REAL WEBSITE STRUCTURE (live crawl):
{json.dumps(page_ctx, indent=2)}

REQUIRED CATEGORY DISTRIBUTION:
{json.dumps(dist)}

RULES:
1. Generate EXACTLY {count} test cases, no more, no less.
2. Base selectors on REAL elements visible in the crawl above.
3. Any test requiring login credentials, payment data, or unavailable state:
   → set automatable=false, blocked_reason="Requires authentication/test data"
4. For automatable=true cases: provide a working Playwright-compatible selector.
5. Write professional QA documentation — detailed steps, clear objectives.
6. Cover: Functional, Negative, Boundary, Validation, Navigation, UI/Visible,
          Form Submission, Error Handling, Edge Cases, Usability.
7. Use realistic input_data values (e.g. "user@test.com", "password123", "", "a"*256).

Return a JSON array of EXACTLY {count} objects with this structure:
{{
  "id": "TC-001",
  "title": "Verify Homepage Title and Branding Are Correct",
  "objective": "Ensure the page title and main heading match expected brand identity",
  "module": "UI/Branding",
  "preconditions": "Browser is open, website URL is accessible",
  "input_data": "N/A",
  "steps": ["1. Navigate to homepage URL", "2. Check browser tab title", "3. Verify H1 heading text"],
  "expected_result": "Browser tab shows correct title; H1 matches brand name",
  "priority": "High",
  "category": "UI/Visible",
  "tags": ["smoke", "ui", "regression"],
  "automatable": true,
  "blocked_reason": null,
  "action": "check_text",
  "selector": "h1",
  "action_value": "{page_data.get('h1', '')}"
}}

Return ONLY the JSON array."""
    try:
        result = _call_gemini(prompt)
        if isinstance(result, list):
            for i, tc in enumerate(result[:count]):
                if not tc.get("id"):
                    tc["id"] = f"TC-{i+1:03d}"
            return result[:count]
    except Exception as e:
        print(f"[TC Generation Error] {e}")
    return []


def _category_distribution(count: int) -> dict:
    scale = count / 30
    return {
        "Functional/Positive":  max(4, int(8 * scale)),
        "Negative":             max(3, int(6 * scale)),
        "Boundary Value":       max(2, int(4 * scale)),
        "Navigation":           max(2, int(4 * scale)),
        "UI/Visibility":        max(2, int(4 * scale)),
        "Form/Validation":      max(2, int(3 * scale)),
        "Error Handling":       max(1, int(3 * scale)),
        "Edge Case":            max(1, int(2 * scale)),
        "Usability":            max(1, int(2 * scale)),
    }


# ── Execution Pipeline ────────────────────────────────────────────────────────
def _execute_test_pipeline(run_id: int, url: str, test_cases: list,
                           execute_limit: int) -> dict:
    results = dict(passed=0, failed=0, healed=0, blocked=0, skipped=0, executed=0)
    _log(run_id, "BROWSER",
         f"Launching Chrome (headless). Execution limit: {execute_limit} test cases.", "SUCCESS")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx     = browser.new_context(viewport={"width": 1280, "height": 720},
                                      user_agent="AutoQA-Agent/1.0")
        page    = ctx.new_page()
        healer  = SelfHealingEngine(page, run_id)

        try:
            _log(run_id, "BROWSER_ACTION", f"Navigating to base URL: {url}", "SUCCESS", url=url)
            page.goto(url, timeout=25000, wait_until="domcontentloaded")
            time.sleep(1)
            title = page.title()
            _log(run_id, "BROWSER_ACTION",
                 f"Page loaded — '{title}'. {len(test_cases)} test cases queued.", "SUCCESS", url=url)

            automatable  = [tc for tc in test_cases if tc.get("automatable", True)
                            and not tc.get("blocked_reason")]
            blocked_tcs  = [tc for tc in test_cases if not tc.get("automatable", True)
                            or tc.get("blocked_reason")]

            # Mark all blocked cases
            for tc in blocked_tcs:
                execute_query("UPDATE autonomous_test_cases SET status='Blocked' WHERE run_id=? AND case_id=?",
                              (run_id, tc["id"]))
                results["blocked"] += 1
                reason = tc.get("blocked_reason", "Requires manual data or authentication")
                _log(run_id, "BLOCKED",
                     f"[{tc['id']}] BLOCKED — {tc.get('title', tc['id'])} | Reason: {reason}",
                     "BLOCKED", tc["id"])

            # Mark overflow as skipped
            to_run  = automatable[:execute_limit]
            to_skip = automatable[execute_limit:]
            for tc in to_skip:
                execute_query("UPDATE autonomous_test_cases SET status='Skipped' WHERE run_id=? AND case_id=?",
                              (run_id, tc["id"]))
                results["skipped"] += 1

            _log(run_id, "BROWSER_ACTION",
                 f"Execution plan: {len(to_run)} to execute, "
                 f"{len(blocked_tcs)} blocked, {len(to_skip)} skipped.", "INFO")

            # Execute each test case
            for step_num, tc in enumerate(to_run, 1):
                results["executed"] += 1
                tc_id    = tc.get("id", f"TC-{step_num:03d}")
                tc_title = tc.get("title", tc.get("scenario", tc_id))
                action   = tc.get("action", "visible")
                selector = tc.get("selector", "body")
                a_value  = tc.get("action_value")
                curr_url = page.url

                _log(run_id, "BROWSER_ACTION",
                     f"[{step_num}/{len(to_run)}] Executing: {tc_id} — {tc_title}",
                     "INFO", tc_id, step_num, curr_url)

                # Navigate-type: go to a full URL
                if action == "navigate" and str(selector).startswith("http"):
                    try:
                        page.goto(selector, timeout=20000, wait_until="domcontentloaded")
                        execute_query("UPDATE autonomous_test_cases SET status='PASS' WHERE run_id=? AND case_id=?",
                                      (run_id, tc_id))
                        results["passed"] += 1
                        _log(run_id, "RESULT", f"[{tc_id}] ✅ PASSED — {tc_title}",
                             "PASS", tc_id, step_num, selector)
                    except Exception as nav_err:
                        execute_query("UPDATE autonomous_test_cases SET status='FAIL' WHERE run_id=? AND case_id=?",
                                      (run_id, tc_id))
                        results["failed"] += 1
                        _log(run_id, "RESULT",
                             f"[{tc_id}] ❌ FAILED — {tc_title} | Navigation unreachable: {str(nav_err)[:150]}",
                             "FAIL", tc_id, step_num)
                        _save_finding(run_id, tc_id, tc_title, str(nav_err))
                    time.sleep(0.3)
                    continue

                # All other actions — use healing engine
                heal = healer.execute(tc_id, tc_title, action, selector, a_value)

                if heal["success"]:
                    if heal["healed"]:
                        execute_query("UPDATE autonomous_test_cases SET status='HEALED' WHERE run_id=? AND case_id=?",
                                      (run_id, tc_id))
                        results["healed"] += 1
                        _log(run_id, "RESULT",
                             f"[{tc_id}] 🛠️ AUTO-HEALED — {tc_title} "
                             f"| Stage: {heal.get('stage')} "
                             f"| New selector: {heal.get('new_selector')} "
                             f"| Confidence: {heal.get('confidence', 0):.0%}",
                             "HEALED", tc_id, step_num, curr_url)
                    else:
                        execute_query("UPDATE autonomous_test_cases SET status='PASS' WHERE run_id=? AND case_id=?",
                                      (run_id, tc_id))
                        results["passed"] += 1
                        _log(run_id, "RESULT", f"[{tc_id}] ✅ PASSED — {tc_title}",
                             "PASS", tc_id, step_num, curr_url)
                else:
                    execute_query("UPDATE autonomous_test_cases SET status='FAIL' WHERE run_id=? AND case_id=?",
                                  (run_id, tc_id))
                    results["failed"] += 1
                    err_msg = heal.get("error", "Unknown failure")
                    _log(run_id, "RESULT",
                         f"[{tc_id}] ❌ FAILED — {tc_title} "
                         f"| All 4 recovery stages exhausted. "
                         f"Selector '{selector}' could not be interacted with.",
                         "FAIL", tc_id, step_num, curr_url)
                    _save_finding(run_id, tc_id, tc_title, err_msg)

                time.sleep(0.4)

        except Exception as e:
            _log(run_id, "ERROR",
                 f"Execution pipeline encountered an unhandled error: {str(e)}", "FAIL")
        finally:
            browser.close()

    return results


def _save_finding(run_id, tc_id, title, error):
    sev = "HIGH" if any(k in title.lower() for k in ["login", "checkout", "payment", "navigation"]) else "MEDIUM"
    execute_query(
        "INSERT INTO autonomous_findings (run_id, title, description, severity, probable_cause) "
        "VALUES (?,?,?,?,?)",
        (run_id, f"[{tc_id}] {title[:100]}", str(error)[:400],
         sev, "Selector mismatch, element state change, or interaction failure")
    )


# ── Risk Analysis ─────────────────────────────────────────────────────────────
def _analyze_risks(run_id, scope, test_cases, results, healing_logs):
    total   = len(test_cases)
    passed  = results.get("passed", 0)
    failed  = results.get("failed", 0)
    healed  = results.get("healed", 0)
    blocked = results.get("blocked", 0)
    executed = results.get("executed", 1)

    pass_rate = (passed + healed) / max(executed, 1)
    readiness = "Ready" if pass_rate >= 0.80 else ("Caution" if pass_rate >= 0.50 else "Not Ready")

    # Weighted risk scoring (0 = perfect, 100 = critical)
    raw_risk = max(5, min(92, int(
        (failed * 18 + blocked * 4 - healed * 7 - passed * 3) / max(total, 1) * 100
    )))
    confidence = round(min(95, pass_rate * 100))

    healed_count = len([h for h in healing_logs if h.get("status") == "Auto-Healed"])
    prompt = f"""Risk assessment for a QA run.
Module: {scope.get('detected_module_type', 'web')}
Flows: {scope.get('key_user_flows', [])}
Results: {total} total, {passed} passed, {failed} failed, {healed} healed, {blocked} blocked
Auto-Healing: {healed_count} successful / {len(healing_logs)} attempts
Risk score: {raw_risk}/100, Readiness: {readiness}

Return JSON (keep risk_score={raw_risk}, readiness="{readiness}", confidence={confidence}):
{{
  "risk_score": {raw_risk},
  "readiness": "{readiness}",
  "confidence": {confidence},
  "high_risk_areas": ["specific risk 1", "specific risk 2", ...],
  "recommendations": ["actionable recommendation 1", ...]
}}"""
    try:
        return _call_gemini(prompt)
    except Exception:
        return {"risk_score": raw_risk, "readiness": readiness,
                "confidence": confidence,
                "high_risk_areas": scope.get("risk_areas", ["Untested modules"]),
                "recommendations": ["Review all failed test cases", "Stabilize selectors"]}


# ── Comprehensive Final Report ────────────────────────────────────────────────
def _build_report(run_id, run, scope, test_cases, results, risk, healing_logs, page_data):
    total    = len(test_cases)
    passed   = results.get("passed", 0)
    failed   = results.get("failed", 0)
    healed   = results.get("healed", 0)
    blocked  = results.get("blocked", 0)
    skipped  = results.get("skipped", 0)
    executed = results.get("executed", 0)
    healed_count   = len([h for h in healing_logs if h.get("status") == "Auto-Healed"])
    unresolved     = len([h for h in healing_logs if h.get("status") == "Unresolved"])
    pass_rate      = (passed + healed) / max(executed, 1)

    if pass_rate >= 0.85:       verdict = "Stable — Ready for Release"
    elif pass_rate >= 0.65:     verdict = "Caution — Important Flows Need Fixes"
    elif pass_rate >= 0.40:     verdict = "High Risk — Core Functionality Unstable"
    else:                       verdict = "Critical — Major Failures Detected"

    prompt = f"""You are a Senior QA Engineer producing a full QA intelligence report.

Website: {page_data.get('title', 'Unknown')} ({run.get('url', '')})
Module Analyzed: {run.get('module_name', 'General')}
Site Type: {scope.get('detected_module_type', 'web application')}
Requirement: {run.get('requirement_text', '')[:400]}

EXECUTION RESULTS:
Total Generated: {total} | Executed: {executed} | Passed: {passed} | Failed: {failed}
Auto-Healed: {healed} | Blocked: {blocked} | Skipped: {skipped}
Self-Healing: {healed_count} recovered / {len(healing_logs)} attempts / {unresolved} unresolved
Risk Score: {risk.get('risk_score')}/100 | Readiness: {risk.get('readiness')} | Verdict: {verdict}
Key Flows: {scope.get('key_user_flows', [])}
Detected Flows: {page_data.get('detected_flows', [])}
High Risk Areas: {risk.get('high_risk_areas', [])}

Generate a COMPREHENSIVE, PROFESSIONAL executive QA report. Return JSON:
{{
  "executive_summary": "3-4 paragraph detailed summary: what was tested, what was found, overall quality",
  "final_verdict": "{verdict}",
  "website_summary": "Detailed description of website type, detected modules, scope",
  "requirement_understanding": "How AI interpreted the requirement and formed testing strategy",
  "major_flows_tested": ["Flow: Navigation — Result: 3/4 passed", ...],
  "passed_summary": "What core features and flows were successfully validated",
  "failed_analysis": "Detailed analysis: what failed, why, severity, affected areas",
  "auto_healing_analysis": "Detailed explanation of healing activity, recoveries, unresolved failures",
  "missing_coverage": ["Area not tested 1", "Area not tested 2"],
  "scoring_explanation": "Why score is {risk.get('risk_score')}/100 — specific weighted factors",
  "test_reliability_insight": "Selector stability observations, UI maturity, improvement suggestions",
  "high_risk_areas": {json.dumps(risk.get('high_risk_areas', []))},
  "recommendations": {json.dumps(risk.get('recommendations', []))}
}}"""

    try:
        report = _call_gemini(prompt)
    except Exception as e:
        report = {
            "executive_summary": (
                f"Executed {total} AI-generated test cases against {run.get('url', 'target website')}. "
                f"Results: {passed} passed, {failed} failed, {healed} auto-healed, {blocked} blocked. "
                f"Overall system readiness: {risk.get('readiness', 'Unknown')}."
            ),
            "final_verdict": verdict,
            "website_summary": f"Analyzed '{page_data.get('title', 'web application')}'",
            "failed_analysis":
                f"{failed} test cases failed. Self-healing recovered {healed_count}.",
            "auto_healing_analysis":
                f"Healing engine attempted {len(healing_logs)} recoveries. "
                f"{healed_count} succeeded, {unresolved} remained unresolved.",
            "recommendations": risk.get("recommendations", []),
            "high_risk_areas": risk.get("high_risk_areas", []),
        }

    # Always inject computed stats
    report["stats"] = {
        "total_generated":    total,
        "total_executed":     executed,
        "passed":             passed,
        "failed":             failed,
        "healed":             healed,
        "blocked":            blocked,
        "skipped":            skipped,
        "healing_attempts":   len(healing_logs),
        "healing_successes":  healed_count,
        "healing_unresolved": unresolved,
        "pass_rate":          round(pass_rate * 100),
        "risk_score":         risk.get("risk_score", 0),
        "readiness":          risk.get("readiness", "Unknown"),
    }
    return report


# ── Main Orchestrator ─────────────────────────────────────────────────────────
def run_autonomous_qa(run_id: int):
    try:
        run  = execute_query("SELECT * FROM autonomous_runs WHERE id=?", (run_id,), fetch=True)[0]
        mode = run.get("execution_mode", DEFAULT_MODE)
        cfg  = MODE_CONFIG.get(mode, MODE_CONFIG[DEFAULT_MODE])

        # Step 0 — Repo Intelligence (Optional)
        repo_url = run.get("repo_url")
        if repo_url:
            execute_query("UPDATE autonomous_runs SET status='Repo Scan' WHERE id=?", (run_id,))
            _log(run_id, "REPO_SCAN", f"Starting repository intelligence scan: {repo_url}")
            from agents.repo_intelligence_agent import RepoIntelligenceAgent
            agent = RepoIntelligenceAgent()
            intelligence = agent.analyze(repo_url)
            
            if "error" not in intelligence:
                execute_query(
                    "INSERT INTO autonomous_repo_intelligence (run_id, analysis_json) VALUES (?,?)",
                    (run_id, json.dumps(intelligence))
                )
                _log(run_id, "REPO_SCAN", 
                     f"Repo scan complete. Detected {intelligence['analysis']['tech_stack']['backend']} / "
                     f"{intelligence['analysis']['tech_stack']['frontend']} stack.")
            else:
                _log(run_id, "REPO_SCAN", f"Repo scan failed: {intelligence['error']}", "WARNING")

        # Step 1 — Crawl page
        execute_query("UPDATE autonomous_runs SET status='Crawling' WHERE id=?", (run_id,))
        _log(run_id, "CRAWL", f"Starting live page crawl: {run.get('url', 'No URL')}")
        page_data = _crawl_page(run["url"]) if run.get("url") else {}
        detected  = page_data.get("detected_flows", [])
        _log(run_id, "CRAWL",
             f"Crawl complete — '{page_data.get('title', 'Unknown')}' | "
             f"Detected flows: {', '.join(detected) or 'General web'} | "
             f"Forms: {len(page_data.get('forms', []))}, "
             f"Buttons: {len(page_data.get('buttons', []))}, "
             f"Links: {len(page_data.get('links', []))}")

        # Step 2 — Analyze requirement
        execute_query("UPDATE autonomous_runs SET status='Analysis' WHERE id=?", (run_id,))
        scope = _analyze_requirement(run.get("requirement_text", ""), run.get("url", ""), page_data)
        execute_query(
            "INSERT INTO autonomous_scope "
            "(run_id, feature_summary, scope_items, assumptions, priority_plan, estimated_coverage) "
            "VALUES (?,?,?,?,?,?)",
            (run_id, scope["summary"], json.dumps(scope["items"]),
             json.dumps(scope["assumptions"]), scope["priority"],
             scope.get("coverage_estimate", 0.80))
        )
        _log(run_id, "ANALYSIS",
             f"Requirement analysis complete. Module: {scope.get('detected_module_type')} | "
             f"Priority: {scope['priority']} | Key flows: {', '.join(scope.get('key_user_flows', []))}")

        # Step 3 — Generate test cases
        execute_query("UPDATE autonomous_runs SET status='Generation' WHERE id=?", (run_id,))
        _log(run_id, "GENERATION",
             f"Generating {cfg['count']} professional test cases in '{mode}' mode…")
        test_cases = _generate_rich_cases(scope, page_data, cfg["count"])

        for tc in test_cases:
            execute_query(
                "INSERT INTO autonomous_test_cases "
                "(run_id, case_id, scenario, case_type, expected_result, priority, generated_by, "
                "title, objective, module_name, preconditions, input_data, steps, category, tags, "
                "automatable, blocked_reason, status, action, selector, action_value) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id,
                 tc.get("id", "TC-?"),
                 tc.get("title", tc.get("id", "")),
                 tc.get("category", "Functional"),
                 tc.get("expected_result", ""),
                 tc.get("priority", "Medium"),
                 "AI Orchestrator",
                 tc.get("title", ""),
                 tc.get("objective", ""),
                 tc.get("module", run.get("module_name", "")),
                 tc.get("preconditions", ""),
                 tc.get("input_data", ""),
                 json.dumps(tc.get("steps", [])),
                 tc.get("category", "Functional"),
                 json.dumps(tc.get("tags", [])),
                 1 if tc.get("automatable", True) else 0,
                 tc.get("blocked_reason", ""),
                 "Blocked" if tc.get("blocked_reason") else "Pending",
                 tc.get("action", "visible"),
                 tc.get("selector", "body"),
                 tc.get("action_value", ""))
            )
        _log(run_id, "GENERATION",
             f"Generated {len(test_cases)} test cases covering "
             f"{len(set(tc.get('category','') for tc in test_cases))} categories.")

        # Step 4 — Execute
        results = {"passed": 0, "failed": 0, "healed": 0, "blocked": 0, "skipped": 0, "executed": 0}
        if run.get("url"):
            execute_query("UPDATE autonomous_runs SET status='Execution' WHERE id=?", (run_id,))
            results = _execute_test_pipeline(run_id, run["url"], test_cases, cfg["execute_limit"])

        # Step 5 — Risk analysis
        execute_query("UPDATE autonomous_runs SET status='Analysis' WHERE id=?", (run_id,))
        healing_logs = execute_query(
            "SELECT * FROM autonomous_healing_logs WHERE run_id=?", (run_id,), fetch=True)
        risk = _analyze_risks(run_id, scope, test_cases, results, healing_logs)
        execute_query(
            "INSERT INTO autonomous_risk_analysis "
            "(run_id, module_risk_score, release_readiness, confidence_score, high_risk_areas, recommendations) "
            "VALUES (?,?,?,?,?,?)",
            (run_id, risk["risk_score"], risk["readiness"], risk["confidence"],
             json.dumps(risk["high_risk_areas"]), json.dumps(risk["recommendations"]))
        )

        # Step 6 — Final report
        execute_query("UPDATE autonomous_runs SET status='Reporting' WHERE id=?", (run_id,))
        report = _build_report(run_id, run, scope, test_cases, results, risk, healing_logs, page_data)
        execute_query(
            "INSERT INTO autonomous_reports (run_id, executive_summary, final_verdict, report_json) "
            "VALUES (?,?,?,?)",
            (run_id, report["executive_summary"], report["final_verdict"], json.dumps(report))
        )

        execute_query(
            "UPDATE autonomous_runs SET status='Completed', completed_at=CURRENT_TIMESTAMP WHERE id=?",
            (run_id,))
        _log(run_id, "COMPLETE",
             f"✅ Autonomous QA complete — Passed: {results['passed']}, "
             f"Failed: {results['failed']}, Healed: {results['healed']}, "
             f"Blocked: {results['blocked']}")

    except Exception as e:
        execute_query("UPDATE autonomous_runs SET status='Failed' WHERE id=?", (run_id,))
        _log(run_id, "ERROR",
             f"Orchestration error: {str(e)}", "FAIL")
        import traceback
        print(f"[Orchestrator Error]\n{traceback.format_exc()}")
