"""
Input Validation Validator – Active check for input validation behavior.

This validator tests how the application handles various input types at
configured test endpoints without using malicious payloads.
"""

from __future__ import annotations

from typing import List, Dict, Any
import requests

from agentqe.interfaces import Finding
from agentqe.security.validators.base import BaseValidator, ValidationContext
from agentqe.security.active_testing_profiles import get_profile_limits


class InputValidationValidator(BaseValidator):
    validator_id = "input_validation_validator"
    name = "Input Validation Behavior"
    description = "Tests how the application handles various input types at configured endpoints"

    def __init__(self):
        super().__init__()
        # Test cases for input validation - non-destructive
        self.test_cases = [
            {
                "name": "empty_input",
                "description": "Empty input field",
                "payload": "",
                "expected_behavior": "Should reject or handle gracefully",
            },
            {
                "name": "whitespace_only",
                "description": "Whitespace-only input",
                "payload": "   ",
                "expected_behavior": "Should reject or trim",
            },
            {
                "name": "long_input",
                "description": "Input exceeding typical length limits",
                "payload": "x" * 5000,
                "expected_behavior": "Should reject or truncate",
            },
            {
                "name": "special_chars",
                "description": "Special characters that are not executable",
                "payload": "!@#$%^&*()_+-=[]{}|;':\",./<>?",
                "expected_behavior": "Should reject or sanitize",
            },
            {
                "name": "unicode_input",
                "description": "Unicode characters",
                "payload": "测试 🔒 🛡️ αβγ",
                "expected_behavior": "Should handle or reject",
            },
            {
                "name": "null_bytes",
                "description": "Null bytes in input",
                "payload": "test\x00input",
                "expected_behavior": "Should reject or handle safely",
            },
            {
                "name": "sql_like",
                "description": "SQL-like patterns (non-executable)",
                "payload": "' OR '1'='1",
                "expected_behavior": "Should reject or treat as literal",
            },
            {
                "name": "script_like",
                "description": "Script-like patterns (non-executable)",
                "payload": "<script>alert(1)</script>",
                "expected_behavior": "Should reject or escape",
            },
        ]

    def check(self, ctx: ValidationContext) -> List[Finding]:
        findings: List[Finding] = []
        target = ctx.normalized_target

        # Get test endpoints from context metadata
        test_endpoints = ctx.scope.get("test_endpoints", {})
        input_endpoints = test_endpoints.get("input_fields", [])

        if not input_endpoints:
            # No configured input endpoints - skip with informational finding
            findings.append(Finding(
                finding_id=f"{self.validator_id}-no-endpoints",
                category="InputValidation",
                severity="Informational",
                description="No input endpoints configured for active testing. Configure test_endpoints.input_fields in scope to enable input validation checks.",
                evidence={"scope": ctx.scope},
                source=self.validator_id,
                metadata={"check_type": "active", "skipped": True},
            ))
            return findings

        # Get profile limits for request budget
        limits = get_profile_limits("safe_active")
        max_requests = limits.get("max_requests_per_second", 3)

        # Test each input endpoint
        for endpoint_config in input_endpoints:
            endpoint_url = endpoint_config.get("url")
            field_name = endpoint_config.get("field_name", "input")
            method = endpoint_config.get("method", "POST")
            content_type = endpoint_config.get("content_type", "application/x-www-form-urlencoded")

            if not endpoint_url:
                continue

            # Resolve relative URL
            if endpoint_url.startswith("/"):
                from urllib.parse import urljoin
                endpoint_url = requests.compat.urljoin(ctx.normalized_target, endpoint_url)

            # Test each validation case
            for test_case in self.test_cases:
                try:
                    payload = {field_name: test_case["payload"]}
                    
                    if method.upper() == "POST":
                        if content_type == "application/json":
                            resp = requests.post(endpoint_url, json=payload, timeout=10, verify=True)
                        else:
                            resp = requests.post(endpoint_url, data=payload, timeout=10, verify=True)
                    else:
                        resp = requests.get(endpoint_url, params=payload, timeout=10, verify=True)

                    # Analyze response
                    finding = self._analyze_response(
                        ctx, test_case, endpoint_url, field_name, resp, content_type
                    )
                    if finding:
                        findings.append(finding)

                except requests.RequestException as exc:
                    findings.append(Finding(
                        finding_id=f"{self.validator_id}-request-error-{test_case['name']}",
                        category="InputValidation",
                        severity="Low",
                        description=f"Request failed for {test_case['name']}: {exc}",
                        evidence={"url": endpoint_url, "error": str(exc)},
                        source=self.validator_id,
                        metadata={"check_type": "active", "error": True},
                    ))

        return findings

    def _analyze_response(self, ctx: ValidationContext, test_case: Dict[str, Any], 
                         url: str, field_name: str, resp: requests.Response,
                         content_type: str) -> Finding | None:
        """Analyze the response for input validation behavior."""
        status = resp.status_code
        content = resp.text[:2000] if resp.text else ""
        headers = dict(resp.headers)

        # Check for various validation behaviors
        issues = []

        # Check if server error (5xx) - might indicate poor input handling
        if 500 <= status < 600:
            issues.append({
                "type": "server_error",
                "severity": "Medium",
                "description": f"Server error ({status}) for {test_case['description']}",
                "evidence": {"status": status, "content_preview": content[:200]}
            })

        # Check for stack traces in response
        if any(keyword in content.lower() for keyword in ["stack trace", "traceback", "exception", "error at line"]):
            issues.append({
                "type": "stack_trace_exposure",
                "severity": "High",
                "description": f"Stack trace exposed in response for {test_case['description']}",
                "evidence": {"content_preview": content[:500]}
            })

        # Check for SQL errors
        if any(keyword in content.lower() for keyword in ["sql syntax", "mysql error", "postgresql error", "sqlite error", "ora-", "syntax error"]):
            issues.append({
                "type": "sql_error_exposure",
                "severity": "High",
                "description": f"SQL error exposed in response for {test_case['description']}",
                "evidence": {"content_preview": content[:500]}
            })

        # Check if input was reflected unsafely
        payload_lower = test_case["payload"].lower()
        if payload_lower in content.lower() and test_case["payload"]:
            # Check if it's in a safe context (like error message showing rejected input)
            if "error" not in content.lower() and "invalid" not in content.lower():
                issues.append({
                    "type": "input_reflection",
                    "severity": "Medium",
                    "description": f"Input reflected in response without clear rejection for {test_case['description']}",
                    "evidence": {"payload": test_case["payload"][:100], "context": content[:200]}
                })

        # Check for successful validation (expected behavior)
        validation_indicators = ["invalid", "invalid input", "validation failed", "validation error", 
                                "must be", "required", "exceeds", "too long", "not allowed"]
        has_validation = any(indicator in content.lower() for indicator in validation_indicators)

        if not issues and not has_validation and status == 200:
            # Request succeeded without clear validation - could be missing validation
            issues.append({
                "type": "potential_missing_validation",
                "severity": "Low",
                "description": f"Input accepted without clear validation for {test_case['description']}",
                "evidence": {"status": status, "payload": test_case["payload"][:100]}
            })

        if issues:
            # Create finding with highest severity issue
            max_severity = max(i["severity"] for i in issues)
            return Finding(
                finding_id=f"{self.validator_id}-{test_case['name']}",
                category="InputValidation",
                severity=max_severity,
                description=f"Input validation issue for {test_case['description']}: {', '.join(i['description'] for i in issues)}",
                evidence={
                    "url": url,
                    "field": field_name,
                    "test_case": test_case["name"],
                    "payload": test_case["payload"][:100],
                    "status": status,
                    "issues": issues,
                    "response_preview": content[:500]
                },
                source=self.validator_id,
                metadata={"check_type": "active"}
            )

        return None