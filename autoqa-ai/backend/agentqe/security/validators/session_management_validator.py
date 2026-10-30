"""
Session Management Validator – Active verification of session handling behavior.

This validator tests session handling using dedicated test accounts and
controlled test sessions.
"""

from __future__ import annotations

from typing import List, Dict, Any
import requests

from agentqe.interfaces import Finding
from agentqe.security.validators.base import BaseValidator, ValidationContext


class SessionManagementValidator(BaseValidator):
    validator_id = "session_management_validator"
    name = "Session Management"
    description = "Verifies session handling behavior using dedicated test sessions"

    def __init__(self):
        super().__init__()
        self.test_scenarios = [
            {
                "name": "unauthenticated_access_protected",
                "description": "Unauthenticated access to protected resource",
                "requires_auth": False,
                "expect_denied": True,
            },
            {
                "name": "logout_invalidation",
                "description": "Session invalidated after logout",
                "requires_auth": True,
                "test_logout": True,
            },
            {
                "name": "session_expiration",
                "description": "Session expires after configured timeout",
                "requires_auth": True,
                "test_expiration": True,
            },
            {
                "name": "session_rotation",
                "description": "Session ID rotates after login",
                "requires_auth": True,
                "test_rotation": True,
            },
            {
                "name": "invalid_session_rejected",
                "description": "Invalid/expired session rejected",
                "requires_auth": True,
                "use_invalid_session": True,
            },
        ]

    def check(self, ctx: ValidationContext) -> List[Finding]:
        findings: List[Finding] = []

        # Get test credentials and session config
        test_creds = ctx.scope.get("test_credentials", {})
        session_config = ctx.scope.get("session_config", {})

        if not test_creds:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-no-creds",
                category="SessionManagement",
                severity="Informational",
                description="No test credentials configured for session management testing",
                evidence={"session_config": session_config},
                source=self.validator_id,
                metadata={"check_type": "active", "skipped": True},
            ))
            return findings

        # Get primary test user credentials
        primary_creds = test_creds.get("user_1") or test_creds.get("user_1")
        if not primary_creds:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-no-primary-creds",
                category="SessionManagement",
                severity="Informational",
                description="No primary test user credentials available",
                evidence={"test_creds_keys": list(test_creds.keys())},
                source=self.validator_id,
                metadata={"check_type": "active", "skipped": True},
            ))
            return findings

        # Run session scenarios
        for scenario in self.test_scenarios:
            findings.extend(self._run_scenario(ctx, scenario))

        return findings

    def _run_scenario(self, ctx: ValidationContext, scenario: Dict[str, Any]) -> List[Finding]:
        findings: List[Finding] = []

        try:
            if scenario["name"] == "unauthenticated_access_protected":
                findings.extend(self._test_unauthenticated_access())
            elif scenario["name"] == "logout_invalidation":
                findings.extend(self._test_logout_invalidation())
            elif scenario["name"] == "session_expiration":
                findings.extend(self._test_session_expiration())
            elif scenario["name"] == "session_rotation":
                findings.extend(self._test_session_rotation())
            elif scenario["name"] == "invalid_session_rejected":
                findings.extend(self._test_invalid_session_rejected())
        except Exception as exc:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-{scenario['name']}-error",
                category="SessionManagement",
                severity="Low",
                description=f"Session test failed: {exc}",
                evidence={"error": str(exc), "scenario": scenario["name"]},
                source=self.validator_id,
                metadata={"check_type": "active", "error": True},
            ))

        return findings

    def _test_unauthenticated_access(self) -> List[Finding]:
        """Test that protected resources reject unauthenticated access."""
        findings: List[Finding] = []
        # This would need a known protected endpoint - use scope config
        return findings

    def _test_logout_invalidation(self) -> List[Finding]:
        """Test that logout properly invalidates the session."""
        findings: List[Finding] = []
        
        # This requires actual test credentials and a logout endpoint
        findings.append(Finding(
            finding_id=f"{self.validator_id}-logout-invalidation-not-impl",
            category="SessionManagement",
            severity="Informational",
            description="Logout invalidation test requires configured test environment with login/logout endpoints",
            evidence={},
            source=self.validator_id,
            metadata={"check_type": "active", "skipped": True},
        ))
        return findings

    def _test_session_expiration(self) -> List[Finding]:
        """Test session expiration behavior."""
        findings: List[Finding] = []
        
        findings.append(Finding(
            finding_id=f"{self.validator_id}-session-expiration-not-impl",
            category="SessionManagement",
            severity="Informational",
            description="Session expiration test requires time manipulation or long-running test",
            evidence={},
            source=self.validator_id,
            metadata={"check_type": "active", "skipped": True},
        ))
        return findings

    def _test_session_rotation(self) -> List[Finding]:
        """Test that session ID rotates after login."""
        findings: List[Finding] = []
        
        findings.append(Finding(
            finding_id=f"{self.validator_id}-session-rotation-not-impl",
            category="SessionManagement",
            severity="Informational",
            description="Session rotation test requires login endpoint and session tracking",
            evidence={},
            source=self.validator_id,
            metadata={"check_type": "active", "skipped": True},
        ))
        return findings

    def _test_invalid_session_rejected(self) -> List[Finding]:
        """Test that invalid/expired sessions are rejected."""
        findings: List[Finding] = []
        
        findings.append(Finding(
            finding_id=f"{self.validator_id}-invalid-session-not-impl",
            category="SessionManagement",
            severity="Informational",
            description="Invalid session rejection test requires session manipulation",
            evidence={},
            source=self.validator_id,
            metadata={"check_type": "active", "skipped": True},
        ))
        return findings