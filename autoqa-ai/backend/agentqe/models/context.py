from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ApplicationContext:

    url: str = ""

    repo_url: str = ""

    requirement: str = ""

    module_name: str = ""

    page_data: Dict[str, Any] = field(
        default_factory=dict
    )

    repository_data: Dict[str, Any] = field(
        default_factory=dict
    )

    source_files: List[str] = field(
        default_factory=list
    )

    api_endpoints: List[str] = field(
        default_factory=list
    )

    existing_tests: List[str] = field(
        default_factory=list
    )

    technology_stack: Dict[str, Any] = field(
        default_factory=dict
    )