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
    
    # Phase 3 Fields
    preconditions: List[str] = field(default_factory=list)
    requirement_refs: List[str] = field(default_factory=list)
    page_refs: List[str] = field(default_factory=list)
    control_refs: List[str] = field(default_factory=list)
    form_refs: List[str] = field(default_factory=list)
    api_refs: List[str] = field(default_factory=list)
    flow_refs: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    
    # Phase 4 Fields
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
            "preconditions": self.preconditions,
            "requirement_refs": self.requirement_refs,
            "page_refs": self.page_refs,
            "control_refs": self.control_refs,
            "form_refs": self.form_refs,
            "api_refs": self.api_refs,
            "flow_refs": self.flow_refs,
            "evidence_refs": self.evidence_refs,
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