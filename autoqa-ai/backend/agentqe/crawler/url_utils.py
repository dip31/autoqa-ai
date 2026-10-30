"""
URL Utilities — normalization, same-domain checks, and URL discovery helpers.
"""
import re
from typing import Optional
from urllib.parse import (
    urlparse, urlunparse, urljoin, urlencode, parse_qs, quote
)


def normalize_url(url: str, strip_params: Optional[list] = None) -> str:
    """
    Normalise a URL for deduplication purposes.

    Handles:
    - Trailing slashes (kept only on root)
    - Fragments (removed — fragments don't identify a new resource)
    - Scheme normalisation (lower-case)
    - Host normalisation (lower-case)
    - Removal of specified tracking query params
    - Encoding consistency
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url)

        scheme = (parsed.scheme or "https").lower()
        netloc = (parsed.netloc or "").lower()
        path = parsed.path or "/"

        # Remove trailing slash except for root
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        # Strip fragments entirely (e.g. #section → ignored)
        fragment = ""

        # Process query params: strip tracking params, keep the rest sorted
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        if strip_params:
            for param in strip_params:
                query_params.pop(param, None)

        # Reconstruct sorted, stable query string
        sorted_query = urlencode(
            {k: v[0] for k, v in sorted(query_params.items())},
            quote_via=quote,
        ) if query_params else ""

        normalised = urlunparse((scheme, netloc, path, "", sorted_query, fragment))
        return normalised
    except Exception:
        return url


def resolve_url(base_url: str, href: str) -> str:
    """
    Resolve a relative or absolute href against a base URL.
    Returns empty string for non-HTTP schemes (javascript:, mailto:, etc.).
    """
    if not href or not href.strip():
        return ""

    href = href.strip()

    # Ignore non-navigable schemes
    if re.match(r'^(javascript|mailto|tel|data|blob|file):', href, re.IGNORECASE):
        return ""

    # Already absolute
    if href.startswith("http://") or href.startswith("https://"):
        return href

    # Protocol-relative
    if href.startswith("//"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}:{href}"

    # Relative URL — resolve against base
    try:
        return urljoin(base_url, href)
    except Exception:
        return ""


def is_same_domain(url: str, origin_url: str) -> bool:
    """
    Return True if *url* is on the same domain (netloc) as *origin_url*.
    Subdomains of the same root are considered different domains by default
    (e.g., api.example.com ≠ example.com) to avoid accidentally crawling
    separate services.
    """
    try:
        url_host = urlparse(url).netloc.lower()
        origin_host = urlparse(origin_url).netloc.lower()
        return url_host == origin_host
    except Exception:
        return False


def extract_origin(url: str) -> str:
    """Return scheme + netloc (the allowed crawl origin)."""
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return ""


def is_navigable_url(url: str) -> bool:
    """
    Return True if the URL looks like a page a user would navigate to.
    Reject binary resources, media, and other non-page content.
    """
    if not url:
        return False

    # Must be http/https
    if not url.startswith("http"):
        return False

    # Reject common non-page extensions
    non_page_exts = (
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
        ".ico", ".pdf", ".zip", ".gz", ".tar", ".mp4", ".mp3",
        ".avi", ".mov", ".webm", ".css", ".js", ".woff", ".woff2",
        ".ttf", ".eot", ".map", ".xml", ".json", ".csv",
    )
    path = urlparse(url).path.lower()
    for ext in non_page_exts:
        if path.endswith(ext):
            return False

    return True
