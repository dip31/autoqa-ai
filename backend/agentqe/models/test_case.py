from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CandidateTest:
    test_id: str
    title: str
    description: str = ""
    perspective: str = "USER"
    test_type: str = "UI"
    target: str = ""
    priority: str = "Medium"
    category: str = ""
    steps: List = field(default_factory=list)
    input_data: str = ""
    expected_result: str = ""
    automatable: bool = True
    blocked_reason: Optional[str] = None
    source_agent: str = ""
    evidence: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)
    risk_score: float = 0.5
    historical_pass_rate: float = 0.0
    historical_failure_rate: float = 0.0
    execution_cost: float = 3.0
    change_impact: float = 0.5
    coverage_gain: float = 0.5
    transformer_score: float = 0.0
    final_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "title": self.title,
            "description": self.description,
            "perspective": self.perspective,
            "test_type": self.test_type,
            "target": self.target,
            "priority": self.priority,
            "category": self.category,
            "steps": self.steps,
            "input_data": self.input_data,
            "expected_result": self.expected_result,
            "automatable": self.automatable,
            "blocked_reason": self.blocked_reason,
            "source_agent": self.source_agent,
            "evidence": self.evidence,
            "metadata": self.metadata,
            "risk_score": self.risk_score,
            "historical_pass_rate": self.historical_pass_rate,
            "historical_failure_rate": self.historical_failure_rate,
            "execution_cost": self.execution_cost,
            "change_impact": self.change_impact,
            "coverage_gain": self.coverage_gain,
            "transformer_score": self.transformer_score,
            "final_score": self.final_score,
        }


# Legacy alias for backward compatibility
TestCase = CandidateTest