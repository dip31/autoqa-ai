from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ApplicationContext:
    url: str = ""
    repo_url: str = ""
    requirement: str = ""
    module_name: str = ""

    # Application identity
    app_name: str = ""
    app_type: str = ""  # e.g., "web", "api", "mobile", "desktop"
    technology_stack: Dict[str, Any] = field(default_factory=dict)
    framework: str = ""

    # Functional areas / modules
    modules: List[str] = field(default_factory=list)
    features: List[Dict[str, Any]] = field(default_factory=list)

    # Requirements
    requirements: List[Dict[str, Any]] = field(default_factory=list)
    user_flows: List[Dict[str, Any]] = field(default_factory=list)

    # Testable areas
    testable_areas: List[Dict[str, Any]] = field(default_factory=list)
    api_endpoints: List[str] = field(default_factory=list)
    discovered_routes: List[str] = field(default_factory=list)
    forms: List[Dict[str, Any]] = field(default_factory=list)

    # Risk areas
    risk_areas: List[Dict[str, Any]] = field(default_factory=list)

    # Repository information
    repository_data: Dict[str, Any] = field(default_factory=dict)
    source_files: List[str] = field(default_factory=list)

    # Raw data from crawls/scans
    page_data: Dict[str, Any] = field(default_factory=dict)

    # Phase 1.5A — Multi-page crawl results
    pages: List[Dict[str, Any]] = field(default_factory=list)  # per-page structured data
    navigation_graph: Dict[str, Any] = field(default_factory=dict)  # nodes + edges
    crawl_metadata: Dict[str, Any] = field(default_factory=dict)  # summary stats

    # Evidence tracking
    evidence: Dict[str, List[str]] = field(default_factory=dict)  # field -> list of sources

    # Phase 1.5F — Cross-modal evidence fusion result.
    # Serialized UnifiedApplicationModel (see agentqe.fusion.schemas). It
    # *references* the evidence above via stable evidence_refs and never
    # replaces it. ``None`` when fusion did not run.
    unified_model: Optional[Dict[str, Any]] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "repo_url": self.repo_url,
            "requirement": self.requirement,
            "module_name": self.module_name,
            "app_name": self.app_name,
            "app_type": self.app_type,
            "technology_stack": self.technology_stack,
            "framework": self.framework,
            "modules": self.modules,
            "features": self.features,
            "requirements": self.requirements,
            "user_flows": self.user_flows,
            "testable_areas": self.testable_areas,
            "api_endpoints": self.api_endpoints,
            "discovered_routes": self.discovered_routes,
            "forms": self.forms,
            "risk_areas": self.risk_areas,
            "repository_data": self.repository_data,
            "source_files": self.source_files,
            "page_data": self.page_data,
            "pages": self.pages,
            "navigation_graph": self.navigation_graph,
            "crawl_metadata": self.crawl_metadata,
            "evidence": self.evidence,
            "unified_model": self.unified_model,
            "metadata": self.metadata,
        }


@dataclass
class ApplicationUnderstandingInput:
    url: str = ""
    repo_url: str = ""
    requirement: str = ""
    module_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "repo_url": self.repo_url,
            "requirement": self.requirement,
            "module_name": self.module_name,
            "metadata": self.metadata,
        }