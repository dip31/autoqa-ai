from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Risk:
    risk_id: str
    area: str
    severity: str
    score: float
    reason: str
    evidence: List[str] = field(default_factory=list)
    affected_tests: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "risk_id": self.risk_id,
            "area": self.area,
            "severity": self.severity,
            "score": self.score,
            "reason": self.reason,
            "evidence": self.evidence,
            "affected_tests": self.affected_tests,
        }