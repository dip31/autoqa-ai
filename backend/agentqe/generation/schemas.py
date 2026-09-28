from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class GenerationContext:
    requirement: str
    pages: List[Dict[str, Any]]
    controls: List[Dict[str, Any]]
    forms: List[Dict[str, Any]]
    apis: List[Dict[str, Any]]
    flows: List[Dict[str, Any]]
    modules: List[Dict[str, Any]]
    repository_context: Dict[str, Any]
    retrieved_documents: List[Dict[str, Any]]
    evidence_refs: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement": self.requirement,
            "pages": self.pages,
            "controls": self.controls,
            "forms": self.forms,
            "apis": self.apis,
            "flows": self.flows,
            "modules": self.modules,
            "repository_context": self.repository_context,
            "retrieved_documents": self.retrieved_documents,
            "evidence_refs": self.evidence_refs
        }
