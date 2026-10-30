"""
ApplicationCrawler — Phase 1.5A Bounded Multi-Page Crawler

Strategy: BFS with hard limits on pages, depth, and total wall-clock time.
Uses a single Playwright browser context for the whole crawl.

Responsibilities:
  - Navigate start URL and each discovered internal page
  - Extract per-page structured data (forms, inputs, buttons, links, etc.)
  - Classify each page using deterministic heuristics
  - Build a navigation graph (nodes + edges)
  - Produce structured discovered_routes
  - Return a CrawlResult consumed by ApplicationUnderstandingAgent

NOT responsible for:
  - Test generation or prioritization
  - Authentication (will flag auth-required pages, not bypass them)
  - LLM analysis, RAG, or embedding
  - Screenshot/vision analysis (deferred to later phases)
"""

import time
import logging
import hashlib
import os
from collections import deque
from typing import Dict, Any, List, Optional, Set
from urllib.parse import urlparse

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from agentqe.crawler.crawl_config import CrawlConfig
from agentqe.crawler.crawl_result import CrawlResult, CrawledPage, PageLink
from agentqe.crawler.url_utils import (
    normalize_url, resolve_url, is_same_domain,
    is_navigable_url, extract_origin,
)
from agentqe.crawler.page_classifier import classify_page

logger = logging.getLogger(__name__)


# JavaScript snippet to extract per-page data.
# Mirrors the existing _crawl_page() extraction so downstream consumers
# receive the same field names.
_PAGE_EXTRACT_JS = """() => {
    const t = s => (s || '').trim().slice(0, 100);
    const tLong = s => (s || '').trim().slice(0, 600);

    return {
        title:      document.title,
        url:        location.href,
        h1:         t(document.querySelector('h1')?.innerText),
        h2s:        Array.from(document.querySelectorAll('h2,h3')).slice(0,10).map(e=>t(e.innerText)),
        nav_links:  Array.from(document.querySelectorAll(
                        'nav a, header a, .menu a, .nav a, [role="navigation"] a'
                    )).slice(0,40).map(a=>({
                        text: t(a.innerText),
                        href: (a.getAttribute('href')||'').slice(0,200)
                    })),
        all_links:  Array.from(document.querySelectorAll('a[href]')).slice(0,80).map(a=>({
                        text: t(a.innerText),
                        href: (a.href||'').slice(0,200)
                    })),
        forms:      Array.from(document.querySelectorAll('form')).slice(0,8).map(f=>({
                        id:     f.id||'',
                        name:   f.getAttribute('name')||'',
                        action: (f.getAttribute('action')||'').slice(0,150),
                        method: (f.getAttribute('method')||'get').toLowerCase(),
                        inputs: Array.from(f.querySelectorAll('input,textarea,select')).map(i=>({
                            type:        i.type||'text',
                            name:        i.name||'',
                            placeholder: (i.placeholder||'').slice(0,60),
                            required:    i.required
                        }))
                    })),
        buttons:    Array.from(document.querySelectorAll('button,[role="button"]'))
                        .slice(0,25).map(b=>t(b.innerText)).filter(Boolean),
        inputs:     Array.from(document.querySelectorAll('input,textarea')).slice(0,20).map(i=>({
                        type:        i.type,
                        name:        i.name,
                        placeholder: (i.placeholder||'').slice(0,60)
                    })),
        images:     document.querySelectorAll('img').length,
        has_login:  !!document.querySelector('input[type="password"]'),
        has_search: !!document.querySelector('input[type="search"],input[placeholder*="search" i]'),
        has_cart:   !!document.querySelector('[class*="cart" i],[id*="cart" i],[href*="cart"]'),
        has_product:!!document.querySelector('[class*="product" i],[class*="item" i]'),
        main_text:  tLong(
                        document.querySelector('main,.main,#main,article')?.innerText
                        || document.body?.innerText || ''
                    )
    };
}"""

