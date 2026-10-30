"""
Finding Verification Engine – evaluates whether evidence supports security claims.

This module provides centralized, deterministic verification rules for all
security validator categories. It transforms raw validator observations into
verified findings with calibrated confidence and severity.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from agentqe.interfaces import Finding
from agentqe.security.models import severity_rank
from agentqe.security.models import SecurityFinding

logger = logging.getLogger(__name__)


class VerificationState(Enum):
    """Verification states for findings."""
    CANDIDATE = "candidate"           # Observed but not yet verified
    VERIFIED = "verified"             # Evidence supports the claim
    INCONCLUSIVE = "inconclusive"     # Insufficient/contradictory evidence
    REJECTED = "rejected"             # Evidence contradicts the claim
    NEEDS_MANUAL_REVIEW = "needs_manual_review"  # Requires human assessment


class ConfidenceLevel(Enum):
    """Confidence levels for findings."""
    VERY_LOW = 0.1
    LOW = 0.3
    MEDIUM = 0.5
    HIGH = 0.7
    VERY_HIGH = 0.9


@dataclass(frozen=True)
class VerificationResult:
    """Result of a verification evaluation."""
    state: VerificationState
    confidence: float
    reason: str
    evidence_summary: Dict[str, Any] = field(default_factory=dict)
    verification_rules_applied: List[str] = field(default_factory=list)
    suggested_severity: Optional[str] = None
    suggested_confidence: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class VerificationRule:
    """Base class for verification rules."""
    
    def __init__(self, rule_id: str, name: str, description: str):
        self.rule_id = rule_id
        self.name = name
        self.description = description
    
    def evaluate(self, finding: Finding, evidence: Dict[str, Any], 
                 context: Dict[str, Any]) -> VerificationResult:
        """Evaluate a finding against this rule."""
        raise NotImplementedError


class InputValidationVerificationRule(VerificationRule):
    """Verification rules for input validation findings."""
    
    def __init__(self):
        super().__init__(
            "input_validation",
            "Input Validation Verification",
            "Validates input validation behavior findings"
        )
    
    def evaluate(self, finding: Finding, evidence: Dict[str, Any], 
                 context: Dict[str, Any]) -> VerificationResult:
        rules_applied = ["input_validation"]
        evidence_summary = {}
        confidence = 0.5
        state = VerificationState.INCONCLUSIVE
        reason = "Insufficient evidence to verify input validation behavior"
        
        issues = evidence.get("issues", [])
        test_case = evidence.get("test_case", {})
        test_name = test_case.get("name", "unknown")
        
        # Check for server errors (5xx) - indicates poor input handling
        if any(i.get("type") == "server_error" for i in issues):
            state = VerificationState.VERIFIED
            confidence = 0.8
            reason = f"Server error ({evidence.get('status', '5xx')}) observed for {test_case.get('description', 'input test')}"
            evidence_summary = {"server_error": True, "status": evidence.get("status")}
        
        # Check for input reflection without clear rejection
        elif any(i.get("type") == "input_reflection" for i in issues):
            state = VerificationState.VERIFIED
            confidence = 0.7
            reason = f"Input reflected without clear validation rejection for {test_case.get('description', 'input test')}"
            evidence_summary = {"input_reflection": True, "payload": evidence.get("payload", "")[:100]}
        
        # Check for SQL errors (potential SQL injection)
        elif any(i.get("type") == "sql_error_exposure" for i in issues):
            state = VerificationState.VERIFIED
            confidence = 0.9
            reason = f"SQL error exposed for {test_case.get('description', 'input test')} - potential SQL injection vector"
            evidence_summary = {"sql_error": True, "content_preview": evidence.get("content_preview", "")[:200]}
        
        # Check for stack traces
        elif any(i.get("type") == "stack_trace_exposure" for i in issues):
            state = VerificationState.VERIFIED
            confidence = 0.8
            reason = f"Stack trace exposed in error response for {test_case.get('description', 'input test')}"
            evidence_summary = {"stack_trace": True, "content_preview": evidence.get("content_preview", "")[:200]}
        
        # Check for successful validation (expected behavior)
        elif any(i.get("type") == "validation_success" for i in issues):
            state = VerificationState.REJECTED
            confidence = 0.8
            reason = f"Input properly rejected with validation error for {test_case.get('description', 'input test')}"
            evidence_summary = {"validation_success": True}
        
        # Check for potential missing validation
        elif any(i.get("type") == "potential_missing_validation" for i in issues):
            state = VerificationState.CANDIDATE
            confidence = 0.4
            reason = f"Input accepted without clear validation for {test_case.get('description', 'input test')} - needs manual review"
            evidence_summary = {"potential_missing_validation": True}
        
        # TLS/SSL errors
        elif any(i.get("type") in ["tls_error", "tls-error"] for i in issues):
            state = VerificationState.VERIFIED
            confidence = 0.8
            reason = f"TLS handshake failed: {evidence.get('error', 'unknown error')}"
            evidence_summary = {"tls_error": True, "error": evidence.get("error")}
        
        # Unreachable endpoint
        elif any(i.get("type") == "unreachable" for i in issues):
            state = VerificationState.INCONCLUSIVE
            confidence = 0.3
            reason = f"Endpoint unreachable: {evidence.get('error', 'unknown')}"
            evidence_summary = {"unreachable": True, "error": evidence.get("error")}
        
        # HTTP allowed when policy requires HTTPS
        elif any(i.get("type") == "http_allowed" for i in issues):
            state = VerificationState.VERIFIED
            confidence = 0.9
            reason = "HTTP accessible while policy requires HTTPS"
            evidence_summary = {"http_allowed": True, "scheme": "http"}
        
        # HTTPS downgrade via redirect
        elif any(i.get("type") == "https_downgrade" for i in issues):
            state = VerificationState.VERIFIED
            confidence = 0.9
            reason = "HTTPS request downgraded to HTTP via redirect"
            evidence_summary = {"downgrade": True, "final_url": evidence.get("final_url")}
        
        return VerificationResult(
            state=state,
            confidence=confidence,
            reason=reason,
            evidence_summary=evidence_summary,
            verification_rules_applied=rules_applied,
            metadata={"validator": "input_validation", "test_case": test_name}
        )


class HeaderBehaviorVerificationRule(VerificationRule):
    """Verification rules for security header behavior findings."""
    
    def __init__(self):
        super().__init__(
            "header_behavior",
            "Security Header Behavior Verification",
            "Verifies security header behavior findings"
        )
    
    def evaluate(self, finding: Finding, evidence: Dict[str, Any], 
                 context: Dict[str, Any]) -> VerificationResult:
        rules_applied = ["header_behavior"]
        confidence = 0.6
        state = VerificationState.INCONCLUSIVE
        reason = "Header behavior observation recorded"
        evidence_summary = {"url": evidence.get("url", "")}
        
        # Missing headers are observed but severity depends on context
        if finding.category == "SecurityHeaders":
            if "missing" in finding.finding_id.lower() or "missing" in finding.description.lower():
                state = VerificationState.VERIFIED
                confidence = 0.7
                reason = f"Header confirmed missing: {finding.description}"
                evidence_summary = {"header": evidence.get("header"), "url": evidence.get("url")}
            elif "weak" in finding.finding_id.lower() or "weak" in finding.description.lower():
                state = VerificationState.VERIFIED
                confidence = 0.6
                reason = f"Header present but weak: {finding.description}"
                evidence_summary = {"header": evidence.get("header"), "value": evidence.get("value")[:200]}
        
        # Cookie security findings
        elif finding.category == "CookieSecurity":
            if "secure" in finding.description.lower() and "missing" in finding.description.lower():
                state = VerificationState.VERIFIED
                confidence = 0.8
                reason = "Cookie missing Secure flag - transmitted over HTTP"
                evidence_summary = {"cookie": evidence.get("cookie")[:200], "url": evidence.get("url")}
            elif "httponly" in finding.description.lower() and "missing" in finding.description.lower():
                state = VerificationState.VERIFIED
                confidence = 0.8
                reason = "Cookie missing HttpOnly flag - accessible to JavaScript"
                evidence_summary = {"cookie": evidence.get("cookie")[:200], "url": evidence.get("url")}
            elif "samesite" in finding.description.lower():
                state = VerificationState.VERIFIED
                confidence = 0.7
                reason = f"Cookie SameSite issue: {finding.description}"
                evidence_summary = {"cookie": evidence.get("cookie")[:200], "url": evidence.get("url")}
        
        # HTTPS enforcement
        elif finding.validator_id == "https_validator":
            if "downgrade" in finding.finding_id.lower():
                state = VerificationState.VERIFIED
                confidence = 0.9
                reason = "HTTPS request downgraded to HTTP via redirect"
                evidence_summary = {"downgrade": True, "final_url": evidence.get("final_url")}
            elif "tls_error" in finding.finding_id.lower():
                state = VerificationState.VERIFIED
                confidence = 0.9
                reason = f"TLS handshake failed: {evidence.get('error', 'unknown')}"
                evidence_summary = {"tls_error": True, "error": evidence.get("error")}
            elif "unreachable" in finding.finding_id.lower():
                state = VerificationState.INCONCLUSIVE
                confidence = 0.3
                reason = f"HTTPS endpoint unreachable: {evidence.get('error', 'unknown')}"
                evidence_summary = {"unreachable": True}
        
        return VerificationResult(
            state=state,
            confidence=confidence,
            reason=reason,
            evidence_summary=evidence_summary,
            verification_rules_applied=rules_applied,
            metadata={"validator": "header_behavior"}
        )


class CookieSecurityVerificationRule(VerificationRule):
    """Verification rules for cookie security findings."""
    
    def __init__(self):
        super().__init__(
            "cookie_security",
            "Cookie Security Verification",
            "Verifies cookie security attribute findings"
        )
    
    def evaluate(self, finding: Finding, evidence: Dict[str, Any], 
                 context: Dict[str, Any]) -> VerificationResult:
        # Handled by HeaderBehaviorVerificationRule
        return VerificationResult(
            state=VerificationState.INCONCLUSIVE,
            confidence=0.5,
            reason="Cookie security findings verified by HeaderBehaviorVerificationRule",
            verification_rules_applied=["cookie_security"],
            metadata={"validator": "cookie_security"}
        )


class InformationDisclosureVerificationRule(VerificationRule):
    """Verification rules for information disclosure findings."""
    
    def __init__(self):
        super().__init__(
            "information_disclosure",
            "Information Disclosure Verification",
            "Verifies information disclosure findings"
        )
    
    def evaluate(self, finding: Finding, evidence: Dict[str, Any], 
                 context: Dict[str, Any]) -> VerificationResult:
        if finding.category != "InformationDisclosure":
            return VerificationResult(
                state=VerificationState.INCONCLUSIVE,
                confidence=0.5,
                reason="Not an information disclosure finding",
                verification_rules_applied=["information_disclosure"],
            )
        
        # Server/framework version headers
        if "header" in finding.evidence and finding.evidence["header"].lower() in [
            "server", "x-powered-by", "x-aspnet-version", "x-generator"
        ]:
            return VerificationResult(
                state=VerificationState.VERIFIED,
                confidence=0.7,
                reason=f"Information disclosure: {finding.description}",
                evidence_summary={"header": finding.evidence.get("header"), 
                                "value": finding.evidence.get("value", "")[:200]},
                verification_rules_applied=["information_disclosure"],
                metadata={"validator": "information_disclosure"}
            )
        
        # Source map references
        if "sourceMappingURL" in finding.evidence.get("match", ""):
            return VerificationResult(
                state=VerificationState.VERIFIED,
                confidence=0.6,
                reason="JavaScript source map reference exposed in production",
                evidence_summary={"match": finding.evidence.get("match", "")[:200]},
                verification_rules_applied=["information_disclosure"],
                metadata={"validator": "information_disclosure"}
            )
        
        # HTML comments
        if "comment" in finding.finding_id.lower() or "comment" in finding.description.lower():
            return VerificationResult(
                state=VerificationState.CANDIDATE,
                confidence=0.4,
                reason="HTML comment may leak internal paths - requires manual review",
                evidence_summary={"match": finding.evidence.get("match", "")[:200]},
                verification_rules_applied=["information_disclosure"],
                metadata={"validator": "information_disclosure"}
            )
        
        return VerificationResult(
            state=VerificationState.INCONCLUSIVE,
            confidence=0.5,
            reason="Information disclosure observation recorded",
            verification_rules_applied=["information_disclosure"],
            metadata={"validator": "information_disclosure"}
        )


class RedirectVerificationRule(VerificationRule):
    """Verification rules for redirect findings."""
    
    def __init__(self):
        super().__init__(
            "redirect_analysis",
            "Redirect Analysis Verification",
            "Verifies redirect chain findings"
        )
    
    def evaluate(self, finding: Finding, evidence: Dict[str, Any], 
                 context: Dict[str, Any]) -> VerificationResult:
        if finding.category != "Redirect" and finding.category != "ScopeViolation":
            return VerificationResult(
                state=VerificationState.INCONCLUSIVE,
                confidence=0.5,
                reason="Not a redirect analysis finding",
                verification_rules_applied=["redirect_analysis"],
            )
        
        # Out of scope redirect
        if "out-of-scope" in finding.finding_id.lower() or finding.category == "ScopeViolation":
            return VerificationResult(
                state=VerificationState.VERIFIED,
                confidence=0.9,
                reason=f"Redirect leads outside authorized scope: {finding.description}",
                evidence_summary={"from": evidence.get("from"), "to": evidence.get("to"), 
                                "reason": finding.evidence.get("reason", "")},
                verification_rules_applied=["redirect_analysis", "scope_validation"],
                metadata={"validator": "redirect_validator"}
            )
        
        # Prohibited IP in redirect
        if "prohibited-ip" in finding.finding_id.lower():
            return VerificationResult(
                state=VerificationState.VERIFIED,
                confidence=0.95,
                reason=f"Redirect resolves to prohibited IP: {finding.description}",
                evidence_summary={"url": evidence.get("url"), "ip": finding.evidence.get("ip"),
                                "reason": finding.evidence.get("reason")},
                verification_rules_applied=["redirect_analysis", "network_safety"],
                metadata={"validator": "redirect_validator"}
            )
        
        # Long redirect chain
        if "long-chain" in finding.finding_id.lower():
            return VerificationResult(
                state=VerificationState.VERIFIED,
                confidence=0.8,
                reason=f"Redirect chain exceeds recommended length: {finding.description}",
                evidence_summary={"chain": finding.evidence.get("chain", [])},
                verification_rules_applied=["redirect_analysis"],
                metadata={"validator": "redirect_validator"}
            )
        
        # Missing location header
        if "missing-location" in finding.finding_id.lower():
            return VerificationResult(
                state=VerificationState.VERIFIED,
                confidence=0.7,
                reason=f"Redirect response missing Location header: {finding.description}",
                evidence_summary={"url": evidence.get("url"), "status": evidence.get("status")},
                verification_rules_applied=["redirect_analysis"],
                metadata={"validator": "redirect_validator"}
            )
        
        return VerificationResult(
            state=VerificationState.INCONCLUSIVE,
            confidence=0.5,
            reason="Redirect observation recorded",
            verification_rules_applied=["redirect_analysis"],
            metadata={"validator": "redirect_validator"}
        )


class TLSVerificationRule(VerificationRule):
    """Verification rules for TLS/SSL findings."""
    
    def __init__(self):
        super().__init__(
            "tls_configuration",
            "TLS Configuration Verification",
            "Verifies TLS certificate and configuration findings"
        )
    
    def evaluate(self, finding: Finding, evidence: Dict[str, Any], 
                 context: Dict[str, Any]) -> VerificationResult:
        if finding.category != "TLS" and finding.category != "TransportSecurity":
            return VerificationResult(
                state=VerificationState.INCONCLUSIVE,
                confidence=0.5,
                reason="Not a TLS configuration finding",
                verification_rules_applied=["tls_configuration"],
            )
        
        # Certificate expired
        if "expired" in finding.finding_id.lower() or "expired" in finding.description.lower():
            days_left = evidence.get("days_left", 0)
            if days_left < 0:
                return VerificationResult(
                    state=VerificationState.VERIFIED,
                    confidence=0.95,
                    reason=f"Certificate expired {abs(evidence.get('days_left', 0))} days ago",
                    evidence_summary={"expires": evidence.get("expires"), 
                                    "days_expired": abs(evidence.get("days_left", 0))},
                    verification_rules_applied=["tls_configuration"],
                    metadata={"validator": "tls_validator"}
                )
            elif evidence.get("days_left", 100) < 30:
                return VerificationResult(
                    state=VerificationState.VERIFIED,
                    confidence=0.9,
                    reason=f"Certificate expires in {evidence.get('days_left', 'unknown')} days",
                    evidence_summary={"expires": evidence.get("expires"), 
                                    "days_left": evidence.get("days_left")},
                    verification_rules_applied=["tls_configuration"],
                    metadata={"validator": "tls_validator"}
                )
        
        # Hostname mismatch
        if "hostname-mismatch" in finding.finding_id.lower() or "mismatch" in finding.description.lower():
            return VerificationResult(
                state=VerificationState.VERIFIED,
                confidence=0.95,
                reason="Certificate hostname mismatch - certificate doesn't match target hostname",
                evidence_summary={"host": evidence.get("host"), "san": evidence.get("SAN", []),
                                "subject": evidence.get("subject")},
                verification_rules_applied=["tls_configuration"],
                metadata={"validator": "tls_validator"}
            )
        
        # SSL/TLS handshake errors
        if "ssl-error" in finding.finding_id.lower() or "tls-error" in finding.finding_id.lower():
            return VerificationResult(
                state=VerificationState.VERIFIED,
                confidence=0.8,
                reason=f"SSL/TLS handshake error: {finding.description}",
                evidence_summary={"error": finding.evidence.get("error", "unknown")},
                verification_rules_applied=["tls_configuration"],
                metadata={"validator": "tls_validator"}
            )
        
        return VerificationResult(
            state=VerificationState.INCONCLUSIVE,
            confidence=0.5,
            reason="TLS observation recorded",
            verification_rules_applied=["tls_configuration"],
            metadata={"validator": "tls_validator"}
        )


class RedirectVerificationRule(VerificationRule):
    """Verification rules for redirect findings - alias for RedirectVerificationRule."""
    
    def __init__(self):
        super().__init__(
            "redirect_analysis",
            "Redirect Analysis Verification",
            "Verifies redirect chain findings"
        )
    
    def evaluate(self, finding: Finding, evidence: Dict[str, Any], 
                 context: Dict[str, Any]) -> VerificationResult:
        # Delegate to RedirectVerificationRule
        rule = RedirectVerificationRule()
        return rule.evaluate(finding, evidence, context)


class CookieSecurityVerificationRule(VerificationRule):
    """Verification rules for cookie security findings."""
    
    def __init__(self):
        super().__init__(
            "cookie_security",
            "Cookie Security Verification",
            "Verifies cookie security attribute findings"
        )
    
    def evaluate(self, finding: Finding, evidence: Dict[str, Any], 
                 context: Dict[str, Any]) -> VerificationResult:
        # Already handled by HeaderBehaviorVerificationRule
        return VerificationResult(
            state=VerificationState.INCONCLUSIVE,
            confidence=0.5,
            reason="Cookie security findings verified by HeaderBehaviorVerificationRule",
            verification_rules_applied=["cookie_security"],
            metadata={"validator": "cookie_security"}
        )


class InformationDisclosureVerificationRule(VerificationRule):
    """Verification rules for information disclosure findings - alias."""
    
    def __init__(self):
        super().__init__(
            "information_disclosure",
            "Information Disclosure Verification",
            "Verifies information disclosure findings"
        )
    
    def evaluate(self, finding: Finding, evidence: Dict[str, Any], 
                 context: Dict[str, Any]) -> VerificationResult:
        rule = InformationDisclosureVerificationRule()
        return rule.evaluate(finding, evidence, context)


# Registry of all verification rules
VERIFICATION_RULES: Dict[str, VerificationRule] = {
    "input_validation": InputValidationVerificationRule(),
    "header_behavior": HeaderBehaviorVerificationRule(),
    "cookie_security": CookieSecurityVerificationRule(),
    "information_disclosure": InformationDisclosureVerificationRule(),
    "redirect_analysis": RedirectVerificationRule(),
    "tls_configuration": TLSVerificationRule(),
    "redirect_analysis": RedirectVerificationRule(),
    "cookie_security": CookieSecurityVerificationRule(),
    "information_disclosure": InformationDisclosureVerificationRule(),
    "tls_configuration": TLSVerificationRule(),
}


def get_verification_rule(validator_id: str) -> Optional[VerificationRule]:
    """Get the verification rule for a validator."""
    # Map validator IDs to rule IDs
    validator_to_rule = {
        "https_validator": "header_behavior",
        "security_headers_validator": "header_behavior",
        "cookie_security_validator": "cookie_security",
        "information_disclosure_validator": "information_disclosure",
        "redirect_validator": "redirect_analysis",
        "tls_validator": "tls_configuration",
        "input_validation_validator": "input_validation",
        "security_headers_validator": "header_behavior",
        "cookie_security_validator": "cookie_security",
        "information_disclosure_validator": "information_disclosure",
        "redirect_validator": "redirect_analysis",
        "tls_validator": "tls_configuration",
    }
    rule_id = validator_to_rule.get(validator_id)
    if rule_id:
        return VERIFICATION_RULES.get(rule_id)
    return None


class FindingVerifier:
    """
    Central finding verification engine.
    
    Evaluates findings against verification rules to determine
    verification state, confidence, and severity.
    """
    
    def __init__(self):
        self.rules = VERIFICATION_RULES
    
    def verify_finding(self, finding: Finding, evidence: Dict[str, Any], 
                       context: Dict[str, Any]) -> VerificationResult:
        """
        Verify a single finding against applicable rules.
        """
        # Get the appropriate verification rule
        rule = get_verification_rule(finding.source)
        if rule is None:
            # Default: inconclusive for unknown validators
            return VerificationResult(
                state=VerificationState.INCONCLUSIVE,
                confidence=0.5,
                reason=f"No verification rule for validator: {finding.source}",
                evidence_summary={"validator": finding.source},
                verification_rules_applied=[],
                metadata={"validator": finding.source}
            )
        
        # Build context
        context = {
            "run_id": finding.run_id if hasattr(finding, 'run_id') else None,
            "validator_id": finding.source,
            "finding_type": finding.category,
        }
        
        # Evaluate using the appropriate rule
        return rule.evaluate(finding, finding.evidence or {}, {})
    
    def verify_findings(self, findings: List[Finding], 
                        evidence_map: Dict[str, Dict[str, Any]],
                        context: Dict[str, Any]) -> List[Finding]:
        """
        Verify a batch of findings and update their verification state.
        
        Updates finding metadata with verification results.
        """
        verified_findings = []
        
        for finding in findings:
            evidence = evidence_map.get(finding.finding_id, finding.evidence or {})
            result = self.verify_finding(finding, evidence, context)
            
            # Update finding metadata with verification results
            finding.metadata = finding.metadata or {}
            finding.metadata.update({
                "verification_state": result.state.value,
                "verification_confidence": result.confidence,
                "verification_reason": result.reason,
                "verification_rules": result.verification_rules_applied,
                "verification_evidence": result.evidence_summary,
                "verified_at": datetime.utcnow().isoformat(),
            }
            
            # Update confidence if suggested
            if result.suggested_confidence is not None:
                finding.confidence = result.suggested_confidence
            
            # Update severity if suggested
            if result.suggested_severity is not None:
                finding.severity = result.suggested_severity
            
            # Add verification state to finding
            finding.verification_state = result.state.value
            
            verified_findings.append(finding)
        
        return verified_findings


# Global verifier instance
_verifier = FindingVerifier()


def verify_findings(findings: List[Finding], 
                   evidence_map: Dict[str, Dict[str, Any]],
                   context: Dict[str, Any]) -> List[Finding]:
    """Convenience function to verify findings using the global verifier."""
    return _verifier.verify_findings(findings, evidence_map, context)


def get_verification_rule(validator_id: str):
    """Get verification rule for a validator."""
    return get_verification_rule(validator_id)