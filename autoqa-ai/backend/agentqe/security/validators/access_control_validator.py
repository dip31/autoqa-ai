"""
Access Control Validator – Active verification of authorization boundaries.

This validator tests access control using designated test identities and
explicitly approved test resources.
"""

from __future__ import annotations

from typing import List, Dict, Any
import requests

from agentqe.interfaces import Finding
from agentqe.security.validators.base import BaseValidator, ValidationContext
from agentqe.security.active_testing_profiles import get_profile_limits


class AccessControlValidator(BaseValidator):
    validator_id = "access_control_validator"
    name = "Access Control Verification"
    description = "Verifies authorization boundaries using designated test identities and test resources"

    def __init__(self):
        super().__init__()
        # Test scenarios for access control
        self.test_scenarios = [
            {
                "name": "anonymous_access_protected",
                "description": "Anonymous access to protected test resource",
                "requires_auth": False,
                "expect_denied": True,
            },
            {
                "name": "authenticated_access_own",
                "description": "Authenticated access to own test resource",
                "requires_auth": True,
                "expect_denied": False,
            },
            {
                "name": "cross_user_access_denied",
                "description": "Access by second test identity to restricted resource",
                "requires_auth": True,
                "as_different_user": True,
                "expect_denied": True,
            },
        ]

    def check(self, ctx: ValidationContext) -> List[Finding]:
        findings: List[Finding] = []

        # Get test resources from context metadata
        test_resources = ctx.scope.get("test_resources", {})
        access_control_config = test_resources.get("access_control", {})

        if not access_control_config:
            # No configured access control resources
            findings.append(Finding(
                finding_id=f"{self.validator_id}-no-config",
                category="AccessControl",
                severity="Informational",
                description="No access control test resources configured. Configure test_resources.access_control in scope to enable access control checks.",
                evidence={"scope": ctx.scope},
                source=self.validator_id,
                metadata={"check_type": "active", "skipped": True},
            ))
            return findings

        # Get test credentials from context
        test_users = ctx.scope.get("test_users", [])
        if len(test_users) < 2:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-insufficient-users",
                category="AccessControl",
                severity="Informational",
                description="Insufficient test users configured for cross-user access testing (need at least 2)",
                evidence={"test_users_count": len(test_users)},
                source=self.validator_id,
                metadata={"check_type": "active", "skipped": True},
            ))

        # Get test resources
        test_resources_list = access_control_config.get("test_resources", [])
        if not test_resources_list:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-no-resources",
                category="AccessControl",
                severity="Informational",
                description="No test resources defined for access control testing",
                evidence={"access_control_config": access_control_config},
                source=self.validator_id,
                metadata={"check_type": "active", "skipped": True},
            ))
            return findings

        # Get credentials for test users
        test_creds = ctx.scope.get("test_credentials", {})

        # Run access control scenarios
        for scenario in self.test_scenarios:
            findings.extend(self._run_scenario(ctx, scenario, test_creds, test_resources_list))

        return findings

    def _run_scenario(self, ctx: ValidationContext, scenario: Dict[str, Any],
                     test_creds: Dict[str, Any], test_resources: List[Dict[str, Any]]) -> List[Finding]:
        findings: List[Finding] = []

        for resource in test_resources:
            resource_url = resource.get("url")
            resource_owner = resource.get("owner")  # user_id who owns this resource
            resource_id = resource.get("id", "unknown")

            if not resource_url:
                continue

            # Resolve URL
            from urllib.parse import urljoin
            if resource_url.startswith("/"):
                resource_url = requests.compat.urljoin(ctx.normalized_target, resource_url)

            # Determine credentials to use
            if scenario["requires_auth"]:
                if scenario.get("as_different_user"):
                    # Use a different user's credentials
                    cred_key = f"user_2"  # Assume second test user
                else:
                    # Use owner's credentials
                    cred_key = f"user_{resource_owner}"
                
                credentials = test_creds.get(cred_key)
                if not credentials:
                    findings.append(Finding(
                        finding_id=f"{self.validator_id}-{scenario['name']}-missing-creds",
                        category="AccessControl",
                        severity="Informational",
                        description=f"Missing credentials for {scenario['name']} test",
                        evidence={"scenario": scenario["name"], "resource": resource_id},
                        source=self.validator_id,
                        metadata={"check_type": "active", "skipped": True},
                    ))
                    continue
            else:
                credentials = None

            # Execute the test
            for test_resource in test_resources:
                test_url = test_resource.get("url")
                if not test_url:
                    continue
                if test_url.startswith("/"):
                    test_url = requests.compat.urljoin(ctx.normalized_target, test_url)

                try:
                    headers = {}
                    cookies = {}
                    if credentials:
                        # Authenticate and get session
                        auth_resp = self._authenticate(ctx.normalized_target, credentials)
                        if auth_resp and auth_resp.cookies:
                            cookies = auth_resp.cookies.get_dict()

                    resp = requests.get(test_url, timeout=10, cookies=cookies, verify=True)
                    
                    finding = self._evaluate_access(
                        ctx, scenario, test_resource, resp, credentials is not None
                    )
                    if finding:
                        findings.append(finding)

                except requests.RequestException as exc:
                    findings.append(Finding(
                        finding_id=f"{self.validator_id}-{scenario['name']}-error",
                        category="AccessControl",
                        severity="Low",
                        description=f"Request failed for {scenario['name']}: {exc}",
                        evidence={"url": test_url, "error": str(exc)},
                        source=self.validator_id,
                        metadata={"check_type": "active", "error": True},
                    ))

        return findings

    def _authenticate(self, base_url: str, credentials: Dict[str, Any]) -> requests.Response:
        """Authenticate and return response with cookies."""
        # Try common login endpoints
        login_urls = ["/login", "/auth/login", "/signin", "/api/auth/login"]
        
        for login_url in login_urls:
            from urllib.parse import urljoin
            full_url = requests.compat.urljoin(base_url, login_url)
            try:
                resp = requests.post(full_url, json=credentials, timeout=10, verify=True)
                if resp.status_code == 200 and resp.cookies:
                    return resp
            except requests.RequestException:
                continue
        return requests.Response()  # Empty response

    def _evaluate_access(self, ctx: ValidationContext, scenario: Dict[str, Any],
                        resource: Dict[str, Any], resp: requests.Response,
                        authenticated: bool) -> Finding | None:
        status = resp.status_code
        resource_id = resource.get("id", "unknown")
        resource_url = resource.get("url", "")
        expect_denied = scenario.get("expect_denied", False)

        # Determine if access was granted
        access_granted = status == 200

        # Check for unexpected access
        if expect_denied and access_granted:
            return Finding(
                finding_id=f"{self.validator_id}-{scenario['name']}-{resource.get('id', 'unknown')}",
                category="AccessControl",
                severity="High",
                description=f"{scenario['description']}: Access GRANTED but should be DENIED",
                evidence={
                    "scenario": scenario["name"],
                    "resource_id": resource.get("id"),
                    "resource_url": resource.get("url"),
                    "status_code": status,
                    "authenticated": authenticated,
                    "expected": "denied",
                    "actual": "granted",
                },
                source=self.validator_id,
                metadata={"check_type": "active", "scenario": scenario["name"]},
            )

        # Check for unexpected denial
        if not expect_denied and not access_granted:
            return Finding(
                finding_id=f"{self.validator_id}-{scenario['name']}-{resource.get('id', 'unknown')}-denied",
                category="AccessControl",
                severity="Medium",
                description=f"{scenario['description']}: Access DENIED but should be GRANTED",
                evidence={
                    "scenario": scenario["name"],
                    "resource_id": resource.get("id"),
                    "resource_url": resource.get("url"),
                    "status_code": status,
                    "authenticated": authenticated,
                    "expected": "granted",
                    "actual": "denied",
                },
                source=self.validator_id,
                metadata={"check_type": "active", "scenario": scenario["name"]},
            )

        # Access as expected
        return Finding(
            finding_id=f"{self.validator_id}-{scenario['name']}-{resource.get('id', 'unknown')}-ok",
            category="AccessControl",
            severity="Informational",
            description=f"{scenario['description']}: Access as expected ({'granted' if access_granted else 'denied'})",
            evidence={
                "scenario": scenario["name"],
                "resource_id": resource.get("id"),
                "resource_url": resource.get("url"),
                "status_code": status,
                "authenticated": authenticated,
            },
            source=self.validator_id,
                metadata={"check_type": "active", "scenario": scenario["name"]},
        )