# Phase 1.5B — DOM Structure Extraction
# Bounded, structured DOM representation for AI/ML processing
_DOM_EXTRACT_JS = """() => {
    const t = s => (s || '').trim().slice(0, 120);
    const tShort = s => (s || '').trim().slice(0, 80);
    const isVisible = el => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
    };
    const getBoundingBox = el => {
        try {
            const rect = el.getBoundingClientRect();
            return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
        } catch { return null; }
    };

    // Sensitive input types that should NEVER have their values recorded
    const SENSITIVE_TYPES = new Set(['password', 'hidden']);
    const SENSITIVE_NAMES = new Set(['password', 'pass', 'pwd', 'secret', 'token', 'csrf', 'xsrf', 'auth', 'api_key', 'apikey', 'access_token', 'refresh_token', 'session', 'cookie']);

    const isSensitive = (el) => {
        const type = (el.type || '').toLowerCase();
        const name = (el.name || '').toLowerCase();
        const id = (el.id || '').toLowerCase();
        const autocomplete = (el.autocomplete || '').toLowerCase();
        return SENSITIVE_TYPES.has(type) || SENSITIVE_NAMES.has(name) || SENSITIVE_NAMES.has(id) || autocomplete.includes('password') || autocomplete.includes('secret');
    };

    const extractElement = (el, idx, parentId) => {
        if (!el || el.nodeType !== Node.ELEMENT_NODE) return null;
        const tag = el.tagName.toLowerCase();
        const visible = isVisible(el);
        const bbox = visible ? getBoundingBox(el) : null;

        const base = {
            tag,
            id: el.id || '',
            name: el.name || '',
            role: el.getAttribute('role') || '',
            type: (el.type || '').toLowerCase(),
            aria_label: el.getAttribute('aria-label') || '',
            aria_labelledby: el.getAttribute('aria-labelledby') || '',
            aria_describedby: el.getAttribute('aria-describedby') || '',
            placeholder: (el.placeholder || '').slice(0, 80),
            text: '',
            href: (el.href || '').slice(0, 200),
            value_presence: false,
            required: el.required || false,
            disabled: el.disabled || false,
            visible,
            bounding_box: bbox,
            parent_ref: parentId || null,
        };

        // Tag-specific enhancements
        if (tag === 'a') {
            base.text = t(el.innerText);
            base.href = (el.href || '').slice(0, 200);
        } else if (tag === 'button' || el.getAttribute('role') === 'button') {
            base.text = t(el.innerText);
        } else if (tag === 'input' || tag === 'textarea' || tag === 'select') {
            base.text = t(el.value || '');
            // NEVER store actual values for sensitive fields
            if (isSensitive(el)) {
                base.value_presence = (el.value || '').length > 0;
                base.text = '';  // Clear text for sensitive
            } else {
                base.value_presence = (el.value || '').length > 0;
            }
        } else if (['h1','h2','h3','h4','h5','h6','p','span','label','div','section','article','header','footer','nav','main','aside'].includes(tag)) {
            base.text = tShort(el.innerText);
        } else if (tag === 'img') {
            base.text = (el.alt || '').slice(0, 80);
        } else {
            base.text = tShort(el.innerText);
        }

        return base;
    };

    // 1. Root element
    const root = extractElement(document.documentElement, 0, null);

    // 2. Interactive elements (bounded)
    const interactiveSelectors = [
        'button:not([disabled])',
        '[role="button"]:not([aria-disabled="true"])',
        'a[href]',
        'input:not([disabled]):not([type="hidden"])',
        'textarea:not([disabled])',
        'select:not([disabled])',
        '[role="checkbox"]',
        '[role="radio"]',
        '[role="menuitem"]',
        '[role="tab"]',
        '[role="link"]',
        '[onclick]',
        '[tabindex]:not([tabindex="-1"])'
    ];
    const interactiveElements = [];
    const seenInteractive = new Set();
    for (const selector of interactiveSelectors) {
        const els = document.querySelectorAll(selector);
        for (let i = 0; i < Math.min(els.length, 50); i++) {
            const el = els[i];
            const key = `${el.tagName}#${el.id || ''}.${el.className || ''}[${el.name || ''}]`;
            if (seenInteractive.has(key)) continue;
            seenInteractive.add(key);
            const extracted = extractElement(el, interactiveElements.length, null);
            if (extracted) interactiveElements.push(extracted);
        }
        if (interactiveElements.length >= 100) break;
    }

    // 3. Forms (bounded)
    const forms = [];
    const formEls = document.querySelectorAll('form');
    for (let i = 0; i < Math.min(formEls.length, 10); i++) {
        const f = formEls[i];
        const inputs = [];
        const inputEls = f.querySelectorAll('input,textarea,select');
        for (let j = 0; j < Math.min(inputEls.length, 20); j++) {
            const inp = inputEls[j];
            inputs.push({
                tag: inp.tagName.toLowerCase(),
                type: (inp.type || 'text').toLowerCase(),
                name: inp.name || '',
                id: inp.id || '',
                placeholder: (inp.placeholder || '').slice(0, 80),
                required: inp.required || false,
                disabled: inp.disabled || false,
                value_presence: !isSensitive(inp) && (inp.value || '').length > 0,
                aria_label: inp.getAttribute('aria-label') || '',
                aria_describedby: inp.getAttribute('aria-describedby') || '',
            });
        }
        forms.push({
            id: f.id || '',
            name: f.getAttribute('name') || '',
            action: (f.getAttribute('action') || '').slice(0, 200),
            method: (f.getAttribute('method') || 'get').toLowerCase(),
            inputs,
            validation_attrs: {
                novalidate: f.hasAttribute('novalidate'),
            }
        });
    }

    // 4. Landmarks (semantic HTML5 + ARIA)
    const landmarkRoles = ['banner', 'navigation', 'main', 'complementary', 'contentinfo', 'search', 'form', 'region'];
    const landmarkTags = ['header', 'nav', 'main', 'aside', 'footer', 'section', 'article', 'form'];
    const landmarks = [];
    const seenLandmarks = new Set();
    // ARIA landmarks
    for (const role of landmarkRoles) {
        const els = document.querySelectorAll(`[role="${role}"]`);
        for (let i = 0; i < Math.min(els.length, 5); i++) {
            const el = els[i];
            const key = `${role}#${el.id || ''}`;
            if (seenLandmarks.has(key)) continue;
            seenLandmarks.add(key);
            landmarks.push({
                type: 'aria',
                role,
                tag: el.tagName.toLowerCase(),
                id: el.id || '',
                label: (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || '').slice(0, 80),
            });
        }
    }
    // HTML5 landmarks
    for (const tag of landmarkTags) {
        const els = document.querySelectorAll(tag);
        for (let i = 0; i < Math.min(els.length, 5); i++) {
            const el = els[i];
            const key = `${tag}#${el.id || ''}`;
            if (seenLandmarks.has(key)) continue;
            seenLandmarks.add(key);
            const roleMap = {'header': 'banner', 'nav': 'navigation', 'main': 'main', 'aside': 'complementary', 'footer': 'contentinfo', 'form': 'form', 'section': 'region', 'article': 'region'};
            landmarks.push({
                type: 'html5',
                role: roleMap[tag] || 'region',
                tag,
                id: el.id || '',
                label: (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || '').slice(0, 80),
            });
        }
    }

    // 5. Text summary (bounded)
    const textParts = [];
    // Page title
    if (document.title) textParts.push({type: 'title', text: t(document.title)});
    // H1
    const h1 = document.querySelector('h1');
    if (h1) textParts.push({type: 'h1', text: t(h1.innerText)});
    // Major headings
    const headings = document.querySelectorAll('h2,h3');
    for (let i = 0; i < Math.min(headings.length, 8); i++) {
        textParts.push({type: headings[i].tagName.toLowerCase(), text: t(headings[i].innerText)});
    }
    // Visible button labels
    const btns = document.querySelectorAll('button,[role="button"]');
    for (let i = 0; i < Math.min(btns.length, 15); i++) {
        const txt = t(btns[i].innerText);
        if (txt) textParts.push({type: 'button', text: txt});
    }
    // Visible link labels
    const links = document.querySelectorAll('a[href]');
    for (let i = 0; i < Math.min(links.length, 20); i++) {
        const txt = t(links[i].innerText);
        if (txt) textParts.push({type: 'link', text: txt});
    }
    // Form labels
    const labels = document.querySelectorAll('label');
    for (let i = 0; i < Math.min(labels.length, 10); i++) {
        const txt = t(labels[i].innerText);
        if (txt) textParts.push({type: 'label', text: txt});
    }

    // 6. Input summary for correlation
    const inputSummary = [];
    const allInputs = document.querySelectorAll('input,textarea,select');
    for (let i = 0; i < Math.min(allInputs.length, 30); i++) {
        const inp = allInputs[i];
        inputSummary.push({
            id: inp.id || '',
            name: inp.name || '',
            type: (inp.type || 'text').toLowerCase(),
            aria_label: inp.getAttribute('aria-label') || '',
            aria_labelledby: inp.getAttribute('aria-labelledby') || '',
            aria_describedby: inp.getAttribute('aria-describedby') || '',
            label_text: '',
        });
    }
    // Try to associate labels with inputs
    for (const inp of allInputs) {
        let labelText = '';
        if (inp.id) {
            const label = document.querySelector(`label[for="${inp.id}"]`);
            if (label) labelText = t(label.innerText);
        }
        if (!labelText) {
            const parentLabel = inp.closest('label');
            if (parentLabel) labelText = t(parentLabel.innerText);
        }
        if (!labelText && inp.getAttribute('aria-label')) {
            labelText = inp.getAttribute('aria-label');
        }
        if (!labelText && inp.getAttribute('aria-labelledby')) {
            const labelledId = inp.getAttribute('aria-labelledby');
            const labelledEl = document.getElementById(labelledId);
            if (labelledEl) labelText = t(labelledEl.innerText);
        }
        for (const sum of inputSummary) {
            if (sum.id === inp.id || sum.name === inp.name) {
                sum.label_text = labelText;
                break;
            }
        }
    }

    return {
        root,
        elements: interactiveElements,  // Reuse interactive as primary element list
        forms,
        interactive_elements: interactiveElements,
        landmarks,
        text_summary: textParts.slice(0, 80),
        input_summary: inputSummary,
    };
}"""

