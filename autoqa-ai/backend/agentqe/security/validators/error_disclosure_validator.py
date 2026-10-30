"""
Error Handling and Information Disclosure Validator – Active verification.

This validator tests error handling behavior using safe, invalid requests
against configured test routes.
"""

from __future__ import annotations

from typing import List, Dict, Any
import requests

from agentqe.interfaces import Finding
from agentqe.security.validators.base import BaseValidator, ValidationContext


class ErrorDisclosureValidator(BaseValidator):
    validator_id = "error_disclosure_validator"
    name = "Error Handling & Information Disclosure"
    description = "Verifies error handling behavior using safe, invalid requests"

    def __init__(self):
        super().__init__()
        self.test_cases = [
            {
                "name": "malformed_json",
                "description": "Malformed JSON body",
                "method": "POST",
                "content_type": "application/json",
                "body": "{ invalid json }",
                "expected_status": [400, 422],
            },
            {
                "name": "missing_required_field",
                "description": "Missing required JSON field",
                "method": "POST",
                "content_type": "application/json",
                "body": "{}",
                "expected_status": [400, 422],
            },
            {
                "name": "wrong_content_type",
                "description": "Unsupported content type",
                "method": "POST",
                "content_type": "application/xml",
                "body": "<test>data</test>",
                "expected_status": [400, 415],
            },
            {
                "name": "invalid_query_param",
                "description": "Invalid query parameter value",
                "method": "GET",
                "params": {"id": "not-a-number"},
                "expected_status": [400, 422],
            },
            {
                "name": "oversized_body",
                "description": "Oversized request body",
                "method": "POST",
                "content_type": "application/json",
                "body": "x" * 100000,
                "expected_status": [413, 400, 422],
            },
            {
                "name": "unsupported_method",
                "description": "HTTP method not allowed",
                "method": "PATCH",
                "expected_status": [405],
            },
            {
                "name": "invalid_path_param",
                "description": "Invalid path parameter",
                "method": "GET",
                "path_suffix": "/invalid/path/that/does/not/exist",
                "expected_status": [404],
            },
        ]

    def check(self, ctx: ValidationContext) -> List[Finding]:
        findings: List[Finding] = []

        # Get test endpoints from context
        test_endpoints = ctx.scope.get("test_endpoints", {})
        error_endpoints = test_endpoints.get("error_handling", [])

        if not error_endpoints:
            # Use base target for generic error testing
            error_endpoints = [{"url": ctx.normalized_target, "methods": ["GET", "POST"]}]

        for endpoint in error_endpoints:
            base_url = endpoint.get("url", ctx.normalized_target)
            allowed_methods = endpoint.get("methods", ["GET", "POST"])

            for test_case in self.test_cases:
                if test_case["method"] not in allowed_methods:
                    continue

                findings = self._run_test_case(ctx, base_url, test_case)
                findings.extend(findings)

        return findings

    def _run_test_case(self, ctx: ValidationContext, base_url: str, 
                       test_case: Dict[str, Any]) -> List[Finding]:
        findings: List[Finding] = []

        try:
            method = test_case["method"]
            url = base_url
            headers = {"Content-Type": test_case.get("content_type", "application/json")}
            params = test_case.get("params", {})
            body = test_case.get("body", None)
            path_suffix = test_case.get("path_suffix", "")

            if path_suffix:
                url = requests.compat.urljoin(base_url, path_suffix)

            if method == "GET":
                resp = requests.get(url, params=params, timeout=10, verify=True)
            elif method == "POST":
                if test_case.get("content_type") == "application/json":
                    resp = requests.post(url, json=body, timeout=10, verify=True, headers=headers)
                else:
                    resp = requests.post(url, data=body, timeout=10, verify=True, headers=headers)
            elif method == "PATCH":
                resp = requests.patch(url, json=body, timeout=10, verify=True, headers=headers)
            else:
                return [Finding(
                    finding_id=f"{self.validator_id}-unsupported-method",
                    category="ErrorHandling",
                    severity="Informational",
                    description=f"Unsupported method {method} for test",
                    evidence={"method": method},
                    source=self.validator_id,
                    metadata={"check_type": "active", "skipped": True},
                )]

            return self._analyze_error_response(ctx, test_case, resp, url)

        except requests.RequestException as exc:
            return [Finding(
                finding_id=f"{self.validator_id}-{test_case['name']}-request-error",
                category="ErrorHandling",
                severity="Low",
                description=f"Request failed for {test_case['name']}: {exc}",
                evidence={"url": base_url, "error": str(exc)},
                source=self.validator_id,
                metadata={"check_type": "active", "error": True},
            )]

    def _analyze_error_response(self, ctx: ValidationContext, test_case: Dict[str, Any],
                               resp: requests.Response, url: str) -> List[Finding]:
        findings: List[Finding] = []
        status = resp.status_code
        content = resp.text[:3000] if resp.text else ""
        content_lower = content.lower()

        # Check if status matches expected
        expected_statuses = test_case.get("expected_status", [])
        status_ok = status in expected_statuses

        issues = []

        # Check for information disclosure in error responses
        if status >= 400:
            # Check for stack traces
            stack_indicators = [
                "traceback", "stack trace", "at line", "file \"", "line ",
                "exception:", "error:", "throw", "catch", "finally",
                "stacktrace", "backtrace"
            ]
            for indicator in stack_indicators:
                if indicator in content_lower:
                    return [Finding(
                        finding_id=f"{self.validator_id}-stack-trace-{test_case['name']}",
                        category="InformationDisclosure",
                        severity="High",
                        description=f"Stack trace exposed in error response for {test_case['description']}",
                        evidence={
                            "url": url,
                            "status": status,
                            "indicator": indicator,
                            "content_preview": content[:500]
                        },
                        source=self.validator_id,
                        metadata={"check_type": "active", "test_case": test_case["name"]},
                    )]

            # Check for sensitive information
            sensitive_patterns = [
                "password", "secret", "token", "api_key", "apikey",
                "access_token", "refresh_token", "private_key", "secret_key",
                "database", "connection", "jdbc:", "mongodb://", "redis://",
                "aws_", "azure_", "gcp_", "secret", "credential"
            ]
            for pattern in sensitive_patterns:
                if pattern in content_lower:
                    return [Finding(
                        finding_id=f"{self.validator_id}-secret-leak-{test_case['name']}",
                        category="InformationDisclosure",
                        severity="Critical",
                        description=f"Potential secret leaked in error response for {test_case['description']}",
                        evidence={
                            "url": url,
                            "status": status,
                            "pattern": pattern,
                            "content_preview": content[:500]
                        },
                        source=self.validator_id,
                        metadata={"check_type": "active", "test_case": test_case["name"]},
                    )]

            # Check for internal paths
            import re
            path_matches = re.findall(r'/(?:home|var|opt|usr|etc|tmp|root)/[\w/\.-]+', content)
            if path_matches:
                return [Finding(
                    finding_id=f"{self.validator_id}-path-disclosure-{test_case['name']}",
                    category="InformationDisclosure",
                    severity="Medium",
                    description=f"Internal filesystem path disclosed in error for {test_case['description']}",
                    evidence={"url": url, "paths": path_matches[:5]},
source=self.validator_id,
                        metadata={"check_type": "active", "test_case": test_case["name"]},
                    )]

            # Check for framework/version disclosure
            framework_indicators = {
                "django": ["django", "csrfmiddlewaretoken"],
                "flask": ["flask", "werkzeug", "jinja2"],
                "express": ["express", "x-powered-by: express"],
                "spring": ["spring", "dispatcherservlet", "org.springframework"],
                "asp.net": ["asp.net", "x-aspnet-version", "x-aspnetmvc-version"],
                "rails": ["rails", "action_controller", "active_record"],
                "laravel": ["laravel", "illuminate\\"],
            }

            for framework, indicators in framework_indicators.items():
                if any(ind in content_lower for ind in indicators):
                    return [Finding(
                        finding_id=f"{self.validator_id}-framework-disclosure-{test_case['name']}",
                        category="InformationDisclosure",
                        severity="Low",
                        description=f"Framework ({framework}) disclosed in error response for {test_case['description']}",
                        evidence={"url": url, "framework": framework, "status": status},
source=self.validator_id,
                        metadata={"check_type": "active", "test_case": test_case["name"]},
                    )]

        # Check for successful response when error expected
        if not status_ok and status >= 400:
            return [Finding(
                finding_id=f"{self.validator_id}-unexpected-status-{test_case['name']}",
                category="ErrorHandling",
                severity="Low",
                description=f"Expected status {expected_statuses} but got {status} for {test_case['description']}",
                evidence={"url": url, "expected": expected_statuses, "actual": status},
source=self.validator_id,
                        metadata={"check_type": "active", "test_case": test_case["name"]},
                    )]

        # Check for generic error page vs detailed error
        if status >= 400 and len(content) > 5000:
            return [Finding(
                finding_id=f"{self.validator_id}-verbose-error-{test_case['name']}",
                category="ErrorHandling",
                severity="Medium",
                description=f"Verbose error page for {test_case['description']} - may leak implementation details",
                evidence={"url": url, "status": status, "content_length": len(content)},
source=self.validator_id,
                        metadata={"check_type": "active", "test_case": test_case["name"]},
                    )]

        return []