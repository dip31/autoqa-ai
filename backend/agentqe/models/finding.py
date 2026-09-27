from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Finding:
    finding_id: str
    category: str
    severity: str
    description: str
    evidence: Dict = field(default_factory=dict)
    source: str = ""
    status: str = "OPEN"

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "evidence": self.evidence,
            "source": self.source,
            "status": self.status,
        }