"""
Application Understanding Agent

Implements IApplicationUnderstanding interface.
Analyzes application from URL, requirements, and repository to produce ApplicationContext.
"""

import json
import re
from typing import Dict, Any, List, Optional
from playwright.sync_api import sync_playwright

from agentqe.interfaces import IApplicationUnderstanding, ApplicationContext, ApplicationUnderstandingInput
from agentqe.models.context import ApplicationContext as ModelApplicationContext, ApplicationUnderstandingInput as ModelInput
from agents.repo_intelligence_agent import RepoIntelligenceAgent
from agents.github_agent import GitHubAgent
from agents.autonomous_agent import _crawl_page, _analyze_requirement
import os
from dotenv import load_dotenv

load_dotenv()


class ApplicationUnderstandingAgent(IApplicationUnderstanding):
    """Application Understanding capability implementation."""

    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token
        self.repo_agent = RepoIntelligenceAgent(github_token) if github_token else None

    def analyze(self, input_data: ApplicationUnderstandingInput) -> ApplicationContext:
        """
        Analyze application and return structured ApplicationContext.

        Args:
            input_data: ApplicationUnderstandingInput containing url, repo_url, requirement, etc.

        Returns:
            ApplicationContext with structured application understanding
        """
        # Convert to model input if needed
        if isinstance(input_data, dict):
            input_data = ModelInput(**input_data)

        ctx = ModelApplicationContext(
            url=input_data.url or "",
            repo_url=input_data.repo_url or "",
            requirement=input_data.requirement or "",
            module_name=input_data.module_name or "",
        )

        # Track evidence sources
        evidence_sources = {}

        # Extract crawl_config from metadata if provided
        crawl_config_data = {}
        if isinstance(input_data, ModelInput) and input_data.metadata:
            crawl_config_data = input_data.metadata.get("crawl_config", {})

        # 1. Application crawling (if URL provided)
        if input_data.url:
            crawl_result = self._crawl_application(input_data.url, crawl_config_data)

            # Populate legacy single-page page_data from the first (depth-0) page
            start_page = next(
                (p for p in crawl_result.get("pages", []) if p.get("depth") == 0),
                {}
            )
            ctx.page_data = start_page
            ctx.app_name = start_page.get("title", "Unknown Application")
            ctx.app_type = "web"

            # Aggregate data across ALL successfully crawled pages
            all_forms = []
            all_flows = []
            seen_forms: set = set()

            for page in crawl_result.get("pages", []):
                if page.get("crawl_status") != "success":
                    continue
                for form in page.get("forms", []):
                    form_key = (form.get("action", ""), form.get("method", ""))
                    if form_key not in seen_forms:
                        seen_forms.add(form_key)
                        all_forms.append(form)
                for flow in page.get("detected_flows", []):
                    if flow not in all_flows:
                        all_flows.append(flow)

            ctx.forms = all_forms
            ctx.modules = all_flows

            # Rich discovered_routes from crawler
            ctx.discovered_routes = [
                r.get("path", r.get("url", ""))
                for r in crawl_result.get("discovered_routes", [])
            ]

            # API endpoints aggregated from all pages
            ctx.api_endpoints = self._extract_api_endpoints_from_pages(
                crawl_result.get("pages", [])
            )

            # Phase 1.5A fields
            ctx.pages = crawl_result.get("pages", [])
            ctx.navigation_graph = crawl_result.get("navigation_graph", {})
            ctx.crawl_metadata = crawl_result.get("crawl_metadata", {})

            self._add_evidence(evidence_sources, "application_crawl", [
                "title", "discovered_routes", "forms", "api_endpoints",
                "modules", "pages", "navigation_graph",
            ])

            # Phase 1.5B — DOM + Accessibility evidence tracking
            pages_with_dom = [p for p in crawl_result.get("pages", []) if p.get("dom")]
            pages_with_ax = [p for p in crawl_result.get("pages", []) if p.get("accessibility_tree")]
            if pages_with_dom:
                self._add_evidence(evidence_sources, "dom_inspection", ["dom"])
            if pages_with_ax:
                self._add_evidence(evidence_sources, "accessibility_tree", ["accessibility_tree"])

            # Phase 1.5C — Network/API evidence tracking
            pages_with_network = [p for p in crawl_result.get("pages", []) if p.get("network_activity")]
            if pages_with_network:
                self._add_evidence(evidence_sources, "network_observation", ["network_activity"])
            
            # Use observed API endpoints from network activity (Phase 1.5C)
            observed_api_endpoints = crawl_result.get("api_endpoints", [])
            if observed_api_endpoints:
                # Convert to simple string list for backward compatibility with api_endpoints field
                ctx.api_endpoints = [
                    f"{ep.get('method', 'GET')} {ep.get('path', ep.get('url', ''))}"
                    for ep in observed_api_endpoints
                ]
                self._add_evidence(evidence_sources, "network_observation", ["api_endpoints"])
            else:
                # Fallback to legacy extraction if no network observations
                ctx.api_endpoints = self._extract_api_endpoints_from_pages(
                    crawl_result.get("pages", [])
                )

        # 2. Repository analysis (if repo URL provided)
        if input_data.repo_url and self.repo_agent:
            repo_data = self._analyze_repository(input_data.repo_url)
            ctx.repository_data = repo_data
            ctx.technology_stack = repo_data.get("analysis", {}).get("tech_stack", {})
            ctx.framework = repo_data.get("analysis", {}).get("tech_stack", {}).get("backend", "")
            ctx.source_files = repo_data.get("analysis", {}).get("key_files", [])
            self._add_evidence(evidence_sources, "repository_analysis", [
                "technology_stack", "framework", "source_files"
            ])

        # 3. Requirement analysis (if requirements provided)
        if input_data.requirement:
            req_analysis = self._analyze_requirements(input_data.requirement, ctx.page_data)
            ctx.requirements = req_analysis.get("requirements", [])
            ctx.user_flows = req_analysis.get("user_flows", [])
            ctx.testable_areas = req_analysis.get("testable_areas", [])
            ctx.risk_areas = req_analysis.get("risk_areas", [])
            self._add_evidence(evidence_sources, "requirement_analysis", [
                "requirements", "user_flows", "testable_areas", "risk_areas"
            ])

        # 4. Combine and infer additional information
        self._infer_additional_context(ctx)

        # Set evidence tracking
        ctx.evidence = evidence_sources

        return ctx

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _crawl_application(self, url: str, crawl_config_data: dict = None) -> Dict[str, Any]:
        """
        Crawl the application URL using the bounded multi-page ApplicationCrawler.
        Falls back to the legacy single-page _crawl_page() if the crawler fails.
        """
        try:
            from agentqe.crawler import ApplicationCrawler, CrawlConfig

            config = CrawlConfig.from_dict(crawl_config_data or {})
            crawler = ApplicationCrawler()
            result = crawler.crawl(url, config)
            return result.to_dict()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Multi-page crawler failed ({e}), falling back to single-page crawl"
            )
            try:
                page_data = _crawl_page(url)
                return {
                    "pages": [{
                        **page_data,
                        "depth": 0,
                        "crawl_status": "success",
                        "page_type": "unknown",
                        "page_type_confidence": "inferred",
                        "links": [],
                        "url": page_data.get("url", url),
                        "status": 200,
                    }],
                    "navigation_graph": {"nodes": [url], "edges": []},
                    "discovered_routes": [
                        {
                            "path": lnk.get("href", ""),
                            "url": lnk.get("href", ""),
                            "depth": 1,
                            "page_type": "unknown",
                            "title": lnk.get("text", ""),
                            "status": None,
                            "crawl_status": "not_crawled",
                            "evidence_type": "observed",
                            "source": "application_crawl",
                        }
                        for lnk in page_data.get("nav_links", [])
                    ],
                    "crawl_metadata": {
                        "start_url": url,
                        "pages_discovered": 1,
                        "pages_analyzed": 1,
                        "pages_failed": 0,
                        "max_pages": 1,
                        "max_depth": 0,
                        "duration_seconds": 0,
                        "warnings": [f"Used legacy fallback: {str(e)[:100]}"],
                    },
                    "warnings": [f"Multi-page crawler unavailable: {str(e)[:100]}"],
                }
            except Exception as fallback_err:
                return {
                    "pages": [],
                    "navigation_graph": {},
                    "discovered_routes": [],
                    "crawl_metadata": {},
                    "warnings": [str(fallback_err)],
                }

    def _analyze_repository(self, repo_url: str) -> Dict[str, Any]:
        """Analyze repository for technology stack and structure."""
        try:
            return self.repo_agent.analyze(repo_url)
        except Exception as e:
            return {"error": str(e), "analysis": {}}

    def _analyze_requirements(self, requirement: str, page_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze requirements and combine with crawled data."""
        try:
            scope = _analyze_requirement(requirement, "", page_data)
            return {
                "requirements": [{"description": requirement, "source": "user_input"}],
                "user_flows": scope.get("key_user_flows", []),
                "testable_areas": scope.get("items", []),
                "risk_areas": [
                    {"area": r, "reason": "Identified from requirements", "source": "requirement_analysis"}
                    for r in scope.get("risk_areas", [])
                ],
            }
        except Exception:
            return {
                "requirements": [{"description": requirement, "source": "user_input"}],
                "user_flows": [],
                "testable_areas": [],
                "risk_areas": [],
            }

    def _extract_api_endpoints(self, page_data: Dict[str, Any]) -> List[str]:
        """Extract potential API endpoints from a single page's data (legacy helper)."""
        endpoints = []
        for link in page_data.get("links", []):
            href = link.get("href", "")
            if "/api/" in href or "/graphql" in href or "/rest/" in href:
                endpoints.append(href)
        for form in page_data.get("forms", []):
            action = form.get("action", "")
            if "/api/" in action:
                endpoints.append(action)
        return list(set(endpoints))

    def _extract_api_endpoints_from_pages(self, pages: List[Dict[str, Any]]) -> List[str]:
        """Extract API endpoints across all crawled pages."""
        endpoints: set = set()
        for page in pages:
            for link in page.get("links", []) + page.get("nav_links", []):
                href = link.get("target", link.get("href", ""))
                if "/api/" in href or "/graphql" in href or "/rest/" in href:
                    endpoints.add(href)
            for form in page.get("forms", []):
                action = form.get("action", "")
                if "/api/" in action:
                    endpoints.add(action)
        return list(endpoints)

    def _infer_additional_context(self, ctx: ModelApplicationContext):
        """Infer additional context from combined data."""
        if not ctx.technology_stack and ctx.page_data:
            ctx.technology_stack = self._infer_tech_from_page(ctx.page_data)
            self._add_evidence(ctx.evidence, "inference", ["technology_stack"])

        if not ctx.app_type:
            if ctx.page_data or ctx.pages:
                ctx.app_type = "web"
            elif ctx.repo_url:
                ctx.app_type = "code"
            else:
                ctx.app_type = "unknown"

        if ctx.modules and not ctx.features:
            ctx.features = [{"name": m, "source": "crawl"} for m in ctx.modules]

        for area in ctx.testable_areas:
            if isinstance(area, str):
                idx = ctx.testable_areas.index(area)
                ctx.testable_areas[idx] = {"area": area, "source": "requirement_analysis"}

    def _infer_tech_from_page(self, page_data: Dict[str, Any]) -> Dict[str, Any]:
        """Infer technology stack from page data."""
        tech = {"backend": "Unknown", "frontend": "Unknown", "database": "Unknown", "tools": []}

        main_text = page_data.get("main_text", "").lower()
        title = page_data.get("title", "").lower()

        if "react" in main_text or "react" in title or "__react" in main_text:
            tech["frontend"] = "React"
        elif "vue" in main_text or "vue" in title:
            tech["frontend"] = "Vue.js"
        elif "angular" in main_text or "ng-" in main_text:
            tech["frontend"] = "Angular"
        elif "next.js" in main_text or "__next" in main_text:
            tech["frontend"] = "Next.js"

        if "django" in main_text:
            tech["backend"] = "Django"
        elif "flask" in main_text:
            tech["backend"] = "Flask"
        elif "express" in main_text:
            tech["backend"] = "Express.js"
        elif "spring" in main_text:
            tech["backend"] = "Spring Boot"

        return tech

    def _add_evidence(self, evidence: Dict[str, List[str]], source: str, fields: List[str]):
        """Track which fields came from which source."""
        for field in fields:
            if field not in evidence:
                evidence[field] = []
            if source not in evidence[field]:
                evidence[field].append(source)