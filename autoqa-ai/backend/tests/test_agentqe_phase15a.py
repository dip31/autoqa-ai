"""
Phase 1.5A — Bounded Multi-Page Application Crawler Tests

Tests are written against unit-testable modules only.
Playwright interactions are fully mocked so no live network calls are made.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from urllib.parse import urlparse


# ─────────────────────────────────────────────────────────────────────────────
# URL Utilities
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeUrl:
    from agentqe.crawler.url_utils import normalize_url

    def test_removes_trailing_slash(self):
        from agentqe.crawler.url_utils import normalize_url
        assert normalize_url("https://example.com/login/") == "https://example.com/login"

    def test_preserves_root_slash(self):
        from agentqe.crawler.url_utils import normalize_url
        result = normalize_url("https://example.com/")
        assert result == "https://example.com/"

    def test_removes_fragment(self):
        from agentqe.crawler.url_utils import normalize_url
        result = normalize_url("https://example.com/#home")
        assert "#" not in result

    def test_strips_tracking_params(self):
        from agentqe.crawler.url_utils import normalize_url
        url = "https://example.com/page?utm_source=google&id=5"
        result = normalize_url(url, strip_params=["utm_source"])
        assert "utm_source" not in result
        assert "id=5" in result

    def test_sorts_query_params(self):
        from agentqe.crawler.url_utils import normalize_url
        a = normalize_url("https://example.com/?b=2&a=1")
        b = normalize_url("https://example.com/?a=1&b=2")
        assert a == b

    def test_lowercases_scheme_and_host(self):
        from agentqe.crawler.url_utils import normalize_url
        result = normalize_url("HTTPS://Example.COM/Path")
        assert result.startswith("https://example.com")

    def test_empty_string_returns_empty(self):
        from agentqe.crawler.url_utils import normalize_url
        assert normalize_url("") == ""


class TestResolveUrl:
    def test_absolute_url_unchanged(self):
        from agentqe.crawler.url_utils import resolve_url
        result = resolve_url("https://example.com", "https://other.com/page")
        assert result == "https://other.com/page"

    def test_relative_url_resolved(self):
        from agentqe.crawler.url_utils import resolve_url
        result = resolve_url("https://example.com/dashboard/", "settings")
        assert "example.com" in result

    def test_absolute_path_resolved(self):
        from agentqe.crawler.url_utils import resolve_url
        result = resolve_url("https://example.com/any/path", "/login")
        assert result == "https://example.com/login"

    def test_javascript_ignored(self):
        from agentqe.crawler.url_utils import resolve_url
        assert resolve_url("https://example.com", "javascript:void(0)") == ""

    def test_mailto_ignored(self):
        from agentqe.crawler.url_utils import resolve_url
        assert resolve_url("https://example.com", "mailto:test@example.com") == ""

    def test_empty_href_ignored(self):
        from agentqe.crawler.url_utils import resolve_url
        assert resolve_url("https://example.com", "") == ""


class TestIsSameDomain:
    def test_same_domain(self):
        from agentqe.crawler.url_utils import is_same_domain
        assert is_same_domain("https://example.com/login", "https://example.com")

    def test_different_domain(self):
        from agentqe.crawler.url_utils import is_same_domain
        assert not is_same_domain("https://google.com", "https://example.com")

    def test_subdomain_is_different(self):
        from agentqe.crawler.url_utils import is_same_domain
        assert not is_same_domain("https://api.example.com", "https://example.com")


class TestIsNavigableUrl:
    def test_html_page_navigable(self):
        from agentqe.crawler.url_utils import is_navigable_url
        assert is_navigable_url("https://example.com/login")

    def test_image_not_navigable(self):
        from agentqe.crawler.url_utils import is_navigable_url
        assert not is_navigable_url("https://example.com/logo.png")

    def test_css_not_navigable(self):
        from agentqe.crawler.url_utils import is_navigable_url
        assert not is_navigable_url("https://example.com/style.css")

    def test_js_file_not_navigable(self):
        from agentqe.crawler.url_utils import is_navigable_url
        assert not is_navigable_url("https://example.com/app.js")

    def test_empty_not_navigable(self):
        from agentqe.crawler.url_utils import is_navigable_url
        assert not is_navigable_url("")


# ─────────────────────────────────────────────────────────────────────────────
# Page Classifier
# ─────────────────────────────────────────────────────────────────────────────

class TestPageClassifier:
    def test_login_url_classifies_as_auth_observed(self):
        from agentqe.crawler.page_classifier import classify_page
        ptype, confidence = classify_page(
            url="https://example.com/login", title="Login",
            has_login=True, has_search=False, has_cart=False, forms=[]
        )
        assert ptype == "authentication"
        assert confidence == "observed"

    def test_register_url_classifies_as_registration(self):
        from agentqe.crawler.page_classifier import classify_page
        ptype, _ = classify_page(
            url="https://example.com/register", title="Register",
            has_login=False, has_search=False, has_cart=False, forms=[]
        )
        assert ptype == "registration"

    def test_password_field_classifies_as_auth_inferred(self):
        from agentqe.crawler.page_classifier import classify_page
        ptype, confidence = classify_page(
            url="https://example.com/", title="",
            has_login=True, has_search=False, has_cart=False, forms=[]
        )
        assert ptype == "authentication"
        assert confidence == "inferred"

    def test_root_path_classifies_as_dashboard(self):
        from agentqe.crawler.page_classifier import classify_page
        ptype, _ = classify_page(
            url="https://example.com/", title="Home",
            has_login=False, has_search=False, has_cart=False, forms=[]
        )
        assert ptype == "dashboard"

    def test_search_url_classifies_as_search(self):
        from agentqe.crawler.page_classifier import classify_page
        ptype, _ = classify_page(
            url="https://example.com/search", title="Search",
            has_login=False, has_search=True, has_cart=False, forms=[]
        )
        assert ptype == "search"

    def test_unknown_url_classifies_as_unknown(self):
        from agentqe.crawler.page_classifier import classify_page
        ptype, _ = classify_page(
            url="https://example.com/xyzabc", title="",
            has_login=False, has_search=False, has_cart=False, forms=[]
        )
        assert ptype == "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# CrawlConfig
# ─────────────────────────────────────────────────────────────────────────────

class TestCrawlConfig:
    def test_defaults(self):
        from agentqe.crawler.crawl_config import CrawlConfig
        cfg = CrawlConfig()
        assert cfg.max_pages == 20
        assert cfg.max_depth == 3
        assert cfg.same_domain_only is True

    def test_hard_cap_enforced_for_max_pages(self):
        from agentqe.crawler.crawl_config import CrawlConfig
        cfg = CrawlConfig(max_pages=999)
        assert cfg.max_pages == 50  # hard cap

    def test_hard_cap_enforced_for_max_depth(self):
        from agentqe.crawler.crawl_config import CrawlConfig
        cfg = CrawlConfig(max_depth=99)
        assert cfg.max_depth == 6

    def test_from_dict_partial(self):
        from agentqe.crawler.crawl_config import CrawlConfig
        cfg = CrawlConfig.from_dict({"max_pages": 5, "max_depth": 2})
        assert cfg.max_pages == 5
        assert cfg.max_depth == 2
        assert cfg.same_domain_only is True  # default preserved

    def test_from_dict_ignores_unknown_keys(self):
        from agentqe.crawler.crawl_config import CrawlConfig
        cfg = CrawlConfig.from_dict({"max_pages": 10, "unknown_key": "value"})
        assert cfg.max_pages == 10


# ─────────────────────────────────────────────────────────────────────────────
# CrawlResult / CrawledPage
# ─────────────────────────────────────────────────────────────────────────────

class TestCrawlResult:
    def test_crawled_page_serialization(self):
        from agentqe.crawler.crawl_result import CrawledPage, PageLink
        page = CrawledPage(
            url="https://example.com/login",
            depth=1,
            status=200,
            title="Login",
            page_type="authentication",
            page_type_confidence="observed",
            forms=[{"action": "/api/login", "method": "post", "inputs": []}],
            crawl_status="success",
        )
        d = page.to_dict()
        assert d["url"] == "https://example.com/login"
        assert d["page_type"] == "authentication"
        assert d["crawl_status"] == "success"
        assert d["forms"][0]["action"] == "/api/login"

    def test_crawl_result_serialization(self):
        from agentqe.crawler.crawl_result import CrawlResult, CrawledPage
        result = CrawlResult(start_url="https://example.com")
        result.pages.append(CrawledPage(url="https://example.com", depth=0))
        result.navigation_graph = {"nodes": ["https://example.com"], "edges": []}
        result.crawl_metadata = {"pages_analyzed": 1}

        d = result.to_dict()
        assert d["start_url"] == "https://example.com"
        assert len(d["pages"]) == 1
        assert d["navigation_graph"]["nodes"] == ["https://example.com"]


# ─────────────────────────────────────────────────────────────────────────────
# ApplicationCrawler — unit tests with mocked Playwright
# ─────────────────────────────────────────────────────────────────────────────

def _make_mock_page_data(url="https://example.com", title="Example"):
    return {
        "title": title,
        "url": url,
        "h1": "Welcome",
        "nav_links": [
            {"text": "Login", "href": "/login"},
            {"text": "Register", "href": "/register"},
        ],
        "all_links": [
            {"text": "Login", "href": "https://example.com/login"},
            {"text": "About", "href": "https://example.com/about"},
            {"text": "GitHub", "href": "https://github.com/user/repo"},  # external
        ],
        "forms": [],
        "buttons": ["Submit"],
        "inputs": [],
        "images": 0,
        "has_login": False,
        "has_search": False,
        "has_cart": False,
        "has_product": False,
        "main_text": "Welcome to the example application",
    }


class TestApplicationCrawlerUnit:
    """Unit tests that mock Playwright entirely."""

    def _build_mock_playwright_stack(self, pages_data: list):
        """
        Build a mock Playwright stack.
        pages_data: list of (url, page_dict) representing pages to serve in order.
        """
        mock_browser = MagicMock()
        mock_ctx = MagicMock()
        mock_page = MagicMock()
        mock_playwright = MagicMock()

        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_ctx
        mock_ctx.new_page.return_value = mock_page

        # Each call to page.goto() returns a mock response with status 200
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response

        # page.url always returns the current URL
        # evaluate() returns the page data for the current call number
        call_counter = {"n": 0}
        data_list = [pd for _, pd in pages_data]

        def evaluate_side_effect(*args, **kwargs):
            idx = min(call_counter["n"], len(data_list) - 1)
            call_counter["n"] += 1
            return data_list[idx]

        mock_page.evaluate.side_effect = evaluate_side_effect

        # page.url reflects whatever goto was called with
        urls = [url for url, _ in pages_data]
        url_idx = {"n": 0}

        def goto_side_effect(url, **kwargs):
            mock_page.url = url
            return mock_response

        mock_page.goto.side_effect = goto_side_effect
        mock_page.url = pages_data[0][0] if pages_data else "https://example.com"

        return mock_playwright, mock_browser, mock_ctx, mock_page

    def test_start_url_is_crawled(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig

        pages = [
            ("https://example.com/", _make_mock_page_data("https://example.com/", "Home")),
        ]
        mock_pw, _, _, mock_page = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                config = CrawlConfig(max_pages=5, max_depth=2)
                result = crawler.crawl("https://example.com/", config)

        assert result.start_url == "https://example.com/"
        assert len(result.pages) >= 1
        assert result.pages[0].depth == 0

    def test_max_pages_respected(self):
        """Crawler should stop after max_pages pages have been visited."""
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig

        # Simulate a page that returns 20 internal links each time
        many_links = [{"text": f"Page {i}", "href": f"https://example.com/page{i}"} for i in range(20)]
        page_data = {**_make_mock_page_data(), "all_links": many_links, "nav_links": many_links}
        pages = [("https://example.com/", page_data)] * 10

        mock_pw, _, _, mock_page = self._build_mock_playwright_stack(pages)
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                # Return increasing time values to prevent timeout
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=3, max_depth=3))

        assert len(result.pages) <= 3
        assert any("max_pages" in w for w in result.warnings)

    def test_external_links_ignored_with_same_domain_only(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig

        page_data = {
            **_make_mock_page_data(),
            "all_links": [
                {"text": "GitHub", "href": "https://github.com/user/repo"},
                {"text": "Google", "href": "https://google.com"},
                {"text": "Internal", "href": "https://example.com/about"},
            ],
            "nav_links": [],
        }
        pages = [
            ("https://example.com/", page_data),
            ("https://example.com/about", _make_mock_page_data("https://example.com/about", "About")),
        ]
        mock_pw, _, _, mock_page = self._build_mock_playwright_stack(pages)

        visited_urls = []

        def goto_side_effect(url, **kwargs):
            visited_urls.append(url)
            mock_page.url = url
            resp = MagicMock()
            resp.status = 200
            return resp

        mock_page.goto.side_effect = goto_side_effect

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl(
                    "https://example.com/",
                    CrawlConfig(max_pages=5, max_depth=2, same_domain_only=True)
                )

        # External domains must not appear in visited URLs
        for url in visited_urls:
            assert "github.com" not in url, f"External URL was crawled: {url}"
            assert "google.com" not in url, f"External URL was crawled: {url}"

    def test_duplicate_urls_not_crawled_twice(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig

        # Both pages link back to the start URL — should not create a loop
        page_data = {
            **_make_mock_page_data(),
            "all_links": [
                {"text": "Home", "href": "https://example.com/"},
                {"text": "Home Again", "href": "https://example.com/"},
                {"text": "About", "href": "https://example.com/about"},
            ],
            "nav_links": [],
        }
        pages = [
            ("https://example.com/", page_data),
            ("https://example.com/about", _make_mock_page_data("https://example.com/about", "About")),
        ]
        mock_pw, _, _, mock_page = self._build_mock_playwright_stack(pages)

        visited_urls = []

        def goto_side_effect(url, **kwargs):
            visited_urls.append(url)
            mock_page.url = url
            resp = MagicMock()
            resp.status = 200
            return resp

        mock_page.goto.side_effect = goto_side_effect

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=10, max_depth=2))

        # Home should appear exactly once
        home_visits = [u for u in visited_urls if u.rstrip("/") == "https://example.com"]
        assert len(home_visits) == 1

    def test_navigation_graph_generated(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig

        page_data = {
            **_make_mock_page_data(),
            "all_links": [{"text": "Login", "href": "https://example.com/login"}],
            "nav_links": [],
        }
        pages = [
            ("https://example.com/", page_data),
            ("https://example.com/login", _make_mock_page_data("https://example.com/login", "Login")),
        ]
        mock_pw, _, _, mock_page = self._build_mock_playwright_stack(pages)

        def goto_side_effect(url, **kwargs):
            mock_page.url = url
            resp = MagicMock()
            resp.status = 200
            return resp

        mock_page.goto.side_effect = goto_side_effect

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=5, max_depth=2))

        assert "nodes" in result.navigation_graph
        assert "edges" in result.navigation_graph

    def test_crawl_metadata_generated(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig

        pages = [("https://example.com/", _make_mock_page_data())]
        mock_pw, _, _, mock_page = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=5))

        meta = result.crawl_metadata
        assert "pages_analyzed" in meta
        assert "pages_failed" in meta
        assert "duration_seconds" in meta
        assert "max_pages" in meta

    def test_failed_page_does_not_destroy_successful_results(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig

        page_data_home = {
            **_make_mock_page_data(),
            "all_links": [
                {"text": "Works", "href": "https://example.com/good"},
                {"text": "Broken", "href": "https://example.com/broken"},
            ],
            "nav_links": [],
        }
        pages = [
            ("https://example.com/", page_data_home),
            ("https://example.com/good", _make_mock_page_data("https://example.com/good", "Good Page")),
        ]
        mock_pw, _, _, mock_page = self._build_mock_playwright_stack(pages)

        call_count = {"n": 0}
        data_list = [pd for _, pd in pages]

        def evaluate_side_effect(*args, **kwargs):
            idx = min(call_count["n"], len(data_list) - 1)
            call_count["n"] += 1
            return data_list[idx]

        mock_page.evaluate.side_effect = evaluate_side_effect

        def goto_side_effect(url, **kwargs):
            mock_page.url = url
            if "broken" in url:
                from playwright.sync_api import Error
                raise Exception("net::ERR_NAME_NOT_RESOLVED")
            resp = MagicMock()
            resp.status = 200
            return resp

        mock_page.goto.side_effect = goto_side_effect

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=5, max_depth=2))

        # Successful pages must be present
        success_pages = [p for p in result.pages if p.crawl_status == "success"]
        assert len(success_pages) >= 1

    def test_per_page_data_preserved(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig

        page_data = {
            **_make_mock_page_data(),
            "forms": [{"id": "login-form", "action": "/api/login", "method": "post", "inputs": [
                {"type": "email", "name": "email", "placeholder": "Email", "required": True}
            ]}],
            "buttons": ["Submit", "Cancel"],
            "inputs": [{"type": "email", "name": "email", "placeholder": "Email"}],
            "has_login": True,
        }
        pages = [("https://example.com/", page_data)]
        mock_pw, _, _, mock_page = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=2))

        page = result.pages[0]
        assert page.forms[0]["action"] == "/api/login"
        assert "Submit" in page.buttons
        assert page.has_login is True

    def test_discovered_routes_populated(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig

        page_data = {
            **_make_mock_page_data(),
            "all_links": [{"text": "Login", "href": "https://example.com/login"}],
            "nav_links": [],
        }
        pages = [
            ("https://example.com/", page_data),
            ("https://example.com/login", _make_mock_page_data("https://example.com/login", "Login")),
        ]
        mock_pw, _, _, mock_page = self._build_mock_playwright_stack(pages)

        def goto_side_effect(url, **kwargs):
            mock_page.url = url
            resp = MagicMock()
            resp.status = 200
            return resp

        mock_page.goto.side_effect = goto_side_effect

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=5, max_depth=2))

        paths = [r["path"] for r in result.discovered_routes]
        assert "/" in paths or any("example.com" in p for p in paths)
        # Evidence must be correctly tagged
        for route in result.discovered_routes:
            assert route.get("source") == "application_crawl"
            assert route.get("evidence_type") == "observed"


# ─────────────────────────────────────────────────────────────────────────────
# ApplicationContext Integration
# ─────────────────────────────────────────────────────────────────────────────

class TestApplicationContextIntegration:
    def test_context_has_new_crawl_fields(self):
        from agentqe.models.context import ApplicationContext
        ctx = ApplicationContext(
            url="https://example.com",
            pages=[{"url": "https://example.com", "depth": 0, "crawl_status": "success"}],
            navigation_graph={"nodes": ["https://example.com"], "edges": []},
            crawl_metadata={"pages_analyzed": 1, "duration_seconds": 2.5},
        )
        d = ctx.to_dict()
        assert "pages" in d
        assert "navigation_graph" in d
        assert "crawl_metadata" in d
        assert len(d["pages"]) == 1
        assert d["crawl_metadata"]["pages_analyzed"] == 1

    def test_context_serializes_all_fields(self):
        from agentqe.models.context import ApplicationContext
        ctx = ApplicationContext(
            url="https://example.com",
            app_name="Test App",
            pages=[{"url": "https://example.com/login", "depth": 1}],
            navigation_graph={"nodes": ["https://example.com"], "edges": []},
        )
        d = ctx.to_dict()
        assert d["app_name"] == "Test App"
        assert d["pages"][0]["url"] == "https://example.com/login"


# ─────────────────────────────────────────────────────────────────────────────
# ApplicationUnderstandingAgent Integration
# ─────────────────────────────────────────────────────────────────────────────

class TestApplicationUnderstandingAgentPhase15A:
    def _make_crawl_result(self, pages_count=3):
        from agentqe.crawler.crawl_result import CrawlResult, CrawledPage
        result = CrawlResult(start_url="https://example.com")
        for i in range(pages_count):
            p = CrawledPage(
                url=f"https://example.com/page{i}",
                depth=i,
                title=f"Page {i}",
                page_type="dashboard" if i == 0 else "unknown",
                crawl_status="success",
                forms=[{"action": f"/api/action{i}", "method": "post", "inputs": []}],
                detected_flows=["Navigation"],
            )
            result.pages.append(p)
        result.navigation_graph = {"nodes": [f"https://example.com/page{i}" for i in range(pages_count)], "edges": []}
        result.discovered_routes = [
            {"path": f"/page{i}", "url": f"https://example.com/page{i}",
             "depth": i, "page_type": "unknown", "title": f"Page {i}",
             "status": 200, "crawl_status": "success",
             "evidence_type": "observed", "source": "application_crawl"}
            for i in range(pages_count)
        ]
        result.crawl_metadata = {
            "pages_analyzed": pages_count, "pages_failed": 0,
            "pages_discovered": pages_count, "duration_seconds": 5.0,
        }
        return result

    @patch('agentqe.agents.application_understanding_agent._analyze_requirement')
    def test_agent_uses_multi_page_crawl_result(self, mock_analyze_req):
        from agentqe.agents.application_understanding_agent import ApplicationUnderstandingAgent
        from agentqe.models.context import ApplicationUnderstandingInput

        mock_analyze_req.return_value = {"key_user_flows": [], "items": [], "risk_areas": []}

        crawl_result = self._make_crawl_result(3)

        with patch('agentqe.agents.application_understanding_agent.ApplicationUnderstandingAgent._crawl_application') as mock_crawl:
            mock_crawl.return_value = crawl_result.to_dict()

            agent = ApplicationUnderstandingAgent()
            result = agent.analyze(ApplicationUnderstandingInput(url="https://example.com"))

        assert len(result.pages) == 3
        assert result.navigation_graph is not None
        assert result.crawl_metadata.get("pages_analyzed") == 3

    @patch('agentqe.agents.application_understanding_agent._analyze_requirement')
    def test_forms_aggregated_across_pages(self, mock_analyze_req):
        from agentqe.agents.application_understanding_agent import ApplicationUnderstandingAgent
        from agentqe.models.context import ApplicationUnderstandingInput

        mock_analyze_req.return_value = {"key_user_flows": [], "items": [], "risk_areas": []}
        crawl_result = self._make_crawl_result(3)

        with patch('agentqe.agents.application_understanding_agent.ApplicationUnderstandingAgent._crawl_application') as mock_crawl:
            mock_crawl.return_value = crawl_result.to_dict()

            agent = ApplicationUnderstandingAgent()
            result = agent.analyze(ApplicationUnderstandingInput(url="https://example.com"))

        # Each of the 3 pages has a unique form action → 3 forms total
        assert len(result.forms) == 3

    @patch('agentqe.agents.application_understanding_agent._analyze_requirement')
    def test_discovered_routes_populated(self, mock_analyze_req):
        from agentqe.agents.application_understanding_agent import ApplicationUnderstandingAgent
        from agentqe.models.context import ApplicationUnderstandingInput

        mock_analyze_req.return_value = {"key_user_flows": [], "items": [], "risk_areas": []}
        crawl_result = self._make_crawl_result(3)

        with patch('agentqe.agents.application_understanding_agent.ApplicationUnderstandingAgent._crawl_application') as mock_crawl:
            mock_crawl.return_value = crawl_result.to_dict()

            agent = ApplicationUnderstandingAgent()
            result = agent.analyze(ApplicationUnderstandingInput(url="https://example.com"))

        assert len(result.discovered_routes) == 3

    @patch('agentqe.agents.application_understanding_agent._analyze_requirement')
    def test_evidence_correctly_tags_application_crawl(self, mock_analyze_req):
        from agentqe.agents.application_understanding_agent import ApplicationUnderstandingAgent
        from agentqe.models.context import ApplicationUnderstandingInput

        mock_analyze_req.return_value = {"key_user_flows": [], "items": [], "risk_areas": []}
        crawl_result = self._make_crawl_result(1)

        with patch('agentqe.agents.application_understanding_agent.ApplicationUnderstandingAgent._crawl_application') as mock_crawl:
            mock_crawl.return_value = crawl_result.to_dict()

            agent = ApplicationUnderstandingAgent()
            result = agent.analyze(ApplicationUnderstandingInput(url="https://example.com"))

        assert "pages" in result.evidence
        assert "application_crawl" in result.evidence["pages"]


# ─────────────────────────────────────────────────────────────────────────────
# Regression: existing Phase 1 tests still work
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase1Regression:
    def test_application_context_legacy_fields_intact(self):
        from agentqe.models.context import ApplicationContext
        ctx = ApplicationContext(
            url="https://example.com",
            app_name="Test",
            forms=[{"action": "/login"}],
            discovered_routes=["/login", "/home"],
            api_endpoints=["/api/users"],
            evidence={"app_name": ["application_crawl"]},
        )
        d = ctx.to_dict()
        assert d["forms"][0]["action"] == "/login"
        assert "/login" in d["discovered_routes"]
        assert "/api/users" in d["api_endpoints"]
        assert "application_crawl" in d["evidence"]["app_name"]

    def test_input_model_unchanged(self):
        from agentqe.models.context import ApplicationUnderstandingInput
        inp = ApplicationUnderstandingInput(
            url="https://example.com",
            requirement="Test req",
            repo_url="",
            module_name="Auth",
        )
        d = inp.to_dict()
        assert d["url"] == "https://example.com"
        assert d["module_name"] == "Auth"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1.5B — DOM + Accessibility Tree Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCrawledPagePhase15B:
    """Tests for Phase 1.5B CrawledPage extensions."""

    def test_crawled_page_has_dom_field(self):
        from agentqe.crawler.crawl_result import CrawledPage
        page = CrawledPage(
            url="https://example.com",
            depth=0,
            dom={"interactive_elements": [], "forms": [], "landmarks": []},
        )
        d = page.to_dict()
        assert "dom" in d
        assert d["dom"]["interactive_elements"] == []

    def test_crawled_page_has_accessibility_tree_field(self):
        from agentqe.crawler.crawl_result import CrawledPage
        page = CrawledPage(
            url="https://example.com",
            depth=0,
            accessibility_tree={"source": "playwright", "root": {"role": "WebArea"}},
        )
        d = page.to_dict()
        assert "accessibility_tree" in d
        assert d["accessibility_tree"]["source"] == "playwright"

    def test_crawled_page_has_ui_insights_field(self):
        from agentqe.crawler.crawl_result import CrawledPage
        page = CrawledPage(
            url="https://example.com",
            depth=0,
            ui_insights={"interactive_element_count": 5, "form_count": 1},
        )
        d = page.to_dict()
        assert "ui_insights" in d
        assert d["ui_insights"]["interactive_element_count"] == 5

    def test_crawled_page_defaults_empty_dicts(self):
        from agentqe.crawler.crawl_result import CrawledPage
        page = CrawledPage(url="https://example.com", depth=0)
        d = page.to_dict()
        assert d["dom"] == {}
        assert d["accessibility_tree"] == {}
        assert d["ui_insights"] == {}


class TestApplicationCrawlerPhase15B:
    """Unit tests for Phase 1.5B DOM + Accessibility extraction with mocked Playwright."""

    def _build_mock_page_data(self, url="https://example.com", title="Example"):
        return {
            "title": title,
            "url": url,
            "h1": "Welcome",
            "nav_links": [
                {"text": "Login", "href": "/login"},
                {"text": "Register", "href": "/register"},
            ],
            "all_links": [
                {"text": "Login", "href": "https://example.com/login"},
                {"text": "About", "href": "https://example.com/about"},
            ],
            "forms": [{
                "id": "login-form",
                "name": "login",
                "action": "/api/login",
                "method": "post",
                "inputs": [
                    {"type": "email", "name": "email", "placeholder": "Email", "required": True},
                    {"type": "password", "name": "password", "placeholder": "Password", "required": True},
                ]
            }],
            "buttons": ["Submit", "Cancel"],
            "inputs": [
                {"type": "email", "name": "email", "placeholder": "Email"},
                {"type": "password", "name": "password", "placeholder": "Password"},
            ],
            "images": 0,
            "has_login": True,
            "has_search": False,
            "has_cart": False,
            "has_product": False,
            "main_text": "Welcome to the example application",
        }

    def _build_mock_playwright_stack(self, pages_data: list):
        """
        Build a mock Playwright stack.
        pages_data: list of (url, page_dict) representing pages to serve in order.
        """
        from unittest.mock import MagicMock
        mock_browser = MagicMock()
        mock_ctx = MagicMock()
        mock_page = MagicMock()
        mock_playwright = MagicMock()

        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_ctx
        mock_ctx.new_page.return_value = mock_page

        # IMPORTANT: Set page.context to the browser context for CDP access
        mock_page.context = mock_ctx

        # Each call to page.goto() returns a mock response with status 200
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response

        # page.url always returns the current URL
        # evaluate() returns the page data for the current call number
        call_counter = {"n": 0}
        data_list = [pd for _, pd in pages_data]

        def evaluate_side_effect(script, *args, **kwargs):
            idx = min(call_counter["n"], len(data_list) - 1)
            call_counter["n"] += 1
            # Return different data based on which JS script is being evaluated
            if "_DOM_EXTRACT_JS" in script or "interactive_elements" in script:
                return self._mock_dom_data()
            return data_list[idx]

        mock_page.evaluate.side_effect = evaluate_side_effect

        # page.url reflects whatever goto was called with
        urls = [url for url, _ in pages_data]
        url_idx = {"n": 0}

        def goto_side_effect(url, **kwargs):
            mock_page.url = url
            return mock_response

        mock_page.goto.side_effect = goto_side_effect
        mock_page.url = pages_data[0][0] if pages_data else "https://example.com"

        # Mock CDP session for accessibility
        mock_cdp = MagicMock()
        mock_ctx.new_cdp_session.return_value = mock_cdp
        
        # CDP send returns different responses based on the command
        def cdp_send_side_effect(command, *args, **kwargs):
            if command == "Accessibility.enable":
                return {}
            elif command == "Accessibility.getFullAXTree":
                return {"nodes": [
                    {"nodeId": 1, "role": {"value": "RootWebArea"}, "name": {"value": "Test Page"}, "properties": [{"name": "focusable", "value": {"value": True}}, {"name": "focused", "value": {"value": True}}], "childIds": [2]},
                    {"nodeId": 2, "role": {"value": "button"}, "name": {"value": "Click me"}, "properties": [{"name": "focusable", "value": {"value": True}}], "childIds": []},
                    {"nodeId": 3, "role": {"value": "textbox"}, "name": {"value": "Email"}, "properties": [{"name": "focusable", "value": {"value": True}}, {"name": "editable", "value": {"value": "plaintext"}}], "childIds": []},
                    {"nodeId": 4, "role": {"value": "textbox"}, "name": {"value": "Password"}, "properties": [{"name": "focusable", "value": {"value": True}}, {"name": "editable", "value": {"value": "plaintext"}}, {"name": "password", "value": {"value": True}}], "childIds": []},
                ]}
            elif command == "Accessibility.disable":
                return {}
            return {}
        
        mock_cdp.send.side_effect = cdp_send_side_effect

        return mock_playwright, mock_browser, mock_ctx, mock_page, mock_cdp

    def _mock_dom_data(self):
        return {
            "root": {"tag": "html", "id": "", "text": "Test Page"},
            "elements": [],
            "forms": [{
                "id": "login-form",
                "name": "login",
                "action": "/api/login",
                "method": "post",
                "inputs": [
                    {"tag": "input", "type": "email", "name": "email", "id": "email", "placeholder": "Email", "required": True, "disabled": False, "value_presence": False, "aria_label": "", "aria_describedby": ""},
                    {"tag": "input", "type": "password", "name": "password", "id": "password", "placeholder": "Password", "required": True, "disabled": False, "value_presence": False, "aria_label": "", "aria_describedby": ""},
                ],
                "validation_attrs": {"novalidate": False}
            }],
            "interactive_elements": [
                {"tag": "input", "type": "email", "name": "email", "id": "email", "placeholder": "Email", "required": True, "disabled": False, "visible": True, "aria_label": "", "text": "", "href": "", "bounding_box": None, "parent_ref": None, "role": "textbox"},
                {"tag": "input", "type": "password", "name": "password", "id": "password", "placeholder": "Password", "required": True, "disabled": False, "visible": True, "aria_label": "", "text": "", "href": "", "bounding_box": None, "parent_ref": None, "role": "textbox", "value_presence": False},
                {"tag": "button", "type": "submit", "name": "", "id": "", "placeholder": "", "required": False, "disabled": False, "visible": True, "aria_label": "", "text": "Submit", "href": "", "bounding_box": None, "parent_ref": None, "role": "button"},
            ],
            "landmarks": [
                {"type": "html5", "role": "banner", "tag": "header", "id": "", "label": ""},
                {"type": "html5", "role": "main", "tag": "main", "id": "", "label": ""},
                {"type": "html5", "role": "contentinfo", "tag": "footer", "id": "", "label": ""},
            ],
            "text_summary": [
                {"type": "title", "text": "Test Page"},
                {"type": "h1", "text": "Welcome"},
                {"type": "button", "text": "Submit"},
            ],
            "input_summary": [
                {"id": "email", "name": "email", "type": "email", "aria_label": "", "aria_labelledby": "", "aria_describedby": "", "label_text": "Email"},
                {"id": "password", "name": "password", "type": "password", "aria_label": "", "aria_labelledby": "", "aria_describedby": "", "label_text": "Password"},
            ],
        }

    def test_dom_extraction_returns_structured_data(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig
        from unittest.mock import patch, MagicMock

        pages = [
            ("https://example.com/", self._build_mock_page_data("https://example.com/", "Home")),
        ]
        mock_pw, _, _, mock_page, mock_cdp = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=1))

        assert len(result.pages) == 1
        page = result.pages[0]
        assert "dom" in page.to_dict()
        dom = page.dom
        assert "interactive_elements" in dom
        assert "forms" in dom
        assert "landmarks" in dom
        assert "text_summary" in dom
        assert "input_summary" in dom

    def test_forms_extracted_without_password_values(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig
        from unittest.mock import patch, MagicMock

        pages = [
            ("https://example.com/", self._build_mock_page_data("https://example.com/", "Home")),
        ]
        mock_pw, _, _, mock_page, mock_cdp = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=1))

        page = result.pages[0]
        dom = page.dom
        # Check that forms are extracted
        assert len(dom["forms"]) == 1
        form = dom["forms"][0]
        assert form["action"] == "/api/login"
        assert form["method"] == "post"
        assert len(form["inputs"]) == 2
        # Check password field doesn't have value
        pwd_input = next(i for i in form["inputs"] if i["type"] == "password")
        assert "value" not in pwd_input or pwd_input.get("value") == ""
        assert pwd_input.get("value_presence") is False

    def test_interactive_elements_extracted(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig
        from unittest.mock import patch, MagicMock

        pages = [
            ("https://example.com/", self._build_mock_page_data("https://example.com/", "Home")),
        ]
        mock_pw, _, _, mock_page, mock_cdp = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=1))

        page = result.pages[0]
        dom = page.dom
        interactive = dom["interactive_elements"]
        assert len(interactive) >= 2  # email, password, button at minimum
        # Check button is present
        button = next((el for el in interactive if el["tag"] == "button"), None)
        assert button is not None
        assert button["text"] == "Submit"

    def test_landmarks_extracted(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig
        from unittest.mock import patch, MagicMock

        pages = [
            ("https://example.com/", self._build_mock_page_data("https://example.com/", "Home")),
        ]
        mock_pw, _, _, mock_page, mock_cdp = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=1))

        page = result.pages[0]
        dom = page.dom
        landmarks = dom["landmarks"]
        assert len(landmarks) >= 3
        roles = {lm["role"] for lm in landmarks}
        assert "banner" in roles or "navigation" in roles or "main" in roles or "contentinfo" in roles

    def test_text_summary_bounded(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig
        from unittest.mock import patch, MagicMock

        pages = [
            ("https://example.com/", self._build_mock_page_data("https://example.com/", "Home")),
        ]
        mock_pw, _, _, mock_page, mock_cdp = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=1))

        page = result.pages[0]
        dom = page.dom
        text_summary = dom["text_summary"]
        assert isinstance(text_summary, list)
        assert len(text_summary) <= 80  # MAX_TEXT_SUMMARY
        for item in text_summary:
            assert "type" in item
            assert "text" in item
            assert len(item["text"]) <= 120

    def test_accessibility_tree_cdp_source(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig
        from unittest.mock import patch, MagicMock

        pages = [
            ("https://example.com/", self._build_mock_page_data("https://example.com/", "Home")),
        ]
        mock_pw, _, _, mock_page, mock_cdp = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=1))

        page = result.pages[0]
        ax = page.accessibility_tree
        assert ax["source"] == "playwright"
        assert "root" in ax
        assert ax["root"]["role"] == "RootWebArea"
        assert "children" in ax["root"]

    def test_accessibility_tree_preserves_hierarchy(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig
        from unittest.mock import patch, MagicMock

        pages = [
            ("https://example.com/", self._build_mock_page_data("https://example.com/", "Home")),
        ]
        mock_pw, _, _, mock_page, mock_cdp = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=1))

        page = result.pages[0]
        ax = page.accessibility_tree
        root = ax["root"]
        assert "children" in root
        assert isinstance(root["children"], list)
        for child in root["children"]:
            assert "role" in child
            assert "name" in child

    def test_accessibility_attributes_extracted(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig
        from unittest.mock import patch, MagicMock

        pages = [
            ("https://example.com/", self._build_mock_page_data("https://example.com/", "Home")),
        ]
        mock_pw, _, _, mock_page, mock_cdp = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=1))

        page = result.pages[0]
        ax = page.accessibility_tree
        root = ax["root"]
        # Check that accessibility attributes are present
        assert "role" in root
        assert "name" in root
        for child in root.get("children", []):
            assert "role" in child
            assert "name" in child

    def test_ui_insights_derived(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig
        from unittest.mock import patch, MagicMock

        pages = [
            ("https://example.com/", self._build_mock_page_data("https://example.com/", "Home")),
        ]
        mock_pw, _, _, mock_page, mock_cdp = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=1))

        page = result.pages[0]
        insights = page.ui_insights
        assert "interactive_element_count" in insights
        assert "form_count" in insights
        assert "input_count" in insights
        assert "button_count" in insights
        assert "link_count" in insights
        assert "landmark_count" in insights
        assert "accessibility_node_count" in insights
        assert "has_login_controls" in insights
        assert "has_search_controls" in insights
        assert "has_submission_controls" in insights
        # With email + password + submit button, should detect login controls
        assert insights["has_login_controls"] is True

    def test_dom_fallback_when_cdp_unavailable(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig
        from unittest.mock import patch, MagicMock

        pages = [
            ("https://example.com/", self._build_mock_page_data("https://example.com/", "Home")),
        ]
        mock_pw, _, _, mock_page, mock_cdp = self._build_mock_playwright_stack(pages)
        # Make CDP fail
        mock_cdp.send.side_effect = Exception("CDP not available")

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=1))

        page = result.pages[0]
        ax = page.accessibility_tree
        assert ax["source"] == "dom_fallback"
        assert "root" in ax
        assert ax["root"]["role"] == "WebArea"

    def test_sensitive_values_never_serialized(self):
        from agentqe.crawler.application_crawler import ApplicationCrawler
        from agentqe.crawler.crawl_config import CrawlConfig
        from unittest.mock import patch, MagicMock

        page_data = self._build_mock_page_data("https://example.com/", "Home")
        pages = [("https://example.com/", page_data)]
        mock_pw, _, _, mock_page, mock_cdp = self._build_mock_playwright_stack(pages)

        with patch("agentqe.crawler.application_crawler.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__ = lambda s, *a: mock_pw
            mock_sp.return_value.__exit__ = MagicMock(return_value=False)
            with patch("agentqe.crawler.application_crawler.time") as mock_time:
                mock_time.time.return_value = 1.0
                mock_time.sleep = MagicMock()

                crawler = ApplicationCrawler()
                result = crawler.crawl("https://example.com/", CrawlConfig(max_pages=1))

        page = result.pages[0]
        dom = page.dom
        # Check that no password values are in the output
        for form in dom.get("forms", []):
            for inp in form.get("inputs", []):
                assert "value" not in inp or inp.get("value") == ""
                if inp["type"] == "password":
                    assert inp.get("value_presence") is False
        # Check interactive elements
        for el in dom.get("interactive_elements", []):
            if el.get("type") == "password":
                assert el.get("text") == ""
                assert el.get("value_presence") is False


class TestApplicationContextPhase15B:
    """Tests for ApplicationContext with Phase 1.5B fields."""

    def test_context_serializes_dom_and_accessibility(self):
        from agentqe.models.context import ApplicationContext
        ctx = ApplicationContext(
            url="https://example.com",
            pages=[{
                "url": "https://example.com",
                "depth": 0,
                "crawl_status": "success",
                "dom": {"interactive_elements": [], "forms": [], "landmarks": []},
                "accessibility_tree": {"source": "playwright", "root": {"role": "WebArea"}},
                "ui_insights": {"interactive_element_count": 0},
            }],
        )
        d = ctx.to_dict()
        assert d["pages"][0]["dom"]["interactive_elements"] == []
        assert d["pages"][0]["accessibility_tree"]["source"] == "playwright"
        assert d["pages"][0]["ui_insights"]["interactive_element_count"] == 0


class TestApplicationUnderstandingAgentPhase15B:
    """Tests for ApplicationUnderstandingAgent evidence tracking with Phase 1.5B."""

    @patch('agentqe.agents.application_understanding_agent._analyze_requirement')
    def test_evidence_tags_dom_inspection(self, mock_analyze_req):
        from agentqe.agents.application_understanding_agent import ApplicationUnderstandingAgent
        from agentqe.models.context import ApplicationUnderstandingInput

        mock_analyze_req.return_value = {"key_user_flows": [], "items": [], "risk_areas": []}
        crawl_result = {
            "pages": [{
                "url": "https://example.com",
                "depth": 0,
                "title": "Home",
                "page_type": "dashboard",
                "crawl_status": "success",
                "dom": {"interactive_elements": [], "forms": [], "landmarks": []},
                "accessibility_tree": {"source": "playwright", "root": {"role": "WebArea"}},
                "ui_insights": {},
                "forms": [],
                "detected_flows": [],
                "links": [],
                "nav_links": [],
            }],
            "navigation_graph": {"nodes": ["https://example.com"], "edges": []},
            "discovered_routes": [{"path": "/", "url": "https://example.com", "depth": 0, "page_type": "dashboard", "title": "Home", "status": 200, "crawl_status": "success", "evidence_type": "observed", "source": "application_crawl"}],
            "crawl_metadata": {"pages_analyzed": 1, "pages_failed": 0, "pages_discovered": 1, "duration_seconds": 1.0},
            "warnings": [],
        }

        with patch('agentqe.agents.application_understanding_agent.ApplicationUnderstandingAgent._crawl_application') as mock_crawl:
            mock_crawl.return_value = crawl_result

            agent = ApplicationUnderstandingAgent()
            result = agent.analyze(ApplicationUnderstandingInput(url="https://example.com"))

        assert "dom" in result.evidence
        assert "dom_inspection" in result.evidence["dom"]
        assert "accessibility_tree" in result.evidence
        assert "accessibility_tree" in result.evidence["accessibility_tree"]


# ─────────────────────────────────────────────────────────────────────────────
# Regression: existing Phase 1.5A tests still work
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase1Regression:
    def test_application_context_legacy_fields_intact(self):
        from agentqe.models.context import ApplicationContext
        ctx = ApplicationContext(
            url="https://example.com",
            app_name="Test",
            forms=[{"action": "/login"}],
            discovered_routes=["/login", "/home"],
            api_endpoints=["/api/users"],
            evidence={"app_name": ["application_crawl"]},
        )
        d = ctx.to_dict()
        assert d["forms"][0]["action"] == "/login"
        assert "/login" in d["discovered_routes"]
        assert "/api/users" in d["api_endpoints"]
        assert "application_crawl" in d["evidence"]["app_name"]

    def test_input_model_unchanged(self):
        from agentqe.models.context import ApplicationUnderstandingInput
        inp = ApplicationUnderstandingInput(
            url="https://example.com",
            requirement="Test req",
            repo_url="",
            module_name="Auth",
        )
        d = inp.to_dict()
        assert d["url"] == "https://example.com"
        assert d["module_name"] == "Auth"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
