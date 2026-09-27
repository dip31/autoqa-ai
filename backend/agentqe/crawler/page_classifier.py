"""
Page classifier — heuristic, deterministic page type classification.
No LLM is used in this phase.
"""
from typing import Dict, Any, Tuple

# Pattern rules: (signals to check) → page_type
# Each rule is (path_keywords, title_keywords, has_login, has_search, has_cart)
_PATH_TYPE_RULES = [
    (["login", "signin", "sign-in", "log-in", "auth"], "authentication"),
    (["register", "signup", "sign-up", "create-account", "join"], "registration"),
    (["dashboard", "home", "overview", "summary"], "dashboard"),
    (["profile", "account", "settings", "preferences", "me"], "profile"),
    (["settings", "preferences", "config", "configuration"], "settings"),
    (["search", "find", "results", "query"], "search"),
    (["product", "item", "catalogue", "catalog", "shop", "store"], "listing"),
    (["product/", "item/", "p/", "detail", "view"], "detail"),
    (["checkout", "cart", "basket", "payment", "order"], "checkout"),
    (["admin", "manage", "management", "cms", "backend", "control"], "admin"),
    (["contact", "support", "help", "faq", "about"], "information"),
    (["404", "error", "not-found", "500"], "error"),
    (["blog", "news", "article", "post", "feed"], "content"),
]


def classify_page(
    url: str,
    title: str,
    has_login: bool,
    has_search: bool,
    has_cart: bool,
    forms: list,
) -> Tuple[str, str]:
    """
    Classify a page using deterministic heuristics.

    Returns:
        (page_type, confidence)  — confidence is "observed" or "inferred"
    """
    url_lower = url.lower()
    title_lower = (title or "").lower()

    # Strong observed signals
    if has_login and has_cart:
        return "checkout", "inferred"
    if has_login and "/login" in url_lower:
        return "authentication", "observed"
    if "/register" in url_lower or "/signup" in url_lower:
        return "registration", "observed"
    if has_login:
        # Has a password field — likely auth
        return "authentication", "inferred"
    if has_cart:
        return "checkout", "inferred"
    if has_search and "search" in url_lower:
        return "search", "observed"

    # Path-based rules
    for keywords, page_type in _PATH_TYPE_RULES:
        for kw in keywords:
            if kw in url_lower:
                return page_type, "observed"
            if kw in title_lower:
                return page_type, "inferred"

    # Form-based fallback
    if forms:
        return "form", "inferred"

    # Root path → dashboard candidate
    from urllib.parse import urlparse
    path = urlparse(url).path
    if path in ("/", ""):
        return "dashboard", "inferred"

    return "unknown", "inferred"