# Default limits for bounded extraction
MAX_INTERACTIVE_ELEMENTS = 100
MAX_FORMS = 10
MAX_FORM_INPUTS = 20
MAX_LANDMARKS = 20
MAX_TEXT_SUMMARY = 80
MAX_ACCESSIBILITY_NODES = 200

# Phase 1.5C — Network observation bounds
MAX_NETWORK_RECORDS_PER_PAGE = 100
MAX_URL_LENGTH = 500
MAX_HEADER_COUNT = 20
MAX_HEADER_VALUE_LENGTH = 200
MAX_NETWORK_METADATA_SIZE = 50000  # bytes

# Sensitive header names to redact
SENSITIVE_HEADERS = {
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "api-key", "token", "access-token", "refresh-token",
    "csrf", "xsrf", "session", "secret", "x-csrf-token", "x-xsrf-token",
    "x-auth-token", "x-access-token", "x-refresh-token", "proxy-authenticate",
    "www-authenticate", "x-forwarded-for", "x-real-ip"
}

# Static resource extensions to exclude from API candidates
STATIC_EXTENSIONS = {
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".ico", ".woff", ".woff2", ".ttf", ".eot", ".map",
    ".mp4", ".webm", ".ogg", ".mp3", ".wav", ".flac",
    ".avi", ".mov", ".mkv", ".pdf", ".zip", ".gz", ".tar"
}

# Resource types that are API candidates
API_CANDIDATE_RESOURCE_TYPES = {"fetch", "xhr"}

# Phase 1.5D — Screenshot bounds
# Maximum full-page screenshot dimensions
MAX_SCREENSHOT_WIDTH = 3840
MAX_SCREENSHOT_HEIGHT = 2160
# Maximum screenshot file size (5MB)
MAX_SCREENSHOT_BYTES = 5_000_000
# Screenshot storage directory
SCREENSHOT_STORAGE_DIR = "backend/data/agentqe/screenshots"


