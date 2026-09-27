"""
Page-level data structures produced by the crawler.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PageLink:
    """Represents a discovered link on a page."""
    source: str          # source page path/URL
    target: str          # resolved target URL
    text: str = ""       # visible link text
    link_type: str = "navigation"   # navigation | form_action | resource


@dataclass
class CrawledPage:
    """
    Structured data collected from a single crawled page.
    Preserves the same fields as the existing _crawl_page() output so that
    downstream consumers are not broken.
    """
    url: str
    depth: int
    status: int = 200
    title: str = ""
    page_type: str = "unknown"          # heuristic classification
    page_type_confidence: str = "inferred"  # observed | inferred
    links: List[PageLink] = field(default_factory=list)
    nav_links: List[Dict[str, Any]] = field(default_factory=list)
    forms: List[Dict[str, Any]] = field(default_factory=list)
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    buttons: List[str] = field(default_factory=list)
    detected_flows: List[str] = field(default_factory=list)
    content_summary: str = ""
    main_text: str = ""
    has_login: bool = False
    has_search: bool = False
    has_cart: bool = False
    has_product: bool = False
    crawl_status: str = "success"       # success | failed | auth_required | timeout
    error: Optional[str] = None
    duration_ms: float = 0.0
    # Phase 1.5B — DOM + Accessibility Tree
    dom: Dict[str, Any] = field(default_factory=dict)
    accessibility_tree: Dict[str, Any] = field(default_factory=dict)
    ui_insights: Dict[str, Any] = field(default_factory=dict)
    # Phase 1.5C — Network/API Understanding
    network_activity: List[Dict[str, Any]] = field(default_factory=list)
    # Phase 1.5D — Screenshot Capture & Visual Evidence
    screenshot: Dict[str, Any] = field(default_factory=dict)
    # Phase 1.5E — Visual UI Parsing Evidence
    visual_ui: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "depth": self.depth,
            "status": self.status,
            "title": self.title,
            "page_type": self.page_type,
            "page_type_confidence": self.page_type_confidence,
            "links": [
                {"source": l.source, "target": l.target, "text": l.text, "type": l.link_type}
                for l in self.links
            ],
            "nav_links": self.nav_links,
            "forms": self.forms,
            "inputs": self.inputs,
            "buttons": self.buttons,
            "detected_flows": self.detected_flows,
            "content_summary": self.content_summary,
            "has_login": self.has_login,
            "has_search": self.has_search,
            "has_cart": self.has_cart,
            "has_product": self.has_product,
            "crawl_status": self.crawl_status,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "dom": self.dom,
            "accessibility_tree": self.accessibility_tree,
            "ui_insights": self.ui_insights,
            "network_activity": self.network_activity,
            "screenshot": self.screenshot,
            "visual_ui": self.visual_ui,
        }


@dataclass
class CrawlResult:
    """Top-level result returned by ApplicationCrawler.crawl()."""
    start_url: str
    pages: List[CrawledPage] = field(default_factory=list)
    navigation_graph: Dict[str, Any] = field(default_factory=dict)
    discovered_routes: List[Dict[str, Any]] = field(default_factory=list)
    crawl_metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    # Phase 1.5C — aggregated API endpoints observed across all pages.
    # ApplicationCrawler.crawl() already populated this attribute, but the field
    # (and its serialization) were missing, so the aggregate never reached
    # consumers. Declared here so it survives to_dict(); purely additive.
    api_endpoints: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_url": self.start_url,
            "pages": [p.to_dict() for p in self.pages],
            "navigation_graph": self.navigation_graph,
            "discovered_routes": self.discovered_routes,
            "crawl_metadata": self.crawl_metadata,
            "warnings": self.warnings,
            "api_endpoints": self.api_endpoints,
        }
