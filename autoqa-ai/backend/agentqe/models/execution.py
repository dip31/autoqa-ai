from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ExecutionResult:
    test_id: str
    status: str
    duration_ms: float = 0.0
    error: Optional[str] = None
    coverage: float = 0.0
    healed: bool = False
    screenshot_path: Optional[str] = None
    security_findings: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "coverage": self.coverage,
            "healed": self.healed,
            "screenshot_path": self.screenshot_path,
            "security_findings": self.security_findings,
            "metadata": self.metadata,
        }