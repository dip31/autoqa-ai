"""
Base class for passive security validators.

Each validator implements `check` which receives a verified target context
and returns a list of Finding objects (from interfaces).
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any

from agentqe.interfaces import Finding
from agentqe.security.models import SecurityRun, TargetAuthorization
from agentqe.security.evidence import EvidenceCollector
from agentqe.security.security_config import CONFIG


class ValidationContext:
    """Immutable context passed to every validator."""
    def __init__(
        self,
        run: SecurityRun,
        auth: TargetAuthorization,
        normalized_target: str,
        scope: Dict[str, Any],
        evidence_collector: EvidenceCollector,
    ):
        self.run = run
        self.auth = auth
        self.normalized_target = normalized_target
        self.scope = scope            # dict with scheme, host, port, path_prefix, allow_subdomains
        self.evidence = evidence_collector


class BaseValidator(ABC):
    """All passive validators inherit from this."""

    # Unique identifier, e.g. "https_validator"
    validator_id: str = ""
    # Human readable name
    name: str = ""
    # Short description
    description: str = ""

    def __init__(self):
        if not self.validator_id:
            raise ValueError("validator_id must be set")
        if not self.name:
            self.name = self.validator_id

    @abstractmethod
    def check(self, ctx: ValidationContext) -> List[Finding]:
        """Execute the validator and return findings (may be empty)."""
        pass

    # ------------------------------------------------------------------
    # Helper to run with timing / error handling – used by the runner
    # ------------------------------------------------------------------
    def execute(self, ctx: ValidationContext) -> List[Finding]:
        start = time.perf_counter()
        try:
            findings = self.check(ctx)
            elapsed = (time.perf_counter() - start) * 1000
            # attach duration meta to each finding
            for f in findings:
                f.metadata = f.metadata or {}
                f.metadata["validator_duration_ms"] = elapsed
            return findings
        except Exception as exc:   # pragma: no cover – defensive
            # Convert unexpected errors into a single synthetic finding
            err_finding = Finding(
                finding_id=f"err-{self.validator_id}",
                category="ValidatorError",
                severity="High",
                description=f"Validator {self.validator_id} raised an exception: {exc}",
                evidence={"error": str(exc)},
                source=self.validator_id,
                status="OPEN",
            )
            return [err_finding]


# ----------------------------------------------------------------------
# Registry helper – validators are registered in the capability registry
# ----------------------------------------------------------------------
from agentqe.interfaces import registry, ISecurityValidator


class ValidatorAdapter(ISecurityValidator):
    """Adapts a BaseValidator to the existing ISecurityValidator interface."""

    def __init__(self, validator: BaseValidator):
        self._validator = validator

    def validate(self, context, tests) -> List[Finding]:
        # The existing interface expects (ApplicationContext, List[CandidateTest]).
        # For passive security we ignore `tests` and build a ValidationContext.
        from agentqe.security.security_runner import build_validation_context

        vctx = build_validation_context(context, tests)
        return self._validator.execute(vctx)


def register_validator(validator: BaseValidator):
    """Register validator in the global capability registry."""
    registry.register(ISecurityValidator, ValidatorAdapter(validator))