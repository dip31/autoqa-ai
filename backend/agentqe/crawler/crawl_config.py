"""
Crawl Configuration for Phase 1.5A Bounded Multi-Page Application Crawler.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class CrawlConfig:
    """
    Safe, bounded crawl configuration with sensible defaults.

    All limits are hard limits — the crawler will never exceed them even if
    the caller requests it.
    """

    # Maximum number of pages to visit (hard cap)
    max_pages: int = 20

    # Maximum BFS depth from the start URL
    max_depth: int = 3

    # Restrict crawl to the same domain as the start URL
    same_domain_only: bool = True

    # Per-page navigation timeout in milliseconds
    page_timeout_ms: int = 15000

    # Total wall-clock budget for the entire crawl in seconds
    overall_timeout_seconds: int = 60

    # Wait after page load before scraping (ms) — allows SPA hydration
    post_load_wait_ms: int = 1500

    # Query parameters to strip during URL normalisation
    # (common tracking/analytics params that don't change app state)
    ignored_query_params: List[str] = field(default_factory=lambda: [
        "utm_source", "utm_medium", "utm_campaign", "utm_term",
        "utm_content", "ref", "referrer", "_ga", "fbclid",
        "gclid", "msclkid",
    ])

    # Phase 1.5D — Screenshot Configuration
    # Enable/disable screenshot capture
    screenshots_enabled: bool = True
    # Screenshot type: "viewport" or "full_page"
    screenshot_type: str = "viewport"
    # Screenshot timeout in milliseconds
    screenshot_timeout_ms: int = 5000
    # Maximum screenshot dimensions (for full_page)
    max_screenshot_width: int = 3840
    max_screenshot_height: int = 2160
    # Maximum screenshot file size in bytes (5MB)
    max_screenshot_bytes: int = 5_000_000

    # Hard caps regardless of user input
    _MAX_PAGES_HARD_CAP: int = 50
    _MAX_DEPTH_HARD_CAP: int = 6

    def __post_init__(self):
        # Enforce hard caps silently
        self.max_pages = min(self.max_pages, self._MAX_PAGES_HARD_CAP)
        self.max_depth = min(self.max_depth, self._MAX_DEPTH_HARD_CAP)
        # Validate screenshot_type
        if self.screenshot_type not in ("viewport", "full_page"):
            self.screenshot_type = "viewport"

    @classmethod
    def from_dict(cls, d: dict) -> "CrawlConfig":
        """Create CrawlConfig from a partial dict, using defaults for missing keys."""
        valid_keys = {
            "max_pages", "max_depth", "same_domain_only",
            "page_timeout_ms", "overall_timeout_seconds",
            "post_load_wait_ms", "ignored_query_params",
            "screenshots_enabled", "screenshot_type",
            "screenshot_timeout_ms", "max_screenshot_width",
            "max_screenshot_height", "max_screenshot_bytes",
        }
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered)
