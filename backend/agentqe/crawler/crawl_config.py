"""
Crawl Configuration for Phase 1.5A Bounded Multi-Page Application Crawler.
"""
from dataclasses import dataclass, field
from typing import List
import os


@dataclass
class CrawlConfig:
    """
    Safe, bounded crawl configuration with sensible defaults.

    All limits are hard limits — the crawler will never exceed them even if
    the caller requests it.
    """

    # Maximum number of pages to visit (hard cap)
    max_pages: int = 3

    # Maximum BFS depth from the start URL
    max_depth: int = 1

    # Restrict crawl to the same domain as the start URL
    same_domain_only: bool = True

    # Per-page navigation timeout in milliseconds
    page_timeout_ms: int = 15000

    # Total wall-clock budget for the entire crawl in seconds
    overall_timeout_seconds: int = int(os.getenv("CRAWLER_OVERALL_TIMEOUT_SECONDS", "3600"))

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

    # Phase 1.5E — Visual UI Parsing (OmniParser) Configuration
    # Enable/disable visual parsing (requires screenshots_enabled=True)
    visual_parsing_enabled: bool = True
    # OmniParser timeout in milliseconds (default 2 minutes for GPU inference)
    omniparser_timeout_ms: int = 120000
    # OmniParser box threshold for detection
    omniparser_box_threshold: float = 0.05
    # OmniParser IOU threshold for NMS
    omniparser_iou_threshold: float = 0.1
    # OmniParser image size for icon detection
    omniparser_imgsz: int = 640

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
        # Load visual parsing settings from env if not explicitly set
        if not hasattr(self, '_env_loaded'):
            self.visual_parsing_enabled = os.getenv("VISUAL_PARSING_ENABLED", "true").lower() == "true"
            self.omniparser_timeout_ms = int(os.getenv("OMNIPARSER_TIMEOUT_MS", str(self.omniparser_timeout_ms)))
            self.omniparser_box_threshold = float(os.getenv("OMNIPARSER_BOX_THRESHOLD", str(self.omniparser_box_threshold)))
            self.omniparser_iou_threshold = float(os.getenv("OMNIPARSER_IOU_THRESHOLD", str(self.omniparser_iou_threshold)))
            self.omniparser_imgsz = int(os.getenv("OMNIPARSER_IMGSZ", str(self.omniparser_imgsz)))

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
            "visual_parsing_enabled", "omniparser_timeout_ms",
            "omniparser_box_threshold", "omniparser_iou_threshold",
            "omniparser_imgsz",
        }
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered)