class ApplicationCrawler:
    """
    Bounded BFS multi-page application crawler.

    Usage:
        config = CrawlConfig(max_pages=10, max_depth=2)
        result = ApplicationCrawler().crawl("https://example.com", config)
    """

    def crawl(
        self,
        start_url: str,
        config: Optional[CrawlConfig] = None,
    ) -> CrawlResult:
        """
        Crawl the application starting from start_url.

        Args:
            start_url: The entry point URL.
            config:    CrawlConfig (uses defaults if None).

        Returns:
            CrawlResult with all pages, navigation graph, and metadata.
        """
        if config is None:
            config = CrawlConfig()

        result = CrawlResult(start_url=start_url)
        crawl_start = time.time()

        if not PLAYWRIGHT_AVAILABLE:
            result.warnings.append(
                "Playwright not available — falling back to single-page crawl via requests"
            )
            result.crawl_metadata = self._empty_metadata(start_url, config, 0)
            return result

        normalised_start = normalize_url(start_url, config.ignored_query_params)
        if not normalised_start.startswith("http"):
            result.warnings.append(f"Invalid start URL: {start_url}")
            result.crawl_metadata = self._empty_metadata(start_url, config, 0)
            return result

        visited: Set[str] = set()      # normalised URLs already crawled
        queued: Set[str] = set()       # normalised URLs in the queue
        # BFS queue: (normalised_url, original_url, depth)
        queue: deque = deque([(normalised_start, start_url, 0)])
        queued.add(normalised_start)

        nav_nodes: List[str] = []
        nav_edges: List[Dict[str, Any]] = []

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                browser_ctx = browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="AutoQA-ApplicationCrawler/1.5a",
                )
                page = browser_ctx.new_page()

                try:
                    while queue:
                        # Check global timeout
                        elapsed = time.time() - crawl_start
                        if elapsed >= config.overall_timeout_seconds:
                            result.warnings.append(
                                f"Overall timeout reached after {elapsed:.1f}s. "
                                f"Crawled {len(visited)}/{config.max_pages} pages."
                            )
                            break

                        # Check page budget
                        if len(visited) >= config.max_pages:
                            result.warnings.append(
                                f"max_pages={config.max_pages} reached."
                            )
                            break

                        norm_url, orig_url, depth = queue.popleft()

                        if norm_url in visited:
                            continue
                        visited.add(norm_url)

                        if depth > config.max_depth:
                            continue

                        # -- Crawl this page --
                        crawled = self._crawl_single_page(
                            page=page,
                            url=orig_url,
                            norm_url=norm_url,
                            depth=depth,
                            config=config,
                        )
                        result.pages.append(crawled)

                        # Navigation graph node
                        if norm_url not in nav_nodes:
                            nav_nodes.append(norm_url)

                        # -- Discover links for next BFS level --
                        if crawled.crawl_status == "success" and depth < config.max_depth:
                            for link in crawled.links:
                                target_norm = normalize_url(
                                    link.target, config.ignored_query_params
                                )
                                if not target_norm:
                                    continue
                                if not is_navigable_url(target_norm):
                                    continue
                                if config.same_domain_only and not is_same_domain(
                                    target_norm, start_url
                                ):
                                    continue
                                if target_norm in visited or target_norm in queued:
                                    continue
                                if len(queued) + len(visited) >= config.max_pages * 2:
                                    break
                                queued.add(target_norm)
                                queue.append((target_norm, link.target, depth + 1))

                                # Navigation graph edge
                                nav_edges.append({
                                    "from": norm_url,
                                    "to": target_norm,
                                    "label": link.text[:60] if link.text else "",
                                })

                finally:
                    browser.close()

        except Exception as e:
            logger.error(f"[ApplicationCrawler] Fatal error: {e}")
            result.warnings.append(f"Crawler encountered an error: {str(e)[:200]}")

        # Build navigation graph
        result.navigation_graph = {
            "nodes": nav_nodes,
            "edges": nav_edges,
        }

        # Build discovered_routes (rich format)
        result.discovered_routes = self._build_discovered_routes(result.pages)

        # Phase 1.5C — Aggregate observed API endpoints from network activity
        result.api_endpoints = self._aggregate_api_endpoints(result.pages)

        # Crawl metadata
        duration = time.time() - crawl_start
        failed = [p for p in result.pages if p.crawl_status != "success"]
        
        # Network metadata
        total_requests = sum(len(p.network_activity) for p in result.pages)
        total_responses = sum(1 for p in result.pages for a in p.network_activity if a.get("response"))
        total_failures = sum(1 for p in result.pages for a in p.network_activity if a.get("request_failed"))
        api_candidates = sum(1 for p in result.pages for a in p.network_activity if a.get("is_api_candidate"))

        result.crawl_metadata = {
            "start_url": start_url,
            "pages_discovered": len(queued),
            "pages_analyzed": len(result.pages) - len(failed),
            "pages_failed": len(failed),
            "max_pages": config.max_pages,
            "max_depth": config.max_depth,
            "same_domain_only": config.same_domain_only,
            "duration_seconds": round(duration, 2),
            "warnings": result.warnings,
            # Phase 1.5C — Network metadata
            "network_requests": total_requests,
            "network_responses": total_responses,
            "network_failures": total_failures,
            "api_candidates": api_candidates,
        }

        return result

    def _crawl_single_page(
        self,
        page,
        url: str,
        norm_url: str,
        depth: int,
        config: CrawlConfig,
    ) -> CrawledPage:
        """Navigate to a single URL and extract structured data."""
        page_start = time.time()
        crawled = CrawledPage(url=url, depth=depth)

        try:
            response = page.goto(
                url,
                timeout=config.page_timeout_ms,
                wait_until="domcontentloaded",
            )
            status = response.status if response else 200

            # Check for auth redirect / HTTP errors
            final_url = page.url
            if status == 401 or status == 403:
                crawled.crawl_status = "authentication_required"
                crawled.status = status
                crawled.duration_ms = (time.time() - page_start) * 1000
                return crawled

            if status >= 400:
                crawled.crawl_status = "failed"
                crawled.status = status
                crawled.error = f"HTTP {status}"
                crawled.duration_ms = (time.time() - page_start) * 1000
                return crawled

            crawled.status = status

            # SPA hydration wait
            time.sleep(config.post_load_wait_ms / 1000.0)

            # Extract page data via JS
            try:
                raw = page.evaluate(_PAGE_EXTRACT_JS)
            except Exception as js_err:
                raw = {}
                crawled.warnings = [f"JS extraction error: {str(js_err)[:100]}"]

            # Map raw data onto CrawledPage
            crawled.title = raw.get("title", "")
            crawled.forms = raw.get("forms", [])
            crawled.inputs = raw.get("inputs", [])
            crawled.buttons = raw.get("buttons", [])
            crawled.nav_links = raw.get("nav_links", [])
            crawled.has_login = raw.get("has_login", False)
            crawled.has_search = raw.get("has_search", False)
            crawled.has_cart = raw.get("has_cart", False)
            crawled.has_product = raw.get("has_product", False)
            crawled.main_text = raw.get("main_text", "")
            crawled.content_summary = crawled.main_text[:200]

            # Check if we ended up on a login page (auth redirect)
            if (
                crawled.has_login
                and ("login" in final_url.lower() or "signin" in final_url.lower())
                and final_url != url
            ):
                crawled.crawl_status = "authentication_required"
            else:
                crawled.crawl_status = "success"

            # Detect flows (same logic as existing _crawl_page)
            flows = []
            if crawled.has_login:
                flows.append("Authentication/Login")
            if crawled.has_search:
                flows.append("Search Functionality")
            if crawled.has_cart:
                flows.append("Shopping Cart")
            if crawled.has_product:
                flows.append("Product Browsing")
            if crawled.forms:
                flows.append("Form Submission")
            if crawled.nav_links:
                flows.append("Navigation")
            crawled.detected_flows = flows

            # Classify page
            page_type, confidence = classify_page(
                url=final_url,
                title=crawled.title,
                has_login=crawled.has_login,
                has_search=crawled.has_search,
                has_cart=crawled.has_cart,
                forms=crawled.forms,
            )
            crawled.page_type = page_type
            crawled.page_type_confidence = confidence

            # Discover links for BFS
            all_link_data = raw.get("all_links", []) + raw.get("nav_links", [])
            seen_hrefs: Set[str] = set()
            for link_raw in all_link_data:
                href = link_raw.get("href", "")
                if not href:
                    continue
                resolved = resolve_url(final_url, href)
                if not resolved or resolved in seen_hrefs:
                    continue
                seen_hrefs.add(resolved)
                crawled.links.append(PageLink(
                    source=final_url,
                    target=resolved,
                    text=link_raw.get("text", ""),
                    link_type="navigation",
                ))

        except Exception as e:
            err_str = str(e)
            if "Timeout" in err_str or "timeout" in err_str:
                crawled.crawl_status = "timeout"
            else:
                crawled.crawl_status = "failed"
            crawled.error = err_str[:300]
            logger.warning(f"[ApplicationCrawler] Failed to crawl {url}: {err_str[:150]}")

        crawled.duration_ms = round((time.time() - page_start) * 1000, 1)
        return crawled

    def _build_discovered_routes(self, pages: List[CrawledPage]) -> List[Dict[str, Any]]:
        """Build the rich discovered_routes structure from crawled pages."""
        routes = []
        seen_paths = set()

        for page in pages:
            try:
                path = urlparse(page.url).path or "/"
            except Exception:
                path = page.url

            if path in seen_paths:
                continue
            seen_paths.add(path)

            routes.append({
                "path": path,
                "url": page.url,
                "source_page": None,  # BFS parent not tracked per-page currently
                "depth": page.depth,
                "page_type": page.page_type,
                "page_type_confidence": page.page_type_confidence,
                "title": page.title or None,
                "status": page.status,
                "crawl_status": page.crawl_status,
                "evidence_type": "observed",
                "source": "application_crawl",
            })

        return routes

    @staticmethod
    def _empty_metadata(start_url: str, config: CrawlConfig, duration: float) -> Dict[str, Any]:
        return {
            "start_url": start_url,
            "pages_discovered": 0,
            "pages_analyzed": 0,
            "pages_failed": 0,
            "max_pages": config.max_pages,
            "max_depth": config.max_depth,
            "same_domain_only": config.same_domain_only,
            "duration_seconds": round(duration, 2),
            "warnings": [],
        }

    # ============================================================
    # Phase 1.5B — DOM + Accessibility Tree Extraction
    # ============================================================

    def _extract_dom(self, page) -> Dict[str, Any]:
        """Extract structured DOM representation from the page."""
        try:
            dom_data = page.evaluate(_DOM_EXTRACT_JS)
            # Ensure all expected keys exist with safe defaults
            return {
                "root": dom_data.get("root", {}),
                "elements": dom_data.get("elements", []),
                "forms": dom_data.get("forms", []),
                "interactive_elements": dom_data.get("interactive_elements", []),
                "landmarks": dom_data.get("landmarks", []),
                "text_summary": dom_data.get("text_summary", []),
                "input_summary": dom_data.get("input_summary", []),
            }
        except Exception as e:
            logger.warning(f"[ApplicationCrawler] DOM extraction failed: {e}")
            return {
                "root": {},
                "elements": [],
                "forms": [],
                "interactive_elements": [],
                "landmarks": [],
                "text_summary": [],
                "input_summary": [],
            }

    def _extract_accessibility_tree_cdp(self, page) -> Optional[Dict[str, Any]]:
        """
        Extract accessibility tree using Playwright CDP session.
        Returns None if CDP accessibility is not available.
        """
        try:
            # Create CDP session for the page
            cdp = page.context.new_cdp_session(page)
            # Enable Accessibility domain
            cdp.send("Accessibility.enable")
            # Get full accessibility tree
            result = cdp.send("Accessibility.getFullAXTree")
            cdp.send("Accessibility.disable")
            cdp.detach()

            nodes = result.get("nodes", [])
            if not nodes:
                return None

            # Build hierarchical tree from flat node list
            node_map = {n["nodeId"]: n for n in nodes}

            for node in nodes:
                node_id = node.get("nodeId")
                parent_id = None
                # Find parent by checking which node has this node as child
                for potential_parent in nodes:
                    if node_id in potential_parent.get("childIds", []):
                        parent_id = potential_parent.get("nodeId")
                        break

                # Build simplified node
                simplified = self._simplify_ax_node(node)
                simplified["_node_id"] = node_id
                simplified["_parent_id"] = parent_id
                node_map[node_id] = simplified

            # Build hierarchy
            root_nodes = []
            for node in nodes:
                node_id = node.get("nodeId")
                simplified = node_map[node_id]
                children = []
                for child_id in node.get("childIds", []):
                    if child_id in node_map:
                        children.append(node_map[child_id])
                simplified["children"] = children
                # Root nodes have no parent in our traversal
                if simplified["_parent_id"] is None:
                    root_nodes.append(simplified)

            # Return the first root (typically RootWebArea)
            root = root_nodes[0] if root_nodes else {}
            # Clean up internal fields
            self._clean_ax_node(root)

            return {
                "source": "playwright",
                "root": root,
                "node_count": len(nodes),
            }

        except Exception as e:
            logger.warning(f"[ApplicationCrawler] CDP accessibility extraction failed: {e}")
            return None

    def _simplify_ax_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """Simplify a CDP accessibility node to essential fields."""
        role = node.get("role", {}).get("value", "")
        name = node.get("name", {}).get("value", "")
        props = node.get("properties", [])

        # Extract properties into a dict
        prop_dict = {}
        for p in props:
            p_name = p.get("name")
            p_value = p.get("value", {}).get("value")
            if p_name and p_value is not None:
                prop_dict[p_name] = p_value

        # Check for sensitive roles/properties
        is_password = role == "textbox" and prop_dict.get("password", False)

        simplified = {
            "role": role,
            "name": name if not is_password else "",  # Never expose password field names with values
            "description": prop_dict.get("description", ""),
            "value": "" if is_password else prop_dict.get("value", ""),
            "checked": prop_dict.get("checked"),
            "selected": prop_dict.get("selected"),
            "expanded": prop_dict.get("expanded"),
            "disabled": prop_dict.get("disabled", False),
            "required": prop_dict.get("required", False),
            "hidden": prop_dict.get("hidden", False),
            "level": prop_dict.get("level"),
            "focusable": prop_dict.get("focusable", False),
            "editable": prop_dict.get("editable"),
            "multiline": prop_dict.get("multiline"),
            "password": is_password,
            "children": [],
        }

        # Remove None values
        return {k: v for k, v in simplified.items() if v is not None and v != "" and v != []}

    def _clean_ax_node(self, node: Dict[str, Any]):
        """Recursively remove internal fields from accessibility node."""
        if not isinstance(node, dict):
            return
        node.pop("_node_id", None)
        node.pop("_parent_id", None)
        children = node.get("children", [])
        for child in children:
            self._clean_ax_node(child)

    def _extract_accessibility_tree_dom_fallback(self, dom_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build accessibility tree from DOM accessibility attributes.
        Used when CDP accessibility API is unavailable.
        """
        def build_node(el: Dict[str, Any]) -> Dict[str, Any]:
            if not el:
                return {}
            role = el.get("role") or self._infer_role_from_tag(el.get("tag", ""), el.get("type", ""))
            name = el.get("aria_label") or el.get("text") or el.get("placeholder") or ""
            children = []
            # We don't have full hierarchy from DOM extraction, so we create a flat list
            # of accessible elements
            return {
                "role": role,
                "name": name[:120] if name else "",
                "description": el.get("aria_describedby", "")[:120] if el.get("aria_describedby") else "",
                "value": "" if el.get("type") == "password" else "",
                "checked": None,
                "selected": None,
                "expanded": None,
                "disabled": el.get("disabled", False),
                "required": el.get("required", False),
                "hidden": not el.get("visible", True),
                "level": None,
                "focusable": role in ("button", "link", "textbox", "checkbox", "radio", "menuitem", "tab", "slider"),
                "editable": el.get("tag") in ("input", "textarea") and el.get("type") not in ("checkbox", "radio", "button", "submit", "hidden"),
                "multiline": el.get("tag") == "textarea",
                "password": el.get("type") == "password",
                "children": children,
            }

        # Build from interactive elements and forms
        accessible_nodes = []
        for el in dom_data.get("interactive_elements", []):
            node = build_node(el)
            if node.get("role"):
                accessible_nodes.append(node)

        # Add form inputs
        for form in dom_data.get("forms", []):
            for inp in form.get("inputs", []):
                node = build_node({
                    "tag": inp.get("tag", "input"),
                    "type": inp.get("type", "text"),
                    "role": inp.get("tag", "input"),
                    "aria_label": inp.get("aria_label", ""),
                    "aria_describedby": inp.get("aria_describedby", ""),
                    "text": inp.get("name", ""),
                    "placeholder": inp.get("placeholder", ""),
                    "disabled": inp.get("disabled", False),
                    "required": inp.get("required", False),
                    "visible": True,
                })
                if node.get("role"):
                    accessible_nodes.append(node)

        # Create a synthetic root
        root = {
            "role": "WebArea",
            "name": dom_data.get("root", {}).get("text", "")[:100] or "Page",
            "children": accessible_nodes[:MAX_ACCESSIBILITY_NODES],
        }

        return {
            "source": "dom_fallback",
            "root": root,
            "node_count": len(accessible_nodes),
        }

    def _infer_role_from_tag(self, tag: str, type_: str) -> str:
        """Infer ARIA role from HTML tag and type."""
        tag = tag.lower()
        type_ = type_.lower()
        if tag == "button" or (tag == "input" and type_ in ("button", "submit", "reset")):
            return "button"
        if tag == "a" or tag == "link":
            return "link"
        if tag == "input":
            if type_ in ("checkbox",):
                return "checkbox"
            if type_ in ("radio",):
                return "radio"
            if type_ in ("text", "email", "password", "search", "tel", "url", "number"):
                return "textbox"
            if type_ in ("file",):
                return "textbox"
        if tag == "textarea":
            return "textbox"
        if tag == "select":
            return "combobox"
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            return "heading"
        if tag == "img":
            return "img"
        if tag in ("nav",):
            return "navigation"
        if tag in ("header",):
            return "banner"
        if tag in ("main",):
            return "main"
        if tag in ("footer",):
            return "contentinfo"
        if tag in ("aside",):
            return "complementary"
        if tag in ("form",):
            return "form"
        if tag in ("section", "article"):
            return "region"
        if tag in ("label",):
            return "label"
        return "generic"

    def _derive_ui_insights(self, dom_data: Dict[str, Any], accessibility_data: Dict[str, Any]) -> Dict[str, Any]:
        """Derive deterministic UI insights from DOM and accessibility data."""
        interactive = dom_data.get("interactive_elements", [])
        forms = dom_data.get("forms", [])
        landmarks = dom_data.get("landmarks", [])
        ax_nodes = accessibility_data.get("root", {}).get("children", []) if accessibility_data else []

        # Count elements by type
        button_count = sum(1 for el in interactive if el.get("tag") == "button" or el.get("role") == "button")
        link_count = sum(1 for el in interactive if el.get("tag") == "a")
        input_count = sum(1 for el in interactive if el.get("tag") in ("input", "textarea", "select"))
        form_count = len(forms)
        nav_count = sum(1 for lm in landmarks if lm.get("role") == "navigation")
        landmark_count = len(landmarks)

        # Detect login controls
        has_email = any(el.get("type") == "email" for el in interactive)
        has_password = any(el.get("type") == "password" for el in interactive)
        has_submit = any(el.get("type") in ("submit", "button") or el.get("role") == "button" for el in interactive)
        has_login_controls = has_email and has_password and has_submit

        # Detect search controls
        has_search_input = any(el.get("type") == "search" for el in interactive)
        has_search_placeholder = any("search" in (el.get("placeholder") or "").lower() for el in interactive)
        has_search_controls = has_search_input or has_search_placeholder

        # Detect submission controls
        has_submission_controls = any(el.get("type") == "submit" for el in interactive) or any(
            "submit" in (el.get("text") or "").lower() for el in interactive
        )

        return {
            "interactive_element_count": len(interactive),
            "form_count": form_count,
            "input_count": input_count,
            "button_count": button_count,
            "link_count": link_count,
            "navigation_count": nav_count,
            "landmark_count": landmark_count,
            "accessibility_node_count": len(ax_nodes),
            "has_login_controls": has_login_controls,
            "has_search_controls": has_search_controls,
            "has_submission_controls": has_submission_controls,
        }

    # ============================================================
    # Phase 1.5C — Network/API Understanding
    # ============================================================

    def _sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Sanitize headers by redacting sensitive values."""
        if not headers:
            return {}
        sanitized = {}
        for key, value in headers.items():
            lower_key = key.lower()
            if lower_key in SENSITIVE_HEADERS:
                sanitized[key] = "[REDACTED]"
            else:
                # Truncate long values
                sanitized[key] = value[:MAX_HEADER_VALUE_LENGTH] if len(value) > MAX_HEADER_VALUE_LENGTH else value
        return sanitized

    def _is_static_resource(self, url: str) -> bool:
        """Check if URL appears to be a static resource."""
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()
            for ext in STATIC_EXTENSIONS:
                if path.endswith(ext):
                    return True
        except Exception:
            pass
        return False

    def _classify_network_request(self, request, response=None) -> Dict[str, Any]:
        """Classify a network request and determine if it's an API candidate."""
        resource_type = request.resource_type
        url = request.url
        method = request.method
        
        # Determine network category
        if resource_type in API_CANDIDATE_RESOURCE_TYPES:
            network_category = "api_candidate"
        elif resource_type == "document":
            network_category = "document"
        elif resource_type in {"stylesheet", "script", "image", "font", "media"}:
            network_category = resource_type
        elif resource_type == "websocket":
            network_category = "websocket"
        else:
            network_category = "other"
        
        # Additional heuristics for API candidate
        is_api_candidate = resource_type in API_CANDIDATE_RESOURCE_TYPES
        
        # Check content type if response available
        content_type = ""
        if response:
            try:
                content_type = response.headers.get("content-type", "") or ""
            except Exception:
                pass
            if "application/json" in content_type.lower():
                is_api_candidate = True
                network_category = "api_candidate"
        
        # Check URL path patterns
        if not is_api_candidate:
            try:
                parsed = urlparse(url)
                path = parsed.path.lower()
                if "/api/" in path or "/graphql" in path or "/rest/" in path or "/v1/" in path or "/v2/" in path:
                    # But only if not a static resource
                    if not self._is_static_resource(url):
                        is_api_candidate = True
                        network_category = "api_candidate"
            except Exception:
                pass
        
        return {
            "network_category": network_category,
            "is_api_candidate": is_api_candidate,
            "content_type": content_type,
        }

    def _extract_network_activity(self, page) -> List[Dict[str, Any]]:
        """Extract network activity from page event listeners."""
        network_records = []
        request_map = {}  # request_id -> request data
        
        def on_request(request):
            """Handle request event."""
            if len(network_records) >= MAX_NETWORK_RECORDS_PER_PAGE:
                return
            try:
                request_id = id(request)  # Use object id as unique identifier
                request_data = {
                    "request_id": f"req_{request_id}",
                    "method": request.method,
                    "url": request.url[:MAX_URL_LENGTH],
                    "resource_type": request.resource_type,
                    "timestamp": time.time(),
                    "headers": self._sanitize_headers(request.headers) if hasattr(request, 'headers') else {},
                    "has_post_data": bool(request.post_data) if hasattr(request, 'post_data') else False,
                    "post_data_size": len(request.post_data) if request.post_data else 0,
                }
                request_map[request_id] = request_data
            except Exception as e:
                logger.debug(f"Network request capture error: {e}")
        
        def on_response(response):
            """Handle response event."""
            try:
                request = response.request
                request_id = id(request)
                
                if request_id in request_map:
                    req_data = request_map[request_id]
                else:
                    # Create minimal request data if not captured
                    req_data = {
                        "request_id": f"req_{request_id}",
                        "method": request.method,
                        "url": request.url[:MAX_URL_LENGTH],
                        "resource_type": request.resource_type,
                        "timestamp": time.time(),
                        "headers": self._sanitize_headers(request.headers) if hasattr(request, 'headers') else {},
                        "has_post_data": bool(request.post_data) if hasattr(request, 'post_data') else False,
                        "post_data_size": len(request.post_data) if request.post_data else 0,
                    }
                
                classification = self._classify_network_request(request, response)
                
                network_record = {
                    **req_data,
                    "response": {
                        "status": response.status,
                        "status_text": response.status_text if hasattr(response, 'status_text') else "",
                        "content_type": classification.get("content_type", ""),
                        "headers": self._sanitize_headers(response.headers) if hasattr(response, 'headers') else {},
                        "timing_ms": None,  # Would require more complex timing capture
                    },
                    "is_api_candidate": classification["is_api_candidate"],
                    "network_category": classification["network_category"],
                }
                
                # Limit total size
                if len(str(network_records)) + len(str(network_record)) < MAX_NETWORK_METADATA_SIZE:
                    network_records.append(network_record)
                
                # Clean up request map
                request_map.pop(request_id, None)
                
            except Exception as e:
                logger.debug(f"Network response capture error: {e}")
        
        def on_request_failed(request):
            """Handle request failure event."""
            try:
                request_id = id(request)
                if request_id in request_map:
                    req_data = request_map[request_id]
                else:
                    req_data = {
                        "request_id": f"req_{request_id}",
                        "method": request.method,
                        "url": request.url[:MAX_URL_LENGTH],
                        "resource_type": request.resource_type,
                        "timestamp": time.time(),
                        "headers": self._sanitize_headers(request.headers) if hasattr(request, 'headers') else {},
                        "has_post_data": bool(request.post_data) if hasattr(request, 'post_data') else False,
                        "post_data_size": len(request.post_data) if request.post_data else 0,
                    }
                
                classification = self._classify_network_request(request)
                
                network_record = {
                    **req_data,
                    "request_failed": True,
                    "failure_text": request.failure_text if hasattr(request, 'failure_text') else "Unknown error",
                    "is_api_candidate": classification["is_api_candidate"],
                    "network_category": classification["network_category"],
                }
                
                if len(str(network_records)) + len(str(network_record)) < MAX_NETWORK_METADATA_SIZE:
                    network_records.append(network_record)
                
                request_map.pop(request_id, None)
                
            except Exception as e:
                logger.debug(f"Network request failed capture error: {e}")
        
        # Attach listeners
        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfailed", on_request_failed)
        
        # Store the listener functions for cleanup
        return network_records, on_request, on_response, on_request_failed

    def _finalize_network_activity(self, page, network_data):
        """Clean up network event listeners and return collected records."""
        network_records, on_request, on_response, on_request_failed = network_data
        try:
            page.remove_listener("request", on_request)
            page.remove_listener("response", on_response)
            page.remove_listener("requestfailed", on_request_failed)
        except Exception:
            pass
        return network_records

    def _aggregate_api_endpoints(self, pages: List[CrawledPage]) -> List[Dict[str, Any]]:
        """Aggregate observed API endpoints from all pages."""
        endpoint_map = {}  # (method, normalized_path) -> endpoint data
        
        for page in pages:
            if page.crawl_status != "success":
                continue
            for activity in page.network_activity:
                if not activity.get("is_api_candidate"):
                    continue
                
                method = activity.get("method", "GET")
                url = activity.get("url", "")
                
                try:
                    parsed = urlparse(url)
                    path = parsed.path
                except Exception:
                    path = url
                
                key = (method.upper(), path)
                
                if key not in endpoint_map:
                    endpoint_map[key] = {
                        "method": method.upper(),
                        "url": url,
                        "path": path,
                        "resource_type": activity.get("resource_type", ""),
                        "status": activity.get("response", {}).get("status") if activity.get("response") else None,
                        "content_type": activity.get("response", {}).get("content_type", "") if activity.get("response") else "",
                        "is_api_candidate": True,
                        "observed_on_pages": [],
                        "observation_count": 0,
                    }
                
                endpoint = endpoint_map[key]
                endpoint["observation_count"] += 1
                page_path = urlparse(page.url).path or "/"
                if page_path not in endpoint["observed_on_pages"]:
                    endpoint["observed_on_pages"].append(page_path)
        
        return list(endpoint_map.values())

    # ============================================================
    # Phase 1.5D — Screenshot Capture & Visual Evidence
    # ============================================================

    def _ensure_screenshot_dir(self) -> str:
        """Ensure screenshot storage directory exists and return its path."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        screenshot_dir = os.path.join(base_dir, SCREENSHOT_STORAGE_DIR)
        os.makedirs(screenshot_dir, exist_ok=True)
        return screenshot_dir

    def _sanitize_filename(self, url: str) -> str:
        """Create a safe filename from URL."""
        # Create a hash of the URL for the filename
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        return f"agentqe_{url_hash}.png"

    def _capture_screenshot(self, page, config: CrawlConfig) -> Dict[str, Any]:
        """
        Capture a screenshot of the current page.
        Returns a dict with screenshot metadata (no binary data).
        """
        if not config.screenshots_enabled:
            return {"status": "disabled"}

        screenshot_start = time.time()
        screenshot_dir = self._ensure_screenshot_dir()
        filename = self._sanitize_filename(page.url)
        filepath = os.path.join(screenshot_dir, filename)

        try:
            # Determine screenshot options based on config
            screenshot_options = {
                "path": filepath,
                "type": "png",
                "timeout": config.screenshot_timeout_ms,
            }

            if config.screenshot_type == "full_page":
                screenshot_options["full_page"] = True
            else:
                screenshot_options["full_page"] = False

            # Capture screenshot
            page.screenshot(**screenshot_options)

            # Get file stats
            file_size = os.path.getsize(filepath)

            # Check size bounds
            if file_size > config.max_screenshot_bytes:
                os.remove(filepath)
                return {
                    "status": "failed",
                    "error": f"Screenshot size {file_size} bytes exceeds limit {config.max_screenshot_bytes} bytes",
                    "capture_type": config.screenshot_type,
                }

            # Get image dimensions (approximate for viewport)
            if config.screenshot_type == "viewport":
                width, height = 1280, 720  # Default viewport
            else:
                # For full page, we'd need to get actual dimensions
                # This is a best-effort approximation
                width, height = min(config.max_screenshot_width, 1920), min(config.max_screenshot_height, 1080)

            # Calculate SHA256 for deduplication/verification
            with open(filepath, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            capture_duration_ms = round((time.time() - screenshot_start) * 1000, 1)

            return {
                "status": "success",
                "storage": "filesystem",
                "path": filepath,
                "format": "png",
                "capture_type": config.screenshot_type,
                "width": width,
                "height": height,
                "size_bytes": file_size,
                "sha256": file_hash,
                "capture_duration_ms": capture_duration_ms,
                "viewport": {"width": 1280, "height": 720},
                "page_url": page.url,
                "timestamp": time.time(),
            }

        except Exception as e:
            # Clean up partial file if it exists
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception:
                    pass
            logger.warning(f"[ApplicationCrawler] Screenshot capture failed for {page.url}: {e}")
            return {
                "status": "failed",
                "error": str(e)[:200],
                "capture_type": config.screenshot_type,
            }

    def _crawl_single_page(
        self,
        page,
        url: str,
        norm_url: str,
        depth: int,
        config: CrawlConfig,
    ) -> CrawledPage:
        """Navigate to a single URL and extract structured data."""
        page_start = time.time()
        crawled = CrawledPage(url=url, depth=depth)

        # Phase 1.5C — Attach network listeners BEFORE navigation to capture all requests
        network_data = self._extract_network_activity(page)

        try:
            response = page.goto(
                url,
                timeout=config.page_timeout_ms,
                wait_until="domcontentloaded",
            )
            status = response.status if response else 200

            # Check for auth redirect / HTTP errors
            final_url = page.url
            if status == 401 or status == 403:
                crawled.crawl_status = "authentication_required"
                crawled.status = status
                crawled.duration_ms = (time.time() - page_start) * 1000
                # Still finalize network activity even on auth redirect
                crawled.network_activity = self._finalize_network_activity(page, network_data)
                return crawled

            if status >= 400:
                crawled.crawl_status = "failed"
                crawled.status = status
                crawled.error = f"HTTP {status}"
                crawled.duration_ms = (time.time() - page_start) * 1000
                crawled.network_activity = self._finalize_network_activity(page, network_data)
                return crawled

            crawled.status = status

            # SPA hydration wait
            time.sleep(config.post_load_wait_ms / 1000.0)

            # Extract page data via JS (existing extraction)
            try:
                raw = page.evaluate(_PAGE_EXTRACT_JS)
            except Exception as js_err:
                raw = {}
                crawled.warnings = [f"JS extraction error: {str(js_err)[:100]}"]

            # Map raw data onto CrawledPage
            crawled.title = raw.get("title", "")
            crawled.forms = raw.get("forms", [])
            crawled.inputs = raw.get("inputs", [])
            crawled.buttons = raw.get("buttons", [])
            crawled.nav_links = raw.get("nav_links", [])
            crawled.has_login = raw.get("has_login", False)
            crawled.has_search = raw.get("has_search", False)
            crawled.has_cart = raw.get("has_cart", False)
            crawled.has_product = raw.get("has_product", False)
            crawled.main_text = raw.get("main_text", "")
            crawled.content_summary = crawled.main_text[:200]

            # Check if we ended up on a login page (auth redirect)
            if (
                crawled.has_login
                and ("login" in final_url.lower() or "signin" in final_url.lower())
                and final_url != url
            ):
                crawled.crawl_status = "authentication_required"
            else:
                crawled.crawl_status = "success"

            # Detect flows (same logic as existing _crawl_page)
            flows = []
            if crawled.has_login:
                flows.append("Authentication/Login")
            if crawled.has_search:
                flows.append("Search Functionality")
            if crawled.has_cart:
                flows.append("Shopping Cart")
            if crawled.has_product:
                flows.append("Product Browsing")
            if crawled.forms:
                flows.append("Form Submission")
            if crawled.nav_links:
                flows.append("Navigation")
            crawled.detected_flows = flows

            # Classify page
            page_type, confidence = classify_page(
                url=final_url,
                title=crawled.title,
                has_login=crawled.has_login,
                has_search=crawled.has_search,
                has_cart=crawled.has_cart,
                forms=crawled.forms,
            )
            crawled.page_type = page_type
            crawled.page_type_confidence = confidence

            # Discover links for BFS
            all_link_data = raw.get("all_links", []) + raw.get("nav_links", [])
            seen_hrefs: Set[str] = set()
            for link_raw in all_link_data:
                href = link_raw.get("href", "")
                if not href:
                    continue
                resolved = resolve_url(final_url, href)
                if not resolved or resolved in seen_hrefs:
                    continue
                seen_hrefs.add(resolved)
                crawled.links.append(PageLink(
                    source=final_url,
                    target=resolved,
                    text=link_raw.get("text", ""),
                    link_type="navigation",
                ))

            # ============================================================
            # Phase 1.5B — DOM + Accessibility Tree Extraction
            # ============================================================
            if crawled.crawl_status == "success":
                # 1. Extract structured DOM
                dom_data = self._extract_dom(page)
                crawled.dom = dom_data

                # 2. Extract accessibility tree (try CDP first, fallback to DOM)
                accessibility_data = self._extract_accessibility_tree_cdp(page)
                if accessibility_data is None:
                    accessibility_data = self._extract_accessibility_tree_dom_fallback(dom_data)
                crawled.accessibility_tree = accessibility_data

                # 3. Derive UI insights
                crawled.ui_insights = self._derive_ui_insights(dom_data, accessibility_data)

            # ============================================================
            # Phase 1.5C — Network/API Understanding
            # ============================================================
            # Finalize network activity collection
            crawled.network_activity = self._finalize_network_activity(page, network_data)

            # ============================================================
            # Phase 1.5D — Screenshot Capture & Visual Evidence
            # ============================================================
            # Capture screenshot after all extractions are complete
            if crawled.crawl_status == "success":
                crawled.screenshot = self._capture_screenshot(page, config)
            else:
                crawled.screenshot = {"status": "skipped", "reason": f"crawl_status={crawled.crawl_status}"}

        except Exception as e:
            err_str = str(e)
            if "Timeout" in err_str or "timeout" in err_str:
                crawled.crawl_status = "timeout"
            else:
                crawled.crawl_status = "failed"
            crawled.error = err_str[:300]
            logger.warning(f"[ApplicationCrawler] Failed to crawl {url}: {err_str[:150]}")
            # Finalize network activity even on error
            crawled.network_activity = self._finalize_network_activity(page, network_data)

        crawled.duration_ms = round((time.time() - page_start) * 1000, 1)
        return crawled
