from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TestCase:
    test_id: str
    scenario: str
    case_type: str
    expected_result: str = ""
    priority: str = "MEDIUM"

    perspective: str = "USER"

    source: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)

    features: List[float] = field(default_factory=list)

    transformer_score: float = 0.0
    selected: bool = False

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "test_id": self.test_id,
            "scenario": self.scenario,
            "case_type": self.case_type,
            "expected_result": self.expected_result,
            "priority": self.priority,
            "perspective": self.perspective,
            "source": self.source,
            "steps": self.steps,
            "features": self.features,
            "transformer_score": self.transformer_score,
            "selected": self.selected,
            "metadata": self.metadata,
        }